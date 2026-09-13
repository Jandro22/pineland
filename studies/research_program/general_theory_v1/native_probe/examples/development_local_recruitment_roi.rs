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

fn config(seed: u64, agents: usize, localities: usize, horizon: f64) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c.state_regeneration.underground_disruption_rate = 0.0;
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
    c.recruitment_rate *= 0.0625;
    c
}

fn local_rooted(engine: &SimulationEngine, locality: usize) -> f64 {
    let p = &engine.particle;
    (0..p.people.organization.len())
        .filter(|&person| {
            p.people.organization[person] as usize == INSURGENT
                && p.people.residence[person] as usize == locality
        })
        .map(|person| {
            p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].clamp(0.0, 1.0)
        })
        .sum()
}

fn rows(seed: u64, engine: &SimulationEngine, increment: f64) -> Vec<String> {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let hazards = recruitment::recruitment_hazard_mass_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let access_sensitivity = recruitment::recruitment_hazard_access_sensitivity_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let local_inst_start = 6 + engine.topology.district_count();
    let public_total = engine.config.political_order.federal_policy_budget
        * engine.config.political_order.public_budget_share;
    let baseline_equal_public = public_total / nloc.max(1) as f64;
    let mut result = Vec::with_capacity(nloc);

    for locality in 0..nloc {
        let population = p.locality.population[locality].max(1.0);
        let institution = local_inst_start + locality;
        let capacity = p
            .political
            .institution_capacity
            .get(institution)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);
        let reach = p
            .political
            .institution_reach
            .get(institution)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);
        let compliance = p
            .political
            .institution_compliance
            .get(institution)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);
        let integrity = p
            .political
            .institution_integrity
            .get(institution)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);
        let autonomy = p
            .political
            .institution_autonomy
            .get(institution)
            .copied()
            .unwrap_or(0.0)
            .clamp(0.0, 1.0);

        let production_slope = capacity * reach * compliance * compliance
            / (population * 0.05).max(1.0);
        let baseline_production = (production_slope * baseline_equal_public).clamp(0.0, 1.0);
        let incremented_production =
            (production_slope * (baseline_equal_public + increment)).clamp(0.0, 1.0);
        let incremental_production = (incremented_production - baseline_production).max(0.0);
        let representation_factor = 0.5 + 0.5 * autonomy;
        let incremental_access = 0.03 * representation_factor * incremental_production;
        let hazard = hazards.get(locality).copied().unwrap_or(0.0).max(0.0);
        let sensitivity = access_sensitivity
            .get(locality)
            .copied()
            .unwrap_or(0.0)
            .max(0.0);
        let hazard_reduction = sensitivity * incremental_access;
        let fractional = if hazard > 1.0e-12 {
            (hazard_reduction / hazard).max(0.0)
        } else {
            0.0
        };
        let saturation_public = if production_slope > 1.0e-15 {
            1.0 / production_slope
        } else {
            f64::INFINITY
        };
        let headroom = (saturation_public - baseline_equal_public).max(0.0);
        let insurgent_control = p.locality.effective_control(locality, 1);
        let government_control = p.locality.effective_control(locality, 0);

        result.push(format!(
            "{seed},{locality},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            population,
            hazard,
            sensitivity,
            baseline_equal_public,
            increment,
            baseline_production,
            incremented_production,
            incremental_access,
            hazard_reduction,
            fractional,
            saturation_public,
            headroom,
            capacity,
            reach,
            compliance,
            integrity,
            autonomy,
            local_rooted(engine, locality),
            insurgent_control,
            government_control,
        ));
    }
    result
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../development_local_recruitment_roi_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026150000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let increment: f64 = arg(&args, 8, 1200.0);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let worlds: Vec<Result<Vec<String>, String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|s| {
                let seed = seed_base + s as u64;
                let mut engine = SimulationEngine::new(config(seed, agents, localities, anchor_day))
                    .map_err(|error| error.to_string())?;
                engine.particle_execution = true;
                engine
                    .advance_until(anchor_day)
                    .map_err(|error| error.to_string())?;
                Ok(rows(seed, &engine, increment))
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,locality,population,baseline_recruitment_hazard,hazard_reduction_per_plus1_political_access,baseline_equal_locality_nominal_public,incremental_nominal_public,baseline_expected_production,incremented_expected_production,incremental_political_access,first_order_hazard_reduction,fractional_hazard_reduction,nominal_public_to_saturate,nominal_public_headroom_to_saturation,institution_capacity,institution_reach,institution_compliance,institution_integrity,institution_autonomy,local_rooted_membership,insurgent_control,government_control")?;
    for world in worlds {
        for line in world.map_err(std::io::Error::other)? {
            writeln!(writer, "{line}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} seeds={seeds} localities={localities} increment={increment:.3}");
    Ok(())
}
