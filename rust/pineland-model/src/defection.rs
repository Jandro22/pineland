//! Security-force breaking: surrender and desertion cascades.
//!
//! Partner forces in Afghanistan (2021), Mosul (2014) and South Vietnam
//! (1975) collapsed mainly through units surrendering, deserting or cutting
//! local deals once they expected others to do the same, not through
//! attrition. Each logistics event, every military formation faces a daily
//! breaking hazard driven by a bounded "breaking pressure":
//!
//! * material stress: supply shortfall and lost combat readiness;
//! * moral stress: lost cohesion;
//! * isolation: no friendly operational formation in or next to its locality;
//! * local threat: insurgent physical control where it stands;
//! * national momentum: insurgent share of combined fielded strength;
//! * abandonment: external support has been withdrawn.
//!
//! A break removes a sub-unit (20-60% of the formation). With hostile forces
//! close it surrenders, handing part of its stores to the nearest insurgent
//! formation; otherwise it deserts. Every break shocks the cohesion of nearby
//! friendly formations and raises national momentum, so breaks feed further
//! breaks: the cascade emerges, it is not scripted.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{python_exp, PyRandomCompat};
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

const PHYSICAL: usize = 1;

fn is_insurgent(particle: &ParticleState, organization: usize) -> bool {
    particle.organizations.kind.get(organization).copied() == Some(3)
}

fn live(particle: &ParticleState, formation: usize) -> bool {
    let f = &particle.formations;
    f.active[formation] != 0 && f.personnel[formation] > 0.0 && f.outside_pineland[formation] == 0
}

fn vicinity(topology: &StaticTopology, locality: usize) -> Vec<usize> {
    let mut near = vec![locality];
    near.extend(
        topology
            .locality_edges
            .neighbors(locality)
            .map(|(destination, _)| destination as usize),
    );
    near
}

/// Insurgent share of combined fielded strength (0.5 = parity).
pub fn national_momentum(particle: &ParticleState) -> f64 {
    let f = &particle.formations;
    let (mut security, mut insurgent) = (0.0, 0.0);
    for formation in 0..f.personnel.len() {
        if !live(particle, formation) {
            continue;
        }
        let organization = f.organization[formation] as usize;
        if organization == crate::MILITARY {
            security += f.personnel[formation];
        } else if is_insurgent(particle, organization) {
            insurgent += f.personnel[formation];
        }
    }
    if security + insurgent <= 0.0 {
        0.5
    } else {
        insurgent / (security + insurgent)
    }
}

/// Breaking pressure of one military formation, in [0, 1].
pub fn breaking_pressure(
    particle: &ParticleState,
    topology: &StaticTopology,
    formation: usize,
    momentum: f64,
) -> f64 {
    let f = &particle.formations;
    let locality = f.locality[formation] as usize;
    let material =
        0.5 * (1.0 - f.supply_fraction(formation)) + 0.5 * (1.0 - f.combat_readiness(formation));
    let moral = 1.0 - clamp01(f.cohesion[formation]);
    let near = vicinity(topology, locality);
    let supported = (0..f.personnel.len()).any(|other| {
        other != formation
            && live(particle, other)
            && f.organization[other] == f.organization[formation]
            && f.operational_status[other] == 1
            && near.contains(&(f.locality[other] as usize))
    });
    let isolation = if supported { 0.0 } else { 1.0 };
    let threat = particle
        .locality
        .insurgent_control
        .get(locality * CONTROL_DIMENSIONS + PHYSICAL)
        .copied()
        .map(clamp01)
        .unwrap_or(0.0);
    let abandonment = if particle.partner_support.support_withdrawn {
        1.0
    } else {
        0.0
    };
    clamp01(
        0.25 * clamp01(material)
            + 0.20 * moral
            + 0.10 * isolation
            + 0.15 * threat
            + 0.25 * clamp01(momentum)
            + 0.05 * abandonment,
    )
}

