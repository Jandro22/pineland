"""Synthetic validation of a study-layer, non-substantive measurement observer."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.action_model import ACTION_ORGANIZATION_KINDS, local_action_support  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402

CONTRACT = ROOT / "studies/research_program/prospective_measurement_retention_contract_v1.json"
OUTPUT = ROOT / "studies/research_program/prospective_measurement_retention_recovery_v1.json"

CONTROL_DIMS = {"formal", "physical", "administrative", "legal", "fiscal", "social", "expected"}


def stable_sha(value) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def formation_state(world) -> dict[str, dict]:
    return {
        formation_id: {
            "organization_id": item.organization_id,
            "locality_id": item.locality_id,
            "microzone_id": item.current_microzone_id,
            "personnel": float(item.personnel),
            "availability": float(item.availability),
            "readiness": float(item.readiness),
            "command": float(item.command),
            "moving": bool(item.moving),
            "operational_status": item.operational_status,
            "outside_pineland": bool(item.outside_pineland),
        }
        for formation_id, item in sorted(world.formations.items())
    }


def detect_formation_changes(before: dict[str, dict], after: dict[str, dict], *, time: float,
                             event_type: str, event_id: str) -> list[dict]:
    changes = []
    before_ids, after_ids = set(before), set(after)
    for formation_id in sorted(after_ids - before_ids):
        changes.append({
            "change_type": "birth", "formation_id": formation_id,
            "time": float(time), "event_type": event_type, "event_id": event_id,
            "before": None, "after": after[formation_id],
        })
    for formation_id in sorted(before_ids - after_ids):
        changes.append({
            "change_type": "removal", "formation_id": formation_id,
            "time": float(time), "event_type": event_type, "event_id": event_id,
            "before": before[formation_id], "after": None,
        })
    for formation_id in sorted(before_ids & after_ids):
        keys = ("locality_id", "microzone_id", "moving", "operational_status", "outside_pineland")
        if any(before[formation_id].get(key) != after[formation_id].get(key) for key in keys):
            changes.append({
                "change_type": "state_change", "formation_id": formation_id,
                "time": float(time), "event_type": event_type, "event_id": event_id,
                "before": before[formation_id], "after": after[formation_id],
            })
    return changes


class ObservingProcessEngine(ProcessEngine):
    def __init__(self, world, lifecycle: list[dict]):
        super().__init__(world)
        self.lifecycle = lifecycle

    def execute(self, event):
        before = formation_state(self.world)
        event_id = super().execute(event)
        after = formation_state(self.world)
        self.lifecycle.extend(detect_formation_changes(
            before, after, time=event.time, event_type=event.event_type, event_id=event_id,
        ))
        return event_id


def snapshot(world, label: str) -> dict:
    controls = {
        locality_id: {
            actor_id: vector.to_dict()
            for actor_id, vector in sorted(locality.control.items())
        }
        for locality_id, locality in sorted(world.localities.items())
    }
    formations = formation_state(world)
    security_posts = {
        post_id: {
            "organization_id": item.organization_id,
            "locality_id": item.locality_id,
            "microzone_id": item.microzone_id,
            "personnel": float(item.personnel),
            "fixed_presence": float(item.fixed_presence),
            "available_fraction": float(item.available_fraction),
            "formation_id": item.formation_id,
        }
        for post_id, item in sorted(world.security_posts.items())
    }
    patrols = {
        patrol_id: {
            "formation_id": item.formation_id,
            "organization_id": item.organization_id,
            "locality_id": item.locality_id,
            "current_microzone_id": item.current_microzone_id,
            "route_history": list(item.route_history),
            "available_at": float(item.available_at),
            "response_fraction": float(item.response_fraction),
            "presence_accounted_at": item.presence_accounted_at,
        }
        for patrol_id, item in sorted(world.patrols.items())
    }
    manpower = {
        f"{organization_id}|{locality_id}": float(quantity)
        for (organization_id, locality_id), quantity in sorted(world.organization_manpower_pools.items())
    }
    manpower_supply = {
        f"{organization_id}|{locality_id}": float(quantity)
        for (organization_id, locality_id), quantity in sorted(
            world.organization_manpower_supply_reserves.items()
        )
    }
    control_beliefs = {
        f"{observer}|{target}|{locality_id}": {
            "control_estimate": belief.control_estimate.to_dict(),
            "confidence": float(belief.confidence),
            "updated_at": float(belief.updated_at),
            "last_reliable_observation_at": float(belief.last_reliable_observation_at),
            "evidence_count": int(belief.evidence_count),
            "contradiction_index": float(belief.contradiction_index),
            "violence_estimate": float(belief.violence_estimate),
        }
        for (observer, target, locality_id), belief in sorted(world.control_beliefs.items())
    }
    presence_beliefs = {
        "|".join(map(str, key)): asdict(belief)
        for key, belief in sorted(world.presence_beliefs.items())
    }
    node_presence_beliefs = {
        "|".join(map(str, key)): asdict(belief)
        for key, belief in sorted(world.node_presence_beliefs.items())
    }
    action_support = {}
    for organization_id, organization in sorted(world.organizations.items()):
        if organization.status != "active" or organization.kind not in ACTION_ORGANIZATION_KINDS:
            continue
        for locality_id in sorted(world.localities):
            support = local_action_support(world, organization_id, locality_id)
            action_support[f"{organization_id}|{locality_id}"] = {
                "unfielded_fighter_equivalents": float(support.unfielded_fighter_equivalents),
                "fielded_fighter_equivalents": float(support.fielded_fighter_equivalents),
                "total_fighter_equivalents": float(support.total_fighter_equivalents),
                "nonfielded_target_personnel": float(support.nonfielded_target_personnel),
                "asset_target_count": int(support.asset_target_count),
                "susceptible_population": float(support.susceptible_population),
                "armed_confrontation": bool(support.armed_confrontation),
                "nonfielded_human_target": bool(support.nonfielded_human_target),
                "government_asset_target": bool(support.government_asset_target),
                "civilian_coercion": bool(support.civilian_coercion),
            }
    records = [asdict(item) for item in world.synthetic_records]
    return {
        "label": label,
        "time": float(world.time),
        "truth": {
            "control": controls,
            "formations": formations,
            "security_posts": security_posts,
            "patrols": patrols,
            "organization_manpower_pools": manpower,
            "organization_manpower_supply_reserves": manpower_supply,
        },
        "actor_information": {
            "control_beliefs": control_beliefs,
            "presence_beliefs": presence_beliefs,
            "node_presence_beliefs": node_presence_beliefs,
        },
        "action_support": action_support,
        "record_layer": records,
    }


def retained_fingerprint(world) -> str:
    payload = {
        "time": float(world.time),
        "summary": world.summary(),
        "control": {
            locality_id: {actor: vector.to_dict() for actor, vector in sorted(locality.control.items())}
            for locality_id, locality in sorted(world.localities.items())
        },
        "formations": formation_state(world),
        "security_posts": {key: asdict(value) for key, value in sorted(world.security_posts.items())},
        "patrols": {key: asdict(value) for key, value in sorted(world.patrols.items())},
        "manpower": {f"{a}|{l}": q for (a, l), q in sorted(world.organization_manpower_pools.items())},
        "manpower_supply": {
            f"{a}|{l}": q
            for (a, l), q in sorted(world.organization_manpower_supply_reserves.items())
        },
        "control_beliefs": {
            f"{o}|{t}|{l}": asdict(b) for (o, t, l), b in sorted(world.control_beliefs.items())
        },
        "presence_beliefs": {"|".join(map(str, k)): asdict(v) for k, v in sorted(world.presence_beliefs.items())},
        "records": [asdict(item) for item in world.synthetic_records],
        "event_counts": dict(sorted(world.event_counts.items())),
    }
    return stable_sha(payload)


def detector_unit_recovery() -> dict:
    base = {
        "A": {"locality_id": "L1", "microzone_id": "M1", "moving": False,
              "operational_status": "effective", "outside_pineland": False},
        "C": {"locality_id": "L3", "microzone_id": "M3", "moving": False,
              "operational_status": "effective", "outside_pineland": False},
    }
    after = {
        "A": {"locality_id": "L2", "microzone_id": "M2", "moving": True,
              "operational_status": "effective", "outside_pineland": False},
        "B": {"locality_id": "L1", "microzone_id": "M1", "moving": False,
              "operational_status": "effective", "outside_pineland": False},
    }
    changes = detect_formation_changes(base, after, time=2.0, event_type="synthetic_unit", event_id="UNIT")
    types = {(row["formation_id"], row["change_type"]) for row in changes}
    expected = {("A", "state_change"), ("B", "birth"), ("C", "removal")}
    return {"passed": types == expected, "observed": sorted([list(item) for item in types]),
            "expected": sorted([list(item) for item in expected])}


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
    baseline.run(until=float(design["horizon_days"]))
    baseline_fp = retained_fingerprint(baseline_world)

    observed_world = generate_pineland(config)
    lifecycle: list[dict] = []
    observed = Simulation(observed_world)
    observed.processes = ObservingProcessEngine(observed_world, lifecycle)
    snapshots = [snapshot(observed_world, "initial_pre_event")]
    for day in range(1, int(design["horizon_days"]) + 1):
        observed.run(until=float(day))
        snapshots.append(snapshot(observed_world, f"day_{day}"))
    observed_fp = retained_fingerprint(observed_world)

    all_controls_valid = all(
        CONTROL_DIMS.issubset(vector.keys())
        for snap in snapshots
        for actors in snap["truth"]["control"].values()
        for vector in actors.values()
    )
    daily_layers = all(
        all(key in snap for key in ("truth", "actor_information", "action_support", "record_layer"))
        and all(key in snap["truth"] for key in (
            "control", "formations", "security_posts", "patrols",
            "organization_manpower_pools", "organization_manpower_supply_reserves"
        ))
        and all(key in snap["actor_information"] for key in (
            "control_beliefs", "presence_beliefs", "node_presence_beliefs"
        ))
        for snap in snapshots
    )
    event_provenance = all(
        all(key in row for key in ("change_type", "formation_id", "time", "event_type", "event_id"))
        for row in lifecycle
    )
    gates = {
        "all_snapshot_days_captured": len(snapshots) == int(design["horizon_days"]) + 1,
        "daily_layers_present": daily_layers,
        "seven_dimensional_control_retained": all_controls_valid,
        "security_post_layer_nonempty": any(snap["truth"]["security_posts"] for snap in snapshots),
        "patrol_layer_nonempty": any(snap["truth"]["patrols"] for snap in snapshots),
        "control_belief_layer_nonempty": any(snap["actor_information"]["control_beliefs"] for snap in snapshots),
        "presence_belief_layer_available": all("presence_beliefs" in snap["actor_information"] for snap in snapshots),
        "action_support_layer_nonempty": any(snap["action_support"] for snap in snapshots),
        "record_layer_available": all(isinstance(snap["record_layer"], list) for snap in snapshots),
        "event_lifecycle_provenance_complete": event_provenance,
        "observer_dynamics_invariant": baseline_fp == observed_fp,
    }
    return {
        "seed": seed,
        "baseline_final_fingerprint": baseline_fp,
        "instrumented_final_fingerprint": observed_fp,
        "lifecycle_event_count": len(lifecycle),
        "lifecycle_change_types": sorted({row["change_type"] for row in lifecycle}),
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "formation_lifecycle": lifecycle,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    design = contract["synthetic_design"]
    repo_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    detector = detector_unit_recovery()
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
        "schema_version": "pineland.prospective_measurement_retention_recovery.v1",
        "experiment_id": contract["experiment_id"],
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
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
        "schema_version": "pineland.prospective_measurement_retention_manifest.v1",
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
            "seed": row["seed"], "passed": row["passed"],
            "snapshot_count": row["snapshot_count"],
            "lifecycle_event_count": row["lifecycle_event_count"],
            "fingerprints_equal": row["gates"]["observer_dynamics_invariant"],
        } for row in results],
        "output": str(OUTPUT),
    }, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
