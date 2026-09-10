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
    time: f64,
    elapsed_days: f64,
) {
    // This is the representative-person implementation of the Python
    // on_mobility handler.  Mobility is a stochastic transition over the
    // person rows, not an aggregate displacement stock update.  Keeping the
    // loop and draw order here is important: a skipped representative must
    // not consume a draw that the oracle would not consume.
    if elapsed_days <= 0.0 {
        return;
    }

    let dynamics = &config.civilian_dynamics;
    let voluntary_probability = reference_probability(
        (config.movement_rate * dynamics.voluntary_move_given_opportunity).clamp(0.0, 1.0),
        elapsed_days,
        1.0,
    );

    let people_count = particle.people.locality.len();
    let locality_count = topology.locality_count();
    let mut displaced_by_origin = vec![0.0; locality_count];
    let trace_all =
        std::env::var_os("PINELAND_MOBILITY_TRACE_ALL").is_some() && (time - 67.0).abs() < 1.0e-9;

    for person in 0..people_count {
        if particle.people.external_state[person] != u32::MAX
            || particle.people.represented_population[person] <= 0.0
        {
            continue;
        }
        let origin = particle.people.residence[person] as usize;
        if origin >= locality_count {
            continue;
        }
        let neighbors = topology
            .locality_edges
            .neighbors(origin)
            .collect::<Vec<_>>();
        if neighbors.is_empty() {
            continue;
        }

        if trace_all {
            eprintln!(
                "MOBILITY_BEGIN person={} origin={} home={} displaced={} count={} since={:.17}",
                person,
                origin,
                particle.people.home[person],
                particle.people.displaced[person],
                particle.people.displacement_count[person],
                particle.people.displaced_since[person],
            );
        }

        // The current baseline has no displaced-since field in the packed
        // native schema.  The return branch is nevertheless represented for
        // checkpoints imported from a state that carries the displacement
        // flag; its first-order behavior is exact for the available state.
        if particle.people.displaced[person] != 0 {
            let home = particle.people.home[person] as usize;
            if home == origin {
                particle.people.displaced[person] = 0;
                particle.people.displaced_since[person] = -1.0;
                particle.people.displacement_origin[person] = u32::MAX;
            } else {
                let home_belief = person_expected_control(particle, person, home);
                let return_probability = reference_probability(
                    (dynamics.return_reference_rate * (0.5 + 0.5 * home_belief)).clamp(0.0, 1.0),
                    elapsed_days,
                    1.0,
                );
                let return_draw = rng.random();
                if trace_all {
                    eprintln!(
                        "MOBILITY_RETURN person={} draw={:.17} probability={:.17}",
                        person, return_draw, return_probability
                    );
                }
                if return_draw < return_probability {
                    // The Python route-aware return takes the first locality
                    // on the shortest path.  For the common adjacent return
                    // case this is the home locality itself; a full route
                    // fallback is supplied below for non-adjacent homes.
                    let destination = first_locality_step(particle, topology, origin, home);
                    if let Some(destination) = destination {
                        if destination != origin {
                            relocate_person(particle, person, destination);
                            if destination == home {
                                particle.people.displaced[person] = 0;
                                particle.people.displaced_since[person] = -1.0;
                                particle.people.displacement_origin[person] = u32::MAX;
                            }
                            continue;
                        }
                    }
                }
                // Resettlement requires the Python displaced-since timestamp,
                // which is intentionally not inferred from a boolean flag.
                // It therefore cannot fire in the packed v1 state.
            }
        }

        let violence = particle.locality.violence[origin];
        let violence_pressure = ((violence - dynamics.displacement_violence_threshold)
            / (1.0 - dynamics.displacement_violence_threshold).max(1.0e-12))
        .clamp(0.0, 1.0);
        let access_pressure = crate::access::locality_access_pressure(particle, topology, origin);
        let forced_probability = reference_probability(
            (dynamics.forced_displacement_reference_rate * violence_pressure.max(access_pressure))
                .clamp(0.0, 1.0),
            elapsed_days,
            1.0,
        );
        let forced_draw = rng.random();
        let forced = forced_draw < forced_probability;
        let voluntary_draw = if forced { None } else { Some(rng.random()) };
        let voluntary = !forced && voluntary_draw.is_some_and(|draw| draw < voluntary_probability);
        if trace_all {
            eprintln!(
                "MOBILITY_DECISION person={} forced_draw={:.17} forced_probability={:.17} voluntary_draw={:?} voluntary_probability={:.17} forced={} voluntary={}",
                person,
                forced_draw,
                forced_probability,
                voluntary_draw,
                voluntary_probability,
                forced,
                voluntary,
            );
        }
        if !forced && !voluntary {
            continue;
        }

        let mut candidates = Vec::with_capacity(neighbors.len());
        let mut utilities = Vec::with_capacity(neighbors.len());
        for (destination, edge_cost) in neighbors {
            let destination = destination as usize;
            let security = destination_expected_control(particle, person, destination);
            let livelihood = (particle.locality.economic_output[destination]
                / particle.locality.population[destination].max(1.0))
            .max(2.0)
            .ln();
            let restriction =
                crate::access::edge_restriction_level(particle, origin, destination, None);
            let utility = 1.2 * security + 0.1 * livelihood
                - edge_cost
                - config.access_restriction.civilian_utility_penalty * restriction;
            candidates.push(destination);
            utilities.push(python_exp(utility.clamp(-10.0, 10.0)));
        }
        if candidates.is_empty() {
            continue;
        }
        let selected = rng
            .choices_indices(candidates.len(), Some(&utilities), 1)
            .expect("civilian mobility weighted choice failed")[0];
        let destination = candidates[selected];
        if trace_all {
            eprintln!(
                "MOBILITY_CHOICE person={} destination={} candidates={:?} utilities={:?}",
                person, destination, candidates, utilities
            );
        }
        if std::env::var_os("PINELAND_MOBILITY_TRACE").is_some() {
            eprintln!(
                "MOBILITY_PERSON time={:.17} person={} origin={}({}) destination={}({}) forced={} voluntary={} forced_draw={:.17} forced_probability={:.17} voluntary_draw={:?} voluntary_probability={:.17} candidates={:?} utilities={:?}",
                time,
                person,
                origin,
                topology.locality_names.get(origin).map(String::as_str).unwrap_or("?"),
                destination,
                topology.locality_names.get(destination).map(String::as_str).unwrap_or("?"),
                forced,
                voluntary,
                forced_draw,
                forced_probability,
                voluntary_draw,
                voluntary_probability,
                candidates,
                utilities,
            );
            for (candidate, (_, edge_cost)) in candidates
                .iter()
                .copied()
                .zip(topology.locality_edges.neighbors(origin))
            {
                eprintln!(
                    "MOBILITY_CANDIDATE person={} locality={}({}) edge_cost={:.17}",
                    person,
                    candidate,
                    topology
                        .locality_names
                        .get(candidate)
                        .map(String::as_str)
                        .unwrap_or("?"),
                    edge_cost,
                );
            }
        }
        relocate_person(particle, person, destination);

        let weight = particle.people.represented_population[person];
        if forced && destination != particle.people.home[person] as usize {
            if particle.people.displaced[person] == 0 {
                particle.people.displaced_since[person] = time;
                particle.people.displacement_origin[person] = origin as u32;
                particle.people.displacement_count[person] =
                    particle.people.displacement_count[person].saturating_add(1);
            }
            particle.people.displaced[person] = 1;
            if destination < displaced_by_origin.len() {
                displaced_by_origin[origin] += weight;
            }
        } else if destination == particle.people.home[person] as usize {
            particle.people.displaced[person] = 0;
            particle.people.displaced_since[person] = -1.0;
            particle.people.displacement_origin[person] = u32::MAX;
        }
    }

    // Python stores displaced population as a stock derived from all
    // displaced representatives currently resident in each locality.
    particle.locality.displaced_population.fill(0.0);
    for person in 0..people_count {
        if particle.people.external_state[person] != u32::MAX
            || particle.people.displaced[person] == 0
        {
            continue;
        }
        let locality = particle.people.residence[person] as usize;
        if locality < particle.locality.displaced_population.len() {
            particle.locality.displaced_population[locality] +=
                particle.people.represented_population[person];
        }
    }

    // Keep the explicit household residence equal to the represented-mass
    // majority after person-level moves.  Python's tie-break is the greatest
    // locality identifier; native locality IDs are the same lexicographic
    // order used by the canonical registry.
    for household in 0..particle.households.residence.len() {
        let start = particle.households.member_offsets[household] as usize;
        let end = particle.households.member_offsets[household + 1] as usize;
        let mut masses = vec![0.0; locality_count];
        for &person in &particle.households.member_indices[start..end] {
            let person = person as usize;
            let locality = particle.people.residence[person] as usize;
            if particle.people.external_state[person] != u32::MAX {
                continue;
            }
            if locality < masses.len() && particle.people.represented_population[person] > 0.0 {
                masses[locality] += particle.people.represented_population[person];
            }
        }
        let mut best = None;
        for (locality, mass) in masses.into_iter().enumerate() {
            if mass <= 0.0 {
                continue;
            }
            if best
                .map(|(best_locality, best_mass)| {
                    mass > best_mass || (mass == best_mass && locality > best_locality)
                })
                .unwrap_or(true)
            {
                best = Some((locality, mass));
            }
        }
        if let Some((locality, _)) = best {
            particle.households.residence[household] = locality as u32;
        }
    }

    // The native state does not yet carry Python's cumulative harm ledger.
    // Keep the local displacement stock authoritative; the ledger is added in
    // the cross-engine checkpoint schema before the historical contract is
    // frozen.
    let _ = (time, displaced_by_origin);
}

