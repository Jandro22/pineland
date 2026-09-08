//! Native observation, detection, fusion, and belief updates.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{
    clamp01, BeliefKey, ObservationRecord, ParticleState, CONTROL_DIMENSIONS,
};
use pineland_core::topology::StaticTopology;

pub fn collect_and_fuse(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) {
    let locality_count = topology.locality_count();
    for locality in 0..locality_count {
        let mut insurgent_personnel = 0.0;
        let mut readiness: f64 = 0.0;
        for formation in 0..particle.formations.personnel.len() {
            if particle.formations.active[formation] == 0
                || particle.formations.locality[formation] as usize != locality
            {
                continue;
            }
            if particle.formations.organization[formation] as usize == crate::INSURGENT {
                insurgent_personnel += particle.formations.personnel[formation];
                readiness = readiness.max(particle.formations.effective_readiness(formation));
            }
        }
        let observability = particle.locality.observability[locality];
        let terrain = particle.locality.terrain_friction[locality];
        let pressure =
            clamp01(particle.locality.violence[locality] + particle.locality.disruption[locality]);
        let detection_probability = clamp01(
            config.information.true_positive_rate
                * (0.5 + 0.5 * observability)
                * (1.0 + config.information.detection_pressure_bonus * pressure)
                * (1.0 + config.information.detection_readiness_bonus * readiness)
                / (1.0 + config.information.detection_terrain_penalty * terrain.max(0.0)),
        );
        let true_present = insurgent_personnel > 0.1;
        let detected = if true_present {
            rng.random() < detection_probability
        } else {
            rng.random() < config.information.false_positive_rate * observability
        };
        let presence = if detected { 1.0 } else { 0.0 };
        let estimate = if detected {
            if true_present {
                insurgent_personnel * (0.7 + 0.6 * rng.random())
            } else {
                rng.uniform(10.0, 100.0)
            }
        } else {
            0.0
        };
        let quality =
            clamp01(0.5 + 0.4 * observability - 0.1 * terrain + 0.1 * rng.uniform(-1.0, 1.0));
        let report_weight = quality
            * config
                .information
                .source_trust
                .get("patrol")
                .copied()
                .unwrap_or(0.88);
        for observer in [crate::GOVERNMENT, crate::MILITARY, crate::POLICE] {
            let index = particle.beliefs.ensure_key(BeliefKey {
                observer: observer as u32,
                target: crate::INSURGENT as u32,
                locality: locality as u32,
                kind: 0,
            });
            particle.beliefs.fuse_presence(
                index,
                time,
                report_weight.max(0.01),
                presence,
                estimate,
                config.information.contradiction_memory_days,
                config.information.contradiction_penalty,
            );
        }
        particle.observations.push(ObservationRecord {
            time,
            kind: 0,
            locality: locality as u32,
            actor: crate::INSURGENT as u32,
            value: if detected {
                estimate.max(presence)
            } else {
                0.0
            },
            confidence: report_weight,
        });
        particle.counters.observations = particle.counters.observations.saturating_add(1);

        let mut control = [0.0; CONTROL_DIMENSIONS];
        let offset = locality * CONTROL_DIMENSIONS;
        for (dimension, control_value) in control.iter_mut().enumerate() {
            *control_value = particle.locality.government_control[offset + dimension]
                + rng.uniform(-config.observation_noise, config.observation_noise);
        }
        let control_index = particle.beliefs.ensure_key(BeliefKey {
            observer: crate::GOVERNMENT as u32,
            target: crate::INSURGENT as u32,
            locality: locality as u32,
            kind: 1,
        });
        particle.beliefs.fuse_control(
            control_index,
            time,
            (quality * config.information.language_fusion_weight).max(0.01),
            &control,
            config.information.contradiction_memory_days,
            config.information.contradiction_penalty,
        );
    }
}

pub fn detection_probability(
    config: &SimulationConfig,
    observability: f64,
    pressure: f64,
    terrain: f64,
    readiness: f64,
) -> f64 {
    clamp01(
        config.information.true_positive_rate
            * (0.5 + 0.5 * observability)
            * (1.0 + config.information.detection_pressure_bonus * pressure)
            * (1.0 + config.information.detection_readiness_bonus * readiness)
            / (1.0 + config.information.detection_terrain_penalty * terrain.max(0.0)),
    )
}
