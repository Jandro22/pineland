"""Run untuned Afghanistan trajectories on the frozen schema-v3 case.

This runner deliberately separates the domestic-core transfer test from the
later Afghanistan-specific external-intervention layer.  Generic Pineland
foreign-state and peace-process generators are disabled here because their
synthetic neighbors/timing are not valid Afghanistan historical inputs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"
DESIGN = STUDY / "config" / "study_design.json"
EVENT_MANIFEST = STUDY / "data" / "processed" / "event_panel_manifest.json"
OUT = STUDY / "runs" / "untuned_domestic_core"
START = date(2004, 1, 1)
END = date(2021, 8, 15)
FORMULATION = "afghanistan_untuned_domestic_core_v1"
DEFAULT_SEEDS = tuple(20_040_101 + 10_007 * index for index in range(4))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _rename_case_organizations(world) -> None:
    world.organizations["government"].name = "Islamic Republic of Afghanistan"
    world.organizations["fdf"].name = "Afghan National Security Forces"
    world.organizations["police"].name = "Afghan National Police"
    world.organizations["insurgent"].name = "Taliban"


def formation_snapshot(world) -> list[dict]:
    result = []
    for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
        district_id = world.localities[formation.locality_id].district_id
        hierarchy = world.district_hierarchy.get(district_id, {})
        result.append({
            "formation_id": formation.formation_id,
            "organization_id": formation.organization_id,
            "locality_id": formation.locality_id,
            "district_id": district_id,
            "province_id": hierarchy.get("province"),
            "region_id": hierarchy.get("region"),
            "personnel": formation.personnel,
            "available_personnel": formation.available_personnel(),
            "effective_readiness": formation.effective_readiness(),
            "supply_fraction": formation.supply_fraction(),
            "operational_status": formation.operational_status,
            "moving": formation.moving,
        })
    return result


def run_seed(seed: int, agent_count: int, horizon_days: float | None = None) -> dict:
    from pineland_sim import Simulation, SimulationConfig, generate_pineland

    case = json.loads(CASE.read_text(encoding="utf-8"))
    full_horizon = float((END - START).days)
    horizon = full_horizon if horizon_days is None else min(full_horizon, float(horizon_days))
    if agent_count < len(case["localities"]):
        raise ValueError(f"Afghanistan empirical case needs agent_count >= {len(case['localities'])}")
    config = SimulationConfig(
        seed=seed,
        horizon_days=horizon,
        agent_count=agent_count,
        locality_count=len(case["localities"]),
        output_mode="ensemble",
    )
    config.information.observation_retention_days = 90.0
    # Taliban organizational persistence is an observed actor-existence input,
    # not a violence target.  Tactical activity remains endogenous.
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, horizon]]
    }
    # Afghanistan's external system is too consequential to substitute the
    # synthetic Pineland neighbors.  These domains are added in the next,
    # explicitly sourced historical layer.
    config.foreign_affairs.enabled = False
    config.peace_process.enabled = False
    config.validate()

    world = generate_pineland(config, empirical_geography=case)
    _rename_case_organizations(world)
    initial_formations = formation_snapshot(world)
    started = time.perf_counter()
    world = Simulation(world).run().world
    runtime = time.perf_counter() - started

    realized = {
        event.event_id: bool(event.true_state_delta.get("contact", 0.0) > 0)
        for event in world.event_log if event.event_type == "contact"
    }
    contacts = []
    for record in world.synthetic_records:
        if record.event_type != "contact" or record.locality_id not in world.localities:
            continue
        district_id = world.localities[record.locality_id].district_id
        hierarchy = world.district_hierarchy[district_id]
        contacts.append({
            "event_id": record.event_id,
            "day": record.time,
            "date": (START + timedelta(days=int(record.time))).isoformat(),
            "week_index": int(record.time // 7),
            "locality_id": record.locality_id,
            "district_id": district_id,
            "province_id": hierarchy["province"],
            "region_id": hierarchy["region"],
            "realized": realized.get(record.event_id, False),
            "recorded": record.recorded,
            "reported_severity": record.reported_severity,
            "geocoding_error": record.geocoding_error,
            "geocoding_error_distance_km": record.geocoding_error_distance_km,
        })

    latent = [row for row in contacts if row["realized"]]
    recorded = [row for row in latent if row["recorded"]]
    return {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "formulation_tag": FORMULATION,
        "parameter_fit": False,
        "seed": seed,
        "agent_count": agent_count,
        "horizon_days": horizon,
        "runtime_seconds": runtime,
        "case_sha256": sha256(CASE),
        "study_design_sha256": sha256(DESIGN),
        "event_panel_manifest_sha256": sha256(EVENT_MANIFEST),
        "config": config.to_dict(),
        "external_layer_status": "generic foreign affairs and peace process intentionally disabled",
        "summary": world.summary(),
        "initial_formations": initial_formations,
        "final_formations": formation_snapshot(world),
        "contacts": contacts,
        "latent_engagements": len(latent),
        "recorded_engagements": len(recorded),
        "latent_active_province_weeks": len({(row["province_id"], row["week_index"]) for row in latent}),
        "recorded_active_province_weeks": len({(row["province_id"], row["week_index"]) for row in recorded}),
        "latent_active_district_weeks": len({(row["district_id"], row["week_index"]) for row in latent}),
        "recorded_active_district_weeks": len({(row["district_id"], row["week_index"]) for row in recorded}),
        "contact_funnel_counts": dict(world.contact_funnel_counts),
        "checkpoints": world.checkpoints,
        "organization_transitions": [asdict(item) for item in world.organization_transitions],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--agent-count", type=int, default=802)
    parser.add_argument("--horizon-days", type=float, default=None)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(DEFAULT_SEEDS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.agent_count < 401 or not args.seeds:
        parser.error("workers must be positive, agent-count >= 401, and at least one seed is required")

    suffix = f"{int(args.horizon_days)}d" if args.horizon_days is not None else "full"
    output_dir = OUT / suffix
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {seed: output_dir / f"seed_{seed}_agents_{args.agent_count}.json" for seed in args.seeds}
    pending = [seed for seed in args.seeds if args.force or not files[seed].exists()]
    started = time.perf_counter()
    if pending:
        with ProcessPoolExecutor(max_workers=min(args.workers, len(pending))) as executor:
            futures = {
                executor.submit(run_seed, seed, args.agent_count, args.horizon_days): seed
                for seed in pending
            }
            for future in as_completed(futures):
                seed = futures[future]
                payload = future.result()
                atomic_json(files[seed], payload)
                print(json.dumps({
                    "completed_seed": seed,
                    "runtime_seconds": payload["runtime_seconds"],
                    "latent_engagements": payload["latent_engagements"],
                    "recorded_engagements": payload["recorded_engagements"],
                }), flush=True)

    from pineland_sim import SimulationConfig
    from pineland_sim.reproducibility import build_run_manifest, file_sha256
    results = [json.loads(files[seed].read_text(encoding="utf-8")) for seed in sorted(args.seeds)]
    representative = SimulationConfig.from_dict(results[0]["config"])
    manifest = build_run_manifest(
        representative,
        seeds=sorted(args.seeds),
        execution_mode={
            "mode": "afghanistan_untuned_domestic_core",
            "workers": min(args.workers, len(args.seeds)),
            "process_isolated": True,
            "foreign_affairs": "disabled_pending_afghanistan_specific_layer",
            "peace_process": "disabled_pending_afghanistan_specific_layer",
        },
        output_schema={"name": "afghanistan_untuned_domestic_core", "version": "1.0.0"},
        case_files=[CASE, DESIGN, EVENT_MANIFEST,
                    STUDY / "data" / "processed" / "source_manifest.json",
                    STUDY / "data" / "processed" / "population_manifest.json"],
        split_file=DESIGN,
        repo_root=ROOT,
        extra={
            "formulation_tag": FORMULATION,
            "runner_sha256": file_sha256(Path(__file__)),
            "parameter_fit": False,
            "agent_count": args.agent_count,
            "horizon_days": results[0]["horizon_days"],
        },
    )
    manifest.update({
        "formulation_tag": FORMULATION,
        "parameter_fit": False,
        "wall_seconds_this_invocation": time.perf_counter() - started,
        "runs": [{
            "seed": row["seed"],
            "runtime_seconds": row["runtime_seconds"],
            "latent_engagements": row["latent_engagements"],
            "recorded_engagements": row["recorded_engagements"],
            "file": files[row["seed"]].name,
            "sha256": sha256(files[row["seed"]]),
        } for row in results],
    })
    atomic_json(output_dir / f"manifest_agents_{args.agent_count}.json", manifest)
    print(json.dumps({"manifest": str(output_dir / f'manifest_agents_{args.agent_count}.json'),
                      "runs": len(results)}), flush=True)


if __name__ == "__main__":
    main()
