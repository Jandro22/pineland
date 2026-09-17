"""Run the Research-v1 full-Pineland synthetic hidden-state recovery benchmark.

This runner is intentionally history-free.  One live Pineland trajectory is
the known world, an observation process hides and corrupts that truth, and the
existing SequentialParticleFilter must reconstruct the latent state from only
the resulting reports.  The truth projection is used exclusively for scoring.

Historical Afghanistan/Nepal artifacts are not imported here.  Passing this
benchmark licenses a synthetic recovery statement only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.config import SimulationConfig  # noqa: E402
from pineland_sim.entities import CONTROL_DIMENSIONS, clamp  # noqa: E402
from pineland_sim.generator import generate_pineland  # noqa: E402
from pineland_sim.recovery import (  # noqa: E402
    MisspecificationScenario,
    ObservationProcessConfig,
    PosteriorPoint,
    SyntheticObservation,
    default_hidden_war_channels,
    direct_hidden_war_channels,
    direct_proxy_baseline,
    evaluate_recovery,
    evaluate_recovery_by_variable,
    extract_pineland_latent_state,
    generate_observations,
    localized_importance_reconstruction,
    observation_batch_log_likelihood,
    observation_design_diagnostics,
    observation_diagnostics,
    posterior_identifiability,
    summarize_posterior_field,
)
from pineland_sim.reproducibility import model_sha256  # noqa: E402
from pineland_sim.simulation import Simulation, SimulationParticle  # noqa: E402
from pineland_sim.state_estimation import (  # noqa: E402
    AssimilationObservation,
    Particle,
    SequentialParticleFilter,
    particle_weights,
)


DEFAULT_VARIABLES = tuple(
    [f"government.{dimension}" for dimension in CONTROL_DIMENSIONS]
    + [f"insurgent.{dimension}" for dimension in CONTROL_DIMENSIONS]
    + [
        "insurgent.foothold",
        "insurgent.embeddedness",
        "insurgent.fighter_capacity",
        "insurgent.supply_capacity",
    ]
)


SCENARIOS = {
    "nominal": MisspecificationScenario(
        "nominal",
        assumed_geolocation_error_probability=0.08,
        assumed_measurement_noise_multiplier=1.0,
    ),
    "exact-coordinates": MisspecificationScenario(
        "exact-coordinates",
        assumed_geolocation_error_probability=0.0,
        assumed_measurement_noise_multiplier=1.0,
    ),
    "underestimated-noise": MisspecificationScenario(
        "underestimated-noise",
        assumed_geolocation_error_probability=0.08,
        assumed_measurement_noise_multiplier=0.50,
    ),
    "no-anchors": MisspecificationScenario(
        "no-anchors",
        assumed_geolocation_error_probability=0.08,
        assumed_measurement_noise_multiplier=1.0,
        dropped_channels=("government_admin_anchor", "insurgent_physical_anchor"),
    ),
}


def _channels(args: argparse.Namespace):
    if args.observation_profile == "mixed-proxy":
        return default_hidden_war_channels()
    if args.observation_profile == "direct-oracle":
        return direct_hidden_war_channels(DEFAULT_VARIABLES)
    raise ValueError(f"unknown observation profile: {args.observation_profile}")


@dataclass(slots=True)
class RecoveryParticleState:
    """Live simulator particle plus immutable analysis snapshots by state time."""

    particle: SimulationParticle
    history: dict[float, dict[str, dict[str, float]]]

    def advance_to(self, time: float) -> None:
        if time > self.particle.time + 1e-12:
            self.particle.advance_to(time)
        self.history[float(time)] = extract_pineland_latent_state(self.particle.world)

    def fork(self, child_index: int) -> "RecoveryParticleState":
        return type(self)(
            self.particle.fork(child_index),
            dict(self.history),
        )


def _configure_simulation(simulation: Simulation) -> Simulation:
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
        execution_backend="optimized",
    )
    return simulation


def _perturb_control_state(
    simulation: Simulation,
    *,
    seed: int,
    sd: float,
) -> None:
    """Draw latent initial control uncertainty without changing mechanisms.

    The same generated country, organizations, networks, and structural
    parameters are retained.  Only the hidden control state is perturbed.
    This is an initial-state prior, not parameter fitting.
    """

    if sd <= 0:
        return
    rng = random.Random(seed)
    for locality_id in sorted(simulation.world.localities):
        locality = simulation.world.localities[locality_id]
        for actor in sorted(locality.control):
            vector = locality.control[actor]
            for dimension in CONTROL_DIMENSIONS:
                setattr(
                    vector,
                    dimension,
                    clamp(float(getattr(vector, dimension)) + rng.gauss(0.0, sd)),
                )


def _base_simulation(args: argparse.Namespace) -> Simulation:
    config = SimulationConfig(
        seed=args.model_seed,
        initialization_seed=args.initialization_seed,
        horizon_days=float(args.days),
        agent_count=int(args.agents),
        locality_count=int(args.localities),
        burn_in_days=0.0,
        include_insurgency=True,
        initial_insurgent_share=float(args.initial_insurgent_share),
        output_mode="calibration",
    )
    config.validate()
    simulation = _configure_simulation(Simulation(generate_pineland(config)))
    simulation.initialize()
    return simulation


def _clone_initial_state(
    base: Simulation,
    *,
    namespace: str,
    perturbation_seed: int,
    perturbation_sd: float,
) -> SimulationParticle:
    simulation = base.clone(
        stream_namespace=namespace,
        copy_output_archives=False,
    )
    _perturb_control_state(
        simulation,
        seed=perturbation_seed,
        sd=perturbation_sd,
    )
    return SimulationParticle(simulation, lineage_id=namespace)


def _boundaries(days: float, interval_days: float) -> list[float]:
    if interval_days <= 0:
        raise ValueError("observation interval must be positive")
    values = [0.0]
    time = interval_days
    while time < days - 1e-12:
        values.append(float(time))
        time += interval_days
    if values[-1] < days - 1e-12:
        values.append(float(days))
    return values


def _truth_and_reports(
    base: Simulation,
    args: argparse.Namespace,
    process: ObservationProcessConfig,
) -> tuple[
    dict[float, dict[str, dict[str, float]]],
    list[SyntheticObservation],
    dict[str, tuple[str, ...]],
]:
    channels = _channels(args)
    truth = _clone_initial_state(
        base,
        namespace="research-v1:truth",
        perturbation_seed=args.truth_seed,
        perturbation_sd=args.prior_sd,
    )
    boundaries = _boundaries(args.days, args.interval_days)
    states: dict[float, dict[str, dict[str, float]]] = {
        0.0: extract_pineland_latent_state(truth.world)
    }
    adjacency = {
        locality_id: tuple(sorted(neighbors))
        for locality_id, neighbors in truth.world.adjacency.items()
    }
    observability = {
        locality_id: max(1e-12, float(locality.observability))
        for locality_id, locality in truth.world.localities.items()
    }
    mean_observability = sum(observability.values()) / max(1, len(observability))
    reporting_multipliers = {
        locality_id: value / mean_observability
        for locality_id, value in observability.items()
    }
    reports: list[SyntheticObservation] = []
    rng = random.Random(args.observation_seed)
    # Do not generate a final-boundary report that cannot arrive within this
    # experiment.  Every generated observation therefore has a legitimate
    # chance to influence a later state estimate.
    for index, state_time in enumerate(boundaries):
        if index > 0:
            truth.advance_to(state_time)
            states[state_time] = extract_pineland_latent_state(truth.world)
        if index == len(boundaries) - 1:
            continue
        reports.extend(generate_observations(
            states[state_time],
            state_time=state_time,
            channels=channels,
            process=process,
            adjacency=adjacency,
            rng=rng,
            observation_prefix="research-v1",
            unit_reporting_multipliers=reporting_multipliers,
        ))
    reports.sort(key=lambda observation: (
        observation.arrival_time,
        observation.state_time,
        observation.observation_id,
    ))
    return states, reports, adjacency


def _active_channels(scenario: MisspecificationScenario, args: argparse.Namespace):
    dropped = set(scenario.dropped_channels)
    return tuple(
        channel
        for channel in _channels(args)
        if channel.name not in dropped
    )


def _run_scenario(
    base: Simulation,
    truth_states: dict[float, dict[str, dict[str, float]]],
    reports: Sequence[SyntheticObservation],
    adjacency: dict[str, tuple[str, ...]],
    scenario: MisspecificationScenario,
    no_assimilation: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    active_channels = _active_channels(scenario, args)
    active_channel_names = {channel.name for channel in active_channels}
    active_reports = [
        observation for observation in reports
        if observation.channel in active_channel_names
    ]
    particles: list[Particle[RecoveryParticleState]] = []
    for index in range(args.particles):
        state = RecoveryParticleState(
            _clone_initial_state(
                base,
                namespace=f"research-v1:particle:{index}",
                perturbation_seed=args.prior_seed + index * 7919,
                perturbation_sd=args.prior_sd,
            ),
            {},
        )
        state.history[0.0] = extract_pineland_latent_state(state.particle.world)
        particles.append(Particle(state))

    assumed_geo = (
        scenario.assumed_geolocation_error_probability
        if scenario.assumed_geolocation_error_probability is not None
        else args.geolocation_error_probability
    )
    assumed_noise = (
        scenario.assumed_measurement_noise_multiplier
        if scenario.assumed_measurement_noise_multiplier is not None
        else args.measurement_noise_multiplier
    )

    def transition(state: RecoveryParticleState, time: float) -> None:
        state.advance_to(time)

    def likelihood(
        state: RecoveryParticleState,
        batch: tuple[SyntheticObservation, ...],
    ) -> float:
        by_state_time: dict[float, list[SyntheticObservation]] = {}
        for observation in batch:
            by_state_time.setdefault(observation.state_time, []).append(observation)
        score = 0.0
        for state_time, observations in by_state_time.items():
            candidate = state.history.get(float(state_time))
            if candidate is None:
                raise RuntimeError(
                    f"particle lacks latent snapshot for report time {state_time}"
                )
            score += observation_batch_log_likelihood(
                candidate,
                observations,
                channels=active_channels,
                adjacency=adjacency,
                assumed_geolocation_error_probability=float(assumed_geo),
                assumed_measurement_noise_multiplier=float(assumed_noise),
            )
        return score

    filter_ = SequentialParticleFilter(
        particles,
        transition=transition,
        log_likelihood=likelihood,
        rng=random.Random(args.filter_seed),
        ess_fraction=args.ess_fraction,
        fork_state=lambda state, child_index: state.fork(child_index),
    )

    boundaries = _boundaries(args.days, args.interval_days)
    consumed: set[str] = set()
    posterior_points: list[PosteriorPoint] = []
    filter_updates: list[dict[str, Any]] = []
    latest_fields = [
        extract_pineland_latent_state(particle.state.particle.world)
        for particle in filter_.particles
    ]
    latest_weights = particle_weights(filter_.particles)

    for boundary in boundaries[1:]:
        batch = tuple(
            observation
            for observation in active_reports
            if (
                observation.observation_id not in consumed
                and observation.arrival_time <= boundary + 1e-12
            )
        )
        consumed.update(observation.observation_id for observation in batch)
        update = filter_.assimilate(AssimilationObservation(
            boundary,
            batch,
            split="training",
            observation_id=f"{scenario.name}:through:{boundary:g}",
        ))
        filter_updates.append(asdict(update) | {"reports_assimilated": len(batch)})
        latest_weights = particle_weights(filter_.particles)
        latest_fields = [
            extract_pineland_latent_state(particle.state.particle.world)
            for particle in filter_.particles
        ]
        posterior_points.extend(summarize_posterior_field(
            truth_states[boundary],
            latest_fields,
            latest_weights,
            time=boundary,
            variables=DEFAULT_VARIABLES,
        ))

    overall = evaluate_recovery(posterior_points)
    by_variable = evaluate_recovery_by_variable(posterior_points)
    design = observation_design_diagnostics(active_channels, DEFAULT_VARIABLES)
    linked = set(design["observation_linked_variables"])
    linked_points = [point for point in posterior_points if point.variable in linked]
    unlinked_points = [point for point in posterior_points if point.variable not in linked]
    grouped_metrics = {
        "all_targets": asdict(overall),
        "observation_linked_targets": (
            asdict(evaluate_recovery(linked_points)) if linked_points else None
        ),
        "snapshot_unobserved_targets": (
            asdict(evaluate_recovery(unlinked_points)) if unlinked_points else None
        ),
    }
    identifiability = posterior_identifiability(
        latest_fields,
        latest_weights,
        variables=DEFAULT_VARIABLES,
    )
    baseline = direct_proxy_baseline(
        active_reports,
        active_channels,
        truth_points=posterior_points,
    )
    prior_metrics = no_assimilation["metrics"]
    relative = {
        "rmse_ratio": (
            overall.rmse / prior_metrics["rmse"]
            if prior_metrics["rmse"] > 0 else None
        ),
        "coverage_90_delta": overall.coverage_90 - prior_metrics["coverage_90"],
        "interval_width_90_ratio": (
            overall.mean_interval_width_90 / prior_metrics["mean_interval_width_90"]
            if prior_metrics["mean_interval_width_90"] > 0 else None
        ),
        "confidently_wrong_rate_delta": (
            overall.confidently_wrong_rate - prior_metrics["confidently_wrong_rate"]
        ),
    }
    return {
        "scenario": asdict(scenario),
        "status": "synthetic_full_pineland_hidden_state_recovery_not_historical_validation",
        "reports_available": len(active_reports),
        "reports_assimilated": len(consumed),
        "filter_updates": filter_updates,
        "metrics": asdict(overall),
        "metric_groups": grouped_metrics,
        "metrics_by_variable": by_variable,
        "observation_design": design,
        "identifiability": identifiability,
        "direct_report_baseline": baseline,
        "relative_to_no_assimilation": relative,
        "posterior_points": [asdict(point) for point in posterior_points],
    }


def _prior_ensemble_history(
    base: Simulation,
    args: argparse.Namespace,
) -> dict[float, list[dict[str, dict[str, float]]]]:
    """Propagate one matched prior ensemble once and retain latent snapshots."""

    states: list[RecoveryParticleState] = []
    for index in range(args.particles):
        state = RecoveryParticleState(
            _clone_initial_state(
                base,
                namespace=f"research-v1:particle:{index}",
                perturbation_seed=args.prior_seed + index * 7919,
                perturbation_sd=args.prior_sd,
            ),
            {},
        )
        state.history[0.0] = extract_pineland_latent_state(state.particle.world)
        states.append(state)
    history = {
        0.0: [state.history[0.0] for state in states]
    }
    for boundary in _boundaries(args.days, args.interval_days)[1:]:
        for state in states:
            state.advance_to(boundary)
        history[boundary] = [
            extract_pineland_latent_state(state.particle.world)
            for state in states
        ]
    return history


def _run_no_assimilation_baseline(
    prior_history: dict[float, list[dict[str, dict[str, float]]]],
    truth_states: dict[float, dict[str, dict[str, float]]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Score the matched prior ensemble without consuming observations."""

    particle_count = len(next(iter(prior_history.values())))
    weights = [1.0 / particle_count] * particle_count
    points: list[PosteriorPoint] = []
    for boundary in _boundaries(args.days, args.interval_days)[1:]:
        points.extend(summarize_posterior_field(
            truth_states[boundary],
            prior_history[boundary],
            weights,
            time=boundary,
            variables=DEFAULT_VARIABLES,
        ))
    overall = evaluate_recovery(points)
    design = observation_design_diagnostics(_channels(args), DEFAULT_VARIABLES)
    linked = set(design["observation_linked_variables"])
    linked_points = [point for point in points if point.variable in linked]
    unlinked_points = [point for point in points if point.variable not in linked]
    return {
        "name": "matched_prior_no_assimilation",
        "status": "synthetic_baseline",
        "metrics": asdict(overall),
        "metric_groups": {
            "all_targets": asdict(overall),
            "observation_linked_targets": asdict(evaluate_recovery(linked_points)),
            "snapshot_unobserved_targets": asdict(evaluate_recovery(unlinked_points)),
        },
        "metrics_by_variable": evaluate_recovery_by_variable(points),
        "posterior_points": [asdict(point) for point in points],
    }


