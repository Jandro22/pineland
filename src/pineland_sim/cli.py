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
from .validation import (calibrate_and_validate, global_sensitivity, model_ladder,
                         parameter_registry, registry_document, bargaining_stress_test,
                         fragmentation_forensic, parameter_recovery_experiment,
                         question_specific_registry)
from .empirical import case_catalog


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
    registry = subparsers.add_parser("parameter-registry", help="write the complete parameter provenance registry")
    registry.add_argument("--config", type=Path)
    registry.add_argument("--output", type=Path, default=Path("outputs/parameter-registry.json"))
    sensitivity = subparsers.add_parser("sensitivity", help="run Latin-hypercube global sensitivity screening")
    sensitivity.add_argument("--config", type=Path)
    sensitivity.add_argument("--samples", type=int, default=32)
    sensitivity.add_argument("--repetitions", type=int, default=1)
    sensitivity.add_argument("--outcomes", nargs="+", default=["government_control", "implementation", "recurrence"])
    sensitivity.add_argument("--parameters", nargs="+")
    sensitivity.add_argument("--agents", type=int, default=250)
    sensitivity.add_argument("--days", type=float, default=180)
    sensitivity.add_argument("--seed", type=int)
    sensitivity.add_argument("--output", type=Path, default=Path("outputs/sensitivity.json"))
    validate = subparsers.add_parser("validate", help="calibrate on one target contract and score a holdout contract")
    validate.add_argument("--config", type=Path)
    validate.add_argument("--training", type=Path, required=True)
    validate.add_argument("--holdout", type=Path, required=True)
    validate.add_argument("--samples", type=int, default=32)
    validate.add_argument("--parameters", nargs="+")
    validate.add_argument("--agents", type=int, default=250)
    validate.add_argument("--days", type=float, default=180)
    validate.add_argument("--seed", type=int)
    validate.add_argument("--output", type=Path, default=Path("outputs/validation.json"))
    ladder = subparsers.add_parser("model-ladder", help="compare null, proxy, reduced, and full models")
    ladder.add_argument("--config", type=Path)
    ladder.add_argument("--targets", type=Path, required=True)
    ladder.add_argument("--agents", type=int, default=250)
    ladder.add_argument("--days", type=float, default=180)
    ladder.add_argument("--seed", type=int)
    ladder.add_argument("--output", type=Path, default=Path("outputs/model-ladder.json"))
    bargaining = subparsers.add_parser("bargaining-stress", help="test agreement ceilings across controlled regimes")
    bargaining.add_argument("--config", type=Path)
    bargaining.add_argument("--replications", type=int, default=100)
    bargaining.add_argument("--months", type=int, default=24)
    bargaining.add_argument("--agents", type=int, default=250)
    bargaining.add_argument("--days", type=float, default=1)
    bargaining.add_argument("--seed", type=int)
    bargaining.add_argument("--output", type=Path, default=Path("outputs/bargaining-stress.json"))
    cases = subparsers.add_parser("case-catalog", help="summarize empirical case packages")
    cases.add_argument("paths", type=Path, nargs="+")
    cases.add_argument("--output", type=Path, default=Path("outputs/case-catalog.json"))
    forensic = subparsers.add_parser("fragmentation-forensic", help="diagnose a fragmentation benchmark miss")
    forensic.add_argument("--config", type=Path)
    forensic.add_argument("--target", type=float, required=True)
    forensic.add_argument("--samples", type=int, default=24)
    forensic.add_argument("--repetitions", type=int, default=2)
    forensic.add_argument("--agents", type=int, default=250)
    forensic.add_argument("--days", type=float, default=180)
    forensic.add_argument("--seed", type=int)
    forensic.add_argument("--output", type=Path, default=Path("outputs/fragmentation-forensic.json"))
    recovery = subparsers.add_parser("parameter-recovery", help="recover a hidden synthetic parameter vector")
    recovery.add_argument("--config", type=Path)
    recovery.add_argument("--samples", type=int, default=24)
    recovery.add_argument("--repetitions", type=int, default=1)
    recovery.add_argument("--parameters", nargs="+")
    recovery.add_argument("--agents", type=int, default=250)
    recovery.add_argument("--days", type=float, default=180)
    recovery.add_argument("--seed", type=int)
    recovery.add_argument("--output", type=Path, default=Path("outputs/parameter-recovery.json"))
    qregistry = subparsers.add_parser("question-registry", help="write a question-specific parameter subset")
    qregistry.add_argument("question", choices=["insurgency_onset", "fragmentation", "recurrence", "foreign_dependence", "control"])
    qregistry.add_argument("--config", type=Path)
    qregistry.add_argument("--output", type=Path, default=Path("outputs/question-registry.json"))
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
    if args.command == "parameter-registry":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(registry_document(config), indent=2), encoding="utf-8")
        print(json.dumps({"parameters": len(parameter_registry(config)), "output": str(args.output)}, indent=2))
        return 0
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
    if args.command == "sensitivity":
        result = global_sensitivity(config, args.outcomes, args.samples, args.parameters, args.repetitions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result["analysis"], indent=2))
        return 0
    if args.command == "validate":
        training = json.loads(args.training.read_text(encoding="utf-8"))
        holdout = json.loads(args.holdout.read_text(encoding="utf-8"))
        result = calibrate_and_validate(config, training, holdout, args.samples, args.parameters)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result["out_of_sample"], indent=2))
        return 0
    if args.command == "model-ladder":
        targets = json.loads(args.targets.read_text(encoding="utf-8"))
        result = model_ladder(config, targets)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({name: item["score"] for name, item in result["models"].items()}, indent=2))
        return 0
    if args.command == "bargaining-stress":
        result = bargaining_stress_test(config, replications=args.replications, months=args.months)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "case-catalog":
        result = case_catalog(args.paths)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "fragmentation-forensic":
        result = fragmentation_forensic(config, args.target, args.samples, args.repetitions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "parameter-recovery":
        result = parameter_recovery_experiment(config, args.parameters, args.samples, args.repetitions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "question-registry":
        result = question_specific_registry(args.question, config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"question": args.question, "parameters": len(result["parameters"])}, indent=2))
        return 0
    outcomes, summary = run_paired_experiment(config, governance_surge(args.multiplier), args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"outcomes": [asdict(x) for x in outcomes], "summary": summary}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
