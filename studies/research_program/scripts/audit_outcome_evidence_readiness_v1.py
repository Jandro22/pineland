"""Audit empirical outcome-operator readiness from the frozen exposure ledger."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

LEDGER = ROOT / "studies/research_program/evidence_exposure_ledger_v1.json"
MEASUREMENT = ROOT / "studies/research_program/outcome_measurement_contract.json"
ACQUISITION = ROOT / "studies/research_program/future_outcome_evidence_acquisition_contract_v1.json"
OUTPUT = ROOT / "studies/research_program/outcome_evidence_readiness_audit_v1.json"


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    measurement = json.loads(MEASUREMENT.read_text(encoding="utf-8"))
    required = set(measurement["outcomes"])
    rows = []
    for case_id, case in ledger["cases"].items():
        missing_outcomes = required - set(case)
        if missing_outcomes:
            raise SystemExit(f"ledger missing outcomes for {case_id}: {sorted(missing_outcomes)}")
        for outcome in sorted(required):
            cell = case[outcome]
            artifacts = cell.get("registered_artifacts", [])
            artifact_checks = []
            for rel in artifacts:
                path = ROOT / rel
                artifact_checks.append({
                    "path": rel,
                    "exists": path.exists(),
                    "sha256": file_sha256(path) if path.exists() and path.is_file() else None,
                })
            evidence_class = cell["evidence_class"]
            historical_direct = evidence_class == "direct_measurement"
            confirmatory_ready = historical_direct and outcome == "violence"
            if outcome == "control":
                # Both cases have independent direct evidence, but neither has
                # a completed longitudinal historical construct-validation gate.
                confirmatory_ready = False
            rows.append({
                "case_id": case_id,
                "outcome": outcome,
                "exposure_status": cell["exposure_status"],
                "evidence_class": evidence_class,
                "historical_direct_measurement_registered": historical_direct,
                "all_registered_artifacts_exist": all(item["exists"] for item in artifact_checks),
                "confirmatory_historical_operator_ready": confirmatory_ready,
                "artifact_checks": artifact_checks,
                "limitations": cell.get("limitations", []),
            })

    by_outcome = {}
    for outcome in sorted(required):
        cells = [row for row in rows if row["outcome"] == outcome]
        by_outcome[outcome] = {
            "cases_with_direct_historical_measurement": sum(row["historical_direct_measurement_registered"] for row in cells),
            "cases_with_confirmatory_operator_ready": sum(row["confirmatory_historical_operator_ready"] for row in cells),
            "case_count": len(cells),
            "historical_cross_case_validation_ready": all(row["confirmatory_historical_operator_ready"] for row in cells),
        }

    payload = {
        "schema_version": "pineland.outcome_evidence_readiness.v1",
        "status": "readiness_audit_not_historical_scoring",
        "ledger_sha256": file_sha256(LEDGER),
        "measurement_contract_sha256": file_sha256(MEASUREMENT),
        "acquisition_contract_sha256": file_sha256(ACQUISITION),
        "rows": rows,
        "by_outcome": by_outcome,
        "program_gates": {
            "all_seven_outcomes_confirmatory_in_both_cases": all(
                value["historical_cross_case_validation_ready"] for value in by_outcome.values()
            ),
            "coin_efficacy_inference_authorized": False,
            "general_theory_promotion_authorized": False,
        },
        "priority_missing_outcomes": [
            item["outcome"] for item in json.loads(ACQUISITION.read_text(encoding="utf-8"))["priority_order"]
        ],
        "interpretation": (
            "The project currently has strong historical violence observation and partial independent control evidence, "
            "but not the joint seven-outcome historical measurement basis required for intervention efficacy or general-theory promotion. "
            "Synthetic estimand recovery is tracked separately and cannot fill an empirical measurement cell."
        ),
        "repository_state": repository_state(ROOT),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "by_outcome": by_outcome,
        "program_gates": payload["program_gates"],
        "priority_missing_outcomes": payload["priority_missing_outcomes"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