pub fn update(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    elapsed_days: f64,
    time: f64,
) {
    let combat = &config.combat;
    if combat.defection_base_hazard_per_day <= 0.0
        || elapsed_days <= 0.0
        || combat.organized_action_architecture != "multichannel_v6"
    {
        return;
    }
    let trace = crate::trace_env!("PINELAND_FUNNEL");
    let formations = (0..particle.formations.personnel.len())
        .filter(|&f| {
            particle.formations.organization[f] as usize == crate::MILITARY && live(particle, f)
        })
        .collect::<Vec<_>>();
    for formation in formations {
        // Recomputed per formation: a break earlier in this event is felt by
        // the next formation (within-event contagion).
        let momentum = national_momentum(particle);
        let pressure = breaking_pressure(particle, topology, formation, momentum);
        let rate = combat.defection_base_hazard_per_day
            * python_exp(
                combat.defection_pressure_slope * (pressure - combat.defection_pressure_midpoint),
            );
        let probability = 1.0 - python_exp(-rate * elapsed_days);
        if rng.random() >= probability {
            continue;
        }
        let share = 0.2 + 0.4 * rng.random();
        let locality = particle.formations.locality[formation] as usize;
        let near = vicinity(topology, locality);
        let receiver = (0..particle.formations.personnel.len())
            .filter(|&other| {
                live(particle, other)
                    && is_insurgent(particle, particle.formations.organization[other] as usize)
                    && near.contains(&(particle.formations.locality[other] as usize))
            })
            .max_by(|a, b| {
                let f = &particle.formations;
                (f.locality[*a] as usize == locality)
                    .cmp(&(f.locality[*b] as usize == locality))
                    .then(f.personnel[*a].total_cmp(&f.personnel[*b]))
                    .then(b.cmp(a))
            });
        let f = &mut particle.formations;
        let broken = f.personnel[formation] * share;
        let stores = f.supply_stock[formation] * share;
        f.personnel[formation] -= broken;
        f.cumulative_losses[formation] += broken;
        f.supply_stock[formation] -= stores;
        let surrendered = receiver.is_some();
        if let Some(receiver) = receiver {
            // Surrendered arms and stores pass to the insurgents.
            let room = (f.supply_capacity[receiver] - f.supply_stock[receiver]).max(0.0);
            f.supply_stock[receiver] += (0.5 * stores).min(room);
        }
        if f.personnel[formation] < 1.0 {
            f.personnel[formation] = 0.0;
            f.active[formation] = 0;
            f.operational_status[formation] = 0;
        }
        // The break shocks nearby friendly units.
        for other in 0..f.personnel.len() {
            if other != formation
                && f.organization[other] as usize == crate::MILITARY
                && near.contains(&(f.locality[other] as usize))
            {
                f.cohesion[other] = clamp01(f.cohesion[other] - 0.15 * share);
            }
        }
        let name = if surrendered {
            "security_surrenders"
        } else {
            "security_desertions"
        };
        *particle
            .counters
            .event_counts
            .entry(name.to_string())
            .or_insert(0) += 1;
        if trace {
            eprintln!(
                "FUNNEL t={:.3} stage=defection formation={} outcome={} pressure={:.3} momentum={:.3} broken={:.1}",
                time,
                formation,
                if surrendered { "surrender" } else { "desert" },
                pressure,
                momentum,
                broken
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pineland_core::rng::RngStreams;

    fn world(supply: f64, cohesion: f64) -> (ParticleState, StaticTopology) {
        let topology = StaticTopology::new(2);
        let mut p = ParticleState::new(
            2,
            topology.microzones.len(),
            7,
            2,
            2,
            RngStreams::new(3, "defection-test"),
        );
        p.organizations.kind[crate::MILITARY] = 1;
        p.organizations.kind[crate::INSURGENT] = 3;
        p.formations.organization = vec![crate::MILITARY as u32, crate::INSURGENT as u32];
        p.formations.locality = vec![0, 0];
        p.formations.personnel = vec![1000.0, 1000.0];
        p.formations.supply_capacity = vec![30_000.0, 30_000.0];
        p.formations.supply_stock = vec![30_000.0 * supply, 0.0];
        p.formations.cohesion = vec![cohesion, 0.8];
        (p, topology)
    }

    fn v6() -> SimulationConfig {
        let mut config = SimulationConfig::default();
        config.combat.organized_action_architecture = "multichannel_v6".to_string();
        config
    }

    #[test]
    fn pressure_rises_with_starvation_and_broken_cohesion() {
        let (healthy, topology) = world(1.0, 1.0);
        let (starved, _) = world(0.0, 0.1);
        let m = national_momentum(&healthy);
        assert!(
            breaking_pressure(&starved, &topology, 0, m)
                > breaking_pressure(&healthy, &topology, 0, m) + 0.2
        );
    }

    #[test]
    fn starved_force_surrenders_stores_to_nearby_insurgents() {
        let (mut p, topology) = world(0.0, 0.05);
        let mut config = v6();
        config.combat.defection_base_hazard_per_day = 1.0;
        p.formations.supply_stock[0] = 1000.0;
        let mut rng = PyRandomCompat::from_seed(5);
        update(&mut p, &topology, &config, &mut rng, 30.0, 10.0);
        assert!(p.formations.personnel[0] < 1000.0);
        assert!(p.formations.supply_stock[1] > 0.0);
        assert_eq!(
            p.counters.event_counts.get("security_surrenders"),
            Some(&1)
        );
    }

    #[test]
    fn disabled_hazard_is_a_no_op() {
        let (mut p, topology) = world(0.0, 0.05);
        let mut config = v6();
        config.combat.defection_base_hazard_per_day = 0.0;
        let mut rng = PyRandomCompat::from_seed(5);
        update(&mut p, &topology, &config, &mut rng, 30.0, 10.0);
        assert_eq!(p.formations.personnel[0], 1000.0);
    }
}
