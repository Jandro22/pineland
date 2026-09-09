//! Actor-facing social belief updates.
//!
//! This process is distinct from the information layer. Python updates each
//! representative person's expected control from community signals and draws
//! one normal variate per perceived actor; it does not decay the packed
//! control-belief confidence table here. Keeping that distinction is required
//! for exact event continuation.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

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

fn community_signal(particle: &ParticleState, locality: usize, actor: usize) -> f64 {
    let mut total = 0.0;
    let mut weighted = 0.0;
    for community in 0..particle.communities.locality.len() {
        if particle.communities.locality[community] as usize != locality {
            continue;
        }
        let start = particle.communities.member_offsets[community] as usize;
        let end = particle.communities.member_offsets[community + 1] as usize;
        let mass = particle.communities.member_indices[start..end]
            .iter()
            .map(|person| particle.people.represented_population[*person as usize])
            .sum::<f64>();
        let signal = if actor == crate::GOVERNMENT {
            particle.communities.government_cooperation[community]
        } else {
            particle.communities.insurgent_sympathy[community]
        };
        weighted += mass * signal;
        total += mass;
    }
    if total > 0.0 {
        clamp01(weighted / total)
    } else {
        0.0
    }
}

/// Advance the actor-facing expected-control state for one beliefs event.
/// The static topology is accepted because the Python process also computes
/// sparse destination signals from its adjacency table; the dense native
/// person state currently stores the same-locality expectation, while the
/// locality graph is retained for the later sparse-destination extension.
pub fn decay_and_propagate(
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
    // Python only exposes the generic insurgent actor to representatives when
    // at least one insurgent organization is active.  After a collapse this
    // changes both the number of normal draws and the set of expected-control
    // fields updated at the boundary, so decide it once before the person
    // loop rather than inferring it from stale per-person affiliation.
    let insurgent_perceived = (0..particle.organizations.kind.len()).any(|organization| {
        particle.organizations.active[organization] != 0
            && organization == crate::INSURGENT
    });
    for person in 0..particle.people.locality.len() {
        let locality = particle.people.residence[person] as usize;
        let community = particle.people.community[person];
        for actor in [crate::GOVERNMENT, crate::INSURGENT] {
            if actor == crate::INSURGENT && !insurgent_perceived {
                continue;
            }
            // Python keeps a person's community partition attached to the
            // representative even after mobility changes residence.  The
            // community signal is therefore selected by community identity,
            // not by requiring that the moved person still resides in the
            // community's original locality.
            let signal = if community != u32::MAX
                && (community as usize) < particle.communities.locality.len()
            {
                if actor == crate::GOVERNMENT {
                    particle.communities.government_cooperation[community as usize]
                } else {
                    particle.communities.insurgent_sympathy[community as usize]
                }
            } else {
                community_signal(particle, locality, actor)
            };
            let observed = clamp01(round_binary64(
                signal + rng.normalvariate(0.0, config.observation_noise),
            ));
            let trust = if actor == crate::GOVERNMENT {
                particle.people.trust[person]
            } else {
                particle.people.trust_insurgent[person]
            };
            // The scalar is person-specific; do not collapse it to one
            // locality-wide learning coefficient.
            let learning = reference_probability(0.12 * trust, elapsed_days);
            let offset = person * 2 + usize::from(actor == crate::INSURGENT);
            let old = particle.people.expected_control[offset];
            let deviation = round_binary64(observed - old);
            let adjustment = round_binary64(learning * deviation);
            particle.people.expected_control[offset] = clamp01(round_binary64(old + adjustment));

            // Python stores destination-specific expectations for every
            // adjacent locality.  A missing entry falls back to the scalar
            // expectation *after* this event's scalar update, then the local
            // aggregate is blended with the same person-specific learning
            // rate.  Keep the sparse Python semantics with a dense native
            // table plus a two-bit presence mask.
            let actor_bit = if actor == crate::GOVERNMENT { 1 } else { 2 };
            for (destination, _) in topology.locality_edges.neighbors(locality) {
                let destination = destination as usize;
                let mask_index = person * topology.locality_count() + destination;
                let value_index = mask_index * 2 + usize::from(actor == crate::INSURGENT);
                if mask_index >= particle.people.expected_destination_control_present.len()
                    || value_index >= particle.people.expected_destination_control.len()
                {
                    continue;
                }
                let prior = if particle.people.expected_destination_control_present[mask_index]
                    & actor_bit
                    != 0
                {
                    particle.people.expected_destination_control[value_index]
                } else {
                    particle.people.expected_control[offset]
                };
                let destination_signal = community_signal(particle, destination, actor);
                let deviation = round_binary64(destination_signal - prior);
                let adjustment = round_binary64(learning * deviation);
                particle.people.expected_destination_control[value_index] =
                    clamp01(round_binary64(prior + adjustment));
                particle.people.expected_destination_control_present[mask_index] |= actor_bit;
            }
        }
    }
}

/// Keep each Python float expression at an observable binary64 boundary.  In
/// optimized native builds LLVM may otherwise contract the multiply/add in a
/// belief update into an FMA and move the final bit of parity-critical state.
#[inline(never)]
fn round_binary64(value: f64) -> f64 {
    unsafe { std::ptr::read_volatile(&value) }
}

pub fn control_estimate(
    particle: &ParticleState,
    observer: usize,
    locality: usize,
) -> [f64; pineland_core::state::CONTROL_DIMENSIONS] {
    let mut result = [0.0; pineland_core::state::CONTROL_DIMENSIONS];
    if let Some(index) = particle.beliefs.keys.iter().position(|key| {
        key.observer as usize == observer && key.locality as usize == locality && key.kind == 1
    }) {
        let offset = index * pineland_core::state::CONTROL_DIMENSIONS;
        result.copy_from_slice(
            &particle.beliefs.control[offset..offset + pineland_core::state::CONTROL_DIMENSIONS],
        );
    }
    result
}
