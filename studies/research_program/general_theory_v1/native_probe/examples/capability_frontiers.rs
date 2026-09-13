use pineland_core::config::SimulationConfig;
use pineland_model::{recruitment, SimulationEngine, GOVERNMENT, INSURGENT, MILITARY};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

#[derive(Clone)]
struct Profile {
    id: String,
    benefit_id: String,
    burden_id: String,
    firepower: f64,
    protection: f64,
    supply_burden: f64,
    terrain_penalty: f64,
    air_intensity: f64,
    air_harm_multiplier: f64,
}

#[derive(Clone)]
struct Snapshot {
    rooted: f64,
    force: f64,
    foothold: f64,
    hazard: f64,
    insurgent_control: f64,
    government_control: f64,
    actions: f64,
    recruitment: f64,
    government_losses: f64,
    population: f64,
    displaced: f64,
    government_capital: f64,
    military_readiness: f64,
    military_supply_fraction: f64,
    contacts: u64,
}

#[derive(Default)]
struct Ledger {
    inflow: f64,
    outflow: f64,
    combat_event_outflow: f64,
}

fn arg<T: std::str::FromStr>(args: &[String], index: usize, default: T) -> T {
    args.get(index)
        .and_then(|v| v.parse::<T>().ok())
        .unwrap_or(default)
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
    c.foreign_affairs.enabled = false;
    c.recruitment_rate *= challenge_recruitment_multiplier.max(0.0);
    c.state_regeneration.underground_disruption_rate *= challenge_disruption_multiplier.max(0.0);
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
    c
}

fn equipment_profiles() -> Vec<Profile> {
    let benefits = [
        ("B0", 1.0, 1.0),
        ("B1", 1.15, 1.10),
        ("B2", 1.30, 1.20),
        ("B3", 1.50, 1.30),
    ];
    let burdens = [
        ("C0", 1.0, 0.0),
        ("C1", 1.20, 0.10),
        ("C2", 1.50, 0.25),
        ("C3", 2.0, 0.50),
    ];
    let mut profiles = Vec::new();
    for (bid, firepower, protection) in benefits {
        for (cid, supply_burden, terrain_penalty) in burdens {
            profiles.push(Profile {
                id: format!("{bid}{cid}"),
                benefit_id: bid.to_string(),
                burden_id: cid.to_string(),
                firepower,
                protection,
                supply_burden,
                terrain_penalty,
                air_intensity: 0.0,
                air_harm_multiplier: 0.0,
            });
        }
    }
    profiles
}

fn air_profiles() -> Vec<Profile> {
    let mut profiles = Vec::new();
    for intensity in [0.0, 0.25, 0.50, 0.75, 1.0] {
        for harm in [0.0, 0.50, 1.0] {
            profiles.push(Profile {
                id: format!("A{intensity:.2}_H{harm:.2}"),
                benefit_id: format!("A{intensity:.2}"),
                burden_id: format!("H{harm:.2}"),
                firepower: 1.0,
                protection: 1.0,
                supply_burden: 1.0,
                terrain_penalty: 0.0,
                air_intensity: intensity,
                air_harm_multiplier: harm,
            });
        }
    }
    profiles
}

