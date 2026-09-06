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
