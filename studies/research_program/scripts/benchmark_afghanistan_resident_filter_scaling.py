"""Measure resident-filter scaling at a meaningful synthetic workload.

The workload is deliberately outcome-free: it exercises repeated training
propagation, nested branches, resampling, and state growth on the historical
Afghanistan geography without reading or fitting to holdout outcomes.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))

from pineland_sim.performance import runtime_manifest
from pineland_sim.reproducibility import decision_state_sha256
from pineland_sim.state_estimation import particle_weights


def _load_runner():
    return importlib.import_module("run_afghanistan_filtered_prospective_2005")


def _observations(runner, world, weeks: int):
    provinces = tuple(sorted(set(world.evaluation_region_by_locality.values())))
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


def _run_one(
    runner,
    templates,
    observations,
    *,
    workers: int,
    branches: int,
    seed: int,
    release_templates: bool = False,
):
    particles = [
        runner.Particle(
            template.state.fork(900_000 + index),
            template.log_weight,
        )
        for index, template in enumerate(templates)
    ]
    if release_templates:
        templates.clear()
    started = perf_counter()
    filter_ = runner.run_training_filter(
        particles,
        observations,
        filter_seed=seed + 17_003,
        likelihood_branches=branches,
        workers=workers,
        collect_worker_diagnostics=True,
    )
    wall_seconds = perf_counter() - started
    return {
        "workers": workers,
        "wall_seconds": wall_seconds,
        "updates": len(filter_.history),
        "weights": particle_weights(filter_.particles),
        "decision_state_sha256": [
            decision_state_sha256(particle.state.world)
            for particle in filter_.particles
        ],
        "nested_propagator_diagnostics": getattr(
            filter_, "nested_propagator_diagnostics", {}
        ),
        "worker_balance_history": getattr(
            filter_, "worker_balance_history", []
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--particles", type=int, default=32)
    parser.add_argument("--weeks", type=int, default=8)
    parser.add_argument("--branches", type=int, default=3)
    parser.add_argument("--workers", type=int, nargs="+", default=(8, 12, 16))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.particles < 2 or args.weeks < 1 or args.branches < 1:
        raise ValueError("particles/weeks/branches must be valid positive values")
    if any(worker < 1 for worker in args.workers):
        raise ValueError("workers must be positive")

    runner = _load_runner()
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    horizon = max(60.0, 7.0 * args.weeks)
    base_world = runner.generate_pineland(
        runner._config(args.seed, horizon), empirical_geography=case
    )
    runner._precompute_province_lookup(base_world)
    templates = [
        runner.build_initial_particle(
            seed=args.seed,
            particle_index=index,
            taliban_strength=runner.DEFAULT_STRENGTHS[
                index % len(runner.DEFAULT_STRENGTHS)
            ],
            prior_family=runner.PRIOR_FAMILY_STRATA[
                index % len(runner.PRIOR_FAMILY_STRATA)
            ],
            horizon=horizon,
            case=case,
            inputs=inputs,
            base_world=base_world,
        )
        for index in range(args.particles)
    ]
    observations = _observations(runner, base_world, args.weeks)
    rows = []
    for worker_index, workers in enumerate(args.workers):
        rows.append(_run_one(
            runner,
            templates,
            observations,
            workers=workers,
            branches=args.branches,
            seed=args.seed,
            release_templates=(worker_index == len(args.workers) - 1),
        ))
    reference = rows[0]
    for row in rows:
        row["exact_state_equivalence"] = (
            row["decision_state_sha256"] == reference["decision_state_sha256"]
        )
        row["exact_weight_equivalence"] = row["weights"] == reference["weights"]
    best = min(rows, key=lambda row: row["wall_seconds"])
    payload = {
        "schema_version": "pineland.performance.afghanistan_resident_filter_scaling.v1",
        "scientific_status": "execution-only; synthetic all-inactive observations",
        "runtime": runtime_manifest(),
        "seed": args.seed,
        "particles": args.particles,
        "weeks": args.weeks,
        "branches": args.branches,
        "results": rows,
        "best_workers": best["workers"],
        "all_exact": all(
            row["exact_state_equivalence"] and row["exact_weight_equivalence"]
            for row in rows
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "best_workers": payload["best_workers"],
        "all_exact": payload["all_exact"],
    }))


if __name__ == "__main__":
    main()
