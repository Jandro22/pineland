use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, INSURGENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone, Debug)]
struct Snapshot {
    rooted_membership: f64,
    fielded_force: f64,
    recruitment_hazard: f64,
    eligible_recruitment_mass: f64,
    foothold_strength: f64,
    insurgent_capital: f64,
    cumulative_recruitment: f64,
    cumulative_disruption: f64,
    active: usize,
}

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

fn base_config(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    anchor_recruitment_multiplier: f64,
) -> SimulationConfig {
    let mut config = SimulationConfig::default();
    config.seed = seed;
    config.initialization_seed = Some(seed);
    config.agent_count = agents;
    config.locality_count = localities;
    config.horizon_days = horizon;
    config.output_mode = "forensic".to_string();
    config.foreign_affairs.enabled = false;
    config.state_regeneration.enabled = true;
    config.recruitment_rate *= anchor_recruitment_multiplier;
    config.state_regeneration.underground_disruption_rate = 0.0;
    config
}

fn rooted_membership(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    (0..p.people.organization.len())
        .filter(|&person| p.people.organization[person] as usize == INSURGENT)
        .map(|person| {
            p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].clamp(0.0, 1.0)
        })
        .sum()
}

fn fielded_force(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    if p.organizations
        .active
        .get(INSURGENT)
        .copied()
        .unwrap_or(0)
        == 0
    {
        return 0.0;
    }
    (0..p.formations.personnel.len())
        .filter(|&formation| {
            p.formations.organization[formation] as usize == INSURGENT
                && p.formations.active[formation] != 0
                && p.formations.operational_status[formation] == 1
                && p.formations.outside_pineland[formation] == 0
        })
        .map(|formation| p.formations.personnel[formation].max(0.0))
        .sum()
}

fn eligible_recruitment_mass(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    let organization_count = p.organizations.kind.len();
    (0..p.people.organization.len())
        .filter_map(|person| {
            let organization = p.people.organization[person] as usize;
            let current_active_insurgent = if organization < organization_count
                && p.organizations.active[organization] != 0
                && p.organizations.kind[organization] == 3
            {
                Some(organization)
            } else {
                None
            };
            if current_active_insurgent.is_some_and(|current| current != INSURGENT) {
                return None;
            }
            let current_fraction = if current_active_insurgent == Some(INSURGENT) {
                p.people.armed_fraction[person].clamp(0.0, 1.0)
            } else {
                0.0
            };
            Some(
                p.people.represented_population[person].max(0.0)
                    * (1.0 - current_fraction).max(0.0),
            )
        })
        .sum()
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let recruitment_hazard = recruitment::recruitment_hazard_mass_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    )
    .into_iter()
    .sum::<f64>();
    let foothold_strength = (0..nloc)
        .map(|locality| {
            let index = INSURGENT * nloc + locality;
            p.footholds
                .strength
                .get(index)
                .copied()
                .unwrap_or(0.0)
                .max(0.0)
        })
        .sum::<f64>();
    let cumulative_disruption = p
        .locality
        .government_cumulative_underground_disruption
        .iter()
        .copied()
        .sum::<f64>();
    Snapshot {
        rooted_membership: rooted_membership(engine),
        fielded_force: fielded_force(engine),
        recruitment_hazard,
        eligible_recruitment_mass: eligible_recruitment_mass(engine),
        foothold_strength,
        insurgent_capital: p
            .organizations
            .capital
            .get(INSURGENT)
            .copied()
            .unwrap_or(0.0),
        cumulative_recruitment: p.counters.recruitment,
        cumulative_disruption,
        active: usize::from(
            p.organizations
                .active
                .get(INSURGENT)
                .copied()
                .unwrap_or(0)
                != 0,
        ),
    }
}

