//! Negotiation, ceasefire, demobilization, implementation, and recurrence.

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
    // Peace processing is a strict no-op at the initial zero-duration event;
    // keeping the RNG untouched is part of trajectory continuation parity.
    if !config.peace_process.enabled || elapsed_days <= 0.0 {
        return;
    }
    let n = topology.locality_count();
    let mut violence = 0.0;
    for locality in 0..n {
        violence += particle.locality.violence[locality];
    }
    violence /= n as f64;
    let fragmentation = particle
        .organizations
        .active
        .iter()
        .filter(|active| **active != 0)
        .count() as f64
        / particle.organizations.active.len().max(1) as f64;
    let bargaining = clamp01(
        config.peace_process.negotiation_base_hazard
            * (1.0 - violence)
            * (1.0 - 0.2 * fragmentation),
    );
    if rng.random() < bargaining * config.peace_process.interval_days {
        let agreement = config.peace_process.agreement_base_hazard
            * (1.0 - violence)
            * (0.5 + particle.organizations.cohesion[crate::INSURGENT]);
        if rng.random() < agreement {
            for locality in 0..n {
                particle.locality.violence[locality] *=
                    (1.0 - config.peace_process.implementation_rate).max(0.0);
                let offset = locality * CONTROL_DIMENSIONS;
                particle.locality.government_control[offset + 3] =
                    clamp01(particle.locality.government_control[offset + 3] + 0.01);
            }
            let demobilized = particle
                .formations
                .personnel
                .iter_mut()
                .enumerate()
                .filter(|(i, _)| particle.formations.organization[*i] as usize == crate::INSURGENT)
                .map(|(_, personnel)| {
                    let amount = *personnel * config.peace_process.demobilization_rate;
                    *personnel -= amount;
                    amount
                })
                .sum::<f64>();
            particle.organizations.member_population[crate::INSURGENT] =
                (particle.organizations.member_population[crate::INSURGENT] - demobilized).max(0.0);
        }
    } else if rng.random()
        < config.peace_process.recurrence_base_hazard * config.peace_process.interval_days
    {
        for locality in 0..n {
            particle.locality.violence[locality] =
                clamp01(particle.locality.violence[locality] + 0.02);
        }
    }
}

pub fn agreement_probability(
    config: &SimulationConfig,
    violence: f64,
    credibility: f64,
    fragmentation: f64,
) -> f64 {
    clamp01(
        config.peace_process.agreement_base_hazard * (1.0 - violence) * credibility.max(0.0)
            / (1.0 + config.peace_process.fragmentation_penalty * fragmentation.max(0.0)),
    )
}