fn reference_probability(probability: f64, elapsed_days: f64, reference_days: f64) -> f64 {
    let probability = probability.clamp(0.0, 1.0);
    if probability <= 0.0 || elapsed_days <= 0.0 {
        0.0
    } else if probability >= 1.0 {
        1.0
    } else {
        1.0 - (1.0 - probability).powf(elapsed_days / reference_days.max(1.0e-12))
    }
}

fn person_expected_control(particle: &ParticleState, person: usize, locality: usize) -> f64 {
    let locality_count = particle.locality.population.len();
    let mask_index = person
        .checked_mul(locality_count)
        .and_then(|value| value.checked_add(locality));
    if let Some(mask_index) = mask_index {
        let value_index = mask_index * 2;
        if particle
            .people
            .expected_destination_control_present
            .get(mask_index)
            .copied()
            .unwrap_or(0)
            & 1
            != 0
        {
            return particle
                .people
                .expected_destination_control
                .get(value_index)
                .copied()
                .unwrap_or(0.5)
                .clamp(0.0, 1.0);
        }
    }
    particle.people.expected_control[person * 2].clamp(0.0, 1.0)
}

fn destination_expected_control(
    particle: &ParticleState,
    person: usize,
    destination: usize,
) -> f64 {
    person_expected_control(particle, person, destination)
}