fn row(
    seed: u64,
    recruitment_multiplier: f64,
    disruption: bool,
    timepoint: &str,
    time: f64,
    current: &Snapshot,
    anchor: &Snapshot,
) -> String {
    let recruitment_since_anchor =
        current.cumulative_recruitment - anchor.cumulative_recruitment;
    let disruption_since_anchor =
        current.cumulative_disruption - anchor.cumulative_disruption;
    [
        seed.to_string(),
        format!("{recruitment_multiplier:.8}"),
        usize::from(disruption).to_string(),
        timepoint.to_string(),
        format!("{time:.6}"),
        format!("{:.17}", current.rooted_membership),
        format!("{:.17}", current.fielded_force),
        format!("{:.17}", current.recruitment_hazard),
        format!("{:.17}", current.eligible_recruitment_mass),
        format!("{:.17}", current.foothold_strength),
        format!("{:.17}", current.insurgent_capital),
        format!("{:.17}", recruitment_since_anchor),
        format!("{:.17}", disruption_since_anchor),
        current.active.to_string(),
    ]
    .join(",")
}

fn run_cell(
    seed: u64,
    anchor_engine: &SimulationEngine,
    recruitment_multiplier: f64,
    disruption: bool,
    intervention_end: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    let anchor = snapshot(&engine);
    engine.config.recruitment_rate =
        SimulationConfig::default().recruitment_rate * recruitment_multiplier;
    engine.config.state_regeneration.underground_disruption_rate = if disruption {
        SimulationConfig::default()
            .state_regeneration
            .underground_disruption_rate
    } else {
        0.0
    };
    engine
        .advance_until(intervention_end)
        .map_err(|error| error.to_string())?;
    let intervention = snapshot(&engine);
    engine.config.state_regeneration.underground_disruption_rate = 0.0;
    engine
        .advance_until(final_day)
        .map_err(|error| error.to_string())?;
    let final_snapshot = snapshot(&engine);
    Ok(vec![
        row(
            seed,
            recruitment_multiplier,
            disruption,
            "anchor",
            anchor_engine.particle.time,
            &anchor,
            &anchor,
        ),
        row(
            seed,
            recruitment_multiplier,
            disruption,
            "intervention_end",
            intervention_end,
            &intervention,
            &anchor,
        ),
        row(
            seed,
            recruitment_multiplier,
            disruption,
            "final",
            final_day,
            &final_snapshot,
            &anchor,
        ),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../coin_pressure_regeneration_metabolic_phase_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026186000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let intervention_end: f64 = arg(&args, 8, 240.0);
    let final_day: f64 = arg(&args, 9, 360.0);
    let anchor_recruitment_multiplier: f64 = arg(&args, 10, 0.0625);
    ensure_parent(&out)?;

    let recruitment_multipliers = [0.03125f64, 0.0625, 0.125];
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let anchors: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|offset| {
                let seed = seed_base + offset as u64;
                let mut engine = SimulationEngine::new(base_config(
                    seed,
                    agents,
                    localities,
                    final_day,
                    anchor_recruitment_multiplier,
                ))
                .map_err(|error| error.to_string())?;
                engine.particle_execution = true;
                engine
                    .advance_until(anchor_day)
                    .map_err(|error| error.to_string())?;
                Ok((seed, engine))
            })
            .collect()
    });
    let mut anchors_ok = Vec::with_capacity(seeds);
    for result in anchors {
        anchors_ok.push(result.map_err(std::io::Error::other)?);
    }
    anchors_ok.sort_by_key(|(seed, _)| *seed);

    let tasks = anchors_ok
        .iter()
        .flat_map(|(seed, engine)| {
            recruitment_multipliers.into_iter().flat_map(move |rate| {
                [false, true]
                    .into_iter()
                    .map(move |disruption| (*seed, engine, rate, disruption))
            })
        })
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, rate, disruption)| {
                run_cell(
                    *seed,
                    engine,
                    *rate,
                    *disruption,
                    intervention_end,
                    final_day,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,recruitment_multiplier,underground_disruption,timepoint,time,rooted_armed_membership_mass,fielded_force_personnel,recruitment_hazard_mass,eligible_recruitment_mass,foothold_strength_sum,canonical_insurgent_capital,cumulative_recruitment_mass_since_anchor,cumulative_underground_disruption_since_anchor,canonical_insurgent_active"
    )?;
    for result in results {
        for line in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{line}")?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} seeds={seeds} cells={} rows={}",
        recruitment_multipliers.len() * 2,
        seeds * recruitment_multipliers.len() * 2 * 3
    );
    Ok(())
}
