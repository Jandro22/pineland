"""Decide whether the one-year Afghanistan run earns a full-horizon ensemble."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
DEFAULT_INPUT = (
    STUDY / "runs" / "transfer_test_v1" / "year"
    / "seed_20040101_taliban_7500.json"
)
DEFAULT_OUTPUT = STUDY / "runs" / "transfer_test_v1" / "year" / "decision.json"


def evaluate(payload: dict) -> dict:
    funnel = payload.get("contact_funnel_counts", {})
    violence = payload.get("violence_validation", {})
    checks = {
        "all_integrity_gates": bool(payload.get("gate", {}).get("passed")),
        "one_year_horizon_reached": float(payload.get("horizon_days", 0.0)) >= 365.0,
        "contact_scheduler_executed": funnel.get("scheduler_executions", 0) > 0,
        "opposing_formations_overlapped": funnel.get("opposing_armed_organizations", 0) > 0,
        "readiness_gate_not_universal": funnel.get("readiness_available_pairs", 0) > 0,
        "positive_contact_hazard_reached": funnel.get("engagement_hazard_draws", 0) > 0,
    }
    integrity_passed = checks["all_integrity_gates"] and checks["one_year_horizon_reached"]
    dynamics_passed = all(value for key, value in checks.items() if key not in {
        "all_integrity_gates", "one_year_horizon_reached"
    })
    authorized = integrity_passed and dynamics_passed
    failed = [name for name, passed in checks.items() if not passed]
    latent_contacts = violence.get("latent_contacts", 0)
    return {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "gate": "one_year_to_full_horizon",
        "parameter_fit": False,
        "checks": checks,
        "failed_checks": failed,
        "observed_latent_contacts": latent_contacts,
        "latent_contact_realization_required_for_promotion": False,
        "outcome_scope": {
            "structural_and_control_validation": authorized,
            "realized_violence_validation": authorized and latent_contacts > 0,
            "interpretation": (
                "Positive hazard opportunities authorize the full structural/control transfer run. "
                "Realized violence interpretation remains unlicensed until at least one latent contact occurs."
            ),
        },
        "full_horizon_ensemble_authorized": authorized,
        "decision": "RUN_FULL_ENSEMBLE" if authorized else "DIAGNOSE_BEFORE_FULL_ENSEMBLE",
        "next_action": (
            "Run run_cloud_full.py --workers 3 locally."
            if authorized else
            "Use the contact funnel to localize the first universal zero gate; do not tune to Afghanistan outcomes."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["full_horizon_ensemble_authorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
