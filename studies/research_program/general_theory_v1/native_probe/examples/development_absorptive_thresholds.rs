use pineland_core::config::SimulationConfig;
use pineland_model::SimulationEngine;
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

fn config(seed: u64, agents: usize, localities: usize, horizon: f64) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.state_regeneration.enabled = true;
    c.foreign_affairs.enabled = false;
    c
}

fn run_seed(seed: u64, agents: usize, localities: usize, time: f64) -> Result<Vec<String>, String> {
    let mut engine =
        SimulationEngine::new(config(seed, agents, localities, time)).map_err(|e| e.to_string())?;
    engine.advance_until(time).map_err(|e| e.to_string())?;
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let institution_start = 6 + engine.topology.district_count();
    let baseline_public = engine.config.political_order.federal_policy_budget
        * engine.config.political_order.public_budget_share
        / nloc.max(1) as f64;
    let mut rows = Vec::with_capacity(nloc);
    for locality in 0..nloc {
        let inst = institution_start + locality;
        let cap = p.political.institution_capacity[inst].clamp(0.0, 1.0);
        let integrity = p.political.institution_integrity[inst].clamp(0.0, 1.0);
        let reach = p.political.institution_reach[inst].clamp(0.0, 1.0);
        let compliance = p.political.institution_compliance[inst].clamp(0.0, 1.0);
        let autonomy = p.political.institution_autonomy[inst].clamp(0.0, 1.0);
        let infrastructure = p.locality.infrastructure[locality].clamp(0.0, 1.0);
        let population = p.locality.population[locality].max(0.0);
        let service_factor = ((0.8 + 0.2 * infrastructure)
            + integrity
            + cap
            + infrastructure
            + (0.5 + 0.5 * autonomy))
            / 5.0;
        let gov_legit_p = if service_factor * (1.0 + integrity) > 1.0e-12 {
            0.7 / (service_factor * (1.0 + integrity))
        } else {
            f64::INFINITY
        };
        let state_legit_p = if integrity > 1.0e-12 {
            0.25 / integrity
        } else {
            f64::INFINITY
        };
        let access_p = 0.4 / (1.0 + autonomy);

        // Deterministic current-state approximation: the political event's
        // sampled compliance has mean approximately equal to stored compliance.
        // Thus nominal public -> effective_public contributes one compliance
        // factor and production contributes the stored second factor.
        let conversion = cap * reach * compliance * compliance;
        let pop_scale = (population * 0.05).max(1.0);
        let public_for = |production: f64| {
            if conversion <= 1.0e-12 || !production.is_finite() {
                f64::INFINITY
            } else {
                production * pop_scale / conversion
            }
        };
        let req_gov = public_for(gov_legit_p);
        let req_state = public_for(state_legit_p);
        let req_access = public_for(access_p);
        let saturation_public = public_for(1.0);
        let marginal_production_per_public = conversion / pop_scale;

        rows.push(format!(
            "{seed},{time:.6},{locality},{population:.17},{cap:.17},{integrity:.17},{reach:.17},{compliance:.17},{autonomy:.17},{infrastructure:.17},{service_factor:.17},{gov_legit_p:.17},{state_legit_p:.17},{access_p:.17},{req_gov:.17},{req_state:.17},{req_access:.17},{saturation_public:.17},{marginal_production_per_public:.17},{baseline_public:.17}",
        ));
    }
    Ok(rows)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../development_absorptive_thresholds_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 4);
    let seed_base: u64 = arg(&args, 6, 2026120000u64);
    let time: f64 = arg(&args, 7, 60.0);
    ensure_parent(&out)?;
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|s| run_seed(seed_base + s as u64, agents, localities, time))
            .collect()
    });
    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,time,locality,population,institution_capacity,institution_integrity,institution_reach,institution_compliance,institution_autonomy,infrastructure,service_factor,production_threshold_government_legitimacy,production_threshold_state_legitimacy,production_threshold_political_access,nominal_public_required_government_legitimacy,nominal_public_required_state_legitimacy,nominal_public_required_political_access,nominal_public_saturation,marginal_production_per_nominal_public,baseline_equal_locality_nominal_public")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} seeds={seeds} rows={}", seeds * localities);
    Ok(())
}
