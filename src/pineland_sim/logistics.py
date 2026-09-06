from __future__ import annotations

from dataclasses import asdict
import heapq
from math import exp, inf, log
from typing import Any

from .entities import (
    CommandEdge,
    ControlVector,
    FormationMovementOrder,
    OrganizationKind,
    ResourceFlow,
    SupplyShipment,
    SupplySource,
    clamp,
)
from .world import WorldState, seeded_rng


def command_edge_key(first_id: str, second_id: str) -> tuple[str, str]:
    if first_id == second_id:
        raise ValueError("command self edges are not permitted")
    return tuple(sorted((first_id, second_id)))


def _add_command_edge(world: WorldState, first_id: str, second_id: str,
                      organization_id: str, reliability: float, latency_hours: float) -> None:
    key = command_edge_key(first_id, second_id)
    world.command_edges[key] = CommandEdge(
        key[0], key[1], organization_id, clamp(reliability), max(0.0, latency_hours)
    )


def locality_leg(world: WorldState, first_id: str, second_id: str,
                 mobility: float) -> tuple[float, float]:
    """Return synthetic distance-km and travel-hours for an adjacent locality leg."""
    terrain_cost = world.adjacency[first_id][second_id]
    infrastructure = (world.localities[first_id].infrastructure +
                      world.localities[second_id].infrastructure) / 2
    distance_km = 18.0 + 22.0 * terrain_cost
    speed_kmh = 42.0 * max(.15, mobility) * max(.2, infrastructure) / max(.5, terrain_cost)
    return distance_km, distance_km / speed_kmh


def shortest_locality_path(world: WorldState, origin_id: str, destination_id: str,
                           mobility: float) -> tuple[list[str], float, float]:
    if origin_id == destination_id:
        return [origin_id], 0.0, 0.0
    cache_key = (origin_id, destination_id, float(mobility))
    cached = world.locality_path_cache.get(cache_key)
    if cached is not None:
        route, distance_km, travel_hours = cached
        return list(route), distance_km, travel_hours
    distances = {origin_id: 0.0}
    previous: dict[str, str] = {}
    queue = [(0.0, origin_id)]
    while queue:
        travel_hours, locality_id = heapq.heappop(queue)
        if travel_hours != distances[locality_id]:
            continue
        if locality_id == destination_id:
            break
        for neighbor_id in world.adjacency[locality_id]:
            _, leg_hours = locality_leg(world, locality_id, neighbor_id, mobility)
            candidate = travel_hours + leg_hours
            if candidate < distances.get(neighbor_id, inf):
                distances[neighbor_id] = candidate
                previous[neighbor_id] = locality_id
                heapq.heappush(queue, (candidate, neighbor_id))
    if destination_id not in distances:
        raise ValueError(f"no locality path from {origin_id} to {destination_id}")
    route = [destination_id]
    while route[-1] != origin_id:
        route.append(previous[route[-1]])
    route.reverse()
    distance_km = sum(locality_leg(world, first, second, mobility)[0]
                      for first, second in zip(route, route[1:]))
    result = (tuple(route), distance_km, distances[destination_id])
    world.locality_path_cache[cache_key] = result
    return list(result[0]), result[1], result[2]


def shortest_locality_travel_times(world: WorldState, origin_id: str,
                                   mobility: float) -> dict[str, float]:
    """Single-source travel times using the exact shortest-path edge costs.

    Reallocation evaluates every possible destination from the same origin.
    Running the identical Dijkstra search once is numerically equivalent to
    rerunning it separately for each destination and avoids an O(V) repetition
    of the graph traversal.
    """
    cache_key = (origin_id, float(mobility))
    cached = world.locality_travel_time_cache.get(cache_key)
    if cached is not None:
        return cached
    distances = {origin_id: 0.0}
    queue = [(0.0, origin_id)]
    while queue:
        travel_hours, locality_id = heapq.heappop(queue)
        if travel_hours != distances[locality_id]:
            continue
        for neighbor_id in world.adjacency[locality_id]:
            _, leg_hours = locality_leg(world, locality_id, neighbor_id, mobility)
            candidate = travel_hours + leg_hours
            if candidate < distances.get(neighbor_id, inf):
                distances[neighbor_id] = candidate
                heapq.heappush(queue, (candidate, neighbor_id))
    world.locality_travel_time_cache[cache_key] = distances
    return distances


