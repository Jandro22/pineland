use pineland_core::config::SimulationConfig;
use pineland_core::scheduler::EventPayload;
use pineland_model::{SimulationEngine, INSURGENT};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;
use std::time::Instant;

fn ensure_parent(path: &str) -> Result<(), Box<dyn Error>> {
    if let Some(parent) = Path::new(path).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    Ok(())
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

fn active_formations_count(e: &SimulationEngine) -> usize {
    let p = &e.particle;
    (0..p.formations.personnel.len())
        .filter(|&f| {
            p.formations.organization[f] as usize == INSURGENT
                && p.formations.active[f] != 0
                && p.formations.operational_status[f] == 1
                && p.formations.outside_pineland[f] == 0
        })
        .count()
}

fn cumulative_losses(e: &SimulationEngine) -> f64 {
    let p = &e.particle;
    (0..p.formations.personnel.len())
        .filter(|&f| p.formations.organization[f] as usize == INSURGENT)
        .map(|f| p.formations.cumulative_losses[f].max(0.0))
        .sum()
}

#[derive(Clone, Debug)]
pub struct SimParams {
    pub seed: u64,
    pub family: String,
    pub rec_mult: f64,
    pub cap_mult: f64,
    pub fighter_conv_mult: f64,
    pub supply_days_mult: f64,
    pub init_supply_frac_mult: f64,
    pub extraction_mult: f64,
    pub external_support_val: Option<f64>,
    pub dynamic_foreign_affairs: bool,
    pub shock_type: String, // "none", "cutoff_120", "capital_shock_150", "surge_120"
}

pub struct TrajectoryResult {
    pub seed: u64,
    pub family: String,
    pub rec_mult: f64,
    pub cap_mult: f64,
    pub fighter_conv_mult: f64,
    pub supply_days_mult: f64,
    pub init_supply_frac_mult: f64,
    pub extraction_mult: f64,
    pub external_support_val: f64,
    pub shock_type: String,

    pub survived_to_120: bool,
    pub k_60: f64,
    pub k_120: f64,
    pub inflow_60_120: f64,
    pub outflow_60_120: f64,
    pub rec_burn_60_120: f64,
    pub b_hat: f64,
    pub tau_k: f64,
    pub omega_k: f64,
    pub lambda_k: f64,
    pub pi_m: f64,

    pub fielded_force_120: f64,
    pub active_formations_120: usize,
    pub rooted_mass_120: f64,
    pub cohesion_120: f64,
    pub recruits_window: f64,
    pub actions_window: u64,
    pub casualties_window: f64,

    pub collapsed: bool,
    pub collapse_time: f64,
    pub collapse_cause: String,
    pub capital_collapse_day360: u8,

    pub final_capital: f64,
    pub final_force: f64,
    pub final_rooted: f64,
    pub final_cohesion: f64,
    pub final_recruits: f64,
    pub final_actions: u64,
    pub final_casualties: f64,
}

pub fn run_trajectory(params: SimParams) -> TrajectoryResult {
    let horizon = 360.0;
    let mut config = SimulationConfig::default();
    config.seed = params.seed;
    config.initialization_seed = Some(params.seed);
    config.agent_count = 300;
    config.locality_count = 34;
    config.horizon_days = horizon;
    config.output_mode = "forensic".to_string();
    config.foreign_affairs.enabled = params.dynamic_foreign_affairs;
    config.state_regeneration.enabled = true;
    config.state_regeneration.underground_disruption_rate = 0.0;
    config.organization_ecology.collapse_requires_fielded_exhaustion = true;

    config.recruitment_rate *= params.rec_mult;
    config.organization_ecology.fighter_conversion_fraction *= params.fighter_conv_mult;
    config.logistics.formation_supply_days *= params.supply_days_mult;
    config.logistics.initial_supply_fraction *= params.init_supply_frac_mult;

    let mut e = SimulationEngine::new(config).expect("engine creation");
    e.particle_execution = true;

    // Apply initial capital scaling
    e.particle.organizations.capital[INSURGENT] *= params.cap_mult;

    // Apply extraction / economy scaling if requested
    if (params.extraction_mult - 1.0).abs() > 1e-5 {
        for loc in 0..e.particle.locality.economic_output.len() {
            e.particle.locality.economic_output[loc] *= params.extraction_mult;
        }
    }

    // Apply external support override if requested
    if let Some(ext) = params.external_support_val {
        e.particle.organizations.external_support[INSURGENT] = ext;
    }
    let actual_ext = e.particle.organizations.external_support[INSURGENT];

    let min_force = e.config.organization_ecology.minimum_formation_personnel;
    let mut k_60 = f64::NAN;
    let mut k_120 = f64::NAN;
    let mut force_120 = f64::NAN;
    let mut forms_120 = 0usize;
    let mut rooted_120 = f64::NAN;
    let mut cohesion_120 = f64::NAN;

    let mut recruits_60 = 0.0;
    let mut recruits_120 = 0.0;
    let mut actions_60 = 0u64;
    let mut actions_120 = 0u64;
    let mut losses_60 = 0.0;
    let mut losses_120 = 0.0;

    let mut inflow_60_120 = 0.0;
    let mut outflow_60_120 = 0.0;
    let mut rec_burn_60_120 = 0.0;

    let mut collapse_time = f64::NAN;
    let mut collapse_cause = "survived".to_string();

    let mut shock_applied = false;

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

        // Snapshot at day 60
        if t_before < 60.0 && t_after >= 60.0 && k_60.is_nan() {
            k_60 = e.particle.organizations.capital[INSURGENT];
            recruits_60 = e.particle.counters.recruitment;
            actions_60 = e.particle.counters.organized_actions;
            losses_60 = cumulative_losses(&e);
        }

        // Snapshot at day 120
        if t_before < 120.0 && t_after >= 120.0 && k_120.is_nan() {
            k_120 = e.particle.organizations.capital[INSURGENT];
            force_120 = operational_force(&e);
            forms_120 = active_formations_count(&e);
            rooted_120 = rooted_mass(&e);
            cohesion_120 = e.particle.organizations.cohesion[INSURGENT];
            recruits_120 = e.particle.counters.recruitment;
            actions_120 = e.particle.counters.organized_actions;
            losses_120 = cumulative_losses(&e);
        }

        // Apply H5 shocks if scheduled
        if !shock_applied {
            if params.shock_type == "cutoff_120" && t_after >= 120.0 {
                e.particle.organizations.external_support[INSURGENT] = 0.0;
                shock_applied = true;
            } else if params.shock_type == "capital_shock_150" && t_after >= 150.0 {
                // Remove 50% of remaining capital at day 150
                e.particle.organizations.capital[INSURGENT] *= 0.50;
                shock_applied = true;
            } else if params.shock_type == "surge_120" && t_after >= 120.0 {
                // Recruitment surge 2x after day 120
                e.config.recruitment_rate *= 2.0;
                shock_applied = true;
            }
        }

        // Track flows in window [60, 120]
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

        // Check collapse at organization ecology event
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

    let survived_to_120 = collapse_time.is_nan() || collapse_time > 120.0;
    let b_hat = (outflow_60_120 - inflow_60_120) / 60.0;
    let tau_k = if b_hat > 0.0 && k_120.is_finite() {
        k_120 / b_hat
    } else {
        f64::INFINITY
    };
    let omega_k = if tau_k.is_infinite() {
        f64::INFINITY
    } else {
        tau_k / 240.0
    };
    let denom = (k_60 + inflow_60_120).max(1.0e-9);
    let lambda_k = rec_burn_60_120 / denom;
    let pi_m = (params.rec_mult * params.fighter_conv_mult) / params.cap_mult.max(1.0e-9);

    let capital_collapse_day360 = if !collapse_time.is_nan()
        && collapse_time <= 360.0
        && collapse_cause == "capital"
    {
        1u8
    } else {
        0u8
    };

    TrajectoryResult {
        seed: params.seed,
        family: params.family,
        rec_mult: params.rec_mult,
        cap_mult: params.cap_mult,
        fighter_conv_mult: params.fighter_conv_mult,
        supply_days_mult: params.supply_days_mult,
        init_supply_frac_mult: params.init_supply_frac_mult,
        extraction_mult: params.extraction_mult,
        external_support_val: actual_ext,
        shock_type: params.shock_type,

        survived_to_120,
        k_60,
        k_120,
        inflow_60_120,
        outflow_60_120,
        rec_burn_60_120,
        b_hat,
        tau_k,
        omega_k,
        lambda_k,
        pi_m,

        fielded_force_120: force_120,
        active_formations_120: forms_120,
        rooted_mass_120: rooted_120,
        cohesion_120,
        recruits_window: (recruits_120 - recruits_60).max(0.0),
        actions_window: actions_120.saturating_sub(actions_60),
        casualties_window: (losses_120 - losses_60).max(0.0),

        collapsed: !collapse_time.is_nan(),
        collapse_time,
        collapse_cause,
        capital_collapse_day360,

        final_capital: e.particle.organizations.capital[INSURGENT],
        final_force: operational_force(&e),
        final_rooted: rooted_mass(&e),
        final_cohesion: e.particle.organizations.cohesion[INSURGENT],
        final_recruits: e.particle.counters.recruitment,
        final_actions: e.particle.counters.organized_actions,
        final_casualties: cumulative_losses(&e),
    }
}

const CSV_HEADER: &str = "seed,family,rec_mult,cap_mult,fighter_conv_mult,supply_days_mult,init_supply_frac_mult,extraction_mult,external_support_val,shock_type,survived_to_120,k_60,k_120,inflow_60_120,outflow_60_120,rec_burn_60_120,b_hat,tau_k,omega_k,lambda_k,pi_m,fielded_force_120,active_formations_120,rooted_mass_120,cohesion_120,recruits_window,actions_window,casualties_window,collapsed,collapse_time,collapse_cause,capital_collapse_day360,final_capital,final_force,final_rooted,final_cohesion,final_recruits,final_actions,final_casualties";

fn write_results(path: &str, results: &[TrajectoryResult]) -> Result<(), Box<dyn Error>> {
    ensure_parent(path)?;
    let mut w = BufWriter::new(File::create(path)?);
    writeln!(w, "{}", CSV_HEADER)?;
    for r in results {
        writeln!(
            w,
            "{},{},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{},{},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{},{:.6},{:.6},{:.6},{},{:.6},{},{:.6},{},{},{:.6},{:.6},{:.6},{:.6},{:.6},{},{:.6}",
            r.seed,
            r.family,
            r.rec_mult,
            r.cap_mult,
            r.fighter_conv_mult,
            r.supply_days_mult,
            r.init_supply_frac_mult,
            r.extraction_mult,
            r.external_support_val,
            r.shock_type,
            r.survived_to_120,
            r.k_60,
            r.k_120,
            r.inflow_60_120,
            r.outflow_60_120,
            r.rec_burn_60_120,
            r.b_hat,
            r.tau_k,
            r.omega_k,
            r.lambda_k,
            r.pi_m,
            r.fielded_force_120,
            r.active_formations_120,
            r.rooted_mass_120,
            r.cohesion_120,
            r.recruits_window,
            r.actions_window,
            r.casualties_window,
            r.collapsed,
            r.collapse_time,
            r.collapse_cause,
            r.capital_collapse_day360,
            r.final_capital,
            r.final_force,
            r.final_rooted,
            r.final_cohesion,
            r.final_recruits,
            r.final_actions,
            r.final_casualties
        )?;
    }
    w.flush()?;
    println!("Saved {} trajectories to {}", results.len(), path);
    Ok(())
}

fn build_discovery_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    let rec_rates = [0.08, 0.12, 0.18, 0.26];
    let cap_mults = [1.0, 1.5];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &r in &rec_rates {
            for &c in &cap_mults {
                cases.push(SimParams {
                    seed,
                    family: "discovery".to_string(),
                    rec_mult: r,
                    cap_mult: c,
                    fighter_conv_mult: 1.0,
                    supply_days_mult: 1.0,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: 1.0,
                    external_support_val: None,
                    dynamic_foreign_affairs: false,
                    shock_type: "none".to_string(),
                });
            }
        }
    }
    cases
}

