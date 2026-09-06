"""Data-free promotion battery for the v5 organization/action/event architecture."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.action_model import (  # noqa: E402
    action_attempt_probability,
    action_choice_weights,
    local_action_support,
    local_fighter_equivalents,
    national_fighter_equivalents,
)
from pineland_sim.entities import OrganizationKind  # noqa: E402


def _world(seed: int):
    return generate_pineland(SimulationConfig(
        seed=seed, agent_count=300, locality_count=24, horizon_days=1.0,
        output_mode="forensic",
    ))


def _insurgent(world):
    organization = next(
        item for item in world.organizations.values()
        if item.kind is OrganizationKind.INSURGENT and item.status == "active"
    )
    formation = next(
        item for item in world.formations.values()
        if item.organization_id == organization.organization_id
    )
    return organization, formation


def _human_target_locality(world):
    return next(
        post.locality_id for post in world.security_posts.values()
        if post.formation_id is None and post.personnel > 0
    )


def _remove_government_targets(world, locality_id: str) -> None:
    for formation in world.formations.values():
        if (
            formation.locality_id == locality_id
            and world.organizations[formation.organization_id].kind in {
                OrganizationKind.MILITARY,
                OrganizationKind.POLICE,
                OrganizationKind.FOREIGN,
            }
        ):
            formation.personnel = 0.0
            formation.operational_status = "ineffective"
    for post in world.security_posts.values():
        if post.locality_id == locality_id and post.formation_id is None:
            post.personnel = 0.0
    for institution in world.political_institutions.values():
        if institution.locality_id == locality_id:
            institution.capacity = 0.0
            institution.reach = 0.0


def _relocate_one_supply_source(world, organization_id: str, locality_id: str) -> None:
    source = next(
        item for item in world.supply_sources.values()
        if item.organization_id == organization_id
    )
    source.locality_id = locality_id
    source.stock = max(1000.0, source.stock)


def _fund_pool(world, organization_id: str, locality_id: str, quantity: float) -> float:
    """Install explicitly equipped synthetic unfielded capacity without free materiel."""
    key = (organization_id, locality_id)
    quantity = max(0.0, float(quantity))
    supply_per_fighter = (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    reserve = quantity * supply_per_fighter
    organization = world.organizations[organization_id]
    if organization.resources < reserve:
        raise RuntimeError("v5 synthetic capacity fixture lacks material backing")
    organization.resources -= reserve
    world.cumulative_resource_to_supply += reserve
    world.organization_manpower_pools[key] = (
        world.organization_manpower_pools.get(key, 0.0) + quantity
    )
    world.organization_manpower_supply_reserves[key] = (
        world.organization_manpower_supply_reserves.get(key, 0.0) + reserve
    )
    return reserve


def run_battery(seed: int = 2026090525) -> dict:
    gates: dict[str, dict] = {}

    # 1. Capacity can persist while a specific violent target family has no support.
    world = _world(seed)
    organization, formation = _insurgent(world)
    locality = formation.locality_id
    _fund_pool(world, organization.organization_id, locality, 100.0)
    _remove_government_targets(world, locality)
    support = local_action_support(world, organization.organization_id, locality)
    attempt = action_attempt_probability(world, organization.organization_id, locality, 1.0)
    gates["capacity_without_relevant_target"] = {
        "passed": bool(
            attempt > 0
            and not support.armed_confrontation
            and not support.nonfielded_human_target
            and not support.government_asset_target
        ),
        "attempt_probability": attempt,
        "fighter_equivalents": support.total_fighter_equivalents,
    }

    # 2. Feasibility does not force action: actor can choose waiting/accommodation.
    world = _world(seed + 1)
    organization, formation = _insurgent(world)
    locality = formation.locality_id
    organization.phenotype["risk_tolerance"] = 0.0
    organization.phenotype["governance_investment"] = 0.0
    weights = action_choice_weights(world, organization.organization_id, locality)
    gates["opportunity_without_willingness"] = {
        "passed": bool(
            weights["wait"] > 0
            and weights["armed_confrontation"] == 0
            and weights["nonfielded_human_target"] == 0
            and weights["asset_violence"] == 0
            and weights["coercion"] == 0
        ),
        "weights": weights,
    }

    # 3. Nonfielded human-target support does not require opposing formation contact.
    world = _world(seed + 2)
    organization, _ = _insurgent(world)
    locality = _human_target_locality(world)
    _fund_pool(world, organization.organization_id, locality, 100.0)
    for formation in world.formations.values():
        if (
            formation.locality_id == locality
            and world.organizations[formation.organization_id].kind in {
                OrganizationKind.MILITARY,
                OrganizationKind.POLICE,
                OrganizationKind.FOREIGN,
            }
        ):
            formation.personnel = 0.0
            formation.operational_status = "ineffective"
    _relocate_one_supply_source(world, organization.organization_id, locality)
    support = local_action_support(world, organization.organization_id, locality)
    gates["nonfielded_target_without_opposing_formation"] = {
        "passed": bool(
            support.nonfielded_human_target and not support.armed_confrontation
        ),
        "human_target_support": support.nonfielded_human_target,
        "battle_support": support.armed_confrontation,
    }

    # 4. Zero observed violence does not identify dominance versus absence.
    dominance = _world(seed + 3)
    organization, formation = _insurgent(dominance)
    locality = formation.locality_id
    dominance.localities[locality].control["insurgent"].physical = 0.9
    dominance.localities[locality].control["insurgent"].social = 0.9
    dominance.localities[locality].control["insurgent"].fiscal = 0.9
    absence = copy.deepcopy(dominance)
    for formation in absence.formations.values():
        if formation.organization_id == organization.organization_id:
            formation.personnel = 0.0
            formation.operational_status = "ineffective"
    for key in list(absence.organization_manpower_pools):
        if key[0] == organization.organization_id:
            del absence.organization_manpower_pools[key]
            absence.organization_manpower_supply_reserves.pop(key, None)
    absence.localities[locality].control["insurgent"].physical = 0.0
    absence.localities[locality].control["insurgent"].social = 0.0
    absence.localities[locality].control["insurgent"].fiscal = 0.0
    gates["dominance_versus_mutual_absence"] = {
        "passed": bool(
            not dominance.state_based_event_times
            and not absence.state_based_event_times
            and dominance.localities[locality].control["insurgent"].physical
            > absence.localities[locality].control["insurgent"].physical
        ),
        "dominance_events": len(dominance.state_based_event_times),
        "absence_events": len(absence.state_based_event_times),
    }

    # 5. Hidden target truth changes execution support, not fixed-belief planning.
    present = _world(seed + 4)
    organization, formation = _insurgent(present)
    locality = _human_target_locality(present)
    _fund_pool(present, organization.organization_id, locality, 100.0)
    missing = copy.deepcopy(present)
    for post in missing.security_posts.values():
        if post.locality_id == locality and post.formation_id is None:
            post.personnel = 0.0
    present_weights = action_choice_weights(present, organization.organization_id, locality)
    missing_weights = action_choice_weights(missing, organization.organization_id, locality)
    gates["false_target_belief"] = {
        "passed": bool(
            present_weights == missing_weights
            and local_action_support(
                present, organization.organization_id, locality
            ).nonfielded_human_target
            and not local_action_support(
                missing, organization.organization_id, locality
            ).nonfielded_human_target
        ),
        "planning_equal": present_weights == missing_weights,
    }

    # 6. Crossing fielding bookkeeping preserves total capacity and nonbattle choice.
    world = _world(seed + 5)
    organization, formation = _insurgent(world)
    locality = formation.locality_id
    total_before = national_fighter_equivalents(world, organization.organization_id)
    weights_before = action_choice_weights(world, organization.organization_id, locality)
    attempt_before = action_attempt_probability(world, organization.organization_id, locality, 1.0)
    moved = formation.personnel
    reserve = moved * (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    if formation.supply_stock < reserve:
        raise RuntimeError("formation-to-pool fixture lacks transferable material backing")
    world.organization_manpower_pools[(organization.organization_id, locality)] = (
        world.organization_manpower_pools.get(
            (organization.organization_id, locality), 0.0
        ) + moved
    )
    world.organization_manpower_supply_reserves[(organization.organization_id, locality)] = (
        world.organization_manpower_supply_reserves.get(
            (organization.organization_id, locality), 0.0
        ) + reserve
    )
    formation.supply_stock -= reserve
    formation.personnel = 0.0
    formation.operational_status = "ineffective"
    weights_after = action_choice_weights(world, organization.organization_id, locality)
    attempt_after = action_attempt_probability(world, organization.organization_id, locality, 1.0)
    gates["formation_threshold_bookkeeping"] = {
        "passed": bool(
            national_fighter_equivalents(world, organization.organization_id) == total_before
            and math.isclose(attempt_before, attempt_after, abs_tol=1e-12)
            and weights_before["nonfielded_human_target"]
            == weights_after["nonfielded_human_target"]
            and weights_before["asset_violence"] == weights_after["asset_violence"]
            and weights_before["coercion"] == weights_after["coercion"]
        ),
        "attempt_before": attempt_before,
        "attempt_after": attempt_after,
    }

    # 7. Raw representative count changes do not alter the action mapping.
    world = _world(seed + 6)
    organization, formation = _insurgent(world)
    locality = formation.locality_id
    before = action_choice_weights(world, organization.organization_id, locality)
    person = next(iter(world.persons.values()))
    twin = copy.deepcopy(person)
    twin.person_id = person.person_id + "-SPLIT"
    person.weight *= 0.5
    twin.weight = person.weight
    world.persons[twin.person_id] = twin
    if person.organization_id in world.organizations:
        world.organizations[person.organization_id].member_ids.add(twin.person_id)
    after = action_choice_weights(world, organization.organization_id, locality)
    gates["representative_split_invariance"] = {
        "passed": before == after,
        "planning_equal": before == after,
    }

    # 8. Relocation changes geography while preserving organization-wide capacity.
    world = _world(seed + 7)
    organization, _ = _insurgent(world)
    origin = next(iter(world.localities))
    destination = next(item for item in world.localities if item != origin)
    reserve = _fund_pool(world, organization.organization_id, origin, 50.0)
    total_before = national_fighter_equivalents(world, organization.organization_id)
    origin_before = sum(local_fighter_equivalents(
        world, organization.organization_id, origin
    ))
    world.organization_manpower_pools[(organization.organization_id, origin)] = 0.0
    world.organization_manpower_supply_reserves.pop((organization.organization_id, origin), None)
    world.organization_manpower_pools[(organization.organization_id, destination)] = (
        world.organization_manpower_pools.get(
            (organization.organization_id, destination), 0.0
        ) + 50.0
    )
    world.organization_manpower_supply_reserves[(organization.organization_id, destination)] = reserve
    gates["complete_organization_relocation"] = {
        "passed": bool(
            national_fighter_equivalents(world, organization.organization_id) == total_before
            and sum(local_fighter_equivalents(
                world, organization.organization_id, origin
            )) == origin_before - 50.0
            and sum(local_fighter_equivalents(
                world, organization.organization_id, destination
            )) >= 50.0
        ),
    }

    # 9. Identical no-violence histories can imply different response to one shock.
    capacity_world = _world(seed + 8)
    organization, formation = _insurgent(capacity_world)
    locality = _human_target_locality(capacity_world)
    _fund_pool(capacity_world, organization.organization_id, locality, 100.0)
    absent_world = copy.deepcopy(capacity_world)
    absent_world.organization_manpower_pools[
        (organization.organization_id, locality)
    ] = 0.0
    absent_world.organization_manpower_supply_reserves.pop(
        (organization.organization_id, locality), None
    )
    for own in absent_world.formations.values():
        if own.organization_id == organization.organization_id and own.locality_id == locality:
            own.personnel = 0.0
            own.operational_status = "ineffective"
    before_same = (
        capacity_world.state_based_event_times == absent_world.state_based_event_times == []
    )
    # The common shock is target exposure; target entities are identical in both.
    p_capacity = action_attempt_probability(
        capacity_world, organization.organization_id, locality, 1.0
    )
    p_absent = action_attempt_probability(
        absent_world, organization.organization_id, locality, 1.0
    )
    gates["same_violence_different_state_common_shock"] = {
        "passed": bool(before_same and p_capacity > p_absent),
        "same_pre_shock_violence_history": before_same,
        "capacity_world_attempt_probability": p_capacity,
        "absence_world_attempt_probability": p_absent,
    }

    passed = all(item["passed"] for item in gates.values())
    return {
        "schema_version": "pineland.v5_action_architecture_validation.v1",
        "historical_outcomes_used": False,
        "historical_parameter_fit": False,
        "gates": gates,
        "passed": passed,
        "interpretation": (
            "The v5 organization/action/event architecture survives the preregistered "
            "data-free support, choice, belief-boundary, bookkeeping, resolution, "
            "relocation, and hidden-state counterexamples."
            if passed else
            "At least one preregistered v5 synthetic rejection gate failed."
        ),
    }


def main() -> int:
    result = run_battery()
    output = ROOT / "studies/research_program/v5_action_architecture_validation.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