def _shortest_locality_route_metrics(
    world: WorldState, origin_id: str, mobility: float
) -> dict[str, tuple[list[str], float, float]]:
    """Return all fastest routes from one origin with distance and travel time.

    Reallocation needs route identity for believed corridor risk and route
    distance for ex-ante movement-supply feasibility.  Computing the complete
    shortest-path tree once preserves the single-source complexity of the
    previous travel-time-only selector rather than rerunning Dijkstra for every
    candidate.
    """
    travel_times = {origin_id: 0.0}
    distances_km = {origin_id: 0.0}
    previous: dict[str, str] = {}
    queue = [(0.0, origin_id)]
    while queue:
        travel_hours, locality_id = heapq.heappop(queue)
        if travel_hours != travel_times[locality_id]:
            continue
        for neighbor_id in world.adjacency[locality_id]:
            leg_distance, leg_hours = locality_leg(
                world, locality_id, neighbor_id, mobility
            )
            candidate = travel_hours + leg_hours
            if candidate < travel_times.get(neighbor_id, inf):
                travel_times[neighbor_id] = candidate
                distances_km[neighbor_id] = distances_km[locality_id] + leg_distance
                previous[neighbor_id] = locality_id
                heapq.heappush(queue, (candidate, neighbor_id))

    routes: dict[str, tuple[list[str], float, float]] = {}
    for destination_id in travel_times:
        if destination_id == origin_id:
            route = [origin_id]
        else:
            route = [destination_id]
            while route[-1] != origin_id:
                route.append(previous[route[-1]])
            route.reverse()
        routes[destination_id] = (
            route, distances_km[destination_id], travel_times[destination_id]
        )
        if destination_id != origin_id:
            world.locality_path_cache[
                (origin_id, destination_id, float(mobility))
            ] = (tuple(route), distances_km[destination_id], travel_times[destination_id])
    world.locality_travel_time_cache[(origin_id, float(mobility))] = dict(travel_times)
    return routes


def reallocation_decision_probability(
    daily_probability: float, interval_days: float
) -> float:
    """Convert a one-day decision probability to an arbitrary scheduler interval.

    The composition law makes command cadence a numerical schedule rather than
    a hidden behavioral parameter.
    """
    probability = clamp(daily_probability)
    interval_days = max(0.0, float(interval_days))
    if probability <= 0.0 or interval_days <= 0.0:
        return 0.0
    if probability >= 1.0:
        return 1.0
    return clamp(1.0 - exp(interval_days * log(1.0 - probability)))


def command_metrics(world: WorldState, organization_id: str,
                    target_node_id: str) -> tuple[float, float]:
    """Return maximum-reliability path and its cumulative latency from organization HQ."""
    _, reliability, latency = command_path(world, organization_id, target_node_id,
                                           f"CMD:{organization_id}")
    return reliability, latency


def command_path(world: WorldState, organization_id: str, source_node_id: str,
                 destination_node_id: str) -> tuple[list[str], float, float]:
    """Return a high-reliability command route and its additive latency.

    Command edges are stored as undirected physical communication links, but
    callers provide a directed information flow.  Reliability compounds across
    the selected path and latency adds across hops, so a local node can possess
    an observation before the headquarters does.
    """
    if source_node_id == destination_node_id:
        return [source_node_id], 1.0, 0.0
    adjacency: dict[str, list[tuple[str, CommandEdge]]] = {}
    for edge in world.command_edges.values():
        if edge.organization_id != organization_id:
            continue
        adjacency.setdefault(edge.node_a_id, []).append((edge.node_b_id, edge))
        adjacency.setdefault(edge.node_b_id, []).append((edge.node_a_id, edge))
    # Minimize negative log reliability, with latency as deterministic tie-breaker.
    scores = {source_node_id: (0.0, 0.0)}
    previous: dict[str, str] = {}
    queue = [(0.0, 0.0, source_node_id)]
    while queue:
        risk, latency, node = heapq.heappop(queue)
        if (risk, latency) != scores[node]:
            continue
        if node == destination_node_id:
            route = [node]
            while route[-1] != source_node_id:
                route.append(previous[route[-1]])
            route.reverse()
            return route, exp(-risk), latency
        for neighbor, edge in adjacency.get(node, ()):
            candidate = (risk - log(max(1e-12, edge.reliability)), latency + edge.latency_hours)
            if candidate < scores.get(neighbor, (inf, inf)):
                scores[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (*candidate, neighbor))
    return [], 0.0, inf


def _record_flow(world: WorldState, time: float, flow_type: str, organization_id: str,
                 locality_id: str, quantity: float, source_id: str | None = None,
                 formation_id: str | None = None) -> None:
    world.resource_flows.append(ResourceFlow(
        f"RF{len(world.resource_flows) + 1:010d}", time, flow_type, organization_id,
        locality_id, quantity, source_id, formation_id,
    ))


