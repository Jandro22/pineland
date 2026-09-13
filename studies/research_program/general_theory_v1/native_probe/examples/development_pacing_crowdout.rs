use pineland_core::config::SimulationConfig;
use pineland_model::{SimulationEngine, GOVERNMENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Default, Clone)]
struct Ledger {
    inflow: f64,
    outflow: f64,
    political: f64,
    governance: f64,
    regeneration: f64,
    other: f64,
}

#[derive(Clone)]
struct Snapshot {
    government_legitimacy: f64,
    state_legitimacy: f64,
    political_access: f64,
    institution_capacity: f64,
    government_control: f64,
    capital: f64,
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
    c.output_mode = "forensic".into();
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c
}

fn snapshot(e: &SimulationEngine) -> Snapshot {
    let p = &e.particle;
    let mut gl = 0.0;
    let mut sl = 0.0;
    let mut access = 0.0;
    let mut pw = 0.0;
    for person in 0..p.people.represented_population.len() {
        let w = p.people.represented_population[person].max(0.0);
        gl += w * p.people.government_legitimacy[person];
        sl += w * p.people.state_legitimacy[person];
        access += w * p.people.political_access[person];
        pw += w;
    }
    let start = 6 + e.topology.district_count();
    let mut ic = 0.0;
    let mut gc = 0.0;
    let mut lw = 0.0;
    for locality in 0..e.topology.locality_count() {
        let w = p.locality.population[locality].max(0.0);
        let inst = start + locality;
        if inst < p.political.institution_capacity.len() {
            ic += w * p.political.institution_capacity[inst];
        }
        gc += w * p.locality.effective_control(locality, 0);
        lw += w;
    }
    Snapshot {
        government_legitimacy: gl / pw.max(1.0e-12),
        state_legitimacy: sl / pw.max(1.0e-12),
        political_access: access / pw.max(1.0e-12),
        institution_capacity: ic / lw.max(1.0e-12),
        government_control: gc / lw.max(1.0e-12),
        capital: p.organizations.capital[GOVERNMENT],
    }
}

fn advance_interval(e: &mut SimulationEngine, until: f64) -> Result<Ledger, String> {
    let mut l = Ledger::default();
    loop {
        let Some(event) = e.particle.scheduler.peek() else {
            break;
        };
        if event.time > until {
            break;
        }
        let kind = event.payload.kind().to_string();
        let before = e.particle.organizations.capital[GOVERNMENT];
        if e.advance_until_limited(until, Some(1))
            .map_err(|x| x.to_string())?
            == 0
        {
            break;
        }
        let delta = e.particle.organizations.capital[GOVERNMENT] - before;
        if delta > 0.0 {
            l.inflow += delta;
        } else if delta < 0.0 {
            let out = -delta;
            l.outflow += out;
            match kind.as_str() {
                "political_order" => l.political += out,
                "governance" => l.governance += out,
                "state_regeneration" => l.regeneration += out,
                _ => l.other += out,
            }
        }
    }
    if e.particle.time < until {
        e.advance_until(until).map_err(|x| x.to_string())?;
    }
    Ok(l)
}

fn run_case(
    seed: u64,
    anchor: &SimulationEngine,
    multiplier: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut e = anchor.clone();
    e.config.political_order.public_allocation_mode = "equal_locality".into();
    e.config.political_order.public_budget_share = 0.90;
    e.config.political_order.patronage_share = 0.08;
    e.config.political_order.private_diversion_share = 0.02;
    e.config.political_order.federal_policy_budget *= multiplier;
    let anchor_capital = e.particle.organizations.capital[GOVERNMENT];
    let mut rows = Vec::new();
    let mut prior = e.particle.time;
    let mut time = prior;
    while time <= final_day + 1.0e-9 {
        let l = if time <= prior + 1.0e-12 {
            Ledger::default()
        } else {
            advance_interval(&mut e, time)?
        };
        let s = snapshot(&e);
        rows.push(format!(
            "{seed},{multiplier:.6},{time:.6},{anchor_capital:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            s.capital,
            s.government_legitimacy,
            s.state_legitimacy,
            s.political_access,
            s.institution_capacity,
            s.government_control,
            l.inflow,
            l.outflow,
            l.political,
            l.governance,
            l.regeneration,
            l.other,
        ));
        prior = time;
        time += 15.0;
    }
    Ok(rows)
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../development_pacing_crowdout_v1.csv".into());
    let seeds: usize = arg(&args, 2, 6);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 6);
    let seed_base: u64 = arg(&args, 6, 2026126100u64);
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
            .map(|i| {
                let seed = seed_base + i as u64;
                let mut e = SimulationEngine::new(config(seed, agents, localities, final_day))
                    .map_err(|x| x.to_string())?;
                e.particle_execution = true;
                e.advance_until(anchor_day).map_err(|x| x.to_string())?;
                Ok((seed, e))
            })
            .collect()
    });
    let mut anchors_ok = Vec::new();
    for a in anchors {
        anchors_ok.push(a.map_err(std::io::Error::other)?);
    }
    let multipliers = [1.0, 5.0, 10.0, 20.0];
    let tasks = anchors_ok
        .iter()
        .flat_map(|(seed, e)| multipliers.iter().map(move |m| (*seed, e, *m)))
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, e, m)| run_case(*seed, e, *m, final_day))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w,"seed,budget_multiplier,time,anchor_government_capital,government_capital,mean_government_legitimacy,mean_state_legitimacy,mean_political_access,mean_local_institution_capacity,population_weighted_government_control,interval_inflow,interval_outflow,interval_political_outflow,interval_governance_outflow,interval_state_regeneration_outflow,interval_other_outflow")?;
    for r in results {
        for row in r.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!("wrote {out} seeds={seeds} cells=4 rows={}", seeds * 4 * 13);
    Ok(())
}
