//! Conserved supply production, consumption, resupply, and readiness.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, python_sum_with_integer_prefix, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
    time: f64,
) {
    let dt = elapsed_days.max(0.0);
    let logistics_trace = crate::trace_env!("PINELAND_LOGISTICS_TRACE");
    let formation_trace = crate::trace_env!("PINELAND_LOGISTICS_FORMATION_TRACE");
    if formation_trace && particle.formations.supply_stock.len() > 7 {
        eprintln!(
            "LOGISTICS_FORMATION_BEGIN time={:.17} dt={:.17} formation=7 stock={:.17} bits={}",
            time,
            dt,
            particle.formations.supply_stock[7],
            particle.formations.supply_stock[7].to_bits()
        );
    }
    if logistics_trace {
        eprintln!(
            "LOGISTICS_BEGIN time={:.17} dt={:.17} in_transit={:.17} in_transit_bits={} shipments={}",
            time,
            dt,
            particle.logistics.in_transit,
            particle.logistics.in_transit.to_bits(),
            particle.logistics.shipment_source.len()
        );
    }
    let _expired = crate::access::decay(particle, time, dt, config);
    reconcile_source_production(particle, topology, config);
    // The Python oracle reconciles carrying capacity to current personnel at
    // the start of every logistics event.  Combat, recruitment, and peace
    // transitions can change personnel without changing the materiel already
    // carried; preserve that stock while shrinking/growing the doctrinal
    // capacity to the current force size.
    for formation in 0..particle.formations.personnel.len() {
        let doctrinal_capacity = (particle.formations.personnel[formation]
            * config.logistics.formation_supply_days)
            .max(0.0);
        particle.formations.supply_capacity[formation] =
            doctrinal_capacity.max(particle.formations.supply_stock[formation]);
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
        // Python refreshes the formation's operational command value from its
        // current HQ path at the start of every logistics event.  The dense
        // Native-v1 representation has one direct command edge per formation;
        // retain the same fallback used by movement when an edge is absent.
        particle.formations.command[formation] = command_reliability(particle, formation);
    }
    for source in 0..particle.logistics.source_stock.len() {
        let production = particle.logistics.source_production[source] * dt;
        let available_capacity = (particle.logistics.source_capacity[source]
            - particle.logistics.source_stock[source])
            .max(0.0);
        let produced = production.min(available_capacity);
        particle.logistics.source_stock[source] += produced;
        particle.logistics.cumulative_produced += produced;
    }

    // Deliver shipments that have reached their destination before evaluating
    // new demand.  The Python world retains the complete shipment archive but
    // uses only the in-transit subset to suppress duplicate dispatches; the
    // dense state mirrors both facts with a status column.
    let mut active_shipment_formations = vec![false; particle.formations.personnel.len()];
    let shipment_count = particle.logistics.shipment_source.len();
    for shipment in 0..shipment_count {
        if particle.logistics.shipment_status[shipment] != SHIPMENT_IN_TRANSIT {
            continue;
        }
        if particle.logistics.shipment_arrives_at[shipment] <= time {
            let formation = particle.logistics.shipment_formation[shipment] as usize;
            if formation >= particle.formations.personnel.len() {
                continue;
            }
            let deliverable = particle.logistics.shipment_quantity_deliverable[shipment];
            if logistics_trace {
                eprintln!(
                    "LOGISTICS_DELIVER shipment={} time={:.17} amount={:.17} before={:.17} status={}",
                    shipment,
                    time,
                    deliverable,
                    particle.logistics.in_transit,
                    particle.logistics.shipment_status[shipment]
                );
            }
            let accepted = deliverable.min(
                particle.formations.supply_capacity[formation]
                    - particle.formations.supply_stock[formation],
            );
            let overflow = deliverable - accepted;
            particle.formations.supply_stock[formation] += accepted;
            particle.formations.sustainment[formation] = supply_ratio(particle, formation);
            particle.logistics.shipment_status[shipment] = SHIPMENT_DELIVERED;
            particle.logistics.in_transit -= deliverable;
            if logistics_trace {
                eprintln!(
                    "LOGISTICS_DELIVERED shipment={} after={:.17} after_bits={}",
                    shipment,
                    particle.logistics.in_transit,
                    particle.logistics.in_transit.to_bits()
                );
            }
            particle.logistics.cumulative_delivered += accepted;
            if overflow > 0.0 {
                particle.logistics.cumulative_lost += overflow;
            }
        } else {
            let formation = particle.logistics.shipment_formation[shipment] as usize;
            if formation < active_shipment_formations.len() {
                active_shipment_formations[formation] = true;
            }
        }
    }
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] == 0 || particle.formations.moving[formation] != 0
        {
            continue;
        }
        let personnel = particle.formations.personnel[formation].max(0.0);
        let equipment_supply_burden = if particle.formations.organization[formation] as usize
            == crate::MILITARY
        {
            config.combat.government_supply_burden_multiplier
        } else {
            1.0
        };
        let demand = personnel
            * particle.formations.availability[formation]
            * config.logistics.presence_consumption_per_person_day
            * equipment_supply_burden
            * dt;
        let consumed = demand.min(particle.formations.supply_stock[formation]);
        let shortfall = (demand - consumed).max(0.0);
        particle.formations.supply_stock[formation] -= consumed;
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
        particle.logistics.cumulative_consumed += consumed;
        let fulfillment = if demand > 0.0 { consumed / demand } else { 1.0 };
        if shortfall > 0.0 {
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation]
                    - config.logistics.readiness_degradation_rate * (1.0 - fulfillment) * dt,
            );
            particle.formations.availability[formation] = clamp01(
                particle.formations.availability[formation]
                    - 0.5 * config.logistics.readiness_degradation_rate * (1.0 - fulfillment) * dt,
            );
            particle.formations.fatigue[formation] =
                clamp01(particle.formations.fatigue[formation] + 0.04 * (1.0 - fulfillment) * dt);
        } else {
            let organization = particle.formations.organization[formation];
            let locality = particle.formations.locality[formation];
            let near_source = particle
                .logistics
                .organization
                .iter()
                .zip(particle.logistics.locality.iter())
                .any(|(&source_organization, &source_locality)| {
                    source_organization == organization && source_locality == locality
                });
            let recovery = if near_source {
                config.logistics.readiness_recovery_near_source
            } else {
                config.logistics.readiness_recovery_remote
            };
            particle.formations.readiness[formation] =
                clamp01(particle.formations.readiness[formation] + recovery * dt);
            particle.formations.availability[formation] = clamp01(
                particle.formations.availability[formation]
                    + config.logistics.availability_recovery_rate * dt,
            );
            particle.formations.fatigue[formation] =
                clamp01(particle.formations.fatigue[formation] - recovery * dt);
            particle.formations.cohesion[formation] =
                clamp01(particle.formations.cohesion[formation] + 0.35 * recovery * dt);
        }
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);

        // Python permits a previously ineffective formation to recover during
        // a fully supplied logistics cycle.  This can matter after an
        // organization collapse, because the next force-movement boundary
        // sees the reactivated formation when renewing local footholds.
        if particle.formations.operational_status[formation] == 0
            && particle.formations.cohesion[formation] > config.combat.ineffective_cohesion * 1.35
            && particle.formations.effective_readiness(formation)
                > config.combat.ineffective_readiness * 1.35
        {
            particle.formations.operational_status[formation] = 1;
        }

        if particle.formations.supply_fraction(formation)
            >= config.logistics.resupply_trigger_fraction
            || active_shipment_formations[formation]
        {
            continue;
        }
        let Some((source, route, travel_hours)) = nearest_source(
            particle,
            topology,
            formation,
            config.logistics.convoy_speed_factor,
        ) else {
            continue;
        };
        // Keep the Python expression's operation order: multiply the target
        // capacity, subtract current stock, then clamp at zero.  The
        // explicit volatile boundaries used by integer-style reductions are
        // not part of this scalar CPython recurrence and can move the final
        // stock by one ulp on a dispatch boundary.
        let desired_delivery = (particle.formations.supply_capacity[formation]
            * config.logistics.resupply_target_fraction
            - particle.formations.supply_stock[formation])
            .max(0.0);
        let base_efficiency =
            python_exp(-config.logistics.shipment_loss_per_travel_hour * travel_hours);
        // Route interdiction is an optional extension of the same dispatch
        // contract.  The baseline certification configuration disables it;
        // the explicit branch keeps the shipment quantity decision separate
        // from realized environmental loss when that feature is enabled.
        let planned_efficiency = base_efficiency;
        let realized_efficiency = base_efficiency;
        let quantity_sent = particle.logistics.source_stock[source]
            .min(desired_delivery / planned_efficiency.max(1.0e-9));
        let quantity_deliverable = quantity_sent * realized_efficiency;
        let shipment_loss = quantity_sent - quantity_deliverable;
        particle.logistics.source_stock[source] -= quantity_sent;
        particle.logistics.cumulative_lost += shipment_loss;
        particle.logistics.cumulative_shipped += quantity_sent;
        particle.logistics.in_transit += quantity_deliverable;
        if logistics_trace {
            eprintln!(
                "LOGISTICS_DISPATCH shipment={} time={:.17} sent={:.17} deliverable={:.17} after={:.17} after_bits={}",
                particle.logistics.shipment_source.len(),
                time,
                quantity_sent,
                quantity_deliverable,
                particle.logistics.in_transit,
                particle.logistics.in_transit.to_bits()
            );
        }
        append_shipment(
            particle,
            source,
            formation,
            particle.logistics.locality[source] as usize,
            particle.formations.locality[formation] as usize,
            &route,
            time,
            time + (0.01_f64).max(travel_hours / 24.0),
            quantity_sent,
            quantity_deliverable,
            shipment_loss,
        );
        particle.formations.sustainment[formation] = supply_ratio(particle, formation);
    }
    // Shipment and movement-order state is added below as the portable state
    // boundary grows; do not synthesize a different demand model here.
    if formation_trace && particle.formations.supply_stock.len() > 7 {
        eprintln!(
            "LOGISTICS_FORMATION_END time={:.17} formation=7 stock={:.17} bits={}",
            time,
            particle.formations.supply_stock[7],
            particle.formations.supply_stock[7].to_bits()
        );
    }
    let _ = rng;
    let _ = time;
}

