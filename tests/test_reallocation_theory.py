"""Synthetic identification tests for formation reallocation theory.

These tests deliberately use generated worlds only.  They do not read Nepal or
Afghanistan outcomes and are intended to constrain general mechanism semantics.
"""

import math

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.logistics import (
    _sanctuary_access,
    choose_reallocation_orders,
    reallocation_decision_probability,
    reallocation_destination_score,
    shortest_locality_travel_times,
)


class MaxChoiceRng:
    """Trigger eligible decisions and select maximum random-utility weight."""

    def random(self):
        return 0.0

    def choices(self, population, weights, k):
        index = max(range(len(weights)), key=weights.__getitem__)
        return [population[index]]


def synthetic_world(seed: int = 20260905):
    config = SimulationConfig(
        agent_count=180,
        locality_count=24,
        horizon_days=2,
        seed=seed,
    )
    config.logistics.reallocation_rate = 1.0
    return generate_pineland(config)


def focal(world, insurgent: bool):
    return next(
        formation for formation in sorted(
            world.formations.values(), key=lambda item: item.formation_id
        )
        if (
            world.organizations[formation.organization_id].kind
            is OrganizationKind.INSURGENT
        ) == insurgent
    )


def set_control_beliefs(
    world,
    formation,
    locality_id,
    *,
    own,
    opponent,
    own_confidence=1.0,
    opponent_confidence=1.0,
):
    insurgent = (
        world.organizations[formation.organization_id].kind
        is OrganizationKind.INSURGENT
    )
    own_target = "insurgent" if insurgent else "government"
    opponent_target = "government" if insurgent else "insurgent"
    legacy = world.beliefs[(formation.organization_id, locality_id)]
    legacy.control_estimate.physical = own
    legacy.confidence = own_confidence
    own_belief = world.control_beliefs[
        (formation.organization_id, own_target, locality_id)
    ]
    own_belief.control_estimate.physical = own
    own_belief.confidence = own_confidence
    opposing = world.control_beliefs[
        (formation.organization_id, opponent_target, locality_id)
    ]
    opposing.control_estimate.physical = opponent
    opposing.confidence = opponent_confidence


def test_reallocation_probability_is_calendar_time_invariant():
    daily = 0.04
    quarter = reallocation_decision_probability(daily, 0.25)
    composed = 1.0 - (1.0 - quarter) ** 4
    assert math.isclose(composed, daily, rel_tol=0.0, abs_tol=1e-12)
    assert reallocation_decision_probability(0.0, 10.0) == 0.0
    assert reallocation_decision_probability(1.0, 0.01) == 1.0


def test_homogeneous_world_has_explicit_stay_option():
    world = synthetic_world(202609051)
    formation = focal(world, insurgent=False)
    for other in world.formations.values():
        if other.formation_id != formation.formation_id:
            other.moving = True
    for locality in world.localities.values():
        locality.population = 10_000
        set_control_beliefs(
            world, formation, locality.locality_id,
            own=.5, opponent=.5,
        )
    orders = choose_reallocation_orders(
        world, 0.0, MaxChoiceRng(), interval_days=1.0
    )
    assert orders == []


def test_government_can_reinforce_threatened_control_not_only_fill_gaps():
    world = synthetic_world(202609052)
    formation = focal(world, insurgent=False)
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ][:2]
    threatened, secure = candidates
    for locality_id, opponent in ((threatened, .9), (secure, .1)):
        world.localities[locality_id].population = 10_000
        set_control_beliefs(
            world, formation, locality_id,
            own=.9, opponent=opponent,
        )
    threatened_score = reallocation_destination_score(
        world, formation, threatened,
        travel_hours=4.0, maximum_population=10_000,
        route=[formation.locality_id, threatened],
    )
    secure_score = reallocation_destination_score(
        world, formation, secure,
        travel_hours=4.0, maximum_population=10_000,
        route=[formation.locality_id, secure],
    )
    assert threatened_score["threatened_control"] > secure_score["threatened_control"]
    assert threatened_score["utility"] > secure_score["utility"]


