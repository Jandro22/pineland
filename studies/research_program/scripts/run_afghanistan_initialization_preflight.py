"""Run the bounded Afghanistan initialization gate against the live source.

This is a construct-level current-core impact preflight.  It conditions stocks
from the declared Afghanistan case inputs but does not simulate historical
outcomes, fit parameters, or bypass the transfer certificate gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
TRANSFER_DIR = ROOT / "studies" / "afghanistan_2004_2021" / "scripts"
if str(TRANSFER_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSFER_DIR))

from run_transfer_test import (  # noqa: E402
    CASE,
    CONTROL,
    CONTROL_OPERATOR,
    CONTROL_VALIDATION_PLAN,
    DESIGN,
    INPUTS_FILE,
    PANEL,
    build_conditioned_world,
    initialization_gate,
    sha256,
)
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402


def build(output: Path, *, seed: int = 20_040_101, strength: float = 7500.0) -> dict:
    before = repository_state(ROOT)
    source_hash = model_sha256(ROOT)
    world, inputs = build_conditioned_world(seed, 1.0, strength)
    gate = initialization_gate(world, inputs, strength)
    after = repository_state(ROOT)
    result = {
        "schema_version": "1.0.0",
        "status": "current_core_initialization_preflight_not_transfer",
        "study_id": "afghanistan_2004_2021",
        "seed": seed,
        "taliban_initial_strength": strength,
        "model_sha256": source_hash,
        "model_hash_stable_during_run": source_hash == model_sha256(ROOT),
        "repository_before": before,
        "repository_after": after,
        "repository_stable_during_run": (
            before["commit_hash"] == after["commit_hash"]
            and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        ),
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "initialization_gate": gate,
        "case_hashes": {
            path.relative_to(ROOT).as_posix(): sha256(path)
            for path in (CASE, INPUTS_FILE, CONTROL, PANEL, CONTROL_OPERATOR, CONTROL_VALIDATION_PLAN, DESIGN)
        },
        "interpretation": (
            "The initialization gate exercises current-core stock, geography, and supply invariants. "
            "It is not a historical transfer result and cannot certify the live core or license calibration."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "status": "current_core_initialization_preflight_manifest",
        "artifact": {"path": output.relative_to(ROOT).as_posix(), "sha256": file_sha256(output)},
        "builder": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Path(__file__)),
        },
        "model_sha256": source_hash,
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["manifest"] = manifest_path.relative_to(ROOT).as_posix()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies" / "research_program" / "afghanistan_initialization_preflight.json",
    )
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({
        "status": result["status"],
        "gate_passed": result["initialization_gate"]["passed"],
        "model_hash_stable_during_run": result["model_hash_stable_during_run"],
        "repository_stable_during_run": result["repository_stable_during_run"],
        "output": args.output.as_posix(),
    }, indent=2))
    return 0 if result["initialization_gate"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
