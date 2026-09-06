"""Audit only the schema/retention needed for future construct checks; do not inspect values."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import file_sha256, repository_state  # noqa: E402

RUN_DIR = ROOT / "studies/nepal_2001_2006/runs/post_structural_repair/final_empirical_rescore_v5"
OUT = ROOT / "studies/research_program/nepal_v5_construct_retention_audit_v1.json"
MAPPING = ROOT / "studies/research_program/nepal_construct_observation_mapping_contract_v1.json"


def shape_only(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    checkpoints = raw.get("checkpoints") or []
    first = checkpoints[0] if checkpoints else {}
    community_state = first.get("community_state") or {}
    control = first.get("control") or {}
    first_community = next(iter(community_state.values()), {})
    first_district = next(iter(control.values()), {})
    actor_dims = {
        actor: sorted(vector.keys()) if isinstance(vector, dict) else []
        for actor, vector in first_district.items()
    } if isinstance(first_district, dict) else {}
    return {
        "filename": path.name,
        "sha256": file_sha256(path),
        "top_level_fields": sorted(raw.keys()),
        "checkpoint_count": len(checkpoints),
        "checkpoint_fields": sorted(first.keys()),
        "community_state_fields": sorted(first_community.keys()) if isinstance(first_community, dict) else [],
        "district_control_actor_dimensions": actor_dims,
        "movement_history_present": isinstance(raw.get("movement_history"), list),
        "initial_formations_present": isinstance(raw.get("initial_formations"), (list, dict)),
        "final_formations_present": isinstance(raw.get("final_formations"), (list, dict)),
        "contacts_present": isinstance(raw.get("contacts"), list),
    }


def main() -> int:
    files = sorted(RUN_DIR.glob("seed_*_agents_750.json"))
    records = [shape_only(path) for path in files]
    required_dims = {"formal", "physical", "administrative", "legal", "fiscal", "social", "expected"}
    all_control = all(
        required_dims.issubset(set(rec["district_control_actor_dimensions"].get("government", [])))
        and required_dims.issubset(set(rec["district_control_actor_dimensions"].get("insurgent", [])))
        for rec in records
    ) if records else False
    all_community = all(
        {"locality_id", "government_cooperation", "insurgent_sympathy"}.issubset(set(rec["community_state_fields"]))
        for rec in records
    ) if records else False
    all_trajectory = all(
        rec["movement_history_present"] and rec["initial_formations_present"] and rec["final_formations_present"]
        for rec in records
    ) if records else False
    payload = {
        "schema_version": "pineland.nepal_v5_construct_retention_audit.v1",
        "status": "schema_only_no_model_values_examined",
        "mapping_contract_sha256": file_sha256(MAPPING),
        "member_count": len(records),
        "expected_member_count": 8,
        "all_members_present": len(records) == 8,
        "all_members_retain_seven_dimensional_district_control": all_control,
        "all_members_retain_community_locality_and_attitude_state": all_community,
        "all_members_retain_formation_movement_trajectory_support": all_trajectory,
        "direct_locality_level_seven_dimensional_control_retained": False,
        "dated_security_post_or_patrol_inventory_retention_established": False,
        "records": records,
        "interpretation": "Stored v5 output can support district-level control checks and potentially reconstruct some fielded-presence trajectories, but it does not by itself license converting narrow locality evidence into district-wide control.",
        "repository_state": repository_state(ROOT)
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "member_count": payload["member_count"],
        "all_members_present": payload["all_members_present"],
        "district_control_retained": all_control,
        "community_state_retained": all_community,
        "trajectory_support_retained": all_trajectory,
        "locality_control_retained": payload["direct_locality_level_seven_dimensional_control_retained"]
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
