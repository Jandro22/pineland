"""Run the synthetic movement-to-local-reproduction factorial.

The runner is deliberately study-layer code. It creates a matched locality
intervention around one moved insurgent formation and never reads Nepal or
Afghanistan outcomes. The five binary factors are independently crossed:
local membership, persistent embedded infrastructure, target knowledge,
logistics, and government pressure.
"""
from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import ActorBelief, ControlVector, OrganizationKind  # noqa: E402
from pineland_sim.organization_ecology import _set_armed_membership  # noqa: E402
from pineland_sim.organizational_state import local_foothold_strength  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    audit_run_manifest,
    build_run_manifest,
    file_sha256,
    model_sha256,
    repository_state,
)

CONTRACT_PATH = ROOT / "studies" / "research_program" / "local_foothold_factorial_contract.json"
FACTOR_NAMES = (
    "local_membership",
    "embedded_infrastructure",
    "target_knowledge",
    "logistics",
    "government_pressure",
)
FACTOR_LEVELS = {
    "local_membership": ("absent", "present"),
    "embedded_infrastructure": ("absent", "present"),
    "target_knowledge": ("uninformed", "informed"),
    "logistics": ("constrained", "sustained"),
    "government_pressure": ("low", "high"),
}


def load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    design = contract.get("design", {})
    if contract.get("historical_outcomes_used") or contract.get("historical_parameter_fitting"):
        raise ValueError("local foothold factorial is synthetic-only")
    if contract.get("core_change_licensed"):
        raise ValueError("synthetic factorial cannot license a core change")
    expected_factors = {
        name: list(values) for name, values in FACTOR_LEVELS.items()
    }
    if design.get("factors") != expected_factors or design.get("cells") != 32:
        raise ValueError("local foothold factorial does not match its declared 32-cell design")
    if not design.get("matched_seed_assignment") or len(design.get("seeds", [])) != 8:
        raise ValueError("matched eight-seed assignment is required")


def _current_supply(world) -> float:
    return (
        sum(source.stock for source in world.supply_sources.values())
        + sum(formation.supply_stock for formation in world.formations.values())
        + sum(world.organization_manpower_supply_reserves.values())
        + world.demobilized_arms
        + world.in_transit_supply_total
    )


def _reset_supply_baseline(world) -> None:
    """Make declared direct treatment edits the synthetic initial condition."""
    world.initial_supply_stock = _current_supply(world)
    world.cumulative_supply_produced = 0.0
    world.cumulative_supply_consumed = 0.0
    world.cumulative_supply_lost = 0.0
    world.cumulative_resource_to_supply = 0.0
    world.initialize_stock_ledger()


def _clear_destination_membership(world, organization_id: str, locality_id: str) -> None:
    organization = world.organizations[organization_id]
    for person in list(world.persons_in_locality(locality_id)):
        if person.organization_id != organization_id:
            continue
        organization.member_ids.discard(person.person_id)
        _set_armed_membership(world, person, None, 0.0)


