from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import copy
from typing import Any


@dataclass(order=True, slots=True)
class ScheduledEvent:
    time: float
    priority: int
    sequence: int
    event_type: str = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
    causal_parent_ids: tuple[str, ...] = field(default_factory=tuple, compare=False)


class EventScheduler:
    def __init__(self, allow_negative: bool = False) -> None:
        self._queue: list[ScheduledEvent] = []
        # Keep the next sequence value as an ordinary integer rather than an
        # itertools.count object.  A scheduler is part of a simulation
        # particle's latent state and must therefore be safely deep-copyable
        # at a filtering/resampling boundary.
        self._next_sequence = 0
        self.allow_negative = allow_negative
        self._cancelled_sequences: set[int] = set()
        self._replacement_sequences: dict[str, int] = {}
        self._metrics_enabled = False
        self._metrics: dict[str, int] = {}

    def enable_metrics(self, enabled: bool = True) -> None:
        self._metrics_enabled = bool(enabled)
        if enabled:
            self._metrics = {
                "scheduled": 0,
                "popped": 0,
                "cancelled": 0,
                "replacements": 0,
                "batches": 0,
                "max_pending": len(self),
            }

    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def schedule(
        self,
        time: float,
        event_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        causal_parent_ids: tuple[str, ...] = (),
    ) -> ScheduledEvent:
        if time < 0 and not self.allow_negative:
            raise ValueError("event time cannot be negative")
        event = ScheduledEvent(
            time,
            priority,
            self._next_sequence,
            event_type,
            payload or {},
            causal_parent_ids,
        )
        self._next_sequence += 1
        heapq.heappush(self._queue, event)
        if self._metrics_enabled:
            self._metrics["scheduled"] += 1
            self._metrics["max_pending"] = max(
                self._metrics["max_pending"], len(self)
            )
        return event

    def cancel(self, event_or_sequence: ScheduledEvent | int) -> bool:
        """Cancel one still-pending event without perturbing other ordering."""
        sequence = (
            event_or_sequence.sequence
            if isinstance(event_or_sequence, ScheduledEvent)
            else int(event_or_sequence)
        )
        if sequence in self._cancelled_sequences:
            return False
        if not any(event.sequence == sequence for event in self._queue):
            return False
        self._cancelled_sequences.add(sequence)
        if self._metrics_enabled:
            self._metrics["cancelled"] += 1
        return True

    def schedule_replacing(
        self,
        key: str,
        time: float,
        event_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        causal_parent_ids: tuple[str, ...] = (),
    ) -> ScheduledEvent:
        """Generation-token scheduling: only the newest keyed event survives."""
        prior = self._replacement_sequences.get(str(key))
        if prior is not None:
            self.cancel(prior)
        event = self.schedule(
            time,
            event_type,
            payload,
            priority,
            causal_parent_ids,
        )
        self._replacement_sequences[str(key)] = event.sequence
        if self._metrics_enabled:
            self._metrics["replacements"] += 1
        return event

    def _discard_cancelled_head(self) -> None:
        while (
            self._queue
            and self._queue[0].sequence in self._cancelled_sequences
        ):
            event = heapq.heappop(self._queue)
            self._cancelled_sequences.discard(event.sequence)

    def pop_next(self) -> ScheduledEvent:
        self._discard_cancelled_head()
        if not self._queue:
            raise IndexError("event queue is empty")
        event = heapq.heappop(self._queue)
        if self._metrics_enabled:
            self._metrics["popped"] += 1
        return event

    def peek_time(self) -> float | None:
        self._discard_cancelled_head()
        return self._queue[0].time if self._queue else None

    def pop_time_batch(self) -> list[ScheduledEvent]:
        """Pop the complete next timestamp in exact scalar-pop order."""
        time = self.peek_time()
        if time is None:
            return []
        result = []
        while self.peek_time() == time:
            result.append(self.pop_next())
        if self._metrics_enabled:
            self._metrics["batches"] += 1
        return result

    def pending_events(self) -> tuple[ScheduledEvent, ...]:
        """Canonical live queue view for reproducibility diagnostics."""
        return tuple(sorted(
            event for event in self._queue
            if event.sequence not in self._cancelled_sequences
        ))

    def __len__(self) -> int:
        return len(self._queue) - len(self._cancelled_sequences)

    def __deepcopy__(self, memo: dict[int, Any]) -> "EventScheduler":
        """Copy both pending events and the future sequence lineage.

        Recreating a scheduler from its queue alone would be subtly wrong:
        events already popped from the queue still consume sequence numbers,
        and those numbers are part of deterministic same-time ordering.  The
        explicit counter preserves that execution state for a particle fork.
        """
        existing = memo.get(id(self))
        if existing is not None:
            return existing
        clone = type(self)(allow_negative=self.allow_negative)
        memo[id(self)] = clone
        clone._queue = copy.deepcopy(self._queue, memo)
        clone._next_sequence = self._next_sequence
        clone._cancelled_sequences = set(self._cancelled_sequences)
        clone._replacement_sequences = dict(self._replacement_sequences)
        clone._metrics_enabled = self._metrics_enabled
        clone._metrics = dict(self._metrics)
        return clone


