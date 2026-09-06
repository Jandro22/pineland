from __future__ import annotations

import heapq
from math import exp, inf
from statistics import mean

from .entities import (
    ActorZoneBelief,
    ControlVector,
    Microzone,
    OrganizationKind,
    Patrol,
    PhysicalEdge,
    SecurityPost,
    clamp,
)
from .world import WorldState, seeded_initialization_rng
from .relations import organizations_allied


_INSURGENT_SIDE_ACTOR = "__insurgent_side__"


def active_insurgent_ids(world: WorldState) -> tuple[str, ...]:
    return tuple(sorted(
        organization.organization_id
        for organization in world.organizations.values()
        if (
            organization.kind is OrganizationKind.INSURGENT
            and organization.status == "active"
        )
    ))


def aggregate_insurgent_control(
    world: WorldState, locality_id: str
) -> ControlVector:
    """Return a derived insurgent-side control vector without mutating truth.

    Concrete organization IDs always remain concrete. The side aggregate is a
    measurement/analysis view composed across currently active insurgent
    organizations. Physical reach uses the dedicated side-level physical
    response calculation when available; other dimensions use the bounded
    union of franchise-specific reach.
    """
    ids = active_insurgent_ids(world)
    if not ids:
        return ControlVector()
    locality = world.localities[locality_id]
    if ids == ("insurgent",):
        # In the legacy/single-franchise world the concrete organization and
        # the side are identical.  Respect the authoritative locality vector
        # directly, including controlled synthetic interventions in tests.
        return ControlVector(**locality.control["insurgent"].to_dict())
    values: dict[str, float] = {}
    for dimension in (
        "formal", "physical", "administrative", "legal", "fiscal", "social", "expected"
    ):
        if dimension == "physical":
            zones = zones_in_locality(world, locality_id)
            side_values = [
                zone.physical_control.get(_INSURGENT_SIDE_ACTOR)
                for zone in zones
            ]
            if zones and all(value is not None for value in side_values):
                values[dimension] = clamp(sum(
                    zone.population_share * float(value)
                    for zone, value in zip(zones, side_values)
                ))
                continue
        complement = 1.0
        for organization_id in ids:
            vector = locality.control.get(organization_id)
            value = getattr(vector, dimension) if vector is not None else 0.0
            complement *= 1.0 - clamp(value)
        values[dimension] = clamp(1.0 - complement)
    return ControlVector(**values)


def physical_edge_key(first_id: str, second_id: str) -> tuple[str, str]:
    if first_id == second_id:
        raise ValueError("physical self edges are not permitted")
    return tuple(sorted((first_id, second_id)))


def _add_physical_edge(world: WorldState, first_id: str, second_id: str,
                       distance_km: float, road_quality: float, disruption: float = 0.0) -> None:
    key = physical_edge_key(first_id, second_id)
    if key in world.physical_edges:
        return
    first = world.microzones[first_id]
    second = world.microzones[second_id]
    terrain = (first.terrain_friction + second.terrain_friction) / 2
    travel_time = distance_km * terrain / max(.1, road_quality) / 20
    edge = PhysicalEdge(key[0], key[1], distance_km, road_quality, travel_time, disruption)
    world.physical_edges[key] = edge
    world.physical_neighbors[first_id][second_id] = key
    world.physical_neighbors[second_id][first_id] = key


def zones_in_locality(world: WorldState, locality_id: str) -> list[Microzone]:
    zone_ids = world.microzone_ids_by_locality.get(locality_id)
    if zone_ids is not None:
        return [world.microzones[zone_id] for zone_id in zone_ids]
    # Compatibility fallback for manually assembled worlds.
    return [zone for zone in world.microzones.values() if zone.locality_id == locality_id]


def posts_in_locality(world: WorldState, locality_id: str) -> list[SecurityPost]:
    post_ids = world.security_post_ids_by_locality.get(locality_id)
    if post_ids is not None:
        return [world.security_posts[post_id] for post_id in post_ids]
    return [post for post in world.security_posts.values()
            if post.locality_id == locality_id]


