"""Short, non-scoring Afghanistan execution profiler.

This script never reads holdout outcomes and does not alter model parameters.
It exists solely to profile execution mechanics on a historically structured
world.  The resulting JSON is a performance artifact, not empirical evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.performance import (
    benchmark_particle_forks,
    benchmark_serialization,
    profile_simulation_events,
    runtime_manifest,
)

RUNNER = Path(__file__).with_name("run_afghanistan_filtered_prospective_2005.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("afghanistan_perf_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--days", type=float, default=30.0)
    parser.add_argument("--forks", type=int, default=8)
    parser.add_argument("--strength", type=float, default=7500.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = _load_runner()
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    started = perf_counter()
    base_world = runner.generate_pineland(
        runner._config(args.seed, max(60.0, args.days)),
        empirical_geography=case,
    )
    particle = runner.build_initial_particle(
        seed=args.seed,
        particle_index=0,
        taliban_strength=args.strength,
        horizon=max(60.0, args.days),
        case=case,
        inputs=inputs,
        base_world=base_world,
    ).state
    initialization_seconds = perf_counter() - started

    fork = benchmark_particle_forks(particle, count=args.forks)
    serialization = benchmark_serialization(particle, repeats=2)
    execution = profile_simulation_events(particle.simulation, until=args.days)
    payload = {
        "schema_version": "pineland.performance.afghanistan_execution.v1",
        "scientific_status": "execution-only; not an empirical fit artifact",
        "runtime": runtime_manifest(),
        "seed": args.seed,
        "days": args.days,
        "taliban_initial_strength": args.strength,
        "initialization_seconds": initialization_seconds,
        "fork_benchmark": fork,
        "serialization_benchmark": serialization,
        "execution_profile": execution,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), **fork, **execution}))


if __name__ == "__main__":
    main()
