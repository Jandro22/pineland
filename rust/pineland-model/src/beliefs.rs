//! Ageing, contradiction, and spatial propagation of actor beliefs.

use pineland_core::config::SimulationConfig;
use pineland_core::state::{clamp01, ParticleState, CONTROL_DIMENSIONS};
use pineland_core::topology::StaticTopology;

pub fn decay_and_propagate(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    let decay_rate = config.information.default_decay_rate.max(0.0);
    for index in 0..particle.beliefs.keys.len() {
        let age = (time - particle.beliefs.updated_at[index]).max(0.0);
        particle.beliefs.confidence[index] =
            clamp01(particle.beliefs.confidence[index] * (-decay_rate * age).exp());
        particle.beliefs.contradiction[index] *= (-age
            / config
                .information
                .contradiction_memory_days
                .max(f64::MIN_POSITIVE))
        .exp();
    }
    // A bounded, deterministic one-hop propagation approximates delayed
    // command relays without consulting world truth.  The source remains the
    // actor's packed belief row, and all updates preserve canonical key order.
    let snapshot = particle.beliefs.clone();
    for index in 0..snapshot.keys.len() {
        let key = &snapshot.keys[index];
        if key.kind != 0 {
            continue;
        }
        let locality = key.locality as usize;
        let mut neighbor = None;
        if locality < topology.locality_count() {
            for (_, weight) in topology
                .road_edges
                .neighbors(topology.primary_zone[locality] as usize)
            {
                if weight.is_finite() {
                    neighbor = Some((topology.primary_zone[locality] as usize, weight));
                    break;
                }
            }
        }
        let Some((_, _)) = neighbor else {
            continue;
        };
        let adjacent = if locality == 0 {
            topology.locality_count().saturating_sub(1)
        } else {
            locality - 1
        };
        let other_key = snapshot.keys.iter().position(|candidate| {
            candidate.observer == key.observer
                && candidate.target == key.target
                && candidate.locality == adjacent as u32
                && candidate.kind == key.kind
        });
        if let Some(other) = other_key {
            let target = particle.beliefs.ensure_key(key.clone());
            let confidence = 0.04 * snapshot.confidence[other];
            particle.beliefs.presence[target] = clamp01(
                (1.0 - confidence) * particle.beliefs.presence[target]
                    + confidence * snapshot.presence[other],
            );
            particle.beliefs.updated_at[target] =
                particle.beliefs.updated_at[target].max(time - 1.0);
        }
    }
    let _ = CONTROL_DIMENSIONS;
}

pub fn control_estimate(
    particle: &ParticleState,
    observer: usize,
    locality: usize,
) -> [f64; CONTROL_DIMENSIONS] {
    let mut result = [0.0; CONTROL_DIMENSIONS];
    if let Some(index) = particle.beliefs.keys.iter().position(|key| {
        key.observer as usize == observer && key.locality as usize == locality && key.kind == 1
    }) {
        let offset = index * CONTROL_DIMENSIONS;
        result.copy_from_slice(&particle.beliefs.control[offset..offset + CONTROL_DIMENSIONS]);
    }
    result
}
