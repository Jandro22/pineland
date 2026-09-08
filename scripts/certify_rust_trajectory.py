"""Compare native trajectory component inventories with the Python oracle.

This is deliberately stricter than comparing a handful of summary numbers.
The native CLI exports the same typed component inventory used by the
initialization certificate, while Python advances the authoritative reference
simulation to the same calendar boundary.  A mismatch is reported by the
first component key and the certificate fails closed.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.reproducibility import canonical_sha256
from pineland_sim.simulation import Simulation
from certify_rust_initialization import (
    SEEDS,
    binary_path,
    python_components,
)


def _native(
    binary: Path,
    config_path: Path,
    seed: int,
    horizon: float,
    max_events: int | None,
) -> dict:
    command = [
        str(binary),
        "certify-trajectory",
        "--config",
        str(config_path),
        "--seed",
        str(seed),
        "--until",
        repr(float(horizon)),
    ]
    if max_events is not None:
        command.extend(["--max-events", str(max_events)])
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _python(
    config: SimulationConfig,
    horizon: float,
    max_events: int | None,
) -> dict:
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.run(until=horizon, max_events=max_events)
    return {
        "counts": {
            "people": len(world.persons),
            "households": len(world.households),
            "communities": len(world.social_communities),
            "organizations": len(world.organizations),
            "formations": len(world.formations),
            "posts": len(world.security_posts),
            "patrols": len(world.patrols),
            "localities": len(world.localities),
            "microzones": len(world.microzones),
            "footholds": len(world.local_footholds),
            "manpower_pools": len(world.organization_manpower_pools),
            "logistics_sources": len(world.supply_sources),
            "belief_state": len(world.beliefs) + len(world.control_beliefs),
            "zone_belief_state": len(world.zone_beliefs),
            "social_edges": len(world.social_edges),
            "command_edges": len(world.command_edges),
            "leaders": len(world.leaders),
            "political_institutions": len(world.political_institutions),
            "party_branches": len(world.party_branches),
            "local_elites": len(world.local_elites),
            "foreign_states": len(world.foreign_states),
            "border_segments": len(world.border_segments),
            "foreign_beliefs": len(world.foreign_beliefs),
            "interpreter_brokers": len(world.interpreter_brokers),
            "organization_relations": len(world.organization_relations),
            "scheduler": len(simulation.scheduler),
        },
        "components": python_components(world, simulation),
    }


def _first_difference(left, right, path: str = ""):
    if type(left) is not type(right):
        return path or "$", left, right
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                return child, left.get(key), right.get(key)
            difference = _first_difference(left[key], right[key], child)
            if difference is not None:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return path, f"length={len(left)}", f"length={len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            difference = _first_difference(left_item, right_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if left != right:
        return path or "$", left, right
    return None


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scenarios" / "baseline.json")
    parser.add_argument("--agent-count", type=int, default=300)
    parser.add_argument("--locality-count", type=int, default=34)
    parser.add_argument(
        "--seeds",
        type=str,
        default=",".join(str(seed) for seed in SEEDS),
        help="comma-separated predeclared seeds",
    )
    parser.add_argument(
        "--horizons",
        type=str,
        default="0.25,0.5,1,2,7,30,90",
        help="comma-separated calendar horizons in days",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="compare the state after this many popped events (diagnostic mode)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    horizons = [float(item) for item in args.horizons.split(",") if item.strip()]
    base = json.loads(args.config.read_text(encoding="utf-8"))
    base.update(
        agent_count=args.agent_count,
        locality_count=args.locality_count,
        burn_in_days=0.0,
        output_mode="calibration",
    )
    binary = binary_path()
    results = []
    with tempfile.TemporaryDirectory(prefix="pineland-trajectory-") as temp:
        config_path = Path(temp) / "config.json"
        config_path.write_text(json.dumps(base, sort_keys=True), encoding="utf-8")
        for seed in seeds:
            for horizon in horizons:
                values = dict(base)
                values["seed"] = seed
                # The configuration contract requires a positive default
                # horizon, while the trajectory certificate deliberately
                # includes the exact t=0 boundary.
                values["horizon_days"] = max(horizon, 1e-9)
                config = SimulationConfig.from_dict(values)
                config.validate()
                native = _native(binary, config_path, seed, horizon, args.max_events)
                reference = _python(config, horizon, args.max_events)
                count_difference = _first_difference(
                    reference["counts"], native.get("counts", {})
                )
                native_components = native.get("components", {})
                native_components = dict(native_components)
                native_components["scheduler"] = native.get("scheduler")
                # The initialization inventory deliberately contains a few
                # native-only diagnostic columns.  Exactness is assessed on
                # the common, Python-defined semantic contract; extra native
                # columns are still retained in the native artifact.
                native_common_components = {
                    key: native_components.get(key)
                    for key in reference["components"]
                }
                component_difference = _first_difference(
                    reference["components"], native_common_components
                )
                difference = component_difference or count_difference
                row = {
                    "seed": seed,
                    "horizon_days": horizon,
                    "status": "passed" if difference is None else "failed",
                    "native_state_hash": native.get("state_hash"),
                    "native_decision_hash": native.get("decision_hash"),
                }
                if difference is not None:
                    path, expected, actual = difference
                    row.update(
                        {
                            "first_difference": path,
                            "python_value": expected,
                            "rust_value": actual,
                        }
                    )
                    if count_difference is not None and component_difference is not None:
                        row.update(
                            {
                                "first_count_difference": count_difference[0],
                                "python_count_value": count_difference[1],
                                "rust_count_value": count_difference[2],
                                "first_component_difference": component_difference[0],
                                "python_component_value": component_difference[1],
                                "rust_component_value": component_difference[2],
                            }
                        )
                    results.append(row)
                    break
                results.append(row)

    failures = [row for row in results if row["status"] != "passed"]
    payload = {
        "schema": "pineland-rust-trajectory-certification-v1",
        "status": "failed" if failures else "passed",
        "binary": str(binary),
        "seeds": seeds,
        "horizons_days": horizons,
        "max_events": args.max_events,
        "requested_cases": len(seeds) * len(horizons),
        "completed_cases": len(results),
        "mismatch_count": len(failures),
        "results": results,
        "certificate_sha256": canonical_sha256(results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
