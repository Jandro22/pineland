use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, GOVERNMENT, INSURGENT, MILITARY};
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
    government_legitimacy: f64,
    institution_capacity: f64,
    actions: f64,
    military_losses: f64,
    population: f64,
    displaced: f64,
    government_capital: f64,
}

#[derive(Default)]
struct Ledger {
    political_outflow: f64,
    total_outflow: f64,
    inflow: f64,
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

fn modes() -> &'static [&'static str] {
    &[
        "equal_locality",
        "per_capita",
        "threat_weighted",
        "need_weighted",
        "marginal_return",
    ]
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let mut rooted = 0.0;
    let mut leg_num = 0.0;
    let mut people_weight = 0.0;
    for person in 0..p.people.organization.len() {
        let w = p.people.represented_population[person].max(0.0);
        if p.people.organization[person] as usize == INSURGENT {
            rooted += w * p.people.armed_fraction[person].clamp(0.0, 1.0);
        }
        leg_num += w * p.people.government_legitimacy[person];
        people_weight += w;
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
    let mut actions = 0.0;
    for locality in 0..nloc {
        let i = INSURGENT * nloc + locality;
        if i < p.footholds.strength.len() {
            foothold += p.footholds.strength[i].max(0.0);
            actions += p.footholds.cumulative_actions[i].max(0.0);
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
    let population = p.locality.population.iter().copied().sum::<f64>();
    let local_inst_start = 6 + engine.topology.district_count();
    let mut gc = 0.0;
    let mut ic = 0.0;
    let mut iw = 0.0;
    let mut insurgent_control = 0.0;
    for locality in 0..nloc {
        let w = p.locality.population[locality].max(0.0);
        gc += w * p.locality.effective_control(locality, 0);
        insurgent_control += w * p.locality.effective_control(locality, 1);
        let institution = local_inst_start + locality;
        if institution < p.political.institution_capacity.len() {
            ic += w * p.political.institution_capacity[institution];
            iw += w;
        }
    }
    let military_losses = (0..p.formations.personnel.len())
        .filter(|&f| p.formations.organization[f] as usize == MILITARY)
        .map(|f| p.formations.cumulative_losses[f].max(0.0))
        .sum::<f64>();
    Snapshot {
        rooted,
        force,
        foothold,
        hazard,
        insurgent_control: insurgent_control / population.max(1e-12),
        government_control: gc / population.max(1e-12),
        government_legitimacy: leg_num / people_weight.max(1e-12),
        institution_capacity: ic / iw.max(1e-12),
        actions,
        military_losses,
        population,
        displaced: p
            .locality
            .displaced_population
            .iter()
            .copied()
            .map(|x| x.max(0.0))
            .sum(),
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

fn row(
    seed: u64,
    mode: &str,
    timepoint: &str,
    time: f64,
    s: &Snapshot,
    anchor: &Snapshot,
    ledger: &Ledger,
) -> String {
    format!(
        "{seed},{mode},{timepoint},{time:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
        s.rooted,
        s.force,
        s.foothold,
        s.hazard,
        s.insurgent_control,
        s.government_control,
        s.government_legitimacy,
        s.institution_capacity,
        s.actions - anchor.actions,
        s.military_losses - anchor.military_losses,
        (anchor.population - s.population).max(0.0),
        s.displaced / anchor.population.max(1e-12),
        s.government_capital,
        ledger.inflow,
        ledger.total_outflow,
        ledger.political_outflow,
        ledger.political_outflow * 0.90,
    )
}

fn run_case(
    seed: u64,
    anchor_engine: &SimulationEngine,
    mode: &str,
    intervention_end: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    let baseline = engine.config.clone();
    let anchor = snapshot(&engine);
    engine.config.political_order.public_allocation_mode = mode.to_string();
    engine.config.political_order.public_budget_share = 0.90;
    engine.config.political_order.patronage_share = 0.08;
    engine.config.political_order.private_diversion_share = 0.02;
    let ledger = advance_ledger(&mut engine, intervention_end)?;
    let end = snapshot(&engine);
    engine.config = baseline;
    engine.advance_until(final_day).map_err(|e| e.to_string())?;
    let final_s = snapshot(&engine);
    Ok(vec![
        row(
            seed,
            mode,
            "anchor",
            anchor_engine.particle.time,
            &anchor,
            &anchor,
            &Ledger::default(),
        ),
        row(
            seed,
            mode,
            "intervention_end",
            intervention_end,
            &end,
            &anchor,
            &ledger,
        ),
        row(seed, mode, "final", final_day, &final_s, &anchor, &ledger),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../development_allocation_frontier_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 16);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 12);
    let seed_base: u64 = arg(&args, 6, 2026121000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let intervention_end: f64 = arg(&args, 8, 240.0);
    let final_day: f64 = arg(&args, 9, 360.0);
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
        .flat_map(|(seed, engine)| modes().iter().map(move |mode| (*seed, engine, *mode)))
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, mode)| run_case(*seed, engine, mode, intervention_end, final_day))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,mode,timepoint,time,rooted_armed_membership_mass,fielded_force_personnel,foothold_strength_sum,recruitment_hazard_mass,population_weighted_insurgent_control,population_weighted_government_control,mean_government_legitimacy,mean_local_institution_capacity,cumulative_insurgent_actions_since_anchor,government_military_losses_since_anchor,population_loss_since_anchor,displaced_population_fraction,government_capital,government_capital_inflow_intervention,government_capital_outflow_intervention,political_order_outflow_intervention,public_development_outflow_intervention")?;
    for result in results {
        for r in result.map_err(std::io::Error::other)? {
            writeln!(w, "{r}")?;
        }
    }
    w.flush()?;
    println!(
        "wrote {out} seeds={seeds} modes={} rows={}",
        modes().len(),
        seeds * modes().len() * 3
    );
    Ok(())
}
