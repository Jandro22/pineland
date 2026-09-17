use pineland_core::config::SimulationConfig;
use pineland_model::{SimulationEngine, GOVERNMENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone)]
struct Snapshot {
    government_legitimacy: f64,
    state_legitimacy: f64,
    political_access: f64,
    institution_capacity: f64,
    government_control: f64,
    government_capital: f64,
}

#[derive(Default)]
struct Ledger {
    inflow: f64,
    total_outflow: f64,
    political_outflow: f64,
}

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
    c.state_regeneration.enabled = true;
    c.foreign_affairs.enabled = false;
    c
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let mut gl = 0.0;
    let mut sl = 0.0;
    let mut pa = 0.0;
    let mut pw = 0.0;
    for person in 0..p.people.represented_population.len() {
        let w = p.people.represented_population[person].max(0.0);
        gl += w * p.people.government_legitimacy[person];
        sl += w * p.people.state_legitimacy[person];
        pa += w * p.people.political_access[person];
        pw += w;
    }
    let nloc = engine.topology.locality_count();
    let local_inst_start = 6 + engine.topology.district_count();
    let mut ic = 0.0;
    let mut gc = 0.0;
    let mut lw = 0.0;
    for locality in 0..nloc {
        let w = p.locality.population[locality].max(0.0);
        let inst = local_inst_start + locality;
        if inst < p.political.institution_capacity.len() {
            ic += w * p.political.institution_capacity[inst];
        }
        gc += w * p.locality.effective_control(locality, 0);
        lw += w;
    }
    Snapshot {
        government_legitimacy: gl / pw.max(1.0e-12),
        state_legitimacy: sl / pw.max(1.0e-12),
        political_access: pa / pw.max(1.0e-12),
        institution_capacity: ic / lw.max(1.0e-12),
        government_control: gc / lw.max(1.0e-12),
        government_capital: p.organizations.capital[GOVERNMENT],
    }
}

fn advance_ledger(engine: &mut SimulationEngine, until: f64) -> Result<Ledger, String> {
    let mut l = Ledger::default();
    loop {
        let Some(event) = engine.particle.scheduler.peek() else {
            break;
        };
        if event.time > until {
            break;
        }
        let kind = event.payload.kind().to_string();
        let before = engine.particle.organizations.capital[GOVERNMENT];
        if engine
            .advance_until_limited(until, Some(1))
            .map_err(|e| e.to_string())?
            == 0
        {
            break;
        }
        let delta = engine.particle.organizations.capital[GOVERNMENT] - before;
        if delta > 0.0 {
            l.inflow += delta;
        } else if delta < 0.0 {
            l.total_outflow += -delta;
            if kind == "political_order" {
                l.political_outflow += -delta;
            }
        }
    }
    if engine.particle.time < until {
        engine.advance_until(until).map_err(|e| e.to_string())?;
    }
    Ok(l)
}

fn modes() -> &'static [&'static str] {
    &["equal_locality", "marginal_return"]
}

fn multipliers() -> &'static [f64] {
    &[1.0, 5.0, 10.0, 20.0, 40.0, 80.0]
}

fn run_case(
    seed: u64,
    anchor_engine: &SimulationEngine,
    mode: &str,
    multiplier: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    let anchor = snapshot(&engine);
    engine.config.political_order.public_allocation_mode = mode.to_string();
    engine.config.political_order.public_budget_share = 0.90;
    engine.config.political_order.patronage_share = 0.08;
    engine.config.political_order.private_diversion_share = 0.02;
    engine.config.political_order.federal_policy_budget *= multiplier;
    let l = advance_ledger(&mut engine, final_day)?;
    let final_s = snapshot(&engine);
    Ok(vec![
        format!(
            "{seed},{mode},{multiplier:.6},anchor,{:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},0,0,0,0",
            anchor_engine.particle.time,
            anchor.government_legitimacy,
            anchor.state_legitimacy,
            anchor.political_access,
            anchor.institution_capacity,
            anchor.government_control,
            anchor.government_capital,
        ),
        format!(
            "{seed},{mode},{multiplier:.6},final,{final_day:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            final_s.government_legitimacy,
            final_s.state_legitimacy,
            final_s.political_access,
            final_s.institution_capacity,
            final_s.government_control,
            final_s.government_capital,
            l.inflow,
            l.total_outflow,
            l.political_outflow,
            l.political_outflow * 0.90,
        ),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../development_dose_response_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 8);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026126000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let final_day: f64 = arg(&args, 8, 240.0);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let anchors: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|s| {
                let seed = seed_base + s as u64;
                let mut e = SimulationEngine::new(config(seed, agents, localities, final_day))
                    .map_err(|x| x.to_string())?;
                e.particle_execution = true;
                e.advance_until(anchor_day).map_err(|x| x.to_string())?;
                Ok((seed, e))
            })
            .collect()
    });
    let mut a = Vec::with_capacity(seeds);
    for r in anchors {
        a.push(r.map_err(std::io::Error::other)?);
    }
    a.sort_by_key(|(seed, _)| *seed);
    let tasks = a
        .iter()
        .flat_map(|(seed, engine)| {
            modes().iter().flat_map(move |mode| {
                multipliers()
                    .iter()
                    .map(move |mult| (*seed, engine, *mode, *mult))
            })
        })
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, mode, mult)| run_case(*seed, engine, mode, *mult, final_day))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,allocation_mode,budget_multiplier,timepoint,time,mean_government_legitimacy,mean_state_legitimacy,mean_political_access,mean_local_institution_capacity,population_weighted_government_control,government_capital,government_capital_inflow,total_government_outflow,political_order_outflow,public_development_outflow")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!(
        "wrote {out} seeds={seeds} cells={} rows={}",
        modes().len() * multipliers().len(),
        seeds * modes().len() * multipliers().len() * 2
    );
    Ok(())
}
