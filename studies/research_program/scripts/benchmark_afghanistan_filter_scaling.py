"""Synthetic-observation Afghanistan particle-filter scaling benchmark."""
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--particles", type=int, default=8)
    parser.add_argument("--weeks", type=int, default=8)
    parser.add_argument("--branches", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = importlib.import_module(
        "run_afghanistan_filtered_prospective_2005"
    )
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    horizon = max(60.0, 7.0 * args.weeks)
    base = runner.generate_pineland(
        runner._config(args.seed, horizon), empirical_geography=case
    )
    runner._precompute_province_lookup(base)
    particles = [
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
            base_world=base,
        )
        for index in range(args.particles)
    ]
    provinces = tuple(sorted(set(base.evaluation_region_by_locality.values())))
    observations = [
        runner.ProvinceWeekObservation(
            start_day=7.0 * week,
            end_day=7.0 * (week + 1),
            week_index=week,
            active_provinces=frozenset(),
            provinces=provinces,
        )
        for week in range(args.weeks)
    ]
    started = perf_counter()
    filter_ = runner.run_training_filter(
        particles,
        observations,
        filter_seed=args.seed + 17_003,
        likelihood_branches=args.branches,
        workers=args.workers,
        collect_worker_diagnostics=True,
    )
    elapsed = perf_counter() - started
    payload = {
        "schema_version": "pineland.performance.afghanistan_filter_scaling.v1",
        "scientific_status": "execution-only; synthetic all-inactive observations",
        "runtime": runtime_manifest(),
        "particles": args.particles,
        "weeks": args.weeks,
        "branches": args.branches,
        "workers": args.workers,
        "wall_seconds": elapsed,
        "updates": len(filter_.history),
        "nested_propagator_diagnostics": getattr(
            filter_, "nested_propagator_diagnostics", {}
        ),
        "worker_balance_history": getattr(
            filter_, "worker_balance_history", []
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "wall_seconds": elapsed,
    }))


if __name__ == "__main__":
    main()