def _prepare_cell(world, factors: dict[str, str]) -> tuple[str, str, str]:
    organization_id = next(
        organization.organization_id
        for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT
        and organization.status == "active"
    )
    organization = world.organizations[organization_id]
    focal = next(
        formation for formation in sorted(
            world.formations.values(), key=lambda item: item.formation_id
        )
        if formation.organization_id == organization_id and formation.personnel > 0
    )
    source_locality_id = focal.locality_id
    destination_locality_id = sorted(world.adjacency[source_locality_id])[0]

    # Keep one focal unit in the matched fixture. A mobile unit is present in
    # every cell, but it has no embeddedness of its own; the treatment factors
    # supply the local base, knowledge, material, and pressure contrasts.
    for formation in world.formations.values():
        if (
            formation.organization_id == organization_id
            and formation.formation_id != focal.formation_id
        ):
            formation.personnel = 0.0
    if focal.locality_id != destination_locality_id:
        world.relocate_formation(focal, destination_locality_id)
    focal.moving = False
    focal.outside_pineland = False
    focal.operational_status = "effective"
    focal.availability = 1.0
    focal.readiness = 1.0
    focal.command = 1.0
    focal.cohesion = 1.0
    focal.quality = 1.0
    focal.information = 1.0
    focal.fatigue = 0.0
    focal.embeddedness = 0.0
    destination_zones = [
        zone for zone in world.microzones.values()
        if zone.locality_id == destination_locality_id
    ]
    focal.current_microzone_id = max(
        destination_zones, key=lambda zone: zone.population_share
    ).microzone_id

    _clear_destination_membership(world, organization_id, destination_locality_id)
    destination = world.localities[destination_locality_id]
    destination.control[organization_id] = ControlVector()
    foothold = world.local_footholds[(organization_id, destination_locality_id)]
    foothold.strength = 0.0
    foothold.raw_signal = 0.0
    foothold.renewal_count = 0
    foothold.first_activated_at = None
    foothold.last_activated_at = None
    foothold.viable_activation_count = 0

    if factors["local_membership"] == "present":
        candidate = next(
            person for person in world.persons_in_locality(destination_locality_id)
            if person.organization_id is None
        )
        fraction = min(0.20, 1_500.0 / max(1.0, candidate.weight))
        _set_armed_membership(world, candidate, organization, fraction)
        organization.member_ids.add(candidate.person_id)

    if factors["embedded_infrastructure"] == "present":
        foothold.strength = 0.75
        foothold.raw_signal = 0.75
        foothold.renewal_count = 1
        foothold.first_activated_at = 0.0
        foothold.last_activated_at = 0.0
        foothold.viable_activation_count = 1

    if factors["target_knowledge"] == "informed":
        destination_belief = ActorBelief(
            organization_id,
            destination_locality_id,
            ControlVector(formal=.9, physical=.9, administrative=.6),
            confidence=.95,
            updated_at=0.0,
            last_reliable_observation_at=0.0,
            evidence_count=1,
        )
        world.control_beliefs[
            (organization_id, "government", destination_locality_id)
        ] = destination_belief
    else:
        for key in list(world.control_beliefs):
            if key[0] == organization_id and key[2] == destination_locality_id:
                belief = world.control_beliefs[key]
                world.control_beliefs[key] = ActorBelief(
                    organization_id,
                    destination_locality_id,
                    ControlVector(),
                    confidence=0.0,
                    updated_at=0.0,
                    evidence_count=0,
                )

    pressure_high = factors["government_pressure"] == "high"
    destination.control["government"] = ControlVector(
        formal=.9 if pressure_high else .2,
        physical=.9 if pressure_high else .2,
        administrative=.9 if pressure_high else .2,
        legal=.9 if pressure_high else .2,
        fiscal=.8 if pressure_high else .2,
        social=.8 if pressure_high else .2,
        expected=.9 if pressure_high else .2,
    )
    destination_posts = [
        post for post in world.security_posts.values()
        if post.locality_id == destination_locality_id
    ]
    for post in destination_posts:
        post.personnel = 250.0 if pressure_high else 25.0
        post.available_fraction = 1.0

    if factors["logistics"] == "sustained":
        focal.supply_stock = focal.supply_capacity
    else:
        focal.supply_stock = 0.08 * focal.supply_capacity
    focal.sustainment = focal.supply_fraction()

    world.rebuild_runtime_entity_indexes()
    _reset_supply_baseline(world)
    return organization_id, source_locality_id, destination_locality_id