fn apply_profile(engine: &mut SimulationEngine, profile: &Profile, experiment: &str) {
    engine.config.combat.government_firepower_multiplier = profile.firepower;
    engine.config.combat.government_protection_multiplier = profile.protection;
    engine.config.combat.government_supply_burden_multiplier = profile.supply_burden;
    engine.config.combat.government_terrain_mobility_penalty = profile.terrain_penalty;
    if experiment == "air" {
        engine.config.combat.government_air_support_intensity = profile.air_intensity;
        engine.config.combat.government_air_support_firepower_bonus = 0.50;
        engine.config.combat.government_air_support_cost_per_contact = 600.0;
        engine
            .config
            .combat
            .government_air_support_civilian_harm_multiplier = profile.air_harm_multiplier;
    }
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let insurgent_owner_active = p
        .organizations
        .active
        .get(INSURGENT)
        .copied()
        .unwrap_or(0)
        != 0;
    let mut rooted = 0.0;
    for person in 0..p.people.organization.len() {
        if p.people.organization[person] as usize == INSURGENT {
            rooted += p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].clamp(0.0, 1.0);
        }
    }
    let force = if insurgent_owner_active {
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
    let mut gc = 0.0;
    let mut ic = 0.0;
    for locality in 0..nloc {
        let w = p.locality.population[locality].max(0.0);
        gc += w * p.locality.effective_control(locality, 0);
        ic += w * p.locality.effective_control(locality, 1);
    }
    let mut gov_losses = 0.0;
    let mut readiness_num = 0.0;
    let mut supply_num = 0.0;
    let mut military_weight = 0.0;
    for f in 0..p.formations.personnel.len() {
        if p.formations.organization[f] as usize != MILITARY {
            continue;
        }
        let w = p.formations.personnel[f].max(0.0);
        gov_losses += p.formations.cumulative_losses[f].max(0.0);
        readiness_num += w * p.formations.effective_readiness(f);
        let supply_fraction = if p.formations.supply_capacity[f] > 1e-12 {
            (p.formations.supply_stock[f] / p.formations.supply_capacity[f]).clamp(0.0, 1.0)
        } else {
            0.0
        };
        supply_num += w * supply_fraction;
        military_weight += w;
    }
    Snapshot {
        rooted,
        force,
        foothold,
        hazard,
        insurgent_control: ic / population.max(1e-12),
        government_control: gc / population.max(1e-12),
        actions,
        recruitment: p.counters.recruitment,
        government_losses: gov_losses,
        population,
        displaced: p.locality.displaced_population.iter().copied().sum(),
        government_capital: p.organizations.capital[GOVERNMENT],
        military_readiness: readiness_num / military_weight.max(1e-12),
        military_supply_fraction: supply_num / military_weight.max(1e-12),
        contacts: p.counters.contacts,
    }
}

fn advance_ledger(engine: &mut SimulationEngine, until: f64) -> Result<Ledger, String> {
    let mut ledger = Ledger::default();
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
            ledger.inflow += delta;
        } else if delta < 0.0 {
            ledger.outflow += -delta;
            if matches!(kind.as_str(), "contact" | "organized_action") {
                ledger.combat_event_outflow += -delta;
            }
        }
    }
    if engine.particle.time < until {
        engine.advance_until(until).map_err(|e| e.to_string())?;
    }
    Ok(ledger)
}

fn row(
    seed: u64,
    experiment: &str,
    profile: &Profile,
    timepoint: &str,
    time: f64,
    s: &Snapshot,
    anchor: &Snapshot,
    ledger: &Ledger,
) -> String {
    vec![
        seed.to_string(),
        experiment.to_string(),
        profile.id.clone(),
        profile.benefit_id.clone(),
        profile.burden_id.clone(),
        format!("{:.17}", profile.firepower),
        format!("{:.17}", profile.protection),
        format!("{:.17}", profile.supply_burden),
        format!("{:.17}", profile.terrain_penalty),
        format!("{:.17}", profile.air_intensity),
        format!("{:.17}", profile.air_harm_multiplier),
        timepoint.to_string(),
        format!("{time:.6}"),
        format!("{:.17}", s.rooted),
        format!("{:.17}", s.force),
        format!("{:.17}", s.foothold),
        format!("{:.17}", s.hazard),
        format!("{:.17}", s.insurgent_control),
        format!("{:.17}", s.government_control),
        format!("{:.17}", s.actions - anchor.actions),
        format!("{:.17}", s.recruitment - anchor.recruitment),
        format!("{:.17}", s.government_losses - anchor.government_losses),
        format!("{:.17}", (anchor.population - s.population).max(0.0)),
        format!("{:.17}", s.displaced / anchor.population.max(1e-12)),
        format!("{:.17}", s.government_capital),
        format!("{:.17}", s.military_readiness),
        format!("{:.17}", s.military_supply_fraction),
        (s.contacts.saturating_sub(anchor.contacts)).to_string(),
        format!("{:.17}", ledger.inflow),
        format!("{:.17}", ledger.outflow),
        format!("{:.17}", ledger.combat_event_outflow),
    ]
    .join(",")
}