def _actor_matches_organization(world: WorldState, organization_id: str,
                                 actor_id: str) -> bool:
    """Match an aggregate side or a concrete organization without id hacks."""
    organization = world.organizations.get(organization_id)
    if organization is None:
        return False
    if actor_id == _INSURGENT_SIDE_ACTOR:
        return organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    if actor_id == "insurgent":
        literal = world.organizations.get("insurgent")
        if literal is not None and literal.status == "active":
            return organization_id == "insurgent"
        return organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    if actor_id == "government":
        if organization_id == "government":
            return organization.status == "active"
        return bool(
            "government" in world.organizations
            and organization.status == "active"
            and organizations_allied(world, organization_id, "government")
        )
    target = world.organizations.get(actor_id)
    if target is not None and target.kind is OrganizationKind.INSURGENT:
        return organization_id == actor_id and target.status == "active"
    return organization_id == actor_id


def generate_physical_world(world: WorldState) -> None:
    config = world.config.physical
    rng = seeded_initialization_rng(world.config, "physical-world-generation")
    world.microzones.clear()
    world.microzone_ids_by_locality.clear()
    world.physical_edges.clear()
    world.physical_neighbors.clear()
    world.security_posts.clear()
    world.security_post_ids_by_locality.clear()
    world.patrols.clear()
    world.zone_beliefs.clear()

    role_names = ("Civic Core", "Market", "Residential", "Transit", "Industrial",
                  "Institutional", "Perimeter", "Outer Settlement")
    for locality_id in sorted(world.localities):
        locality = world.localities[locality_id]
        zone_count = {
            "city": config.city_microzones,
            "town": config.town_microzones,
            "village-cluster": config.village_microzones,
        }[locality.kind]
        raw_shares = [rng.lognormvariate(0, .45) for _ in range(zone_count)]
        total_share = sum(raw_shares)
        zone_ids = []
        for index, raw_share in enumerate(raw_shares):
            zone_id = f"{locality_id}-Z{index + 1:02d}"
            zone_ids.append(zone_id)
            world.microzones[zone_id] = Microzone(
                zone_id, locality_id, role_names[index], raw_share / total_share,
                infrastructure=clamp(locality.infrastructure + rng.uniform(-.18, .18), .05, 1),
                terrain_friction=max(.35, locality.terrain_friction * rng.uniform(.75, 1.25)),
                observability=clamp(locality.observability + rng.uniform(-.2, .2), .05, 1),
                physical_control={"government": 0.0},
            )
            world.physical_neighbors[zone_id] = {}
        world.microzone_ids_by_locality[locality_id] = list(zone_ids)
        # A connected backbone plus shortcut roads; no zone-type control bonuses.
        for index in range(len(zone_ids) - 1):
            _add_physical_edge(world, zone_ids[index], zone_ids[index + 1],
                               rng.uniform(.25, 1.4), clamp(locality.infrastructure * rng.uniform(.75, 1.2), .1, 1))
        if len(zone_ids) > 2:
            _add_physical_edge(world, zone_ids[-1], zone_ids[0], rng.uniform(.4, 1.8),
                               clamp(locality.infrastructure * rng.uniform(.7, 1.15), .1, 1))
        for first_index, first_id in enumerate(zone_ids):
            for second_id in zone_ids[first_index + 2:]:
                if second_id not in world.physical_neighbors[first_id] and rng.random() < config.extra_edge_probability:
                    _add_physical_edge(world, first_id, second_id, rng.uniform(.5, 2.2),
                                       clamp(locality.infrastructure * rng.uniform(.65, 1.2), .1, 1))

        central_zone = min(zone_ids, key=lambda zone_id: sum(
            world.physical_edges[key].travel_time_hours for key in world.physical_neighbors[zone_id].values()))
        if locality.administrative_role in {"administrative_center", "district_headquarters"}:
            population_basis = (
                world.districts[locality.district_id].population
                if locality.administrative_role == "district_headquarters"
                else locality.population
            )
            police_personnel = max(15.0, min(300.0, population_basis * .0015))
            post_id = f"POST-{locality_id}-POLICE"
            world.security_posts[post_id] = SecurityPost(
                post_id, "police", locality_id, central_zone, police_personnel,
                fixed_presence=clamp(police_personnel / 250), available_fraction=.65,
            )

    for formation in world.formations.values():
        locality_zones = zones_in_locality(world, formation.locality_id)
        post_zone = max(locality_zones, key=lambda zone: zone.population_share)
        formation.current_microzone_id = post_zone.microzone_id
        if world.organizations[formation.organization_id].kind.value == "insurgent":
            continue
        post_id = f"POST-{formation.formation_id}"
        world.security_posts[post_id] = SecurityPost(
            post_id, formation.organization_id, formation.locality_id, post_zone.microzone_id,
            formation.personnel, fixed_presence=clamp(formation.personnel / 2_000),
            available_fraction=.4, formation_id=formation.formation_id,
        )
        patrol_id = f"PATROL-{formation.formation_id}"
        world.patrols[patrol_id] = Patrol(
            patrol_id, formation.formation_id, formation.organization_id, formation.locality_id,
            post_zone.microzone_id, [post_zone.microzone_id], 0.0, response_fraction=.3,
        )

    for post_id, post in world.security_posts.items():
        world.security_post_ids_by_locality.setdefault(post.locality_id, []).append(post_id)

    # Initial true control is generated from topology, posts, and response fields.
    for locality_id in world.localities:
        aggregates = recompute_contested_controls(world, locality_id, 0.0)
        for actor, aggregate in aggregates.items():
            world.localities[locality_id].control.setdefault(actor, ControlVector()).physical = aggregate

    for actor_id, organization in world.organizations.items():
        for zone in world.microzones.values():
            # Beliefs are keyed by the concrete observer organization.  A
            # splinter must inherit the insurgent-side prior just like the
            # original organization; identifier equality with the literal
            # ``"insurgent"`` is not a valid type test.
            control_actor = ("insurgent" if organization.kind.value == "insurgent"
                             else "government")
            truth = zone.physical_control.get(control_actor, 0.0)
            noise = rng.uniform(-config.zone_observation_noise, config.zone_observation_noise)
            world.zone_beliefs[(actor_id, zone.microzone_id)] = ActorZoneBelief(
                actor_id, zone.microzone_id, clamp(truth + noise), .35, 0.0
            )


