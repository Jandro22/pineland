use pineland_core::config::SimulationConfig;
use pineland_core::rng::PyRandomCompat;
use pineland_core::state::{clamp01, CONTROL_DIMENSIONS};
use pineland_model::{
    combat, state_regeneration, SimulationEngine, GOVERNMENT, INSURGENT, MILITARY, POLICE,
};
use rayon::prelude::*;
use std::env;
use std::error::Error;
use std::fs::{create_dir_all, File};
use std::io::{BufWriter, Write};
use std::path::Path;

const NONE_ORG: u32 = u32::MAX;

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

fn synthetic_v2_config(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c.state_regeneration.enabled = true;
    c
}

fn local_state_institution(engine: &SimulationEngine, locality: usize) -> Option<usize> {
    let index = 6 + engine.topology.district_count() + locality;
    (index < engine.particle.political.institution_capacity.len()).then_some(index)
}

fn neutralize_insurgent(engine: &mut SimulationEngine) {
    let p = &mut engine.particle;
    let nloc = engine.topology.locality_count();
    let org_count = p.organizations.kind.len();

    for person in 0..p.people.organization.len() {
        if p.people.organization[person] as usize == INSURGENT {
            p.people.organization[person] = NONE_ORG;
            p.people.armed_fraction[person] = 0.0;
        }
        if matches!(p.people.public_behavior[person], 1 | 2) {
            p.people.public_behavior[person] = 0;
        }
        if org_count > INSURGENT && p.people.social_exposure.len() >= (person + 1) * org_count {
            p.people.social_exposure[person * org_count + INSURGENT] = 0.0;
        }
    }
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize == INSURGENT {
            p.formations.personnel[formation] = 0.0;
            p.formations.supply_stock[formation] = 0.0;
            p.formations.active[formation] = 0;
            p.formations.operational_status[formation] = 0;
            p.formations.moving[formation] = 0;
            p.formations.outside_pineland[formation] = 0;
        }
    }
    for index in 0..p.manpower.pool.len() {
        if p.manpower.organization[index] as usize == INSURGENT {
            p.manpower.pool[index] = 0.0;
            p.manpower.supply_reserve[index] = 0.0;
        }
    }
    for index in 0..p.logistics.source_stock.len() {
        if p.logistics.organization[index] as usize == INSURGENT {
            p.logistics.source_stock[index] = 0.0;
            p.logistics.source_capacity[index] = 0.0;
            p.logistics.source_production[index] = 0.0;
        }
    }
    for locality in 0..nloc {
        let offset = locality * CONTROL_DIMENSIONS;
        if p.locality.insurgent_control.len() >= offset + CONTROL_DIMENSIONS {
            p.locality.insurgent_control[offset..offset + CONTROL_DIMENSIONS].fill(0.0);
        }
        if locality < p.locality.insurgent_governance.len() {
            p.locality.insurgent_governance[locality] = 0.0;
        }
        if org_count > INSURGENT {
            let org_offset = (locality * org_count + INSURGENT) * CONTROL_DIMENSIONS;
            if p.locality.organization_control.len() >= org_offset + CONTROL_DIMENSIONS {
                p.locality.organization_control[org_offset..org_offset + CONTROL_DIMENSIONS]
                    .fill(0.0);
            }
        }
        let foothold = INSURGENT * nloc + locality;
        if foothold < p.footholds.strength.len() {
            p.footholds.strength[foothold] = 0.0;
            p.footholds.raw_signal[foothold] = 0.0;
            p.footholds.membership[foothold] = 0.0;
            p.footholds.embeddedness[foothold] = 0.0;
            p.footholds.access[foothold] = 0.0;
            p.footholds.target_knowledge[foothold] = 0.0;
            p.footholds.infrastructure[foothold] = 0.0;
            p.footholds.sustainment[foothold] = 0.0;
        }
    }
    for status in &mut p.protos.status {
        *status = 3;
    }
    if INSURGENT < p.organizations.active.len() {
        p.organizations.active[INSURGENT] = 0;
        p.organizations.member_population[INSURGENT] = 0.0;
        p.organizations.external_support[INSURGENT] = 0.0;
        p.organizations.external_sanctuary[INSURGENT] = 0.0;
    }
}

fn evenly_spaced_capacity_focals(engine: &SimulationEngine, count: usize) -> Vec<usize> {
    let mut ranked = (0..engine.topology.locality_count())
        .filter_map(|locality| {
            local_state_institution(engine, locality).map(|institution| {
                (
                    locality,
                    engine.particle.political.institution_capacity[institution],
                )
            })
        })
        .collect::<Vec<_>>();
    ranked.sort_by(|a, b| a.1.total_cmp(&b.1).then_with(|| a.0.cmp(&b.0)));
    let take = count.min(ranked.len());
    if take == 0 {
        return Vec::new();
    }
    if take == 1 {
        return vec![ranked[ranked.len() / 2].0];
    }
    let mut selected = Vec::with_capacity(take);
    for k in 0..take {
        let rank = ((k as f64) * (ranked.len() - 1) as f64 / (take - 1) as f64).round() as usize;
        let locality = ranked[rank.min(ranked.len() - 1)].0;
        if !selected.contains(&locality) {
            selected.push(locality);
        }
    }
    selected
}

