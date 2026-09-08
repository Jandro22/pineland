"""Development runner for a training-filtered Afghanistan 2005 forecast.

This runner is intentionally separate from the consumed frozen-core 2005
artifact.  It reads only complete 2004 province-week observations, updates a
posterior ensemble of live simulation particles, freezes that ensemble at the
training boundary, and then propagates it through the 2005 forecast window.
No 2005 outcome row is used by the runner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import random
import sys
from time import perf_counter, process_time
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
    ParticleBatchState,
    PersistentParticlePool,
    SequentialParticleFilter,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    NativeEnsembleRunner,
    generate_pineland,
)
from pineland_sim.state_estimation import (  # noqa: E402
    binary_mcse,
    binary_mcse_upper_bound,
    GuidedProposalPropagator,
    monte_carlo_standard_error,
    RaoBlackwellizedActivityLikelihood,
    particle_weights,
)
from pineland_sim.experimental_methods import ExperimentalMethodGate  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    decision_state_sha256,
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
POSTERIOR_CACHE_SCHEMA = "pineland.afghanistan.posterior_cache.v1"
TRAINING_RESTART_SCHEMA = "pineland.afghanistan.training_restart.v1"
INITIAL_PARTICLE_CACHE_SCHEMA = "pineland.afghanistan.initial_particle_cache.v1"
FORECAST_CACHE_SCHEMA = "pineland.afghanistan.forecast_cache.v1"
RESIDENT_CACHE_SCHEMA = "pineland.afghanistan.resident_particle_cache.v1"
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
    province_bits: dict[str, int] = field(init=False, repr=False, compare=False)
    active_mask: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        bits = {province: 1 << index for index, province in enumerate(self.provinces)}
        object.__setattr__(self, "province_bits", bits)
        object.__setattr__(
            self,
            "active_mask",
            sum(bits[province] for province in self.active_provinces),
        )


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


def _conditioned_branch_mask_index(
    branch_masks: list[int],
    observed_mask: int,
    rng: random.Random,
) -> tuple[int, int, bool]:
    """Bitset-equivalent descendant selection for compact province surfaces."""
    if not branch_masks:
        raise ValueError("at least one branch is required")
    mismatches = [
        (int(mask) ^ int(observed_mask)).bit_count()
        for mask in branch_masks
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

    def __init__(
        self,
        *,
        branches: int,
        selection_seed: int,
        consume_parent_branch: bool = True,
    ) -> None:
        if branches < 1:
            raise ValueError("likelihood branches must be at least one")
        self.branches = branches
        self.selection_seed = int(selection_seed)
        self.consume_parent_branch = bool(consume_parent_branch)
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
        parent_lineage = state.lineage_id
        candidate_states: list[SimulationParticle] = []
        minimum_mismatch: int | None = None
        active_counts = [0] * len(observation.provinces)
        for branch_index in range(self.branches):
            if (
                self.consume_parent_branch
                and branch_index == self.branches - 1
            ):
                branch = state.consume_fork(branch_index)
            else:
                branch = state.fork(branch_index)
            branch.advance_to(time)
            active_mask = _active_province_mask(branch, observation)
            mismatch = (
                int(active_mask) ^ int(observation.active_mask)
            ).bit_count()
            if (
                minimum_mismatch is None
                or mismatch < minimum_mismatch
            ):
                minimum_mismatch = mismatch
                candidate_states = [branch]
            elif mismatch == minimum_mismatch:
                candidate_states.append(branch)
            for index in range(len(active_counts)):
                active_counts[index] += int(bool(active_mask & (1 << index)))

        log_likelihood = 0.0
        for index, province in enumerate(observation.provinces):
            probability = _jeffreys_branch_probability(
                active_counts[index], self.branches
            )
            log_likelihood += _bernoulli_log_probability(
                probability,
                bool(observation.active_mask & observation.province_bits[province]),
            )

        if minimum_mismatch is None or not candidate_states:
            raise RuntimeError("nested propagation produced no descendants")
        selection_rng = random.Random(
            _nested_selection_seed(
                self.selection_seed,
                parent_lineage,
                observation.week_index,
            )
        )
        selected_state = candidate_states[
            selection_rng.randrange(len(candidate_states))
        ]
        exact = minimum_mismatch == 0
        self.calls += 1
        self.exact_match_calls += int(exact)
        self.minimum_mismatch_sum += minimum_mismatch
        self.maximum_minimum_mismatch = max(
            self.maximum_minimum_mismatch, minimum_mismatch
        )
        return selected_state, log_likelihood

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


class RaoBlackwellizedOperationalPropagator:
    """One-trajectory operational propagator using the action-hazard ledger.

    Organized-action opportunities already expose their integrated hazard in
    the latent world.  This propagator scores the complete province-week
    surface from those hazards instead of simulating a fixed collection of
    descendant branches and selecting one by Hamming distance.  It is an
    explicitly opt-in research method; the historical runner keeps the nested
    branch contract unless a caller supplies a validated method gate.
    """

    def __init__(
        self,
        *,
        likelihood: RaoBlackwellizedActivityLikelihood | None = None,
        channels: tuple[str, ...] = ("organized_action",),
    ) -> None:
        self.likelihood = likelihood or RaoBlackwellizedActivityLikelihood()
        self.channels = tuple(str(channel) for channel in channels)
        self.calls = 0
        self.hazard_opportunities = 0

    def _hazards_by_province(
        self,
        state: SimulationParticle,
        observation: ProvinceWeekObservation,
    ) -> dict[str, tuple[float, ...]]:
        hazards: dict[str, list[float]] = {
            province: [] for province in observation.provinces
        }
        for (week, locality_id, channel), integrated_hazard in sorted(
            state.world.activity_hazard_ledger.items()
        ):
            if int(week) != int(observation.week_index):
                continue
            if self.channels and str(channel) not in self.channels:
                continue
            province = _province_for_locality(state.world, locality_id)
            if province in hazards and float(integrated_hazard) > 0.0:
                hazards[province].append(float(integrated_hazard))
                self.hazard_opportunities += 1
        return {province: tuple(values) for province, values in hazards.items()}

    def __call__(
        self,
        state: SimulationParticle,
        time: float,
        observation: ProvinceWeekObservation,
    ) -> tuple[SimulationParticle, float]:
        state.advance_to(time)
        hazards = self._hazards_by_province(state, observation)
        observed = {
            province: province in observation.active_provinces
            for province in observation.provinces
        }
        score = self.likelihood.score(observed, hazards)
        self.calls += 1
        return state, float(score)

    def diagnostics(self) -> dict[str, float | int]:
        return {
            "rao_blackwellized_calls": self.calls,
            "hazard_opportunities": self.hazard_opportunities,
            "nested_propagation_calls": 0,
            "exact_descendant_match_calls": 0,
            "exact_descendant_match_fraction": 0.0,
            "mean_minimum_descendant_hamming_mismatch": 0.0,
            "maximum_minimum_descendant_hamming_mismatch": 0,
        }


def _nested_selection_seed(
    filter_seed: int,
    lineage_id: str,
    week_index: int,
) -> int:
    material = f"{int(filter_seed)}|{lineage_id}|{int(week_index)}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _posterior_cache_digest(cache_key: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            cache_key, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _posterior_cache_paths(
    cache_dir: Path,
    cache_key: dict[str, object],
) -> tuple[Path, Path]:
    digest = _posterior_cache_digest(cache_key)
    return (
        cache_dir / f"posterior-{digest}.json",
        cache_dir / f"posterior-{digest}.pkl",
    )


def _initial_particle_cache_key(
    cache_key: dict[str, object],
    *,
    particle_index: int,
    taliban_strength: float,
    prior_family: str,
) -> dict[str, object]:
    return {
        "schema_version": INITIAL_PARTICLE_CACHE_SCHEMA,
        "source_commit": cache_key["source_commit"],
        "model_sha256": cache_key["model_sha256"],
        "runner_sha256": cache_key["runner_sha256"],
        "case_sha256": cache_key["case_sha256"],
        "historical_inputs_sha256": cache_key["historical_inputs_sha256"],
        "seed": cache_key["seed"],
        "horizon": cache_key["horizon"],
        "execution_backend": cache_key.get("execution_backend", "optimized"),
        "particle_index": int(particle_index),
        "taliban_initial_strength": float(taliban_strength),
        "prior_family": str(prior_family),
        "python_cache_tag": cache_key["python_cache_tag"],
    }


def _initial_particle_cache_paths(
    cache_dir: Path, key: dict[str, object]
) -> tuple[Path, Path]:
    digest = _posterior_cache_digest(key)
    return (
        cache_dir / f"initial-{digest}.json",
        cache_dir / f"initial-{digest}.pkl",
    )


def _save_initial_particle_cache(
    cache_dir: Path,
    key: dict[str, object],
    particle: Particle[SimulationParticle],
) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, payload_path = _initial_particle_cache_paths(cache_dir, key)
    payload = pickle.dumps(particle, protocol=pickle.HIGHEST_PROTOCOL)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    payload_tmp = payload_path.with_suffix(payload_path.suffix + ".tmp")
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    payload_tmp.write_bytes(payload)
    os.replace(payload_tmp, payload_path)
    manifest = {
        "schema_version": INITIAL_PARTICLE_CACHE_SCHEMA,
        "cache_key": key,
        "payload_sha256": payload_sha256,
        "payload_bytes": len(payload),
        "format": "trusted-local-python-pickle",
        "canonical_scientific_artifact": False,
    }
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return manifest_path, payload_path


def _load_initial_particle_cache(
    cache_dir: Path, key: dict[str, object]
) -> Particle[SimulationParticle] | None:
    manifest_path, payload_path = _initial_particle_cache_paths(cache_dir, key)
    if not manifest_path.exists() or not payload_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != INITIAL_PARTICLE_CACHE_SCHEMA:
        raise ValueError("initial particle cache schema mismatch")
    if manifest.get("cache_key") != key:
        raise ValueError("initial particle cache provenance mismatch")
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest.get("payload_sha256"):
        raise ValueError("initial particle cache payload hash mismatch")
    return pickle.loads(payload)


def _snapshot_filter(
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
    *,
    states: list[SimulationParticle] | None = None,
) -> dict[str, object]:
    particles = filter_.particles
    if states is not None:
        if len(states) != len(particles):
            raise ValueError("restart snapshot state count does not match filter")
        particles = [
            Particle(state, particle.log_weight)
            for state, particle in zip(states, particles)
        ]
    return {
        "particles": particles,
        "history": filter_.history,
        "root_ancestors": list(filter_._root_ancestors),
        "resampling_events": int(filter_._resampling_events),
        "last_time": float(filter_.last_time),
        "frozen": bool(filter_.frozen),
        "rng_state": filter_.rng.getstate(),
        "nested_propagator_diagnostics": getattr(
            filter_, "nested_propagator_diagnostics", {}
        ),
        "method_diagnostics": getattr(filter_, "method_diagnostics", {}),
        "likelihood_method": getattr(filter_, "likelihood_method", "nested"),
    }


def _training_restart_paths(
    cache_dir: Path,
    cache_key: dict[str, object],
    completed_week_index: int,
) -> tuple[Path, Path]:
    digest = _posterior_cache_digest(cache_key)
    stem = f"training-{digest}-week-{int(completed_week_index):03d}"
    return cache_dir / f"{stem}.json", cache_dir / f"{stem}.pkl"


def _save_training_restart(
    cache_dir: Path,
    cache_key: dict[str, object],
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
    *,
    completed_week_index: int,
    states: list[SimulationParticle] | None = None,
) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, payload_path = _training_restart_paths(
        cache_dir, cache_key, completed_week_index
    )
    payload = pickle.dumps(
        _snapshot_filter(filter_, states=states),
        protocol=pickle.HIGHEST_PROTOCOL,
    )
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    payload_tmp = payload_path.with_suffix(payload_path.suffix + ".tmp")
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    payload_tmp.write_bytes(payload)
    os.replace(payload_tmp, payload_path)
    manifest = {
        "schema_version": TRAINING_RESTART_SCHEMA,
        "cache_key": cache_key,
        "completed_week_index": int(completed_week_index),
        "last_time": float(filter_.last_time),
        "payload_sha256": payload_sha256,
        "payload_bytes": len(payload),
        "format": "trusted-local-python-pickle",
        "canonical_scientific_artifact": False,
    }
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return manifest_path, payload_path


def _load_latest_training_restart(
    cache_dir: Path,
    cache_key: dict[str, object],
    *,
    filter_seed: int,
) -> tuple[
    SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation] | None,
    Path | None,
    int | None,
]:
    digest = _posterior_cache_digest(cache_key)
    candidates = sorted(
        cache_dir.glob(f"training-{digest}-week-*.json"),
        reverse=True,
    ) if cache_dir.exists() else []
    for manifest_path in candidates:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != TRAINING_RESTART_SCHEMA:
                continue
            if manifest.get("cache_key") != cache_key:
                continue
            completed_week = int(manifest["completed_week_index"])
            expected_manifest, payload_path = _training_restart_paths(
                cache_dir, cache_key, completed_week
            )
            if expected_manifest != manifest_path or not payload_path.exists():
                continue
            payload = payload_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != manifest.get(
                "payload_sha256"
            ):
                continue
            filter_ = _restore_filter(
                pickle.loads(payload), filter_seed=filter_seed
            )
            filter_.frozen = False
            return filter_, manifest_path, completed_week
        except (KeyError, TypeError, ValueError, OSError, pickle.PickleError):
            continue
    return None, None, None


def _restore_filter(
    snapshot: dict[str, object],
    *,
    filter_seed: int,
    ess_fraction: float = 0.5,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    filter_ = SequentialParticleFilter(
        list(snapshot["particles"]),
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(filter_seed),
        ess_fraction=ess_fraction,
        allowed_split="training",
        fork_state=lambda state, child_index: state.fork(child_index),
    )
    filter_.history = list(snapshot["history"])
    filter_._root_ancestors = list(snapshot["root_ancestors"])
    filter_._resampling_events = int(snapshot["resampling_events"])
    filter_.last_time = float(snapshot["last_time"])
    filter_.rng.setstate(snapshot["rng_state"])
    filter_.frozen = bool(snapshot["frozen"])
    filter_.nested_propagator_diagnostics = dict(
        snapshot.get("nested_propagator_diagnostics", {})
    )
    filter_.method_diagnostics = dict(snapshot.get("method_diagnostics", {}))
    filter_.likelihood_method = str(
        snapshot.get("likelihood_method", "nested")
    )
    return filter_


def _reattach_particle_states(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    states: list[SimulationParticle],
) -> None:
    """Attach resident-worker states without altering coordinator weights."""
    if len(states) != len(filter_.particles):
        raise ValueError("worker snapshot size does not match the filter")
    log_weights = [particle.log_weight for particle in filter_.particles]
    filter_.particles = [
        Particle(state, log_weight)
        for state, log_weight in zip(states, log_weights)
    ]


def _save_posterior_cache(
    cache_dir: Path,
    cache_key: dict[str, object],
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, payload_path = _posterior_cache_paths(cache_dir, cache_key)
    payload = pickle.dumps(_snapshot_filter(filter_), protocol=pickle.HIGHEST_PROTOCOL)
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    payload_tmp = payload_path.with_suffix(payload_path.suffix + ".tmp")
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    payload_tmp.write_bytes(payload)
    os.replace(payload_tmp, payload_path)
    manifest = {
        "schema_version": POSTERIOR_CACHE_SCHEMA,
        "cache_key": cache_key,
        "payload_sha256": payload_sha256,
        "payload_bytes": len(payload),
        "format": "trusted-local-python-pickle",
        "canonical_scientific_artifact": False,
    }
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return manifest_path, payload_path


def _load_posterior_cache(
    cache_dir: Path,
    cache_key: dict[str, object],
    *,
    filter_seed: int,
) -> tuple[
    SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    Path,
]:
    manifest_path, payload_path = _posterior_cache_paths(cache_dir, cache_key)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != POSTERIOR_CACHE_SCHEMA:
        raise ValueError("posterior cache schema mismatch")
    if manifest.get("cache_key") != cache_key:
        raise ValueError("posterior cache provenance mismatch")
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest.get("payload_sha256"):
        raise ValueError("posterior cache payload hash mismatch")
    # This cache is intentionally a local execution accelerator rather than a
    # publication artifact.  Only content-addressed files created by this
    # runner should ever be loaded.
    snapshot = pickle.loads(payload)
    return (
        _restore_filter(snapshot, filter_seed=filter_seed),
        manifest_path,
    )


def _resident_cache_paths(
    cache_dir: Path,
    cache_key: dict[str, object],
    *,
    stage: str,
    completed_week_index: int | None = None,
) -> tuple[Path, Path, str]:
    digest = _posterior_cache_digest(cache_key)
    suffix = (
        f"-week-{int(completed_week_index):03d}"
        if completed_week_index is not None else ""
    )
    prefix = f"{stage}-resident-{digest}{suffix}"
    return (
        cache_dir / f"{prefix}.json",
        cache_dir / f"{prefix}.meta.pkl",
        prefix,
    )


def _save_resident_particle_cache(
    cache_dir: Path,
    cache_key: dict[str, object],
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
    executor: PersistentParticlePool,
    *,
    stage: str,
    completed_week_index: int | None = None,
) -> Path:
    """Persist filter metadata centrally and live particle payloads in workers."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, metadata_path, prefix = _resident_cache_paths(
        cache_dir,
        cache_key,
        stage=stage,
        completed_week_index=completed_week_index,
    )
    metadata = pickle.dumps(
        _snapshot_filter(filter_),
        protocol=pickle.HIGHEST_PROTOCOL,
    )
    metadata_sha256 = hashlib.sha256(metadata).hexdigest()
    metadata_tmp = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    metadata_tmp.write_bytes(metadata)
    os.replace(metadata_tmp, metadata_path)
    persisted = executor.persist_states(str(cache_dir.resolve()), prefix)
    manifest = {
        "schema_version": RESIDENT_CACHE_SCHEMA,
        "cache_key": cache_key,
        "stage": stage,
        "completed_week_index": completed_week_index,
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": metadata_sha256,
        "particles": persisted,
        "canonical_scientific_artifact": False,
    }
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return manifest_path