fn build_h1_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    // H1: Capital replenishment family - vary real endogenous/recurring capital inflow (extraction)
    // Extraction multipliers: 0.5x (halved extraction) and 2.0x (doubled extraction)
    let extractions = [0.5, 2.0];
    let rec_rates = [0.12, 0.18];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &ext in &extractions {
            for &r in &rec_rates {
                cases.push(SimParams {
                    seed,
                    family: "H1_replenishment".to_string(),
                    rec_mult: r,
                    cap_mult: 1.0,
                    fighter_conv_mult: 1.0,
                    supply_days_mult: 1.0,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: ext,
                    external_support_val: None,
                    dynamic_foreign_affairs: false,
                    shock_type: "none".to_string(),
                });
            }
        }
    }
    cases
}

fn build_h2_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    // H2: External-resource family - vary external support to tested ledger
    // Default external support is 10,000/yr -> test 0.0 (zero subsidy) and 30,000.0 (3x baseline subsidy)
    let ext_supports = [0.0, 30000.0];
    let rec_rates = [0.12, 0.18];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &ext in &ext_supports {
            for &r in &rec_rates {
                cases.push(SimParams {
                    seed,
                    family: "H2_external_resource".to_string(),
                    rec_mult: r,
                    cap_mult: 1.0,
                    fighter_conv_mult: 1.0,
                    supply_days_mult: 1.0,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: 1.0,
                    external_support_val: Some(ext),
                    dynamic_foreign_affairs: false,
                    shock_type: "none".to_string(),
                });
            }
        }
    }
    cases
}