def decay_presence(zone: Microzone, actor: str, time: float, tau_days: float) -> float:
    previous_time = zone.presence_updated_at.get(actor, time)
    elapsed = max(0.0, time - previous_time)
    memory = zone.presence_memory.get(actor, 0.0) * exp(-elapsed / tau_days)
    zone.presence_memory[actor] = memory
    zone.presence_updated_at[actor] = time
    return memory


def record_presence(world: WorldState, microzone_id: str, actor: str,
                    amount: float, time: float) -> float:
    zone = world.microzones[microzone_id]
    current = decay_presence(zone, actor, time, world.config.physical.presence_memory_days)
    zone.presence_memory[actor] = current + max(0.0, amount)
    return zone.presence_memory[actor]


def ensure_zone_belief(world: WorldState, actor_id: str, microzone_id: str,
                       time: float) -> ActorZoneBelief:
    """Return a routing belief for actors created after physical initialization.

    Dynamic organizations (notably foreign expeditionary commands) can acquire
    patrols after ``generate_physical_world`` has populated the initial belief
    table.  Missing entries must not crash routing, and initializing them from
    hidden true control would violate the truth firewall.  Use the same neutral
    uncertain prior scale as initial zone beliefs until observations update it.
    """
    if microzone_id not in world.microzones:
        raise KeyError(f"unknown microzone {microzone_id!r}")
    key = (actor_id, microzone_id)
    belief = world.zone_beliefs.get(key)
    if belief is None:
        belief = ActorZoneBelief(actor_id, microzone_id, .5, .35, float(time))
        world.zone_beliefs[key] = belief
    return belief


