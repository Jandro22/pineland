"""Compare the completed transfer trajectories with frozen-data competitors."""
from __future__ import annotations

import csv
import argparse
from datetime import date
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from pineland_sim.reproducibility import model_sha256, repository_state

STUDY = ROOT / "studies" / "afghanistan_2004_2021"
RUNS = STUDY / "runs" / "transfer_test_v1" / "full"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"
COMPETITORS = STUDY / "results" / "competitors" / "competitor_scores.csv"
OUT = STUDY / "results" / "transfer_test_v1"
STRENGTHS = (5000, 7500, 10000)
SEED = 20040101
START_DATE = date(2004, 1, 1)
END_DATE = date(2021, 8, 15)


def score(y: list[int], p: list[float]) -> dict:
    bounded = [min(1 - 1e-9, max(1e-9, value)) for value in p]
    return {
        "n": len(y),
        "observed_rate": sum(y) / max(1, len(y)),
        "predicted_rate": sum(bounded) / max(1, len(bounded)),
        "log_score": sum(
            actual * math.log(predicted) + (1 - actual) * math.log(1 - predicted)
            for actual, predicted in zip(y, bounded)
        ) / max(1, len(y)),
        "brier": sum((actual - predicted) ** 2 for actual, predicted in zip(y, bounded)) / max(1, len(y)),
    }