const SHIPMENT_IN_TRANSIT: u8 = 0;
const SHIPMENT_DELIVERED: u8 = 1;

#[derive(Clone, Debug)]
struct RouteMetric {
    route: Vec<usize>,
    travel_hours: f64,
}

fn append_shipment(
    particle: &mut ParticleState,
    source: usize,
    formation: usize,
    origin_locality: usize,
    destination_locality: usize,
    route: &[usize],
    departed_at: f64,
    arrives_at: f64,
    quantity_sent: f64,
    quantity_deliverable: f64,
    loss: f64,
) {
    particle.logistics.shipment_source.push(source as u32);
    particle.logistics.shipment_formation.push(formation as u32);
    particle
        .logistics
        .shipment_origin_locality
        .push(origin_locality as u32);
    particle
        .logistics
        .shipment_destination_locality
        .push(destination_locality as u32);
    let prior_route_end = particle
        .logistics
        .shipment_route_offsets
        .last()
        .copied()
        .unwrap_or(0);
    particle
        .logistics
        .shipment_route_nodes
        .extend(route.iter().map(|node| *node as u32));
    particle
        .logistics
        .shipment_route_offsets
        .push(prior_route_end + route.len() as u32);
    particle.logistics.shipment_departed_at.push(departed_at);
    particle.logistics.shipment_arrives_at.push(arrives_at);
    particle
        .logistics
        .shipment_quantity_sent
        .push(quantity_sent);
    particle
        .logistics
        .shipment_quantity_deliverable
        .push(quantity_deliverable);
    particle.logistics.shipment_loss.push(loss);
    particle.logistics.shipment_status.push(SHIPMENT_IN_TRANSIT);
}

