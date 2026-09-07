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
from math import ceil, exp, expm1, isfinite, log, log1p, sqrt
import multiprocessing as mp
import hashlib
import os
import pickle
import random
from time import perf_counter
import traceback
from typing import Callable, Generic, Iterable, Iterator, Mapping, Sequence, TypeVar


StateT = TypeVar("StateT")
ObservationT = TypeVar("ObservationT")
JobT = TypeVar("JobT")
ResultT = TypeVar("ResultT")


def _share_resident_static_route_caches(states: dict[int, object]):
    """Share pure locality-routing memoization across resident simulations."""
    worlds = [
        getattr(state, "world", None)
        for state in states.values()
        if getattr(state, "world", None) is not None
    ]
    if not worlds:
        return None
    template = worlds[0]
    caches = (
        template.locality_path_cache,
        template.locality_travel_time_cache,
        template.locality_route_metrics_cache,
    )
    for world in worlds[1:]:
        world.locality_path_cache = caches[0]
        world.locality_travel_time_cache = caches[1]
        world.locality_route_metrics_cache = caches[2]
    return caches


def _attach_resident_static_route_caches(state, caches) -> None:
    if caches is None:
        return
    world = getattr(state, "world", None)
    if world is None:
        return
    world.locality_path_cache = caches[0]
    world.locality_travel_time_cache = caches[1]
    world.locality_route_metrics_cache = caches[2]


