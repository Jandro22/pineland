"""Run the frozen Afghanistan core through 2005 without scoring target outcomes.

This runner intentionally writes only model predictions and structural diagnostics.
The 2005 empirical panel is opened only by the separate scorer after all members
exist, preserving a clean reveal boundary for the preregistered prospective gate.
"""
from __future__ import annotations

import argparse
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
from pineland_sim.reproducibility import model_sha256, repository_state, trajectory_sha256

FORECAST_START_DAY = 366.0
FORECAST_END_DAY = 731.0


def _active_cells(world, *, recorded: bool) -> list[dict[str, int | str]]:
    cells: set[tuple[str, int]] = set()
    if recorded:
        source = (
            (record.time, record.locality_id)
            for record in world.synthetic_records
            if record.recorded and record.event_type in {"contact", "state_based_violence"}
        )
    else:
        source = zip(world.state_based_event_times, world.state_based_event_localities)
    for event_time, locality_id in source:
        if not (FORECAST_START_DAY <= float(event_time) < FORECAST_END_DAY):
            continue
        if locality_id not in world.localities:
            continue
        province = world.district_hierarchy[
            world.localities[locality_id].district_id
        ]["province"]
        cells.add((province, int(float(event_time) // 7)))
    return [
        {"province_id": province, "week_index": week}
        for province, week in sorted(cells)
    ]


def run(seed: int, strength: float, output: Path) -> dict:
    before_hash = model_sha256(ROOT)
    repo = repository_state(ROOT)
    if repo["tracked_diff_sha256"] != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855":
        raise RuntimeError("tracked source/study diff changed after prospective gate freeze")
    world, inputs = build_conditioned_world(seed, FORECAST_END_DAY, strength)
    initial = initialization_gate(world, inputs, strength)
    if not initial["passed"]:
        raise RuntimeError(f"initialization gate failed: {initial}")
    schedule = HistoricalCoalitionSchedule(inputs)
    started = time.perf_counter()
    result = Simulation(world, policy_hook=lambda state, day: schedule(state, day)).run()
    runtime = time.perf_counter() - started
    after_hash = model_sha256(ROOT)
    if after_hash != before_hash:
        raise RuntimeError("model hash changed during prospective run")
    payload = {
        "schema_version": "1.0",
        "seed": seed,
        "taliban_initial_strength": strength,
        "forecast_start_day": FORECAST_START_DAY,
        "forecast_end_day": FORECAST_END_DAY,
        "runtime_seconds": runtime,
        "events_processed": result.events_processed,
        "stopped_at": result.stopped_at,
        "model_sha256": before_hash,
        "git_commit": repo["commit_hash"],
        "tracked_diff_sha256": repo["tracked_diff_sha256"],
        "initialization_gate": initial,
        "stock_ledger_residual": world.stock_ledger_residual(),
        "supply_conservation_residual": world.supply_conservation_residual(),
        "trajectory_sha256": trajectory_sha256(world),
        "latent_active_cells_2005": _active_cells(world, recorded=False),
        "recorded_active_cells_2005": _active_cells(world, recorded=True),
        "summary": {
            "active_insurgent_formation_personnel": sum(
                f.personnel for f in world.formations.values()
                if f.organization_id == "insurgent" and f.personnel > 0
            ),
            "mobilized_fighter_pool": sum(
                quantity for (owner, _), quantity in world.organization_manpower_pools.items()
                if owner == "insurgent"
            ),
            "mobilized_fighter_pool_supply": sum(
                quantity for (owner, _), quantity in world.organization_manpower_supply_reserves.items()
                if owner == "insurgent"
            ),
        },
        "empirical_2005_outcomes_read": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--strength", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.seed, args.strength, args.output)
    print(json.dumps({
        "output": str(args.output),
        "runtime_seconds": result["runtime_seconds"],
        "latent_active_cells_2005": len(result["latent_active_cells_2005"]),
        "recorded_active_cells_2005": len(result["recorded_active_cells_2005"]),
    }))


if __name__ == "__main__":
    main()
