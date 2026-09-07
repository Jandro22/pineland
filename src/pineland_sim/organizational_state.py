"""Local organizational capability derived from existing causal state.

This module contains no historical geography or case parameters. It converts
already-modeled membership, clandestine manpower, formations, institutions,
control, and actor-held information into locality-specific organizational
embeddedness and operational knowledge.
"""
from __future__ import annotations

from math import sqrt

from .entities import OrganizationKind, clamp
from .relations import STATE_SECURITY_KINDS, organizations_hostile


def local_membership_rootedness(
    world, organization_id: str, locality_id: str
) -> dict[str, float]:
    organization = world.organizations[organization_id]
    target = world.localities[locality_id]
    represented_local = 0.0
    home_local = 0.0
    home_district = 0.0
    for person_id in organization.member_ids:
        person = world.persons.get(person_id)
        if (
            person is None
            or person.organization_id != organization_id
            or person.armed_fraction <= 0
            or person.residence_locality_id != locality_id
        ):
            continue
        represented = person.weight * person.armed_fraction
        if represented <= 0:
            continue
        represented_local += represented
        if person.home_locality_id == locality_id:
            home_local += represented
        home = world.localities.get(person.home_locality_id)
        if home is not None and home.district_id == target.district_id:
            home_district += represented
    if represented_local <= 1e-12:
        return {
            "represented_local_membership": 0.0,
            "home_locality_share": 0.0,
            "home_district_share": 0.0,
        }
    return {
        "represented_local_membership": represented_local,
        "home_locality_share": clamp(home_local / represented_local),
        "home_district_share": clamp(home_district / represented_local),
    }


def _equipped_pool(world, organization_id: str, locality_id: str) -> float:
    manpower = max(
        0.0,
        float(world.organization_manpower_pools.get(
            (organization_id, locality_id), 0.0
        )),
    )
    reserve = max(
        0.0,
        float(world.organization_manpower_supply_reserves.get(
            (organization_id, locality_id), 0.0
        )),
    )
    supply_per_fighter = max(
        1e-12,
        float(world.config.logistics.formation_supply_days)
        * float(world.config.logistics.initial_supply_fraction),
    )
    return min(manpower, reserve / supply_per_fighter)


def local_organizational_embeddedness(
    world, organization_id: str, locality_id: str
) -> float:
    """Bounded union of modeled local organizational foothold channels."""
    organization = world.organizations[organization_id]
    cfg = world.config.organization_ecology
    threshold = max(1e-12, float(cfg.minimum_formation_personnel))
    profile = local_membership_rootedness(
        world, organization_id, locality_id
    )
    member_depth = clamp(
        profile["represented_local_membership"]
        / max(1e-12, float(cfg.minimum_proto_represented_population))
    )
    origin_depth = clamp(
        (
            profile["home_locality_share"]
            + profile["home_district_share"]
        ) / 2.0
    )
    member_channel = member_depth * (0.5 + 0.5 * origin_depth)

    pool_depth = clamp(
        _equipped_pool(world, organization_id, locality_id) / threshold
    )
    pool_channel = pool_depth * clamp(organization.local_knowledge)

    formations = [
        formation
        for formation in world.formations.values()
        if (
            formation.organization_id == organization_id
            and formation.locality_id == locality_id
            and formation.personnel > 0
            and not formation.moving
            and not formation.outside_pineland
            and formation.operational_status == "effective"
        )
    ]
    fielded = sum(formation.personnel for formation in formations)
    if fielded > 0:
        mean_embeddedness = sum(
            formation.personnel * clamp(formation.embeddedness)
            for formation in formations
        ) / fielded
        formation_channel = clamp(fielded / threshold) * mean_embeddedness
    else:
        formation_channel = 0.0

    vector = world.localities[locality_id].control.get(organization_id)
    institutional_channel = (
        0.0
        if vector is None
        else clamp(
            (vector.social + vector.administrative + vector.expected) / 3.0
        )
    )

    complement = 1.0
    for value in (
        member_channel,
        pool_channel,
        formation_channel,
        institutional_channel,
    ):
        complement *= 1.0 - clamp(value)
    return clamp(1.0 - complement)


def local_operational_information(
    world,
    organization_id: str,
    locality_id: str,
    target_organization_id: str | None = None,
) -> float:
    """Actor-held local target information; hidden opponent truth is excluded."""
    observer_ids = {organization_id}
    observer_ids.update(
        formation.formation_id
        for formation in world.formations.values()
        if formation.organization_id == organization_id
    )
    if target_organization_id is not None:
        targets = {target_organization_id}
        target = world.organizations.get(target_organization_id)
        if target is not None:
            if target.kind in STATE_SECURITY_KINDS:
                targets.add("government")
            elif target.kind is OrganizationKind.INSURGENT:
                targets.add("insurgent")
    else:
        targets = {
            other.organization_id
            for other in world.organizations.values()
            if (
                other.organization_id != organization_id
                and other.status == "active"
                and organizations_hostile(
                    world, organization_id, other.organization_id
                )
            )
        }

    evidence = []
    for belief in (
        *world.presence_beliefs.values(),
        *world.node_presence_beliefs.values(),
    ):
        if (
            belief.observer_id in observer_ids
            and belief.locality_id == locality_id
            and belief.target_actor_id in targets
            and belief.evidence_count > 0
        ):
            world.materialize_compact_confidence(belief)
            evidence.append(
                clamp(belief.confidence) * clamp(belief.presence_estimate)
            )
    for target_id in targets:
        belief = world.control_beliefs.get(
            (organization_id, target_id, locality_id)
        )
        if belief is None or belief.evidence_count <= 0:
            continue
        target_signal = max(
            clamp(belief.control_estimate.formal),
            clamp(belief.control_estimate.physical),
            clamp(belief.control_estimate.administrative),
        )
        evidence.append(clamp(belief.confidence) * target_signal)
    return max(evidence, default=0.0)


def local_operational_knowledge(
    world,
    organization_id: str,
    locality_id: str,
    target_organization_id: str | None = None,
) -> float:
    """General tradecraft combined with genuinely local access/information."""
    organization = world.organizations[organization_id]
    embedded = local_organizational_embeddedness(
        world, organization_id, locality_id
    )
    information = local_operational_information(
        world,
        organization_id,
        locality_id,
        target_organization_id,
    )
    local_access = 1.0 - (1.0 - embedded) * (1.0 - information)
    return clamp(sqrt(clamp(organization.local_knowledge) * local_access))
