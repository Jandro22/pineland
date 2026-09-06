"""Synthetic identification test for persistent insurgent operational posture.

This study never opens historical case outcomes. It intervenes only on the
already-existing Organization.persistence trait and asks whether the new
movement state behaves as theorized without switching off ordinary mobility or
violating stock/supply accounting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.reproducibility import model_sha256  # noqa: E402


DEFAULT_OUT = (
    ROOT / "studies" / "research_program" /
    "operational_posture_identification_recovery.json"
)
SEEDS = tuple(2026090601 + index for index in range(8))


def _insurgent_formations(world):
    return [
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    ]


def run_cell(seed: int, persistence: float, horizon_days: float) -> dict:
    config = SimulationConfig(
        seed=seed,
        agent_count=600,
        locality_count=34,
        horizon_days=horizon_days,
        output_mode="calibration",
    )
    config.logistics.reallocation_rate = .18
    world = generate_pineland(config)
    for organization in world.organizations.values():
        if organization.kind is OrganizationKind.INSURGENT:
            organization.persistence = persistence
    command_sequences: dict[str, list[str]] = {}
    occupied_localities: set[str] = set()
    sampled_times: set[float] = set()

    def hook(state, time):
        # Policy hooks execute immediately before each scheduled event. Command
        # boundaries therefore expose the posture chosen at the previous
        # strategic reconsideration, without inspecting hidden future state.
        if abs((time / state.config.intervals.command) -
               round(time / state.config.intervals.command)) > 1e-9:
            return
        if time in sampled_times:
            return
        sampled_times.add(time)
        for formation in _insurgent_formations(state):
            occupied_localities.add(formation.locality_id)
            command_sequences.setdefault(formation.formation_id, []).append(
                formation.operational_posture
            )

    Simulation(world, policy_hook=hook).run()
    switches = 0
    opportunities = 0
    established_runs: list[int] = []
    for sequence in command_sequences.values():
        sequence = [value for value in sequence if value != "portfolio"]
        if not sequence:
            continue
        run_length = 1
        for previous, current in zip(sequence, sequence[1:]):
            opportunities += 1
            if current != previous:
                switches += 1
                established_runs.append(run_length)
                run_length = 1
            else:
                run_length += 1
        established_runs.append(run_length)
    reallocation_orders = [
        order for order in world.movement_orders.values()
        if order.purpose == "reallocation"
        and world.organizations[order.organization_id].kind is OrganizationKind.INSURGENT
    ]
    return {
        "seed": seed,
        "persistence": persistence,
        "switches": switches,
        "established_posture_transitions": opportunities,
        "switch_rate": switches / max(1, opportunities),
        "mean_posture_run_command_boundaries": (
            statistics.mean(established_runs) if established_runs else 0.0
        ),
        "reallocation_orders": len(reallocation_orders),
        "occupied_localities": len(occupied_localities),
        "stock_ledger_residual": world.stock_ledger_residual(),
        "supply_conservation_residual": world.supply_conservation_residual(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--days", type=float, default=45.0)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    before = model_sha256(ROOT)
    cells = {
        "low_persistence": [
            run_cell(seed, 0.0, args.days) for seed in SEEDS
        ],
        "high_persistence": [
            run_cell(seed, .95, args.days) for seed in SEEDS
        ],
    }
    after = model_sha256(ROOT)

    def aggregate(rows):
        return {
            "mean_switch_rate": statistics.mean(row["switch_rate"] for row in rows),
            "mean_posture_run_command_boundaries": statistics.mean(
                row["mean_posture_run_command_boundaries"] for row in rows
            ),
            "mean_reallocation_orders": statistics.mean(
                row["reallocation_orders"] for row in rows
            ),
            "mean_occupied_localities": statistics.mean(
                row["occupied_localities"] for row in rows
            ),
        }

    low = aggregate(cells["low_persistence"])
    high = aggregate(cells["high_persistence"])
    checks = {
        "model_hash_stable": before == after,
        "higher_persistence_reduces_switch_rate": (
            high["mean_switch_rate"] < .5 * low["mean_switch_rate"]
        ),
        "higher_persistence_extends_posture_runs": (
            high["mean_posture_run_command_boundaries"]
            > low["mean_posture_run_command_boundaries"]
        ),
        "mobility_remains_live_low": all(
            row["reallocation_orders"] > 0 for row in cells["low_persistence"]
        ),
        "mobility_remains_live_high": all(
            row["reallocation_orders"] > 0 for row in cells["high_persistence"]
        ),
        "stock_ledgers_clean": all(
            abs(row["stock_ledger_residual"]) <= 1e-5
            for rows in cells.values() for row in rows
        ),
        "supply_ledgers_clean": all(
            abs(row["supply_conservation_residual"]) <= 1e-5
            for rows in cells.values() for row in rows
        ),
    }
    payload = {
        "schema_version": "1.0",
        "status": "synthetic_identification_recovery_not_empirical_fit",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "intervention": {
            "parameter": "Organization.persistence",
            "low": 0.0,
            "high": .95,
            "note": (
                "Extreme synthetic interventions identify mechanism direction; "
                "production persistence values are unchanged."
            ),
        },
        "horizon_days": args.days,
        "seeds": list(SEEDS),
        "model_sha256_start": before,
        "model_sha256_end": after,
        "aggregate": {
            "low_persistence": low,
            "high_persistence": high,
        },
        "checks": checks,
        "passed": all(checks.values()),
        "cells": cells,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output.relative_to(ROOT)),
        "passed": payload["passed"],
        "aggregate": payload["aggregate"],
        "checks": checks,
    }, indent=2))


if __name__ == "__main__":
    main()
