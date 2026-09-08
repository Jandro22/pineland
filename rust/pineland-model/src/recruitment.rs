//! Recruitment, local manpower pools, and foothold renewal.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn recruit(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    elapsed_days: f64,
) {
    // Recruitment is intentionally not evaluated at the zero-duration
    // initialization event. This mirrors ProcessEngine.on_recruitment and
    // preserves the process RNG continuation contract.
    if !config.include_insurgency || elapsed_days <= 0.0 {
        return;
    }
    let n = topology.locality_count();
    let mut total_recruited = 0.0;
    for locality in 0..n {
        let index = crate::INSURGENT * n + locality;
        let access = particle.footholds.access[index];
        if config.organization_ecology.recruitment_requires_access && access < 0.02 {
            continue;
        }
        let social_signal = particle.locality.insurgent_control
            [locality * pineland_core::state::CONTROL_DIMENSIONS + 5];
        let grievance_proxy = clamp01(
            0.2 + particle.locality.violence[locality] + particle.locality.disruption[locality],
        );
        let potential = particle.locality.population[locality]
            * config.recruitment_rate.max(0.0)
            * (0.3 + access)
            * (0.4 + social_signal + grievance_proxy * 0.3)
            * config.intervals.recruitment;
        let recruited = if rng.random() < (0.25 + access * 0.5).min(1.0) {
            potential * (0.7 + 0.6 * rng.random())
        } else {
            0.0
        };
        particle.footholds.cumulative_recruits[index] += recruited;
        particle.footholds.membership[index] = clamp01(
            particle.footholds.membership[index]
                + recruited / particle.locality.population[locality].max(1.0),
        );
        particle.footholds.strength[index] += recruited
            * config
                .organization_ecology
                .fighter_conversion_fraction
                .max(0.01);
        particle.footholds.embeddedness[index] = clamp01(
            particle.footholds.embeddedness[index]
                + recruited / particle.locality.population[locality].max(1.0) * 3.0,
        );
        particle.footholds.sustainment[index] =
            clamp01(particle.footholds.sustainment[index] + access * 0.01);
        particle.footholds.updated_at[index] = time;
        total_recruited += recruited;
        let target = particle
            .formations
            .organization
            .iter()
            .enumerate()
            .find(|(formation, organization)| {
                particle.formations.active[*formation] != 0
                    && **organization as usize == crate::INSURGENT
                    && particle.formations.locality[*formation] as usize == locality
            })
            .map(|(formation, _)| formation);
        if let Some(formation) = target {
            particle.formations.personnel[formation] +=
                recruited * config.organization_ecology.fighter_conversion_fraction;
            particle.formations.supply_capacity[formation] += recruited
                * config.organization_ecology.fighter_conversion_fraction
                * config.logistics.formation_supply_days;
        }
    }
    particle.organizations.member_population[crate::INSURGENT] += total_recruited;
    particle.counters.recruitment += total_recruited;
}

pub fn foothold_viability(
    particle: &ParticleState,
    organization: usize,
    locality: usize,
    topology: &StaticTopology,
    threshold: f64,
) -> bool {
    let index = organization * topology.locality_count() + locality;
    particle
        .footholds
        .strength
        .get(index)
        .copied()
        .unwrap_or(0.0)
        > threshold
        && particle
            .footholds
            .sustainment
            .get(index)
            .copied()
            .unwrap_or(0.0)
            > threshold
}