fn run_case(
    seed: u64,
    anchor_engine: &SimulationEngine,
    experiment: &str,
    profile: &Profile,
    intervention_end: f64,
    final_day: f64,
) -> Result<Vec<String>, String> {
    let mut e = anchor_engine.clone();
    let baseline = e.config.clone();
    let anchor = snapshot(&e);
    apply_profile(&mut e, profile, experiment);
    // Equipment profiles have no calibrated capital-cost denominator in the
    // frozen contract; their declared burdens are supply demand, terrain
    // mobility, readiness and government losses.  Single-stepping every event
    // solely to reconstruct gross capital flow therefore adds large forensic
    // overhead without contributing to the equipment analysis.  Preserve the
    // exact simulation path by using the normal batched advance and leave the
    // unused capital-flow ledger at zero.  Air-support profiles retain the
    // event-level ledger because support cost is a primary outcome there.
    let ledger = if experiment == "equipment" {
        e.advance_until(intervention_end).map_err(|x| x.to_string())?;
        Ledger::default()
    } else {
        advance_ledger(&mut e, intervention_end)?
    };
    let end = snapshot(&e);
    e.config = baseline;
    e.advance_until(final_day).map_err(|x| x.to_string())?;
    let final_s = snapshot(&e);
    Ok(vec![
        row(
            seed,
            experiment,
            profile,
            "anchor",
            anchor_engine.particle.time,
            &anchor,
            &anchor,
            &Ledger::default(),
        ),
        row(
            seed,
            experiment,
            profile,
            "intervention_end",
            intervention_end,
            &end,
            &anchor,
            &ledger,
        ),
        row(
            seed, experiment, profile, "final", final_day, &final_s, &anchor, &ledger,
        ),
    ])
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    let experiment = args.get(1).map(String::as_str).unwrap_or("equipment");
    if !matches!(experiment, "equipment" | "air") {
        return Err("first argument must be equipment or air".into());
    }
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| format!("../{experiment}_frontier.csv"));
    let seeds: usize = arg(&args, 3, 12);
    let agents: usize = arg(&args, 4, 300);
    let localities: usize = arg(&args, 5, 34);
    let threads: usize = arg(&args, 6, 12);
    let default_seed = if experiment == "equipment" {
        2026122000u64
    } else {
        2026123000u64
    };
    let seed_base: u64 = arg(&args, 7, default_seed);
    let anchor_day: f64 = arg(&args, 8, 60.0);
    let intervention_end: f64 = arg(&args, 9, 240.0);
    let final_day: f64 = arg(&args, 10, 360.0);
    let challenge_recruitment_multiplier: f64 = arg(&args, 11, 1.0);
    let challenge_disruption_multiplier: f64 = arg(&args, 12, 1.0);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let profiles = if experiment == "equipment" {
        equipment_profiles()
    } else {
        air_profiles()
    };
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let anchors: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|s| {
                let seed = seed_base + s as u64;
                let mut e = SimulationEngine::new(config(
                    seed,
                    agents,
                    localities,
                    final_day,
                    challenge_recruitment_multiplier,
                    challenge_disruption_multiplier,
                ))
                .map_err(|x| x.to_string())?;
                e.particle_execution = true;
                e.advance_until(anchor_day).map_err(|x| x.to_string())?;
                Ok((seed, e))
            })
            .collect()
    });
    let mut anchors_ok = Vec::with_capacity(seeds);
    for r in anchors {
        anchors_ok.push(r.map_err(std::io::Error::other)?);
    }
    let tasks = anchors_ok
        .iter()
        .flat_map(|(seed, engine)| profiles.iter().map(move |p| (*seed, engine, p)))
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, profile)| {
                run_case(
                    *seed,
                    engine,
                    experiment,
                    profile,
                    intervention_end,
                    final_day,
                )
            })
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,experiment,profile,benefit_id,burden_id,firepower_multiplier,protection_multiplier,supply_burden_multiplier,terrain_mobility_penalty,air_support_intensity,air_harm_multiplier,timepoint,time,rooted_armed_membership_mass,fielded_force_personnel,foothold_strength_sum,recruitment_hazard_mass,population_weighted_insurgent_control,population_weighted_government_control,cumulative_insurgent_actions_since_anchor,cumulative_recruitment_since_anchor,government_military_losses_since_anchor,population_loss_since_anchor,displaced_population_fraction,government_capital,mean_military_readiness,mean_military_supply_fraction,contacts_since_anchor,government_capital_inflow_intervention,government_capital_outflow_intervention,combat_event_outflow_intervention")?;
    for result in results {
        for r in result.map_err(std::io::Error::other)? {
            writeln!(w, "{r}")?;
        }
    }
    w.flush()?;
    println!(
        "wrote {out} experiment={experiment} seeds={seeds} profiles={} rows={} challenge_recruitment_multiplier={challenge_recruitment_multiplier:.6} challenge_disruption_multiplier={challenge_disruption_multiplier:.6}",
        profiles.len(),
        seeds * profiles.len() * 3
    );
    Ok(())
}
