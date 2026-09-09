//! Formation orders and represented civilian mobility.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat, RngError};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

const GOVERNMENT: usize = 0;
const MILITARY: usize = 1;
const POLICE: usize = 2;
const INSURGENT: usize = 6;

const MOVE_PENDING: u8 = 1;
const MOVE_MOVING: u8 = 2;
const MOVE_FAILED_COMMAND: u8 = 3;
const MOVE_BLOCKED_UNAVAILABLE: u8 = 4;
const MOVE_BLOCKED_SUPPLY: u8 = 5;
const MOVE_ARRIVED: u8 = 6;

const POSTURE_PORTFOLIO: u8 = 0;
const POSTURE_FRONTIER: u8 = 1;
const POSTURE_FOOTHOLD: u8 = 2;
const POSTURE_STRONGHOLD: u8 = 3;
const POSTURE_EXPLORATION: u8 = 4;

#[derive(Clone, Debug)]
struct RouteMetric {
    route: Vec<usize>,
    distance_km: f64,
    travel_hours: f64,
}

pub fn civilian_mobility(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
) {
    for locality in 0..topology.locality_count() {
        let violence = particle.locality.violence[locality];
        if violence >= config.civilian_dynamics.displacement_violence_threshold {
            let amount = particle.locality.population[locality]
                * config.civilian_dynamics.forced_displacement_reference_rate
                * config.intervals.mobility;
            particle.locality.displaced_population[locality] =
                (particle.locality.displaced_population[locality] + amount)
                    .min(particle.locality.population[locality]);
        } else if particle.locality.displaced_population[locality] > 0.0
            && rng.random()
                < config.civilian_dynamics.return_reference_rate * config.intervals.mobility
        {
            particle.locality.displaced_population[locality] =
                (particle.locality.displaced_population[locality] * 0.98).max(0.0);
        }
    }
}

pub fn command(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) -> Result<(), RngError> {
    // Python composes the daily decision probability with the actual command
    // interval.  The t=0 command boundary is therefore a true no-op and must
    // not consume a command-stream draw.
    if elapsed_days <= 0.0 {
        return Ok(());
    }
    let daily_probability = config.logistics.reallocation_rate.clamp(0.0, 1.0);
    let decision_probability = if daily_probability <= 0.0 {
        0.0
    } else if daily_probability >= 1.0 {
        1.0
    } else {
        (1.0 - python_exp(elapsed_days * (1.0 - daily_probability).ln())).clamp(0.0, 1.0)
    };
    if decision_probability <= 0.0 {
        return Ok(());
    }

    let maximum_population = topology
        .locality_population
        .iter()
        .copied()
        .fold(0.0, f64::max);
    let formation_count = particle.formations.personnel.len();
    for formation in 0..formation_count {
        // This follows choose_reallocation_orders exactly.  In particular,
        // active is not an additional filter: Python's deployable_personnel
        // predicate is the authoritative availability boundary.
        if particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.personnel[formation] <= 0.0
            || particle.formations.operational_status[formation] != 1
            || particle.formations.deployable_personnel(formation) <= 0.0
            || has_active_order(particle, formation)
        {
            continue;
        }
        if rng.random() >= decision_probability {
            continue;
        }

        let organization = particle.formations.organization[formation] as usize;
        let route_metrics = all_route_metrics(
            particle,
            topology,
            particle.formations.locality[formation] as usize,
            particle.formations.mobility[formation],
        );
        let insurgent = particle.organizations.kind.get(organization).copied() == Some(3);
        let footholds = if insurgent {
            Some(local_armed_footholds(
                particle,
                topology,
                organization,
                config,
            ))
        } else {
            None
        };
        let posture = if insurgent {
            Some(select_insurgent_posture(
                particle,
                organization,
                formation,
                config,
                rng,
            )?)
        } else {
            None
        };
        let moving_personnel =
            particle.formations.personnel[formation] * particle.formations.availability[formation];
        let origin = particle.formations.locality[formation] as usize;
        let mut destinations = Vec::new();
        if config.logistics.reallocation_destination_scope == "adjacent" {
            destinations.push(origin);
            destinations.extend(
                topology
                    .locality_edges
                    .neighbors(origin)
                    .map(|(neighbor, _)| neighbor as usize),
            );
            destinations.sort_unstable();
            destinations.dedup();
        } else {
            destinations.extend(0..topology.locality_count());
        }

        let mut candidates = Vec::new();
        let mut utilities = Vec::new();
        for destination in destinations {
            let Some(metric) = route_metrics.get(destination).and_then(Option::as_ref) else {
                continue;
            };
            let movement_cost = moving_personnel
                * metric.distance_km
                * config.logistics.movement_consumption_per_person_km;
            // The commander checks feasibility before issuing. The force
            // movement event checks again after command latency.
            if destination != origin
                && movement_cost > particle.formations.supply_stock[formation] + 1.0e-12
            {
                continue;
            }
            let score = destination_score(
                particle,
                topology,
                config,
                formation,
                destination,
                metric,
                maximum_population,
                footholds.as_deref(),
                posture,
            );
            candidates.push(destination);
            utilities.push(python_exp(score.clamp(-8.0, 8.0)));
        }
        if candidates.is_empty() {
            continue;
        }
        let selected = rng.choices_indices(candidates.len(), Some(&utilities), 1)?[0];
        let destination = candidates[selected];
        if destination == origin {
            continue;
        }
        issue_reallocation_order(
            particle,
            topology,
            config,
            formation,
            destination,
            time,
            rng,
            route_metrics[destination]
                .as_ref()
                .expect("selected movement destination has a route"),
        );
    }
    Ok(())
}