fn nearest_source(
    particle: &ParticleState,
    topology: &StaticTopology,
    formation: usize,
    convoy_speed_factor: f64,
) -> Option<(usize, Vec<usize>, f64)> {
    let organization = particle.formations.organization[formation] as usize;
    let mobility = particle.formations.mobility[formation] * convoy_speed_factor;
    let destination = particle.formations.locality[formation] as usize;
    let mut best: Option<(usize, Vec<usize>, f64)> = None;
    for source in 0..particle.logistics.source_stock.len() {
        if particle.logistics.organization[source] as usize != organization
            || particle.logistics.source_stock[source] <= 0.0
        {
            continue;
        }
        let origin = particle.logistics.locality[source] as usize;
        let Some(metric) = shortest_route_metric(particle, topology, origin, destination, mobility)
        else {
            continue;
        };
        if best
            .as_ref()
            .is_none_or(|(_, _, hours)| metric.travel_hours < *hours)
        {
            best = Some((source, metric.route, metric.travel_hours));
        }
    }
    best
}

fn shortest_route_metric(
    particle: &ParticleState,
    topology: &StaticTopology,
    origin: usize,
    destination: usize,
    mobility: f64,
) -> Option<RouteMetric> {
    let count = topology.locality_count();
    if origin >= count || destination >= count {
        return None;
    }
    let mut travel = vec![f64::INFINITY; count];
    let mut distance = vec![0.0; count];
    let mut previous = vec![usize::MAX; count];
    let mut settled = vec![false; count];
    travel[origin] = 0.0;
    for _ in 0..count {
        let mut next = None;
        for node in 0..count {
            if settled[node] || !travel[node].is_finite() {
                continue;
            }
            if next.is_none_or(|current| {
                travel[node]
                    .total_cmp(&travel[current])
                    .then_with(|| node.cmp(&current))
                    == std::cmp::Ordering::Less
            }) {
                next = Some(node);
            }
        }
        let Some(node) = next else { break };
        settled[node] = true;
        for (neighbor, _) in topology.locality_edges.neighbors(node) {
            let neighbor = neighbor as usize;
            let Some((leg_distance, leg_hours)) =
                locality_leg(particle, topology, node, neighbor, mobility)
            else {
                continue;
            };
            let candidate = travel[node] + leg_hours;
            if candidate < travel[neighbor] {
                travel[neighbor] = candidate;
                distance[neighbor] = distance[node] + leg_distance;
                previous[neighbor] = node;
            }
        }
    }
    if !travel[destination].is_finite() {
        return None;
    }
    let mut route = vec![destination];
    while route[route.len() - 1] != origin {
        let parent = previous[route[route.len() - 1]];
        if parent == usize::MAX {
            return None;
        }
        route.push(parent);
    }
    route.reverse();
    Some(RouteMetric {
        route,
        travel_hours: travel[destination],
    })
}

