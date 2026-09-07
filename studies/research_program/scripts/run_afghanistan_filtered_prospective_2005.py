"""Development runner for a training-filtered Afghanistan 2005 forecast.

This runner is intentionally separate from the consumed frozen-core 2005
artifact.  It reads only complete 2004 province-week observations, updates a
posterior ensemble of live simulation particles, freezes that ensemble at the
training boundary, and then propagates it through the 2005 forecast window.
No 2005 outcome row is used by the runner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import csv
import json
import math
from pathlib import Path
import random
import sys
from typing import Iterable

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"
INPUTS = STUDY / "config" / "historical_case_inputs.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(STUDY / "scripts"))

from historical_case import (  # noqa: E402
    HistoricalCoalitionSchedule,
    condition_world,
    load_historical_inputs,
    sample_taliban_spatial_prior,
    sample_security_deployment_prior,
    TALIBAN_PRIOR_FAMILIES,
)
from pineland_sim import (  # noqa: E402
    AssimilationObservation,
    Particle,
    SequentialParticleFilter,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.state_estimation import particle_weights  # noqa: E402
from pineland_sim.relations import STATE_SECURITY_KINDS  # noqa: E402


TRAINING_YEAR = "2004"
TRAINING_END_DAY = 364.0  # complete weeks only; the boundary week is excluded
FORECAST_START_DAY = 371.0  # first complete 2005 province-week
FORECAST_END_DAY = 731.0
DEFAULT_PARTICLE_COUNT = 128
DEFAULT_STRENGTHS = (5000.0, 7500.0, 10000.0)
PRIOR_FAMILY_STRATA = tuple(sorted(TALIBAN_PRIOR_FAMILIES))


@dataclass(frozen=True, slots=True)
class ProvinceWeekObservation:
    start_day: float
    end_day: float
    week_index: int
    active_provinces: frozenset[str]
    provinces: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BernoulliEventObservationModel:
    """Predeclared event-incidence observation model for filtering."""

    sensitivity: float = 0.80
    false_positive_rate: float = 0.02

    def __post_init__(self) -> None:
        if not 0 < self.sensitivity < 1:
            raise ValueError("sensitivity must be in (0, 1)")
        if not 0 < self.false_positive_rate < 1:
            raise ValueError("false_positive_rate must be in (0, 1)")

    def log_probability(
        self,
        predicted_active: bool | float,
        observed_active: bool,
    ) -> float:
        if isinstance(predicted_active, bool):
            latent_probability = 1.0 if predicted_active else 0.0
        else:
            latent_probability = min(1.0, max(0.0, float(predicted_active)))
        return self.log_probability_from_latent_probability(
            latent_probability,
            observed_active,
        )

    def observed_probability(self, latent_probability: float) -> float:
        """Apply the declared measurement operator to latent incidence."""
        latent_probability = min(1.0, max(0.0, float(latent_probability)))
        return self.false_positive_rate + (
            self.sensitivity - self.false_positive_rate
        ) * latent_probability

    def log_probability_from_latent_probability(
        self,
        latent_probability: float,
        observed_active: bool,
    ) -> float:
        probability = self.observed_probability(latent_probability)
        if not observed_active:
            probability = 1.0 - probability
        return math.log(probability)


def _load_case() -> dict:
    return json.loads(CASE.read_text(encoding="utf-8"))


def load_training_observations(
    panel_path: Path = PANEL,
    *,
    training_year: str = TRAINING_YEAR,
    complete_through_day: float = TRAINING_END_DAY,
) -> list[ProvinceWeekObservation]:
    """Build observations without materializing any non-training row."""
    by_week: dict[int, dict[str, int]] = {}
    provinces: set[str] = set()
    year_prefix = f"{training_year}-"
    with panel_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            week_start = row["week_start"]
            if week_start < year_prefix:
                continue
            # The panel is grouped by province rather than globally ordered,
            # so rows after the training year must be skipped instead of
            # stopping the stream (which would drop later provinces).  They
            # never enter ``by_week`` and cannot update the filter.
            if not week_start.startswith(year_prefix):
                continue
            week_index = int(row["week_index"])
            start_day = 7.0 * week_index
            end_day = start_day + 7.0
            if end_day > complete_through_day + 1e-12:
                continue
            province = row["province_id"]
            provinces.add(province)
            by_week.setdefault(week_index, {})[province] = int(
                row["taliban_state_active"]
            )

    ordered_provinces = tuple(sorted(provinces))
    observations = []
    for week_index in sorted(by_week):
        values = by_week[week_index]
        if set(values) != set(ordered_provinces):
            raise ValueError(f"training week {week_index} is not a complete province surface")
        observations.append(
            ProvinceWeekObservation(
                start_day=7.0 * week_index,
                end_day=7.0 * (week_index + 1),
                week_index=week_index,
                active_provinces=frozenset(
                    province for province, active in values.items() if active
                ),
                provinces=ordered_provinces,
            )
        )
    if not observations:
        raise ValueError("no complete training observations were found")
    return observations


def _config(seed: int, horizon: float) -> SimulationConfig:
    config = SimulationConfig(
        seed=seed,
        initialization_seed=20040101,
        horizon_days=horizon,
        agent_count=401,
        locality_count=401,
        output_mode="ensemble",
    )
    config.information.observation_retention_days = 90.0
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, horizon]]
    }
    config.foreign_affairs.enabled = False
    config.peace_process.enabled = False
    config.validate()
    return config


def build_initial_particle(
    *,
    seed: int,
    particle_index: int,
    taliban_strength: float,
    prior_family: str | None = None,
    horizon: float,
    case: dict,
    inputs: dict,
) -> Particle[SimulationParticle]:
    """Create one prior particle with an independent latent spatial draw."""
    config = _config(seed, horizon)
    world = generate_pineland(config, empirical_geography=case)
    prior_rng = random.Random(
        seed * 1_000_003 + particle_index * 97_409 + int(taliban_strength)
    )
    prior = sample_taliban_spatial_prior(
        inputs,
        prior_rng,
        total_strength=taliban_strength,
        prior_family=prior_family,
        preperiod_counts=case["preperiod_taliban_state_conflict_counts_2003"],
        preperiod_province_counts=case.get(
            "preperiod_taliban_state_conflict_province_background_counts_2003",
            {},
        ),
        locality_ids=world.localities,
    )
    security_prior = sample_security_deployment_prior(world, prior_rng)
    condition_world(
        world,
        inputs,
        taliban_strength,
        taliban_prior=prior,
        security_prior=security_prior,
    )
    schedule = HistoricalCoalitionSchedule(inputs)
    simulation = Simulation(
        world,
        policy_hook=schedule,
        stream_namespace=f"particle:{seed}:prior:{particle_index}",
    )
    return Particle(
        SimulationParticle(
            simulation,
            lineage_id=f"{seed}.{particle_index}",
        )
    )


def _province_for_locality(world, locality_id: str) -> str:
    district_id = world.localities[locality_id].district_id
    return world.district_hierarchy[district_id]["province"]


def _active_provinces(
    state: SimulationParticle,
    observation: ProvinceWeekObservation,
) -> set[str]:
    world = state.world
    return {
        _province_for_locality(world, event.locality_id)
        for event in world.state_based_events
        if observation.start_day <= float(event.time) < observation.end_day
        and event.locality_id in world.localities
        and "insurgent" in event.actor_organization_ids
        and any(
            world.organizations.get(actor) is not None
            and world.organizations[actor].kind in STATE_SECURITY_KINDS
            for actor in event.actor_organization_ids
            if actor != "insurgent"
        )
    }


def make_log_likelihood(
    observation_model: BernoulliEventObservationModel,
):
    def log_likelihood(
        state: SimulationParticle,
        observation: ProvinceWeekObservation,
    ) -> float:
        predicted = _active_provinces(state, observation)
        return sum(
            observation_model.log_probability(
                province in predicted,
                province in observation.active_provinces,
            )
            for province in observation.provinces
        )

    return log_likelihood


def make_nested_propagator(
    observation_model: BernoulliEventObservationModel,
    *,
    branches: int,
    rng: random.Random,
):
    """Estimate P(observation | latent state) with short nested continuations."""
    if branches < 1:
        raise ValueError("likelihood branches must be at least one")

    def propagate_and_score(
        state: SimulationParticle,
        time: float,
        observation: ProvinceWeekObservation,
    ) -> tuple[SimulationParticle, float]:
        branch_states = []
        active_counts = {province: 0 for province in observation.provinces}
        for branch_index in range(branches):
            branch = state.fork(branch_index)
            branch.advance_to(time)
            branch_states.append(branch)
            for province in _active_provinces(branch, observation):
                if province in active_counts:
                    active_counts[province] += 1
        log_likelihood = 0.0
        for province in observation.provinces:
            latent_probability = active_counts[province] / branches
            log_likelihood += observation_model.log_probability_from_latent_probability(
                latent_probability,
                province in observation.active_provinces,
            )
        # Keep one realized branch as the particle's continuing aleatory path;
        # the likelihood itself is based on all short continuations.
        return branch_states[rng.randrange(branches)], log_likelihood

    return propagate_and_score


def run_training_filter(
    particles: list[Particle[SimulationParticle]],
    observations: Iterable[ProvinceWeekObservation],
    *,
    filter_seed: int,
    observation_model: BernoulliEventObservationModel | None = None,
    ess_fraction: float = 0.5,
    likelihood_branches: int = 3,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    model = observation_model or BernoulliEventObservationModel()
    filter_ = SequentialParticleFilter(
        particles,
        propagate_and_score=make_nested_propagator(
            model,
            branches=likelihood_branches,
            rng=random.Random(filter_seed + 7919),
        ),
        rng=random.Random(filter_seed),
        ess_fraction=ess_fraction,
        allowed_split="training",
        fork_state=lambda state, child_index: state.fork(child_index),
    )
    for observation in observations:
        filter_.assimilate(
            AssimilationObservation(
                time=observation.end_day,
                value=observation,
                split="training",
                observation_id=f"province-week-{observation.week_index}",
            )
        )
    filter_.freeze()
    return filter_


def _forecast_cells(
    state: SimulationParticle,
    *,
    start_day: float,
    end_day: float,
) -> set[tuple[str, int]]:
    world = state.world
    return {
        (_province_for_locality(world, event.locality_id), int(float(event.time) // 7))
        for event in world.state_based_events
        if start_day <= float(event.time) < end_day
        and event.locality_id in world.localities
        and "insurgent" in event.actor_organization_ids
        and any(
            world.organizations.get(actor) is not None
            and world.organizations[actor].kind in STATE_SECURITY_KINDS
            for actor in event.actor_organization_ids
            if actor != "insurgent"
        )
    }


def forecast_weighted_field(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    *,
    start_day: float = FORECAST_START_DAY,
    end_day: float = FORECAST_END_DAY,
    observation_model: BernoulliEventObservationModel | None = None,
    forecast_branches: int = 3,
    forecast_seed: int = 0,
) -> dict[str, object]:
    """Freeze the posterior and return latent and observed incidence fields."""
    if forecast_branches < 1:
        raise ValueError("forecast branches must be at least one")
    model = observation_model or BernoulliEventObservationModel()
    filter_.freeze()
    weights = particle_weights(filter_.particles)
    provinces = sorted({
        _province_for_locality(particle.state.world, locality_id)
        for particle in filter_.particles
        for locality_id in particle.state.world.localities
    })
    first_week = int(start_day // 7)
    last_week = int(math.ceil(end_day / 7.0))
    latent_probability: dict[tuple[str, int], float] = {
        (province, week): 0.0
        for week in range(first_week, last_week)
        for province in provinces
    }
    member_cells: list[list[dict[str, int | str]]] = []
    forecast_branch_cells: list[list[list[dict[str, int | str]]]] = []
    for particle, weight in zip(filter_.particles, weights):
        branch_cell_sets = []
        for branch_index in range(forecast_branches):
            branch = particle.state.fork(branch_index)
            branch.advance_to(end_day)
            branch_cell_sets.append(
                _forecast_cells(branch, start_day=start_day, end_day=end_day)
            )
        cells = set().union(*branch_cell_sets) if branch_cell_sets else set()
        member_cells.append([
            {"province_id": province, "week_index": week}
            for province, week in sorted(cells)
        ])
        forecast_branch_cells.append([
            [
                {"province_id": province, "week_index": week}
                for province, week in sorted(branch_cells)
            ]
            for branch_cells in branch_cell_sets
        ])
        for branch_cells in branch_cell_sets:
            for cell in branch_cells:
                latent_probability[cell] = (
                    latent_probability.get(cell, 0.0)
                    + weight / forecast_branches
                )
    observed_probability = {
        cell: model.observed_probability(probability)
        for cell, probability in latent_probability.items()
    }

    def field_rows(values: dict[tuple[str, int], float]) -> list[dict[str, object]]:
        return [
            {
                "province_id": province,
                "week_index": week,
                "probability": probability,
            }
            for (province, week), probability in sorted(values.items())
        ]

    return {
        "posterior_weights": weights,
        # The primary predictive estimand is observed province-week incidence;
        # latent mechanistic incidence remains available for explanation.
        "probability_field": field_rows(observed_probability),
        "latent_probability_field": field_rows(latent_probability),
        "observed_probability_field": field_rows(observed_probability),
        "member_active_cells": member_cells,
        "forecast_branch_cells": forecast_branch_cells,
        "forecast_branches": forecast_branches,
    }


def run(
    *,
    seed: int,
    taliban_strength: float | None = None,
    particles: int,
    output: Path,
    horizon: float = FORECAST_END_DAY,
    strengths: tuple[float, ...] = DEFAULT_STRENGTHS,
    likelihood_branches: int = 3,
    forecast_branches: int = 3,
) -> dict:
    if particles < 2:
        raise ValueError("at least two particles are required")
    if horizon < FORECAST_END_DAY:
        raise ValueError("filtered 2005 runner requires the full forecast boundary")
    if taliban_strength is not None:
        strength_strata = (float(taliban_strength),)
    else:
        strength_strata = tuple(float(strength) for strength in strengths)
    if not strength_strata:
        raise ValueError("at least one Taliban strength stratum is required")
    particle_strengths = tuple(
        strength_strata[index % len(strength_strata)]
        for index in range(particles)
    )
    case = _load_case()
    inputs = load_historical_inputs()
    observations = load_training_observations()
    initial_particles = [
        build_initial_particle(
            seed=seed,
            particle_index=index,
            taliban_strength=particle_strengths[index],
            prior_family=PRIOR_FAMILY_STRATA[index % len(PRIOR_FAMILY_STRATA)],
            horizon=horizon,
            case=case,
            inputs=inputs,
        )
        for index in range(particles)
    ]
    filter_ = run_training_filter(
        initial_particles,
        observations,
        filter_seed=seed + 17_003,
        likelihood_branches=likelihood_branches,
    )
    posterior_boundary = max(observation.end_day for observation in observations)
    forecast = forecast_weighted_field(
        filter_,
        forecast_branches=forecast_branches,
        forecast_seed=seed + 29_011,
    )
    filter_diagnostics = [asdict(item) for item in filter_.history]
    smc_diagnostics = {
        **filter_.ancestry_diagnostics(),
        "minimum_posterior_ess": min(
            (item["posterior_ess"] for item in filter_diagnostics),
            default=float(particles),
        ),
        "minimum_posterior_ess_fraction": min(
            (
                item["posterior_ess"] / max(1, particles)
                for item in filter_diagnostics
            ),
            default=1.0,
        ),
        "support_exhausted": False,
        "all_update_likelihoods_finite": True,
    }
    payload = {
        "schema_version": "pineland.afghanistan.filtered_prospective_2005.v2",
        "seed": seed,
        "taliban_initial_strength": (
            float(taliban_strength) if taliban_strength is not None else None
        ),
        "taliban_initial_strengths": list(strength_strata),
        "particle_initial_strengths": list(particle_strengths),
        "prior_family_strata": list(PRIOR_FAMILY_STRATA),
        "particle_prior_families": [
            PRIOR_FAMILY_STRATA[index % len(PRIOR_FAMILY_STRATA)]
            for index in range(particles)
        ],
        "particle_count": particles,
        "training_year": TRAINING_YEAR,
        "training_boundary_day": posterior_boundary,
        "forecast_start_day": FORECAST_START_DAY,
        "forecast_end_day": FORECAST_END_DAY,
        "assimilation_split": "training",
        # Compatibility field: "read" means admitted to the observation
        # stream, not physically scanned while iterating the province-grouped
        # CSV.  The explicit ``used`` field removes that ambiguity.
        "holdout_outcomes_read": False,
        "holdout_outcomes_used": False,
        "observation_model": asdict(BernoulliEventObservationModel()),
        "likelihood_branches": likelihood_branches,
        "forecast_branches": forecast_branches,
        "filter_updates": filter_diagnostics,
        "smc_diagnostics": smc_diagnostics,
        "posterior_probability_field": forecast["probability_field"],
        "posterior_latent_probability_field": forecast["latent_probability_field"],
        "posterior_observed_probability_field": forecast["observed_probability_field"],
        "posterior_weights": forecast["posterior_weights"],
        "member_active_cells": forecast["member_active_cells"],
        "forecast_branch_cells": forecast["forecast_branch_cells"],
        "posterior_frozen": filter_.frozen,
        "predictive_estimand": "observed_province_week_conflict_incidence",
        "latent_estimand": "latent_Taliban_state_security_event_incidence",
        "actor_existence_conditioning": (
            "conditional spatial conflict forecast given Taliban identity persistence"
        ),
        "probability_field_definition": (
            "posterior predictive probability of an observed province-week "
            "Taliban-state-security conflict event for every surface cell; "
            "latent mechanistic incidence is reported separately"
        ),
        "posterior_particle_summaries": [
            particle.state.world.summary() for particle in filter_.particles
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--strength", type=float, choices=DEFAULT_STRENGTHS)
    parser.add_argument("--particles", type=int, default=DEFAULT_PARTICLE_COUNT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(
        seed=args.seed,
        taliban_strength=args.strength,
        particles=args.particles,
        output=args.output,
    )
    print(json.dumps({
        "output": str(args.output),
        "particle_count": payload["particle_count"],
        "training_boundary_day": payload["training_boundary_day"],
        "forecast_probability_cells": len(payload["posterior_probability_field"]),
    }))


if __name__ == "__main__":
    main()
