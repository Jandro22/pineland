"""Exact benchmark for consuming the final nested branch in place."""
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

from pineland_sim.reproducibility import simulation_execution_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--branches", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = importlib.import_module(
        "run_afghanistan_filtered_prospective_2005"
    )
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    horizon = max(60.0, args.weeks * 7.0)
    base = runner.generate_pineland(
        runner._config(args.seed, horizon), empirical_geography=case
    )
    runner._precompute_province_lookup(base)

    def make_state():
        return runner.build_initial_particle(
            seed=args.seed,
            particle_index=0,
            taliban_strength=runner.DEFAULT_STRENGTHS[0],
            prior_family=runner.PRIOR_FAMILY_STRATA[0],
            horizon=horizon,
            case=case,
            inputs=inputs,
            base_world=base,
        ).state

    reference_state = make_state()
    optimized_state = make_state()
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

    def execute(state, consume: bool):
        scores = []
        started = perf_counter()
        for observation in observations:
            propagator = runner.NestedOperationalPropagator(
                branches=args.branches,
                selection_seed=args.seed + 17_003,
                consume_parent_branch=consume,
            )
            state, score = propagator(
                state, observation.end_day, observation
            )
            scores.append(score)
        return state, scores, perf_counter() - started

    reference_state, reference_scores, reference_seconds = execute(
        reference_state, False
    )
    optimized_state, optimized_scores, optimized_seconds = execute(
        optimized_state, True
    )
    reference_hash = simulation_execution_sha256(
        reference_state.simulation,
        lineage_id=reference_state.lineage_id,
    )
    optimized_hash = simulation_execution_sha256(
        optimized_state.simulation,
        lineage_id=optimized_state.lineage_id,
    )
    payload = {
        "schema_version": "pineland.performance.nested_clone_reduction.v1",
        "scientific_status": "execution-only; synthetic observation surface",
        "weeks": args.weeks,
        "branches": args.branches,
        "reference_seconds": reference_seconds,
        "optimized_seconds": optimized_seconds,
        "speedup": reference_seconds / optimized_seconds,
        "exact_scores": reference_scores == optimized_scores,
        "exact_execution_state": reference_hash == optimized_hash,
        "reference_hash": reference_hash,
        "optimized_hash": optimized_hash,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload))
    raise SystemExit(
        0 if payload["exact_scores"] and payload["exact_execution_state"] else 1
    )


if __name__ == "__main__":
    main()
