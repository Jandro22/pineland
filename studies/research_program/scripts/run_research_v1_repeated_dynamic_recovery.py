"""Repeat the live-dynamics Research-v1 recovery experiment across known worlds.

This is the Level-1 bridge between the cheap repeated snapshot assay and the
single-world dynamic benchmark.  Every replication generates a fresh synthetic
Pineland country, propagates one matched prior ensemble through live dynamics,
and scores localized reconstruction against the known latent trajectory.

Historical case data are never loaded.  Results are development evidence only
until world counts, particle counts, observation severities, and claim gates are
frozen before a confirmatory batch.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.recovery import ObservationProcessConfig  # noqa: E402
from pineland_sim.reproducibility import model_sha256  # noqa: E402
from studies.research_program.scripts.run_research_v1_synthetic_recovery import (  # noqa: E402
    _base_simulation,
    _prior_ensemble_history,
    _run_localized_reconstruction,
    _truth_and_reports,
)


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    prior_mse = _mean([row["prior_mse"] for row in rows])
    posterior_mse = _mean([row["posterior_mse"] for row in rows])
    deltas = [row["posterior_mse"] - row["prior_mse"] for row in rows]
    mean_delta = _mean(deltas)
    se_delta = (
        statistics.stdev(deltas) / sqrt(len(deltas)) if len(deltas) > 1 else None
    )
    return {
        "worlds": len(rows),
        "prior_mse": prior_mse,
        "posterior_mse": posterior_mse,
        "prior_rmse": sqrt(max(0.0, prior_mse)),
        "posterior_rmse": sqrt(max(0.0, posterior_mse)),
        "mse_ratio_vs_prior": posterior_mse / prior_mse if prior_mse > 0 else None,
        "mse_information_gain_fraction": (
            1.0 - posterior_mse / prior_mse if prior_mse > 0 else None
        ),
        "mean_paired_mse_delta": mean_delta,
        "paired_mse_delta_se": se_delta,
        "paired_mse_delta_normal_95": (
            [mean_delta - 1.96 * se_delta, mean_delta + 1.96 * se_delta]
            if se_delta is not None else None
        ),
        "world_win_rate": _mean([
            row["posterior_mse"] < row["prior_mse"] for row in rows
        ]),
        "posterior_coverage_90": _mean([
            row["posterior_coverage_90"] for row in rows
        ]),
        "prior_coverage_90": _mean([
            row["prior_coverage_90"] for row in rows
        ]),
        "posterior_confidently_wrong_rate": _mean([
            row["posterior_confidently_wrong_rate"] for row in rows
        ]),
        "mean_support_fraction": _mean([
            row["mean_ess"] / row["particles"] for row in rows
        ]),
        "minimum_support_fraction": min(
            row["minimum_ess"] / row["particles"] for row in rows
        ),
        "interpretation": (
            "Positive information-gain fraction means localized reconstruction "
            "reduced trajectory MSE relative to the matched no-assimilation prior "
            "on average across known synthetic worlds. The normal interval is a "
            "development diagnostic, not preregistered confirmatory inference."
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.worlds < 2:
        raise ValueError("repeated dynamic recovery requires at least two worlds")
    if args.particles < 2:
        raise ValueError("repeated dynamic recovery requires at least two particles")
    if args.maximum_delay_days >= args.interval_days:
        raise ValueError("maximum-delay-days must be smaller than interval-days")

    process = ObservationProcessConfig(
        reporting_multiplier=args.reporting_multiplier,
        geolocation_error_probability=args.geolocation_error_probability,
        maximum_delay_days=args.maximum_delay_days,
        measurement_noise_multiplier=args.measurement_noise_multiplier,
        false_report_probability=args.false_report_probability,
        geographic_reporting_bias_strength=args.geographic_reporting_bias_strength,
    )
    profile_rows: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in args.profile
    }

    for world_index in range(args.worlds):
        world_args = argparse.Namespace(**vars(args))
        world_args.model_seed = args.model_seed + 100_003 * world_index
        world_args.initialization_seed = (
            args.initialization_seed + 200_003 * world_index
        )
        world_args.truth_seed = args.truth_seed + 300_007 * world_index
        world_args.prior_seed = args.prior_seed + 400_009 * world_index
        world_args.observation_seed = args.observation_seed + 500_009 * world_index

        base = _base_simulation(world_args)
        prior_history = _prior_ensemble_history(base, world_args)

        for profile in args.profile:
            world_args.observation_profile = profile
            truth_states, reports, adjacency = _truth_and_reports(
                base, world_args, process
            )
            result = _run_localized_reconstruction(
                prior_history,
                truth_states,
                reports,
                adjacency,
                world_args,
            )
            linked_metrics = result["metrics_observation_linked"]
            prior_metrics = result["prior_metrics_observation_linked"]
            profile_rows[profile].append({
                "world_index": world_index,
                "particles": args.particles,
                "reports": len(reports),
                "posterior_mse": linked_metrics["rmse"] ** 2,
                "prior_mse": prior_metrics["rmse"] ** 2,
                "posterior_coverage_90": linked_metrics["coverage_90"],
                "prior_coverage_90": prior_metrics["coverage_90"],
                "posterior_confidently_wrong_rate": (
                    linked_metrics["confidently_wrong_rate"]
                ),
                "mean_ess": result["support"]["mean_ess"],
                "minimum_ess": result["support"]["minimum_ess"],
                "maximum_weight": result["support"]["maximum_weight"],
            })

    return {
        "schema_version": "pineland.research_v1.repeated_dynamic_recovery.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_development_only",
        "question": (
            "Across repeated live synthetic conflict trajectories, does localized "
            "report assimilation reduce hidden-state reconstruction error relative "
            "to the matched dynamically propagated prior?"
        ),
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "historical_case_data_loaded": False,
        },
        "design": {
            "worlds": args.worlds,
            "agents": args.agents,
            "localities": args.localities,
            "days": args.days,
            "interval_days": args.interval_days,
            "particles": args.particles,
            "truth_sd": args.truth_sd,
            "prior_sd": args.prior_sd,
            "state_localization": args.state_localization,
            "localization_radius": args.localization_radius,
            "profiles": args.profile,
            "observation_process": {
                "reporting_multiplier": args.reporting_multiplier,
                "geolocation_error_probability": args.geolocation_error_probability,
                "maximum_delay_days": args.maximum_delay_days,
                "measurement_noise_multiplier": args.measurement_noise_multiplier,
                "false_report_probability": args.false_report_probability,
                "geographic_reporting_bias_strength": (
                    args.geographic_reporting_bias_strength
                ),
            },
        },
        "profiles": {
            profile: {
                "aggregate": _aggregate(rows),
                "worlds": rows,
            }
            for profile, rows in profile_rows.items()
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/research-v1/repeated-dynamic-recovery.json",
    )
    parser.add_argument("--worlds", type=int, default=4)
    parser.add_argument("--agents", type=int, default=60)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--interval-days", type=float, default=7.0)
    parser.add_argument("--particles", type=int, default=16)
    parser.add_argument("--truth-sd", type=float, default=0.10)
    parser.add_argument("--prior-sd", type=float, default=0.10)
    parser.add_argument("--initial-insurgent-share", type=float, default=0.001)
    parser.add_argument("--reporting-multiplier", type=float, default=1.0)
    parser.add_argument("--geolocation-error-probability", type=float, default=0.08)
    parser.add_argument("--maximum-delay-days", type=float, default=3.0)
    parser.add_argument("--measurement-noise-multiplier", type=float, default=1.0)
    parser.add_argument("--false-report-probability", type=float, default=0.0)
    parser.add_argument("--geographic-reporting-bias-strength", type=float, default=0.0)
    parser.add_argument("--localization-radius", type=int, default=0)
    parser.add_argument(
        "--state-localization",
        choices=["locality", "component"],
        default="component",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=["mixed-proxy", "direct-oracle"],
        default=None,
    )
    parser.add_argument("--model-seed", type=int, default=2026091701)
    parser.add_argument("--initialization-seed", type=int, default=2026091702)
    parser.add_argument("--truth-seed", type=int, default=2026091703)
    parser.add_argument("--prior-seed", type=int, default=2026091704)
    parser.add_argument("--observation-seed", type=int, default=2026091705)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.profile is None:
        args.profile = ["mixed-proxy", "direct-oracle"]
    payload = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "profiles": {
            profile: result["aggregate"]
            for profile, result in payload["profiles"].items()
        },
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
