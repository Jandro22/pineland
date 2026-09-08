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
) {
    if !config.political_order.enabled {
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

pub fn turnout(particle: &ParticleState, locality: usize, config: &SimulationConfig) -> f64 {
    let offset = locality * CONTROL_DIMENSIONS;
    clamp01(
        0.5 + config.political_order.election_turnout_sensitivity
            * (particle.locality.government_control[offset + 5]
                - particle.locality.violence[locality]),
    )
}
