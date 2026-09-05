"""Run the frozen, untuned Nepal ensemble with deterministic process parallelism.

Each seed is an isolated process and writes one resumable JSON result.  Worker
count changes throughput only: seed assignment and sorted collation are fixed.
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
import platform
import sys
import time


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
LEGACY_CASE_PATH = STUDY / "config" / "case_environment.json"
CASE_PATH = STUDY / "config" / "case_environment_repaired.json"
SPLIT_PATH = STUDY / "config" / "split_manifest.json"
OUT = STUDY / "runs" / "post_structural_repair" / "untuned_realized"
FORMULATION_TAG = "post_structural_repair_v1"
START = date(2001, 11, 26)
END = date(2006, 11, 21)
DEFAULT_SEEDS = tuple(20_011_126 + 10_007 * index for index in range(8))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def formation_snapshot(world) -> list[dict]:
    """Capture armed physical presence and readiness without changing state."""
    return [
        {
            "formation_id": formation.formation_id,
            "organization_id": formation.organization_id,
            "organization_status": world.organizations[formation.organization_id].status,
            "locality_id": formation.locality_id,
            "microzone_id": formation.current_microzone_id,
            "personnel": formation.personnel,
            "available_personnel": formation.available_personnel(),
            "readiness": formation.readiness,
            "effective_readiness": formation.effective_readiness(),
            "availability": formation.availability,
            "supply_fraction": formation.supply_fraction(),
            "command": formation.command,
            "operational_status": formation.operational_status,
            "moving": formation.moving,
            "outside_pineland": formation.outside_pineland,
            "organization_member_representatives": sum(
                1 for person in world.persons.values()
                if person.organization_id == formation.organization_id
            ),
            "organization_mobilized_represented_population": sum(
                person.weight * person.armed_fraction for person in world.persons.values()
                if person.organization_id == formation.organization_id
            ),
        }
        for formation in sorted(world.formations.values(), key=lambda item: item.formation_id)
    ]


def organization_snapshot(world) -> list[dict]:
    return [
        {
            "organization_id": organization.organization_id,
            "kind": organization.kind.value,
            "status": organization.status,
            "member_count": len(organization.member_ids),
            "represented_membership": sum(
                world.persons[pid].weight * (world.persons[pid].armed_fraction
                                              if organization.kind.value == "insurgent" else 1.0)
                for pid in organization.member_ids
                if pid in world.persons
            ),
            "resources": organization.resources,
        }
        for organization in sorted(world.organizations.values(), key=lambda item: item.organization_id)
        if organization.kind.value in {"military", "police", "foreign", "insurgent"}
    ]


def run_seed(seed: int, agent_count: int, variant: str = "E_combined",
             config_overrides: dict[str, object] | None = None,
             world_transform: str | None = None) -> dict:
    # Imports occur inside workers so Windows spawn does not initialize the
    # simulation in the coordinator process.
    from pineland_sim.config import SimulationConfig
    from pineland_sim.generator import generate_pineland
    from pineland_sim.simulation import Simulation
    from pineland_sim.reproducibility import model_sha256, repository_state

    model_hash_start = model_sha256(ROOT)
    repository_at_start = repository_state(ROOT)

    case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    horizon = (END - START).days
    config = SimulationConfig(
        seed=seed, horizon_days=horizon, agent_count=agent_count,
        locality_count=len(case["localities"]), output_mode="ensemble",
    )
    # The target stream and checkpoint state are retained; raw reports older
    # than this horizon are pruned only after relay delivery.  A sensitivity
    # run with retention disabled is required before interpretation.
    config.information.observation_retention_days = 90.0
    # Frozen nested opportunity-structure designs.  These switches alter only
    # general model semantics; no historical outcome is read here.
    if variant in {"A_prior_repaired", "B_persistence", "D_contact_semantics"}:
        config.force_structure.mode = "legacy"
    if variant in {"A_prior_repaired", "B_persistence", "C_decomposition", "D_contact_semantics"}:
        config.logistics.source_capacity_model = "population_catchment"
    if variant in {"A_prior_repaired", "B_persistence", "C_decomposition"}:
        config.combat.contact_opportunity_model = "legacy_symmetric"
    if variant in {"B_persistence", "E_combined"}:
        config.organization_ecology.observed_active_intervals = {
            "insurgent": [[0.0, float(horizon)]]
        }
    for path, value in (config_overrides or {}).items():
        target = config
        parts = path.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        setattr(target, parts[-1], value)
    config.validate()
    world = generate_pineland(config, empirical_geography=case)
    transform_diagnostics: dict[str, object] = {"mode": world_transform or "none"}
    if world_transform == "degree_preserving_rewire":
        # Study-only graph surgery for a matched structural ablation.  This
        # changes no simulator parameter and preserves every person's degree.
        from pineland_sim.networks import degree_preserving_rewire, network_diagnostics
        transform_diagnostics["network_before"] = network_diagnostics(world)
        transform_diagnostics["rewire"] = degree_preserving_rewire(
            world, seed + 11, preserve_attributes=True,
        )
        transform_diagnostics["network_after"] = network_diagnostics(world)
    elif world_transform == "remove_patrols":
        # Strong response-process knockout used only in the residual diagnosis:
        # formation reallocation is disabled separately by configuration and
        # clearing patrols prevents the patrol scheduler from creating an
        # adaptive route/observation response.  The baseline path is unchanged.
        transform_diagnostics["patrols_removed"] = len(world.patrols)
        world.patrols.clear()
    elif world_transform not in {None, "none"}:
        raise ValueError(f"unknown world_transform: {world_transform}")
    initial_formations = formation_snapshot(world)
    initial_organizations = organization_snapshot(world)
    started = time.perf_counter()
    world = Simulation(world).run().world
    elapsed = time.perf_counter() - started
    model_hash_end = model_sha256(ROOT)
    realized_contacts = {
        entry.event_id: bool(
            (
                entry.event_type == "contact"
                and entry.true_state_delta.get("contact", 0.0) > 0
            )
            or (
                entry.event_type == "organized_action"
                and entry.true_state_delta.get("state_based_violence_event", 0.0) > 0
            )
        )
        for entry in world.event_log
        if entry.event_type in {"contact", "organized_action"}
    }
    contact_details = {
        entry.event_id: dict(entry.true_state_delta)
        for entry in world.event_log if entry.event_type in {"contact", "organized_action"}
    }
    contacts = [
        {
            "event_id": record.event_id,
            "day": record.time,
            "date": (START + timedelta(days=int(record.time))).isoformat(),
            "locality_id": record.locality_id,
            "district_id": world.localities[record.locality_id].district_id,
            "recorded": record.recorded,
            "reported_severity": record.reported_severity,
            "reported_actor": record.reported_actor,
            "geocoding_error": record.geocoding_error,
            "geocoding_error_distance_km": record.geocoding_error_distance_km,
            "realized": realized_contacts.get(record.event_id, False),
            "latent_details": contact_details.get(record.event_id, {}),
        }
        for record in world.synthetic_records
        if record.event_type in {"contact", "state_based_violence"}
    ]
    false_events = [asdict(record) for record in world.synthetic_records
                    if record.event_type == "false_event"]
    return {
        "schema_version": "1.0.0",
        "study_id": "nepal_2001_2006",
        "benchmark_stage": "post_structural_repair",
        "formulation_tag": FORMULATION_TAG,
        "opportunity_variant": variant,
        "seed": seed,
        "agent_count": agent_count,
        "horizon_days": config.horizon_days,
        "runtime_seconds": elapsed,
        "model_sha256_start": model_hash_start,
        "model_sha256_end": model_hash_end,
        "model_stable_during_run": model_hash_start == model_hash_end,
        "commit_hash": repository_at_start["commit_hash"],
        "dirty_tree": repository_at_start["dirty_tree"],
        "tracked_diff_sha256": repository_at_start["tracked_diff_sha256"],
        "case_sha256": digest(CASE_PATH),
        "legacy_case_sha256": digest(LEGACY_CASE_PATH),
        "split_sha256": digest(SPLIT_PATH),
        "config": config.to_dict(),
        "world_transform": transform_diagnostics,
        "summary": world.summary(),
        "initial_formations": initial_formations,
        "final_formations": formation_snapshot(world),
        "initial_organizations": initial_organizations,
        "final_organizations": organization_snapshot(world),
        "movement_history": [asdict(order) for order in world.movement_orders.values()],
        "event_counts": dict(world.event_counts),
        "contacts": contacts,
        "contact_funnel": world.contact_funnel_records,
        "contact_funnel_counts": world.contact_funnel_counts,
        "action_funnel_counts": world.action_funnel_counts,
        "realized_contact_count": int(sum(item["realized"] for item in contacts)),
        "recorded_realized_contact_count": int(sum(item["realized"] and item["recorded"] for item in contacts)),
        "false_recorded_events": false_events,
        "checkpoints": world.checkpoints,
        "organization_transitions": [asdict(item) for item in world.organization_transitions],
        "peace_transitions": [asdict(item) for item in world.peace_transitions],
    }


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--agent-count", type=int, default=750)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(DEFAULT_SEEDS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--variant", choices=("A_prior_repaired", "B_persistence",
                                                "C_decomposition", "D_contact_semantics",
                                                "E_combined"), default="E_combined")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.workers < 1 or args.agent_count < 1 or not args.seeds:
        parser.error("positive workers, positive agent-count, and at least one seed are required")
    if len(set(args.seeds)) != len(args.seeds):
        parser.error("seeds must be unique")

    output_dir = (args.output_dir or (
        STUDY / "runs" / "post_structural_repair" / "opportunity_nested" / args.variant
    )).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {seed: output_dir / f"seed_{seed}_agents_{args.agent_count}.json" for seed in args.seeds}
    pending = [seed for seed, path in expected.items() if args.force or not path.exists()]
    if pending:
        from pineland_sim.reproducibility import require_certified_core
        try:
            require_certified_core(ROOT)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    prior_manifest_path = output_dir / f"manifest_agents_{args.agent_count}.json"
    prior_manifest = (json.loads(prior_manifest_path.read_text(encoding="utf-8"))
                      if prior_manifest_path.exists() and not args.force else None)
    started = time.perf_counter()
    if pending:
        with ProcessPoolExecutor(max_workers=min(args.workers, len(pending))) as executor:
            futures = {executor.submit(run_seed, seed, args.agent_count, args.variant): seed for seed in pending}
            for future in as_completed(futures):
                seed = futures[future]
                payload = future.result()
                atomic_json(expected[seed], payload)
                print(json.dumps({"completed_seed": seed,
                                  "runtime_seconds": payload["runtime_seconds"],
                                  "contacts": len(payload["contacts"])}), flush=True)

    files = [expected[seed] for seed in sorted(args.seeds)]
    results = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    missing_provenance = [
        path.name for path, row in zip(files, results, strict=True)
        if not row.get("model_sha256_start") or not row.get("model_sha256_end")
        or not row.get("tracked_diff_sha256")
    ]
    if missing_provenance:
        raise SystemExit(
            "refusing to backfill provenance around legacy trajectories; rerun with --force: "
            + ", ".join(missing_provenance)
        )
    if any(not row["model_stable_during_run"] for row in results):
        raise SystemExit("model source changed during at least one trajectory")
    wall_seconds = (time.perf_counter() - started if pending else
                    float((prior_manifest or {}).get("wall_seconds_this_invocation", 0.0)))
    from pineland_sim.config import SimulationConfig
    from pineland_sim.reproducibility import (
        build_run_manifest, canonical_sha256, file_sha256,
    )
    representative_config = SimulationConfig.from_dict(results[0]["config"])
    run_rows = [
        {
            "seed": row["seed"],
            "runtime_seconds": row["runtime_seconds"],
            "config_sha256": canonical_sha256(row["config"]),
            "contact_attempts": len(row["contacts"]),
            "scheduled_recorded_contact_attempts": sum(item["recorded"] for item in row["contacts"]),
            "realized_contacts": sum(item["realized"] for item in row["contacts"]),
            "realized_recorded_contacts": sum(item["realized"] and item["recorded"]
                                               for item in row["contacts"]),
            "file": path.name,
            "sha256": digest(path),
            "model_sha256_start": row["model_sha256_start"],
            "model_sha256_end": row["model_sha256_end"],
            "tracked_diff_sha256": row["tracked_diff_sha256"],
        }
        for row, path in zip(results, files, strict=True)
    ]
    manifest = build_run_manifest(
        representative_config,
        seeds=sorted(args.seeds),
        execution_mode={
            "mode": "untuned_ensemble",
            "output_mode": "ensemble",
            "workers": min(args.workers, len(args.seeds)),
            "process_isolated": True,
            "collation": "sorted_seed_order",
            "bounded_information_retention_days": 90.0,
        },
        output_schema={
            "name": "nepal_untuned_realized_ensemble",
            "version": "2.0.0",
            "per_seed_format": "json",
            "manifest_format": "json",
        },
        case_files=[
            CASE_PATH,
            LEGACY_CASE_PATH,
            STUDY / "config" / "study.json",
            STUDY / "data" / "manifests" / "sources.json",
        ],
        split_file=SPLIT_PATH,
        repo_root=ROOT,
        extra={
            "runner_sha256": file_sha256(Path(__file__)),
            "stage": "untuned",
            "opportunity_variant": args.variant,
            "parameter_fit": False,
            "agent_count": args.agent_count,
            "determinism_contract":
                "isolated fixed seeds; sorted collation; worker count is non-substantive",
            "artifacts": {
                path.relative_to(ROOT).as_posix(): digest(path) for path in files
            },
        },
    )
    # Preserve stable top-level fields consumed by the report builder while
    # adding the complete reproduction envelope above.
    manifest.update({
        "stage": "untuned",
        "opportunity_variant": args.variant,
        "parameter_fit": False,
        "workers": min(args.workers, len(args.seeds)),
        "determinism_contract": "isolated fixed seeds; sorted collation; worker count is non-substantive",
        "case_sha256": digest(CASE_PATH),
        "agent_count": args.agent_count,
        "wall_seconds_this_invocation": wall_seconds,
        "wall_seconds_scope": "parallel trajectory execution; preserved on collation-only reruns",
        "runs": run_rows,
    })
    atomic_json(output_dir / f"manifest_agents_{args.agent_count}.json", manifest)
    print(json.dumps({"manifest": str(output_dir / f'manifest_agents_{args.agent_count}.json'),
                      "runs": len(results), "wall_seconds": manifest["wall_seconds_this_invocation"]}),
          flush=True)


if __name__ == "__main__":
    main()
