"""Read-only, declared diagnostics for the frozen v5 Nepal confrontation."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from run_aligned_predictive_competition import frozen_core, sha256, validate_member

PROGRAM = ROOT / "studies/research_program"


def auc(y, scores):
    y = np.asarray(y, dtype=int)
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    positive, negative = int(y.sum()), int((1 - y).sum())
    if not positive or not negative:
        return None
    return float((ranks[y == 1].sum() - positive * (positive + 1) / 2) / (positive * negative))


def aligned_frames(old, new):
    keys = ["district_id", "week_start"]
    if old.duplicated(keys).any() or new.duplicated(keys).any():
        raise ValueError("duplicate historical cells")
    old, new = (frame.sort_values(keys).reset_index(drop=True) for frame in (old, new))
    identity = keys + ["split", "observed_active"]
    if not old[identity].equals(new[identity]):
        raise ValueError("historical rows, targets, or splits changed")
    simple = [c for c in old if c not in identity and not c.startswith("pineland_")]
    if set(simple) != {c for c in new if c not in identity and not c.startswith("pineland_")}:
        raise ValueError("simple competitor set changed")
    if not np.allclose(old[simple], new[simple], rtol=0, atol=1e-12):
        raise ValueError("simple competitor predictions changed")
    return old, new


def control_signal(run, panel, locality_district):
    axes = ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")
    checkpoints = sorted(run["checkpoints"], key=lambda c: c["time"])
    times = np.array([c["time"] for c in checkpoints])
    values = []
    for checkpoint in checkpoints:
        district = {}
        for locality, actors in checkpoint["control"].items():
            value = sum(actors["insurgent"][a] - actors["government"][a] for a in axes) / len(axes)
            district.setdefault(locality_district[locality], []).append(value)
        values.append({d: float(np.mean(v)) for d, v in district.items()})
    days = (pd.to_datetime(panel.week_start) - pd.Timestamp("2001-11-26")).dt.days
    indices = np.searchsorted(times, days, side="right") - 1
    if (indices < 0).any():
        raise ValueError("missing prior checkpoint")
    return np.array([values[i][d] for i, d in zip(indices, panel.district_id)])


def main():
    execution = PROGRAM / "historical_revalidation_v5/execution_contract.json"
    model, diff = frozen_core(execution)
    old_dir, new_dir = (PROGRAM / f"predictive_competition/nepal_{v}" for v in ("v4", "v5"))
    decision = json.loads((new_dir / "decision.json").read_text())
    if not decision["ensemble_complete"] or not decision["final_historical_stage"]:
        raise ValueError("full frozen ensemble required")
    for directory in (old_dir, new_dir):
        manifest = json.loads((directory / "manifest.json").read_text())
        for name in ("aligned_predictions", "scores", "decision"):
            suffix = "json" if name == "decision" else "csv"
            if sha256(directory / f"{name}.{suffix}") != manifest[f"{name}_sha256"]:
                raise ValueError(f"competition artifact drift: {directory.name}/{name}")
    old, new = aligned_frames(pd.read_csv(old_dir / "aligned_predictions.csv"),
                              pd.read_csv(new_dir / "aligned_predictions.csv"))
    study = ROOT / "studies/nepal_2001_2006"
    case = json.loads((study / "config/case_environment_repaired.json").read_text())
    mapping = {row["locality_id"]: row["district_id"] for row in case["localities"]}
    files = sorted((study / "runs/post_structural_repair/final_empirical_rescore_v5").glob("seed_*_agents_750.json"))
    if len(files) != 8:
        raise ValueError("exactly eight frozen seeds required")
    signals, funnels, seeds = [], [], []
    for path in files:
        run = validate_member(path, model, diff)
        seeds.append(run["seed"])
        signals.append(control_signal(run, new, mapping))
        funnels.append({"seed": run["seed"], "counts": run["action_funnel_counts"]})
    if seeds != json.loads(execution.read_text())["nepal_seeds"]:
        raise ValueError("seed identities differ from execution contract")
    state_signal = np.mean(signals, axis=0)
    rows = []
    for split in sorted(new.split.unique()):
        mask = new.split.eq(split).to_numpy()
        y = new.loc[mask, "observed_active"].to_numpy()
        row = {"split": split, "rows": len(y), "observed_activity": float(y.mean()),
               "v5_prior_control_composite_auc": auc(y, state_signal[mask])}
        for label, frame in (("v4", old), ("v5", new)):
            for channel in ("recorded", "latent"):
                p = frame.loc[mask, f"pineland_{channel}_ensemble"].to_numpy()
                row[f"{label}_{channel}"] = {"mean_probability": float(p.mean()),
                    "auc": auc(y, p), "brier": float(np.mean((p-y)**2))}
        recorded = row["v5_recorded"]
        latent = row["v5_latent"]
        row["rate_error"] = {
            "observed_activity_rate": row["observed_activity"],
            "recorded_mean_probability": recorded["mean_probability"],
            "latent_mean_probability": latent["mean_probability"],
            "recorded_rate_bias": recorded["mean_probability"] - row["observed_activity"],
            "latent_rate_bias": latent["mean_probability"] - row["observed_activity"],
        }
        row["discrimination"] = {
            "recorded_auc": recorded["auc"],
            "latent_auc": latent["auc"],
        }
        row["proper_scores"] = {
            "recorded_brier": recorded["brier"],
            "latent_brier": latent["brier"],
        }
        row["latent_to_recorded_information_loss"] = {
            "auc_change_recorded_minus_latent": (
                None if recorded["auc"] is None or latent["auc"] is None
                else recorded["auc"] - latent["auc"]
            ),
            "brier_change_recorded_minus_latent": recorded["brier"] - latent["brier"],
            "mean_probability_change_recorded_minus_latent": (
                recorded["mean_probability"] - latent["mean_probability"]
            ),
            "interpretation": (
                "Descriptive observation-channel attenuation only; it does not identify "
                "the recording process as the causal source of predictive error."
            ),
        }
        row["model_implied_control_signal"] = {
            "prior_control_composite_auc": row["v5_prior_control_composite_auc"],
            "independently_validated": False,
        }
        row["recorded_brier_improvement_v5_over_v4"] = row["v4_recorded"]["brier"] - row["v5_recorded"]["brier"]
        rows.append(row)
    contract = PROGRAM / "v5_theory_discrimination_contract.json"
    payload = {"schema_version": "pineland.v5_historical_diagnosis.v1",
        "model_sha256": model, "identical_rows_targets_splits_competitors": True,
        "diagnostic_not_confirmatory": True, "primary_verdict": decision["verdict"],
        "split_diagnostics": rows, "action_funnels_by_seed": funnels,
        "diagnostic_decomposition": [
            "rate_error", "discrimination", "latent_to_recorded_information_loss",
            "model_implied_control_signal",
        ],
        "capacity_measurement_note": "The control composite is model-implied territorial state, not independently validated capacity.",
        "belief_support_localization": "Unavailable from aggregate action funnels; no inferred local causal diagnosis.",
        "input_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in
            [Path(__file__), contract, execution, old_dir / "manifest.json", new_dir / "manifest.json",
             old_dir / "aligned_predictions.csv", new_dir / "aligned_predictions.csv", *files]},
        "calibration_licensed": False, "coin_inference_licensed": False}
    output = PROGRAM / "historical_revalidation_v5/nepal_theory_diagnosis.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "splits": rows}, indent=2))


if __name__ == "__main__":
    main()
