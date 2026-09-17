import math
import random

import pytest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.combat import _capability, resolve_engagement
from pineland_sim.events import ScheduledEvent
from pineland_sim.information import detection_probability, observe_target
from pineland_sim.logistics import (
    advance_movement_orders,
    choose_reallocation_orders,
    create_movement_order,
    update_logistics,
)
from pineland_sim.processes import ProcessEngine


def micro_world(seed: int = 62001, *, horizon_days: float = 2.3):
    config = SimulationConfig(
        seed=seed,
        agent_count=120,
        locality_count=17,
        horizon_days=horizon_days,
        output_mode="ensemble",
    )
    config.organization_ecology.enabled = False
    config.combat.contact_opportunity_model = "directional_pairwise"
    config.combat.contact_supply_rule = "no_gate"
    config.information.attribution_error_rate = 0.0
    world = generate_pineland(config)
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    for formation in (government, insurgent):
        formation.availability = 1.0
        formation.readiness = 1.0
        formation.command = 1.0
        formation.cohesion = 1.0
        formation.quality = 1.0
        formation.information = 1.0
        formation.fatigue = 0.0
        formation.supply_stock = formation.supply_capacity
        formation.moving = False
        formation.outside_pineland = False
        formation.operational_status = "effective"
    world.organizations["insurgent"].status = "active"
    # The synthetic battery intentionally normalizes the two focal formations
    # after world generation. Re-baseline conserved supply so later scheduler
    # tests can run the normal checkpoint/invariant path without mistaking
    # that fixture setup for an endogenous stock creation.
    world.initial_supply_stock = (
        sum(source.stock for source in world.supply_sources.values()) +
        sum(formation.supply_stock for formation in world.formations.values()) +
        world.demobilized_arms +
        sum(
            shipment.quantity_deliverable for shipment in world.supply_shipments.values()
            if shipment.status == "in_transit"
        )
    )
    return world, government.formation_id, insurgent.formation_id


def contact_trace(base, government_id: str, insurgent_id: str, *, interval_days: float = 1.0,
                  force_detection: bool = True, rate: float = 0.4):
    world = base.clone()
    world.config.contact_rate = rate
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    event = ScheduledEvent(0.0, 20, 0, "contact", {
        "locality_id": government.locality_id,
        "microzone_id": government.current_microzone_id,
        "government_formation_id": government_id,
        "insurgent_formation_id": insurgent_id,
        "force_detection": force_detection,
        "interval_days": interval_days,
    })
    ProcessEngine(world).execute(event)
    return world, world.contact_funnel_records[-1]


class AlwaysSelectRng:
    def random(self):
        return 0.0

    def choices(self, population, weights, k):
        return [population[0]]


def test_detection_uses_readiness_once_and_target_exposure_monotonically():
    world, government_id, insurgent_id = micro_world()
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    zone_id = government.current_microzone_id

    government.readiness = .1
    low_readiness = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    government.readiness = .9
    high_readiness = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    assert high_readiness > low_readiness

    insurgent.embeddedness = 0.0
    exposed = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    insurgent.embeddedness = 1.0
    concealed = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    assert exposed > concealed

    # Immediate supply stock and HQ connectivity are not local visual/sensor
    # acuity multipliers. Their accumulated operational consequences still
    # reach detection through stored readiness/availability.
    government.supply_stock = 0.0
    government.command = .05
    isolated = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    government.supply_stock = government.supply_capacity
    government.command = 1.0
    connected = detection_probability(
        world, government_id, insurgent_id, government.locality_id,
        source_type="contact", microzone_id=zone_id,
    )
    assert isolated == pytest.approx(connected, abs=1e-12)