fn weighted_police_professionalism(engine: &SimulationEngine, locality: usize) -> f64 {
    let mut num = 0.0;
    let mut den = 0.0;
    for post in 0..engine.particle.security_posts.personnel.len() {
        if engine.particle.security_posts.organization[post] as usize != POLICE
            || engine.particle.security_posts.locality[post] as usize != locality
        {
            continue;
        }
        let w = engine.particle.security_posts.personnel[post].max(0.0);
        num += w * engine.particle.security_posts.professionalism[post];
        den += w;
    }
    if den > 1e-12 {
        num / den
    } else {
        0.0
    }
}

fn local_police_personnel(engine: &SimulationEngine, locality: usize) -> f64 {
    (0..engine.particle.security_posts.personnel.len())
        .filter(|post| {
            engine.particle.security_posts.organization[*post] as usize == POLICE
                && engine.particle.security_posts.locality[*post] as usize == locality
                && engine.particle.security_posts.staffed[*post] != 0
        })
        .map(|post| engine.particle.security_posts.personnel[post].max(0.0))
        .sum()
}

fn local_military_personnel(engine: &SimulationEngine, locality: usize) -> f64 {
    (0..engine.particle.formations.personnel.len())
        .filter(|formation| {
            engine.particle.formations.organization[*formation] as usize == MILITARY
                && engine.particle.formations.locality[*formation] as usize == locality
                && engine.particle.formations.outside_pineland[*formation] == 0
        })
        .map(|formation| engine.particle.formations.personnel[formation].max(0.0))
        .sum()
}

fn weighted_military_experience(engine: &SimulationEngine, locality: usize) -> f64 {
    let mut num = 0.0;
    let mut den = 0.0;
    for f in 0..engine.particle.formations.personnel.len() {
        if engine.particle.formations.organization[f] as usize != MILITARY
            || engine.particle.formations.locality[f] as usize != locality
        {
            continue;
        }
        let w = engine.particle.formations.personnel[f].max(0.0);
        num += w * engine.particle.formations.experience[f];
        den += w;
    }
    if den > 1e-12 {
        num / den
    } else {
        0.0
    }
}

fn state_v2_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    step: f64,
    focal: usize,
    capital_mult: f64,
    shock_fraction: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_v2_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.enabled = false;
    let mut engine = SimulationEngine::new(config).map_err(|e| e.to_string())?;
    neutralize_insurgent(&mut engine);
    let institution = local_state_institution(&engine, focal)
        .ok_or_else(|| format!("missing local institution {focal}"))?;
    let base_capital = engine.particle.organizations.capital[GOVERNMENT];
    engine.particle.organizations.capital[GOVERNMENT] = (base_capital * capital_mult).max(0.0);
    let baseline_capacity = engine.particle.political.institution_capacity[institution];
    let baseline_control = engine.particle.locality.effective_control(focal, 0);
    let baseline_admin = engine.particle.locality.administrative_capacity[focal];
    engine.particle.political.institution_capacity[institution] =
        (baseline_capacity * shock_fraction).clamp(0.0, 1.0);
    engine.particle.locality.administrative_capacity[focal] =
        (baseline_admin * shock_fraction).clamp(0.0, 1.0);

    // Shock the persistent security stocks as well as downstream control.
    // Without a personnel vacancy the regeneration pipeline has nothing to
    // refill, so an output-only shock cannot identify the replacement loop.
    for post in 0..engine.particle.security_posts.personnel.len() {
        if engine.particle.security_posts.locality[post] as usize == focal
            && engine.particle.security_posts.organization[post] as usize == POLICE
        {
            engine.particle.security_posts.personnel[post] *= shock_fraction;
            engine.particle.security_posts.presence[post] =
                clamp01(engine.particle.security_posts.personnel[post] / 250.0);
            engine.particle.security_posts.staffed[post] =
                u8::from(engine.particle.security_posts.personnel[post] > 0.0);
        }
    }
    for formation in 0..engine.particle.formations.personnel.len() {
        if engine.particle.formations.organization[formation] as usize == MILITARY
            && engine.particle.formations.locality[formation] as usize == focal
        {
            engine.particle.formations.personnel[formation] *= shock_fraction;
            engine.particle.formations.supply_stock[formation] *= shock_fraction;
            engine.particle.formations.supply_capacity[formation] *= shock_fraction;
        }
    }
    let offset = focal * CONTROL_DIMENSIONS;
    for dimension in [2usize, 3, 5, 6] {
        engine.particle.locality.government_control[offset + dimension] =
            (engine.particle.locality.government_control[offset + dimension] * shock_fraction)
                .clamp(0.0, 1.0);
    }

    let mut rows = Vec::new();
    let mut t = 0.0;
    loop {
        let p = &engine.particle;
        rows.push(format!(
            "{seed},{focal},{capital_mult:.17},{shock_fraction:.17},{base_capital:.17},{baseline_capacity:.17},{baseline_control:.17},{baseline_admin:.17},{t:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            p.political.institution_capacity[institution],
            p.political.institution_reach[institution],
            p.political.institution_integrity[institution],
            p.political.institution_compliance[institution],
            p.locality.effective_control(focal, 0),
            p.locality.government_control[offset],
            p.locality.government_control[offset + 1],
            p.locality.government_control[offset + 2],
            p.locality.government_control[offset + 3],
            p.locality.government_control[offset + 4],
            p.locality.government_control[offset + 5],
            p.locality.government_control[offset + 6],
            p.locality.administrative_capacity[focal],
            p.locality.government_governance[focal],
            p.organizations.capital[GOVERNMENT],
            p.locality.government_security_recruit_pipeline[focal],
            p.locality.government_security_reserve[focal],
            p.locality.government_intelligence_penetration[focal],
            p.locality.government_cumulative_security_recruits[focal],
            p.locality.government_cumulative_security_deployments[focal],
            p.locality.government_cumulative_admin_rebuild[focal],
            p.locality.government_cumulative_underground_disruption[focal],
            weighted_police_professionalism(&engine, focal),
            weighted_military_experience(&engine, focal),
            local_police_personnel(&engine, focal),
            local_military_personnel(&engine, focal),
            p.locality.economic_output[focal],
        ));
        if t + 1e-9 >= horizon {
            break;
        }
        t = (t + step).min(horizon);
        engine.advance_until(t).map_err(|e| e.to_string())?;
    }
    Ok(rows)
}