def _focal_metrics(world, organization_id: str, source_locality_id: str,
                   destination_locality_id: str, horizon_days: float) -> dict[str, Any]:
    events = [
        event for event in world.state_based_events
        if event.initiating_organization_id == organization_id
    ]
    destination_events = [
        event for event in events if event.locality_id == destination_locality_id
    ]
    weeks = {int(float(event.time) // 7) for event in destination_events}
    one_week_persistence = any((week + 1) in weeks for week in weeks)
    foothold = world.local_footholds[(organization_id, destination_locality_id)]
    neighbors = set(world.adjacency.get(destination_locality_id, {}))
    new_viable = sum(
        item.organization_id == organization_id
        and item.locality_id != source_locality_id
        and item.locality_id != destination_locality_id
        and item.viable_activation_count > 0
        for item in world.local_footholds.values()
    )
    neighbor_colonization = sum(
        item.organization_id == organization_id
        and item.locality_id in neighbors
        and item.viable_activation_count > 0
        for item in world.local_footholds.values()
    )
    focal = world.formations.get("PRF-01")
    if focal is None or focal.organization_id != organization_id:
        focal = next(
            formation for formation in world.formations.values()
            if formation.organization_id == organization_id
        )
    hazard_integral = sum(
        value for (week, locality_id, channel), value
        in world.activity_hazard_ledger.items()
        if locality_id == destination_locality_id
    )
    recorded = sum(
        1 for record in world.synthetic_records
        if record.recorded and record.locality_id == destination_locality_id
    )
    return {
        "probability_of_focal_locality_action_within_30_days": float(bool(destination_events)),
        "one_week_action_persistence": float(one_week_persistence),
        "foothold_survival_at_90_days": float(
            foothold.strength >= world.config.organization_ecology.local_foothold_viability_threshold
        ),
        "new_viable_footholds_from_focal_locality": new_viable,
        "neighbor_colonization_count": neighbor_colonization,
        "focal_action_hazard_integral": hazard_integral,
        "focal_fielded_personnel": focal.personnel,
        "focal_supply_fraction": focal.supply_fraction(),
        "focal_readiness": focal.effective_readiness(),
        "latent_state_based_events": len(events),
        "recorded_state_based_events": recorded,
        "supply_conservation_residual": world.supply_conservation_residual(),
        "destination_foothold_strength": local_foothold_strength(
            world, organization_id, destination_locality_id
        ),
        "horizon_days": horizon_days,
    }


def run_cell(*, contract: dict[str, Any], seed: int, factors: dict[str, str],
             horizon_days: float, agent_count: int, locality_count: int) -> dict[str, Any]:
    model_before = model_sha256(ROOT)
    config = SimulationConfig(
        seed=seed,
        horizon_days=horizon_days,
        agent_count=agent_count,
        locality_count=locality_count,
        output_mode="ensemble",
        random_stream_namespace="local-foothold-factorial",
    )
    config.logistics.reallocation_rate = 0.0
    world = generate_pineland(config)
    organization_id, source, destination = _prepare_cell(world, factors)
    simulation = Simulation(world)
    simulation.run(until=horizon_days, validate_invariants=True, checkpoint=False)
    model_after = model_sha256(ROOT)
    if model_before != model_after:
        raise RuntimeError("model source changed during factorial cell")
    metrics = _focal_metrics(world, organization_id, source, destination, horizon_days)
    manifest = build_run_manifest(
        config,
        seeds=[seed],
        execution_mode={"kind": "synthetic_local_foothold_factorial"},
        output_schema={"name": "local_foothold_factorial_cell", "version": "1.0.0"},
        repo_root=ROOT,
        extra={
            "experiment_id": contract["experiment_id"],
            "factors": factors,
            "source_locality_id": source,
            "destination_locality_id": destination,
            "model_sha256_start": model_before,
            "model_sha256_end": model_after,
            "historical_outcomes_used": False,
            "historical_parameter_fitting": False,
            "core_change_licensed": False,
        },
    )
    return {
        "seed": seed,
        "factors": factors,
        "source_locality_id": source,
        "destination_locality_id": destination,
        "metrics": metrics,
        "manifest": manifest,
        "manifest_audit": audit_run_manifest(manifest),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--days", type=float, default=None)
    parser.add_argument("--agents", type=int, default=None)
    parser.add_argument("--localities", type=int, default=None)
    args = parser.parse_args()
    contract = load_contract()
    validate_contract(contract)
    design = contract["design"]
    seeds = (
        [int(seed) for seed in design["seeds"]]
        if args.full
        else [args.seed if args.seed is not None else int(design["seeds"][0])]
    )
    horizon = float(design["horizon_days"] if args.full else (args.days or 30.0))
    agents = int(design["agent_count"] if args.full else (args.agents or 300))
    localities = int(design["locality_count"] if args.full else (args.localities or 34))
    levels = [FACTOR_LEVELS[name] for name in FACTOR_NAMES]
    before = repository_state(ROOT)
    cells = []
    for seed in seeds:
        for values in product(*levels):
            factors = dict(zip(FACTOR_NAMES, values))
            cells.append(run_cell(
                contract=contract,
                seed=seed,
                factors=factors,
                horizon_days=horizon,
                agent_count=agents,
                locality_count=localities,
            ))
    after = repository_state(ROOT)
    result = {
        "schema_version": "1.0.0",
        "experiment_id": contract["experiment_id"],
        "status": "full_synthetic_only" if args.full else "pilot_synthetic_only",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "repository_before": before,
        "repository_after": after,
        "cells": cells,
        "model_hash_stable": (
            before.get("commit_hash") == after.get("commit_hash")
            and before.get("tracked_diff_sha256") == after.get("tracked_diff_sha256")
            and all(
                cell["manifest"]["extra"]["model_sha256_start"]
                == cell["manifest"]["extra"]["model_sha256_end"]
                for cell in cells
            )
        ),
        "integrity_passed": all(cell["manifest_audit"]["valid"] for cell in cells),
        "scientific_acceptance_gate_passed": False,
        "interpretation": (
            "Synthetic matched-factor diagnostics only. Results cannot license "
            "historical fitting or a core change."
        ),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps({
        "schema_version": "1.0.0",
        "status": "synthetic_local_foothold_factorial_manifest",
        "artifact": output.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(output),
        "contract": CONTRACT_PATH.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT_PATH),
        "model_hashes": sorted({
            cell["manifest"]["extra"]["model_sha256_start"] for cell in cells
        }),
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "cells": len(cells),
        "integrity_passed": result["integrity_passed"],
        "scientific_acceptance_gate_passed": False,
        "output": output.as_posix(),
    }, indent=2))
    return 0 if result["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
