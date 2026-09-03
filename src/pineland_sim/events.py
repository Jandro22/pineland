from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from itertools import count
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
        self._sequence = count()
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
        event = ScheduledEvent(time, priority, next(self._sequence), event_type, payload or {}, causal_parent_ids)
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
