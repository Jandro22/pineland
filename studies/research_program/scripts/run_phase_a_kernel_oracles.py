"""Run independent per-kernel oracle checks for the migrated Phase-A islands."""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import (  # noqa: E402
    ParticleBatchState,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.action_model import action_attempt_hazard  # noqa: E402
from pineland_sim.ensemble import EnsembleBeliefState  # noqa: E402
from pineland_sim.native_ensemble import GOVERNMENT_SIDE, INSURGENT_SIDE  # noqa: E402
from pineland_sim.native_kernels import available as native_available  # noqa: E402
from pineland_sim.physical import response_times  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402


def _particle(seed: int) -> SimulationParticle:
    config = SimulationConfig(
        seed=seed,
        agent_count=80,
        locality_count=17,
        horizon_days=7.0,
        output_mode="ensemble",
    )
    simulation = Simulation(generate_pineland(config))
    simulation.configure_execution(
        execution_backend="ensemble",
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    return SimulationParticle(simulation)


def physical_and_action_oracle() -> dict[str, Any]:
    comparisons = 0
    response_errors: list[float] = []
    hazard_errors: list[float] = []
    for seed in range(2026090801, 2026090901):
        particle = _particle(seed)
        batch = ParticleBatchState.from_particles([particle])
        hot = batch.hot_state
        world = particle.world
        for locality_id in batch.topology.locality_ids:
            locality_index = batch.topology.locality_index[locality_id]
            for side, actor in (
                (GOVERNMENT_SIDE, "government"),
                (INSURGENT_SIDE, "insurgent"),
            ):
                packed = hot.response_times(
                    0, locality_index, side, 0.0, batch.topology
                )
                reference = response_times(
                    world,
                    locality_id,
                    actor,
                    0.0,
                    use_runtime_indexes=False,
                )
                for zone_id, expected in reference.items():
                    observed = packed[batch.topology.microzone_index[zone_id]]
                    if math.isinf(expected) and math.isinf(observed):
                        error = 0.0
                    else:
                        error = abs(float(observed) - float(expected))
                    response_errors.append(error)
                    comparisons += 1
        for organization_id in world.organizations:
            if not hot.organization_action_eligible[hot._oo(0, hot.organization_index[organization_id])]:
                continue
            oi = hot.organization_index[organization_id]
            for locality_id in batch.topology.locality_ids:
                li = batch.topology.locality_index[locality_id]
                observed = hot.action_attempt_hazard(0, oi, li)
                expected = action_attempt_hazard(world, organization_id, locality_id)
                hazard_errors.append(abs(float(observed) - float(expected)))
    return {
        "generated_seeds": 100,
        "response_time_comparisons": len(response_errors),
        "action_hazard_comparisons": len(hazard_errors),
        "response_time_max_absolute_error": max(response_errors),
        "action_hazard_max_absolute_error": max(hazard_errors),
        "passed": max(response_errors) == 0.0 and max(hazard_errors) <= 1.0e-12,
    }


def _fusion_case(
    *,
    stride: int,
    rows: list[list[float]],
    updates: list[tuple[int, tuple[str, ...], float, float, Any]],
    method: str,
    native_environment: str,
    native_enabled: bool,
) -> list[float]:
    keys = tuple(("observer", "actor", f"locality-{index}") for index in range(len(rows)))
    state = EnsembleBeliefState.from_rows(keys, [rows], stride)
    prior = list(state.state)
    os.environ[native_environment] = "1" if native_enabled else "0"
    if method == "control":
        state.fuse_control(
            updates,
            contradiction_memory_days=30.0,
            contradiction_penalty=0.45,
        )
    elif method == "presence":
        state.fuse_presence(
            updates,
            contradiction_memory_days=30.0,
            contradiction_penalty=0.45,
        )
    else:
        state.fuse_zone(
            updates,
            contradiction_memory_days=30.0,
            contradiction_penalty=0.45,
        )
    return list(state.state)


def numeric_fusion_oracle() -> dict[str, Any]:
    rng = random.Random(2026090811)
    keys = tuple(("observer", "actor", f"locality-{index}") for index in range(32))
    control_rows = [
        [
            *[rng.random() for _ in range(7)],
            0.02 + 0.96 * rng.random(),
            rng.random() * 4.0,
            -1.0e9,
            float(rng.randrange(4)),
            rng.random(),
            rng.random() * 2.0,
        ]
        for _ in keys
    ]
    presence_rows = [
        [rng.random(), 0.02 + 0.96 * rng.random(), rng.random() * 4.0,
         -1.0e9, float(rng.randrange(4)), rng.random(), rng.random() * 3000.0]
        for _ in keys
    ]
    zone_rows = [
        [rng.random(), 0.02 + 0.96 * rng.random(), rng.random() * 4.0,
         -1.0e9, float(rng.randrange(4)), rng.random()]
        for _ in keys
    ]
    control_updates = [
        (0, keys[index % len(keys)], rng.random() * 8.0,
         0.02 + 0.5 * rng.random(), [rng.random() for _ in range(7)])
        for index in range(512)
    ]
    presence_updates = [
        (0, keys[index % len(keys)], rng.random() * 8.0,
         0.02 + 0.5 * rng.random(), rng.random(), rng.random() * 3000.0)
        for index in range(512)
    ]
    zone_updates = [
        (0, keys[index % len(keys)], rng.random() * 8.0,
         0.02 + 0.5 * rng.random(), rng.random())
        for index in range(512)
    ]
    cases = {
        "control": (13, control_rows, control_updates, "PINELAND_NATIVE_CONTROL_BATCH"),
        "presence": (7, presence_rows, presence_updates, "PINELAND_NATIVE_INFORMATION_BATCH"),
        "zone": (6, zone_rows, zone_updates, "PINELAND_NATIVE_INFORMATION_BATCH"),
    }
    results: dict[str, Any] = {}
    for name, (stride, rows, updates, variable) in cases.items():
        os.environ[variable] = "0"
        reference = _fusion_case(
            stride=stride, rows=rows, updates=updates,
            method=name, native_environment=variable, native_enabled=False,
        )
        os.environ[variable] = "1"
        native = _fusion_case(
            stride=stride, rows=rows, updates=updates,
            method=name, native_environment=variable, native_enabled=True,
        )
        errors = [abs(float(a) - float(b)) for a, b in zip(reference, native)]
        results[name] = {
            "state_values": len(errors),
            "updates": len(updates),
            "max_absolute_error": max(errors),
            "passed": max(errors) <= 1.0e-12,
        }
    os.environ.pop("PINELAND_NATIVE_CONTROL_BATCH", None)
    os.environ.pop("PINELAND_NATIVE_INFORMATION_BATCH", None)
    return {
        "native_library_available": native_available(),
        "kernels": results,
        "passed": bool(native_available() and all(item["passed"] for item in results.values())),
    }


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing kernel evidence: {output}")
    physical_action = physical_and_action_oracle()
    numeric = numeric_fusion_oracle()
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_kernel_oracles_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "physical_generated_states": 100,
            "physical_tolerance": {"absolute": 0.0, "relative": 0.0},
            "action_cells": "all active organization-locality cells in 100 generated worlds",
            "action_tolerance": 1.0e-12,
            "information_fusion_updates_per_kernel": 512,
            "information_tolerance": 1.0e-12,
        },
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "commit": repository_state(ROOT)["commit_hash"],
            "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
            "command": "python studies/research_program/scripts/run_phase_a_kernel_oracles.py",
        },
        "physical_and_action": physical_action,
        "numeric_information_fusion": numeric,
        "passed": bool(physical_action["passed"] and numeric["passed"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_kernel_oracles_v1.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({
        "output": str(args.output.resolve()),
        "passed": result["passed"],
        "physical_action_passed": result["physical_and_action"]["passed"],
        "numeric_information_passed": result["numeric_information_fusion"]["passed"],
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