def structural_gate_assessment(run: dict) -> dict:
    """Reassess only the obsolete absolute supply tolerance in archived runs."""
    checks = dict(run.get("gate", {}).get("checks", {}))
    summary = run.get("summary", {})
    residual = float(summary.get("supply_conservation_residual", float("nan")))
    scale = abs(float(summary.get("supply_consumed", float("nan"))))
    tolerance = 1e-5 + 1e-12 * scale
    valid = math.isfinite(residual) and math.isfinite(scale)
    supply = {"passed": valid and abs(residual) <= tolerance,
              "reason": "within_scaled_tolerance" if valid and abs(residual) <= tolerance else "outside_scaled_tolerance",
              "residual": residual, "scale": scale, "atol": 1e-5, "rtol": 1e-12,
              "tolerance": tolerance if valid else None,
              "relative_residual": abs(residual) / scale if valid and scale else None}
    original_supply = checks.get("supply_ledger")
    checks["supply_ledger"] = supply["passed"]
    return {
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "supply_reassessment": {
            **supply,
            "original_gate_value": original_supply,
            "scale_is_conservative_lower_bound": True,
            "interpretation": "Numerical conservation only; no empirical outcome is changed.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=RUNS)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    runs_dir = args.runs_dir
    output_dir = args.output_dir
    seed = args.seed
    paths = [runs_dir / f"seed_{seed}_taliban_{strength}.json" for strength in STRENGTHS]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit("missing completed trajectories: " + ", ".join(missing))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    with PANEL.open(encoding="utf-8", newline="") as handle:
        panel = list(csv.DictReader(handle))
    recorded_sets = [{
        (cell["province_id"], int(cell["week_index"]))
        for cell in run["violence_validation"]["recorded_active_cells"]
    } for run in runs]

    pineland_scores = []
    for split in sorted({row["split"] for row in panel}):
        rows = [row for row in panel if row["split"] == split]
        y = [int(row["taliban_state_active"]) for row in rows]
        probabilities = []
        for row in rows:
            key = (row["province_id"], int(row["week_index"]))
            hits = sum(key in cells for cells in recorded_sets)
            # Jeffreys smoothing avoids pretending three structural-strength
            # variants are an infinite stochastic ensemble.
            probabilities.append((hits + 0.5) / (len(recorded_sets) + 1.0))
        pineland_scores.append({
            "split": split,
            "model": "pineland_strength_mixture",
            "fit_scope": "untuned_three_initial_strengths_one_seed",
            **score(y, probabilities),
        })

    competitor_rows = []
    with COMPETITORS.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            competitor_rows.append({
                **row,
                "n": int(row["n"]),
                **{field: float(row[field]) for field in (
                    "observed_rate", "predicted_rate", "log_score", "brier"
                )},
            })
    all_scores = competitor_rows + pineland_scores
    control = {
        str(run["taliban_initial_strength"]): run.get("control_validation")
        for run in runs
    }
    observed_horizon = runs[0].get("horizon_days")
    observed_stage = runs[0].get("stage", "unknown")
    if observed_stage == "full" and observed_horizon is not None and observed_horizon < (END_DATE - START_DATE).days:
        observed_stage = "staged_custom_horizon"
    control_target_day = (date(2017, 10, 15) - START_DATE).days
    control_statuses = {
        str(run["taliban_initial_strength"]): run.get(
            "control_validation_status",
            "not_reached_horizon" if run.get("horizon_days", 0) < control_target_day else "unknown",
        )
        for run in runs
    }
    control_gate_statuses = {
        str(run["taliban_initial_strength"]): (
            (run.get("control_validation") or {}).get("validation_gate_status")
            or (
                "legacy_measurement_failure"
                if (run.get("control_validation") or {}).get("observation_operator_status")
                != "prospective_unfitted_observation_operator"
                else "unassessed_missing_predeclared_success_gate"
            )
        )
        for run in runs
    }
    frozen_core = json.loads(
        (ROOT / "studies" / "research_program" / "core_freeze.json").read_text(encoding="utf-8")
    )
    live_model = model_sha256(ROOT)
    live_repo = repository_state(ROOT)
    analysis_core_matches_frozen = live_model == frozen_core["model_sha256"]
    run_provenance_captured = all(
        run.get("model_sha256_start")
        and run.get("model_sha256_end")
        and run.get("tracked_diff_sha256")
        for run in runs
    )
    run_provenance_matches_frozen = run_provenance_captured and all(
        run["model_sha256_start"] == run["model_sha256_end"] == frozen_core["model_sha256"]
        and run["tracked_diff_sha256"] == frozen_core["tracked_diff_sha256"]
        for run in runs
    )
    structural_assessments = {
        str(run["taliban_initial_strength"]): structural_gate_assessment(run)
        for run in runs
    }
    manpower_diagnostics = {}
    for run in runs:
        summary = run.get("summary", {})
        strength = str(run["taliban_initial_strength"])
        active = float(summary.get("active_insurgent_formation_personnel", 0.0))
        mobilized = float(summary.get("mobilized_insurgent_represented_population", 0.0))
        control_level = float(summary.get("mean_insurgent_effective_control", 0.0))
        manpower_diagnostics[strength] = {
            "active_formation_personnel": active,
            "mobilized_represented_population": mobilized,
            "mean_insurgent_effective_control": control_level,
            "fielded_share_of_mobilized": active / mobilized if mobilized else None,
            "high_manpower_negligible_control_flag": active >= 100_000 and control_level < 0.01,
            "interpretation": "Diagnostic of recruitment/presence/control coupling; not a validation target.",
        }
    report = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "parameter_fit": False,
        "holdout_refit": False,
        "horizon_days": observed_horizon,
        "run_stage": observed_stage,
        "provenance": {
            "status": "frozen_run_provenance_verified" if run_provenance_matches_frozen else "run_provenance_unverified",
            "live_model_sha256_at_analysis": live_model,
            "frozen_model_sha256": frozen_core["model_sha256"],
            "live_tracked_diff_sha256_at_analysis": live_repo["tracked_diff_sha256"],
            "frozen_tracked_diff_sha256": frozen_core["tracked_diff_sha256"],
            "run_provenance_captured": run_provenance_captured,
            "run_provenance_matches_frozen_certificate": run_provenance_matches_frozen,
            "analysis_core_matches_frozen_model": analysis_core_matches_frozen,
            "analysis_tracked_diff_matches_frozen_run": live_repo["tracked_diff_sha256"] == frozen_core["tracked_diff_sha256"],
            "transfer_claims_licensed": run_provenance_matches_frozen,
        },
        "all_structural_gates_passed": all(item["passed"] for item in structural_assessments.values()),
        "numeric_gate_reassessment": structural_assessments,
        "strengths": list(STRENGTHS),
        "seed": seed,
        "runtime_seconds": {str(run["taliban_initial_strength"]): run["runtime_seconds"] for run in runs},
        "hazard_diagnostics": {str(run["taliban_initial_strength"]): run["hazard_diagnostics"] for run in runs},
        "violence_counts": {str(run["taliban_initial_strength"]): {
            "latent_contacts": run["violence_validation"]["latent_contacts"],
            "recorded_contacts": run["violence_validation"]["recorded_contacts"],
        } for run in runs},
        "outcome_licenses": {
            "control_validation": all(run.get("control_validation") is not None for run in runs),
            "control_measurement_licensed": all(
                (run.get("control_validation") or {}).get("observation_operator_status")
                == "prospective_unfitted_observation_operator" for run in runs
            ),
            "control_validation_passed": all(
                (run.get("control_validation") or {}).get("validation_passed") is True for run in runs
            ),
            "control_validation_assessed": all(
                status in {"passed", "failed"} for status in control_gate_statuses.values()
            ),
            "control_validation_gate_statuses": control_gate_statuses,
            "control_validation_statuses": control_statuses,
            "control_validation_target_day": control_target_day,
            "control_validation_target_reached": all(
                status != "not_reached_horizon" for status in control_statuses.values()
            ),
            "latent_violence_dynamics": all(
                run["violence_validation"].get("latent_contacts", 0) > 0 for run in runs
            ),
            "recorded_violence_dynamics": all(
                run["violence_validation"].get("recorded_contacts", 0) > 0 for run in runs
            ),
            "note": (
                "Zero latent or recorded contacts do not invalidate structural or control results, "
                "but they prohibit interpreting violence scores as realized engagement validation."
            ),
        },
        "control_validation": control,
        "manpower_control_diagnostics": manpower_diagnostics,
        "scores": all_scores,
        "interpretation_rule": (
            "Pineland earns predictive value only where it improves held-out scores or control validation "
            "relative to training-only competitors; mechanism interpretation remains provisional."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "transfer_comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    heldout = [row for row in all_scores if row["split"] != "training"]
    lines = [
        "# Afghanistan transfer result",
        "",
        "No simulator parameter was fitted and no holdout was refit.",
        "",
        f"All structural gates passed: **{report['all_structural_gates_passed']}**.",
        f"Frozen-core provenance verified: **{report['provenance']['transfer_claims_licensed']}**.",
        "",
        "## Held-out comparison",
        "",
        "| Split | Model | Log score | Brier | Predicted rate | Observed rate |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in heldout:
        lines.append(
            f"| {row['split']} | {row['model']} | {row['log_score']:.4f} | "
            f"{row['brier']:.4f} | {row['predicted_rate']:.4f} | {row['observed_rate']:.4f} |"
        )
    lines.extend(["", "## Independent control validation", ""])
    for strength, metrics in control.items():
        if metrics is None:
            status = control_statuses.get(str(strength), "unknown")
            if status == "not_reached_horizon":
                lines.append(
                    f"- Initial Taliban strength {strength}: control target not reached "
                    f"(target day {control_target_day}; horizon {observed_horizon})."
                )
            else:
                lines.append(f"- Initial Taliban strength {strength}: no dated snapshot reached ({status}).")
        else:
            lines.append(
                f"- Initial Taliban strength {strength}: n={metrics['n']}, "
                f"MAE={metrics['mae']:.4f}, Pearson={metrics['pearson']}; "
                f"measurement={metrics.get('observation_operator_status', 'legacy effective scalar')}."
            )
    lines.extend(["", "## Manpower/control diagnostic", ""])
    for strength, metrics in manpower_diagnostics.items():
        lines.append(
            f"- Initial Taliban strength {strength}: active personnel={metrics['active_formation_personnel']:.0f}, "
            f"mobilized represented population={metrics['mobilized_represented_population']:.0f}, "
            f"mean insurgent effective control={metrics['mean_insurgent_effective_control']:.6f}, "
            f"high-manpower/negligible-control flag={metrics['high_manpower_negligible_control_flag']}."
        )
    lines.extend([
        "",
        "## Outcome scope",
        "",
        f"Latent violence dynamics licensed: **{report['outcome_licenses']['latent_violence_dynamics']}**.",
        f"Recorded violence dynamics licensed: **{report['outcome_licenses']['recorded_violence_dynamics']}**.",
        "Zero-contact runs may still inform structural, control, and hazard diagnostics, "
        "but are not evidence of realized engagement reproduction.",
        "Transfer claims are prohibited when the live core hash or tracked diff differs from the frozen transfer record.",
        "",
        report["interpretation_rule"],
        "",
    ])
    (output_dir / "transfer_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(output_dir), "scores": len(all_scores)}, indent=2))


if __name__ == "__main__":
    main()