def _load_resident_particle_cache(
    manifest_path: Path,
    cache_key: dict[str, object],
    *,
    filter_seed: int,
) -> tuple[
    SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    Path,
    list[str],
    int | None,
]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != RESIDENT_CACHE_SCHEMA:
        raise ValueError("resident particle cache schema mismatch")
    if manifest.get("cache_key") != cache_key:
        raise ValueError("resident particle cache provenance mismatch")
    metadata_path = Path(manifest["metadata_path"])
    if not metadata_path.exists():
        raise ValueError("resident particle cache metadata is missing")
    metadata = metadata_path.read_bytes()
    if hashlib.sha256(metadata).hexdigest() != manifest.get("metadata_sha256"):
        raise ValueError("resident particle cache metadata hash mismatch")
    particle_rows = sorted(
        manifest["particles"], key=lambda row: int(row["slot"])
    )
    expected_slots = list(range(len(particle_rows)))
    if [int(row["slot"]) for row in particle_rows] != expected_slots:
        raise ValueError("resident particle cache slots are not contiguous")
    state_paths: list[str] = []
    for row in particle_rows:
        path = Path(row["path"])
        if not path.exists() or path.stat().st_size != int(row["bytes"]):
            raise ValueError("resident particle cache state payload is missing or truncated")
        if file_sha256(path) != row.get("payload_sha256"):
            raise ValueError("resident particle cache state payload hash mismatch")
        state_paths.append(str(path))
    filter_ = _restore_filter(
        pickle.loads(metadata), filter_seed=filter_seed
    )
    return (
        filter_,
        manifest_path,
        state_paths,
        manifest.get("completed_week_index"),
    )


