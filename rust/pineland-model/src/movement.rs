//! Formation orders and represented civilian mobility.

use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::ParticleState;
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
    _particle: &mut ParticleState,
    _topology: &StaticTopology,
    _config: &SimulationConfig,
    _time: f64,
) {
    // Formation reallocation is an issued-order process in the Python
    // reference.  A command boundary must not mutate formation state
    // directly (doing so turns an order into an instantaneous move).
}
