"""Record a controlled incomplete fixed-work benchmark without inventing timing."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import canonical_sha256, file_sha256, model_sha256, repository_state  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/phase_a_fixed_work_benchmark_failure_v1.json")
    parser.add_argument("--study-id", default="phase_a_fixed_work_benchmark_failure_v1")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--unbalanced-resampling", action="store_true")
    parser.add_argument(
        "--termination",
        default="controlled stop after the complete fixed ensemble failed to produce a finished artifact",
    )
    parser.add_argument(
        "--resource-window",
        default="resident workers remained memory-heavy and execution was load-imbalanced; no partial timing accepted",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    payload = {
        "schema_version": "1.0.0",
        "study_id": args.study_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "incomplete_resource_limit",
        "protocol": {
            "particles": 32,
            "weekly_boundaries": 8,
            "branch_equivalents": 3,
            "pwb": 768,
            "engine": "resident_filter_transport",
            "workers": args.workers,
            "balance_resampling": not args.unbalanced_resampling,
            "synthetic_observations": "all-inactive; no historical outcome values read or fitted",
        },
        "observed": {
            "complete_ensemble": False,
            "complete_timing": False,
            "partial_results_reported": False,
            "termination": args.termination,
            "resource_window": args.resource_window,
        },
        "interpretation": "No PWB/s value is reported. E1 and E2 remain failed_closed pending a complete repeat.",
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "dirty_paths": repository_state(ROOT)["dirty_paths"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "python": platform.python_version(),
            "record_script_sha256": file_sha256(Path(__file__)),
            "protocol_sha256": canonical_sha256({
                "particles": 32,
                "weekly_boundaries": 8,
                "branch_equivalents": 3,
                "workers": args.workers,
                "balance_resampling": not args.unbalanced_resampling,
            }),
        },
        "passed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": False}))


if __name__ == "__main__":
    main()
