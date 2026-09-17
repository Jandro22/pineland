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
    continuity: bool,
) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c.organization_ecology.collapse_requires_fielded_exhaustion = continuity;
    c
}

fn snapshot(engine: &SimulationEngine) -> (f64, f64, f64, u8, f64, f64, f64, f64, f64, usize) {
    let p = &engine.particle;
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
    let hazard = recruitment::recruitment_hazard_mass_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    )
    .into_iter()
    .sum::<f64>();
    let active = p.organizations.active.get(INSURGENT).copied().unwrap_or(0);
    let nloc = engine.topology.locality_count();
    let mut disruption = 0.0;
    let mut control = 0.0;
    let mut weight = 0.0;
    for locality in 0..nloc {
        disruption += p.locality.government_cumulative_underground_disruption[locality].max(0.0);
        let w = p.locality.population[locality].max(0.0);
        control += w * p.locality.effective_control(locality, 1);
        weight += w;
    }
    let insurgent_organizations = (0..p.organizations.kind.len())
        .filter(|&organization| {
            p.organizations.kind[organization] == 3 && p.organizations.active[organization] != 0
        })
        .collect::<Vec<_>>();
    let ecosystem_rooted = (0..p.people.organization.len())
        .filter_map(|person| {
            let organization = p.people.organization[person] as usize;
            (organization < p.organizations.kind.len()
                && p.organizations.kind[organization] == 3
                && p.organizations.active[organization] != 0)
                .then_some(
                    p.people.represented_population[person].max(0.0)
                        * p.people.armed_fraction[person].clamp(0.0, 1.0),
                )
        })
        .sum::<f64>();
    let ecosystem_force = (0..p.formations.personnel.len())
        .filter_map(|formation| {
            let organization = p.formations.organization[formation] as usize;
            (organization < p.organizations.kind.len()
                && p.organizations.kind[organization] == 3
                && p.organizations.active[organization] != 0
                && p.formations.active[formation] != 0
                && p.formations.operational_status[formation] == 1
                && p.formations.outside_pineland[formation] == 0)
                .then_some(p.formations.personnel[formation].max(0.0))
        })
        .sum::<f64>();
    let ecosystem_hazard = insurgent_organizations
        .iter()
        .map(|&organization| {
            recruitment::recruitment_hazard_mass_by_locality(
                p,
                &engine.topology,
                &engine.config,
                organization,
            )
            .into_iter()
            .sum::<f64>()
        })
        .sum::<f64>();
    (
        rooted,
        force,
        hazard,
        active,
        disruption,
        control / weight.max(1.0e-12),
        ecosystem_rooted,
        ecosystem_force,
        ecosystem_hazard,
        insurgent_organizations.len(),
    )
}

fn run_case(
    seed: u64,
    agents: usize,
    localities: usize,
    continuity: bool,
) -> Result<Vec<String>, String> {
    let mut e = SimulationEngine::new(config(seed, agents, localities, 360.0, continuity))
        .map_err(|x| x.to_string())?;
    e.particle_execution = true;
    let variant = if continuity {
        "fielded_continuity"
    } else {
        "legacy"
    };
    let mut rows = Vec::new();
    let mut time = 0.0;
    while time <= 360.0 + 1.0e-9 {
        e.advance_until(time).map_err(|x| x.to_string())?;
        let (
            rooted,
            force,
            hazard,
            active,
            disruption,
            control,
            ecosystem_rooted,
            ecosystem_force,
            ecosystem_hazard,
            ecosystem_orgs,
        ) = snapshot(&e);
        rows.push(format!(
            "{seed},{variant},{time:.6},{rooted:.17},{force:.17},{hazard:.17},{active},{disruption:.17},{control:.17},{ecosystem_rooted:.17},{ecosystem_force:.17},{ecosystem_hazard:.17},{ecosystem_orgs}"
        ));
        time += 15.0;
    }
    Ok(rows)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../fielded_continuity_architecture_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 8);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026127000u64);
    ensure_parent(&out)?;

    let mut cases = Vec::new();
    for s in 0..seeds {
        let seed = seed_base + s as u64;
        cases.push((seed, false));
        cases.push((seed, true));
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, continuity)| run_case(*seed, agents, localities, *continuity))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,variant,time,rooted_armed_membership_mass,operational_fielded_force,recruitment_hazard_mass,organization_active,cumulative_underground_disruption,population_weighted_insurgent_control,ecosystem_rooted_membership,ecosystem_operational_force,ecosystem_recruitment_hazard,active_insurgent_organizations")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!(
        "wrote {out} seeds={seeds} variants=2 rows={}",
        seeds * 2 * 25
    );
    Ok(())
}
