"""Historical-panel estimators and immutable split safeguards.

These functions operate on recorded evidence. They deliberately do not import
simulation state or infer latent truth from event counts.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from statistics import mean, pvariance
from typing import Any


VALID_SPLITS = frozenset({
    "training", "temporal_validation", "geographic_validation",
    "strict_joint_holdout",
})


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_split(path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("status") != "frozen_before_fit":
        raise ValueError("split manifest is not frozen before fit")
    if set(manifest.get("splits", {})) != VALID_SPLITS:
        raise ValueError("split manifest must define exactly the four preregistered splits")
    if manifest.get("held_out_outcomes_may_enter_calibration") is not False:
        raise ValueError("split manifest permits calibration leakage")
    if manifest.get("validation_may_refit") is not False:
        raise ValueError("split manifest permits validation refitting")
    return manifest


def rows_for_purpose(rows: Iterable[Mapping[str, Any]], split: str,
                     purpose: str) -> list[Mapping[str, Any]]:
    if split not in VALID_SPLITS:
        raise ValueError(f"unknown split: {split}")
    if purpose == "calibration" and split != "training":
        raise PermissionError("calibration may consume training outcomes only")
    if purpose not in {"calibration", "validation", "description"}:
        raise ValueError(f"unknown purpose: {purpose}")
    return [row for row in rows if row["split"] == split]


def assert_validation_lock(lock: Mapping[str, Any], expected_split_hash: str) -> None:
    if lock.get("status") != "locked":
        raise PermissionError("validation requires a locked calibration manifest")
    if lock.get("split_manifest_sha256") != expected_split_hash:
        raise PermissionError("calibration lock belongs to a different split manifest")
    if lock.get("refit_permitted") is not False:
        raise PermissionError("validation lock permits refitting")


def gini(values: Sequence[float]) -> float:
    nonnegative = sorted(max(0.0, float(value)) for value in values)
    total, count = sum(nonnegative), len(nonnegative)
    if not count or total == 0:
        return 0.0
    return sum((2 * index - count - 1) * value
               for index, value in enumerate(nonnegative, 1)) / (count * total)


def population_adjusted_hhi(events: Sequence[float], population: Sequence[float]) -> float:
    if len(events) != len(population) or not events:
        raise ValueError("events and population must be non-empty and aligned")
    event_total, population_total = sum(events), sum(population)
    if event_total <= 0 or population_total <= 0:
        return 0.0
    observed = sum((value / event_total) ** 2 for value in events)
    baseline = sum((value / population_total) ** 2 for value in population)
    return (observed - baseline) / max(1e-12, 1.0 - baseline)


def fano_factor(values: Sequence[float]) -> float:
    return pvariance(values) / mean(values) if values and mean(values) > 0 else 0.0


def burstiness(gaps: Sequence[float]) -> float:
    if len(gaps) < 2:
        return 0.0
    average, variance = mean(gaps), pvariance(gaps)
    deviation = sqrt(variance)
    return (deviation - average) / (deviation + average) if deviation + average else 0.0


def lag_correlation(values: Sequence[float], lag: int = 1) -> float:
    if lag < 1 or len(values) <= lag:
        return 0.0
    left, right = values[:-lag], values[lag:]
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = sqrt(sum((a - left_mean) ** 2 for a in left) *
                       sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else 0.0


def active_run_lengths(values: Sequence[float]) -> list[int]:
    runs: list[int] = []
    current = 0
    for value in values:
        if value > 0:
            current += 1
        elif current:
            runs.append(current); current = 0
    if current:
        runs.append(current)
    return runs


def morans_i(values: Mapping[str, float], adjacency: Mapping[str, Sequence[str]]) -> float:
    keys = sorted(values)
    average = mean(values[key] for key in keys)
    deviations = {key: values[key] - average for key in keys}
    links = [(first, second) for first in keys
             for second in adjacency.get(first, ()) if second in values]
    denominator = sum(value ** 2 for value in deviations.values())
    if not links or denominator == 0:
        return 0.0
    numerator = sum(deviations[first] * deviations[second] for first, second in links)
    return len(keys) / len(links) * numerator / denominator


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, first)
    lat2, lon2 = map(radians, second)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371.0088 * asin(min(1.0, sqrt(value)))
