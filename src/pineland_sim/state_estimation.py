"""Generic sequential state-estimation utilities for partially observed worlds.

This module deliberately contains no empirical case data and no model-fitting
logic.  Structural parameters belong to the transition model; particle weights
represent uncertainty about latent *state*.  A study layer must supply its own
predeclared observation likelihood before historical assimilation is allowed.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from concurrent.futures import Executor
from dataclasses import dataclass
from math import exp, isfinite, log
import multiprocessing as mp
import random
from time import perf_counter
import traceback
from typing import Callable, Generic, Iterable, Iterator, Sequence, TypeVar


StateT = TypeVar("StateT")
ObservationT = TypeVar("ObservationT")
JobT = TypeVar("JobT")
ResultT = TypeVar("ResultT")


def _resident_particle_worker(
    command_queue,
    result_queue,
    initial_states,
    propagate,
    fork_state,
) -> None:
    """Run particle states in one resident process.

    The worker protocol deliberately returns only scores and compact
    diagnostics during propagation.  Mutable states stay resident and are
    forked locally after the coordinator sends parent indices.
    """
    states = dict(initial_states)
    try:
        while True:
            command, payload = command_queue.get()
            if command == "shutdown":
                result_queue.put(("shutdown", None))
                return
            if command == "propagate":
                time, observation = payload
                results = []
                for slot in sorted(states):
                    new_state, score, diagnostics = propagate(
                        states[slot], time, observation
                    )
                    states[slot] = new_state
                    results.append((slot, score, diagnostics))
                result_queue.put(("propagate", results))
                continue
            if command == "propagate_profiled":
                time, observation = payload
                started = perf_counter()
                results = []
                for slot in sorted(states):
                    new_state, score, diagnostics = propagate(
                        states[slot], time, observation
                    )
                    states[slot] = new_state
                    results.append((slot, score, diagnostics))
                result_queue.put((
                    "propagate_profiled",
                    {
                        "results": results,
                        "wall_seconds": perf_counter() - started,
                        "state_count": len(states),
                    },
                ))
                continue
            if command == "resample":
                # The mapping is child slot -> locally resident parent slot.
                # All children are assigned to the worker that owns their
                # parent, so no state migration is needed.
                parent_by_child = payload
                states = {
                    child: fork_state(states[parent], child)
                    for child, parent in parent_by_child.items()
                }
                result_queue.put(("resample", None))
                continue
            if command == "snapshot":
                result_queue.put(("snapshot", list(states.items())))
                continue
            raise ValueError(f"unknown resident particle command: {command!r}")
    except BaseException:
        result_queue.put(("error", traceback.format_exc()))


class PersistentParticlePool(Generic[StateT, ObservationT, ResultT]):
    """Keep particle states resident while a filter advances.

    Each worker owns a changing subset of globally indexed particles.  On a
    resampling step, every child is assigned to its selected parent's worker;
    the worker performs the normal state fork locally.  Consequently the
    coordinator exchanges only observations, scores, ancestry indices, and
    compact diagnostics—not a full simulation object graph every week.

    ``propagate`` must return ``(new_state, score, diagnostics)`` and both
    callbacks must be importable/pickleable top-level callables when the spawn
    multiprocessing context is used (the Windows default).
    """

    def __init__(
        self,
        states: Sequence[StateT],
        *,
        propagate: Callable[[StateT, float, ObservationT], tuple[StateT, float, ResultT]],
        fork_state: Callable[[StateT, int], StateT],
        workers: int,
    ) -> None:
        if not states:
            raise ValueError("a persistent particle pool needs at least one state")
        if workers < 1:
            raise ValueError("workers must be positive")
        self._closed = False
        self._context = mp.get_context("spawn")
        self._propagate = propagate
        self._fork_state = fork_state
        self._workers = []
        self._assignment: dict[int, int] = {}
        worker_count = min(int(workers), len(states))
        partitions = [[] for _ in range(worker_count)]
        for slot, state in enumerate(states):
            worker_index = slot % worker_count
            partitions[worker_index].append((slot, state))
            self._assignment[slot] = worker_index
        for initial_states in partitions:
            command_queue = self._context.Queue()
            result_queue = self._context.Queue()
            process = self._context.Process(
                target=_resident_particle_worker,
                args=(
                    command_queue,
                    result_queue,
                    initial_states,
                    self._propagate,
                    self._fork_state,
                ),
            )
            process.start()
            self._workers.append((process, command_queue, result_queue))

    def _send_to_all(self, command: str, payload) -> None:
        for _, command_queue, _ in self._workers:
            command_queue.put((command, payload))

    @staticmethod
    def _receive(result_queue, expected: str):
        command, payload = result_queue.get()
        if command == "error":
            raise RuntimeError(f"resident particle worker failed:\n{payload}")
        if command != expected:
            raise RuntimeError(
                f"resident particle worker returned {command!r}, expected {expected!r}"
            )
        return payload

    def propagate(
        self,
        time: float,
        observation: ObservationT,
    ) -> list[tuple[int, float, ResultT]]:
        """Advance every resident particle and return ordered compact results."""
        self._send_to_all("propagate", (float(time), observation))
        results = []
        for _, _, result_queue in self._workers:
            results.extend(self._receive(result_queue, "propagate"))
        results.sort(key=lambda item: item[0])
        expected_slots = list(range(len(self._assignment)))
        if [item[0] for item in results] != expected_slots:
            raise RuntimeError("resident particle worker returned an incomplete particle set")
        return results

    def propagate_profiled(
        self,
        time: float,
        observation: ObservationT,
    ) -> tuple[
        list[tuple[int, float, ResultT]],
        list[dict[str, float | int]],
    ]:
        """Advance particles and return worker-local compute diagnostics."""
        self._send_to_all(
            "propagate_profiled", (float(time), observation)
        )
        results = []
        worker_rows = []
        for worker_index, (_, _, result_queue) in enumerate(self._workers):
            payload = self._receive(
                result_queue, "propagate_profiled"
            )
            results.extend(payload["results"])
            worker_rows.append({
                "worker_index": worker_index,
                "wall_seconds": float(payload["wall_seconds"]),
                "state_count": int(payload["state_count"]),
            })
        results.sort(key=lambda item: item[0])
        expected_slots = list(range(len(self._assignment)))
        if [item[0] for item in results] != expected_slots:
            raise RuntimeError(
                "resident particle worker returned an incomplete particle set"
            )
        return results, worker_rows

    def resample(self, parent_indices: Sequence[int]) -> None:
        """Fork resampled children on the workers holding their parents."""
        if len(parent_indices) != len(self._assignment):
            raise ValueError("resampling must return one parent per particle")
        by_worker: list[dict[int, int]] = [
            {} for _ in self._workers
        ]
        new_assignment: dict[int, int] = {}
        for child, parent in enumerate(parent_indices):
            parent = int(parent)
            worker_index = self._assignment.get(parent)
            if worker_index is None:
                raise ValueError(f"resampling referenced unknown parent {parent}")
            by_worker[worker_index][child] = parent
            new_assignment[child] = worker_index
        for worker_index, (_, command_queue, _) in enumerate(self._workers):
            command_queue.put(("resample", by_worker[worker_index]))
        for _, _, result_queue in self._workers:
            self._receive(result_queue, "resample")
        self._assignment = new_assignment

    def snapshot(self) -> list[StateT]:
        """Return the current ordered states, paying the IPC cost once."""
        self._send_to_all("snapshot", None)
        states: dict[int, StateT] = {}
        for _, _, result_queue in self._workers:
            states.update(dict(self._receive(result_queue, "snapshot")))
        expected_slots = list(range(len(self._assignment)))
        if sorted(states) != expected_slots:
            raise RuntimeError("resident particle worker returned an incomplete snapshot")
        return [states[slot] for slot in expected_slots]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for _, command_queue, _ in self._workers:
            command_queue.put(("shutdown", None))
        for process, _, result_queue in self._workers:
            try:
                self._receive(result_queue, "shutdown")
            finally:
                process.join(timeout=10)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
        self._workers.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()


def bounded_process_map(
    executor: Executor,
    function: Callable[[JobT], ResultT],
    jobs: Iterable[JobT],
    *,
    max_in_flight: int,
) -> Iterator[ResultT]:
    """Yield ordered executor results without eagerly queuing every job."""
    if max_in_flight < 1:
        raise ValueError("max_in_flight must be positive")
    iterator = iter(jobs)
    pending = {}
    next_index = 0
    while len(pending) < max_in_flight:
        try:
            job = next(iterator)
        except StopIteration:
            break
        pending[next_index] = executor.submit(function, job)
        next_index += 1
    result_index = 0
    while pending:
        result = pending.pop(result_index).result()
        yield result
        result_index += 1
        try:
            job = next(iterator)
        except StopIteration:
            continue
        pending[next_index] = executor.submit(function, job)
        next_index += 1


def chunked(items: Sequence[JobT], chunk_size: int) -> Iterator[list[JobT]]:
    """Yield deterministic contiguous batches for process-isolated work."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    for start in range(0, len(items), chunk_size):
        yield list(items[start:start + chunk_size])