def generate_logistics_world(world: WorldState) -> None:
    config = world.config.logistics
    rng = seeded_rng(world.config, "logistics-world-generation")
    world.command_edges.clear()
    world.supply_sources.clear()
    world.supply_shipments.clear()
    world.active_shipment_ids.clear()
    world.in_transit_supply_total = 0.0
    world.movement_orders.clear()
    world.active_movement_order_ids.clear()
    world.resource_flows.clear()
    world.control_cost_consumed = {locality_id: 0.0 for locality_id in world.localities}
    world.cumulative_supply_produced = 0.0
    world.cumulative_supply_consumed = 0.0
    world.cumulative_supply_lost = 0.0

    formations_by_org: dict[str, list] = {}
    for formation in world.formations.values():
        formation.home_locality_id = formation.locality_id
        formation.supply_capacity = formation.personnel * config.formation_supply_days
        formation.supply_stock = formation.supply_capacity * config.initial_supply_fraction
        formation.sustainment = formation.supply_fraction()
        formation.availability = .85
        formation.moving = False
        formations_by_org.setdefault(formation.organization_id, []).append(formation)

    for organization_id, formations in formations_by_org.items():
        organization = world.organizations[organization_id]
        if organization.kind in {OrganizationKind.MILITARY, OrganizationKind.POLICE}:
            source_localities = []
            for district in world.districts.values():
                administrative = [
                    locality_id for locality_id in district.locality_ids
                    if world.localities[locality_id].administrative_role in
                    {"district_headquarters", "administrative_center"}
                ]
                source_localities.append(
                    sorted(administrative)[0] if administrative else district.locality_ids[0]
                )
        else:
            source_localities = sorted({formation.home_locality_id for formation in formations})
        organization_daily_requirement = (sum(f.personnel for f in formations) *
                                          config.presence_consumption_per_person_day *
                                          config.organization_sustainment_coverage)
        catchment_weights = [world.districts[world.localities[x].district_id].population
                             for x in source_localities]
        total_weight = sum(catchment_weights)
        for index, locality_id in enumerate(source_localities):
            locality = world.localities[locality_id]
            # A source located at the district/container hub supports the
            # whole administrative container, not merely the population of
            # the hub locality.  Using ``locality.population`` here silently
            # under-scales supply whenever an empirical adapter represents
            # historical districts as localities nested inside larger
            # containers (as Nepal does).
            catchment = world.districts[locality.district_id]
            if config.source_capacity_model == "organization_manpower":
                production = organization_daily_requirement * catchment_weights[index] / max(1.0, total_weight)
                capacity = max(5_000.0, production / config.source_daily_production_fraction)
            else:
                capacity = max(5_000.0, catchment.population * config.source_capacity_per_resident)
            source_id = f"SUP-{organization_id}-{index + 1:02d}"
            world.supply_sources[source_id] = SupplySource(
                source_id, organization_id, locality_id, capacity * .7, capacity,
                capacity * config.source_daily_production_fraction,
            )
        for formation in formations:
            reliability = clamp(.35 + .35 * organization.institutional_quality + .3 * formation.command)
            district = world.districts[world.localities[formation.locality_id].district_id]
            latency = 1.0 + 6.0 * (1 - district.connectivity) + rng.uniform(0, 1.5)
            _add_command_edge(world, f"CMD:{organization_id}", formation.formation_id,
                              organization_id, reliability, latency)
            formation.command = reliability

    world.initial_supply_stock = (
        sum(source.stock for source in world.supply_sources.values()) +
        sum(formation.supply_stock for formation in world.formations.values())
    )


def consume_formation_supply(world: WorldState, formation_id: str, amount: float,
                             flow_type: str, locality_id: str, time: float) -> tuple[float, float]:
    formation = world.formations[formation_id]
    demanded = max(0.0, amount)
    consumed = min(formation.supply_stock, demanded)
    formation.supply_stock -= consumed
    formation.sustainment = formation.supply_fraction()
    world.cumulative_supply_consumed += consumed
    if world.organizations[formation.organization_id].kind is not OrganizationKind.INSURGENT:
        world.control_cost_consumed[locality_id] = world.control_cost_consumed.get(locality_id, 0.0) + consumed
    if consumed:
        _record_flow(world, time, flow_type, formation.organization_id, locality_id,
                     consumed, formation_id=formation_id)
    return consumed, demanded - consumed


def create_movement_order(world: WorldState, formation_id: str, destination_id: str,
                          time: float, rng=None, *, purpose: str = "reallocation"
                          ) -> FormationMovementOrder:
    rng = rng or seeded_rng(world.config, f"movement-order:{formation_id}:{len(world.movement_orders)}")
    formation = world.formations[formation_id]
    route, distance_km, travel_hours = shortest_locality_path(
        world, formation.locality_id, destination_id, formation.mobility
    )
    reliability, latency = command_metrics(world, formation.organization_id, formation_id)
    moving_personnel = formation.personnel * formation.availability
    cost = moving_personnel * distance_km * world.config.logistics.movement_consumption_per_person_km
    status = "pending" if rng.random() <= reliability else "failed_command"
    order = FormationMovementOrder(
        f"MO{len(world.movement_orders) + 1:08d}", formation_id, formation.organization_id,
        formation.locality_id, destination_id, route, time, time + latency / 24,
        travel_hours, distance_km, cost, reliability, latency, status,
        purpose=purpose,
    )
    world.movement_orders[order.order_id] = order
    if order.status in {"pending", "moving"}:
        world.active_movement_order_ids[order.order_id] = None
    return order


def _active_movement_orders(world: WorldState):
    """Visit live orders in archive insertion order, without scanning history."""
    for order_id in list(world.active_movement_order_ids):
        order = world.movement_orders.get(order_id)
        if order is None or order.status not in {"pending", "moving"}:
            world.active_movement_order_ids.pop(order_id, None)
            continue
        yield order


def _local_armed_footholds(world: WorldState, organization_id: str) -> dict[str, float]:
    """Return locality-scale clandestine foothold strength from represented members.

    This is intentionally independent of current formation occupancy.  A force
    can leave a locality while recruited/embedded members remain, so geographic
    reproduction is not forced to restart from zero after every movement.
    """
    represented: dict[str, float] = {}
    organization = world.organizations[organization_id]
    for person_id in organization.member_ids:
        person = world.persons.get(person_id)
        if (person is None or person.organization_id != organization_id or
                person.armed_fraction <= 0):
            continue
        represented[person.residence_locality_id] = (
            represented.get(person.residence_locality_id, 0.0) +
            person.weight * person.armed_fraction
        )
    scale = max(
        1e-9, world.config.organization_ecology.minimum_proto_represented_population
    )
    return {locality_id: clamp(quantity / scale)
            for locality_id, quantity in represented.items()}


