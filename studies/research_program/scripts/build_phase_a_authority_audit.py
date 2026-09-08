"""Build and validate the Phase-A packed-state authority inventory."""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.ensemble import StaticWorldTopology  # noqa: E402
from pineland_sim.native_ensemble import PackedHotState  # noqa: E402
from pineland_sim.reproducibility import model_sha256, repository_state  # noqa: E402


AUTHORITIES = {
    "PACKED_AUTHORITATIVE",
    "STATIC_TOPOLOGY",
    "EXPLICIT_SPARSE_BOUNDARY",
    "OUTPUT_ONLY",
}


PACKED_AUTHORITIES: dict[str, tuple[str, str, bool]] = {
    # Batch shape and indexing are immutable for a packed topology.
    "particle_count": ("OUTPUT_ONLY", "batch shape, not a scientific state input", False),
    "formation_ids": ("STATIC_TOPOLOGY", "formation codebook", False),
    "organization_ids": ("STATIC_TOPOLOGY", "organization codebook", False),
    "patrol_ids": ("STATIC_TOPOLOGY", "patrol codebook", False),
    "post_ids": ("STATIC_TOPOLOGY", "security-post codebook", False),
    "supply_source_ids": ("STATIC_TOPOLOGY", "supply-source codebook", False),
    "formation_index": ("STATIC_TOPOLOGY", "formation codebook index", False),
    "organization_index": ("STATIC_TOPOLOGY", "organization codebook index", False),
    "patrol_index": ("STATIC_TOPOLOGY", "patrol codebook index", False),
    "post_index": ("STATIC_TOPOLOGY", "security-post codebook index", False),
    "supply_source_index": ("STATIC_TOPOLOGY", "supply-source codebook index", False),
    "locality_ids": ("STATIC_TOPOLOGY", "locality codebook", False),
    "microzone_ids": ("STATIC_TOPOLOGY", "microzone codebook", False),

    # Organization/action state.
    "organization_present": ("PACKED_AUTHORITATIVE", "organization existence", True),
    "organization_active": ("PACKED_AUTHORITATIVE", "organization status", True),
    "organization_kind": ("PACKED_AUTHORITATIVE", "organization type", True),
    "organization_government_side": ("PACKED_AUTHORITATIVE", "actor-side resolution", True),
    "organization_action_eligible": ("PACKED_AUTHORITATIVE", "organized-action eligibility", True),
    "manpower_pool": ("PACKED_AUTHORITATIVE", "unfielded organizational manpower", True),
    "manpower_supply_reserve": ("PACKED_AUTHORITATIVE", "local manpower sustainment reserve", True),

    # Formation, patrol and post physical state.
    "formation_present": ("PACKED_AUTHORITATIVE", "formation existence", True),
    "formation_organization": ("PACKED_AUTHORITATIVE", "formation ownership", True),
    "formation_locality": ("PACKED_AUTHORITATIVE", "formation locality", True),
    "formation_microzone": ("PACKED_AUTHORITATIVE", "formation microzone", True),
    "formation_values": ("PACKED_AUTHORITATIVE", "personnel/readiness/supply/quality state", True),
    "formation_flags": ("PACKED_AUTHORITATIVE", "moving/outside/effective state", True),
    "post_present": ("PACKED_AUTHORITATIVE", "security-post existence", True),
    "post_values": ("PACKED_AUTHORITATIVE", "post presence/availability", True),
    "post_indices": ("PACKED_AUTHORITATIVE", "post ownership/location links", True),
    "patrol_present": ("PACKED_AUTHORITATIVE", "patrol existence", True),
    "patrol_values": ("PACKED_AUTHORITATIVE", "patrol availability/response memory", True),
    "patrol_indices": ("PACKED_AUTHORITATIVE", "patrol ownership/location links", True),
    "locality_population": ("PACKED_AUTHORITATIVE", "mutable locality population after civilian harm", True),

    # Supply/logistics state.
    "supply_source_present": ("PACKED_AUTHORITATIVE", "supply-source existence", True),
    "supply_source_organization": ("PACKED_AUTHORITATIVE", "supply-source ownership", True),
    "supply_source_locality": ("PACKED_AUTHORITATIVE", "supply-source locality", True),
    "supply_source_stock": ("PACKED_AUTHORITATIVE", "mutable source stock", True),

    # Belief and physical-control state.
    "zone_presence_memory": ("PACKED_AUTHORITATIVE", "government/insurgent presence memory", True),
    "zone_presence_updated_at": ("PACKED_AUTHORITATIVE", "presence-memory clocks", True),
    "zone_physical_control": ("PACKED_AUTHORITATIVE", "aggregate zone physical control", True),
    "zone_insurgent_side_raw": ("PACKED_AUTHORITATIVE", "literal insurgent-side physical memory", True),
    "zone_org_presence_memory": ("PACKED_AUTHORITATIVE", "organization-specific presence memory", True),
    "zone_org_presence_updated_at": ("PACKED_AUTHORITATIVE", "organization presence clocks", True),
    "zone_org_physical_control": ("PACKED_AUTHORITATIVE", "organization-specific physical control", True),
    "zone_population_share": ("STATIC_TOPOLOGY", "fixed microzone population share", True),
    "config_values": ("PACKED_AUTHORITATIVE", "lane-specific scientific configuration", True),
    "next_clocks": ("PACKED_AUTHORITATIVE", "migrated process clock continuation", True),
    "clock_intervals": ("PACKED_AUTHORITATIVE", "migrated process clock intervals", True),
    "rng_states": ("PACKED_AUTHORITATIVE", "migrated process RNG continuation", True),
    "dirty_lanes": ("OUTPUT_ONLY", "synchronization bookkeeping", False),
}


