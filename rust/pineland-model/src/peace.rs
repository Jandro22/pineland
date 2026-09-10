//! Negotiation, ceasefire, demobilization, implementation, and recurrence.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    _particle: &mut ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
    elapsed_days: f64,
) {
    // The compact native particle state does not retain Python's negotiation,
    // agreement, or provision records.  Do not synthesize agreement or
    // recurrence effects from a hazard-only approximation: that creates
    // latent state changes which the Python reference did not make (and, in
    // particular, demobilizes insurgent formations spuriously).  Consume the
    // same one decision draw used by the no-active-negotiation Python path so
    // the dedicated process stream keeps its cadence without changing the
    // representable particle state.
    if !config.peace_process.enabled || elapsed_days <= 0.0 {
        return;
    }
    let _ = rng.random();
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
