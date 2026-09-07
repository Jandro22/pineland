"""Execution-only streaming helpers for large forensic histories."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Generic, Iterable, TypeVar


STREAMABLE_ARCHIVE_FIELDS = frozenset({
    "event_log",
    "contact_funnel_records",
    "causal_ledger",
    "synthetic_records",
    "checkpoints",
    "state_deltas",
    "stock_transactions",
    "organization_eligibility_log",
    "organization_onset_log",
    "civilian_harm_events",
    "resource_flows",
    "engagements",
    "state_based_events",
    "political_transfers",
    "policy_implementations",
    "external_transfers",
    "peace_transitions",
})


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [_jsonable(item) for item in value]
    return value


class JsonlArchiveSink:
    """Append typed archive records without retaining them all in RAM."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, field_name: str, records: Iterable[Any]) -> int:
        if field_name not in STREAMABLE_ARCHIVE_FIELDS:
            raise ValueError(f"field is not an output-only stream: {field_name}")
        count = 0
        with self.path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps({
                    "archive": field_name,
                    "record": _jsonable(record),
                }, sort_keys=True) + "\n")
                count += 1
        return count


def stream_world_archives(
    world,
    sink: JsonlArchiveSink,
    *,
    fields: Iterable[str],
    clear: bool = True,
) -> dict[str, int]:
    """Stream selected output-only histories and optionally release memory."""
    counts = {}
    for field_name in fields:
        if field_name not in STREAMABLE_ARCHIVE_FIELDS:
            raise ValueError(f"field is not an output-only stream: {field_name}")
        records = getattr(world, field_name)
        if isinstance(records, dict):
            iterable = records.values()
        else:
            iterable = records
        counts[field_name] = sink.append(field_name, iterable)
        if clear:
            records.clear()
    return counts


T = TypeVar("T")


class TimeWindowBuffer(Generic[T]):
    """Bounded time-memory buffer for mechanisms with finite causal memory."""

    def __init__(self, window: float, *, max_records: int | None = None) -> None:
        if window < 0:
            raise ValueError("window must be nonnegative")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be positive")
        self.window = float(window)
        self.max_records = max_records
        self._records: deque[tuple[float, T]] = deque()

    def append(self, time: float, value: T) -> None:
        time = float(time)
        self._records.append((time, value))
        self.evict(time)
        if self.max_records is not None:
            while len(self._records) > self.max_records:
                self._records.popleft()

    def evict(self, current_time: float) -> None:
        cutoff = float(current_time) - self.window
        while self._records and self._records[0][0] < cutoff:
            self._records.popleft()

    def values(self, current_time: float) -> tuple[T, ...]:
        self.evict(current_time)
        return tuple(value for _, value in self._records)

    def __len__(self) -> int:
        return len(self._records)
