"""Audit civilian-harm coding and Pineland compatibility without historical values."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"

ACQUISITION = PROGRAM / "civilian_harm_acquisition_contract_v1.json"
EXPOSURE = PROGRAM / "civilian_harm_source_exposure_log_v1.csv"
CODING = PROGRAM / "civilian_harm_coding_contract_v1.json"
COMPAT = PROGRAM / "civilian_harm_model_compatibility_contract_v1.json"
TEMPLATE = PROGRAM / "civilian_harm_first_coder_template_v1.csv"
OUT = PROGRAM / "civilian_harm_measurement_readiness_audit_v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    acquisition = load_json(ACQUISITION)
    coding = load_json(CODING)
    compat = load_json(COMPAT)
    with EXPOSURE.open(encoding="utf-8-sig", newline="") as handle:
        exposure = list(csv.DictReader(handle))
    with TEMPLATE.open(encoding="utf-8-sig", newline="") as handle:
        template_fields = next(csv.reader(handle))

    required = coding["required_coded_fields"]
    missing_template_fields = [field for field in required if field not in template_fields]
    candidate_statuses = sorted({row["first_coder_status"] for row in exposure})
    historical_values_already_coded = any(
        status not in {"", "candidate_discovered_not_value_coded"}
        for status in candidate_statuses
    )
    component_auth = {
        name: cell["historical_numeric_comparison_authorized"]
        for name, cell in compat["components"].items()
    }
    payload = {
        "schema_version": "pineland.civilian_harm_measurement_readiness.v1",
        "status": "pre_value_coding_measurement_audit",
        "artifact_hashes": {
            "acquisition_contract": sha(ACQUISITION),
            "source_exposure_log": sha(EXPOSURE),
            "coding_contract": sha(CODING),
            "model_compatibility_contract": sha(COMPAT),
            "first_coder_template": sha(TEMPLATE),
        },
        "candidate_source_count": len(exposure),
        "candidate_source_ids_unique": len({row["candidate_source_id"] for row in exposure}) == len(exposure),
        "candidate_cases": sorted({row["case_id"] for row in exposure}),
        "candidate_source_family_count": len({row["source_family"] for row in exposure}),
        "candidate_first_coder_statuses": candidate_statuses,
        "historical_values_already_coded": historical_values_already_coded,
        "coding_schema_frozen_before_value_coding": not historical_values_already_coded,
        "missing_first_coder_template_fields": missing_template_fields,
        "component_historical_numeric_comparison_authorized": component_auth,
        "all_components_historically_comparable_now": all(component_auth.values()),
        "gates": {
            "source_discovery_protocol_frozen": acquisition["status"] == "prospective_before_new_civilian_harm_source_discovery",
            "coding_semantics_frozen": coding["status"] == "prospective_before_candidate_source_value_coding",
            "first_coder_schema_complete": not missing_template_fields,
            "model_semantic_compatibility_ready": all(component_auth.values()),
            "confirmatory_historical_harm_validation_authorized": False,
            "historical_predictive_rescore_authorized": False,
            "parameter_fitting_authorized": False,
            "core_change_authorized": False,
        },
        "next_licensed_step": (
            "Source-bound first coding may now read and extract the candidate historical harm values. "
            "Those values remain measurement evidence only and cannot be compared numerically with Pineland until prospective semantic/retention identification passes after the historical freeze."
        ),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
