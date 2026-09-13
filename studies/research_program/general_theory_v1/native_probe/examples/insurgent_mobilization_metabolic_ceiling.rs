use pineland_core::config::SimulationConfig;
use pineland_model::{SimulationEngine, INSURGENT};
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
    recruitment_mult: f64,
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
    c.state_regeneration.underground_disruption_rate = 0.0;
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
    c.recruitment_rate *= recruitment_mult;
    c
}

fn rooted_mass(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.people.organization.len())
        .filter(|&i| p.people.organization[i] as usize == INSURGENT)
        .map(|i| p.people.represented_population[i].max(0.0) * p.people.armed_fraction[i].max(0.0))
        .sum()
}

fn operational_force(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.formations.personnel.len())
        .filter(|&f| {
            p.formations.organization[f] as usize == INSURGENT
                && p.formations.active[f] != 0
                && p.formations.operational_status[f] == 1
                && p.formations.outside_pineland[f] == 0
        })
        .map(|f| p.formations.personnel[f].max(0.0))
        .sum()
}

fn cumulative_insurgent_losses(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.formations.personnel.len())
        .filter(|&f| p.formations.organization[f] as usize == INSURGENT)
        .map(|f| p.formations.cumulative_losses[f].max(0.0))
        .sum()
}

fn classify(
    pre_capital: f64,
    pre_cohesion: f64,
    pre_rooted: f64,
    pre_force: f64,
    minimum_force: f64,
) -> &'static str {
    if pre_capital <= 1.0e-9 {
        "capital"
    } else if pre_cohesion < 0.12 {
        "cohesion"
    } else if pre_rooted <= 1.0e-9 && pre_force < minimum_force.max(1.0e-9) {
        "rooted_and_fielded_exhaustion"
    } else {
        "stochastic"
    }
}