@dataclass(slots=True)
class Particle(Generic[StateT]):
    state: StateT
    log_weight: float = 0.0


class PosteriorSupportExhausted(RuntimeError):
    """Raised when an observation assigns zero support to every particle."""


def normalize_log_weights(
    log_weights: Sequence[float],
    *,
    strict: bool = False,
) -> list[float]:
    """Normalize arbitrary log weights without numerical underflow."""
    if not log_weights:
        raise ValueError("cannot normalize an empty particle set")
    finite = [value for value in log_weights if isfinite(value)]
    if not finite:
        if strict:
            raise PosteriorSupportExhausted(
                "posterior support exhausted: all particle log weights are non-finite"
            )
        return [1.0 / len(log_weights)] * len(log_weights)
    maximum = max(finite)
    scaled = [exp(value - maximum) if isfinite(value) else 0.0
              for value in log_weights]
    total = sum(scaled)
    if total <= 0:
        if strict:
            raise PosteriorSupportExhausted(
                "posterior support exhausted: normalized particle mass is zero"
            )
        return [1.0 / len(log_weights)] * len(log_weights)
    return [value / total for value in scaled]


def particle_weights(
    particles: Sequence[Particle[StateT]],
    *,
    strict: bool = False,
) -> list[float]:
    return normalize_log_weights(
        [particle.log_weight for particle in particles],
        strict=strict,
    )


