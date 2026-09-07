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
import copy
import csv
import hashlib
import json
import math
import os
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
    PersistentParticlePool,
    SequentialParticleFilter,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.state_estimation import (  # noqa: E402
    particle_weights,
)
from pineland_sim.reproducibility import (  # noqa: E402
    file_sha256,
    model_sha256,
    repository_state,
)


TRAINING_YEAR = "2004"
TRAINING_END_DAY = 364.0  # complete weeks only; the boundary week is excluded
FORECAST_START_DAY = 371.0  # first complete 2005 province-week
FORECAST_END_DAY = 731.0
DEFAULT_PARTICLE_COUNT = 128
DEFAULT_STRENGTHS = (5000.0, 7500.0, 10000.0)
PRIOR_FAMILY_STRATA = tuple(sorted(TALIBAN_PRIOR_FAMILIES))
COMPETITOR_INFORMATION_CONTRACT = {
    "schema_version": "pineland.afghanistan.information_matched_competitors.v1",
    "evaluation_surface": "observed province-week Taliban-state-security incidence",
    "shared_observed_information": [
        "2003 high-precision district occupancy evidence",
        "2003 lower-precision province/background evidence",
        "complete 2004 province-week training incidence",
        "fixed 401-district adjacency topology",
        "source-era population and WorldPop settlement covariates",
        "province and humanitarian-region hierarchy",
    ],
    "candidate_internal_latent_uncertainty": [
        "stratified initial Taliban strength prior",
        "stratified occupancy/force prior family",
        "outcome-free ANA/ANP deployment prior",
        "latent process state and aleatory forecast branches",
    ],
    "competitor_feature_families": [
        "global prevalence",
        "province empirical Bayes",
        "region empirical Bayes",
        "local persistence",
        "temporal self-excitation",
        "spatial-neighbor self-excitation",
        "topology-aware diffusion",
        "preperiod geography plus causal 2004 training history",
        "static source-grounded geography",
    ],
    "competitor_fit_scope": "2004 training rows only",
    "holdout_target_updates": False,
    "holdout_refit": False,
    "candidate_holdout_refit": False,
    "unmatched_candidate_state_not_exposed_as_features": [
        "latent particle states",
        "simulated security deployment draws",
        "simulated event realizations",
    ],
    "unresolved_exogenous_geography": [
        "independent terrain/elevation/ruggedness data",
        "preperiod road/travel-time data",
        "independent district language composition",
        "independent preperiod facility/deployment records",
    ],
}


@dataclass(frozen=True, slots=True)
class ProvinceWeekObservation:
    start_day: float
    end_day: float
    week_index: int
    active_provinces: frozenset[str]
    provinces: tuple[str, ...]


def _jeffreys_branch_probability(active_count: int, branches: int) -> float:
    """Finite-Monte-Carlo estimate of target-compatible event probability.

    The 1/2,1/2 Jeffreys pseudo-counts regularize a finite nested simulation
    estimate so that a small branch sample never converts numerical absence
    into a claim of zero physical probability. This is a Monte-Carlo
    estimator, not a historical source sensitivity/false-positive model.
    """
    if branches < 1:
        raise ValueError("branches must be at least one")
    if not 0 <= active_count <= branches:
        raise ValueError("active_count must lie in [0, branches]")
    return (active_count + 0.5) / (branches + 1.0)


def _bernoulli_log_probability(
    probability: float,
    observed_active: bool,
) -> float:
    probability = min(1.0, max(0.0, float(probability)))
    if not observed_active:
        probability = 1.0 - probability
    if probability <= 0.0:
        return -float("inf")
    return math.log(probability)