def _sanctuary_access(world: WorldState, organization_id: str,
                      locality_id: str, *, mobility: float | None = None) -> float:
    """Map external sanctuary onto a continuous sponsor-border access gradient.

    Sanctuary is not a magical organization-wide bonus and is not a binary
    property of the exact border locality.  Access declines with actor-known
    travel cost from a sponsor-linked border and is attenuated by permeability,
    monitoring, infrastructure, and terrain.  No realized territorial control
    enters this calculation.
    """
    organization = world.organizations[organization_id]
    if organization.external_sanctuary <= 0 or not organization.sponsor_dependence:
        return 0.0
    if mobility is None:
        mobilities = [
            formation.mobility for formation in world.formations.values()
            if formation.organization_id == organization_id
        ]
        mobility = sum(mobilities) / len(mobilities) if mobilities else .5
    mobility = max(.05, mobility)
    best = 0.0
    for border in world.border_segments.values():
        dependence = organization.sponsor_dependence.get(border.foreign_state_id, 0.0)
        if dependence <= 0:
            continue
        permeability = clamp(
            0.35 * border.social_permeability +
            0.30 * border.kinship_overlap +
            0.20 * border.language_overlap +
            0.15 * border.legal_permeability
        )
        border_quality = clamp(
            permeability * max(.1, border.infrastructure) *
            (1.0 - clamp(border.state_monitoring)) /
            max(.5, border.terrain_friction)
        )
        travel_hours = shortest_locality_travel_times(
            world, border.locality_id, mobility
        ).get(locality_id, inf)
        if travel_hours == inf:
            continue
        distance_access = exp(
            -world.config.logistics.reallocation_travel_time_weight * travel_hours
        )
        best = max(best, dependence * border_quality * distance_access)
    return clamp(organization.external_sanctuary * best)


def _control_belief_value(
    world: WorldState, observer_id: str, target_actor_id: str, locality_id: str,
    *, legacy_fallback: bool = False,
) -> tuple[float, float, float]:
    """Return raw estimate, confidence-shrunk estimate, and confidence.

    A low-confidence extreme estimate must not remain an extreme strategic
    signal.  Shrinking toward the explicit 0.5 prior separates exploitation of
    the posterior mean from the uncertainty bonus used for exploration.
    """
    # The legacy own-side belief remains the documented Phase-3 command view
    # and is synchronized from the richer target-specific belief store by the
    # information subsystem.  Prefer it for own-side reads so older callers and
    # saved states retain identical belief semantics; opponent reads use the
    # target-specific store.
    belief = (world.beliefs.get((observer_id, locality_id))
              if legacy_fallback else None)
    if belief is None:
        belief = world.control_beliefs.get((observer_id, target_actor_id, locality_id))
    raw = clamp(belief.control_estimate.physical if belief else .5)
    confidence = clamp(belief.confidence if belief else 0.0)
    adjusted = clamp(.5 + confidence * (raw - .5))
    return raw, adjusted, confidence


def _reallocation_side_targets(world: WorldState, organization_id: str) -> tuple[str, str]:
    organization = world.organizations[organization_id]
    if organization.kind is OrganizationKind.INSURGENT:
        return "insurgent", "government"
    return "government", "insurgent"


def _believed_route_risk(
    world: WorldState, organization_id: str, opponent_target: str,
    route: list[str] | tuple[str, ...],
) -> float:
    """Mean believed opponent control on intermediate route localities."""
    intermediate = list(route[1:-1])
    if not intermediate:
        return 0.0
    return sum(
        _control_belief_value(
            world, organization_id, opponent_target, locality_id
        )[1]
        for locality_id in intermediate
    ) / len(intermediate)


