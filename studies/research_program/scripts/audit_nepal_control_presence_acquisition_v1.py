"""Audit first-coder Nepal Eastern control/presence acquisition against its frozen contract."""
from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

CONTRACT = ROOT / "studies/research_program/nepal_control_presence_acquisition_contract_v1.json"
DATA = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_staging_v1.csv"
PROV = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_staging_v1_provenance.json"
OUT = ROOT / "studies/research_program/nepal_control_presence_acquisition_audit_v1.json"


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    evidence = rows(DATA)
    repo_before = repository_state(ROOT)
    priority_ids = {item["district_id"] for item in contract["frozen_scope"]["priority_districts"]}
    priority_start = date.fromisoformat(contract["frozen_scope"]["priority_period_start"])
    priority_end = date.fromisoformat(contract["frozen_scope"]["priority_period_end"])
    eastern = [row for row in evidence if row["district_id"] in priority_ids]
    priority = [
        row for row in eastern
        if date.fromisoformat(row["date_end"]) >= priority_start
        and date.fromisoformat(row["date_start"]) <= priority_end
    ]
    unique_eastern = sorted({row["district_id"] for row in eastern})
    unique_priority = sorted({row["district_id"] for row in priority})
    families = sorted({row["publisher"] for row in evidence})
    second_coded = [
        row for row in evidence
        if row.get("second_coder", "").strip()
        and row.get("adjudication_status", "").strip() not in {"", "pending_second_coder"}
    ]
    gate = contract["target_coverage_gate"]
    first_coder_gates = {
        "minimum_eastern_district_coverage": len(unique_eastern) >= int(gate["minimum_unique_eastern_holdout_districts_with_admissible_evidence"]),
        "minimum_2005_2006_eastern_coverage": len(unique_priority) >= int(gate["minimum_unique_eastern_holdout_districts_with_2005_2006_evidence"]),
        "minimum_source_families": len(families) >= int(gate["minimum_distinct_source_families"]),
        "all_rows_have_precise_locator": all(row["source_passage_or_precise_locator"].strip() for row in evidence),
        "all_rows_preserve_spatial_scope": all(row["spatial_scope"].strip() for row in evidence),
        "no_ucdp_source": all("ucdp" not in row["source_id"].lower() and "ucdp" not in row["publisher"].lower() for row in evidence),
    }
    confirmatory_gates = {
        **first_coder_gates,
        "all_rows_second_coded_and_adjudicated": len(second_coded) == len(evidence),
    }
    payload = {
        "schema_version": "pineland.nepal_control_presence_acquisition_audit.v1",
        "status": "first_coder_coverage_complete_confirmatory_gate_pending",
        "contract_sha256": file_sha256(CONTRACT),
        "data_sha256": file_sha256(DATA),
        "provenance_sha256": file_sha256(PROV),
        "row_count": len(evidence),
        "unique_eastern_holdout_districts": len(unique_eastern),
        "eastern_holdout_district_ids": unique_eastern,
        "unique_2005_2006_eastern_holdout_districts": len(unique_priority),
        "priority_period_district_ids": unique_priority,
        "source_families": families,
        "first_coder_gates": first_coder_gates,
        "first_coder_coverage_gate_passed": all(first_coder_gates.values()),
        "confirmatory_gates": confirmatory_gates,
        "confirmatory_construct_validity_use_authorized": all(confirmatory_gates.values()),
        "second_coder_rows_complete": len(second_coded),
        "next_required_action": "Independent second coding and adjudication of every staged row before any confirmatory construct-validity score is computed.",
        "historical_rescoring_authorized": False,
        "parameter_fitting_authorized": False,
        "repository_before": repo_before,
        "repository_after": repository_state(ROOT)
    }
    payload["tracked_diff_stable"] = payload["repository_before"].get("tracked_diff_sha256") == payload["repository_after"].get("tracked_diff_sha256")
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": payload["row_count"],
        "unique_eastern": payload["unique_eastern_holdout_districts"],
        "unique_2005_2006": payload["unique_2005_2006_eastern_holdout_districts"],
        "source_families": payload["source_families"],
        "first_coder_gate": payload["first_coder_coverage_gate_passed"],
        "confirmatory_authorized": payload["confirmatory_construct_validity_use_authorized"],
        "tracked_diff_stable": payload["tracked_diff_stable"]
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
