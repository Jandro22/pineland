//! Social exposure and public-behavior transitions.
//!
//! This is the dense native translation of ``SimulationProcesses``' social
//! influence event.  The event is intentionally evaluated person by person
//! in canonical person/neighbor order: the RNG draw made for one weighted
//! representative must not depend on hash-map iteration or on a parallel
//! reduction order.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;
use std::collections::BTreeMap;

const KIND_INSURGENT: u8 = 3;
const NO_ORGANIZATION: u32 = u32::MAX;

// Stable Python public-behavior codes.  These are kept local to the native
// process so adding a state column later cannot silently change the ordering
// passed to random.choices.
const BEHAVIOR_NEUTRAL: u8 = 0;
const BEHAVIOR_INSURGENT_SYMPATHY: u8 = 1;
const BEHAVIOR_ARMED_PARTICIPATION: u8 = 2;
const BEHAVIOR_GOVERNMENT_COOPERATION: u8 = 3;
const BEHAVIOR_PARTY_PARTICIPATION: u8 = 4;
const BEHAVIOR_CIVIL_SOCIETY: u8 = 5;
const BEHAVIOR_PROTEST: u8 = 6;
const BEHAVIOR_INACTIVE: u8 = 7;
const BEHAVIOR_MIGRATION: u8 = 8;

fn reference_probability(probability: f64, elapsed_days: f64) -> f64 {
    let probability = clamp01(probability);
    if probability <= 0.0 || elapsed_days <= 0.0 {
        0.0
    } else if probability >= 1.0 {
        1.0
    } else {
        1.0 - (1.0 - probability).powf(elapsed_days)
    }
}

fn behavior_score(behavior: u8) -> (f64, f64) {
    match behavior {
        BEHAVIOR_GOVERNMENT_COOPERATION => (1.0, 0.0),
        BEHAVIOR_PARTY_PARTICIPATION => (0.25, 0.0),
        BEHAVIOR_CIVIL_SOCIETY => (0.15, 0.0),
        BEHAVIOR_PROTEST => (-0.15, 0.1),
        BEHAVIOR_INSURGENT_SYMPATHY => (-0.4, 0.7),
        BEHAVIOR_ARMED_PARTICIPATION => (-0.7, 1.0),
        BEHAVIOR_INACTIVE | BEHAVIOR_MIGRATION | BEHAVIOR_NEUTRAL => (0.0, 0.0),
        _ => (0.0, 0.0),
    }
}

fn is_insurgent_behavior(behavior: u8) -> bool {
    matches!(
        behavior,
        BEHAVIOR_INSURGENT_SYMPATHY | BEHAVIOR_ARMED_PARTICIPATION
    )
}

/// Social edges are already canonicalized by world generation. Build a
/// lookup once per event so neighbor traversal remains the packed adjacency
/// order while edge attributes are read without a nondeterministic map walk.
fn edge_lookup(particle: &ParticleState) -> BTreeMap<(usize, usize), usize> {
    let mut result = BTreeMap::new();
    for edge in 0..particle.social_edges.person_a.len() {
        let first = particle.social_edges.person_a[edge] as usize;
        let second = particle.social_edges.person_b[edge] as usize;
        result.insert((first.min(second), first.max(second)), edge);
    }
    result
}

fn set_insurgent_control(particle: &mut ParticleState, locality: usize, delta: f64) {
    let offset = locality * CONTROL_DIMENSIONS;
    particle.locality.insurgent_control[offset + 5] =
        clamp01(particle.locality.insurgent_control[offset + 5] + delta);
}

fn refresh_community_aggregates(particle: &mut ParticleState) {
    for community in 0..particle.communities.locality.len() {
        let start = particle.communities.member_offsets[community] as usize;
        let end = particle.communities.member_offsets[community + 1] as usize;
        let members = &particle.communities.member_indices[start..end];
        let mut total = 0.0;
        let mut government = 0.0;
        let mut insurgent = 0.0;
        for person in members.iter().copied().map(|value| value as usize) {
            let weight = particle.people.represented_population[person];
            total += weight;
            if particle.people.public_behavior[person] == BEHAVIOR_GOVERNMENT_COOPERATION {
                government += weight;
            }
            if is_insurgent_behavior(particle.people.public_behavior[person]) {
                insurgent += weight;
            }
        }
        if total > 0.0 {
            particle.communities.government_cooperation[community] = government / total;
            particle.communities.insurgent_sympathy[community] = insurgent / total;
        }
    }
}