def reallocation_destination_score(
    world: WorldState,
    formation,
    locality_id: str,
    *,
    travel_hours: float | None = None,
    maximum_population: float | None = None,
    footholds: dict[str, float] | None = None,
    route: list[str] | tuple[str, ...] | None = None,
) -> dict[str, float]:
    """Return actor-belief-based destination components and log utility.

    The current locality is a legitimate candidate, giving every formation an
    explicit stay option.  State-aligned forces respond to insecure territorial
    coverage, including threatened strongpoints rather than only low-own-control
    gaps.  Insurgents use the existing frontier/foothold/stronghold/exploration
    portfolio, augmented by spatial sponsor-sanctuary access.  Both sides use
    confidence-shrunk beliefs and believed intermediate-route risk; model truth
    is never consulted.
    """
    if travel_hours is None or route is None:
        if locality_id == formation.locality_id:
            inferred_route, inferred_hours = [formation.locality_id], 0.0
        else:
            inferred_route, _, inferred_hours = shortest_locality_path(
                world, formation.locality_id, locality_id, formation.mobility
            )
        if travel_hours is None:
            travel_hours = inferred_hours
        if route is None:
            route = inferred_route
    if maximum_population is None:
        maximum_population = max(locality.population for locality in world.localities.values())
    organization = world.organizations[formation.organization_id]
    own_target, opponent_target = _reallocation_side_targets(
        world, formation.organization_id
    )
    own_raw, own_control, own_confidence = _control_belief_value(
        world, formation.organization_id, own_target, locality_id,
        legacy_fallback=True,
    )
    opponent_raw, opponent_control, opponent_confidence = _control_belief_value(
        world, formation.organization_id, opponent_target, locality_id
    )
    importance = world.localities[locality_id].population / max(1.0, maximum_population)
    uncertainty = 1.0 - min(own_confidence, opponent_confidence)
    route_risk = _believed_route_risk(
        world, formation.organization_id, opponent_target, route
    )
    risk_tolerance = clamp(organization.phenotype.get("risk_tolerance", .5))
    route_risk_penalty = (1.0 - risk_tolerance) * route_risk
    cfg = world.config.logistics

    if organization.kind is OrganizationKind.INSURGENT:
        footholds = footholds if footholds is not None else _local_armed_footholds(
            world, formation.organization_id
        )
        foothold = footholds.get(locality_id, 0.0)
        # Frontier opportunity is high where own establishment is weak and
        # perceived government reach is weak.  The floor keeps contested
        # destinations selectable rather than imposing a hard gate.
        frontier = (1.0 - own_control) * (0.35 + 0.65 * (1.0 - opponent_control))
        base_strategic = (
            cfg.insurgent_frontier_weight * frontier +
            cfg.insurgent_foothold_weight * foothold +
            cfg.insurgent_stronghold_weight * own_control +
            cfg.reallocation_exploration_weight * uncertainty
        )
        sanctuary = _sanctuary_access(
            world, formation.organization_id, locality_id,
            mobility=formation.mobility,
        )
        # Sanctuary is an additional refuge/access channel, not a fifth weight
        # that would require retuning the existing insurgent portfolio.
        strategic = clamp(base_strategic + (1.0 - base_strategic) * sanctuary)
        components = {
            "frontier": frontier,
            "foothold": foothold,
            "stronghold": own_control,
            "sanctuary": sanctuary,
            "uncertainty": uncertainty,
            "government_control": opponent_control,
            "opponent_control": opponent_control,
            "opponent_control_raw": opponent_raw,
            "own_control": own_control,
            "own_control_raw": own_raw,
        }
    else:
        gap = 1.0 - own_control
        threatened_control = own_control * opponent_control
        # One minus secure, uncontested own control.  This preserves gap filling
        # while also valuing defense of a strongpoint believed to be contested.
        territorial_need = 1.0 - own_control * (1.0 - opponent_control)
        strategic = clamp(
            (1.0 - cfg.reallocation_exploration_weight) * territorial_need +
            cfg.reallocation_exploration_weight * uncertainty
        )
        components = {
            "gap": gap,
            "threatened_control": threatened_control,
            "territorial_need": territorial_need,
            "uncertainty": uncertainty,
            "insurgent_control": opponent_control,
            "opponent_control": opponent_control,
            "opponent_control_raw": opponent_raw,
            "own_control": own_control,
            "own_control_raw": own_raw,
        }

    utility = (
        cfg.reallocation_strategic_weight * strategic +
        cfg.reallocation_importance_weight * importance -
        cfg.reallocation_travel_time_weight * travel_hours -
        route_risk_penalty
    )
    components.update({
        "strategic": strategic,
        "importance": importance,
        "travel_hours": travel_hours,
        "route_risk": route_risk,
        "route_risk_penalty": route_risk_penalty,
        "utility": utility,
    })
    return components


def choose_reallocation_orders(
    world: WorldState, time: float, rng, *, interval_days: float = 1.0
) -> list[FormationMovementOrder]:
    orders = []
    maximum_population = max(
        locality.population for locality in world.localities.values()
    )
    foothold_cache: dict[str, dict[str, float]] = {}
    decision_probability = reallocation_decision_probability(
        world.config.logistics.reallocation_rate, interval_days
    )
    busy_formations = {order.formation_id for order in _active_movement_orders(world)}
    for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
        if (formation.moving or formation.outside_pineland or formation.personnel <= 0 or
                formation.operational_status != "effective" or
                formation.deployable_personnel() <= 0 or
                formation.formation_id in busy_formations):
            continue
        if rng.random() >= decision_probability:
            continue
        route_metrics = _shortest_locality_route_metrics(
            world, formation.locality_id, formation.mobility
        )
        candidates: list[str] = []
        utilities = []
        if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT:
            foothold_cache.setdefault(
                formation.organization_id,
                _local_armed_footholds(world, formation.organization_id),
            )
        moving_personnel = formation.personnel * formation.availability
        for locality_id in sorted(world.localities):
            route, distance_km, travel_hours = route_metrics[locality_id]
            movement_cost = (
                moving_personnel * distance_km *
                world.config.logistics.movement_consumption_per_person_km
            )
            # A commander knows its own stock and should not deliberately issue
            # an order that is already impossible at issue time.  Execution
            # still revalidates stock because another demand can intervene
            # during command latency.
            if (locality_id != formation.locality_id and
                    movement_cost > formation.supply_stock + 1e-12):
                continue
            components = reallocation_destination_score(
                world, formation, locality_id,
                travel_hours=travel_hours,
                maximum_population=maximum_population,
                footholds=foothold_cache.get(formation.organization_id),
                route=route,
            )
            candidates.append(locality_id)
            utilities.append(exp(max(-8, min(8, components["utility"]))))
        destination = rng.choices(candidates, weights=utilities, k=1)[0]
        if destination == formation.locality_id:
            continue
        orders.append(create_movement_order(
            world, formation.formation_id, destination, time, rng, purpose="reallocation"
        ))
    return orders


