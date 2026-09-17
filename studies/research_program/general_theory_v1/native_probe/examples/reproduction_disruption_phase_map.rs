use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, GOVERNMENT, INSURGENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone)]
struct Snapshot {
    rooted: f64,
    force: f64,
    foothold: f64,
    hazard: f64,
    insurgent_control: f64,
    government_control: f64,
    government_capital: f64,
    insurgent_capital: f64,
    disruption: f64,
    intelligence: f64,
}

fn arg<T: std::str::FromStr>(args: &[String], index: usize, default: T) -> T {
    args.get(index)
        .and_then(|v| v.parse::<T>().ok())
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

fn config(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    recruitment_multiplier: f64,
    disruption_multiplier: f64,
) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.initial_insurgent_share = 0.001;
    c.state_regeneration.enabled = true;
    c.foreign_affairs.enabled = false;
    c.recruitment_rate *= recruitment_multiplier;
    c.state_regeneration.underground_disruption_rate *= disruption_multiplier;
    c
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let mut rooted = 0.0;
    for person in 0..p.people.organization.len() {
        if p.people.organization[person] as usize == INSURGENT {
            rooted += p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].clamp(0.0, 1.0);
        }
    }
    let force = (0..p.formations.personnel.len())
        .filter(|&f| {
            p.formations.organization[f] as usize == INSURGENT
                && p.formations.active[f] != 0
                && p.formations.operational_status[f] == 1
                && p.formations.outside_pineland[f] == 0
        })
        .map(|f| p.formations.personnel[f].max(0.0))
        .sum::<f64>();
    let mut foothold = 0.0;
    for locality in 0..nloc {
        let index = INSURGENT * nloc + locality;
        if index < p.footholds.strength.len() {
            foothold += p.footholds.strength[index].max(0.0);
        }
    }
    let hazard = recruitment::recruitment_hazard_mass_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    )
    .into_iter()
    .sum::<f64>();
    let total_pop = p.locality.population.iter().copied().sum::<f64>();
    let mut ic = 0.0;
    let mut gc = 0.0;
    let mut disruption = 0.0;
    let mut intelligence_num = 0.0;
    for locality in 0..nloc {
        let w = p.locality.population[locality].max(0.0);
        ic += w * p.locality.effective_control(locality, 1);
        gc += w * p.locality.effective_control(locality, 0);
        disruption += p.locality.government_cumulative_underground_disruption[locality].max(0.0);
        intelligence_num +=
            w * p.locality.government_intelligence_penetration[locality].clamp(0.0, 1.0);
    }
    Snapshot {
        rooted,
        force,
        foothold,
        hazard,
        insurgent_control: ic / total_pop.max(1.0e-12),
        government_control: gc / total_pop.max(1.0e-12),
        government_capital: p.organizations.capital[GOVERNMENT],
        insurgent_capital: p.organizations.capital[INSURGENT],
        disruption,
        intelligence: intelligence_num / total_pop.max(1.0e-12),
    }
}

fn run_case(
    seed: u64,
    agents: usize,
    localities: usize,
    recruitment_multiplier: f64,
    disruption_multiplier: f64,
) -> Result<Vec<String>, String> {
    let mut engine = SimulationEngine::new(config(
        seed,
        agents,
        localities,
        360.0,
        recruitment_multiplier,
        disruption_multiplier,
    ))
    .map_err(|e| e.to_string())?;
    let mut rows = Vec::new();
    for &time in &[60.0_f64, 180.0, 360.0] {
        engine.advance_until(time).map_err(|e| e.to_string())?;
        let s = snapshot(&engine);
        rows.push(format!(
            "{seed},{recruitment_multiplier:.6},{disruption_multiplier:.6},{time:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            s.rooted,
            s.force,
            s.foothold,
            s.hazard,
            s.insurgent_control,
            s.government_control,
            s.government_capital,
            s.insurgent_capital,
            s.disruption,
            s.intelligence,
        ));
    }
    Ok(rows)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../reproduction_disruption_phase_map_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 4);
    let agents: usize = arg(&args, 3, 180);
    let localities: usize = arg(&args, 4, 24);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026125000u64);
    ensure_parent(&out)?;

    let recruitment = [0.5, 1.0, 2.0, 4.0, 8.0];
    let disruption = [0.0, 0.125, 0.25, 0.5, 1.0];
    let mut cases = Vec::new();
    for s in 0..seeds {
        let seed = seed_base + s as u64;
        for r in recruitment {
            for d in disruption {
                cases.push((seed, r, d));
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, r, d)| run_case(*seed, agents, localities, *r, *d))
            .collect()
    });
    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,recruitment_multiplier,disruption_multiplier,time,rooted_armed_membership_mass,fielded_force_personnel,foothold_strength_sum,recruitment_hazard_mass,population_weighted_insurgent_control,population_weighted_government_control,government_capital,insurgent_capital,cumulative_underground_disruption,population_weighted_intelligence_penetration")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} cases={} rows={}", cases.len(), cases.len() * 3);
    Ok(())
}
