"""Persistent actor-owned access restrictions on locality corridors."""
from __future__ import annotations

from math import exp

from .entities import AccessRestriction, clamp
from .relations import organizations_hostile


def corridor_key(
    organization_id: str, first_locality_id: str, second_locality_id: str
) -> tuple[str, str, str]:
    if first_locality_id == second_locality_id:
        raise ValueError("corridor requires distinct localities")
    first, second = sorted((first_locality_id, second_locality_id))
    return organization_id, first, second


def build_access_restriction(
    world,
    organization_id: str,
    first_locality_id: str,
    second_locality_id: str,
    effort: float,
    time: float,
) -> AccessRestriction:
    if second_locality_id not in world.adjacency.get(first_locality_id, {}):
        raise ValueError("access restrictions can only be built on adjacent localities")
    key = corridor_key(organization_id, first_locality_id, second_locality_id)
    restriction = world.access_restrictions.get(key)
    if restriction is None:
        restriction = AccessRestriction(
            organization_id,
            key[1],
            key[2],
            0.0,
            float(time),
            float(time),
        )
        world.access_restrictions[key] = restriction
    rate = world.config.access_restriction.build_rate
    increment = clamp(rate * clamp(effort))
    restriction.level = clamp(
        1.0 - (1.0 - restriction.level) * (1.0 - increment)
    )
    restriction.cumulative_effort += max(0.0, float(effort))
    restriction.updated_at = float(time)
    return restriction


def decay_access_restrictions(world, time: float, elapsed_days: float) -> int:
    if elapsed_days <= 0:
        return 0
    decay_rate = world.config.access_restriction.decay_per_day
    factor = exp(-decay_rate * elapsed_days)
    removed = 0
    for key, restriction in list(world.access_restrictions.items()):
        restriction.level = clamp(restriction.level * factor)
        restriction.updated_at = float(time)
        if restriction.level <= 1e-9:
            del world.access_restrictions[key]
            removed += 1
    return removed


def edge_restriction_level(
    world,
    first_locality_id: str,
    second_locality_id: str,
    moving_organization_id: str | None = None,
) -> float:
    first, second = sorted((first_locality_id, second_locality_id))
    levels = []
    for (owner_id, edge_first, edge_second), restriction in world.access_restrictions.items():
        if edge_first != first or edge_second != second or restriction.level <= 0:
            continue
        if moving_organization_id is None:
            levels.append(restriction.level)
        elif owner_id == moving_organization_id:
            continue
        elif (
            owner_id in world.organizations
            and moving_organization_id in world.organizations
            and organizations_hostile(world, owner_id, moving_organization_id)
        ):
            levels.append(restriction.level)
    if not levels:
        return 0.0
    complement = 1.0
    for value in levels:
        complement *= 1.0 - clamp(value)
    return clamp(1.0 - complement)


def route_restriction_level(
    world, route: list[str] | tuple[str, ...], moving_organization_id: str | None = None
) -> float:
    return max(
        (
            edge_restriction_level(world, first, second, moving_organization_id)
            for first, second in zip(route, route[1:])
        ),
        default=0.0,
    )


def locality_access_pressure(world, locality_id: str) -> float:
    neighbors = world.adjacency.get(locality_id, {})
    if not neighbors:
        return 0.0
    return sum(
        edge_restriction_level(world, locality_id, neighbor, None)
        for neighbor in neighbors
    ) / len(neighbors)


def access_diagnostics(world) -> dict:
    return {
        "active_restrictions": len(world.access_restrictions),
        "mean_level": (
            sum(item.level for item in world.access_restrictions.values())
            / max(1, len(world.access_restrictions))
        ),
        "by_corridor": {
            "|".join(key): item.level
            for key, item in sorted(world.access_restrictions.items())
        },
    }
