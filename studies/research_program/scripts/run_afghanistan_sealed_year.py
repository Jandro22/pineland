"""Generate one sealed Afghanistan holdout-year forecast without reading outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studies/afghanistan_2004_2021/scripts"))

from historical_case import HistoricalCoalitionSchedule
from run_transfer_test import build_conditioned_world, initialization_gate
from pineland_sim import Simulation
from pineland_sim.reproducibility import (
    model_sha256,
    repository_state,
    trajectory_sha256,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_sha256(path: Path) -> str:
    return file_sha256(path)


def _active_cells(
    world, *, start_day: float, end_day: float, recorded: bool
) -> list[dict[str, int | str]]:
    cells: set[tuple[str, int]] = set()
    if recorded:
        source = (
            (record.time, record.locality_id)
            for record in world.synthetic_records
            if (
                record.recorded
                and record.event_type in {"contact", "state_based_violence"}
            )
        )
    else:
        source = zip(
            world.state_based_event_times,
            world.state_based_event_localities,
        )
    for event_time, locality_id in source:
        event_time = float(event_time)
        if not (start_day <= event_time < end_day):
            continue
        if locality_id not in world.localities:
            continue
        province = world.district_hierarchy[
            world.localities[locality_id].district_id
        ]["province"]
        cells.add((province, int(event_time // 7)))
    return [
        {"province_id": province, "week_index": week}
        for province, week in sorted(cells)
    ]


def run(
    gate_path: Path, seed: int, strength: float, output: Path
) -> dict:
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if not gate.get("created_without_forecast_outcome_access"):
        raise RuntimeError("gate lacks pre-reveal declaration")
    protocol = gate["protocol"]
    if file_sha256(Path(__file__).resolve()) != protocol["runner_sha256"]:
        raise RuntimeError("runner source differs from sealed protocol")

    expected_pairs = {
        (float(s), int(rng_seed))
        for s in gate["ensemble"]["taliban_initial_strengths"]
        for rng_seed in gate["ensemble"]["stochastic_seeds"]
    }
    if (float(strength), int(seed)) not in expected_pairs:
        raise RuntimeError("seed/strength pair is outside the sealed ensemble")

    frozen = gate["frozen_core"]
    before_hash = model_sha256(ROOT)
    repo = repository_state(ROOT)
    if before_hash != frozen["model_sha256"]:
        raise RuntimeError("model source differs from sealed empirical core")
    if repo["tracked_diff_sha256"] != frozen["tracked_diff_sha256"]:
        raise RuntimeError("tracked repository diff differs from sealed empirical core")

    start_day = float(gate["forecast_window"]["start_day"])
    end_day = float(gate["forecast_window"]["end_day"])
    world, inputs = build_conditioned_world(seed, end_day, strength)
    initial = initialization_gate(world, inputs, strength)
    if not initial["passed"]:
        raise RuntimeError(f"initialization gate failed: {initial}")

    schedule = HistoricalCoalitionSchedule(inputs)
    started = time.perf_counter()
    result = Simulation(
        world,
        policy_hook=lambda state, day: schedule(state, day),
    ).run()
    runtime = time.perf_counter() - started

    after_hash = model_sha256(ROOT)
    if after_hash != before_hash:
        raise RuntimeError("model source changed during sealed forecast")
    final_repo = repository_state(ROOT)
    if final_repo["tracked_diff_sha256"] != frozen["tracked_diff_sha256"]:
        raise RuntimeError("tracked repository diff changed during sealed forecast")

    active_insurgent_ids = {
        organization.organization_id
        for organization in world.organizations.values()
        if organization.kind.value == "insurgent" and organization.status == "active"
    }
    payload = {
        "schema_version": "pineland.afghanistan.sealed_year_run.v1",
        "holdout_year": int(gate["holdout_year"]),
        "gate_sha256": gate_sha256(gate_path),
        "seed": int(seed),
        "taliban_initial_strength": float(strength),
        "forecast_start_day": start_day,
        "forecast_end_day": end_day,
        "runtime_seconds": runtime,
        "events_processed": result.events_processed,
        "stopped_at": result.stopped_at,
        "model_sha256": before_hash,
        "git_commit_at_start": repo["commit_hash"],
        "tracked_diff_sha256": repo["tracked_diff_sha256"],
        "initialization_gate": initial,
        "stock_ledger_residual": world.stock_ledger_residual(),
        "supply_conservation_residual": world.supply_conservation_residual(),
        "population_residual": world.global_accounting_diagnostics()[
            "population_residual"
        ],
        "trajectory_sha256": trajectory_sha256(world),
        "latent_active_cells": _active_cells(
            world, start_day=start_day, end_day=end_day, recorded=False
        ),
        "recorded_active_cells": _active_cells(
            world, start_day=start_day, end_day=end_day, recorded=True
        ),
        "summary": {
            "active_insurgent_organizations": len(active_insurgent_ids),
            "active_insurgent_formation_personnel": sum(
                formation.personnel
                for formation in world.formations.values()
                if formation.organization_id in active_insurgent_ids
                and formation.personnel > 0
            ),
            "mobilized_fighter_pool": sum(
                quantity
                for (owner, _), quantity in world.organization_manpower_pools.items()
                if owner in active_insurgent_ids
            ),
            "mobilized_fighter_pool_supply": sum(
                quantity
                for (owner, _), quantity
                in world.organization_manpower_supply_reserves.items()
                if owner in active_insurgent_ids
            ),
        },
        "empirical_forecast_outcomes_read": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--strength", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.gate, args.seed, args.strength, args.output)
    print(json.dumps({
        "output": str(args.output),
        "runtime_seconds": result["runtime_seconds"],
        "latent_active_cells": len(result["latent_active_cells"]),
        "recorded_active_cells": len(result["recorded_active_cells"]),
        "empirical_forecast_outcomes_read": False,
    }))


if __name__ == "__main__":
    main()
