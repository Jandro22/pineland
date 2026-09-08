//! Patrol movement and presence-memory refresh.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{PyRandomCompat, RngError};
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn advance(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    time: f64,
) {
    pineland_model_presence(particle, topology, config, time);
    let formations = particle.formations.personnel.len();
    let mut destinations = Vec::with_capacity(formations);
    for formation in 0..formations {
        if particle.formations.active[formation] == 0 {
            destinations.push(None);
            continue;
        }
        let current = particle.formations.microzone[formation] as usize;
        let candidates: Vec<(u32, f64)> = topology.road_edges.neighbors(current).collect();
        if candidates.is_empty() {
            destinations.push(None);
            continue;
        }
        let organization = particle.formations.organization[formation] as usize;
        let selected =
            if config.physical.adaptive_patrol_routing && organization != crate::INSURGENT {
                candidates.iter().copied().max_by(|a, b| {
                    let a_score = particle.zones.insurgent_presence[a.0 as usize] + 0.02 * a.1;
                    let b_score = particle.zones.insurgent_presence[b.0 as usize] + 0.02 * b.1;
                    a_score.total_cmp(&b_score).then_with(|| b.0.cmp(&a.0))
                })
            } else {
                rng.choice_index(candidates.len())
                    .ok()
                    .map(|index| candidates[index])
            };
        destinations.push(selected.map(|(zone, _)| zone as usize));
    }
    for (formation, destination) in destinations.into_iter().enumerate() {
        let Some(destination) = destination else {
            continue;
        };
        let current = particle.formations.microzone[formation] as usize;
        let distance = topology.distance(current.into(), destination.into());
        let terrain = particle.zones.terrain_friction[destination];
        let movement_cost =
            distance * terrain * config.logistics.movement_consumption_per_person_km;
        let available = particle.formations.supply_stock[formation] >= movement_cost;
        if available && particle.formations.availability[formation] > 0.08 {
            particle.formations.microzone[formation] = destination as u32;
            particle.formations.locality[formation] = topology.microzone_to_locality[destination];
            particle.formations.supply_stock[formation] =
                (particle.formations.supply_stock[formation] - movement_cost).max(0.0);
            particle.formations.fatigue[formation] =
                clamp01(particle.formations.fatigue[formation] + 0.01 * terrain);
            particle.formations.moving[formation] = 1;
            particle.patrols.route_position[formation] = current as u32;
            particle.patrols.route_target[formation] = destination as u32;
            particle.patrols.last_departure[formation] = time;
            particle.patrols.next_available[formation] =
                time + distance.max(0.01) / (1.0 + particle.formations.mobility[formation]);
        }
    }
    pineland_model_presence(particle, topology, config, time);
}

fn pineland_model_presence(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    time: f64,
) {
    super::physical::record_presence(particle, topology, config, time);
}

pub fn route_cost(topology: &StaticTopology, source: usize, target: usize, terrain: f64) -> f64 {
    topology.distance(source.into(), target.into()) * terrain.max(0.01)
}

pub fn _rng_error(_: RngError) {}