def effective_sample_size(weights: Sequence[float]) -> float:
    """Return 1/sum(w^2) after defensively normalizing the supplied weights."""
    if not weights:
        raise ValueError("effective sample size needs at least one weight")
    total = sum(max(0.0, float(weight)) for weight in weights)
    if total <= 0:
        return float(len(weights))
    normalized = [max(0.0, float(weight)) / total for weight in weights]
    return 1.0 / sum(weight * weight for weight in normalized)


def measurement_update(
    particles: Sequence[Particle[StateT]],
    observation: ObservationT,
    log_likelihood: Callable[[StateT, ObservationT], float],
    *,
    strict: bool = False,
) -> dict[str, float]:
    """Condition particle state weights on one observation.

    The supplied likelihood may inspect latent state but must not mutate it.
    Parameters are never changed by this function.
    """
    if not particles:
        raise ValueError("measurement update needs at least one particle")
    prior = particle_weights(particles, strict=strict)
    for particle, prior_weight in zip(particles, prior):
        likelihood = float(log_likelihood(particle.state, observation))
        particle.log_weight = (
            -float("inf") if prior_weight <= 0 or not isfinite(likelihood)
            else log(prior_weight) + likelihood
        )
    posterior = particle_weights(particles, strict=strict)
    for particle, weight in zip(particles, posterior):
        particle.log_weight = log(weight) if weight > 0 else -float("inf")
    return {
        "prior_ess": effective_sample_size(prior),
        "posterior_ess": effective_sample_size(posterior),
        "maximum_posterior_weight": max(posterior),
    }


