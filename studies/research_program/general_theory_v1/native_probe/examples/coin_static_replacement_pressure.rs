use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, INSURGENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

fn arg<T: std::str::FromStr>(args: &[String], index: usize, default: T) -> T {
    args.get(index)
        .and_then(|value| value.parse::<T>().ok())
        .unwrap_or(default)
}

fn ensure_parent(path: &str) -> Result<(), Box<dyn Error>> {
    if let Some(parent) = Path::new(path).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    Ok(())
}

fn config(seed: u64, agents: usize, localities: usize, horizon: f64) -> SimulationConfig {
    let mut config = SimulationConfig::default();
    config.seed = seed;
    config.initialization_seed = Some(seed);
    config.agent_count = agents;
    config.locality_count = localities;
    config.horizon_days = horizon;
    config.output_mode = "forensic".to_string();
    config.foreign_affairs.enabled = false;
    config.state_regeneration.enabled = true;
    config.recruitment_rate *= 0.0625;
    config.state_regeneration.underground_disruption_rate = 0.0;
    config
}

fn rooted_mass(engine: &SimulationEngine) -> f64 {
    let particle = &engine.particle;
    (0..particle.people.organization.len())
        .filter(|&person| particle.people.organization[person] as usize == INSURGENT)
        .map(|person| {
            particle.people.represented_population[person].max(0.0)
                * particle.people.armed_fraction[person].clamp(0.0, 1.0)
        })
        .sum()
}

fn eligible_mass(engine: &SimulationEngine) -> f64 {
    let particle = &engine.particle;
    let organization_count = particle.organizations.kind.len();
    (0..particle.people.organization.len())
        .filter_map(|person| {
            let raw = particle.people.organization[person];
            let organization = raw as usize;
            let current_active_insurgent = if organization < organization_count
                && particle.organizations.active[organization] != 0
                && particle.organizations.kind[organization] == 3
            {
                Some(organization)
            } else {
                None
            };
            if current_active_insurgent.is_some_and(|current| current != INSURGENT) {
                return None;
            }
            let current_fraction = if current_active_insurgent == Some(INSURGENT) {
                particle.people.armed_fraction[person].clamp(0.0, 1.0)
            } else {
                0.0
            };
            Some(
                particle.people.represented_population[person].max(0.0)
                    * (1.0 - current_fraction).max(0.0),
            )
        })
        .sum()
}

fn hazard(engine: &SimulationEngine) -> f64 {
    recruitment::recruitment_hazard_mass_by_locality(
        &engine.particle,
        &engine.topology,
        &engine.config,
        INSURGENT,
    )
    .into_iter()
    .sum()
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../coin_static_replacement_pressure_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 16);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026183000u64);
    let state_time: f64 = arg(&args, 7, 60.0);
    ensure_parent(&out)?;

    let scales = [1.0f64, 0.9, 0.75, 0.5, 0.25, 0.0];
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let rows: Vec<Result<Vec<String>, String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|offset| {
                let seed = seed_base + offset as u64;
                let mut engine =
                    SimulationEngine::new(config(seed, agents, localities, state_time))
                        .map_err(|error| error.to_string())?;
                engine.particle_execution = true;
                engine
                    .advance_until(state_time)
                    .map_err(|error| error.to_string())?;
                let baseline_hazard = hazard(&engine);
                let mut seed_rows = Vec::with_capacity(scales.len());
                for scale in scales {
                    let mut shocked = engine.clone();
                    for person in 0..shocked.particle.people.organization.len() {
                        if shocked.particle.people.organization[person] as usize == INSURGENT {
                            shocked.particle.people.armed_fraction[person] *= scale;
                        }
                    }
                    let rooted = rooted_mass(&shocked);
                    let eligible = eligible_mass(&shocked);
                    let recruitment_hazard = hazard(&shocked);
                    let ratio = if baseline_hazard > 0.0 {
                        recruitment_hazard / baseline_hazard
                    } else {
                        f64::NAN
                    };
                    seed_rows.push(format!(
                        "{seed},{scale:.6},{rooted:.17},{eligible:.17},{recruitment_hazard:.17},{baseline_hazard:.17},{ratio:.17}"
                    ));
                }
                Ok(seed_rows)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,armed_membership_scale,rooted_armed_membership_mass,eligible_represented_mass,recruitment_hazard_mass,baseline_recruitment_hazard_mass,hazard_ratio"
    )?;
    for result in rows {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} seeds={seeds} scales={} rows={}", scales.len(), seeds * scales.len());
    Ok(())
}
