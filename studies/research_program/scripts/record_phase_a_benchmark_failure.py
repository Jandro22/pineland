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
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    payload = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_fixed_work_benchmark_failure_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "incomplete_resource_limit",
        "protocol": {
            "particles": 32,
            "weekly_boundaries": 8,
            "branch_equivalents": 3,
            "pwb": 768,
            "engine": "resident_filter_transport",
            "workers": 16,
            "synthetic_observations": "all-inactive; no historical outcome values read or fitted",
        },
        "observed": {
            "complete_ensemble": False,
            "complete_timing": False,
            "partial_results_reported": False,
            "termination": "controlled stop after working set exceeded approximately 20 GB without completing the fixed ensemble",
            "resource_window": "approximately 20 GB working set; child workers confirmed terminated",
        },
        "interpretation": "No PWB/s value is reported. E1 and E2 remain failed_closed pending a complete repeat.",
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "dirty_paths": repository_state(ROOT)["dirty_paths"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "python": platform.python_version(),
            "record_script_sha256": file_sha256(Path(__file__)),
            "protocol_sha256": canonical_sha256({"particles": 32, "weekly_boundaries": 8, "branch_equivalents": 3, "workers": 16}),
        },
        "passed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": False}))


if __name__ == "__main__":
    main()
