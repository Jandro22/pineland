"""Classify adjudicated Nepal evidence against prospectively frozen state-retention rules.

This audit deliberately inspects no v5 model values.  It uses only the
adjudicated historical evidence, empirical geography, and previously audited
output schema/retention.  Rows lacking construct+space+time compatibility are
retained as unscored rather than projected onto a broader latent state.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

EVIDENCE = ROOT / "studies/nepal_2001_2006/data/processed/nepal_eastern_control_presence_adjudicated_v1.csv"
GEOGRAPHY = ROOT / "studies/nepal_2001_2006/data/processed/settlement_geography.csv"
MAPPING = ROOT / "studies/research_program/nepal_construct_observation_mapping_contract_v1.json"
RETENTION = ROOT / "studies/research_program/nepal_v5_construct_retention_audit_v1.json"
ADJUDICATION = ROOT / "studies/research_program/nepal_control_presence_adjudication_v1.json"
OUT = ROOT / "studies/research_program/nepal_construct_compatibility_audit_v1.json"


LOCALITY_HINTS = {
    "11b8d4a5e627": ["Damak", "Bhadrapur", "Mechinagar"],
    "2c7a45d69253": ["Ilam"],
    "39d96300ced7": ["Khanar"],
    "4f8bf2492d43": [],
    "60a7cee12357": ["Phidim"],
    "6d5a31f877f2": ["Jubing", "Beni", "Garma", "Kaku", "Wasa", "Kagel", "Tingla", "Kerung", "Tapting", "Patale", "Junbesi", "Sunkhani"],
    "6e04e40be38e": ["Rakke", "Ranke", "Phidim"],
    "7ad902d44286": ["Phidim"],
    "7c95742e2e81": ["Khandbari"],
    "a4f3a0b74b48": ["Risku", "Tribeni"],
    "acd798e13d7b": ["Myanglung"],
    "ba5b17f0971e": [],
    "eec925a82a6c": ["Khandbari"],
    "fa4fb4b19cd6": ["Mahadeva", "Jhurkiya", "Rangeli", "Babiyabirta"],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def main() -> int:
    evidence = read_csv(EVIDENCE)
    geography = read_csv(GEOGRAPHY)
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    retention = json.loads(RETENTION.read_text(encoding="utf-8"))
    names = {}
    for row in geography:
        names.setdefault(norm(row["name"]), []).append(row)

    rows = []
    for row in evidence:
        blind_id = row["blind_id"]
        hints = LOCALITY_HINTS.get(blind_id, [])
        exact_matches = []
        for hint in hints:
            for match in names.get(norm(hint), []):
                if match["district_id"] == row["district_id"]:
                    exact_matches.append({
                        "historical_name": hint,
                        "locality_id": match["locality_id"],
                        "model_name": match["name"],
                        "administrative_role": match["administrative_role"],
                    })

        observable = row["observable"]
        category = "unscored_retention_or_operator_mismatch"
        reasons = []
        potential_direct_state = None

        if observable in {"government_armed_presence", "maoist_armed_presence"}:
            potential_direct_state = "dated_fielded_presence"
            if not exact_matches:
                reasons.append("historical armed-presence locality has no unambiguous exact match in the retained empirical locality grid")
            if not retention.get("all_members_retain_formation_movement_trajectory_support"):
                reasons.append("formation/movement trajectory support not retained")
            # Even with movement orders, formation creation timestamps are not retained in the frozen run artifact.
            reasons.append("frozen v5 output does not establish creation time for formations absent from initial_formations, so dated presence reconstruction is incomplete")
        elif observable in {"checkpoint_or_patrol_presence", "security_post_or_garrison_presence"}:
            potential_direct_state = "dated_security_presence"
            reasons.append("dated security-post/patrol inventory retention was not established in the frozen v5 output")
        elif observable == "territorial_access_constraint":
            potential_direct_state = "dated_access_or_local_physical_authority"
            reasons.append("frozen mapping forbids district-control substitution for blockade/access evidence")
            reasons.append("dated locality-level access/physical-authority state was not retained")
        elif observable == "government_administrative_presence":
            potential_direct_state = "government_administrative_control"
            reasons.append("source distinguishes rural villages from district headquarters, while frozen v5 retains only district-level administrative control")
            reasons.append("locality-level administrative control was not retained, so the spatial contrast cannot be tested without aggregation bias")
        elif observable == "maoist_shadow_governance":
            potential_direct_state = "insurgent_administrative_legal_fiscal_social_control"
            scope_lower = row["spatial_scope"].lower()
            obviously_subdistrict = any(token in scope_lower for token in [
                "municipalit", "vdc", "lower-", "lower ", "risku", "tribeni", "border-area", "named rural"
            ])
            if obviously_subdistrict:
                reasons.append("historical governance claim is subdistrict/locality scoped while frozen v5 control is district-level")
            else:
                reasons.append("no prospectively frozen observation operator maps this specific regulatory/taxation claim to a numeric seven-dimensional district-control threshold")
            reasons.append("community cooperation/sympathy is explicitly prohibited as a substitute for governance/control")
        elif observable == "territorial_control_claim":
            potential_direct_state = "frozen_ordinal_district_control_projection"
            category = "potentially_scoreable_existing_projection"
            reasons.append("eligible only if the source itself is district-wide; no such adjudicated row is currently present")
        else:
            reasons.append("observable has no declared construct mapping")

        scoreable = category == "potentially_scoreable_existing_projection" and observable == "territorial_control_claim"
        rows.append({
            "blind_id": blind_id,
            "district_id": row["district_id"],
            "district_name": row["district_name"],
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "actor_id": row["actor_id"],
            "observable": observable,
            "spatial_scope": row["spatial_scope"],
            "historical_locality_hints": hints,
            "exact_empirical_locality_matches": exact_matches,
            "potential_direct_model_state": potential_direct_state,
            "classification": category,
            "scoreable_under_frozen_contract": scoreable,
            "blocking_reasons": reasons,
        })

    scoreable = [r for r in rows if r["scoreable_under_frozen_contract"]]
    exact_locality_rows = [r for r in rows if r["exact_empirical_locality_matches"]]
    payload = {
        "schema_version": "pineland.nepal_construct_compatibility_audit.v1",
        "status": "compatibility_audit_without_model_value_inspection",
        "model_values_inspected": False,
        "adjudicated_evidence_rows": len(rows),
        "rows_with_at_least_one_exact_empirical_locality_match": len(exact_locality_rows),
        "rows_scoreable_under_frozen_construct_mapping": len(scoreable),
        "scoreable_blind_ids": [r["blind_id"] for r in scoreable],
        "construct_validity_status": "not_identified_from_frozen_nepal_v5_outputs",
        "construct_validity_gate_passed": False,
        "interpretation": (
            "The newly adjudicated evidence materially improves historical construct measurement, but none of the 14 rows can be scored against the frozen v5 output without violating the predeclared construct/spatial mapping or inventing a post-hoc observation threshold. This is an output-retention/measurement-identification limitation, not evidence that the latent state is correct or incorrect."
        ),
        "rules_preserved": [
            "no locality claim upgraded to district control",
            "no violence proxy used",
            "no community-attitude proxy substituted for control/presence",
            "no post-hoc numeric threshold created after model values",
            "no Nepal rerun or predictive rescore licensed"
        ],
        "next_design_requirement": (
            "Future validation runs must prospectively retain dated locality-level seven-dimensional control, fixed-security/post/patrol state, formation birth/death and movement state, and a source-specific observation operator before historical values are inspected. Nepal v5 remains frozen and is not rerun to repair this limitation."
        ),
        "inputs": {
            "adjudicated_evidence_sha256": file_sha256(EVIDENCE),
            "geography_sha256": file_sha256(GEOGRAPHY),
            "mapping_contract_sha256": file_sha256(MAPPING),
            "retention_audit_sha256": file_sha256(RETENTION),
            "adjudication_sha256": file_sha256(ADJUDICATION),
        },
        "rows": rows,
        "repository_state": repository_state(ROOT),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "evidence_rows": len(rows),
        "exact_locality_match_rows": len(exact_locality_rows),
        "scoreable_rows": len(scoreable),
        "construct_validity_status": payload["construct_validity_status"],
        "construct_gate": payload["construct_validity_gate_passed"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
