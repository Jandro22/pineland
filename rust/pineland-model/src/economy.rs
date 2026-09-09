//! Economic output, fiscal extraction, and external support flows.
//!
//! The implementation mirrors `ProcessEngine.on_economy`: output is advanced
//! once per locality, government tax is credited immediately, and insurgent
//! extraction/support is applied in stable organization order.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::python_exp;
use pineland_core::state::{ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const FISCAL: usize = 4;

fn organization_control(particle: &ParticleState, locality: usize, organization: usize) -> f64 {
    if organization == crate::INSURGENT {
        return particle.locality.insurgent_control[locality * CONTROL_DIMENSIONS + FISCAL];
    }
    let organization_count = particle.organizations.kind.len();
    let offset = pineland_core::state::LocalityState::organization_control_offset(
        locality,
        organization,
        organization_count,
    );
    particle
        .locality
        .organization_control
        .get(offset + FISCAL)
        .copied()
        .unwrap_or(0.0)
}

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
    let cycle_scale = elapsed_days / 30.0;
    let government = crate::GOVERNMENT;
    let insurgents = (0..particle.organizations.kind.len())
        .filter(|organization| {
            particle.organizations.kind[*organization] == 3
                && particle.organizations.active[*organization] != 0
        })
        .collect::<Vec<_>>();

    for locality in 0..topology.locality_count() {
        let offset = locality * CONTROL_DIMENSIONS;
        let security = particle.locality.government_control[offset + 1];
        let access_pressure = crate::access::locality_access_pressure(particle, topology, locality);
        let reference_net_fraction = (0.002 + 0.004 * particle.locality.infrastructure[locality])
            * (0.5 + 0.5 * security)
            - (0.003 * particle.locality.violence[locality]
                + 0.002 * particle.locality.disruption[locality])
            - config.access_restriction.economic_penalty * access_pressure
            - 0.001;
        let base = (1.0 + reference_net_fraction).max(0.0);
        let growth_factor = if base == 0.0 {
            0.0
        } else {
            // Python evaluates `base ** cycle_scale`; exp(scale*ln(base))
            // retains the same real-valued operation while using the
            // project-wide platform math wrapper for the exponential.
            python_exp(cycle_scale * base.ln())
        };
        let delta = particle.locality.economic_output[locality] * (growth_factor - 1.0);
        particle.locality.economic_output[locality] =
            (particle.locality.economic_output[locality] + delta).max(1.0);

        let tax = particle.locality.economic_output[locality]
            * 0.0005
            * particle.locality.government_control[offset + FISCAL]
            * cycle_scale;
        particle.organizations.capital[government] += tax;
        for &organization in &insurgents {
            let extraction = particle.locality.economic_output[locality]
                * 0.00015
                * organization_control(particle, locality, organization)
                * cycle_scale;
            particle.organizations.capital[organization] += extraction;
        }
    }

    // External support is an organization-level annual flow and is credited
    // exactly once per active organization, not once per locality.
    for organization in insurgents {
        particle.organizations.capital[organization] +=
            particle.organizations.external_support[organization] / 12.0 * cycle_scale;
    }
}
