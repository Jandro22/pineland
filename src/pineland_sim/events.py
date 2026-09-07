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
        return event

    def pop_next(self) -> ScheduledEvent:
        if not self._queue:
            raise IndexError("event queue is empty")
        return heapq.heappop(self._queue)

    def peek_time(self) -> float | None:
        return self._queue[0].time if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)

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
        return event

    def pop_next(self) -> ScheduledEvent:
        if not self._size:
            raise IndexError("event queue is empty")
        time = self._times[0]
        bucket = self._buckets[time]
        event = heapq.heappop(bucket)
        self._size -= 1
        if not bucket:
            del self._buckets[time]
            heapq.heappop(self._times)
        return event

    def peek_time(self) -> float | None:
        return self._times[0] if self._times else None

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
        return clone