fn build_h3_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    // H3: Logistics-cost family - vary formation_supply_days
    // formation_supply_days multipliers: 0.5x (15d -> 12 supply/fighter) vs 1.5x (45d -> 36 supply/fighter)
    let supply_days = [0.5, 1.5];
    let rec_rates = [0.12, 0.18];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &sd in &supply_days {
            for &r in &rec_rates {
                cases.push(SimParams {
                    seed,
                    family: "H3_logistics_cost".to_string(),
                    rec_mult: r,
                    cap_mult: 1.0,
                    fighter_conv_mult: 1.0,
                    supply_days_mult: sd,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: 1.0,
                    external_support_val: None,
                    dynamic_foreign_affairs: false,
                    shock_type: "none".to_string(),
                });
            }
        }
    }
    cases
}

fn build_h4_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    // H4: Force-structure/absorption family - vary fighter conversion fraction
    // Multipliers: 0.5x (0.04 conversion) vs 1.5x (0.12 conversion)
    let conv_mults = [0.5, 1.5];
    let rec_rates = [0.12, 0.18];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &cm in &conv_mults {
            for &r in &rec_rates {
                cases.push(SimParams {
                    seed,
                    family: "H4_force_structure".to_string(),
                    rec_mult: r,
                    cap_mult: 1.0,
                    fighter_conv_mult: cm,
                    supply_days_mult: 1.0,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: 1.0,
                    external_support_val: None,
                    dynamic_foreign_affairs: false,
                    shock_type: "none".to_string(),
                });
            }
        }
    }
    cases
}

