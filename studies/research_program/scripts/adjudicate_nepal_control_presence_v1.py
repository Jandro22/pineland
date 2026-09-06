"""Source-bound adjudication of the locked blind Nepal control/presence codings.

The exact preregistered agreement result is preserved unchanged.  Adjudication
resolves ontology labels and the three observable disagreements using rules
frozen before unblinding; it does not alter historical predictive scoring.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

FIRST = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_staging_v1.csv"
SECOND = ROOT / "studies/research_program/nepal_second_coder_completed_v1.csv"
KEY = ROOT / "studies/research_program/nepal_second_coder_blind_key_v1.json"
AGREEMENT = ROOT / "studies/research_program/nepal_second_coder_agreement_v1.json"
ADJ_CONTRACT = ROOT / "studies/research_program/nepal_control_presence_adjudication_contract_v1.json"
MAP_CONTRACT = ROOT / "studies/research_program/nepal_construct_observation_mapping_contract_v1.json"
ACQ_CONTRACT = ROOT / "studies/research_program/nepal_control_presence_acquisition_contract_v1.json"
LOCK = ROOT / "studies/research_program/nepal_second_coder_shard_lock_v1.json"
MERGE_MANIFEST = ROOT / "studies/research_program/nepal_second_coder_merge_manifest_v1.json"
OUT_CSV = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_adjudicated_v1.csv"
OUT_JSON = ROOT / "studies/research_program/nepal_control_presence_adjudication_v1.json"


DECISIONS = {
    "11b8d4a5e627": dict(
        actor_id="insurgent", observable="maoist_shadow_governance",
        date_start="2006-09-04", date_end="2006-09-04",
        value_or_category="municipal_tax_collection_and_contract_allocation",
        spatial_scope="Damak, Bhadrapur, and Mechinagar municipalities",
        confidence="HIGH",
        rationale="Both coders agree on construct/date. Historical CPN (Maoist) is mapped to the model's canonical insurgent actor; scope remains the three named municipalities.",
    ),
    "2c7a45d69253": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2004-09-01", date_end="2004-09-07",
        value_or_category="maoist_imposed_blockade_of_ilam_headquarters_and_trade_centres",
        spatial_scope="Ilam district headquarters and explicitly reported trade centres",
        confidence="HIGH",
        rationale="Both coders agree on construct. The narrower independently coded 1-7 September blockade interval is retained; 8 September fear/emptying is not carried into the blockade interval.",
    ),
    "39d96300ced7": dict(
        actor_id="insurgent", observable="maoist_armed_presence",
        date_start="2006-10-11", date_end="2006-10-11",
        value_or_category="school_used_as_maoist_barracks_with_25_cadres_reported_present",
        spatial_scope="Sharada Higher Secondary School compound, Khanar VDC, Sunsari district",
        confidence="HIGH",
        rationale="Both coders agree on armed presence. The source-report date is used rather than the publication-week envelope.",
    ),
    "4f8bf2492d43": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2005-10-01", date_end="2005-12-31",
        value_or_category="homes_padlocked_or_marked_and_land_seized_from_RNA_families",
        spatial_scope="reported Khotang cases; specific localities not stated",
        confidence="MEDIUM",
        rationale="Both coders agree on construct and quarter. Confidence is conservatively reduced to MEDIUM because OHCHR reports district cases without exact localities or incident dates.",
    ),
    "60a7cee12357": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2005-09-09", date_end="2005-09-09",
        value_or_category="maoist_road_blockade_active_at_panchthar_district_headquarters",
        spatial_scope="Panchthar district headquarters (Phidim) and its road access",
        confidence="HIGH",
        rationale="Both coders agree on the blockade. The publication-date current-status observation is retained without back-carry to the ceasefire start.",
    ),
    "6d5a31f877f2": dict(
        actor_id="insurgent", observable="maoist_shadow_governance",
        date_start="2004-05-16", date_end="2004-05-16",
        value_or_category="peoples_government_taxation_and_NGO_project_approval_regime",
        spatial_scope="listed lower-Solukhumbu VDCs",
        confidence="HIGH",
        rationale="Both coders agree on fiscal/regulatory shadow governance. The source dateline is retained as the observation date; no publication-week carry-forward.",
    ),
    "6e04e40be38e": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2005-09-09", date_end="2005-09-09",
        value_or_category="passengers_turned_back_by_maoist_blockade",
        spatial_scope="Rakke/Ranke Bajar on the Ilam-Phidim border-road corridor",
        confidence="MEDIUM",
        rationale="Both coders agree; the corridor location is retained without district-wide extrapolation and the observation is limited to the report date.",
    ),
    "7ad902d44286": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2004-08-25", date_end="2004-09-08",
        value_or_category="cordon_blockade_and_closure_sequence_at_phidim",
        spatial_scope="Phidim/Phidim Bazaar, Panchthar district headquarters",
        confidence="HIGH",
        rationale="Both coders independently recover the explicitly dated Maoist/PLA/people's-government program and its district-headquarters scope.",
    ),
    "7c95742e2e81": dict(
        actor_id="government", observable="government_administrative_presence",
        date_start="2005-10-07", date_end="2005-10-07",
        value_or_category="government_withdrawn_from_rural_villages_with_VDC_and_development_staff_concentrated_in_Khandbari",
        spatial_scope="Sankhuwasabha rural villages versus Khandbari district headquarters",
        confidence="HIGH",
        rationale="The source explicitly reports total government withdrawal from villages, VDC/development/health staff in Khandbari, and police not venturing into villages. This is retained as the distinct government-administrative observation; Maoist movement restriction is separately retained in eec925a82a6c.",
    ),
    "a4f3a0b74b48": dict(
        actor_id="insurgent", observable="maoist_shadow_governance",
        date_start="2005-09-03", date_end="2005-09-09",
        value_or_category="household_tax_rice_and_cash_demands_after_ceasefire",
        spatial_scope="Risku and Tribeni areas of Udayapur district",
        confidence="MEDIUM",
        rationale="Both coders agree on local taxation/shadow governance. The source gives an occurrence window after the 3 September ceasefire through the report date; confidence is conservatively MEDIUM because it does not establish a broader administrative apparatus.",
    ),
    "acd798e13d7b": dict(
        actor_id="insurgent", observable="maoist_shadow_governance",
        date_start="2005-09-09", date_end="2005-09-09",
        value_or_category="maoist_ban_preventing_NGO_and_community_organization_operation",
        spatial_scope="Tehrathum district NGO/community-organization activity; exact subdistrict locations unspecified",
        confidence="HIGH",
        rationale="Observable disagreement resolved using the prospectively frozen mapping: NGO/permit/rule enforcement may identify administrative/legal shadow-governance reach. The source says a yearlong ban remained in force, but the exact one-year start date is not back-calculated; current status is coded on the report date.",
    ),
    "ba5b17f0971e": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2005-09-09", date_end="2005-09-09",
        value_or_category="maoist_road_blockade_active_at_taplejung_district_headquarters",
        spatial_scope="Taplejung district headquarters",
        confidence="HIGH",
        rationale="Both coders agree. The current-status blockade is retained on the report date without district-wide extrapolation.",
    ),
    "eec925a82a6c": dict(
        actor_id="insurgent", observable="territorial_access_constraint",
        date_start="2005-10-07", date_end="2005-10-07",
        value_or_category="maoist_restrictions_on_village_to_Khandbari_and_market_movement",
        spatial_scope="Sankhuwasabha village-to-Khandbari and village-to-market movement",
        confidence="HIGH",
        rationale="The source supports both taxation and mobility authority. Under the frozen narrower-claim rule, the explicit movement restriction is retained as territorial access constraint rather than combining two constructs in one row.",
    ),
    "fa4fb4b19cd6": dict(
        actor_id="insurgent", observable="maoist_shadow_governance",
        date_start="2006-08-09", date_end="2006-08-09",
        value_or_category="local_permission_payment_protection_and_police_interference_rules",
        spatial_scope="named rural Morang border-area VDCs, especially Mahadeva and Jhurkiya",
        confidence="MEDIUM",
        rationale="Both coders identify de facto local regulation/shadow governance. The report date and narrower named-area scope are retained.",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    agreement = json.loads(AGREEMENT.read_text(encoding="utf-8"))
    key = json.loads(KEY.read_text(encoding="utf-8"))["mapping"]
    first = {row["record_id"]: row for row in read_csv(FIRST)}
    second = {row["blind_id"]: row for row in read_csv(SECOND)}
    if set(second) != set(DECISIONS):
        raise SystemExit("adjudication decisions do not exactly cover locked second-coder rows")

    output_fields = [
        "blind_id", "source_id", "source_title", "publisher", "source_url_or_archive_ref",
        "record_id", "date_start", "date_end", "district_id", "district_name", "actor_id",
        "observable", "value_or_category", "spatial_scope", "temporal_precision", "confidence",
        "source_passage_or_precise_locator", "adjudication_rationale", "first_coder_actor",
        "second_coder_actor", "first_coder_observable", "second_coder_observable",
        "first_coder_confidence", "second_coder_confidence", "adjudication_status"
    ]
    adjudicated: list[dict[str, str]] = []
    semantic_actor_agreement = 0
    raw_decisions = []
    for blind_id, decision in DECISIONS.items():
        f = first[key[blind_id]["first_coder_record_id"]]
        s = second[blind_id]
        second_actor = s["actor_id"].strip().lower()
        semantic_second = (
            "insurgent" if ("maoist" in second_actor or "pla" in second_actor) else
            "government" if second_actor in {"government", "state", "rna", "police"} else
            second_actor
        )
        semantic_agree = f["actor_id"] == semantic_second
        semantic_actor_agreement += int(semantic_agree)
        temporal_precision = (
            "day" if decision["date_start"] == decision["date_end"] else "bounded_interval"
        )
        row = {
            "blind_id": blind_id,
            "source_id": f["source_id"], "source_title": f["source_title"],
            "publisher": f["publisher"], "source_url_or_archive_ref": f["source_url_or_archive_ref"],
            "record_id": f["record_id"], "date_start": decision["date_start"],
            "date_end": decision["date_end"], "district_id": f["district_id"],
            "district_name": f["district_name"], "actor_id": decision["actor_id"],
            "observable": decision["observable"], "value_or_category": decision["value_or_category"],
            "spatial_scope": decision["spatial_scope"], "temporal_precision": temporal_precision,
            "confidence": decision["confidence"],
            "source_passage_or_precise_locator": f["source_passage_or_precise_locator"],
            "adjudication_rationale": decision["rationale"],
            "first_coder_actor": f["actor_id"], "second_coder_actor": s["actor_id"],
            "first_coder_observable": f["observable"], "second_coder_observable": s["observable"],
            "first_coder_confidence": f["confidence"], "second_coder_confidence": s["confidence"],
            "adjudication_status": "adjudicated_source_bound",
        }
        adjudicated.append(row)
        raw_decisions.append({
            "blind_id": blind_id,
            "semantic_actor_agreement_before_adjudication": semantic_agree,
            "observable_exact_agreement_before_adjudication": f["observable"] == s["observable"],
            "decision": decision,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(adjudicated)

    acq = json.loads(ACQ_CONTRACT.read_text(encoding="utf-8"))
    priority_start = date.fromisoformat(acq["frozen_scope"]["priority_period_start"])
    priority_end = date.fromisoformat(acq["frozen_scope"]["priority_period_end"])
    districts = {row["district_id"] for row in adjudicated}
    priority_districts = {
        row["district_id"] for row in adjudicated
        if date.fromisoformat(row["date_end"]) >= priority_start
        and date.fromisoformat(row["date_start"]) <= priority_end
    }
    source_families = {row["publisher"] for row in adjudicated}
    coverage_gate = acq["target_coverage_gate"]
    coverage = {
        "unique_eastern_holdout_districts": len(districts),
        "unique_2005_2006_eastern_holdout_districts": len(priority_districts),
        "distinct_source_families": len(source_families),
        "minimum_eastern_districts_pass": len(districts) >= int(coverage_gate["minimum_unique_eastern_holdout_districts_with_admissible_evidence"]),
        "minimum_priority_period_districts_pass": len(priority_districts) >= int(coverage_gate["minimum_unique_eastern_holdout_districts_with_2005_2006_evidence"]),
        "minimum_source_families_pass": len(source_families) >= int(coverage_gate["minimum_distinct_source_families"]),
    }
    coverage["passed"] = all(v for k, v in coverage.items() if k.endswith("_pass"))

    primary = agreement["metrics"]
    payload = {
        "schema_version": "pineland.nepal_control_presence_adjudication.v1",
        "status": "adjudicated_construct_evidence_not_historical_rescore",
        "primary_preregistered_agreement_preserved": {
            "metrics": primary,
            "quality_gates": agreement["quality_gates"],
            "pre_adjudication_quality_gate_passed": agreement["pre_adjudication_quality_gate_passed"],
            "note": "The failed exact actor-string gate is retained unchanged and is not replaced by the post-hoc semantic sensitivity metric."
        },
        "posthoc_actor_ontology_sensitivity": {
            "semantic_equivalent_rows": semantic_actor_agreement,
            "total_rows": len(adjudicated),
            "semantic_actor_agreement": semantic_actor_agreement / len(adjudicated),
            "interpretation": "Secondary diagnostic only: CPN (Maoist)/Maoist/PLA labels are mapped to Pineland's canonical insurgent actor. The Sankhuwasabha government-withdrawal row remains a substantive actor/observable disagreement before adjudication."
        },
        "observable_disagreements_adjudicated": [
            item for item in raw_decisions if not item["observable_exact_agreement_before_adjudication"]
        ],
        "all_disagreements_adjudicated": True,
        "unresolved_disagreements": [],
        "adjudicated_row_count": len(adjudicated),
        "coverage_after_adjudication": coverage,
        "confirmatory_construct_evidence_use_authorized": bool(coverage["passed"]),
        "construct_validity_result": "not_yet_scored_against_model_state",
        "historical_predictive_rescoring_authorized": False,
        "parameter_fitting_authorized": False,
        "core_change_authorized": False,
        "inputs": {
            "first_coder_sha256": file_sha256(FIRST),
            "locked_second_coder_sha256": file_sha256(SECOND),
            "agreement_sha256": file_sha256(AGREEMENT),
            "adjudication_contract_sha256": file_sha256(ADJ_CONTRACT),
            "mapping_contract_sha256": file_sha256(MAP_CONTRACT),
            "acquisition_contract_sha256": file_sha256(ACQ_CONTRACT),
            "shard_lock_sha256": file_sha256(LOCK),
            "merge_manifest_sha256": file_sha256(MERGE_MANIFEST),
        },
        "adjudicated_csv": OUT_CSV.relative_to(ROOT).as_posix(),
        "adjudicated_csv_sha256": file_sha256(OUT_CSV),
        "decisions": raw_decisions,
        "repository_state": repository_state(ROOT),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary_gate_passed": payload["primary_preregistered_agreement_preserved"]["pre_adjudication_quality_gate_passed"],
        "primary_actor_exact": primary["actor_agreement_among_jointly_admissible"],
        "primary_observable_exact": primary["observable_agreement_among_jointly_admissible"],
        "posthoc_semantic_actor": payload["posthoc_actor_ontology_sensitivity"]["semantic_actor_agreement"],
        "observable_disagreements_adjudicated": len(payload["observable_disagreements_adjudicated"]),
        "coverage": coverage,
        "confirmatory_construct_evidence_use_authorized": payload["confirmatory_construct_evidence_use_authorized"],
        "adjudicated_csv_sha256": payload["adjudicated_csv_sha256"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
