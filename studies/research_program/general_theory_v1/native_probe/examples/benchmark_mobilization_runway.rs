use pineland_core::config::SimulationConfig;
use pineland_model::{SimulationEngine, INSURGENT};
use std::time::Instant;

fn synthetic_config(seed: u64, horizon: f64) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = 300;
    c.locality_count = 34;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c.state_regeneration.underground_disruption_rate = 0.0;
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
    c
}

fn rooted_mass(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.people.organization.len())
        .filter(|&i| p.people.organization[i] as usize == INSURGENT)
        .map(|i| p.people.represented_population[i].max(0.0) * p.people.armed_fraction[i].max(0.0))
        .sum()
}

fn operational_force(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.formations.personnel.len())
        .filter(|&f| {
            p.formations.organization[f] as usize == INSURGENT
                && p.formations.active[f] != 0
                && p.formations.operational_status[f] == 1
                && p.formations.outside_pineland[f] == 0
        })
        .map(|f| p.formations.personnel[f].max(0.0))
        .sum()
}

fn run_single_world(seed: u64, recruitment_mult: f64, horizon: f64) -> (f64, String, f64) {
    let mut config = synthetic_config(seed, horizon);
    config.recruitment_rate *= recruitment_mult;
    let mut e = SimulationEngine::new(config).expect("engine creation");
    e.particle_execution = true;

    let mut collapse_time = f64::NAN;
    let mut collapse_cause = "survived".to_string();
    let min_force = e.config.organization_ecology.minimum_formation_personnel;

    while e.particle.time < horizon - 1.0e-9 {
        let Some(event) = e.particle.scheduler.peek() else { break; };
        if event.time > horizon { break; }
        let is_org = matches!(event.payload, pineland_core::scheduler::EventPayload::OrganizationEcology);
        let pre_state = if is_org {
            Some((
                e.particle.organizations.active[INSURGENT],
                e.particle.organizations.capital[INSURGENT],
                e.particle.organizations.cohesion[INSURGENT],
                rooted_mass(&e),
                operational_force(&e),
            ))
        } else {
            None
        };

        let processed = e.advance_until_limited(horizon, Some(1)).expect("advance");
        if processed == 0 { break; }

        if let Some((active_before, cap_pre, coh_pre, root_pre, force_pre)) = pre_state {
            let active_after = e.particle.organizations.active[INSURGENT];
            if active_before != 0 && active_after == 0 {
                collapse_time = e.particle.time;
                if cap_pre <= 1.0e-9 {
                    collapse_cause = "capital".to_string();
                } else if coh_pre < 0.12 {
                    collapse_cause = "cohesion".to_string();
                } else if root_pre <= 1.0e-9 && force_pre < min_force {
                    collapse_cause = "rooted_and_fielded_exhaustion".to_string();
                } else {
                    collapse_cause = "stochastic".to_string();
                }
                break;
            }
        }
    }
    (collapse_time, collapse_cause, e.particle.time)
}

fn main() {
    println!("Benchmarking 8 worlds across 360 days horizon...");
    let seeds = [
        2026130001u64, 2026130002, 2026130003, 2026130004,
        2026130005, 2026130006, 2026130007, 2026130008,
    ];
    let start_all = Instant::now();
    for (i, &seed) in seeds.iter().enumerate() {
        let t0 = Instant::now();
        let (collapse_t, cause, final_t) = run_single_world(seed, 1.0, 360.0);
        let elapsed = t0.elapsed().as_secs_f64();
        println!(
            "World {}/8 (seed={}): elapsed={:.3}s, final_time={:.1}d, collapse_time={:.1}d, cause={}",
            i + 1, seed, elapsed, final_t, collapse_t, cause
        );
    }
    let total_elapsed = start_all.elapsed().as_secs_f64();
    println!("Total elapsed for 8 worlds: {:.3}s (mean: {:.3}s/world)", total_elapsed, total_elapsed / 8.0);
}
