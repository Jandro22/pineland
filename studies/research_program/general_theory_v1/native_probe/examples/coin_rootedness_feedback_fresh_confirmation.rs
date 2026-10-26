use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, INSURGENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone, Copy)]
struct Snapshot {
    rooted: f64,
    force: f64,
    capital: f64,
    recruitment: f64,
    disruption: f64,
    active: usize,
    hazard: f64,
    hazard_no_root: f64,
    eligible: f64,
    selected_access: f64,
    base_intensity: f64,
    combined_intensity: f64,
    grievance: f64,
    fear: f64,
    political_access: f64,
    compatibility: f64,
    local_congruence: f64,
    mean_logit: f64,
    social_exposure: f64,
    social_capital: f64,
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

fn base_config(seed: u64, agents: usize, localities: usize, horizon: f64, anchor_rate: f64) -> SimulationConfig {
    let mut config = SimulationConfig::default();
    config.seed = seed;
    config.initialization_seed = Some(seed);
    config.agent_count = agents;
    config.locality_count = localities;
    config.horizon_days = horizon;
    config.output_mode = "forensic".to_string();
    config.foreign_affairs.enabled = false;
    config.state_regeneration.enabled = true;
    config.recruitment_rate *= anchor_rate;
    config.state_regeneration.underground_disruption_rate = 0.0;
    config
}

fn rooted(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    (0..p.people.organization.len())
        .filter(|&i| p.people.organization[i] as usize == INSURGENT)
        .map(|i| p.people.represented_population[i].max(0.0) * p.people.armed_fraction[i].clamp(0.0, 1.0))
        .sum()
}

fn force(engine: &SimulationEngine) -> f64 {
    let p = &engine.particle;
    if p.organizations.active.get(INSURGENT).copied().unwrap_or(0) == 0 {
        return 0.0;
    }
    (0..p.formations.personnel.len())
        .filter(|&i| {
            p.formations.organization[i] as usize == INSURGENT
                && p.formations.active[i] != 0
                && p.formations.operational_status[i] == 1
                && p.formations.outside_pineland[i] == 0
        })
        .map(|i| p.formations.personnel[i].max(0.0))
        .sum()
}

fn disruption(engine: &SimulationEngine) -> f64 {
    engine
        .particle
        .locality
        .government_cumulative_underground_disruption
        .iter()
        .copied()
        .sum()
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let d = recruitment::recruitment_diagnostic_summary(
        &engine.particle,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let mut no_root_config = engine.config.clone();
    no_root_config.organization_ecology.local_rootedness_weight = 0.0;
    let no_root = recruitment::recruitment_diagnostic_summary(
        &engine.particle,
        &engine.topology,
        &no_root_config,
        INSURGENT,
    );
    Snapshot {
        rooted: rooted(engine),
        force: force(engine),
        capital: engine.particle.organizations.capital.get(INSURGENT).copied().unwrap_or(0.0),
        recruitment: engine.particle.counters.recruitment,
        disruption: disruption(engine),
        active: usize::from(engine.particle.organizations.active.get(INSURGENT).copied().unwrap_or(0) != 0),
        hazard: d.hazard_mass,
        hazard_no_root: no_root.hazard_mass,
        eligible: d.eligible_represented_mass,
        selected_access: d.mean_selected_access,
        base_intensity: d.mean_base_intensity,
        combined_intensity: d.mean_combined_intensity,
        grievance: d.mean_grievance,
        fear: d.mean_fear,
        political_access: d.mean_political_access,
        compatibility: d.mean_compatibility,
        local_congruence: d.mean_local_congruence,
        mean_logit: d.mean_logit,
        social_exposure: d.mean_social_access,
        social_capital: d.capital_social,
    }
}

fn row(seed: u64, rate: f64, u: bool, tp: &str, time: f64, s: &Snapshot, anchor: &Snapshot) -> String {
    [
        seed.to_string(),
        format!("{rate:.8}"),
        usize::from(u).to_string(),
        tp.to_string(),
        format!("{time:.6}"),
        format!("{:.17}", s.rooted),
        format!("{:.17}", s.force),
        format!("{:.17}", s.capital),
        format!("{:.17}", s.recruitment - anchor.recruitment),
        format!("{:.17}", s.disruption - anchor.disruption),
        s.active.to_string(),
        format!("{:.17}", s.hazard),
        format!("{:.17}", s.hazard_no_root),
        format!("{:.17}", s.eligible),
        format!("{:.17}", s.selected_access),
        format!("{:.17}", s.base_intensity),
        format!("{:.17}", s.combined_intensity),
        format!("{:.17}", s.grievance),
        format!("{:.17}", s.fear),
        format!("{:.17}", s.political_access),
        format!("{:.17}", s.compatibility),
        format!("{:.17}", s.local_congruence),
        format!("{:.17}", s.mean_logit),
        format!("{:.17}", s.social_exposure),
        format!("{:.17}", s.social_capital),
    ].join(",")
}

fn run_cell(
    seed: u64,
    anchor_engine: &SimulationEngine,
    rate: f64,
    u: bool,
    intervention_end: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    engine.config.recruitment_rate = SimulationConfig::default().recruitment_rate * rate;
    engine.config.state_regeneration.underground_disruption_rate = if u {
        SimulationConfig::default().state_regeneration.underground_disruption_rate
    } else {
        0.0
    };
    let anchor = snapshot(&engine);
    engine.advance_until(intervention_end).map_err(|e| e.to_string())?;
    let intervention = snapshot(&engine);
    engine.config.state_regeneration.underground_disruption_rate = 0.0;
    engine.advance_until(final_day).map_err(|e| e.to_string())?;
    let final_snapshot = snapshot(&engine);
    Ok(vec![
        row(seed, rate, u, "anchor", anchor_engine.particle.time, &anchor, &anchor),
        row(seed, rate, u, "intervention_end", intervention_end, &intervention, &anchor),
        row(seed, rate, u, "final", final_day, &final_snapshot, &anchor),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args.get(1).cloned().unwrap_or_else(|| "../coin_rootedness_feedback_fresh_confirmation_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 24);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026191000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let intervention_end: f64 = arg(&args, 8, 240.0);
    let final_day: f64 = arg(&args, 9, 360.0);
    let anchor_rate: f64 = arg(&args, 10, 0.0625);
    ensure_parent(&out)?;
    let rates = [0.03125f64, 0.125];
    let pool = rayon::ThreadPoolBuilder::new().num_threads(threads).build()?;

    let anchors: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seeds).into_par_iter().map(|offset| {
            let seed = seed_base + offset as u64;
            let mut engine = SimulationEngine::new(base_config(seed, agents, localities, final_day, anchor_rate))
                .map_err(|e| e.to_string())?;
            engine.particle_execution = true;
            engine.advance_until(anchor_day).map_err(|e| e.to_string())?;
            Ok((seed, engine))
        }).collect()
    });
    let mut anchors_ok = Vec::with_capacity(seeds);
    for result in anchors {
        anchors_ok.push(result.map_err(std::io::Error::other)?);
    }
    anchors_ok.sort_by_key(|(seed, _)| *seed);

    let tasks = anchors_ok.iter().flat_map(|(seed, engine)| {
        rates.iter().copied().flat_map(move |rate| {
            [false, true].into_iter().map(move |u| (*seed, engine, rate, u))
        })
    }).collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks.par_iter().map(|(seed, engine, rate, u)| {
            run_cell(*seed, engine, *rate, *u, intervention_end, final_day)
        }).collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,recruitment_multiplier,underground_disruption,timepoint,time,rooted_armed_membership_mass,fielded_force_personnel,canonical_insurgent_capital,cumulative_recruitment_mass_since_anchor,cumulative_underground_disruption_since_anchor,canonical_insurgent_active,recruitment_hazard_mass,recruitment_hazard_no_rootedness,eligible_recruitment_mass,mean_selected_access,mean_base_intensity,mean_combined_intensity,mean_grievance,mean_fear,mean_political_access,mean_compatibility,mean_local_congruence,mean_logit,mean_social_exposure,canonical_insurgent_social_capital")?;
    let mut count = 0usize;
    for result in results {
        for line in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{line}")?;
            count += 1;
        }
    }
    writer.flush()?;
    println!("wrote {out} seeds={seeds} cells={} rows={count}", rates.len() * 2);
    Ok(())
}