def record_presence_exposure(world: WorldState, microzone_id: str, actor: str,
                             target_presence: float, duration_days: float,
                             time: float) -> float:
    """Integrate a constant patrol footprint over an interval ending at time.

    Presence memory obeys exponential decay toward the supplied patrol
    footprint.  The closed-form contribution makes one long dwell and any
    partition of that same dwell produce the same memory at a common
    calendar time.
    """
    if duration_days < 0:
        raise ValueError("presence exposure duration cannot be negative")
    zone = world.microzones[microzone_id]
    tau_days = world.config.physical.presence_memory_days
    current = decay_presence(zone, actor, time, tau_days)
    contribution = (
        max(0.0, float(target_presence)) *
        (1.0 - exp(-max(0.0, float(duration_days)) / tau_days))
    )
    zone.presence_memory[actor] = current + contribution
    return contribution


def advance_patrol_presence_memory(world: WorldState, time: float,
                                   patrol_id: str | None = None) -> float:
    """Integrate every currently deployed patrol through the given time.

    Patrol memory is generated only by the explicitly deployed patrol element,
    not by the full parent formation and not by stationary formation occupancy.
    A per-patrol accounting timestamp prevents callback frequency from creating
    or deleting presence memory.
    """
    total_contribution = 0.0
    patrols = (
        [world.patrols[patrol_id]]
        if patrol_id is not None and patrol_id in world.patrols
        else ([] if patrol_id is not None else
              sorted(world.patrols.values(), key=lambda item: item.patrol_id))
    )
    for patrol in patrols:
        formation = world.formations.get(patrol.formation_id)
        if (formation is None or formation.personnel <= 0 or formation.moving or
                formation.outside_pineland or formation.operational_status != "effective" or
                formation.locality_id != patrol.locality_id or
                patrol.current_microzone_id not in world.microzones):
            continue
        if patrol.available_at > time:
            continue
        start = (patrol.available_at if patrol.presence_accounted_at is None
                 else max(patrol.available_at, patrol.presence_accounted_at))
        duration = max(0.0, float(time) - float(start))
        if duration <= 0:
            patrol.presence_accounted_at = max(float(start), float(time))
            continue
        organization = world.organizations.get(formation.organization_id)
        if organization is None:
            patrol.presence_accounted_at = float(time)
            continue
        actor = ("insurgent" if organization.kind is OrganizationKind.INSURGENT
                 else "government")
        locality = world.localities[patrol.locality_id]
        deployed_strength = (
            formation.effective_strength() * clamp(patrol.response_fraction)
        )
        normalized_strength = (
            deployed_strength / max(250.0, locality.population * .002)
        )
        target = world.config.physical.patrol_memory_gain * normalized_strength
        total_contribution += record_presence_exposure(
            world, patrol.current_microzone_id, actor, target, duration, time
        )
        patrol.presence_accounted_at = float(time)
    return total_contribution


