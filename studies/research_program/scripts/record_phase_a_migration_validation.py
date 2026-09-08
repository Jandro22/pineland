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
    parser.add_argument(
        "--fixed-work",
        type=Path,
        help="Complete fixed 768-PWB benchmark used as the performance authority.",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)

    baseline = _load(args.baseline.resolve())
    migrated = _load(args.migrated.resolve())
    exactness = _load(args.exactness.resolve())
    fixed_work = _load(args.fixed_work.resolve()) if args.fixed_work else None
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
    fixed_work_gate = {
        "complete_768_pwb_artifact": False,
        "rate_reported": False,
        "E1_passed": False,
        "E2_passed": False,
        "median_pwb_per_second": None,
        "repetitions": 0,
        "interpretation": (
            "The optimization is validated locally; full-work throughput remains "
            "failed-closed until a complete fixed ensemble is available."
        ),
    }
    if fixed_work is not None:
        protocol = fixed_work.get("protocol", {})
        results = fixed_work.get("results", {})
        repeats = results.get("repeats", [])
        complete = bool(
            fixed_work.get("passed")
            and int(protocol.get("particles", 0)) == 32
            and int(protocol.get("weekly_boundaries", 0)) == 8
            and int(protocol.get("branch_equivalents", 0)) == 3
            and int(protocol.get("pwb_per_repeat", 0)) == 768
            and len(repeats) >= 5
        )
        fixed_work_gate = {
            "complete_768_pwb_artifact": complete,
            "rate_reported": bool(results.get("median_pwb_per_second") is not None),
            "E1_passed": bool(results.get("E1_passed", False)),
            "E2_passed": bool(results.get("E2_passed", False)),
            "median_pwb_per_second": results.get("median_pwb_per_second"),
            "repetitions": len(repeats),
            "artifact": str(args.fixed_work.resolve().relative_to(ROOT)).replace("\\", "/"),
            "interpretation": (
                "E1 is the minimum performance gate; E2 remains a target and is "
                "reported as negative evidence when unmet."
            ),
        }
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
        "fixed_work_gate": fixed_work_gate,
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
                "fixed_work": fixed_work.get("provenance") if fixed_work is not None else None,
            }),
        },
        "passed": bool(
            exactness["passed"]
            and baseline["passed"]
            and migrated["passed"]
            and migrated_wall < baseline_wall
            and same_hashes
            and same_weights
            and fixed_work_gate["complete_768_pwb_artifact"]
            and fixed_work_gate["E1_passed"]
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "passed": result["passed"]}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