def test_target_readiness_supply_availability_and_command_do_not_suppress_other_side_initiation():
    base, government_id, insurgent_id = micro_world()
    base.config.combat.accidental_contact_fraction = 0.0
    base.config.combat.contact_supply_rule = "no_gate"

    _, baseline = contact_trace(base, government_id, insurgent_id)
    government_rate = baseline["directional_hazards_per_day"][government_id]

    for attribute, value in (
        ("readiness", 0.0),
        ("availability", 0.0),
        ("command", 0.0),
    ):
        variant = base.clone()
        setattr(variant.formations[insurgent_id], attribute, value)
        _, trace = contact_trace(variant, government_id, insurgent_id)
        assert trace["directional_hazards_per_day"][government_id] == pytest.approx(
            government_rate, abs=1e-12
        )

    variant = base.clone()
    variant.formations[insurgent_id].supply_stock = 0.0
    _, trace = contact_trace(variant, government_id, insurgent_id)
    assert trace["directional_hazards_per_day"][government_id] == pytest.approx(
        government_rate, abs=1e-12
    )


def test_supply_contact_branches_are_directional_not_hidden_target_gates():
    base, government_id, insurgent_id = micro_world()
    base.config.combat.accidental_contact_fraction = 0.0
    base.config.combat.contact_supply_rule = "initiation_asymmetry"
    base.formations[government_id].supply_stock = base.formations[government_id].supply_capacity
    base.formations[insurgent_id].supply_stock = 0.0
    _, first = contact_trace(base, government_id, insurgent_id)
    assert first["directional_hazards_per_day"][government_id] > 0
    assert first["directional_hazards_per_day"][insurgent_id] == 0

    reverse = base.clone()
    reverse.formations[government_id].supply_stock = 0.0
    reverse.formations[insurgent_id].supply_stock = reverse.formations[insurgent_id].supply_capacity
    _, second = contact_trace(reverse, government_id, insurgent_id)
    assert second["directional_hazards_per_day"][government_id] == 0
    assert second["directional_hazards_per_day"][insurgent_id] > 0

    continuous = base.clone()
    continuous.config.combat.contact_supply_rule = "continuous"
    continuous.formations[government_id].supply_stock = continuous.formations[government_id].supply_capacity
    continuous.formations[insurgent_id].supply_stock = 0.0
    _, third = contact_trace(continuous, government_id, insurgent_id)
    assert third["directional_supply_factors"][government_id] == pytest.approx(1.0)
    assert third["directional_supply_factors"][insurgent_id] == pytest.approx(.2)


def test_directional_contact_cause_identifies_the_only_capable_initiator():
    base, government_id, insurgent_id = micro_world()
    base.config.combat.accidental_contact_fraction = 0.0
    base.formations[insurgent_id].command = 0.0
    world, trace = contact_trace(base, government_id, insurgent_id, rate=50.0)
    assert trace["contact_cause"] == "government_initiated"
    assert trace["initiator_organization_id"] == world.formations[government_id].organization_id
    engagement = next(iter(world.engagements.values()))
    assert engagement.contact_cause == "government_initiated"
    assert engagement.initiator_organization_id == world.formations[government_id].organization_id

    reverse = base.clone()
    reverse.formations[government_id].command = 0.0
    reverse.formations[insurgent_id].command = 1.0
    world, trace = contact_trace(reverse, government_id, insurgent_id, rate=50.0)
    assert trace["contact_cause"] == "insurgent_initiated"
    assert trace["initiator_organization_id"] == world.formations[insurgent_id].organization_id


def test_contact_rate_is_per_pair_per_day_and_interval_invariant():
    base, government_id, insurgent_id = micro_world()
    base.config.combat.accidental_contact_fraction = .1
    rate = .37
    recovered_rates = []
    for dt in (.125, .25, .5, 1.0, 2.0):
        _, trace = contact_trace(
            base, government_id, insurgent_id, interval_days=dt, rate=rate,
        )
        assert trace["contact_hazard_rate_per_day"] == pytest.approx(rate, abs=1e-12)
        recovered_rates.append(-math.log1p(-trace["contact_hazard"]) / dt)
    assert max(recovered_rates) - min(recovered_rates) < 1e-12