def systematic_resample_indices(weights: Sequence[float], rng: random.Random) -> list[int]:
    """Systematic resampling with one random draw and deterministic traversal."""
    if not weights:
        raise ValueError("resampling needs at least one particle")
    total = sum(max(0.0, float(weight)) for weight in weights)
    normalized = (
        [max(0.0, float(weight)) / total for weight in weights]
        if total > 0 else
        [1.0 / len(weights)] * len(weights)
    )
    count = len(normalized)
    start = rng.random() / count
    positions = [start + index / count for index in range(count)]
    indices: list[int] = []
    cumulative = normalized[0]
    source_index = 0
    for position in positions:
        while position > cumulative and source_index < count - 1:
            source_index += 1
            cumulative += normalized[source_index]
        indices.append(source_index)
    return indices


def resample_particles(
    particles: Sequence[Particle[StateT]],
    rng: random.Random,
    *,
    clone_state: Callable[[StateT], StateT] = deepcopy,
    fork_state: Callable[[StateT, int], StateT] | None = None,
) -> tuple[list[Particle[StateT]], dict[str, float | int | list[int]]]:
    """Resample latent states and reset to an equal-weight posterior ensemble.

    ``fork_state`` is an optional particle-aware clone hook.  It receives the
    selected parent state and the child position, allowing live simulator
    particles to carry a distinct future stochastic lineage after a duplicate
    parent is selected.  The original one-argument ``clone_state`` API remains
    the default for ordinary immutable or deepcopyable states.
    """
    weights = particle_weights(particles)
    indices = systematic_resample_indices(weights, rng)
    resampled = [
        Particle(
            (fork_state(particles[index].state, child_index)
             if fork_state is not None
             else clone_state(particles[index].state)),
            0.0,
        )
        for child_index, index in enumerate(indices)
    ]
    return resampled, {
        "ess_before": effective_sample_size(weights),
        "unique_parent_particles": len(set(indices)),
        "parent_indices": indices,
    }


def resample_if_degenerate(
    particles: Sequence[Particle[StateT]],
    rng: random.Random,
    *,
    ess_fraction: float = 0.5,
    clone_state: Callable[[StateT], StateT] = deepcopy,
    fork_state: Callable[[StateT, int], StateT] | None = None,
) -> tuple[list[Particle[StateT]], dict[str, float | int | bool | list[int]]]:
    """Resample only when ESS falls below a predeclared particle fraction."""
    if not 0 < ess_fraction <= 1:
        raise ValueError("ess_fraction must be in (0, 1]")
    weights = particle_weights(particles)
    ess = effective_sample_size(weights)
    threshold = ess_fraction * len(particles)
    if ess >= threshold:
        return list(particles), {
            "resampled": False,
            "ess_before": ess,
            "threshold": threshold,
            "parent_indices": list(range(len(particles))),
        }
    resampled, diagnostics = resample_particles(
        particles,
        rng,
        clone_state=clone_state,
        fork_state=fork_state,
    )
    return resampled, {
        "resampled": True,
        "threshold": threshold,
        **diagnostics,
    }


@dataclass(frozen=True, slots=True)
class AssimilationObservation(Generic[ObservationT]):
    """An observation presented to the state filter.

    The split label is deliberately part of the value passed to the filter.
    A filter configured for training-only assimilation rejects every other
    label before it advances a particle, making accidental holdout updates a
    hard error rather than a convention in a caller.
    """

    time: float
    value: ObservationT
    split: str = "training"
    observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class FilterUpdateDiagnostics:
    time: float
    observation_id: str | None
    split: str
    prior_ess: float
    posterior_ess: float
    maximum_posterior_weight: float
    resampled: bool
    unique_parent_particles: int
    distinct_root_ancestors: int
    lineage_entropy: float
    maximum_ancestry_concentration: float
    resampling_events: int


