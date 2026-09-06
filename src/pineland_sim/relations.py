"""Organization-to-organization relationships and path-dependent rivalry.

Kinds are taxonomic. Relations are strategic. Keeping those concepts separate
removes the former assumption that every non-insurgent actor belongs to one
government side and every insurgent is mutually aligned with every other
insurgent.
"""
from __future__ import annotations

from itertools import combinations
from math import exp, log

from .entities import (
    OrganizationKind,
    OrganizationRelation,
    RelationStatus,
    clamp,
)


STATE_SECURITY_KINDS = {
    OrganizationKind.GOVERNMENT,
    OrganizationKind.MILITARY,
    OrganizationKind.POLICE,
    OrganizationKind.INTELLIGENCE,
}


def relation_key(first_id: str, second_id: str) -> tuple[str, str]:
    if first_id == second_id:
        raise ValueError("organization relation requires distinct actors")
    return tuple(sorted((str(first_id), str(second_id))))


def _default_status(world, first_id: str, second_id: str) -> RelationStatus:
    first = world.organizations.get(first_id)
    second = world.organizations.get(second_id)
    if first is None or second is None:
        return RelationStatus.NEUTRAL
    if first.kind in STATE_SECURITY_KINDS and second.kind in STATE_SECURITY_KINDS:
        return RelationStatus.ALLIED
    if (
        (first.kind is OrganizationKind.INSURGENT and second.kind in STATE_SECURITY_KINDS)
        or
        (second.kind is OrganizationKind.INSURGENT and first.kind in STATE_SECURITY_KINDS)
    ):
        return RelationStatus.HOSTILE
    return RelationStatus.NEUTRAL


def ensure_relation(world, first_id: str, second_id: str, time: float | None = None):
    key = relation_key(first_id, second_id)
    relation = world.organization_relations.get(key)
    if relation is None:
        status = _default_status(world, *key)
        relation = OrganizationRelation(
            key[0],
            key[1],
            status=status,
            hostility_memory=1.0 if status is RelationStatus.HOSTILE else 0.0,
            cooperation_memory=1.0 if status is RelationStatus.ALLIED else 0.0,
            updated_at=world.time if time is None else float(time),
        )
        world.organization_relations[key] = relation
    return relation


def initialize_organization_relations(world, time: float = 0.0) -> None:
    world.organization_relations.clear()
    active = [
        organization.organization_id
        for organization in world.organizations.values()
        if organization.status == "active"
    ]
    for first_id, second_id in combinations(sorted(active), 2):
        ensure_relation(world, first_id, second_id, time)


def set_relation(
    world,
    first_id: str,
    second_id: str,
    status: RelationStatus | str,
    time: float | None = None,
    *,
    rivalry_memory: float | None = None,
    hostility_memory: float | None = None,
    cooperation_memory: float | None = None,
):
    relation = ensure_relation(world, first_id, second_id, time)
    relation.status = RelationStatus(status)
    if rivalry_memory is not None:
        relation.rivalry_memory = clamp(rivalry_memory)
    if hostility_memory is not None:
        relation.hostility_memory = clamp(hostility_memory)
    if cooperation_memory is not None:
        relation.cooperation_memory = clamp(cooperation_memory)
    relation.updated_at = world.time if time is None else float(time)
    return relation


def relation_status(world, first_id: str, second_id: str) -> RelationStatus:
    if first_id == second_id:
        return RelationStatus.ALLIED
    relation = ensure_relation(world, first_id, second_id)
    for actor in (first_id, second_id):
        organization = world.organizations.get(actor)
        if (
            organization is not None
            and organization.kind is OrganizationKind.INSURGENT
            and world.ceasefires.get(actor) == "active"
        ):
            other = second_id if actor == first_id else first_id
            other_org = world.organizations.get(other)
            if other_org is not None and other_org.kind in STATE_SECURITY_KINDS:
                return RelationStatus.CEASEFIRE
    return relation.status


def organizations_hostile(world, first_id: str, second_id: str) -> bool:
    return relation_status(world, first_id, second_id) is RelationStatus.HOSTILE