fn relocate_person(particle: &mut ParticleState, person: usize, destination: usize) {
    particle.people.locality[person] = destination as u32;
    particle.people.residence[person] = destination as u32;
}

fn first_locality_step(
    particle: &ParticleState,
    topology: &StaticTopology,
    origin: usize,
    destination: usize,
) -> Option<usize> {
    if origin == destination {
        return Some(origin);
    }
    all_route_metrics(particle, topology, origin, 1.0)
        .get(destination)
        .and_then(|metric| metric.as_ref())
        .and_then(|metric| metric.route.get(1).copied())
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
    let mut formation_order: Vec<usize> = (0..formation_count).collect();
    formation_order.sort_by(|&a, &b| {
        let name_a = crate::information::formation_name(particle, a);
        let name_b = crate::information::formation_name(particle, b);
        name_a.cmp(&name_b)
    });
    for formation in formation_order {
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
        let decision_draw = rng.random();
        if std::env::var_os("PINELAND_COMMAND_TRACE").is_some() && time >= 9.99 {
            eprintln!(
                "COMMAND_FORMATION index={} time={:.17} decision_draw={:.17} threshold={:.17} posture_before={} locality={} availability={:.17} status={} moving={} order_status={}",
                formation,
                time,
                decision_draw,
                decision_probability,
                particle.formations.operational_posture[formation],
                particle.formations.locality[formation],
                particle.formations.availability[formation],
                particle.formations.operational_status[formation],
                particle.formations.moving[formation],
                particle.formations.movement_status[formation],
            );
        }
        if decision_draw >= decision_probability {
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
        if std::env::var_os("PINELAND_COMMAND_TRACE").is_some() && time >= 9.99 {
            eprintln!(
                "COMMAND_SELECTED index={} posture={} candidates_pending",
                formation,
                posture.unwrap_or(POSTURE_PORTFOLIO),
            );
        }
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
            if std::env::var_os("PINELAND_COMMAND_CANDIDATE_TRACE").is_some()
                && ((formation == 5 && (time - 27.0).abs() < 1.0e-12)
                    || (formation == 18 && (time - 42.0).abs() < 1.0e-12))
            {
                eprintln!(
                    "COMMAND_CANDIDATE destination={} score={:.17} travel_hours={:.17} distance_km={:.17} own_control={:.17} opponent_control={:.17} uncertainty={:.17}",
                    destination,
                    score,
                    metric.travel_hours,
                    metric.distance_km,
                    belief_triplet(particle, organization, target_pair(particle, organization).0, destination, 1).1,
                    opponent_control(particle, organization, target_pair(particle, organization).1, destination).1,
                    1.0 - belief_triplet(particle, organization, target_pair(particle, organization).0, destination, 1).2.min(
                        opponent_control(particle, organization, target_pair(particle, organization).1, destination).2,
                    ),
                );
            }
            candidates.push(destination);
            utilities.push(python_exp(score.clamp(-8.0, 8.0)));
        }
        if candidates.is_empty() {
            continue;
        }
        let selected = rng.choices_indices(candidates.len(), Some(&utilities), 1)?[0];
        let destination = candidates[selected];
        if std::env::var_os("PINELAND_COMMAND_TRACE").is_some() && time >= 9.99 {
            eprintln!(
                "COMMAND_DESTINATION index={} destination={} origin={} candidates={} selected={}",
                formation,
                destination,
                origin,
                candidates.len(),
                selected,
            );
        }
        if destination == origin {
            continue;
        }
        issue_movement_order(
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
            0,
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
                if (node == 11 && neighbor == 3 || node == 3 && neighbor == 10) && std::env::var_os("PINELAND_COMMAND_TRACE").is_some() {
                    eprintln!("LEG_DEBUG node={} neighbor={} leg_dist={:.17} bits={:x} dist_neighbor={:.17} bits={:x}", node, neighbor, leg_distance, leg_distance.to_bits(), distances[neighbor], distances[neighbor].to_bits());
                }
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
        if destination == 10 && origin == 11 && std::env::var_os("PINELAND_COMMAND_TRACE").is_some() {
            eprintln!(
                "DEBUG_METRIC_11_10 distance={:.17} bits={:x}",
                distances[destination],
                distances[destination].to_bits(),
            );
        }
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
        // Python's persistent local-foothold channel is insurgent-only.
        // State-side actions can still mark a security organization's dense
        // foothold row active for diagnostics, but that row must not become a
        // refuge signal for military or police movement.
        if organization == INSURGENT && index < particle.footholds.strength.len() {
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

/// Issue a movement order in the compact native order representation.
/// `purpose == 1` is a withdrawal; all other purposes use ordinary execution
/// eligibility at the force-movement boundary.
fn issue_movement_order(
    particle: &mut ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    destination: usize,
    time: f64,
    rng: &mut PyRandomCompat,
    metric: &RouteMetric,
    purpose: u8,
) {
    let organization = particle.formations.organization[formation] as usize;
    let moving_personnel =
        particle.formations.personnel[formation] * particle.formations.availability[formation];
    let restriction =
        crate::access::route_restriction_level(particle, &metric.route, Some(organization));
    let restriction_multiplier =
        1.0 + config.access_restriction.hostile_movement_penalty * restriction;
    let travel_hours = metric.travel_hours * restriction_multiplier;
    let supply_cost = moving_personnel
        * metric.distance_km
        * config.logistics.movement_consumption_per_person_km
        * restriction_multiplier;
    let (reliability, latency_hours) = command_metrics(particle, organization, formation);
    let command_draw = rng.random();
    let status = if command_draw <= reliability {
        MOVE_PENDING
    } else {
        MOVE_FAILED_COMMAND
    };
    if std::env::var_os("PINELAND_COMMAND_TRACE").is_some() {
        eprintln!(
            "COMMAND_ORDER time={:.17} index={} destination={} reliability={:.17} status_draw={:.17} status={} purpose={} distance_km={:.17} travel_hours={:.17} supply_cost={:.17} route={:?}",
            time, formation, destination, reliability, command_draw, status, purpose,
            metric.distance_km, metric.travel_hours, supply_cost, metric.route,
        );
    }
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
    particle.formations.movement_purpose[formation] = purpose;
}

/// Reproduce Python's post-disengagement refuge choice.  The choice is
/// deterministic conditional on the current decision state; only the final
/// command-reliability draw is stochastic.
pub(crate) fn issue_withdrawal_order(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    time: f64,
    rng: &mut PyRandomCompat,
) -> bool {
    if formation >= particle.formations.personnel.len()
        || particle.formations.moving[formation] != 0
        || particle.formations.outside_pineland[formation] != 0
        || particle.formations.personnel[formation] <= 0.0
        || has_active_order(particle, formation)
    {
        return false;
    }
    let origin = particle.formations.locality[formation] as usize;
    let mobility = particle.formations.mobility[formation].max(0.05);
    let route_metrics = all_route_metrics(particle, topology, origin, mobility);
    let organization = particle.formations.organization[formation] as usize;
    let footholds = local_armed_footholds(particle, topology, organization, config);
    let (own_target, opponent_target) = target_pair(particle, organization);
    let phenotype_offset = organization * 8;
    let risk_tolerance = particle
        .organizations
        .phenotype
        .get(phenotype_offset + 4)
        .copied()
        .unwrap_or(0.5)
        .clamp(0.0, 1.0);
    let mut best: Option<(f64, usize)> = None;
    for destination in 0..topology.locality_count() {
        if destination == origin {
            continue;
        }
        let Some(metric) = route_metrics.get(destination).and_then(Option::as_ref) else {
            continue;
        };
        let moving_personnel = particle.formations.personnel[formation]
            * particle.formations.availability[formation].clamp(0.0, 1.0);
        let movement_cost = moving_personnel
            * metric.distance_km
            * config.logistics.movement_consumption_per_person_km;
        if movement_cost > particle.formations.supply_stock[formation] + 1.0e-12 {
            continue;
        }
        let (_, own_control, own_confidence) =
            belief_triplet(particle, organization, own_target, destination, 1);
        let (_, opponent_adjusted, opponent_confidence) =
            opponent_control(particle, organization, opponent_target, destination);
        let uncertainty = 1.0 - own_confidence.min(opponent_confidence);
        let refuge = 0.45 * own_control
            + 0.30 * (1.0 - opponent_adjusted)
            + 0.20 * footholds.get(destination).copied().unwrap_or(0.0)
            + 0.05 * uncertainty;
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
        let sanctuary = 0.0;
        let score = 2.2 * refuge + 1.6 * sanctuary
            - 0.04 * metric.travel_hours
            - (1.0 - risk_tolerance) * route_risk;
        if std::env::var_os("PINELAND_WITHDRAWAL_TRACE").is_some()
            && formation == 5
            && (time - 28.0).abs() < 1.0e-12
        {
            eprintln!(
                "WITHDRAWAL_CANDIDATE destination={} score={:.17} own_control={:.17} own_confidence={:.17} opponent_control={:.17} opponent_confidence={:.17} foothold={:.17} uncertainty={:.17} route_risk={:.17} travel_hours={:.17} movement_cost={:.17}",
                destination,
                score,
                own_control,
                own_confidence,
                opponent_adjusted,
                opponent_confidence,
                footholds.get(destination).copied().unwrap_or(0.0),
                uncertainty,
                route_risk,
                metric.travel_hours,
                movement_cost,
            );
        }
        if best
            .map(|(best_score, best_destination)| {
                score > best_score || (score == best_score && destination > best_destination)
            })
            .unwrap_or(true)
        {
            best = Some((score, destination));
        }
    }
    let Some((_, destination)) = best else {
        return false;
    };
    if std::env::var_os("PINELAND_WITHDRAWAL_TRACE").is_some()
        && formation == 5
        && (time - 28.0).abs() < 1.0e-12
    {
        eprintln!("WITHDRAWAL_SELECTED destination={}", destination);
    }
    let metric = route_metrics[destination]
        .as_ref()
        .expect("selected withdrawal destination has a route");
    issue_movement_order(
        particle,
        topology,
        config,
        formation,
        destination,
        time,
        rng,
        metric,
        1,
    );
    true
}

/// Reproduce Python's deterministic reinforcement candidate selection and
/// materialize the resulting order when the loss threshold is crossed.
pub(crate) fn issue_reinforcement_order(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    formation: usize,
    loss_fraction: f64,
    time: f64,
    rng: &mut PyRandomCompat,
) -> bool {
    if formation >= particle.formations.personnel.len()
        || loss_fraction < config.combat.reinforcement_threshold
    {
        return false;
    }
    let organization = particle.formations.organization[formation] as usize;
    let origin = particle.formations.locality[formation] as usize;
    let mut best: Option<(f64, usize)> = None;
    for candidate in 0..particle.formations.personnel.len() {
        if candidate == formation
            || particle.formations.organization[candidate] as usize != organization
            || particle.formations.moving[candidate] != 0
            || particle.formations.outside_pineland[candidate] != 0
            || particle.formations.personnel[candidate] <= 0.0
            || particle.formations.deployable_personnel(candidate) <= 0.0
            || particle.formations.locality[candidate] as usize == origin
            || particle.formations.operational_status[candidate] != 1
        {
            continue;
        }
        let effectiveness = particle.formations.personnel[candidate]
            * particle.formations.availability[candidate].clamp(0.0, 1.0)
            * particle.formations.quality[candidate]
            * particle.formations.cohesion[candidate]
            * particle.formations.effective_readiness(candidate);
        if best
            .map(|(best_effectiveness, _)| effectiveness > best_effectiveness)
            .unwrap_or(true)
        {
            best = Some((effectiveness, candidate));
        }
    }
    let Some((_, candidate)) = best else {
        return false;
    };
    let route_metrics = all_route_metrics(
        particle,
        topology,
        particle.formations.locality[candidate] as usize,
        particle.formations.mobility[candidate],
    );
    let Some(metric) = route_metrics.get(origin).and_then(Option::as_ref) else {
        return false;
    };
    issue_movement_order(
        particle, topology, config, candidate, origin, time, rng, metric, 0,
    );
    true
}

/// Execute pending and in-flight formation orders at a force-movement
/// boundary. No RNG is consumed: the command event owns all stochastic order
/// selection and success draws.
pub fn advance_movement_orders(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    time: f64,
) -> Vec<usize> {
    let mut arrived_formations = Vec::new();
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
            arrived_formations.push(formation);
        }
    }
    arrived_formations
}

fn patrol_for_formation(particle: &ParticleState, formation: usize) -> Option<usize> {
    particle
        .patrols
        .formation
        .iter()
        .enumerate()
        .find(|(patrol, candidate)| {
            **candidate as usize == formation
                && particle.patrols.active.get(*patrol).copied().unwrap_or(0) != 0
        })
        .map(|(patrol, _)| patrol)
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
