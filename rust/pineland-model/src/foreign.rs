//! Foreign affairs, sanctuary/support, migration pressure, and withdrawal.

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
    if !config.foreign_affairs.enabled {
        return;
    }
    let n = topology.locality_count();
    let government = particle
        .locality
        .government_control
        .iter()
        .step_by(CONTROL_DIMENSIONS)
        .copied()
        .sum::<f64>()
        / n as f64;
    let insurgent = particle
        .locality
        .insurgent_control
        .iter()
        .skip(1)
        .step_by(CONTROL_DIMENSIONS)
        .copied()
        .sum::<f64>()
        / n as f64;
    let willingness = clamp01(
        config.foreign_affairs.intervention_base_hazard
            * (1.0 + insurgent)
            * (1.0 - government * 0.4),
    );
    if rng.random() < willingness * config.foreign_affairs.interval_days {
        let support = particle.organizations.member_population[crate::INSURGENT]
            * config.foreign_affairs.support_budget_fraction;
        particle.organizations.external_support[crate::INSURGENT] += support;
        particle.organizations.capital[crate::INSURGENT] +=
            support * config.foreign_affairs.host_transfer_efficiency;
        particle
            .formations
            .supply_stock
            .iter_mut()
            .enumerate()
            .filter(|(i, _)| particle.formations.organization[*i] as usize == crate::INSURGENT)
            .for_each(|(_, stock)| *stock += support * 0.02);
    }
    particle.organizations.external_support[crate::INSURGENT] *=
        (1.0 - config.foreign_affairs.withdrawal_rate * 0.01).max(0.0);
    for locality in 0..n {
        particle.locality.displaced_population[locality] = (particle.locality.displaced_population
            [locality]
            + particle.locality.population[locality]
                * config.foreign_affairs.migration_rate
                * 0.01
                * insurgent)
            .min(particle.locality.population[locality]);
    }
}

pub fn withdrawal_fraction(config: &SimulationConfig, willingness: f64) -> f64 {
    if willingness < config.foreign_affairs.withdrawal_threshold {
        config.foreign_affairs.withdrawal_rate
    } else {
        0.0
    }
}
