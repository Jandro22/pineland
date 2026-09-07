"""Execution-only performance instrumentation for Pineland.

Nothing in this module participates in transition equations, RNG namespaces,
scientific hashes, or archival output.  It exists to make optimization
measurable while keeping the reference scientific state untouched.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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

    def record(self, elapsed: float) -> None:
        self.count += 1
        self.wall_seconds += float(elapsed)
        if elapsed > self.maximum_seconds:
            self.maximum_seconds = float(elapsed)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "wall_seconds": self.wall_seconds,
            "mean_seconds": self.wall_seconds / self.count if self.count else 0.0,
            "maximum_seconds": self.maximum_seconds,
        }


class EventTimingProbe:
    """Temporarily time ProcessEngine handlers on one Simulation instance."""

    def __init__(self, simulation) -> None:
        self.simulation = simulation
        self.timings: dict[str, EventTiming] = defaultdict(EventTiming)
        self._original_execute = None

    def __enter__(self) -> "EventTimingProbe":
        original = self.simulation.processes.execute
        self._original_execute = original

        def timed_execute(event):
            started = perf_counter()
            try:
                return original(event)
            finally:
                self.timings[event.event_type].record(perf_counter() - started)

        self.simulation.processes.execute = timed_execute
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._original_execute is not None:
            self.simulation.processes.execute = self._original_execute

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
    return {
        "wall_seconds": perf_counter() - started,
        "until": float(until),
        "event_types": probe.to_dict(),
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
