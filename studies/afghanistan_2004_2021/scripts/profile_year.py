"""Bounded execution and mechanism diagnosis; never launches the full horizon."""
from __future__ import annotations

import argparse
import cProfile
import csv
import json
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from historical_case import HistoricalCoalitionSchedule
from run_transfer_test import build_conditioned_world, initialization_gate, violence_score
from pineland_sim import Simulation
from pineland_sim.entities import CONTROL_DIMENSIONS
from pineland_sim.reproducibility import (
    canonical_sha256, decision_state_component_hashes, model_sha256, trajectory_sha256,
)


def activity_overlap(days: float, violence: dict) -> dict:
    """Score both layers on exactly the same declared province-week cells."""
    panel = ROOT / "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv"
    with panel.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["week_index"]) * 7 <= days]
    cells = {(row["province_id"], int(row["week_index"])) for row in rows}
    observed = {(row["province_id"], int(row["week_index"])) for row in rows
                if int(row["taliban_state_active"])}
    result = {"cells": len(cells), "observed_active": len(observed)}
    for layer in ("latent", "recorded"):
        predicted = {(row["province_id"], row["week_index"])
                     for row in violence[f"{layer}_active_cells"]} & cells
        true_positive = len(predicted & observed)
        result[layer] = {
            "active": len(predicted), "true_positive": true_positive,
            "sensitivity": true_positive / max(1, len(observed)),
            "precision": true_positive / max(1, len(predicted)),
            "jaccard": true_positive / max(1, len(predicted | observed)),
        }
    return result


def run(days: float, profile: bool = False) -> dict:
    if not 0 < days <= 366:
        raise ValueError("This diagnostic is restricted to 0 < days <= 366")
    source_hash = model_sha256(ROOT)
    started = time.perf_counter()
    world, inputs = build_conditioned_world(20_040_101, days, 7500.0)
    initial = initialization_gate(world, inputs, 7500.0)
    assert initial["passed"], initial
    initialization_seconds = time.perf_counter() - started
    schedule = HistoricalCoalitionSchedule(inputs)
    windows = []
    last_wall = time.perf_counter()
    last_day = 0.0

    def hook(state, day):
        nonlocal last_wall, last_day
        schedule(state, day)
        if day >= last_day + 30:
            now = time.perf_counter()
            actor_funnels = {}
            for actor_locality, counts in state.action_funnel_by_actor_locality.items():
                actor = actor_locality.split("|", 1)[0]
                actor_bucket = actor_funnels.setdefault(actor, {})
                for key, value in counts.items():
                    actor_bucket[key] = actor_bucket.get(key, 0) + value
            insurgent_formations = [
                formation for formation in state.formations.values()
                if formation.organization_id == "insurgent" and formation.personnel > 0
            ]
            row = {"start_day": last_day, "end_day": day,
                   "wall_seconds": now - last_wall,
                   "formations": len(state.formations),
                   "observations": len(state.observations),
                   "shipments": len(state.supply_shipments),
                   "movement_orders": len(state.movement_orders),
                   "action_funnel_by_actor_cumulative": actor_funnels,
                   "insurgent_personnel": sum(f.personnel for f in insurgent_formations),
                   "insurgent_available_personnel": sum(
                       f.available_personnel() for f in insurgent_formations
                   ),
                   "insurgent_zero_supply_formations": sum(
                       f.supply_fraction() <= 1e-12 for f in insurgent_formations
                   )}
            windows.append(row)
            print(json.dumps(row), flush=True)
            last_day, last_wall = day, now

    profiler = cProfile.Profile()
    started = time.perf_counter()
    if profile:
        profiler.enable()
    result = Simulation(world, policy_hook=hook).run()
    if profile:
        profiler.disable()
    elapsed = time.perf_counter() - started
    dimensions = {}
    for actor in ("government", "insurgent"):
        vectors = [loc.control[actor] for loc in world.localities.values()]
        dimensions[actor] = {
            dimension: {"mean": sum(getattr(v, dimension) for v in vectors) / len(vectors),
                        "positive_localities": sum(getattr(v, dimension) > 0 for v in vectors)}
            for dimension in CONTROL_DIMENSIONS
        }
    components = decision_state_component_hashes(world)
    rows = []
    if profile:
        for (filename, line, function), values in pstats.Stats(profiler).stats.items():
            rows.append({"file": Path(filename).name, "line": line, "function": function,
                         "calls": values[1], "self_seconds": values[2],
                         "cumulative_seconds": values[3]})
        rows.sort(key=lambda row: -row["cumulative_seconds"])
    violence = violence_score(world, days)
    return {
        "status": "one_year_diagnostic_not_empirical_acceptance",
        "days": days, "seed": 20_040_101, "profile_enabled": profile,
        "model_sha256_start": source_hash, "model_sha256_end": model_sha256(ROOT),
        "initialization_seconds": initialization_seconds, "runtime_seconds": elapsed,
        "windows": windows, "initialization_gate": initial,
        "events_processed": result.events_processed, "stopped_at": result.stopped_at,
        "component_hashes": components, "decision_components_sha256": canonical_sha256(components),
        "trajectory_sha256": trajectory_sha256(world), "summary": world.summary(),
        "control_dimensions": dimensions, "violence_validation": violence,
        "activity_overlap": activity_overlap(days, violence),
        "action_funnel_by_actor_locality": world.action_funnel_by_actor_locality,
        "insurgent_formations": [
            {"id": f.formation_id, "locality_id": f.locality_id, "personnel": f.personnel,
             "available_personnel": f.available_personnel(), "command": f.command,
             "readiness": f.readiness, "supply_fraction": f.supply_fraction(),
             "availability": f.availability, "status": f.operational_status}
            for f in world.formations.values() if f.organization_id == "insurgent"
        ],
        "top_profile": rows[:35],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=30)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.days, args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runtime_seconds": payload["runtime_seconds"]}), flush=True)
