from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.performance import (
    EventTiming,
    compare_reference_optimized,
    profile_simulation_events,
)
from pineland_sim.events import CalendarEventScheduler, EventScheduler


def test_event_timing_reports_exact_p95():
    timing = EventTiming()
    for value in range(1, 21):
        timing.record(float(value))
    payload = timing.to_dict()
    assert payload["count"] == 20
    assert payload["p95_seconds"] == 19.0
    assert payload["maximum_seconds"] == 20.0


def test_execution_profiler_is_output_only_and_restores_counters():
    world = generate_pineland(
        SimulationConfig(
            agent_count=30,
            locality_count=17,
            horizon_days=1,
            seed=991,
        )
    )
    simulation = Simulation(world)
    assert world.performance_counters is None
    payload = profile_simulation_events(simulation, until=0.25)
    assert world.performance_counters is None
    assert payload["wall_seconds"] >= 0.0
    assert payload["scheduler_max_pending"] >= 0
    assert payload["event_types"]
    assert "cache_counters" in payload
    assert "active_sets" in payload


def test_calendar_scheduler_exactly_matches_heap_ordering():
    heap = EventScheduler()
    calendar = CalendarEventScheduler()
    rows = [
        (2.0, "a", 10),
        (1.0, "b", 20),
        (1.0, "c", 10),
        (1.0, "d", 10),
        (3.0, "e", 5),
    ]
    for time, event_type, priority in rows:
        heap.schedule(time, event_type, priority=priority)
        calendar.schedule(time, event_type, priority=priority)
    heap_rows = []
    calendar_rows = []
    while heap:
        event = heap.pop_next()
        heap_rows.append((event.time, event.priority, event.sequence, event.event_type))
    while calendar:
        event = calendar.pop_next()
        calendar_rows.append(
            (event.time, event.priority, event.sequence, event.event_type)
        )
    assert calendar_rows == heap_rows


def test_calendar_scheduler_survives_burn_in_reinitialization():
    config = SimulationConfig(
        agent_count=30,
        locality_count=17,
        horizon_days=1,
        seed=993,
        burn_in_days=0.25,
    )
    simulation = Simulation(generate_pineland(config))
    simulation.configure_execution(scheduler_backend="calendar")
    simulation.initialize()
    assert isinstance(simulation.scheduler, CalendarEventScheduler)


def test_reference_and_optimized_execution_dual_run_agree():
    world = generate_pineland(
        SimulationConfig(
            agent_count=40,
            locality_count=17,
            horizon_days=1,
            seed=992,
        )
    )
    result = compare_reference_optimized(world, until=0.5)
    assert result["exact_decision_state_equivalence"] is True
    assert result["differing_components"] == []
