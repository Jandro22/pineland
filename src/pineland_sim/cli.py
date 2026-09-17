from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

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
from .research_audit import (causal_ledger_audit, foreign_withdrawal_diagnostics,
                             language_factorial, long_horizon_diagnostics,
                             null_and_extreme_checks, output_mode_benchmark,
                             recording_calibration, resolution_ladder,
                             scheduler_audit, topology_ablation,
                             truth_firewall_check, truth_firewall_battery,
                             representative_agent_audit, publication_readiness_report,
                             long_horizon_ensemble)
from .empirical import case_catalog, first_paper_experiment_spec


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
    run.add_argument("--output-mode", choices=["forensic", "ensemble", "calibration"],
                     help="retained output fidelity; dynamics are unchanged")
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
    audit = subparsers.add_parser("audit", help="run executable causal-integrity and measurement audits")
    audit.add_argument("--config", type=Path)
    audit.add_argument("--agents", type=int, default=250)
    audit.add_argument("--days", type=float, default=30.0)
    audit.add_argument("--recording-repetitions", type=int, default=200)
    audit.add_argument("--output", type=Path, default=Path("outputs/research-audit.json"))
    benchmark = subparsers.add_parser("output-benchmark", help="benchmark lossless output modes")
    benchmark.add_argument("--config", type=Path)
    benchmark.add_argument("--agents", type=int, default=250)
    benchmark.add_argument("--days", type=float, default=30.0)
    benchmark.add_argument("--seed", type=int)
    benchmark.add_argument("--output", type=Path, default=Path("outputs/output-benchmark.json"))
    topology = subparsers.add_parser("topology-ablation", help="compare original, rewired, and random-mixing graphs")
    topology.add_argument("--config", type=Path)
    topology.add_argument("--agents", type=int, default=250)
    topology.add_argument("--days", type=float, default=30.0)
    topology.add_argument("--seed", type=int)
    topology.add_argument("--swaps", type=int)
    topology.add_argument("--output", type=Path, default=Path("outputs/topology-ablation.json"))
    language = subparsers.add_parser("language-factorial", help="run the eight-cell language factorial")
    language.add_argument("--config", type=Path)
    language.add_argument("--agents", type=int, default=250)
    language.add_argument("--days", type=float, default=30.0)
    language.add_argument("--seed", type=int)
    language.add_argument("--repetitions", type=int, default=8)
    language.add_argument("--workers", type=int, help="parallel workers (default: up to 8 cores)")
    language.add_argument("--output", type=Path, default=Path("outputs/language-factorial.json"))
    resolution = subparsers.add_parser("resolution-audit", help="run the powered resolution ladder")
    resolution.add_argument("--config", type=Path)
    resolution.add_argument("--agents", type=int, nargs="+", default=[25_000, 75_000, 250_000])
    resolution.add_argument("--days", type=float, default=30.0)
    resolution.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    resolution.add_argument("--output", type=Path, default=Path("outputs/resolution-audit.json"))
    longrun = subparsers.add_parser("long-horizon", help="run multi-year pathology diagnostics")
    longrun.add_argument("--config", type=Path)
    longrun.add_argument("--agents", type=int, default=250)
    longrun.add_argument("--years", type=int, default=5)
    longrun.add_argument("--seed", type=int)
    longrun.add_argument("--seeds", type=int, nargs="+")
    longrun.add_argument("--output", type=Path, default=Path("outputs/long-horizon.json"))
    paper = subparsers.add_parser("paper-spec", help="emit the Research-v1 first-paper evidence contract")
    paper.add_argument("--output", type=Path, default=Path("outputs/first-paper-spec.json"))
    reproduce = subparsers.add_parser("reproduce", help="run a frozen research reproduction entry point")
    reproduce.add_argument("target", choices=["paper1"])
    reproduce.add_argument("--profile", choices=["smoke", "development"], default="smoke")
    reproduce.add_argument("--output", type=Path)
    firewall = subparsers.add_parser("truth-firewall", help="run the decision-level hidden-state metamorphic battery")
    firewall.add_argument("--config", type=Path)
    firewall.add_argument("--agents", type=int, default=250)
    firewall.add_argument("--days", type=float, default=2.0)
    firewall.add_argument("--seed", type=int)
    firewall.add_argument("--output", type=Path, default=Path("outputs/truth-firewall.json"))
    representative = subparsers.add_parser("representative-audit", help="audit representative-agent and household semantics")
    representative.add_argument("--config", type=Path)
    representative.add_argument("--agents", type=int, default=250)
    representative.add_argument("--days", type=float, default=2.0)
    representative.add_argument("--seed", type=int)
    representative.add_argument("--output", type=Path, default=Path("outputs/representative-audit.json"))
    readiness = subparsers.add_parser("readiness-report", help="produce the publication-readiness report")
    readiness.add_argument("--config", type=Path)
    readiness.add_argument("--agents", type=int, default=250)
    readiness.add_argument("--days", type=float, default=2.0)
    readiness.add_argument("--years", type=int, default=1)
    readiness.add_argument("--seed", type=int)
    readiness.add_argument("--language-repetitions", type=int, default=8)
    readiness.add_argument("--workers", type=int, help="parallel workers (default: up to 8 cores)")
    readiness.add_argument("--full", action="store_true", help="also run powered resolution/sensitivity/recovery batteries")
    readiness.add_argument("--long-horizon", action="store_true", help="include the multi-year pathology run")
    readiness.add_argument("--output", type=Path, default=Path("outputs/publication-readiness.json"))
    return parser


