"""Audit whether current historical construct evidence identifies a quantitative observation operator."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

REGISTRY = ROOT / "studies/research_program/construct_evidence_registry_v1.json"
CONTRACT = ROOT / "studies/research_program/measurement_error_identification_contract_v1.json"
COMPATIBILITY = ROOT / "studies/research_program/nepal_construct_compatibility_audit_v1.json"
OUT = ROOT / "studies/research_program/measurement_operator_identifiability_audit_v1.json"


def overlaps(a, b) -> bool:
    return max(date.fromisoformat(a["date_start"]), date.fromisoformat(b["date_start"])) <= min(
        date.fromisoformat(a["date_end"]), date.fromisoformat(b["date_end"])
    )


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    compatibility = json.loads(COMPATIBILITY.read_text(encoding="utf-8"))
    records = registry["records"]
    overlap_pairs = []
    independent_pairs = []
    compatible_construct_pairs = []
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if a["district_id"] != b["district_id"] or not overlaps(a, b):
                continue
            same_family = a["source_family"]["originating_family"] == b["source_family"]["originating_family"]
            same_source_document = a["source_id"] == b["source_id"]
            same_actor = a["actor_id"] == b["actor_id"]
            same_observable = a["observable"] == b["observable"]
            pair = {
                "record_a": a["record_id"], "record_b": b["record_id"],
                "district_id": a["district_id"],
                "same_source_document": same_source_document,
                "same_originating_source_family": same_family,
                "same_actor": same_actor,
                "same_observable": same_observable,
                "source_family_a": a["source_family"]["originating_family"],
                "source_family_b": b["source_family"]["originating_family"],
            }
            overlap_pairs.append(pair)
            if not same_family and not same_source_document:
                independent_pairs.append(pair)
                if same_actor and same_observable:
                    compatible_construct_pairs.append(pair)

    component_status = {
        "source_detection": {
            "identified": False,
            "reason": "No independent reference design establishes which compatible latent-positive cells went unreported; source silence cannot be treated as a false negative."
        },
        "source_false_positive": {
            "identified": False,
            "reason": "No independently validated latent-negative reference sample exists for these control/presence constructs."
        },
        "actor_attribution": {
            "identified": False,
            "reason": "Blind coder agreement measures coding reproducibility, not true historical actor attribution accuracy."
        },
        "construct_classification_reproducibility": {
            "identified": True,
            "reason": "Blind second coding plus adjudication provides a reproducibility measure for the coding protocol, not a source-accuracy probability."
        },
        "temporal_error": {
            "identified": False,
            "reason": "Intervals are preserved, but there is no independent timing reference sufficient to estimate a temporal error distribution."
        },
        "spatial_error": {
            "identified": False,
            "reason": "Some place names map exactly, but there is no replicated geolocation truth sample sufficient to estimate a spatial error distribution."
        },
        "source_dependence": {
            "identified": False,
            "reason": "Current evidence contains no independent construct-compatible district-time overlap from which dependence/error correlation can be estimated."
        },
    }
    immutable_gate = registry["immutable_source_document_count"] == registry["source_document_count"]
    independent_overlap_gate = len(compatible_construct_pairs) > 0
    latent_compatibility_gate = compatibility["rows_scoreable_under_frozen_construct_mapping"] > 0
    gates = {
        "all_source_documents_immutable_bound": immutable_gate,
        "independent_construct_compatible_overlap_exists": independent_overlap_gate,
        "frozen_model_latent_compatibility_exists": latent_compatibility_gate,
        "measurement_errors_identified_without_predictive_fit": all(
            component_status[name]["identified"]
            for name in ("source_detection", "source_false_positive", "actor_attribution", "temporal_error", "spatial_error", "source_dependence")
        ),
    }
    quantitative_authorized = all(gates.values())
    payload = {
        "schema_version": "pineland.measurement_operator_identifiability_audit.v1",
        "status": "quantitative_operator_not_identified" if not quantitative_authorized else "quantitative_operator_identification_gate_passed",
        "registry_sha256": file_sha256(REGISTRY),
        "contract_sha256": file_sha256(CONTRACT),
        "compatibility_audit_sha256": file_sha256(COMPATIBILITY),
        "record_count": len(records),
        "source_document_count": registry["source_document_count"],
        "immutable_source_document_count": registry["immutable_source_document_count"],
        "district_time_overlap_pair_count": len(overlap_pairs),
        "independent_source_overlap_pair_count": len(independent_pairs),
        "independent_construct_compatible_overlap_pair_count": len(compatible_construct_pairs),
        "overlap_pairs": overlap_pairs,
        "independent_overlap_pairs": independent_pairs,
        "component_identifiability": component_status,
        "gates": gates,
        "quantitative_historical_observation_operator_authorized": quantitative_authorized,
        "qualitative_construct_evidence_use_remains_authorized": True,
        "historical_predictive_rescore_authorized": False,
        "parameter_fitting_authorized": False,
        "core_change_authorized": False,
        "next_empirical_requirement": [
            "archive/hash-bind the eight current construct-evidence source documents or immutable archival representations",
            "acquire genuinely independent source-family observations for prospectively sampled matching place/time/construct cells",
            "include reference designs capable of identifying false-negative/false-positive components rather than treating non-reporting as truth",
            "apply the already validated prospective measurement-retention layer in future validation cases before historical scoring"
        ],
        "interpretation": "The current evidence supports scoped qualitative construct assessment and coding-reproducibility claims, but it does not identify a quantitative source-error model. No measurement parameter should be learned from Nepal predictive fit.",
        "repository_state": repository_state(ROOT),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "records": payload["record_count"],
        "source_documents": payload["source_document_count"],
        "immutable_source_documents": payload["immutable_source_document_count"],
        "district_time_overlap_pairs": payload["district_time_overlap_pair_count"],
        "independent_source_overlap_pairs": payload["independent_source_overlap_pair_count"],
        "independent_construct_compatible_overlap_pairs": payload["independent_construct_compatible_overlap_pair_count"],
        "quantitative_operator_authorized": quantitative_authorized,
        "gates": gates,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