def test_directional_production_contact_consumes_existing_detection_belief_without_resampling():
    base, government_id, insurgent_id = micro_world()
    government = base.formations[government_id]
    insurgent = base.formations[insurgent_id]
    observe_target(
        base, government.organization_id, government_id, "SEED:G", "organization_member",
        government.locality_id, insurgent.organization_id, 0.0, random.Random(1),
        insurgent_id, microzone_id=government.current_microzone_id,
        force_detection=True,
    )
    observe_target(
        base, insurgent.organization_id, insurgent_id, "SEED:I", "organization_member",
        insurgent.locality_id, government.organization_id, 0.0, random.Random(2),
        government_id, microzone_id=insurgent.current_microzone_id,
        force_detection=True,
    )
    base.config.combat.contact_supply_rule = "hard_gate"
    base.formations[insurgent_id].supply_stock = 0.0
    before = len(base.observations)
    world, trace = contact_trace(
        base, government_id, insurgent_id,
        interval_days=.4, force_detection=None, rate=.4,
    )
    assert trace["detection_source"] == "actor_local_presence_belief"
    assert trace["detection_signal"][government_id] > 0
    assert trace["detection_signal"][insurgent_id] > 0
    assert len(world.observations) == before


def test_fixed_actor_detection_beliefs_make_contact_cadence_probability_invariant():
    base, government_id, insurgent_id = micro_world()
    government = base.formations[government_id]
    insurgent = base.formations[insurgent_id]
    for observer, target, seed in (
        (government, insurgent, 11),
        (insurgent, government, 12),
    ):
        observe_target(
            base, observer.organization_id, observer.formation_id,
            f"SEED:{observer.formation_id}", "organization_member",
            observer.locality_id, target.organization_id, 0.0, random.Random(seed),
            target.formation_id, microzone_id=observer.current_microzone_id,
            force_detection=True,
        )
    base.config.combat.accidental_contact_fraction = .1
    horizon = 2.3
    rate = .37
    totals = []
    for cadence in (.25, .7, 1.0, 2.0):
        full, remainder = divmod(horizon, cadence)
        windows = [cadence] * int(full)
        if remainder > 1e-12:
            windows.append(remainder)
        survival = 1.0
        for interval in windows:
            _, trace = contact_trace(
                base, government_id, insurgent_id,
                interval_days=interval, force_detection=None, rate=rate,
            )
            survival *= 1.0 - trace["contact_hazard"]
        totals.append(1.0 - survival)
    assert max(totals) - min(totals) < 1e-12


class ContactWindowProbe(Simulation):
    def __init__(self, world):
        self.contact_windows = []
        super().__init__(world)

    def _schedule_contacts(self, current_time, *, interval_days=None, realization_time=None):
        self.contact_windows.append((current_time, interval_days, realization_time))


def test_scheduler_contact_windows_preserve_full_cadence_across_observation_horizon():
    horizon = 2.3
    for cadence in (.25, .7, 1.0, 2.0):
        world, _, _ = micro_world(62100 + int(cadence * 100), horizon_days=horizon)
        # This probe exercises the legacy formation-contact scheduler directly.
        # The default multichannel architecture schedules organized_action
        # windows instead and is covered in test_action_model.py.
        world.config.combat.organized_action_architecture = "legacy_contact_only"
        world.config.intervals.contact = cadence
        simulation = ContactWindowProbe(world)
        simulation.run(until=horizon)
        windows = simulation.contact_windows
        assert windows
        # Observation boundaries must not truncate the latent cadence.  The
        # final scan processed before ``horizon`` is allowed to schedule a
        # realization beyond it so that checkpointed and uninterrupted runs
        # have identical future queues.
        assert all(float(interval) == pytest.approx(cadence) for _, interval, _ in windows)
        starts = [float(start) for start, _, _ in windows]
        assert starts[0] == pytest.approx(0.0, abs=1e-12)
        assert starts[-1] <= horizon + 1e-12
        assert starts[-1] + cadence > horizon
        for left, right in zip(starts, starts[1:]):
            assert right - left == pytest.approx(cadence, abs=1e-12)
        for start, interval, realization in windows:
            assert realization == pytest.approx(start + interval, abs=1e-12)