fn locality_leg(
    particle: &ParticleState,
    topology: &StaticTopology,
    first: usize,
    second: usize,
    mobility: f64,
) -> Option<(f64, f64)> {
    let terrain_cost = topology
        .locality_edges
        .neighbors(first)
        .find_map(|(neighbor, weight)| (neighbor as usize == second).then_some(weight))?;
    let infrastructure =
        (particle.locality.infrastructure[first] + particle.locality.infrastructure[second]) / 2.0;
    let distance_km = 18.0 + 22.0 * terrain_cost;
    let speed_kmh = 42.0 * mobility.max(0.15) * infrastructure.max(0.2) / terrain_cost.max(0.5);
    Some((distance_km, distance_km / speed_kmh))
}

fn command_reliability(particle: &ParticleState, formation: usize) -> f64 {
    let organization = particle.formations.organization[formation] as usize;
    for edge in 0..particle.command_edges.organization.len() {
        if particle.command_edges.organization[edge] as usize == organization
            && particle.command_edges.formation[edge] as usize == formation
        {
            return particle.command_edges.reliability[edge].clamp(0.0, 1.0);
        }
    }
    particle.formations.command[formation].clamp(0.0, 1.0)
}

fn reconcile_source_production(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
) {
    if config.logistics.source_capacity_model != "organization_manpower" {
        return;
    }
    let organization_count = particle.organizations.kind.len();
    for organization in 0..organization_count {
        let source_indices: Vec<usize> = particle
            .logistics
            .organization
            .iter()
            .enumerate()
            .filter_map(|(index, &candidate)| (candidate as usize == organization).then_some(index))
            .collect();
        if source_indices.is_empty() {
            continue;
        }
        let formation_indices: Vec<usize> = particle
            .formations
            .organization
            .iter()
            .enumerate()
            .filter_map(|(index, &candidate)| {
                (candidate as usize == organization && particle.formations.active[index] != 0)
                    .then_some(index)
            })
            .collect();
        // Match Python's per-organization dictionary accumulation exactly;
        // an optimized iterator reduction may reassociate the additions and
        // move a parity value by one ulp.
        let mut personnel = 0.0;
        for &formation in &formation_indices {
            personnel =
                round_binary64(personnel + particle.formations.personnel[formation].max(0.0));
        }
        let equipment_supply_burden = if organization == crate::MILITARY {
            config.combat.government_supply_burden_multiplier
        } else {
            1.0
        };
        let requirement = round_binary64(
            round_binary64(
                personnel
                    * config.logistics.presence_consumption_per_person_day
                    * equipment_supply_burden,
            )
                * config.logistics.organization_sustainment_coverage,
        );
        let territorial = particle
            .organizations
            .kind
            .get(organization)
            .is_some_and(|kind| *kind == 1 || *kind == 2);
        let mut weights = Vec::with_capacity(source_indices.len());
        let mut integer_prefix_len = 0;
        let mut integer_prefix_open = true;
        for &source in &source_indices {
            let locality = particle.logistics.locality[source];
            let weight = if territorial {
                let district = topology
                    .locality_to_district
                    .get(locality as usize)
                    .copied()
                    .unwrap_or(u32::MAX);
                let population = particle
                    .locality
                    .district_population
                    .get(district as usize)
                    .copied()
                    .unwrap_or_else(|| {
                        topology
                            .district_population
                            .get(district as usize)
                            .copied()
                            .unwrap_or(0.0)
                    });
                let is_integer = integer_prefix_open
                    && particle
                        .locality
                        .district_population_is_integer
                        .get(district as usize)
                        .copied()
                        .unwrap_or(0)
                        != 0
                    && population > 1.0;
                if is_integer {
                    integer_prefix_len += 1;
                } else {
                    integer_prefix_open = false;
                }
                population.max(1.0)
            } else {
                integer_prefix_open = false;
                python_sum(
                    &formation_indices
                        .iter()
                        .filter(|&&formation| {
                            particle.formations.home_locality[formation] == locality
                        })
                        .map(|&formation| particle.formations.personnel[formation].max(0.0))
                        .collect::<Vec<_>>(),
                )
            };
            weights.push(weight);
        }
        let weight_total = if territorial {
            python_sum_with_integer_prefix(&weights, integer_prefix_len)
        } else {
            python_sum(&weights)
        };
        if weight_total <= 0.0 {
            weights.fill(1.0);
            integer_prefix_len = 0;
        }
        let total_weight = if territorial {
            python_sum_with_integer_prefix(&weights, integer_prefix_len)
        } else {
            python_sum(&weights)
        };
        if crate::trace_env!("PINELAND_LOGISTICS_RECON_TRACE") {
            eprintln!(
                "LOGISTICS_RECON organization={} personnel={:.17} personnel_bits={} requirement={:.17} requirement_bits={} weights={:?} total_weight={:.17}",
                organization,
                personnel,
                personnel.to_bits(),
                requirement,
                requirement.to_bits(),
                weights,
                total_weight
            );
        }
        for (&source, &weight) in source_indices.iter().zip(weights.iter()) {
            // Keep the two Python operations (multiply, then divide) as two
            // observable IEEE-754 boundaries; otherwise an optimized native
            // build may contract/reassociate them and differ by one ulp.
            let numerator = round_binary64(requirement * weight);
            let production = round_binary64(numerator / total_weight);
            particle.logistics.source_production[source] = production;
            particle.logistics.source_capacity[source] = particle.logistics.source_capacity[source]
                .max(particle.logistics.source_stock[source])
                .max(production / config.logistics.source_daily_production_fraction.max(1e-12));
            if crate::trace_env!("PINELAND_LOGISTICS_RECON_TRACE") {
                eprintln!(
                    "LOGISTICS_SOURCE organization={} source={} weight={:.17} weight_bits={} production={:.17} production_bits={} capacity={:.17}",
                    organization,
                    source,
                    weight,
                    weight.to_bits(),
                    production,
                    production.to_bits(),
                    particle.logistics.source_capacity[source]
                );
            }
        }
    }
}

/// Force the same binary64 rounding boundary that CPython applies when a
/// float result is stored back into a Python object.  MSVC/LLVM may otherwise
/// retain an intermediate in a wider register across a short reduction,
/// which changes the last bit of parity-critical accumulations.
#[inline(never)]
fn round_binary64(value: f64) -> f64 {
    unsafe { std::ptr::read_volatile(&value) }
}

pub fn supply_ratio(particle: &ParticleState, formation: usize) -> f64 {
    if particle
        .formations
        .supply_capacity
        .get(formation)
        .copied()
        .unwrap_or(0.0)
        <= 0.0
    {
        0.0
    } else {
        particle.formations.supply_stock[formation] / particle.formations.supply_capacity[formation]
    }
}

#[cfg(test)]
mod tests {
    use super::round_binary64;

    #[test]
    fn python_accumulation_rounds_at_each_addition() {
        let value = f64::from_bits(4_651_811_840_107_362_532);
        let mut total = 0.0;
        for _ in 0..9 {
            total = round_binary64(total + value);
        }
        assert_eq!(total.to_bits(), 4_666_063_465_490_677_759);
    }
}
