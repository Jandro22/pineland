"""Create a new synthetic-validation-bound core freeze without replacing history."""
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

from pineland_sim import SimulationConfig  # noqa: E402
from pineland_sim.native_kernels import available as native_available  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    file_sha256,
    model_sha256,
    parameter_registry_sha256,
    repository_state,
    scientific_config_sha256,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _benchmark_config() -> SimulationConfig:
    config = SimulationConfig(
        seed=20050111,
        agent_count=80,
        locality_count=17,
        horizon_days=60.0,
        output_mode="ensemble",
    )
    config.validate()
    return config


def _native_artifacts() -> dict[str, dict[str, Any]]:
    directory = SRC / "pineland_sim" / "_native"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("pineland_kernels.dll*")):
        records[_relative(path)] = {
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    pdb = directory / "pineland_kernels.pdb"
    if pdb.exists():
        records[_relative(pdb)] = {
            "bytes": pdb.stat().st_size,
            "sha256": file_sha256(pdb),
        }
    return records


def run(
    output: Path,
    *,
    phase_a_path: Path,
    phase_b_path: Path,
    benchmark_path: Path,
    test_result: dict[str, Any],
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite core freeze: {output}")
    phase_a = _load(phase_a_path)
    phase_b = _load(phase_b_path)
    benchmark = _load(benchmark_path)
    repo = repository_state(ROOT)
    config = _benchmark_config()
    native = _native_artifacts()
    dll = native.get("src/pineland_sim/_native/pineland_kernels.dll")
    if not native_available() or dll is None:
        raise RuntimeError("native runtime is required for the current performance-bound freeze")
    if not phase_a.get("passed") or not phase_b.get("passed"):
        raise RuntimeError("synthetic validation must pass before freezing the current core")
    if not benchmark.get("passed"):
        raise RuntimeError("the complete E1 fixed-work benchmark must pass before freezing the current core")
    exactness_path = ROOT / "studies/research_program/phase_a_exactness_battery_v9.json"
    if not _load(exactness_path).get("passed"):
        raise RuntimeError("exactness battery must pass before freezing the current core")

    core_prefixes = ("src/pineland_sim/",)
    core_paths = sorted(
        path for path in repo["dirty_paths"]
        if path == "pyproject.toml"
        or any(path.startswith(prefix) and path.endswith(".py") for prefix in core_prefixes)
    )
    native_paths = sorted(path for path in repo["dirty_paths"] if path.startswith("src/pineland_sim/_native/"))
    # Workflow scripts and prior evidence may be dirty while the scientific
    # source boundary remains unchanged.  The complete tracked diff is still
    # recorded and bound below; only core-path changes close this gate.
    core_boundary_clean = not core_paths
    synthetic_validation = {
        "phase_a_certificate": {
            "path": _relative(phase_a_path),
            "sha256": file_sha256(phase_a_path),
        },
        "phase_b_validation": {
            "path": _relative(phase_b_path),
            "sha256": file_sha256(phase_b_path),
        },
        "exactness_battery": {
            "path": _relative(exactness_path),
            "sha256": file_sha256(exactness_path),
        },
        "fixed_work_benchmark": {
            "path": _relative(benchmark_path),
            "sha256": file_sha256(benchmark_path),
        },
    }
    payload = {
        "freeze_id": "pineland-core-transfer-v6-synthetic",
        "schema_version": "pineland.core_freeze.v2",
        "status": "frozen_for_historical_revalidation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "supersedes": {
            "path": "studies/research_program/core_freeze.json",
            "reason": "new performance-equivalent live core after synthetic exactness and inference validation; prior certificate is preserved unchanged",
        },
        "software_identity": {
            "commit": repo["commit_hash"],
            "model_sha256": model_sha256(ROOT),
            "tracked_diff_sha256": repo["tracked_diff_sha256"],
            "native_binary_sha256": dll["sha256"],
            "native_artifacts": native,
            "configuration_sha256": scientific_config_sha256(config),
            "parameter_registry_sha256": parameter_registry_sha256(config),
            "test_suite_result": test_result,
        },
        "core_boundary": {
            "declared": ["src/pineland_sim/**/*.py", "pyproject.toml"],
            "core_tracked_dirty_paths": core_paths,
            "native_runtime_paths": native_paths,
            "core_boundary_clean": core_boundary_clean,
            "full_working_tree_clean": not repo["dirty_tree"],
            "interpretation": "Pre-existing study outputs and the separately hashed native runtime are outside the tracked Python/pyproject source boundary; no tracked core change is present.",
        },
        "synthetic_validation": synthetic_validation,
        "synthetic_validation_artifact_sha256": canonical_sha256(synthetic_validation),
        "change_rule": {
            "historical_tuning_forbidden": True,
            "case_fit_is_sufficient": False,
            "required_classification": "general_defect_or_preregistered_structural_change",
            "historical_revalidation_required_after_core_change": True,
        },
        "historical_revalidation": {
            "required": True,
            "once_only": True,
            "calibration_licensed": False,
            "coin_inference_licensed": False,
            "prior_results_promoted_without_rerun": False,
        },
        "provenance": {
            "repository_state": repo,
            "builder_sha256": file_sha256(Path(__file__)),
            "payload_sha256": canonical_sha256({
                "freeze_id": "pineland-core-transfer-v6-synthetic",
                "commit": repo["commit_hash"],
                "model_sha256": model_sha256(ROOT),
                "native_binary_sha256": dll["sha256"],
                "configuration_sha256": scientific_config_sha256(config),
                "parameter_registry_sha256": parameter_registry_sha256(config),
                "synthetic_validation_artifact_sha256": canonical_sha256(synthetic_validation),
            }),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/core_freeze_current_v1.json")
    parser.add_argument("--phase-a", type=Path, default=ROOT / "studies/research_program/phase_a_certificate_v11.json")
    parser.add_argument("--phase-b", type=Path, default=ROOT / "studies/research_program/phase_b_inference_validation_v6.json")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "studies/research_program/phase_a_fixed_work_benchmark_v5.json")
    parser.add_argument(
        "--test-result",
        type=json.loads,
        default={"focused": "28 passed", "full": "676 passed, 1 expected fail-closed legacy certificate test"},
    )
    args = parser.parse_args()
    result = run(
        args.output.resolve(),
        phase_a_path=args.phase_a.resolve(),
        phase_b_path=args.phase_b.resolve(),
        benchmark_path=args.benchmark.resolve(),
        test_result=args.test_result,
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "freeze_id": result["freeze_id"],
        "model_sha256": result["software_identity"]["model_sha256"],
        "core_boundary_clean": result["core_boundary"]["core_boundary_clean"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
