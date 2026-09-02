from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .config import SimulationConfig
from .experiments import governance_surge, run_paired_experiment
from .generator import generate_pineland
from .simulation import Simulation
from .networks import write_network_snapshot
from .scaling import compare_agent_scales


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pineland-sim", description="Pineland COIN-SIM research engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="write a baseline scenario configuration")
    init.add_argument("path", type=Path)
    run = subparsers.add_parser("run", help="run one stochastic trajectory")
    run.add_argument("--config", type=Path)
    run.add_argument("--output", type=Path, default=Path("outputs/latest"))
    run.add_argument("--agents", type=int)
    run.add_argument("--days", type=float)
    run.add_argument("--seed", type=int)
    run.add_argument("--network-snapshot", type=Path, help="optional social graph debug export")
    run.add_argument("--debug-agent", action="append", default=[])
    run.add_argument("--debug-community", action="append", default=[])
    paired = subparsers.add_parser("paired", help="run matched-seed governance-surge experiment")
    paired.add_argument("--config", type=Path)
    paired.add_argument("--repetitions", type=int, default=10)
    paired.add_argument("--multiplier", type=float, default=1.5)
    paired.add_argument("--agents", type=int)
    paired.add_argument("--days", type=float)
    paired.add_argument("--seed", type=int)
    paired.add_argument("--output", type=Path, default=Path("outputs/paired.json"))
    scale = subparsers.add_parser("scale-check", help="compare macro behavior across agent resolutions")
    scale.add_argument("--config", type=Path)
    scale.add_argument("--agents", type=int, nargs="+", required=True)
    scale.add_argument("--days", type=float, default=30.0)
    scale.add_argument("--output", type=Path, default=Path("outputs/scale-comparison.json"))
    return parser


def _config(args) -> SimulationConfig:
    config = SimulationConfig.load(args.config) if getattr(args, "config", None) else SimulationConfig()
    for argument, attribute in (("agents", "agent_count"), ("days", "horizon_days"), ("seed", "seed")):
        value = getattr(args, argument, None)
        if value is not None and not isinstance(value, list):
            setattr(config, attribute, value)
    config.validate()
    return config


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "init":
        args.path.parent.mkdir(parents=True, exist_ok=True)
        SimulationConfig().save(args.path)
        print(args.path)
        return 0
    config = _config(args)
    if args.command == "run":
        result = Simulation(generate_pineland(config)).run()
        result.world.write_results(args.output)
        if args.network_snapshot:
            write_network_snapshot(result.world, args.network_snapshot,
                                   args.debug_agent or None, args.debug_community or None)
        print(json.dumps(result.world.summary(), indent=2))
        return 0
    if args.command == "scale-check":
        comparison = compare_agent_scales(config, args.agents, args.days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
        print(json.dumps(comparison, indent=2))
        return 0
    outcomes, summary = run_paired_experiment(config, governance_surge(args.multiplier), args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"outcomes": [asdict(x) for x in outcomes], "summary": summary}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
