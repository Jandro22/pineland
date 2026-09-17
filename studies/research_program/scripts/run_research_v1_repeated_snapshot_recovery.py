"""Repeated-world measurement benchmark for Research-v1 hidden-state recovery.

This diagnostic isolates the observation model from conflict dynamics.  Each
replication generates a fresh synthetic Pineland initialization, draws a hidden
truth state, draws an independent prior particle ensemble, generates noisy
reports, and compares a radius-zero localized posterior with the matched prior.

The scientific unit is the synthetic world, not an individual locality.  The
reported paired MSE difference therefore answers whether observations improve
state estimation *on average across known truths* instead of over-interpreting
one convenient or inconvenient realization.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from math import sqrt
from pathlib import Path
import random
import statistics
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.recovery import (  # noqa: E402
    ObservationProcessConfig,
    default_hidden_war_channels,
    direct_hidden_war_channels,
    evaluate_recovery,
    extract_pineland_latent_state,
    generate_observations,
    localized_importance_reconstruction,
    observation_design_diagnostics,
    summarize_posterior_field,
)
from pineland_sim.reproducibility import model_sha256  # noqa: E402
from studies.research_program.scripts.run_research_v1_synthetic_recovery import (  # noqa: E402
    DEFAULT_VARIABLES,
    _base_simulation,
    _clone_initial_state,
)


def _channels(profile: str):
    if profile == "mixed-proxy":
        return default_hidden_war_channels()
    if profile == "direct-oracle":
        return direct_hidden_war_channels(DEFAULT_VARIABLES)
    raise ValueError(profile)


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _paired_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
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
        "posterior_rmse": sqrt(max(0.0, posterior_mse)),
        "prior_rmse": sqrt(max(0.0, prior_mse)),
        "mse_ratio_vs_prior": (
            posterior_mse / prior_mse if prior_mse > 0.0 else None
        ),
        "mse_information_gain_fraction": (
            1.0 - posterior_mse / prior_mse if prior_mse > 0.0 else None
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
            row["posterior_metrics"]["coverage_90"] for row in rows
        ]),
        "prior_coverage_90": _mean([
            row["prior_metrics"]["coverage_90"] for row in rows
        ]),
        "posterior_confidently_wrong_rate": _mean([
            row["posterior_metrics"]["confidently_wrong_rate"] for row in rows
        ]),
        "mean_local_ess_fraction": _mean([
            row["mean_local_ess_fraction"] for row in rows
        ]),
        "minimum_local_ess_fraction": min(
            row["minimum_local_ess_fraction"] for row in rows
        ),
        "interpretation": (
            "Negative paired MSE delta / positive information-gain fraction means "
            "the reports improve estimation on average across synthetic truths. "
            "The normal interval is descriptive pilot uncertainty, not a "
            "preregistered confirmatory test."
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.worlds < 2:
        raise ValueError("repeated recovery requires at least two worlds")
    if args.particles < 2:
        raise ValueError("repeated recovery requires at least two particles")

    profile_rows: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in args.profile
    }
    for world_index in range(args.worlds):
        # Each replication changes both the generated synthetic country seed and
        # the hidden-state draw.  Every observation profile within a replication
        # sees the same truth and matched prior ensemble.
        world_args = argparse.Namespace(**vars(args))
        world_args.model_seed = args.model_seed + 100_003 * world_index
        world_args.initialization_seed = args.initialization_seed + 200_003 * world_index
        base = _base_simulation(world_args)
        truth_particle = _clone_initial_state(
            base,
            namespace=f"research-v1:repeated:truth:{world_index}",
            perturbation_seed=args.truth_seed + 300_007 * world_index,
            perturbation_sd=args.truth_sd,
        )
        truth = extract_pineland_latent_state(truth_particle.world)
        adjacency = {
            locality_id: tuple(sorted(neighbors))
            for locality_id, neighbors in truth_particle.world.adjacency.items()
        }
        particle_fields = []
        for particle_index in range(args.particles):
            particle = _clone_initial_state(
                base,
                namespace=(
                    f"research-v1:repeated:particle:{world_index}:{particle_index}"
                ),
                perturbation_seed=(
                    args.prior_seed
                    + 400_009 * world_index
                    + 7_919 * particle_index
                ),
                perturbation_sd=args.prior_sd,
            )
            particle_fields.append(extract_pineland_latent_state(particle.world))

        uniform = [1.0 / len(particle_fields)] * len(particle_fields)
        for profile_index, profile in enumerate(args.profile):
            channels = _channels(profile)
            design = observation_design_diagnostics(channels, DEFAULT_VARIABLES)
            variables = tuple(design["observation_linked_variables"])
            observations = generate_observations(
                truth,
                state_time=0.0,
                channels=channels,
                process=ObservationProcessConfig(
                    reporting_multiplier=args.reporting_multiplier,
                    geolocation_error_probability=args.geolocation_error_probability,
                    maximum_delay_days=0.0,
                    measurement_noise_multiplier=args.measurement_noise_multiplier,
                    false_report_probability=args.false_report_probability,
                ),
                adjacency=adjacency,
                rng=random.Random(
                    args.observation_seed
                    + 500_009 * world_index
                    + 10_007 * profile_index
                ),
                observation_prefix=f"repeated:{world_index}:{profile}",
            )
            posterior_points, support = localized_importance_reconstruction(
                truth,
                particle_fields,
                observations,
                channels=channels,
                adjacency=adjacency,
                time=0.0,
                variables=variables,
                radius=0,
                assumed_geolocation_error_probability=(
                    args.geolocation_error_probability
                ),
                assumed_measurement_noise_multiplier=(
                    args.measurement_noise_multiplier
                ),
            )
            prior_points = summarize_posterior_field(
                truth,
                particle_fields,
                uniform,
                time=0.0,
                variables=variables,
            )
            posterior_metrics = evaluate_recovery(posterior_points)
            prior_metrics = evaluate_recovery(prior_points)
            posterior_mse = statistics.fmean(
                point.error * point.error for point in posterior_points
            )
            prior_mse = statistics.fmean(
                point.error * point.error for point in prior_points
            )
            profile_rows[profile].append({
                "world_index": world_index,
                "reports": len(observations),
                "posterior_mse": posterior_mse,
                "prior_mse": prior_mse,
                "posterior_metrics": asdict(posterior_metrics),
                "prior_metrics": asdict(prior_metrics),
                "mean_local_ess_fraction": (
                    statistics.fmean(row.ess for row in support) / args.particles
                ),
                "minimum_local_ess_fraction": (
                    min(row.ess for row in support) / args.particles
                ),
            })

    return {
        "schema_version": "pineland.research_v1.repeated_snapshot_recovery.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_pilot_only",
        "question": (
            "Across repeated known synthetic truths, do localized noisy reports "
            "reduce hidden-state estimation error relative to the matched prior?"
        ),
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "historical_case_data_loaded": False,
        },
        "design": {
            "worlds": args.worlds,
            "agents": args.agents,
            "localities": args.localities,
            "particles": args.particles,
            "truth_sd": args.truth_sd,
            "prior_sd": args.prior_sd,
            "reporting_multiplier": args.reporting_multiplier,
            "geolocation_error_probability": args.geolocation_error_probability,
            "measurement_noise_multiplier": args.measurement_noise_multiplier,
            "false_report_probability": args.false_report_probability,
            "profiles": args.profile,
            "localization_radius": 0,
        },
        "profiles": {
            profile: {
                "aggregate": _paired_summary(rows),
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
        default=ROOT / "outputs/research-v1/repeated-snapshot-recovery.json",
    )
    parser.add_argument("--worlds", type=int, default=16)
    parser.add_argument("--agents", type=int, default=60)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--particles", type=int, default=64)
    parser.add_argument("--truth-sd", type=float, default=0.10)
    parser.add_argument("--prior-sd", type=float, default=0.10)
    parser.add_argument("--initial-insurgent-share", type=float, default=0.001)
    parser.add_argument("--reporting-multiplier", type=float, default=1.0)
    parser.add_argument("--geolocation-error-probability", type=float, default=0.0)
    parser.add_argument("--measurement-noise-multiplier", type=float, default=1.0)
    parser.add_argument("--false-report-probability", type=float, default=0.0)
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