def test_cumulative_contact_probability_is_calendar_time_invariant():
    horizon = 2.3
    rate = .37
    base, government_id, insurgent_id = micro_world(horizon_days=horizon)
    base.config.combat.accidental_contact_fraction = .1
    expected = 1.0 - math.exp(-rate * horizon)
    cumulative = []
    for cadence in (.25, .7, 1.0, 2.0):
        full, remainder = divmod(horizon, cadence)
        windows = [cadence] * int(full)
        if remainder > 1e-12:
            windows.append(remainder)
        survival = 1.0
        for interval in windows:
            _, trace = contact_trace(
                base, government_id, insurgent_id,
                interval_days=interval, rate=rate,
            )
            survival *= 1.0 - trace["contact_hazard"]
        cumulative.append(1.0 - survival)
    assert all(value == pytest.approx(expected, abs=1e-12) for value in cumulative)


def test_distance_is_a_physical_opportunity_boundary_not_a_capability_penalty():
    base, government_id, insurgent_id = micro_world()
    government = base.formations[government_id]
    insurgent = base.formations[insurgent_id]
    insurgent.current_microzone_id = next(
        zone.microzone_id for zone in base.microzones.values()
        if zone.locality_id == government.locality_id and
        zone.microzone_id != government.current_microzone_id
    )
    simulation = Simulation(base)
    simulation._schedule_contacts(0.0)
    assert not any(
        event.event_type == "contact" and
        event.payload.get("government_formation_id") == government_id and
        event.payload.get("insurgent_formation_id") == insurgent_id
        for event in simulation.scheduler._queue
    )
    _, trace = contact_trace(base, government_id, insurgent_id)
    assert trace["failure_reason"] == "no_microzone_proximity"
    assert trace["gate_counts"]["engagement_hazard_draws"] == 0


def test_combat_capability_applies_readiness_supply_and_manpower_monotonically_once():
    base, government_id, _ = micro_world()
    formation = base.formations[government_id]
    zone = base.microzones[formation.current_microzone_id]

    formation.supply_stock = formation.supply_capacity
    formation.readiness = 1.0
    full_supply = _capability(formation, zone, 1.0)
    formation.supply_stock = 0.0
    empty_supply = _capability(formation, zone, 1.0)
    # Supply enters capability only through effective readiness, which is then
    # inside the 0.72 manpower/capability exponent exactly once.
    assert full_supply / empty_supply == pytest.approx((1.0 / .2) ** .72, rel=1e-12)

    formation.supply_stock = formation.supply_capacity
    formation.readiness = .5
    half_readiness = _capability(formation, zone, 1.0)
    formation.readiness = 1.0
    full_readiness = _capability(formation, zone, 1.0)
    assert full_readiness / half_readiness == pytest.approx((1.0 / .5) ** .72, rel=1e-12)

    original_personnel = formation.personnel
    formation.personnel = original_personnel * 2
    double_manpower = _capability(formation, zone, 1.0)
    formation.personnel = original_personnel
    normal_manpower = _capability(formation, zone, 1.0)
    assert double_manpower / normal_manpower == pytest.approx(2.0 ** .72, rel=1e-12)


def test_low_availability_reduces_capability_but_does_not_make_target_invulnerable():
    world, government_id, insurgent_id = micro_world()
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    government.availability = 0.0
    before = government.personnel
    engagement, _ = resolve_engagement(
        world, "E-exposure", government, insurgent,
        (government.organization_id, insurgent.organization_id),
        0.0, random.Random(7),
    )
    assert engagement.effective_capability[government_id] <= 1e-8
    assert engagement.personnel_losses[government_id] > 0.0
    assert government.personnel < before