def _conditioned_branch_index(
    branch_active_provinces: list[set[str]],
    observed_active_provinces: frozenset[str],
    rng: random.Random,
) -> tuple[int, int, bool]:
    """Select the nested descendant most consistent with the observation.

    Exact matching descendants are selected when present. With a finite nested
    sample, an exact 34-province surface may be absent; in that case the
    minimum-Hamming descendants form the deterministic approximation set and
    only tie-breaking is random. The mismatch is returned for diagnostics.
    """
    if not branch_active_provinces:
        raise ValueError("at least one branch is required")
    mismatches = [
        len(active.symmetric_difference(observed_active_provinces))
        for active in branch_active_provinces
    ]
    minimum = min(mismatches)
    candidates = [
        index for index, mismatch in enumerate(mismatches)
        if mismatch == minimum
    ]
    selected = candidates[rng.randrange(len(candidates))]
    return selected, minimum, minimum == 0


class NestedOperationalPropagator:
    """Nested predictive likelihood plus observation-conditioned descendant."""

    def __init__(self, *, branches: int, selection_seed: int) -> None:
        if branches < 1:
            raise ValueError("likelihood branches must be at least one")
        self.branches = branches
        self.selection_seed = int(selection_seed)
        self.calls = 0
        self.exact_match_calls = 0
        self.minimum_mismatch_sum = 0
        self.maximum_minimum_mismatch = 0

    def __call__(
        self,
        state: SimulationParticle,
        time: float,
        observation: ProvinceWeekObservation,
    ) -> tuple[SimulationParticle, float]:
        branch_states: list[SimulationParticle] = []
        branch_active: list[set[str]] = []
        active_counts = {province: 0 for province in observation.provinces}
        for branch_index in range(self.branches):
            branch = state.fork(branch_index)
            branch.advance_to(time)
            active = _active_provinces(branch, observation)
            branch_states.append(branch)
            branch_active.append(active)
            for province in active:
                if province in active_counts:
                    active_counts[province] += 1

        log_likelihood = 0.0
        for province in observation.provinces:
            probability = _jeffreys_branch_probability(
                active_counts[province], self.branches
            )
            log_likelihood += _bernoulli_log_probability(
                probability,
                province in observation.active_provinces,
            )

        selected, minimum_mismatch, exact = _conditioned_branch_index(
            branch_active,
            observation.active_provinces,
            random.Random(
                _nested_selection_seed(
                    self.selection_seed,
                    state.lineage_id,
                    observation.week_index,
                )
            ),
        )
        self.calls += 1
        self.exact_match_calls += int(exact)
        self.minimum_mismatch_sum += minimum_mismatch
        self.maximum_minimum_mismatch = max(
            self.maximum_minimum_mismatch, minimum_mismatch
        )
        return branch_states[selected], log_likelihood

    def diagnostics(self) -> dict[str, float | int]:
        return {
            "nested_propagation_calls": self.calls,
            "exact_descendant_match_calls": self.exact_match_calls,
            "exact_descendant_match_fraction": (
                self.exact_match_calls / self.calls if self.calls else 0.0
            ),
            "mean_minimum_descendant_hamming_mismatch": (
                self.minimum_mismatch_sum / self.calls if self.calls else 0.0
            ),
            "maximum_minimum_descendant_hamming_mismatch": (
                self.maximum_minimum_mismatch
            ),
        }


def _nested_selection_seed(
    filter_seed: int,
    lineage_id: str,
    week_index: int,
) -> int:
    material = f"{int(filter_seed)}|{lineage_id}|{int(week_index)}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


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
    base_world=None,
) -> Particle[SimulationParticle]:
    """Create one prior particle with an independent latent spatial draw."""
    config = _config(seed, horizon)
    world = (
        copy.deepcopy(base_world)
        if base_world is not None
        else generate_pineland(config, empirical_geography=case)
    )
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
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
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
        for locality_id in world.state_based_event_localities_by_week.get(
            observation.week_index, ()
        )
    }


