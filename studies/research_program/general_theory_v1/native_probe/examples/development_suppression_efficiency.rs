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
    org_active: u8,
    rooted: f64,
    force: f64,
    foothold: f64,
    hazard: f64,
    insurgent_control: f64,
    government_control: f64,
    government_legitimacy: f64,
    political_access: f64,
    institution_capacity: f64,
    actions: f64,
    recruitment: f64,
    military_losses: f64,
    population: f64,
    displaced: f64,
    government_capital: f64,
}

#[derive(Default, Clone)]
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
    c.foreign_affairs.enabled = false;
    c.state_regeneration.enabled = true;
    c.state_regeneration.underground_disruption_rate = 0.0;
    c.organization_ecology.collapse_requires_fielded_exhaustion = true;
    c.recruitment_rate *= 0.0625;
    c
}

fn modes() -> &'static [&'static str] {
    &[
        "equal_locality",
        "threat_weighted",
        "need_weighted",
        "marginal_return",
    ]
}

fn multipliers() -> &'static [f64] {
    &[1.0, 2.0, 5.0, 10.0, 20.0]
}

fn snapshot(engine: &SimulationEngine) -> Snapshot {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let owner_active = p
        .organizations
        .active
        .get(INSURGENT)
        .copied()
        .unwrap_or(0);

    let rooted = if owner_active != 0 {
        (0..p.people.organization.len())
            .filter(|&person| p.people.organization[person] as usize == INSURGENT)
            .map(|person| {
                p.people.represented_population[person].max(0.0)
                    * p.people.armed_fraction[person].clamp(0.0, 1.0)
            })
            .sum()
    } else {
        0.0
    };

    let force = if owner_active != 0 {
        (0..p.formations.personnel.len())
            .filter(|&f| {
                p.formations.organization[f] as usize == INSURGENT
                    && p.formations.active[f] != 0
                    && p.formations.operational_status[f] == 1
                    && p.formations.outside_pineland[f] == 0
                    && p.formations.personnel[f] > 0.0
            })
            .map(|f| p.formations.personnel[f].max(0.0))
            .sum()
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
    let hazard = if owner_active != 0 {
        recruitment::recruitment_hazard_mass_by_locality(
            p,
            &engine.topology,
            &engine.config,
            INSURGENT,
        )
        .into_iter()
        .sum::<f64>()
    } else {
        0.0
    };

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

    let mut government_legitimacy = 0.0;
    let mut political_access = 0.0;
    let mut people_weight = 0.0;
    for person in 0..p.people.represented_population.len() {
        let w = p.people.represented_population[person].max(0.0);
        government_legitimacy += w * p.people.government_legitimacy[person];
        political_access += w * p.people.political_access[person];
        people_weight += w;
    }

    let military_losses = (0..p.formations.personnel.len())
        .filter(|&f| p.formations.organization[f] as usize == MILITARY)
        .map(|f| p.formations.cumulative_losses[f].max(0.0))
        .sum::<f64>();

    Snapshot {
        org_active: owner_active,
        rooted,
        force,
        foothold,
        hazard,
        insurgent_control: insurgent_control / population.max(1e-12),
        government_control: gc / population.max(1e-12),
        government_legitimacy: government_legitimacy / people_weight.max(1e-12),
        political_access: political_access / people_weight.max(1e-12),
        institution_capacity: ic / iw.max(1e-12),
        actions,
        recruitment: p.counters.recruitment,
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
    // The primary denominator for this assay is nominal public-development
    // spending, which is exactly 90% of gross political-order outflow under
    // the frozen policy mix.  The original audit runner advanced one event at
    // a time merely to observe those sparse political events; that is exact
    // but needlessly expensive.  Here we batch all already-scheduled events
    // before the next political event, then single-step that political event
    // itself.  Recomputing the queue after every batch keeps this exact even
    // when processed events schedule additional work before the target time.
    //
    // Gross all-event inflow/outflow are intentionally left NaN in this fast
    // path rather than pretending a net capital change is a gross ledger.
    // They are secondary diagnostics and can be recovered later for selected
    // cells with the slower forensic ledger.  Political outflow, the cost
    // denominator used by the preregistered ROI analysis, remains exact.
    let mut l = Ledger {
        inflow: f64::NAN,
        total_outflow: f64::NAN,
        political_outflow: 0.0,
    };
    loop {
        let scheduled = engine.particle.scheduler.events_sorted();
        let target = scheduled
            .iter()
            .enumerate()
            .find(|(_, event)| {
                event.time <= until + 1.0e-12 && event.payload.kind() == "political_order"
            })
            .map(|(index, event)| (index, event.time));
        drop(scheduled);

        let Some((events_before, target_time)) = target else {
            engine.advance_until(until).map_err(|e| e.to_string())?;
            break;
        };

        if events_before > 0 {
            let processed = engine
                .advance_until_limited(target_time, Some(events_before))
                .map_err(|e| e.to_string())?;
            if processed == 0 {
                return Err(format!(
                    "development ledger made no progress before political event at {target_time}"
                ));
            }
            continue;
        }

        let Some(next) = engine.particle.scheduler.peek() else {
            return Err("development ledger lost scheduled political event".to_string());
        };
        if next.payload.kind() != "political_order" || (next.time - target_time).abs() > 1.0e-9 {
            // Defensive fallback if heap ordering differs from the sorted
            // diagnostic view.  Consume one event and recompute rather than
            // assuming an ordering that could perturb the scientific state.
            if engine
                .advance_until_limited(target_time, Some(1))
                .map_err(|e| e.to_string())?
                == 0
            {
                return Err("development ledger heap-order fallback made no progress".to_string());
            }
            continue;
        }

        let before = engine.particle.organizations.capital[GOVERNMENT];
        if engine
            .advance_until_limited(target_time, Some(1))
            .map_err(|e| e.to_string())?
            != 1
        {
            return Err(format!(
                "development ledger failed to process political event at {target_time}"
            ));
        }
        let after = engine.particle.organizations.capital[GOVERNMENT];
        l.political_outflow += (before - after).max(0.0);
    }
    Ok(l)
}

fn row(
    seed: u64,
    mode: &str,
    multiplier: f64,
    timepoint: &str,
    time: f64,
    s: &Snapshot,
    anchor: &Snapshot,
    ledger: &Ledger,
) -> String {
    vec![
        seed.to_string(),
        mode.to_string(),
        format!("{multiplier:.6}"),
        timepoint.to_string(),
        format!("{time:.6}"),
        s.org_active.to_string(),
        format!("{:.17}", s.rooted),
        format!("{:.17}", s.force),
        format!("{:.17}", s.foothold),
        format!("{:.17}", s.hazard),
        format!("{:.17}", s.recruitment - anchor.recruitment),
        format!("{:.17}", s.actions - anchor.actions),
        format!("{:.17}", s.insurgent_control),
        format!("{:.17}", s.government_control),
        format!("{:.17}", s.government_legitimacy),
        format!("{:.17}", s.political_access),
        format!("{:.17}", s.institution_capacity),
        format!("{:.17}", s.military_losses - anchor.military_losses),
        format!("{:.17}", (anchor.population - s.population).max(0.0)),
        format!("{:.17}", s.displaced / anchor.population.max(1e-12)),
        format!("{:.17}", s.government_capital),
        format!("{:.17}", ledger.inflow),
        format!("{:.17}", ledger.total_outflow),
        format!("{:.17}", ledger.political_outflow),
        format!("{:.17}", ledger.political_outflow * 0.90),
    ]
    .join(",")
}

fn run_case(
    seed: u64,
    anchor_engine: &SimulationEngine,
    mode: &str,
    multiplier: f64,
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
    engine.config.political_order.federal_policy_budget *= multiplier;

    let ledger = advance_ledger(&mut engine, intervention_end)?;
    let end = snapshot(&engine);

    engine.config = baseline;
    engine.advance_until(final_day).map_err(|e| e.to_string())?;
    let final_s = snapshot(&engine);

    Ok(vec![
        row(
            seed,
            mode,
            multiplier,
            "anchor",
            anchor_engine.particle.time,
            &anchor,
            &anchor,
            &Ledger::default(),
        ),
        row(
            seed,
            mode,
            multiplier,
            "intervention_end",
            intervention_end,
            &end,
            &anchor,
            &ledger,
        ),
        row(
            seed,
            mode,
            multiplier,
            "final",
            final_day,
            &final_s,
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
        .unwrap_or_else(|| "../development_suppression_efficiency_v1.csv".to_string());
    let seeds: usize = arg(&args, 2, 12);
    let agents: usize = arg(&args, 3, 300);
    let localities: usize = arg(&args, 4, 34);
    let threads: usize = arg(&args, 5, 8);
    let seed_base: u64 = arg(&args, 6, 2026148000u64);
    let anchor_day: f64 = arg(&args, 7, 60.0);
    let intervention_end: f64 = arg(&args, 8, 180.0);
    let final_day: f64 = arg(&args, 9, 270.0);

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
    let mut anchors_ok = Vec::with_capacity(seeds);
    for result in anchors {
        anchors_ok.push(result.map_err(std::io::Error::other)?);
    }
    anchors_ok.sort_by_key(|(seed, _)| *seed);

    let tasks = anchors_ok
        .iter()
        .flat_map(|(seed, engine)| {
            modes().iter().flat_map(move |mode| {
                multipliers()
                    .iter()
                    .map(move |multiplier| (*seed, engine, *mode, *multiplier))
            })
        })
        .collect::<Vec<_>>();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(seed, engine, mode, multiplier)| {
                run_case(
                    *seed,
                    engine,
                    mode,
                    *multiplier,
                    intervention_end,
                    final_day,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,allocation_mode,budget_multiplier,timepoint,time,canonical_insurgent_active,rooted_armed_membership_mass,active_owner_fielded_force_personnel,foothold_strength_sum,recruitment_hazard_mass,cumulative_recruitment_since_anchor,cumulative_insurgent_actions_since_anchor,population_weighted_insurgent_control,population_weighted_government_control,mean_government_legitimacy,mean_political_access,mean_local_institution_capacity,government_military_losses_since_anchor,population_loss_since_anchor,displaced_population_fraction,government_capital,government_capital_inflow_intervention,total_government_outflow_intervention,political_order_outflow_intervention,public_development_outflow_intervention")?;
    for result in results {
        for line in result.map_err(std::io::Error::other)? {
            writeln!(writer, "{line}")?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} seeds={seeds} cells={} rows={}",
        modes().len() * multipliers().len(),
        seeds * modes().len() * multipliers().len() * 3
    );
    Ok(())
}
