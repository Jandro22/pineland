"""Local organizational capability derived from existing causal state.

This module contains no historical geography or case parameters. It converts
already-modeled membership, clandestine manpower, formations, institutions,
control, and actor-held information into locality-specific organizational
embeddedness and operational knowledge.
"""
from __future__ import annotations

from math import exp, sqrt

from .entities import LocalFoothold, OrganizationKind, clamp
from .relations import STATE_SECURITY_KINDS, organizations_hostile


def local_membership_rootedness(
    world, organization_id: str, locality_id: str
) -> dict[str, float]:
    organization = world.organizations[organization_id]
    target = world.localities[locality_id]
    represented_local = 0.0
    home_local = 0.0
    home_district = 0.0
    # Organizations store membership as a set for O(1) updates.  The
    # transition equations nevertheless require a stable summation order so
    # the oracle is independent of PYTHONHASHSEED and can be compared bitwise
    # with the native person-index traversal.
    for person_id in sorted(organization.member_ids):
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


def _foothold_organizations(world):
    return (
        organization
        for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT
    )


def _foothold_threshold(world) -> float:
    return clamp(float(world.config.organization_ecology.local_foothold_viability_threshold))


def _ensure_local_foothold(world, organization_id: str, locality_id: str,
                           time: float | None = None) -> LocalFoothold:
    key = (organization_id, locality_id)
    foothold = world.local_footholds.get(key)
    if foothold is None:
        timestamp = float(world.time if time is None else time)
        foothold = LocalFoothold(
            organization_id=organization_id,
            locality_id=locality_id,
            updated_at=timestamp,
        )
        world.local_footholds[key] = foothold
    return foothold


def initialize_local_footholds(world, time: float | None = None) -> None:
    """Create explicit local organizational stocks from the initial state.

    This is an initialization bridge, not a new source of fighters.  The
    stock records what the existing membership, pooled capacity, formations,
    and institutional state imply at time zero so later movement can be
    distinguished from first arrival.
    """
    timestamp = float(world.time if time is None else time)
    threshold = _foothold_threshold(world)
    for organization in _foothold_organizations(world):
        for locality_id in sorted(world.localities):
            key = (organization.organization_id, locality_id)
            if key in world.local_footholds:
                continue
            raw = local_organizational_embeddedness(
                world, organization.organization_id, locality_id
            )
            foothold = LocalFoothold(
                organization_id=organization.organization_id,
                locality_id=locality_id,
                strength=raw,
                raw_signal=raw,
                updated_at=timestamp,
                first_activated_at=timestamp if raw >= threshold else None,
                last_activated_at=timestamp if raw >= threshold else None,
                viable_activation_count=1 if raw >= threshold else 0,
            )
            world.local_footholds[key] = foothold


def advance_local_footholds(world, time: float | None = None) -> None:
    """Renew or decay locality footholds at a deterministic event boundary.

    Current local organizational evidence can raise the stock immediately;
    absent renewal, the old stock decays exponentially.  Organization
    persistence changes the memory timescale, while the explicit memory
    parameter remains the same across cases.  No random draw is used here.
    """
    timestamp = float(world.time if time is None else time)
    initialize_local_footholds(world, timestamp)
    threshold = _foothold_threshold(world)
    base_memory = max(
        1e-9,
        float(world.config.organization_ecology.local_foothold_memory_days),
    )
    for foothold in world.local_footholds.values():
        organization = world.organizations.get(foothold.organization_id)
        if organization is None:
            foothold.updated_at = timestamp
            continue
        elapsed = max(0.0, timestamp - float(foothold.updated_at))
        memory_days = base_memory * (0.5 + clamp(organization.persistence))
        retention = exp(-elapsed / max(1e-9, memory_days))
        raw = local_organizational_embeddedness(
            world, foothold.organization_id, foothold.locality_id
        )
        previous = clamp(foothold.strength)
        if raw > 1e-12:
            foothold.renewal_count += 1
        if previous >= threshold:
            foothold.cumulative_active_days += elapsed
        # Renewal is an observed local signal; it cannot be negative and is
        # allowed to arrive faster than memory decays after a formation or
        # recruitment event.  The retained stock is never used as fighter
        # equivalents directly.
        updated = clamp(max(previous * retention, raw))
        if previous < threshold <= updated:
            foothold.viable_activation_count += 1
            if foothold.first_activated_at is None:
                foothold.first_activated_at = timestamp
            foothold.last_activated_at = timestamp
        elif updated >= threshold:
            foothold.last_activated_at = timestamp
        foothold.strength = updated
        foothold.raw_signal = raw
        foothold.updated_at = timestamp


