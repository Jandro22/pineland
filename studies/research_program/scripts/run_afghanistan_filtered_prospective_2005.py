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


def _forecast_cache_key(
    cache_key: dict[str, object],
    filter_: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ],
    *,
    start_day: float,
    end_day: float,
    forecast_branches: int,
) -> dict[str, object]:
    """Bind forecast reuse to the exact frozen posterior and forecast contract."""
    return {
        "schema_version": FORECAST_CACHE_SCHEMA,
        "posterior_cache_key_sha256": _posterior_cache_digest(cache_key),
        "posterior_last_time": float(filter_.last_time),
        "posterior_weights": particle_weights(filter_.particles),
        "posterior_lineages": [
            particle.state.lineage_id for particle in filter_.particles
        ],
        "posterior_decision_state_sha256": [
            decision_state_sha256(particle.state.world)
            for particle in filter_.particles
        ],
        "forecast_start_day": float(start_day),
        "forecast_end_day": float(end_day),
        "forecast_branches": int(forecast_branches),
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
    resume_filter: SequentialParticleFilter[
        SimulationParticle, ProvinceWeekObservation
    ] | None = None,
    restart_cache_dir: Path | None = None,
    restart_cache_key: dict[str, object] | None = None,
    restart_every_weeks: int = 13,
    collect_worker_diagnostics: bool = False,
    balance_resampling: bool = True,
) -> SequentialParticleFilter[SimulationParticle, ProvinceWeekObservation]:
    if workers < 1:
        raise ValueError("workers must be positive")
    if restart_cache_dir is not None and restart_cache_key is None:
        raise ValueError("restart cache key is required when restart caching is enabled")
    if restart_every_weeks < 1:
        raise ValueError("restart_every_weeks must be positive")
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
            assignment_before = (
                executor.assignment_counts()
                if collect_worker_diagnostics else None
            )
            if collect_worker_diagnostics:
                completed, worker_rows = executor.propagate_profiled(
                    observation.end_day,
                    (observation, likelihood_branches, filter_seed),
                )
            else:
                completed = executor.propagate(
                    observation.end_day,
                    (observation, likelihood_branches, filter_seed),
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
        initial_states = [particle.state for particle in filter_.particles]
        with PersistentParticlePool(
            initial_states,
            propagate=_nested_persistent_job,
            fork_state=_fork_particle_state,
            workers=workers,
        ) as executor:
            # The coordinator retains only weights/ancestry metadata while
            # workers own the mutable simulation objects.
            filter_.particles = [
                Particle(None, particle.log_weight)
                for particle in filter_.particles
            ]
            del initial_states
            particles = []
            for observation in ordered_observations:
                assimilate_one(observation, executor)
                maybe_save_restart(observation, executor)
            _reattach_particle_states(filter_, executor.snapshot())
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
) -> list[dict[int, int]]:
    state, start_day, end_day, forecast_branches, province_bits = job
    branch_week_masks = []
    for branch_index in range(forecast_branches):
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
) -> tuple[SimulationParticle, float, list[dict[int, int]]]:
    """Run forecast branches in a resident worker and return only cells."""
    start_day, end_day, forecast_branches, province_bits = payload
    return state, 0.0, _forecast_particle_job(
        (state, start_day, end_day, forecast_branches, province_bits)
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
    provinces = tuple(sorted({
        _province_for_locality(particle.state.world, locality_id)
        for particle in filter_.particles
        for locality_id in particle.state.world.localities
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
    if workers == 1:
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
    else:
        initial_states = [particle.state for particle in filter_.particles]
        with PersistentParticlePool(
            initial_states,
            propagate=_forecast_persistent_job,
            fork_state=_fork_particle_state,
            workers=workers,
        ) as executor:
            filter_.particles = [
                Particle(None, particle.log_weight)
                for particle in filter_.particles
            ]
            del initial_states
            completed = [
                diagnostics
                for _, _, diagnostics in executor.propagate(
                    end_day,
                    (start_day, end_day, forecast_branches, province_bits),
                )
            ]
            forecast_states = executor.snapshot()
        filter_.particles = [
            Particle(
                state,
                math.log(weight) if weight > 0 else -float("inf"),
            )
            for state, weight in zip(forecast_states, weights)
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
    posterior_cache_dir: Path | None = None,
    training_restart_dir: Path | None = None,
    restart_every_weeks: int = 13,
    initial_cache_dir: Path | None = None,
    forecast_cache_dir: Path | None = None,
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
        "horizon": float(horizon),
        "python_cache_tag": sys.implementation.cache_tag,
    }
    posterior_cache_hit = False
    posterior_cache_manifest: Path | None = None
    training_restart_hit = False
    training_restart_manifest: Path | None = None
    training_restart_week: int | None = None
    initial_particle_cache_hits = 0
    initial_particle_cache_attempts = 0
    forecast_cache_hit = False
    forecast_cache_manifest: Path | None = None
    if posterior_cache_dir is not None:
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
                        _config(seed, horizon), empirical_geography=case
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
                )
                if initial_cache_dir is not None:
                    _save_initial_particle_cache(
                        initial_cache_dir, initial_key, particle
                    )
                initial_particles.append(particle)
            del base_world
        else:
            initial_particles = []
        filter_ = run_training_filter(
            initial_particles,
            observations,
            filter_seed=filter_seed,
            likelihood_branches=likelihood_branches,
            workers=workers,
            resume_filter=resume_filter,
            restart_cache_dir=training_restart_dir,
            restart_cache_key=cache_key if training_restart_dir is not None else None,
            restart_every_weeks=restart_every_weeks,
        )
        if posterior_cache_dir is not None:
            posterior_cache_manifest, _ = _save_posterior_cache(
                posterior_cache_dir, cache_key, filter_
            )
    posterior_boundary = max(observation.end_day for observation in observations)
    if abs(filter_.last_time - posterior_boundary) > 1e-9:
        raise ValueError(
            "posterior cache/training state does not end at the declared boundary"
        )
    forecast_key = _forecast_cache_key(
        cache_key,
        filter_,
        start_day=FORECAST_START_DAY,
        end_day=FORECAST_END_DAY,
        forecast_branches=forecast_branches,
    )
    cached_forecast = (
        _load_forecast_cache(forecast_cache_dir, forecast_key)
        if forecast_cache_dir is not None else None
    )
    if cached_forecast is None:
        forecast = forecast_weighted_field(
            filter_,
            forecast_branches=forecast_branches,
            workers=workers,
        )
        if forecast_cache_dir is not None:
            forecast_cache_manifest, _ = _save_forecast_cache(
                forecast_cache_dir, forecast_key, forecast
            )
    else:
        forecast, forecast_cache_manifest = cached_forecast
        forecast_cache_hit = True
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
        "assimilation_probability_estimator": (
            "Jeffreys-regularized nested Monte-Carlo probability of the "
            "target-compatible event surface"
        ),
        "competitor_information_contract": COMPETITOR_INFORMATION_CONTRACT,
        "likelihood_branches": likelihood_branches,
        "forecast_branches": forecast_branches,
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
