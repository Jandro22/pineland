import math

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.combat import resolve_engagement
from pineland_sim.entities import OrganizationKind
from pineland_sim.logistics import (
    advance_movement_orders,
    choose_withdrawal_order,
    reallocation_destination_score,
    shortest_locality_path,
)
from pineland_sim.organization_ecology import (
    _set_armed_membership,
    organization_survival_social_base,
    recruit_and_retain,
)
from pineland_sim.physical import record_presence_exposure, recompute_contested_controls


class ZeroRng:
    def random(self):
        return 0.0

    def normalvariate(self, mean, sigma):
        return mean

    def uniform(self, low, high):
        return low

    def expovariate(self, lambd):
        return 1.0 / lambd


def _world(seed=20260905):
    return generate_pineland(SimulationConfig(
        agent_count=500, locality_count=24, horizon_days=2, seed=seed,
    ))


def _insurgent(world):
    return next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT
        and organization.status == "active"
    )


def _insurgent_formation(world, organization):
    return next(
        formation for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
        and formation.personnel > 0
    )


def test_insurgent_reallocation_has_a_real_frontier_channel_not_only_stronghold_seeking():
    world = _world(901)
    organization = _insurgent(world)
    formation = _insurgent_formation(world, organization)
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ][:2]
    frontier_id, stronghold_id = candidates
    for locality_id in candidates:
        world.localities[locality_id].population = 10_000
        own = world.beliefs[(organization.organization_id, locality_id)]
        own.confidence = 1.0
        own_specific = world.control_beliefs[
            (organization.organization_id, "insurgent", locality_id)
        ]
        own_specific.confidence = 1.0
        government = world.control_beliefs[
            (organization.organization_id, "government", locality_id)
        ]
        government.confidence = 1.0
        government.control_estimate.physical = 0.1
    world.beliefs[(organization.organization_id, frontier_id)].control_estimate.physical = 0.1
    world.beliefs[(organization.organization_id, stronghold_id)].control_estimate.physical = 0.9
    world.control_beliefs[
        (organization.organization_id, "insurgent", frontier_id)
    ].control_estimate.physical = 0.1
    world.control_beliefs[
        (organization.organization_id, "insurgent", stronghold_id)
    ].control_estimate.physical = 0.9

    frontier = reallocation_destination_score(
        world, formation, frontier_id, travel_hours=4.0,
        maximum_population=10_000, footholds={},
    )
    stronghold = reallocation_destination_score(
        world, formation, stronghold_id, travel_hours=4.0,
        maximum_population=10_000, footholds={},
    )
    assert frontier["frontier"] > stronghold["frontier"]
    assert frontier["utility"] > stronghold["utility"]


def test_insurgent_reallocation_still_allows_embedded_stronghold_consolidation():
    world = _world(902)
    organization = _insurgent(world)
    formation = _insurgent_formation(world, organization)
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ][:2]
    stronghold_id, hostile_frontier_id = candidates
    for locality_id in candidates:
        world.localities[locality_id].population = 10_000
        own = world.beliefs[(organization.organization_id, locality_id)]
        own.confidence = 1.0
        own_specific = world.control_beliefs[
            (organization.organization_id, "insurgent", locality_id)
        ]
        own_specific.confidence = 1.0
        government = world.control_beliefs[
            (organization.organization_id, "government", locality_id)
        ]
        government.confidence = 1.0
    world.beliefs[(organization.organization_id, stronghold_id)].control_estimate.physical = 0.9
    world.control_beliefs[
        (organization.organization_id, "insurgent", stronghold_id)
    ].control_estimate.physical = 0.9
    world.control_beliefs[
        (organization.organization_id, "government", stronghold_id)
    ].control_estimate.physical = 0.1
    world.beliefs[
        (organization.organization_id, hostile_frontier_id)
    ].control_estimate.physical = 0.1
    world.control_beliefs[
        (organization.organization_id, "insurgent", hostile_frontier_id)
    ].control_estimate.physical = 0.1
    world.control_beliefs[
        (organization.organization_id, "government", hostile_frontier_id)
    ].control_estimate.physical = 0.9

    stronghold = reallocation_destination_score(
        world, formation, stronghold_id, travel_hours=4.0,
        maximum_population=10_000, footholds={stronghold_id: 1.0},
    )
    hostile = reallocation_destination_score(
        world, formation, hostile_frontier_id, travel_hours=4.0,
        maximum_population=10_000, footholds={},
    )
    assert stronghold["utility"] > hostile["utility"]