def _config(args) -> SimulationConfig:
    config = SimulationConfig.load(args.config) if getattr(args, "config", None) else SimulationConfig()
    for argument, attribute in (("agents", "agent_count"), ("days", "horizon_days"), ("seed", "seed"),
                                ("output_mode", "output_mode")):
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
    if args.command == "audit":
        config.agent_count = args.agents
        config.horizon_days = args.days
        result = {
            "truth_firewall": truth_firewall_check(config, min(2.0, args.days)),
            "truth_firewall_battery": truth_firewall_battery(config, min(2.0, args.days)),
            "representative_agents": representative_agent_audit(config, min(2.0, args.days)),
            "scheduler": scheduler_audit(config, args.days),
            "causal_ledger": causal_ledger_audit(config, min(7.0, args.days)),
            "null_and_extreme": null_and_extreme_checks(config),
            "recording": recording_calibration(config, args.recording_repetitions),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "output-benchmark":
        result = output_mode_benchmark(config, args.days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "topology-ablation":
        result = topology_ablation(config, args.days, args.swaps)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "language-factorial":
        result = language_factorial(config, args.days, args.repetitions, args.workers)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "resolution-audit":
        config.agent_count = max(args.agents)
        config.horizon_days = args.days
        result = resolution_ladder(config, args.agents, args.seeds, args.days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"agent_counts": result["agent_counts"], "seeds": result["seeds"],
                          "comparisons": result["comparisons"]}, indent=2))
        return 0
    if args.command == "long-horizon":
        result = (long_horizon_ensemble(config, args.years, args.seeds)
                  if args.seeds else long_horizon_diagnostics(config, args.years))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"years": result["years"], "warnings": result["warnings"],
                          "all_pass": result.get("all_pass", not result["warnings"]),
                          "stock_residual": result.get("stock_residual"),
                          "supply_residual": result.get("supply_residual"),
                          "final_distributions": result.get("final_distributions")}, indent=2))
        return 0
    if args.command == "paper-spec":
        result = first_paper_experiment_spec()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "reproduce":
        root = Path(__file__).resolve().parents[2]
        runner = root / "studies/research_program/scripts/run_research_v1_synthetic_recovery.py"
        if not runner.exists():
            raise FileNotFoundError(
                "paper1 reproduction requires the Pineland source repository with studies/"
            )
        output = args.output or (
            Path("outputs/research-v1/reproduce-paper1-smoke.json")
            if args.profile == "smoke"
            else Path("outputs/research-v1/reproduce-paper1-development.json")
        )
        command = [sys.executable, str(runner), "--output", str(output)]
        if args.profile == "smoke":
            command += [
                "--agents", "60", "--particles", "8", "--days", "14",
                "--interval-days", "7", "--scenario", "nominal",
            ]
        else:
            command += [
                "--agents", "120", "--particles", "32", "--days", "28",
                "--interval-days", "7", "--scenario", "all",
                "--localization-radius-sweep", "0", "1", "2",
                "--state-localization", "component",
            ]
        completed = subprocess.run(command, cwd=root, check=False)
        return int(completed.returncode)
    if args.command == "truth-firewall":
        result = truth_firewall_battery(config, args.days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "representative-audit":
        result = representative_agent_audit(config, args.days)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "readiness-report":
        result = publication_readiness_report(
            config, horizon_days=args.days, long_horizon_years=args.years,
            language_repetitions=args.language_repetitions, run_expensive=args.full,
            run_long_horizon=args.long_horizon, workers=args.workers)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"methods_paper_readiness_score": result["methods_paper_readiness_score"],
                          "substantive_paper_readiness_score": result["substantive_paper_readiness_score"],
                          "closed_questions": result["closed_questions"],
                          "open_or_conditional_questions": result["open_or_conditional_questions"],
                          "runtime_seconds": result["runtime_seconds"]}, indent=2))
        return 0
    outcomes, summary = run_paired_experiment(config, governance_surge(args.multiplier), args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"outcomes": [asdict(x) for x in outcomes], "summary": summary}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
