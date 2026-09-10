//! Recruitment, local manpower pools, and foothold renewal.
//!
//! The Python implementation treats a representative person as a fractional
//! cohort. This module keeps that same contract in the native state: draws
//! are made per available sub-cohort, fighter equivalents are converted from
//! represented membership, and a local pool is equipped before it can become
//! a formation. The ordering and arithmetic are part of the parity
//! certificate.

use pineland_core::config::SimulationConfig;
use pineland_core::ids::LocalityId;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

const KIND_INSURGENT: u8 = 3;
const NO_ORGANIZATION: u32 = u32::MAX;
const BEHAVIOR_INSURGENT_SYMPATHY: u8 = 1;
const BEHAVIOR_ARMED_PARTICIPATION: u8 = 2;
const BEHAVIOR_GOVERNMENT_COOPERATION: u8 = 3;
const BEHAVIOR_PROTEST: u8 = 6;

#[derive(Clone, Copy)]
struct Candidate {
    organization: usize,
    intensity: f64,
    compatibility: f64,
}

fn logistic(value: f64) -> f64 {
    1.0 / (1.0 + python_exp(-value))
}

fn behavior_score(behavior: u8) -> (f64, f64) {
    match behavior {
        BEHAVIOR_GOVERNMENT_COOPERATION => (1.0, 0.0),
        4 => (0.25, 0.0),
        5 => (0.15, 0.0),
        BEHAVIOR_PROTEST => (-0.15, 0.1),
        BEHAVIOR_INSURGENT_SYMPATHY => (-0.4, 0.7),
        BEHAVIOR_ARMED_PARTICIPATION => (-0.7, 1.0),
        _ => (0.0, 0.0),
    }
}

#[allow(dead_code)]
fn social_exposure(
    particle: &ParticleState,
    person: usize,
    active_insurgents: &[usize],
    active_mask: &[bool],
) -> Vec<f64> {
    let organization_count = particle.organizations.kind.len();
    let mut signal_by_org = vec![0.0; organization_count];
    let mut total_signal = 0.0;
    let mut total_weight = 0.0;
    let start = particle.social_edges.neighbor_offsets[person] as usize;
    let end = particle.social_edges.neighbor_offsets[person + 1] as usize;
    for neighbor_value in &particle.social_edges.neighbor_indices[start..end] {
        let neighbor = *neighbor_value as usize;
        let edge_index = (0..particle.social_edges.person_a.len()).find(|edge| {
            let first = particle.social_edges.person_a[*edge] as usize;
            let second = particle.social_edges.person_b[*edge] as usize;
            (first == person && second == neighbor) || (first == neighbor && second == person)
        });
        let Some(edge) = edge_index else { continue };
        let influence = particle.social_edges.weight[edge]
            * particle.social_edges.trust[edge]
            * particle.social_edges.represented_relationships[edge];
        let (_, mut neighbor_insurgent) = behavior_score(particle.people.public_behavior[neighbor]);
        let neighbor_organization = particle.people.organization[neighbor];
        if neighbor_organization != NO_ORGANIZATION
            && (neighbor_organization as usize) < organization_count
            && active_mask[neighbor_organization as usize]
        {
            // Python uses max(armed_fraction, behavior_signal * armed_fraction)
            // for an active armed member.
            neighbor_insurgent = particle.people.armed_fraction[neighbor]
                .max(neighbor_insurgent * particle.people.armed_fraction[neighbor]);
            let organization = neighbor_organization as usize;
            signal_by_org[organization] += influence * neighbor_insurgent;
        } else if neighbor_insurgent > 0.0 && !active_insurgents.is_empty() {
            let mut affinity_total = 0.0;
            for organization in active_insurgents {
                let value = particle.people.insurgent_affinity
                    [neighbor * organization_count + *organization];
                if value > 0.0 {
                    affinity_total += value;
                }
            }
            if affinity_total > 0.0 {
                for organization in active_insurgents {
                    let value = particle.people.insurgent_affinity
                        [neighbor * organization_count + *organization];
                    if value > 0.0 {
                        signal_by_org[*organization] +=
                            influence * neighbor_insurgent * value / affinity_total;
                    }
                }
            }
        }
        if active_insurgents.is_empty() {
            neighbor_insurgent = 0.0;
        }
        total_signal += influence * neighbor_insurgent;
        total_weight += influence;
    }
    if total_weight != 0.0 {
        total_signal /= total_weight;
        for organization in active_insurgents {
            signal_by_org[*organization] /= total_weight;
        }
    }
    if active_insurgents.len() == 1 {
        signal_by_org[active_insurgents[0]] = total_signal;
    }
    signal_by_org
}

