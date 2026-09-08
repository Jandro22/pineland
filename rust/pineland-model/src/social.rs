//! Social exposure and public-behavior aggregation in dense form.

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
    for locality in 0..topology.locality_count() {
        let offset = locality * CONTROL_DIMENSIONS;
        let insurgent_foothold = crate::INSURGENT * topology.locality_count() + locality;
        let embeddedness = particle.footholds.embeddedness[insurgent_foothold];
        let exposure = clamp01(
            embeddedness + 0.2 * particle.locality.violence[locality] + rng.uniform(-0.03, 0.03),
        );
        let rate = config.social_network.behavior_update_rate * config.intervals.social_influence;
        particle.locality.government_control[offset + 5] = clamp01(
            particle.locality.government_control[offset + 5] * (1.0 - rate)
                + (1.0 - exposure) * rate,
        );
        particle.locality.insurgent_control[offset + 5] = clamp01(
            particle.locality.insurgent_control[offset + 5] * (1.0 - rate) + exposure * rate,
        );
        particle.footholds.raw_signal[insurgent_foothold] =
            clamp01(particle.footholds.raw_signal[insurgent_foothold] * 0.98 + exposure * 0.02);
    }
}

pub fn language_compatibility(enabled: bool, shared_language: f64) -> f64 {
    if enabled {
        clamp01(shared_language)
    } else {
        1.0
    }
}
