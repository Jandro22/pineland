//! Political institutions, patronage, elections, and peaceful alternatives.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
    elapsed_days: f64,
) {
    if !config.political_order.enabled || elapsed_days <= 0.0 {
        if config.political_order.enabled && elapsed_days == 0.0 && _time.abs() <= 1.0e-12 {
            run_initial_election(particle, config);
        }
        return;
    }
    let budget =
        config.political_order.federal_policy_budget * config.political_order.public_budget_share;
    for locality in 0..topology.locality_count() {
        let offset = locality * CONTROL_DIMENSIONS;
        let fiscal = (budget / particle.locality.population[locality].max(1.0)).min(1.0);
        let patronage = config.political_order.patronage_share * (0.7 + 0.6 * rng.random());
        particle.locality.government_control[offset] = clamp01(
            particle.locality.government_control[offset]
                + config.political_order.capacity_learning_rate * fiscal,
        );
        particle.locality.government_control[offset + 4] = clamp01(
            particle.locality.government_control[offset + 4] + fiscal * 0.02
                - patronage * config.political_order.patronage_capacity_damage,
        );
        particle.locality.government_control[offset + 5] = clamp01(
            particle.locality.government_control[offset + 5]
                + config.political_order.peaceful_channel_strength * fiscal * 0.01,
        );
    }
}

/// The Python political-order process runs an election at its zero-length
/// initialization boundary when no election has yet been recorded.  The
/// native state does not retain an output-only election log, so this helper
/// applies the decision-relevant consequences exactly once at t=0.
fn run_initial_election(particle: &mut ParticleState, config: &SimulationConfig) {
    let parties = [crate::PARTY_1, crate::PARTY_2, crate::PARTY_3];
    let mut votes = [0.0; 3];
    for person in 0..particle.people.locality.len() {
        let base_turnout = clamp01(
            particle.people.political_access[person]
                * (0.45 + 0.55 * particle.people.state_legitimacy[person]),
        );
        let sensitivity = config.political_order.election_turnout_sensitivity.max(0.1);
        let turnout = clamp01(base_turnout.powf(1.0 / sensitivity));
        let locality = particle.people.residence[person] as usize;
        let mut utilities = [0.0; 3];
        for (slot, party) in parties.iter().copied().enumerate() {
            let branch = (0..particle.political.branch_party.len()).find(|index| {
                particle.political.branch_party[*index] as usize == party
                    && particle.political.branch_locality[*index] as usize == locality
            });
            let electoral_support = branch
                .and_then(|index| particle.political.branch_electoral_support.get(index))
                .copied()
                .unwrap_or(0.0);
            utilities[slot] = (particle.people.party_legitimacy[person * 3 + slot]
                * particle.people.preferences[person * 3 + slot]
                * (1.0 + electoral_support))
                .max(0.001);
        }
        let total = utilities.iter().sum::<f64>();
        if total > 0.0 {
            for slot in 0..3 {
                votes[slot] +=
                    particle.people.represented_population[person] * turnout * utilities[slot]
                        / total;
            }
        }
    }
    let winner_slot = votes
        .iter()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(right.1).then_with(|| right.0.cmp(&left.0)))
        .map(|(slot, _)| slot)
        .unwrap_or(0);
    let winner = parties[winner_slot] as u32;
    particle.political.ruling_party = winner;
    for governing_party in &mut particle.political.institution_governing_party {
        *governing_party = winner;
    }
    for index in 0..particle.political.branch_party.len() {
        if particle.political.branch_party[index] == winner {
            particle.political.branch_institutional_influence[index] =
                clamp01(particle.political.branch_institutional_influence[index] + 0.08);
        } else {
            particle.political.branch_institutional_influence[index] =
                clamp01(particle.political.branch_institutional_influence[index] - 0.02);
        }
    }
}

pub fn turnout(particle: &ParticleState, locality: usize, config: &SimulationConfig) -> f64 {
    let offset = locality * CONTROL_DIMENSIONS;
    clamp01(
        0.5 + config.political_order.election_turnout_sensitivity
            * (particle.locality.government_control[offset + 5]
                - particle.locality.violence[locality]),
    )
}
