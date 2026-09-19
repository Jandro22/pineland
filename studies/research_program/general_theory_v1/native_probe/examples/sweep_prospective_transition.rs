use pineland_core::config::SimulationConfig;
use pineland_core::scheduler::EventPayload;
use pineland_model::{SimulationEngine, INSURGENT};
use rayon::prelude::*;
use std::time::Instant;

fn synthetic_config(seed: u64, horizon: f64) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = 300;
    c.locality_count = 34;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c.state_regeneration.underground_disruption_rate = 0.0;
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
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

struct RunResult {
    seed: u64,
    rec_mult: f64,
    cap_mult: f64,
    survived_120: bool,
    collapsed: bool,
    collapse_time: f64,
    collapse_cause: String,
    k_60: f64,
    k_120: f64,
    inflow: f64,
    outflow: f64,
    omega_k: f64,
}

fn simulate(seed: u64, rec_mult: f64, cap_mult: f64) -> RunResult {
    let horizon = 360.0;
    let mut cfg = synthetic_config(seed, horizon);
    cfg.recruitment_rate *= rec_mult;
    let mut e = SimulationEngine::new(cfg).expect("engine");
    e.particle_execution = true;
    e.particle.organizations.capital[INSURGENT] *= cap_mult;

    let min_force = e.config.organization_ecology.minimum_formation_personnel;
    let mut k_60 = f64::NAN;
    let mut k_120 = f64::NAN;
    let mut inflow_60_120 = 0.0;
    let mut outflow_60_120 = 0.0;
    let mut rec_burn_60_120 = 0.0;
    let mut collapse_time = f64::NAN;
    let mut collapse_cause = "survived".to_string();

    while e.particle.time < horizon - 1.0e-9 {
        let Some(event) = e.particle.scheduler.peek() else { break; };
        if event.time > horizon { break; }

        let payload = event.payload.clone();
        let is_cap_event = matches!(
            payload,
            EventPayload::Recruitment | EventPayload::Economy | EventPayload::ForeignAffairs
        );
        let is_org_event = matches!(payload, EventPayload::OrganizationEcology);
        let cap_before = if is_cap_event {
            Some(e.particle.organizations.capital[INSURGENT])
        } else {
            None
        };
        let org_pre = if is_org_event {
            Some((
                e.particle.organizations.active[INSURGENT],
                e.particle.organizations.capital[INSURGENT],
                e.particle.organizations.cohesion[INSURGENT],
                rooted_mass(&e),
                operational_force(&e),
            ))
        } else {
            None
        };

        let t_before = e.particle.time;
        let processed = e.advance_until_limited(horizon, Some(1)).expect("advance");
        if processed == 0 { break; }
        let t_after = e.particle.time;

        if t_before < 60.0 && t_after >= 60.0 && k_60.is_nan() {
            k_60 = e.particle.organizations.capital[INSURGENT];
        }
        if t_before < 120.0 && t_after >= 120.0 && k_120.is_nan() {
            k_120 = e.particle.organizations.capital[INSURGENT];
        }

        if let Some(cb) = cap_before {
            let ca = e.particle.organizations.capital[INSURGENT];
            let delta = ca - cb;
            if t_after >= 60.0 && t_after <= 120.0 {
                if delta > 0.0 {
                    inflow_60_120 += delta;
                } else if delta < 0.0 {
                    let out = -delta;
                    outflow_60_120 += out;
                    if matches!(payload, EventPayload::Recruitment) {
                        rec_burn_60_120 += out;
                    }
                }
            }
        }

        if let Some((active_before, cap_pre, coh_pre, root_pre, force_pre)) = org_pre {
            let active_after = e.particle.organizations.active[INSURGENT];
            if active_before != 0 && active_after == 0 {
                collapse_time = t_after;
                if cap_pre <= 1.0e-9 {
                    collapse_cause = "capital".to_string();
                } else if coh_pre < 0.12 {
                    collapse_cause = "cohesion".to_string();
                } else if root_pre <= 1.0e-9 && force_pre < min_force {
                    collapse_cause = "rooted_and_fielded_exhaustion".to_string();
                } else {
                    collapse_cause = "stochastic".to_string();
                }
                break;
            }
        }
    }

    let survived_120 = collapse_time.is_nan() || collapse_time > 120.0;
    let b_hat = (outflow_60_120 - inflow_60_120) / 60.0;
    let omega_k = if b_hat > 0.0 && k_120.is_finite() {
        (k_120 / b_hat) / 240.0
    } else {
        f64::INFINITY
    };

    RunResult {
        seed,
        rec_mult,
        cap_mult,
        survived_120,
        collapsed: !collapse_time.is_nan(),
        collapse_time,
        collapse_cause,
        k_60,
        k_120,
        inflow: inflow_60_120,
        outflow: outflow_60_120,
        omega_k,
    }
}

fn main() {
    println!("Testing parameter sweep for prospective transition...");
    let rec_rates = [0.10, 0.15, 0.20, 0.25, 0.35, 0.50];
    let cap_mults = [0.5, 1.0, 1.5, 2.0];
    let seeds = [2026130001u64, 2026130002, 2026130003, 2026130004];

    let mut cases = Vec::new();
    for &s in &seeds {
        for &r in &rec_rates {
            for &c in &cap_mults {
                cases.push((s, r, c));
            }
        }
    }

    let t0 = Instant::now();
    let results: Vec<RunResult> = cases
        .par_iter()
        .map(|(s, r, c)| simulate(*s, *r, *c))
        .collect();

    println!("Completed {} cases in {:.2}s", results.len(), t0.elapsed().as_secs_f64());
    println!("rec_mult,cap_mult,n,surv120,cap_coll_360,other_coll,surv360,mean_omega");
    for &r in &rec_rates {
        for &c in &cap_mults {
            let cell: Vec<&RunResult> = results.iter().filter(|x| (x.rec_mult - r).abs() < 1e-5 && (x.cap_mult - c).abs() < 1e-5).collect();
            let surv120_count = cell.iter().filter(|x| x.survived_120).count();
            let cap_coll_count = cell.iter().filter(|x| x.survived_120 && x.collapse_cause == "capital" && x.collapse_time <= 360.0).count();
            let other_coll = cell.iter().filter(|x| x.survived_120 && x.collapsed && x.collapse_cause != "capital" && x.collapse_time <= 360.0).count();
            let surv360 = cell.iter().filter(|x| x.survived_120 && !x.collapsed).count();
            let omegas: Vec<f64> = cell.iter().filter(|x| x.survived_120).map(|x| x.omega_k).collect();
            let mean_omega = if !omegas.is_empty() { omegas.iter().sum::<f64>() / omegas.len() as f64 } else { f64::NAN };
            println!("{:.2},{:.1},{},{},{},{},{},{:.2}", r, c, cell.len(), surv120_count, cap_coll_count, other_coll, surv360, mean_omega);
        }
    }
}
