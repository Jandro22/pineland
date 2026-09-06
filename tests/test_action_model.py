from __future__ import annotations

import copy
import math
import random
from unittest.mock import patch

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.action_model import (
    action_attempt_probability,
    action_choice_weights,
    execution_probability,
    local_action_support,
    local_fighter_equivalents,
    national_fighter_equivalents,
)
from pineland_sim.entities import OrganizationKind
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


def _world(seed: int = 41, *, output_mode: str = "forensic"):
    return generate_pineland(SimulationConfig(
        seed=seed,
        agent_count=240,
        locality_count=24,
        horizon_days=2.0,
        output_mode=output_mode,
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


def test_execution_uses_local_supply_without_double_charging_organization_cash():
    world = _world()
    organization, formation = _insurgent(world)
    locality_id = formation.locality_id
    funded = execution_probability(world, organization.organization_id, locality_id, .2, .8)
    organization.resources = 0.0
    organization.capital["material"] = 0.0
    converted = execution_probability(world, organization.organization_id, locality_id, .2, .8)
    assert converted == funded
    assert converted > 0.0


def _human_target_locality(world) -> str:
    post = next(
        item for item in world.security_posts.values()
        if item.formation_id is None and item.personnel > 0
    )
    return post.locality_id


def _action_event(organization_id: str, locality_id: str, interval_days: float = 1.0):
    return ScheduledEvent(
        1.0, 18, 0, "organized_action",
        {
            "organization_id": organization_id,
            "locality_id": locality_id,
            "interval_days": interval_days,
        },
    )


def _fund_pool(world, organization_id: str, locality_id: str, quantity: float) -> None:
    """Create explicitly equipped unfielded capacity for action-model tests."""
    key = (organization_id, locality_id)
    supply_per_fighter = (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    reserve = quantity * supply_per_fighter
    organization = world.organizations[organization_id]
    assert organization.resources >= reserve
    organization.resources -= reserve
    world.cumulative_resource_to_supply += reserve
    world.organization_manpower_pools[key] = (
        world.organization_manpower_pools.get(key, 0.0) + quantity
    )
    world.organization_manpower_supply_reserves[key] = (
        world.organization_manpower_supply_reserves.get(key, 0.0) + reserve
    )


def test_action_attempt_probability_composes_in_calendar_time():
    world = _world()
    organization, formation = _insurgent(world)
    p1 = action_attempt_probability(
        world, organization.organization_id, formation.locality_id, 1.0
    )
    p2 = action_attempt_probability(
        world, organization.organization_id, formation.locality_id, 2.0
    )
    assert math.isclose(p2, 1.0 - (1.0 - p1) ** 2, rel_tol=0, abs_tol=1e-12)


def test_action_attempt_probability_preserves_multiple_capacity_units():
    world = _world(seed=405)
    organization, formation = _insurgent(world)
    locality_id = formation.locality_id
    formation.personnel = 75.0
    one_unit = action_attempt_probability(
        world, organization.organization_id, locality_id, 1.0
    )
    formation.personnel = 750.0
    ten_units = action_attempt_probability(
        world, organization.organization_id, locality_id, 1.0
    )
    assert ten_units > one_unit * 3


def test_hidden_target_truth_cannot_change_fixed_belief_planning():
    base = _world(seed=42)
    organization, formation = _insurgent(base)
    locality_id = formation.locality_id
    altered = copy.deepcopy(base)
    before = action_choice_weights(base, organization.organization_id, locality_id)
    altered.localities[locality_id].control["government"].physical = 0.0
    for item in altered.formations.values():
        if altered.organizations[item.organization_id].kind in {
            OrganizationKind.MILITARY,
            OrganizationKind.POLICE,
            OrganizationKind.FOREIGN,
        }:
            item.personnel *= 25.0
    for post in altered.security_posts.values():
        if post.locality_id == locality_id and post.formation_id is None:
            post.personnel = 0.0
    for institution in altered.political_institutions.values():
        if institution.locality_id == locality_id:
            institution.capacity = 0.0
            institution.reach = 0.0
    after = action_choice_weights(altered, organization.organization_id, locality_id)
    assert before == after


def test_formation_to_pool_transfer_preserves_capacity_and_nonbattle_choice():
    world = _world(seed=43)
    organization, formation = _insurgent(world)
    locality_id = formation.locality_id
    before_total = national_fighter_equivalents(world, organization.organization_id)
    before_weights = action_choice_weights(world, organization.organization_id, locality_id)
    before_attempt = action_attempt_probability(
        world, organization.organization_id, locality_id, 1.0
    )
    moved = formation.personnel
    reserve = moved * (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    assert formation.supply_stock >= reserve
    world.organization_manpower_pools[(organization.organization_id, locality_id)] = (
        world.organization_manpower_pools.get(
            (organization.organization_id, locality_id), 0.0
        ) + moved
    )
    world.organization_manpower_supply_reserves[(organization.organization_id, locality_id)] = reserve
    formation.supply_stock -= reserve
    formation.personnel = 0.0
    formation.operational_status = "ineffective"
    after_weights = action_choice_weights(world, organization.organization_id, locality_id)
    after_attempt = action_attempt_probability(
        world, organization.organization_id, locality_id, 1.0
    )
    assert national_fighter_equivalents(world, organization.organization_id) == before_total
    assert math.isclose(after_attempt, before_attempt, rel_tol=0, abs_tol=1e-12)
    assert after_weights["nonfielded_human_target"] == before_weights["nonfielded_human_target"]
    assert after_weights["asset_violence"] == before_weights["asset_violence"]
    assert after_weights["coercion"] == before_weights["coercion"]
    assert after_weights["armed_confrontation"] == 0.0


def test_relocation_moves_local_capacity_without_reproduction():
    world = _world(seed=44)
    organization, _ = _insurgent(world)
    origin = next(iter(world.localities))
    destination = next(item for item in world.localities if item != origin)
    _fund_pool(world, organization.organization_id, origin, 50.0)
    before = national_fighter_equivalents(world, organization.organization_id)
    origin_before = sum(local_fighter_equivalents(
        world, organization.organization_id, origin
    ))
    world.organization_manpower_pools[(organization.organization_id, origin)] = 0.0
    reserve = world.organization_manpower_supply_reserves.pop(
        (organization.organization_id, origin)
    )
    world.organization_manpower_pools[(organization.organization_id, destination)] = (
        world.organization_manpower_pools.get(
            (organization.organization_id, destination), 0.0
        ) + 50.0
    )
    world.organization_manpower_supply_reserves[(organization.organization_id, destination)] = reserve
    assert national_fighter_equivalents(world, organization.organization_id) == before
    assert sum(local_fighter_equivalents(
        world, organization.organization_id, origin
    )) == origin_before - 50.0
    assert sum(local_fighter_equivalents(
        world, organization.organization_id, destination
    )) >= 50.0


def test_false_target_belief_changes_execution_not_planning():
    world = _world(seed=45)
    organization, _ = _insurgent(world)
    locality_id = _human_target_locality(world)
    _fund_pool(world, organization.organization_id, locality_id, 100.0)
    missing = copy.deepcopy(world)
    for post in missing.security_posts.values():
        if post.locality_id == locality_id and post.formation_id is None:
            post.personnel = 0.0
    assert action_choice_weights(
        world, organization.organization_id, locality_id
    ) == action_choice_weights(
        missing, organization.organization_id, locality_id
    )
    forced_choice = (
        "nonfielded_human_target",
        action_choice_weights(world, organization.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
        patch("pineland_sim.processes.execution_probability", return_value=1.0),
    ):
        present_result = ProcessEngine(world, rng=random.Random(1)).on_organized_action(
            "EA", _action_event(organization.organization_id, locality_id)
        )
        missing_result = ProcessEngine(missing, rng=random.Random(1)).on_organized_action(
            "EB", _action_event(organization.organization_id, locality_id)
        )
    assert present_result["latent_event"] == 1.0
    assert present_result["state_based_violence_event"] == 1.0
    assert missing_result["latent_event"] == 0.0
    assert missing_result["failure_reason"] == "believed_human_target_absent"


def test_asset_violence_does_not_count_as_state_based_human_violence():
    world = _world(seed=46)
    organization, _ = _insurgent(world)
    locality_id = next(iter(world.localities))
    _fund_pool(world, organization.organization_id, locality_id, 100.0)
    forced_choice = (
        "asset_violence",
        action_choice_weights(world, organization.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
        patch("pineland_sim.processes.execution_probability", return_value=1.0),
    ):
        ProcessEngine(world, rng=random.Random(2)).execute(
            _action_event(organization.organization_id, locality_id)
        )
    entry = world.event_log[-1]
    record = world.synthetic_records[-1]
    assert entry.event_type == "organized_action"
    assert entry.true_state_delta["latent_event"] == 1.0
    assert entry.true_state_delta["state_based_violence_event"] == 0.0
    assert record.event_type == "asset_violence"
    assert len(world.state_based_event_times) == 0


def test_nonfielded_human_attack_updates_manpower_ledger_as_destruction():
    world = _world(seed=47)
    organization, _ = _insurgent(world)
    locality_id = _human_target_locality(world)
    _fund_pool(world, organization.organization_id, locality_id, 100.0)
    world.initialize_stock_ledger()
    before = world.tracked_stock_totals()["fixed_security_personnel"]
    forced_choice = (
        "nonfielded_human_target",
        action_choice_weights(world, organization.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
        patch("pineland_sim.processes.execution_probability", return_value=1.0),
    ):
        ProcessEngine(world, rng=random.Random(3)).execute(
            _action_event(organization.organization_id, locality_id)
        )
    after = world.tracked_stock_totals()["fixed_security_personnel"]
    assert after < before
    transaction = next(
        item for item in world.stock_transactions
        if item.stock_name == "fixed_security_personnel"
    )
    assert transaction.flow_kind == "destruction"
    assert transaction.event_type == "organized_action"
    assert len(world.state_based_event_times) == 1


def test_default_scheduler_uses_multichannel_actions_and_legacy_is_replayable():
    world = _world(seed=48, output_mode="ensemble")
    result = Simulation(world).run(until=1.0)
    assert result.world.event_counts.get("organized_action", 0) > 0
    assert result.world.event_counts.get("contact", 0) == 0
    legacy = _world(seed=48, output_mode="ensemble")
    legacy.config.combat.organized_action_architecture = "legacy_contact_only"
    Simulation(legacy).run(until=1.0)
    assert legacy.event_counts.get("organized_action", 0) == 0


def test_pre_v013_serialized_config_replays_legacy_contact_architecture():
    payload = SimulationConfig(seed=4801, agent_count=100, locality_count=17).to_dict()
    del payload["combat"]["organized_action_architecture"]
    restored = SimulationConfig.from_dict(payload)
    assert restored.combat.organized_action_architecture == "legacy_contact_only"


def test_ceasefire_suppresses_violent_choice_without_erasing_capacity():
    world = _world(seed=49)
    organization, formation = _insurgent(world)
    locality_id = formation.locality_id
    before = action_choice_weights(world, organization.organization_id, locality_id)
    capacity_before = sum(local_fighter_equivalents(
        world, organization.organization_id, locality_id
    ))
    world.ceasefires[organization.organization_id] = "active"
    after = action_choice_weights(world, organization.organization_id, locality_id)
    capacity_after = sum(local_fighter_equivalents(
        world, organization.organization_id, locality_id
    ))
    assert capacity_after == capacity_before
    assert after["armed_confrontation"] <= before["armed_confrontation"]
    assert after["nonfielded_human_target"] < before["nonfielded_human_target"]
    assert after["asset_violence"] < before["asset_violence"]
    assert after["coercion"] == before["coercion"]


def test_local_action_support_distinguishes_battle_from_other_targets():
    world = _world(seed=50)
    organization, formation = _insurgent(world)
    locality_id = _human_target_locality(world)
    _fund_pool(world, organization.organization_id, locality_id, 50.0)
    formation.personnel = 0.0
    formation.operational_status = "ineffective"
    support = local_action_support(world, organization.organization_id, locality_id)
    assert not support.armed_confrontation
    assert support.nonfielded_human_target
    assert support.government_asset_target
    assert support.civilian_coercion


def test_distant_supply_cannot_materialize_local_nonbattle_attack():
    world = _world(seed=51)
    organization, formation = _insurgent(world)
    locality_id = next(
        locality for locality in world.localities
        if locality != formation.locality_id
        and any(
            institution.locality_id == locality
            for institution in world.political_institutions.values()
        )
    )
    # Keep armed personnel at the target locality but strip its local
    # consumable stock.  Distant national stock must not teleport into the
    # execution gate.
    formation.locality_id = locality_id
    formation.current_microzone_id = None
    formation.personnel = max(100.0, formation.personnel)
    formation.supply_stock = 0.0
    # Ensure every organization-owned material stock is physically elsewhere.
    for source in world.supply_sources.values():
        if source.organization_id == organization.organization_id:
            assert source.locality_id != locality_id or setattr(
                source, "locality_id", formation.locality_id
            ) is None
    forced_choice = (
        "asset_violence",
        action_choice_weights(world, organization.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
    ):
        result = ProcessEngine(world, rng=random.Random(4)).on_organized_action(
            "EC", _action_event(organization.organization_id, locality_id)
        )
    assert result["latent_event"] == 0.0
    assert result["execution_probability"] == 0.0
    assert result["supply_consumed"] == 0.0
    assert result["unmet_supply"] > 0.0


def test_unequipped_manpower_pool_does_not_create_action_capacity():
    world = _world(seed=511)
    organization, _ = _insurgent(world)
    occupied = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
    }
    locality_id = next(locality for locality in world.localities if locality not in occupied)
    key = (organization.organization_id, locality_id)
    world.organization_manpower_pools[key] = 100.0
    assert key not in world.organization_manpower_supply_reserves
    unfielded, fielded = local_fighter_equivalents(
        world, organization.organization_id, locality_id
    )
    assert unfielded == 0.0
    assert fielded == 0.0
    assert action_attempt_probability(
        world, organization.organization_id, locality_id, 1.0
    ) == 0.0


def test_selected_nonbattle_action_consumes_local_material_budget_once():
    world = _world(seed=52)
    organization, formation = _insurgent(world)
    locality_id = next(iter(world.localities))
    _fund_pool(world, organization.organization_id, locality_id, 100.0)
    source = next(
        item for item in world.supply_sources.values()
        if item.organization_id == organization.organization_id
    )
    source.locality_id = locality_id
    source.stock = max(source.stock, 1000.0)
    organization.local_knowledge = 1.0
    organization.capital["material"] = 1.0
    world.initialize_stock_ledger()
    before_supply = world.tracked_stock_totals()["military_supply"]
    forced_choice = (
        "asset_violence",
        action_choice_weights(world, organization.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
    ):
        ProcessEngine(world, rng=random.Random(5)).execute(
            _action_event(organization.organization_id, locality_id)
        )
    after_supply = world.tracked_stock_totals()["military_supply"]
    entry = world.event_log[-1]
    consumed = entry.true_state_delta["supply_consumed"]
    assert consumed > 0.0
    assert math.isclose(before_supply - after_supply, consumed, rel_tol=0, abs_tol=1e-9)
    transactions = [
        item for item in world.stock_transactions
        if item.event_type == "organized_action" and item.stock_name == "military_supply"
    ]
    assert len(transactions) == 1
    assert math.isclose(-transactions[0].delta, consumed, rel_tol=0, abs_tol=1e-9)


def test_representative_split_does_not_change_action_choice_when_state_is_fixed():
    world = _world(seed=53)
    organization, formation = _insurgent(world)
    locality_id = formation.locality_id
    before = action_choice_weights(world, organization.organization_id, locality_id)
    # Split one representative into two bookkeeping nodes while preserving its
    # represented mass.  Action choice does not read raw representative counts.
    person = next(iter(world.persons.values()))
    twin = copy.deepcopy(person)
    twin.person_id = person.person_id + "-SPLIT"
    person.weight *= 0.5
    twin.weight = person.weight
    world.persons[twin.person_id] = twin
    if person.organization_id in world.organizations:
        world.organizations[person.organization_id].member_ids.add(twin.person_id)
    after = action_choice_weights(world, organization.organization_id, locality_id)
    assert after == before


def test_government_side_can_initiate_against_unfielded_insurgent_manpower():
    world = _world(seed=54)
    insurgent, _ = _insurgent(world)
    actor_formation = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind in {
            OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN
        }
    )
    actor = world.organizations[actor_formation.organization_id]
    locality_id = actor_formation.locality_id
    world.organization_manpower_pools[(insurgent.organization_id, locality_id)] = 80.0
    actor_formation.supply_stock = max(actor_formation.supply_stock, 500.0)
    before = world.organization_manpower_pools[(insurgent.organization_id, locality_id)]
    forced_choice = (
        "nonfielded_human_target",
        action_choice_weights(world, actor.organization_id, locality_id),
    )
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
        patch("pineland_sim.processes.execution_probability", return_value=1.0),
    ):
        result = ProcessEngine(world, rng=random.Random(6)).on_organized_action(
            "EG", _action_event(actor.organization_id, locality_id)
        )
    after = world.organization_manpower_pools.get((insurgent.organization_id, locality_id), 0.0)
    assert result["latent_event"] == 1.0
    assert result["state_based_violence_event"] == 1.0
    assert result["target_type"] == "unfielded_insurgent_manpower"
    assert after < before


def test_same_zero_violence_history_different_hidden_capacity_diverges_after_common_shock():
    capacity_world = _world(seed=55)
    insurgent, formation = _insurgent(capacity_world)
    locality_id = _human_target_locality(capacity_world)
    _fund_pool(capacity_world, insurgent.organization_id, locality_id, 100.0)
    absent_world = copy.deepcopy(capacity_world)
    absent_world.organization_manpower_pools.pop((insurgent.organization_id, locality_id), None)
    absent_world.organization_manpower_supply_reserves.pop(
        (insurgent.organization_id, locality_id), None
    )
    for item in absent_world.formations.values():
        if item.organization_id == insurgent.organization_id and item.locality_id == locality_id:
            item.personnel = 0.0
            item.operational_status = "ineffective"

    # Both worlds have the same empty observed violence history before the
    # common exogenous target-access shock; only hidden organizational state differs.
    assert capacity_world.state_based_event_times == absent_world.state_based_event_times == []
    assert action_attempt_probability(
        capacity_world, insurgent.organization_id, locality_id, 1.0
    ) > 0.0
    assert action_attempt_probability(
        absent_world, insurgent.organization_id, locality_id, 1.0
    ) == 0.0

