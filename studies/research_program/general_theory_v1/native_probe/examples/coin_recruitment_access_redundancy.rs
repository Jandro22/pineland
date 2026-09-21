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

fn scale_membership(engine: &mut SimulationEngine, scale: f64) {
    for person in 0..engine.particle.people.organization.len() {
        if engine.particle.people.organization[person] as usize == INSURGENT {
            engine.particle.people.armed_fraction[person] *= scale;
        }
    }
}

fn remove_social_access(engine: &mut SimulationEngine) {
    let organization_count = engine.particle.organizations.kind.len();
    for person in 0..engine.particle.people.organization.len() {
        let index = person * organization_count + INSURGENT;
        if index < engine.particle.people.social_exposure.len() {
            engine.particle.people.social_exposure[index] = 0.0;
        }
    }
}

fn remove_formation_access(engine: &mut SimulationEngine) {
    for formation in 0..engine.particle.formations.organization.len() {
        if engine.particle.formations.organization[formation] as usize == INSURGENT {
            engine.particle.formations.personnel[formation] = 0.0;
        }
    }
}

fn remove_foothold_access(engine: &mut SimulationEngine) {
    let locality_count = engine.topology.locality_count();
    for locality in 0..locality_count {
        let index = INSURGENT * locality_count + locality;
        if index < engine.particle.footholds.strength.len() {
            engine.particle.footholds.strength[index] = 0.0;
        }
    }
}

fn remove_member_access(engine: &mut SimulationEngine) {
    engine.config.organization_ecology.minimum_proto_represented_population = 1.0e30;
}

fn apply_access_regime(engine: &mut SimulationEngine, regime: &str) -> Result<(), String> {
    match regime {
        "all" => {}
        "social_only" => {
            remove_formation_access(engine);
            remove_foothold_access(engine);
            remove_member_access(engine);
        }
        "formation_only" => {
            remove_social_access(engine);
            remove_foothold_access(engine);
            remove_member_access(engine);
        }
        "foothold_only" => {
            remove_social_access(engine);
            remove_formation_access(engine);
            remove_member_access(engine);
        }
        "member_only" => {
            remove_social_access(engine);
            remove_formation_access(engine);
            remove_foothold_access(engine);
        }
        "none" => {
            remove_social_access(engine);
            remove_formation_access(engine);
            remove_foothold_access(engine);
            remove_member_access(engine);
        }
        _ => return Err(format!("unknown access regime {regime}")),
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../coin_recruitment_access_redundancy_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 16);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026184000u64);
    let state_time: f64 = arg(&args, 7, 60.0);
    ensure_parent(&out)?;

    let regimes = [
        "all",
        "social_only",
        "formation_only",
        "foothold_only",
        "member_only",
        "none",
    ];
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
                let mut seed_rows = Vec::with_capacity(regimes.len());
                for regime in regimes {
                    let mut baseline = engine.clone();
                    apply_access_regime(&mut baseline, regime)?;
                    let baseline_hazard = hazard(&baseline);
                    let mut thinned = baseline.clone();
                    scale_membership(&mut thinned, 0.75);
                    let thinned_hazard = hazard(&thinned);
                    let ratio = if baseline_hazard > 1.0e-15 {
                        thinned_hazard / baseline_hazard
                    } else if thinned_hazard <= 1.0e-15 {
                        1.0
                    } else {
                        f64::INFINITY
                    };
                    seed_rows.push(format!(
                        "{seed},{regime},{baseline_hazard:.17},{thinned_hazard:.17},{ratio:.17}"
                    ));
                }
                Ok(seed_rows)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,access_regime,baseline_hazard,thinned_hazard,hazard_ratio"
    )?;
    for result in rows {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} seeds={seeds} regimes={} rows={}",
        regimes.len(),
        seeds * regimes.len()
    );
    Ok(())
}