fn has_active_order(particle: &ParticleState, formation: usize) -> bool {
    particle.formations.movement_status.get(formation).copied() == Some(MOVE_PENDING)
        || particle.formations.movement_status.get(formation).copied() == Some(MOVE_MOVING)
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

fn all_route_metrics(
    particle: &ParticleState,
    topology: &StaticTopology,
    origin: usize,
    mobility: f64,
) -> Vec<Option<RouteMetric>> {
    let count = topology.locality_count();
    let mut travel = vec![f64::INFINITY; count];
    let mut distances = vec![0.0; count];
    let mut previous = vec![usize::MAX; count];
    let mut settled = vec![false; count];
    travel[origin] = 0.0;

    // A linear min-queue is intentional here. It has the same (distance,
    // locality-id) order as Python heapq and avoids introducing a platform-
    // dependent ordering for equal-cost candidates.
    for _ in 0..count {
        let mut next = None;
        for node in 0..count {
            if settled[node] || !travel[node].is_finite() {
                continue;
            }
            let replace = next.is_none_or(|current| {
                travel[node]
                    .total_cmp(&travel[current])
                    .then_with(|| node.cmp(&current))
                    == std::cmp::Ordering::Less
            });
            if replace {
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
                distances[neighbor] = distances[node] + leg_distance;
                previous[neighbor] = node;
            }
        }
    }

    let mut result = vec![None; count];
    for destination in 0..count {
        if !travel[destination].is_finite() {
            continue;
        }
        let mut route = vec![destination];
        while route[route.len() - 1] != origin {
            let parent = previous[route[route.len() - 1]];
            if parent == usize::MAX {
                route.clear();
                break;
            }
            route.push(parent);
        }
        if route.is_empty() {
            continue;
        }
        route.reverse();
        result[destination] = Some(RouteMetric {
            route,
            distance_km: distances[destination],
            travel_hours: travel[destination],
        });
    }
    result
}

fn local_armed_footholds(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    config: &SimulationConfig,
) -> Vec<f64> {
    let mut represented = vec![0.0; topology.locality_count()];
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let locality = particle.people.locality[person] as usize;
        if locality < represented.len() {
            represented[locality] += particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
        }
    }
    let scale = config
        .organization_ecology
        .minimum_proto_represented_population
        .max(1.0e-9);
    for locality in 0..represented.len() {
        represented[locality] = clamp01(represented[locality] / scale);
        let index = organization * topology.locality_count() + locality;
        if index < particle.footholds.strength.len() {
            represented[locality] = represented[locality].max(particle.footholds.strength[index]);
        }
    }
    represented
}