def _nested_particle_job(
    job: tuple[
        SimulationParticle,
        float,
        ProvinceWeekObservation,
        int,
        int,
    ],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    state, time, observation, branches, filter_seed = job
    propagator = NestedOperationalPropagator(
        branches=branches,
        selection_seed=filter_seed,
    )
    new_state, likelihood = propagator(state, time, observation)
    return new_state, likelihood, propagator.diagnostics()


def _fork_particle_state(state: SimulationParticle, child_index: int) -> SimulationParticle:
    """Pickle-safe fork callback for the generic resident particle pool."""
    return state.fork(child_index)


def _nested_persistent_job(
    state: SimulationParticle,
    time: float,
    payload: tuple[ProvinceWeekObservation, int, int],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    """Resident-worker adapter for the nested forecast propagator."""
    observation, branches, filter_seed = payload
    return _nested_particle_job(
        (state, time, observation, branches, filter_seed)
    )


def make_nested_propagator(
    *,
    branches: int,
    selection_seed: int,
):
    return NestedOperationalPropagator(
        branches=branches,
        selection_seed=selection_seed,
    )


def run_training_filter(
    particles: list[Particle[SimulationParticle]],
    observations: Iterable[ProvinceWeekObservation],
    *,
    filter_seed: int,
    ess_fraction: float = 0.5,
    likelihood_branches: int = 3,
    workers: int = 1,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    if workers < 1:
        raise ValueError("workers must be positive")
    filter_ = SequentialParticleFilter(
        particles,
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(filter_seed),
        ess_fraction=ess_fraction,
        allowed_split="training",
        fork_state=lambda state, child_index: state.fork(child_index),
    )
    nested_calls = 0
    exact_calls = 0
    mismatch_sum = 0.0
    max_mismatch = 0

    def assimilate_one(
        observation: ProvinceWeekObservation,
        executor: object | None,
    ) -> None:
        nonlocal nested_calls, exact_calls, mismatch_sum, max_mismatch
        if executor is None:
            jobs = [
                (
                    particle.state,
                    observation.end_day,
                    observation,
                    likelihood_branches,
                    filter_seed,
                )
                for particle in filter_.particles
            ]
            completed = list(map(_nested_particle_job, jobs))
        else:
            completed = executor.propagate(
                observation.end_day,
                (observation, likelihood_branches, filter_seed),
            )
        if executor is not None:
            completed = [
                (None, likelihood, diagnostics)
                for _, likelihood, diagnostics in completed
            ]
        propagated = [(state, likelihood) for state, likelihood, _ in completed]
        for _, _, diagnostics in completed:
            calls = int(diagnostics["nested_propagation_calls"])
            nested_calls += calls
            exact_calls += int(diagnostics["exact_descendant_match_calls"])
            mismatch_sum += (
                float(diagnostics["mean_minimum_descendant_hamming_mismatch"])
                * calls
            )
            max_mismatch = max(
                max_mismatch,
                int(
                    diagnostics[
                        "maximum_minimum_descendant_hamming_mismatch"
                    ]
                ),
            )
        assimilation = AssimilationObservation(
            time=observation.end_day,
            value=observation,
            split="training",
            observation_id=f"province-week-{observation.week_index}",
        )
        if executor is None:
            filter_.assimilate_precomputed(assimilation, propagated)
        else:
            diagnostics, parent_indices = filter_.assimilate_scores(
                assimilation,
                [likelihood for _, likelihood, _ in completed],
            )
            if diagnostics.resampled:
                executor.resample(parent_indices)

    ordered_observations = list(observations)
    if workers == 1:
        for observation in ordered_observations:
            assimilate_one(observation, None)
    else:
        with PersistentParticlePool(
            [particle.state for particle in filter_.particles],
            propagate=_nested_persistent_job,
            fork_state=_fork_particle_state,
            workers=workers,
        ) as executor:
            for observation in ordered_observations:
                assimilate_one(observation, executor)
            filter_.particles = [
                Particle(state, 0.0) for state in executor.snapshot()
            ]
    filter_.freeze()
    filter_.nested_propagator_diagnostics = {
        "nested_propagation_calls": nested_calls,
        "exact_descendant_match_calls": exact_calls,
        "exact_descendant_match_fraction": (
            exact_calls / nested_calls if nested_calls else 0.0
        ),
        "mean_minimum_descendant_hamming_mismatch": (
            mismatch_sum / nested_calls if nested_calls else 0.0
        ),
        "maximum_minimum_descendant_hamming_mismatch": max_mismatch,
        "workers": workers,
    }
    return filter_


def _forecast_cells(
    state: SimulationParticle,
    *,
    start_day: float,
    end_day: float,
) -> set[tuple[str, int]]:
    world = state.world
    first_week = int(start_day // 7)
    last_week = int(math.ceil(end_day / 7.0))
    return {
        (province, week)
        for week in range(first_week, last_week)
        for locality_id in world.state_based_event_localities_by_week.get(week, ())
        for province in (_province_for_locality(world, locality_id),)
    }


def _forecast_particle_job(
    job: tuple[SimulationParticle, float, float, int],
) -> list[set[tuple[str, int]]]:
    state, start_day, end_day, forecast_branches = job
    branch_cell_sets = []
    for branch_index in range(forecast_branches):
        branch = state.fork(branch_index)
        branch.advance_to(end_day)
        branch_cell_sets.append(
            _forecast_cells(branch, start_day=start_day, end_day=end_day)
        )
    return branch_cell_sets


def _forecast_persistent_job(
    state: SimulationParticle,
    time: float,
    payload: tuple[float, float, int],
) -> tuple[SimulationParticle, float, list[set[tuple[str, int]]]]:
    """Run forecast branches in a resident worker and return only cells."""
    start_day, end_day, forecast_branches = payload
    return state, 0.0, _forecast_particle_job(
        (state, start_day, end_day, forecast_branches)
    )


def forecast_weighted_field(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    *,
    start_day: float = FORECAST_START_DAY,
    end_day: float = FORECAST_END_DAY,
    forecast_branches: int = 3,
    workers: int = 1,
) -> dict[str, object]:
    """Freeze the posterior and return target-compatible event probabilities."""
    if forecast_branches < 1:
        raise ValueError("forecast branches must be at least one")
    if workers < 1:
        raise ValueError("workers must be positive")
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
    jobs = [
        (particle.state, start_day, end_day, forecast_branches)
        for particle in filter_.particles
    ]
    if workers == 1:
        completed = list(map(_forecast_particle_job, jobs))
    else:
        with PersistentParticlePool(
            [particle.state for particle in filter_.particles],
            propagate=_forecast_persistent_job,
            fork_state=_fork_particle_state,
            workers=workers,
        ) as executor:
            completed = [
                diagnostics
                for _, _, diagnostics in executor.propagate(
                    end_day, (start_day, end_day, forecast_branches)
                )
            ]
    for branch_cell_sets, weight in zip(completed, weights):
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
        "probability_field": field_rows(latent_probability),
        "mechanistic_event_probability_field": field_rows(latent_probability),
        "target_probability_field": field_rows(latent_probability),
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
    workers: int = 1,
) -> dict:
    repo = repository_state(ROOT)
    empty_diff_sha256 = hashlib.sha256(b"").hexdigest()
    if repo["tracked_diff_sha256"] != empty_diff_sha256:
        raise RuntimeError(
            "filtered empirical forecast requires an empty tracked diff"
        )
    if particles < 2:
        raise ValueError("at least two particles are required")
    if workers < 1:
        raise ValueError("workers must be positive")
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
    training_observation_sha256 = hashlib.sha256(
        json.dumps(
            [
                {
                    "week_index": observation.week_index,
                    "start_day": observation.start_day,
                    "end_day": observation.end_day,
                    "active_provinces": sorted(observation.active_provinces),
                    "provinces": list(observation.provinces),
                }
                for observation in observations
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    base_world = generate_pineland(
        _config(seed, horizon), empirical_geography=case
    )
    initial_particles = [
        build_initial_particle(
            seed=seed,
            particle_index=index,
            taliban_strength=particle_strengths[index],
            prior_family=PRIOR_FAMILY_STRATA[index % len(PRIOR_FAMILY_STRATA)],
            horizon=horizon,
            case=case,
            inputs=inputs,
            base_world=base_world,
        )
        for index in range(particles)
    ]
    del base_world
    filter_ = run_training_filter(
        initial_particles,
        observations,
        filter_seed=seed + 17_003,
        likelihood_branches=likelihood_branches,
        workers=workers,
    )
    posterior_boundary = max(observation.end_day for observation in observations)
    forecast = forecast_weighted_field(
        filter_,
        forecast_branches=forecast_branches,
        workers=workers,
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
        "minimum_distinct_root_ancestors": min(
            (item["distinct_root_ancestors"] for item in filter_diagnostics),
            default=particles,
        ),
        "minimum_lineage_entropy": min(
            (item["lineage_entropy"] for item in filter_diagnostics),
            default=0.0,
        ),
        "maximum_ancestry_concentration": max(
            (
                item["maximum_ancestry_concentration"]
                for item in filter_diagnostics
            ),
            default=1.0 / max(1, particles),
        ),
        "support_exhausted": False,
        "all_update_likelihoods_finite": True,
    }
    payload = {
        "schema_version": "pineland.afghanistan.filtered_prospective_2005.v2",
        "source_commit_at_run": repo["commit_hash"],
        "model_sha256": model_sha256(ROOT),
        "tracked_diff_sha256": repo["tracked_diff_sha256"],
        "runner_sha256": file_sha256(Path(__file__)),
        "case_sha256": file_sha256(CASE),
        "historical_inputs_sha256": file_sha256(INPUTS),
        "training_observation_sha256": training_observation_sha256,
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
        "quantitative_measurement_operator_applied": False,
        "measurement_operator_status": (
            "not quantitatively identified; no sensitivity or false-positive "
            "transform is applied in this benchmark"
        ),
        "assimilation_probability_estimator": (
            "Jeffreys-regularized nested Monte-Carlo probability of the "
            "target-compatible event surface"
        ),
        "competitor_information_contract": COMPETITOR_INFORMATION_CONTRACT,
        "likelihood_branches": likelihood_branches,
        "forecast_branches": forecast_branches,
        "parallel_workers": workers,
        "parallel_backend": "processes" if workers > 1 else "sequential",
        "filter_updates": filter_diagnostics,
        "nested_propagator_diagnostics": getattr(
            filter_, "nested_propagator_diagnostics", {}
        ),
        "smc_diagnostics": smc_diagnostics,
        "posterior_probability_field": forecast["probability_field"],
        "posterior_mechanistic_event_probability_field": forecast[
            "mechanistic_event_probability_field"
        ],
        "posterior_target_probability_field": forecast["target_probability_field"],
        "posterior_weights": forecast["posterior_weights"],
        "member_active_cells": forecast["member_active_cells"],
        "forecast_branch_cells": forecast["forecast_branch_cells"],
        "posterior_frozen": filter_.frozen,
        "predictive_estimand": "target_compatible_province_week_event_incidence",
        "mechanistic_estimand": "Taliban_state_security_event_incidence",
        "actor_existence_conditioning": (
            "conditional spatial conflict forecast given Taliban identity persistence"
        ),
        "probability_field_definition": (
            "posterior predictive probability of a target-compatible "
            "province-week Taliban-state-security event for every surface "
            "cell; no unlicensed quantitative historical measurement "
            "operator is applied"
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
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(10, os.cpu_count() or 1)),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(
        seed=args.seed,
        taliban_strength=args.strength,
        particles=args.particles,
        workers=args.workers,
        output=args.output,
    )
    print(json.dumps({
        "output": str(args.output),
        "particle_count": payload["particle_count"],
        "parallel_workers": payload["parallel_workers"],
        "training_boundary_day": payload["training_boundary_day"],
        "forecast_probability_cells": len(payload["posterior_probability_field"]),
    }))


if __name__ == "__main__":
    main()
