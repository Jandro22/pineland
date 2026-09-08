"""Assemble the Phase-A exactness/performance certificate without recertifying core."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    file_sha256,
    model_sha256,
    repository_state,
)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite certificate: {output}")
    program = ROOT / "studies/research_program"
    artifacts = {
        "A1_exactness": program / "phase_a_exactness_battery_v1.json",
        "A2_packed_authority": program / "phase_a_packed_state_authority_v1.json",
        "A3_kernel_oracles": program / "phase_a_kernel_oracles_v1.json",
        "A4_profile": program / "phase_a_execution_profile_v1.json",
        "B_inference": program / "phase_b_inference_validation_v2.json",
    }
    benchmark_path = program / "phase_a_fixed_work_benchmark_v1.json"
    loaded = {name: _load(path) for name, path in artifacts.items()}
    benchmark = _load(benchmark_path)
    checks = {
        "A1_exact_scheduler_oracle": bool(loaded["A1_exactness"]["passed"]),
        "A2_authority_inventory": bool(loaded["A2_packed_authority"]["passed"]),
        "A3_kernel_oracles": bool(loaded["A3_kernel_oracles"]["passed"]),
        "A4_profile_accounting": bool(loaded["A4_profile"]["passed"]),
        "A5_E1_minimum": bool(benchmark["results"]["E1_passed"]),
        "A5_E2_target": bool(benchmark["results"]["E2_passed"]),
        "A7_packed_filtering": bool(
            loaded["A1_exactness"].get("resampling", {}).get("passed", False)
            and benchmark["protocol"]["native_runner"]
        ),
        "B_synthetic_inference": bool(loaded["B_inference"]["passed"]),
    }
    phase_a_passed = all(checks[name] for name in (
        "A1_exact_scheduler_oracle",
        "A2_authority_inventory",
        "A3_kernel_oracles",
        "A4_profile_accounting",
        "A5_E1_minimum",
        "A7_packed_filtering",
    ))
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_certificate_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "phase_a_passed" if phase_a_passed else "phase_a_failed_closed",
        "checks": checks,
        "interpretation": {
            "E2_is_target_not_gate": True,
            "historical_tuning_used": False,
            "core_freeze_recertified": False,
            "negative_evidence_policy": "Any missing or failed component keeps the certificate failed_closed; no component is silently downgraded.",
        },
        "evidence": {
            name: {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(path),
                "passed": bool(loaded[name]["passed"]),
            }
            for name, path in artifacts.items()
        },
        "benchmark": {
            "path": str(benchmark_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": file_sha256(benchmark_path),
            "median_pwb_per_second": benchmark["results"]["median_pwb_per_second"],
            "E1_passed": benchmark["results"]["E1_passed"],
            "E2_passed": benchmark["results"]["E2_passed"],
        },
        "provenance": {
            "commit": repository_state(ROOT)["commit_hash"],
            "dirty_paths": repository_state(ROOT)["dirty_paths"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "model_sha256": model_sha256(ROOT),
            "certificate_payload_sha256": canonical_sha256(checks),
            "builder_sha256": file_sha256(Path(__file__)),
        },
        "passed": phase_a_passed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_certificate_v1.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