@pytest.mark.parametrize("mode", ["ineffective", "moving", "outside", "zero_personnel"])
def test_resolver_rejects_zombie_or_nonpresent_formations(mode):
    world, government_id, insurgent_id = micro_world()
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    if mode == "ineffective":
        insurgent.operational_status = "ineffective"
    elif mode == "moving":
        insurgent.moving = True
    elif mode == "outside":
        insurgent.outside_pineland = True
    else:
        insurgent.personnel = 0.0
    with pytest.raises(ValueError, match="combat-ineligible"):
        resolve_engagement(
            world, "E-zombie", government, insurgent,
            (government.organization_id,), 0.0, random.Random(1),
        )


def test_scheduler_and_handler_both_exclude_unit_that_becomes_ineffective():
    world, government_id, insurgent_id = micro_world()
    simulation = Simulation(world)
    simulation._schedule_contacts(0.0, interval_days=1.0, realization_time=1.0)
    event = next(
        event for event in simulation.scheduler._queue
        if event.event_type == "contact" and
        event.payload["government_formation_id"] == government_id and
        event.payload["insurgent_formation_id"] == insurgent_id
    )
    world.formations[insurgent_id].operational_status = "ineffective"
    world.time = event.time
    ProcessEngine(world).execute(event)
    assert not world.engagements
    assert world.contact_funnel_records[-1]["failure_reason"] == "no_active_insurgent_formation"


@pytest.mark.parametrize("mode", ["ineffective", "outside", "zero_personnel", "zero_availability"])
def test_reallocation_selector_excludes_non_deployable_formations(mode):
    world, government_id, _ = micro_world()
    focal = world.formations[government_id]
    for formation in world.formations.values():
        if formation.formation_id != government_id:
            formation.moving = True
    world.config.logistics.reallocation_rate = 1.0
    if mode == "ineffective":
        focal.operational_status = "ineffective"
    elif mode == "outside":
        focal.outside_pineland = True
    elif mode == "zero_personnel":
        focal.personnel = 0.0
    else:
        focal.availability = 0.0
    orders = choose_reallocation_orders(world, 0.0, AlwaysSelectRng())
    assert not any(order.formation_id == government_id for order in orders)


def test_pending_movement_revalidates_formation_before_departure():
    world, government_id, _ = micro_world()
    formation = world.formations[government_id]
    destination = next(iter(world.adjacency[formation.locality_id]))
    order = create_movement_order(
        world, government_id, destination, 0.0, AlwaysSelectRng()
    )
    assert order.status == "pending"
    formation.operational_status = "ineffective"
    result = advance_movement_orders(world, order.execute_at)
    assert order.status == "blocked_unavailable"
    assert result["blocked_unavailable"] == 1
    assert not formation.moving
    assert formation.locality_id == order.origin_locality_id


def test_ineffective_unit_has_zero_strength_until_logistics_recovery_reactivates_it():
    world, government_id, _ = micro_world()
    formation = world.formations[government_id]
    formation.operational_status = "ineffective"
    formation.availability = .08
    formation.cohesion = 1.0
    formation.readiness = 1.0
    formation.supply_stock = formation.supply_capacity
    assert formation.effective_strength() == 0.0
    update_logistics(world, 1.0, 1.0)
    assert formation.operational_status == "effective"
    assert formation.effective_strength() > 0.0


def test_combat_changes_control_only_through_later_physical_refresh():
    world, government_id, insurgent_id = micro_world()
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    locality = world.localities[government.locality_id]
    before = {actor: vector.to_dict() for actor, vector in locality.control.items()}
    resolve_engagement(
        world, "E-control", government, insurgent,
        (government.organization_id, insurgent.organization_id),
        0.0, random.Random(5),
    )
    after_combat = {actor: vector.to_dict() for actor, vector in locality.control.items()}
    assert after_combat == before
