"""Prospective synthetic repair test for the v1 contact-challenge routing defect.

This script does not edit the live simulator or historical inputs.  It imports the
existing study-layer factorial adapter and changes only the component-test config
object so contact_scan explicitly exercises the legacy contact scheduler.  The
production v5 architecture remains multichannel_v5.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "studies" / "research_program" / "scripts"
SRC = ROOT / "src"
for path in (SCRIPTS, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_spatial_factorial_pilot as base  # noqa: E402
from pineland_sim import SimulationConfig as LiveSimulationConfig  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    certified_core_status,
    file_sha256,
    model_sha256,
    repository_state,
)


CONTRACT = ROOT / "studies" / "research_program" / "spatial_contact_routing_repair_contract_v2.json"


def component_test_config(*args, **kwargs):
    config = LiveSimulationConfig(*args, **kwargs)
    config.combat.organized_action_architecture = "legacy_contact_only"
    return config


def run(*, full: bool, seed: int | None = None) -> dict:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    base.validate_contract(contract)
    if full:
        certificate = certified_core_status(ROOT)
        if not certificate["passed"]:
            raise RuntimeError(f"active core certificate failed: {certificate}")

    design = contract["design"]
    seeds = [int(value) for value in design["seeds"]] if full else [int(seed or design["seeds"][0])]
    cells = [
        (memory, destination)
        for memory in design["factors"]["presence_memory"]
        for destination in design["factors"]["destination_choice"]
    ]

    repository_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    original_config = base.SimulationConfig
    base.SimulationConfig = component_test_config
    results = []
    try:
        for run_seed in seeds:
            for memory, destination in cells:
                results.append(base.run_cell(
                    contract=contract,
                    seed=run_seed,
                    presence_memory=memory,
                    destination_choice=destination,
                    horizon_days=float(design["horizon_days"]),
                    agent_count=int(design["agent_count"]),
                    locality_count=int(design["locality_count"]),
                    challenge=True,
                ))
    finally:
        base.SimulationConfig = original_config

    repository_after = repository_state(ROOT)
    model_after = model_sha256(ROOT)
    max_supply_residual = max(
        abs(float(cell["metrics"]["supply_conservation_residual"])) for cell in results
    )
    funnel_counts = [int(cell["metrics"]["contact_funnel_records"]) for cell in results]
    latent_counts = [int(cell["metrics"]["latent_contact_count"]) for cell in results]
    gate = {
        "all_cells_reach_contact_funnel": all(value > 0 for value in funnel_counts),
        "all_cells_produce_at_least_one_latent_contact": all(value > 0 for value in latent_counts),
        "supply_conservation_passed": max_supply_residual <= float(
            contract["acceptance_gate"]["all_cells_supply_conservation_absolute_residual_max"]
        ),
        "model_hash_stable": model_before == model_after,
        "tracked_diff_stable": (
            repository_before.get("tracked_diff_sha256") == repository_after.get("tracked_diff_sha256")
        ),
        "cell_manifest_audits_valid": all(cell["manifest_audit"]["valid"] for cell in results),
    }
    passed = all(gate.values())
    return {
        "schema_version": "pineland.synthetic_contact_routing_repair.v2",
        "experiment_id": contract["experiment_id"],
        "status": "full" if full else "smoke",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "production_architecture_changed": False,
        "component_test_contact_routing": "legacy_contact_only",
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "base_factorial_runner_sha256": file_sha256(base.Path(base.__file__)),
        "model_sha256": model_before,
        "repository_before": repository_before,
        "repository_after": repository_after,
        "seeds": seeds,
        "cell_count": len(results),
        "gate": gate,
        "max_supply_conservation_absolute_residual": max_supply_residual,
        "contact_funnel_record_counts": funnel_counts,
        "latent_contact_counts": latent_counts,
        "passed": passed,
        "localized_hypothesis_supported": passed,
        "interpretation": contract["interpretation"],
        "cells": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    report = run(full=args.full, seed=args.seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.synthetic_contact_routing_repair_manifest.v2",
        "artifact": output.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(output),
        "contract": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "passed": report["passed"],
    }
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "passed": report["passed"],
        "gate": report["gate"],
        "latent_contact_counts": report["latent_contact_counts"],
    }, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