class CalendarEventScheduler:
    """Exact same-time bucket scheduler for recurring event-heavy workloads.

    Events retain the identical ordering key of time, priority, and sequence.
    A heap tracks distinct timestamps and a second heap orders events within
    each timestamp. This is opt-in execution infrastructure; the reference
    heap scheduler remains the default.
    """

    def __init__(self, allow_negative: bool = False) -> None:
        self._times: list[float] = []
        self._buckets: dict[float, list[ScheduledEvent]] = {}
        self._next_sequence = 0
        self.allow_negative = allow_negative
        self._size = 0
        self._cancelled_sequences: set[int] = set()
        self._replacement_sequences: dict[str, int] = {}
        self._metrics_enabled = False
        self._metrics: dict[str, int] = {}

    def enable_metrics(self, enabled: bool = True) -> None:
        self._metrics_enabled = bool(enabled)
        if enabled:
            self._metrics = {
                "scheduled": 0,
                "popped": 0,
                "cancelled": 0,
                "replacements": 0,
                "batches": 0,
                "max_pending": len(self),
            }

    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def schedule(
        self,
        time: float,
        event_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        causal_parent_ids: tuple[str, ...] = (),
    ) -> ScheduledEvent:
        if time < 0 and not self.allow_negative:
            raise ValueError("event time cannot be negative")
        event = ScheduledEvent(
            time,
            priority,
            self._next_sequence,
            event_type,
            payload or {},
            causal_parent_ids,
        )
        self._next_sequence += 1
        bucket = self._buckets.get(time)
        if bucket is None:
            bucket = []
            self._buckets[time] = bucket
            heapq.heappush(self._times, time)
        heapq.heappush(bucket, event)
        self._size += 1
        if self._metrics_enabled:
            self._metrics["scheduled"] += 1
            self._metrics["max_pending"] = max(
                self._metrics["max_pending"], len(self)
            )
        return event

    def cancel(self, event_or_sequence: ScheduledEvent | int) -> bool:
        sequence = (
            event_or_sequence.sequence
            if isinstance(event_or_sequence, ScheduledEvent)
            else int(event_or_sequence)
        )
        if sequence in self._cancelled_sequences:
            return False
        if not any(
            event.sequence == sequence
            for bucket in self._buckets.values()
            for event in bucket
        ):
            return False
        self._cancelled_sequences.add(sequence)
        self._size -= 1
        if self._metrics_enabled:
            self._metrics["cancelled"] += 1
        return True

    def schedule_replacing(
        self,
        key: str,
        time: float,
        event_type: str,
        payload: dict[str, Any] | None = None,
        priority: int = 100,
        causal_parent_ids: tuple[str, ...] = (),
    ) -> ScheduledEvent:
        prior = self._replacement_sequences.get(str(key))
        if prior is not None:
            self.cancel(prior)
        event = self.schedule(
            time,
            event_type,
            payload,
            priority,
            causal_parent_ids,
        )
        self._replacement_sequences[str(key)] = event.sequence
        if self._metrics_enabled:
            self._metrics["replacements"] += 1
        return event

    def _discard_cancelled_head(self) -> None:
        while self._times:
            time = self._times[0]
            bucket = self._buckets[time]
            while (
                bucket
                and bucket[0].sequence in self._cancelled_sequences
            ):
                event = heapq.heappop(bucket)
                self._cancelled_sequences.discard(event.sequence)
            if bucket:
                return
            del self._buckets[time]
            heapq.heappop(self._times)

    def pop_next(self) -> ScheduledEvent:
        self._discard_cancelled_head()
        if not self._size:
            raise IndexError("event queue is empty")
        time = self._times[0]
        bucket = self._buckets[time]
        event = heapq.heappop(bucket)
        self._size -= 1
        if self._metrics_enabled:
            self._metrics["popped"] += 1
        if not bucket:
            del self._buckets[time]
            heapq.heappop(self._times)
        return event

    def peek_time(self) -> float | None:
        self._discard_cancelled_head()
        return self._times[0] if self._times else None

    def pop_time_batch(self) -> list[ScheduledEvent]:
        time = self.peek_time()
        if time is None:
            return []
        result = []
        while self.peek_time() == time:
            result.append(self.pop_next())
        if self._metrics_enabled:
            self._metrics["batches"] += 1
        return result

    def pending_events(self) -> tuple[ScheduledEvent, ...]:
        return tuple(sorted(
            event
            for bucket in self._buckets.values()
            for event in bucket
            if event.sequence not in self._cancelled_sequences
        ))

    def __len__(self) -> int:
        return self._size

    def __deepcopy__(
        self, memo: dict[int, Any]
    ) -> "CalendarEventScheduler":
        existing = memo.get(id(self))
        if existing is not None:
            return existing
        clone = type(self)(allow_negative=self.allow_negative)
        memo[id(self)] = clone
        clone._times = list(self._times)
        clone._buckets = copy.deepcopy(self._buckets, memo)
        clone._next_sequence = self._next_sequence
        clone._size = self._size
        clone._cancelled_sequences = set(self._cancelled_sequences)
        clone._replacement_sequences = dict(self._replacement_sequences)
        clone._metrics_enabled = self._metrics_enabled
        clone._metrics = dict(self._metrics)
        return clone
