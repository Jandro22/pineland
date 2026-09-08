//! Spatial armed contact opportunity and combat resolution.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::scheduler::EventPayload;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn schedule_contacts(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) -> Result<(), pineland_core::scheduler::SchedulerError> {
    if !config.include_insurgency {
        return Ok(());
    }
    let mut candidates = Vec::new();
    for first in 0..particle.formations.personnel.len() {
        if particle.formations.active[first] == 0
            || particle.formations.organization[first] as usize != crate::INSURGENT
        {
            continue;
        }
        for second in 0..particle.formations.personnel.len() {
            if particle.formations.active[second] == 0
                || !matches!(
                    particle.formations.organization[second] as usize,
                    crate::MILITARY | crate::POLICE
                )
            {
                continue;
            }
            if first == second {
                continue;
            }
            let locality_a = particle.formations.locality[first] as usize;
            let locality_b = particle.formations.locality[second] as usize;
            let distance = topology.locality_distance(locality_a.into(), locality_b.into());
            if locality_a != locality_b && distance > 35.0 {
                continue;
            }
            let pressure = if locality_a == locality_b { 1.0 } else { 0.35 };
            let readiness = (particle.formations.effective_readiness(first)
                + particle.formations.effective_readiness(second))
                / 2.0;
            let probability = 1.0
                - (-config.contact_rate.max(0.0)
                    * config.intervals.contact
                    * pressure
                    * (0.2 + readiness))
                    .exp();
            if rng.random() < probability {
                candidates.push((
                    first,
                    second,
                    locality_a,
                    particle.formations.microzone[first] as usize,
                ));
            }
        }
    }
    candidates.sort_unstable();
    candidates.dedup();
    for (first, second, locality, microzone) in candidates {
        particle.scheduler.schedule(
            time,
            100,
            EventPayload::Contact {
                first: first.into(),
                second: second.into(),
                locality: locality.into(),
                microzone: microzone.into(),
            },
        )?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub fn resolve_contact(
    particle: &mut ParticleState,
    _topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
    first: usize,
    second: usize,
    locality: usize,
    microzone: usize,
) {
    if first >= particle.formations.personnel.len()
        || second >= particle.formations.personnel.len()
        || first == second
    {
        return;
    }
    if particle.formations.active[first] == 0 || particle.formations.active[second] == 0 {
        return;
    }
    let first_strength = particle.formations.effective_strength(first).max(0.001);
    let second_strength = particle.formations.effective_strength(second).max(0.001);
    let initiative = first_strength / (first_strength + second_strength);
    let stochastic = (1.0 + config.combat.stochastic_sigma * rng.normalvariate(0.0, 1.0)).max(0.1);
    let first_loss_fraction = clamp01(
        config.combat.base_attrition_rate
            * stochastic
            * (0.6 + second_strength / first_strength).min(3.0),
    )
    .min(config.combat.max_loss_fraction);
    let second_loss_fraction = clamp01(
        config.combat.base_attrition_rate
            * (2.0 - stochastic * 0.35).max(0.2)
            * (0.6 + first_strength / second_strength).min(3.0),
    )
    .min(config.combat.max_loss_fraction);
    let first_loss = particle.formations.personnel[first] * first_loss_fraction;
    let second_loss = particle.formations.personnel[second] * second_loss_fraction;
    particle.formations.personnel[first] =
        (particle.formations.personnel[first] - first_loss).max(0.0);
    particle.formations.personnel[second] =
        (particle.formations.personnel[second] - second_loss).max(0.0);
    particle.formations.cumulative_losses[first] += first_loss;
    particle.formations.cumulative_losses[second] += second_loss;
    particle.formations.cohesion[first] = clamp01(
        particle.formations.cohesion[first]
            - first_loss_fraction * config.combat.cohesion_loss_multiplier,
    );
    particle.formations.cohesion[second] = clamp01(
        particle.formations.cohesion[second]
            - second_loss_fraction * config.combat.cohesion_loss_multiplier,
    );
    particle.formations.readiness[first] = clamp01(
        particle.formations.readiness[first]
            - first_loss_fraction * config.combat.readiness_cost_multiplier,
    );
    particle.formations.readiness[second] = clamp01(
        particle.formations.readiness[second]
            - second_loss_fraction * config.combat.readiness_cost_multiplier,
    );
    let supply = (first_loss + second_loss)
        * config.combat.supply_per_person_hour
        * config.combat.interval_hours;
    particle.formations.supply_stock[first] =
        (particle.formations.supply_stock[first] - supply * 0.6).max(0.0);
    particle.formations.supply_stock[second] =
        (particle.formations.supply_stock[second] - supply * 0.4).max(0.0);
    if particle.formations.personnel[first] < 1.0
        || particle.formations.cohesion[first] < config.combat.ineffective_cohesion
    {
        particle.formations.operational_status[first] = 0;
    }
    if particle.formations.personnel[second] < 1.0
        || particle.formations.cohesion[second] < config.combat.ineffective_cohesion
    {
        particle.formations.operational_status[second] = 0;
    }
    if locality < particle.locality.violence.len() {
        particle.locality.violence[locality] =
            clamp01(particle.locality.violence[locality] + 0.08 + 0.02 * rng.random());
        particle.locality.disruption[locality] =
            clamp01(particle.locality.disruption[locality] + 0.04);
    }
    particle.counters.contacts = particle.counters.contacts.saturating_add(1);
    particle.counters.civilian_harm += (first_loss + second_loss)
        * config.combat.civilian_exposure_rate
        * particle
            .locality
            .population
            .get(locality)
            .copied()
            .unwrap_or(0.0);
    particle.counters.deaths += first_loss + second_loss;
    particle
        .observations
        .push(pineland_core::state::ObservationRecord {
            time,
            kind: 1,
            locality: locality as u32,
            actor: particle.formations.organization[second],
            value: first_loss + second_loss,
            confidence: config.information.contact_true_positive_rate,
        });
    let _ = (microzone, initiative);
}

pub fn effective_capability(particle: &ParticleState, formation: usize) -> f64 {
    particle.formations.effective_strength(formation)
}
