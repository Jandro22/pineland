"""Measure particle-state growth at fixed observation boundaries.

Serialized size is used as a process-transfer/cache-size proxy and fork wall
time as the cloning proxy.  The script is execution-only and never reads
forecast outcomes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.performance import runtime_manifest

RUNNER = Path(__file__).with_name("run_afghanistan_filtered_prospective_2005.py")


def _load_runner():
    spec = importlib.util.spec_from_file_location("afghanistan_growth_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _measure(state, week: int) -> dict:
    payload_started = perf_counter()
    payload = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    serialize_seconds = perf_counter() - payload_started
    fork_started = perf_counter()
    child = state.fork(80_000 + week)
    fork_seconds = perf_counter() - fork_started
    world = state.world
    return {
        "week": int(week),
        "day": float(week * 7),
        "serialized_bytes": len(payload),
        "serialize_seconds": serialize_seconds,
        "fork_seconds": fork_seconds,
        "beliefs": len(world.beliefs),
        "control_beliefs": len(world.control_beliefs),
        "zone_beliefs": len(world.zone_beliefs),
        "presence_beliefs": len(world.presence_beliefs),
        "node_presence_beliefs": len(world.node_presence_beliefs),
        "live_observations": len(world.observations),
        "live_information_relays": len(world.information_relays),
        "active_information_relays": len(world.active_information_relays),
        "corroboration_entries": sum(
            len(history) for history in world.observation_source_index.values()
        ),
        "resource_flow_records": len(world.resource_flows),
        "child_lineage": child.lineage_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20050111)
    parser.add_argument("--strength", type=float, default=7500.0)
    parser.add_argument(
        "--weeks", type=int, nargs="+", default=(0, 13, 26, 39, 52)
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    weeks = sorted(set(args.weeks))
    if not weeks or weeks[0] < 0:
        raise ValueError("weeks must be nonnegative")

    runner = _load_runner()
    case = runner._load_case()
    inputs = runner.load_historical_inputs()
    horizon = max(60.0, 7.0 * max(weeks))
    base_world = runner.generate_pineland(
        runner._config(args.seed, horizon), empirical_geography=case
    )
    state = runner.build_initial_particle(
        seed=args.seed,
        particle_index=0,
        taliban_strength=args.strength,
        horizon=horizon,
        case=case,
        inputs=inputs,
        base_world=base_world,
    ).state
    rows = []
    for week in weeks:
        if week:
            state.advance_to(week * 7.0)
        rows.append(_measure(state, week))
    payload = {
        "schema_version": "pineland.performance.particle_growth.v1",
        "scientific_status": "execution-only",
        "runtime": runtime_manifest(),
        "seed": args.seed,
        "taliban_initial_strength": args.strength,
        "measurements": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "measurements": len(rows)}))


if __name__ == "__main__":
    main()
