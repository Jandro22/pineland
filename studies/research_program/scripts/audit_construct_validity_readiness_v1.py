"""Audit case-level construct-validity readiness without changing frozen inputs."""
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


OUT = ROOT / "studies" / "research_program" / "construct_validity_readiness_audit_v1.json"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _record(path: Path):
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def audit_nepal() -> dict:
    base = ROOT / "studies" / "nepal_2001_2006"
    study_path = base / "config" / "study.json"
    split_path = base / "config" / "split_manifest.json"
    plan_path = base / "config" / "control_presence_evidence_plan.json"
    projection_path = base / "config" / "control_presence_projection.json"
    evidence_path = base / "data" / "processed" / "nepal_sparse_control_presence.csv"
    provenance_path = base / "data" / "processed" / "nepal_sparse_control_presence_provenance.json"
    district_path = base / "config" / "districts.csv"

    study = _json(study_path)
    split = _json(split_path)
    plan = _json(plan_path)
    provenance = _json(provenance_path)
    evidence = _csv(evidence_path)
    districts = {row["district_id"]: row for row in _csv(district_path)}
    start = _parse_date(study["period"]["start"])
    end = _parse_date(study["period"]["end"])

    overlap = [
        row for row in evidence
        if _parse_date(row["end_date"]) >= start and _parse_date(row["start_date"]) <= end
    ]
    overlap_districts = sorted({row["district_id"] for row in overlap})
    geographic_holdout = [
        row for row in overlap
        if districts.get(row["district_id"], {}).get("is_eastern_holdout", "").lower() == "true"
    ]
    training_geography = [row for row in overlap if row not in geographic_holdout]

    provenance_claim = provenance.get("limitations", "")
    claimed_overlap = 4 if "Only four observations overlap" in provenance_claim else None
    checks = {
        "independent_of_ucdp_claimed": provenance.get("constructed_independently_of_ucdp") is True,
        "missingness_not_carried_forward": "never carry" in provenance.get("missingness_rule", "").lower(),
        "structured_sparse_evidence_exists": len(evidence) > 0,
        "plan_status_is_stale": plan.get("status") == "plan_only_no_structured_presence_panel_ingested" and len(evidence) > 0,
        "provenance_overlap_count_matches_frozen_study_period": (
            claimed_overlap is None or claimed_overlap == len(overlap)
        ),
        "has_any_analytical_period_control_evidence": len(overlap) > 0,
        "has_geographic_holdout_control_evidence": len(geographic_holdout) > 0,
        "has_longitudinal_representative_control_panel": False,
    }
    return {
        "status": "sparse_independent_evidence_not_longitudinal_panel",
        "study_period": {"start": start.isoformat(), "end": end.isoformat()},
        "total_sparse_rows": len(evidence),
        "analytical_period_overlap_rows": len(overlap),
        "analytical_period_unique_districts": len(overlap_districts),
        "analytical_period_district_ids": overlap_districts,
        "training_geography_overlap_rows": len(training_geography),
        "geographic_holdout_overlap_rows": len(geographic_holdout),
        "provenance_claimed_overlap_rows": claimed_overlap,
        "projection_frozen_before_accuracy": _json(projection_path).get("frozen_before_accuracy") is True,
        "checks": checks,
        "construct_validity_gate_passed": False,
        "blocking_reasons": [
            "Only three sparse independent observations overlap the frozen analytical period.",
            "No independent sparse-control observation lies in the frozen Eastern geographic holdout.",
            "The evidence is purposive and cannot validate a longitudinal district-week latent-control trajectory.",
            "The control-presence plan status is stale relative to the now-ingested sparse evidence file.",
            "The sparse-evidence provenance claims four analytical-period overlaps, but the frozen study dates yield three.",
        ],
        "permitted_use": (
            "Independent qualitative/sparse construct cross-check on the three overlapping training-geography observations only; "
            "not calibration, not geographic-holdout validation, and not longitudinal control scoring."
        ),
        "inputs": [_record(path) for path in (
            study_path, split_path, plan_path, projection_path, evidence_path,
            provenance_path, district_path,
        )],
    }


