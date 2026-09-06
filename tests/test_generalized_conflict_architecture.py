from copy import deepcopy
import random

import pytest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.access import build_access_restriction
from pineland_sim.action_model import available_battle_pairs
from pineland_sim.civilian import apply_direct_civilian_harm
from pineland_sim.combat import resolve_engagement
from pineland_sim.entities import ControlVector, RelationStatus
from pineland_sim.events import ScheduledEvent
from pineland_sim.logistics import create_movement_order, shortest_locality_path
from pineland_sim.organizational_state import local_organizational_embeddedness
from pineland_sim.organization_ecology import (
    _transfer_defecting_membership,
)
from pineland_sim.processes import ProcessEngine, _continuous_capacity_update
from pineland_sim.physical import (
    aggregate_insurgent_control,
    recompute_contested_controls,
)
from pineland_sim.relations import set_relation


def _world(seed: int = 8801):
    return generate_pineland(
        SimulationConfig(
            agent_count=160,
            locality_count=17,
            horizon_days=3,
            burn_in_days=0.0,
            seed=seed,
        )
    )


def _add_rival(world, *, locality_id: str | None = None):
    source = world.organizations["insurgent"]
    rival = deepcopy(source)
    rival.organization_id = "rival"
    rival.name = "Synthetic Rival"
    rival.member_ids = set()
    rival.resources = 0.0
    world.organizations[rival.organization_id] = rival
    for locality in world.localities.values():
        locality.control.setdefault(rival.organization_id, ControlVector())

    source_formation = world.formations["PRF-01"]
    rival_formation = deepcopy(source_formation)
    rival_formation.formation_id = "RIVAL-01"
    rival_formation.organization_id = rival.organization_id
    rival_formation.locality_id = locality_id or source_formation.locality_id
    rival_formation.current_microzone_id = source_formation.current_microzone_id
    world.formations[rival_formation.formation_id] = rival_formation
    return rival, rival_formation


def test_hostile_splinter_can_fight_through_normal_combat_engine():
    world = _world()
    source_formation = world.formations["PRF-01"]
    rival, rival_formation = _add_rival(
        world, locality_id=source_formation.locality_id
    )
    set_relation(
        world,
        "insurgent",
        rival.organization_id,
        RelationStatus.HOSTILE,
        0.0,
        rivalry_memory=1.0,
        hostility_memory=1.0,
    )
    pairs = available_battle_pairs(
        world, "insurgent", source_formation.locality_id
    )
    assert any(
        first.formation_id == source_formation.formation_id
        and second.formation_id == rival_formation.formation_id
        for first, second in pairs
    )
    engagement, _ = resolve_engagement(
        world,
        "E-rival",
        source_formation,
        rival_formation,
        ("insurgent", rival.organization_id),
        0.0,
        random.Random(8),
        initiator_organization_id="insurgent",
        contact_cause="synthetic_factional_conflict",
    )
    assert engagement.personnel_losses[source_formation.formation_id] >= 0
    assert engagement.personnel_losses[rival_formation.formation_id] >= 0


def test_concrete_insurgent_id_is_not_overwritten_by_side_aggregate():
    world = _world(seed=8810)
    original = world.formations["PRF-01"]
    rival, rival_formation = _add_rival(
        world, locality_id=original.locality_id
    )
    rival_formation.personnel = original.personnel * 2.0
    rival_formation.supply_stock = min(
        rival_formation.supply_capacity,
        max(rival_formation.supply_stock, original.supply_stock),
    )
    locality_id = original.locality_id

    adjusted = recompute_contested_controls(world, locality_id, 0.0)

    assert "insurgent" in adjusted
    assert rival.organization_id in adjusted
    assert adjusted["insurgent"] == pytest.approx(
        world.localities[locality_id].control["insurgent"].physical
    )
    aggregate = aggregate_insurgent_control(world, locality_id)
    assert aggregate.physical >= adjusted["insurgent"] - 1e-12
    assert aggregate.physical >= adjusted[rival.organization_id] - 1e-12