fn language_compatibility(
    particle: &ParticleState,
    person: usize,
    profile: Option<[f64; 4]>,
) -> f64 {
    let Some(profile) = profile else { return 1.0 };
    let offset = person * 4;
    let mut result: f64 = 0.0;
    for language in 0..4 {
        result = result.max(particle.people.languages[offset + language].min(profile[language]));
    }
    clamp01(result)
}

fn access_language_factor(
    particle: &ParticleState,
    person: usize,
    profile: Option<[f64; 4]>,
) -> f64 {
    0.35 + 0.65 * language_compatibility(particle, person, profile)
}

fn rootedness(
    particle: &ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
) -> (f64, f64, f64) {
    let target_district = topology.locality_to_district[locality] as usize;
    let mut represented_local = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.residence[person] as usize != locality
            || particle.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        if represented <= 0.0 {
            continue;
        }
        represented_local += represented;
        if particle.people.home[person] as usize == locality {
            home_local += represented;
        }
        if topology
            .locality_to_district
            .get(particle.people.home[person] as usize)
            .copied()
            .unwrap_or(u32::MAX) as usize
            == target_district
        {
            home_district += represented;
        }
    }
    if represented_local <= 1.0e-12 {
        (0.0, 0.0, 0.0)
    } else {
        (
            represented_local,
            clamp01(home_local / represented_local),
            clamp01(home_district / represented_local),
        )
    }
}

fn local_profile(
    particle: &ParticleState,
    organization: usize,
    locality: Option<usize>,
) -> Option<[f64; 4]> {
    let mut mass = 0.0;
    let mut totals = [0.0; 4];
    for person in 0..particle.people.locality.len() {
        if particle.people.organization[person] as usize != organization
            || particle.people.armed_fraction[person] <= 0.0
            || locality.is_some_and(|value| particle.people.residence[person] as usize != value)
        {
            continue;
        }
        let represented =
            particle.people.represented_population[person] * particle.people.armed_fraction[person];
        mass += represented;
        let offset = person * 4;
        for language in 0..4 {
            totals[language] += represented * particle.people.languages[offset + language];
        }
    }
    if mass <= 1.0e-12 {
        None
    } else {
        Some(totals.map(|value| value / mass))
    }
}

fn record_foothold_recruitment(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    organization: usize,
    locality: usize,
    represented_mass: f64,
) {
    let index = organization * topology.locality_count() + locality;
    if index >= particle.footholds.cumulative_recruits.len() {
        return;
    }
    particle.footholds.cumulative_recruits[index] += represented_mass.max(0.0);
    particle.footholds.renewal_count[index] =
        particle.footholds.renewal_count[index].saturating_add(1);
    particle.footholds.embeddedness[index] = particle.footholds.strength[index];
}

fn find_manpower(particle: &ParticleState, organization: usize, locality: usize) -> Option<usize> {
    (0..particle.manpower.pool.len()).find(|index| {
        particle.manpower.organization[*index] as usize == organization
            && particle.manpower.locality[*index] as usize == locality
    })
}

fn ensure_manpower(particle: &mut ParticleState, organization: usize, locality: usize) -> usize {
    if let Some(index) = find_manpower(particle, organization, locality) {
        return index;
    }
    particle.manpower.organization.push(organization as u32);
    particle.manpower.locality.push(locality as u32);
    particle.manpower.pool.push(0.0);
    particle.manpower.supply_reserve.push(0.0);
    particle.manpower.pool.len() - 1
}

fn resize_formation(particle: &mut ParticleState, config: &SimulationConfig, formation: usize) {
    let doctrinal = (particle.formations.personnel[formation]
        * config.logistics.formation_supply_days)
        .max(0.0);
    particle.formations.supply_capacity[formation] =
        doctrinal.max(particle.formations.supply_stock[formation]);
    particle.formations.sustainment[formation] =
        if particle.formations.supply_capacity[formation] > 0.0 {
            clamp01(
                particle.formations.supply_stock[formation]
                    / particle.formations.supply_capacity[formation],
            )
        } else {
            0.0
        };
}

fn shift_dynamic_code(value: &mut u32, threshold: u32) {
    // Codes below 0x2000_0000 are the canonical organization/formation/
    // post/auxiliary/command ranges.  0x2000_0000..0x3fff_ffff is reserved
    // for stable hashed patrol source identities; those identities must not
    // be reindexed when a formation is appended.  Fallback hashes use the
    // separate 0x4000_0000 namespace and are likewise excluded.
    if *value != u32::MAX && *value >= threshold && *value < 0x2000_0000 {
        *value = value.saturating_add(1);
    }
}

