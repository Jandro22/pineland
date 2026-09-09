//! Foreign affairs, sanctuary/support, migration pressure, and withdrawal.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

fn logistic(value: f64) -> f64 {
    if value >= 0.0 {
        1.0 / (1.0 + python_exp(-value))
    } else {
        let exponential = python_exp(value);
        exponential / (1.0 + exponential)
    }
}

fn reference_probability(probability: f64, elapsed_days: f64, reference_days: f64) -> f64 {
    let probability = clamp01(probability);
    if probability <= 0.0 || elapsed_days <= 0.0 {
        0.0
    } else if probability >= 1.0 {
        1.0
    } else {
        1.0 - python_exp(
            (elapsed_days / reference_days.max(f64::MIN_POSITIVE)) * (1.0 - probability).ln(),
        )
    }
}

fn expected_destination_control(
    particle: &ParticleState,
    person: usize,
    locality: usize,
    locality_count: usize,
) -> f64 {
    let scalar = particle.people.expected_control[person * 2];
    let mask_index = person * locality_count + locality;
    let value_index = mask_index * 2;
    if mask_index < particle.people.expected_destination_control_present.len()
        && particle.people.expected_destination_control_present[mask_index] & 1 != 0
        && value_index < particle.people.expected_destination_control.len()
    {
        particle.people.expected_destination_control[value_index]
    } else {
        scalar
    }
}