fn run_state_v2(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../state_regeneration_v2.csv".into());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let focal_count: usize = arg(args, 6, 8);
    let horizon: f64 = arg(args, 7, 180.0);
    let step: f64 = arg(args, 8, 15.0);
    let threads: usize = arg(args, 9, 16);
    let seed_base: u64 = arg(args, 10, 2026093100u64);
    ensure_parent(&out)?;
    let capitals = [0.25, 0.5, 1.0, 2.0, 4.0];
    let shocks = [0.1, 0.3, 0.5, 1.0];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        let mut c = synthetic_v2_config(seed, agents, localities, horizon);
        c.foreign_affairs.enabled = false;
        c.organization_ecology.enabled = false;
        let reference = SimulationEngine::new(c)?;
        for focal in evenly_spaced_capacity_focals(&reference, focal_count) {
            for &capital in &capitals {
                for &shock in &shocks {
                    cases.push((seed, focal, capital, shock));
                }
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, focal, capital, shock)| {
                state_v2_case(
                    *seed, agents, localities, horizon, step, *focal, *capital, *shock,
                )
            })
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,focal,capital_mult,shock_fraction,base_government_capital,baseline_institution_capacity,baseline_government_effective_control,baseline_structural_admin,time,institution_capacity,institution_reach,institution_integrity,institution_compliance,government_effective_control,government_formal,government_physical,government_administrative,government_legal,government_fiscal,government_social,government_expected,structural_administrative_capacity,government_governance,government_capital,security_recruit_pipeline,security_reserve,intelligence_penetration,cumulative_security_recruits,cumulative_security_deployments,cumulative_admin_rebuild,cumulative_underground_disruption,police_professionalism,military_experience,police_personnel,military_personnel,economic_output")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn run_state_capital_transition(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../state_regeneration_capital_transition.csv".into());
    let seed_count: usize = arg(args, 3, 4);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let focal_count: usize = arg(args, 6, 4);
    let horizon: f64 = arg(args, 7, 180.0);
    let step: f64 = arg(args, 8, 15.0);
    let threads: usize = arg(args, 9, 16);
    let seed_base: u64 = arg(args, 10, 2026109000u64);
    ensure_parent(&out)?;
    // Frozen before fresh outcomes in state_regeneration_capital_transition_contract_v1.json.
    let capitals = [0.05, 0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 1.00];
    let shocks = [0.10, 0.50];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        let mut c = synthetic_v2_config(seed, agents, localities, horizon);
        c.foreign_affairs.enabled = false;
        c.organization_ecology.enabled = false;
        let reference = SimulationEngine::new(c)?;
        for focal in evenly_spaced_capacity_focals(&reference, focal_count) {
            for &capital in &capitals {
                for &shock in &shocks {
                    cases.push((seed, focal, capital, shock));
                }
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, focal, capital, shock)| {
                state_v2_case(
                    *seed, agents, localities, horizon, step, *focal, *capital, *shock,
                )
            })
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,focal,capital_mult,shock_fraction,base_government_capital,baseline_institution_capacity,baseline_government_effective_control,baseline_structural_admin,time,institution_capacity,institution_reach,institution_integrity,institution_compliance,government_effective_control,government_formal,government_physical,government_administrative,government_legal,government_fiscal,government_social,government_expected,structural_administrative_capacity,government_governance,government_capital,security_recruit_pipeline,security_reserve,intelligence_penetration,cumulative_security_recruits,cumulative_security_deployments,cumulative_admin_rebuild,cumulative_underground_disruption,police_professionalism,military_experience,police_personnel,military_personnel,economic_output")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn state_mechanism_factorial_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    step: f64,
    focal: usize,
    state_regeneration_enabled: bool,
    political_capacity_frozen: bool,
    label: &str,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_v2_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.enabled = false;
    config.state_regeneration.enabled = state_regeneration_enabled;
    if political_capacity_frozen {
        // Preserve political spending, service production, control updates,
        // elections, and patronage flows.  Freeze only the three terms that
        // directly update the institution-capacity memory stock.
        config.political_order.capacity_learning_rate = 0.0;
        config.political_order.capacity_decay_rate = 0.0;
        config.political_order.patronage_capacity_damage = 0.0;
    }
    let mut engine = SimulationEngine::new(config).map_err(|e| e.to_string())?;
    neutralize_insurgent(&mut engine);
    let institution = local_state_institution(&engine, focal)
        .ok_or_else(|| format!("missing local institution {focal}"))?;
    let baseline_capacity = engine.particle.political.institution_capacity[institution];
    let baseline_admin = engine.particle.locality.administrative_capacity[focal];
    let baseline_control = engine.particle.locality.effective_control(focal, 0);
    let base_capital = engine.particle.organizations.capital[GOVERNMENT];

    // Match the severe state-v2 causal-stock shock, but keep capital at 1x.
    let shock_fraction = 0.10_f64;
    engine.particle.political.institution_capacity[institution] =
        (baseline_capacity * shock_fraction).clamp(0.0, 1.0);
    engine.particle.locality.administrative_capacity[focal] =
        (baseline_admin * shock_fraction).clamp(0.0, 1.0);
    for post in 0..engine.particle.security_posts.personnel.len() {
        if engine.particle.security_posts.locality[post] as usize == focal
            && engine.particle.security_posts.organization[post] as usize == POLICE
        {
            engine.particle.security_posts.personnel[post] *= shock_fraction;
            engine.particle.security_posts.presence[post] =
                clamp01(engine.particle.security_posts.personnel[post] / 250.0);
            engine.particle.security_posts.staffed[post] =
                u8::from(engine.particle.security_posts.personnel[post] > 0.0);
        }
    }
    for formation in 0..engine.particle.formations.personnel.len() {
        if engine.particle.formations.organization[formation] as usize == MILITARY
            && engine.particle.formations.locality[formation] as usize == focal
        {
            engine.particle.formations.personnel[formation] *= shock_fraction;
            engine.particle.formations.supply_stock[formation] *= shock_fraction;
            engine.particle.formations.supply_capacity[formation] *= shock_fraction;
        }
    }
    let offset = focal * CONTROL_DIMENSIONS;
    for dimension in [2usize, 3, 5, 6] {
        engine.particle.locality.government_control[offset + dimension] =
            (engine.particle.locality.government_control[offset + dimension] * shock_fraction)
                .clamp(0.0, 1.0);
    }

    let initial_capacity = engine.particle.political.institution_capacity[institution];
    let initial_admin = engine.particle.locality.administrative_capacity[focal];
    let initial_control = engine.particle.locality.effective_control(focal, 0);
    let mut rows = Vec::new();
    let mut t = 0.0;
    loop {
        let p = &engine.particle;
        rows.push(format!(
            "{seed},{focal},{label},{},{},{baseline_capacity:.17},{baseline_admin:.17},{baseline_control:.17},{initial_capacity:.17},{initial_admin:.17},{initial_control:.17},{base_capital:.17},{t:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            u8::from(state_regeneration_enabled),
            if political_capacity_frozen { "frozen" } else { "active" },
            p.political.institution_capacity[institution],
            p.locality.administrative_capacity[focal],
            p.locality.effective_control(focal, 0),
            p.political.institution_integrity[institution],
            p.political.institution_reach[institution],
            p.political.institution_compliance[institution],
            p.locality.government_cumulative_admin_rebuild[focal],
            p.locality.government_cumulative_security_recruits[focal],
            p.locality.government_cumulative_security_deployments[focal],
            p.organizations.capital[GOVERNMENT],
        ));
        if t + 1.0e-9 >= horizon {
            break;
        }
        t = (t + step).min(horizon);
        engine.advance_until(t).map_err(|e| e.to_string())?;
    }
    Ok(rows)
}