def organizations_allied(world, first_id: str, second_id: str) -> bool:
    return relation_status(world, first_id, second_id) in {
        RelationStatus.ALLIED,
        RelationStatus.COOPERATIVE,
    }


def record_relation_harm(
    world, first_id: str, second_id: str, magnitude: float, time: float
) -> OrganizationRelation:
    relation = ensure_relation(world, first_id, second_id, time)
    magnitude = clamp(magnitude)
    relation.hostility_memory = clamp(
        1.0 - (1.0 - relation.hostility_memory) * (1.0 - magnitude)
    )
    relation.rivalry_memory = clamp(
        1.0 - (1.0 - relation.rivalry_memory) * (1.0 - 0.5 * magnitude)
    )
    relation.cooperation_memory *= 1.0 - magnitude
    relation.last_interaction_at = float(time)
    relation.updated_at = float(time)
    if relation.hostility_memory >= world.config.relationships.hostility_threshold:
        relation.status = RelationStatus.HOSTILE
    elif relation.rivalry_memory >= world.config.relationships.rivalry_threshold:
        relation.status = RelationStatus.RIVAL
    return relation


def record_relation_cooperation(
    world, first_id: str, second_id: str, magnitude: float, time: float
) -> OrganizationRelation:
    relation = ensure_relation(world, first_id, second_id, time)
    magnitude = clamp(magnitude)
    relation.cooperation_memory = clamp(
        1.0 - (1.0 - relation.cooperation_memory) * (1.0 - magnitude)
    )
    relation.rivalry_memory *= 1.0 - magnitude
    relation.hostility_memory *= 1.0 - magnitude
    relation.last_interaction_at = float(time)
    relation.updated_at = float(time)
    if relation.cooperation_memory >= 0.55 and relation.hostility_memory < 0.2:
        relation.status = RelationStatus.COOPERATIVE
    return relation


def inherit_parent_relations(
    world,
    parent_ids: tuple[str, ...] | list[str],
    child_ids: tuple[str, ...] | list[str],
    time: float,
) -> None:
    """Give new organizations their parents' strategic relationships."""
    parents = tuple(parent_ids)
    children = tuple(child_ids)
    rank = {
        RelationStatus.ALLIED: 0,
        RelationStatus.COOPERATIVE: 1,
        RelationStatus.NEUTRAL: 2,
        RelationStatus.CEASEFIRE: 3,
        RelationStatus.RIVAL: 4,
        RelationStatus.HOSTILE: 5,
    }
    for child_id in children:
        for other_id, other in world.organizations.items():
            if other_id == child_id or other_id in children or other.status != "active":
                continue
            inherited = []
            for parent_id in parents:
                key = relation_key(parent_id, other_id)
                if key in world.organization_relations:
                    inherited.append(world.organization_relations[key])
            if inherited:
                status = max((item.status for item in inherited), key=rank.__getitem__)
                set_relation(
                    world,
                    child_id,
                    other_id,
                    status,
                    time,
                    rivalry_memory=max(item.rivalry_memory for item in inherited),
                    hostility_memory=max(item.hostility_memory for item in inherited),
                    cooperation_memory=max(item.cooperation_memory for item in inherited),
                )
            else:
                ensure_relation(world, child_id, other_id, time)
    if len(parents) == 1 and len(children) > 1:
        for first_id, second_id in combinations(children, 2):
            set_relation(
                world,
                first_id,
                second_id,
                RelationStatus.RIVAL,
                time,
                rivalry_memory=world.config.relationships.split_rivalry_memory,
            )
    elif len(parents) > 1 and len(children) == 1:
        for first_id, second_id in combinations(parents, 2):
            if first_id in world.organizations and second_id in world.organizations:
                record_relation_cooperation(world, first_id, second_id, 0.5, time)


def _presence_sites(world, organization_id: str) -> set[str]:
    sites = {
        formation.locality_id
        for formation in world.formations.values()
        if (
            formation.organization_id == organization_id
            and formation.personnel > 0
            and not formation.outside_pineland
        )
    }
    organization = world.organizations.get(organization_id)
    if organization is not None:
        sites.update(
            world.persons[person_id].residence_locality_id
            for person_id in organization.member_ids
            if (
                person_id in world.persons
                and world.persons[person_id].organization_id == organization_id
                and world.persons[person_id].armed_fraction > 0
            )
        )
    return sites


