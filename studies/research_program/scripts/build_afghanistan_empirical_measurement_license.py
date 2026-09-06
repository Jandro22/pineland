"""Build the claim license for the Afghanistan one-year empirical benchmark.

This gate deliberately separates:
1. prospective instrumentation correctness (can the simulator retain/emit the
   intended measurement state without changing latent dynamics?), from
2. historical observation-operator identification (do independent empirical
   sources identify false-negative/false-positive/attribution error rates?).

The second condition is required before recorded-event predictions may become
a promotion criterion. A latent-mechanism holdout may still be scored while
the recorded layer remains diagnostic-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
IDENT = (
    ROOT
    / "studies/research_program/measurement_operator_identifiability_audit_v1.json"
)
RETENTION = (
    ROOT
    / "studies/research_program/prospective_measurement_retention_recovery_v2.json"
)
AFGHAN_REFERENCE = (
    ROOT
    / "studies/research_program/afghanistan_violence_measurement_reference_v1.json"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_license(output: Path) -> dict:
    ident = json.loads(IDENT.read_text(encoding="utf-8"))
    retention = json.loads(RETENTION.read_text(encoding="utf-8"))
    instrumentation_pass = bool(
        retention.get("passed")
        and retention.get("historical_outcomes_used") is False
        and retention.get("historical_parameter_fitting") is False
        and all(retention.get("global_gates", {}).values())
    )
    generic_quantitative_identification = bool(
        ident.get("quantitative_historical_observation_operator_authorized")
    )

    afghanistan_reference = None
    afghanistan_reference_pass = False
    if AFGHAN_REFERENCE.exists():
        afghanistan_reference = json.loads(
            AFGHAN_REFERENCE.read_text(encoding="utf-8")
        )
        required = {
            "independent_source_families_at_least_two": True,
            "province_week_state_based_violence_construct_match": True,
            "positive_reference_cells_identified": True,
            "negative_reference_cells_identified": True,
            "actor_attribution_reference_identified": True,
            "source_dependence_audited": True,
            "parameters_fit_without_pineland_outcomes": True,
        }
        checks = afghanistan_reference.get("checks", {})
        afghanistan_reference_pass = all(
            checks.get(name) is expected for name, expected in required.items()
        )

    recorded_license = (
        instrumentation_pass
        and generic_quantitative_identification
        and afghanistan_reference_pass
    )
    payload = {
        "schema_version": "pineland.afghanistan.empirical_measurement_license.v1",
        "instrumentation_recovery": {
            "passed": instrumentation_pass,
            "artifact": str(RETENTION.relative_to(ROOT)).replace("\\", "/"),
            "sha256": file_sha256(RETENTION),
        },
        "generic_measurement_identification": {
            "authorized": generic_quantitative_identification,
            "artifact": str(IDENT.relative_to(ROOT)).replace("\\", "/"),
            "sha256": file_sha256(IDENT),
            "unidentified_components": sorted(
                name
                for name, row in ident.get(
                    "component_identifiability", {}
                ).items()
                if not row.get("identified")
            ),
        },
        "afghanistan_violence_reference": {
            "artifact_exists": AFGHAN_REFERENCE.exists(),
            "passed": afghanistan_reference_pass,
            "required_construct": (
                "province-week Taliban-government state-based violence"
            ),
            "required_evidence": [
                "at least two genuinely independent source families",
                "positive and defensible negative/reference cells",
                "independently corroborated actor attribution",
                "source genealogy/dependence audit",
                "measurement parameters estimated without Pineland fit",
            ],
            "artifact": (
                str(AFGHAN_REFERENCE.relative_to(ROOT)).replace("\\", "/")
                if AFGHAN_REFERENCE.exists() else None
            ),
            "sha256": (
                file_sha256(AFGHAN_REFERENCE)
                if AFGHAN_REFERENCE.exists() else None
            ),
        },
        "licenses": {
            "latent_mechanism_empirical_scoring": True,
            "recorded_event_diagnostic_reporting": True,
            "recorded_event_promotion_gate": recorded_license,
        },
        "status": (
            "recorded_operator_licensed"
            if recorded_license
            else "recorded_operator_blocked_pending_independent_measurement_evidence"
        ),
        "interpretation": (
            "The prospective retention machinery is structurally validated, "
            "but recorded-event promotion remains blocked unless independent "
            "historical measurement evidence identifies the observation operator. "
            "This gate may not be bypassed by fitting recording parameters to "
            "Afghanistan predictive outcomes."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_license(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
