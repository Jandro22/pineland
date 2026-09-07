"""Run the standard Pineland execution-only performance suite.

Defaults are intentionally bounded.  Pass --full to include the expensive
one-year and 52-week growth probes.  No historical forecast outcome is read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter


HERE = Path(__file__).resolve().parent


def _run(script: str, arguments: list[str]) -> dict:
    command = [sys.executable, str(HERE / script), *arguments]
    started = perf_counter()
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "script": script,
        "command": command,
        "wall_seconds": perf_counter() - started,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, list[str]]] = [
        (
            "profile_afghanistan_execution.py",
            [
                "--days", "30",
                "--forks", "8",
                "--output", str(args.output_dir / "afghanistan_30d.json"),
            ],
        ),
        (
            "benchmark_afghanistan_worker_scaling.py",
            [
                "--particles", "8",
                "--branches", "1",
                "--days", "1",
                "--workers", "1", "2", "4", "6", "8", "10",
                "--output", str(args.output_dir / "worker_scaling.json"),
            ],
        ),
        (
            "benchmark_afghanistan_particle_growth.py",
            [
                "--weeks", "0", "13",
                "--output", str(args.output_dir / "particle_growth.json"),
            ],
        ),
    ]
    if args.full:
        jobs.extend([
            (
                "profile_afghanistan_execution.py",
                [
                    "--days", "365",
                    "--forks", "8",
                    "--output", str(args.output_dir / "afghanistan_365d.json"),
                ],
            ),
            (
                "benchmark_afghanistan_particle_growth.py",
                [
                    "--weeks", "0", "13", "26", "39", "52",
                    "--output", str(args.output_dir / "particle_growth_52w.json"),
                ],
            ),
        ])

    results = []
    for script, arguments in jobs:
        result = _run(script, arguments)
        results.append(result)
        if result["returncode"] != 0:
            break
    payload = {
        "schema_version": "pineland.performance.standard_suite.v1",
        "scientific_status": "execution-only",
        "full": args.full,
        "runs": results,
        "passed": all(item["returncode"] == 0 for item in results),
    }
    manifest = args.output_dir / "suite_manifest.json"
    manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "manifest": str(manifest),
        "passed": payload["passed"],
        "completed_runs": len(results),
    }))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