TOPOLOGY_FIELDS = {
    field.name for field in fields(StaticWorldTopology)
}


SPARSE_BOUNDARIES = [
    {
        "boundary": "scheduler_queue_and_sequence",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "Simulation.scheduler",
        "reason": "Exact event ordering is retained in the scheduler oracle.",
    },
    {
        "boundary": "process_rng_streams_and_event_counter",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "ProcessEngine",
        "reason": "Reference handlers and fork lineage metadata retain exact continuation.",
    },
    {
        "boundary": "rich_entity_creation",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "NativeEnsembleRunner._rebuild_structure",
        "reason": "A structural event rebuilds the packed codebook once, without hiding a rich-world fallback.",
    },
    {
        "boundary": "realized_organized_action",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "NativeEnsembleRunner._organized_action_event",
        "reason": "Only realized actions cross to the exact reference consequence handler; no-op hazards remain packed.",
    },
    {
        "boundary": "non_migrated_event_types",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "NativeEnsembleRunner._execute_reference_event",
        "reason": "The boundary is named and counted; it is never an implicit particle.advance_to fallback.",
    },
    {
        "boundary": "numeric_information_rows_and_relays",
        "authority": "EXPLICIT_SPARSE_BOUNDARY",
        "owner": "NumericInformationRuntime",
        "reason": "Fixed-width reports/relays are retained as the explicit information boundary representation.",
    },
]


def build(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing authority evidence: {output}"
        )
    packed_fields = {field.name for field in fields(PackedHotState)}
    missing = sorted(packed_fields - PACKED_AUTHORITIES.keys())
    extra = sorted(PACKED_AUTHORITIES.keys() - packed_fields)
    invalid = sorted(
        name for name, (authority, _reason, _future) in PACKED_AUTHORITIES.items()
        if authority not in AUTHORITIES
    )
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_packed_state_authority_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "command": "python studies/research_program/scripts/build_phase_a_authority_audit.py",
        },
        "authority_legend": sorted(AUTHORITIES),
        "packed_hot_state_inventory": [
            {
                "field": name,
                "authority": authority,
                "future_decision_input": future,
                "reason": reason,
            }
            for name, (authority, reason, future) in sorted(PACKED_AUTHORITIES.items())
        ],
        "static_topology_schema_fields": sorted(TOPOLOGY_FIELDS),
        "explicit_sparse_boundaries": SPARSE_BOUNDARIES,
        "checks": {
            "every_packed_field_declared": not missing,
            "no_undeclared_inventory_entries": not extra,
            "all_authorities_valid": not invalid,
            "no_future_decision_field_without_authority": not missing and not invalid,
            "missing_packed_fields": missing,
            "extra_inventory_entries": extra,
            "invalid_authorities": invalid,
        },
        "passed": not missing and not extra and not invalid,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_packed_state_authority_v1.json",
    )
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
