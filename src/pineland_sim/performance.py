"""Execution-only performance instrumentation for Pineland.

Nothing in this module participates in transition equations, RNG namespaces,
scientific hashes, or archival output.  It exists to make optimization
measurable while keeping the reference scientific state untouched.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil
import os
import pickle
import platform
import sys
from time import perf_counter
from typing import Any


@dataclass(slots=True)
class EventTiming:
    count: int = 0
    wall_seconds: float = 0.0
    maximum_seconds: float = 0.0
    samples: list[float] = field(default_factory=list)

    def record(self, elapsed: float) -> None:
        self.count += 1
        self.wall_seconds += float(elapsed)
        self.samples.append(float(elapsed))
        if elapsed > self.maximum_seconds:
            self.maximum_seconds = float(elapsed)

    def to_dict(self) -> dict[str, float | int]:
        ordered = sorted(self.samples)
        p95 = (
            ordered[max(0, ceil(0.95 * len(ordered)) - 1)]
            if ordered else 0.0
        )
        return {
            "count": self.count,
            "wall_seconds": self.wall_seconds,
            "mean_seconds": self.wall_seconds / self.count if self.count else 0.0,
            "maximum_seconds": self.maximum_seconds,
            "p95_seconds": p95,
        }


class EventTimingProbe:
    """Temporarily time ProcessEngine handlers on one Simulation instance."""

    def __init__(self, simulation) -> None:
        self.simulation = simulation
        self.timings: dict[str, EventTiming] = defaultdict(EventTiming)
        self._original_execute = None
        self._previous_counters = None
        self.scheduler_max_pending = len(simulation.scheduler)

    def __enter__(self) -> "EventTimingProbe":
        original = self.simulation.processes.execute
        self._original_execute = original
        self._previous_counters = self.simulation.world.performance_counters
        self.simulation.world.performance_counters = {}

        def timed_execute(event):
            started = perf_counter()
            try:
                return original(event)
            finally:
                self.timings[event.event_type].record(perf_counter() - started)
                self.scheduler_max_pending = max(
                    self.scheduler_max_pending, len(self.simulation.scheduler)
                )

        self.simulation.processes.execute = timed_execute
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_execute is not None:
            self.simulation.processes.execute = self._original_execute
        self.simulation.world.performance_counters = self._previous_counters

    def to_dict(self) -> dict[str, dict[str, float | int]]:
        return {
            event_type: timing.to_dict()
            for event_type, timing in sorted(self.timings.items())
        }


def profile_simulation_events(simulation, *, until: float) -> dict[str, Any]:
    """Advance one simulation while collecting event-type timing diagnostics."""
    started = perf_counter()
    with EventTimingProbe(simulation) as probe:
        simulation.run(until=until)
        counters = dict(simulation.world.performance_counters or {})
        active_sets = {
            "formations": len(simulation.world.formations),
            "active_information_relays": len(
                simulation.world.active_information_relays
            ),
            "active_shipments": len(simulation.world.active_shipment_ids),
            "active_movement_orders": len(
                simulation.world.active_movement_order_ids
            ),
            "state_event_weeks": len(
                simulation.world.state_based_event_localities_by_week
            ),
        }
    return {
        "wall_seconds": perf_counter() - started,
        "until": float(until),
        "event_types": probe.to_dict(),
        "scheduler_max_pending": probe.scheduler_max_pending,
        "cache_counters": counters,
        "active_sets": active_sets,
    }


def benchmark_particle_forks(particle, *, count: int = 8) -> dict[str, float | int]:
    if count < 1:
        raise ValueError("count must be positive")
    started = perf_counter()
    children = [particle.fork(index) for index in range(count)]
    elapsed = perf_counter() - started
    # Retain children until after the timing boundary so garbage collection
    # cannot make one run artificially cheaper than another.
    child_count = len(children)
    return {
        "fork_count": child_count,
        "wall_seconds": elapsed,
        "seconds_per_fork": elapsed / child_count,
    }


def benchmark_serialization(value: Any, *, repeats: int = 3) -> dict[str, float | int]:
    """Measure trusted-local worker/cache serialization without writing files."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    encode_total = 0.0
    decode_total = 0.0
    payload = b""
    for _ in range(repeats):
        started = perf_counter()
        payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        encode_total += perf_counter() - started
        started = perf_counter()
        pickle.loads(payload)
        decode_total += perf_counter() - started
    return {
        "repeats": repeats,
        "payload_bytes": len(payload),
        "mean_encode_seconds": encode_total / repeats,
        "mean_decode_seconds": decode_total / repeats,
    }


def runtime_manifest() -> dict[str, Any]:
    """Return execution provenance useful for comparing benchmark artifacts."""
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_cache_tag": sys.implementation.cache_tag,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "gil_enabled": bool(getattr(sys, "_is_gil_enabled", lambda: True)()),
    }


def compare_reference_optimized(world, *, until: float) -> dict[str, Any]:
    """Dual-run a small world and localize any execution-semantic mismatch."""
    from .reproducibility import decision_state_component_hashes
    from .simulation import Simulation

    reference = Simulation(world.clone())
    optimized = Simulation(world.clone())
    optimized.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    reference_started = perf_counter()
    reference.run(until=until)
    reference_seconds = perf_counter() - reference_started
    optimized_started = perf_counter()
    optimized.run(until=until)
    optimized_seconds = perf_counter() - optimized_started
    left = decision_state_component_hashes(reference.world)
    right = decision_state_component_hashes(optimized.world)
    differing = sorted(
        key for key in set(left) | set(right)
        if left.get(key) != right.get(key)
    )
    return {
        "exact_decision_state_equivalence": not differing,
        "differing_components": differing,
        "reference_seconds": reference_seconds,
        "optimized_seconds": optimized_seconds,
        "speedup": (
            reference_seconds / optimized_seconds
            if optimized_seconds > 0 else float("inf")
        ),
    }
