"""Measure whole-world particle-weight collapse as observation dimension grows.

This diagnostic freezes the latent world at one synthetic time slice. It does
not test dynamics. Instead it asks a narrower question: how quickly does the
current global particle representation lose effective support as reports from
more localities are multiplied into one joint likelihood?

The experiment is useful precisely because a failure cannot be blamed on
historical data, transition-model misspecification, or reporting delay.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
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
    observation_batch_log_likelihood,
    observation_design_diagnostics,
    summarize_posterior_field,
)
from pineland_sim.reproducibility import model_sha256  # noqa: E402
from pineland_sim.state_estimation import (  # noqa: E402
    effective_sample_size,
    normalize_log_weights,
)

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


def _rmse(points) -> float:
    return evaluate_recovery(points).rmse


def run(args: argparse.Namespace) -> dict[str, Any]:
    base = _base_simulation(args)
    truth_particle = _clone_initial_state(
        base,
        namespace="research-v1:weight-diagnostic:truth",
        perturbation_seed=args.truth_seed,
        perturbation_sd=args.truth_sd,
    )
    truth = extract_pineland_latent_state(truth_particle.world)
    units = sorted(truth)
    adjacency = {
        locality_id: tuple(sorted(neighbors))
        for locality_id, neighbors in truth_particle.world.adjacency.items()
    }

    particle_fields = []
    for index in range(args.particles):
        particle = _clone_initial_state(
            base,
            namespace=f"research-v1:weight-diagnostic:particle:{index}",
            perturbation_seed=args.prior_seed + index * 7919,
            perturbation_sd=args.prior_sd,
        )
        particle_fields.append(extract_pineland_latent_state(particle.world))

    rows: list[dict[str, Any]] = []
    for profile_index, profile in enumerate(args.profile):
        channels = _channels(profile)
        design = observation_design_diagnostics(channels, DEFAULT_VARIABLES)
        linked_variables = tuple(design["observation_linked_variables"])
        for reporting_index, reporting_multiplier in enumerate(args.reporting_multiplier):
            process = ObservationProcessConfig(
                reporting_multiplier=reporting_multiplier,
                geolocation_error_probability=0.0,
                maximum_delay_days=0.0,
                measurement_noise_multiplier=1.0,
                false_report_probability=0.0,
            )
            observations = generate_observations(
                truth,
                state_time=0.0,
                channels=channels,
                process=process,
                adjacency=adjacency,
                rng=random.Random(
                    args.observation_seed
                    + 1009 * profile_index
                    + 100_003 * reporting_index
                ),
                observation_prefix=f"weight:{profile}:{reporting_multiplier:g}",
            )
            for requested_particles in args.particle_count_sweep:
                particle_count = min(args.particles, int(requested_particles))
                active_fields = particle_fields[:particle_count]
                for requested_count in args.locality_count_sweep:
                    count = min(len(units), requested_count)
                    selected = set(units[:count])
                    selected_truth = {
                        unit_id: truth[unit_id] for unit_id in units[:count]
                    }
                    selected_fields = [
                        {unit_id: field[unit_id] for unit_id in units[:count]}
                        for field in active_fields
                    ]
                    selected_observations = [
                        observation
                        for observation in observations
                        if observation.true_unit_id in selected
                    ]
                    log_weights = [
                        observation_batch_log_likelihood(
                            field,
                            selected_observations,
                            channels=channels,
                            adjacency=adjacency,
                        )
                        for field in active_fields
                    ]
                    weights = normalize_log_weights(log_weights, strict=True)
                    prior_weights = [1.0 / particle_count] * particle_count
                    posterior_points = summarize_posterior_field(
                        selected_truth,
                        selected_fields,
                        weights,
                        time=0.0,
                        variables=linked_variables,
                    )
                    prior_points = summarize_posterior_field(
                        selected_truth,
                        selected_fields,
                        prior_weights,
                        time=0.0,
                        variables=linked_variables,
                    )
                    localized_points = []
                    local_ess_values = []
                    local_max_weights = []
                    for unit_id in units[:count]:
                        local_observations = [
                            observation
                            for observation in selected_observations
                            if observation.reported_unit_id == unit_id
                        ]
                        local_log_weights = [
                            observation_batch_log_likelihood(
                                field,
                                local_observations,
                                channels=channels,
                                adjacency=adjacency,
                            )
                            for field in active_fields
                        ]
                        local_weights = normalize_log_weights(
                            local_log_weights, strict=True
                        )
                        local_ess_values.append(effective_sample_size(local_weights))
                        local_max_weights.append(max(local_weights))
                        localized_points.extend(summarize_posterior_field(
                            {unit_id: truth[unit_id]},
                            [{unit_id: field[unit_id]} for field in active_fields],
                            local_weights,
                            time=0.0,
                            variables=linked_variables,
                        ))
                    posterior_metrics = evaluate_recovery(posterior_points)
                    prior_metrics = evaluate_recovery(prior_points)
                    localized_metrics = evaluate_recovery(localized_points)
                    rows.append({
                        "profile": profile,
                        "reporting_multiplier": reporting_multiplier,
                        "localities": count,
                        "reports": len(selected_observations),
                        "particle_count": particle_count,
                        "ess": effective_sample_size(weights),
                        "ess_fraction": effective_sample_size(weights) / particle_count,
                        "maximum_weight": max(weights),
                        "top_five_weight": sum(sorted(weights, reverse=True)[:5]),
                        "posterior_rmse": posterior_metrics.rmse,
                        "prior_rmse": prior_metrics.rmse,
                        "rmse_ratio_vs_prior": (
                            posterior_metrics.rmse / prior_metrics.rmse
                            if prior_metrics.rmse > 0 else None
                        ),
                        "posterior_coverage_90": posterior_metrics.coverage_90,
                        "prior_coverage_90": prior_metrics.coverage_90,
                        "posterior_width_90": posterior_metrics.mean_interval_width_90,
                        "prior_width_90": prior_metrics.mean_interval_width_90,
                        "localized_rmse": localized_metrics.rmse,
                        "localized_rmse_ratio_vs_prior": (
                            localized_metrics.rmse / prior_metrics.rmse
                            if prior_metrics.rmse > 0 else None
                        ),
                        "localized_coverage_90": localized_metrics.coverage_90,
                        "localized_width_90": localized_metrics.mean_interval_width_90,
                        "mean_local_ess": sum(local_ess_values) / len(local_ess_values),
                        "minimum_local_ess": min(local_ess_values),
                        "maximum_local_weight": max(local_max_weights),
                        "snapshot_design_rank": design["snapshot_design_rank"],
                        "linked_variables": len(linked_variables),
                    })

    return {
        "schema_version": "pineland.research_v1.weight_collapse.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_diagnostic_only",
        "question": (
            "How does global particle support degrade as the number of simultaneously "
            "observed localities and reports increases?"
        ),
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "historical_case_data_loaded": False,
        },
        "design": {
            "agents": args.agents,
            "particles": args.particles,
            "particle_count_sweep": args.particle_count_sweep,
            "prior_sd": args.prior_sd,
            "truth_sd": args.truth_sd,
            "profiles": args.profile,
            "reporting_multipliers": args.reporting_multiplier,
            "locality_count_sweep": args.locality_count_sweep,
        },
        "rows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/research-v1/weight-collapse.json",
    )
    parser.add_argument("--agents", type=int, default=60)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--particles", type=int, default=64)
    parser.add_argument(
        "--particle-count-sweep",
        type=int,
        nargs="+",
        default=None,
        help="nested particle prefixes evaluated from one maximum-size prior ensemble",
    )
    parser.add_argument("--prior-sd", type=float, default=0.10)
    parser.add_argument("--truth-sd", type=float, default=0.10)
    parser.add_argument("--initial-insurgent-share", type=float, default=0.001)
    parser.add_argument(
        "--profile",
        action="append",
        choices=["mixed-proxy", "direct-oracle"],
        default=None,
    )
    parser.add_argument(
        "--reporting-multiplier",
        type=float,
        action="append",
        default=None,
    )
    parser.add_argument(
        "--locality-count-sweep",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8, 17],
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
    if args.reporting_multiplier is None:
        args.reporting_multiplier = [1.0, 0.5, 0.25]
    if args.particle_count_sweep is None:
        args.particle_count_sweep = [
            count for count in (8, 16, 32, 64) if count <= args.particles
        ]
        if args.particles not in args.particle_count_sweep:
            args.particle_count_sweep.append(args.particles)
    if any(count < 2 for count in args.particle_count_sweep):
        raise ValueError("particle-count-sweep values must be at least two")
    if max(args.particle_count_sweep) > args.particles:
        raise ValueError("particle-count-sweep cannot exceed --particles")
    payload = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "rows": len(payload["rows"]),
        "worst_ess_fraction": min(row["ess_fraction"] for row in payload["rows"]),
        "conditions_with_ess_below_10_percent": sum(
            row["ess_fraction"] < 0.10 for row in payload["rows"]
        ),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