def test_insurgent_policy_supports_frontier_and_persistent_foothold_channels():
    world = synthetic_world(202609053)
    formation = focal(world, insurgent=True)
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ][:2]
    frontier, secure = candidates
    for locality_id, own in ((frontier, .1), (secure, .9)):
        world.localities[locality_id].population = 10_000
        set_control_beliefs(
            world, formation, locality_id,
            own=own, opponent=.1,
        )
    frontier_score = reallocation_destination_score(
        world, formation, frontier,
        travel_hours=4.0, maximum_population=10_000,
        footholds={}, route=[formation.locality_id, frontier],
    )
    secure_score = reallocation_destination_score(
        world, formation, secure,
        travel_hours=4.0, maximum_population=10_000,
        footholds={}, route=[formation.locality_id, secure],
    )
    assert frontier_score["frontier"] > secure_score["frontier"]
    assert frontier_score["utility"] > secure_score["utility"]

    with_foothold = reallocation_destination_score(
        world, formation, secure,
        travel_hours=4.0, maximum_population=10_000,
        footholds={secure: 1.0}, route=[formation.locality_id, secure],
    )
    assert with_foothold["foothold"] == 1.0
    assert with_foothold["utility"] > secure_score["utility"]


def test_low_confidence_does_not_make_extreme_control_a_hidden_strong_signal():
    world = synthetic_world(202609054)
    formation = focal(world, insurgent=True)
    locality_id = next(
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    )
    set_control_beliefs(
        world, formation, locality_id,
        own=1.0, opponent=0.0,
        own_confidence=0.0, opponent_confidence=0.0,
    )
    score = reallocation_destination_score(
        world, formation, locality_id,
        travel_hours=0.0,
        maximum_population=world.localities[locality_id].population,
        footholds={}, route=[formation.locality_id, locality_id],
    )
    assert score["own_control_raw"] == 1.0
    assert score["opponent_control_raw"] == 0.0
    assert score["own_control"] == .5
    assert score["opponent_control"] == .5
    assert score["uncertainty"] == 1.0


def test_sanctuary_is_spatial_gradient_not_border_only_switch():
    world = synthetic_world(202609055)
    formation = focal(world, insurgent=True)
    organization = world.organizations[formation.organization_id]
    border = next(iter(world.border_segments.values()))
    organization.external_sanctuary = 1.0
    organization.sponsor_dependence = {border.foreign_state_id: 1.0}
    travel = shortest_locality_travel_times(
        world, border.locality_id, formation.mobility
    )
    far = max(travel, key=travel.get)
    near_access = _sanctuary_access(
        world, formation.organization_id, border.locality_id,
        mobility=formation.mobility,
    )
    far_access = _sanctuary_access(
        world, formation.organization_id, far,
        mobility=formation.mobility,
    )
    assert near_access > 0.0
    assert 0.0 <= far_access < near_access

    # The gradient must actually enter ordinary allocation utility, not merely
    # exist as an unused diagnostic helper.  Equalize every competing term and
    # hold travel time fixed to isolate the sanctuary channel.
    near = border.locality_id
    for locality_id in (near, far):
        world.localities[locality_id].population = 10_000
        set_control_beliefs(
            world, formation, locality_id,
            own=.5, opponent=.5,
        )
    near_score = reallocation_destination_score(
        world, formation, near,
        travel_hours=4.0, maximum_population=10_000,
        footholds={}, route=[formation.locality_id, near],
    )
    far_score = reallocation_destination_score(
        world, formation, far,
        travel_hours=4.0, maximum_population=10_000,
        footholds={}, route=[formation.locality_id, far],
    )
    assert near_score["sanctuary"] > far_score["sanctuary"]
    assert near_score["utility"] > far_score["utility"]


def test_believed_hostile_intermediate_route_reduces_utility():
    world = synthetic_world(202609056)
    formation = focal(world, insurgent=True)
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ][:2]
    destination, intermediate = candidates
    set_control_beliefs(
        world, formation, destination, own=.2, opponent=.2,
    )
    set_control_beliefs(
        world, formation, intermediate, own=.2, opponent=.9,
    )
    exposed = reallocation_destination_score(
        world, formation, destination,
        travel_hours=5.0,
        maximum_population=world.localities[destination].population,
        footholds={},
        route=[formation.locality_id, intermediate, destination],
    )
    direct = reallocation_destination_score(
        world, formation, destination,
        travel_hours=5.0,
        maximum_population=world.localities[destination].population,
        footholds={},
        route=[formation.locality_id, destination],
    )
    assert exposed["route_risk"] > direct["route_risk"]
    assert exposed["utility"] < direct["utility"]


def test_reallocation_does_not_issue_known_unaffordable_move():
    world = synthetic_world(202609057)
    formation = focal(world, insurgent=False)
    for other in world.formations.values():
        if other.formation_id != formation.formation_id:
            other.moving = True
    formation.supply_stock = 0.0
    orders = choose_reallocation_orders(
        world, 0.0, MaxChoiceRng(), interval_days=1.0
    )
    assert orders == []

