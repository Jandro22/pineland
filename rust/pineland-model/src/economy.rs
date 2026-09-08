//! Economic production, disruption, and fiscal control.

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
        let violence = particle.locality.violence[locality];
        let disruption = particle.locality.disruption[locality];
        let offset = locality * CONTROL_DIMENSIONS;
        let recovery = (0.002 + particle.locality.government_control[offset + 4] * 0.004)
            * config.intervals.economy;
        particle.locality.disruption[locality] =
            clamp01(disruption * (1.0 - 0.01 * config.intervals.economy) + violence * 0.01);
        particle.locality.economic_output[locality] = (particle.locality.economic_output[locality]
            * (1.0 - particle.locality.disruption[locality] * 0.005)
            * (1.0 + recovery))
            .max(0.0);
        particle.locality.government_control[offset + 4] = clamp01(
            particle.locality.government_control[offset + 4]
                + 0.002 * particle.locality.economic_output[locality].ln_1p() / 10.0
                - particle.locality.disruption[locality]
                    * config.access_restriction.economic_penalty,
        );
        particle.locality.violence[locality] =
            clamp01(violence * (-0.01 * config.intervals.economy).exp());
    }
}