fn select_insurgent_posture(
    particle: &mut ParticleState,
    organization: usize,
    formation: usize,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
) -> Result<u8, RngError> {
    let current = particle.formations.operational_posture[formation];
    if matches!(
        current,
        POSTURE_FRONTIER | POSTURE_FOOTHOLD | POSTURE_STRONGHOLD | POSTURE_EXPLORATION
    ) && rng.random() < particle.organizations.persistence[organization].clamp(0.0, 1.0)
    {
        return Ok(current);
    }
    let weights = [
        config.logistics.insurgent_frontier_weight,
        config.logistics.insurgent_foothold_weight,
        config.logistics.insurgent_stronghold_weight,
        config.logistics.reallocation_exploration_weight,
    ];
    let selected = rng.choices_indices(4, Some(&weights), 1)?[0];
    let posture = match selected {
        0 => POSTURE_FRONTIER,
        1 => POSTURE_FOOTHOLD,
        2 => POSTURE_STRONGHOLD,
        _ => POSTURE_EXPLORATION,
    };
    particle.formations.operational_posture[formation] = posture;
    Ok(posture)
}

fn belief_triplet(
    particle: &ParticleState,
    observer: usize,
    target: usize,
    locality: usize,
    kind: u8,
) -> (f64, f64, f64) {
    let Some(index) = particle.beliefs.keys.iter().position(|key| {
        key.observer as usize == observer
            && key.target as usize == target
            && key.locality as usize == locality
            && key.kind == kind
    }) else {
        return (0.5, 0.5, 0.0);
    };
    let raw = particle.beliefs.control[index * pineland_core::state::CONTROL_DIMENSIONS + 1]
        .clamp(0.0, 1.0);
    let confidence = particle.beliefs.confidence[index].clamp(0.0, 1.0);
    let adjusted = (0.5 + confidence * (raw - 0.5)).clamp(0.0, 1.0);
    (raw, adjusted, confidence)
}

fn target_pair(particle: &ParticleState, organization: usize) -> (usize, usize) {
    if organization == INSURGENT
        || particle.organizations.kind.get(organization).copied() == Some(3)
    {
        (INSURGENT, GOVERNMENT)
    } else if matches!(organization, GOVERNMENT | MILITARY | POLICE) {
        (GOVERNMENT, INSURGENT)
    } else {
        (organization, INSURGENT)
    }
}

fn opponent_control(
    particle: &ParticleState,
    observer: usize,
    target: usize,
    locality: usize,
) -> (f64, f64, f64) {
    if target >= particle.organizations.kind.len() || particle.organizations.active[target] == 0 {
        return (0.0, 0.0, 0.0);
    }
    belief_triplet(particle, observer, target, locality, 2)
}

