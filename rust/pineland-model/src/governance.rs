//! Administrative and non-state governance transitions.

use pineland_core::config::SimulationConfig;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _time: f64,
    elapsed_days: f64,
) {
    if elapsed_days <= 0.0 {
        return;
    }
    for locality in 0..topology.locality_count() {
        let offset = locality * CONTROL_DIMENSIONS;
        let capacity = particle.locality.administrative_capacity[locality];
        let disruption = particle.locality.disruption[locality];
        let violence = particle.locality.violence[locality];
        let learning =
            config.political_order.capacity_learning_rate * config.intervals.governance / 30.0;
        particle.locality.government_governance[locality] = clamp01(
            particle.locality.government_governance[locality] + learning * capacity
                - config.political_order.capacity_decay_rate * disruption,
        );
        particle.locality.government_control[offset + 2] = clamp01(
            particle.locality.government_control[offset + 2] + learning * capacity
                - violence * 0.01,
        );
        particle.locality.government_control[offset + 3] = clamp01(
            particle.locality.government_control[offset + 3] + learning * 0.8 - violence * 0.012,
        );
        particle.locality.government_control[offset + 4] = clamp01(
            particle.locality.government_control[offset + 4] + learning * 0.6 - disruption * 0.006,
        );
        particle.locality.government_control[offset + 5] = clamp01(
            particle.locality.government_control[offset + 5] + learning * 0.35 - violence * 0.01,
        );
        let foothold = crate::INSURGENT * topology.locality_count() + locality;
        let rooted = particle
            .footholds
            .embeddedness
            .get(foothold)
            .copied()
            .unwrap_or(0.0);
        if config.nonstate_governance.enabled {
            particle.locality.insurgent_governance[locality] = clamp01(
                particle.locality.insurgent_governance[locality]
                    + config.nonstate_governance.gain_per_30_days * rooted
                    - config.nonstate_governance.decay_per_30_days * (1.0 - rooted),
            );
        }
        particle.locality.insurgent_control[offset + 2] = clamp01(
            particle.locality.insurgent_control[offset + 2]
                + particle.locality.insurgent_governance[locality] * 0.02,
        );
        particle.locality.insurgent_control[offset + 5] = clamp01(
            particle.locality.insurgent_control[offset + 5]
                + particle.locality.insurgent_governance[locality] * 0.015,
        );
    }
}