def response_times(world: WorldState, locality_id: str, actor: str, time: float) -> dict[str, float]:
    zone_ids = [zone.microzone_id for zone in zones_in_locality(world, locality_id)]
    distances = {zone_id: inf for zone_id in zone_ids}
    queue: list[tuple[float, str]] = []
    for post in posts_in_locality(world, locality_id):
        organization = world.organizations[post.organization_id]
        available_fraction = post.available_fraction
        if post.formation_id:
            formation = world.formations[post.formation_id]
            if (formation.moving or formation.outside_pineland or
                    formation.operational_status != "effective" or
                    formation.locality_id != post.locality_id):
                available_fraction = 0.0
            else:
                available_fraction *= formation.availability * formation.effective_readiness()
        if (_actor_matches_organization(world, post.organization_id, actor) and
                available_fraction > 0):
            mobilization_delay = (1 - available_fraction) * world.config.physical.response_decay_hours
            if mobilization_delay < distances[post.microzone_id]:
                distances[post.microzone_id] = mobilization_delay
                heapq.heappush(queue, (mobilization_delay, post.microzone_id))
    for patrol in world.patrols.values():
        if patrol.locality_id != locality_id:
            continue
        formation = world.formations[patrol.formation_id]
        effective_fraction = (
            patrol.response_fraction * formation.availability * formation.effective_readiness()
            if formation.operational_status == "effective" and not formation.outside_pineland
            else 0.0
        )
        if (patrol.locality_id == locality_id and
                _actor_matches_organization(world, patrol.organization_id, actor) and
                patrol.available_at <= time and not formation.moving and effective_fraction > 0):
            dispatch_delay = (1 - effective_fraction) * world.config.physical.response_decay_hours
            if dispatch_delay < distances[patrol.current_microzone_id]:
                distances[patrol.current_microzone_id] = dispatch_delay
                heapq.heappush(queue, (dispatch_delay, patrol.current_microzone_id))
    # A formation remains a physical response source even when it has no
    # patrol object (the normal case for insurgent formations).  Its explicit
    # current microzone is the source location; this keeps both sides
    # symmetric and removes the former patrol-only presence assumption.
    for formation in world.formations.values():
        if (formation.locality_id != locality_id or
                not _actor_matches_organization(world, formation.organization_id, actor) or
                formation.moving or formation.outside_pineland or
                formation.operational_status != "effective" or formation.personnel <= 0 or
                formation.current_microzone_id not in distances):
            continue
        effective_fraction = .30 * formation.availability * formation.effective_readiness()
        if effective_fraction > 0:
            dispatch_delay = (1 - effective_fraction) * world.config.physical.response_decay_hours
            if dispatch_delay < distances[formation.current_microzone_id]:
                distances[formation.current_microzone_id] = dispatch_delay
                heapq.heappush(queue, (dispatch_delay, formation.current_microzone_id))
    while queue:
        distance, zone_id = heapq.heappop(queue)
        if distance != distances[zone_id]:
            continue
        for neighbor_id, edge_key in world.physical_neighbors[zone_id].items():
            edge = world.physical_edges[edge_key]
            candidate = distance + edge.travel_time_hours * (1 + edge.disruption)
            if candidate < distances[neighbor_id]:
                distances[neighbor_id] = candidate
                heapq.heappush(queue, (candidate, neighbor_id))
    return distances