fn run_state_mechanism_factorial(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../state_recovery_mechanism_factorial.csv".into());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let focal_count: usize = arg(args, 6, 4);
    let horizon: f64 = arg(args, 7, 180.0);
    let step: f64 = arg(args, 8, 15.0);
    let threads: usize = arg(args, 9, 16);
    let seed_base: u64 = arg(args, 10, 2026119000u64);
    ensure_parent(&out)?;

    let cells = [
        (false, false, "political_only"),
        (true, false, "full_v2"),
        (false, true, "neither_capacity_loop"),
        (true, true, "regeneration_only"),
    ];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        let mut reference_config = synthetic_v2_config(seed, agents, localities, horizon);
        reference_config.foreign_affairs.enabled = false;
        reference_config.organization_ecology.enabled = false;
        let reference = SimulationEngine::new(reference_config)?;
        for focal in evenly_spaced_capacity_focals(&reference, focal_count) {
            for &(regen, frozen, label) in &cells {
                cases.push((seed, focal, regen, frozen, label));
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, focal, regen, frozen, label)| {
                state_mechanism_factorial_case(
                    *seed, agents, localities, horizon, step, *focal, *regen, *frozen, label,
                )
            })
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,focal,cell,state_regeneration,political_capacity_evolution,baseline_institution_capacity,baseline_structural_admin,baseline_government_effective_control,initial_institution_capacity,initial_structural_admin,initial_government_effective_control,base_government_capital,time,institution_capacity,structural_administrative_capacity,government_effective_control,institution_integrity,institution_reach,institution_compliance,cumulative_admin_rebuild,cumulative_security_recruits,cumulative_security_deployments,government_capital")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn military_human_capital_snapshot(engine: &SimulationEngine) -> (f64, f64, f64) {
    let p = &engine.particle;
    let mut personnel = 0.0;
    let mut exp_weighted = 0.0;
    let mut capability_core = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != MILITARY
            || p.formations.outside_pineland[formation] != 0
            || p.formations.active[formation] == 0
        {
            continue;
        }
        let n = p.formations.personnel[formation].max(0.0);
        if n <= 0.0 {
            continue;
        }
        let exp = p.formations.experience[formation].clamp(0.0, 1.0);
        let exp_factor = 0.75 + 0.50 * exp;
        let available = n * p.formations.availability[formation].clamp(0.0, 1.0);
        let mobility = p.formations.mobility[formation].clamp(0.15, 1.0);
        let embedded = 0.55 + 0.45 * p.formations.embeddedness[formation].clamp(0.0, 1.0);
        capability_core += available.max(0.0).powf(0.72)
            * p.formations.quality[formation].max(0.0)
            * exp_factor
            * p.formations.cohesion[formation].max(0.05)
            * mobility.powf(0.35)
            * embedded;
        personnel += n;
        exp_weighted += n * exp;
    }
    let mean_exp = if personnel > 1.0e-12 {
        exp_weighted / personnel
    } else {
        0.0
    };
    (personnel, mean_exp, capability_core)
}

