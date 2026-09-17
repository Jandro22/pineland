"""Synthetic hidden-state recovery infrastructure for Pineland research.

The scientific purpose of this module is narrower than the simulator itself:
given a known latent trajectory, generate an intentionally incomplete
observation stream, estimate the latent trajectory, and score how well the
posterior recovers truth.  Historical case data are deliberately absent.

The observation model is expressed as linear proxy channels over latent state
variables.  A channel may load on one variable (a relatively direct proxy) or
several variables (an intentionally ambiguous proxy).  This makes it possible
to test both recovery and non-identifiability without changing the transition
model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import exp, isfinite, log, pi, sqrt
import random
import statistics
from typing import Iterable, Mapping, Sequence

from .entities import CONTROL_DIMENSIONS, clamp


StateVector = dict[str, float]
StateField = dict[str, StateVector]


@dataclass(frozen=True, slots=True)
class ObservationChannel:
    """One researcher-visible proxy for one or more hidden state variables."""

    name: str
    loadings: tuple[tuple[str, float], ...]
    intercept: float = 0.0
    measurement_sd: float = 0.10
    reporting_probability: float = 0.60
    minimum_value: float = 0.0
    maximum_value: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("observation channel name cannot be blank")
        if not self.loadings:
            raise ValueError("observation channel requires at least one loading")
        if self.measurement_sd <= 0:
            raise ValueError("measurement_sd must be positive")
        if not 0 <= self.reporting_probability <= 1:
            raise ValueError("reporting_probability must be in [0, 1]")
        if self.minimum_value >= self.maximum_value:
            raise ValueError("observation bounds must be ordered")
        if any(not name or not isfinite(weight) for name, weight in self.loadings):
            raise ValueError("channel loadings must be finite and named")

    def expected_value(self, state: Mapping[str, float]) -> float:
        value = self.intercept + sum(
            weight * float(state.get(variable, 0.0))
            for variable, weight in self.loadings
        )
        return min(self.maximum_value, max(self.minimum_value, value))

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["loadings"] = {name: weight for name, weight in self.loadings}
        return payload


@dataclass(frozen=True, slots=True)
class ObservationProcessConfig:
    """Data-degradation process applied after the latent world is generated."""

    reporting_multiplier: float = 1.0
    geolocation_error_probability: float = 0.08
    maximum_delay_days: float = 3.0
    measurement_noise_multiplier: float = 1.0
    false_report_probability: float = 0.0
    geographic_reporting_bias_strength: float = 0.0

    def __post_init__(self) -> None:
        if self.reporting_multiplier < 0:
            raise ValueError("reporting_multiplier cannot be negative")
        if not 0 <= self.geolocation_error_probability <= 1:
            raise ValueError("geolocation_error_probability must be in [0, 1]")
        if self.maximum_delay_days < 0:
            raise ValueError("maximum_delay_days cannot be negative")
        if self.measurement_noise_multiplier <= 0:
            raise ValueError("measurement_noise_multiplier must be positive")
        if not 0 <= self.false_report_probability <= 1:
            raise ValueError("false_report_probability must be in [0, 1]")
        if not 0 <= self.geographic_reporting_bias_strength <= 1:
            raise ValueError("geographic_reporting_bias_strength must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class SyntheticObservation:
    """One imperfect report produced from a known synthetic latent state."""

    observation_id: str
    channel: str
    state_time: float
    arrival_time: float
    true_unit_id: str
    reported_unit_id: str
    value: float
    measurement_sd: float
    geolocation_error: bool = False
    false_report: bool = False


@dataclass(frozen=True, slots=True)
class PosteriorPoint:
    time: float
    unit_id: str
    variable: str
    truth: float
    mean: float
    median: float
    lower_50: float
    upper_50: float
    lower_90: float
    upper_90: float
    lower_95: float
    upper_95: float
    posterior_sd: float

    @property
    def error(self) -> float:
        return self.mean - self.truth


@dataclass(frozen=True, slots=True)
class RecoveryMetrics:
    count: int
    bias: float
    mae: float
    rmse: float
    coverage_50: float
    coverage_90: float
    coverage_95: float
    mean_interval_width_90: float
    confidently_wrong_rate: float
    mean_spatial_correlation: float | None
    change_events: int
    detected_change_events: int
    change_detection_rate: float | None
    mean_detection_lag_days: float | None


@dataclass(frozen=True, slots=True)
class LocalizedSupportDiagnostic:
    time: float
    unit_id: str
    radius: int
    reports: int
    ess: float
    maximum_weight: float


@dataclass(frozen=True, slots=True)
class ComponentLocalizedSupportDiagnostic:
    """Support diagnostic for one locality-variable marginal posterior."""

    time: float
    unit_id: str
    variable: str
    radius: int
    reports: int
    relevant_channels: int
    ess: float
    maximum_weight: float


@dataclass(frozen=True, slots=True)
class MisspecificationScenario:
    """Declared mismatch between data generation and estimator assumptions."""

    name: str
    assumed_geolocation_error_probability: float | None = None
    assumed_measurement_noise_multiplier: float | None = None
    dropped_channels: tuple[str, ...] = ()


def default_hidden_war_channels() -> tuple[ObservationChannel, ...]:
    """Return a conservative mixed-proxy observation menu for synthetic work.

    These are *measurement contracts*, not empirical claims.  The direct-ish
    channels make the first recovery benchmark diagnosable, while the mixed
    channels create deliberate confounding that can be exposed by the
    identifiability diagnostics.
    """

    return (
        ObservationChannel(
            "security_presence_report",
            (("insurgent.physical", 0.55), ("government.physical", -0.45)),
            intercept=0.45,
            measurement_sd=0.12,
            reporting_probability=0.70,
        ),
        ObservationChannel(
            "administrative_function_report",
            (("government.administrative", 0.80), ("insurgent.administrative", -0.20)),
            intercept=0.10,
            measurement_sd=0.10,
            reporting_probability=0.55,
        ),
        ObservationChannel(
            "taxation_coercion_report",
            (("insurgent.fiscal", 0.70), ("insurgent.foothold", 0.30)),
            measurement_sd=0.13,
            reporting_probability=0.40,
        ),
        ObservationChannel(
            "public_alignment_report",
            (("insurgent.social", 0.50), ("insurgent.expected", 0.25),
             ("government.social", -0.25)),
            intercept=0.25,
            measurement_sd=0.15,
            reporting_probability=0.35,
        ),
        ObservationChannel(
            "organizational_presence_report",
            (("insurgent.embeddedness", 0.45), ("insurgent.foothold", 0.30),
             ("insurgent.fighter_capacity", 0.25)),
            measurement_sd=0.11,
            reporting_probability=0.50,
        ),
        ObservationChannel(
            "logistics_readiness_report",
            (("insurgent.supply_capacity", 0.60),
             ("insurgent.fighter_capacity", 0.40)),
            measurement_sd=0.14,
            reporting_probability=0.30,
        ),
        # Two relatively direct anchors are intentionally retained.  They let
        # the harness distinguish estimator failure from a completely
        # unidentified measurement design before harder channels are removed.
        ObservationChannel(
            "government_admin_anchor",
            (("government.administrative", 1.0),),
            measurement_sd=0.08,
            reporting_probability=0.25,
        ),
        ObservationChannel(
            "insurgent_physical_anchor",
            (("insurgent.physical", 1.0),),
            measurement_sd=0.08,
            reporting_probability=0.20,
        ),
    )


def direct_hidden_war_channels(
    variables: Sequence[str],
    *,
    measurement_sd: float = 0.10,
    reporting_probability: float = 0.20,
) -> tuple[ObservationChannel, ...]:
    """Return an intentionally favorable full-rank synthetic measurement set.

    This profile is an estimator diagnostic, not a realistic intelligence
    collection claim.  If the state estimator cannot recover under these
    direct channels, the failure belongs to inference/support rather than to
    ambiguity in the mixed proxy design.
    """

    return tuple(
        ObservationChannel(
            f"direct::{variable}",
            ((variable, 1.0),),
            measurement_sd=measurement_sd,
            reporting_probability=reporting_probability,
        )
        for variable in variables
    )


def observation_design_diagnostics(
    channels: Sequence[ObservationChannel],
    variables: Sequence[str],
    *,
    tolerance: float = 1e-10,
) -> dict[str, object]:
    """Diagnose snapshot identifiability of the declared linear proxy design.

    This is deliberately a property of the measurement design, not of a
    realized particle ensemble.  A rank deficiency proves that the channel
    matrix cannot uniquely identify every listed coordinate from one
    locality-time snapshot without additional dynamic/prior restrictions.
    Conversely, full rank would not by itself prove practical recoverability.
    """

    variables = tuple(variables)
    index = {variable: position for position, variable in enumerate(variables)}
    matrix: list[list[float]] = []
    loaded_by: dict[str, list[str]] = {variable: [] for variable in variables}
    loading_energy: dict[str, float] = {variable: 0.0 for variable in variables}
    for channel in channels:
        row = [0.0] * len(variables)
        for variable, weight in channel.loadings:
            if variable not in index:
                continue
            row[index[variable]] = float(weight)
            loaded_by[variable].append(channel.name)
            loading_energy[variable] += float(weight) ** 2
        matrix.append(row)

    # Stable-enough Gaussian elimination for this small declared design.
    working = [row[:] for row in matrix]
    rank = 0
    column = 0
    while rank < len(working) and column < len(variables):
        pivot = max(
            range(rank, len(working)),
            key=lambda row_index: abs(working[row_index][column]),
        )
        if abs(working[pivot][column]) <= tolerance:
            column += 1
            continue
        working[rank], working[pivot] = working[pivot], working[rank]
        pivot_value = working[rank][column]
        working[rank] = [value / pivot_value for value in working[rank]]
        for row_index in range(len(working)):
            if row_index == rank:
                continue
            factor = working[row_index][column]
            if abs(factor) <= tolerance:
                continue
            working[row_index] = [
                current - factor * pivot_component
                for current, pivot_component in zip(
                    working[row_index], working[rank]
                )
            ]
        rank += 1
        column += 1

    linked = [variable for variable in variables if loaded_by[variable]]
    unlinked = [variable for variable in variables if not loaded_by[variable]]
    return {
        "channels": len(channels),
        "variables": len(variables),
        "snapshot_design_rank": rank,
        "snapshot_nullity": len(variables) - rank,
        "full_snapshot_identification_possible": rank == len(variables),
        "observation_linked_variables": linked,
        "snapshot_unobserved_variables": unlinked,
        "variable_loading_strength": {
            variable: sqrt(loading_energy[variable])
            for variable in variables
        },
        "loaded_by_channels": loaded_by,
        "interpretation": (
            "Rank deficiency is a structural warning for one-time-slice measurement. "
            "Dynamics and informative priors can add identifying restrictions, but "
            "they must be tested rather than assumed."
        ),
    }


def extract_pineland_latent_state(world) -> StateField:
    """Project the live world into analysis-only hidden-state coordinates.

    The projection never mutates the world and does not expose actor beliefs.
    All seven control dimensions are retained for both government and the
    aggregate insurgent side.  Local organizational foothold is included as a
    separate latent stock rather than being folded into territorial control.
    """

    from .action_model import capacity_saturation
    from .organizational_state import (
        local_foothold_strength,
        local_organizational_embeddedness,
    )
    from .physical import active_insurgent_ids, aggregate_insurgent_control

    insurgent_ids = active_insurgent_ids(world)
    field: StateField = {}
    for locality_id in sorted(world.localities):
        locality = world.localities[locality_id]
        row: StateVector = {}
        government = locality.control["government"]
        insurgent = aggregate_insurgent_control(world, locality_id)
        for dimension in CONTROL_DIMENSIONS:
            row[f"government.{dimension}"] = clamp(
                float(getattr(government, dimension))
            )
            row[f"insurgent.{dimension}"] = clamp(
                float(getattr(insurgent, dimension))
            )
        if insurgent_ids:
            complement = 1.0
            embedded_complement = 1.0
            fighter_complement = 1.0
            supply_complement = 1.0
            formation_threshold = max(
                1e-12,
                float(world.config.organization_ecology.minimum_formation_personnel),
            )
            supply_per_fighter = max(
                1e-12,
                float(world.config.logistics.formation_supply_days)
                * float(world.config.logistics.initial_supply_fraction),
            )
            for organization_id in insurgent_ids:
                complement *= 1.0 - clamp(
                    local_foothold_strength(world, organization_id, locality_id)
                )
                embedded_complement *= 1.0 - clamp(
                    local_organizational_embeddedness(
                        world, organization_id, locality_id
                    )
                )
                fighter_complement *= 1.0 - clamp(
                    capacity_saturation(world, organization_id, locality_id)
                )
                reserve = max(
                    0.0,
                    float(world.organization_manpower_supply_reserves.get(
                        (organization_id, locality_id), 0.0
                    )),
                )
                supply_depth = clamp(
                    reserve / (formation_threshold * supply_per_fighter)
                )
                supply_complement *= 1.0 - supply_depth
            row["insurgent.foothold"] = clamp(1.0 - complement)
            row["insurgent.embeddedness"] = clamp(1.0 - embedded_complement)
            row["insurgent.fighter_capacity"] = clamp(1.0 - fighter_complement)
            row["insurgent.supply_capacity"] = clamp(1.0 - supply_complement)
        else:
            row["insurgent.foothold"] = 0.0
            row["insurgent.embeddedness"] = 0.0
            row["insurgent.fighter_capacity"] = 0.0
            row["insurgent.supply_capacity"] = 0.0
        field[locality_id] = row
    return field


def _normal_logpdf(value: float, mean: float, sd: float) -> float:
    variance = sd * sd
    return -0.5 * (log(2.0 * pi * variance) + (value - mean) ** 2 / variance)


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    if maximum == float("-inf"):
        return maximum
    return maximum + log(sum(exp(value - maximum) for value in values))


def generate_observations(
    state: StateField,
    *,
    state_time: float,
    channels: Sequence[ObservationChannel],
    process: ObservationProcessConfig,
    adjacency: Mapping[str, Iterable[str]],
    rng: random.Random,
    observation_prefix: str = "synthetic",
    unit_reporting_multipliers: Mapping[str, float] | None = None,
) -> list[SyntheticObservation]:
    """Generate delayed, noisy, spatially fallible reports from known truth."""

    reports: list[SyntheticObservation] = []
    counter = 0
    for unit_id in sorted(state):
        unit_state = state[unit_id]
        neighbors = tuple(sorted(adjacency.get(unit_id, ())))
        raw_unit_multiplier = (
            float(unit_reporting_multipliers.get(unit_id, 1.0))
            if unit_reporting_multipliers is not None
            else 1.0
        )
        if raw_unit_multiplier < 0 or not isfinite(raw_unit_multiplier):
            raise ValueError("unit reporting multipliers must be finite and nonnegative")
        unit_multiplier = (
            1.0 - process.geographic_reporting_bias_strength
            + process.geographic_reporting_bias_strength * raw_unit_multiplier
        )
        for channel in channels:
            probability = min(
                1.0,
                channel.reporting_probability
                * process.reporting_multiplier
                * unit_multiplier,
            )
            if rng.random() >= probability:
                continue
            false_report = rng.random() < process.false_report_probability
            expected = (
                rng.uniform(channel.minimum_value, channel.maximum_value)
                if false_report
                else channel.expected_value(unit_state)
            )
            sd = channel.measurement_sd * process.measurement_noise_multiplier
            value = min(
                channel.maximum_value,
                max(channel.minimum_value, rng.gauss(expected, sd)),
            )
            geolocation_error = bool(
                neighbors and rng.random() < process.geolocation_error_probability
            )
            reported_unit_id = rng.choice(neighbors) if geolocation_error else unit_id
            delay = rng.random() * process.maximum_delay_days
            counter += 1
            reports.append(SyntheticObservation(
                observation_id=f"{observation_prefix}:{state_time:g}:{counter}",
                channel=channel.name,
                state_time=float(state_time),
                arrival_time=float(state_time + delay),
                true_unit_id=unit_id,
                reported_unit_id=reported_unit_id,
                value=float(value),
                measurement_sd=float(sd),
                geolocation_error=geolocation_error,
                false_report=false_report,
            ))
    return reports


def observation_batch_log_likelihood(
    state: StateField,
    observations: Sequence[SyntheticObservation],
    *,
    channels: Sequence[ObservationChannel],
    adjacency: Mapping[str, Iterable[str]],
    assumed_geolocation_error_probability: float = 0.0,
    assumed_measurement_noise_multiplier: float = 1.0,
) -> float:
    """Score a candidate latent field against one report batch.

    When a non-zero geolocation-error probability is declared, likelihood is a
    finite spatial mixture over the reported unit and its neighbors.  This lets
    misspecification studies compare a correctly specified spatial observation
    model with the common but unsafe assumption that reported coordinates are
    exact.
    """

    channel_by_name = {channel.name: channel for channel in channels}
    if not 0 <= assumed_geolocation_error_probability <= 1:
        raise ValueError("assumed geolocation error probability must be in [0, 1]")
    if assumed_measurement_noise_multiplier <= 0:
        raise ValueError("assumed measurement noise multiplier must be positive")
    total = 0.0
    for observation in observations:
        channel = channel_by_name[observation.channel]
        reported = observation.reported_unit_id
        if reported not in state:
            continue
        neighbors = tuple(
            unit for unit in sorted(adjacency.get(reported, ())) if unit in state
        )
        sd = channel.measurement_sd * assumed_measurement_noise_multiplier
        if not neighbors or assumed_geolocation_error_probability <= 0:
            total += _normal_logpdf(
                observation.value,
                channel.expected_value(state[reported]),
                sd,
            )
            continue
        error_probability = assumed_geolocation_error_probability
        components = [
            log(max(1e-15, 1.0 - error_probability))
            + _normal_logpdf(
                observation.value,
                channel.expected_value(state[reported]),
                sd,
            )
        ]
        neighbor_mass = error_probability / len(neighbors)
        components.extend(
            log(max(1e-15, neighbor_mass))
            + _normal_logpdf(
                observation.value,
                channel.expected_value(state[neighbor]),
                sd,
            )
            for neighbor in neighbors
        )
        total += _logsumexp(components)
    return total


def graph_neighborhood(
    adjacency: Mapping[str, Iterable[str]],
    unit_id: str,
    radius: int,
) -> tuple[str, ...]:
    """Return units within an unweighted graph radius, including the focal unit."""

    if radius < 0:
        raise ValueError("localization radius cannot be negative")
    visited = {unit_id}
    frontier = {unit_id}
    for _ in range(radius):
        next_frontier = {
            neighbor
            for current in frontier
            for neighbor in adjacency.get(current, ())
            if neighbor not in visited
        }
        if not next_frontier:
            break
        visited.update(next_frontier)
        frontier = next_frontier
    return tuple(sorted(visited))


def localized_importance_reconstruction(
    truth: StateField,
    particle_fields: Sequence[StateField],
    observations: Sequence[SyntheticObservation],
    *,
    channels: Sequence[ObservationChannel],
    adjacency: Mapping[str, Iterable[str]],
    time: float,
    variables: Sequence[str] | None = None,
    radius: int = 0,
    assumed_geolocation_error_probability: float = 0.0,
    assumed_measurement_noise_multiplier: float = 1.0,
) -> tuple[list[PosteriorPoint], list[LocalizedSupportDiagnostic]]:
    """Estimate locality marginals without multiplying all-country likelihoods.

    Each particle remains a complete, causally coherent Pineland trajectory.
    For the marginal posterior of one locality, only observations reported in
    that locality (or within ``radius`` graph steps) contribute to its
    importance weight. No world-state splicing occurs.

    This is a localized marginal approximation, not an exact joint posterior:
    distant evidence that is informative through cross-locality dynamics is
    deliberately omitted. The radius therefore exposes a bias/support tradeoff
    that must be evaluated empirically.
    """

    if not particle_fields:
        raise ValueError("localized reconstruction requires particles")
    points: list[PosteriorPoint] = []
    diagnostics: list[LocalizedSupportDiagnostic] = []
    for unit_id in sorted(truth):
        neighborhood = set(graph_neighborhood(adjacency, unit_id, radius))
        local_observations = [
            observation
            for observation in observations
            if observation.reported_unit_id in neighborhood
        ]
        log_weights = [
            observation_batch_log_likelihood(
                field,
                local_observations,
                channels=channels,
                adjacency=adjacency,
                assumed_geolocation_error_probability=(
                    assumed_geolocation_error_probability
                ),
                assumed_measurement_noise_multiplier=(
                    assumed_measurement_noise_multiplier
                ),
            )
            for field in particle_fields
        ]
        # Import locally to keep the recovery module's public dependency
        # direction simple: state_estimation does not depend on recovery.
        from .state_estimation import effective_sample_size, normalize_log_weights

        weights = normalize_log_weights(log_weights, strict=True)
        unit_fields = [{unit_id: field[unit_id]} for field in particle_fields]
        points.extend(summarize_posterior_field(
            {unit_id: truth[unit_id]},
            unit_fields,
            weights,
            time=time,
            variables=variables,
        ))
        diagnostics.append(LocalizedSupportDiagnostic(
            time=float(time),
            unit_id=unit_id,
            radius=radius,
            reports=len(local_observations),
            ess=effective_sample_size(weights),
            maximum_weight=max(weights),
        ))
    return points, diagnostics


def component_localized_importance_reconstruction(
    truth: StateField,
    particle_fields: Sequence[StateField],
    observations: Sequence[SyntheticObservation],
    *,
    channels: Sequence[ObservationChannel],
    adjacency: Mapping[str, Iterable[str]],
    time: float,
    variables: Sequence[str] | None = None,
    radius: int = 0,
    assumed_geolocation_error_probability: float = 0.0,
    assumed_measurement_noise_multiplier: float = 1.0,
) -> tuple[list[PosteriorPoint], list[ComponentLocalizedSupportDiagnostic]]:
    """Estimate locality-variable marginals using only structurally relevant reports.

    Locality localization prevents evidence from distant places from collapsing a
    whole-country particle ensemble. This second localization prevents a report
    about one latent construct from reweighting unrelated coordinates merely
    because a finite particle ensemble happens to correlate them.

    A report is relevant to a target variable when its declared observation
    channel has a non-zero loading on that variable. Mixed-proxy channels may
    therefore inform several marginals, preserving their intended ambiguity.
    Particles remain complete coherent Pineland worlds; only the importance
    weights used to summarize each marginal differ.
    """

    if not particle_fields:
        raise ValueError("component-localized reconstruction requires particles")
    if radius < 0:
        raise ValueError("localization radius cannot be negative")

    from .state_estimation import effective_sample_size, normalize_log_weights

    channel_by_name = {channel.name: channel for channel in channels}
    variables_by_channel = {
        channel.name: {
            variable for variable, weight in channel.loadings if abs(weight) > 0.0
        }
        for channel in channels
    }
    points: list[PosteriorPoint] = []
    diagnostics: list[ComponentLocalizedSupportDiagnostic] = []
    uniform = [1.0 / len(particle_fields)] * len(particle_fields)

    for unit_id in sorted(truth):
        neighborhood = set(graph_neighborhood(adjacency, unit_id, radius))
        available_variables = variables or tuple(sorted(truth[unit_id]))
        unit_fields = [{unit_id: field[unit_id]} for field in particle_fields]
        for variable in available_variables:
            if variable not in truth[unit_id]:
                continue
            relevant_names = {
                name for name, loaded_variables in variables_by_channel.items()
                if variable in loaded_variables
            }
            relevant_channels = tuple(
                channel_by_name[name] for name in sorted(relevant_names)
            )
            local_observations = [
                observation
                for observation in observations
                if (
                    observation.reported_unit_id in neighborhood
                    and observation.channel in relevant_names
                )
            ]
            if local_observations:
                log_weights = [
                    observation_batch_log_likelihood(
                        field,
                        local_observations,
                        channels=relevant_channels,
                        adjacency=adjacency,
                        assumed_geolocation_error_probability=(
                            assumed_geolocation_error_probability
                        ),
                        assumed_measurement_noise_multiplier=(
                            assumed_measurement_noise_multiplier
                        ),
                    )
                    for field in particle_fields
                ]
                weights = normalize_log_weights(log_weights, strict=True)
            else:
                weights = uniform

            points.extend(summarize_posterior_field(
                {unit_id: truth[unit_id]},
                unit_fields,
                weights,
                time=time,
                variables=(variable,),
            ))
            diagnostics.append(ComponentLocalizedSupportDiagnostic(
                time=float(time),
                unit_id=unit_id,
                variable=variable,
                radius=radius,
                reports=len(local_observations),
                relevant_channels=len(relevant_channels),
                ess=effective_sample_size(weights),
                maximum_weight=max(weights),
            ))

    return points, diagnostics


def _weighted_quantile(
    values: Sequence[float], weights: Sequence[float], probability: float
) -> float:
    if not values or len(values) != len(weights):
        raise ValueError("weighted quantile requires equally sized non-empty inputs")
    pairs = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        raise ValueError("weights must have positive mass")
    target = min(1.0, max(0.0, probability)) * total
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return float(value)
    return float(pairs[-1][0])


def summarize_posterior_field(
    truth: StateField,
    particle_fields: Sequence[StateField],
    weights: Sequence[float],
    *,
    time: float,
    variables: Sequence[str] | None = None,
) -> list[PosteriorPoint]:
    """Summarize a weighted posterior over the same units as known truth."""

    if not particle_fields:
        raise ValueError("posterior summary requires at least one particle")
    if len(particle_fields) != len(weights):
        raise ValueError("particle fields and weights must align")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("posterior weights must have positive mass")
    normalized = [weight / total_weight for weight in weights]
    points: list[PosteriorPoint] = []
    for unit_id in sorted(truth):
        available_variables = variables or tuple(sorted(truth[unit_id]))
        for variable in available_variables:
            if variable not in truth[unit_id]:
                continue
            values = [
                float(field.get(unit_id, {}).get(variable, 0.0))
                for field in particle_fields
            ]
            mean = sum(weight * value for weight, value in zip(normalized, values))
            variance = sum(
                weight * (value - mean) ** 2
                for weight, value in zip(normalized, values)
            )
            points.append(PosteriorPoint(
                time=float(time),
                unit_id=unit_id,
                variable=variable,
                truth=float(truth[unit_id][variable]),
                mean=float(mean),
                median=_weighted_quantile(values, normalized, 0.5),
                lower_50=_weighted_quantile(values, normalized, 0.25),
                upper_50=_weighted_quantile(values, normalized, 0.75),
                lower_90=_weighted_quantile(values, normalized, 0.05),
                upper_90=_weighted_quantile(values, normalized, 0.95),
                lower_95=_weighted_quantile(values, normalized, 0.025),
                upper_95=_weighted_quantile(values, normalized, 0.975),
                posterior_sd=sqrt(max(0.0, variance)),
            ))
    return points


def _pearson(first: Sequence[float], second: Sequence[float]) -> float | None:
    if len(first) != len(second) or len(first) < 2:
        return None
    mean_first = statistics.fmean(first)
    mean_second = statistics.fmean(second)
    left = [value - mean_first for value in first]
    right = [value - mean_second for value in second]
    denominator = sqrt(
        sum(value * value for value in left)
        * sum(value * value for value in right)
    )
    if denominator <= 1e-15:
        return None
    return sum(a * b for a, b in zip(left, right)) / denominator


def evaluate_recovery(
    points: Sequence[PosteriorPoint],
    *,
    confidence_width_threshold: float = 0.15,
    change_threshold: float = 0.10,
    detection_fraction: float = 0.50,
) -> RecoveryMetrics:
    """Compute calibration, accuracy, spatial, and change-detection metrics."""

    if not points:
        raise ValueError("recovery evaluation requires posterior points")
    errors = [point.error for point in points]
    coverage_50 = [point.lower_50 <= point.truth <= point.upper_50 for point in points]
    coverage_90 = [point.lower_90 <= point.truth <= point.upper_90 for point in points]
    coverage_95 = [point.lower_95 <= point.truth <= point.upper_95 for point in points]
    widths_90 = [point.upper_90 - point.lower_90 for point in points]
    confidently_wrong = [
        (not covered) and width <= confidence_width_threshold
        for covered, width in zip(coverage_90, widths_90)
    ]

    by_time_variable: dict[tuple[float, str], list[PosteriorPoint]] = {}
    for point in points:
        by_time_variable.setdefault((point.time, point.variable), []).append(point)
    spatial_correlations: list[float] = []
    for group in by_time_variable.values():
        correlation = _pearson(
            [point.truth for point in group], [point.mean for point in group]
        )
        if correlation is not None:
            spatial_correlations.append(correlation)

    by_unit_variable: dict[tuple[str, str], list[PosteriorPoint]] = {}
    for point in points:
        by_unit_variable.setdefault((point.unit_id, point.variable), []).append(point)
    detection_lags: list[float] = []
    change_events = 0
    detected_change_events = 0
    for group in by_unit_variable.values():
        group = sorted(group, key=lambda point: point.time)
        for index in range(1, len(group)):
            prior = group[index - 1]
            current = group[index]
            truth_change = current.truth - prior.truth
            if abs(truth_change) < change_threshold:
                continue
            change_events += 1
            direction = 1.0 if truth_change > 0 else -1.0
            required = detection_fraction * abs(truth_change)
            baseline = prior.mean
            detected = None
            for future in group[index:]:
                if direction * (future.mean - baseline) >= required:
                    detected = future.time - current.time
                    break
            if detected is not None:
                detected_change_events += 1
                detection_lags.append(float(detected))

    return RecoveryMetrics(
        count=len(points),
        bias=statistics.fmean(errors),
        mae=statistics.fmean(abs(error) for error in errors),
        rmse=sqrt(statistics.fmean(error * error for error in errors)),
        coverage_50=statistics.fmean(coverage_50),
        coverage_90=statistics.fmean(coverage_90),
        coverage_95=statistics.fmean(coverage_95),
        mean_interval_width_90=statistics.fmean(widths_90),
        confidently_wrong_rate=statistics.fmean(confidently_wrong),
        mean_spatial_correlation=(
            statistics.fmean(spatial_correlations) if spatial_correlations else None
        ),
        change_events=change_events,
        detected_change_events=detected_change_events,
        change_detection_rate=(
            detected_change_events / change_events if change_events else None
        ),
        mean_detection_lag_days=(
            statistics.fmean(detection_lags) if detection_lags else None
        ),
    )


def evaluate_recovery_by_variable(
    points: Sequence[PosteriorPoint],
) -> dict[str, dict[str, float | int | None]]:
    by_variable: dict[str, list[PosteriorPoint]] = {}
    for point in points:
        by_variable.setdefault(point.variable, []).append(point)
    return {
        variable: asdict(evaluate_recovery(variable_points))
        for variable, variable_points in sorted(by_variable.items())
    }


def posterior_identifiability(
    particle_fields: Sequence[StateField],
    weights: Sequence[float],
    *,
    variables: Sequence[str],
    correlation_threshold: float = 0.90,
) -> dict[str, object]:
    """Flag variable pairs that remain tightly coupled in the posterior.

    High posterior correlation is not by itself proof of non-identifiability,
    but persistent near-collinearity across units is a useful warning that the
    available observation design may not distinguish two latent coordinates.
    """

    if len(particle_fields) != len(weights) or not particle_fields:
        raise ValueError("particle fields and weights must align")
    total = sum(weights)
    normalized = [weight / total for weight in weights]
    units = sorted(set.intersection(*[set(field) for field in particle_fields]))
    pair_correlations: dict[tuple[str, str], list[float]] = {}
    for unit_id in units:
        means: dict[str, float] = {}
        centered: dict[str, list[float]] = {}
        for variable in variables:
            values = [field[unit_id].get(variable, 0.0) for field in particle_fields]
            mean = sum(weight * value for weight, value in zip(normalized, values))
            means[variable] = mean
            centered[variable] = [value - mean for value in values]
        for left_index, left in enumerate(variables):
            for right in variables[left_index + 1:]:
                covariance = sum(
                    weight * a * b
                    for weight, a, b in zip(normalized, centered[left], centered[right])
                )
                left_variance = sum(
                    weight * value * value
                    for weight, value in zip(normalized, centered[left])
                )
                right_variance = sum(
                    weight * value * value
                    for weight, value in zip(normalized, centered[right])
                )
                denominator = sqrt(left_variance * right_variance)
                if denominator > 1e-15:
                    pair_correlations.setdefault((left, right), []).append(
                        covariance / denominator
                    )
    signatures = {
        tuple(
            round(float(field[unit_id].get(variable, 0.0)), 12)
            for unit_id in units
            for variable in variables
        )
        for field in particle_fields
    }
    squared_mass = sum(weight * weight for weight in normalized)
    posterior_ess = 1.0 / squared_mass if squared_mass > 0 else 0.0
    rows = []
    for pair, correlations in sorted(pair_correlations.items()):
        mean_abs = statistics.fmean(abs(value) for value in correlations)
        rows.append({
            "left": pair[0],
            "right": pair[1],
            "units": len(correlations),
            "mean_absolute_posterior_correlation": mean_abs,
            "warning": mean_abs >= correlation_threshold,
        })
    return {
        "correlation_threshold": correlation_threshold,
        "particle_count": len(particle_fields),
        "unique_particle_fields": len(signatures),
        "posterior_effective_sample_size": posterior_ess,
        "support_warning": (
            len(signatures) < min(8, len(particle_fields))
            or posterior_ess < min(8.0, float(len(particle_fields)))
        ),
        "interpretation": (
            "Posterior correlation is a collinearity warning, not proof of structural "
            "non-identifiability. Duplicate/resampled particle support can make "
            "correlations spuriously extreme."
        ),
        "pairs": rows,
        "warning_pairs": [row for row in rows if row["warning"]],
    }


def direct_proxy_baseline(
    observations: Sequence[SyntheticObservation],
    channels: Sequence[ObservationChannel],
    *,
    truth_points: Sequence[PosteriorPoint],
    prior_mean: float = 0.5,
) -> dict[str, object]:
    """Score a deliberately simple latest-direct-report baseline.

    Only channels with exactly one +1 loading and zero intercept are eligible.
    This keeps the comparator transparent and prevents a supposedly simple
    baseline from quietly embedding the full measurement model.
    """

    direct = {
        channel.name: channel.loadings[0][0]
        for channel in channels
        if len(channel.loadings) == 1
        and abs(channel.loadings[0][1] - 1.0) <= 1e-12
        and abs(channel.intercept) <= 1e-12
    }
    by_key: dict[tuple[str, str], list[SyntheticObservation]] = {}
    for observation in observations:
        variable = direct.get(observation.channel)
        if variable is None:
            continue
        by_key.setdefault((observation.reported_unit_id, variable), []).append(observation)
    errors: list[float] = []
    eligible_errors: list[float] = []
    covered = 0
    eligible_points = 0
    direct_variables = set(direct.values())
    for point in truth_points:
        candidates = [
            observation
            for observation in by_key.get((point.unit_id, point.variable), ())
            if observation.arrival_time <= point.time
        ]
        if candidates:
            estimate = max(candidates, key=lambda item: item.arrival_time).value
            covered += 1
        else:
            estimate = prior_mean
        error = float(estimate - point.truth)
        errors.append(error)
        if point.variable in direct_variables:
            eligible_points += 1
            eligible_errors.append(error)
    return {
        "name": "latest_direct_proxy_or_prior",
        "eligible_channels": sorted(direct),
        "points": len(errors),
        "direct_observation_coverage": covered / len(errors) if errors else 0.0,
        "direct_observation_coverage_among_eligible": (
            covered / eligible_points if eligible_points else 0.0
        ),
        "direct_eligible_points": eligible_points,
        "bias": statistics.fmean(errors) if errors else None,
        "mae": statistics.fmean(abs(error) for error in errors) if errors else None,
        "rmse": (
            sqrt(statistics.fmean(error * error for error in errors))
            if errors else None
        ),
        "eligible_variable_bias": (
            statistics.fmean(eligible_errors) if eligible_errors else None
        ),
        "eligible_variable_mae": (
            statistics.fmean(abs(error) for error in eligible_errors)
            if eligible_errors else None
        ),
        "eligible_variable_rmse": (
            sqrt(statistics.fmean(error * error for error in eligible_errors))
            if eligible_errors else None
        ),
    }


def observation_diagnostics(
    observations: Sequence[SyntheticObservation],
) -> dict[str, object]:
    if not observations:
        return {
            "count": 0,
            "geolocation_error_rate": 0.0,
            "false_report_rate": 0.0,
            "mean_delay_days": 0.0,
            "by_channel": {},
        }
    by_channel: dict[str, int] = {}
    for observation in observations:
        by_channel[observation.channel] = by_channel.get(observation.channel, 0) + 1
    return {
        "count": len(observations),
        "geolocation_error_rate": statistics.fmean(
            observation.geolocation_error for observation in observations
        ),
        "false_report_rate": statistics.fmean(
            observation.false_report for observation in observations
        ),
        "mean_delay_days": statistics.fmean(
            observation.arrival_time - observation.state_time
            for observation in observations
        ),
        "by_channel": dict(sorted(by_channel.items())),
    }