def _resident_particle_worker(
    worker_index,
    command_queue,
    result_queue,
    peer_command_queues,
    initial_states,
    initial_state_paths,
    propagate,
    fork_state,
    summarize_state,
) -> None:
    """Run particle states in one resident process.

    The worker protocol deliberately returns only scores and compact
    diagnostics during propagation.  Mutable states stay resident and are
    forked locally after the coordinator sends parent indices.
    """
    if initial_states is not None:
        states = dict(initial_states)
    else:
        states = {}
        try:
            for slot, path in initial_state_paths:
                with open(path, "rb") as handle:
                    states[int(slot)] = pickle.load(handle)
        except BaseException:
            result_queue.put(("error", traceback.format_exc()))
            return
    shared_route_caches = _share_resident_static_route_caches(states)
    pending_imports: dict[int, dict[int, StateT]] = {}
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
            if command == "evaluate_nonmutating":
                # Execute an arbitrary set of slot-local jobs without
                # replacing the resident parent states.  The supplied
                # propagation callback is responsible for treating these
                # payloads as non-mutating (forecast sampling forks a temporary
                # child).  Job IDs allow the same posterior parent to be
                # sampled repeatedly in one batch while preserving caller
                # order.
                results = []
                for job_id, slot, time, observation in payload:
                    slot = int(slot)
                    if slot not in states:
                        raise KeyError(
                            f"worker {worker_index} does not own slot {slot}"
                        )
                    _, score, diagnostics = propagate(
                        states[slot], float(time), observation
                    )
                    results.append(
                        (int(job_id), slot, score, diagnostics)
                    )
                result_queue.put(("evaluate_nonmutating", results))
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
            if command == "import_resampled":
                generation, child, state = payload
                _attach_resident_static_route_caches(
                    state, shared_route_caches
                )
                pending_imports.setdefault(int(generation), {})[
                    int(child)
                ] = state
                continue
            if command == "import_parent_bundle":
                generation, parent_state, children = payload
                _attach_resident_static_route_caches(
                    parent_state, shared_route_caches
                )
                generation = int(generation)
                target = pending_imports.setdefault(generation, {})
                for child in children:
                    child = int(child)
                    target[child] = fork_state(parent_state, child)
                continue
            if command == "resample_balanced":
                generation, child_plan, expected_state_count = payload
                generation = int(generation)
                old_states = states
                next_states: dict[int, StateT] = {}
                exported = 0
                export_bundles = 0
                remote_groups: dict[
                    tuple[int, int], list[int]
                ] = {}
                for child, parent, target_worker in child_plan:
                    child = int(child)
                    parent = int(parent)
                    target_worker = int(target_worker)
                    if target_worker == worker_index:
                        next_states[child] = fork_state(
                            old_states[parent], child
                        )
                    else:
                        remote_groups.setdefault(
                            (parent, target_worker), []
                        ).append(child)
                        exported += 1
                for (parent, target_worker), children in sorted(
                    remote_groups.items()
                ):
                    peer_command_queues[target_worker].put((
                        "import_parent_bundle",
                        (generation, old_states[parent], tuple(children)),
                    ))
                    export_bundles += 1
                imported = pending_imports.pop(generation, {})
                next_states.update(imported)
                while len(next_states) < int(expected_state_count):
                    import_command, import_payload = command_queue.get()
                    if import_command == "import_parent_bundle":
                        import_generation, parent_state, children = (
                            import_payload
                        )
                        import_generation = int(import_generation)
                        _attach_resident_static_route_caches(
                            parent_state, shared_route_caches
                        )
                        target = (
                            next_states
                            if import_generation == generation
                            else pending_imports.setdefault(
                                import_generation, {}
                            )
                        )
                        for child in children:
                            child = int(child)
                            target[child] = fork_state(
                                parent_state, child
                            )
                        continue
                    if import_command != "import_resampled":
                        raise RuntimeError(
                            "balanced resampling received a non-import "
                            f"command before its barrier: {import_command!r}"
                        )
                    import_generation, child, state = import_payload
                    import_generation = int(import_generation)
                    _attach_resident_static_route_caches(
                        state, shared_route_caches
                    )
                    if import_generation != generation:
                        pending_imports.setdefault(
                            import_generation, {}
                        )[int(child)] = state
                        continue
                    next_states[int(child)] = state
                states = next_states
                result_queue.put((
                    "resample_balanced",
                    {
                        "state_count": len(states),
                        "exported": exported,
                        "export_bundles": export_bundles,
                        "imported": len(states)
                        - sum(
                            1
                            for _, _, target_worker in child_plan
                            if int(target_worker) == worker_index
                        ),
                    },
                ))
                continue
            if command == "snapshot":
                result_queue.put(("snapshot", list(states.items())))
                continue
            if command == "summarize":
                if summarize_state is None:
                    raise RuntimeError(
                        "resident particle pool has no state summarizer"
                    )
                result_queue.put((
                    "summarize",
                    [
                        (slot, summarize_state(states[slot]))
                        for slot in sorted(states)
                    ],
                ))
                continue
            if command == "persist":
                cache_dir, prefix = payload
                cache_dir = os.fspath(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
                persisted = []
                for slot in sorted(states):
                    path = os.path.join(
                        cache_dir, f"{prefix}-particle-{int(slot):06d}.pkl"
                    )
                    temporary = f"{path}.tmp-{os.getpid()}"
                    with open(temporary, "wb") as handle:
                        pickle.dump(
                            states[slot], handle, protocol=pickle.HIGHEST_PROTOCOL
                        )
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(temporary, path)
                    with open(path, "rb") as handle:
                        payload_bytes = handle.read()
                    metadata = (
                        summarize_state(states[slot])
                        if summarize_state is not None else {}
                    )
                    persisted.append({
                        "slot": int(slot),
                        "path": path,
                        "bytes": len(payload_bytes),
                        "payload_sha256": hashlib.sha256(
                            payload_bytes
                        ).hexdigest(),
                        "metadata": metadata,
                    })
                result_queue.put(("persist", persisted))
                continue
            if command == "metrics":
                process_times = os.times()
                result_queue.put((
                    "metrics",
                    {
                        "cpu_seconds": float(
                            process_times.user + process_times.system
                        ),
                    },
                ))
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
        states: Sequence[StateT] | None = None,
        *,
        propagate: Callable[[StateT, float, ObservationT], tuple[StateT, float, ResultT]],
        fork_state: Callable[[StateT, int], StateT],
        workers: int,
        state_paths: Sequence[str] | None = None,
        summarize_state: Callable[[StateT], object] | None = None,
    ) -> None:
        if (states is None) == (state_paths is None):
            raise ValueError(
                "provide exactly one of states or state_paths"
            )
        if states is not None and not states:
            raise ValueError("a persistent particle pool needs at least one state")
        if state_paths is not None and not state_paths:
            raise ValueError("a persistent particle pool needs at least one state path")
        if workers < 1:
            raise ValueError("workers must be positive")
        self._closed = False
        self._context = mp.get_context("spawn")
        self._propagate = propagate
        self._fork_state = fork_state
        self._summarize_state = summarize_state
        self._workers = []
        self._assignment: dict[int, int] = {}
        self._resample_generation = 0
        particle_count = len(states) if states is not None else len(state_paths)
        worker_count = min(int(workers), particle_count)
        partitions = [[] for _ in range(worker_count)]
        path_partitions = [[] for _ in range(worker_count)]
        for slot in range(particle_count):
            worker_index = slot % worker_count
            if states is not None:
                partitions[worker_index].append((slot, states[slot]))
            else:
                path_partitions[worker_index].append(
                    (slot, os.fspath(state_paths[slot]))
                )
            self._assignment[slot] = worker_index
        command_queues = [
            self._context.Queue() for _ in range(worker_count)
        ]
        result_queues = [
            self._context.Queue() for _ in range(worker_count)
        ]
        for worker_index, initial_states in enumerate(partitions):
            command_queue = command_queues[worker_index]
            result_queue = result_queues[worker_index]
            process = self._context.Process(
                target=_resident_particle_worker,
                args=(
                    worker_index,
                    command_queue,
                    result_queue,
                    command_queues,
                    initial_states if states is not None else None,
                    path_partitions[worker_index] if state_paths is not None else None,
                    self._propagate,
                    self._fork_state,
                    self._summarize_state,
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

    def evaluate_nonmutating(
        self,
        jobs: Sequence[tuple[int, float, ObservationT]],
    ) -> list[tuple[int, int, float, ResultT]]:
        """Evaluate selected resident slots without replacing parent state.

        Each input is ``(slot, time, payload)``. Multiple jobs may reference
        the same slot. The propagation callback must implement the payload as
        a temporary/non-mutating evaluation; this method deliberately does not
        attempt to infer or copy state itself.
        """
        by_worker: list[list[tuple[int, int, float, ObservationT]]] = [
            [] for _ in self._workers
        ]
        for job_id, (raw_slot, raw_time, payload) in enumerate(jobs):
            slot = int(raw_slot)
            worker_index = self._assignment.get(slot)
            if worker_index is None:
                raise ValueError(
                    f"resident evaluation referenced unknown slot {slot}"
                )
            by_worker[worker_index].append(
                (job_id, slot, float(raw_time), payload)
            )
        for worker_index, (_, command_queue, _) in enumerate(self._workers):
            command_queue.put((
                "evaluate_nonmutating", by_worker[worker_index]
            ))
        results: list[tuple[int, int, float, ResultT]] = []
        for _, _, result_queue in self._workers:
            results.extend(self._receive(
                result_queue, "evaluate_nonmutating"
            ))
        results.sort(key=lambda item: item[0])
        if [item[0] for item in results] != list(range(len(jobs))):
            raise RuntimeError(
                "resident non-mutating evaluation returned an incomplete job set"
            )
        return results

    def assignment_counts(self) -> list[int]:
        """Return the current number of resident particle slots per worker."""
        counts = Counter(self._assignment.values())
        return [
            int(counts.get(worker_index, 0))
            for worker_index in range(len(self._workers))
        ]

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

    def resample_balanced(
        self, parent_indices: Sequence[int]
    ) -> dict[str, int | list[int]]:
        """Resample exactly while restoring an even resident-worker layout.

        Children are forked on the worker holding their selected parent so
        ancestry and RNG namespace semantics remain unchanged. Only the
        minimum number of children required to fill worker capacity deficits
        are migrated, directly from source worker to destination worker.
        """
        if len(parent_indices) != len(self._assignment):
            raise ValueError(
                "resampling must return one parent per particle"
            )
        worker_count = len(self._workers)
        particle_count = len(parent_indices)
        capacities = [
            particle_count // worker_count
            + (1 if worker_index < particle_count % worker_count else 0)
            for worker_index in range(worker_count)
        ]
        remaining = list(capacities)
        origins = []
        for child, raw_parent in enumerate(parent_indices):
            parent = int(raw_parent)
            source_worker = self._assignment.get(parent)
            if source_worker is None:
                raise ValueError(
                    f"resampling referenced unknown parent {parent}"
                )
            origins.append((child, parent, source_worker))

        target_by_child: dict[int, int] = {}
        # Keep as many children as possible with the worker that owns the
        # selected parent. This minimizes serialized state migration.
        for child, _, source_worker in origins:
            if remaining[source_worker] > 0:
                target_by_child[child] = source_worker
                remaining[source_worker] -= 1
        target_cursor = 0
        for child, _, _ in origins:
            if child in target_by_child:
                continue
            while (
                target_cursor < worker_count
                and remaining[target_cursor] == 0
            ):
                target_cursor += 1
            if target_cursor >= worker_count:
                raise RuntimeError(
                    "balanced resampling capacity accounting failed"
                )
            target_by_child[child] = target_cursor
            remaining[target_cursor] -= 1

        by_source: list[list[tuple[int, int, int]]] = [
            [] for _ in self._workers
        ]
        new_assignment: dict[int, int] = {}
        migrated = 0
        for child, parent, source_worker in origins:
            target_worker = target_by_child[child]
            by_source[source_worker].append(
                (child, parent, target_worker)
            )
            new_assignment[child] = target_worker
            if target_worker != source_worker:
                migrated += 1

        self._resample_generation += 1
        generation = self._resample_generation
        for worker_index, (_, command_queue, _) in enumerate(
            self._workers
        ):
            command_queue.put((
                "resample_balanced",
                (
                    generation,
                    by_source[worker_index],
                    capacities[worker_index],
                ),
            ))
        exported = 0
        export_bundles = 0
        imported = 0
        for _, _, result_queue in self._workers:
            payload = self._receive(
                result_queue, "resample_balanced"
            )
            exported += int(payload["exported"])
            export_bundles += int(payload["export_bundles"])
            imported += int(payload["imported"])
        self._assignment = new_assignment
        return {
            "migrated_particles": migrated,
            "exported_particles": exported,
            "export_bundles": export_bundles,
            "imported_particles": imported,
            "assignment_counts": self.assignment_counts(),
        }

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

    def summarize(self) -> list[tuple[int, object]]:
        """Return compact per-slot metadata without exporting particle state."""
        self._send_to_all("summarize", None)
        summaries: dict[int, object] = {}
        for _, _, result_queue in self._workers:
            summaries.update(dict(self._receive(result_queue, "summarize")))
        expected_slots = list(range(len(self._assignment)))
        if sorted(summaries) != expected_slots:
            raise RuntimeError(
                "resident particle worker returned incomplete summaries"
            )
        return [(slot, summaries[slot]) for slot in expected_slots]

    def persist_states(
        self, cache_dir: str, prefix: str
    ) -> list[dict[str, object]]:
        """Persist resident states worker-side and return metadata only.

        The state payload never crosses back through the coordinator. Files are
        committed with flush/fsync followed by atomic rename, so a manifest can
        safely reference only complete payloads.
        """
        self._send_to_all("persist", (os.fspath(cache_dir), str(prefix)))
        persisted = []
        for _, _, result_queue in self._workers:
            persisted.extend(self._receive(result_queue, "persist"))
        persisted.sort(key=lambda row: int(row["slot"]))
        expected_slots = list(range(len(self._assignment)))
        if [int(row["slot"]) for row in persisted] != expected_slots:
            raise RuntimeError(
                "resident particle worker persisted an incomplete particle set"
            )
        return persisted

    def cpu_seconds(self) -> float:
        """Return aggregate user+system CPU time for resident workers."""
        self._send_to_all("metrics", None)
        return sum(
            float(self._receive(result_queue, "metrics")["cpu_seconds"])
            for _, _, result_queue in self._workers
        )

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


def probability_at_least_one(probabilities: Iterable[float]) -> float:
    """Return ``1 - prod(1-p_i)`` with stable survival arithmetic."""
    log_survival = 0.0
    for raw_probability in probabilities:
        probability = min(1.0, max(0.0, float(raw_probability)))
        if probability >= 1.0:
            return 1.0
        if probability > 0.0:
            log_survival += log1p(-probability)
    return min(1.0, max(0.0, -expm1(log_survival)))


def hazard_to_probability(hazard_per_day: float, interval_days: float = 1.0) -> float:
    """Convert a continuous-time hazard into an interval probability."""
    interval_days = float(interval_days)
    if interval_days < 0:
        raise ValueError("interval_days cannot be negative")
    hazard = max(0.0, float(hazard_per_day))
    return min(1.0, max(0.0, -expm1(-hazard * interval_days)))


def probability_to_hazard(probability: float, interval_days: float = 1.0) -> float:
    """Convert an interval probability into its equivalent constant hazard."""
    interval_days = float(interval_days)
    if interval_days <= 0:
        raise ValueError("interval_days must be positive")
    probability = min(1.0, max(0.0, float(probability)))
    if probability >= 1.0:
        return float("inf")
    return -log1p(-probability) / interval_days


def aggregate_hazard(hazards: Iterable[float]) -> float:
    """Add independent continuous hazards without converting through p-space."""
    return sum(max(0.0, float(hazard)) for hazard in hazards)


def aggregate_hazard_probability(
    hazards: Iterable[float],
    interval_days: float = 1.0,
) -> float:
    """Return the probability of at least one event from independent hazards."""
    return hazard_to_probability(aggregate_hazard(hazards), interval_days)


@dataclass(frozen=True, slots=True)
class RaoBlackwellizedActivityLikelihood:
    """Likelihood for binary activity observations from opportunity hazards.

    A trajectory supplies one or more opportunity hazards for each locality or
    evaluation unit.  Their uncertainty is integrated analytically with
    ``P(Y=1)=1-exp(-sum(lambda_i) * dt)`` rather than estimated by a fixed
    number of fully simulated descendants.
    """

    epsilon: float = 1.0e-12

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.epsilon) < 0.5:
            raise ValueError("epsilon must be in [0, .5)")

    def probability_from_hazards(
        self,
        hazards: Iterable[float],
        *,
        interval_days: float = 1.0,
    ) -> float:
        return aggregate_hazard_probability(hazards, interval_days)

    def probability_from_opportunities(
        self,
        probabilities: Iterable[float],
    ) -> float:
        return probability_at_least_one(probabilities)

    def log_likelihood(
        self,
        observed: bool | int | float,
        hazards: Iterable[float],
        *,
        interval_days: float = 1.0,
        inputs_are_probabilities: bool = False,
    ) -> float:
        probability = (
            self.probability_from_opportunities(hazards)
            if inputs_are_probabilities
            else self.probability_from_hazards(
                hazards, interval_days=interval_days
            )
        )
        epsilon = float(self.epsilon)
        if epsilon:
            probability = min(1.0 - epsilon, max(epsilon, probability))
        y = bool(observed)
        return log(probability if y else 1.0 - probability)

    def score(
        self,
        observed_by_unit: Mapping[str, bool | int | float],
        hazards_by_unit: Mapping[str, Iterable[float]],
        *,
        interval_days: float = 1.0,
        inputs_are_probabilities: bool = False,
    ) -> float:
        """Sum unit log likelihoods in deterministic key order."""
        return sum(
            self.log_likelihood(
                observed_by_unit[unit],
                hazards_by_unit.get(unit, ()),
                interval_days=interval_days,
                inputs_are_probabilities=inputs_are_probabilities,
            )
            for unit in sorted(observed_by_unit)
        )

    __call__ = log_likelihood


# Shorter spelling retained for callers that use the statistical term rather
# than the activity-specific name.
RaoBlackwellizedHazardLikelihood = RaoBlackwellizedActivityLikelihood


def guided_importance_log_weight(
    log_transition_density: float,
    log_likelihood: float,
    log_proposal_density: float,
    *,
    log_prior_weight: float = 0.0,
) -> float:
    """Return the log importance correction for a guided SMC proposal."""
    return (
        float(log_prior_weight)
        + float(log_transition_density)
        + float(log_likelihood)
        - float(log_proposal_density)
    )


def guided_log_weights(
    log_prior_weights: Sequence[float],
    log_transition_densities: Sequence[float],
    log_likelihoods: Sequence[float],
    log_proposal_densities: Sequence[float],
) -> list[float]:
    """Vector form of :func:`guided_importance_log_weight`."""
    lengths = {
        len(log_prior_weights),
        len(log_transition_densities),
        len(log_likelihoods),
        len(log_proposal_densities),
    }
    if len(lengths) != 1:
        raise ValueError("guided SMC arrays must have equal lengths")
    return [
        guided_importance_log_weight(
            transition, likelihood, proposal, log_prior_weight=prior
        )
        for prior, transition, likelihood, proposal in zip(
            log_prior_weights,
            log_transition_densities,
            log_likelihoods,
            log_proposal_densities,
        )
    ]


@dataclass(frozen=True, slots=True)
class GuidedProposalPropagator(Generic[StateT, ObservationT]):
    """Turn an observation-guided proposal into an SMC weight increment.

    ``propose`` may use the current observation to construct a new state.  The
    two density callbacks then supply the transition density ``p`` and the
    proposal density ``q`` for that realized state.  The returned score is
    exactly ``log p + log likelihood - log q``; prior particle mass remains in
    the filter and is not double-counted here.
    """

    propose: Callable[[StateT, float, ObservationT], StateT]
    log_transition_density: Callable[
        [StateT, StateT, float, ObservationT], float
    ]
    log_proposal_density: Callable[
        [StateT, StateT, float, ObservationT], float
    ]
    log_likelihood: Callable[[StateT, ObservationT], float]

    def __call__(
        self,
        state: StateT,
        time: float,
        observation: ObservationT,
    ) -> tuple[StateT, float]:
        proposed = self.propose(state, float(time), observation)
        return proposed, guided_importance_log_weight(
            self.log_transition_density(
                state, proposed, float(time), observation
            ),
            self.log_likelihood(proposed, observation),
            self.log_proposal_density(
                state, proposed, float(time), observation
            ),
        )


# A descriptive alias for call sites that model proposals as transition
# kernels rather than propagators.
GuidedSMCPropagator = GuidedProposalPropagator


def monte_carlo_standard_error(
    values: Sequence[float],
    *,
    weights: Sequence[float] | None = None,
) -> float:
    """Estimate Monte Carlo standard error for unweighted or weighted draws."""
    if not values:
        raise ValueError("MCSE needs at least one draw")
    numeric = [float(value) for value in values]
    if any(not isfinite(value) for value in numeric):
        raise ValueError("MCSE values must be finite")
    if weights is None:
        count = len(numeric)
        if count < 2:
            return 0.0
        mean = sum(numeric) / count
        variance = sum((value - mean) ** 2 for value in numeric) / (count - 1)
        return sqrt(max(0.0, variance) / count)
    if len(weights) != len(numeric):
        raise ValueError("MCSE weights must match values")
    nonnegative = [max(0.0, float(weight)) for weight in weights]
    total = sum(nonnegative)
    if total <= 0:
        raise ValueError("MCSE weights must have positive mass")
    normalized = [weight / total for weight in nonnegative]
    mean = sum(weight * value for weight, value in zip(normalized, numeric))
    sum_squared_weights = sum(weight * weight for weight in normalized)
    if sum_squared_weights >= 1.0:
        return 0.0
    # The finite-sample weighted variance correction and effective sample size
    # are both needed: treating a concentrated posterior as n raw draws is
    # overconfident.
    variance = sum(
        weight * (value - mean) ** 2
        for weight, value in zip(normalized, numeric)
    ) / (1.0 - sum_squared_weights)
    effective_n = 1.0 / sum_squared_weights
    return sqrt(max(0.0, variance) / effective_n)


def binary_mcse(
    probability_or_values: float | Sequence[float],
    sample_count: int | None = None,
) -> float:
    """Return Bernoulli MCSE from ``p,n`` or a binary draw sequence."""
    if isinstance(probability_or_values, (int, float)):
        probability = min(1.0, max(0.0, float(probability_or_values)))
        if sample_count is None:
            raise ValueError("sample_count is required when probability is scalar")
        count = int(sample_count)
        if count < 1:
            raise ValueError("sample_count must be positive")
        return sqrt(probability * (1.0 - probability) / count)
    values = [float(value) for value in probability_or_values]
    if not values or any(value not in (0.0, 1.0) for value in values):
        raise ValueError("binary draws must be a nonempty 0/1 sequence")
    probability = sum(values) / len(values)
    return sqrt(probability * (1.0 - probability) / len(values))


def required_trajectories_for_mcse(
    probability: float | None,
    tolerance: float,
    *,
    z_value: float = 1.0,
) -> int:
    """Conservative draw count for a binary posterior probability MCSE target."""
    tolerance = float(tolerance)
    z_value = float(z_value)
    if tolerance <= 0.0 or z_value <= 0.0:
        raise ValueError("tolerance and z_value must be positive")
    variance_bound = 0.25 if probability is None else min(
        0.25,
        max(0.0, float(probability)) * (1.0 - min(1.0, max(0.0, float(probability)))),
    )
    return max(1, int(ceil(variance_bound * z_value * z_value / (tolerance * tolerance))))


@dataclass(frozen=True, slots=True)
class AdaptiveMonteCarloResult:
    estimate: float
    mcse: float
    sample_count: int
    batches: int
    converged: bool
    values: tuple[float, ...]


def adaptive_monte_carlo(
    sample: Callable[[], float],
    *,
    tolerance: float,
    min_samples: int = 32,
    max_samples: int = 4096,
    batch_size: int = 32,
) -> AdaptiveMonteCarloResult:
    """Draw until empirical MCSE is below ``tolerance`` or budget is exhausted."""
    tolerance = float(tolerance)
    min_samples = int(min_samples)
    max_samples = int(max_samples)
    batch_size = int(batch_size)
    if tolerance <= 0.0:
        raise ValueError("tolerance must be positive")
    if min_samples < 1 or max_samples < min_samples or batch_size < 1:
        raise ValueError("invalid adaptive Monte Carlo sample budget")
    values: list[float] = []
    batches = 0
    converged = False
    while len(values) < max_samples:
        draw_count = min(batch_size, max_samples - len(values))
        for _ in range(draw_count):
            value = float(sample())
            if not isfinite(value):
                raise ValueError("adaptive Monte Carlo sampler returned a non-finite value")
            values.append(value)
        batches += 1
        if len(values) >= min_samples:
            mcse = monte_carlo_standard_error(values)
            if mcse <= tolerance:
                converged = True
                break
    estimate = sum(values) / len(values)
    return AdaptiveMonteCarloResult(
        estimate=estimate,
        mcse=monte_carlo_standard_error(values),
        sample_count=len(values),
        batches=batches,
        converged=converged,
        values=tuple(values),
    )


# Public aliases make the intent explicit at call sites in study runners.
at_least_one_event_probability = probability_at_least_one
adaptive_posterior_predictive = adaptive_monte_carlo
