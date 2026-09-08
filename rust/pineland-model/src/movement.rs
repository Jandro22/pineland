//! Formation orders and represented civilian mobility.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, ParticleState};
use pineland_core::topology::StaticTopology;

pub fn civilian_mobility(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
    _time: f64,
) {
    for locality in 0..topology.locality_count() {
        let violence = particle.locality.violence[locality];
        if violence >= config.civilian_dynamics.displacement_violence_threshold {
            let amount = particle.locality.population[locality]
                * config.civilian_dynamics.forced_displacement_reference_rate
                * config.intervals.mobility;
            particle.locality.displaced_population[locality] =
                (particle.locality.displaced_population[locality] + amount)
                    .min(particle.locality.population[locality]);
        } else if particle.locality.displaced_population[locality] > 0.0
            && rng.random()
                < config.civilian_dynamics.return_reference_rate * config.intervals.mobility
        {
            particle.locality.displaced_population[locality] =
                (particle.locality.displaced_population[locality] * 0.98).max(0.0);
        }
    }
}

pub fn command(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    _time: f64,
) {
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] == 0 || particle.formations.moving[formation] != 0
        {
            continue;
        }
        let organization = particle.formations.organization[formation] as usize;
        if organization == crate::INSURGENT {
            continue;
        }
        let locality = particle.formations.locality[formation] as usize;
        let current = particle.formations.microzone[formation] as usize;
        let mut destination = None;
        let current_signal = topology.insurgent_control_placeholder(current, particle);
        for (neighbor, _) in topology.road_edges.neighbors(current) {
            let score = topology.insurgent_control_placeholder(neighbor as usize, particle);
            if score > current_signal + 0.05 {
                destination = Some(neighbor as usize);
                break;
            }
        }
        if let Some(destination) = destination {
            let distance = topology.distance(current.into(), destination.into());
            let cost = distance
                * particle.locality.terrain_friction[locality]
                * config.logistics.movement_consumption_per_person_km;
            if particle.formations.supply_stock[formation] >= cost
                && particle.formations.command[formation] > 0.2
            {
                particle.formations.supply_stock[formation] -= cost;
                particle.formations.microzone[formation] = destination as u32;
                particle.formations.locality[formation] =
                    topology.microzone_to_locality[destination];
                particle.formations.moving[formation] = 1;
                particle.formations.fatigue[formation] =
                    clamp01(particle.formations.fatigue[formation] + 0.02);
            }
        }
    }
}

trait ZoneSignal {
    fn insurgent_control_placeholder(&self, zone: usize, particle: &ParticleState) -> f64;
}
impl ZoneSignal for StaticTopology {
    fn insurgent_control_placeholder(&self, zone: usize, particle: &ParticleState) -> f64 {
        particle
            .zones
            .insurgent_control
            .get(zone)
            .copied()
            .unwrap_or(0.0)
            + particle
                .zones
                .insurgent_presence
                .get(zone)
                .copied()
                .unwrap_or(0.0)
                * 0.2
    }
}
