"""Run one complete synthetic A5 fixed-work benchmark repetition."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import platform
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
SCRIPTS = ROOT / "studies" / "research_program" / "scripts"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SCRIPTS))

from pineland_sim import (  # noqa: E402
    Particle,
    PersistentParticlePool,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.reproducibility import (  # noqa: E402
    decision_state_sha256,
    file_sha256,
    model_sha256,
    repository_state,
    scientific_config_sha256,
)
from pineland_sim.state_estimation import particle_weights  # noqa: E402
import run_afghanistan_filtered_prospective_2005 as runner  # noqa: E402


PARTICLES = 32
WEEKS = 8
BRANCHES = 3
PWB = PARTICLES * WEEKS * BRANCHES
BASE_SEED = 20050111


def _config(seed: int) -> SimulationConfig:
    config = SimulationConfig(
        seed=seed,
        agent_count=80,
        locality_count=17,
        horizon_days=60.0,
        output_mode="ensemble",
    )
    config.validate()
    return config


def _build_particles(seed: int, particle_count: int) -> list[Particle[SimulationParticle]]:
    particles = []
    for index in range(particle_count):
        world = generate_pineland(_config(seed + index))
        world.evaluation_region_by_locality = {
            locality_id: locality_id for locality_id in world.localities
        }
        simulation = Simulation(world)
        simulation.configure_execution(
            execution_backend="ensemble",
            validate_invariants=False,
            checkpointing=False,
            retain_output_archives=False,
        )
        particles.append(
            Particle(
                SimulationParticle(
                    simulation,
                    lineage_id=f"fixed.{seed}.{index}",
                )
            )
        )
    return particles


def _observations(world, weeks: int):
    provinces = tuple(sorted(world.localities))
    return [
        runner.ProvinceWeekObservation(
            start_day=7.0 * week,
            end_day=7.0 * (week + 1),
            week_index=week,
            active_provinces=frozenset(),
            provinces=provinces,
        )
        for week in range(weeks)
    ]


def run(
    *,
    output: Path,
    seed: int = BASE_SEED,
    workers: int = 16,
    particle_count: int = PARTICLES,
    weeks: int = WEEKS,
    branches: int = BRANCHES,
    balance_resampling: bool = True,
) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing benchmark evidence: {output}")
    if particle_count < 2 or weeks < 1 or branches < 1:
        raise ValueError("particle_count/weeks/branches must be valid")
    if workers < 1 or workers > particle_count:
        raise ValueError("workers must lie in [1, particles]")
    particles = _build_particles(seed, particle_count)
    observations = _observations(particles[0].state.world, weeks)
    config = _config(seed)
    started = perf_counter()
    coordinator_cpu_started = process_time()
    pool = PersistentParticlePool(
        [particle.state for particle in particles],
        propagate=runner._resident_particle_job,
        fork_state=runner._fork_particle_state,
        workers=workers,
        summarize_state=runner._resident_particle_hash,
    )
    try:
        filter_ = runner.run_training_filter(
            particles,
            observations,
            filter_seed=seed + 17_003,
            likelihood_branches=branches,
            workers=workers,
            resident_pool=pool,
            keep_resident=True,
            balance_resampling=balance_resampling,
            packed_execution=True,
        )
        summaries = dict(pool.summarize())
        worker_cpu_seconds = pool.cpu_seconds()
    finally:
        pool.close()
    wall_seconds = perf_counter() - started
    row = {
        "seed": int(seed),
        "particles": particle_count,
        "weekly_boundaries": weeks,
        "branch_equivalents": branches,
        "pwb": particle_count * weeks * branches,
        "wall_seconds": wall_seconds,
        "pwb_per_second": particle_count * weeks * branches / wall_seconds,
        "coordinator_cpu_seconds": process_time() - coordinator_cpu_started,
        "resident_worker_cpu_seconds": worker_cpu_seconds,
        "process_count": int(1 + workers),
        "workers": workers,
        "engine": "packed_nested_resident_filter",
        "weights": particle_weights(filter_.particles),
        "decision_state_sha256": [
            summaries[index]["decision_state_sha256"]
            for index in range(particle_count)
        ],
        "nested_propagator_diagnostics": getattr(
            filter_, "nested_propagator_diagnostics", {}
        ),
        "worker_balance_history": getattr(
            filter_, "worker_balance_history", []
        ),
    }
    repo = repository_state(ROOT)
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_fixed_work_benchmark_v1",
        "protocol": {
            "particles": particle_count,
            "weekly_boundaries": weeks,
            "branch_equivalents": branches,
            "pwb": particle_count * weeks * branches,
            "observations": "synthetic all-inactive; no historical outcomes read",
            "engine": row["engine"],
            "workers": workers,
            "warmup": "none required; CPython has no JIT and process launch is included",
            "acceptance": {
                "E1_pwb_per_second_minimum": 4.0,
                "E2_pwb_per_second_target": 10.0,
                "E1_passed": row["pwb_per_second"] >= 4.0,
                "E2_passed": row["pwb_per_second"] >= 10.0,
            },
        },
        "result": row,
        "provenance": {
            "commit": repo["commit_hash"],
            "dirty_paths": repo["dirty_paths"],
            "tracked_diff_sha256": repo["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "configuration_sha256": scientific_config_sha256(config),
            "runner_sha256": file_sha256(Path(__file__)),
            "python": platform.python_version(),
            "logical_cpu_count": os.cpu_count(),
        },
        "passed": row["pwb_per_second"] >= 4.0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output.resolve()),
        "pwb_per_second": row["pwb_per_second"],
        "E1_passed": result["protocol"]["acceptance"]["E1_passed"],
        "E2_passed": result["protocol"]["acceptance"]["E2_passed"],
    }, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=BASE_SEED)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--particles", type=int, default=PARTICLES)
    parser.add_argument("--weeks", type=int, default=WEEKS)
    parser.add_argument("--branches", type=int, default=BRANCHES)
    parser.add_argument("--unbalanced-resampling", action="store_true")
    args = parser.parse_args()
    run(
        output=args.output.resolve(),
        seed=args.seed,
        workers=args.workers,
        particle_count=args.particles,
        weeks=args.weeks,
        branches=args.branches,
        balance_resampling=not args.unbalanced_resampling,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