fn interpreter_channel_quality(
    particle: &ParticleState,
    foreign_state: usize,
    locality: usize,
    language_overlap: f64,
    social_permeability: f64,
    kinship_overlap: f64,
) -> f64 {
    let capacity = clamp01(
        language_overlap
            * (0.45 + 0.35 * clamp01(social_permeability) + 0.20 * clamp01(kinship_overlap)),
    );
    if capacity <= 0.0 || locality >= particle.locality.population.len() {
        return 0.0;
    }
    let demographic_quality =
        clamp01(0.35 + 0.35 * clamp01(social_permeability) + 0.30 * clamp01(kinship_overlap));
    let mut broker_quality: f64 = 0.0;
    for index in 0..particle.foreign.interpreter_person.len() {
        if particle.foreign.interpreter_foreign_state[index] as usize != foreign_state
            || particle.foreign.interpreter_locality[index] as usize != locality
        {
            continue;
        }
        broker_quality = broker_quality.max(
            particle.foreign.interpreter_foreign_language[index]
                * particle.foreign.interpreter_local_language[index]
                * particle.foreign.interpreter_foreign_trust[index]
                * particle.foreign.interpreter_local_trust[index]
                * particle.foreign.interpreter_cultural_knowledge[index],
        );
    }
    clamp01(capacity * demographic_quality.max(broker_quality))
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // The reference process returns before touching state or consuming RNG
    // when the scheduler reports the initialization event with zero elapsed
    // time.
    if !config.foreign_affairs.enabled || elapsed_days <= 0.0 {
        return;
    }
    // Python evaluates the cross-border migration hazard for every
    // representative person before it updates diaspora links or foreign
    // beliefs.  External membership is explicit state: it changes the
    // return branch, but still consumes exactly one draw per person.
    let locality_count = topology.locality_count();
    for person in 0..particle.people.locality.len() {
        if particle.people.external_state[person] != u32::MAX {
            let state = particle.people.external_state[person] as usize;
            let perceived_home_security = expected_destination_control(
                particle,
                person,
                particle.people.home[person] as usize,
                locality_count,
            );
            let safety_gain =
                (1.0 - perceived_home_security) - (1.0 - particle.foreign.opportunity[state]) * 0.2;
            let reference_hazard = clamp01(
                config.foreign_affairs.return_rate
                    * logistic(-2.0 * safety_gain + particle.people.state_legitimacy[person]),
            );
            let hazard =
                reference_probability(reference_hazard, config.foreign_affairs.interval_days, 30.0);
            if rng.random() < hazard {
                particle.people.external_state[person] = u32::MAX;
                particle.people.migration_status[person] = 4;
                particle.people.origin_tie_strength[person] =
                    clamp01(particle.people.origin_tie_strength[person] + 0.15);
            } else {
                particle.people.origin_tie_strength[person] *=
                    python_exp(-0.02 * config.foreign_affairs.interval_days / 30.0);
                for link in 0..particle.foreign.diaspora_person.len() {
                    if particle.foreign.diaspora_person[link] as usize == person {
                        particle.foreign.diaspora_social_strength[link] =
                            particle.people.origin_tie_strength[person];
                    }
                }
            }
            continue;
        }

        let locality = particle.people.residence[person] as usize;
        let district = topology.locality_to_district[locality] as usize;
        let Some(border) = (0..particle.foreign.border_foreign_state.len())
            .filter(|index| particle.foreign.border_district[*index] as usize == district)
            .max_by(|left, right| {
                particle.foreign.border_social_permeability[*left]
                    .total_cmp(&particle.foreign.border_social_permeability[*right])
            })
        else {
            continue;
        };
        let state = particle.foreign.border_foreign_state[border] as usize;
        let pressure = particle.locality.violence[locality]
            + particle.people.fear[person]
            + 0.4 * (1.0 - particle.people.government_legitimacy[person]);
        let attraction = particle.foreign.opportunity[state]
            + particle.foreign.border_kinship_overlap[border]
            + particle.foreign.border_language_overlap[border]
            - particle.foreign.border_terrain_friction[border]
                * (1.0 - particle.foreign.border_legal_permeability[border]);
        let reference_hazard =
            clamp01(config.foreign_affairs.migration_rate * logistic(pressure + attraction - 1.6));
        let hazard =
            reference_probability(reference_hazard, config.foreign_affairs.interval_days, 30.0);
        if rng.random() < hazard {
            particle.people.external_state[person] = state as u32;
            particle.people.migration_status[person] =
                if particle.locality.violence[locality] > 0.25 {
                    1
                } else if particle.people.fear[person] > 0.55 {
                    2
                } else {
                    3
                };
            particle.people.origin_tie_strength[person] = 1.0;
            particle.foreign.diaspora_person.push(person as u32);
            particle.foreign.diaspora_foreign_state.push(state as u32);
            particle
                .foreign
                .diaspora_origin_locality
                .push(particle.people.home[person]);
            particle.foreign.diaspora_social_strength.push(1.0);
            particle
                .foreign
                .diaspora_financial_capacity
                .push(particle.people.resources[person] * 0.2);
            particle
                .foreign
                .diaspora_information_reliability
                .push(clamp01(
                    0.35 + 0.5 * particle.foreign.border_language_overlap[border],
                ));
            particle.foreign.diaspora_created_at.push(time);
        }
    }

    // Python snapshots the active insurgent recipients once, before the
    // neighbor-state loop.  Support recipient selection is therefore based
    // on the same live organization set for every foreign state in this
    // event, with prior support breaking ties by organization identity.
    let active_insurgents = (0..particle.organizations.kind.len())
        .filter(|&organization| {
            particle.organizations.kind[organization] == 3
                && particle.organizations.active.get(organization).copied() == Some(1)
        })
        .collect::<Vec<_>>();

    // Diaspora remittances are resource transfers from the foreign system to
    // the represented civilian cohort.  Message draws occur after every
    // active link's transfer, exactly as in the Python registry loop.
    let cycle_scale = config.foreign_affairs.interval_days / 30.0;
    for link in 0..particle.foreign.diaspora_person.len() {
        let person = particle.foreign.diaspora_person[link] as usize;
        if particle.people.external_state[person] == u32::MAX {
            continue;
        }
        let state = particle.foreign.diaspora_foreign_state[link] as usize;
        let amount = particle.foreign.resources[state].min(
            particle.foreign.diaspora_financial_capacity[link]
                * config.foreign_affairs.diaspora_remittance_rate
                * particle.foreign.diaspora_social_strength[link]
                * cycle_scale,
        );
        particle.foreign.resources[state] -= amount;
        particle.people.resources[person] += amount;
        let household = particle.people.household[person] as usize;
        if household < particle.households.resources.len() {
            particle.households.resources[household] += amount;
        }
        particle.foreign.cumulative_external_remittances += amount;
        let message_probability = reference_probability(
            clamp01(
                config.foreign_affairs.diaspora_information_rate
                    * particle.foreign.diaspora_information_reliability[link],
            ),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let _message = rng.random() < message_probability;
    }

    for state in 0..particle.foreign.resources.len() {
        let mut border_indices = Vec::new();
        for border in 0..particle.foreign.border_foreign_state.len() {
            if particle.foreign.border_foreign_state[border] as usize == state {
                border_indices.push(border);
            }
        }
        for border in border_indices {
            let locality = particle.foreign.border_locality[border] as usize;
            let interpreter_quality = interpreter_channel_quality(
                particle,
                state,
                locality,
                particle.foreign.border_language_overlap[border],
                particle.foreign.border_social_permeability[border],
                particle.foreign.border_kinship_overlap[border],
            );
            // Foreign actors consume the government actor's reported belief,
            // not realized locality control.  This is the same
            // `belief_view("government").locality_control(..., "government")`
            // boundary used by Python.
            let host_estimate =
                crate::beliefs::control_estimate(particle, crate::GOVERNMENT, locality)[1];
            let noise = config.foreign_affairs.belief_noise
                * (1.0 - config.foreign_affairs.interpreter_effect * interpreter_quality);
            if let Some(belief) = (0..particle.foreign.belief_foreign_state.len()).find(|index| {
                particle.foreign.belief_foreign_state[*index] as usize == state
                    && particle.foreign.belief_locality[*index] as usize == locality
            }) {
                let government = clamp01(host_estimate + rng.normalvariate(0.0, noise));
                let insurgent = clamp01(1.0 - government + rng.normalvariate(0.0, noise));
                particle.foreign.belief_government_control[belief] = government;
                particle.foreign.belief_insurgent_presence[belief] = insurgent;
                particle.foreign.belief_confidence[belief] = clamp01(
                    0.2 + 0.45 * interpreter_quality
                        + 0.2 * particle.foreign.border_language_overlap[border],
                );
                particle.foreign.belief_updated_at[belief] = time;
                if std::env::var_os("PINELAND_FOREIGN_TRACE").is_some() {
                    eprintln!(
                        "FOREIGN_BELIEF time={:.17} index={} state={} locality={} host={:.17} quality={:.17} noise={:.17} government={:.17} insurgent={:.17} confidence={:.17}",
                        time,
                        belief,
                        state,
                        locality,
                        host_estimate,
                        interpreter_quality,
                        noise,
                        government,
                        insurgent,
                        particle.foreign.belief_confidence[belief],
                    );
                }
            }
        }

        let belief_indices = (0..particle.foreign.belief_foreign_state.len())
            .filter(|index| particle.foreign.belief_foreign_state[*index] as usize == state)
            .collect::<Vec<_>>();
        let perceived_progress = belief_indices
            .iter()
            .map(|index| particle.foreign.belief_government_control[*index])
            .sum::<f64>()
            / belief_indices.len().max(1) as f64;
        let cost_denominator =
            (particle.foreign.resources[state] + particle.foreign.cumulative_cost[state]).max(1.0);
        let cost_pressure = particle.foreign.cumulative_cost[state] / cost_denominator;
        let rival_presence = (particle.foreign.rival_offsets[state + 1]
            - particle.foreign.rival_offsets[state])
            .min(1) as f64
            * 0.0;
        let willingness = clamp01(logistic(
            1.2 * particle.foreign.stability_preference[state]
                + particle.foreign.regional_influence[state]
                + perceived_progress
                - config.foreign_affairs.willingness_cost_weight * cost_pressure
                - config.foreign_affairs.willingness_casualty_weight
                    * particle.foreign.cumulative_casualties[state]
                    / 100.0
                - particle.foreign.domestic_opposition[state]
                - 1.0,
        ));
        particle.foreign.willingness[state] = willingness;

        // The Python process samples support and intervention decisions for
        // every neighbor, even when both probabilities are zero in a
        // particular realization.  Preserve those stream positions now.
        let support_probability = reference_probability(
            clamp01(willingness * 0.3),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let support_draw = if config.foreign_affairs.support_budget_fraction > 0.0 {
            Some(rng.random())
        } else {
            None
        };
        let support_selected = support_draw.is_some_and(|draw| draw < support_probability);
        if support_selected {
            let recipient = if particle.foreign.government_alignment[state]
                >= particle.foreign.ideological_alignment[state]
                || active_insurgents.is_empty()
            {
                crate::GOVERNMENT
            } else {
                active_insurgents
                    .iter()
                    .copied()
                    .min_by(|left, right| {
                        let left_support = particle
                            .foreign
                            .support_foreign_state
                            .iter()
                            .zip(&particle.foreign.support_recipient)
                            .zip(&particle.foreign.support_total)
                            .filter(|((foreign, candidate), _)| {
                                **foreign as usize == state && **candidate as usize == *left
                            })
                            .map(|(_, total)| *total)
                            .sum::<f64>();
                        let right_support = particle
                            .foreign
                            .support_foreign_state
                            .iter()
                            .zip(&particle.foreign.support_recipient)
                            .zip(&particle.foreign.support_total)
                            .filter(|((foreign, candidate), _)| {
                                **foreign as usize == state && **candidate as usize == *right
                            })
                            .map(|(_, total)| *total)
                            .sum::<f64>();
                        right_support
                            .total_cmp(&left_support)
                            .then_with(|| left.cmp(right))
                    })
                    .unwrap_or(crate::GOVERNMENT)
            };
            let total = particle.foreign.resources[state].min(
                particle.foreign.resources[state]
                    * config.foreign_affairs.support_budget_fraction
                    * willingness,
            );
            if total > 0.0 {
                particle.foreign.resources[state] -= total;
                let financial = total * 0.22;
                let political = total * 0.08;
                let material = total * 0.19;
                let training = total * 0.14;
                let organizational = total * 0.10;
                let denominator = total.max(1.0);
                particle.organizations.capital[recipient] += financial;
                if recipient == crate::GOVERNMENT {
                    let learning = training + organizational;
                    let institution_count = particle.political.institution_capacity.len();
                    for capacity in &mut particle.political.institution_capacity {
                        *capacity = clamp01(
                            *capacity
                                + learning / denominator * 0.02 / institution_count.max(1) as f64,
                        );
                    }
                    for person in 0..particle.people.government_legitimacy.len() {
                        particle.people.government_legitimacy[person] = clamp01(
                            particle.people.government_legitimacy[person]
                                + political / denominator
                                    * 0.002
                                    * (particle.people.trust[person] - 0.35),
                        );
                    }
                } else if particle.organizations.kind[recipient] == 3 {
                    // Match deliver_support's insurgent-recipient effects.
                    // Financial support enters the ordinary organization
                    // resource account above; these additional channels alter
                    // local execution and sponsor dependence without creating
                    // personnel.
                    particle.organizations.external_sanctuary[recipient] =
                        clamp01(particle.organizations.external_sanctuary[recipient] + 0.12);
                    let phenotype = recipient * 8 + 7;
                    if phenotype < particle.organizations.phenotype.len() {
                        particle.organizations.phenotype[phenotype] =
                            clamp01(particle.organizations.phenotype[phenotype] + 0.04);
                    }
                    particle.organizations.capital_organizational[recipient] = clamp01(
                        particle.organizations.capital_organizational[recipient]
                            + organizational / denominator * 0.08,
                    );
                    let formation_count = particle
                        .formations
                        .organization
                        .iter()
                        .filter(|owner| **owner as usize == recipient)
                        .count()
                        .max(1) as f64;
                    let material_per_formation = material / formation_count;
                    for formation in 0..particle.formations.organization.len() {
                        if particle.formations.organization[formation] as usize != recipient {
                            continue;
                        }
                        particle.formations.quality[formation] = clamp01(
                            particle.formations.quality[formation] + training / denominator * 0.025,
                        );
                        particle.formations.cohesion[formation] = clamp01(
                            particle.formations.cohesion[formation]
                                + training / denominator * 0.015,
                        );
                        let accepted = material_per_formation.min(
                            particle.formations.supply_capacity[formation]
                                - particle.formations.supply_stock[formation],
                        );
                        particle.formations.supply_stock[formation] += accepted;
                        particle.logistics.cumulative_produced += accepted;
                    }
                }
                particle.foreign.cumulative_cost[state] += total;
                particle.foreign.support_foreign_state.push(state as u32);
                particle.foreign.support_recipient.push(recipient as u32);
                particle.foreign.support_total.push(total);
            }
        }
        let intervention_probability = reference_probability(
            clamp01(config.foreign_affairs.intervention_base_hazard * willingness),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let _intervention = rng.random() < intervention_probability;
        let _ = (_intervention, rival_presence);
    }
}

pub fn withdrawal_fraction(config: &SimulationConfig, willingness: f64) -> f64 {
    if willingness < config.foreign_affairs.withdrawal_threshold {
        config.foreign_affairs.withdrawal_rate
    } else {
        0.0
    }
}
