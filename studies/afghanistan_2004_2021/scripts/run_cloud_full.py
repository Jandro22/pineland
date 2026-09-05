"""Run the three frozen Afghanistan full-horizon trajectories concurrently.

Each strength writes atomically as soon as it completes, so a VM interruption
cannot turn a partial trajectory into a result and completed strengths survive
for later download or resumption.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from run_transfer_test import DEFAULT_SEED, OUT, atomic_json, run_case, sha256, stage_spec


def _run(strength: float, seed: int, horizon: float) -> tuple[float, dict]:
    result = run_case(seed, horizon, strength)
    result["stage"] = "full"
    return strength, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--strengths", type=float, nargs="*", default=[5000.0, 7500.0, 10000.0])
    parser.add_argument(
        "--horizon-days", type=float,
        help="Optional staged horizon override; use for cheap transfer ensembles before the full 2004-2021 run.",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        help="Optional result directory; defaults to runs/transfer_test_v1/full.",
    )
    args = parser.parse_args()
    horizon = float(args.horizon_days) if args.horizon_days is not None else stage_spec("full")[0]
    stage_dir = args.output_dir or (OUT / "full")
    stage_dir.mkdir(parents=True, exist_ok=True)
    files = {
        strength: stage_dir / f"seed_{args.seed}_taliban_{int(strength)}.json"
        for strength in args.strengths
    }
    pending = [strength for strength, path in files.items() if not path.exists()]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=min(args.workers, len(pending) or 1)) as executor:
        futures = {
            executor.submit(_run, strength, args.seed, horizon): strength
            for strength in pending
        }
        for future in as_completed(futures):
            strength, payload = future.result()
            atomic_json(files[strength], payload)
            print(json.dumps({
                "completed_strength": strength,
                "passed": payload["gate"]["passed"],
                "runtime_seconds": payload["runtime_seconds"],
                "latent_contacts": payload["violence_validation"]["latent_contacts"],
                "recorded_contacts": payload["violence_validation"]["recorded_contacts"],
            }), flush=True)

    results = [json.loads(files[strength].read_text(encoding="utf-8")) for strength in args.strengths]
    manifest = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "formulation": "sourced_transfer_test_v1",
        "stage": "full" if args.horizon_days is None else "staged_custom_horizon",
        "parameter_fit": False,
        "horizon_days": horizon,
        "seed": args.seed,
        "strengths": args.strengths,
        "parallel_workers": min(args.workers, len(args.strengths)),
        "all_gates_passed": all(result["gate"]["passed"] for result in results),
        "wall_seconds_this_invocation": time.perf_counter() - started,
        "files": [
            {"path": files[strength].name, "sha256": sha256(files[strength])}
            for strength in args.strengths
        ],
        "case_hashes": results[0]["case_hashes"],
        "model_sha256": results[0].get("model_sha256_end"),
        "tracked_diff_sha256": results[0].get("tracked_diff_sha256"),
        "model_stable_during_runs": all(result.get("model_stable_during_run") for result in results),
    }
    atomic_json(stage_dir / "manifest.json", manifest)
    print(json.dumps(manifest), flush=True)
    return 0 if manifest["all_gates_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