def choose_withdrawal_order(world: WorldState, formation_id: str, time: float, rng
                            ) -> FormationMovementOrder | None:
    """Create a belief-driven withdrawal toward refuge after disengagement.

    Withdrawal is distinct from ordinary force reallocation: it prioritizes
    perceived own-side security, weak opposing control, embedded local
    footholds, and mapped external sanctuary.  It can be issued to a formation
    that has become combat-ineffective so long as personnel remain.
    """
    formation = world.formations[formation_id]
    if (formation.moving or formation.outside_pineland or formation.personnel <= 0 or
            any(order.formation_id == formation_id and
                order.status in {"pending", "moving"}
                for order in _active_movement_orders(world))):
        return None
    candidates = [
        locality_id for locality_id in sorted(world.localities)
        if locality_id != formation.locality_id
    ]
    if not candidates:
        return None
    route_metrics = _shortest_locality_route_metrics(
        world, formation.locality_id, max(.05, formation.mobility)
    )
    footholds = _local_armed_footholds(world, formation.organization_id)
    insurgent = (
        world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    )
    own_target, opponent_target = _reallocation_side_targets(
        world, formation.organization_id
    )
    risk_tolerance = clamp(
        world.organizations[formation.organization_id].phenotype.get("risk_tolerance", .5)
    )
    scored: list[tuple[float, str]] = []
    for locality_id in candidates:
        route, distance_km, travel_hours = route_metrics[locality_id]
        movement_cost = (
            formation.personnel * formation.availability * distance_km *
            world.config.logistics.movement_consumption_per_person_km
        )
        if movement_cost > formation.supply_stock + 1e-12:
            continue
        _, own_control, own_confidence = _control_belief_value(
            world, formation.organization_id, own_target, locality_id,
            legacy_fallback=True,
        )
        _, opponent_control, opponent_confidence = _control_belief_value(
            world, formation.organization_id, opponent_target, locality_id
        )
        uncertainty = 1.0 - min(own_confidence, opponent_confidence)
        refuge = (
            .45 * own_control +
            .30 * (1.0 - opponent_control) +
            .20 * footholds.get(locality_id, 0.0) +
            .05 * uncertainty
        )
        sanctuary = _sanctuary_access(
            world, formation.organization_id, locality_id,
            mobility=formation.mobility,
        ) if insurgent else 0.0
        route_risk = _believed_route_risk(
            world, formation.organization_id, opponent_target, route
        )
        score = (
            2.2 * refuge + 1.6 * sanctuary - .04 * travel_hours -
            (1.0 - risk_tolerance) * route_risk
        )
        scored.append((score, locality_id))
    if not scored:
        return None
    _, destination = max(scored, key=lambda item: (item[0], item[1]))
    return create_movement_order(
        world, formation_id, destination, time, rng, purpose="withdrawal"
    )


def advance_movement_orders(world: WorldState, time: float) -> dict[str, int | float]:
    departed = arrived = blocked = unavailable = 0
    movement_cost = 0.0
    for order in _active_movement_orders(world):
        formation = world.formations[order.formation_id]
        if order.status == "pending" and order.execute_at <= time:
            withdrawal = order.purpose == "withdrawal"
            if (formation.moving or formation.outside_pineland or formation.personnel <= 0 or
                    (not withdrawal and (
                        formation.operational_status != "effective" or
                        formation.deployable_personnel() <= 0
                    ))):
                order.status = "blocked_unavailable"
                world.active_movement_order_ids.pop(order.order_id, None)
                unavailable += 1
                continue
            if formation.supply_stock + 1e-12 < order.supply_cost:
                order.status = "blocked_supply"
                world.active_movement_order_ids.pop(order.order_id, None)
                blocked += 1
                continue
            consumed, _ = consume_formation_supply(
                world, formation.formation_id, order.supply_cost, "movement",
                order.origin_locality_id, time,
            )
            movement_cost += consumed
            formation.moving = True
            order.status = "moving"
            order.arrives_at = time + order.travel_time_hours / 24
            patrol = next((item for item in world.patrols.values()
                           if item.formation_id == formation.formation_id), None)
            if patrol:
                patrol.available_at = order.arrives_at
                patrol.response_fraction = 0.0
                patrol.presence_accounted_at = order.arrives_at
            departed += 1
        if order.status == "moving" and order.arrives_at is not None and order.arrives_at <= time:
            formation.moving = False
            formation.locality_id = order.destination_locality_id
            formation.fatigue = clamp(formation.fatigue + .015 * order.travel_time_hours / 24)
            formation.readiness = clamp(formation.readiness - .01 * order.travel_time_hours / 24)
            formation.availability = clamp(formation.availability - .05)
            zones = [zone for zone in world.microzones.values()
                     if zone.locality_id == formation.locality_id]
            destination_zone = max(zones, key=lambda zone: zone.population_share)
            formation.current_microzone_id = destination_zone.microzone_id
            patrol = next((item for item in world.patrols.values()
                           if item.formation_id == formation.formation_id), None)
            if patrol:
                patrol.locality_id = formation.locality_id
                patrol.current_microzone_id = destination_zone.microzone_id
                patrol.route_history.append(destination_zone.microzone_id)
                patrol.available_at = time
                patrol.response_fraction = .3
                patrol.presence_accounted_at = time
            order.status = "arrived"
            world.active_movement_order_ids.pop(order.order_id, None)
            arrived += 1
    return {"departed": departed, "arrived": arrived, "blocked_supply": blocked,
            "blocked_unavailable": unavailable,
            "movement_supply_consumed": movement_cost}