fn human_capital_case(
    seed: u64,
    agents: usize,
    localities: usize,
    recruitment_mult: f64,
    training_mult: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_v2_config(seed, agents, localities, 360.0);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.enabled = false;
    config.state_regeneration.police_allocation_share = 0.0;
    config.state_regeneration.security_recruitment_rate *= recruitment_mult;
    config.state_regeneration.security_training_rate *= training_mult;
    config.state_regeneration.administrative_rebuild_rate = 0.0;
    config.state_regeneration.administrative_decay_rate = 0.0;
    config.state_regeneration.intelligence_gain_rate = 0.0;
    config.state_regeneration.intelligence_decay_rate = 0.0;
    config.state_regeneration.underground_disruption_rate = 0.0;
    let mut engine = SimulationEngine::new(config).map_err(|e| e.to_string())?;
    neutralize_insurgent(&mut engine);
    engine.particle.organizations.capital[GOVERNMENT] = 1.0e12;
    let count = engine
        .particle
        .formations
        .organization
        .iter()
        .filter(|o| **o as usize == MILITARY)
        .count()
        .max(1) as f64;
    let target = engine.config.force_structure.government_target_personnel
        * engine.config.state_regeneration.military_target_multiplier
        / count;
    for formation in 0..engine.particle.formations.personnel.len() {
        if engine.particle.formations.organization[formation] as usize != MILITARY {
            continue;
        }
        engine.particle.formations.personnel[formation] = target;
        engine.particle.formations.experience[formation] = 0.90;
        engine.particle.formations.quality[formation] = 0.75;
        engine.particle.formations.cohesion[formation] = 0.90;
        engine.particle.formations.readiness[formation] = 1.0;
        engine.particle.formations.availability[formation] = 1.0;
        engine.particle.formations.mobility[formation] = 0.50;
        engine.particle.formations.embeddedness[formation] = 0.50;
        engine.particle.formations.sustainment[formation] = 1.0;
        engine.particle.formations.active[formation] = 1;
        engine.particle.formations.operational_status[formation] = 1;
        let capacity = target * engine.config.logistics.formation_supply_days * 4.0;
        engine.particle.formations.supply_capacity[formation] = capacity;
        engine.particle.formations.supply_stock[formation] = capacity;
    }
    for value in &mut engine
        .particle
        .locality
        .government_security_recruit_pipeline
    {
        *value = 0.0;
    }
    for value in &mut engine.particle.locality.government_security_reserve {
        *value = 0.0;
    }
    let (baseline_personnel, baseline_experience, baseline_capability) =
        military_human_capital_snapshot(&engine);
    for formation in 0..engine.particle.formations.personnel.len() {
        if engine.particle.formations.organization[formation] as usize == MILITARY {
            engine.particle.formations.personnel[formation] *= 0.50;
            engine.particle.formations.supply_stock[formation] *= 0.50;
            engine.particle.formations.supply_capacity[formation] *= 0.50;
        }
    }
    let mut rows = Vec::new();
    for &time in &[0.0, 30.0, 90.0, 180.0, 360.0] {
        if time > engine.particle.time + 1.0e-12 {
            engine.advance_until(time).map_err(|e| e.to_string())?;
        }
        let (personnel, experience, capability) = military_human_capital_snapshot(&engine);
        rows.push(format!(
            "{seed},{recruitment_mult:.17},{training_mult:.17},{time:.6},{baseline_personnel:.17},{baseline_experience:.17},{baseline_capability:.17},{personnel:.17},{experience:.17},{capability:.17},{:.17},{:.17},{:.17}",
            personnel / baseline_personnel.max(1.0e-12),
            capability / baseline_capability.max(1.0e-12),
            personnel / baseline_personnel.max(1.0e-12) - capability / baseline_capability.max(1.0e-12),
        ));
    }
    Ok(rows)
}