def test_patrol_presence_exposure_is_calendar_time_invariant():
    world = _world(903)
    organization = _insurgent(world)
    formation = _insurgent_formation(world, organization)
    zone = world.microzones[formation.current_microzone_id]
    tau = world.config.physical.presence_memory_days

    def run(step):
        zone.presence_memory["insurgent"] = 0.0
        zone.presence_updated_at["insurgent"] = 0.0
        elapsed = step
        while elapsed <= 2.0 + 1e-12:
            record_presence_exposure(
                world, zone.microzone_id, "insurgent", 0.6, step, elapsed
            )
            elapsed += step
        return zone.presence_memory["insurgent"]

    quarter_day = run(0.25)
    one_day = run(1.0)
    expected = 0.6 * (1.0 - math.exp(-2.0 / tau))
    assert math.isclose(quarter_day, expected, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(one_day, expected, rel_tol=0, abs_tol=1e-12)


def test_stationary_insurgent_occupancy_is_current_reach_not_patrol_memory():
    world = _world(904)
    organization = _insurgent(world)
    formation = _insurgent_formation(world, organization)
    zone = world.microzones[formation.current_microzone_id]
    zone.presence_memory["insurgent"] = 0.0
    zone.presence_updated_at["insurgent"] = 0.0
    recompute_contested_controls(world, formation.locality_id, 1.0)
    assert zone.physical_control["insurgent"] > 0.0
    assert zone.presence_memory["insurgent"] == 0.0


def test_survival_social_base_ignores_unrelated_national_population_mass():
    world = _world(905)
    organization = _insurgent(world)
    before = organization_survival_social_base(world, organization)
    unrelated = next(
        person for person in world.persons.values()
        if person.organization_id != organization.organization_id
    )
    unrelated.weight *= 1000.0
    after = organization_survival_social_base(world, organization)
    assert math.isclose(before, after, rel_tol=0, abs_tol=1e-15)


def test_disengaged_ineffective_formation_can_execute_withdrawal_to_refuge():
    world = _world(906)
    organization = _insurgent(world)
    formation = _insurgent_formation(world, organization)
    target = min(
        (locality_id for locality_id in world.localities
         if locality_id != formation.locality_id),
        key=lambda locality_id: shortest_locality_path(
            world, formation.locality_id, locality_id, formation.mobility
        )[2],
    )
    for locality_id in world.localities:
        own = world.beliefs[(organization.organization_id, locality_id)]
        own.control_estimate.physical = 0.05
        own.confidence = 1.0
        government = world.control_beliefs.get(
            (organization.organization_id, "government", locality_id)
        )
        if government is not None:
            government.control_estimate.physical = 0.95
            government.confidence = 1.0
    world.beliefs[(organization.organization_id, target)].control_estimate.physical = 0.95
    world.control_beliefs[
        (organization.organization_id, "government", target)
    ].control_estimate.physical = 0.05
    formation.operational_status = "ineffective"
    formation.availability = 0.1
    formation.supply_capacity = max(formation.supply_capacity, 1_000_000_000.0)
    formation.supply_stock = formation.supply_capacity

    order = choose_withdrawal_order(world, formation.formation_id, 0.0, ZeroRng())
    assert order is not None
    assert order.purpose == "withdrawal"
    assert order.destination_locality_id == target
    advance_movement_orders(world, order.execute_at)
    assert order.status == "moving"
    assert formation.moving


def test_combat_disengagement_creates_explicit_withdrawal_order():
    world = _world(908)
    organization = _insurgent(world)
    insurgent = _insurgent_formation(world, organization)
    government = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind
        is not OrganizationKind.INSURGENT
        and formation.personnel > 0
    )
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    # Guarantee sufficient materiel for a post-contact withdrawal and make
    # disengagement deterministic without changing the combat equations.
    for formation in (government, insurgent):
        formation.supply_capacity = max(formation.supply_capacity, 1_000_000_000.0)
        formation.supply_stock = formation.supply_capacity
    world.config.combat.disengagement_base = 1.0

    engagement, _ = resolve_engagement(
        world, "SYNTHETIC-WITHDRAWAL", government, insurgent,
        (government.organization_id, insurgent.organization_id), 0.0, ZeroRng(),
    )
    assert engagement.disengaged
    assert engagement.withdrawal_order_ids
    for order_id in engagement.withdrawal_order_ids:
        order = world.movement_orders[order_id]
        assert order.formation_id in engagement.disengaged
        assert order.purpose == "withdrawal"


def test_local_clandestine_members_remain_recruitment_access_without_local_force():
    world = _world(907)
    organization = _insurgent(world)
    formation_localities = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
        and formation.personnel > 0
    }
    locality_id = next(
        locality_id for locality_id in sorted(world.localities)
        if locality_id not in formation_localities
        and sum(person.residence_locality_id == locality_id
                for person in world.persons.values()) >= 2
    )
    local_people = [
        person for person in world.persons.values()
        if person.residence_locality_id == locality_id
    ]
    for person in local_people:
        if person.organization_id == organization.organization_id:
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
    seed, candidate = local_people[:2]
    _set_armed_membership(seed, organization, 0.10)
    organization.member_ids.add(seed.person_id)
    _set_armed_membership(candidate, None, 0.0)
    candidate.social_exposure.clear()
    candidate.grievance = 1.0
    candidate.fear = 0.0
    candidate.political_access = 0.0
    candidate.identities["federal"] = organization.ideology.get("reform", .5)
    world.config.recruitment_rate = 10.0
    world.config.organization_ecology.recruitment_requires_access = True

    recruit_and_retain(world, 0.0, ZeroRng(), interval_days=1.0)
    assert candidate.organization_id == organization.organization_id
    assert candidate.armed_fraction > 0
