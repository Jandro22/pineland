"""Benchmark resident particle scaling without reading forecast outcomes.

The benchmark uses a short synthetic observation surface on the historically
structured Afghanistan world.  It measures pool startup, propagation, and
snapshot/IPC separately, then verifies that every worker count produces the
same decision-state hashes and nested likelihoods.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.reproducibility import decision_state_sha256
from pineland_sim.state_estimation import PersistentParticlePool
from pineland_sim.performance import runtime_manifest

RUNNER = Path(__file__).with_name("run_afghanistan_filtered_prospective_2005.py")


def _load_runner():
    script_dir = str(RUNNER.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    return importlib.import_module(RUNNER.stem)


def _synthetic_observation(runner, state, end_day: float):
    world = state.world
    provinces = tuple(sorted({
        runner._province_for_locality(world, locality_id)
        for locality_id in world.localities
    }))
    return runner.ProvinceWeekObservation(
        start_day=0.0,
        end_day=float(end_day),
        week_index=0,
        active_provinces=frozenset(),
        provinces=provinces,
    )


def _run_one(runner, initial_states, observation, *, workers: int, branches: int,
             filter_seed: int) -> dict:
    states = [state.fork(90_000 + index) for index, state in enumerate(initial_states)]
    started = perf_counter()
    if workers == 1:
        startup_seconds = 0.0
        propagation_started = perf_counter()
        results = [
            runner._nested_particle_job((
                state,
                observation.end_day,
                observation,
                branches,
                filter_seed,
            ))
            for state in states
        ]
        propagation_seconds = perf_counter() - propagation_started
        snapshots = [state for state, _, _ in results]
        snapshot_seconds = 0.0
        scores = [score for _, score, _ in results]
    else:
        pool_started = perf_counter()
        pool = PersistentParticlePool(
            states,
            propagate=runner._nested_persistent_job,
            fork_state=runner._fork_particle_state,
            workers=workers,
        )
        startup_seconds = perf_counter() - pool_started
        try:
            propagation_started = perf_counter()
            compact = pool.propagate(
                observation.end_day,
                (observation, branches, filter_seed),
            )
            propagation_seconds = perf_counter() - propagation_started
            scores = [score for _, score, _ in compact]
            snapshot_started = perf_counter()
            snapshots = pool.snapshot()
            snapshot_seconds = perf_counter() - snapshot_started
        finally:
            pool.close()
    total_seconds = perf_counter() - started
    hashes = [decision_state_sha256(state.world) for state in snapshots]
    return {
        "workers": int(workers),
        "startup_seconds": startup_seconds,
        "propagation_seconds": propagation_seconds,
        "snapshot_seconds": snapshot_seconds,
        "total_seconds": total_seconds,
        "decision_state_sha256": hashes,
        "scores": scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--particles", type=int, default=4)
    parser.add_argument("--branches", type=int, default=1)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument(
        "--workers", type=int, nargs="+", default=(1, 2, 4, 6, 8, 10)
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.particles < 1 or args.branches < 1 or args.days <= 0:
        raise ValueError("particles/branches/days must be positive")

    runner = _load_runner()
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    base_world = runner.generate_pineland(
        runner._config(args.seed, max(60.0, args.days)),
        empirical_geography=case,
    )
    initial_states = [
        runner.build_initial_particle(
            seed=args.seed,
            particle_index=index,
            taliban_strength=runner.DEFAULT_STRENGTHS[
                index % len(runner.DEFAULT_STRENGTHS)
            ],
            prior_family=runner.PRIOR_FAMILY_STRATA[
                index % len(runner.PRIOR_FAMILY_STRATA)
            ],
            horizon=max(60.0, args.days),
            case=case,
            inputs=inputs,
            base_world=base_world,
        ).state
        for index in range(args.particles)
    ]
    observation = _synthetic_observation(runner, initial_states[0], args.days)
    rows = [
        _run_one(
            runner,
            initial_states,
            observation,
            workers=workers,
            branches=args.branches,
            filter_seed=args.seed + 17_003,
        )
        for workers in args.workers
        if workers >= 1
    ]
    reference = rows[0]
    for row in rows[1:]:
        row["exact_state_equivalence"] = (
            row["decision_state_sha256"] == reference["decision_state_sha256"]
        )
        row["exact_score_equivalence"] = row["scores"] == reference["scores"]
    reference["exact_state_equivalence"] = True
    reference["exact_score_equivalence"] = True
    best = min(rows, key=lambda row: row["propagation_seconds"])
    payload = {
        "schema_version": "pineland.performance.worker_scaling.v1",
        "scientific_status": "execution-only; synthetic observation surface",
        "runtime": runtime_manifest(),
        "seed": args.seed,
        "particles": args.particles,
        "branches": args.branches,
        "days": args.days,
        "results": rows,
        "best_workers_by_propagation": best["workers"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "best_workers_by_propagation": best["workers"],
        "all_exact": all(
            row["exact_state_equivalence"] and row["exact_score_equivalence"]
            for row in rows
        ),
    }))


if __name__ == "__main__":
    main()