class SequentialParticleFilter(Generic[StateT, ObservationT]):
    """Sequentially estimate latent state without changing transition rules.

    The transition callback advances one state to an observation boundary.
    The likelihood callback is read-only and is the only place where an
    observation enters the particle weights.  Structural parameters therefore
    remain in each state unchanged; resampling only changes the posterior
    multiplicity of latent states.
    """

    def __init__(
        self,
        particles: Sequence[Particle[StateT]],
        *,
        transition: Callable[[StateT, float], None] | None = None,
        log_likelihood: Callable[[StateT, ObservationT], float] | None = None,
        propagate_and_score: Callable[
            [StateT, float, ObservationT], tuple[StateT, float]
        ] | None = None,
        rng: random.Random,
        ess_fraction: float = 0.5,
        allowed_split: str = "training",
        clone_state: Callable[[StateT], StateT] = deepcopy,
        fork_state: Callable[[StateT, int], StateT] | None = None,
    ) -> None:
        if not particles:
            raise ValueError("a particle filter needs at least one particle")
        if not 0 < ess_fraction <= 1:
            raise ValueError("ess_fraction must be in (0, 1]")
        self.particles = list(particles)
        self.transition = transition
        self.log_likelihood = log_likelihood
        self.propagate_and_score = propagate_and_score
        if propagate_and_score is None and (transition is None or log_likelihood is None):
            raise ValueError(
                "particle filter needs transition/log_likelihood or "
                "propagate_and_score"
            )
        if propagate_and_score is not None and transition is not None:
            raise ValueError(
                "provide either transition/log_likelihood or propagate_and_score, "
                "not both transition paths"
            )
        self.rng = rng
        self.ess_fraction = ess_fraction
        self.allowed_split = allowed_split
        self.clone_state = clone_state
        self.fork_state = fork_state
        self.last_time = float("-inf")
        self.frozen = False
        self.history: list[FilterUpdateDiagnostics] = []
        self._root_ancestors = list(range(len(self.particles)))
        self._resampling_events = 0

    def ancestry_diagnostics(self) -> dict[str, float | int]:
        """Return lineage support diagnostics for the current particle set."""
        counts = Counter(self._root_ancestors)
        particle_count = max(1, len(self._root_ancestors))
        probabilities = [
            count / particle_count for count in counts.values()
        ]
        entropy = -sum(
            probability * log(probability)
            for probability in probabilities
            if probability > 0
        )
        return {
            "distinct_root_ancestors": len(counts),
            "lineage_entropy": entropy,
            "maximum_ancestry_concentration": max(probabilities, default=1.0),
            "resampling_events": self._resampling_events,
        }

    def freeze(self) -> None:
        """Close the historical-assimilation phase at the forecast boundary.

        A training-only split protects the filter from accidentally consuming
        a row from the wrong data partition.  Freezing adds the second guard
        required by a prospective workflow: once forward propagation starts,
        no later call can silently turn the posterior into a holdout-tuned
        state estimate.
        """
        self.frozen = True

    def _validate_observation(
        self,
        observation: AssimilationObservation[ObservationT],
    ) -> None:
        if self.frozen:
            raise RuntimeError(
                "particle filter is frozen at the forecast boundary and cannot "
                "assimilate additional observations"
            )
        if observation.split != self.allowed_split:
            raise ValueError(
                "particle filter refuses observations outside its declared "
                f"split {self.allowed_split!r}: got {observation.split!r}"
            )
        if observation.time < self.last_time - 1e-12:
            raise ValueError("observations must arrive in nondecreasing time order")

    def _commit_propagated_update(
        self,
        observation: AssimilationObservation[ObservationT],
        propagated: Sequence[tuple[StateT, float]],
    ) -> FilterUpdateDiagnostics:
        if len(propagated) != len(self.particles):
            raise ValueError(
                "precomputed propagation must return exactly one result per particle"
            )
        prior = particle_weights(self.particles, strict=True)
        for particle, prior_weight, (new_state, likelihood) in zip(
            self.particles, prior, propagated
        ):
            particle.state = new_state
            likelihood = float(likelihood)
            particle.log_weight = (
                -float("inf")
                if prior_weight <= 0 or not isfinite(likelihood)
                else log(prior_weight) + likelihood
            )
        posterior = particle_weights(self.particles, strict=True)
        for particle, weight in zip(self.particles, posterior):
            particle.log_weight = log(weight) if weight > 0 else -float("inf")
        update = {
            "prior_ess": effective_sample_size(prior),
            "posterior_ess": effective_sample_size(posterior),
            "maximum_posterior_weight": max(posterior),
        }
        previous_roots = list(self._root_ancestors)
        resampled, resampling = resample_if_degenerate(
            self.particles,
            self.rng,
            ess_fraction=self.ess_fraction,
            clone_state=self.clone_state,
            fork_state=self.fork_state,
        )
        self.particles = resampled
        parent_indices = list(
            resampling.get("parent_indices", range(len(self.particles)))
        )
        if bool(resampling["resampled"]):
            self._root_ancestors = [
                previous_roots[index] for index in parent_indices
            ]
            self._resampling_events += 1
        ancestry = self.ancestry_diagnostics()
        diagnostics = FilterUpdateDiagnostics(
            time=float(observation.time),
            observation_id=observation.observation_id,
            split=observation.split,
            prior_ess=float(update["prior_ess"]),
            posterior_ess=float(update["posterior_ess"]),
            maximum_posterior_weight=float(update["maximum_posterior_weight"]),
            resampled=bool(resampling["resampled"]),
            unique_parent_particles=int(
                resampling.get("unique_parent_particles", len(self.particles))
            ),
            distinct_root_ancestors=int(ancestry["distinct_root_ancestors"]),
            lineage_entropy=float(ancestry["lineage_entropy"]),
            maximum_ancestry_concentration=float(
                ancestry["maximum_ancestry_concentration"]
            ),
            resampling_events=int(ancestry["resampling_events"]),
        )
        self.history.append(diagnostics)
        self.last_time = float(observation.time)
        return diagnostics

    def assimilate_precomputed(
        self,
        observation: AssimilationObservation[ObservationT],
        propagated: Sequence[tuple[StateT, float]],
    ) -> FilterUpdateDiagnostics:
        """Commit externally propagated particles through the normal SMC update.

        This is an execution hook for process-isolated propagation. It does not
        bypass split/freeze guards, weighting, ESS, resampling, or ancestry
        accounting.
        """
        self._validate_observation(observation)
        return self._commit_propagated_update(observation, propagated)

    def assimilate_scores(
        self,
        observation: AssimilationObservation[ObservationT],
        likelihoods: Sequence[float],
    ) -> tuple[FilterUpdateDiagnostics, list[int]]:
        """Commit scores when a separate execution engine owns particle state.

        This keeps weighting, ESS thresholds, systematic resampling, and
        ancestry accounting identical to ``assimilate_precomputed`` while a
        resident worker pool keeps the actual mutable states out of the
        coordinator process.  The returned parent indices are the only state
        operation the external executor needs to perform.
        """
        self._validate_observation(observation)
        if len(likelihoods) != len(self.particles):
            raise ValueError("score count must equal the particle count")
        prior = particle_weights(self.particles, strict=True)
        for particle, prior_weight, likelihood in zip(
            self.particles, prior, likelihoods
        ):
            likelihood = float(likelihood)
            particle.log_weight = (
                -float("inf")
                if prior_weight <= 0 or not isfinite(likelihood)
                else log(prior_weight) + likelihood
            )
        posterior = particle_weights(self.particles, strict=True)
        for particle, weight in zip(self.particles, posterior):
            particle.log_weight = log(weight) if weight > 0 else -float("inf")
        update = {
            "prior_ess": effective_sample_size(prior),
            "posterior_ess": effective_sample_size(posterior),
            "maximum_posterior_weight": max(posterior),
        }
        previous_roots = list(self._root_ancestors)
        threshold = self.ess_fraction * len(self.particles)
        if update["posterior_ess"] >= threshold:
            parent_indices = list(range(len(self.particles)))
            resampled = False
        else:
            parent_indices = systematic_resample_indices(posterior, self.rng)
            resampled = True
        if resampled:
            self.particles = [
                Particle(self.particles[index].state, 0.0)
                for index in parent_indices
            ]
            self._root_ancestors = [
                previous_roots[index] for index in parent_indices
            ]
            self._resampling_events += 1
        ancestry = self.ancestry_diagnostics()
        diagnostics = FilterUpdateDiagnostics(
            time=float(observation.time),
            observation_id=observation.observation_id,
            split=observation.split,
            prior_ess=float(update["prior_ess"]),
            posterior_ess=float(update["posterior_ess"]),
            maximum_posterior_weight=float(update["maximum_posterior_weight"]),
            resampled=resampled,
            unique_parent_particles=len(set(parent_indices)),
            distinct_root_ancestors=int(ancestry["distinct_root_ancestors"]),
            lineage_entropy=float(ancestry["lineage_entropy"]),
            maximum_ancestry_concentration=float(
                ancestry["maximum_ancestry_concentration"]
            ),
            resampling_events=int(ancestry["resampling_events"]),
        )
        self.history.append(diagnostics)
        self.last_time = float(observation.time)
        return diagnostics, parent_indices

    def assimilate(
        self,
        observation: AssimilationObservation[ObservationT],
    ) -> FilterUpdateDiagnostics:
        """Advance to and assimilate one predeclared observation boundary."""
        self._validate_observation(observation)

        if self.propagate_and_score is None:
            assert self.transition is not None
            assert self.log_likelihood is not None
            for particle in self.particles:
                self.transition(particle.state, observation.time)
            update = measurement_update(
                self.particles,
                observation.value,
                self.log_likelihood,
                strict=True,
            )
        else:
            propagated = [
                self.propagate_and_score(
                    particle.state,
                    observation.time,
                    observation.value,
                )
                for particle in self.particles
            ]
            return self._commit_propagated_update(observation, propagated)
        previous_roots = list(self._root_ancestors)
        resampled, resampling = resample_if_degenerate(
            self.particles,
            self.rng,
            ess_fraction=self.ess_fraction,
            clone_state=self.clone_state,
            fork_state=self.fork_state,
        )
        self.particles = resampled
        parent_indices = list(resampling.get("parent_indices", range(len(self.particles))))
        if bool(resampling["resampled"]):
            self._root_ancestors = [
                previous_roots[index] for index in parent_indices
            ]
            self._resampling_events += 1
        ancestry = self.ancestry_diagnostics()
        diagnostics = FilterUpdateDiagnostics(
            time=float(observation.time),
            observation_id=observation.observation_id,
            split=observation.split,
            prior_ess=float(update["prior_ess"]),
            posterior_ess=float(update["posterior_ess"]),
            maximum_posterior_weight=float(update["maximum_posterior_weight"]),
            resampled=bool(resampling["resampled"]),
            unique_parent_particles=int(
                resampling.get("unique_parent_particles", len(self.particles))
            ),
            distinct_root_ancestors=int(ancestry["distinct_root_ancestors"]),
            lineage_entropy=float(ancestry["lineage_entropy"]),
            maximum_ancestry_concentration=float(
                ancestry["maximum_ancestry_concentration"]
            ),
            resampling_events=int(ancestry["resampling_events"]),
        )
        self.history.append(diagnostics)
        self.last_time = float(observation.time)
        return diagnostics
