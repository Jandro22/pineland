use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, GOVERNMENT, INSURGENT, MILITARY};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone, Debug, Default)]
struct GovernmentLedger {
    inflow: f64,
    outflow: f64,
    political_order_outflow: f64,
    governance_outflow: f64,
    state_regeneration_outflow: f64,
    other_outflow: f64,
}

#[derive(Clone, Debug)]
struct Snapshot {
    rooted_armed_membership_mass: f64,
    fielded_force_personnel: f64,
    foothold_strength_sum: f64,
    recruitment_hazard_mass: f64,
    population_weighted_insurgent_control: f64,
    population_weighted_government_control: f64,
    cumulative_insurgent_actions: f64,
    mean_government_legitimacy: f64,
    mean_state_legitimacy: f64,
    mean_local_institution_capacity: f64,
    government_military_losses: f64,
    population_total: f64,
    displaced_population: f64,
    government_capital: f64,
    canonical_insurgent_active: usize,
    canonical_insurgent_capital: f64,
    ecosystem_rooted_membership: f64,
    ecosystem_operational_force: f64,
    ecosystem_recruitment_hazard: f64,
    active_insurgent_organizations: usize,
}

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
    challenge_recruitment_multiplier: f64,
    challenge_disruption_multiplier: f64,
) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.state_regeneration.enabled = true;
    // Phase A isolates domestic government strategy.
    c.foreign_affairs.enabled = false;
    // Optional challenge-support modifiers are environmental conditions, not
    // strategy levers. Defaults are exactly 1x/1x, preserving Phase A.
    c.recruitment_rate *= challenge_recruitment_multiplier;
    c.state_regeneration.underground_disruption_rate *= challenge_disruption_multiplier;
    c
}

fn strategy_ids() -> &'static [&'static str] {
    &[
        "baseline",
        "clean_governance",
        "spending_surge",
        "clean_spending_surge",
        "security_expansion",
        "police_first",
        "military_first",
        "admin_first",
        "integrated",
        "patronage_heavy",
    ]
}

fn selected_strategy_ids(profile: &str) -> Result<Vec<&'static str>, String> {
    match profile {
        "full" => Ok(strategy_ids().to_vec()),
        "baseline_only" => Ok(vec!["baseline"]),
        _ => Err(format!(
            "unknown strategy profile {profile}; expected full or baseline_only"
        )),
    }
}