fn destination_score(
    particle: &ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    destination: usize,
    metric: &RouteMetric,
    maximum_population: f64,
    footholds: Option<&[f64]>,
    posture: Option<u8>,
) -> f64 {
    let organization = particle.formations.organization[formation] as usize;
    let (own_target, opponent_target) = target_pair(particle, organization);
    let (own_raw, own_control, own_confidence) =
        belief_triplet(particle, organization, own_target, destination, 1);
    let (opponent_raw, opponent_adjusted, opponent_confidence) =
        opponent_control(particle, organization, opponent_target, destination);
    let importance = particle.locality.population[destination] / maximum_population.max(1.0);
    let uncertainty = 1.0 - own_confidence.min(opponent_confidence);
    let intermediate = metric
        .route
        .iter()
        .skip(1)
        .take(metric.route.len().saturating_sub(2))
        .map(|locality| opponent_control(particle, organization, opponent_target, *locality).1)
        .collect::<Vec<_>>();
    let route_risk = if intermediate.is_empty() {
        0.0
    } else {
        python_sum(&intermediate) / intermediate.len() as f64
    };
    let phenotype_offset = organization * 8;
    let risk_tolerance = particle
        .organizations
        .phenotype
        .get(phenotype_offset + 4)
        .copied()
        .unwrap_or(0.5)
        .clamp(0.0, 1.0);
    let route_risk_penalty = (1.0 - risk_tolerance) * route_risk;
    let kind = particle
        .organizations
        .kind
        .get(organization)
        .copied()
        .unwrap_or(0);
    let strategic = if kind == 3 {
        let frontier = (1.0 - own_control) * (0.35 + 0.65 * (1.0 - opponent_adjusted));
        let foothold = footholds
            .and_then(|values| values.get(destination))
            .copied()
            .unwrap_or(0.0);
        let stronghold = own_control;
        let base = if posture.is_none() || posture == Some(POSTURE_PORTFOLIO) {
            config.logistics.insurgent_frontier_weight * frontier
                + config.logistics.insurgent_foothold_weight * foothold
                + config.logistics.insurgent_stronghold_weight * stronghold
                + config.logistics.reallocation_exploration_weight * uncertainty
        } else {
            match posture.unwrap() {
                POSTURE_FRONTIER => frontier,
                POSTURE_FOOTHOLD => foothold,
                POSTURE_STRONGHOLD => stronghold,
                POSTURE_EXPLORATION => uncertainty,
                _ => 0.0,
            }
        };
        // Sanctuary is not yet represented in the dense native state. The
        // default Pineland world has no sponsor sanctuary, so this is exactly
        // the Python value at the current certification boundary.
        base.clamp(0.0, 1.0)
    } else {
        let threatened_control = own_control * opponent_adjusted;
        let territorial_need = 1.0 - own_control * (1.0 - opponent_adjusted);
        let _gap = 1.0 - own_control;
        let _ = threatened_control;
        ((1.0 - config.logistics.reallocation_exploration_weight) * territorial_need
            + config.logistics.reallocation_exploration_weight * uncertainty)
            .clamp(0.0, 1.0)
    };
    let _ = (own_raw, opponent_raw);
    config.logistics.reallocation_strategic_weight * strategic
        + config.logistics.reallocation_importance_weight * importance
        - config.logistics.reallocation_travel_time_weight * metric.travel_hours
        - route_risk_penalty
}

fn command_metrics(particle: &ParticleState, organization: usize, formation: usize) -> (f64, f64) {
    for edge in 0..particle.command_edges.organization.len() {
        if particle.command_edges.organization[edge] as usize == organization
            && particle.command_edges.formation[edge] as usize == formation
        {
            return (
                particle.command_edges.reliability[edge].clamp(0.0, 1.0),
                particle.command_edges.latency_hours[edge].max(0.0),
            );
        }
    }
    (particle.formations.command[formation].clamp(0.0, 1.0), 0.0)
}

fn issue_reallocation_order(
    particle: &mut ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    destination: usize,
    time: f64,
    rng: &mut PyRandomCompat,
    metric: &RouteMetric,
) {
    let organization = particle.formations.organization[formation] as usize;
    let moving_personnel =
        particle.formations.personnel[formation] * particle.formations.availability[formation];
    let restriction_multiplier = 1.0;
    let travel_hours = metric.travel_hours * restriction_multiplier;
    let supply_cost = moving_personnel
        * metric.distance_km
        * config.logistics.movement_consumption_per_person_km
        * restriction_multiplier;
    let (reliability, latency_hours) = command_metrics(particle, organization, formation);
    let status = if rng.random() <= reliability {
        MOVE_PENDING
    } else {
        MOVE_FAILED_COMMAND
    };
    particle.movement_order_count = particle.movement_order_count.saturating_add(1);
    particle.formations.movement_destination[formation] = destination as u32;
    particle.formations.movement_origin[formation] = particle.formations.locality[formation];
    particle.formations.movement_execute_at[formation] = time + latency_hours / 24.0;
    particle.formations.movement_arrives_at[formation] = -1.0;
    particle.formations.movement_travel_hours[formation] = travel_hours;
    particle.formations.movement_distance_km[formation] = metric.distance_km;
    particle.formations.movement_supply_cost[formation] = supply_cost;
    particle.formations.movement_order_sequence[formation] = particle.movement_order_count;
    particle.formations.movement_status[formation] = status;
    particle.formations.movement_purpose[formation] = 0;
}