/// Appending an organization moves the numeric base of every existing
/// dynamic observer by one.  Kind-3 belief rows are the only belief rows in
/// that namespace; actor-level rows for the existing organization registry
/// (including observer 7, the aggregate insurgent actor) must remain fixed.
pub(crate) fn shift_dynamic_observer_codes_after_organization(
    particle: &mut ParticleState,
    old_organizations: usize,
) {
    let threshold = old_organizations as u32;
    for key in &mut particle.beliefs.keys {
        if key.kind == 3 {
            shift_dynamic_code(&mut key.observer, threshold);
        }
    }
    for state in [
        &mut particle.presence_beliefs,
        &mut particle.node_presence_beliefs,
    ] {
        for key in &mut state.keys {
            shift_dynamic_code(&mut key.observer, threshold);
        }
    }
    for observation in &mut particle.information_observations {
        shift_dynamic_code(&mut observation.source, threshold);
        shift_dynamic_code(&mut observation.observer_node, threshold);
        shift_dynamic_code(&mut observation.source_identity, threshold);
    }
    for relay in &mut particle.information_relays {
        shift_dynamic_code(&mut relay.source_node, threshold);
        shift_dynamic_code(&mut relay.destination_node, threshold);
        for node in &mut relay.route {
            shift_dynamic_code(node, threshold);
        }
    }
    for entry in &mut particle.information_history {
        shift_dynamic_code(&mut entry.source_identity, threshold);
    }
}

/// Dynamic observer codes reserve the formation range first, followed by
/// posts, auxiliary nodes, and command nodes. Appending a formation therefore
/// shifts every already-materialized node after the old formation range. The
/// Python certificate recomputes that canonical code from the final registry;
/// native continuation state must perform the same re-indexing at the append
/// boundary.
pub(crate) fn shift_dynamic_observer_codes(particle: &mut ParticleState, old_formations: usize) {
    let threshold = (particle.organizations.kind.len() + old_formations) as u32;
    for key in &mut particle.beliefs.keys {
        shift_dynamic_code(&mut key.observer, threshold);
    }
    for state in [
        &mut particle.presence_beliefs,
        &mut particle.node_presence_beliefs,
    ] {
        for key in &mut state.keys {
            shift_dynamic_code(&mut key.observer, threshold);
        }
    }
    for observation in &mut particle.information_observations {
        shift_dynamic_code(&mut observation.source, threshold);
        shift_dynamic_code(&mut observation.observer_node, threshold);
        shift_dynamic_code(&mut observation.source_identity, threshold);
    }
    for relay in &mut particle.information_relays {
        shift_dynamic_code(&mut relay.source_node, threshold);
        shift_dynamic_code(&mut relay.destination_node, threshold);
        for node in &mut relay.route {
            shift_dynamic_code(node, threshold);
        }
    }
    for entry in &mut particle.information_history {
        shift_dynamic_code(&mut entry.source_identity, threshold);
    }
}

/// Insert a command node into the lexically sorted command range.  Registry
/// growth shifts the numeric base of the old commands, but inserting the new
/// organization also shifts the commands at and after its sorted position.
pub(crate) fn shift_dynamic_observer_codes_after_command_insertion(
    particle: &mut ParticleState,
    command_start: u32,
    old_command_count: usize,
    insert_position: usize,
) {
    let split = command_start.saturating_add(insert_position as u32);
    let old_end = command_start.saturating_add(old_command_count as u32);
    let shift = |value: &mut u32| {
        if *value != u32::MAX
            && *value >= split
            && *value < old_end
            && *value < 0x2000_0000
        {
            *value = value.saturating_add(1);
        }
    };
    for key in &mut particle.beliefs.keys {
        if key.kind == 3 {
            shift(&mut key.observer);
        }
    }
    for state in [
        &mut particle.presence_beliefs,
        &mut particle.node_presence_beliefs,
    ] {
        for key in &mut state.keys {
            shift(&mut key.observer);
        }
    }
    for observation in &mut particle.information_observations {
        shift(&mut observation.source);
        shift(&mut observation.observer_node);
        shift(&mut observation.source_identity);
    }
    for relay in &mut particle.information_relays {
        shift(&mut relay.source_node);
        shift(&mut relay.destination_node);
        for node in &mut relay.route {
            shift(node);
        }
    }
    for entry in &mut particle.information_history {
        shift(&mut entry.source_identity);
    }
}

