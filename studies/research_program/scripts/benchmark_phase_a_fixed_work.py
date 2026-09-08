"""Run the preregistered fixed Phase-A packed-work benchmark.

The unit is a particle-week-boundary (PWB): one particle advanced through one
weekly boundary.  The acceptance workload is fixed at 32 particles, 8 weekly
boundaries, and 3 independent branch-equivalents, i.e. 768 PWB per measured
repeat.  This script does not change model parameters and refuses to overwrite
an existing artifact.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import SimulationConfig  # noqa: E402
from pineland_sim.native_kernels import available as native_available  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    file_sha256,
    model_sha256,
    repository_state,
    scientific_config_sha256,
)


PARTICLES = 32
WEEKLY_BOUNDARIES = 8
BRANCH_EQUIVALENTS = 3
HORIZON_DAYS = 7.0 * WEEKLY_BOUNDARIES
BASE_SEED = 20050111
WORKERS = 16
BALANCE_RESAMPLING = False
PWB_PER_REPEAT = PARTICLES * WEEKLY_BOUNDARIES * BRANCH_EQUIVALENTS


def _run_repeat(repeat_index: int, *, workers: int) -> dict[str, Any]:
    runner_script = ROOT / "studies/research_program/scripts/benchmark_phase_a_fixed_workload.py"
    with tempfile.TemporaryDirectory(prefix="pineland_phase_a_fixed_work_") as temp_dir:
        raw_output = Path(temp_dir) / f"repeat_{repeat_index}.json"
        command = [
            sys.executable,
            str(runner_script),
            "--seed", str(BASE_SEED + repeat_index),
            "--workers", str(workers),
            "--output", str(raw_output),
        ]
        started = time.perf_counter()
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        subprocess_wall = time.perf_counter() - started
        if completed.returncode != 0:
            raise RuntimeError(
                "fixed production benchmark failed:\n"
                + completed.stdout[-4000:]
                + completed.stderr[-4000:]
            )
        payload = json.loads(raw_output.read_text(encoding="utf-8"))
    row = payload["result"]
    if row["workers"] != workers:
        raise RuntimeError(f"expected a {workers}-worker result, got {row['workers']}")
    wall_seconds = float(row["wall_seconds"])
    return {
        "repeat": repeat_index,
        "particles": PARTICLES,
        "weekly_boundaries": WEEKLY_BOUNDARIES,
        "branch_equivalents": BRANCH_EQUIVALENTS,
        "pwb": PWB_PER_REPEAT,
        "wall_seconds": wall_seconds,
        "pwb_per_second": PWB_PER_REPEAT / wall_seconds,
        "subprocess_wall_seconds": subprocess_wall,
        "workers": workers,
        "engine": "packed_nested_resident_filter",
        "source_payload": payload,
    }


def run(*, output: Path, repetitions: int, workers: int = WORKERS) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing benchmark evidence: {output}")
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    if workers < 1 or workers > PARTICLES:
        raise ValueError("workers must lie in [1, particles]")
    config = SimulationConfig(
        seed=BASE_SEED,
        agent_count=80,
        locality_count=17,
        horizon_days=max(60.0, HORIZON_DAYS),
        output_mode="ensemble",
    )
    repeats = [
        _run_repeat(index, workers=workers) for index in range(repetitions)
    ]
    rates = [item["pwb_per_second"] for item in repeats]
    median_rate = statistics.median(rates)
    return {
        "schema_version": "1.0.0",
        "study_id": "phase_a_fixed_work_benchmark_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "particles": PARTICLES,
            "weekly_boundaries": WEEKLY_BOUNDARIES,
            "branch_equivalents": BRANCH_EQUIVALENTS,
            "pwb_per_repeat": PWB_PER_REPEAT,
            "repetitions": repetitions,
            "horizon_days": HORIZON_DAYS,
            "engine": "packed_nested_resident_filter",
            "workers": workers,
            "balance_resampling": BALANCE_RESAMPLING,
            "synthetic_observations": "all-inactive; no historical outcome values are read or fitted",
            "likelihood_branches": BRANCH_EQUIVALENTS,
            "historical_geography_for_execution": False,
            "acceptance": {
                "E1_pwb_per_second_minimum": 4.0,
                "E2_pwb_per_second_target": 10.0,
                "E1_passed": median_rate >= 4.0,
                "E2_passed": median_rate >= 10.0,
            },
        },
        "results": {
            "repeats": repeats,
            "median_pwb_per_second": median_rate,
            "min_pwb_per_second": min(rates),
            "max_pwb_per_second": max(rates),
            "E1_passed": median_rate >= 4.0,
            "E2_passed": median_rate >= 10.0,
            "passed": median_rate >= 4.0,
        },
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "dirty_paths": repository_state(ROOT)["dirty_paths"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "configuration_sha256": scientific_config_sha256(config),
            "python": platform.python_version(),
            "native_kernels_available": native_available(),
            "script_sha256": file_sha256(Path(__file__)),
            "benchmark_payload_sha256": canonical_sha256({
                "particles": PARTICLES,
                "weekly_boundaries": WEEKLY_BOUNDARIES,
                "branch_equivalents": BRANCH_EQUIVALENTS,
                "base_seed": BASE_SEED,
                "workers": workers,
                "balance_resampling": BALANCE_RESAMPLING,
                "horizon_days": HORIZON_DAYS,
            }),
        },
        "passed": median_rate >= 4.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_fixed_work_benchmark_v1.json",
    )
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    result = run(
        output=args.output.resolve(),
        repetitions=args.repetitions,
        workers=args.workers,
    )
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "median_pwb_per_second": result["results"]["median_pwb_per_second"],
        "E1_passed": result["results"]["E1_passed"],
        "E2_passed": result["results"]["E2_passed"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
