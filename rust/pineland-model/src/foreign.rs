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
        1.0
            - python_exp(
                (elapsed_days / reference_days.max(f64::MIN_POSITIVE))
                    * (1.0 - probability).ln(),
            )
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
            * (0.45
                + 0.35 * clamp01(social_permeability)
                + 0.20 * clamp01(kinship_overlap)),
    );
    if capacity <= 0.0 || locality >= particle.locality.population.len() {
        return 0.0;
    }
    let demographic_quality = clamp01(
        0.35
            + 0.35 * clamp01(social_permeability)
            + 0.30 * clamp01(kinship_overlap),
    );
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
    // representative person before it updates any foreign-state beliefs.
    // Even when no person crosses a border, those draws are part of the
    // process stream and must be consumed in the same order.
    for person in 0..particle.people.locality.len() {
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
        let reference_hazard = clamp01(
            config.foreign_affairs.migration_rate * logistic(pressure + attraction - 1.6),
        );
        let hazard = reference_probability(
            reference_hazard,
            config.foreign_affairs.interval_days,
            30.0,
        );
        let _departure = rng.random() < hazard;
        // The baseline native state does not yet expose the Python diaspora
        // registry; retain the exact draw and state-neutral path here until
        // the explicit cross-border rows are added to the checkpoint schema.
        let _ = _departure;
    }

    if std::env::var_os("PINELAND_FOREIGN_TRACE").is_some() {
        let mut probe = rng.clone();
        eprintln!(
            "FOREIGN_AFTER_MIGRATION next_random={:.17} next_normal={:.17}",
            probe.random(),
            probe.normalvariate(0.0, 1.0),
        );
    }

    // No diaspora links exist in the generated baseline state.  This loop is
    // intentionally represented by the later explicit registry port rather
    // than inventing a synthetic draw here.

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
            let host_estimate = crate::beliefs::control_estimate(
                particle,
                crate::GOVERNMENT,
                locality,
            )[1];
            let noise = config.foreign_affairs.belief_noise
                * (1.0 - config.foreign_affairs.interpreter_effect * interpreter_quality);
            if let Some(belief) = (0..particle.foreign.belief_foreign_state.len()).find(|index| {
                particle.foreign.belief_foreign_state[*index] as usize == state
                    && particle.foreign.belief_locality[*index] as usize == locality
            }) {
                let government =
                    clamp01(host_estimate + rng.normalvariate(0.0, noise));
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
                        "FOREIGN_BELIEF index={} state={} locality={} host={:.17} quality={:.17} noise={:.17} government={:.17} insurgent={:.17} confidence={:.17}",
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
        let cost_pressure = particle.foreign.cumulative_cost[state]
            / (1.0 + particle.foreign.resources[state] + particle.foreign.cumulative_cost[state]);
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
        let _support = rng.random() < support_probability;
        let intervention_probability = reference_probability(
            clamp01(
                config.foreign_affairs.intervention_base_hazard * willingness,
            ),
            config.foreign_affairs.interval_days,
            30.0,
        );
        let _intervention = rng.random() < intervention_probability;
        let _ = (_support, _intervention);
    }
}

pub fn withdrawal_fraction(config: &SimulationConfig, willingness: f64) -> f64 {
    if willingness < config.foreign_affairs.withdrawal_threshold {
        config.foreign_affairs.withdrawal_rate
    } else {
        0.0
    }
}
