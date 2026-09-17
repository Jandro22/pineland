use pineland_core::config::SimulationConfig;
use pineland_core::rng::{seed_from_namespace, PyRandomCompat};
use pineland_model::{combat, SimulationEngine, INSURGENT, MILITARY};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

fn arg<T: std::str::FromStr>(args: &[String], index: usize, default: T) -> T {
    args.get(index)
        .and_then(|v| v.parse::<T>().ok())
        .unwrap_or(default)
}

fn config(seed: u64, agents: usize, localities: usize) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = 1.0;
    c.state_regeneration.enabled = true;
    c.foreign_affairs.enabled = false;
    c.output_mode = "forensic".into();
    c
}

fn first_formation(engine: &SimulationEngine, organization: usize) -> Result<usize, String> {
    engine
        .particle
        .formations
        .organization
        .iter()
        .enumerate()
        .find(|(_, o)| **o as usize == organization)
        .map(|(i, _)| i)
        .ok_or_else(|| format!("missing formation for organization {organization}"))
}

fn match_formation(engine: &mut SimulationEngine, formation: usize, experience: f64) {
    let f = &mut engine.particle.formations;
    f.personnel[formation] = 300.0;
    f.quality[formation] = 0.70;
    f.experience[formation] = experience;
    f.cohesion[formation] = 0.75;
    f.readiness[formation] = 1.0;
    f.sustainment[formation] = 1.0;
    f.information[formation] = 0.60;
    f.mobility[formation] = 0.70;
    f.command[formation] = 0.70;
    f.embeddedness[formation] = 0.50;
    f.fatigue[formation] = 0.0;
    f.availability[formation] = 1.0;
    f.active[formation] = 1;
    f.operational_status[formation] = 1;
    f.moving[formation] = 0;
    f.outside_pineland[formation] = 0;
    f.supply_capacity[formation] = 10_000.0;
    f.supply_stock[formation] = 10_000.0;
    f.cumulative_losses[formation] = 0.0;
}

fn run_cell(
    base: &SimulationEngine,
    world_seed: u64,
    replicate: usize,
    gov_e: f64,
    ins_e: f64,
) -> Result<String, String> {
    let mut e = base.clone();
    let gov = first_formation(&e, MILITARY)?;
    let ins = first_formation(&e, INSURGENT)?;
    let locality = e.particle.formations.locality[gov] as usize;
    let microzone = e.particle.formations.microzone[gov] as usize;
    e.particle.formations.locality[ins] = locality as u32;
    e.particle.formations.microzone[ins] = microzone as u32;
    match_formation(&mut e, gov, gov_e);
    match_formation(&mut e, ins, ins_e);
    e.particle.organizations.active[MILITARY] = 1;
    e.particle.organizations.active[INSURGENT] = 1;

    let namespace = format!("veterancy-contact:{world_seed}:{replicate}");
    let rng_seed = seed_from_namespace(202613200000u64, &namespace, "engagement");
    let mut rng = PyRandomCompat::from_seed(rng_seed);
    combat::resolve_organized_engagement(
        &mut e.particle,
        &e.topology,
        &e.config,
        &mut rng,
        1.0,
        gov,
        ins,
        MILITARY,
        true,
    );
    let gov_loss = e.particle.formations.cumulative_losses[gov].max(0.0);
    let ins_loss = e.particle.formations.cumulative_losses[ins].max(0.0);
    let gov_frac = gov_loss / 300.0;
    let ins_frac = ins_loss / 300.0;
    let exchange = ins_frac / gov_frac.max(1.0e-12);
    let gov_survives = e.particle.formations.operational_status[gov] == 1;
    let ins_survives = e.particle.formations.operational_status[ins] == 1;
    let gov_wins_loss = gov_frac < ins_frac;
    let terrain = e
        .particle
        .zones
        .terrain_friction
        .get(microzone)
        .copied()
        .unwrap_or(1.0);
    let observability = e
        .particle
        .zones
        .observability
        .get(microzone)
        .copied()
        .unwrap_or(0.5);
    Ok(format!(
        "{world_seed},{replicate},{rng_seed},{gov_e:.6},{ins_e:.6},{locality},{microzone},{terrain:.17},{observability:.17},{gov_loss:.17},{ins_loss:.17},{gov_frac:.17},{ins_frac:.17},{exchange:.17},{gov_wins_loss},{gov_survives},{ins_survives},{:.17},{:.17}",
        e.particle.formations.experience[gov],
        e.particle.formations.experience[ins]
    ))
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../veterancy_matched_engagement_v1.csv".into());
    let worlds: usize = arg(&args, 2, 6);
    let replicates: usize = arg(&args, 3, 128);
    let agents: usize = arg(&args, 4, 180);
    let localities: usize = arg(&args, 5, 24);
    let threads: usize = arg(&args, 6, 8);
    let seed_base: u64 = arg(&args, 7, 2026132000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let mut bases = Vec::new();
    for i in 0..worlds {
        let seed = seed_base + i as u64;
        bases.push((
            seed,
            SimulationEngine::new(config(seed, agents, localities))?,
        ));
    }
    let experience = [0.1, 0.5, 0.9];
    let tasks = bases
        .iter()
        .flat_map(|(seed, base)| {
            (0..replicates).flat_map(move |rep| {
                experience.into_iter().flat_map(move |g| {
                    experience
                        .into_iter()
                        .map(move |i| (*seed, base, rep, g, i))
                })
            })
        })
        .collect::<Vec<_>>();
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<String, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, base, rep, g, i)| run_cell(base, *seed, *rep, *g, *i))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "world_seed,replicate,rng_seed,government_experience,insurgent_experience,locality,microzone,terrain_friction,observability,government_loss,insurgent_loss,government_loss_fraction,insurgent_loss_fraction,exchange_ratio_insurgent_over_government,government_wins_loss_exchange,government_operational_survival,insurgent_operational_survival,government_post_experience,insurgent_post_experience")?;
    for r in results {
        writeln!(w, "{}", r.map_err(std::io::Error::other)?)?;
    }
    w.flush()?;
    println!(
        "wrote {out} worlds={worlds} replicates={replicates} cells=9 rows={}",
        tasks.len()
    );
    Ok(())
}