def recompute_microzone_control(world: WorldState, locality_id: str,
                                actor: str, time: float,
                                apply_contestation: bool = True) -> float:
    config = world.config.physical
    # Direct callers receive the same completed patrol-memory accounting as a
    # scheduled physical refresh. Repeated calls at the same time are idempotent
    # because each patrol tracks its own accounting boundary.
    advance_patrol_presence_memory(world, time)
    # Public test/policy hooks may relocate a formation by locality only.  Keep
    # the explicit microzone state coherent at the next physical refresh.
    local_zones = zones_in_locality(world, locality_id)
    if local_zones:
        default_zone = max(local_zones, key=lambda zone: zone.population_share).microzone_id
        for formation in world.formations.values():
            if formation.locality_id == locality_id and (
                    formation.current_microzone_id not in world.microzones or
                    world.microzones[formation.current_microzone_id].locality_id != locality_id):
                formation.current_microzone_id = default_zone
    effective_actor = (
        _INSURGENT_SIDE_ACTOR
        if (
            actor == "insurgent"
            and not (
                "insurgent" in world.organizations
                and world.organizations["insurgent"].status == "active"
            )
        )
        else actor
    )
    times = response_times(world, locality_id, effective_actor, time)
    posts_by_zone: dict[str, float] = {}
    for post in posts_in_locality(world, locality_id):
        if _actor_matches_organization(world, post.organization_id, effective_actor):
            effective_presence = post.fixed_presence
            if post.formation_id:
                formation = world.formations[post.formation_id]
                if (formation.moving or formation.outside_pineland or
                        formation.operational_status != "effective" or
                        formation.locality_id != post.locality_id):
                    effective_presence = 0.0
                else:
                    effective_presence *= formation.availability * formation.effective_readiness()
            posts_by_zone[post.microzone_id] = posts_by_zone.get(post.microzone_id, 0.0) + effective_presence
    formations_by_zone: dict[str, float] = {}
    locality = world.localities[locality_id]
    for formation in world.formations.values():
        if (not _actor_matches_organization(world, formation.organization_id, effective_actor) or
                formation.locality_id != locality_id or
                formation.moving or formation.outside_pineland or
                formation.operational_status != "effective" or formation.personnel <= 0 or
                formation.current_microzone_id not in world.microzones):
            continue
        strength = formation.effective_strength()
        formations_by_zone[formation.current_microzone_id] = (
            formations_by_zone.get(formation.current_microzone_id, 0.0) +
            config.formation_presence_gain * strength / max(250.0, locality.population * .002))
    aggregate = 0.0
    for zone in zones_in_locality(world, locality_id):
        memory_actor = effective_actor
        if effective_actor == _INSURGENT_SIDE_ACTOR:
            memory = sum(
                decay_presence(
                    zone, organization_id, time, config.presence_memory_days
                )
                for organization_id in active_insurgent_ids(world)
            )
        else:
            memory = decay_presence(zone, memory_actor, time, config.presence_memory_days)
        presence = 1 - exp(-(memory +
                             config.fixed_post_presence_gain * posts_by_zone.get(zone.microzone_id, 0.0) +
                             formations_by_zone.get(zone.microzone_id, 0.0)))
        response = 0.0 if times[zone.microzone_id] == inf else exp(-times[zone.microzone_id] / config.response_decay_hours)
        zone.physical_control[effective_actor] = clamp(.55 * presence + .45 * response)
        aggregate += zone.population_share * zone.physical_control[effective_actor]
    aggregate = clamp(aggregate)
    if apply_contestation and actor in {"government", "insurgent"}:
        opponent = _INSURGENT_SIDE_ACTOR if actor == "government" else "government"
        if any(organization.kind.value == "insurgent" and organization.status == "active"
               for organization in world.organizations.values()):
            # Recompute the opponent's raw reach without recursively applying
            # contestation, then expose the contested value through this
            # backwards-compatible public helper.
            if opponent == _INSURGENT_SIDE_ACTOR:
                recompute_microzone_control(
                    world, locality_id, _INSURGENT_SIDE_ACTOR, time,
                    apply_contestation=False,
                )
                opponent_key = _INSURGENT_SIDE_ACTOR
            else:
                recompute_microzone_control(
                    world, locality_id, opponent, time,
                    apply_contestation=False,
                )
                opponent_key = opponent
            adjusted = 0.0
            for zone in zones_in_locality(world, locality_id):
                value = zone.physical_control.get(effective_actor, 0.0)
                opponent_value = zone.physical_control.get(opponent_key, 0.0)
                zone.physical_control[effective_actor] = clamp(
                    value * (.65 + .35 * (1 - opponent_value))
                )
                adjusted += (
                    zone.population_share
                    * zone.physical_control[effective_actor]
                )
            aggregate = clamp(adjusted)
    return aggregate