fn apply_strategy(engine: &mut SimulationEngine, strategy: &str) -> Result<(), String> {
    let c = &mut engine.config;
    match strategy {
        "baseline" => {}
        "clean_governance" => {
            c.political_order.public_budget_share = 0.88;
            c.political_order.patronage_share = 0.10;
            c.political_order.private_diversion_share = 0.02;
        }
        "spending_surge" => {
            c.political_order.federal_policy_budget *= 2.0;
        }
        "clean_spending_surge" => {
            c.political_order.federal_policy_budget *= 2.0;
            c.political_order.public_budget_share = 0.88;
            c.political_order.patronage_share = 0.10;
            c.political_order.private_diversion_share = 0.02;
        }
        "security_expansion" => {
            c.state_regeneration.security_recruitment_rate *= 2.0;
            c.state_regeneration.security_training_rate *= 2.0;
            c.state_regeneration.military_target_multiplier *= 1.25;
        }
        "police_first" => {
            c.state_regeneration.security_recruitment_rate *= 2.0;
            c.state_regeneration.security_training_rate *= 2.0;
            c.state_regeneration.police_allocation_share = 0.85;
            c.state_regeneration.police_target_population_fraction *= 1.5;
        }
        "military_first" => {
            c.state_regeneration.security_recruitment_rate *= 2.0;
            c.state_regeneration.security_training_rate *= 2.0;
            c.state_regeneration.police_allocation_share = 0.20;
            c.state_regeneration.military_target_multiplier *= 1.5;
        }
        "admin_first" => {
            c.state_regeneration.administrative_rebuild_rate *= 2.0;
            c.political_order.public_budget_share = 0.80;
            c.political_order.patronage_share = 0.15;
            c.political_order.private_diversion_share = 0.05;
        }
        "integrated" => {
            c.political_order.federal_policy_budget *= 1.5;
            c.political_order.public_budget_share = 0.82;
            c.political_order.patronage_share = 0.13;
            c.political_order.private_diversion_share = 0.05;
            c.state_regeneration.security_recruitment_rate *= 1.5;
            c.state_regeneration.security_training_rate *= 1.5;
            c.state_regeneration.police_allocation_share = 0.65;
            c.state_regeneration.police_target_population_fraction *= 1.25;
            c.state_regeneration.military_target_multiplier *= 1.15;
            c.state_regeneration.administrative_rebuild_rate *= 1.5;
        }
        "patronage_heavy" => {
            c.political_order.public_budget_share = 0.40;
            c.political_order.patronage_share = 0.40;
            c.political_order.private_diversion_share = 0.20;
        }
        _ => return Err(format!("unknown strategy {strategy}")),
    }
    Ok(())
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let mut rooted = 0.0;
    let mut gov_leg_num = 0.0;
    let mut state_leg_num = 0.0;
    let mut people_weight = 0.0;
    for person in 0..p.people.organization.len() {
        let w = p.people.represented_population[person].max(0.0);
        if p.people.organization[person] as usize == INSURGENT {
            rooted += w * p.people.armed_fraction[person].clamp(0.0, 1.0);
        }
        gov_leg_num += w * p.people.government_legitimacy[person];
        state_leg_num += w * p.people.state_legitimacy[person];
        people_weight += w;
    }

    // Canonical fielded-force outcomes must obey the same active-owner
    // semantics used by the live-insurgency closure recertification.  Logistics
    // can restore operational_status on retained formation records after the
    // owning organization has become inactive; those records are not a live
    // canonical insurgent force and must not enter policy outcomes.
    let fielded = if p
        .organizations
        .active
        .get(INSURGENT)
        .copied()
        .unwrap_or(0)
        != 0
    {
        (0..p.formations.personnel.len())
            .filter(|&f| {
                p.formations.organization[f] as usize == INSURGENT
                    && p.formations.active[f] != 0
                    && p.formations.operational_status[f] == 1
                    && p.formations.outside_pineland[f] == 0
            })
            .map(|f| p.formations.personnel[f].max(0.0))
            .sum::<f64>()
    } else {
        0.0
    };

    let mut foothold_strength = 0.0;
    let mut actions = 0.0;
    for locality in 0..nloc {
        let index = INSURGENT * nloc + locality;
        if index < p.footholds.strength.len() {
            foothold_strength += p.footholds.strength[index].max(0.0);
            actions += p.footholds.cumulative_actions[index].max(0.0);
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

    let pop_total = p.locality.population.iter().copied().sum::<f64>();
    let mut gov_control = 0.0;
    let mut ins_control = 0.0;
    let mut inst_capacity = 0.0;
    let mut inst_weight = 0.0;
    let local_inst_start = 6 + engine.topology.district_count();
    for locality in 0..nloc {
        let w = p.locality.population[locality].max(0.0);
        gov_control += w * p.locality.effective_control(locality, 0);
        ins_control += w * p.locality.effective_control(locality, 1);
        let institution = local_inst_start + locality;
        if institution < p.political.institution_capacity.len() {
            inst_capacity += w * p.political.institution_capacity[institution];
            inst_weight += w;
        }
    }

    let gov_losses = (0..p.formations.personnel.len())
        .filter(|&f| p.formations.organization[f] as usize == MILITARY)
        .map(|f| p.formations.cumulative_losses[f].max(0.0))
        .sum::<f64>();
    let displaced = p
        .locality
        .displaced_population
        .iter()
        .copied()
        .map(|v| v.max(0.0))
        .sum::<f64>();

    let insurgent_organizations = (0..p.organizations.kind.len())
        .filter(|&organization| {
            p.organizations.kind[organization] == 3 && p.organizations.active[organization] != 0
        })
        .collect::<Vec<_>>();
    let ecosystem_rooted_membership = (0..p.people.organization.len())
        .filter_map(|person| {
            let organization = p.people.organization[person] as usize;
            (organization < p.organizations.kind.len()
                && p.organizations.kind[organization] == 3
                && p.organizations.active[organization] != 0)
                .then_some(
                    p.people.represented_population[person].max(0.0)
                        * p.people.armed_fraction[person].clamp(0.0, 1.0),
                )
        })
        .sum::<f64>();
    let ecosystem_operational_force = (0..p.formations.personnel.len())
        .filter_map(|formation| {
            let organization = p.formations.organization[formation] as usize;
            (organization < p.organizations.kind.len()
                && p.organizations.kind[organization] == 3
                && p.organizations.active[organization] != 0
                && p.formations.active[formation] != 0
                && p.formations.operational_status[formation] == 1
                && p.formations.outside_pineland[formation] == 0)
                .then_some(p.formations.personnel[formation].max(0.0))
        })
        .sum::<f64>();
    let ecosystem_recruitment_hazard = insurgent_organizations
        .iter()
        .map(|&organization| {
            recruitment::recruitment_hazard_mass_by_locality(
                p,
                &engine.topology,
                &engine.config,
                organization,
            )
            .into_iter()
            .sum::<f64>()
        })
        .sum::<f64>();

    Snapshot {
        rooted_armed_membership_mass: rooted,
        fielded_force_personnel: fielded,
        foothold_strength_sum: foothold_strength,
        recruitment_hazard_mass: hazard,
        population_weighted_insurgent_control: if pop_total > 0.0 {
            ins_control / pop_total
        } else {
            0.0
        },
        population_weighted_government_control: if pop_total > 0.0 {
            gov_control / pop_total
        } else {
            0.0
        },
        cumulative_insurgent_actions: actions,
        mean_government_legitimacy: gov_leg_num / people_weight.max(1e-12),
        mean_state_legitimacy: state_leg_num / people_weight.max(1e-12),
        mean_local_institution_capacity: inst_capacity / inst_weight.max(1e-12),
        government_military_losses: gov_losses,
        population_total: pop_total,
        displaced_population: displaced,
        government_capital: p.organizations.capital[GOVERNMENT],
        canonical_insurgent_active: usize::from(
            p.organizations
                .active
                .get(INSURGENT)
                .copied()
                .unwrap_or(0)
                != 0,
        ),
        canonical_insurgent_capital: p
            .organizations
            .capital
            .get(INSURGENT)
            .copied()
            .unwrap_or(0.0),
        ecosystem_rooted_membership,
        ecosystem_operational_force,
        ecosystem_recruitment_hazard,
        active_insurgent_organizations: insurgent_organizations.len(),
    }
}

fn advance_with_government_ledger(
    engine: &mut SimulationEngine,
    until: f64,
) -> Result<GovernmentLedger, String> {
    let mut ledger = GovernmentLedger::default();
    loop {
        let Some(event) = engine.particle.scheduler.peek() else {
            break;
        };
        if event.time > until {
            break;
        }
        let kind = event.payload.kind().to_string();
        let before = engine.particle.organizations.capital[GOVERNMENT];
        let processed = engine
            .advance_until_limited(until, Some(1))
            .map_err(|e| e.to_string())?;
        if processed == 0 {
            break;
        }
        let after = engine.particle.organizations.capital[GOVERNMENT];
        let delta = after - before;
        if delta > 0.0 {
            ledger.inflow += delta;
        } else if delta < 0.0 {
            let out = -delta;
            ledger.outflow += out;
            match kind.as_str() {
                "political_order" => ledger.political_order_outflow += out,
                "governance" => ledger.governance_outflow += out,
                "state_regeneration" => ledger.state_regeneration_outflow += out,
                _ => ledger.other_outflow += out,
            }
        }
    }
    if engine.particle.time < until {
        engine.advance_until(until).map_err(|e| e.to_string())?;
    }
    Ok(ledger)
}

fn snapshot_row(
    seed: u64,
    strategy: &str,
    timepoint: &str,
    time: f64,
    s: &Snapshot,
    anchor: &Snapshot,
    ledger: &GovernmentLedger,
) -> String {
    let actions_since_anchor = s.cumulative_insurgent_actions - anchor.cumulative_insurgent_actions;
    let losses_since_anchor = s.government_military_losses - anchor.government_military_losses;
    let population_loss = (anchor.population_total - s.population_total).max(0.0);
    let displaced_fraction = s.displaced_population / anchor.population_total.max(1e-12);
    format!(
        "{seed},{strategy},{timepoint},{time:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{},{:.17},{:.17},{:.17},{:.17},{}",
        s.rooted_armed_membership_mass,
        s.fielded_force_personnel,
        s.foothold_strength_sum,
        s.recruitment_hazard_mass,
        s.population_weighted_insurgent_control,
        s.population_weighted_government_control,
        actions_since_anchor,
        s.mean_government_legitimacy,
        s.mean_state_legitimacy,
        s.mean_local_institution_capacity,
        losses_since_anchor,
        population_loss,
        displaced_fraction,
        s.government_capital,
        ledger.inflow,
        ledger.outflow,
        ledger.political_order_outflow,
        ledger.governance_outflow,
        ledger.state_regeneration_outflow,
        ledger.other_outflow,
        s.canonical_insurgent_active,
        s.canonical_insurgent_capital,
        s.ecosystem_rooted_membership,
        s.ecosystem_operational_force,
        s.ecosystem_recruitment_hazard,
        s.active_insurgent_organizations,
    )
}

fn run_case(
    seed: u64,
    anchor_engine: &SimulationEngine,
    strategy: &str,
    intervention_end: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut engine = anchor_engine.clone();
    let baseline_config = engine.config.clone();
    let anchor = snapshot(&engine);
    apply_strategy(&mut engine, strategy)?;
    let ledger = advance_with_government_ledger(&mut engine, intervention_end)?;
    let intervention = snapshot(&engine);
    engine.config = baseline_config;
    engine.advance_until(final_day).map_err(|e| e.to_string())?;
    let final_snapshot = snapshot(&engine);
    Ok(vec![
        snapshot_row(
            seed,
            strategy,
            "anchor",
            anchor_engine.particle.time,
            &anchor,
            &anchor,
            &GovernmentLedger::default(),
        ),
        snapshot_row(
            seed,
            strategy,
            "intervention_end",
            intervention_end,
            &intervention,
            &anchor,
            &ledger,
        ),
        snapshot_row(
            seed,
            strategy,
            "final",
            final_day,
            &final_snapshot,
            &anchor,
            &ledger,
        ),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let out = args
        .get(1)
        .cloned()
        .unwrap_or_else(|| "../government_strategy_frontier_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 12);
    let seed_base: u64 = arg(&args, 6, 2026120000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let intervention_end: f64 = arg(&args, 8, 240.0);
    let final_day: f64 = arg(&args, 9, 360.0);
    let challenge_recruitment_multiplier: f64 = arg(&args, 10, 1.0);
    let challenge_disruption_multiplier: f64 = arg(&args, 11, 1.0);
    let strategy_profile = args.get(12).map(String::as_str).unwrap_or("full");
    let strategies = selected_strategy_ids(strategy_profile).map_err(std::io::Error::other)?;
    ensure_parent(&out)?;

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let anchors: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|s| {
                let seed = seed_base + s as u64;
                let mut engine = SimulationEngine::new(config(
                    seed,
                    agents,
                    localities,
                    final_day,
                    challenge_recruitment_multiplier,
                    challenge_disruption_multiplier,
                ))
                .map_err(|e| e.to_string())?;
                engine.particle_execution = true;
                engine
                    .advance_until(anchor_day)
                    .map_err(|e| e.to_string())?;
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
            strategies
                .iter()
                .map(move |strategy| (*seed, engine, *strategy))
        })
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, strategy)| {
                run_case(*seed, engine, strategy, intervention_end, final_day)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,strategy,timepoint,time,rooted_armed_membership_mass,fielded_force_personnel,foothold_strength_sum,recruitment_hazard_mass,population_weighted_insurgent_control,population_weighted_government_control,cumulative_insurgent_actions_since_anchor,mean_government_legitimacy,mean_state_legitimacy,mean_local_institution_capacity,government_military_losses_since_anchor,population_loss_since_anchor,displaced_population_fraction,government_capital,government_capital_inflow_intervention,government_capital_outflow_intervention,political_order_outflow_intervention,governance_outflow_intervention,state_regeneration_outflow_intervention,other_outflow_intervention,canonical_insurgent_active,canonical_insurgent_capital,ecosystem_rooted_membership,ecosystem_operational_force,ecosystem_recruitment_hazard,active_insurgent_organizations")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} seeds={seeds} strategies={} rows={} challenge_recruitment_multiplier={challenge_recruitment_multiplier:.6} challenge_disruption_multiplier={challenge_disruption_multiplier:.6} strategy_profile={strategy_profile}",
        strategies.len(),
        seeds * strategies.len() * 3
    );
    Ok(())
}
