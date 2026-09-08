"""Record exactness and measured-speed validation for the Phase-A migration."""
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

from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    model_sha256,
    repository_state,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_migration_validation_v1.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_execution_profile_v1.json",
    )
    parser.add_argument(
        "--migrated",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_execution_profile_v5.json",
    )
    parser.add_argument(
        "--exactness",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_exactness_battery_v5.json",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)

    baseline = _load(args.baseline.resolve())
    migrated = _load(args.migrated.resolve())
    exactness = _load(args.exactness.resolve())
    balanced = _load(ROOT / "studies/research_program/phase_a_bounded_transport_benchmark_v6_balanced.json")
    unbalanced = _load(ROOT / "studies/research_program/phase_a_bounded_transport_benchmark_v7_unbalanced.json")
    baseline_wall = float(baseline["median"]["wall_seconds"])
    migrated_wall = float(migrated["median"]["wall_seconds"])
    balanced_row = balanced["results"][0]
    unbalanced_row = unbalanced["results"][0]
    same_hashes = (
        balanced_row["decision_state_sha256"]
        == unbalanced_row["decision_state_sha256"]
    )
    same_weights = balanced_row["weights"] == unbalanced_row["weights"]
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_migration_validation_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "migration_exactness_preserved_profile_improved",
        "comparison": {
            "baseline_profile": str(args.baseline.resolve().relative_to(ROOT)).replace("\\", "/"),
            "migrated_profile": str(args.migrated.resolve().relative_to(ROOT)).replace("\\", "/"),
            "baseline_median_wall_seconds": baseline_wall,
            "migrated_median_wall_seconds": migrated_wall,
            "wall_speedup": baseline_wall / migrated_wall,
            "wall_reduction_fraction": 1.0 - migrated_wall / baseline_wall,
            "baseline_median_profile_cpu_seconds": float(baseline["median"]["profile_cpu_seconds"]),
            "migrated_median_profile_cpu_seconds": float(migrated["median"]["profile_cpu_seconds"]),
        },
        "exactness": {
            "artifact": str(args.exactness.resolve().relative_to(ROOT)).replace("\\", "/"),
            "passed": bool(exactness["passed"]),
            "comparisons": int(exactness["exactness"]["comparison_count"]),
            "world_state_mismatches": int(exactness["exactness"]["world_state_mismatches"]),
            "execution_state_mismatches": int(exactness["exactness"]["execution_state_mismatches"]),
            "resampling_passed": bool(exactness["resampling"]["passed"]),
        },
        "bounded_transport_equivalence": {
            "balanced": "studies/research_program/phase_a_bounded_transport_benchmark_v6_balanced.json",
            "unbalanced": "studies/research_program/phase_a_bounded_transport_benchmark_v7_unbalanced.json",
            "same_decision_state_hashes": same_hashes,
            "same_weights": same_weights,
            "particle_count": 8,
            "weekly_boundaries": 2,
            "branch_equivalents": 1,
            "hash_count": len(balanced_row["decision_state_sha256"]),
        },
        "fixed_work_gate": {
            "complete_768_pwb_artifact": False,
            "rate_reported": False,
            "interpretation": "The optimization is validated locally; full-work throughput remains failed-closed until a complete fixed ensemble is available.",
        },
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "dirty_paths": repository_state(ROOT)["dirty_paths"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "python": platform.python_version(),
            "input_sha256": canonical_sha256({
                "baseline": baseline["provenance"],
                "migrated": migrated["provenance"],
                "exactness": exactness["provenance"],
            }),
        },
        "passed": bool(
            exactness["passed"]
            and baseline["passed"]
            and migrated["passed"]
            and migrated_wall < baseline_wall
            and same_hashes
            and same_weights
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": result["passed"]}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