fn run_human_capital_absorption(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../human_capital_absorption.csv".into());
    let seed_count: usize = arg(args, 3, 16);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let threads: usize = arg(args, 6, 16);
    let seed_base: u64 = arg(args, 7, 2026114000u64);
    ensure_parent(&out)?;
    let multipliers = [0.5, 1.0, 2.0, 4.0];
    let mut cases = Vec::new();
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        for &recruitment in &multipliers {
            for &training in &multipliers {
                cases.push((seed, recruitment, training));
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, recruitment, training)| {
                human_capital_case(*seed, agents, localities, *recruitment, *training)
            })
            .collect()
    });
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,recruitment_mult,training_mult,time,baseline_personnel,baseline_experience,baseline_capability_core,personnel,mean_experience,capability_core,personnel_recovery_fraction,capability_recovery_fraction,headcount_capability_gap")?;
    for result in results {
        for row in result.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    w.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn focal_with_insurgent_members(engine: &SimulationEngine) -> usize {
    let mut mass = vec![0.0; engine.topology.locality_count()];
    for i in 0..engine.particle.people.organization.len() {
        if engine.particle.people.organization[i] as usize == INSURGENT {
            let l = engine.particle.people.residence[i] as usize;
            if l < mass.len() {
                mass[l] += engine.particle.people.represented_population[i]
                    * engine.particle.people.armed_fraction[i].max(0.0);
            }
        }
    }
    mass.iter()
        .enumerate()
        .max_by(|a, b| a.1.total_cmp(b.1))
        .map(|x| x.0)
        .unwrap_or(0)
}

fn local_rooted_membership(engine: &SimulationEngine, locality: usize) -> f64 {
    let mut total = 0.0;
    for i in 0..engine.particle.people.organization.len() {
        if engine.particle.people.organization[i] as usize == INSURGENT
            && engine.particle.people.residence[i] as usize == locality
        {
            total += engine.particle.people.represented_population[i]
                * engine.particle.people.armed_fraction[i].max(0.0);
        }
    }
    total
}

fn police_memory_case(
    seed: u64,
    initial_prof: f64,
    staffing_mult: f64,
) -> Result<Vec<String>, String> {
    let mut c = synthetic_v2_config(seed, 300, 34, 112.0);
    c.foreign_affairs.enabled = false;
    c.organization_ecology.enabled = false;
    c.state_regeneration.security_recruitment_rate = 0.0;
    c.state_regeneration.reserve_attrition_rate = 0.0;
    c.state_regeneration.administrative_rebuild_rate = 0.0;
    c.state_regeneration.administrative_decay_rate = 0.0;
    let mut e = SimulationEngine::new(c).map_err(|x| x.to_string())?;
    let focal = focal_with_insurgent_members(&e);
    e.particle.locality.government_intelligence_penetration[focal] = 0.0;
    let police_target = (e.particle.locality.population[focal]
        * e.config
            .state_regeneration
            .police_target_population_fraction)
        .clamp(15.0, 300.0);
    for post in 0..e.particle.security_posts.personnel.len() {
        if e.particle.security_posts.organization[post] as usize == POLICE
            && e.particle.security_posts.locality[post] as usize == focal
        {
            e.particle.security_posts.personnel[post] = police_target * staffing_mult;
            e.particle.security_posts.presence[post] =
                clamp01(e.particle.security_posts.personnel[post] / 250.0);
            e.particle.security_posts.professionalism[post] = initial_prof;
            e.particle.security_posts.staffed[post] = 1;
        }
    }
    let parent_standard = clamp01(
        0.40 * e.particle.organizations.institutional_quality[POLICE]
            + 0.30 * e.particle.organizations.discipline[POLICE]
            + 0.30 * e.particle.organizations.accountability[POLICE],
    );
    let start_membership = local_rooted_membership(&e, focal);
    let mut cumulative_disrupted = 0.0;
    let mut rows = Vec::new();
    let horizons = [14.0, 28.0, 56.0, 112.0];
    let mut previous = 0.0;
    for &time in &horizons {
        let summary = state_regeneration::update(
            &mut e.particle,
            &e.topology,
            &e.config,
            time,
            time - previous,
        );
        cumulative_disrupted += summary.underground_disrupted;
        previous = time;
        rows.push(format!(
            "police,{seed},{focal},{initial_prof:.17},{staffing_mult:.17},{parent_standard:.17},{start_membership:.17},{time:.6},{:.17},{:.17},{:.17},{:.17}",
            weighted_police_professionalism(&e, focal),
            e.particle.locality.government_intelligence_penetration[focal],
            local_rooted_membership(&e, focal),
            cumulative_disrupted,
        ));
    }
    Ok(rows)
}

fn normalize_combat_pair(
    e: &mut SimulationEngine,
    quality: f64,
    experience: f64,
) -> Result<(usize, usize), String> {
    let first = e
        .particle
        .formations
        .organization
        .iter()
        .position(|o| *o as usize == MILITARY)
        .ok_or_else(|| "missing military formation".to_string())?;
    let second = e
        .particle
        .formations
        .organization
        .iter()
        .position(|o| *o as usize == INSURGENT)
        .ok_or_else(|| "missing insurgent formation".to_string())?;
    let locality = e.particle.formations.locality[first] as usize;
    let zone = e.topology.locality_post_zone[locality];
    for (formation, q, v) in [(first, quality, experience), (second, 0.75, 0.5)] {
        e.particle.formations.locality[formation] = locality as u32;
        e.particle.formations.microzone[formation] = zone;
        e.particle.formations.home_locality[formation] = locality as u32;
        e.particle.formations.personnel[formation] = 500.0;
        e.particle.formations.quality[formation] = q;
        e.particle.formations.experience[formation] = v;
        e.particle.formations.cohesion[formation] = 0.80;
        e.particle.formations.readiness[formation] = 0.90;
        e.particle.formations.sustainment[formation] = 1.0;
        e.particle.formations.information[formation] = 0.60;
        e.particle.formations.mobility[formation] = 0.70;
        e.particle.formations.command[formation] = 0.85;
        e.particle.formations.embeddedness[formation] = 0.50;
        e.particle.formations.fatigue[formation] = 0.0;
        e.particle.formations.availability[formation] = 0.90;
        e.particle.formations.supply_capacity[formation] = 50_000.0;
        e.particle.formations.supply_stock[formation] = 50_000.0;
        e.particle.formations.active[formation] = 1;
        e.particle.formations.moving[formation] = 0;
        e.particle.formations.operational_status[formation] = 1;
        e.particle.formations.outside_pineland[formation] = 0;
    }
    Ok((first, second))
}

fn apply_government_turnover(e: &mut SimulationEngine, formation: usize, turnover: f64) {
    if turnover <= 0.0 {
        return;
    }
    let formation_count = e
        .particle
        .formations
        .organization
        .iter()
        .filter(|o| **o as usize == MILITARY)
        .count()
        .max(1);
    let target = 500.0;
    e.config.force_structure.government_target_personnel = target * formation_count as f64;
    e.config.state_regeneration.military_target_multiplier = 1.0;
    e.config.state_regeneration.police_allocation_share = 0.0;
    e.config.state_regeneration.security_recruitment_rate = 0.0;
    e.config.state_regeneration.security_training_rate = 0.0;
    e.config.state_regeneration.reserve_attrition_rate = 0.0;
    e.config.state_regeneration.deployment_cost_per_person = 0.0;
    e.config.state_regeneration.administrative_rebuild_rate = 0.0;
    e.config.state_regeneration.administrative_decay_rate = 0.0;
    e.config.state_regeneration.intelligence_gain_rate = 0.0;
    e.config.state_regeneration.intelligence_decay_rate = 0.0;
    e.config.state_regeneration.underground_disruption_rate = 0.0;
    for f in 0..e.particle.formations.personnel.len() {
        if e.particle.formations.organization[f] as usize == MILITARY {
            e.particle.formations.personnel[f] = target;
        }
    }
    let locality = e.particle.formations.locality[formation] as usize;
    e.particle.formations.personnel[formation] = target * (1.0 - turnover);
    e.particle.locality.government_security_reserve[locality] = target * turnover + 1.0;
    e.particle.organizations.capital[GOVERNMENT] =
        e.particle.organizations.capital[GOVERNMENT].max(1.0e12);
    let _ = state_regeneration::update(&mut e.particle, &e.topology, &e.config, 14.0, 14.0);
}

fn veterancy_case(
    seed: u64,
    pair: usize,
    quality: f64,
    experience: f64,
    turnover: f64,
    replicate: usize,
) -> Result<String, String> {
    let mut c = synthetic_v2_config(seed, 300, 17, 30.0);
    c.foreign_affairs.enabled = false;
    c.organization_ecology.enabled = false;
    let mut e = SimulationEngine::new(c).map_err(|x| x.to_string())?;
    let (first, _second) = normalize_combat_pair(&mut e, quality, experience)?;
    apply_government_turnover(&mut e, first, turnover);
    // Restore all instantaneous non-quality/non-experience combat fields after
    // the turnover intervention so the post-turnover comparison isolates the
    // experience memory stock rather than incidental regeneration side effects.
    let post_experience = e.particle.formations.experience[first];
    let (first, second) = normalize_combat_pair(&mut e, quality, post_experience)?;
    let factor = quality * (0.75 + 0.50 * post_experience);
    let before_first = e.particle.formations.personnel[first];
    let before_second = e.particle.formations.personnel[second];
    let mut rng = PyRandomCompat::from_seed(202610010000u64 + replicate as u64);
    combat::resolve_organized_engagement(
        &mut e.particle,
        &e.topology,
        &e.config,
        &mut rng,
        0.0,
        first,
        second,
        MILITARY,
        true,
    );
    let loss_first = (before_first - e.particle.formations.personnel[first]) / before_first;
    let loss_second = (before_second - e.particle.formations.personnel[second]) / before_second;
    Ok(format!(
        "veterancy,{seed},{pair},{replicate},{quality:.17},{experience:.17},{turnover:.17},{post_experience:.17},{factor:.17},{loss_first:.17},{loss_second:.17}"
    ))
}

fn run_discrimination(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../force_discrimination_v1.csv".into());
    let seed_count: usize = arg(args, 3, 8);
    let replicates: usize = arg(args, 4, 256);
    let threads: usize = arg(args, 5, 16);
    ensure_parent(&out)?;
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;

    let mut police_tasks = Vec::new();
    for s in 0..seed_count {
        let seed = 2026093200u64 + s as u64;
        for initial_prof in [0.1, 0.5, 0.9] {
            for staffing in [0.5, 1.0, 1.5] {
                police_tasks.push((seed, initial_prof, staffing));
            }
        }
    }
    let police_rows: Vec<Result<Vec<String>, String>> = pool.install(|| {
        police_tasks
            .par_iter()
            .map(|(seed, prof, staffing)| police_memory_case(*seed, *prof, *staffing))
            .collect()
    });

    let pairs = [
        (0usize, 0.9375, 0.1),
        (1usize, 0.75, 0.5),
        (2usize, 0.625, 0.9),
    ];
    let mut veteran_tasks = Vec::new();
    for replicate in 0..replicates {
        for &(pair, q, v) in &pairs {
            for turnover in [0.0, 0.2, 0.4, 0.6] {
                veteran_tasks.push((pair, q, v, turnover, replicate));
            }
        }
    }
    let veteran_rows: Vec<Result<String, String>> = pool.install(|| {
        veteran_tasks
            .par_iter()
            .map(|(pair, q, v, turnover, replicate)| {
                veterancy_case(2026093300, *pair, *q, *v, *turnover, *replicate)
            })
            .collect()
    });

    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "assay,seed_or_case,focal_or_pair,initial_prof_or_replicate,staffing_or_quality,parent_standard_or_initial_experience,start_membership_or_turnover,time_or_post_experience,professionalism_or_capability,intelligence_or_loss_actor,remaining_membership_or_loss_defender,cumulative_disrupted")?;
    for rows in police_rows {
        for row in rows.map_err(std::io::Error::other)? {
            writeln!(w, "{row}")?;
        }
    }
    for row in veteran_rows {
        let raw = row.map_err(std::io::Error::other)?;
        let fields = raw.split(',').collect::<Vec<_>>();
        // Normalize the veterancy record to the shared 12-column transport
        // schema; semantic column names are decoded by the analyzer by assay.
        writeln!(
            w,
            "{},{},{},{},{},{},{},{},{},{},{},",
            fields[0],
            fields[1],
            fields[2],
            fields[3],
            fields[4],
            fields[5],
            fields[6],
            fields[7],
            fields[8],
            fields[9],
            fields[10]
        )?;
    }
    w.flush()?;
    println!(
        "wrote {out} police_cases={} veterancy_cases={}",
        police_tasks.len(),
        veteran_tasks.len()
    );
    Ok(())
}