def local_foothold_strength(world, organization_id: str, locality_id: str) -> float:
    """Return persistent local organizational stock without creating capacity."""
    organization = world.organizations.get(organization_id)
    if organization is None or organization.kind is not OrganizationKind.INSURGENT:
        return 0.0
    foothold = world.local_footholds.get((organization_id, locality_id))
    if foothold is None:
        # Compatibility for hand-built test worlds and old checkpoints: the
        # raw embeddedness channel remains available to callers directly, but
        # there is no persistent stock until an updater records a boundary.
        return 0.0
    if foothold.renewal_count <= 0:
        # Initial state is not silently treated as a post-movement memory
        # stock until an event boundary has renewed it.  This keeps direct
        # fixture mutations truthful while normal simulations call the
        # updater before their first transition.
        return 0.0
    return clamp(foothold.strength)


def record_local_foothold_arrival(world, formation, time: float | None = None) -> None:
    """Record a physical arrival as renewal of local organizational stock."""
    organization = world.organizations.get(formation.organization_id)
    if organization is None or organization.kind is not OrganizationKind.INSURGENT:
        return
    timestamp = float(world.time if time is None else time)
    foothold = _ensure_local_foothold(
        world, formation.organization_id, formation.locality_id, timestamp
    )
    foothold.cumulative_arrivals += 1
    foothold.renewal_count += 1
    threshold = max(
        1e-9, float(world.config.organization_ecology.minimum_formation_personnel)
    )
    arrival_signal = clamp(
        max(0.0, float(formation.personnel)) / threshold
    ) * clamp(float(formation.embeddedness))
    foothold.strength = clamp(max(foothold.strength, arrival_signal))
    foothold.raw_signal = max(foothold.raw_signal, arrival_signal)


def record_local_foothold_recruitment(
    world, organization_id: str, locality_id: str, represented_mass: float
) -> None:
    foothold = _ensure_local_foothold(world, organization_id, locality_id)
    foothold.cumulative_recruits += max(0.0, float(represented_mass))
    foothold.renewal_count += 1


def record_local_foothold_action(
    world, organization_id: str, locality_id: str
) -> None:
    foothold = _ensure_local_foothold(world, organization_id, locality_id)
    foothold.cumulative_actions += 1
    foothold.renewal_count += 1


def local_foothold_diagnostics(world) -> dict:
    """Compact diagnostics for persistence, renewal, and spatial reproduction."""
    rows = []
    for key in sorted(world.local_footholds):
        foothold = world.local_footholds[key]
        rows.append({
            "organization_id": foothold.organization_id,
            "locality_id": foothold.locality_id,
            "strength": clamp(foothold.strength),
            "raw_signal": clamp(foothold.raw_signal),
            "updated_at": foothold.updated_at,
            "first_activated_at": foothold.first_activated_at,
            "last_activated_at": foothold.last_activated_at,
            "cumulative_active_days": foothold.cumulative_active_days,
            "cumulative_arrivals": foothold.cumulative_arrivals,
            "cumulative_recruits": foothold.cumulative_recruits,
            "cumulative_actions": foothold.cumulative_actions,
            "viable_activation_count": foothold.viable_activation_count,
            "renewal_count": foothold.renewal_count,
        })
    threshold = _foothold_threshold(world)
    viable = [row for row in rows if row["strength"] >= threshold]
    return {
        "viability_threshold": threshold,
        "count": len(rows),
        "viable_count": len(viable),
        "mean_strength": (
            sum(row["strength"] for row in rows) / len(rows) if rows else 0.0
        ),
        "mean_viable_strength": (
            sum(row["strength"] for row in viable) / len(viable) if viable else 0.0
        ),
        "viable_activation_count": sum(
            row["viable_activation_count"] for row in rows
        ),
        "rows": rows,
    }


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
    persistent = local_foothold_strength(world, organization_id, locality_id)
    # A durable foothold carries local routines forward after a formation
    # moves. It supplements, rather than replaces, actor-held target evidence.
    local_access = 1.0 - (1.0 - embedded) * (1.0 - information) * (1.0 - persistent)
    return clamp(sqrt(clamp(organization.local_knowledge) * local_access))
