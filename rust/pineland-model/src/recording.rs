//! Imperfect historical recording layer kept separate from latent dynamics.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
) {
    if !config.recording.enabled {
        return;
    }
    let Some(event) = particle.event_log.last().cloned() else {
        return;
    };
    if event.locality == u32::MAX || event.locality as usize >= topology.locality_count() {
        return;
    }
    let locality = event.locality as usize;
    let severity = clamp01(
        particle.locality.violence[locality]
            + 0.05 * rng.normalvariate(0.0, config.recording.severity_noise),
    );
    let access = particle.locality.infrastructure[locality];
    let remoteness = particle.locality.terrain_friction[locality];
    let logit = config.recording.base_logit
        + config.recording.severity_weight * severity
        + config.recording.access_weight * access
        - config.recording.remoteness_penalty * remoteness;
    let probability = 1.0 / (1.0 + (-logit).exp());
    if rng.random() < probability {
        particle.counters.recorded_events = particle.counters.recorded_events.saturating_add(1);
    }
}

pub fn recording_probability(
    config: &SimulationConfig,
    severity: f64,
    access: f64,
    remoteness: f64,
) -> f64 {
    let x = config.recording.base_logit
        + config.recording.severity_weight * severity
        + config.recording.access_weight * access
        - config.recording.remoteness_penalty * remoteness;
    1.0 / (1.0 + (-x).exp())
}
