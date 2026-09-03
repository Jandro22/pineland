from __future__ import annotations

from dataclasses import asdict
import heapq
from math import exp, inf, log
from typing import Any

from .entities import (
    CommandEdge,
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
    return route, distance_km, distances[destination_id]


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
    world.movement_orders.clear()
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
        source_localities = ([district.locality_ids[0] for district in world.districts.values()]
                             if organization.kind in {OrganizationKind.MILITARY, OrganizationKind.POLICE}
                             else sorted({formation.home_locality_id for formation in formations}))
        for index, locality_id in enumerate(source_localities):
            locality = world.localities[locality_id]
            capacity = max(5_000.0, locality.population * config.source_capacity_per_resident)
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
                          time: float, rng=None) -> FormationMovementOrder:
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
    )
    world.movement_orders[order.order_id] = order
    return order


def choose_reallocation_orders(world: WorldState, time: float, rng) -> list[FormationMovementOrder]:
    orders = []
    for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
        if formation.moving or any(order.formation_id == formation.formation_id and
                                   order.status in {"pending", "moving"}
                                   for order in world.movement_orders.values()):
            continue
        if rng.random() >= world.config.logistics.reallocation_rate:
            continue
        candidates = [locality_id for locality_id in sorted(world.localities)
                      if locality_id != formation.locality_id]
        utilities = []
        for locality_id in candidates:
            belief = world.beliefs.get((formation.organization_id, locality_id))
            estimated = belief.control_estimate.physical if belief else .5
            confidence = belief.confidence if belief else 0.0
            route, _, travel_hours = shortest_locality_path(
                world, formation.locality_id, locality_id, formation.mobility
            )
            importance = world.localities[locality_id].population / max(
                locality.population for locality in world.localities.values()
            )
            if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT:
                need = estimated
            else:
                need = 1 - estimated
            # Commanders act on perceived need and confidence, never on truth.
            # Low-confidence areas retain a small exploratory value rather than
            # disappearing from the decision set.
            perceived_need = need * (.55 + .45 * confidence) + .18 * (1 - confidence)
            utilities.append(exp(max(-8, min(8, 2.0 * perceived_need +
                                               .5 * importance - .03 * travel_hours))))
        destination = rng.choices(candidates, weights=utilities, k=1)[0]
        orders.append(create_movement_order(world, formation.formation_id, destination, time, rng))
    return orders


def advance_movement_orders(world: WorldState, time: float) -> dict[str, int | float]:
    departed = arrived = blocked = 0
    movement_cost = 0.0
    for order in world.movement_orders.values():
        formation = world.formations[order.formation_id]
        if order.status == "pending" and order.execute_at <= time:
            if formation.supply_stock + 1e-12 < order.supply_cost:
                order.status = "blocked_supply"
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
            order.status = "arrived"
            arrived += 1
    return {"departed": departed, "arrived": arrived, "blocked_supply": blocked,
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

    for shipment in world.supply_shipments.values():
        if shipment.status == "in_transit" and shipment.arrives_at <= time:
            formation = world.formations[shipment.formation_id]
            accepted = min(shipment.quantity_deliverable,
                           formation.supply_capacity - formation.supply_stock)
            overflow = shipment.quantity_deliverable - accepted
            formation.supply_stock += accepted
            formation.sustainment = formation.supply_fraction()
            shipment.status = "delivered"
            delivered += accepted
            if overflow:
                world.cumulative_supply_lost += overflow
                lost += overflow
            _record_flow(world, time, "delivery", shipment.organization_id,
                         shipment.destination_locality_id, accepted,
                         shipment.source_id, shipment.formation_id)

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

        active_shipment = any(shipment.formation_id == formation.formation_id and
                              shipment.status == "in_transit"
                              for shipment in world.supply_shipments.values())
        if formation.supply_fraction() >= config.resupply_trigger_fraction or active_shipment:
            continue
        source, route, travel_hours = _nearest_source(world, formation)
        if source is None:
            continue
        desired_delivery = max(0.0, formation.supply_capacity * config.resupply_target_fraction -
                               formation.supply_stock)
        efficiency = exp(-config.shipment_loss_per_travel_hour * travel_hours)
        quantity_sent = min(source.stock, desired_delivery / max(efficiency, 1e-9))
        quantity_deliverable = quantity_sent * efficiency
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
               sum(shipment.quantity_deliverable for shipment in world.supply_shipments.values()
                   if shipment.status == "in_transit"))
    return {
        "supply_conservation": {
            "initial": world.initial_supply_stock,
            "produced": world.cumulative_supply_produced,
            "consumed": world.cumulative_supply_consumed,
            "lost": world.cumulative_supply_lost,
            "current": current,
            "residual": (world.initial_supply_stock + world.cumulative_supply_produced -
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
        "control_cost": {locality_id: control_cost(world, locality_id)
                         for locality_id in world.localities},
    }