fn create_local_formation(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    personnel: f64,
    startup_stock: f64,
) {
    let peer_indices = (0..particle.formations.personnel.len())
        .filter(|formation| particle.formations.organization[*formation] as usize == organization)
        .collect::<Vec<_>>();
    let mean = |values: &Vec<f64>| {
        if peer_indices.is_empty() {
            0.0
        } else {
            python_sum(
                &peer_indices
                    .iter()
                    .map(|index| values[*index])
                    .collect::<Vec<_>>(),
            ) / peer_indices.len() as f64
        }
    };
    let quality = if peer_indices.is_empty() {
        0.4
    } else {
        mean(&particle.formations.quality)
    };
    let cohesion = if peer_indices.is_empty() {
        particle.organizations.cohesion[organization]
    } else {
        mean(&particle.formations.cohesion)
    };
    let readiness = if peer_indices.is_empty() {
        0.55
    } else {
        mean(&particle.formations.readiness)
    };
    let information = if peer_indices.is_empty() {
        0.45
    } else {
        mean(&particle.formations.information)
    };
    let mobility = if peer_indices.is_empty() {
        particle.organizations.mobility[organization]
    } else {
        mean(&particle.formations.mobility)
    };
    let command = if peer_indices.is_empty() {
        0.5
    } else {
        mean(&particle.formations.command)
    };
    let embeddedness = if peer_indices.is_empty() {
        crate::organizations::local_embeddedness(particle, topology, config, organization, locality)
    } else {
        mean(&particle.formations.embeddedness)
    };

    let formation = particle.formations.personnel.len();
    shift_dynamic_observer_codes(particle, formation);
    let zone = topology
        .zones_for_locality(LocalityId(locality as u32))
        .max_by(|left, right| {
            topology.zone_population_share[*left]
                .total_cmp(&topology.zone_population_share[*right])
                .then_with(|| right.cmp(left))
        })
        .unwrap_or(topology.locality_post_zone[locality] as usize);
    let capacity = (personnel * config.logistics.formation_supply_days).max(0.0);
    let stock = startup_stock.max(0.0).min(capacity);

    particle.formations.organization.push(organization as u32);
    particle.formations.locality.push(locality as u32);
    particle.formations.microzone.push(zone as u32);
    particle.formations.personnel.push(personnel);
    particle.formations.quality.push(quality);
    particle.formations.cohesion.push(cohesion);
    particle.formations.readiness.push(readiness);
    particle.formations.sustainment.push(if capacity > 0.0 {
        stock / capacity
    } else {
        0.0
    });
    particle.formations.information.push(information);
    particle.formations.mobility.push(mobility);
    particle.formations.command.push(command);
    particle.formations.embeddedness.push(embeddedness);
    particle.formations.fatigue.push(0.0);
    particle.formations.availability.push(0.65);
    particle.formations.supply_stock.push(stock);
    particle
        .formations
        .supply_capacity
        .push(capacity.max(stock));
    particle.formations.home_locality.push(locality as u32);
    particle.formations.active.push(1);
    particle.formations.moving.push(0);
    particle.formations.operational_status.push(1);
    particle.formations.cumulative_losses.push(0.0);
    particle.formations.outside_pineland.push(0);
    particle.formations.operational_posture.push(0);
    particle.formations.movement_destination.push(u32::MAX);
    particle.formations.movement_origin.push(u32::MAX);
    particle.formations.movement_execute_at.push(0.0);
    particle.formations.movement_arrives_at.push(-1.0);
    particle.formations.movement_travel_hours.push(0.0);
    particle.formations.movement_distance_km.push(0.0);
    particle.formations.movement_supply_cost.push(0.0);
    particle.formations.movement_order_sequence.push(0);
    particle.formations.movement_status.push(0);
    particle.formations.movement_purpose.push(0);
    particle.formations.external_state.push(u32::MAX);

    // Newly created local formations are not patrol objects in Python.
    particle.patrols.formation.push(formation as u32);
    particle.patrols.active.push(0);
    particle.patrols.route_position.push(0);
    particle.patrols.route_target.push(0);
    particle.patrols.last_departure.push(-1.0e9);
    particle.patrols.next_available.push(0.0);
    particle.patrols.response_fraction.push(0.3);
    particle.patrols.presence_accounted_at.push(-1.0e300);
    particle.patrols.detections.push(0);

    let centralization = particle.organizations.phenotype[organization * 8].clamp(0.0, 1.0);
    let reliability = clamp01(
        0.3 + 0.35 * centralization
            + 0.25 * particle.organizations.institutional_quality[organization],
    );
    particle
        .command_edges
        .organization
        .push(organization as u32);
    particle.command_edges.formation.push(formation as u32);
    particle.command_edges.reliability.push(reliability);
    particle
        .command_edges
        .latency_hours
        .push(10.0 * (1.0 - centralization) + 1.0);
}

