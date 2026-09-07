"""Benchmark forecast output equivalence without returning full particle states."""
from __future__ import annotations

import importlib
import json
import math
from pathlib import Path
import random
import sys
from time import perf_counter
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPTS))


def main() -> None:
    runner = importlib.import_module(
        "run_afghanistan_filtered_prospective_2005"
    )
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    base = runner.generate_pineland(
        runner._config(20050111, 30.0),
        empirical_geography=case,
    )
    runner._precompute_province_lookup(base)
    states = [
        runner.build_initial_particle(
            seed=20050111,
            particle_index=index,
            taliban_strength=(5000.0, 7500.0)[index],
            horizon=30.0,
            case=case,
            inputs=inputs,
            base_world=base,
        ).state
        for index in range(2)
    ]

    def make_filter():
        return runner.SequentialParticleFilter(
            [
                runner.Particle(state, math.log(0.5))
                for state in states
            ],
            transition=lambda state, time: None,
            log_likelihood=lambda state, observation: 0.0,
            rng=random.Random(1),
            allowed_split="training",
        )

    sequential_filter = make_filter()
    started = perf_counter()
    sequential = runner.forecast_weighted_field(
        sequential_filter,
        start_day=0.0,
        end_day=7.0,
        forecast_branches=1,
        workers=1,
    )
    sequential_seconds = perf_counter() - started

    parallel_filter = make_filter()
    with patch.object(
        runner.PersistentParticlePool,
        "snapshot",
        side_effect=AssertionError("forecast snapshot is forbidden"),
    ):
        started = perf_counter()
        parallel = runner.forecast_weighted_field(
            parallel_filter,
            start_day=0.0,
            end_day=7.0,
            forecast_branches=1,
            workers=2,
        )
        parallel_seconds = perf_counter() - started

    payload = {
        "schema_version": "pineland.performance.forecast_ipc.v1",
        "scientific_status": "execution-only",
        "exact_output_equivalence": sequential == parallel,
        "sequential_seconds": sequential_seconds,
        "parallel_seconds": parallel_seconds,
        "posterior_summary_count": len(
            parallel["posterior_particle_summaries"]
        ),
        "full_state_snapshot_used": False,
    }
    output = (
        ROOT
        / "studies"
        / "research_program"
        / "afghanistan_performance"
        / "forecast_ipc_no_snapshot.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(0 if payload["exact_output_equivalence"] else 1)


if __name__ == "__main__":
    main()