/// Execute pending and in-flight formation orders at a force-movement
/// boundary. No RNG is consumed: the command event owns all stochastic order
/// selection and success draws.
pub fn advance_movement_orders(particle: &mut ParticleState, topology: &StaticTopology, time: f64) {
    let mut order_indices = (0..particle.formations.personnel.len())
        .filter(|&formation| {
            matches!(
                particle.formations.movement_status[formation],
                MOVE_PENDING | MOVE_MOVING
            )
        })
        .collect::<Vec<_>>();
    order_indices.sort_by_key(|&formation| particle.formations.movement_order_sequence[formation]);

    for formation in order_indices {
        if particle.formations.movement_status[formation] == MOVE_PENDING
            && particle.formations.movement_execute_at[formation] <= time
        {
            let withdrawal = particle.formations.movement_purpose[formation] == 1;
            if particle.formations.moving[formation] != 0
                || particle.formations.outside_pineland[formation] != 0
                || particle.formations.personnel[formation] <= 0.0
                || (!withdrawal
                    && (particle.formations.operational_status[formation] != 1
                        || particle.formations.deployable_personnel(formation) <= 0.0))
            {
                particle.formations.movement_status[formation] = MOVE_BLOCKED_UNAVAILABLE;
                continue;
            }
            let cost = particle.formations.movement_supply_cost[formation];
            if particle.formations.supply_stock[formation] + 1.0e-12 < cost {
                particle.formations.movement_status[formation] = MOVE_BLOCKED_SUPPLY;
                continue;
            }
            let consumed = cost
                .max(0.0)
                .min(particle.formations.supply_stock[formation]);
            particle.formations.supply_stock[formation] -= consumed;
            particle.formations.sustainment[formation] =
                particle.formations.supply_fraction(formation);
            particle.logistics.cumulative_consumed += consumed;
            particle.formations.moving[formation] = 1;
            particle.formations.movement_status[formation] = MOVE_MOVING;
            let arrives_at = time + particle.formations.movement_travel_hours[formation] / 24.0;
            particle.formations.movement_arrives_at[formation] = arrives_at;
            if let Some(patrol) = patrol_for_formation(particle, formation) {
                particle.patrols.next_available[patrol] = arrives_at;
                particle.patrols.response_fraction[patrol] = 0.0;
                particle.patrols.presence_accounted_at[patrol] = arrives_at;
            }
        }

        if particle.formations.movement_status[formation] == MOVE_MOVING
            && particle.formations.movement_arrives_at[formation] <= time
        {
            let destination = particle.formations.movement_destination[formation] as usize;
            if destination >= topology.locality_count() {
                particle.formations.movement_status[formation] = MOVE_BLOCKED_UNAVAILABLE;
                particle.formations.moving[formation] = 0;
                continue;
            }
            particle.formations.moving[formation] = 0;
            particle.formations.locality[formation] = destination as u32;
            particle.formations.fatigue[formation] = clamp01(
                particle.formations.fatigue[formation]
                    + 0.015 * particle.formations.movement_travel_hours[formation] / 24.0,
            );
            particle.formations.readiness[formation] = clamp01(
                particle.formations.readiness[formation]
                    - 0.01 * particle.formations.movement_travel_hours[formation] / 24.0,
            );
            particle.formations.availability[formation] =
                clamp01(particle.formations.availability[formation] - 0.05);
            let destination_zone = modal_zone(topology, destination);
            particle.formations.microzone[formation] = destination_zone as u32;
            if let Some(patrol) = patrol_for_formation(particle, formation) {
                particle.patrols.route_position[patrol] = destination_zone as u32;
                particle.patrols.route_target[patrol] = destination_zone as u32;
                particle.patrols.last_departure[patrol] = time;
                particle.patrols.next_available[patrol] = time;
                particle.patrols.response_fraction[patrol] = 0.3;
                particle.patrols.presence_accounted_at[patrol] = time;
            }
            particle.formations.movement_status[formation] = MOVE_ARRIVED;
        }
    }
}

fn patrol_for_formation(particle: &ParticleState, formation: usize) -> Option<usize> {
    particle
        .patrols
        .formation
        .iter()
        .position(|&candidate| candidate as usize == formation)
}

fn modal_zone(topology: &StaticTopology, locality: usize) -> usize {
    let mut selected = topology.primary_zone[locality] as usize;
    let mut selected_share = f64::NEG_INFINITY;
    for zone in topology.zones_for_locality(locality.into()) {
        let share = topology.zone_population_share[zone];
        if share > selected_share {
            selected = zone;
            selected_share = share;
        }
    }
    selected
}