fn apply_local_fighter_change(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    delta: f64,
) -> (f64, usize) {
    if delta.abs() <= 1.0e-12 {
        return (0.0, 0);
    }
    let requested = delta;
    let key = ensure_manpower(particle, organization, locality);
    let target_size = config.force_structure.insurgent_target_personnel;
    let minimum = config.organization_ecology.minimum_formation_personnel;
    let supply_per_fighter = (config.logistics.formation_supply_days
        * config.logistics.initial_supply_fraction)
        .max(1.0e-12);
    if delta > 0.0 {
        particle.manpower.pool[key] += delta;
        let desired = particle.manpower.pool[key] * supply_per_fighter;
        let reserve = particle.manpower.supply_reserve[key];
        let converted = (desired - reserve)
            .max(0.0)
            .min(particle.organizations.capital[organization].max(0.0));
        if converted > 0.0 {
            particle.organizations.capital[organization] -= converted;
            particle.manpower.supply_reserve[key] += converted;
        }

        let mut local = (0..particle.formations.personnel.len())
            .filter(|formation| {
                particle.formations.organization[*formation] as usize == organization
                    && particle.formations.locality[*formation] as usize == locality
                    && particle.formations.personnel[*formation] > 0.0
                    && particle.formations.active[*formation] != 0
                    && particle.formations.operational_status[*formation] == 1
                    && particle.formations.moving[*formation] == 0
                    && particle.formations.outside_pineland[*formation] == 0
            })
            .collect::<Vec<_>>();
        local.sort_by(|left, right| {
            particle.formations.personnel[*left]
                .total_cmp(&particle.formations.personnel[*right])
                .then_with(|| left.cmp(right))
        });
        for formation in local {
            let room = (target_size - particle.formations.personnel[formation]).max(0.0);
            let equipped = particle.manpower.supply_reserve[key] / supply_per_fighter;
            let amount = room.min(particle.manpower.pool[key]).min(equipped);
            if amount > 0.0 {
                let supply = amount * supply_per_fighter;
                particle.formations.personnel[formation] += amount;
                particle.formations.supply_stock[formation] += supply;
                particle.manpower.pool[key] -= amount;
                particle.manpower.supply_reserve[key] -= supply;
                resize_formation(particle, config, formation);
            }
            if particle.manpower.pool[key] <= 1.0e-12 {
                break;
            }
        }
        let mut created = 0;
        while particle.manpower.pool[key] >= minimum {
            let equipped = particle.manpower.supply_reserve[key] / supply_per_fighter;
            let size = particle.manpower.pool[key].min(target_size).min(equipped);
            if size < minimum {
                break;
            }
            let supply = size * supply_per_fighter;
            create_local_formation(
                particle,
                topology,
                config,
                organization,
                locality,
                size,
                supply,
            );
            particle.manpower.pool[key] -= size;
            particle.manpower.supply_reserve[key] -= supply;
            created += 1;
        }
        if particle.manpower.pool[key].abs() <= 1.0e-12 {
            particle.manpower.pool[key] = 0.0;
        }
        if particle.manpower.supply_reserve[key].abs() <= 1.0e-12 {
            particle.manpower.supply_reserve[key] = 0.0;
        }
        if particle.manpower.pool[key] == 0.0 && particle.manpower.supply_reserve[key] == 0.0 {
            particle.manpower.organization.remove(key);
            particle.manpower.locality.remove(key);
            particle.manpower.pool.remove(key);
            particle.manpower.supply_reserve.remove(key);
        }
        return (requested, created);
    }

    let mut remaining = -delta;
    let from_pool = particle.manpower.pool[key].min(remaining);
    particle.manpower.pool[key] -= from_pool;
    remaining -= from_pool;
    let mut removed = from_pool;
    let mut candidates = (0..particle.formations.personnel.len())
        .filter(|formation| {
            particle.formations.organization[*formation] as usize == organization
                && particle.formations.personnel[*formation] > 0.0
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|left, right| {
        let left_distance = topology.locality_distance(
            LocalityId(locality as u32),
            LocalityId(particle.formations.locality[*left]),
        );
        let right_distance = topology.locality_distance(
            LocalityId(locality as u32),
            LocalityId(particle.formations.locality[*right]),
        );
        left_distance
            .total_cmp(&right_distance)
            .then_with(|| {
                particle.formations.personnel[*right]
                    .total_cmp(&particle.formations.personnel[*left])
            })
            .then_with(|| left.cmp(right))
    });
    for formation in candidates {
        if remaining <= 1.0e-12 {
            break;
        }
        let amount = particle.formations.personnel[formation].min(remaining);
        particle.formations.personnel[formation] -= amount;
        removed += amount;
        remaining -= amount;
        resize_formation(particle, config, formation);
    }
    (-(removed), 0)
}

fn set_membership(particle: &mut ParticleState, person: usize, organization: usize, fraction: f64) {
    let fraction = clamp01(fraction);
    particle.people.organization[person] = organization as u32;
    particle.people.armed_fraction[person] = fraction;
    particle.people.rebel_sympathy[person] = fraction;
    let organization_count = particle.organizations.kind.len();
    let row = &mut particle.people.insurgent_affinity
        [person * organization_count..(person + 1) * organization_count];
    row.fill(0.0);
    row[organization] = fraction.max(1.0e-12);
    particle.people.public_behavior[person] = if fraction >= 0.5 {
        BEHAVIOR_ARMED_PARTICIPATION
    } else {
        BEHAVIOR_INSURGENT_SYMPATHY
    };
}

fn recompute_member_population(particle: &mut ParticleState) {
    let mut masses = vec![Vec::<f64>::new(); particle.organizations.member_population.len()];
    for person in 0..particle.people.locality.len() {
        let organization = particle.people.organization[person];
        if organization == NO_ORGANIZATION {
            continue;
        }
        if let Some(values) = masses.get_mut(organization as usize) {
            values.push(
                particle.people.represented_population[person]
                    * particle.people.armed_fraction[person],
            );
        }
    }
    for (organization, values) in masses.into_iter().enumerate() {
        particle.organizations.member_population[organization] = python_sum(&values);
    }
}

pub(crate) fn refresh_foothold_memberships(
    particle: &mut ParticleState,
    topology: &StaticTopology,
) {
    let locality_count = topology.locality_count();
    for organization in 0..particle.organizations.kind.len() {
        for locality in 0..locality_count {
            let index = organization * locality_count + locality;
            if index >= particle.footholds.membership.len()
                || particle.organizations.kind[organization] != KIND_INSURGENT
            {
                continue;
            }
            let mass = python_sum(
                &(0..particle.people.locality.len())
                    .filter(|person| {
                        particle.people.organization[*person] as usize == organization
                            && particle.people.residence[*person] as usize == locality
                            && particle.people.armed_fraction[*person] > 0.0
                    })
                    .map(|person| {
                        particle.people.represented_population[person]
                            * particle.people.armed_fraction[person]
                    })
                    .collect::<Vec<_>>(),
            );
            particle.footholds.membership[index] =
                clamp01(mass / particle.locality.population[locality].max(1.0e-12));
        }
    }
}

pub fn recruit(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // Recruitment is intentionally not evaluated at the zero-duration
    // initialization event. This mirrors ProcessEngine.on_recruitment and
    // preserves the process RNG continuation contract.
    if !config.include_insurgency || elapsed_days <= 0.0 {
        return;
    }
    let locality_count = topology.locality_count();
    let organization_count = particle.organizations.kind.len();
    let mut active_insurgents = (0..organization_count)
        .filter(|organization| {
            particle.organizations.active[*organization] != 0
                && particle.organizations.kind[*organization] == KIND_INSURGENT
        })
        .collect::<Vec<_>>();
    active_insurgents.sort_unstable();
    let mut active_mask = vec![false; organization_count];
    for organization in &active_insurgents {
        active_mask[*organization] = true;
    }

    // These channels are frozen at the interval boundary, exactly as in the
    // Python loop. New recruits therefore cannot immediately make later
    // representatives look more locally embedded.
    let mut formation_personnel = vec![vec![0.0; locality_count]; organization_count];
    let mut member_weight = vec![vec![0.0; locality_count]; organization_count];
    for formation in 0..particle.formations.personnel.len() {
        let organization = particle.formations.organization[formation] as usize;
        let locality = particle.formations.locality[formation] as usize;
        if organization < organization_count
            && locality < locality_count
            && particle.formations.personnel[formation] > 0.0
            && particle.formations.active[formation] != 0
            && particle.formations.operational_status[formation] == 1
            && particle.formations.moving[formation] == 0
            && particle.formations.outside_pineland[formation] == 0
        {
            formation_personnel[organization][locality] += particle.formations.personnel[formation];
        }
    }
    for person in 0..particle.people.locality.len() {
        let organization = particle.people.organization[person] as usize;
        let locality = particle.people.residence[person] as usize;
        if organization < organization_count
            && locality < locality_count
            && particle.people.armed_fraction[person] > 0.0
            && active_mask[organization]
        {
            member_weight[organization][locality] += particle.people.represented_population[person]
                * particle.people.armed_fraction[person];
        }
    }

    let mut rooted = vec![vec![(0.0, 0.0, 0.0); locality_count]; organization_count];
    let mut global_profiles = vec![None; organization_count];
    let mut local_profiles = vec![vec![None; locality_count]; organization_count];
    for organization in &active_insurgents {
        for locality in 0..locality_count {
            rooted[*organization][locality] =
                rootedness(particle, topology, *organization, locality);
            local_profiles[*organization][locality] =
                local_profile(particle, *organization, Some(locality));
        }
        global_profiles[*organization] = local_profile(particle, *organization, None);
    }

    let minimum_formation = config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0e-9);
    let minimum_proto = config
        .organization_ecology
        .minimum_proto_represented_population
        .max(1.0e-9);
    let mut total_recruited = 0.0;

    for person in 0..particle.people.locality.len() {
        let locality = particle.people.residence[person] as usize;
        let current_organization = {
            let value = particle.people.organization[person];
            if value != NO_ORGANIZATION
                && (value as usize) < organization_count
                && active_mask[value as usize]
            {
                Some(value as usize)
            } else {
                None
            }
        };
        let current_fraction = current_organization
            .map(|_| particle.people.armed_fraction[person])
            .unwrap_or(0.0);
        let eligible_fraction = (1.0 - current_fraction).max(0.0);
        let mut candidates = Vec::new();

        if eligible_fraction > 1.0e-12 {
            for organization in active_insurgents.iter().copied().filter(|organization| {
                current_organization.is_none_or(|current| current == *organization)
            }) {
                let exposure = particle.people.social_exposure
                    [person * organization_count + organization]
                    .clamp(0.0, 1.0);
                let formation_access = (formation_personnel[organization][locality]
                    / minimum_formation)
                    .clamp(0.0, 1.0);
                let member_access =
                    (member_weight[organization][locality] / minimum_proto).clamp(0.0, 1.0);
                let formation_language =
                    access_language_factor(particle, person, global_profiles[organization]);
                let member_language = access_language_factor(
                    particle,
                    person,
                    local_profiles[organization][locality],
                );
                let foothold_index = organization * locality_count + locality;
                let foothold_access = if foothold_index < particle.footholds.strength.len()
                    && particle.footholds.renewal_count[foothold_index] > 0
                {
                    particle.footholds.strength[foothold_index].clamp(0.0, 1.0)
                } else {
                    0.0
                };
                let access_strength = exposure
                    .max(formation_access * formation_language)
                    .max(member_access * member_language)
                    .max(foothold_access * formation_language);
                if config.organization_ecology.recruitment_requires_access && access_strength <= 0.0
                {
                    continue;
                }
                let federal_identity = particle.people.identities[person * 3 + 2];
                let compatibility = 1.0
                    - (federal_identity - particle.organizations.ideology[organization * 2]).abs();
                let (_, home_locality_share, home_district_share) = rooted[organization][locality];
                let local_salience = particle.people.identities[person * 3];
                let district_salience = particle.people.identities[person * 3 + 1];
                let salience_total = local_salience + district_salience;
                let local_congruence = if salience_total <= 1.0e-12 {
                    0.0
                } else {
                    let rooted_match = (local_salience * home_locality_share
                        + district_salience * home_district_share)
                        / salience_total;
                    let salience_strength = (salience_total / 2.0).clamp(0.0, 1.0);
                    ((2.0 * rooted_match - 1.0) * salience_strength).clamp(-1.0, 1.0)
                };
                let logit = 1.5 * particle.people.grievance[person]
                    + config.social_network.recruitment_exposure_weight * exposure
                    + compatibility
                    + particle.organizations.capital_social[organization]
                    - particle.people.fear[person]
                    - 2.6
                    - config.political_order.peaceful_channel_strength
                        * particle.people.political_access[person]
                    + config.organization_ecology.local_rootedness_weight * local_congruence;
                let base_intensity = logistic(logit);
                let intensity = if config.organization_ecology.recruitment_requires_access {
                    base_intensity * access_strength
                } else {
                    base_intensity
                };
                if intensity > 0.0 {
                    candidates.push(Candidate {
                        organization,
                        intensity,
                        compatibility,
                    });
                }
            }
        }

        let mut recruited_this_interval = false;
        if !candidates.is_empty() {
            let total_intensity = python_sum(
                &candidates
                    .iter()
                    .map(|candidate| candidate.intensity)
                    .collect::<Vec<_>>(),
            );
            let probability = 1.0
                - python_exp(
                    -config.recruitment_rate.max(0.0) * total_intensity.max(0.0) * elapsed_days,
                );
            let n = config.organization_ecology.recruitment_subcohorts;
            let available = (eligible_fraction * n as f64).ceil() as usize;
            let available = available.min(n);
            let recruited_cohorts = (0..available)
                .filter(|_| rng.random() < probability)
                .count();
            let delta_fraction = (recruited_cohorts as f64 / n as f64).min(eligible_fraction);
            if delta_fraction > 0.0 {
                let (winner, compatibility) = if candidates.len() == 1 {
                    (candidates[0].organization, candidates[0].compatibility)
                } else {
                    let draw = rng.random() * total_intensity;
                    let mut cumulative = 0.0;
                    let mut chosen = candidates[candidates.len() - 1];
                    for candidate in candidates.iter().copied() {
                        cumulative += candidate.intensity;
                        if draw <= cumulative {
                            chosen = candidate;
                            break;
                        }
                    }
                    (chosen.organization, chosen.compatibility)
                };
                let winner_fraction = if current_organization == Some(winner) {
                    current_fraction + delta_fraction
                } else {
                    delta_fraction
                };
                set_membership(particle, person, winner, winner_fraction);
                let represented_delta =
                    particle.people.represented_population[person] * delta_fraction;
                total_recruited += represented_delta;
                let fighter_delta =
                    represented_delta * config.organization_ecology.fighter_conversion_fraction;
                record_foothold_recruitment(
                    particle,
                    topology,
                    winner,
                    locality,
                    represented_delta,
                );
                let _ = apply_local_fighter_change(
                    particle,
                    topology,
                    config,
                    winner,
                    locality,
                    fighter_delta,
                );
                let diversity = (compatibility - 0.5).abs() * 2.0;
                let represented_members = particle
                    .people
                    .locality
                    .iter()
                    .enumerate()
                    .filter(|(index, _)| particle.people.organization[*index] as usize == winner)
                    .map(|(index, _)| {
                        particle.people.represented_population[index]
                            * particle.people.armed_fraction[index]
                    })
                    .collect::<Vec<_>>();
                let mass = python_sum(&represented_members);
                particle.organizations.cohesion[winner] = clamp01(
                    particle.organizations.cohesion[winner]
                        - config.organization_ecology.recruitment_diversity_penalty
                            * diversity
                            * delta_fraction
                            / 10.0_f64.max(mass),
                );
                recruited_this_interval = true;
            }
        }

        // The incumbent exit hazard is kept exact for the initial franchise.
        // Rival defection is activated with dynamic organization support in
        // the ecology layer; it does not affect the one-franchise baseline.
        if !recruited_this_interval {
            if let Some(organization) = current_organization {
                let exit_intensity = logistic(
                    particle.people.fear[person] + 0.7
                        - particle.organizations.cohesion[organization]
                        - particle.people.grievance[person],
                );
                let exit_probability = 1.0
                    - python_exp(
                        -config.membership_exit_rate.max(0.0) * exit_intensity * elapsed_days,
                    );
                let n = config.organization_ecology.recruitment_subcohorts;
                let active_cohorts = ((particle.people.armed_fraction[person] * n as f64)
                    .ceil()
                    .max(1.0) as usize)
                    .min(n);
                let exited = (0..active_cohorts)
                    .filter(|_| rng.random() < exit_probability)
                    .count();
                let exit_fraction =
                    (exited as f64 / n as f64).min(particle.people.armed_fraction[person]);
                if exit_fraction > 0.0 {
                    let represented_delta =
                        particle.people.represented_population[person] * exit_fraction;
                    let fighter_delta =
                        represented_delta * config.organization_ecology.fighter_conversion_fraction;
                    let _ = apply_local_fighter_change(
                        particle,
                        topology,
                        config,
                        organization,
                        locality,
                        -fighter_delta,
                    );
                    let remaining = particle.people.armed_fraction[person] - exit_fraction;
                    if remaining <= 1.0e-12 {
                        let prior_fraction = particle.people.armed_fraction[person];
                        particle.people.organization[person] = NO_ORGANIZATION;
                        particle.people.armed_fraction[person] = 0.0;
                        let row = &mut particle.people.insurgent_affinity
                            [person * organization_count..(person + 1) * organization_count];
                        row[organization] = row[organization].max(prior_fraction);
                        particle.people.rebel_sympathy[person] =
                            particle.people.rebel_sympathy[person].max(prior_fraction);
                        if particle.people.public_behavior[person] == BEHAVIOR_ARMED_PARTICIPATION {
                            particle.people.public_behavior[person] = BEHAVIOR_INSURGENT_SYMPATHY;
                        }
                    } else {
                        set_membership(particle, person, organization, remaining);
                    }
                }
            }
        }
    }
    recompute_member_population(particle);
    refresh_foothold_memberships(particle, topology);
    particle.counters.recruitment += total_recruited;
    let _ = time;
}

pub fn foothold_viability(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
    topology: &StaticTopology,
    threshold: f64,
) -> bool {
    let index = organization * topology.locality_count() + locality;
    particle
        .footholds
        .strength
        .get(index)
        .copied()
        .unwrap_or(0.0)
        > threshold
        && particle
            .footholds
            .sustainment
            .get(index)
            .copied()
            .unwrap_or(0.0)
            > threshold
}