fn build_h5_params(seed_count: usize, seed_base: u64) -> Vec<SimParams> {
    // H5: History/shock family - support cutoff at day 120 vs capital shock at day 150
    let shocks = ["cutoff_120", "capital_shock_150"];
    let rec_rates = [0.10, 0.14];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &sh in &shocks {
            for &r in &rec_rates {
                cases.push(SimParams {
                    seed,
                    family: "H5_history_shock".to_string(),
                    rec_mult: r,
                    cap_mult: 1.25,
                    fighter_conv_mult: 1.0,
                    supply_days_mult: 1.0,
                    init_supply_frac_mult: 1.0,
                    extraction_mult: 1.0,
                    external_support_val: None,
                    dynamic_foreign_affairs: false,
                    shock_type: sh.to_string(),
                });
            }
        }
    }
    cases
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = env::args().collect();
    let mode = args.get(1).map(String::as_str).unwrap_or("discovery");
    let out_path = args.get(2).cloned().unwrap_or_else(|| {
        format!("../../../../outputs/coin-mechanisms/mobilization_runway_{mode}_v1.csv")
    });
    let seed_count: usize = args.get(3).and_then(|x| x.parse().ok()).unwrap_or(24);
    let seed_base: u64 = args.get(4).and_then(|x| x.parse().ok()).unwrap_or(2026131000);

    println!("Running mode: {} with {} seeds (seed_base={})", mode, seed_count, seed_base);
    let cases = match mode {
        "discovery" => build_discovery_params(seed_count, seed_base),
        "h1" => build_h1_params(seed_count, seed_base),
        "h2" => build_h2_params(seed_count, seed_base),
        "h3" => build_h3_params(seed_count, seed_base),
        "h4" => build_h4_params(seed_count, seed_base),
        "h5" => build_h5_params(seed_count, seed_base),
        _ => return Err(format!("Unknown mode {}", mode).into()),
    };

    println!("Total cases: {}", cases.len());
    let t0 = Instant::now();
    let results: Vec<TrajectoryResult> = cases.par_iter().cloned().map(run_trajectory).collect();
    let elapsed = t0.elapsed().as_secs_f64();
    println!("Finished {} cases in {:.2}s ({:.3}s/case)", results.len(), elapsed, elapsed / results.len() as f64);

    write_results(&out_path, &results)?;
    Ok(())
}