def _run_localized_reconstruction(
    prior_history: dict[float, list[dict[str, dict[str, float]]]],
    truth_states: dict[float, dict[str, dict[str, float]]],
    reports: Sequence[SyntheticObservation],
    adjacency: dict[str, tuple[str, ...]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run a localized fixed-lag reconstruction over coherent prior worlds."""

    channels = _channels(args)
    design = observation_design_diagnostics(channels, DEFAULT_VARIABLES)
    linked = set(design["observation_linked_variables"])
    points: list[PosteriorPoint] = []
    support = []
    prior_points: list[PosteriorPoint] = []
    uniform = [1.0 / args.particles] * args.particles
    report_times = sorted({observation.state_time for observation in reports})
    for state_time in report_times:
        time_reports = [
            observation for observation in reports
            if observation.state_time == state_time
        ]
        local_points, local_support = localized_importance_reconstruction(
            truth_states[state_time],
            prior_history[state_time],
            time_reports,
            channels=channels,
            adjacency=adjacency,
            time=state_time,
            variables=DEFAULT_VARIABLES,
            radius=args.localization_radius,
            assumed_geolocation_error_probability=args.geolocation_error_probability,
            assumed_measurement_noise_multiplier=args.measurement_noise_multiplier,
        )
        points.extend(local_points)
        support.extend(local_support)
        prior_points.extend(summarize_posterior_field(
            truth_states[state_time],
            prior_history[state_time],
            uniform,
            time=state_time,
            variables=DEFAULT_VARIABLES,
        ))
    metrics = evaluate_recovery(points)
    prior_metrics = evaluate_recovery(prior_points)
    linked_points = [point for point in points if point.variable in linked]
    linked_prior_points = [
        point for point in prior_points if point.variable in linked
    ]
    linked_metrics = evaluate_recovery(linked_points)
    linked_prior_metrics = evaluate_recovery(linked_prior_points)
    return {
        "status": "localized_marginal_approximation_not_joint_posterior",
        "radius": args.localization_radius,
        "metrics": asdict(metrics),
        "metrics_observation_linked": asdict(linked_metrics),
        "prior_metrics_same_targets": asdict(prior_metrics),
        "prior_metrics_observation_linked": asdict(linked_prior_metrics),
        "relative_to_prior": {
            "rmse_ratio": metrics.rmse / prior_metrics.rmse,
            "linked_rmse_ratio": linked_metrics.rmse / linked_prior_metrics.rmse,
            "coverage_90_delta": metrics.coverage_90 - prior_metrics.coverage_90,
        },
        "support": {
            "unit_time_updates": len(support),
            "mean_ess": sum(row.ess for row in support) / len(support),
            "minimum_ess": min(row.ess for row in support),
            "maximum_weight": max(row.maximum_weight for row in support),
            "mean_reports_per_local_posterior": (
                sum(row.reports for row in support) / len(support)
            ),
        },
        "support_rows": [asdict(row) for row in support],
        "metrics_by_variable": evaluate_recovery_by_variable(points),
        "posterior_points": [asdict(point) for point in points],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.days <= 0 or args.interval_days <= 0:
        raise ValueError("days and interval-days must be positive")
    if args.particles < 2:
        raise ValueError("synthetic recovery requires at least two particles")
    if args.maximum_delay_days >= args.interval_days:
        # This is supported mathematically, but the standard research-v1
        # benchmark intentionally guarantees at least one later boundary at
        # which every report can arrive.
        raise ValueError("maximum-delay-days must be smaller than interval-days")

    process = ObservationProcessConfig(
        reporting_multiplier=args.reporting_multiplier,
        geolocation_error_probability=args.geolocation_error_probability,
        maximum_delay_days=args.maximum_delay_days,
        measurement_noise_multiplier=args.measurement_noise_multiplier,
        false_report_probability=args.false_report_probability,
        geographic_reporting_bias_strength=args.geographic_reporting_bias_strength,
    )
    base = _base_simulation(args)
    truth_states, reports, adjacency = _truth_and_reports(base, args, process)
    prior_history = _prior_ensemble_history(base, args)
    no_assimilation = _run_no_assimilation_baseline(
        prior_history, truth_states, args
    )
    localized_reconstruction = _run_localized_reconstruction(
        prior_history,
        truth_states,
        reports,
        adjacency,
        args,
    )
    scenario_names = list(SCENARIOS) if args.scenario == ["all"] else args.scenario
    unknown = sorted(set(scenario_names) - set(SCENARIOS))
    if unknown:
        raise ValueError(f"unknown scenarios: {unknown}")
    results = {
        name: _run_scenario(
            base,
            truth_states,
            reports,
            adjacency,
            SCENARIOS[name],
            no_assimilation,
            args,
        )
        for name in scenario_names
    }
    payload = {
        "schema_version": "pineland.research_v1.synthetic_recovery.v1",
        "study_id": "research_v1_hidden_war_synthetic_recovery",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_only_no_historical_claim",
        "research_question": (
            "When the true conflict state is known, which hidden political and "
            "organizational conditions can Pineland recover from incomplete, "
            "noisy observations, with calibrated uncertainty?"
        ),
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "runner": str(Path(__file__).resolve().relative_to(ROOT)).replace("\\", "/"),
            "historical_case_data_loaded": False,
        },
        "design": {
            "agents": args.agents,
            "localities": args.localities,
            "days": args.days,
            "interval_days": args.interval_days,
            "particles": args.particles,
            "ess_fraction": args.ess_fraction,
            "prior_control_sd": args.prior_sd,
            "variables": list(DEFAULT_VARIABLES),
            "observation_process": asdict(process),
            "observation_profile": args.observation_profile,
            "channels": [channel.to_dict() for channel in _channels(args)],
            "observation_design": observation_design_diagnostics(
                _channels(args), DEFAULT_VARIABLES
            ),
        },
        "observation_diagnostics": observation_diagnostics(reports),
        "truth_boundaries": sorted(truth_states),
        "no_assimilation_baseline": no_assimilation,
        "localized_reconstruction": localized_reconstruction,
        "scenario_results": results,
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run full-Pineland synthetic hidden-state recovery."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/research-v1/synthetic-recovery.json",
    )
    parser.add_argument("--agents", type=int, default=120)
    parser.add_argument("--localities", type=int, default=17)
    parser.add_argument("--days", type=float, default=28.0)
    parser.add_argument("--interval-days", type=float, default=7.0)
    parser.add_argument("--particles", type=int, default=16)
    parser.add_argument("--ess-fraction", type=float, default=0.50)
    parser.add_argument("--prior-sd", type=float, default=0.10)
    parser.add_argument("--initial-insurgent-share", type=float, default=0.001)
    parser.add_argument("--reporting-multiplier", type=float, default=1.0)
    parser.add_argument("--geolocation-error-probability", type=float, default=0.08)
    parser.add_argument("--maximum-delay-days", type=float, default=3.0)
    parser.add_argument("--measurement-noise-multiplier", type=float, default=1.0)
    parser.add_argument("--false-report-probability", type=float, default=0.0)
    parser.add_argument(
        "--localization-radius",
        type=int,
        default=0,
        help="graph radius of reports used for each localized marginal posterior",
    )
    parser.add_argument(
        "--geographic-reporting-bias-strength",
        type=float,
        default=0.0,
        help="0 disables heterogeneous coverage; 1 uses the full locality-observability gradient",
    )
    parser.add_argument(
        "--observation-profile",
        choices=["mixed-proxy", "direct-oracle"],
        default="mixed-proxy",
        help="mixed proxy design or deliberately favorable full-rank direct measurements",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[*SCENARIOS, "all"],
        default=None,
        help="repeat for multiple scenarios; use 'all' for the misspecification battery",
    )
    parser.add_argument("--model-seed", type=int, default=2026091701)
    parser.add_argument("--initialization-seed", type=int, default=2026091702)
    parser.add_argument("--truth-seed", type=int, default=2026091703)
    parser.add_argument("--prior-seed", type=int, default=2026091704)
    parser.add_argument("--observation-seed", type=int, default=2026091705)
    parser.add_argument("--filter-seed", type=int, default=2026091706)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.scenario is None:
        args.scenario = ["nominal"]
    payload = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = {
        "output": str(args.output),
        "status": payload["status"],
        "observations": payload["observation_diagnostics"]["count"],
        "scenarios": {
            name: {
                "rmse": result["metrics"]["rmse"],
                "coverage_90": result["metrics"]["coverage_90"],
                "confidently_wrong_rate": result["metrics"]["confidently_wrong_rate"],
                "spatial_correlation": result["metrics"]["mean_spatial_correlation"],
                "no_assimilation_rmse": payload["no_assimilation_baseline"]["metrics"]["rmse"],
                "rmse_ratio_vs_no_assimilation": result["relative_to_no_assimilation"]["rmse_ratio"],
                "direct_report_rmse": result["direct_report_baseline"]["rmse"],
            }
            for name, result in payload["scenario_results"].items()
        },
        "localized_reconstruction": {
            "rmse": payload["localized_reconstruction"]["metrics"]["rmse"],
            "linked_rmse_ratio_vs_prior": payload["localized_reconstruction"]["relative_to_prior"]["linked_rmse_ratio"],
            "coverage_90": payload["localized_reconstruction"]["metrics"]["coverage_90"],
            "minimum_ess": payload["localized_reconstruction"]["support"]["minimum_ess"],
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