def _nearest_source(world: WorldState, formation) -> tuple[SupplySource | None, list[str], float]:
    best: tuple[float, SupplySource, list[str]] | None = None
    for source in world.supply_sources.values():
        if source.organization_id != formation.organization_id or not source.operational or source.stock <= 0:
            continue
        route, _, hours = shortest_locality_path(
            world, source.locality_id, formation.locality_id,
            formation.mobility * world.config.logistics.convoy_speed_factor,
        )
        if best is None or hours < best[0]:
            best = (hours, source, route)
    return (None, [], inf) if best is None else (best[1], best[2], best[0])


def update_logistics(world: WorldState, time: float, delta_days: float) -> dict[str, float | int]:
    config = world.config.logistics
    produced = delivered = consumed = lost = 0.0
    shipments_created = 0
    # Reconcile carrying capacity to current manpower without discarding
    # existing materiel.  This also catches personnel changes caused by combat
    # or peace processes outside organization-ecology recruitment.
    for formation in world.formations.values():
        doctrinal_capacity = max(0.0, formation.personnel * config.formation_supply_days)
        formation.supply_capacity = max(doctrinal_capacity, formation.supply_stock)
        formation.sustainment = formation.supply_fraction()
    for source in world.supply_sources.values():
        if not source.operational:
            continue
        quantity = min(source.capacity - source.stock, source.production_per_day * delta_days)
        source.stock += quantity
        world.cumulative_supply_produced += quantity
        produced += quantity
        if quantity:
            _record_flow(world, time, "production", source.organization_id,
                         source.locality_id, quantity, source_id=source.source_id)

    # Visit only in-flight shipments. Even one full archive scan per tick
    # accumulates quadratic work as completed shipments grow with the horizon.
    active_shipment_formations: set[str] = set()
    for shipment_id in list(world.active_shipment_ids):
        shipment = world.supply_shipments.get(shipment_id)
        if shipment is None or shipment.status != "in_transit":
            world.active_shipment_ids.pop(shipment_id, None)
            continue
        if shipment.status == "in_transit" and shipment.arrives_at <= time:
            formation = world.formations[shipment.formation_id]
            accepted = min(shipment.quantity_deliverable,
                           formation.supply_capacity - formation.supply_stock)
            overflow = shipment.quantity_deliverable - accepted
            formation.supply_stock += accepted
            formation.sustainment = formation.supply_fraction()
            shipment.status = "delivered"
            world.active_shipment_ids.pop(shipment_id, None)
            world.in_transit_supply_total -= shipment.quantity_deliverable
            delivered += accepted
            if overflow:
                world.cumulative_supply_lost += overflow
                lost += overflow
            _record_flow(world, time, "delivery", shipment.organization_id,
                         shipment.destination_locality_id, accepted,
                         shipment.source_id, shipment.formation_id)
        elif shipment.status == "in_transit":
            active_shipment_formations.add(shipment.formation_id)

    for formation in world.formations.values():
        reliability, _ = command_metrics(world, formation.organization_id, formation.formation_id)
        formation.command = reliability
        if formation.moving:
            continue
        demand = (formation.personnel * formation.availability *
                  config.presence_consumption_per_person_day * delta_days)
        used, shortfall = consume_formation_supply(
            world, formation.formation_id, demand, "sustained_presence",
            formation.locality_id, time,
        )
        consumed += used
        fulfillment = used / demand if demand else 1.0
        if shortfall:
            formation.readiness = clamp(
                formation.readiness - config.readiness_degradation_rate * (1 - fulfillment) * delta_days
            )
            formation.availability = clamp(
                formation.availability - .5 * config.readiness_degradation_rate * (1 - fulfillment) * delta_days
            )
            formation.fatigue = clamp(formation.fatigue + .04 * (1 - fulfillment) * delta_days)
        else:
            near_source = any(source.organization_id == formation.organization_id and
                              source.locality_id == formation.locality_id and source.operational
                              for source in world.supply_sources.values())
            recovery = (config.readiness_recovery_near_source if near_source
                        else config.readiness_recovery_remote)
            formation.readiness = clamp(formation.readiness + recovery * delta_days)
            formation.availability = clamp(
                formation.availability + config.availability_recovery_rate * delta_days
            )
            formation.fatigue = clamp(formation.fatigue - recovery * delta_days)
            formation.cohesion = clamp(formation.cohesion + .35 * recovery * delta_days)
            combat = world.config.combat
            if (formation.operational_status == "ineffective" and
                    formation.cohesion > combat.ineffective_cohesion * 1.35 and
                    formation.effective_readiness() > combat.ineffective_readiness * 1.35):
                formation.operational_status = "effective"

        active_shipment = formation.formation_id in active_shipment_formations
        if formation.supply_fraction() >= config.resupply_trigger_fraction or active_shipment:
            continue
        source, route, travel_hours = _nearest_source(world, formation)
        if source is None:
            continue
        desired_delivery = max(0.0, formation.supply_capacity * config.resupply_target_fraction -
                               formation.supply_stock)
        base_efficiency = exp(-config.shipment_loss_per_travel_hour * travel_hours)
        planned_efficiency = base_efficiency
        realized_efficiency = base_efficiency
        interdiction_loss = 0.0
        if config.route_interdiction_enabled and config.route_interdiction_rate > 0:
            belief_view = world.belief_view(formation.organization_id)
            perceived_route_risk = sum(
                belief_view.locality_control(lid, "insurgent").physical
                for lid in route
            ) / max(1, len(route))
            planned_interdiction_loss = (
                config.route_interdiction_rate * perceived_route_risk *
                max(1.0, travel_hours / 24)
            )
            planned_efficiency *= exp(-planned_interdiction_loss)
            # Realized interdiction is an environment process and correctly
            # consumes truth.  It may change losses/delivery, but not the
            # quantity the actor decided to dispatch.
            route_risk = sum(world.localities[lid].control.get("insurgent", ControlVector()).physical
                             for lid in route) / max(1, len(route))
            interdiction_loss = config.route_interdiction_rate * route_risk * max(1.0, travel_hours / 24)
            realized_efficiency *= exp(-interdiction_loss)
        quantity_sent = min(source.stock, desired_delivery / max(planned_efficiency, 1e-9))
        quantity_deliverable = quantity_sent * realized_efficiency
        shipment_loss = quantity_sent - quantity_deliverable
        source.stock -= quantity_sent
        world.cumulative_supply_lost += shipment_loss
        lost += shipment_loss
        shipment = SupplyShipment(
            f"SH{len(world.supply_shipments) + 1:08d}", formation.organization_id,
            source.source_id, formation.formation_id, source.locality_id,
            formation.locality_id, route, time,
            time + max(.01, travel_hours / 24), quantity_sent,
            quantity_deliverable, shipment_loss,
        )
        world.supply_shipments[shipment.shipment_id] = shipment
        world.active_shipment_ids[shipment.shipment_id] = None
        world.in_transit_supply_total += shipment.quantity_deliverable
        shipments_created += 1
        _record_flow(world, time, "shipment_departure", formation.organization_id,
                     source.locality_id, quantity_sent, source.source_id, formation.formation_id)

        formation.sustainment = formation.supply_fraction()

    return {"produced": produced, "delivered": delivered, "consumed": consumed,
            "lost": lost, "shipments_created": shipments_created}


