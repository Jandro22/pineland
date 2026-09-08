//! Patrol movement and presence-memory refresh.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::{PyRandomCompat, RngError};
use pineland_core::state::ParticleState;
use pineland_core::topology::StaticTopology;

pub fn advance(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _rng: &mut PyRandomCompat,
    patrol: usize,
    time: f64,
) {
    pineland_model_presence(particle, topology, config, time);
    if patrol >= particle.formations.personnel.len() || particle.formations.active[patrol] == 0 {
        return;
    }
    let current = particle.patrols.route_target[patrol] as usize;
    let candidates: Vec<(u32, f64)> = topology.road_edges.neighbors(current).collect();
    let Some((destination, _)) = candidates.first().copied() else {
        return;
    };
    let destination = destination as usize;
    let distance = topology.distance(current.into(), destination.into());
    let terrain = particle.zones.terrain_friction[destination];
    let movement_cost = distance * terrain * config.logistics.movement_consumption_per_person_km;
    if particle.formations.supply_stock[patrol] >= movement_cost
        && particle.formations.availability[patrol] > 0.08
    {
        particle.patrols.route_position[patrol] = current as u32;
        particle.patrols.route_target[patrol] = destination as u32;
        particle.patrols.last_departure[patrol] = time;
        particle.patrols.next_available[patrol] =
            time + distance.max(0.01) / (1.0 + particle.formations.mobility[patrol]);
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