def _load_latest_resident_training_restart(
    cache_dir: Path,
    cache_key: dict[str, object],
    *,
    filter_seed: int,
) -> tuple[
    SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation] | None,
    Path | None,
    int | None,
    list[str] | None,
]:
    digest = _posterior_cache_digest(cache_key)
    candidates = sorted(
        cache_dir.glob(f"training-resident-{digest}-week-*.json"),
        reverse=True,
    ) if cache_dir.exists() else []
    for manifest_path in candidates:
        try:
            filter_, manifest, paths, week = _load_resident_particle_cache(
                manifest_path, cache_key, filter_seed=filter_seed
            )
            filter_.frozen = False
            return filter_, manifest, week, paths
        except (KeyError, TypeError, ValueError, OSError, pickle.PickleError):
            continue
    return None, None, None, None


def _forecast_cache_key(
    cache_key: dict[str, object],
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
    *,
    start_day: float,
    end_day: float,
    forecast_branches: int,
    particle_metadata: list[dict[str, object]] | None = None,
    mcse_tolerance: float | None = None,
    min_forecast_trajectories: int = 32,
    max_forecast_trajectories: int | None = None,
    forecast_seed: int | None = None,
) -> dict[str, object]:
    """Bind forecast reuse to the exact frozen posterior and forecast contract."""
    if particle_metadata is None:
        particle_metadata = [
            {
                "lineage_id": particle.state.lineage_id,
                "decision_state_sha256": decision_state_sha256(
                    particle.state.world
                ),
            }
            for particle in filter_.particles
        ]
    return {
        "schema_version": FORECAST_CACHE_SCHEMA,
        "posterior_cache_key_sha256": _posterior_cache_digest(cache_key),
        "posterior_last_time": float(filter_.last_time),
        "posterior_weights": particle_weights(filter_.particles),
        "posterior_lineages": [
            str(item["lineage_id"]) for item in particle_metadata
        ],
        "posterior_decision_state_sha256": [
            str(item["decision_state_sha256"])
            for item in particle_metadata
        ],
        "forecast_start_day": float(start_day),
        "forecast_end_day": float(end_day),
        "forecast_branches": int(forecast_branches),
        "forecast_mcse_tolerance": (
            None if mcse_tolerance is None else float(mcse_tolerance)
        ),
        "min_forecast_trajectories": int(min_forecast_trajectories),
        "max_forecast_trajectories": (
            None if max_forecast_trajectories is None
            else int(max_forecast_trajectories)
        ),
        "forecast_seed": None if forecast_seed is None else int(forecast_seed),
        "python_cache_tag": sys.implementation.cache_tag,
    }


def _forecast_cache_paths(
    cache_dir: Path,
    key: dict[str, object],
) -> tuple[Path, Path]:
    digest = _posterior_cache_digest(key)
    return (
        cache_dir / f"forecast-{digest}.manifest.json",
        cache_dir / f"forecast-{digest}.json",
    )