def recompute_contested_controls(world: WorldState, locality_id: str, time: float,
                                 competition_strength: float = .35) -> dict[str, float]:
    """Recompute side-level and franchise-level physical reach.

    Raw reach is generated independently from posts, presence and response;
    contestation is a separate relational step so the order in which actors
    are iterated cannot bias the result.  Concrete insurgent organizations are
    contested by government reach but not by one another here: inter-franchise
    hostility is a separate theory layer and must not be smuggled into physical
    aggregation merely because two organizations coexist.
    """
    actors = ["government"]
    active_insurgents = list(active_insurgent_ids(world))
    actors.extend(active_insurgents)
    raw_aggregate: dict[str, float] = {}
    raw_zones: dict[str, dict[str, float]] = {}
    for actor in actors:
        raw_aggregate[actor] = recompute_microzone_control(
            world, locality_id, actor, time, apply_contestation=False)
        raw_zones[actor] = {
            zone.microzone_id: zone.physical_control.get(actor, 0.0)
            for zone in zones_in_locality(world, locality_id)
        }
    if active_insurgents:
        recompute_microzone_control(
            world, locality_id, _INSURGENT_SIDE_ACTOR, time,
            apply_contestation=False,
        )
        raw_zones[_INSURGENT_SIDE_ACTOR] = {
            zone.microzone_id: zone.physical_control.get(
                _INSURGENT_SIDE_ACTOR, 0.0
            )
            for zone in zones_in_locality(world, locality_id)
        }
    adjusted: dict[str, float] = {}
    zones = zones_in_locality(world, locality_id)
    for actor in actors:
        # Government is contested by the aggregate insurgent side.  Aggregate
        # and concrete insurgent actors are each contested by government.  A
        # future rivalry/strife layer may add faction-on-faction contestation,
        # but until then coexistence is not synonymous with hostility.
        opponent = (
            _INSURGENT_SIDE_ACTOR
            if actor == "government" else "government"
        )
        aggregate = 0.0
        for zone in zones:
            value = raw_zones[actor][zone.microzone_id]
            opponent_value = raw_zones.get(opponent, {}).get(zone.microzone_id, 0.0)
            zone.physical_control[actor] = clamp(value * (1 - competition_strength * opponent_value))
            aggregate += zone.population_share * zone.physical_control[actor]
        adjusted[actor] = clamp(aggregate)
    # Preserve the historical aggregate key only when no active concrete
    # organization owns the literal identifier "insurgent".
    if active_insurgents and "insurgent" not in active_insurgents:
        aggregate = 0.0
        for zone in zones:
            value = raw_zones[_INSURGENT_SIDE_ACTOR][zone.microzone_id]
            government_value = raw_zones["government"][zone.microzone_id]
            contested = clamp(
                value * (1 - competition_strength * government_value)
            )
            zone.physical_control["insurgent"] = contested
            aggregate += zone.population_share * contested
        adjusted["insurgent"] = clamp(aggregate)
    return adjusted


def physical_diagnostics(world: WorldState) -> dict:
    locality_ranges = {}
    for locality_id in world.localities:
        zones = zones_in_locality(world, locality_id)
        values = [zone.physical_control.get("government", 0.0) for zone in zones]
        insurgent_values = [zone.physical_control.get("insurgent", 0.0) for zone in zones]
        times = response_times(world, locality_id, "government", world.time)
        insurgent_times = response_times(world, locality_id, "insurgent", world.time)
        locality_ranges[locality_id] = {
            "minimum": min(values), "mean": mean(values), "maximum": max(values),
            "range": max(values) - min(values),
            "zones": {
                zone.microzone_id: {
                    "population_share": zone.population_share,
                    "physical_control": zone.physical_control.get("government", 0.0),
                    "presence_memory": zone.presence_memory.get("government", 0.0),
                    "insurgent_presence_memory": zone.presence_memory.get("insurgent", 0.0),
                    "insurgent_physical_control": zone.physical_control.get("insurgent", 0.0),
                    "response_time_hours": None if times[zone.microzone_id] == inf else times[zone.microzone_id],
                }
                for zone in zones
            },
            "insurgent_mean": mean(insurgent_values),
            "insurgent_response_time_hours": {
                zone.microzone_id: None if insurgent_times[zone.microzone_id] == inf else insurgent_times[zone.microzone_id]
                for zone in zones
            },
        }
    return {
        "microzones": len(world.microzones),
        "edges": len(world.physical_edges),
        "posts": len(world.security_posts),
        "patrols": len(world.patrols),
        "localities": locality_ranges,
    }
