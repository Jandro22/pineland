//! Belief-routed organized action opportunities and multi-channel outcomes.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::scheduler::EventPayload;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn action_attempt_hazard(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
) -> f64 {
    if organization >= particle.organizations.active.len()
        || locality >= particle.locality.population.len()
        || particle.organizations.active[organization] == 0
    {
        return 0.0;
    }
    let n = particle.locality.population.len();
    let foothold = organization * n + locality;
    let rooted = particle
        .footholds
        .embeddedness
        .get(foothold)
        .copied()
        .unwrap_or(0.0);
    let strength = particle
        .footholds
        .strength
        .get(foothold)
        .copied()
        .unwrap_or(0.0);
    let capital = particle.organizations.capital[organization];
    let cohesion = particle.organizations.cohesion[organization];
    config.organized_action_rate.max(0.0)
        * (0.25 + rooted)
        * (0.25 + strength / 1000.0)
        * (0.25 + capital / 100.0)
        * (0.35 + cohesion)
}

pub fn action_attempt_probability(
    particle: &ParticleState,
    config: &SimulationConfig,
    organization: usize,
    locality: usize,
    interval_days: f64,
) -> f64 {
    let hazard =
        action_attempt_hazard(particle, config, organization, locality) * interval_days.max(0.0);
    1.0 - (-hazard).exp()
}

pub fn opportunities(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) {
    if !config.include_insurgency
        || particle
            .organizations
            .active
            .get(crate::INSURGENT)
            .copied()
            .unwrap_or(0)
            == 0
    {
        return;
    }
    let n = topology.locality_count();
    for locality in 0..n {
        let probability = action_attempt_probability(
            particle,
            config,
            crate::INSURGENT,
            locality,
            config.intervals.contact,
        );
        if rng.random() >= probability {
            continue;
        }
        let foothold = crate::INSURGENT * n + locality;
        particle.footholds.cumulative_actions[foothold] += 1.0;
        particle.counters.organized_actions = particle.counters.organized_actions.saturating_add(1);
        let intensity =
            clamp01(0.04 + 0.16 * particle.footholds.embeddedness[foothold] + 0.08 * rng.random());
        particle.locality.violence[locality] =
            clamp01(particle.locality.violence[locality] + intensity);
        particle.locality.disruption[locality] =
            clamp01(particle.locality.disruption[locality] + intensity * 0.6);
        let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
        particle.locality.government_control[offset + 3] =
            clamp01(particle.locality.government_control[offset + 3] - intensity * 0.18);
        particle.locality.insurgent_control[offset + 3] =
            clamp01(particle.locality.insurgent_control[offset + 3] + intensity * 0.2);
        particle.footholds.raw_signal[foothold] =
            clamp01(particle.footholds.raw_signal[foothold] + intensity);
        particle.footholds.last_activated_at[foothold] = time;
        if particle.footholds.first_activated_at[foothold] < -1e8 {
            particle.footholds.first_activated_at[foothold] = time;
        }
        particle.footholds.cumulative_active_days[foothold] += config.intervals.contact;
        // If opposing formations are colocated, planning creates a typed
        // contact event.  Execution resolves truth only in combat.rs.
        let mut government = None;
        let mut insurgent = None;
        for formation in 0..particle.formations.personnel.len() {
            if particle.formations.active[formation] == 0
                || particle.formations.locality[formation] as usize != locality
            {
                continue;
            }
            match particle.formations.organization[formation] as usize {
                crate::INSURGENT if insurgent.is_none() => insurgent = Some(formation),
                crate::MILITARY | crate::POLICE if government.is_none() => {
                    government = Some(formation)
                }
                _ => {}
            }
        }
        if let (Some(first), Some(second)) = (insurgent, government) {
            let zone = particle.formations.microzone[first] as usize;
            let _ = particle.scheduler.schedule(
                time,
                100,
                EventPayload::Contact {
                    first: first.into(),
                    second: second.into(),
                    locality: locality.into(),
                    microzone: zone.into(),
                },
            );
        }
    }
}

pub fn apply_nonviolent_coercion(particle: &mut ParticleState, locality: usize, amount: f64) {
    if locality >= particle.locality.population.len() {
        return;
    }
    let offset = locality * pineland_core::state::CONTROL_DIMENSIONS;
    particle.locality.insurgent_control[offset + 5] =
        clamp01(particle.locality.insurgent_control[offset + 5] + amount);
    particle.locality.government_control[offset + 5] =
        clamp01(particle.locality.government_control[offset + 5] - amount * 0.4);
}