def _save_forecast_cache(
    cache_dir: Path,
    key: dict[str, object],
    forecast: dict[str, object],
) -> tuple[Path, Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, payload_path = _forecast_cache_paths(cache_dir, key)
    payload = (
        json.dumps(forecast, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    payload_tmp = payload_path.with_suffix(payload_path.suffix + ".tmp")
    manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    payload_tmp.write_bytes(payload)
    os.replace(payload_tmp, payload_path)
    manifest = {
        "schema_version": FORECAST_CACHE_SCHEMA,
        "cache_key": key,
        "payload_sha256": payload_sha256,
        "payload_bytes": len(payload),
        "format": "json-compute-cache",
        "canonical_scientific_artifact": False,
    }
    manifest_tmp.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(manifest_tmp, manifest_path)
    return manifest_path, payload_path


def _load_forecast_cache(
    cache_dir: Path,
    key: dict[str, object],
) -> tuple[dict[str, object], Path] | None:
    manifest_path, payload_path = _forecast_cache_paths(cache_dir, key)
    if not manifest_path.exists() or not payload_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != FORECAST_CACHE_SCHEMA:
        raise ValueError("forecast cache schema mismatch")
    if manifest.get("cache_key") != key:
        raise ValueError("forecast cache provenance mismatch")
    payload = payload_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest.get("payload_sha256"):
        raise ValueError("forecast cache payload hash mismatch")
    return json.loads(payload.decode("utf-8")), manifest_path


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


def _config(
    seed: int,
    horizon: float,
    *,
    execution_backend: str = "optimized",
) -> SimulationConfig:
    config = SimulationConfig(
        seed=seed,
        initialization_seed=20040101,
        horizon_days=horizon,
        agent_count=401,
        locality_count=401,
        output_mode="ensemble",
    )
    if execution_backend not in {"optimized", "ensemble"}:
        raise ValueError("execution_backend must be 'optimized' or 'ensemble'")
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
    execution_backend: str = "optimized",
) -> Particle[SimulationParticle]:
    """Create one prior particle with an independent latent spatial draw."""
    config = _config(seed, horizon, execution_backend=execution_backend)
    world = (
        base_world.clone(share_static=True)
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
        execution_backend=execution_backend,
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
    cached = world.evaluation_region_by_locality.get(locality_id)
    if cached is not None:
        return cached
    district_id = world.localities[locality_id].district_id
    province = world.district_hierarchy[district_id]["province"]
    world.evaluation_region_by_locality[locality_id] = province
    return province


def _precompute_province_lookup(world) -> None:
    world.evaluation_region_by_locality = {
        locality_id: world.district_hierarchy[
            world.localities[locality_id].district_id
        ]["province"]
        for locality_id in world.localities
    }


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


def _active_province_mask(
    state: SimulationParticle,
    observation: ProvinceWeekObservation,
) -> int:
    world = state.world
    mask = 0
    bits = observation.province_bits
    for locality_id in world.state_based_event_localities_by_week.get(
        observation.week_index, ()
    ):
        bit = bits.get(_province_for_locality(world, locality_id))
        if bit is not None:
            mask |= bit
    return mask


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


def _nested_packed_particle_job(
    job: tuple[
        SimulationParticle,
        float,
        ProvinceWeekObservation,
        int,
        int,
    ],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    """Run the exact nested branches through one packed authoritative batch.

    Branch creation and selection are byte-for-byte the nested contract.  Only
    the propagation substrate changes: the three independent descendants share
    one packed topology/hot-state execution object and retain their reference
    schedulers for sparse oracle boundaries.
    """
    state, time, observation, branches, filter_seed = job
    parent_lineage = state.lineage_id
    branch_states = [
        state.consume_fork(index)
        if index == branches - 1
        else state.fork(index)
        for index in range(branches)
    ]
    batch = ParticleBatchState.from_particles(branch_states)
    runner = NativeEnsembleRunner.from_batch(batch, scheduler_oracle=True)
    batch.advance_to(time, runner=runner)
    active_counts = [0] * len(observation.provinces)
    masks: list[int] = []
    for branch in branch_states:
        mask = _active_province_mask(branch, observation)
        masks.append(mask)
        for province_index in range(len(active_counts)):
            active_counts[province_index] += int(
                bool(mask & (1 << province_index))
            )

    log_likelihood = 0.0
    for province_index, province in enumerate(observation.provinces):
        probability = _jeffreys_branch_probability(
            active_counts[province_index], branches
        )
        log_likelihood += _bernoulli_log_probability(
            probability,
            bool(observation.active_mask & observation.province_bits[province]),
        )
    selected_index, minimum_mismatch, _ = _conditioned_branch_mask_index(
        masks,
        observation.active_mask,
        random.Random(
            _nested_selection_seed(
                filter_seed, parent_lineage, observation.week_index
            )
        ),
    )
    # Only the selected descendant continues.  The branch mask is a scheduler
    # output already resident on each reference world; exporting all discarded
    # lanes would add no scientific information and would pay the full object
    # graph materialization cost three times.
    batch.synchronize_lane_to_world(selected_index)
    diagnostics = {
        "nested_propagation_calls": 1,
        "exact_descendant_match_calls": int(minimum_mismatch == 0),
        "exact_descendant_match_fraction": float(minimum_mismatch == 0),
        "mean_minimum_descendant_hamming_mismatch": minimum_mismatch,
        "maximum_minimum_descendant_hamming_mismatch": minimum_mismatch,
        "packed_runner_sparse_boundaries": int(runner.sparse_boundaries),
    }
    return branch_states[selected_index], log_likelihood, diagnostics


def _global_packed_nested_job(
    states: list[SimulationParticle],
    time: float,
    observation: ProvinceWeekObservation,
    branches: int,
    filter_seed: int,
) -> list[tuple[SimulationParticle, float, dict[str, float | int]]]:
    """Propagate every particle/branch lane in one exact packed batch.

    The branch construction, Jeffreys likelihood, conditioned selection, and
    lineage seed are identical to ``_nested_packed_particle_job``.  Packing
    across particles removes one Python batch construction and one IPC job per
    particle/week while preserving a separate scheduler/RNG lane for every
    branch.  This is an execution-only transformation: no equation or
    observation operator changes.
    """
    if not states:
        raise ValueError("global packed propagation needs at least one state")
    if branches < 1:
        raise ValueError("branches must be positive")
    branch_states: list[SimulationParticle] = []
    parent_lineages: list[str] = []
    for state in states:
        parent_lineages.append(state.lineage_id)
        for index in range(branches):
            branch_states.append(
                state.consume_fork(index)
                if index == branches - 1
                else state.fork(index)
            )
    batch = ParticleBatchState.from_particles(branch_states)
    runner = NativeEnsembleRunner.from_batch(batch, scheduler_oracle=True)
    batch.advance_to(time, runner=runner)

    results: list[tuple[SimulationParticle, float, dict[str, float | int]]] = []
    for parent_index, parent_lineage in enumerate(parent_lineages):
        offset = parent_index * branches
        masks = [
            _active_province_mask(branch_states[offset + index], observation)
            for index in range(branches)
        ]
        log_likelihood = 0.0
        for province in observation.provinces:
            bit = observation.province_bits[province]
            active_count = sum(bool(mask & bit) for mask in masks)
            probability = _jeffreys_branch_probability(active_count, branches)
            log_likelihood += _bernoulli_log_probability(
                probability,
                bool(observation.active_mask & bit),
            )
        selected_index, minimum_mismatch, _ = _conditioned_branch_mask_index(
            masks,
            observation.active_mask,
            random.Random(
                _nested_selection_seed(
                    filter_seed, parent_lineage, observation.week_index
                )
            ),
        )
        selected_lane = offset + selected_index
        batch.synchronize_lane_to_world(selected_lane)
        results.append((
            branch_states[selected_lane],
            log_likelihood,
            {
                "nested_propagation_calls": 1,
                "exact_descendant_match_calls": int(minimum_mismatch == 0),
                "exact_descendant_match_fraction": float(minimum_mismatch == 0),
                "mean_minimum_descendant_hamming_mismatch": minimum_mismatch,
                "maximum_minimum_descendant_hamming_mismatch": minimum_mismatch,
                "packed_runner_sparse_boundaries": int(runner.sparse_boundaries),
            },
        ))
    return results


def _rao_blackwellized_particle_job(
    job: tuple[
        SimulationParticle,
        float,
        ProvinceWeekObservation,
        RaoBlackwellizedActivityLikelihood | None,
    ],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    state, time, observation, likelihood = job
    propagator = RaoBlackwellizedOperationalPropagator(
        likelihood=likelihood,
    )
    new_state, score = propagator(state, time, observation)
    return new_state, score, propagator.diagnostics()


def _guided_particle_job(
    job: tuple[
        SimulationParticle,
        float,
        ProvinceWeekObservation,
        GuidedProposalPropagator,
    ],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    state, time, observation, propagator = job
    new_state, score = propagator(state, time, observation)
    return new_state, float(score), {
        "guided_propagation_calls": 1,
        "nested_propagation_calls": 0,
        "exact_descendant_match_calls": 0,
        "exact_descendant_match_fraction": 0.0,
        "mean_minimum_descendant_hamming_mismatch": 0.0,
        "maximum_minimum_descendant_hamming_mismatch": 0,
    }


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


def _nested_packed_persistent_job(
    state: SimulationParticle,
    time: float,
    payload: tuple[ProvinceWeekObservation, int, int],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    observation, branches, filter_seed = payload
    return _nested_packed_particle_job(
        (state, time, observation, branches, filter_seed)
    )


def _rao_blackwellized_persistent_job(
    state: SimulationParticle,
    time: float,
    payload: tuple[
        ProvinceWeekObservation,
        RaoBlackwellizedActivityLikelihood | None,
    ],
) -> tuple[SimulationParticle, float, dict[str, float | int]]:
    """Resident-worker adapter for the one-trajectory RB propagator."""
    observation, likelihood = payload
    return _rao_blackwellized_particle_job(
        (state, time, observation, likelihood)
    )


def _resident_particle_job(
    state: SimulationParticle,
    time: float,
    payload,
) -> tuple[SimulationParticle, float, dict[str, object]]:
    """Dispatch training and forecast work through one resident pool."""
    if (
        isinstance(payload, tuple)
        and len(payload) == 2
        and payload[0] == "forecast"
    ):
        return _forecast_persistent_job(state, time, payload[1])
    if (
        isinstance(payload, tuple)
        and len(payload) == 3
        and payload[0] == "rao_blackwellized"
    ):
        return _rao_blackwellized_persistent_job(
            state,
            time,
            (payload[1], payload[2]),
        )
    if (
        isinstance(payload, tuple)
        and len(payload) == 4
        and payload[0] == "packed_nested"
    ):
        return _nested_packed_persistent_job(
            state,
            time,
            (payload[1], payload[2], payload[3]),
        )
    if (
        isinstance(payload, tuple)
        and len(payload) == 6
        and payload[0] == "forecast_sample"
    ):
        _, start_day, end_day, branch_index, province_bits, _sample_id = payload
        branch = state.fork(int(branch_index))
        branch.advance_to(float(end_day))
        return state, 0.0, {
            "week_masks": _forecast_week_masks(
                branch,
                start_day=float(start_day),
                end_day=float(end_day),
                province_bits=province_bits,
            ),
            "sample_id": int(_sample_id),
        }
    return _nested_persistent_job(state, time, payload)


def _resident_particle_identity(state: SimulationParticle) -> dict[str, object]:
    """Return cache-key metadata without exporting the resident state."""
    world = state.world
    provinces = tuple(sorted({
        world.evaluation_region_by_locality.get(
            locality_id,
            world.district_hierarchy[world.localities[locality_id].district_id][
                "province"
            ],
        )
        for locality_id in world.localities
    }))
    return {
        "lineage_id": state.lineage_id,
        "decision_state_sha256": decision_state_sha256(world),
        "province_ids": provinces,
        "posterior_summary": world.summary(),
    }


def _resident_particle_hash(state: SimulationParticle) -> dict[str, object]:
    """Return only the state fields needed by execution benchmarks."""
    return {
        "lineage_id": state.lineage_id,
        "decision_state_sha256": decision_state_sha256(state.world),
    }


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
    likelihood_method: str = "nested",
    rb_likelihood: RaoBlackwellizedActivityLikelihood | None = None,
    guided_propagator: GuidedProposalPropagator | None = None,
    method_gate: ExperimentalMethodGate | None = None,
    workers: int = 1,
    resume_filter: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ] | None = None,
    restart_cache_dir: Path | None = None,
    restart_cache_key: dict[str, object] | None = None,
    restart_every_weeks: int = 13,
    collect_worker_diagnostics: bool = False,
    balance_resampling: bool = True,
    resident_pool: PersistentParticlePool | None = None,
    keep_resident: bool = False,
    packed_execution: bool = False,
    global_packed_execution: bool = False,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    if workers < 1:
        raise ValueError("workers must be positive")
    if restart_cache_dir is not None and restart_cache_key is None:
        raise ValueError("restart cache key is required when restart caching is enabled")
    if restart_every_weeks < 1:
        raise ValueError("restart_every_weeks must be positive")
    if resident_pool is not None and workers == 1:
        raise ValueError("resident_pool requires workers greater than one")
    if global_packed_execution and (
        not packed_execution
        or workers != 1
        or resident_pool is not None
    ):
        raise ValueError(
            "global packed execution requires packed_execution=True, workers=1, "
            "and no resident pool"
        )
    likelihood_method = str(likelihood_method)
    if likelihood_method not in {"nested", "rao_blackwellized", "guided"}:
        raise ValueError(
            "likelihood_method must be 'nested', 'rao_blackwellized', or 'guided'"
        )
    if guided_propagator is not None:
        if likelihood_method not in {"nested", "guided"}:
            raise ValueError("guided_propagator conflicts with the selected likelihood method")
        likelihood_method = "guided"
    if likelihood_method != "nested":
        if method_gate is None:
            raise RuntimeError(
                f"{likelihood_method} requires a provenance-bound method gate"
            )
        method_gate.require_synthetic_validation()
        if (
            likelihood_method == "guided"
            and (workers != 1 or resident_pool is not None)
        ):
            raise ValueError(
                "guided proposals currently require the in-process executor"
            )
        if likelihood_method == "guided" and guided_propagator is None:
            raise ValueError("guided likelihood mode requires guided_propagator")
    filter_ = resume_filter or SequentialParticleFilter(
        particles,
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(filter_seed),
        ess_fraction=ess_fraction,
        allowed_split="training",
        fork_state=lambda state, child_index: state.fork(child_index),
    )
    prior_nested = getattr(filter_, "nested_propagator_diagnostics", {})
    nested_calls = int(prior_nested.get("nested_propagation_calls", 0))
    exact_calls = int(prior_nested.get("exact_descendant_match_calls", 0))
    mismatch_sum = (
        float(prior_nested.get("mean_minimum_descendant_hamming_mismatch", 0.0))
        * nested_calls
    )
    max_mismatch = int(
        prior_nested.get("maximum_minimum_descendant_hamming_mismatch", 0)
    )
    method_diagnostics = dict(getattr(filter_, "method_diagnostics", {}))
    filter_.likelihood_method = likelihood_method
    worker_balance_history = list(
        getattr(filter_, "worker_balance_history", [])
    )

    def refresh_nested_diagnostics() -> None:
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
        filter_.method_diagnostics = {
            "likelihood_method": likelihood_method,
            **method_diagnostics,
        }

    def maybe_save_restart(
        observation: ProvinceWeekObservation,
        executor: object | None,
    ) -> None:
        if (
            restart_cache_dir is None
            or restart_cache_key is None
            or (observation.week_index + 1) % restart_every_weeks != 0
        ):
            return
        refresh_nested_diagnostics()
        if executor is not None and all(
            particle.state is None for particle in filter_.particles
        ):
            _save_resident_particle_cache(
                restart_cache_dir,
                restart_cache_key,
                filter_,
                executor,
                stage="training",
                completed_week_index=observation.week_index,
            )
        else:
            states = executor.snapshot() if executor is not None else None
            _save_training_restart(
                restart_cache_dir,
                restart_cache_key,
                filter_,
                completed_week_index=observation.week_index,
                states=states,
            )

    def assimilate_one(
        observation: ProvinceWeekObservation,
        executor: object | None,
    ) -> None:
        nonlocal nested_calls, exact_calls, mismatch_sum, max_mismatch
        if executor is None:
            if likelihood_method == "nested":
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
                completed = list(map(
                    _nested_packed_particle_job if packed_execution
                    else _nested_particle_job,
                    jobs,
                ))
            elif likelihood_method == "rao_blackwellized":
                jobs = [
                    (
                        particle.state,
                        observation.end_day,
                        observation,
                        rb_likelihood,
                    )
                    for particle in filter_.particles
                ]
                completed = list(map(_rao_blackwellized_particle_job, jobs))
            else:
                assert guided_propagator is not None
                jobs = [
                    (
                        particle.state,
                        observation.end_day,
                        observation,
                        guided_propagator,
                    )
                    for particle in filter_.particles
                ]
                completed = list(map(_guided_particle_job, jobs))
        else:
            assignment_before = (
                executor.assignment_counts()
                if collect_worker_diagnostics else None
            )
            resident_payload = (
                ("rao_blackwellized", observation, rb_likelihood)
                if likelihood_method == "rao_blackwellized"
                else (
                    ("packed_nested", observation, likelihood_branches, filter_seed)
                    if packed_execution
                    else (observation, likelihood_branches, filter_seed)
                )
            )
            if collect_worker_diagnostics:
                completed, worker_rows = executor.propagate_profiled(
                    observation.end_day,
                    resident_payload,
                )
            else:
                completed = executor.propagate(
                    observation.end_day,
                    resident_payload,
                )
                worker_rows = None
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
            for key, value in diagnostics.items():
                if key.endswith("_calls") or key == "hazard_opportunities":
                    method_diagnostics[key] = int(method_diagnostics.get(key, 0)) + int(value)
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
            resample_transport = None
            if diagnostics.resampled:
                if balance_resampling:
                    resample_transport = executor.resample_balanced(
                        parent_indices
                    )
                else:
                    executor.resample(parent_indices)
            if collect_worker_diagnostics:
                worker_balance_history.append({
                    "week_index": int(observation.week_index),
                    "end_day": float(observation.end_day),
                    "posterior_ess": float(diagnostics.posterior_ess),
                    "maximum_posterior_weight": float(
                        diagnostics.maximum_posterior_weight
                    ),
                    "resampled": bool(diagnostics.resampled),
                    "unique_parent_particles": int(
                        diagnostics.unique_parent_particles
                    ),
                    "assignment_before": list(assignment_before or ()),
                    "assignment_after": executor.assignment_counts(),
                    "worker_compute": list(worker_rows or ()),
                    "resample_transport": resample_transport,
                })

    ordered_observations = [
        observation
        for observation in observations
        if observation.end_day > filter_.last_time + 1e-12
    ]
    if workers == 1:
        for observation in ordered_observations:
            assimilate_one(observation, None)
            maybe_save_restart(observation, None)
    else:
        owns_executor = resident_pool is None
        executor = resident_pool
        if global_packed_execution:
            completed = _global_packed_nested_job(
                [particle.state for particle in filter_.particles],
                observation.end_day,
                observation,
                likelihood_branches,
                filter_seed,
            )
        elif executor is None:
            initial_states = [particle.state for particle in filter_.particles]
            executor = PersistentParticlePool(
                initial_states,
                propagate=_resident_particle_job,
                fork_state=_fork_particle_state,
                workers=workers,
                summarize_state=_resident_particle_identity,
            )
            # Windows spawn has already serialized the states into the
            # resident workers.  Drop the coordinator's duplicate references
            # before propagation so the fixed ensemble is bounded by worker
            # residency rather than by an avoidable parent-side copy.
            del initial_states
        try:
            # The coordinator retains only weights/ancestry metadata while
            # workers own the mutable simulation objects.
            filter_.particles = [
                Particle(None, particle.log_weight)
                for particle in filter_.particles
            ]
            particles.clear()
            for observation in ordered_observations:
                assimilate_one(observation, executor)
                maybe_save_restart(observation, executor)
            if owns_executor or not keep_resident:
                _reattach_particle_states(filter_, executor.snapshot())
        finally:
            if owns_executor or not keep_resident:
                executor.close()
    filter_.freeze()
    refresh_nested_diagnostics()
    if collect_worker_diagnostics:
        filter_.worker_balance_history = worker_balance_history
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


def _forecast_week_masks(
    state: SimulationParticle,
    *,
    start_day: float,
    end_day: float,
    province_bits: dict[str, int],
) -> dict[int, int]:
    """Compact forecast event surface as one integer bitset per week."""
    world = state.world
    first_week = int(start_day // 7)
    last_week = int(math.ceil(end_day / 7.0))
    masks: dict[int, int] = {}
    for week in range(first_week, last_week):
        mask = 0
        for locality_id in world.state_based_event_localities_by_week.get(week, ()):
            bit = province_bits.get(_province_for_locality(world, locality_id))
            if bit is not None:
                mask |= bit
        if mask:
            masks[week] = mask
    return masks


def _mask_cells(
    week_masks: dict[int, int],
    provinces: tuple[str, ...],
    province_bits: dict[str, int],
) -> set[tuple[str, int]]:
    """Convert compact masks to the historical external cell representation."""
    return {
        (province, week)
        for week, mask in week_masks.items()
        for province in provinces
        if mask & province_bits[province]
    }


def _forecast_particle_job(
    job: tuple[
        SimulationParticle,
        float,
        float,
        int,
        dict[str, int],
    ],
    *,
    consume_parent_branch: bool = False,
) -> list[dict[int, int]]:
    state, start_day, end_day, forecast_branches, province_bits = job
    branch_week_masks = []
    for branch_index in range(forecast_branches):
        if (
            consume_parent_branch
            and branch_index == forecast_branches - 1
        ):
            branch = state.consume_fork(branch_index)
        else:
            branch = state.fork(branch_index)
        branch.advance_to(end_day)
        branch_week_masks.append(
            _forecast_week_masks(
                branch,
                start_day=start_day,
                end_day=end_day,
                province_bits=province_bits,
            )
        )
    return branch_week_masks


def _forecast_persistent_job(
    state: SimulationParticle,
    time: float,
    payload: tuple[float, float, int, dict[str, int]],
) -> tuple[SimulationParticle, float, dict[str, object]]:
    """Run forecast branches and return compact forecast/output diagnostics."""
    start_day, end_day, forecast_branches, province_bits = payload
    posterior_summary = state.world.summary()
    return state, 0.0, {
        "branch_week_masks": _forecast_particle_job(
            (state, start_day, end_day, forecast_branches, province_bits),
            consume_parent_branch=True,
        ),
        "posterior_summary": posterior_summary,
    }


def forecast_mcse_controlled_field(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    *,
    start_day: float = FORECAST_START_DAY,
    end_day: float = FORECAST_END_DAY,
    tolerance: float,
    min_trajectories: int = 32,
    max_trajectories: int = 4096,
    seed: int = 0,
    resident_pool: PersistentParticlePool | None = None,
    resident_particle_metadata: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Sample posterior-predictive trajectories until the field MCSE converges.

    A posterior member is selected with its frozen SMC weight for each
    trajectory, then one independent future is forked from that member.  The
    returned field is therefore an ordinary posterior-predictive Monte Carlo
    estimator; unlike the legacy branch count, the stopping rule is attached
    to its stated precision target. Resident workers may evaluate future
    trajectories concurrently while results are consumed in deterministic
    prefix order.
    """
    tolerance = float(tolerance)
    min_trajectories = int(min_trajectories)
    max_trajectories = int(max_trajectories)
    if tolerance <= 0.0:
        raise ValueError("forecast MCSE tolerance must be positive")
    if min_trajectories < 1 or max_trajectories < min_trajectories:
        raise ValueError("invalid forecast trajectory budget")
    if not filter_.particles:
        raise ValueError("MCSE-controlled forecast requires posterior particles")
    if resident_pool is None and any(
        particle.state is None for particle in filter_.particles
    ):
        raise ValueError(
            "MCSE-controlled forecast requires in-process or resident particle states"
        )
    filter_.freeze()
    weights = particle_weights(filter_.particles)
    if resident_pool is None:
        provinces = tuple(sorted({
            _province_for_locality(particle.state.world, locality_id)
            for particle in filter_.particles
            for locality_id in particle.state.world.localities
        }))
        posterior_summaries = [
            particle.state.world.summary() for particle in filter_.particles
        ]
    else:
        metadata = (
            resident_particle_metadata
            if resident_particle_metadata is not None
            else [item for _, item in resident_pool.summarize()]
        )
        provinces = tuple(sorted({
            province
            for particle_metadata in metadata
            for province in particle_metadata["province_ids"]
        }))
        posterior_summaries = [
            dict(particle_metadata.get("posterior_summary", {}))
            for particle_metadata in metadata
        ]
    province_bits = {
        province: 1 << index for index, province in enumerate(provinces)
    }
    first_week = int(start_day // 7)
    last_week = int(math.ceil(end_day / 7.0))
    cells = tuple(
        (province, week)
        for week in range(first_week, last_week)
        for province in provinces
    )
    values_by_cell: dict[tuple[str, int], list[float]] = {
        cell: [] for cell in cells
    }
    member_cells: list[list[dict[str, int | str]]] = []
    branch_cells: list[list[list[dict[str, int | str]]]] = []
    rng = random.Random(int(seed))
    trajectory_count = 0
    converged = False
    maximum_mcse = float("inf")
    def record_masks(masks: dict[int, int]) -> None:
        nonlocal trajectory_count, converged, maximum_mcse
        active_cells = _mask_cells(masks, provinces, province_bits)
        member_cells.append([
            {"province_id": province, "week_index": week}
            for province, week in sorted(active_cells)
        ])
        branch_cells.append([[
            {"province_id": province, "week_index": week}
            for province, week in sorted(active_cells)
        ]])
        for province, week in cells:
            values_by_cell[(province, week)].append(
                1.0 if (province, week) in active_cells else 0.0
            )
        trajectory_count += 1
        if trajectory_count >= min_trajectories:
            maximum_mcse = max(
                (
                    binary_mcse_upper_bound(values)
                    for values in values_by_cell.values()
                ),
                default=0.0,
            )
            if maximum_mcse <= tolerance:
                converged = True

    while trajectory_count < max_trajectories and not converged:
        if resident_pool is None:
            particle_index = rng.choices(
                range(len(filter_.particles)), weights=weights, k=1
            )[0]
            branch = filter_.particles[particle_index].state.fork(
                trajectory_count
            )
            branch.advance_to(end_day)
            record_masks(_forecast_week_masks(
                branch,
                start_day=start_day,
                end_day=end_day,
                province_bits=province_bits,
            ))
            continue

        # Generate a deterministic prefix of posterior-parent selections and
        # evaluate it concurrently. Results are consumed in that same prefix
        # order; if the MCSE rule would have stopped in the middle of the
        # batch, later completed jobs are ignored, reproducing the serial
        # estimator exactly while allowing the expensive futures to overlap.
        batch_width = max(1, len(resident_pool.assignment_counts()) * 2)
        remaining = max_trajectories - trajectory_count
        batch_count = min(batch_width, remaining)
        jobs = []
        for offset in range(batch_count):
            sample_id = trajectory_count + offset
            particle_index = rng.choices(
                range(len(filter_.particles)), weights=weights, k=1
            )[0]
            jobs.append((
                int(particle_index),
                float(end_day),
                (
                    "forecast_sample",
                    float(start_day),
                    float(end_day),
                    int(sample_id),
                    province_bits,
                    int(sample_id),
                ),
            ))
        for _, _, _, diagnostics in resident_pool.evaluate_nonmutating(jobs):
            if converged:
                break
            record_masks(dict(diagnostics["week_masks"]))
    if not converged:
        maximum_mcse = max(
            (
                binary_mcse_upper_bound(values)
                for values in values_by_cell.values()
            ),
            default=0.0,
        )
    latent_probability = {
        cell: sum(values) / trajectory_count
        for cell, values in values_by_cell.items()
    }
    field_rows = [
        {
            "province_id": province,
            "week_index": week,
            "probability": latent_probability[(province, week)],
            "mcse": monte_carlo_standard_error(
                values_by_cell[(province, week)]
            ),
        }
        for province, week in cells
    ]
    return {
        "posterior_weights": weights,
        "probability_field": field_rows,
        "mechanistic_event_probability_field": field_rows,
        "target_probability_field": field_rows,
        "member_active_cells": member_cells,
        "forecast_branch_cells": branch_cells,
        "forecast_branches": 1,
        "forecast_trajectories": trajectory_count,
        "forecast_mcse_tolerance": tolerance,
        "maximum_mcse": maximum_mcse,
        "mcse_converged": converged,
        "posterior_particle_summaries": posterior_summaries,
    }


def forecast_weighted_field(
    filter_: SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation],
    *,
    start_day: float = FORECAST_START_DAY,
    end_day: float = FORECAST_END_DAY,
    forecast_branches: int = 3,
    workers: int = 1,
    resident_pool: PersistentParticlePool | None = None,
    resident_particle_metadata: list[dict[str, object]] | None = None,
    mcse_tolerance: float | None = None,
    min_forecast_trajectories: int = 32,
    max_forecast_trajectories: int = 4096,
    forecast_seed: int = 0,
) -> dict[str, object]:
    """Freeze the posterior and return target-compatible event probabilities."""
    if mcse_tolerance is not None:
        return forecast_mcse_controlled_field(
            filter_,
            start_day=start_day,
            end_day=end_day,
            tolerance=mcse_tolerance,
            min_trajectories=min_forecast_trajectories,
            max_trajectories=max_forecast_trajectories,
            seed=forecast_seed,
            resident_pool=resident_pool,
            resident_particle_metadata=resident_particle_metadata,
        )
    if forecast_branches < 1:
        raise ValueError("forecast branches must be at least one")
    if workers < 1:
        raise ValueError("workers must be positive")
    filter_.freeze()
    weights = particle_weights(filter_.particles)
    if resident_pool is None:
        provinces = tuple(sorted({
            _province_for_locality(particle.state.world, locality_id)
            for particle in filter_.particles
            for locality_id in particle.state.world.localities
        }))
    else:
        metadata = (
            resident_particle_metadata
            if resident_particle_metadata is not None
            else [metadata for _, metadata in resident_pool.summarize()]
        )
        provinces = tuple(sorted({
            province
            for particle_metadata in metadata
            for province in particle_metadata["province_ids"]
        }))
    province_bits = {
        province: 1 << index for index, province in enumerate(provinces)
    }
    first_week = int(start_day // 7)
    last_week = int(math.ceil(end_day / 7.0))
    latent_probability: dict[tuple[str, int], float] = {
        (province, week): 0.0
        for week in range(first_week, last_week)
        for province in provinces
    }
    member_cells: list[list[dict[str, int | str]]] = []
    forecast_branch_cells: list[list[list[dict[str, int | str]]]] = []
    posterior_particle_summaries: list[dict[str, object]]
    if global_packed_execution:
        for observation in ordered_observations:
            assimilate_one(observation, None)
            maybe_save_restart(observation, None)
    elif workers == 1:
        jobs = [
            (
                particle.state,
                start_day,
                end_day,
                forecast_branches,
                province_bits,
            )
            for particle in filter_.particles
        ]
        completed = list(map(_forecast_particle_job, jobs))
        posterior_particle_summaries = [
            particle.state.world.summary()
            for particle in filter_.particles
        ]
    else:
        owns_executor = resident_pool is None
        executor = resident_pool
        if executor is None:
            initial_states = [particle.state for particle in filter_.particles]
            executor = PersistentParticlePool(
                initial_states,
                propagate=_resident_particle_job,
                fork_state=_fork_particle_state,
                workers=workers,
                summarize_state=_resident_particle_identity,
            )
        try:
            filter_.particles = [
                Particle(None, particle.log_weight)
                for particle in filter_.particles
            ]
            worker_payloads = [
                diagnostics
                for _, _, diagnostics in executor.propagate(
                    end_day,
                    (
                        "forecast",
                        (start_day, end_day, forecast_branches, province_bits),
                    ),
                )
            ]
        finally:
            if owns_executor:
                executor.close()
        completed = [
            payload["branch_week_masks"] for payload in worker_payloads
        ]
        posterior_particle_summaries = [
            payload["posterior_summary"] for payload in worker_payloads
        ]
    for branch_week_masks, weight in zip(completed, weights):
        combined_masks: dict[int, int] = {}
        for week_masks in branch_week_masks:
            for week, mask in week_masks.items():
                combined_masks[week] = combined_masks.get(week, 0) | mask
        cells = _mask_cells(combined_masks, provinces, province_bits)
        member_cells.append([
            {"province_id": province, "week_index": week}
            for province, week in sorted(cells)
        ])
        forecast_branch_cells.append([
            [
                {"province_id": province, "week_index": week}
                for province, week in sorted(
                    _mask_cells(week_masks, provinces, province_bits)
                )
            ]
            for week_masks in branch_week_masks
        ])
        increment = weight / forecast_branches
        for week_masks in branch_week_masks:
            for week, mask in week_masks.items():
                for province in provinces:
                    if mask & province_bits[province]:
                        cell = (province, week)
                        latent_probability[cell] = (
                            latent_probability.get(cell, 0.0) + increment
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
        "posterior_particle_summaries": posterior_particle_summaries,
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
    likelihood_method: str = "nested",
    execution_backend: str = "optimized",
    forecast_branches: int = 3,
    forecast_mcse_tolerance: float | None = None,
    min_forecast_trajectories: int = 32,
    max_forecast_trajectories: int | None = None,
    forecast_seed: int | None = None,
    rb_likelihood: RaoBlackwellizedActivityLikelihood | None = None,
    guided_propagator: GuidedProposalPropagator | None = None,
    method_gate: ExperimentalMethodGate | None = None,
    workers: int = 1,
    posterior_cache_dir: Path | None = None,
    training_restart_dir: Path | None = None,
    restart_every_weeks: int = 13,
    initial_cache_dir: Path | None = None,
    forecast_cache_dir: Path | None = None,
) -> dict:
    run_started = perf_counter()
    coordinator_cpu_started = process_time()
    training_wall_seconds = 0.0
    training_cpu_seconds = 0.0
    forecast_wall_seconds = 0.0
    forecast_cpu_seconds = 0.0
    resident_worker_cpu_seconds: float | None = None
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
    if execution_backend not in {"optimized", "ensemble"}:
        raise ValueError("execution_backend must be 'optimized' or 'ensemble'")
    if likelihood_method not in {"nested", "rao_blackwellized", "guided"}:
        raise ValueError(
            "likelihood_method must be 'nested', 'rao_blackwellized', or 'guided'"
        )
    if guided_propagator is not None and likelihood_method not in {
        "nested", "guided"
    }:
        raise ValueError(
            "guided_propagator conflicts with the selected likelihood method"
        )
    if guided_propagator is not None:
        likelihood_method = "guided"
    if likelihood_method == "guided" and guided_propagator is None:
        raise ValueError("guided likelihood mode requires guided_propagator")
    effective_min_forecast_trajectories = int(min_forecast_trajectories)
    effective_max_forecast_trajectories = (
        4096 if max_forecast_trajectories is None
        else int(max_forecast_trajectories)
    )
    effective_forecast_seed = 0 if forecast_seed is None else int(forecast_seed)
    if effective_min_forecast_trajectories < 1:
        raise ValueError("min_forecast_trajectories must be positive")
    if effective_max_forecast_trajectories < effective_min_forecast_trajectories:
        raise ValueError(
            "max_forecast_trajectories must be at least min_forecast_trajectories"
        )
    if forecast_mcse_tolerance is not None and float(forecast_mcse_tolerance) <= 0:
        raise ValueError("forecast_mcse_tolerance must be positive")
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
    filter_seed = seed + 17_003
    runner_sha256 = file_sha256(Path(__file__))
    model_hash = model_sha256(ROOT)
    cache_key = {
        "schema_version": POSTERIOR_CACHE_SCHEMA,
        "source_commit": repo["commit_hash"],
        "model_sha256": model_hash,
        "runner_sha256": runner_sha256,
        "case_sha256": file_sha256(CASE),
        "historical_inputs_sha256": file_sha256(INPUTS),
        "training_observation_sha256": training_observation_sha256,
        "seed": int(seed),
        "filter_seed": int(filter_seed),
        "particle_count": int(particles),
        "particle_initial_strengths": list(particle_strengths),
        "particle_prior_families": [
            PRIOR_FAMILY_STRATA[index % len(PRIOR_FAMILY_STRATA)]
            for index in range(particles)
        ],
        "likelihood_branches": int(likelihood_branches),
        "likelihood_method": str(likelihood_method),
        "execution_backend": str(execution_backend),
        "method_gate": (
            None if method_gate is None else asdict(method_gate)
        ),
        "rb_likelihood_epsilon": (
            None if rb_likelihood is None else float(rb_likelihood.epsilon)
        ),
        # A guided proposal is an explicitly user-supplied callable. Its
        # preregistration/validation binding is the stable cache identity;
        # the gate is required for every non-default empirical method.
        "guided_proposal_validation_sha256": (
            None if method_gate is None else method_gate.validation_sha256
        ),
        "horizon": float(horizon),
        "forecast_mcse_tolerance": (
            None if forecast_mcse_tolerance is None
            else float(forecast_mcse_tolerance)
        ),
        "min_forecast_trajectories": int(min_forecast_trajectories),
        "max_forecast_trajectories": effective_max_forecast_trajectories,
        "forecast_seed": effective_forecast_seed,
        "python_cache_tag": sys.implementation.cache_tag,
    }
    posterior_cache_hit = False
    posterior_cache_manifest: Path | None = None
    training_restart_hit = False
    training_restart_manifest: Path | None = None
    training_restart_week: int | None = None
    resident_state_paths: list[str] | None = None
    resume_state_paths: list[str] | None = None
    initial_particle_cache_hits = 0
    initial_particle_cache_attempts = 0
    forecast_cache_hit = False
    forecast_cache_manifest: Path | None = None
    resident_pool: PersistentParticlePool | None = None
    if posterior_cache_dir is not None:
        if workers > 1:
            manifest_path, _, _ = _resident_cache_paths(
                posterior_cache_dir,
                cache_key,
                stage="posterior",
            )
            if manifest_path.exists():
                (
                    filter_,
                    posterior_cache_manifest,
                    resident_state_paths,
                    _,
                ) = _load_resident_particle_cache(
                    manifest_path, cache_key, filter_seed=filter_seed
                )
                posterior_cache_hit = True
            else:
                filter_ = None
        else:
            manifest_path, payload_path = _posterior_cache_paths(
                posterior_cache_dir, cache_key
            )
            if manifest_path.exists() and payload_path.exists():
                filter_, posterior_cache_manifest = _load_posterior_cache(
                    posterior_cache_dir,
                    cache_key,
                    filter_seed=filter_seed,
                )
                posterior_cache_hit = True
            else:
                filter_ = None
    else:
        filter_ = None

    if filter_ is None:
        resume_filter = None
        if training_restart_dir is not None:
            if workers > 1:
                (
                    resume_filter,
                    training_restart_manifest,
                    training_restart_week,
                    resume_state_paths,
                ) = _load_latest_resident_training_restart(
                    training_restart_dir,
                    cache_key,
                    filter_seed=filter_seed,
                )
            else:
                (
                    resume_filter,
                    training_restart_manifest,
                    training_restart_week,
                ) = _load_latest_training_restart(
                    training_restart_dir,
                    cache_key,
                    filter_seed=filter_seed,
                )
            training_restart_hit = resume_filter is not None
        if resume_filter is None:
            initial_particles = []
            base_world = None
            for index in range(particles):
                prior_family = PRIOR_FAMILY_STRATA[
                    index % len(PRIOR_FAMILY_STRATA)
                ]
                initial_key = _initial_particle_cache_key(
                    cache_key,
                    particle_index=index,
                    taliban_strength=particle_strengths[index],
                    prior_family=prior_family,
                )
                cached_particle = (
                    _load_initial_particle_cache(initial_cache_dir, initial_key)
                    if initial_cache_dir is not None else None
                )
                if initial_cache_dir is not None:
                    initial_particle_cache_attempts += 1
                if cached_particle is not None:
                    initial_particle_cache_hits += 1
                    initial_particles.append(cached_particle)
                    continue
                if base_world is None:
                    base_world = generate_pineland(
                        _config(
                            seed,
                            horizon,
                            execution_backend=execution_backend,
                        ),
                        empirical_geography=case,
                    )
                    _precompute_province_lookup(base_world)
                particle = build_initial_particle(
                    seed=seed,
                    particle_index=index,
                    taliban_strength=particle_strengths[index],
                    prior_family=prior_family,
                    horizon=horizon,
                    case=case,
                    inputs=inputs,
                    base_world=base_world,
                    execution_backend=execution_backend,
                )
                if initial_cache_dir is not None:
                    _save_initial_particle_cache(
                        initial_cache_dir, initial_key, particle
                    )
                initial_particles.append(particle)
            del base_world
        else:
            initial_particles = []
        if workers > 1:
            if resume_state_paths is not None:
                resident_pool = PersistentParticlePool(
                    state_paths=resume_state_paths,
                    propagate=_resident_particle_job,
                    fork_state=_fork_particle_state,
                    workers=workers,
                    summarize_state=_resident_particle_identity,
                )
            else:
                resident_pool = PersistentParticlePool(
                    [
                        particle.state
                        for particle in (initial_particles or resume_filter.particles)
                    ],
                    propagate=_resident_particle_job,
                    fork_state=_fork_particle_state,
                    workers=workers,
                    summarize_state=_resident_particle_identity,
                )
        training_started = perf_counter()
        training_cpu_started = process_time()
        filter_ = run_training_filter(
            initial_particles,
            observations,
            filter_seed=filter_seed,
            likelihood_branches=likelihood_branches,
            likelihood_method=likelihood_method,
            rb_likelihood=rb_likelihood,
            guided_propagator=guided_propagator,
            method_gate=method_gate,
            workers=workers,
            resume_filter=resume_filter,
            restart_cache_dir=training_restart_dir,
            restart_cache_key=cache_key if training_restart_dir is not None else None,
            restart_every_weeks=restart_every_weeks,
            resident_pool=resident_pool,
            keep_resident=resident_pool is not None,
        )
        training_wall_seconds = perf_counter() - training_started
        training_cpu_seconds = process_time() - training_cpu_started
        if posterior_cache_dir is not None:
            if resident_pool is not None:
                posterior_cache_manifest = _save_resident_particle_cache(
                    posterior_cache_dir,
                    cache_key,
                    filter_,
                    resident_pool,
                    stage="posterior",
                )
            else:
                posterior_cache_manifest, _ = _save_posterior_cache(
                    posterior_cache_dir, cache_key, filter_
                )
    posterior_boundary = max(observation.end_day for observation in observations)
    if abs(filter_.last_time - posterior_boundary) > 1e-9:
        raise ValueError(
            "posterior cache/training state does not end at the declared boundary"
        )
    if (
        resident_pool is None
        and workers > 1
        and filter_.particles
    ):
        if resident_state_paths is not None:
            resident_pool = PersistentParticlePool(
                state_paths=resident_state_paths,
                propagate=_resident_particle_job,
                fork_state=_fork_particle_state,
                workers=workers,
                summarize_state=_resident_particle_identity,
            )
        elif filter_.particles[0].state is not None:
            resident_pool = PersistentParticlePool(
                [particle.state for particle in filter_.particles],
                propagate=_resident_particle_job,
                fork_state=_fork_particle_state,
                workers=workers,
                summarize_state=_resident_particle_identity,
            )
    resident_metadata = (
        [metadata for _, metadata in resident_pool.summarize()]
        if resident_pool is not None else None
    )
    forecast_key = _forecast_cache_key(
        cache_key,
        filter_,
        start_day=FORECAST_START_DAY,
        end_day=FORECAST_END_DAY,
        forecast_branches=forecast_branches,
        particle_metadata=resident_metadata,
        mcse_tolerance=forecast_mcse_tolerance,
        min_forecast_trajectories=min_forecast_trajectories,
        max_forecast_trajectories=effective_max_forecast_trajectories,
        forecast_seed=effective_forecast_seed,
    )
    forecast_started = perf_counter()
    forecast_cpu_started = process_time()
    try:
        cached_forecast = (
            _load_forecast_cache(forecast_cache_dir, forecast_key)
            if forecast_cache_dir is not None else None
        )
        if cached_forecast is None:
            forecast = forecast_weighted_field(
                filter_,
                forecast_branches=forecast_branches,
                workers=workers,
                resident_pool=resident_pool,
                resident_particle_metadata=resident_metadata,
                mcse_tolerance=forecast_mcse_tolerance,
                min_forecast_trajectories=min_forecast_trajectories,
                max_forecast_trajectories=effective_max_forecast_trajectories,
                forecast_seed=effective_forecast_seed,
            )
            if forecast_cache_dir is not None:
                forecast_cache_manifest, _ = _save_forecast_cache(
                    forecast_cache_dir, forecast_key, forecast
                )
        else:
            forecast, forecast_cache_manifest = cached_forecast
            forecast_cache_hit = True
    finally:
        forecast_wall_seconds = perf_counter() - forecast_started
        forecast_cpu_seconds = process_time() - forecast_cpu_started
        if resident_pool is not None:
            resident_worker_cpu_seconds = resident_pool.cpu_seconds()
            resident_pool.close()
            resident_pool = None
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
        "model_sha256": model_hash,
        "tracked_diff_sha256": repo["tracked_diff_sha256"],
        "runner_sha256": runner_sha256,
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
        "likelihood_method": likelihood_method,
        "execution_backend": execution_backend,
        "experimental_method_gate": (
            None if method_gate is None else asdict(method_gate)
        ),
        "assimilation_probability_estimator": (
            "Jeffreys-regularized nested Monte-Carlo probability of the "
            "target-compatible event surface"
            if likelihood_method == "nested" else
            "Rao-Blackwellized conditional probability from integrated "
            "organized-action opportunity hazards"
            if likelihood_method == "rao_blackwellized" else
            "guided-SMC importance-corrected target-compatible event likelihood"
        ),
        "competitor_information_contract": COMPETITOR_INFORMATION_CONTRACT,
        "likelihood_branches": likelihood_branches,
        "forecast_branches": forecast_branches,
        "forecast_trajectories": forecast.get("forecast_trajectories"),
        "forecast_mcse_tolerance": forecast.get("forecast_mcse_tolerance"),
        "forecast_maximum_mcse": forecast.get("maximum_mcse"),
        "forecast_mcse_converged": forecast.get("mcse_converged"),
        "forecast_estimator": (
            "MCSE-controlled posterior-predictive trajectory sampling"
            if forecast_mcse_tolerance is not None else
            "fixed-branch posterior-predictive trajectory sampling"
        ),
        "method_diagnostics": getattr(filter_, "method_diagnostics", {}),
        "parallel_workers": workers,
        "parallel_backend": "processes" if workers > 1 else "sequential",
        "posterior_cache": {
            "enabled": posterior_cache_dir is not None,
            "hit": posterior_cache_hit,
            "cache_key_sha256": _posterior_cache_digest(cache_key),
            "manifest": (
                str(posterior_cache_manifest)
                if posterior_cache_manifest is not None else None
            ),
            "canonical_scientific_artifact": False,
        },
        "training_restart_cache": {
            "enabled": training_restart_dir is not None,
            "resumed": training_restart_hit,
            "resumed_completed_week_index": training_restart_week,
            "manifest": (
                str(training_restart_manifest)
                if training_restart_manifest is not None else None
            ),
            "restart_every_weeks": restart_every_weeks,
            "canonical_scientific_artifact": False,
        },
        "initial_particle_cache": {
            "enabled": initial_cache_dir is not None,
            "hits": initial_particle_cache_hits,
            "attempts": initial_particle_cache_attempts,
            "misses": max(
                0,
                initial_particle_cache_attempts
                - initial_particle_cache_hits,
            ),
            "canonical_scientific_artifact": False,
        },
        "forecast_cache": {
            "enabled": forecast_cache_dir is not None,
            "hit": forecast_cache_hit,
            "cache_key_sha256": _posterior_cache_digest(forecast_key),
            "manifest": (
                str(forecast_cache_manifest)
                if forecast_cache_manifest is not None else None
            ),
            "canonical_scientific_artifact": False,
        },
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
        "posterior_particle_summaries": forecast[
            "posterior_particle_summaries"
        ],
        "performance": {
            "wall_seconds_before_artifact_write": perf_counter() - run_started,
            "coordinator_cpu_seconds_before_artifact_write": (
                process_time() - coordinator_cpu_started
            ),
            "training_wall_seconds": training_wall_seconds,
            "training_coordinator_cpu_seconds": training_cpu_seconds,
            "forecast_wall_seconds": forecast_wall_seconds,
            "forecast_coordinator_cpu_seconds": forecast_cpu_seconds,
            "resident_worker_cpu_seconds": resident_worker_cpu_seconds,
            "resident_worker_count": workers if workers > 1 else 0,
            "full_state_snapshot_used": False,
            "posterior_cache_hit": posterior_cache_hit,
            "forecast_cache_hit": forecast_cache_hit,
            "canonical_scientific_artifact": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--strength", type=float, choices=DEFAULT_STRENGTHS)
    parser.add_argument("--particles", type=int, default=DEFAULT_PARTICLE_COUNT)
    parser.add_argument("--likelihood-branches", type=int, default=3)
    parser.add_argument(
        "--likelihood-method",
        choices=["nested", "rao_blackwellized", "guided"],
        default="nested",
        help=(
            "experimental synthetic-validated likelihood method; the "
            "default nested method is the empirical contract"
        ),
    )
    parser.add_argument(
        "--execution-backend",
        choices=["optimized", "ensemble"],
        default="optimized",
        help="numeric execution representation for particle propagation",
    )
    parser.add_argument("--forecast-branches", type=int, default=3)
    parser.add_argument(
        "--forecast-mcse-tolerance",
        type=float,
        help="optional binary-field MCSE stopping tolerance",
    )
    parser.add_argument("--min-forecast-trajectories", type=int, default=32)
    parser.add_argument("--max-forecast-trajectories", type=int)
    parser.add_argument("--forecast-seed", type=int)
    parser.add_argument("--horizon", type=float, default=FORECAST_END_DAY)
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, os.cpu_count() or 1),
    )
    parser.add_argument(
        "--posterior-cache-dir",
        type=Path,
        help=(
            "optional content-addressed local cache for the frozen training "
            "posterior; skips repeated 2004 assimilation when provenance matches"
        ),
    )
    parser.add_argument(
        "--training-restart-dir",
        type=Path,
        help=(
            "optional content-addressed observation-boundary restart cache "
            "for interrupted training assimilation"
        ),
    )
    parser.add_argument(
        "--initial-cache-dir",
        type=Path,
        help=(
            "optional content-addressed trusted-local cache for conditioned "
            "initial simulation particles"
        ),
    )
    parser.add_argument(
        "--forecast-cache-dir",
        type=Path,
        help=(
            "optional content-addressed cache for the frozen-posterior "
            "forecast compute result"
        ),
    )
    parser.add_argument(
        "--restart-every-weeks",
        type=int,
        default=13,
        help="training restart snapshot cadence in completed weeks",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(
        seed=args.seed,
        taliban_strength=args.strength,
        particles=args.particles,
        workers=args.workers,
        likelihood_branches=args.likelihood_branches,
        likelihood_method=args.likelihood_method,
        execution_backend=args.execution_backend,
        forecast_branches=args.forecast_branches,
        forecast_mcse_tolerance=args.forecast_mcse_tolerance,
        min_forecast_trajectories=args.min_forecast_trajectories,
        max_forecast_trajectories=args.max_forecast_trajectories,
        forecast_seed=args.forecast_seed,
        horizon=args.horizon,
        posterior_cache_dir=args.posterior_cache_dir,
        training_restart_dir=args.training_restart_dir,
        restart_every_weeks=args.restart_every_weeks,
        initial_cache_dir=args.initial_cache_dir,
        forecast_cache_dir=args.forecast_cache_dir,
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