def control_cost(world: WorldState, locality_id: str) -> dict[str, float]:
    elapsed = max(world.time, 1.0)
    consumed_per_day = world.control_cost_consumed.get(locality_id, 0.0) / elapsed
    population = max(1, world.localities[locality_id].population)
    per_thousand = consumed_per_day / population * 1_000
    physical = world.localities[locality_id].control["government"].physical
    return {
        "supply_units_per_day": consumed_per_day,
        "supply_units_per_1000_residents_day": per_thousand,
        "physical_control": physical,
        "control_sustainability": physical / (1 + per_thousand),
    }


def logistics_diagnostics(world: WorldState) -> dict[str, Any]:
    current = (sum(source.stock for source in world.supply_sources.values()) +
               sum(formation.supply_stock for formation in world.formations.values()) +
               world.demobilized_arms +
               sum(shipment.quantity_deliverable for shipment in world.supply_shipments.values()
                   if shipment.status == "in_transit"))
    return {
        "supply_conservation": {
            "initial": world.initial_supply_stock,
            "produced": world.cumulative_supply_produced,
            "converted_from_resources": world.cumulative_resource_to_supply,
            "consumed": world.cumulative_supply_consumed,
            "lost": world.cumulative_supply_lost,
            "current": current,
            "residual": (world.initial_supply_stock + world.cumulative_supply_produced +
                         world.cumulative_resource_to_supply -
                         world.cumulative_supply_consumed - world.cumulative_supply_lost - current),
        },
        "formations": {
            formation_id: {
                "assigned_personnel": formation.personnel,
                "available_personnel": formation.available_personnel(),
                "availability": formation.availability,
                "readiness": formation.readiness,
                "effective_readiness": formation.effective_readiness(),
                "supply_stock": formation.supply_stock,
                "supply_fraction": formation.supply_fraction(),
                "command_reliability": formation.command,
                "fatigue": formation.fatigue,
                "locality_id": formation.locality_id,
                "moving": formation.moving,
            }
            for formation_id, formation in world.formations.items()
        },
        "movement_orders": {order_id: asdict(order) for order_id, order in world.movement_orders.items()},
        "shipments": {shipment_id: asdict(shipment)
                      for shipment_id, shipment in world.supply_shipments.items()},
        "route_interdiction": {
            "enabled": world.config.logistics.route_interdiction_enabled,
            "rate": world.config.logistics.route_interdiction_rate,
        },
        "control_cost": {locality_id: control_cost(world, locality_id)
                         for locality_id in world.localities},
    }