fn usage() {
    eprintln!("theory_v2_assays state-v2 OUT.csv [seeds=8] [agents=300] [localities=34] [focals=8] [horizon=180] [step=15] [threads=16] [seed_base=2026093100]");
    eprintln!("theory_v2_assays state-mechanism-factorial OUT.csv [seeds=8] [agents=300] [localities=34] [focals=4] [horizon=180] [step=15] [threads=16] [seed_base=2026119000]");
    eprintln!("theory_v2_assays state-capital-transition OUT.csv [seeds=4] [agents=300] [localities=34] [focals=4] [horizon=180] [step=15] [threads=16] [seed_base=2026109000]");
    eprintln!("theory_v2_assays human-capital-absorption OUT.csv [seeds=16] [agents=300] [localities=34] [threads=16] [seed_base=2026114000]");
    eprintln!("theory_v2_assays discriminate OUT.csv [police_seeds=8] [combat_replicates=256] [threads=16]");
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    match args.get(1).map(String::as_str) {
        Some("state-v2") => run_state_v2(&args),
        Some("state-capital-transition") => run_state_capital_transition(&args),
        Some("state-mechanism-factorial") => run_state_mechanism_factorial(&args),
        Some("human-capital-absorption") => run_human_capital_absorption(&args),
        Some("discriminate") => run_discrimination(&args),
        _ => {
            usage();
            Ok(())
        }
    }
}
