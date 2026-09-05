"""Run the frozen Nepal resolution ladder without fitting or case bonuses."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
import json
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
CASE = STUDY / "config" / "case_environment_repaired.json"
SPLIT = STUDY / "config" / "split_manifest.json"
OUT = STUDY / "results" / "post_structural_repair" / "resolution_forensic"
START = date(2001, 11, 26)
END = date(2006, 11, 21)
SEEDS = (20_011_126, 20_051_154)
AGENT_COUNTS = (750, 1500, 3000, 7500)


def digest(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(world) -> list[dict]:
    return [
        {
            "formation_id": f.formation_id,
            "organization_id": f.organization_id,
            "organization_status": world.organizations[f.organization_id].status,
            "locality_id": f.locality_id,
            "microzone_id": f.current_microzone_id,
            "personnel": f.personnel,
            "available_personnel": f.available_personnel(),
            "readiness": f.readiness,
            "effective_readiness": f.effective_readiness(),
            "availability": f.availability,
            "supply_fraction": f.supply_fraction(),
            "operational_status": f.operational_status,
            "moving": f.moving,
        }
        for f in sorted(world.formations.values(), key=lambda item: item.formation_id)
    ]


def run_one(agent_count: int, seed: int) -> dict:
    from pineland_sim.config import SimulationConfig
    from pineland_sim.generator import generate_pineland
    from pineland_sim.simulation import Simulation

    case = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(seed=seed, horizon_days=(END - START).days,
                              agent_count=agent_count, locality_count=len(case["localities"]),
                              output_mode="ensemble")
    config.information.observation_retention_days = 90.0
    config.organization_ecology.observed_active_intervals = {"insurgent": [[0.0, float((END - START).days)]]}
    world = generate_pineland(config, empirical_geography=case)
    initial = snapshot(world)
    started = time.perf_counter()
    world = Simulation(world).run().world
    elapsed = time.perf_counter() - started
    return {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006",
        "agent_count": agent_count, "seed": seed, "runtime_seconds": elapsed,
        "case_sha256": digest(CASE), "split_sha256": digest(SPLIT),
        "initial_formations": initial, "final_formations": snapshot(world),
        "summary": world.summary(),
        "contact_funnel_counts": world.contact_funnel_counts,
        "contact_funnel_records": world.contact_funnel_records,
        "organization_transitions": [
            {"transition_type": t.transition_type, "time": t.time,
             "parent_ids": t.parent_ids, "child_ids": t.child_ids}
            for t in world.organization_transitions
        ],
    }


def reuse_750_benchmark(seed: int) -> dict | None:
    """Reuse the authoritative instrumented 750-agent trajectory when present.

    The resolution ladder is a sensitivity analysis; rerunning an already
    completed matched-seed trajectory would only add wall time and could
    accidentally create a second source of truth for the baseline.
    """
    path = STUDY / "runs" / "post_structural_repair" / "untuned_realized" / f"seed_{seed}_agents_750.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"initial_formations", "final_formations", "summary",
                "contact_funnel_counts", "contact_funnel"}
    if not required.issubset(payload):
        return None
    return {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006",
        "agent_count": 750, "seed": seed,
        "runtime_seconds": payload.get("runtime_seconds", 0.0),
        "case_sha256": payload.get("case_sha256", digest(CASE)),
        "split_sha256": payload.get("split_sha256", digest(SPLIT)),
        "initial_formations": payload["initial_formations"],
        "final_formations": payload["final_formations"],
        "summary": payload["summary"],
        "contact_funnel_counts": payload["contact_funnel_counts"],
        "contact_funnel_records": payload["contact_funnel"],
        "organization_transitions": payload.get("organization_transitions", []),
        "reused_from": str(path.relative_to(STUDY)),
    }


def compact(payload: dict) -> dict:
    counts = payload["contact_funnel_counts"]
    def count(prefix: str) -> int:
        return int(counts.get(prefix, 0))
    return {
        "agent_count": payload["agent_count"], "seed": payload["seed"],
        "runtime_seconds": payload["runtime_seconds"],
        "initial_formation_count": len(payload["initial_formations"]),
        "final_formation_count": len(payload["final_formations"]),
        "initial_insurgent_physical_formations": sum(
            f["organization_id"] == "insurgent" and f["operational_status"] == "effective"
            for f in payload["initial_formations"]),
        "final_insurgent_physical_formations": sum(
            f["organization_id"] == "insurgent" and f["operational_status"] == "effective"
            and f["organization_status"] == "active" for f in payload["final_formations"]),
        "scheduler_executions": count("scheduler_executions"),
        "same_locality_candidate_pairs": count("same_locality_candidate_pairs"),
        "microzone_eligible_candidate_pairs": count("microzone_eligible_candidate_pairs"),
        "proximity_qualified_pairs": count("proximity_qualified_pairs"),
        "true_target_presence_cases": count("true_target_presence_cases"),
        "detected_opponent_sides": count("detected_opponent_sides"),
        "failed_detection_sides": count("failed_detection_sides"),
        "readiness_available_pairs": count("readiness_available_pairs"),
        "supply_eligible_pairs": count("supply_eligible_pairs"),
        "command_eligible_pairs": count("command_eligible_pairs"),
        "engagement_hazard_draws": count("engagement_hazard_draws"),
        "engagement_hazard_passes": count("engagement_hazard_passes"),
        "realized_latent_contacts": count("realized_latent_contacts"),
        "recorded_contacts": count("recorded_contacts"),
        "failure_reasons": {k.removeprefix("failure_reason:"): v
                            for k, v in counts.items() if k.startswith("failure_reason:")},
        "recruitment_total": payload["summary"]["recruitment_total"],
        "mean_insurgent_effective_control": payload["summary"]["mean_insurgent_effective_control"],
        "mean_government_effective_control": payload["summary"]["mean_government_effective_control"],
        "organization_transitions": len(payload["organization_transitions"]),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(agents, seed) for agents in AGENT_COUNTS for seed in SEEDS]
    results = []
    pending = []
    for agents, seed in jobs:
        path = OUT / f"resolution_{agents}_{seed}.json"
        if path.exists():
            results.append(json.loads(path.read_text()))
        elif agents == 750 and (payload := reuse_750_benchmark(seed)) is not None:
            path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
            results.append(payload)
        else:
            pending.append((agents, seed))
    if pending:
        with ProcessPoolExecutor(max_workers=min(4, len(pending))) as executor:
            futures = {executor.submit(run_one, agents, seed): (agents, seed)
                       for agents, seed in pending}
            for future in as_completed(futures):
                payload = future.result()
                path = OUT / f"resolution_{payload['agent_count']}_{payload['seed']}.json"
                path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
                results.append(payload)
                print(json.dumps(compact(payload)), flush=True)
    results.sort(key=lambda item: (item["agent_count"], item["seed"]))
    compact_rows = [compact(item) for item in results]
    output = {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006",
        "design": "matched seeds and frozen empirical inputs; no calibration",
        "agent_counts": list(AGENT_COUNTS), "seeds": list(SEEDS),
        "case_sha256": digest(CASE), "split_sha256": digest(SPLIT),
        "rows": compact_rows,
        "raw_files": [f"resolution_{r['agent_count']}_{r['seed']}.json" for r in results],
    }
    (OUT / "resolution_ladder.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"runs": len(results), "pending_completed": len(pending),
                      "output": str(OUT / "resolution_ladder.json")}))


if __name__ == "__main__":
    main()
