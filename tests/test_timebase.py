from __future__ import annotations

import pytest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine
from pineland_sim.timebase import reference_probability


def test_reference_probability_composes_across_partitions():
    monthly = reference_probability(.2, 30.0, 30.0)
    half_month = reference_probability(.2, 15.0, 30.0)
    assert monthly == pytest.approx(.2)
    assert 1 - (1 - half_month) ** 2 == pytest.approx(monthly)


def test_economy_external_support_is_not_multiplied_by_locality_count():
    config = SimulationConfig(
        agent_count=200,
        locality_count=24,
        horizon_days=1,
        seed=20260905,
    )
    world = generate_pineland(config)
    insurgent = world.organizations["insurgent"]
    insurgent.external_support = 12_000.0
    for locality in world.localities.values():
        locality.control["insurgent"].fiscal = 0.0

    before = insurgent.resources
    result = ProcessEngine(world).on_economy(
        "E-TIMEBASE-ECONOMY",
        ScheduledEvent(30.0, 0, 0, "economy", {"interval": 30.0}),
    )

    assert result["external_support_inflow"] == pytest.approx(1_000.0)
    assert insurgent.resources - before == pytest.approx(1_000.0)


def test_daily_mobility_probability_composes_when_scheduler_is_refined():
    probability = .12
    half_day = reference_probability(probability, .5, 1.0)
    assert 1 - (1 - half_day) ** 2 == pytest.approx(probability)