def audit_afghanistan() -> dict:
    base = ROOT / "studies" / "afghanistan_2004_2021"
    design_path = base / "config" / "study_design.json"
    observation_path = base / "config" / "control_observation_model.json"
    validation_path = base / "config" / "control_validation_plan.json"
    control_path = base / "data" / "processed" / "sigar_oct2017_control_401.csv"
    crosswalk_path = base / "data" / "processed" / "sigar_407_to_401_crosswalk.csv"
    source_manifest_path = base / "data" / "processed" / "source_manifest.json"

    design = _json(design_path)
    observation = _json(observation_path)
    validation = _json(validation_path)
    control = _csv(control_path)
    crosswalk = _csv(crosswalk_path)

    unique_ids = {row["district_id"] for row in control}
    no_single_status = [row for row in control if not row.get("single_source_status")]
    no_numeric_control = [row for row in control if not row.get("government_control_index")]
    aggregate_rows = [row for row in control if int(row.get("source_district_count") or 0) > 1]
    relation_counts: dict[str, int] = {}
    for row in crosswalk:
        relation = row.get("relation") or "MISSING"
        relation_counts[relation] = relation_counts.get(relation, 0) + 1

    checks = {
        "independent_control_source_declared": design.get("control_source_policy", "").startswith("independent of UCDP"),
        "observation_operator_unfitted": observation.get("fitting") == "none",
        "observation_operator_prospective": observation.get("status") == "prospective_unfitted_observation_operator",
        "all_401_analysis_districts_present": len(control) == 401 and len(unique_ids) == 401,
        "crosswalk_accounts_for_407_source_rows": len(crosswalk) == 407,
        "all_401_have_single_source_category": len(no_single_status) == 0,
        "all_401_have_numeric_control_index": len(no_numeric_control) == 0,
        "training_only_control_success_threshold_preregistered": (
            validation.get("success_gate", {}).get("status") != "blocked_on_training_only_control_competitors"
        ),
        "longitudinal_pre_target_control_panel_exists": False,
    }
    return {
        "status": "strong_single_snapshot_with_crosswalk_not_longitudinal_construct_validation",
        "target_date": validation.get("target_date"),
        "analysis_district_rows": len(control),
        "unique_analysis_district_ids": len(unique_ids),
        "source_crosswalk_rows": len(crosswalk),
        "crosswalk_relation_counts": relation_counts,
        "rows_without_single_source_status": len(no_single_status),
        "rows_without_numeric_control_index": len(no_numeric_control),
        "multi_source_aggregate_rows": len(aggregate_rows),
        "districts_without_numeric_control_index": [
            {"district_id": row["district_id"], "province": row["province_name"], "district": row["district_name"]}
            for row in no_numeric_control
        ],
        "checks": checks,
        "construct_validity_gate_passed": False,
        "blocking_reasons": [
            "The SIGAR evidence is a single October 2017 cross-section, not a longitudinal 2004-2021 control panel.",
            "Eight harmonized districts have no single-source SIGAR category after the 407-to-401 crosswalk; seven are multi-source aggregates.",
            "At least one harmonized district has no numeric SIGAR control value and must remain missing.",
            "The prospective control-validation plan explicitly lacks a preregistered training-only numeric success threshold.",
        ],
        "permitted_use": (
            "Independent target-date construct assessment with the frozen observation operator, preserving crosswalk/missingness uncertainty; "
            "not calibration and not evidence that the entire latent control trajectory is historically valid."
        ),
        "inputs": [_record(path) for path in (
            design_path, observation_path, validation_path, control_path,
            crosswalk_path, source_manifest_path,
        )],
    }


def main() -> int:
    repo_before = repository_state(ROOT)
    payload = {
        "schema_version": "pineland.construct_validity_readiness_audit.v1",
        "status": "audit_not_model_change",
        "historical_outcomes_used_for_parameter_fitting": False,
        "core_modified": False,
        "nepal": audit_nepal(),
        "afghanistan": audit_afghanistan(),
        "program_gate": {
            "passed": False,
            "reason": (
                "Neither case currently supplies the longitudinal, independently measured local control/presence evidence required "
                "to validate the full latent-control trajectory. Afghanistan has a strong target-date cross-section; Nepal has only sparse training-geography evidence."
            ),
            "next_evidence_priority": [
                "Nepal: independently code additional dated actor-specific presence/control evidence, prioritizing the frozen Eastern geographic holdout and 2005-2006 period.",
                "Afghanistan: construct a harmonized pre-target longitudinal control/presence panel or explicitly retain target-date-only construct validation.",
                "For both: preserve source-level uncertainty, actor identity, date interval, geography, and missingness rather than imputing from violence."
            ],
        },
        "repository_before": repo_before,
    }
    payload["repository_after"] = repository_state(ROOT)
    payload["tracked_diff_stable"] = (
        payload["repository_before"].get("tracked_diff_sha256") ==
        payload["repository_after"].get("tracked_diff_sha256")
    )
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.construct_validity_readiness_audit_manifest.v1",
        "artifact": OUT.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(OUT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "tracked_diff_stable": payload["tracked_diff_stable"],
    }
    OUT.with_name(OUT.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(OUT),
        "tracked_diff_stable": payload["tracked_diff_stable"],
        "nepal": {
            "overlap_rows": payload["nepal"]["analytical_period_overlap_rows"],
            "geographic_holdout_rows": payload["nepal"]["geographic_holdout_overlap_rows"],
            "gate": payload["nepal"]["construct_validity_gate_passed"],
        },
        "afghanistan": {
            "rows": payload["afghanistan"]["analysis_district_rows"],
            "missing_numeric": payload["afghanistan"]["rows_without_numeric_control_index"],
            "gate": payload["afghanistan"]["construct_validity_gate_passed"],
        },
        "program_gate": payload["program_gate"]["passed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
