"""Audit first-coder civilian-harm evidence without comparing it to Pineland."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
EXPOSURE = PROGRAM / "civilian_harm_source_exposure_log_v1.csv"
CODED = PROGRAM / "civilian_harm_first_coder_v1.csv"
CONTRACT = PROGRAM / "civilian_harm_coding_contract_v1.json"
PROVENANCE = PROGRAM / "civilian_harm_first_coder_provenance_v1.json"
OUTPUT = PROGRAM / "civilian_harm_first_coder_audit_v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    exposure = read_csv(EXPOSURE)
    coded = read_csv(CODED)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    exposed_ids = {row["candidate_source_id"] for row in exposure}
    coded_source_ids = {row["candidate_source_id"] for row in coded}

    errors: list[str] = []
    if len(exposed_ids) != len(exposure):
        errors.append("duplicate_candidate_source_id")
    if len({row["harm_record_id"] for row in coded}) != len(coded):
        errors.append("duplicate_harm_record_id")
    unknown_sources = sorted(coded_source_ids - exposed_ids)
    if unknown_sources:
        errors.append("coded_source_not_in_exposure_log:" + ",".join(unknown_sources))

    required = set(contract["required_coded_fields"])
    if coded:
        missing_columns = sorted(required - set(coded[0]))
        if missing_columns:
            errors.append("missing_required_columns:" + ",".join(missing_columns))

    by_case_component: dict[str, Counter[str]] = defaultdict(Counter)
    source_families: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in coded:
        by_case_component[row["case_id"]][row["component"]] += 1
        source_families[row["case_id"]][row["component"]].add(row["source_family"])

    # Independence is assessed conservatively from claim provenance, not raw
    # document count.  UNHCR_via_IDMC remains dependent on UNHCR for the coded
    # national figures; repeated UNAMA reports remain one family.
    independent_origins = {
        "nepal_2001_2006": {
            "direct_harm": {"OHCHR"},
            "displacement": {"UNHCR"},
            "resource_loss": {"OHCHR"},
        },
        "afghanistan_2004_2021": {
            "direct_harm": {"UNAMA_OHCHR"},
            "displacement": {"UNHCR"},
            "resource_loss": set(),
        },
    }
    coverage = {}
    for case_id, components in independent_origins.items():
        coverage[case_id] = {}
        for component in ("direct_harm", "displacement", "resource_loss"):
            origins = components[component]
            coverage[case_id][component] = {
                "coded_record_count": by_case_component[case_id][component],
                "raw_coded_source_families": sorted(source_families[case_id][component]),
                "independent_originating_families": sorted(origins),
                "independent_originating_family_count": len(origins),
            }

    first_coder_coverage_gate = {
        "nepal_direct_harm_two_independent_families": len(independent_origins["nepal_2001_2006"]["direct_harm"]) >= 2,
        "nepal_displacement_or_resource_loss_present": bool(
            independent_origins["nepal_2001_2006"]["displacement"] or
            independent_origins["nepal_2001_2006"]["resource_loss"]
        ),
        "afghanistan_direct_harm_two_independent_families_or_audited_series_plus_independent_overlap": False,
        "afghanistan_longitudinal_displacement_present": by_case_component["afghanistan_2004_2021"]["displacement"] >= 2,
    }
    payload = {
        "schema_version": "pineland.civilian_harm_first_coder_audit.v1",
        "status": "first_coder_audit_not_confirmatory",
        "errors": errors,
        "artifact_hashes": {
            "exposure_log": sha(EXPOSURE),
            "coded_table": sha(CODED),
            "coding_contract": sha(CONTRACT),
            "provenance": sha(PROVENANCE),
        },
        "candidate_source_count": len(exposure),
        "coded_record_count": len(coded),
        "coded_source_count": len(coded_source_ids),
        "case_component_coverage": coverage,
        "first_coder_coverage_gate": first_coder_coverage_gate,
        "first_coder_coverage_gate_passed": all(first_coder_coverage_gate.values()),
        "confirmatory_use_authorized": False,
        "second_coder_required": True,
        "model_comparison_authorized": False,
        "historical_rescore_authorized": False,
        "core_change_authorized": False,
        "source_dependency_guard": provenance["source_dependency_findings"],
        "interpretation": (
            "The first-coder pass establishes usable historical harm records while preserving missingness, "
            "source dependence, and source-native units. It does not yet satisfy independent-source coverage, "
            "second-coder reliability, immutable-source binding, or semantic comparability to current Pineland harm output."
        ),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
