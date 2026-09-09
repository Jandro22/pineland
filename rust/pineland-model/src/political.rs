//! Political institutions, patronage, elections, and peaceful alternatives.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, python_sum, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    if !config.political_order.enabled || elapsed_days <= 0.0 {
        if config.political_order.enabled && elapsed_days == 0.0 && time.abs() <= 1.0e-12 {
            run_initial_election(particle, config);
        }
        return;
    }

    // This is the dense translation of political_order.process_political_order.
    // Keep its operation order aligned with Python: the political event is a
    // decision-state transition, not merely a small control increment.
    let cycle_scale = elapsed_days / 30.0;
    let decay_factor = python_exp(
        -config.political_order.patronage_decay_rate * elapsed_days / 365.0,
    );
    for patronage in &mut particle.political.branch_patronage {
        *patronage *= decay_factor;
    }

    let government = crate::GOVERNMENT;
    let budget = particle.organizations.capital[government]
        .min(config.political_order.federal_policy_budget * cycle_scale);
    particle.organizations.capital[government] -= budget;
    let public_total = budget * config.political_order.public_budget_share;
    let patronage_total = budget * config.political_order.patronage_share;
    let private_total = budget * config.political_order.private_diversion_share;
    particle.political.private_diversion_stock += private_total;

    let district_count = topology.district_count();
    let locality_institution_start = 6 + district_count;
    for locality in 0..topology.locality_count() {
        let institution = locality_institution_start + locality;
        let public = public_total / topology.locality_count().max(1) as f64;
        let mut patronage = patronage_total / topology.locality_count().max(1) as f64;
        let compliance_noise = rng.normalvariate(0.0, 0.08);
        let compliance = clamp01(
            particle.political.institution_compliance[institution]
                + compliance_noise * particle.political.institution_autonomy[institution],
        );
        let effective_public = public * compliance;
        let distorted = public - effective_public;
        patronage += distorted * 0.7;
        let private_local = distorted * 0.3;
        particle.political.private_diversion_stock += private_local;

        // The Python implementation routes local patronage through the
        // ruling branch and then through its explicit broker anchors.  The
        // native political state stores the same branch/elite accounts using
        // canonical locality-major indexing.
        let ruling_party = particle.political.ruling_party as usize;
        let ruling_branch = if (crate::PARTY_1..=crate::PARTY_3).contains(&ruling_party) {
            Some(locality * 3 + (ruling_party - crate::PARTY_1))
        } else {
            None
        };
        if let Some(branch) = ruling_branch {
            particle.political.branch_patronage[branch] += patronage;
            let start = particle.political.branch_broker_offsets[branch] as usize;
            let end = particle.political.branch_broker_offsets[branch + 1] as usize;
            let broker_pool = patronage * config.political_order.elite_broker_share;
            let broker_count = (end - start).max(1) as f64;
            for offset in start..end {
                let elite = particle.political.branch_broker_indices[offset] as usize;
                let amount = broker_pool / broker_count;
                particle.political.elite_resources[elite] += amount;
                particle.political.branch_patronage[branch] -= amount;
            }
        }

        let scale = (effective_public / cycle_scale)
            / (particle.locality.population[locality] * 0.05).max(1.0);
        // Python's `_service_output` uses the institution's stored
        // compliance for production.  The newly sampled compliance value is
        // used above for effective public spending, but is not written back
        // to the institution before service output is calculated.
        let production = clamp01(
            particle.political.institution_capacity[institution]
                * particle.political.institution_reach[institution]
                * particle.political.institution_compliance[institution]
                * scale,
        );
        let security = production * (0.8 + 0.2 * particle.locality.infrastructure[locality]);
        let justice = production * particle.political.institution_integrity[institution];
        let administration = production * particle.political.institution_capacity[institution];
        let services = production * particle.locality.infrastructure[locality];
        let representation =
            production * (0.5 + 0.5 * particle.political.institution_autonomy[institution]);
        let quality = python_sum(&[
            security,
            justice,
            administration,
            services,
            representation,
        ]) / 5.0;
        let integrity_loss = config.political_order.patronage_capacity_damage * patronage
            / (public + patronage).max(1.0);

        if std::env::var_os("PINELAND_POLITICAL_TRACE").is_some() {
            eprintln!(
                "POLITICAL locality={} institution={} noise={:.17} public={:.17} patronage={:.17} compliance={:.17} effective_public={:.17} scale={:.17} production={:.17} outputs={:.17},{:.17},{:.17},{:.17},{:.17} quality={:.17} integrity_loss={:.17}",
                locality,
                institution,
                compliance_noise,
                public,
                patronage,
                compliance,
                effective_public,
                scale,
                production,
                security,
                justice,
                administration,
                services,
                representation,
                quality,
                integrity_loss,
            );
        }

        particle.political.institution_resources[institution] += effective_public;
        particle.political.institution_capacity[institution] = clamp01(
            particle.political.institution_capacity[institution]
                + cycle_scale
                    * (config.political_order.capacity_learning_rate * quality
                        - config.political_order.capacity_decay_rate * (1.0 - quality)
                        - integrity_loss),
        );
        particle.political.institution_integrity[institution] = clamp01(
            particle.political.institution_integrity[institution]
                - cycle_scale * integrity_loss,
        );
        // Python spends the institution's temporary allocation completely on
        // the local service output. Preserve the same post-event zero account
        // and operation order rather than leaving a duplicate stock.
        particle.political.institution_resources[institution] -= effective_public;

        let offset = locality * CONTROL_DIMENSIONS;
        particle.locality.government_control[offset] = clamp01(
            particle.locality.government_control[offset]
                + 0.0,
        );
        particle.locality.government_control[offset + 2] = clamp01(
            particle.locality.government_control[offset + 2]
                + 0.004 * administration * cycle_scale,
        );
        particle.locality.government_control[offset + 3] = clamp01(
            particle.locality.government_control[offset + 3]
                + 0.004 * justice * cycle_scale,
        );
        particle.locality.government_control[offset + 5] = clamp01(
            particle.locality.government_control[offset + 5]
                + 0.003 * services * cycle_scale,
        );
        particle.locality.government_control[offset + 5] = clamp01(
            particle.locality.government_control[offset + 5]
                + 0.0,
        );
        particle.locality.government_control[offset + 6] = clamp01(
            particle.locality.government_control[offset + 6]
                + 0.003 * representation * cycle_scale,
        );

        let patronage_reach = {
            let routed = patronage
                * ((1.0 - config.political_order.elite_broker_share)
                    + config.political_order.elite_broker_share);
            routed / cycle_scale / (particle.locality.population[locality] * 0.01).max(1.0)
        };
        for person in 0..particle.people.residence.len() {
            if particle.people.residence[person] as usize != locality {
                continue;
            }
            let fairness = particle.political.institution_integrity[institution];
            let experience = quality * (0.5 + 0.5 * fairness);
            particle.people.government_legitimacy[person] = clamp01(
                particle.people.government_legitimacy[person]
                    + 0.04 * (experience - 0.35) * cycle_scale,
            );
            particle.people.state_legitimacy[person] = clamp01(
                particle.people.state_legitimacy[person]
                    + 0.01 * (justice - 0.25) * cycle_scale,
            );
            particle.people.political_access[person] = clamp01(
                particle.people.political_access[person]
                    + 0.03 * (representation - 0.2) * cycle_scale,
            );
            if let Some(branch) = ruling_branch {
                let party_slot = particle.political.branch_party[branch] as usize - crate::PARTY_1;
                if party_slot < 3 {
                    let party_offset = person * 3 + party_slot;
                    particle.people.party_legitimacy[party_offset] = clamp01(
                        particle.people.party_legitimacy[party_offset]
                            + cycle_scale
                                * (0.025 * patronage_reach
                                    - 0.015 * (1.0 - fairness)),
                    );
                    for other in 0..3 {
                        if other != party_slot {
                            let offset = person * 3 + other;
                            particle.people.party_legitimacy[offset] = clamp01(
                                particle.people.party_legitimacy[offset]
                                    - 0.008 * patronage_reach * cycle_scale,
                            );
                        }
                    }
                }
            }
        }
    }

    if particle.political.institution_governing_party.is_empty() {
        return;
    }
    if time - 0.0 >= config.political_order.election_interval_days {
        run_election(particle, topology, config, time);
    }
}

fn run_election(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _time: f64,
) {
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
            let support = branch
                .and_then(|index| particle.political.branch_electoral_support.get(index))
                .copied()
                .unwrap_or(0.0);
            utilities[slot] = (particle.people.party_legitimacy[person * 3 + slot]
                * particle.people.preferences[person * 3 + slot]
                * (1.0 + support))
                .max(0.001);
        }
        let total = python_sum(&utilities);
        if total > 0.0 {
            for slot in 0..3 {
                votes[slot] += particle.people.represented_population[person]
                    * turnout
                    * utilities[slot]
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
            particle.political.branch_institutional_influence[index] = clamp01(
                particle.political.branch_institutional_influence[index] + 0.08,
            );
        } else {
            particle.political.branch_institutional_influence[index] = clamp01(
                particle.political.branch_institutional_influence[index] - 0.02,
            );
        }
    }
    let _ = topology;
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
