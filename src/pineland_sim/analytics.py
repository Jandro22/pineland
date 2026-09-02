from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean, pstdev
from typing import Iterable

from .entities import CONTROL_DIMENSIONS
from .world import WorldState
from .networks import locality_social_aggregation, network_diagnostics


def locality_control_change(world: WorldState, locality_id: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in world.causal_ledger:
        if item.locality_id == locality_id:
            result[item.mechanism][item.dimension] += item.amount
    return {mechanism: dict(values) for mechanism, values in result.items()}


def control_velocity(checkpoints: Iterable[dict], locality_id: str, actor: str = "government") -> float:
    points = list(checkpoints)
    if len(points) < 2:
        return 0.0
    first, last = points[0], points[-1]
    dt = last["time"] - first["time"]
    if dt <= 0:
        return 0.0
    delta = [last["control"][locality_id][actor][key] - first["control"][locality_id][actor][key]
             for key in CONTROL_DIMENSIONS]
    return sqrt(sum((value / dt) ** 2 for value in delta))


def district_control(world: WorldState, district_id: str, actor: str = "government") -> float:
    localities = [world.localities[x] for x in world.districts[district_id].locality_ids]
    total_weight = sum(locality.population * (1 + world.districts[district_id].connectivity) for locality in localities)
    return sum(locality.control[actor].effective() * locality.population *
               (1 + world.districts[district_id].connectivity) for locality in localities) / total_weight


def district_control_distribution(world: WorldState, district_id: str,
                                  actor: str = "government") -> dict[str, float]:
    """Retain population-weighted mean, dispersion, and connected-edge control."""
    localities = [world.localities[x] for x in world.districts[district_id].locality_ids]
    total_population = sum(locality.population for locality in localities)
    values = {locality.locality_id: locality.control[actor].effective() for locality in localities}
    weighted_mean = sum(values[locality.locality_id] * locality.population
                        for locality in localities) / total_population
    variance = sum(locality.population * (values[locality.locality_id] - weighted_mean) ** 2
                   for locality in localities) / total_population
    numerator = 0.0
    denominator = 0.0
    locality_ids = set(values)
    for first in locality_ids:
        for second, cost in world.adjacency[first].items():
            if second in locality_ids and first < second:
                connectivity = 1 / max(cost, 1e-9)
                numerator += connectivity * values[first] * values[second]
                denominator += connectivity
    return {"mean": weighted_mean, "variance": variance,
            "connected_control": numerator / denominator if denominator else weighted_mean ** 2,
            "minimum": min(values.values()), "maximum": max(values.values())}


def ensemble_summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("ensemble cannot be empty")
    ordered = sorted(values)
    quantile = lambda q: ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
    return {"mean": mean(values), "std": pstdev(values), "p05": quantile(.05),
            "median": quantile(.5), "p95": quantile(.95),
            "probability_positive": sum(value > 0 for value in values) / len(values)}
