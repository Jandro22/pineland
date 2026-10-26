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

fn foothold_strength(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    (0..nloc)
        .map(|locality| {
            p.footholds
                .strength
                .get(INSURGENT * nloc + locality)
                .copied()
                .unwrap_or(0.0)
                .max(0.0)
        })
        .sum()
}

fn cumulative_disruption(engine: &SimulationEngine) -> f64 {
    engine
        .particle
        .locality
        .government_cumulative_underground_disruption
        .iter()
        .copied()
        .sum()
}

fn output_row(
    seed: u64,
    rate: f64,
    disruption: bool,
    time: f64,
    engine: &SimulationEngine,
    anchor_recruitment: f64,
    anchor_disruption: f64,
) -> String {
    let p = &engine.particle;
    let d = recruitment::recruitment_diagnostic_summary(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    [
        seed.to_string(),
        format!("{rate:.8}"),
        usize::from(disruption).to_string(),
        format!("{time:.6}"),
        format!("{:.17}", rooted_membership(engine)),
        format!("{:.17}", fielded_force(engine)),
        format!("{:.17}", foothold_strength(engine)),
        format!(
            "{:.17}",
            p.organizations
                .capital
                .get(INSURGENT)
                .copied()
                .unwrap_or(0.0)
        ),
        format!("{:.17}", p.counters.recruitment - anchor_recruitment),
        format!("{:.17}", cumulative_disruption(engine) - anchor_disruption),
        usize::from(
            p.organizations
                .active
                .get(INSURGENT)
                .copied()
                .unwrap_or(0)
                != 0,
        )
        .to_string(),
        format!("{:.17}", d.hazard_mass),
        format!("{:.17}", d.eligible_represented_mass),
        format!("{:.17}", d.accessible_eligible_represented_mass),
        format!("{:.17}", d.mean_social_access),
        format!("{:.17}", d.mean_formation_access),
        format!("{:.17}", d.mean_member_access),
        format!("{:.17}", d.mean_foothold_access),
        format!("{:.17}", d.mean_selected_access),
        format!("{:.17}", d.mean_base_intensity),
        format!("{:.17}", d.mean_combined_intensity),
        format!("{:.17}", d.mean_grievance),
        format!("{:.17}", d.mean_fear),
        format!("{:.17}", d.mean_political_access),
        format!("{:.17}", d.mean_compatibility),
        format!("{:.17}", d.mean_local_congruence),
        format!("{:.17}", d.mean_logit),
        format!("{:.17}", d.dominant_social_fraction),
        format!("{:.17}", d.dominant_formation_fraction),
        format!("{:.17}", d.dominant_member_fraction),
        format!("{:.17}", d.dominant_foothold_fraction),
        format!("{:.17}", d.capital_social),
    ]
    .join(",")
}

fn diagnostic_times(anchor_day: f64, end_day: f64) -> Vec<f64> {
    let mut times = vec![anchor_day];
    let mut time = ((anchor_day / 7.0).floor() + 1.0) * 7.0;
    while time < end_day - 1.0e-9 {
        times.push(time);
        time += 7.0;
    }
    if times
        .last()
        .is_none_or(|last| (*last - end_day).abs() > 1.0e-9)
    {
        times.push(end_day);
    }
    times
}

fn run_cell(
    seed: u64,
    anchor_engine: &SimulationEngine,
    rate: f64,
    disruption: bool,
    end_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    engine.config.recruitment_rate = SimulationConfig::default().recruitment_rate * rate;
    engine.config.state_regeneration.underground_disruption_rate = if disruption {
        SimulationConfig::default()
            .state_regeneration
            .underground_disruption_rate
    } else {
        0.0
    };
    let anchor_recruitment = engine.particle.counters.recruitment;
    let anchor_disruption = cumulative_disruption(&engine);
    let mut rows = Vec::new();
    for time in diagnostic_times(engine.particle.time, end_day) {
        if time > engine.particle.time + 1.0e-9 {
            engine
                .advance_until(time)
                .map_err(|error| error.to_string())?;
        }
        rows.push(output_row(
            seed,
            rate,
            disruption,
            time,
            &engine,
            anchor_recruitment,
            anchor_disruption,
        ));
    }
    Ok(rows)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../coin_regenerative_throttling_weekly_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026186000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let end_day: f64 = arg(&args, 8, 240.0);
    let anchor_recruitment_multiplier: f64 = arg(&args, 9, 0.0625);
    let rate_profile = args.get(10).map(String::as_str).unwrap_or("all");
    ensure_parent(&out)?;

    let rates = match rate_profile {
        "all" => vec![0.03125f64, 0.0625, 0.125],
        "high_only" => vec![0.125f64],
        other => return Err(format!("unknown rate profile {other}").into()),
    };
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
                    end_day,
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
            rates.iter().copied().flat_map(move |rate| {
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
                run_cell(*seed, engine, *rate, *disruption, end_day)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,recruitment_multiplier,underground_disruption,time,rooted_armed_membership_mass,fielded_force_personnel,foothold_strength_sum,canonical_insurgent_capital,cumulative_recruitment_mass_since_anchor,cumulative_underground_disruption_since_anchor,canonical_insurgent_active,hazard_mass,eligible_represented_mass,accessible_eligible_represented_mass,mean_social_access,mean_formation_access,mean_member_access,mean_foothold_access,mean_selected_access,mean_base_intensity,mean_combined_intensity,mean_grievance,mean_fear,mean_political_access,mean_compatibility,mean_local_congruence,mean_logit,dominant_social_fraction,dominant_formation_fraction,dominant_member_fraction,dominant_foothold_fraction,canonical_insurgent_social_capital"
    )?;
    let mut count = 0usize;
    for result in results {
        for line in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{line}")?;
            count += 1;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} seeds={seeds} cells={} rows={count} times_per_cell={}",
        rates.len() * 2,
        diagnostic_times(anchor_day, end_day).len()
    );
    Ok(())
}
