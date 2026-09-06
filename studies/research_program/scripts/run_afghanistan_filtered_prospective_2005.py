"""Development runner for a training-filtered Afghanistan 2005 forecast.

This runner is intentionally separate from the consumed frozen-core 2005
artifact.  It reads only complete 2004 province-week observations, updates a
posterior ensemble of live simulation particles, freezes that ensemble at the
training boundary, and then propagates it through the 2005 forecast window.
No 2005 outcome row is opened by the runner.
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


TRAINING_YEAR = "2004"
TRAINING_END_DAY = 364.0  # complete weeks only; the boundary week is excluded
FORECAST_START_DAY = 371.0  # first complete 2005 province-week
FORECAST_END_DAY = 731.0


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

    def log_probability(self, predicted_active: bool, observed_active: bool) -> float:
        if predicted_active:
            probability = self.sensitivity if observed_active else 1.0 - self.sensitivity
        else:
            probability = (
                self.false_positive_rate
                if observed_active else 1.0 - self.false_positive_rate
            )
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
    with panel_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row["week_start"].startswith(f"{training_year}-"):
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
        preperiod_counts=case["preperiod_taliban_state_conflict_counts_2003"],
    )
    condition_world(world, inputs, taliban_strength, taliban_prior=prior)
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
        _province_for_locality(world, locality_id)
        for event_time, locality_id in zip(
            world.state_based_event_times,
            world.state_based_event_localities,
        )
        if observation.start_day <= float(event_time) < observation.end_day
        and locality_id in world.localities
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


def run_training_filter(
    particles: list[Particle[SimulationParticle]],
    observations: Iterable[ProvinceWeekObservation],
    *,
    filter_seed: int,
    observation_model: BernoulliEventObservationModel | None = None,
    ess_fraction: float = 0.5,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    model = observation_model or BernoulliEventObservationModel()
    filter_ = SequentialParticleFilter(
        particles,
        transition=lambda state, time: state.advance_to(time),
        log_likelihood=make_log_likelihood(model),
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
    return filter_


def _forecast_cells(
    state: SimulationParticle,
    *,
    start_day: float,
    end_day: float,
) -> set[tuple[str, int]]:
    world = state.world
    return {
        (_province_for_locality(world, locality_id), int(float(event_time) // 7))
        for event_time, locality_id in zip(
            world.state_based_event_times,
            world.state_based_event_localities,
        )
        if start_day <= float(event_time) < end_day
        and locality_id in world.localities
    }


def forecast_weighted_field(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    *,
    start_day: float = FORECAST_START_DAY,
    end_day: float = FORECAST_END_DAY,
) -> dict[str, object]:
    """Freeze the posterior and return weighted mechanistic event incidence."""
    for particle in filter_.particles:
        particle.state.advance_to(end_day)
    weights = particle_weights(filter_.particles)
    cell_probability: dict[tuple[str, int], float] = {}
    member_cells: list[list[dict[str, int | str]]] = []
    for particle, weight in zip(filter_.particles, weights):
        cells = _forecast_cells(particle.state, start_day=start_day, end_day=end_day)
        member_cells.append([
            {"province_id": province, "week_index": week}
            for province, week in sorted(cells)
        ])
        for cell in cells:
            cell_probability[cell] = cell_probability.get(cell, 0.0) + weight
    return {
        "posterior_weights": weights,
        "probability_field": [
            {
                "province_id": province,
                "week_index": week,
                "probability": probability,
            }
            for (province, week), probability in sorted(cell_probability.items())
        ],
        "member_active_cells": member_cells,
    }


def run(
    *,
    seed: int,
    taliban_strength: float,
    particles: int,
    output: Path,
    horizon: float = FORECAST_END_DAY,
) -> dict:
    if particles < 2:
        raise ValueError("at least two particles are required")
    if horizon < FORECAST_END_DAY:
        raise ValueError("filtered 2005 runner requires the full forecast boundary")
    case = _load_case()
    inputs = load_historical_inputs()
    observations = load_training_observations()
    initial_particles = [
        build_initial_particle(
            seed=seed,
            particle_index=index,
            taliban_strength=taliban_strength,
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
    )
    posterior_boundary = max(observation.end_day for observation in observations)
    forecast = forecast_weighted_field(filter_)
    payload = {
        "schema_version": "pineland.afghanistan.filtered_prospective_2005.v1",
        "seed": seed,
        "taliban_initial_strength": taliban_strength,
        "particle_count": particles,
        "training_year": TRAINING_YEAR,
        "training_boundary_day": posterior_boundary,
        "forecast_start_day": FORECAST_START_DAY,
        "forecast_end_day": FORECAST_END_DAY,
        "assimilation_split": "training",
        "holdout_outcomes_read": False,
        "observation_model": asdict(BernoulliEventObservationModel()),
        "filter_updates": [asdict(item) for item in filter_.history],
        "posterior_probability_field": forecast["probability_field"],
        "posterior_weights": forecast["posterior_weights"],
        "member_active_cells": forecast["member_active_cells"],
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
    parser.add_argument("--strength", type=float, choices=(5000.0, 7500.0, 10000.0), required=True)
    parser.add_argument("--particles", type=int, default=32)
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
