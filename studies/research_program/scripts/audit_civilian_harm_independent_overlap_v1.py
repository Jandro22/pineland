"""Audit source-independence coverage after the civilian-harm overlap pass."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
CONTRACT = PROGRAM / "civilian_harm_independent_overlap_acquisition_contract_v1.json"
LOG = PROGRAM / "civilian_harm_independent_overlap_exposure_log_v1.csv"
CODED = PROGRAM / "civilian_harm_independent_overlap_first_coder_v1.csv"
PROV = PROGRAM / "civilian_harm_independent_overlap_provenance_v1.json"
BASE_AUDIT = PROGRAM / "civilian_harm_first_coder_audit_v1.json"
OUT = PROGRAM / "civilian_harm_independent_overlap_audit_v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    baseline = json.loads(BASE_AUDIT.read_text(encoding="utf-8"))
    candidates = rows(LOG)
    coded = rows(CODED)
    expected_audit_sha = contract["triggering_audit_sha256"]
    actual_audit_sha = sha(BASE_AUDIT)
    if expected_audit_sha != actual_audit_sha:
        raise SystemExit(f"triggering audit changed: expected {expected_audit_sha}, got {actual_audit_sha}")

    admitted = [r for r in candidates if r["admission_status"] == "admitted_independent_family"]
    admitted_by_case = {}
    for case in ("nepal_2001_2006", "afghanistan_2004_2021"):
        admitted_by_case[case] = sorted({r["source_family"] for r in admitted if r["case_id"] == case})
    coded_admitted_ids = {r["candidate_overlap_id"] for r in admitted}
    coded_by_case = {
        case: sum(1 for r in coded if r["case_id"] == case and r["candidate_overlap_id"] in coded_admitted_ids)
        for case in admitted_by_case
    }
    gates = {
        "triggering_audit_hash_locked": expected_audit_sha == actual_audit_sha,
        "nepal_second_direct_harm_family_acquired": len(admitted_by_case["nepal_2001_2006"]) >= 1,
        "afghanistan_independent_overlap_family_acquired": len(admitted_by_case["afghanistan_2004_2021"]) >= 1,
        "admitted_sources_have_coded_direct_harm": all(v >= 1 for v in coded_by_case.values()),
        "source_independence_coverage_gate_passed": False,
        "confirmatory_use_authorized": False,
        "model_comparison_authorized": False,
        "historical_rescore_authorized": False,
        "parameter_fitting_authorized": False,
        "core_change_authorized": False,
    }
    gates["source_independence_coverage_gate_passed"] = all([
        gates["triggering_audit_hash_locked"],
        gates["nepal_second_direct_harm_family_acquired"],
        gates["afghanistan_independent_overlap_family_acquired"],
        gates["admitted_sources_have_coded_direct_harm"],
    ])
    payload = {
        "schema_version": "pineland.civilian_harm_independent_overlap_audit.v1",
        "status": "source_independence_coverage_audit_not_confirmatory",
        "artifact_hashes": {
            "contract": sha(CONTRACT),
            "triggering_first_coder_audit": actual_audit_sha,
            "candidate_log": sha(LOG),
            "coded_overlap_table": sha(CODED),
            "provenance": sha(PROV),
        },
        "baseline_first_coder_coverage_gate_passed": baseline["first_coder_coverage_gate_passed"],
        "candidate_count": len(candidates),
        "admitted_independent_families_by_case": admitted_by_case,
        "coded_admitted_records_by_case": coded_by_case,
        "gates": gates,
        "interpretation": (
            "The source-independence gap that blocked the first-coder coverage gate is now filled at the discovery/first-coding level: "
            "INSEC supplies explicit Nepal civilian incident evidence independent of OHCHR, and Afghanistan Rights Monitor supplies an independently originated 2010 casualty estimate overlapping the UNAMA/OHCHR monitoring era. "
            "This does not authorize confirmatory historical harm validation: blind second coding, reliability assessment, source-byte binding where obtainable, and Pineland semantic/retention identification remain outstanding."
        ),
        "next_licensed_step": "Freeze and build a blind second-coder packet containing the union of the original first-coder harm records and admitted independent-overlap records, while withholding first-coder values and decisions."
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
