"""Read-only diagnostic decomposition for the frozen v5 Afghanistan confrontation.

This script never fits the simulator or competitors.  It runs only after the
three-strength full-horizon ensemble and aligned predictive competition exist.
The three strengths are treated as initial-condition uncertainty, not stochastic
replications.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
RUN_DIR = ROOT / "studies" / "afghanistan_2004_2021" / "runs" / "transfer_test_v5" / "full"
COMPETITION = PROGRAM / "predictive_competition" / "afghanistan_v5"
EXECUTION = PROGRAM / "historical_revalidation_v5" / "execution_contract.json"
OUTPUT = PROGRAM / "historical_revalidation_v5" / "afghanistan_theory_diagnosis.json"

sys.path.insert(0, str(PROGRAM / "scripts"))
from run_aligned_predictive_competition import frozen_core, sha256, validate_member  # noqa: E402


def auc(y: np.ndarray, scores: np.ndarray) -> float | None:
    y = np.asarray(y, dtype=int)
    scores = np.asarray(scores, dtype=float)
    positive = int(y.sum())
    negative = int((1 - y).sum())
    if not positive or not negative:
        return None
    ranks = pd.Series(scores).rank(method="average").to_numpy()
    return float(
        (ranks[y == 1].sum() - positive * (positive + 1) / 2)
        / (positive * negative)
    )


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def log_score(y: np.ndarray, p: np.ndarray) -> float:
    eps = 1e-12
    p = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    y = np.asarray(y, dtype=float)
    return float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_competition_artifacts() -> dict:
    manifest = json.loads((COMPETITION / "manifest.json").read_text(encoding="utf-8"))
    for stem, suffix in (
        ("aligned_predictions", "csv"),
        ("scores", "csv"),
        ("decision", "json"),
    ):
        path = COMPETITION / f"{stem}.{suffix}"
        if sha256(path) != manifest[f"{stem}_sha256"]:
            raise ValueError(f"competition artifact drift: {path}")
    decision = json.loads((COMPETITION / "decision.json").read_text(encoding="utf-8"))
    if not decision.get("ensemble_complete") or not decision.get("final_historical_stage"):
        raise ValueError("full final Afghanistan ensemble required")
    if decision.get("expected_members") != 3 or decision.get("member_count") != 3:
        raise ValueError("Afghanistan v5 requires exactly three strength conditions")
    return decision


def main() -> int:
    model_hash, diff_hash = frozen_core(EXECUTION)
    decision = validate_competition_artifacts()
    frame = pd.read_csv(COMPETITION / "aligned_predictions.csv")
    required = {
        "split",
        "observed_active",
        "pineland_recorded_ensemble",
        "pineland_latent_ensemble",
    }
    if not required <= set(frame):
        raise ValueError(f"missing aligned columns: {sorted(required - set(frame))}")

    runs = []
    for path in RUN_DIR.glob("seed_*_taliban_*.json"):
        run = validate_member(path, model_hash, diff_hash)
        runs.append((path, run))
    runs.sort(key=lambda item: int(item[1]["taliban_initial_strength"]))
    strengths = [int(run["taliban_initial_strength"]) for _, run in runs]
    if strengths != [5000, 7500, 10000]:
        raise ValueError(f"unexpected Afghanistan strength envelope: {strengths}")

    split_diagnostics = []
    for split in sorted(frame["split"].unique()):
        subset = frame.loc[frame["split"].eq(split)]
        y = subset["observed_active"].to_numpy(dtype=int)
        recorded = subset["pineland_recorded_ensemble"].to_numpy(dtype=float)
        latent = subset["pineland_latent_ensemble"].to_numpy(dtype=float)
        observed_rate = float(y.mean())
        recorded_rate = float(recorded.mean())
        latent_rate = float(latent.mean())
        recorded_auc = auc(y, recorded)
        latent_auc = auc(y, latent)
        recorded_brier = brier(y, recorded)
        latent_brier = brier(y, latent)
        split_diagnostics.append({
            "split": split,
            "rows": int(len(subset)),
            "rate_error": {
                "observed_activity_rate": observed_rate,
                "recorded_mean_probability": recorded_rate,
                "latent_mean_probability": latent_rate,
                "recorded_rate_bias": recorded_rate - observed_rate,
                "latent_rate_bias": latent_rate - observed_rate,
            },
            "discrimination": {
                "recorded_auc": recorded_auc,
                "latent_auc": latent_auc,
            },
            "proper_scores": {
                "recorded_brier": recorded_brier,
                "latent_brier": latent_brier,
                "recorded_log_score": log_score(y, recorded),
                "latent_log_score": log_score(y, latent),
            },
            "latent_to_recorded_information_loss": {
                "auc_change_recorded_minus_latent": (
                    None if recorded_auc is None or latent_auc is None
                    else recorded_auc - latent_auc
                ),
                "brier_change_recorded_minus_latent": recorded_brier - latent_brier,
                "mean_probability_change_recorded_minus_latent": recorded_rate - latent_rate,
                "interpretation": (
                    "Descriptive observation-channel attenuation only; it does not identify "
                    "the recording model as the causal source of predictive error."
                ),
            },
        })

    control = []
    for path, run in runs:
        validation = run.get("control_validation")
        if validation is None:
            row = {
                "strength": int(run["taliban_initial_strength"]),
                "status": run.get("control_validation_status"),
                "validation": None,
            }
        else:
            row = {
                "strength": int(run["taliban_initial_strength"]),
                "status": run.get("control_validation_status"),
                "validation_gate_status": validation.get("validation_gate_status"),
                "validation_passed": validation.get("validation_passed"),
                "snapshot_time": validation.get("snapshot_time"),
                "target_date": validation.get("target_date"),
                "n": validation.get("n"),
                "mae": validation.get("mae"),
                "rmse": validation.get("rmse"),
                "population_weighted_mae": validation.get("population_weighted_mae"),
                "pearson": validation.get("pearson"),
                "observed_mean": validation.get("observed_mean"),
                "modeled_mean": validation.get("modeled_mean"),
                "observation_operator_sha256": validation.get("observation_operator_sha256"),
                "control_validation_plan_sha256": validation.get("control_validation_plan_sha256"),
            }
        control.append(row)

    payload = {
        "schema_version": "pineland.v5_afghanistan_historical_diagnosis.v1",
        "diagnostic_not_confirmatory": True,
        "primary_verdict": decision["verdict"],
        "model_sha256": model_hash,
        "tracked_diff_sha256": diff_hash,
        "ensemble_semantics": (
            "Three Taliban initial-strength conditions quantify a declared slice of "
            "initialization uncertainty; they are not independent stochastic replications."
        ),
        "split_diagnostics": split_diagnostics,
        "independent_control_assessment": control,
        "action_funnel_localization_rule": (
            "Aggregate action-funnel counts may describe global execution frequency but "
            "cannot identify locality-specific belief, support, access, or opportunity errors."
        ),
        "interpretation_rules": [
            "Rate error and discrimination are reported separately.",
            "Latent-to-recorded differences are descriptive observation-channel diagnostics, not causal attribution.",
            "Independent control evidence is retained even if the violence competition passes or fails.",
            "A failed primary predictive gate cannot be overridden by diagnostics.",
            "No event-rate tuning, holdout refit, or mechanism change is licensed by this report.",
        ],
        "input_sha256": {
            str(Path(__file__).relative_to(ROOT)): sha256(Path(__file__)),
            str(EXECUTION.relative_to(ROOT)): sha256(EXECUTION),
            str((COMPETITION / "manifest.json").relative_to(ROOT)): sha256(COMPETITION / "manifest.json"),
            str((COMPETITION / "aligned_predictions.csv").relative_to(ROOT)): sha256(COMPETITION / "aligned_predictions.csv"),
            str((COMPETITION / "scores.csv").relative_to(ROOT)): sha256(COMPETITION / "scores.csv"),
            str((COMPETITION / "decision.json").relative_to(ROOT)): sha256(COMPETITION / "decision.json"),
            **{str(path.relative_to(ROOT)): file_digest(path) for path, _ in runs},
        },
        "calibration_licensed": False,
        "coin_inference_licensed": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(json.dumps({
        "output": str(OUTPUT),
        "primary_verdict": decision["verdict"],
        "splits": split_diagnostics,
        "independent_control_assessment": control,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
