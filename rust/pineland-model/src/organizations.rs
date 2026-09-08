//! Endogenous organization ecology over the fixed numeric organization table.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // The Python process engine treats the initialization-time ecology event
    // as a true no-op.  In particular, it must not consume the ecology RNG
    // stream or mutate organization/foothold state before a positive ecology
    // interval has elapsed.
    if !config.organization_ecology.enabled || elapsed_days <= 0.0 {
        return;
    }
    for organization in 0..particle.organizations.active.len() {
        if particle.organizations.active[organization] == 0 {
            continue;
        }
        let adaptation = config.organization_ecology.adaptation_rate * 0.01;
        particle.organizations.cohesion[organization] = clamp01(
            particle.organizations.cohesion[organization]
                + adaptation * (0.6 - particle.organizations.cohesion[organization]),
        );
        particle.organizations.capital[organization] = (particle.organizations.capital
            [organization]
            + particle.organizations.external_support[organization] * 0.01)
            .max(0.0);
        if rng.random()
            < config.organization_ecology.succession_base_hazard
                * config.organization_ecology.interval_days
        {
            particle.organizations.succession_count[organization] =
                particle.organizations.succession_count[organization].saturating_add(1);
            particle.organizations.persistence[organization] =
                clamp01(particle.organizations.persistence[organization] + 0.02);
        }
    }
    let n = topology.locality_count();
    for locality in 0..n {
        let index = crate::INSURGENT * n + locality;
        let age = (time - particle.footholds.updated_at[index]).max(0.0);
        let recent = (-age
            / config
                .organization_ecology
                .local_foothold_memory_days
                .max(f64::MIN_POSITIVE))
        .exp();
        particle.footholds.sustainment[index] =
            clamp01(particle.footholds.sustainment[index] * (0.98 + 0.02 * recent));
        if particle.footholds.strength[index]
            > config.organization_ecology.minimum_formation_personnel
        {
            particle.footholds.viable_activation_count[index] =
                particle.footholds.viable_activation_count[index].saturating_add(1);
        }
        if rng.random()
            < config.organization_ecology.collapse_base_hazard
                * config.organization_ecology.interval_days
                * (1.0 - particle.footholds.sustainment[index])
        {
            particle.footholds.active[index] = 0;
            particle.footholds.strength[index] *= 0.5;
        }
    }
}

pub fn onset_hazard(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    locality: usize,
) -> f64 {
    if locality >= topology.locality_count() {
        return 0.0;
    }
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    config.organization_ecology.birth_base_hazard
        * (1.0 - particle.locality.government_control[offset + 5])
        * (1.0 + particle.locality.violence[locality])
}