def test_defection_conserves_manpower_without_transferring_source_equipment():
    world = _world(seed=8802)
    source = world.organizations["insurgent"]
    rival, _ = _add_rival(world)
    person = next(
        person
        for person in world.persons.values()
        if person.residence_locality_id == world.formations["PRF-01"].locality_id
    )
    person.organization_id = source.organization_id
    person.armed_fraction = 0.5
    source.member_ids.add(person.person_id)
    represented = person.weight * person.armed_fraction
    fighter_delta = (
        represented
        * world.config.organization_ecology.fighter_conversion_fraction
    )
    key = (source.organization_id, person.residence_locality_id)
    destination_key = (rival.organization_id, person.residence_locality_id)
    supply_per_fighter = (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    world.organization_manpower_pools[key] = fighter_delta
    world.organization_manpower_supply_reserves[key] = (
        fighter_delta * supply_per_fighter
    )
    source_reserve_before = world.organization_manpower_supply_reserves[key]
    total_pool_before = sum(world.organization_manpower_pools.values())

    represented_moved, fighters_moved = _transfer_defecting_membership(
        world, person, source, rival
    )

    assert represented_moved == pytest.approx(represented)
    assert fighters_moved == pytest.approx(fighter_delta)
    assert person.organization_id == rival.organization_id
    assert person.person_id not in source.member_ids
    assert person.person_id in rival.member_ids
    assert world.organization_manpower_pools.get(key, 0.0) == pytest.approx(0.0)
    assert world.organization_manpower_pools[destination_key] == pytest.approx(
        fighter_delta
    )
    assert sum(world.organization_manpower_pools.values()) == pytest.approx(
        total_pool_before
    )
    assert world.organization_manpower_supply_reserves[key] == pytest.approx(
        source_reserve_before
    )
    assert world.organization_manpower_supply_reserves.get(
        destination_key, 0.0
    ) == pytest.approx(0.0)


def test_nonstate_governance_accumulates_then_decays_without_local_capacity():
    world = _world(seed=8803)
    organization = world.organizations["insurgent"]
    formation = world.formations["PRF-01"]
    locality = world.localities[formation.locality_id]
    organization.institutional_quality = 1.0
    organization.capital["organizational"] = 1.0
    organization.phenotype["governance_investment"] = 1.0
    before = locality.control["insurgent"].administrative
    event = ScheduledEvent(
        30.0, 70, 0, "governance",
        {"interval": 30.0, "elapsed_days": 30.0},
    )
    engine = ProcessEngine(world, rng=random.Random(3))
    world.time = 30.0
    engine.on_governance("E-gov-1", event)
    accumulated = locality.control["insurgent"].administrative
    assert accumulated > before

    for item in world.formations.values():
        if item.organization_id == organization.organization_id:
            item.personnel = 0.0
    organization.member_ids.clear()
    world.organization_manpower_pools = {
        key: value
        for key, value in world.organization_manpower_pools.items()
        if key[0] != organization.organization_id
    }
    world.time = 60.0
    engine.on_governance("E-gov-2", event)
    assert locality.control["insurgent"].administrative < accumulated


def test_nonstate_governance_stock_composes_exactly_in_calendar_time():
    once = _continuous_capacity_update(
        0.17, 0.63, 0.022, 0.035, 30.0
    )
    partitioned = 0.17
    for _ in range(3):
        partitioned = _continuous_capacity_update(
            partitioned, 0.63, 0.022, 0.035, 10.0
        )
    assert partitioned == pytest.approx(once, abs=1e-12)


def test_existing_membership_and_governance_provide_gradual_clandestine_hysteresis():
    """Existing stocks persist after fielding is removed, then collapse together."""
    world = _world(seed=8805)
    organization = world.organizations["insurgent"]
    formation = world.formations["PRF-01"]
    locality_id = formation.locality_id
    local_members = [
        person for person in world.persons.values()
        if (
            person.person_id in organization.member_ids
            and person.residence_locality_id == locality_id
        )
    ]
    assert local_members
    # Keep a small represented facilitator cohort so the union-of-channels
    # metric does not saturate at one before the fielded formation is removed.
    for person in local_members:
        person.armed_fraction = 0.005

    organization.institutional_quality = 1.0
    organization.capital["organizational"] = 1.0
    organization.phenotype["governance_investment"] = 1.0
    engine = ProcessEngine(world, rng=random.Random(5))

    world.time = 30.0
    engine.on_governance(
        "E-hysteresis-1",
        ScheduledEvent(30.0, 70, 0, "governance", {"interval": 30.0, "elapsed_days": 30.0}),
    )
    with_formation = local_organizational_embeddedness(
        world, organization.organization_id, locality_id
    )

    # Remove/mobile the fielded formation while retaining local members and
    # the governance/control stock already established by the organization.
    formation.personnel = 0.0
    formation.moving = True
    organization.phenotype["governance_investment"] = 0.0
    world.time = 60.0
    engine.on_governance(
        "E-hysteresis-2",
        ScheduledEvent(60.0, 70, 1, "governance", {"interval": 30.0, "elapsed_days": 30.0}),
    )
    without_formation = local_organizational_embeddedness(
        world, organization.organization_id, locality_id
    )
    world.time = 90.0
    engine.on_governance(
        "E-hysteresis-3",
        ScheduledEvent(90.0, 70, 2, "governance", {"interval": 30.0, "elapsed_days": 30.0}),
    )
    decayed = local_organizational_embeddedness(
        world, organization.organization_id, locality_id
    )
    assert with_formation > 0.0
    assert without_formation > decayed > 0.0

    # Removing both people and institutional/control stocks collapses the
    # existing representation; no hidden recent-event memory is involved.
    organization.member_ids.clear()
    for key in list(world.organization_manpower_pools):
        if key[0] == organization.organization_id:
            world.organization_manpower_pools.pop(key)
    world.localities[locality_id].control[organization.organization_id] = ControlVector()
    assert local_organizational_embeddedness(
        world, organization.organization_id, locality_id
    ) == pytest.approx(0.0)


def test_hostile_access_restriction_increases_movement_time_and_supply_cost():
    world = _world(seed=8804)
    formation = world.formations["FDF-01"]
    origin = formation.locality_id
    destination = next(iter(world.adjacency[origin]))
    route, _, _ = shortest_locality_path(
        world, origin, destination, formation.mobility
    )
    before = create_movement_order(
        world, formation.formation_id, destination, 0.0, random.Random(1)
    )
    world.movement_orders.clear()
    world.active_movement_order_ids.clear()
    for first, second in zip(route, route[1:]):
        build_access_restriction(
            world, "insurgent", first, second, 1.0, 0.0
        )
    after = create_movement_order(
        world, formation.formation_id, destination, 0.0, random.Random(1)
    )
    assert after.travel_time_hours > before.travel_time_hours
    assert after.supply_cost > before.supply_cost


def test_direct_civilian_harm_closes_population_ledger_and_preserves_armed_mass():
    world = _world(seed=8805)
    locality_id = next(
        locality_id
        for locality_id in world.localities
        if any(
            person.residence_locality_id == locality_id
            for person in world.persons.values()
        )
    )
    person = next(
        person
        for person in world.persons.values()
        if person.residence_locality_id == locality_id
    )
    person.armed_fraction = 0.25
    old_armed_mass = person.weight * person.armed_fraction
    population_before = world.weighted_population()

    harm = apply_direct_civilian_harm(
        world,
        "E-civilian-harm",
        locality_id,
        100.0,
        cause="synthetic_test",
        responsible_organization_id="insurgent",
    )

    assert harm.deaths > 0
    assert world.weighted_population() == pytest.approx(
        population_before - harm.deaths
    )
    assert person.weight * person.armed_fraction == pytest.approx(
        old_armed_mass
    )
    diagnostics = world.global_accounting_diagnostics()
    assert diagnostics["population_residual"] == pytest.approx(0.0, abs=1e-6)