fn run_case(
    seed: u64,
    agents: usize,
    localities: usize,
    recruitment_mult: f64,
    horizon: f64,
) -> Result<String, String> {
    let mut e = SimulationEngine::new(config(seed, agents, localities, horizon, recruitment_mult))
        .map_err(|x| x.to_string())?;
    e.particle_execution = true;
    let initial_capital = e.particle.organizations.capital[INSURGENT];
    let minimum_force = e.config.organization_ecology.minimum_formation_personnel;
    let mut inflow = 0.0;
    let mut outflow = 0.0;
    let mut recruitment_burn = 0.0;
    let mut economy_inflow = 0.0;
    let mut collapse_time = f64::NAN;
    let mut collapse_event = "none".to_string();
    let mut collapse_cause = "survived".to_string();
    let mut pre_capital = f64::NAN;
    let mut pre_cohesion = f64::NAN;
    let mut pre_rooted = f64::NAN;
    let mut pre_force = f64::NAN;
    let mut pre_losses = f64::NAN;
    let mut recruitment_at_collapse = f64::NAN;

    while e.particle.time < horizon - 1.0e-9 {
        let Some(event) = e.particle.scheduler.peek() else {
            break;
        };
        if event.time > horizon {
            break;
        }
        let kind = event.payload.kind().to_string();
        // Only recruitment and economy events can change the canonical
        // insurgent's capital in this assay (foreign affairs are disabled).
        // Only the organization event can execute the collapse predicate.
        // The original probe recomputed O(people + formations) diagnostics
        // before *every* event; preserve identical accounting/classification
        // while paying that cost only at the scientifically relevant boundary.
        let capital_event = matches!(kind.as_str(), "recruitment" | "economy");
        let organization_event = kind == "organization";
        let capital_before = capital_event
            .then(|| e.particle.organizations.capital[INSURGENT]);
        let collapse_pre = organization_event.then(|| {
            (
                e.particle.organizations.active[INSURGENT],
                e.particle.organizations.capital[INSURGENT],
                e.particle.organizations.cohesion[INSURGENT],
                rooted_mass(&e),
                operational_force(&e),
                cumulative_insurgent_losses(&e),
                e.particle.counters.recruitment,
            )
        });
        let processed = e
            .advance_until_limited(horizon, Some(1))
            .map_err(|x| x.to_string())?;
        if processed == 0 {
            break;
        }
        if let Some(capital_before) = capital_before {
            let capital_after = e.particle.organizations.capital[INSURGENT];
            let delta = capital_after - capital_before;
            if delta > 0.0 {
                inflow += delta;
                if kind == "economy" {
                    economy_inflow += delta;
                }
            } else if delta < 0.0 {
                outflow += -delta;
                if kind == "recruitment" {
                    recruitment_burn += -delta;
                }
            }
        }
        if let Some((active_before, capital_before, cohesion_before, rooted_before, force_before, losses_before, recruitment_before)) = collapse_pre {
            let active_after = e.particle.organizations.active[INSURGENT];
            if active_before != 0 && active_after == 0 {
                collapse_time = e.particle.time;
                collapse_event = kind;
                pre_capital = capital_before;
                pre_cohesion = cohesion_before;
                pre_rooted = rooted_before;
                pre_force = force_before;
                pre_losses = losses_before;
                recruitment_at_collapse = recruitment_before;
                collapse_cause = classify(
                    pre_capital,
                    pre_cohesion,
                    pre_rooted,
                    pre_force,
                    minimum_force,
                )
                .to_string();
                break;
            }
        }
    }

    if e.particle.time < horizon && e.particle.organizations.active[INSURGENT] != 0 {
        e.advance_until(horizon).map_err(|x| x.to_string())?;
    }
    let collapsed = e.particle.organizations.active[INSURGENT] == 0;
    let final_capital = e.particle.organizations.capital[INSURGENT];
    let final_cohesion = e.particle.organizations.cohesion[INSURGENT];
    let final_rooted = rooted_mass(&e);
    let final_force = operational_force(&e);
    let final_recruitment = e.particle.counters.recruitment;
    let runway = recruitment_burn / (initial_capital + inflow).max(1.0e-12);
    Ok(format!(
        "{seed},{recruitment_mult:.6},{collapsed},{collapse_time:.17},{collapse_event},{collapse_cause},{initial_capital:.17},{inflow:.17},{outflow:.17},{recruitment_burn:.17},{economy_inflow:.17},{runway:.17},{pre_capital:.17},{pre_cohesion:.17},{pre_rooted:.17},{pre_force:.17},{pre_losses:.17},{recruitment_at_collapse:.17},{final_capital:.17},{final_cohesion:.17},{final_rooted:.17},{final_force:.17},{final_recruitment:.17}"
    ))
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../insurgent_mobilization_metabolic_ceiling_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 8);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026128000u64);
    let horizon: f64 = arg(&args, 7, 180.0);
    let profile = args.get(8).map(String::as_str).unwrap_or("main");
    ensure_parent(&out)?;
    let rates: Vec<f64> = match profile {
        "main" => vec![0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0],
        "low" => vec![0.0, 0.03125, 0.0625, 0.125, 0.25, 0.5],
        "confirm_low" => vec![0.0, 0.03125, 0.0625, 0.125, 0.25],
        "risk_frontier" => vec![
            0.0, 0.03125, 0.05, 0.0625, 0.075, 0.0875, 0.10, 0.1125, 0.125, 0.15,
            0.20, 0.25,
        ],
        _ => {
            return Err(
                format!(
                    "unknown profile {profile}; expected main, low, confirm_low, or risk_frontier"
                )
                .into(),
            )
        }
    };
    let cases = (0..seeds)
        .flat_map(|s| {
            rates
                .iter()
                .copied()
                .map(move |r| (seed_base + s as u64, r))
        })
        .collect::<Vec<_>>();
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<String, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, r)| run_case(*seed, agents, localities, *r, horizon))
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,recruitment_multiplier,collapsed,collapse_time,collapse_event,collapse_cause,initial_capital,capital_inflow,capital_outflow,recruitment_capital_burn,economy_capital_inflow,runway_ratio,precollapse_capital,precollapse_cohesion,precollapse_rooted,precollapse_operational_force,precollapse_cumulative_losses,cumulative_recruitment_at_collapse,final_capital,final_cohesion,final_rooted,final_operational_force,final_cumulative_recruitment")?;
    for r in results {
        writeln!(w, "{}", r.map_err(std::io::Error::other)?)?;
    }
    w.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}