fn sync_legacy_rebel_sympathy(particle: &mut ParticleState, person: usize) {
    let organization_count = particle.organizations.kind.len();
    if crate::INSURGENT < organization_count {
        particle.people.rebel_sympathy[person] =
            particle.people.insurgent_affinity[person * organization_count + crate::INSURGENT];
    }
}

/// Advance one social-influence event.
pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
    elapsed_days: f64,
) {
    if elapsed_days <= 0.0 {
        return;
    }

    let people_count = particle.people.locality.len();
    let organization_count = particle.organizations.kind.len();
    let mut active_insurgents = (0..organization_count)
        .filter(|organization| {
            particle.organizations.active[*organization] != 0
                && particle.organizations.kind[*organization] == KIND_INSURGENT
        })
        .collect::<Vec<_>>();
    active_insurgents.sort_unstable();
    let insurgent_available = !active_insurgents.is_empty();
    let behavior_probability =
        reference_probability(config.social_network.behavior_update_rate, elapsed_days);
    let edges = edge_lookup(particle);

    let mut locality_government_shift = vec![0.0; topology.locality_count()];
    let mut locality_insurgent_shift = vec![0.0; topology.locality_count()];
    let mut locality_franchise_shift = BTreeMap::<(usize, usize), f64>::new();

    for person in 0..people_count {
        let old_affinity = (0..organization_count)
            .map(|organization| {
                particle.people.insurgent_affinity[person * organization_count + organization]
            })
            .collect::<Vec<_>>();

        let mut government_signal = 0.0;
        let mut insurgent_signal = 0.0;
        let mut insurgent_signal_by_org = vec![0.0; organization_count];
        let mut total_weight = 0.0;

        let start = particle.social_edges.neighbor_offsets[person] as usize;
        let end = particle.social_edges.neighbor_offsets[person + 1] as usize;
        for neighbor in particle.social_edges.neighbor_indices[start..end]
            .iter()
            .copied()
            .map(|value| value as usize)
        {
            let edge_index = edges
                .get(&(person.min(neighbor), person.max(neighbor)))
                .copied()
                .expect("social adjacency references an absent edge");
            let influence = particle.social_edges.weight[edge_index]
                * particle.social_edges.trust[edge_index]
                * particle.social_edges.represented_relationships[edge_index];
            let (neighbor_government, mut neighbor_insurgent) =
                behavior_score(particle.people.public_behavior[neighbor]);

            let neighbor_organization = particle.people.organization[neighbor];
            let neighbor_is_active_insurgent = neighbor_organization != NO_ORGANIZATION
                && (neighbor_organization as usize) < organization_count
                && active_insurgents.contains(&(neighbor_organization as usize));
            if neighbor_is_active_insurgent {
                neighbor_insurgent = particle.people.armed_fraction[neighbor]
                    .max(neighbor_insurgent * particle.people.armed_fraction[neighbor]);
                let organization = neighbor_organization as usize;
                insurgent_signal_by_org[organization] += influence * neighbor_insurgent;
            } else if neighbor_insurgent > 0.0 {
                let mut affinity_total = 0.0;
                for organization in active_insurgents.iter().copied() {
                    let value = particle.people.insurgent_affinity
                        [neighbor * organization_count + organization];
                    if value > 0.0 {
                        affinity_total += value;
                    }
                }
                if affinity_total > 0.0 {
                    for organization in active_insurgents.iter().copied() {
                        let value = particle.people.insurgent_affinity
                            [neighbor * organization_count + organization];
                        if value > 0.0 {
                            insurgent_signal_by_org[organization] +=
                                influence * neighbor_insurgent * value / affinity_total;
                        }
                    }
                }
            }
            if !insurgent_available {
                neighbor_insurgent = 0.0;
            }
            government_signal += influence * neighbor_government.max(0.0);
            insurgent_signal += influence * neighbor_insurgent;
            total_weight += influence;
        }

        if total_weight != 0.0 {
            government_signal /= total_weight;
            insurgent_signal /= total_weight;
            for organization in active_insurgents.iter().copied() {
                insurgent_signal_by_org[organization] /= total_weight;
            }
        }
        if active_insurgents.len() == 1 {
            insurgent_signal_by_org[active_insurgents[0]] = insurgent_signal;
        }

        if particle.people.organization[person] == NO_ORGANIZATION
            && is_insurgent_behavior(particle.people.public_behavior[person])
        {
            let affinity_total = active_insurgents
                .iter()
                .copied()
                .map(|organization| insurgent_signal_by_org[organization])
                .sum::<f64>();
            if affinity_total > 0.0 {
                let row = &mut particle.people.insurgent_affinity
                    [person * organization_count..(person + 1) * organization_count];
                row.fill(0.0);
                for organization in active_insurgents.iter().copied() {
                    let value = insurgent_signal_by_org[organization];
                    if value > 0.0 {
                        row[organization] = clamp01(value / affinity_total);
                    }
                }
            }
        }
        sync_legacy_rebel_sympathy(particle, person);

        // Python consumes exactly one gate draw for every person, including a
        // person whose chosen behavior remains unchanged.
        if rng.random() >= behavior_probability {
            continue;
        }

        let preference_start = person * 3;
        let party_affinity = particle.people.preferences[preference_start..preference_start + 3]
            .iter()
            .copied()
            .fold(0.0f64, f64::max);
        let expected_government = particle.people.expected_control[person * 2];
        let expected_insurgent = particle.people.expected_control[person * 2 + 1];
        let member_organization = particle.people.organization[person];
        let armed_membership_utility = if member_organization != NO_ORGANIZATION
            && (member_organization as usize) < organization_count
            && particle.organizations.kind[member_organization as usize] == KIND_INSURGENT
        {
            -1.5 + 3.0 * particle.people.armed_fraction[person]
        } else {
            -1.5
        };
        let exposure_weight = config.social_network.behavior_exposure_weight;
        let peaceful_channel_strength = config.political_order.peaceful_channel_strength;
        let grievance = particle.people.grievance[person];
        let fear = particle.people.fear[person];
        let efficacy = particle.people.efficacy[person];
        let political_access = particle.people.political_access[person];
        let mut choices = vec![
            BEHAVIOR_INACTIVE,
            BEHAVIOR_GOVERNMENT_COOPERATION,
            BEHAVIOR_PARTY_PARTICIPATION,
            BEHAVIOR_CIVIL_SOCIETY,
            BEHAVIOR_PROTEST,
            BEHAVIOR_INSURGENT_SYMPATHY,
            BEHAVIOR_ARMED_PARTICIPATION,
            BEHAVIOR_MIGRATION,
        ];
        let mut utilities = vec![
            0.7 + fear - efficacy,
            party_affinity + expected_government + exposure_weight * government_signal
                - grievance
                - 0.4 * fear,
            party_affinity + efficacy + political_access - 0.5 * fear,
            0.5 + efficacy + 0.6 * political_access - 0.3 * fear,
            1.2 * grievance + efficacy + 0.25 * political_access - fear,
            1.2 * grievance + expected_insurgent + exposure_weight * insurgent_signal - fear,
            armed_membership_utility + grievance + exposure_weight * insurgent_signal
                - fear
                - peaceful_channel_strength * political_access,
            (if particle.people.displaced[person] != 0 {
                1.4
            } else {
                -0.8
            }) + fear
                - expected_government,
        ];
        if !insurgent_available {
            choices.retain(|choice| {
                *choice != BEHAVIOR_INSURGENT_SYMPATHY && *choice != BEHAVIOR_ARMED_PARTICIPATION
            });
            utilities = choices
                .iter()
                .map(|choice| match *choice {
                    BEHAVIOR_INACTIVE => 0.7 + fear - efficacy,
                    BEHAVIOR_GOVERNMENT_COOPERATION => {
                        party_affinity + expected_government + exposure_weight * government_signal
                            - grievance
                            - 0.4 * fear
                    }
                    BEHAVIOR_PARTY_PARTICIPATION => {
                        party_affinity + efficacy + political_access - 0.5 * fear
                    }
                    BEHAVIOR_CIVIL_SOCIETY => 0.5 + efficacy + 0.6 * political_access - 0.3 * fear,
                    BEHAVIOR_PROTEST => 1.2 * grievance + efficacy + 0.25 * political_access - fear,
                    BEHAVIOR_MIGRATION => {
                        (if particle.people.displaced[person] != 0 {
                            1.4
                        } else {
                            -0.8
                        }) + fear
                            - expected_government
                    }
                    _ => 0.0,
                })
                .collect();
        }
        let peak = utilities.iter().copied().fold(f64::NEG_INFINITY, f64::max);
        let weights = utilities
            .iter()
            .map(|utility| python_exp(*utility - peak))
            .collect::<Vec<_>>();
        let choice_index = rng
            .choices_indices(choices.len(), Some(&weights), 1)
            .expect("social behavior utility weights must be valid")[0];
        let new_behavior = choices[choice_index];
        let old_behavior = particle.people.public_behavior[person];
        if new_behavior == old_behavior {
            continue;
        }

        let (old_government, old_insurgent) = behavior_score(old_behavior);
        let (new_government, new_insurgent) = behavior_score(new_behavior);
        let locality = particle.people.residence[person] as usize;
        locality_government_shift[locality] +=
            particle.people.represented_population[person] * (new_government - old_government);
        locality_insurgent_shift[locality] +=
            particle.people.represented_population[person] * (new_insurgent - old_insurgent);
        particle.people.public_behavior[person] = new_behavior;

        if member_organization == NO_ORGANIZATION {
            if is_insurgent_behavior(new_behavior) {
                let affinity_total = active_insurgents
                    .iter()
                    .copied()
                    .map(|organization| insurgent_signal_by_org[organization])
                    .sum::<f64>();
                let row = &mut particle.people.insurgent_affinity
                    [person * organization_count..(person + 1) * organization_count];
                row.fill(0.0);
                if affinity_total > 0.0 {
                    for organization in active_insurgents.iter().copied() {
                        let value = insurgent_signal_by_org[organization];
                        if value > 0.0 {
                            row[organization] = clamp01(value / affinity_total);
                        }
                    }
                }
            } else {
                particle.people.insurgent_affinity
                    [person * organization_count..(person + 1) * organization_count]
                    .fill(0.0);
            }
        }
        sync_legacy_rebel_sympathy(particle, person);

        let affinity_shares = |values: &[f64], behavior: u8| -> Vec<(usize, f64)> {
            let mut total = 0.0;
            for organization in active_insurgents.iter().copied() {
                let value = values[organization];
                if value > 0.0 {
                    total += value;
                }
            }
            if total > 0.0 {
                active_insurgents
                    .iter()
                    .copied()
                    .filter_map(|organization| {
                        let value = values[organization];
                        (value > 0.0).then_some((organization, value / total))
                    })
                    .collect()
            } else if active_insurgents.len() == 1 && is_insurgent_behavior(behavior) {
                vec![(active_insurgents[0], 1.0)]
            } else {
                Vec::new()
            }
        };
        let old_shares = affinity_shares(&old_affinity, old_behavior);
        let current_row = &particle.people.insurgent_affinity
            [person * organization_count..(person + 1) * organization_count];
        let new_shares = affinity_shares(current_row, new_behavior);
        for organization in active_insurgents.iter().copied() {
            let old_share = old_shares
                .iter()
                .find_map(|(candidate, share)| (*candidate == organization).then_some(*share))
                .unwrap_or(0.0);
            let new_share = new_shares
                .iter()
                .find_map(|(candidate, share)| (*candidate == organization).then_some(*share))
                .unwrap_or(0.0);
            let old_specific = old_insurgent * old_share;
            let new_specific = new_insurgent * new_share;
            let specific_shift =
                particle.people.represented_population[person] * (new_specific - old_specific);
            if specific_shift != 0.0 {
                *locality_franchise_shift
                    .entry((locality, organization))
                    .or_insert(0.0) += specific_shift;
            }
        }
    }

    for locality in 0..topology.locality_count() {
        let population = particle.locality.population[locality].max(1.0);
        let government_shift = locality_government_shift[locality];
        let insurgent_shift = locality_insurgent_shift[locality];
        if government_shift != 0.0 {
            let offset = locality * CONTROL_DIMENSIONS;
            particle.locality.government_control[offset + 5] = clamp01(
                particle.locality.government_control[offset + 5]
                    + 0.01 * government_shift / population,
            );
        }
        if insurgent_available && !active_insurgents.contains(&crate::INSURGENT) {
            let delta = 0.01 * insurgent_shift / population;
            if delta != 0.0 {
                set_insurgent_control(particle, locality, delta);
            }
        }
    }
    for ((locality, organization), represented_shift) in locality_franchise_shift {
        // Native v1 has one packed insurgent control vector. Every active
        // insurgent franchise maps to that vector until the dynamic actor
        // table gains per-franchise locality controls.
        if organization < organization_count
            && particle.organizations.kind[organization] == KIND_INSURGENT
        {
            let population = particle.locality.population[locality].max(1.0);
            let delta = 0.01 * represented_shift / population;
            if delta != 0.0 {
                set_insurgent_control(particle, locality, delta);
            }
        }
    }

    refresh_community_aggregates(particle);
}

pub fn language_compatibility(enabled: bool, shared_language: f64) -> f64 {
    if enabled {
        clamp01(shared_language)
    } else {
        1.0
    }
}
