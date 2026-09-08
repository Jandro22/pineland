"""Run the preregistered Phase-A scheduler/oracle exactness battery.

The battery compares both future decision state and continuation state.  A
matching world with a different scheduler/RNG continuation is a failure: it
only means that divergence has been postponed.

This script is deliberately independent of historical inputs and never tunes
the model.  It writes a new, content-addressed result only when the requested
output path does not already exist.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import (  # noqa: E402
    NativeEnsembleRunner,
    PackedParticleFilter,
    ParticleBatchState,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.native_kernels import (  # noqa: E402
    available as native_available,
    control_batch_enabled,
    information_batch_enabled,
    information_event_enabled,
    information_event_plan_enabled,
)
from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    decision_state_component_hashes,
    decision_state_sha256,
    file_sha256,
    model_sha256,
    repository_state,
    scientific_config_sha256,
    simulation_execution_payload,
    simulation_execution_sha256,
)
from pineland_sim.state_estimation import systematic_resample_indices  # noqa: E402


SEEDS = tuple(range(92101, 92113))
HORIZONS = (0.25, 0.50, 1.0, 2.0, 7.0)
RESAMPLING_SEEDS = (93001, 93002, 93003, 93004)


def _particle(seed: int) -> SimulationParticle:
    config = SimulationConfig(
        seed=seed,
        agent_count=80,
        locality_count=17,
        horizon_days=max(HORIZONS),
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


def run_exactness_battery(
    *,
    seeds: tuple[int, ...] = SEEDS,
    horizons: tuple[float, ...] = HORIZONS,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    mismatch_count = 0
    for seed in seeds:
        reference = _particle(seed)
        native = _particle(seed)
        batch = ParticleBatchState.from_particles([native])
        runner = NativeEnsembleRunner.from_batch(batch)
        for horizon in horizons:
            reference.advance_to(horizon)
            batch.advance_to(horizon, runner=runner)
            batch.synchronize_lane_to_world(0)
            reference_components = decision_state_component_hashes(reference.world)
            native_components = decision_state_component_hashes(native.world)
            world_differences = sorted(
                key
                for key in set(reference_components) | set(native_components)
                if reference_components.get(key) != native_components.get(key)
            )
            reference_execution = simulation_execution_payload(
                reference.simulation, lineage_id=reference.lineage_id
            )
            native_execution = simulation_execution_payload(
                native.simulation, lineage_id=native.lineage_id
            )
            execution_differences = sorted(
                key
                for key in set(reference_execution) | set(native_execution)
                if reference_execution.get(key) != native_execution.get(key)
            )
            row = {
                "seed": seed,
                "horizon_days": horizon,
                "world_state_match": not world_differences,
                "execution_state_match": not execution_differences,
                "world_state_sha256": decision_state_sha256(native.world),
                "reference_world_state_sha256": decision_state_sha256(reference.world),
                "execution_sha256": simulation_execution_sha256(
                    native.simulation, lineage_id=native.lineage_id
                ),
                "reference_execution_sha256": simulation_execution_sha256(
                    reference.simulation, lineage_id=reference.lineage_id
                ),
                "world_differences": world_differences,
                "execution_differences": execution_differences,
            }
            rows.append(row)
            mismatch_count += int(bool(world_differences or execution_differences))
    return {
        "seed_count": len(seeds),
        "horizon_count": len(horizons),
        "comparison_count": len(rows),
        "rows": rows,
        "world_state_mismatches": sum(not row["world_state_match"] for row in rows),
        "execution_state_mismatches": sum(
            not row["execution_state_match"] for row in rows
        ),
        "mismatch_count": mismatch_count,
        "passed": mismatch_count == 0,
    }


def _resampling_once() -> dict[str, Any]:
    particles = [_particle(seed) for seed in RESAMPLING_SEEDS]
    root_rng_seed = 314159
    expected_parents = tuple(
        systematic_resample_indices(
            (1.0, 0.0, 0.0, 0.0), random.Random(root_rng_seed)
        )
    )
    filter_ = PackedParticleFilter.from_particles(
        particles,
        rng=random.Random(root_rng_seed),
        ess_fraction=0.99,
        native_runner=True,
    )
    update = filter_.update(
        0.25,
        log_likelihood=(0.0, -100.0, -100.0, -100.0),
    )
    children = tuple(filter_.batch.particles)
    child_world_hashes = tuple(decision_state_sha256(item.world) for item in children)
    child_execution_hashes = tuple(
        simulation_execution_sha256(item.simulation, lineage_id=item.lineage_id)
        for item in children
    )
    parent_world_hash = decision_state_sha256(particles[0].world)
    child_worlds_match_parent = all(value == parent_world_hash for value in child_world_hashes)
    child_lineages = tuple(item.lineage_id for item in children)
    child_lineages_independent = len(set(child_lineages)) == len(child_lineages)
    child_execution_independent = len(set(child_execution_hashes)) == len(child_execution_hashes)

    # Continue the duplicated children.  Their world states should initially be
    # identical, but their declared lineage streams must be allowed to diverge.
    continuation = filter_.update(
        2.0,
        log_likelihood=(0.0, 0.0, 0.0, 0.0),
    )
    continued_world_hashes = tuple(
        decision_state_sha256(item.world) for item in filter_.batch.particles
    )
    return {
        "root_rng_seed": root_rng_seed,
        "particle_seeds": RESAMPLING_SEEDS,
        "expected_parent_indices": expected_parents,
        "observed_parent_indices": update.parent_indices,
        "resampled": update.resampled,
        "lineages": child_lineages,
        "child_world_hashes": child_world_hashes,
        "child_execution_hashes": child_execution_hashes,
        "child_worlds_match_selected_parent": child_worlds_match_parent,
        "child_lineages_independent": child_lineages_independent,
        "child_execution_states_independent": child_execution_independent,
        "continuation_world_hashes": continued_world_hashes,
        "continuation_diverged": len(set(continued_world_hashes)) > 1,
        "continuation_update_resampled": continuation.resampled,
        "passed": (
            update.resampled
            and update.parent_indices == expected_parents
            and child_worlds_match_parent
            and child_lineages_independent
            and child_execution_independent
            and len(set(continued_world_hashes)) > 1
        ),
    }


def run_resampling_reproducibility() -> dict[str, Any]:
    first = _resampling_once()
    second = _resampling_once()
    return {
        "first": first,
        "second": second,
        "repeated_result_match": first == second,
        "passed": bool(first["passed"] and second["passed"] and first == second),
    }


def provenance() -> dict[str, Any]:
    native_path = SRC / "pineland_sim" / "_native" / "pineland_kernels.dll"
    config = SimulationConfig(
        seed=SEEDS[0],
        agent_count=80,
        locality_count=17,
        horizon_days=max(HORIZONS),
        output_mode="ensemble",
    )
    return {
        "commit": repository_state(ROOT)["commit_hash"],
        "dirty_paths": repository_state(ROOT)["dirty_paths"],
        "tracked_diff_sha256": repository_state(ROOT)["tracked_diff_sha256"],
        "model_sha256": model_sha256(ROOT),
        "configuration_sha256": scientific_config_sha256(config),
        "python": platform.python_version(),
        "native_kernel": {
            "available": native_available(),
            "control_batch_enabled": control_batch_enabled(),
            "information_batch_enabled": information_batch_enabled(),
            "information_event_enabled": information_event_enabled(),
            "information_event_plan_enabled": information_event_plan_enabled(),
            "dll_sha256": file_sha256(native_path) if native_path.exists() else None,
        },
        "command": "python studies/research_program/scripts/run_phase_a_exactness_battery.py",
    }


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(
            f"refusing to overwrite existing evidence: {output}; choose a new output path"
        )
    exactness = run_exactness_battery()
    resampling = run_resampling_reproducibility()
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_a_exactness_battery_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "seeds": SEEDS,
            "horizons_days": HORIZONS,
            "world_state_requirement": "zero differing decision-state components",
            "execution_state_requirement": "zero differing scheduler/RNG components",
            "resampling_requirement": "exact parent selection and independent child lineage",
        },
        "provenance": provenance(),
        "exactness": exactness,
        "resampling": resampling,
        "passed": bool(exactness["passed"] and resampling["passed"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["artifact_sha256"] = canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_a_exactness_battery_v1.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({
        "output": str(args.output.resolve()),
        "passed": result["passed"],
        "comparisons": result["exactness"]["comparison_count"],
        "world_state_mismatches": result["exactness"]["world_state_mismatches"],
        "execution_state_mismatches": result["exactness"]["execution_state_mismatches"],
        "resampling_passed": result["resampling"]["passed"],
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
