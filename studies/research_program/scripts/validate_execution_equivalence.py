"""Synthetic exact/distributional validation for alternate execution backends."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.reproducibility import simulation_execution_sha256


def _metrics(world) -> dict[str, float]:
    localities = list(world.localities.values())
    return {
        "weighted_population": world.weighted_population(),
        "cumulative_deaths": world.cumulative_deaths,
        "formation_count": float(len(world.formations)),
        "active_insurgent_organizations": float(sum(
            organization.kind.value == "insurgent"
            and organization.status == "active"
            for organization in world.organizations.values()
        )),
        "mean_government_physical_control": (
            sum(
                locality.control.get("government").physical
                for locality in localities
                if "government" in locality.control
            )
            / max(
                1,
                sum("government" in locality.control for locality in localities),
            )
        ),
        "mean_violence": (
            sum(locality.violence for locality in localities)
            / max(1, len(localities))
        ),
    }


def _run(
    seed: int,
    *,
    days: float,
    agents: int,
    execution_backend: str,
    scheduler_backend: str,
) -> tuple[Simulation, dict[str, float]]:
    config = SimulationConfig(
        seed=seed,
        agent_count=agents,
        locality_count=17,
        horizon_days=days,
        output_mode="ensemble",
    )
    simulation = Simulation(generate_pineland(config))
    simulation.configure_execution(
        execution_backend=execution_backend,
        scheduler_backend=scheduler_backend,
    )
    simulation.run(until=days)
    return simulation, _metrics(simulation.world)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--seed-base", type=int, default=2026090700)
    parser.add_argument("--days", type=float, default=30.0)
    parser.add_argument("--agents", type=int, default=120)
    parser.add_argument(
        "--candidate-backend",
        choices=("reference", "optimized"),
        default="optimized",
    )
    parser.add_argument(
        "--candidate-scheduler",
        choices=("heap", "calendar"),
        default="heap",
    )
    parser.add_argument(
        "--mode", choices=("exact", "distributional"), default="exact"
    )
    parser.add_argument("--relative-tolerance", type=float, default=0.02)
    parser.add_argument("--absolute-tolerance", type=float, default=1e-9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.seeds < 1:
        raise ValueError("seeds must be positive")

    paired = []
    exact_all = True
    for offset in range(args.seeds):
        seed = args.seed_base + offset
        reference, reference_metrics = _run(
            seed,
            days=args.days,
            agents=args.agents,
            execution_backend="reference",
            scheduler_backend="heap",
        )
        candidate, candidate_metrics = _run(
            seed,
            days=args.days,
            agents=args.agents,
            execution_backend=args.candidate_backend,
            scheduler_backend=args.candidate_scheduler,
        )
        exact = (
            simulation_execution_sha256(reference)
            == simulation_execution_sha256(candidate)
        )
        exact_all &= exact
        paired.append({
            "seed": seed,
            "exact_execution_state": exact,
            "reference": reference_metrics,
            "candidate": candidate_metrics,
        })

    metric_checks = {}
    for metric in paired[0]["reference"]:
        reference_values = [row["reference"][metric] for row in paired]
        candidate_values = [row["candidate"][metric] for row in paired]
        reference_mean = statistics.fmean(reference_values)
        candidate_mean = statistics.fmean(candidate_values)
        difference = candidate_mean - reference_mean
        tolerance = (
            args.absolute_tolerance
            + args.relative_tolerance * max(abs(reference_mean), 1e-12)
        )
        metric_checks[metric] = {
            "reference_mean": reference_mean,
            "candidate_mean": candidate_mean,
            "mean_difference": difference,
            "tolerance": tolerance,
            "passed": abs(difference) <= tolerance,
        }
    distributional_pass = all(
        item["passed"] for item in metric_checks.values()
    )
    passed = exact_all if args.mode == "exact" else distributional_pass
    payload = {
        "schema_version": "pineland.execution_equivalence.v1",
        "scientific_status": "synthetic-only validation",
        "historical_fit_used_for_validation": False,
        "mode": args.mode,
        "candidate_backend": args.candidate_backend,
        "candidate_scheduler": args.candidate_scheduler,
        "preregistered_tolerances": {
            "relative": args.relative_tolerance,
            "absolute": args.absolute_tolerance,
        },
        "exact_all": exact_all,
        "distributional_pass": distributional_pass,
        "metric_checks": metric_checks,
        "paired_runs": paired,
        "passed": passed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "passed": passed,
        "exact_all": exact_all,
    }))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
