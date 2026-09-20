"""Diagnose which synthetic observation channels add recoverable information.

This is a one-snapshot, history-free Research-v1 diagnostic. It uses one fixed
hidden Pineland world and one fixed prior ensemble, then compares the full mixed
proxy observation design with leave-one-channel-out and single-channel
conditions. All conditions are scored on the same target variables, so removing
a channel cannot make a result look better merely by dropping the variables that
became unobserved.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.recovery import (  # noqa: E402
    ObservationChannel,
    ObservationProcessConfig,
    default_hidden_war_channels,
    evaluate_recovery,
    evaluate_recovery_by_variable,
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


def _condition(
    *,
    name: str,
    active_channels: Sequence[ObservationChannel],
    full_target_variables: Sequence[str],
    observations,
    truth,
    particle_fields,
    adjacency,
) -> dict[str, Any]:
    active_names = {channel.name for channel in active_channels}
    active_observations = [
        observation
        for observation in observations
        if observation.channel in active_names
    ]
    uniform = [1.0 / len(particle_fields)] * len(particle_fields)
    prior_points = summarize_posterior_field(
        truth,
        particle_fields,
        uniform,
        time=0.0,
        variables=full_target_variables,
    )
    localized_points = []
    ess_values: list[float] = []
    max_weights: list[float] = []
    reports_by_unit: list[int] = []
    for unit_id in sorted(truth):
        local_observations = [
            observation
            for observation in active_observations
            if observation.reported_unit_id == unit_id
        ]
        log_weights = [
            observation_batch_log_likelihood(
                field,
                local_observations,
                channels=active_channels,
                adjacency=adjacency,
            )
            for field in particle_fields
        ]
        weights = normalize_log_weights(log_weights, strict=True)
        ess_values.append(effective_sample_size(weights))
        max_weights.append(max(weights))
        reports_by_unit.append(len(local_observations))
        localized_points.extend(summarize_posterior_field(
            {unit_id: truth[unit_id]},
            [{unit_id: field[unit_id]} for field in particle_fields],
            weights,
            time=0.0,
            variables=full_target_variables,
        ))

    metrics = evaluate_recovery(localized_points)
    prior_metrics = evaluate_recovery(prior_points)
    design = observation_design_diagnostics(active_channels, DEFAULT_VARIABLES)
    return {
        "name": name,
        "active_channels": sorted(active_names),
        "report_count": len(active_observations),
        "design_rank": design["snapshot_design_rank"],
        "design_nullity": design["snapshot_nullity"],
        "snapshot_unobserved_variables": design["snapshot_unobserved_variables"],
        "metrics": asdict(metrics),
        "prior_metrics": asdict(prior_metrics),
        "relative_to_prior": {
            "rmse_ratio": metrics.rmse / prior_metrics.rmse,
            "coverage_90_delta": metrics.coverage_90 - prior_metrics.coverage_90,
            "interval_width_90_ratio": (
                metrics.mean_interval_width_90 / prior_metrics.mean_interval_width_90
                if prior_metrics.mean_interval_width_90 > 0 else None
            ),
        },
        "support": {
            "mean_ess": sum(ess_values) / len(ess_values),
            "minimum_ess": min(ess_values),
            "mean_ess_fraction": (
                sum(ess_values) / len(ess_values) / len(particle_fields)
            ),
            "maximum_weight": max(max_weights),
            "mean_reports_per_unit": sum(reports_by_unit) / len(reports_by_unit),
        },
        "metrics_by_variable": evaluate_recovery_by_variable(localized_points),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    base = _base_simulation(args)
    truth_particle = _clone_initial_state(
        base,
        namespace="research-v1:channel-ablation:truth",
        perturbation_seed=args.truth_seed,
        perturbation_sd=args.truth_sd,
    )
    truth = extract_pineland_latent_state(truth_particle.world)
    adjacency = {
        locality_id: tuple(sorted(neighbors))
        for locality_id, neighbors in truth_particle.world.adjacency.items()
    }
    particle_fields = []
    for index in range(args.particles):
        particle = _clone_initial_state(
            base,
            namespace=f"research-v1:channel-ablation:particle:{index}",
            perturbation_seed=args.prior_seed + index * 7919,
            perturbation_sd=args.prior_sd,
        )
        particle_fields.append(extract_pineland_latent_state(particle.world))

    channels = default_hidden_war_channels()
    full_design = observation_design_diagnostics(channels, DEFAULT_VARIABLES)
    target_variables = tuple(full_design["observation_linked_variables"])
    observations = generate_observations(
        truth,
        state_time=0.0,
        channels=channels,
        process=ObservationProcessConfig(
            reporting_multiplier=args.reporting_multiplier,
            geolocation_error_probability=0.0,
            maximum_delay_days=0.0,
            measurement_noise_multiplier=1.0,
            false_report_probability=0.0,
        ),
        adjacency=adjacency,
        rng=random.Random(args.observation_seed),
        observation_prefix="channel-ablation",
    )

    conditions: list[tuple[str, tuple[ObservationChannel, ...]]] = [
        ("full", tuple(channels)),
    ]
    for channel in channels:
        conditions.append((
            f"without::{channel.name}",
            tuple(item for item in channels if item.name != channel.name),
        ))
    for channel in channels:
        conditions.append((f"only::{channel.name}", (channel,)))

    results = {
        name: _condition(
            name=name,
            active_channels=active,
            full_target_variables=target_variables,
            observations=observations,
            truth=truth,
            particle_fields=particle_fields,
            adjacency=adjacency,
        )
        for name, active in conditions
    }
    full_rmse = results["full"]["metrics"]["rmse"]
    for result in results.values():
        result["relative_to_full"] = {
            "rmse_ratio": result["metrics"]["rmse"] / full_rmse,
            "coverage_90_delta": (
                result["metrics"]["coverage_90"]
                - results["full"]["metrics"]["coverage_90"]
            ),
        }

    return {
        "schema_version": "pineland.research_v1.channel_ablation.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_diagnostic_only",
        "question": (
            "Which mixed-proxy observation channels add independent recoverable "
            "information, and which primarily reduce particle support?"
        ),
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "historical_case_data_loaded": False,
        },
        "design": {
            "agents": args.agents,
            "particles": args.particles,
            "prior_sd": args.prior_sd,
            "truth_sd": args.truth_sd,
            "reporting_multiplier": args.reporting_multiplier,
            "target_variables": list(target_variables),
            "full_observation_design": full_design,
        },
        "conditions": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/research-v1/channel-ablation.json",
    )
    parser.add_argument("--agents", type=int, default=60)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=1.0)
    parser.add_argument("--particles", type=int, default=64)
    parser.add_argument("--prior-sd", type=float, default=0.10)
    parser.add_argument("--truth-sd", type=float, default=0.10)
    parser.add_argument("--initial-insurgent-share", type=float, default=0.001)
    parser.add_argument("--reporting-multiplier", type=float, default=1.0)
    parser.add_argument("--model-seed", type=int, default=2026091701)
    parser.add_argument("--initialization-seed", type=int, default=2026091702)
    parser.add_argument("--truth-seed", type=int, default=2026091703)
    parser.add_argument("--prior-seed", type=int, default=2026091704)
    parser.add_argument("--observation-seed", type=int, default=2026091705)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.particles < 2:
        raise ValueError("channel ablation requires at least two particles")
    payload = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    full = payload["conditions"]["full"]
    leave_one_out = {
        name.removeprefix("without::"): {
            "rmse_ratio_vs_full": result["relative_to_full"]["rmse_ratio"],
            "coverage_90_delta_vs_full": result["relative_to_full"]["coverage_90_delta"],
            "design_rank": result["design_rank"],
        }
        for name, result in payload["conditions"].items()
        if name.startswith("without::")
    }
    print(json.dumps({
        "output": str(args.output),
        "full_rmse_ratio_vs_prior": full["relative_to_prior"]["rmse_ratio"],
        "full_coverage_90": full["metrics"]["coverage_90"],
        "leave_one_out": leave_one_out,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
