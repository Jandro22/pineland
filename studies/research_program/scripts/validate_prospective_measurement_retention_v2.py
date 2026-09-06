"""One-shot synthetic validation of passive, scheduled measurement retention."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402

V1_RUNNER = ROOT / "studies/research_program/scripts/validate_prospective_measurement_retention_v1.py"
spec = importlib.util.spec_from_file_location("retention_v1_helpers", V1_RUNNER)
v1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(v1)

CONTRACT = ROOT / "studies/research_program/prospective_measurement_retention_contract_v2.json"
OUTPUT = ROOT / "studies/research_program/prospective_measurement_retention_recovery_v2.json"


class ScheduledSnapshotProcessEngine(v1.ObservingProcessEngine):
    def __init__(self, world, lifecycle: list[dict], snapshots: list[dict]):
        super().__init__(world, lifecycle)
        self.snapshots = snapshots

    def execute(self, event):
        if event.event_type == "measurement_snapshot_v2":
            self.snapshots.append(v1.snapshot(self.world, f"day_{int(round(event.time))}"))
            # Deliberately bypass ProcessEngine.execute: no event counter, RNG,
            # event log, state mutation, or recording operation is permitted.
            return f"MEASURE-{int(round(event.time))}"
        return super().execute(event)


def run_one(seed: int, design: dict) -> dict:
    config = SimulationConfig(
        seed=seed,
        agent_count=int(design["agent_count"]),
        locality_count=int(design["locality_count"]),
        horizon_days=float(design["horizon_days"]),
        output_mode="forensic",
    )

    baseline_world = generate_pineland(config)
    baseline = Simulation(baseline_world)
    baseline_result = baseline.run(until=float(design["horizon_days"]))
    baseline_fp = v1.retained_fingerprint(baseline_world)

    world = generate_pineland(config)
    lifecycle: list[dict] = []
    snapshots: list[dict] = []
    sim = Simulation(world)
    sim.processes = ScheduledSnapshotProcessEngine(world, lifecycle, snapshots)
    sim.initialize()
    for day in design["measurement_days"]:
        sim.scheduler.schedule(
            float(day), "measurement_snapshot_v2", {"measurement_day": int(day)},
            priority=int(design["measurement_event_priority"]),
        )
    observed_result = sim.run(until=float(design["horizon_days"]))
    observed_fp = v1.retained_fingerprint(world)

    expected_days = [float(day) for day in design["measurement_days"]]
    actual_days = [float(item["time"]) for item in snapshots]
    daily_layers = all(
        all(key in snap for key in ("truth", "actor_information", "action_support", "record_layer"))
        and all(key in snap["truth"] for key in (
            "control", "formations", "security_posts", "patrols", "organization_manpower_pools"
        ))
        and all(key in snap["actor_information"] for key in (
            "control_beliefs", "presence_beliefs", "node_presence_beliefs"
        ))
        for snap in snapshots
    )
    controls_valid = all(
        v1.CONTROL_DIMS.issubset(vector.keys())
        for snap in snapshots
        for actors in snap["truth"]["control"].values()
        for vector in actors.values()
    )
    lifecycle_provenance = all(
        all(key in row for key in ("change_type", "formation_id", "time", "event_type", "event_id"))
        for row in lifecycle
    )
    gates = {
        "measurement_days_exact_once": actual_days == expected_days,
        "daily_layers_present": daily_layers,
        "seven_dimensional_control_retained": controls_valid,
        "security_post_layer_nonempty": any(snap["truth"]["security_posts"] for snap in snapshots),
        "patrol_layer_nonempty": any(snap["truth"]["patrols"] for snap in snapshots),
        "control_belief_layer_nonempty": any(snap["actor_information"]["control_beliefs"] for snap in snapshots),
        "presence_belief_layer_available": all("presence_beliefs" in snap["actor_information"] for snap in snapshots),
        "action_support_layer_nonempty": any(snap["action_support"] for snap in snapshots),
        "record_layer_available": all(isinstance(snap["record_layer"], list) for snap in snapshots),
        "event_lifecycle_provenance_complete": lifecycle_provenance,
        "observer_dynamics_invariant": baseline_fp == observed_fp,
        "same_calendar_horizon": baseline_result.stopped_at == observed_result.stopped_at == float(design["horizon_days"]),
    }
    return {
        "seed": seed,
        "baseline_final_fingerprint": baseline_fp,
        "instrumented_final_fingerprint": observed_fp,
        "baseline_events_processed": baseline_result.events_processed,
        "instrumented_events_processed_including_noop_measurements": observed_result.events_processed,
        "measurement_event_count": len(snapshots),
        "lifecycle_event_count": len(lifecycle),
        "lifecycle_change_types": sorted({row["change_type"] for row in lifecycle}),
        "gates": gates,
        "passed": all(gates.values()),
        "snapshots": snapshots,
        "formation_lifecycle": lifecycle,
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    design = contract["synthetic_design"]
    repo_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    detector = v1.detector_unit_recovery()
    results = [run_one(int(seed), design) for seed in design["seeds"]]
    model_after = model_sha256(ROOT)
    repo_after = repository_state(ROOT)
    global_gates = {
        "lifecycle_detector_unit_recovery": detector["passed"],
        "all_seed_gates_pass": all(row["passed"] for row in results),
        "model_hash_stable": model_before == model_after,
        "tracked_diff_stable": repo_before.get("tracked_diff_sha256") == repo_after.get("tracked_diff_sha256"),
    }
    payload = {
        "schema_version": "pineland.prospective_measurement_retention_recovery.v2",
        "experiment_id": contract["experiment_id"],
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "parent_failed_experiment": contract["parent_failed_experiment"],
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "v1_helper_runner_sha256": file_sha256(V1_RUNNER),
        "model_sha256": model_before,
        "repository_before": repo_before,
        "repository_after": repo_after,
        "detector_unit_recovery": detector,
        "results": results,
        "global_gates": global_gates,
        "passed": all(global_gates.values()),
        "interpretation": contract["interpretation"],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.prospective_measurement_retention_manifest.v2",
        "artifact": OUTPUT.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(OUTPUT),
        "contract": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "passed": payload["passed"],
    }
    OUTPUT.with_name(OUTPUT.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "passed": payload["passed"],
        "global_gates": global_gates,
        "seed_summaries": [{
            "seed": row["seed"],
            "passed": row["passed"],
            "measurement_events": row["measurement_event_count"],
            "lifecycle_events": row["lifecycle_event_count"],
            "lifecycle_types": row["lifecycle_change_types"],
            "fingerprints_equal": row["gates"]["observer_dynamics_invariant"],
        } for row in results],
        "output": str(OUTPUT),
    }, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