def update_relationship_ecology(
    world, time: float, interval_days: float, rng
) -> dict[str, int]:
    """Decay dyadic memory and allow rivalry to escalate or de-escalate."""
    if interval_days <= 0:
        return {"rivalries": 0, "escalations": 0, "deescalations": 0}
    cfg = world.config.relationships
    decay = exp(log(0.5) * interval_days / cfg.memory_half_life_days)
    active_insurgents = sorted(
        (
            organization
            for organization in world.organizations.values()
            if organization.kind is OrganizationKind.INSURGENT
            and organization.status == "active"
        ),
        key=lambda item: item.organization_id,
    )
    rivalries = escalations = deescalations = 0
    for first, second in combinations(active_insurgents, 2):
        relation = ensure_relation(world, first.organization_id, second.organization_id, time)
        relation.rivalry_memory *= decay
        relation.hostility_memory *= decay
        relation.cooperation_memory *= decay
        first_sites = _presence_sites(world, first.organization_id)
        second_sites = _presence_sites(world, second.organization_id)
        union = first_sites | second_sites
        overlap = len(first_sites & second_sites) / max(1, len(union))
        keys = set(first.ideology) | set(second.ideology)
        ideology_distance = (
            sum(
                abs(first.ideology.get(key, 0.5) - second.ideology.get(key, 0.5))
                for key in keys
            )
            / max(1, len(keys))
        )
        rivalry_pressure = clamp(overlap * (0.25 + 0.75 * ideology_distance))
        cooperation_pressure = clamp(overlap * (1.0 - ideology_distance))
        assimilation = 1.0 - decay
        relation.rivalry_memory = clamp(
            relation.rivalry_memory + assimilation * rivalry_pressure
        )
        relation.cooperation_memory = clamp(
            relation.cooperation_memory + assimilation * 0.5 * cooperation_pressure
        )
        previous = relation.status
        if (
            relation.status in {RelationStatus.NEUTRAL, RelationStatus.COOPERATIVE}
            and relation.rivalry_memory >= cfg.rivalry_threshold
        ):
            relation.status = RelationStatus.RIVAL
            rivalries += 1
        if relation.status is RelationStatus.RIVAL:
            reference_probability = clamp(
                cfg.escalation_base_hazard * relation.rivalry_memory
            )
            interval_probability = (
                1.0 - (1.0 - reference_probability) ** (interval_days / 7.0)
                if reference_probability < 1.0
                else 1.0
            )
            if rng.random() < interval_probability:
                relation.status = RelationStatus.HOSTILE
                relation.hostility_memory = max(
                    relation.hostility_memory, cfg.hostility_threshold
                )
                escalations += 1
        elif relation.status is RelationStatus.HOSTILE:
            reference_probability = clamp(
                cfg.deescalation_reference_rate
                * max(0.0, cfg.rivalry_threshold - relation.hostility_memory)
            )
            interval_probability = (
                1.0 - (1.0 - reference_probability) ** (interval_days / 7.0)
                if reference_probability < 1.0
                else 1.0
            )
            if (
                relation.hostility_memory < cfg.rivalry_threshold
                and rng.random() < interval_probability
            ):
                relation.status = RelationStatus.RIVAL
                deescalations += 1
        relation.updated_at = float(time)
        if previous is not relation.status:
            relation.last_interaction_at = float(time)
    return {
        "rivalries": rivalries,
        "escalations": escalations,
        "deescalations": deescalations,
    }


def relationship_diagnostics(world) -> dict:
    return {
        "relations": len(world.organization_relations),
        "by_status": {
            status.value: sum(
                relation.status is status
                for relation in world.organization_relations.values()
            )
            for status in RelationStatus
        },
        "dyads": {
            "|".join(key): {
                "status": relation.status.value,
                "rivalry_memory": relation.rivalry_memory,
                "hostility_memory": relation.hostility_memory,
                "cooperation_memory": relation.cooperation_memory,
            }
            for key, relation in sorted(world.organization_relations.items())
        },
    }
