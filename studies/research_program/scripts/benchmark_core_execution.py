"""Generic small/synthetic execution, fork, and serialization benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import Simulation, SimulationConfig, SimulationParticle, generate_pineland
from pineland_sim.performance import (
    benchmark_particle_forks,
    benchmark_serialization,
    runtime_manifest,
)
from pineland_sim.reproducibility import decision_state_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=120)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=30.0)
    parser.add_argument("--forks", type=int, default=8)
    parser.add_argument("--serializations", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = SimulationConfig(
        agent_count=args.agents,
        locality_count=args.localities,
        horizon_days=args.days,
        seed=args.seed,
        output_mode="ensemble",
    )
    simulation = Simulation(generate_pineland(config))
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    started = perf_counter()
    simulation.run(until=args.days)
    run_seconds = perf_counter() - started
    particle = SimulationParticle(simulation=simulation, lineage_id="benchmark")
    payload = {
        "schema_version": "pineland.performance.core_execution.v1",
        "scientific_status": "execution-only",
        "runtime": runtime_manifest(),
        "agents": args.agents,
        "localities": args.localities,
        "days": args.days,
        "run_seconds": run_seconds,
        "decision_state_sha256": decision_state_sha256(simulation.world),
        "fork": benchmark_particle_forks(particle, count=args.forks),
        "serialization": benchmark_serialization(
            particle, repeats=args.serializations
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "run_seconds": run_seconds,
    }))


if __name__ == "__main__":
    main()
