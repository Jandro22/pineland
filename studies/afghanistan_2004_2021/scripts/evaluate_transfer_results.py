"""Apply the post-run Afghanistan transfer promotion rule."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "studies/afghanistan_2004_2021/results/transfer_test_v1/transfer_comparison.json"


def evaluate(report: dict) -> dict:
    heldout = [row for row in report.get("scores", []) if row.get("split") != "training"]
    pineland = {row["split"]: row for row in heldout if row.get("model") == "pineland_strength_mixture"}
    competitors = {}
    for row in heldout:
        if row.get("model") == "pineland_strength_mixture":
            continue
        competitors.setdefault(row["split"], []).append(row)
    competitor_dominance = {
        split: bool(pineland.get(split)) and max(rows, key=lambda row: row["log_score"])["log_score"] >= pineland[split]["log_score"]
        for split, rows in competitors.items()
    }
    counts = report.get("violence_counts", {})
    licenses = report.get("outcome_licenses", {})
    provenance = report.get("provenance", {})
    control_statuses = licenses.get("control_validation_statuses", {})
    control_gate_statuses = licenses.get("control_validation_gate_statuses", {})
    target_reached = bool(licenses.get("control_validation_target_reached"))
    control_not_reached_horizon = bool(control_statuses) and all(
        status == "not_reached_horizon" for status in control_statuses.values()
    )
    checks = {
        "structural_gates": bool(report.get("all_structural_gates_passed")),
        "frozen_core_provenance": provenance.get("transfer_claims_licensed") is True,
        "run_provenance_captured": provenance.get("run_provenance_captured") is True,
        "run_provenance_matches_frozen_certificate": provenance.get("run_provenance_matches_frozen_certificate") is True,
        "independent_control_validation": bool(licenses.get("control_validation")),
        "control_measurement_licensed": bool(licenses.get("control_measurement_licensed")),
        "control_validation_passed": bool(licenses.get("control_validation_passed")),
        "control_validation_assessed": bool(licenses.get("control_validation_assessed")),
        "control_validation_target_reached": target_reached,
        "latent_violence_dynamics_all_strengths": bool(licenses.get("latent_violence_dynamics")),
        "recorded_violence_dynamics_all_strengths": bool(licenses.get("recorded_violence_dynamics")),
        "pineland_not_dominated_on_every_holdout": bool(competitor_dominance) and not all(competitor_dominance.values()),
    }
    promoted = all(checks.values())
    if promoted:
        next_action = "Proceed to preregistered cross-case comparison."
    elif provenance.get("transfer_claims_licensed") is not True:
        if provenance.get("status") != "frozen_core_verified":
            next_action = "Do not calibrate or claim transfer. Restore or supersede the frozen-core provenance record before using any trajectory for transfer claims."
        elif provenance.get("run_provenance_captured") is not True:
            next_action = "Do not calibrate or claim transfer. Rerun the staged ensemble under the current frozen certificate with per-run model and tracked-diff hashes captured."
        else:
            next_action = "Do not calibrate or claim transfer. The trajectory provenance does not match the frozen certificate; rerun from the frozen certificate."
    elif (target_reached and bool(licenses.get("control_measurement_licensed")) and
          not bool(licenses.get("control_validation_assessed"))):
        next_action = (
            "Do not classify the prospective control score as pass or failure. "
            "Establish a training-only preregistered control success gate before a future target run; "
            "do not tune on the target snapshot."
        )
    elif target_reached:
        next_action = "Preserve the completed target-period failure. Do not tune on these outcomes or promote transfer; document measurement and provenance limitations."
    else:
        next_action = "Do not calibrate or claim transfer. Extend to the preregistered 2017 control target and reassess control and held-out prediction."
    return {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "horizon_days": report.get("horizon_days"),
        "run_stage": report.get("run_stage"),
        "parameter_fit": False,
        "holdout_refit": False,
        "checks": checks,
        "control_validation_statuses": control_statuses,
        "control_validation_target_day": licenses.get("control_validation_target_day"),
        "provenance": provenance,
        "control_gate_assessment": (
            "unassessed_not_reached_horizon"
            if control_not_reached_horizon and not target_reached
            else "failed_or_missing_snapshot"
            if not bool(licenses.get("control_validation"))
            else "completed_failed_legacy_measurement"
            if not bool(licenses.get("control_measurement_licensed"))
            else "unassessed_missing_predeclared_success_gate"
            if not bool(licenses.get("control_validation_assessed"))
            else "failed"
            if not bool(licenses.get("control_validation_passed"))
            else "passed"
        ),
        "control_validation_gate_statuses": control_gate_statuses,
        "competitor_dominance_by_holdout": competitor_dominance,
        "violence_counts": counts,
        "promoted_to_general_transfer": promoted,
        "decision": "PROMOTE_TRANSFER" if promoted else "HOLD_TRANSFER_AND_DIAGNOSE",
        "next_action": next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["promoted_to_general_transfer"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
