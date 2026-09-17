use pineland_core::config::SimulationConfig;
use pineland_core::rng::{seed_from_namespace, PyRandomCompat, RngStreams};
use pineland_core::scheduler::EventPayload;
use pineland_core::state::{ParticleState, CONTROL_DIMENSIONS};
use pineland_model::{SimulationEngine, GOVERNMENT, INSURGENT, MILITARY};
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

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn weighted_mean(sum: f64, weight: f64) -> f64 {
    if weight > 0.0 {
        sum / weight
    } else {
        0.0
    }
}

fn synthetic_config(seed: u64, agents: usize, localities: usize, horizon: f64) -> SimulationConfig {
    let mut c = SimulationConfig::default();
    c.seed = seed;
    c.initialization_seed = Some(seed);
    c.agent_count = agents;
    c.locality_count = localities;
    c.horizon_days = horizon;
    c.output_mode = "forensic".to_string();
    c
}

fn focal_locality(engine: &SimulationEngine) -> usize {
    let p = &engine.particle;
    let n = engine.topology.locality_count();
    let mut score = vec![0.0; n];
    for person in 0..p.people.residence.len() {
        let loc = p.people.residence[person] as usize;
        if loc < n && p.people.organization[person] as usize == INSURGENT {
            score[loc] +=
                p.people.represented_population[person] * p.people.armed_fraction[person].max(0.0);
        }
    }
    for f in 0..p.formations.personnel.len() {
        let loc = p.formations.locality[f] as usize;
        if loc < n && p.formations.organization[f] as usize == INSURGENT {
            score[loc] += p.formations.personnel[f].max(0.0);
        }
    }
    score
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.total_cmp(b.1))
        .map(|x| x.0)
        .unwrap_or(0)
}

fn local_people<'a>(p: &'a ParticleState, locality: usize) -> impl Iterator<Item = usize> + 'a {
    (0..p.people.residence.len()).filter(move |&i| p.people.residence[i] as usize == locality)
}

fn local_insurgent_formations<'a>(
    p: &'a ParticleState,
    locality: usize,
) -> impl Iterator<Item = usize> + 'a {
    (0..p.formations.personnel.len()).filter(move |&f| {
        p.formations.organization[f] as usize == INSURGENT
            && p.formations.locality[f] as usize == locality
            && p.formations.active[f] != 0
            && p.formations.operational_status[f] == 1
            && p.formations.moving[f] == 0
            && p.formations.outside_pineland[f] == 0
    })
}

fn local_manpower_indices<'a>(
    p: &'a ParticleState,
    locality: usize,
) -> impl Iterator<Item = usize> + 'a {
    (0..p.manpower.pool.len()).filter(move |&i| {
        p.manpower.organization[i] as usize == INSURGENT
            && p.manpower.locality[i] as usize == locality
    })
}

fn local_logistics_indices<'a>(
    p: &'a ParticleState,
    locality: usize,
) -> impl Iterator<Item = usize> + 'a {
    (0..p.logistics.source_stock.len()).filter(move |&i| {
        p.logistics.organization[i] as usize == INSURGENT
            && p.logistics.locality[i] as usize == locality
    })
}

const PANEL_COLUMNS: &[&str] = &[
    "m_armed_mass",
    "m_member_depth",
    "m_rooted_local_share",
    "m_rooted_district_share",
    "m_social_exposure",
    "f_personnel",
    "f_effective_strength",
    "f_mean_readiness",
    "f_mean_embeddedness",
    "l_supply_stock",
    "l_supply_fraction",
    "k_belief_conf",
    "k_presence_conf",
    "k_formation_info",
    "k_tradecraft",
    "e_foothold_strength",
    "e_renewal_count",
    "e_viable_activations",
    "e_cum_arrivals",
    "e_cum_recruits",
    "e_cum_actions",
    "c_ins_effective",
    "c_gov_effective",
    "c_margin",
    "c_ins_formal",
    "c_ins_physical",
    "c_ins_admin",
    "c_ins_legal",
    "c_ins_fiscal",
    "c_ins_social",
    "c_ins_expected",
    "c_gov_formal",
    "c_gov_physical",
    "c_gov_admin",
    "c_gov_legal",
    "c_gov_fiscal",
    "c_gov_social",
    "c_gov_expected",
    "x_expected_gov",
    "x_expected_ins",
    "x_grievance",
    "x_fear",
    "x_political_access",
    "x_state_legitimacy",
    "x_government_legitimacy",
    "x_trust_insurgent",
    "x_insurgent_behavior_share",
    "s_admin_capacity",
    "s_security_personnel",
    "s_institution_capacity",
    "s_institution_reach",
    "s_government_governance",
    "u_external_support",
    "u_external_sanctuary",
    "u_foreign_capacity",
    "population",
    "economic_output",
    "infrastructure",
    "terrain_friction",
    "observability",
    "violence",
    "disruption",
    "displaced_share",
    "org_cohesion",
    "org_discipline",
    "org_persistence",
    "org_mobility",
    "org_institutional_quality",
    "org_capital_social",
    "org_capital_political",
    "org_capital_organizational",
    "org_capital_material",
    "org_liquid_capital",
    "org_risk_tolerance",
    "org_governance_investment",
    "formation_quality",
    "formation_command",
    "formation_fatigue",
    "formation_availability",
    "network_mean_degree",
    "access_pressure",
    "total_contacts",
    "total_organized_actions",
    "total_recruitment",
    "total_civilian_harm",
];

fn snapshot_values(engine: &SimulationEngine, locality: usize) -> Vec<f64> {
    let p = &engine.particle;
    let c = &engine.config;
    let topo = &engine.topology;
    let district = topo
        .locality_to_district
        .get(locality)
        .copied()
        .unwrap_or(u32::MAX);
    let org_count = p.organizations.kind.len();

    let mut local_pop = 0.0;
    let mut armed_mass = 0.0;
    let mut home_local = 0.0;
    let mut home_district = 0.0;
    let mut exposure_sum = 0.0;
    let mut expected_gov = 0.0;
    let mut expected_ins = 0.0;
    let mut grievance = 0.0;
    let mut fear = 0.0;
    let mut political_access = 0.0;
    let mut state_leg = 0.0;
    let mut gov_leg = 0.0;
    let mut trust_ins = 0.0;
    let mut insurgent_behavior = 0.0;
    let mut displaced = 0.0;
    let mut degree_weighted = 0.0;
    for person in local_people(p, locality) {
        let w = p.people.represented_population[person].max(0.0);
        local_pop += w;
        if org_count > INSURGENT && p.people.social_exposure.len() >= (person + 1) * org_count {
            exposure_sum +=
                w * p.people.social_exposure[person * org_count + INSURGENT].clamp(0.0, 1.0);
        }
        if p.people.expected_control.len() >= person * 2 + 2 {
            expected_gov += w * p.people.expected_control[person * 2];
            expected_ins += w * p.people.expected_control[person * 2 + 1];
        }
        grievance += w * p.people.grievance[person];
        fear += w * p.people.fear[person];
        political_access += w * p.people.political_access[person];
        state_leg += w * p.people.state_legitimacy[person];
        gov_leg += w * p.people.government_legitimacy[person];
        trust_ins += w * p.people.trust_insurgent[person];
        if matches!(p.people.public_behavior[person], 1 | 2) {
            insurgent_behavior += w;
        }
        if p.people.displaced[person] != 0 {
            displaced += w;
        }
        if p.social_edges.neighbor_offsets.len() > person + 1 {
            degree_weighted += w
                * (p.social_edges.neighbor_offsets[person + 1]
                    - p.social_edges.neighbor_offsets[person]) as f64;
        }
        if p.people.organization[person] as usize == INSURGENT
            && p.people.armed_fraction[person] > 0.0
        {
            let aw = w * p.people.armed_fraction[person].max(0.0);
            armed_mass += aw;
            if p.people.home[person] as usize == locality {
                home_local += aw;
            }
            let hd = topo
                .locality_to_district
                .get(p.people.home[person] as usize)
                .copied()
                .unwrap_or(u32::MAX);
            if hd == district {
                home_district += aw;
            }
        }
    }
    let min_proto = c
        .organization_ecology
        .minimum_proto_represented_population
        .max(1e-12);
    let member_depth = (armed_mass / min_proto).clamp(0.0, 1.0);
    let rooted_local = weighted_mean(home_local, armed_mass);
    let rooted_district = weighted_mean(home_district, armed_mass);

    let formations: Vec<usize> = local_insurgent_formations(p, locality).collect();
    let f_personnel = formations
        .iter()
        .map(|&f| p.formations.personnel[f].max(0.0))
        .sum::<f64>();
    let f_effective = formations
        .iter()
        .map(|&f| p.formations.effective_strength(f))
        .sum::<f64>();
    let f_ready = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.effective_readiness(f))
            .sum(),
        f_personnel,
    );
    let f_embed = weighted_mean(
        formations
            .iter()
            .map(|&f| {
                p.formations.personnel[f].max(0.0) * p.formations.embeddedness[f].clamp(0.0, 1.0)
            })
            .sum(),
        f_personnel,
    );
    let formation_info = weighted_mean(
        formations
            .iter()
            .map(|&f| {
                p.formations.personnel[f].max(0.0) * p.formations.information[f].clamp(0.0, 1.0)
            })
            .sum(),
        f_personnel,
    );
    let formation_quality = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.quality[f])
            .sum(),
        f_personnel,
    );
    let formation_command = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.command[f])
            .sum(),
        f_personnel,
    );
    let formation_fatigue = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.fatigue[f])
            .sum(),
        f_personnel,
    );
    let formation_availability = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.availability[f])
            .sum(),
        f_personnel,
    );

    let mut supply_stock = formations
        .iter()
        .map(|&f| p.formations.supply_stock[f].max(0.0))
        .sum::<f64>();
    let supply_fraction = weighted_mean(
        formations
            .iter()
            .map(|&f| p.formations.personnel[f].max(0.0) * p.formations.supply_fraction(f))
            .sum(),
        f_personnel,
    );
    for i in local_manpower_indices(p, locality) {
        supply_stock += p.manpower.supply_reserve[i].max(0.0);
    }
    for i in local_logistics_indices(p, locality) {
        supply_stock += p.logistics.source_stock[i].max(0.0);
    }

    let belief_conf = mean(
        &p.beliefs
            .keys
            .iter()
            .enumerate()
            .filter(|(_, k)| {
                k.observer as usize == INSURGENT
                    && k.target as usize == GOVERNMENT
                    && k.locality as usize == locality
            })
            .map(|(i, _)| p.beliefs.confidence.get(i).copied().unwrap_or(0.0))
            .collect::<Vec<_>>(),
    );
    let presence_conf = mean(
        &p.presence_beliefs
            .keys
            .iter()
            .enumerate()
            .filter(|(_, k)| {
                k.observer as usize == INSURGENT
                    && k.target as usize == GOVERNMENT
                    && k.locality as usize == locality
            })
            .map(|(i, _)| p.presence_beliefs.confidence.get(i).copied().unwrap_or(0.0))
            .collect::<Vec<_>>(),
    );
    let tradecraft = p
        .organizations
        .local_knowledge
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0);

    let fi = INSURGENT * topo.locality_count() + locality;
    let foothold = |v: &Vec<f64>| v.get(fi).copied().unwrap_or(0.0);
    let foothold_u32 = |v: &Vec<u32>| v.get(fi).copied().unwrap_or(0) as f64;
    let e_strength = foothold(&p.footholds.strength);
    let e_renewals = foothold_u32(&p.footholds.renewal_count);
    let e_viable = foothold_u32(&p.footholds.viable_activation_count);
    let e_arrivals = foothold(&p.footholds.cumulative_arrivals);
    let e_recruits = foothold(&p.footholds.cumulative_recruits);
    let e_actions = foothold(&p.footholds.cumulative_actions);

    let ins_eff = p.locality.effective_control(locality, 1);
    let gov_eff = p.locality.effective_control(locality, 0);
    let off = locality * CONTROL_DIMENSIONS;
    let mut ins_dims = [0.0; CONTROL_DIMENSIONS];
    let mut gov_dims = [0.0; CONTROL_DIMENSIONS];
    if p.locality.insurgent_control.len() >= off + CONTROL_DIMENSIONS {
        ins_dims.copy_from_slice(&p.locality.insurgent_control[off..off + CONTROL_DIMENSIONS]);
    }
    if p.locality.government_control.len() >= off + CONTROL_DIMENSIONS {
        gov_dims.copy_from_slice(&p.locality.government_control[off..off + CONTROL_DIMENSIONS]);
    }

    let mut security_personnel = 0.0;
    for post in 0..p.security_posts.locality.len() {
        if p.security_posts.locality[post] as usize == locality
            && p.security_posts.staffed.get(post).copied().unwrap_or(0) != 0
            && p.security_posts
                .organization
                .get(post)
                .copied()
                .unwrap_or(INSURGENT as u32) as usize
                != INSURGENT
        {
            security_personnel += p
                .security_posts
                .personnel
                .get(post)
                .copied()
                .unwrap_or(0.0)
                .max(0.0);
        }
    }
    let mut inst_caps = Vec::new();
    let mut inst_reach = Vec::new();
    for i in 0..p.political.institution_locality.len() {
        if p.political.institution_locality[i] as usize == locality {
            inst_caps.push(
                p.political
                    .institution_capacity
                    .get(i)
                    .copied()
                    .unwrap_or(0.0),
            );
            inst_reach.push(p.political.institution_reach.get(i).copied().unwrap_or(0.0));
        }
    }
    let foreign_capacity = (0..p.foreign_interventions.provided_capacity.len())
        .filter(|&i| {
            p.foreign_interventions
                .recipient
                .get(i)
                .copied()
                .unwrap_or(u32::MAX) as usize
                == INSURGENT
        })
        .map(|i| p.foreign_interventions.provided_capacity[i].max(0.0))
        .sum::<f64>();
    let orgv = |v: &Vec<f64>| v.get(INSURGENT).copied().unwrap_or(0.0);
    let pheno = |d: usize| {
        p.organizations
            .phenotype
            .get(INSURGENT * 8 + d)
            .copied()
            .unwrap_or(0.0)
    };

    let mut access_vals = Vec::new();
    for i in 0..p.access_restrictions.level.len() {
        if p.access_restrictions.first_locality[i] as usize == locality
            || p.access_restrictions.second_locality[i] as usize == locality
        {
            access_vals.push(p.access_restrictions.level[i].clamp(0.0, 1.0));
        }
    }

    let pop = p
        .locality
        .population
        .get(locality)
        .copied()
        .unwrap_or(local_pop);
    let econ = p
        .locality
        .economic_output
        .get(locality)
        .copied()
        .unwrap_or(0.0);
    let infra = p
        .locality
        .infrastructure
        .get(locality)
        .copied()
        .unwrap_or(0.0);
    let terrain = p
        .locality
        .terrain_friction
        .get(locality)
        .copied()
        .unwrap_or(0.0);
    let observability = p
        .locality
        .observability
        .get(locality)
        .copied()
        .unwrap_or(0.0);
    let violence = p.locality.violence.get(locality).copied().unwrap_or(0.0);
    let disruption = p.locality.disruption.get(locality).copied().unwrap_or(0.0);
    let admin_capacity = p
        .locality
        .administrative_capacity
        .get(locality)
        .copied()
        .unwrap_or(0.0);
    let gov_governance = p
        .locality
        .government_governance
        .get(locality)
        .copied()
        .unwrap_or(0.0);

    vec![
        armed_mass,
        member_depth,
        rooted_local,
        rooted_district,
        weighted_mean(exposure_sum, local_pop),
        f_personnel,
        f_effective,
        f_ready,
        f_embed,
        supply_stock,
        supply_fraction,
        belief_conf,
        presence_conf,
        formation_info,
        tradecraft,
        e_strength,
        e_renewals,
        e_viable,
        e_arrivals,
        e_recruits,
        e_actions,
        ins_eff,
        gov_eff,
        ins_eff - gov_eff,
        ins_dims[0],
        ins_dims[1],
        ins_dims[2],
        ins_dims[3],
        ins_dims[4],
        ins_dims[5],
        ins_dims[6],
        gov_dims[0],
        gov_dims[1],
        gov_dims[2],
        gov_dims[3],
        gov_dims[4],
        gov_dims[5],
        gov_dims[6],
        weighted_mean(expected_gov, local_pop),
        weighted_mean(expected_ins, local_pop),
        weighted_mean(grievance, local_pop),
        weighted_mean(fear, local_pop),
        weighted_mean(political_access, local_pop),
        weighted_mean(state_leg, local_pop),
        weighted_mean(gov_leg, local_pop),
        weighted_mean(trust_ins, local_pop),
        weighted_mean(insurgent_behavior, local_pop),
        admin_capacity,
        security_personnel,
        mean(&inst_caps),
        mean(&inst_reach),
        gov_governance,
        orgv(&p.organizations.external_support),
        orgv(&p.organizations.external_sanctuary),
        foreign_capacity,
        pop,
        econ,
        infra,
        terrain,
        observability,
        violence,
        disruption,
        weighted_mean(displaced, local_pop),
        orgv(&p.organizations.cohesion),
        orgv(&p.organizations.discipline),
        orgv(&p.organizations.persistence),
        orgv(&p.organizations.mobility),
        orgv(&p.organizations.institutional_quality),
        orgv(&p.organizations.capital_social),
        orgv(&p.organizations.capital_political),
        orgv(&p.organizations.capital_organizational),
        orgv(&p.organizations.capital_material),
        orgv(&p.organizations.capital),
        pheno(4),
        pheno(2),
        formation_quality,
        formation_command,
        formation_fatigue,
        formation_availability,
        weighted_mean(degree_weighted, local_pop),
        mean(&access_vals),
        p.counters.contacts as f64,
        p.counters.organized_actions as f64,
        p.counters.recruitment,
        p.counters.civilian_harm,
    ]
}

fn write_panel_header<W: Write>(w: &mut W, prefix: &[&str]) -> std::io::Result<()> {
    let mut cols = prefix.iter().map(|s| s.to_string()).collect::<Vec<_>>();
    cols.extend(PANEL_COLUMNS.iter().map(|s| s.to_string()));
    writeln!(w, "{}", cols.join(","))
}

fn write_panel_row<W: Write>(w: &mut W, prefix: &[String], values: &[f64]) -> std::io::Result<()> {
    let mut row = prefix.to_vec();
    row.extend(values.iter().map(|v| format!("{:.17}", v)));
    writeln!(w, "{}", row.join(","))
}

fn panel_index(name: &str) -> usize {
    PANEL_COLUMNS
        .iter()
        .position(|candidate| *candidate == name)
        .unwrap_or_else(|| panic!("missing panel column {name}"))
}

fn spatial_member_pressure(engine: &SimulationEngine, locality: usize) -> f64 {
    let mut sum = 0.0;
    let mut count = 0usize;
    let m_idx = panel_index("m_member_depth");
    for (neighbor, _) in engine.topology.locality_edges.neighbors(locality) {
        let neighbor = neighbor as usize;
        if neighbor < engine.topology.locality_count() {
            sum += snapshot_values(engine, neighbor)[m_idx];
            count += 1;
        }
    }
    if count > 0 {
        sum / count as f64
    } else {
        0.0
    }
}

fn local_police_professionalism_for_closure(engine: &SimulationEngine, locality: usize) -> f64 {
    let p = &engine.particle;
    let mut weighted = 0.0;
    let mut weight = 0.0;
    for post in 0..p.security_posts.personnel.len() {
        if p.security_posts.organization[post] as usize != pineland_model::POLICE
            || p.security_posts.locality[post] as usize != locality
            || p.security_posts.staffed[post] == 0
        {
            continue;
        }
        let personnel = p.security_posts.personnel[post].max(0.0);
        weighted += personnel * p.security_posts.professionalism[post].clamp(0.0, 1.0);
        weight += personnel;
    }
    weighted_mean(weighted, weight)
}

fn local_formation_experience_for_closure(
    engine: &SimulationEngine,
    locality: usize,
    organization: usize,
) -> f64 {
    let p = &engine.particle;
    let mut weighted = 0.0;
    let mut weight = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != organization
            || p.formations.locality[formation] as usize != locality
            || p.formations.active[formation] == 0
            || p.formations.operational_status[formation] == 0
            || p.formations.outside_pineland[formation] != 0
        {
            continue;
        }
        let personnel = p.formations.personnel[formation].max(0.0);
        weighted += personnel * p.formations.experience[formation].clamp(0.0, 1.0);
        weight += personnel;
    }
    weighted_mean(weighted, weight)
}

const CLOSURE_FEATURE_COUNT: usize = 30;
type ClosureFeatureVector = [f64; CLOSURE_FEATURE_COUNT];

fn rooted_membership_mass_from_snapshot(v: &[f64]) -> f64 {
    let armed_mass = v[panel_index("m_armed_mass")].max(0.0);
    let rooted_local = v[panel_index("m_rooted_local_share")].clamp(0.0, 1.0);
    let rooted_district = v[panel_index("m_rooted_district_share")].clamp(0.0, 1.0);
    let origin_depth = ((rooted_local + rooted_district) / 2.0).clamp(0.0, 1.0);
    armed_mass * (0.5 + 0.5 * origin_depth)
}

/// One-hop source reservoir implied by the production movement Markov blanket.
/// Default movement is adjacent-only, so these are the states capable of
/// directly supplying the focal locality at the next relocation opportunity.
fn closure_ring1_features(
    engine: &SimulationEngine,
    locality: usize,
    recruitment_hazard_by_locality: &[f64],
) -> [f64; 3] {
    let p = &engine.particle;
    let locality_count = engine.topology.locality_count();
    let mut neighbor_mask = vec![false; locality_count];
    for (neighbor, _) in engine.topology.locality_edges.neighbors(locality) {
        let neighbor = neighbor as usize;
        if neighbor < locality_count {
            neighbor_mask[neighbor] = true;
        }
    }
    let mut transportable = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != INSURGENT {
            continue;
        }
        let origin = p.formations.locality[formation] as usize;
        if origin < locality_count && neighbor_mask[origin] {
            transportable += closure_transport_strength_if_present(p, formation).max(0.0);
        }
    }
    let mut rooted = 0.0;
    let mut hazard = 0.0;
    for neighbor in 0..locality_count {
        if !neighbor_mask[neighbor] {
            continue;
        }
        let v = snapshot_values(engine, neighbor);
        rooted += rooted_membership_mass_from_snapshot(&v);
        hazard += recruitment_hazard_by_locality
            .get(neighbor)
            .copied()
            .unwrap_or(0.0)
            .max(0.0);
    }
    [transportable.ln_1p(), rooted.ln_1p(), hazard.ln_1p()]
}

/// Probe-local source-parity copy of movement::transport_strength_if_present.
/// The production helper is intentionally private; closure delay coordinates
/// must nevertheless weight committed orders by the exact same transported
/// capacity used by inbound/net transport pressure rather than by generic
/// combat effective strength.
fn closure_transport_strength_if_present(p: &ParticleState, formation: usize) -> f64 {
    if formation >= p.formations.personnel.len()
        || p.formations.outside_pineland[formation] != 0
        || p.formations.personnel[formation] <= 0.0
        || p.formations.operational_status[formation] != 1
    {
        return 0.0;
    }
    let personnel = p.formations.personnel[formation].max(0.0);
    let available = personnel
        * p.formations.availability[formation].clamp(0.0, 1.0)
        * p.formations.effective_readiness(formation);
    if available <= 0.0 {
        0.0
    } else {
        available
            * p.formations.quality[formation]
            * p.formations.cohesion[formation]
            * (0.5 + p.formations.information[formation])
    }
}

/// First-order committed movement delay state for the focal locality.
///
/// Existing inbound/net transport pressure already includes the *mass* of
/// pending/moving orders, but not when those orders will execute/arrive.  For
/// closure we therefore retain the committed inbound/outbound mass and its
/// strength-weighted ETA.  These are theory diagnostics only; no model state
/// or causal mechanism is changed.
fn closure_delay_features(engine: &SimulationEngine, locality: usize) -> [f64; 4] {
    let p = &engine.particle;
    let owner_active = p
        .organizations
        .active
        .get(INSURGENT)
        .copied()
        .unwrap_or(0)
        != 0;
    if !owner_active {
        return [0.0; 4];
    }
    let now = p.time;
    let mut incoming_strength = 0.0;
    let mut incoming_eta_weighted = 0.0;
    let mut outgoing_strength = 0.0;
    let mut outgoing_eta_weighted = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != INSURGENT
            || p.formations.active[formation] == 0
            || p.formations.operational_status[formation] == 0
            || p.formations.outside_pineland[formation] != 0
            || p.formations.personnel[formation] <= 0.0
        {
            continue;
        }
        let status = p.formations.movement_status[formation];
        if !matches!(status, 1 | 2) {
            continue;
        }
        let origin = p.formations.locality[formation] as usize;
        let destination = p.formations.movement_destination[formation] as usize;
        if origin == destination {
            continue;
        }
        let strength = closure_transport_strength_if_present(p, formation).max(0.0);
        if strength <= 0.0 {
            continue;
        }
        let eta = if status == 2 {
            (p.formations.movement_arrives_at[formation] - now).max(0.0)
        } else {
            (p.formations.movement_execute_at[formation] - now).max(0.0)
                + p.formations.movement_travel_hours[formation].max(0.0) / 24.0
        };
        if destination == locality {
            incoming_strength += strength;
            incoming_eta_weighted += strength * eta;
        }
        if origin == locality {
            outgoing_strength += strength;
            outgoing_eta_weighted += strength * eta;
        }
    }
    [
        incoming_strength.ln_1p(),
        weighted_mean(incoming_eta_weighted, incoming_strength),
        outgoing_strength.ln_1p(),
        weighted_mean(outgoing_eta_weighted, outgoing_strength),
    ]
}

fn closure_features_with_transport(
    engine: &SimulationEngine,
    locality: usize,
    inbound_transport_pressure: f64,
    net_transport_pressure: f64,
    executable_inbound_transport_pressure: f64,
    executable_net_transport_pressure: f64,
) -> ClosureFeatureVector {
    let v = snapshot_values(engine, locality);
    let k_intel = mean(&[
        v[panel_index("k_belief_conf")],
        v[panel_index("k_presence_conf")],
        v[panel_index("k_formation_info")],
    ]);
    let state_capacity = mean(&[
        v[panel_index("c_gov_effective")],
        v[panel_index("s_admin_capacity")],
        v[panel_index("s_institution_capacity")],
        v[panel_index("s_government_governance")],
    ]);
    let external = v[panel_index("u_external_support")]
        + v[panel_index("u_external_sanctuary")]
        + (1.0 + v[panel_index("u_foreign_capacity")].max(0.0)).ln();
    let renewal_potential = pineland_model::organizations::local_embeddedness(
        &engine.particle,
        &engine.topology,
        &engine.config,
        INSURGENT,
        locality,
    );
    let organization_persistence = engine
        .particle
        .organizations
        .persistence
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    // Source-faithful replacement candidate for clipped membership depth:
    // production local_embeddedness weights membership by
    // 0.5 + 0.5*origin_depth, but clips the magnitude at one proto threshold.
    // Keep the same rootedness weighting while preserving unbounded stock.
    let rooted_membership_stock = rooted_membership_mass_from_snapshot(&v).ln_1p();
    let recruitment_hazard_by_locality =
        pineland_model::recruitment::recruitment_hazard_mass_by_locality(
        &engine.particle,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let recruitment_hazard = recruitment_hazard_by_locality
        .get(locality)
        .copied()
        .unwrap_or(0.0)
        .max(0.0)
        .ln_1p();
    let social_exposure = v[panel_index("m_social_exposure")].clamp(0.0, 1.0);
    let delay = closure_delay_features(engine, locality);
    let ring1 = closure_ring1_features(engine, locality, &recruitment_hazard_by_locality);
    [
        v[panel_index("m_member_depth")],
        (1.0 + v[panel_index("f_effective_strength")].max(0.0)).ln(),
        v[panel_index("e_foothold_strength")],
        v[panel_index("c_margin")],
        (1.0 + v[panel_index("org_liquid_capital")].max(0.0)).ln(),
        spatial_member_pressure(engine, locality),
        v[panel_index("l_supply_fraction")],
        k_intel,
        v[panel_index("x_expected_ins")] - v[panel_index("x_expected_gov")],
        state_capacity,
        external,
        local_police_professionalism_for_closure(engine, locality),
        local_formation_experience_for_closure(engine, locality, pineland_model::MILITARY),
        local_formation_experience_for_closure(engine, locality, INSURGENT),
        renewal_potential,
        organization_persistence,
        inbound_transport_pressure.max(0.0).ln_1p(),
        net_transport_pressure.signum() * net_transport_pressure.abs().ln_1p(),
        rooted_membership_stock,
        recruitment_hazard,
        social_exposure,
        delay[0],
        delay[1],
        delay[2],
        delay[3],
        executable_inbound_transport_pressure.max(0.0).ln_1p(),
        executable_net_transport_pressure.signum()
            * executable_net_transport_pressure.abs().ln_1p(),
        ring1[0],
        ring1[1],
        ring1[2],
    ]
}

fn closure_features(engine: &SimulationEngine, locality: usize) -> ClosureFeatureVector {
    let transport = pineland_model::movement::inbound_transport_pressures(
        &engine.particle,
        &engine.topology,
        &engine.config,
    );
    let net_transport = pineland_model::movement::insurgent_transport_net_pressures(
        &engine.particle,
        &engine.topology,
        &engine.config,
    );
    let executable_transport = pineland_model::movement::executable_inbound_transport_pressures(
        &engine.particle,
        &engine.topology,
        &engine.config,
    );
    let executable_net_transport =
        pineland_model::movement::insurgent_executable_transport_net_pressures(
            &engine.particle,
            &engine.topology,
            &engine.config,
        );
    closure_features_with_transport(
        engine,
        locality,
        transport.get(locality).copied().unwrap_or(0.0),
        net_transport.get(locality).copied().unwrap_or(0.0),
        executable_transport.get(locality).copied().unwrap_or(0.0),
        executable_net_transport
            .get(locality)
            .copied()
            .unwrap_or(0.0),
    )
}

fn closure_activity_score(features: &ClosureFeatureVector) -> f64 {
    features[0] + features[2] + features[1] / (1.0 + features[1].max(0.0))
}

fn closure_hidden_diagnostics(engine: &SimulationEngine, locality: usize) -> [f64; 46] {
    let p = &engine.particle;
    let mut raw_personnel = 0.0;
    let mut readiness_sum = 0.0;
    let mut quality_sum = 0.0;
    let mut cohesion_sum = 0.0;
    let mut experience_sum = 0.0;
    let mut availability_sum = 0.0;
    let mut sustainment_sum = 0.0;
    let mut formation_count = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != INSURGENT
            || p.formations.locality[formation] as usize != locality
            || p.formations.active[formation] == 0
            || p.formations.operational_status[formation] == 0
            || p.formations.outside_pineland[formation] != 0
            || p.formations.personnel[formation] <= 0.0
        {
            continue;
        }
        let w = p.formations.personnel[formation].max(0.0);
        raw_personnel += w;
        readiness_sum += w * p.formations.readiness[formation].clamp(0.0, 1.0);
        quality_sum += w * p.formations.quality[formation].clamp(0.0, 1.0);
        cohesion_sum += w * p.formations.cohesion[formation].clamp(0.0, 1.0);
        experience_sum += w * p.formations.experience[formation].clamp(0.0, 1.0);
        availability_sum += w * p.formations.availability[formation].clamp(0.0, 1.0);
        sustainment_sum += w * p.formations.sustainment[formation].clamp(0.0, 1.0);
        formation_count += 1.0;
    }
    let denom = raw_personnel.max(1.0e-12);

    let mut manpower_pool = 0.0;
    let mut supply_reserve = 0.0;
    for index in 0..p.manpower.pool.len() {
        if p.manpower.organization[index] as usize == INSURGENT
            && p.manpower.locality[index] as usize == locality
        {
            manpower_pool += p.manpower.pool[index].max(0.0);
            supply_reserve += p.manpower.supply_reserve[index].max(0.0);
        }
    }
    let supply_per_fighter = (engine.config.logistics.formation_supply_days
        * engine.config.logistics.initial_supply_fraction)
        .max(1.0e-12);
    let fieldable_reserve = manpower_pool.min(supply_reserve / supply_per_fighter);

    let foothold = INSURGENT * engine.topology.locality_count() + locality;
    let foothold_strength = p.footholds.strength.get(foothold).copied().unwrap_or(0.0);
    let foothold_embeddedness = p
        .footholds
        .embeddedness
        .get(foothold)
        .copied()
        .unwrap_or(0.0);
    let foothold_renewals = p
        .footholds
        .renewal_count
        .get(foothold)
        .copied()
        .unwrap_or(0) as f64;
    let foothold_recruits = p
        .footholds
        .cumulative_recruits
        .get(foothold)
        .copied()
        .unwrap_or(0.0);
    let foothold_arrivals = p
        .footholds
        .cumulative_arrivals
        .get(foothold)
        .copied()
        .unwrap_or(0.0);
    let last_activation = p
        .footholds
        .last_activated_at
        .get(foothold)
        .copied()
        .unwrap_or(-1.0e9);
    let foothold_age = if last_activation > -1.0e8 {
        (engine.particle.time - last_activation).max(0.0)
    } else {
        1.0e9
    };

    let hazard = pineland_model::recruitment::recruitment_hazard_mass_by_locality(
        p,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let recruitment_hazard = hazard.get(locality).copied().unwrap_or(0.0).max(0.0);

    let organization_count = p.organizations.kind.len();
    let mut exposure_weighted = 0.0;
    let mut exposure_mass = 0.0;
    let mut rooted_mass = 0.0;
    for person in 0..p.people.residence.len() {
        if p.people.residence[person] as usize != locality {
            continue;
        }
        let represented = p.people.represented_population[person].max(0.0);
        if organization_count > INSURGENT
            && p.people.social_exposure.len() >= (person + 1) * organization_count
        {
            exposure_weighted += represented
                * p.people.social_exposure[person * organization_count + INSURGENT].clamp(0.0, 1.0);
            exposure_mass += represented;
        }
        if p.people.organization[person] as usize == INSURGENT
            && p.people.home[person] as usize == locality
            && p.people.armed_fraction[person] > 0.0
        {
            rooted_mass += represented * p.people.armed_fraction[person].max(0.0);
        }
    }
    let mean_social_exposure = if exposure_mass > 0.0 {
        exposure_weighted / exposure_mass
    } else {
        0.0
    };

    // Causal pipeline state.  Instantaneous net transport is a first moment:
    // two worlds can have the same current flux but different committed
    // arrival times.  Record the hidden delay line without promoting it to a
    // closure coordinate; this is diagnostic-only until a fresh contract is
    // registered.
    let now = p.time;
    let mut incoming_strength = 0.0;
    let mut incoming_eta_weighted = 0.0;
    let mut incoming_eta_min = f64::INFINITY;
    let mut incoming_orders = 0.0;
    let mut outgoing_strength = 0.0;
    let mut outgoing_eta_weighted = 0.0;
    let mut outgoing_orders = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != INSURGENT
            || p.formations.active[formation] == 0
            || p.formations.operational_status[formation] == 0
            || p.formations.outside_pineland[formation] != 0
            || p.formations.personnel[formation] <= 0.0
        {
            continue;
        }
        let status = p.formations.movement_status[formation];
        if !matches!(status, 1 | 2) {
            continue;
        }
        let origin = p.formations.locality[formation] as usize;
        let destination = p.formations.movement_destination[formation] as usize;
        if origin == destination {
            continue;
        }
        let strength = closure_transport_strength_if_present(p, formation).max(0.0);
        if strength <= 0.0 {
            continue;
        }
        let eta = if status == 2 {
            (p.formations.movement_arrives_at[formation] - now).max(0.0)
        } else {
            (p.formations.movement_execute_at[formation] - now).max(0.0)
                + p.formations.movement_travel_hours[formation].max(0.0) / 24.0
        };
        if destination == locality {
            incoming_strength += strength;
            incoming_eta_weighted += strength * eta;
            incoming_eta_min = incoming_eta_min.min(eta);
            incoming_orders += 1.0;
        }
        if origin == locality {
            outgoing_strength += strength;
            outgoing_eta_weighted += strength * eta;
            outgoing_orders += 1.0;
        }
    }
    let incoming_eta_mean = weighted_mean(incoming_eta_weighted, incoming_strength);
    let outgoing_eta_mean = weighted_mean(outgoing_eta_weighted, outgoing_strength);
    if !incoming_eta_min.is_finite() {
        incoming_eta_min = 0.0;
    }

    // One-shot scheduled events are another inherited future commitment.  The
    // recurring clocks are synchronized by fixed intervals; these one-shots
    // can still differ across matched worlds because they were emitted from a
    // lagged microstate before the anchor snapshot.
    let mut pending_local_insurgent_actions = 0.0;
    let mut pending_local_other_actions = 0.0;
    let mut next_local_action_delay = f64::INFINITY;
    let mut pending_local_contacts = 0.0;
    for event in p.scheduler.events_sorted() {
        match event.payload {
            EventPayload::OrganizedAction {
                organization,
                locality: event_locality,
            } if event_locality.get() as usize == locality => {
                if organization.get() as usize == INSURGENT {
                    pending_local_insurgent_actions += 1.0;
                } else {
                    pending_local_other_actions += 1.0;
                }
                next_local_action_delay = next_local_action_delay.min((event.time - now).max(0.0));
            }
            EventPayload::Contact {
                locality: event_locality,
                ..
            } if event_locality.get() as usize == locality => {
                pending_local_contacts += 1.0;
            }
            _ => {}
        }
    }
    if !next_local_action_delay.is_finite() {
        next_local_action_delay = 0.0;
    }

    // Upstream/network state.  The local scalar transport coordinate is an
    // aggregate over formations and source localities.  Future transport can
    // diverge if equal current aggregates are generated by different command
    // quality or different nonlocal reservoirs.  These are post-hoc
    // diagnostics only; they are not silently promoted into the closure state.
    let org_institutional_quality = p
        .organizations
        .institutional_quality
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    let phenotype_offset = INSURGENT * 8;
    let org_centralization = p
        .organizations
        .phenotype
        .get(phenotype_offset)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    let org_cohesion = p
        .organizations
        .cohesion
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);
    let org_persistence = p
        .organizations
        .persistence
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0)
        .clamp(0.0, 1.0);

    let mut neighbor_mask = vec![false; engine.topology.locality_count()];
    for (neighbor, _) in engine.topology.locality_edges.neighbors(locality) {
        let neighbor = neighbor as usize;
        if neighbor < neighbor_mask.len() {
            neighbor_mask[neighbor] = true;
        }
    }
    let mut local_command_weight = 0.0;
    let mut local_command_reliability = 0.0;
    let mut local_command_latency = 0.0;
    let mut external_command_weight = 0.0;
    let mut external_command_reliability = 0.0;
    let mut external_command_latency = 0.0;
    let mut external_transportable_strength = 0.0;
    let mut external_formation_count = 0.0;
    let mut neighbor_transportable_strength = 0.0;
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize != INSURGENT {
            continue;
        }
        let strength = closure_transport_strength_if_present(p, formation).max(0.0);
        if strength <= 0.0 {
            continue;
        }
        let mut reliability = p.formations.command[formation].clamp(0.0, 1.0);
        let mut latency = 0.0;
        for edge in 0..p.command_edges.organization.len() {
            if p.command_edges.organization[edge] as usize == INSURGENT
                && p.command_edges.formation[edge] as usize == formation
            {
                reliability = p.command_edges.reliability[edge].clamp(0.0, 1.0);
                latency = p.command_edges.latency_hours[edge].max(0.0);
                break;
            }
        }
        let origin = p.formations.locality[formation] as usize;
        if origin == locality {
            local_command_weight += strength;
            local_command_reliability += strength * reliability;
            local_command_latency += strength * latency;
        } else {
            external_command_weight += strength;
            external_command_reliability += strength * reliability;
            external_command_latency += strength * latency;
            external_transportable_strength += strength;
            external_formation_count += 1.0;
            if origin < neighbor_mask.len() && neighbor_mask[origin] {
                neighbor_transportable_strength += strength;
            }
        }
    }

    let mut external_rooted_mass = 0.0;
    let mut neighbor_rooted_mass = 0.0;
    for person in 0..p.people.organization.len() {
        if p.people.organization[person] as usize != INSURGENT
            || p.people.armed_fraction[person] <= 0.0
        {
            continue;
        }
        let home = p.people.home[person] as usize;
        if home == locality {
            continue;
        }
        let mass = p.people.represented_population[person].max(0.0)
            * p.people.armed_fraction[person].max(0.0);
        external_rooted_mass += mass;
        if home < neighbor_mask.len() && neighbor_mask[home] {
            neighbor_rooted_mass += mass;
        }
    }
    let external_recruitment_hazard = hazard
        .iter()
        .enumerate()
        .filter(|(i, _)| *i != locality)
        .map(|(_, x)| x.max(0.0))
        .sum::<f64>();
    let neighbor_recruitment_hazard = hazard
        .iter()
        .enumerate()
        .filter(|(i, _)| *i < neighbor_mask.len() && neighbor_mask[*i])
        .map(|(_, x)| x.max(0.0))
        .sum::<f64>();

    [
        (1.0 + raw_personnel).ln(),
        readiness_sum / denom,
        quality_sum / denom,
        cohesion_sum / denom,
        experience_sum / denom,
        availability_sum / denom,
        sustainment_sum / denom,
        formation_count,
        (1.0 + manpower_pool).ln(),
        (1.0 + supply_reserve).ln(),
        (1.0 + fieldable_reserve).ln(),
        foothold_strength,
        foothold_embeddedness,
        (1.0 + foothold_renewals).ln(),
        (1.0 + foothold_recruits.max(0.0)).ln(),
        (1.0 + foothold_arrivals.max(0.0)).ln(),
        foothold_age.ln_1p(),
        recruitment_hazard.ln_1p(),
        mean_social_exposure,
        (1.0 + rooted_mass).ln(),
        incoming_strength.ln_1p(),
        incoming_eta_mean,
        incoming_eta_min,
        incoming_orders,
        outgoing_strength.ln_1p(),
        outgoing_eta_mean,
        outgoing_orders,
        pending_local_insurgent_actions,
        pending_local_other_actions,
        next_local_action_delay,
        pending_local_contacts,
        org_institutional_quality,
        org_centralization,
        org_cohesion,
        org_persistence,
        weighted_mean(local_command_reliability, local_command_weight),
        weighted_mean(local_command_latency, local_command_weight),
        weighted_mean(external_command_reliability, external_command_weight),
        weighted_mean(external_command_latency, external_command_weight),
        external_transportable_strength.ln_1p(),
        external_formation_count,
        external_rooted_mass.ln_1p(),
        external_recruitment_hazard.ln_1p(),
        neighbor_rooted_mass.ln_1p(),
        neighbor_recruitment_hazard.ln_1p(),
        neighbor_transportable_strength.ln_1p(),
    ]
}

const CLOSURE_HIDDEN_NAMES: [&str; 46] = [
    "log_raw_fielded_personnel",
    "mean_readiness",
    "mean_quality",
    "mean_cohesion",
    "mean_experience",
    "mean_availability",
    "mean_sustainment",
    "formation_count",
    "log_manpower_pool",
    "log_supply_reserve",
    "log_fieldable_reserve",
    "foothold_strength_hidden",
    "foothold_embeddedness_hidden",
    "log_foothold_renewals",
    "log_cumulative_local_recruits",
    "log_cumulative_local_arrivals",
    "log_foothold_age_days",
    "log_recruitment_hazard_mass",
    "mean_social_exposure",
    "log_rooted_member_mass",
    "log_pending_incoming_strength",
    "pending_incoming_mean_eta_days",
    "pending_incoming_min_eta_days",
    "pending_incoming_order_count",
    "log_pending_outgoing_strength",
    "pending_outgoing_mean_eta_days",
    "pending_outgoing_order_count",
    "pending_local_insurgent_actions",
    "pending_local_other_actions",
    "next_local_action_delay_days",
    "pending_local_contacts",
    "organization_institutional_quality",
    "organization_centralization",
    "organization_cohesion",
    "organization_persistence_hidden",
    "local_command_reliability",
    "local_command_latency_hours",
    "external_command_reliability",
    "external_command_latency_hours",
    "log_external_transportable_strength",
    "external_transportable_formation_count",
    "log_external_rooted_mass",
    "log_external_recruitment_hazard",
    "log_neighbor_rooted_mass",
    "log_neighbor_recruitment_hazard",
    "log_neighbor_transportable_strength",
];

#[derive(Clone, Debug)]
struct ClosurePair {
    pair_id: usize,
    left_engine: usize,
    right_engine: usize,
    left_seed: u64,
    right_seed: u64,
    locality: usize,
    distance: f64,
    stratum: String,
    left_pre: ClosureFeatureVector,
    right_pre: ClosureFeatureVector,
}

fn feature_scales(features: &[Vec<ClosureFeatureVector>]) -> ClosureFeatureVector {
    let mut all: [Vec<f64>; CLOSURE_FEATURE_COUNT] = std::array::from_fn(|_| Vec::new());
    for engine_features in features {
        for f in engine_features {
            for k in 0..CLOSURE_FEATURE_COUNT {
                all[k].push(f[k]);
            }
        }
    }
    let mut scales = [1.0; CLOSURE_FEATURE_COUNT];
    for k in 0..CLOSURE_FEATURE_COUNT {
        let mu = mean(&all[k]);
        let variance = if all[k].len() > 1 {
            all[k].iter().map(|x| (x - mu) * (x - mu)).sum::<f64>() / (all[k].len() as f64 - 1.0)
        } else {
            0.0
        };
        scales[k] = variance.sqrt().max(1e-6);
    }
    scales
}

fn select_closure_pairs(
    engines: &[(u64, SimulationEngine)],
    candidate: &str,
    requested_pairs: usize,
    require_live_anchor: bool,
) -> Vec<ClosurePair> {
    let feature_indices: &[usize] = match candidate {
        "minimal4" => &[0, 1, 2, 3],
        "core5" => &[0, 1, 2, 3, 4],
        "core6spatial" => &[0, 1, 2, 3, 4, 5],
        "operational9" => &[0, 1, 2, 3, 4, 5, 6, 7, 8],
        "competitive11" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "competitive11v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "professionalism12v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "veterancy13v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13],
        "competitive14v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
        "renewal15v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
        "memory15v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15],
        "regenerative16v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "transport15v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16],
        "reaction_transport17v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        "transport12v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16],
        "reaction_transport14v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16],
        "nettransport12v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 17],
        "transportnet13v2" => &[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 17],
        "rootedstock11v3" => &[18, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_hazard12v3" => &[18, 19, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_social12v3" => &[18, 20, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        // V3 synthesis candidates.  Signed net transport was independently
        // identified before the membership representation screen; these
        // candidates combine that flux coordinate with the source-faithful
        // rooted stock, with/without the best development-screen priming
        // coordinate (social exposure).
        "rootedstock_net12v3" => &[18, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_social_net13v3" => &[18, 20, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_hazard_net13v3" => &[18, 19, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_transport_net13v3" => &[18, 16, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        // First-order stock-flow-delay state.  The existing net transport
        // coordinate is retained; four additional coordinates represent the
        // committed inbound/outbound movement masses and their ETA moments.
        "rootedstock_delay16v4" => &[18, 17, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 21, 22, 23, 24],
        // Measurement-correction candidate: same dimensionality as the
        // rooted-stock/net-flux core, but replace intended-order net pressure
        // with command-reliability-weighted executable net flux.
        "rootedstock_execnet12v4" => &[18, 26, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "rootedstock_execnet_ring1_15v5" => {
            &[18, 26, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 27, 28, 29]
        }
        _ => &[0, 1, 2, 3],
    };
    let locality_count = engines
        .first()
        .map(|(_, e)| e.topology.locality_count())
        .unwrap_or(0);
    // Transport pressure is a global movement-choice diagnostic: computing it
    // independently for every locality would repeat the same route/softmax
    // integration O(locality_count) times.  Materialize one vector per engine
    // and reuse it for all candidate states.  This changes no scientific
    // quantity; it only removes redundant probe work.
    let all_features = engines
        .iter()
        .map(|(_, engine)| {
            let transport = pineland_model::movement::inbound_transport_pressures(
                &engine.particle,
                &engine.topology,
                &engine.config,
            );
            let net_transport = pineland_model::movement::insurgent_transport_net_pressures(
                &engine.particle,
                &engine.topology,
                &engine.config,
            );
            let executable_transport =
                pineland_model::movement::executable_inbound_transport_pressures(
                    &engine.particle,
                    &engine.topology,
                    &engine.config,
                );
            let executable_net_transport =
                pineland_model::movement::insurgent_executable_transport_net_pressures(
                    &engine.particle,
                    &engine.topology,
                    &engine.config,
                );
            (0..locality_count)
                .map(|locality| {
                    closure_features_with_transport(
                        engine,
                        locality,
                        transport.get(locality).copied().unwrap_or(0.0),
                        net_transport.get(locality).copied().unwrap_or(0.0),
                        executable_transport.get(locality).copied().unwrap_or(0.0),
                        executable_net_transport
                            .get(locality)
                            .copied()
                            .unwrap_or(0.0),
                    )
                })
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    let scales = feature_scales(&all_features);
    let live_anchor = |engine_index: usize, locality: usize| -> bool {
        if !require_live_anchor {
            return true;
        }
        let engine = &engines[engine_index].1;
        let owner_active = engine
            .particle
            .organizations
            .active
            .get(INSURGENT)
            .copied()
            .unwrap_or(0)
            != 0;
        let capital_positive = engine
            .particle
            .organizations
            .capital
            .get(INSURGENT)
            .copied()
            .unwrap_or(0.0)
            > 1.0e-12;
        let feature = &all_features[engine_index][locality];
        let rooted_positive = feature[18] > 1.0e-12;
        // feature[1] is log1p(local effective canonical-insurgent force).
        // Because owner_active is required separately, this is the corrected
        // active-owner fielded-force gate rather than the legacy status-only
        // formation-record quantity.
        let active_owner_force_positive = feature[1] > 1.0e-12;
        owner_active && capital_positive && rooted_positive && active_owner_force_positive
    };

    let mut ranked_states = Vec::<(f64, usize, usize)>::new();
    for (engine_index, _) in engines.iter().enumerate() {
        for locality in 0..locality_count {
            if !live_anchor(engine_index, locality) {
                continue;
            }
            ranked_states.push((
                closure_activity_score(&all_features[engine_index][locality]),
                engine_index,
                locality,
            ));
        }
    }
    ranked_states.sort_by(|a, b| {
        a.0.total_cmp(&b.0)
            .then_with(|| a.1.cmp(&b.1))
            .then_with(|| a.2.cmp(&b.2))
    });
    let mut activity_band = std::collections::BTreeMap::<(usize, usize), &'static str>::new();
    let ranked_len = ranked_states.len().max(1);
    for (rank, (_, engine_index, locality)) in ranked_states.into_iter().enumerate() {
        let band = match (rank * 3) / ranked_len {
            0 => "low",
            1 => "mid",
            _ => "high",
        };
        activity_band.insert((engine_index, locality), band);
    }
    let mut candidates = Vec::<ClosurePair>::new();
    for locality in 0..locality_count {
        let features: Vec<ClosureFeatureVector> = all_features
            .iter()
            .map(|engine_features| engine_features[locality])
            .collect();
        for left in 0..engines.len() {
            for right in (left + 1)..engines.len() {
                if !live_anchor(left, locality) || !live_anchor(right, locality) {
                    continue;
                }
                let mut squared = 0.0;
                for &k in feature_indices {
                    let z = (features[left][k] - features[right][k]) / scales[k];
                    squared += z * z;
                }
                let Some(&left_stratum) = activity_band.get(&(left, locality)) else {
                    continue;
                };
                let Some(&right_stratum) = activity_band.get(&(right, locality)) else {
                    continue;
                };
                if left_stratum != right_stratum {
                    continue;
                }
                candidates.push(ClosurePair {
                    pair_id: 0,
                    left_engine: left,
                    right_engine: right,
                    left_seed: engines[left].0,
                    right_seed: engines[right].0,
                    locality,
                    distance: squared.sqrt(),
                    stratum: left_stratum.to_string(),
                    left_pre: features[left],
                    right_pre: features[right],
                });
            }
        }
    }
    candidates.sort_by(|a, b| a.distance.total_cmp(&b.distance));

    // Greedy matching prevents one unusually convenient state from dominating
    // the evidence through repeated reuse. Allocate approximately equally over
    // low/mid/high activity strata so trivial dormant states cannot dominate.
    let mut used = std::collections::BTreeSet::<(usize, usize)>::new();
    let mut selected = Vec::new();
    let strata = ["low", "mid", "high"];
    let base_quota = requested_pairs / strata.len();
    let remainder = requested_pairs % strata.len();
    for (si, stratum) in strata.iter().enumerate() {
        let quota = base_quota + usize::from(si < remainder);
        let mut taken = 0usize;
        for pair in candidates.iter().filter(|p| p.stratum == *stratum) {
            let left_key = (pair.left_engine, pair.locality);
            let right_key = (pair.right_engine, pair.locality);
            if used.contains(&left_key) || used.contains(&right_key) {
                continue;
            }
            let mut pair = pair.clone();
            pair.pair_id = selected.len();
            used.insert(left_key);
            used.insert(right_key);
            selected.push(pair);
            taken += 1;
            if taken >= quota {
                break;
            }
        }
    }
    if selected.len() < requested_pairs {
        for pair in &candidates {
            let left_key = (pair.left_engine, pair.locality);
            let right_key = (pair.right_engine, pair.locality);
            if used.contains(&left_key) || used.contains(&right_key) {
                continue;
            }
            let mut pair = pair.clone();
            pair.pair_id = selected.len();
            used.insert(left_key);
            used.insert(right_key);
            selected.push(pair);
            if selected.len() >= requested_pairs {
                break;
            }
        }
    }
    selected
}

fn closure_branch_rows(
    pair: &ClosurePair,
    engines: &[(u64, SimulationEngine)],
    candidate: &str,
    anchor: f64,
    horizon: f64,
    branch: usize,
) -> Result<Vec<String>, String> {
    // Candidate-independent common random numbers.  Cross-candidate closure
    // comparisons are only scientifically interpretable when an identical
    // matched state pair receives the identical continuation streams.  Pair
    // identity is therefore derived from immutable state provenance rather
    // than candidate label or candidate-local pair ordinal.
    let namespace = format!(
        "gt-closure-v3:{}:{}:{}:{}",
        pair.left_seed, pair.right_seed, pair.locality, branch
    );
    let branch_seed = seed_from_namespace(202609300000u64, &namespace, "branch");
    let mut rows = Vec::with_capacity(2);
    for (side, engine_index, pre) in [
        ("L", pair.left_engine, pair.left_pre),
        ("R", pair.right_engine, pair.right_pre),
    ] {
        let mut engine = engines[engine_index].1.clone();
        // Common-random-number future: both sides of a matched pair receive
        // identical fresh process streams. Scheduler contents remain part of
        // the inherited hidden microstate by design.
        engine.config.seed = branch_seed;
        engine.particle.rng = RngStreams::new(branch_seed, namespace.clone());
        engine.configure_particle_execution();
        let pre_org_active = engine
            .particle
            .organizations
            .active
            .get(INSURGENT)
            .copied()
            .unwrap_or(0);
        let base = snapshot_values(&engine, pair.locality);
        let pre_legacy_logf = (1.0 + base[panel_index("f_effective_strength")].max(0.0)).ln();
        let pre_active_owner_logf = if pre_org_active != 0 {
            pre_legacy_logf
        } else {
            0.0
        };
        engine
            .advance_until(anchor + horizon)
            .map_err(|e| format!("closure continuation failed: {e}"))?;
        let final_org_active = engine
            .particle
            .organizations
            .active
            .get(INSURGENT)
            .copied()
            .unwrap_or(0);
        let final_v = snapshot_values(&engine, pair.locality);
        let final_features = closure_features(&engine, pair.locality);

        let e_final = final_v[panel_index("e_foothold_strength")];
        let action_delta =
            (final_v[panel_index("e_cum_actions")] - base[panel_index("e_cum_actions")]).max(0.0);
        let recruit_delta =
            (final_v[panel_index("e_cum_recruits")] - base[panel_index("e_cum_recruits")]).max(0.0);
        let c_final = final_v[panel_index("c_margin")];
        let final_legacy_logf = (1.0 + final_v[panel_index("f_effective_strength")].max(0.0)).ln();
        let final_active_owner_logf = if final_org_active != 0 {
            final_legacy_logf
        } else {
            0.0
        };
        let row = vec![
            pair.pair_id.to_string(),
            candidate.to_string(),
            format!("{anchor:.6}"),
            format!("{horizon:.6}"),
            branch.to_string(),
            side.to_string(),
            pair.left_seed.to_string(),
            pair.right_seed.to_string(),
            pair.locality.to_string(),
            format!("{:.17}", pair.distance),
            pair.stratum.clone(),
            format!("{:.17}", pre[0]),
            format!("{:.17}", pre[1]),
            format!("{:.17}", pre[2]),
            format!("{:.17}", pre[3]),
            format!("{:.17}", pre[4]),
            format!("{:.17}", pre[5]),
            format!("{:.17}", pre[6]),
            format!("{:.17}", pre[7]),
            format!("{:.17}", pre[8]),
            format!("{:.17}", pre[9]),
            format!("{:.17}", pre[10]),
            format!("{:.17}", pre[11]),
            format!("{:.17}", pre[12]),
            format!("{:.17}", pre[13]),
            format!("{:.17}", pre[14]),
            format!("{:.17}", pre[15]),
            format!("{:.17}", pre[16]),
            format!("{:.17}", pre[17]),
            format!("{:.17}", pre[18]),
            format!("{:.17}", pre[19]),
            format!("{:.17}", pre[20]),
            format!("{:.17}", pre[21]),
            format!("{:.17}", pre[22]),
            format!("{:.17}", pre[23]),
            format!("{:.17}", pre[24]),
            format!("{:.17}", pre[25]),
            format!("{:.17}", pre[26]),
            format!("{:.17}", pre[27]),
            format!("{:.17}", pre[28]),
            format!("{:.17}", pre[29]),
            u8::from(e_final >= 0.20).to_string(),
            format!("{:.17}", action_delta.ln_1p()),
            format!("{:.17}", recruit_delta.ln_1p()),
            format!("{:.17}", final_v[panel_index("m_member_depth")]),
            format!(
                "{:.17}",
                (1.0 + final_v[panel_index("f_effective_strength")].max(0.0)).ln()
            ),
            format!("{:.17}", e_final),
            format!("{:.17}", c_final - base[panel_index("c_margin")]),
            format!("{:.17}", c_final),
            format!("{:.17}", final_v[panel_index("c_gov_effective")]),
            format!("{:.17}", final_features[18]),
            format!("{:.17}", final_features[19]),
            format!("{:.17}", final_features[20]),
            format!(
                "{:.17}",
                if final_org_active != 0 { final_features[16] } else { 0.0 }
            ),
            format!(
                "{:.17}",
                if final_org_active != 0 { final_features[17] } else { 0.0 }
            ),
            format!("{:.17}", final_features[21]),
            format!("{:.17}", final_features[22]),
            format!("{:.17}", final_features[23]),
            format!("{:.17}", final_features[24]),
            format!(
                "{:.17}",
                if final_org_active != 0 { final_features[25] } else { 0.0 }
            ),
            format!(
                "{:.17}",
                if final_org_active != 0 { final_features[26] } else { 0.0 }
            ),
            format!("{:.17}", final_features[27]),
            format!("{:.17}", final_features[28]),
            format!("{:.17}", final_features[29]),
            pre_org_active.to_string(),
            final_org_active.to_string(),
            format!("{pre_active_owner_logf:.17}"),
            format!("{final_active_owner_logf:.17}"),
        ];
        rows.push(row.join(","));
    }
    Ok(rows)
}

fn closure_candidate_supported(candidate: &str) -> bool {
    matches!(
        candidate,
        "minimal4"
            | "core5"
            | "core6spatial"
            | "operational9"
            | "competitive11"
            | "competitive11v2"
            | "professionalism12v2"
            | "veterancy13v2"
            | "competitive14v2"
            | "renewal15v2"
            | "memory15v2"
            | "regenerative16v2"
            | "transport15v2"
            | "reaction_transport17v2"
            | "transport12v2"
            | "reaction_transport14v2"
            | "nettransport12v2"
            | "transportnet13v2"
            | "rootedstock11v3"
            | "rootedstock_hazard12v3"
            | "rootedstock_social12v3"
            | "rootedstock_net12v3"
            | "rootedstock_social_net13v3"
            | "rootedstock_hazard_net13v3"
            | "rootedstock_transport_net13v3"
            | "rootedstock_delay16v4"
            | "rootedstock_execnet12v4"
            | "rootedstock_execnet_ring1_15v5"
    )
}

fn closure_candidate_uses_state_regeneration(candidate: &str) -> bool {
    candidate.ends_with("v2")
        || candidate.ends_with("v3")
        || candidate.ends_with("v4")
        || candidate.ends_with("v5")
}

const CLOSURE_CSV_HEADER: &str = "pair_id,candidate,anchor_days,horizon_days,branch,side,left_seed,right_seed,locality,match_distance,stratum,pre_M,pre_logF,pre_E,pre_C,pre_logKo,pre_NM,pre_L,pre_Kintel,pre_X,pre_S,pre_U,pre_police_professionalism,pre_government_veterancy,pre_insurgent_veterancy,pre_renewal_potential,pre_organization_persistence,pre_inbound_transport_pressure,pre_net_transport_pressure,pre_Mstar,pre_recruitment_hazard,pre_social_exposure,pre_pending_incoming_strength,pre_pending_incoming_mean_eta_days,pre_pending_outgoing_strength,pre_pending_outgoing_mean_eta_days,pre_executable_inbound_transport_pressure,pre_executable_net_transport_pressure,pre_neighbor_transportable_strength,pre_neighbor_rooted_mass,pre_neighbor_recruitment_hazard,viable,log1p_actions_delta,log1p_recruits_delta,final_M,final_logF,final_E,control_delta,final_C,final_state_control,final_Mstar,final_recruitment_hazard,final_social_exposure,final_inbound_transport_pressure,final_net_transport_pressure,final_pending_incoming_strength,final_pending_incoming_mean_eta_days,final_pending_outgoing_strength,final_pending_outgoing_mean_eta_days,final_executable_inbound_transport_pressure,final_executable_net_transport_pressure,final_neighbor_transportable_strength,final_neighbor_rooted_mass,final_neighbor_recruitment_hazard,pre_org_active,final_org_active,pre_active_owner_logF,final_active_owner_logF";

fn run_distributional_closure(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../distributional_closure_v2.csv".to_string());
    let pool_seeds: usize = arg(args, 3, 24);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let anchor: f64 = arg(args, 6, 60.0);
    let horizon: f64 = arg(args, 7, 30.0);
    let requested_pairs: usize = arg(args, 8, 24);
    let branches: usize = arg(args, 9, 32);
    let threads: usize = arg(args, 10, 16);
    let candidate = args.get(11).map(|s| s.as_str()).unwrap_or("minimal4");
    let dynamic_seed_base: u64 = arg(args, 12, 2026092000u64);
    let initialization_seed: u64 = arg(args, 13, 2026091900u64);
    let recruitment_multiplier: f64 = arg(args, 14, 1.0f64);
    let require_live_anchor: u8 = arg(args, 15, 0u8);
    let require_live_anchor = require_live_anchor != 0;
    if !closure_candidate_supported(candidate) {
        return Err(format!(
            "candidate must be minimal4, core5, core6spatial, operational9, competitive11, competitive11v2, professionalism12v2, veterancy13v2, competitive14v2, renewal15v2, memory15v2, regenerative16v2, transport15v2, reaction_transport17v2, transport12v2, reaction_transport14v2, nettransport12v2, transportnet13v2, rootedstock11v3, rootedstock_hazard12v3, rootedstock_social12v3, rootedstock_net12v3, rootedstock_social_net13v3, rootedstock_hazard_net13v3, rootedstock_transport_net13v3, rootedstock_delay16v4, rootedstock_execnet12v4, or rootedstock_execnet_ring1_15v5; got {candidate}"
        )
        .into());
    }
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let built: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..pool_seeds)
            .into_par_iter()
            .map(|s| {
                let seed = dynamic_seed_base + s as u64;
                let mut c = synthetic_config(seed, agents, localities, anchor + horizon);
                c.initialization_seed = Some(initialization_seed);
                c.recruitment_rate *= recruitment_multiplier.max(0.0);
                if closure_candidate_uses_state_regeneration(candidate) {
                    c.state_regeneration.enabled = true;
                }
                let mut engine = SimulationEngine::new(c).map_err(|e| e.to_string())?;
                engine.particle_execution = true;
                engine.advance_until(anchor).map_err(|e| e.to_string())?;
                Ok((seed, engine))
            })
            .collect()
    });
    let mut engines = Vec::with_capacity(pool_seeds);
    for result in built {
        engines.push(result.map_err(|e| format!("closure pool generation failed: {e}"))?);
    }
    engines.sort_by_key(|(seed, _)| *seed);
    let pairs = select_closure_pairs(&engines, candidate, requested_pairs, require_live_anchor);
    if pairs.is_empty() {
        return Err("no closure pairs selected".into());
    }
    eprintln!(
        "closure {}: selected {} pairs from {} dynamic seeds; best distance {:.6}, worst {:.6}; recruitment_multiplier={:.6}; live_anchor_filter={}",
        candidate,
        pairs.len(),
        pool_seeds,
        pairs.first().unwrap().distance,
        pairs.last().unwrap().distance,
        recruitment_multiplier,
        require_live_anchor,
    );

    let tasks: Vec<(&ClosurePair, usize)> = pairs
        .iter()
        .flat_map(|pair| (0..branches).map(move |branch| (pair, branch)))
        .collect();
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(pair, branch)| {
                closure_branch_rows(pair, &engines, candidate, anchor, horizon, *branch)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "{CLOSURE_CSV_HEADER}")?;
    for result in results {
        for row in result.map_err(|e| format!("closure branch failed: {e}"))? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out}");
    Ok(())
}

/// Run several closure candidates against one shared anchor-world pool.
///
/// This is scientifically equivalent to invoking `closure` once per candidate
/// when all candidates use the same theory-version gate.  It only removes the
/// redundant initialization + anchor simulation, which is particularly useful
/// during reduced-state searches where candidate matching changes but the
/// underlying world pool does not.
fn run_distributional_closure_battery(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out_dir = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../closure_battery".to_string());
    let candidate_arg = args
        .get(3)
        .cloned()
        .unwrap_or_else(|| "rootedstock_social12v3,rootedstock_net12v3".to_string());
    let candidates = candidate_arg
        .split(',')
        .map(str::trim)
        .filter(|x| !x.is_empty())
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Err("closure-battery requires at least one candidate".into());
    }
    for candidate in &candidates {
        if !closure_candidate_supported(candidate) {
            return Err(format!("unsupported closure candidate in battery: {candidate}").into());
        }
    }
    let regeneration_gate = closure_candidate_uses_state_regeneration(candidates[0]);
    if candidates
        .iter()
        .any(|candidate| closure_candidate_uses_state_regeneration(candidate) != regeneration_gate)
    {
        return Err(
            "closure-battery candidates must share the same state-regeneration theory gate".into(),
        );
    }

    let pool_seeds: usize = arg(args, 4, 48);
    let agents: usize = arg(args, 5, 300);
    let localities: usize = arg(args, 6, 34);
    let anchor: f64 = arg(args, 7, 60.0);
    let horizon: f64 = arg(args, 8, 30.0);
    let requested_pairs: usize = arg(args, 9, 24);
    let branches: usize = arg(args, 10, 32);
    let threads: usize = arg(args, 11, 16);
    let dynamic_seed_base: u64 = arg(args, 12, 2026092000u64);
    let initialization_seed: u64 = arg(args, 13, 2026091900u64);
    let recruitment_multiplier: f64 = arg(args, 14, 1.0f64);
    let require_live_anchor: u8 = arg(args, 15, 0u8);
    let require_live_anchor = require_live_anchor != 0;
    create_dir_all(&out_dir)?;

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let built: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..pool_seeds)
            .into_par_iter()
            .map(|s| {
                let seed = dynamic_seed_base + s as u64;
                let mut c = synthetic_config(seed, agents, localities, anchor + horizon);
                c.initialization_seed = Some(initialization_seed);
                c.recruitment_rate *= recruitment_multiplier.max(0.0);
                c.state_regeneration.enabled = regeneration_gate;
                let mut engine = SimulationEngine::new(c).map_err(|e| e.to_string())?;
                engine.particle_execution = true;
                engine.advance_until(anchor).map_err(|e| e.to_string())?;
                Ok((seed, engine))
            })
            .collect()
    });
    let mut engines = Vec::with_capacity(pool_seeds);
    for result in built {
        engines.push(result.map_err(|e| format!("closure battery pool generation failed: {e}"))?);
    }
    engines.sort_by_key(|(seed, _)| *seed);

    for candidate in candidates {
        let pairs = select_closure_pairs(&engines, candidate, requested_pairs, require_live_anchor);
        if pairs.is_empty() {
            return Err(format!("no closure pairs selected for {candidate}").into());
        }
        let min_distance = pairs
            .iter()
            .map(|pair| pair.distance)
            .fold(f64::INFINITY, f64::min);
        let max_distance = pairs
            .iter()
            .map(|pair| pair.distance)
            .fold(0.0_f64, f64::max);
        eprintln!(
            "closure battery {candidate}: selected {} pairs from {pool_seeds} dynamic seeds; best distance {min_distance:.6}, worst {max_distance:.6}; recruitment_multiplier={recruitment_multiplier:.6}; live_anchor_filter={require_live_anchor}",
            pairs.len()
        );
        let tasks = pairs
            .iter()
            .flat_map(|pair| (0..branches).map(move |branch| (pair, branch)))
            .collect::<Vec<_>>();
        let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
            tasks
                .par_iter()
                .map(|(pair, branch)| {
                    closure_branch_rows(pair, &engines, candidate, anchor, horizon, *branch)
                })
                .collect()
        });
        let out = Path::new(&out_dir).join(format!("{candidate}.csv"));
        let mut writer = BufWriter::new(File::create(&out)?);
        writeln!(writer, "{CLOSURE_CSV_HEADER}")?;
        for result in results {
            for row in result.map_err(|e| format!("closure battery branch failed: {e}"))? {
                writeln!(writer, "{row}")?;
            }
        }
        writer.flush()?;
        println!("wrote {}", out.display());
    }
    Ok(())
}

fn run_closure_hidden_diagnostics(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../closure_hidden_diagnostics.csv".to_string());
    let pool_seeds: usize = arg(args, 3, 36);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let anchor: f64 = arg(args, 6, 60.0);
    let requested_pairs: usize = arg(args, 7, 24);
    let threads: usize = arg(args, 8, 8);
    let candidate = args
        .get(9)
        .map(|s| s.as_str())
        .unwrap_or("nettransport12v2");
    let dynamic_seed_base: u64 = arg(args, 10, 2026107000u64);
    let initialization_seed: u64 = arg(args, 11, 2026106900u64);
    let recruitment_multiplier: f64 = arg(args, 12, 1.0f64);
    let require_live_anchor: u8 = arg(args, 13, 0u8);
    let require_live_anchor = require_live_anchor != 0;
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let built: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..pool_seeds)
            .into_par_iter()
            .map(|s| {
                let seed = dynamic_seed_base + s as u64;
                let mut c = synthetic_config(seed, agents, localities, anchor);
                c.initialization_seed = Some(initialization_seed);
                c.recruitment_rate *= recruitment_multiplier.max(0.0);
                if candidate.ends_with("v2") || candidate.ends_with("v3") || candidate.ends_with("v4") {
                    c.state_regeneration.enabled = true;
                }
                let mut engine = SimulationEngine::new(c).map_err(|e| e.to_string())?;
                engine.particle_execution = true;
                engine.advance_until(anchor).map_err(|e| e.to_string())?;
                Ok((seed, engine))
            })
            .collect()
    });
    let mut engines = Vec::with_capacity(pool_seeds);
    for result in built {
        engines
            .push(result.map_err(|e| format!("closure diagnostic pool generation failed: {e}"))?);
    }
    engines.sort_by_key(|(seed, _)| *seed);
    let pairs = select_closure_pairs(&engines, candidate, requested_pairs, require_live_anchor);
    if pairs.is_empty() {
        return Err("no closure diagnostic pairs selected".into());
    }

    let mut writer = BufWriter::new(File::create(&out)?);
    let mut header = vec![
        "pair_id",
        "candidate",
        "side",
        "seed",
        "other_seed",
        "locality",
        "stratum",
        "match_distance",
    ]
    .into_iter()
    .map(str::to_string)
    .collect::<Vec<_>>();
    header.extend(CLOSURE_HIDDEN_NAMES.iter().map(|x| x.to_string()));
    writeln!(writer, "{}", header.join(","))?;
    for pair in &pairs {
        for (side, engine_index, seed, other_seed) in [
            ("L", pair.left_engine, pair.left_seed, pair.right_seed),
            ("R", pair.right_engine, pair.right_seed, pair.left_seed),
        ] {
            let diagnostic = closure_hidden_diagnostics(&engines[engine_index].1, pair.locality);
            let mut row = vec![
                pair.pair_id.to_string(),
                candidate.to_string(),
                side.to_string(),
                seed.to_string(),
                other_seed.to_string(),
                pair.locality.to_string(),
                pair.stratum.clone(),
                format!("{:.17}", pair.distance),
            ];
            row.extend(diagnostic.iter().map(|v| format!("{v:.17}")));
            writeln!(writer, "{}", row.join(","))?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} pairs={} recruitment_multiplier={:.6} live_anchor_filter={}",
        pairs.len(), recruitment_multiplier, require_live_anchor
    );
    Ok(())
}

fn stress_block_available(engine: &SimulationEngine, locality: usize, block: &str) -> bool {
    let p = &engine.particle;
    match block {
        "police_professionalism" => (0..p.security_posts.personnel.len()).any(|post| {
            p.security_posts.organization[post] as usize == pineland_model::POLICE
                && p.security_posts.locality[post] as usize == locality
                && p.security_posts.staffed[post] != 0
                && p.security_posts.personnel[post] > 0.0
        }),
        "government_veterancy" | "insurgent_veterancy" => {
            let organization = if block == "government_veterancy" {
                pineland_model::MILITARY
            } else {
                INSURGENT
            };
            let opponent = if organization == pineland_model::MILITARY {
                INSURGENT
            } else {
                pineland_model::MILITARY
            };
            let present = |wanted: usize| {
                (0..p.formations.personnel.len()).any(|formation| {
                    p.formations.organization[formation] as usize == wanted
                        && p.formations.locality[formation] as usize == locality
                        && p.formations.active[formation] != 0
                        && p.formations.operational_status[formation] != 0
                        && p.formations.outside_pineland[formation] == 0
                        && p.formations.personnel[formation] > 0.0
                })
            };
            present(organization) && present(opponent)
        }
        _ => false,
    }
}

fn set_stress_block(
    engine: &mut SimulationEngine,
    locality: usize,
    block: &str,
    value: f64,
) -> Result<(), String> {
    let value = value.clamp(0.0, 1.0);
    let p = &mut engine.particle;
    let mut changed = 0usize;
    match block {
        "police_professionalism" => {
            for post in 0..p.security_posts.personnel.len() {
                if p.security_posts.organization[post] as usize == pineland_model::POLICE
                    && p.security_posts.locality[post] as usize == locality
                    && p.security_posts.staffed[post] != 0
                    && p.security_posts.personnel[post] > 0.0
                {
                    p.security_posts.professionalism[post] = value;
                    changed += 1;
                }
            }
        }
        "government_veterancy" | "insurgent_veterancy" => {
            let organization = if block == "government_veterancy" {
                pineland_model::MILITARY
            } else {
                INSURGENT
            };
            for formation in 0..p.formations.personnel.len() {
                if p.formations.organization[formation] as usize == organization
                    && p.formations.locality[formation] as usize == locality
                    && p.formations.active[formation] != 0
                    && p.formations.operational_status[formation] != 0
                    && p.formations.outside_pineland[formation] == 0
                    && p.formations.personnel[formation] > 0.0
                {
                    p.formations.experience[formation] = value;
                    changed += 1;
                }
            }
        }
        _ => return Err(format!("unknown stress block {block}")),
    }
    if changed == 0 {
        return Err(format!(
            "stress block {block} has no eligible local state at locality {locality}"
        ));
    }
    Ok(())
}

fn stress_focals(engine: &SimulationEngine, block: &str, requested: usize) -> Vec<(usize, String)> {
    if requested == 0 {
        return Vec::new();
    }
    let mut candidates = (0..engine.topology.locality_count())
        .filter(|locality| stress_block_available(engine, *locality, block))
        .map(|locality| {
            (
                closure_activity_score(&closure_features(engine, locality)),
                locality,
            )
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|left, right| {
        left.0
            .total_cmp(&right.0)
            .then_with(|| left.1.cmp(&right.1))
    });
    let take = requested.min(candidates.len());
    if take == 0 {
        return Vec::new();
    }
    if take == 1 {
        return vec![(candidates[candidates.len() / 2].1, "mid".to_string())];
    }
    let mut selected = Vec::with_capacity(take);
    for k in 0..take {
        let rank =
            ((k as f64) * ((candidates.len() - 1) as f64) / ((take - 1) as f64)).round() as usize;
        let locality = candidates[rank.min(candidates.len() - 1)].1;
        if selected.iter().any(|(existing, _)| *existing == locality) {
            continue;
        }
        let stratum = if k == 0 {
            "low"
        } else if k + 1 == take {
            "high"
        } else {
            "mid"
        };
        selected.push((locality, stratum.to_string()));
    }
    selected
}

fn stress_hidden_value(features: &ClosureFeatureVector, block: &str) -> f64 {
    match block {
        "police_professionalism" => features[11],
        "government_veterancy" => features[12],
        "insurgent_veterancy" => features[13],
        _ => f64::NAN,
    }
}

fn local_formation_cumulative_losses(
    engine: &SimulationEngine,
    locality: usize,
    organization: usize,
) -> f64 {
    let p = &engine.particle;
    (0..p.formations.personnel.len())
        .filter(|formation| {
            p.formations.organization[*formation] as usize == organization
                && p.formations.locality[*formation] as usize == locality
                && p.formations.outside_pineland[*formation] == 0
        })
        .map(|formation| p.formations.cumulative_losses[formation].max(0.0))
        .sum()
}

fn stress_branch_rows(
    base_engine: &SimulationEngine,
    seed: u64,
    locality: usize,
    stratum: &str,
    block: &str,
    anchor: f64,
    horizon: f64,
    branch: usize,
) -> Result<Vec<String>, String> {
    let pre = closure_features(base_engine, locality);
    let branch_seed = 202610010000u64
        .wrapping_add(seed.wrapping_mul(10_000))
        .wrapping_add((locality as u64).wrapping_mul(100))
        .wrapping_add(branch as u64);
    let namespace = format!("gt-v2-stress:{block}:{seed}:{locality}:{branch}");
    let mut rows = Vec::with_capacity(2);
    for (side, value) in [("low", 0.10), ("high", 0.90)] {
        let mut engine = base_engine.clone();
        set_stress_block(&mut engine, locality, block, value)?;
        let intervened = closure_features(&engine, locality);
        for k in 0..11 {
            if (intervened[k] - pre[k]).abs() > 1.0e-12 {
                return Err(format!(
                    "stress intervention {block} changed competitive11 feature {k}: {} -> {}",
                    pre[k], intervened[k]
                ));
            }
        }
        engine.config.seed = branch_seed;
        engine.particle.rng = RngStreams::new(branch_seed, namespace.clone());
        engine.configure_particle_execution();
        let before = snapshot_values(&engine, locality);
        let before_intelligence =
            engine.particle.locality.government_intelligence_penetration[locality];
        let before_disruption = engine
            .particle
            .locality
            .government_cumulative_underground_disruption[locality];
        let before_government_losses =
            local_formation_cumulative_losses(&engine, locality, pineland_model::MILITARY);
        let before_insurgent_losses =
            local_formation_cumulative_losses(&engine, locality, INSURGENT);
        engine
            .advance_until(anchor + horizon)
            .map_err(|error| format!("stress continuation failed: {error}"))?;
        let final_v = snapshot_values(&engine, locality);
        let final_features = closure_features(&engine, locality);
        let e_final = final_v[panel_index("e_foothold_strength")];
        let action_delta =
            (final_v[panel_index("e_cum_actions")] - before[panel_index("e_cum_actions")]).max(0.0);
        let recruit_delta = (final_v[panel_index("e_cum_recruits")]
            - before[panel_index("e_cum_recruits")])
        .max(0.0);
        let c_final = final_v[panel_index("c_margin")];
        let row = vec![
            block.to_string(),
            seed.to_string(),
            locality.to_string(),
            stratum.to_string(),
            format!("{anchor:.6}"),
            format!("{horizon:.6}"),
            branch.to_string(),
            side.to_string(),
            format!("{value:.17}"),
            format!("{:.17}", stress_hidden_value(&intervened, block)),
            format!("{:.17}", pre[0]),
            format!("{:.17}", pre[1]),
            format!("{:.17}", pre[2]),
            format!("{:.17}", pre[3]),
            format!("{:.17}", pre[4]),
            format!("{:.17}", pre[5]),
            format!("{:.17}", pre[6]),
            format!("{:.17}", pre[7]),
            format!("{:.17}", pre[8]),
            format!("{:.17}", pre[9]),
            format!("{:.17}", pre[10]),
            u8::from(e_final >= 0.20).to_string(),
            format!("{:.17}", action_delta.ln_1p()),
            format!("{:.17}", recruit_delta.ln_1p()),
            format!("{:.17}", final_v[panel_index("m_member_depth")]),
            format!(
                "{:.17}",
                (1.0 + final_v[panel_index("f_effective_strength")].max(0.0)).ln()
            ),
            format!("{:.17}", e_final),
            format!("{:.17}", c_final - before[panel_index("c_margin")]),
            format!("{:.17}", c_final),
            format!("{:.17}", final_v[panel_index("c_gov_effective")]),
            format!(
                "{:.17}",
                engine.particle.locality.government_intelligence_penetration[locality]
                    - before_intelligence
            ),
            format!(
                "{:.17}",
                engine
                    .particle
                    .locality
                    .government_cumulative_underground_disruption[locality]
                    - before_disruption
            ),
            format!(
                "{:.17}",
                local_formation_cumulative_losses(&engine, locality, pineland_model::MILITARY)
                    - before_government_losses
            ),
            format!(
                "{:.17}",
                local_formation_cumulative_losses(&engine, locality, INSURGENT)
                    - before_insurgent_losses
            ),
            format!("{:.17}", stress_hidden_value(&final_features, block)),
        ];
        rows.push(row.join(","));
    }
    Ok(rows)
}

fn run_v2_omitted_state_stress(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../v2_omitted_state_stress.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let anchor: f64 = arg(args, 6, 60.0);
    let horizon: f64 = arg(args, 7, 30.0);
    let focal_count: usize = arg(args, 8, 3);
    let branches: usize = arg(args, 9, 32);
    let threads: usize = arg(args, 10, 16);
    let block = args
        .get(11)
        .map(String::as_str)
        .unwrap_or("police_professionalism");
    if !matches!(
        block,
        "police_professionalism" | "government_veterancy" | "insurgent_veterancy"
    ) {
        return Err(format!(
            "block must be police_professionalism, government_veterancy, or insurgent_veterancy; got {block}"
        )
        .into());
    }
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let built: Vec<Result<(u64, SimulationEngine), String>> = pool.install(|| {
        (0..seed_count)
            .into_par_iter()
            .map(|index| {
                let seed = 2026100200u64 + index as u64;
                let mut config = synthetic_config(seed, agents, localities, anchor + horizon);
                config.state_regeneration.enabled = true;
                let mut engine =
                    SimulationEngine::new(config).map_err(|error| error.to_string())?;
                engine.configure_particle_execution();
                engine
                    .advance_until(anchor)
                    .map_err(|error| error.to_string())?;
                Ok((seed, engine))
            })
            .collect()
    });
    let mut engines = Vec::with_capacity(seed_count);
    for result in built {
        engines.push(result.map_err(|error| format!("stress anchor generation failed: {error}"))?);
    }
    engines.sort_by_key(|(seed, _)| *seed);

    let mut tasks = Vec::<(usize, usize, String, usize)>::new();
    for (engine_index, (_, engine)) in engines.iter().enumerate() {
        let focals = stress_focals(engine, block, focal_count);
        for (locality, stratum) in focals {
            for branch in 0..branches {
                tasks.push((engine_index, locality, stratum.clone(), branch));
            }
        }
    }
    if tasks.is_empty() {
        return Err(format!("no eligible stress tasks for block {block}").into());
    }
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        tasks
            .par_iter()
            .map(|(engine_index, locality, stratum, branch)| {
                let (seed, engine) = &engines[*engine_index];
                stress_branch_rows(
                    engine, *seed, *locality, stratum, block, anchor, horizon, *branch,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "block,seed,locality,stratum,anchor_days,horizon_days,branch,side,assigned_hidden_value,realized_hidden_value,pre_M,pre_logF,pre_E,pre_C,pre_logKo,pre_NM,pre_L,pre_Kintel,pre_X,pre_S,pre_U,viable,log1p_actions_delta,log1p_recruits_delta,final_M,final_logF,final_E,control_delta,final_C,final_state_control,intelligence_delta,underground_disruption_delta,government_formation_losses_delta,insurgent_formation_losses_delta,final_hidden_value")?;
    for result in results {
        for row in result.map_err(|error| format!("stress branch failed: {error}"))? {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} block={block} tasks={}", tasks.len());
    Ok(())
}

fn run_panel(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../macrostate_panel.csv".to_string());
    let seed_count: usize = arg(args, 3, 16);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let horizon: f64 = arg(args, 6, 120.0);
    let step: f64 = arg(args, 7, 30.0);
    let seed_base: u64 = arg(args, 8, 2026091000u64);
    // Optional theory-v2 switch used only for synthetic diagnostics.  The
    // legacy default remains false so archived panel invocations are exactly
    // reproducible.
    let theory_v2 = args
        .get(9)
        .map(|value| matches!(value.as_str(), "1" | "true" | "v2" | "yes"))
        .unwrap_or(false);
    let shared_initialization_seed = args.get(10).and_then(|value| value.parse::<u64>().ok());
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let mut w = BufWriter::new(File::create(&out)?);
    write_panel_header(&mut w, &["seed", "time", "locality", "focal"])?;
    for s in 0..seed_count {
        let seed = seed_base + s as u64;
        let mut c = synthetic_config(seed, agents, localities, horizon);
        c.state_regeneration.enabled = theory_v2;
        if let Some(initialization_seed) = shared_initialization_seed {
            c.initialization_seed = Some(initialization_seed);
        }
        let mut engine = SimulationEngine::new(c)?;
        let focal = focal_locality(&engine);
        let mut t = 0.0;
        loop {
            for loc in 0..engine.topology.locality_count() {
                write_panel_row(
                    &mut w,
                    &[
                        seed.to_string(),
                        format!("{t:.6}"),
                        loc.to_string(),
                        u8::from(loc == focal).to_string(),
                    ],
                    &snapshot_values(&engine, loc),
                )?;
            }
            if t + 1e-9 >= horizon {
                break;
            }
            t = (t + step).min(horizon);
            engine.advance_until(t)?;
        }
        eprintln!("panel seed {}/{} complete", s + 1, seed_count);
    }
    w.flush()?;
    println!("wrote {out}");
    Ok(())
}

fn run_topology_edges(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../topology_edges.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let seed_base: u64 = arg(args, 6, 2026101000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w, "seed,from_locality,to_locality")?;
    for s in 0..seed_count {
        let seed = seed_base.wrapping_add(s as u64);
        // Only initialization is required.  synthetic_config fixes
        // initialization_seed=seed, exactly matching the panel world for the
        // same seed while leaving the scientific production model untouched.
        let engine = SimulationEngine::new(synthetic_config(seed, agents, localities, 1.0))?;
        for from in 0..engine.topology.locality_count() {
            for (to, _) in engine.topology.locality_edges.neighbors(from) {
                writeln!(w, "{seed},{from},{}", to as usize)?;
            }
        }
    }
    w.flush()?;
    println!("wrote {out}");
    Ok(())
}

fn first_insurgent_formation(p: &ParticleState) -> Option<usize> {
    (0..p.formations.personnel.len()).find(|&f| p.formations.organization[f] as usize == INSURGENT)
}

fn apply_channel_factorial(
    engine: &mut SimulationEngine,
    focal: usize,
    m: u8,
    f: u8,
    l: u8,
    k: u8,
    i: u8,
) {
    let nloc = engine.topology.locality_count();
    let p = &mut engine.particle;
    let min_proto = engine
        .config
        .organization_ecology
        .minimum_proto_represented_population
        .max(1.0);
    let min_form = engine
        .config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0);

    // Common clean focal-memory starting point. This is a synthetic intervention,
    // not a historical initialization change.
    let fi = INSURGENT * nloc + focal;
    if fi < p.footholds.strength.len() {
        p.footholds.active[fi] = 1;
        p.footholds.strength[fi] = 0.0;
        p.footholds.raw_signal[fi] = 0.0;
        p.footholds.embeddedness[fi] = 0.0;
        p.footholds.renewal_count[fi] = 0;
        p.footholds.viable_activation_count[fi] = 0;
        p.footholds.cumulative_active_days[fi] = 0.0;
        p.footholds.cumulative_arrivals[fi] = 0.0;
        p.footholds.cumulative_recruits[fi] = 0.0;
        p.footholds.cumulative_actions[fi] = 0.0;
        p.footholds.first_activated_at[fi] = -1.0e9;
        p.footholds.last_activated_at[fi] = -1.0e9;
        p.footholds.updated_at[fi] = 0.0;
        if fi < p.footholds.target_knowledge.len() {
            p.footholds.target_knowledge[fi] = if k == 1 { 1.0 } else { 0.0 };
        }
        if fi < p.footholds.infrastructure.len() {
            p.footholds.infrastructure[fi] = if i == 1 { 1.0 } else { 0.0 };
        }
        if fi < p.footholds.sustainment.len() {
            p.footholds.sustainment[fi] = if l == 1 { 1.0 } else { 0.0 };
        }
    }

    // M: local rooted armed membership. Low removes only focal insurgent membership;
    // high plants enough local rooted membership to exceed the proto scale.
    let people_here = (0..p.people.residence.len())
        .filter(|&x| p.people.residence[x] as usize == focal)
        .collect::<Vec<_>>();
    for &person in &people_here {
        if p.people.organization[person] as usize == INSURGENT {
            p.people.organization[person] = NONE_ORG;
            p.people.armed_fraction[person] = 0.0;
        }
    }
    if m == 1 {
        let mut planted = 0.0;
        for &person in &people_here {
            p.people.organization[person] = INSURGENT as u32;
            p.people.armed_fraction[person] = 1.0;
            if p.people.home[person] as usize != focal {
                p.people.home[person] = focal as u32;
            }
            if p.people.insurgent_affinity.len() >= (person + 1) * p.organizations.kind.len() {
                p.people.insurgent_affinity[person * p.organizations.kind.len() + INSURGENT] = 1.0;
            }
            planted += p.people.represented_population[person].max(0.0);
            if planted >= 1.25 * min_proto {
                break;
            }
        }
    }

    // F: fielded local capacity. Use the existing insurgent formation identity so
    // scheduler/RNG lineage is unchanged; remove other insurgent fielded stocks.
    let focal_zone = engine
        .topology
        .zones_for_locality(focal.into())
        .next()
        .unwrap_or(0);
    let chosen = first_insurgent_formation(p);
    for form in 0..p.formations.personnel.len() {
        if p.formations.organization[form] as usize == INSURGENT {
            p.formations.personnel[form] = 0.0;
            p.formations.supply_stock[form] = 0.0;
        }
    }
    if let Some(form) = chosen {
        p.formations.locality[form] = focal as u32;
        p.formations.microzone[form] = focal_zone as u32;
        p.formations.home_locality[form] = focal as u32;
        p.formations.active[form] = 1;
        p.formations.moving[form] = 0;
        p.formations.outside_pineland[form] = 0;
        p.formations.operational_status[form] = 1;
        p.formations.availability[form] = 1.0;
        p.formations.readiness[form] = 1.0;
        p.formations.command[form] = 0.9;
        p.formations.quality[form] = 0.7;
        p.formations.cohesion[form] = 0.8;
        p.formations.embeddedness[form] = if f == 1 { 1.0 } else { 0.0 };
        p.formations.personnel[form] = if f == 1 { 1.5 * min_form } else { 0.0 };
        p.formations.information[form] = if k == 1 { 0.95 } else { 0.05 };
        let cap =
            (2.0 * min_form * engine.config.logistics.formation_supply_days.max(1.0)).max(1.0);
        p.formations.supply_capacity[form] = cap;
        p.formations.supply_stock[form] = if l == 1 { cap } else { 0.0 };
        p.formations.sustainment[form] = if l == 1 { 1.0 } else { 0.0 };
    }

    // L: local reserve and source system. Keep source identity, relocate one
    // insurgent source to the focal locality, and make low/high persistent.
    for x in 0..p.manpower.pool.len() {
        if p.manpower.organization[x] as usize == INSURGENT
            && p.manpower.locality[x] as usize == focal
        {
            p.manpower.supply_reserve[x] = if l == 1 {
                2.0 * min_form * engine.config.logistics.formation_supply_days.max(1.0)
            } else {
                0.0
            };
        }
    }
    let mut source_done = false;
    for x in 0..p.logistics.source_stock.len() {
        if p.logistics.organization[x] as usize == INSURGENT {
            if !source_done {
                p.logistics.locality[x] = focal as u32;
                let cap = (4.0 * min_form * engine.config.logistics.formation_supply_days.max(1.0))
                    .max(1.0);
                p.logistics.source_capacity[x] = if l == 1 { cap } else { 0.0 };
                p.logistics.source_stock[x] = if l == 1 { cap } else { 0.0 };
                p.logistics.source_production[x] = if l == 1 { cap * 0.02 } else { 0.0 };
                source_done = true;
            } else if l == 0 {
                p.logistics.source_stock[x] = 0.0;
                p.logistics.source_production[x] = 0.0;
            }
        }
    }

    // K: actor-held local information, not hidden opponent truth.
    if INSURGENT < p.organizations.local_knowledge.len() {
        p.organizations.local_knowledge[INSURGENT] = if k == 1 { 0.9 } else { 0.1 };
    }
    for b in 0..p.beliefs.keys.len() {
        let key = &p.beliefs.keys[b];
        if key.observer as usize == INSURGENT
            && key.target as usize == GOVERNMENT
            && key.locality as usize == focal
        {
            p.beliefs.confidence[b] = if k == 1 { 0.95 } else { 0.02 };
            p.beliefs.source_confidence[b] = if k == 1 { 0.95 } else { 0.02 };
            if b * CONTROL_DIMENSIONS + CONTROL_DIMENSIONS <= p.beliefs.control.len() {
                let val = if k == 1 { 0.75 } else { 0.5 };
                p.beliefs.control[b * CONTROL_DIMENSIONS..(b + 1) * CONTROL_DIMENSIONS].fill(val);
            }
        }
    }
    for b in 0..p.presence_beliefs.keys.len() {
        let key = &p.presence_beliefs.keys[b];
        if key.observer as usize == INSURGENT
            && key.target as usize == GOVERNMENT
            && key.locality as usize == focal
        {
            p.presence_beliefs.confidence[b] = if k == 1 { 0.95 } else { 0.02 };
            p.presence_beliefs.estimate[b] = if k == 1 { 0.75 } else { 0.0 };
        }
    }

    // I: local insurgent institutional/shadow-governance capacity. This is the
    // direct institutional channel used by local_embeddedness.
    let value = if i == 1 { 0.75 } else { 0.0 };
    let off = focal * CONTROL_DIMENSIONS;
    for d in [2usize, 3, 4, 5, 6] {
        if off + d < p.locality.insurgent_control.len() {
            p.locality.insurgent_control[off + d] = value;
        }
    }
    if p.locality.organization_control.len()
        >= (focal * p.organizations.kind.len() + INSURGENT + 1) * CONTROL_DIMENSIONS
    {
        let oo = (focal * p.organizations.kind.len() + INSURGENT) * CONTROL_DIMENSIONS;
        for d in [2usize, 3, 4, 5, 6] {
            p.locality.organization_control[oo + d] = value;
        }
    }
    if focal < p.locality.insurgent_governance.len() {
        p.locality.insurgent_governance[focal] = value;
    }
}

fn run_factorial(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../channel_factorial.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let horizon: f64 = arg(args, 6, 90.0);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let mut w = BufWriter::new(File::create(&out)?);
    let mut header = vec!["seed", "cell", "focal", "M", "F", "L", "K", "I"]
        .into_iter()
        .map(str::to_string)
        .collect::<Vec<_>>();
    header.extend(PANEL_COLUMNS.iter().map(|x| format!("init_{x}")));
    header.extend(PANEL_COLUMNS.iter().map(|x| format!("final_{x}")));
    writeln!(w, "{}", header.join(","))?;
    for s in 0..seed_count {
        let seed = 2026091100u64 + s as u64;
        let base = SimulationEngine::new(synthetic_config(seed, agents, localities, horizon))?;
        let focal = focal_locality(&base);
        for cell in 0..32u32 {
            let m = ((cell >> 0) & 1) as u8;
            let f = ((cell >> 1) & 1) as u8;
            let l = ((cell >> 2) & 1) as u8;
            let k = ((cell >> 3) & 1) as u8;
            let i = ((cell >> 4) & 1) as u8;
            let mut e = base.clone();
            apply_channel_factorial(&mut e, focal, m, f, l, k, i);
            let init = snapshot_values(&e, focal);
            e.advance_until(horizon)?;
            let finalv = snapshot_values(&e, focal);
            let mut row = vec![
                seed.to_string(),
                cell.to_string(),
                focal.to_string(),
                m.to_string(),
                f.to_string(),
                l.to_string(),
                k.to_string(),
                i.to_string(),
            ];
            row.extend(init.iter().map(|v| format!("{v:.17}")));
            row.extend(finalv.iter().map(|v| format!("{v:.17}")));
            writeln!(w, "{}", row.join(","))?;
        }
        eprintln!("factorial seed {}/{} complete", s + 1, seed_count);
    }
    w.flush()?;
    println!("wrote {out}");
    Ok(())
}

fn aggregate_endogenous(engine: &SimulationEngine) -> Vec<f64> {
    let p = &engine.particle;
    let n = engine.topology.locality_count();
    let threshold = engine
        .config
        .organization_ecology
        .local_foothold_viability_threshold;
    let mut active = 0.0;
    let mut strength = 0.0;
    let mut armed = 0.0;
    let mut fielded = 0.0;
    let mut ci = 0.0;
    let mut cg = 0.0;
    for loc in 0..n {
        let fi = INSURGENT * n + loc;
        let s = p.footholds.strength.get(fi).copied().unwrap_or(0.0);
        strength += s;
        if s >= threshold {
            active += 1.0;
        }
        ci += p.locality.effective_control(loc, 1);
        cg += p.locality.effective_control(loc, 0);
    }
    for person in 0..p.people.residence.len() {
        if p.people.organization[person] as usize == INSURGENT {
            armed += p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].max(0.0);
        }
    }
    for f in 0..p.formations.personnel.len() {
        if p.formations.organization[f] as usize == INSURGENT
            && p.formations.active[f] != 0
            && p.formations.operational_status[f] == 1
            && p.formations.outside_pineland[f] == 0
        {
            fielded += p.formations.personnel[f].max(0.0);
        }
    }
    vec![
        active,
        strength / n.max(1) as f64,
        armed,
        fielded,
        ci / n.max(1) as f64,
        cg / n.max(1) as f64,
        p.counters.organized_actions as f64,
        p.counters.recruitment,
        p.organizations.active.get(INSURGENT).copied().unwrap_or(0) as f64,
    ]
}

fn run_criticality(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../criticality_sweep.csv".to_string());
    let seed_count: usize = arg(args, 3, 4);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let horizon: f64 = arg(args, 6, 180.0);
    let step: f64 = arg(args, 7, 30.0);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let mut w = BufWriter::new(File::create(&out)?);
    writeln!(w,"seed,recruitment_mult,memory_mult,fielding_mult,time,active_footholds,mean_foothold_strength,total_armed_membership,total_fielded_personnel,mean_insurgent_control,mean_government_control,total_actions,total_recruitment,insurgent_org_active")?;
    let rvals = [0.25, 0.5, 1.0, 2.0, 4.0];
    let mvals = [0.5, 1.0, 2.0];
    let fvals = [0.5, 1.0, 2.0];
    for s in 0..seed_count {
        let seed = 2026091200u64 + s as u64;
        for &rm in &rvals {
            for &mm in &mvals {
                for &fm in &fvals {
                    let mut c = synthetic_config(seed, agents, localities, horizon);
                    c.foreign_affairs.enabled = false; // closed-system criticality: no immigration/support term u_t
                    c.recruitment_rate *= rm;
                    c.organization_ecology.local_foothold_memory_days *= mm;
                    c.organization_ecology.fighter_conversion_fraction =
                        (c.organization_ecology.fighter_conversion_fraction * fm).clamp(0.0, 1.0);
                    let mut e = SimulationEngine::new(c)?;
                    let mut t = 0.0;
                    loop {
                        let vals = aggregate_endogenous(&e);
                        let mut row = vec![
                            seed.to_string(),
                            rm.to_string(),
                            mm.to_string(),
                            fm.to_string(),
                            format!("{t:.6}"),
                        ];
                        row.extend(vals.iter().map(|v| format!("{v:.17}")));
                        writeln!(w, "{}", row.join(","))?;
                        if t + 1e-9 >= horizon {
                            break;
                        }
                        t = (t + step).min(horizon);
                        e.advance_until(t)?;
                    }
                }
            }
        }
        eprintln!("criticality seed {}/{} complete", s + 1, seed_count);
    }
    w.flush()?;
    println!("wrote {out}");
    Ok(())
}

fn reset_insurgent_reproductive_state(engine: &mut SimulationEngine) {
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
            p.footholds.updated_at[foothold] = 0.0;
            p.footholds.first_activated_at[foothold] = -1.0e9;
            p.footholds.last_activated_at[foothold] = -1.0e9;
            p.footholds.cumulative_active_days[foothold] = 0.0;
            p.footholds.cumulative_arrivals[foothold] = 0.0;
            p.footholds.cumulative_recruits[foothold] = 0.0;
            p.footholds.cumulative_actions[foothold] = 0.0;
            p.footholds.viable_activation_count[foothold] = 0;
            p.footholds.renewal_count[foothold] = 0;
            p.footholds.active[foothold] = 1;
        }
    }

    // Background proto-organizations are disabled for the impulse assay.
    for status in &mut p.protos.status {
        *status = 3;
    }

    if INSURGENT < p.organizations.external_support.len() {
        p.organizations.external_support[INSURGENT] = 0.0;
        p.organizations.external_sanctuary[INSURGENT] = 0.0;
        p.organizations.active[INSURGENT] = 1;
    }
    for index in 0..p.access_restrictions.owner.len() {
        if p.access_restrictions.owner[index] as usize == INSURGENT {
            p.access_restrictions.level[index] = 0.0;
            p.access_restrictions.cumulative_effort[index] = 0.0;
        }
    }
}

fn plant_parent(engine: &mut SimulationEngine, origin: usize, parent_type: &str) {
    if parent_type == "none" {
        return;
    }
    let p = &mut engine.particle;
    let nloc = engine.topology.locality_count();
    let org_count = p.organizations.kind.len();
    let min_proto = engine
        .config
        .organization_ecology
        .minimum_proto_represented_population
        .max(1.0);
    let min_form = engine
        .config
        .organization_ecology
        .minimum_formation_personnel
        .max(1.0);
    let has_membership = parent_type.contains('M');
    let has_formation = parent_type.contains('F');
    let has_governance = parent_type.contains('G');

    if has_membership {
        // Exactly one threshold-equivalent unit of rooted armed membership.
        // Fractional armed_fraction on the final representative person avoids
        // overshooting the unit merely because representative weights are coarse.
        let target = min_proto;
        let mut planted = 0.0;
        for person in 0..p.people.residence.len() {
            if p.people.residence[person] as usize != origin || planted >= target {
                continue;
            }
            let represented = p.people.represented_population[person].max(0.0);
            if represented <= 0.0 {
                continue;
            }
            let fraction = ((target - planted) / represented).clamp(0.0, 1.0);
            if fraction <= 0.0 {
                continue;
            }
            p.people.organization[person] = INSURGENT as u32;
            p.people.armed_fraction[person] = fraction;
            p.people.home[person] = origin as u32;
            p.people.public_behavior[person] = 2;
            if org_count > INSURGENT && p.people.social_exposure.len() >= (person + 1) * org_count {
                p.people.social_exposure[person * org_count + INSURGENT] = 1.0;
            }
            planted += represented * fraction;
        }
    }

    if has_formation {
        if let Some(formation) = first_insurgent_formation(p) {
            let zone = engine
                .topology
                .primary_zone
                .get(origin)
                .copied()
                .unwrap_or(0) as usize;
            let personnel = min_form;
            p.formations.locality[formation] = origin as u32;
            p.formations.microzone[formation] = zone as u32;
            p.formations.home_locality[formation] = origin as u32;
            p.formations.active[formation] = 1;
            p.formations.operational_status[formation] = 1;
            p.formations.moving[formation] = 0;
            p.formations.outside_pineland[formation] = 0;
            p.formations.personnel[formation] = personnel;
            p.formations.availability[formation] = 1.0;
            p.formations.readiness[formation] = 1.0;
            p.formations.quality[formation] = 0.75;
            p.formations.cohesion[formation] = 0.85;
            p.formations.command[formation] = 0.9;
            p.formations.embeddedness[formation] = 1.0;
            p.formations.information[formation] = 0.9;
            let capacity =
                (2.0 * personnel * engine.config.logistics.formation_supply_days.max(1.0)).max(1.0);
            p.formations.supply_capacity[formation] = capacity;
            p.formations.supply_stock[formation] = capacity;
            p.formations.sustainment[formation] = 1.0;
        }
    }

    if has_governance {
        let offset = origin * CONTROL_DIMENSIONS;
        for dimension in [2usize, 3, 4, 5, 6] {
            if offset + dimension < p.locality.insurgent_control.len() {
                p.locality.insurgent_control[offset + dimension] = engine
                    .config
                    .organization_ecology
                    .local_foothold_viability_threshold;
            }
        }
        if org_count > INSURGENT {
            let org_offset = (origin * org_count + INSURGENT) * CONTROL_DIMENSIONS;
            if p.locality.organization_control.len() >= org_offset + CONTROL_DIMENSIONS {
                for dimension in [2usize, 3, 4, 5, 6] {
                    p.locality.organization_control[org_offset + dimension] = engine
                        .config
                        .organization_ecology
                        .local_foothold_viability_threshold;
                }
            }
        }
        if origin < p.locality.insurgent_governance.len() {
            p.locality.insurgent_governance[origin] = engine
                .config
                .organization_ecology
                .local_foothold_viability_threshold;
        }
    }

    let foothold = INSURGENT * nloc + origin;
    if foothold < p.footholds.strength.len() {
        let value = engine
            .config
            .organization_ecology
            .local_foothold_viability_threshold;
        p.footholds.strength[foothold] = value;
        p.footholds.raw_signal[foothold] = value;
        p.footholds.embeddedness[foothold] = value;
        p.footholds.renewal_count[foothold] = 1;
        p.footholds.viable_activation_count[foothold] = 1;
        p.footholds.first_activated_at[foothold] = 0.0;
        p.footholds.last_activated_at[foothold] = 0.0;
    }
}

fn rooted_member_mass(p: &ParticleState, locality: usize) -> f64 {
    (0..p.people.residence.len())
        .filter(|&person| {
            p.people.organization[person] as usize == INSURGENT
                && p.people.residence[person] as usize == locality
                && p.people.home[person] as usize == locality
        })
        .map(|person| {
            p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].max(0.0)
        })
        .sum()
}

fn home_fielded_mass(p: &ParticleState, locality: usize) -> f64 {
    (0..p.formations.personnel.len())
        .filter(|&formation| {
            p.formations.organization[formation] as usize == INSURGENT
                && p.formations.home_locality[formation] as usize == locality
                && p.formations.active[formation] != 0
                && p.formations.operational_status[formation] == 1
                && p.formations.outside_pineland[formation] == 0
        })
        .map(|formation| p.formations.personnel[formation].max(0.0))
        .sum()
}

fn governance_capacity(p: &ParticleState, locality: usize) -> f64 {
    let offset = locality * CONTROL_DIMENSIONS;
    if p.locality.insurgent_control.len() < offset + CONTROL_DIMENSIONS {
        return 0.0;
    }
    [2usize, 3, 4, 5, 6]
        .iter()
        .map(|&dimension| p.locality.insurgent_control[offset + dimension])
        .sum::<f64>()
        / 5.0
}

fn child_signature(engine: &SimulationEngine, locality: usize) -> Option<&'static str> {
    let foothold = INSURGENT * engine.topology.locality_count() + locality;
    let viable = engine
        .particle
        .footholds
        .strength
        .get(foothold)
        .copied()
        .unwrap_or(0.0)
        >= engine
            .config
            .organization_ecology
            .local_foothold_viability_threshold;
    if !viable {
        return None;
    }
    let m = rooted_member_mass(&engine.particle, locality)
        >= engine
            .config
            .organization_ecology
            .minimum_proto_represented_population;
    let f = home_fielded_mass(&engine.particle, locality)
        >= engine
            .config
            .organization_ecology
            .minimum_formation_personnel;
    let g = governance_capacity(&engine.particle, locality)
        >= engine
            .config
            .organization_ecology
            .local_foothold_viability_threshold;
    // E-only viability is intentionally not reproduction: it can be created
    // by a relocated formation or transient memory without any locally rooted
    // membership, locally generated force, or shadow-governance capacity.
    match (m, f, g) {
        (true, false, false) => Some("M"),
        (false, true, false) => Some("F"),
        (false, false, true) => Some("G"),
        (true, true, false) => Some("MF"),
        (true, false, true) => Some("MG"),
        (false, true, true) => Some("FG"),
        (true, true, true) => Some("MFG"),
        (false, false, false) => None,
    }
}

fn child_present(engine: &SimulationEngine, locality: usize, child_type: &str) -> bool {
    let foothold = INSURGENT * engine.topology.locality_count() + locality;
    let viable = engine
        .particle
        .footholds
        .strength
        .get(foothold)
        .copied()
        .unwrap_or(0.0)
        >= engine
            .config
            .organization_ecology
            .local_foothold_viability_threshold;
    if !viable {
        return false;
    }
    match child_type {
        "M" => {
            rooted_member_mass(&engine.particle, locality)
                >= engine
                    .config
                    .organization_ecology
                    .minimum_proto_represented_population
        }
        "F" => {
            home_fielded_mass(&engine.particle, locality)
                >= engine
                    .config
                    .organization_ecology
                    .minimum_formation_personnel
        }
        "G" => {
            governance_capacity(&engine.particle, locality)
                >= engine
                    .config
                    .organization_ecology
                    .local_foothold_viability_threshold
        }
        _ => false,
    }
}

fn sterilize_child_locality(engine: &mut SimulationEngine, locality: usize, parent_origin: usize) {
    let p = &mut engine.particle;
    let nloc = engine.topology.locality_count();
    let org_count = p.organizations.kind.len();

    for person in 0..p.people.residence.len() {
        if p.people.organization[person] as usize == INSURGENT
            && p.people.home[person] as usize == locality
        {
            p.people.organization[person] = NONE_ORG;
            p.people.armed_fraction[person] = 0.0;
            if matches!(p.people.public_behavior[person], 1 | 2) {
                p.people.public_behavior[person] = 0;
            }
        }
    }
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize == INSURGENT
            && p.formations.home_locality[formation] as usize == locality
            && locality != parent_origin
        {
            p.formations.personnel[formation] = 0.0;
            p.formations.supply_stock[formation] = 0.0;
            p.formations.active[formation] = 0;
            p.formations.operational_status[formation] = 0;
        }
    }
    for index in 0..p.manpower.pool.len() {
        if p.manpower.organization[index] as usize == INSURGENT
            && p.manpower.locality[index] as usize == locality
        {
            p.manpower.pool[index] = 0.0;
            p.manpower.supply_reserve[index] = 0.0;
        }
    }
    for index in 0..p.logistics.source_stock.len() {
        if p.logistics.organization[index] as usize == INSURGENT
            && p.logistics.locality[index] as usize == locality
        {
            p.logistics.source_stock[index] = 0.0;
            p.logistics.source_capacity[index] = 0.0;
            p.logistics.source_production[index] = 0.0;
        }
    }

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
            p.locality.organization_control[org_offset..org_offset + CONTROL_DIMENSIONS].fill(0.0);
        }
    }

    let foothold = INSURGENT * nloc + locality;
    if foothold < p.footholds.strength.len() {
        p.footholds.strength[foothold] = 0.0;
        p.footholds.raw_signal[foothold] = 0.0;
        p.footholds.membership[foothold] = 0.0;
        p.footholds.embeddedness[foothold] = 0.0;
        p.footholds.renewal_count[foothold] = 0;
        p.footholds.viable_activation_count[foothold] = 0;
    }
}

fn locality_graph_metrics(
    topology: &pineland_core::topology::StaticTopology,
    origin: usize,
) -> (Vec<usize>, Vec<f64>) {
    let n = topology.locality_count();
    let mut hops = vec![usize::MAX; n];
    if origin < n {
        let mut queue = std::collections::VecDeque::new();
        hops[origin] = 0;
        queue.push_back(origin);
        while let Some(node) = queue.pop_front() {
            let next_hops = hops[node].saturating_add(1);
            for (neighbor, _) in topology.locality_edges.neighbors(node) {
                let neighbor = neighbor as usize;
                if neighbor < n && hops[neighbor] == usize::MAX {
                    hops[neighbor] = next_hops;
                    queue.push_back(neighbor);
                }
            }
        }
    }

    // Tiny synthetic locality graphs make an O(n^2) Dijkstra preferable to
    // adding heap-order/tie semantics to a scientific probe.
    let mut path_cost = vec![f64::INFINITY; n];
    let mut visited = vec![false; n];
    if origin < n {
        path_cost[origin] = 0.0;
    }
    for _ in 0..n {
        let mut best = None::<usize>;
        for node in 0..n {
            if visited[node] || !path_cost[node].is_finite() {
                continue;
            }
            if best
                .map(|current| {
                    path_cost[node] < path_cost[current]
                        || (path_cost[node] == path_cost[current] && node < current)
                })
                .unwrap_or(true)
            {
                best = Some(node);
            }
        }
        let Some(node) = best else { break };
        visited[node] = true;
        for (neighbor, edge_cost) in topology.locality_edges.neighbors(node) {
            let neighbor = neighbor as usize;
            if neighbor >= n || visited[neighbor] {
                continue;
            }
            let candidate = path_cost[node] + edge_cost.max(0.0);
            if candidate < path_cost[neighbor] {
                path_cost[neighbor] = candidate;
            }
        }
    }
    (hops, path_cost)
}

fn parent_social_kernel_features(
    particle: &ParticleState,
    origin: usize,
    locality_count: usize,
) -> (Vec<f64>, Vec<usize>, Vec<f64>) {
    let people_count = particle.people.residence.len();
    let planted = (0..people_count)
        .filter(|&person| {
            particle.people.organization[person] as usize == INSURGENT
                && particle.people.residence[person] as usize == origin
                && particle.people.home[person] as usize == origin
                && particle.people.armed_fraction[person] > 0.0
        })
        .collect::<Vec<_>>();
    let planted_mask = {
        let mut mask = vec![false; people_count];
        for &person in &planted {
            mask[person] = true;
        }
        mask
    };

    // Build the same undirected social graph carried by the packed edge table.
    // Edge indices are retained so influence uses exactly weight*trust*
    // represented_relationships, matching the production social process.
    let mut adjacency = vec![Vec::<(usize, usize)>::new(); people_count];
    for edge in 0..particle.social_edges.person_a.len() {
        let a = particle.social_edges.person_a[edge] as usize;
        let b = particle.social_edges.person_b[edge] as usize;
        if a < people_count && b < people_count {
            adjacency[a].push((b, edge));
            adjacency[b].push((a, edge));
        }
    }
    for neighbors in &mut adjacency {
        neighbors.sort_by_key(|(neighbor, edge)| (*neighbor, *edge));
    }

    let disconnected = people_count.saturating_add(1);
    let mut social_hops = vec![disconnected; people_count];
    let mut queue = std::collections::VecDeque::new();
    for &person in &planted {
        social_hops[person] = 0;
        queue.push_back(person);
    }
    while let Some(person) = queue.pop_front() {
        let next_hops = social_hops[person].saturating_add(1);
        for &(neighbor, _) in &adjacency[person] {
            if social_hops[neighbor] == disconnected {
                social_hops[neighbor] = next_hops;
                queue.push_back(neighbor);
            }
        }
    }

    let mut exposure_weighted = vec![0.0; locality_count];
    let mut structural_weighted = vec![0.0; locality_count];
    let mut population_weight = vec![0.0; locality_count];
    let mut locality_min_hops = vec![disconnected; locality_count];

    for person in 0..people_count {
        let locality = particle.people.residence[person] as usize;
        if locality >= locality_count {
            continue;
        }
        let represented = particle.people.represented_population[person].max(0.0);
        let mut total_influence = 0.0;
        let mut planted_influence = 0.0;
        let mut origin_influence = 0.0;
        for &(neighbor, edge) in &adjacency[person] {
            let influence = particle.social_edges.weight[edge]
                * particle.social_edges.trust[edge]
                * particle.social_edges.represented_relationships[edge];
            total_influence += influence;
            if planted_mask[neighbor] {
                planted_influence +=
                    influence * particle.people.armed_fraction[neighbor].clamp(0.0, 1.0);
            }
            if particle.people.residence[neighbor] as usize == origin {
                origin_influence += influence;
            }
        }
        let exposure = if total_influence > 0.0 {
            (planted_influence / total_influence).clamp(0.0, 1.0)
        } else {
            0.0
        };
        let structural = if total_influence > 0.0 {
            (origin_influence / total_influence).clamp(0.0, 1.0)
        } else {
            0.0
        };
        exposure_weighted[locality] += represented * exposure;
        structural_weighted[locality] += represented * structural;
        population_weight[locality] += represented;
        locality_min_hops[locality] = locality_min_hops[locality].min(social_hops[person]);
    }

    let mut exposure = vec![0.0; locality_count];
    let mut structural = vec![0.0; locality_count];
    for locality in 0..locality_count {
        if population_weight[locality] > 0.0 {
            exposure[locality] = exposure_weighted[locality] / population_weight[locality];
            structural[locality] = structural_weighted[locality] / population_weight[locality];
        }
    }
    (exposure, locality_min_hops, structural)
}

fn first_nonzero_recruitment_hazard(
    engine: &SimulationEngine,
    max_time: f64,
) -> Result<(f64, Vec<f64>), String> {
    let mut probe = engine.clone();
    probe.configure_particle_execution();
    loop {
        let Some(next) = probe.particle.scheduler.peek() else {
            return Ok((f64::NAN, vec![0.0; probe.topology.locality_count()]));
        };
        if next.time > max_time + 1.0e-12 {
            return Ok((f64::NAN, vec![0.0; probe.topology.locality_count()]));
        }
        if next.payload.kind() == "recruitment" && next.elapsed_days > 1.0e-12 {
            let hazard = pineland_model::recruitment::recruitment_hazard_mass_by_locality(
                &probe.particle,
                &probe.topology,
                &probe.config,
                INSURGENT,
            );
            if hazard.iter().sum::<f64>() > 0.0 {
                return Ok((next.time, hazard));
            }
        }
        let event_time = next.time;
        let processed = probe
            .advance_until_limited(event_time, Some(1))
            .map_err(|error| error.to_string())?;
        if processed != 1 {
            return Err(format!(
                "first-recruitment hazard probe expected one event at {event_time}, processed {processed}"
            ));
        }
    }
}

#[allow(dead_code)]
struct SterileRecruitmentKernel {
    first_nonzero_time: f64,
    first_nonzero_hazard: Vec<f64>,
    cumulative_30: Vec<f64>,
    cumulative_90: Vec<f64>,
    cumulative_180: Vec<f64>,
}

#[allow(dead_code)]
fn sterile_recruitment_kernel(
    engine: &SimulationEngine,
) -> Result<SterileRecruitmentKernel, String> {
    let mut probe = engine.clone();
    let recruitment_rate = probe.config.recruitment_rate;
    // Sterilize membership reproduction while leaving every propagation,
    // behavioral, political, mobility, and access process untouched. The
    // diagnostic config below restores the production recruitment rate only
    // for the pure hazard calculation, never for state transitions.
    probe.config.recruitment_rate = 0.0;
    probe.configure_particle_execution();
    let n = probe.topology.locality_count();
    let mut first_nonzero_time = f64::NAN;
    let mut first_nonzero_hazard = vec![0.0; n];
    let mut cumulative_30 = vec![0.0; n];
    let mut cumulative_90 = vec![0.0; n];
    let mut cumulative_180 = vec![0.0; n];

    loop {
        let Some(next) = probe.particle.scheduler.peek() else {
            break;
        };
        if next.time > 180.0 + 1.0e-12 {
            break;
        }
        if next.payload.kind() == "recruitment" && next.elapsed_days > 1.0e-12 {
            let mut diagnostic_config = probe.config.clone();
            diagnostic_config.recruitment_rate = recruitment_rate;
            let hazard = pineland_model::recruitment::recruitment_hazard_mass_by_locality(
                &probe.particle,
                &probe.topology,
                &diagnostic_config,
                INSURGENT,
            );
            if !first_nonzero_time.is_finite() && hazard.iter().sum::<f64>() > 0.0 {
                first_nonzero_time = next.time;
                first_nonzero_hazard.clone_from(&hazard);
            }
            let dt = next.elapsed_days.max(0.0);
            for locality in 0..n {
                let increment = hazard[locality] * dt;
                if next.time <= 30.0 + 1.0e-12 {
                    cumulative_30[locality] += increment;
                }
                if next.time <= 90.0 + 1.0e-12 {
                    cumulative_90[locality] += increment;
                }
                if next.time <= 180.0 + 1.0e-12 {
                    cumulative_180[locality] += increment;
                }
            }
        }
        let event_time = next.time;
        let processed = probe
            .advance_until_limited(event_time, Some(1))
            .map_err(|error| error.to_string())?;
        if processed != 1 {
            return Err(format!(
                "sterile recruitment kernel expected one event at {event_time}, processed {processed}"
            ));
        }
    }
    Ok(SterileRecruitmentKernel {
        first_nonzero_time,
        first_nonzero_hazard,
        cumulative_30,
        cumulative_90,
        cumulative_180,
    })
}

fn reproduction_first_hazard_case(
    seed: u64,
    agents: usize,
    localities: usize,
    origin: usize,
    parent_type: &str,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, 30.0);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.proto_base_hazard = 0.0;
    config.organization_ecology.birth_base_hazard = 0.0;
    config.organization_ecology.split_base_hazard = 0.0;
    config.organization_ecology.merger_base_hazard = 0.0;
    config.organization_ecology.succession_base_hazard = 0.0;
    config.organization_ecology.adaptation_rate = 0.0;
    config.output_mode = "ensemble".to_string();
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    if origin >= engine.topology.locality_count() {
        return Ok(Vec::new());
    }
    reset_insurgent_reproductive_state(&mut engine);
    plant_parent(&mut engine, origin, parent_type);

    let immediate = pineland_model::recruitment::recruitment_hazard_mass_by_locality(
        &engine.particle,
        &engine.topology,
        &engine.config,
        INSURGENT,
    );
    let (first_nonzero_time, first_nonzero_hazard) =
        first_nonzero_recruitment_hazard(&engine, 60.0)?;
    let immediate_total = immediate.iter().sum::<f64>();
    let first_total = first_nonzero_hazard.iter().sum::<f64>();
    let mut rows = Vec::with_capacity(engine.topology.locality_count());
    for destination in 0..engine.topology.locality_count() {
        rows.push(format!(
            "{seed},{origin},{destination},{parent_type},{first_nonzero_time:.17},{:.17},{:.17},{immediate_total:.17},{first_total:.17},{:.17},{:.17}",
            immediate[destination],
            first_nonzero_hazard[destination],
            if immediate_total > 0.0 { immediate[destination] / immediate_total } else { 0.0 },
            if first_total > 0.0 { first_nonzero_hazard[destination] / first_total } else { 0.0 },
        ));
    }
    Ok(rows)
}

fn run_reproduction_first_hazard(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../reproduction_first_hazard.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 17);
    let threads: usize = arg(args, 6, 16);
    let seed_base: u64 = arg(args, 7, 2026102000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let mut cases = Vec::new();
    for seed_index in 0..seed_count {
        let seed = seed_base + seed_index as u64;
        for origin in 0..localities {
            for parent_type in ["M", "MF", "MG", "MFG"] {
                cases.push((seed, origin, parent_type.to_string()));
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, origin, parent_type)| {
                reproduction_first_hazard_case(*seed, agents, localities, *origin, parent_type)
            })
            .collect()
    });
    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,origin,destination,parent_type,first_nonzero_hazard_time,immediate_hazard_mass,first_nonzero_hazard_mass,immediate_total_hazard,first_nonzero_total_hazard,immediate_hazard_share,first_nonzero_hazard_share")?;
    for result in results {
        let rows =
            result.map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
        for row in rows {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn reproduction_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    origin: usize,
    parent_type: &str,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    // Prevent unrelated organizational births/splits from being counted as
    // offspring of the planted parent. Existing INSURGENT organization
    // phenotype remains as the actor-level Theta context.
    config.organization_ecology.proto_base_hazard = 0.0;
    config.organization_ecology.birth_base_hazard = 0.0;
    config.organization_ecology.split_base_hazard = 0.0;
    config.organization_ecology.merger_base_hazard = 0.0;
    config.organization_ecology.succession_base_hazard = 0.0;
    config.organization_ecology.adaptation_rate = 0.0;
    config.output_mode = "ensemble".to_string();
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    if origin >= engine.topology.locality_count() {
        return Ok(Vec::new());
    }
    reset_insurgent_reproductive_state(&mut engine);
    plant_parent(&mut engine, origin, parent_type);
    let (locality_graph_hops, locality_graph_path_cost) =
        locality_graph_metrics(&engine.topology, origin);
    let (parent_social_exposure_potential, parent_social_min_hops, cross_locality_social_influence) =
        parent_social_kernel_features(&engine.particle, origin, engine.topology.locality_count());
    engine.configure_particle_execution();

    let locality_count = engine.topology.locality_count();
    let mut first_hit = vec![None::<(f64, String, String)>; locality_count];
    loop {
        let Some(next) = engine.particle.scheduler.peek() else {
            break;
        };
        if next.time > horizon {
            break;
        }
        let trigger = next.payload.kind().to_string();
        let processed = engine
            .advance_until_limited(horizon, Some(1))
            .map_err(|error| error.to_string())?;
        if processed == 0 {
            break;
        }
        let now = engine.particle.time;
        let newly_present = (0..locality_count)
            .filter_map(|locality| {
                if locality == origin || first_hit[locality].is_some() {
                    return None;
                }
                child_signature(&engine, locality)
                    .map(|signature| (locality, signature.to_string()))
            })
            .collect::<Vec<_>>();
        for (locality, signature) in newly_present {
            first_hit[locality] = Some((now, trigger.clone(), signature));
            // Sterilize immediately: counted children cannot generate
            // grandchildren in this first-generation next-generation assay.
            sterilize_child_locality(&mut engine, locality, origin);
        }
    }

    let adjacent = engine
        .topology
        .locality_edges
        .neighbors(origin)
        .map(|(locality, _)| locality as usize)
        .collect::<Vec<_>>();
    let mut rows = Vec::with_capacity(locality_count.saturating_sub(1));
    for destination in 0..locality_count {
        if destination == origin {
            continue;
        }
        let dx = engine
            .topology
            .x_km
            .get(destination)
            .copied()
            .unwrap_or(0.0)
            - engine.topology.x_km.get(origin).copied().unwrap_or(0.0);
        let dy = engine
            .topology
            .y_km
            .get(destination)
            .copied()
            .unwrap_or(0.0)
            - engine.topology.y_km.get(origin).copied().unwrap_or(0.0);
        let (hit, time, trigger, child_type) = match &first_hit[destination] {
            Some((time, trigger, child_type)) => (1, *time, trigger.as_str(), child_type.as_str()),
            None => (0, f64::NAN, "", ""),
        };
        let graph_hops = locality_graph_hops[destination];
        let graph_hops_value = if graph_hops == usize::MAX {
            (locality_count + 1) as f64
        } else {
            graph_hops as f64
        };
        let graph_cost = locality_graph_path_cost[destination];
        rows.push(format!(
            "{seed},{origin},{destination},{parent_type},{child_type},{hit},{time:.17},{trigger},{},{:.17},{graph_hops_value:.17},{graph_cost:.17},{:.17},{},{:.17}",
            u8::from(adjacent.contains(&destination)),
            (dx * dx + dy * dy).sqrt(),
            parent_social_exposure_potential[destination],
            parent_social_min_hops[destination],
            cross_locality_social_influence[destination],
        ));
    }
    Ok(rows)
}

fn run_reproduction_impulse(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../reproduction_impulse.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 17);
    let horizon: f64 = arg(args, 6, 90.0);
    let threads: usize = arg(args, 7, 16);
    let seed_base: u64 = arg(args, 8, 2026091300u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let mut test_config = synthetic_config(seed_base, agents, localities, horizon);
    test_config.foreign_affairs.enabled = false;
    let test_engine = SimulationEngine::new(test_config)?;
    let locality_count = test_engine.topology.locality_count();
    drop(test_engine);

    let mut cases = Vec::new();
    for seed_index in 0..seed_count {
        let seed = seed_base + seed_index as u64;
        for origin in 0..locality_count {
            for parent_type in ["none", "E", "M", "F", "G", "MF", "MG", "FG", "MFG"] {
                cases.push((seed, origin, parent_type.to_string()));
            }
        }
    }

    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(seed, origin, parent_type)| {
                reproduction_case(*seed, agents, localities, horizon, *origin, parent_type)
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,origin,destination,parent_type,child_type,child,first_time,trigger_event,adjacent_origin,distance_km,locality_graph_hops,locality_graph_path_cost,parent_social_exposure_potential,parent_social_min_hops,cross_locality_social_influence"
    )?;
    for result in results {
        let rows =
            result.map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
        for row in rows {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!(
        "wrote {out} cases={} localities={locality_count}",
        cases.len()
    );
    Ok(())
}

fn mobilization_snapshot(engine: &SimulationEngine) -> Vec<f64> {
    let p = &engine.particle;
    let nloc = engine.topology.locality_count();
    let mut armed = 0.0;
    let mut fielded = 0.0;
    let mut active_footholds = 0.0;
    let mut fiscal_control = 0.0;
    for person in 0..p.people.residence.len() {
        if p.people.organization[person] as usize == INSURGENT {
            armed += p.people.represented_population[person].max(0.0)
                * p.people.armed_fraction[person].max(0.0);
        }
    }
    for formation in 0..p.formations.personnel.len() {
        if p.formations.organization[formation] as usize == INSURGENT
            && p.formations.active[formation] != 0
            && p.formations.operational_status[formation] == 1
            && p.formations.outside_pineland[formation] == 0
        {
            fielded += p.formations.personnel[formation].max(0.0);
        }
    }
    let threshold = engine
        .config
        .organization_ecology
        .local_foothold_viability_threshold;
    for locality in 0..nloc {
        let foothold = INSURGENT * nloc + locality;
        if p.footholds.strength.get(foothold).copied().unwrap_or(0.0) >= threshold {
            active_footholds += 1.0;
        }
        let offset = locality * CONTROL_DIMENSIONS;
        if offset + 4 < p.locality.insurgent_control.len() {
            fiscal_control += p.locality.insurgent_control[offset + 4];
        }
    }
    let active = p.organizations.active.get(INSURGENT).copied().unwrap_or(0) as f64;
    let capital = p
        .organizations
        .capital
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0);
    let cohesion = p
        .organizations
        .cohesion
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0);
    let capital_material = p
        .organizations
        .capital_material
        .get(INSURGENT)
        .copied()
        .unwrap_or(0.0);
    vec![
        active,
        capital,
        cohesion,
        capital_material,
        armed,
        fielded,
        active_footholds,
        fiscal_control / nloc.max(1) as f64,
        p.counters.recruitment,
    ]
}

fn mobilization_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    step: f64,
    recruitment_mult: f64,
    fielding_mult: f64,
    capital_mult: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    // Isolate the focal organization.  Its own collapse process, economy,
    // recruitment, logistics, combat, and foothold dynamics remain active.
    config.organization_ecology.proto_base_hazard = 0.0;
    config.organization_ecology.birth_base_hazard = 0.0;
    config.organization_ecology.split_base_hazard = 0.0;
    config.organization_ecology.merger_base_hazard = 0.0;
    config.organization_ecology.succession_base_hazard = 0.0;
    config.recruitment_rate *= recruitment_mult;
    config.organization_ecology.fighter_conversion_fraction =
        (config.organization_ecology.fighter_conversion_fraction * fielding_mult).clamp(0.0, 1.0);

    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    if INSURGENT >= engine.particle.organizations.capital.len() {
        return Err("canonical insurgent organization missing".to_string());
    }
    let base_capital = engine.particle.organizations.capital[INSURGENT];
    engine.particle.organizations.capital[INSURGENT] = (base_capital * capital_mult).max(0.0);
    if INSURGENT < engine.particle.organizations.capital_material.len() {
        engine.particle.organizations.capital_material[INSURGENT] =
            (engine.particle.organizations.capital[INSURGENT] / 150_000.0).clamp(0.0, 1.0);
    }

    let mut rows = Vec::new();
    let mut t = 0.0;
    loop {
        let values = mobilization_snapshot(&engine);
        rows.push(format!(
            "{seed},{recruitment_mult:.17},{fielding_mult:.17},{capital_mult:.17},{:.17},{:.17},{t:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            recruitment_mult * fielding_mult / capital_mult.max(1.0e-12),
            base_capital,
            values[0],
            values[1],
            values[2],
            values[3],
            values[4],
            values[5],
            values[6],
            values[7],
            values[8],
        ));
        if t + 1.0e-9 >= horizon {
            break;
        }
        t = (t + step).min(horizon);
        engine.advance_until(t).map_err(|error| error.to_string())?;
    }
    Ok(rows)
}

#[derive(Clone, Debug, Default)]
struct CapitalFlowLedger {
    positive: f64,
    negative: f64,
    economy_positive: f64,
    recruitment_negative: f64,
    other_abs: f64,
}

fn advance_with_capital_ledger(
    engine: &mut SimulationEngine,
    until: f64,
    organization: usize,
    ledger: &mut CapitalFlowLedger,
) -> Result<(), String> {
    loop {
        let Some(next) = engine.particle.scheduler.peek() else {
            break;
        };
        if next.time > until + 1.0e-12 {
            break;
        }
        let event_time = next.time;
        let event_kind = next.payload.kind().to_string();
        let before = engine
            .particle
            .organizations
            .capital
            .get(organization)
            .copied()
            .unwrap_or(0.0);
        let processed = engine
            .advance_until_limited(event_time, Some(1))
            .map_err(|error| error.to_string())?;
        if processed != 1 {
            return Err(format!(
                "capital ledger expected one event at {event_time}, processed {processed}"
            ));
        }
        let after = engine
            .particle
            .organizations
            .capital
            .get(organization)
            .copied()
            .unwrap_or(0.0);
        let delta = after - before;
        if delta > 0.0 {
            ledger.positive += delta;
            if event_kind == "economy" {
                ledger.economy_positive += delta;
            } else {
                ledger.other_abs += delta;
            }
        } else if delta < 0.0 {
            let burn = -delta;
            ledger.negative += burn;
            if event_kind == "recruitment" {
                ledger.recruitment_negative += burn;
            } else {
                ledger.other_abs += burn;
            }
        }
    }
    Ok(())
}

fn mobilization_ledger_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    step: f64,
    recruitment_mult: f64,
    fielding_mult: f64,
    capital_mult: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.proto_base_hazard = 0.0;
    config.organization_ecology.birth_base_hazard = 0.0;
    config.organization_ecology.split_base_hazard = 0.0;
    config.organization_ecology.merger_base_hazard = 0.0;
    config.organization_ecology.succession_base_hazard = 0.0;
    config.recruitment_rate *= recruitment_mult;
    config.organization_ecology.fighter_conversion_fraction =
        (config.organization_ecology.fighter_conversion_fraction * fielding_mult).clamp(0.0, 1.0);

    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    if INSURGENT >= engine.particle.organizations.capital.len() {
        return Err("canonical insurgent organization missing".to_string());
    }
    let base_capital = engine.particle.organizations.capital[INSURGENT];
    let initial_capital = (base_capital * capital_mult).max(0.0);
    engine.particle.organizations.capital[INSURGENT] = initial_capital;
    if INSURGENT < engine.particle.organizations.capital_material.len() {
        engine.particle.organizations.capital_material[INSURGENT] =
            (initial_capital / 150_000.0).clamp(0.0, 1.0);
    }

    let mut ledger = CapitalFlowLedger::default();
    let mut rows = Vec::new();
    let mut t = 0.0;
    loop {
        let values = mobilization_snapshot(&engine);
        let capital = values[1];
        let expected = initial_capital + ledger.positive - ledger.negative;
        let residual = capital - expected;
        let denominator = initial_capital + ledger.positive;
        let lambda_k = if denominator > 1.0e-12 {
            ledger.negative / denominator
        } else if ledger.negative > 0.0 {
            f64::INFINITY
        } else {
            0.0
        };
        rows.push(format!(
            "{seed},{recruitment_mult:.17},{fielding_mult:.17},{capital_mult:.17},{base_capital:.17},{initial_capital:.17},{t:.6},{:.17},{capital:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{residual:.17},{lambda_k:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            values[0],
            ledger.positive,
            ledger.negative,
            ledger.economy_positive,
            ledger.recruitment_negative,
            ledger.other_abs,
            values[2],
            values[4],
            values[5],
            values[6],
            values[8],
        ));
        if t + 1.0e-9 >= horizon {
            break;
        }
        t = (t + step).min(horizon);
        advance_with_capital_ledger(&mut engine, t, INSURGENT, &mut ledger)?;
    }
    Ok(rows)
}

fn run_mobilization_resource_ledger(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../mobilization_resource_ledger.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let horizon: f64 = arg(args, 6, 180.0);
    let step: f64 = arg(args, 7, 15.0);
    let threads: usize = arg(args, 8, 16);
    let seed_base: u64 = arg(args, 9, 2026108000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let recruitment_values = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0];
    let fielding_values = [0.25, 0.5, 1.0, 2.0];
    let capital_values = [0.25, 0.5, 1.0, 2.0, 4.0];
    let mut cases = Vec::new();
    for seed_index in 0..seed_count {
        let seed = seed_base + seed_index as u64;
        for &recruitment in &recruitment_values {
            for &fielding in &fielding_values {
                for &capital in &capital_values {
                    cases.push((seed, recruitment, fielding, capital));
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
            .map(|(seed, recruitment, fielding, capital)| {
                mobilization_ledger_case(
                    *seed,
                    agents,
                    localities,
                    horizon,
                    step,
                    *recruitment,
                    *fielding,
                    *capital,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,recruitment_mult,fielding_mult,capital_mult,base_capital,initial_capital,time,org_active,capital,capital_inflow,capital_outflow,economy_positive,recruitment_negative,other_abs_flow,accounting_residual,lambda_k,cohesion,armed_membership,fielded_personnel,active_footholds,cumulative_recruitment")?;
    for result in results {
        let rows =
            result.map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
        for row in rows {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn run_mobilization_trap(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../mobilization_trap.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let horizon: f64 = arg(args, 6, 180.0);
    let step: f64 = arg(args, 7, 15.0);
    let threads: usize = arg(args, 8, 16);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let recruitment_values = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0];
    let fielding_values = [0.25, 0.5, 1.0, 2.0];
    let capital_values = [0.25, 0.5, 1.0, 2.0, 4.0];
    let mut cases = Vec::new();
    for seed_index in 0..seed_count {
        let seed = 2026091400u64 + seed_index as u64;
        for &recruitment in &recruitment_values {
            for &fielding in &fielding_values {
                for &capital in &capital_values {
                    cases.push((seed, recruitment, fielding, capital));
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
            .map(|(seed, recruitment, fielding, capital)| {
                mobilization_case(
                    *seed,
                    agents,
                    localities,
                    horizon,
                    step,
                    *recruitment,
                    *fielding,
                    *capital,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,recruitment_mult,fielding_mult,capital_mult,strain_proxy,base_capital,time,org_active,capital,cohesion,capital_material,armed_membership,fielded_personnel,active_footholds,mean_insurgent_fiscal_control,cumulative_recruitment")?;
    for result in results {
        let rows =
            result.map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
        for row in rows {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn neutralize_insurgent_for_state_regeneration(engine: &mut SimulationEngine) {
    // Reuse the synthetic reproductive-state reset, then make the canonical
    // insurgent organization inactive.  With organization ecology disabled
    // this prevents new insurgent recruitment/organizational activity while
    // leaving all government transition equations untouched.
    reset_insurgent_reproductive_state(engine);
    if INSURGENT < engine.particle.organizations.active.len() {
        engine.particle.organizations.active[INSURGENT] = 0;
        engine.particle.organizations.member_population[INSURGENT] = 0.0;
    }
}

fn local_state_institution(engine: &SimulationEngine, locality: usize) -> Option<usize> {
    let index = 6 + engine.topology.district_count() + locality;
    (index < engine.particle.political.institution_capacity.len()).then_some(index)
}

fn state_regeneration_snapshot(
    engine: &SimulationEngine,
    locality: usize,
) -> Result<Vec<f64>, String> {
    let p = &engine.particle;
    let institution = local_state_institution(engine, locality)
        .ok_or_else(|| format!("missing local institution for locality {locality}"))?;
    let offset = locality * CONTROL_DIMENSIONS;
    if p.locality.government_control.len() < offset + CONTROL_DIMENSIONS {
        return Err(format!(
            "missing government control row for locality {locality}"
        ));
    }
    let government_capital = p
        .organizations
        .capital
        .get(GOVERNMENT)
        .copied()
        .unwrap_or(0.0);
    Ok(vec![
        p.political.institution_capacity[institution],
        p.political.institution_reach[institution],
        p.political.institution_integrity[institution],
        p.political.institution_compliance[institution],
        p.locality.effective_control(locality, 0),
        p.locality.government_control[offset],
        p.locality.government_control[offset + 1],
        p.locality.government_control[offset + 2],
        p.locality.government_control[offset + 3],
        p.locality.government_control[offset + 4],
        p.locality.government_control[offset + 5],
        p.locality.government_control[offset + 6],
        p.locality.administrative_capacity[locality],
        p.locality.government_governance[locality],
        government_capital,
        p.locality.economic_output[locality],
        p.locality.infrastructure[locality],
        p.locality.population[locality],
    ])
}

fn state_regeneration_case(
    seed: u64,
    agents: usize,
    localities: usize,
    horizon: f64,
    step: f64,
    focal: usize,
    capital_mult: f64,
    shock_fraction: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, horizon);
    config.foreign_affairs.enabled = false;
    config.organization_ecology.enabled = false;
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    if focal >= engine.topology.locality_count() {
        return Err(format!("focal locality {focal} outside generated topology"));
    }
    neutralize_insurgent_for_state_regeneration(&mut engine);

    if GOVERNMENT >= engine.particle.organizations.capital.len() {
        return Err("canonical government organization missing".to_string());
    }
    let base_government_capital = engine.particle.organizations.capital[GOVERNMENT];
    engine.particle.organizations.capital[GOVERNMENT] =
        (base_government_capital * capital_mult).max(0.0);

    let institution = local_state_institution(&engine, focal)
        .ok_or_else(|| format!("missing local institution for locality {focal}"))?;
    let baseline_institution_capacity = engine.particle.political.institution_capacity[institution];
    let baseline_control = engine.particle.locality.effective_control(focal, 0);
    let baseline_structural_admin = engine.particle.locality.administrative_capacity[focal];
    engine.particle.political.institution_capacity[institution] =
        (baseline_institution_capacity * shock_fraction).clamp(0.0, 1.0);
    let offset = focal * CONTROL_DIMENSIONS;
    // Administrative, legal, social, and expected control are the local
    // governance dimensions shocked by the preregistered design.  Formal,
    // physical, and fiscal control remain as pre-shock context.
    for dimension in [2usize, 3, 5, 6] {
        engine.particle.locality.government_control[offset + dimension] =
            (engine.particle.locality.government_control[offset + dimension] * shock_fraction)
                .clamp(0.0, 1.0);
    }

    let mut rows = Vec::new();
    let mut t = 0.0;
    loop {
        let v = state_regeneration_snapshot(&engine, focal)?;
        rows.push(format!(
            "{seed},{focal},{capital_mult:.17},{shock_fraction:.17},{base_government_capital:.17},{baseline_institution_capacity:.17},{baseline_control:.17},{baseline_structural_admin:.17},{t:.6},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17}",
            v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[10], v[11], v[12], v[13], v[14], v[15], v[16], v[17]
        ));
        if t + 1.0e-9 >= horizon {
            break;
        }
        t = (t + step).min(horizon);
        engine.advance_until(t).map_err(|error| error.to_string())?;
    }
    Ok(rows)
}

fn evenly_spaced_capacity_focals(engine: &SimulationEngine, count: usize) -> Vec<usize> {
    let n = engine.topology.locality_count();
    if n == 0 || count == 0 {
        return Vec::new();
    }
    let mut ranked = (0..n)
        .filter_map(|locality| {
            local_state_institution(engine, locality).map(|institution| {
                (
                    locality,
                    engine.particle.political.institution_capacity[institution],
                )
            })
        })
        .collect::<Vec<_>>();
    ranked.sort_by(|left, right| {
        left.1
            .total_cmp(&right.1)
            .then_with(|| left.0.cmp(&right.0))
    });
    let take = count.min(ranked.len());
    if take == 1 {
        return vec![ranked[ranked.len() / 2].0];
    }
    let mut selected = Vec::with_capacity(take);
    for k in 0..take {
        let rank =
            ((k as f64) * ((ranked.len() - 1) as f64) / ((take - 1) as f64)).round() as usize;
        let locality = ranked[rank.min(ranked.len() - 1)].0;
        if !selected.contains(&locality) {
            selected.push(locality);
        }
    }
    selected
}

fn run_state_regeneration_metadata(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../state_regeneration_metadata.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let focal_count: usize = arg(args, 6, 8);
    let seed_base: u64 = arg(args, 7, 2026093100u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(
        writer,
        "seed,focal,capital_mult,population,base_government_capital,government_capital,static_admin_ceiling,baseline_admin,admin_max_interval_gain,admin_full_unit_affordability,admin_affordability_ratio,security_max_interval_recruits,security_max_training_cost,security_training_affordability_ratio"
    )?;
    for seed_index in 0..seed_count {
        let seed = seed_base + seed_index as u64;
        let mut config = synthetic_config(seed, agents, localities, 0.0);
        config.foreign_affairs.enabled = false;
        config.organization_ecology.enabled = false;
        let reference = SimulationEngine::new(config)?;
        let focals = evenly_spaced_capacity_focals(&reference, focal_count);
        let base_capital = reference.particle.organizations.capital[GOVERNMENT].max(0.0);
        let dt = reference.config.state_regeneration.interval_days.max(0.0);
        let admin_max_interval_gain = 1.0
            - (-reference
                .config
                .state_regeneration
                .administrative_rebuild_rate
                .max(0.0)
                * dt)
                .exp();
        for focal in focals {
            let population = reference.particle.locality.population[focal].max(1.0);
            let static_admin_ceiling = reference
                .topology
                .locality_administrative_capacity
                .get(focal)
                .copied()
                .unwrap_or(1.0)
                .clamp(0.0, 1.0);
            let baseline_admin = reference.particle.locality.administrative_capacity[focal];
            for capital_mult in [0.25, 0.5, 1.0, 2.0, 4.0] {
                let capital = base_capital * capital_mult;
                let admin_unit_cost = population
                    * reference
                        .config
                        .state_regeneration
                        .administrative_rebuild_cost;
                let admin_full_unit_affordability = if admin_unit_cost > 0.0 {
                    capital / admin_unit_cost
                } else {
                    f64::INFINITY
                };
                let admin_affordability_ratio = if admin_max_interval_gain > 0.0 {
                    admin_full_unit_affordability / admin_max_interval_gain
                } else {
                    f64::INFINITY
                };
                let security_max_interval_recruits = population
                    * reference
                        .config
                        .state_regeneration
                        .security_recruitment_rate
                        .max(0.0)
                    * dt;
                let security_max_training_cost = security_max_interval_recruits
                    * reference
                        .config
                        .state_regeneration
                        .training_cost_per_person
                        .max(0.0);
                let security_training_affordability_ratio = if security_max_training_cost > 0.0 {
                    capital / security_max_training_cost
                } else {
                    f64::INFINITY
                };
                writeln!(
                    writer,
                    "{seed},{focal},{capital_mult:.17},{population:.17},{base_capital:.17},{capital:.17},{static_admin_ceiling:.17},{baseline_admin:.17},{admin_max_interval_gain:.17},{admin_full_unit_affordability:.17},{admin_affordability_ratio:.17},{security_max_interval_recruits:.17},{security_max_training_cost:.17},{security_training_affordability_ratio:.17}"
                )?;
            }
        }
    }
    writer.flush()?;
    println!("wrote {out}");
    Ok(())
}

fn formation_index_for_org(
    engine: &SimulationEngine,
    organization: usize,
) -> Result<usize, String> {
    engine
        .particle
        .formations
        .organization
        .iter()
        .enumerate()
        .find(|(index, value)| {
            **value as usize == organization
                && engine.particle.formations.active[*index] != 0
                && engine.particle.formations.personnel[*index] > 0.0
        })
        .map(|(index, _)| index)
        .ok_or_else(|| format!("missing active formation for organization {organization}"))
}

fn normalize_veterancy_pair(
    engine: &mut SimulationEngine,
    first: usize,
    second: usize,
    first_experience: f64,
    second_experience: f64,
) {
    let locality = engine.particle.formations.locality[first];
    let microzone = engine.particle.formations.microzone[first];
    for (formation, experience) in [(first, first_experience), (second, second_experience)] {
        engine.particle.formations.locality[formation] = locality;
        engine.particle.formations.home_locality[formation] = locality;
        engine.particle.formations.microzone[formation] = microzone;
        engine.particle.formations.personnel[formation] = 300.0;
        engine.particle.formations.quality[formation] = 0.75;
        engine.particle.formations.experience[formation] = experience;
        engine.particle.formations.cohesion[formation] = 0.90;
        engine.particle.formations.readiness[formation] = 1.0;
        engine.particle.formations.sustainment[formation] = 1.0;
        engine.particle.formations.information[formation] = 0.50;
        engine.particle.formations.mobility[formation] = 0.50;
        engine.particle.formations.command[formation] = 0.80;
        engine.particle.formations.embeddedness[formation] = 0.50;
        engine.particle.formations.fatigue[formation] = 0.0;
        engine.particle.formations.availability[formation] = 1.0;
        engine.particle.formations.supply_capacity[formation] = 1.0e9;
        engine.particle.formations.supply_stock[formation] = 1.0e9;
        engine.particle.formations.active[formation] = 1;
        engine.particle.formations.moving[formation] = 0;
        engine.particle.formations.operational_status[formation] = 1;
        engine.particle.formations.cumulative_losses[formation] = 0.0;
        engine.particle.formations.outside_pineland[formation] = 0;
        engine.particle.formations.movement_status[formation] = 0;
        engine.particle.formations.movement_destination[formation] = u32::MAX;
        engine.particle.formations.movement_origin[formation] = u32::MAX;
    }
}

fn controlled_veterancy_case(
    replicate: usize,
    seed_base: u64,
    side: &str,
    experience: f64,
    engagements: usize,
) -> Result<String, String> {
    let seed = seed_base + replicate as u64;
    let mut config = synthetic_config(seed, 120, 12, engagements as f64 + 1.0);
    config.state_regeneration.enabled = true;
    config.foreign_affairs.enabled = false;
    config.organization_ecology.enabled = false;
    let mut engine = SimulationEngine::new(config.clone()).map_err(|error| error.to_string())?;
    let military = formation_index_for_org(&engine, MILITARY)?;
    let insurgent = formation_index_for_org(&engine, INSURGENT)?;
    let (first, second, tested_org) = if side == "government" {
        (military, insurgent, MILITARY)
    } else {
        (insurgent, military, INSURGENT)
    };
    normalize_veterancy_pair(&mut engine, first, second, experience, 0.50);
    let initial_first = engine.particle.formations.personnel[first];
    let initial_second = engine.particle.formations.personnel[second];
    let mut rng = PyRandomCompat::from_seed(seed);
    let mut single_loss = 0.0;
    let mut single_opponent_loss = 0.0;
    let mut tactical_win = false;
    let mut completed = 0usize;
    for engagement in 0..engagements {
        if engine.particle.formations.operational_status[first] == 0
            || engine.particle.formations.operational_status[second] == 0
            || engine.particle.formations.personnel[first] <= 0.0
            || engine.particle.formations.personnel[second] <= 0.0
        {
            break;
        }
        engine.particle.formations.moving[first] = 0;
        engine.particle.formations.moving[second] = 0;
        engine.particle.formations.outside_pineland[first] = 0;
        engine.particle.formations.outside_pineland[second] = 0;
        let before_first = engine.particle.formations.personnel[first];
        let before_second = engine.particle.formations.personnel[second];
        pineland_model::combat::resolve_organized_engagement(
            &mut engine.particle,
            &engine.topology,
            &config,
            &mut rng,
            engagement as f64 + 1.0,
            first,
            second,
            tested_org,
            true,
        );
        let loss_first = (before_first - engine.particle.formations.personnel[first]).max(0.0);
        let loss_second = (before_second - engine.particle.formations.personnel[second]).max(0.0);
        if engagement == 0 {
            single_loss = loss_first / before_first.max(1.0e-12);
            single_opponent_loss = loss_second / before_second.max(1.0e-12);
            tactical_win = single_opponent_loss > single_loss;
        }
        completed += 1;
    }
    let final_first = engine.particle.formations.personnel[first].max(0.0);
    let final_second = engine.particle.formations.personnel[second].max(0.0);
    let own_losses = (initial_first - final_first).max(0.0);
    let opponent_losses = (initial_second - final_second).max(0.0);
    let combat_effective =
        engine.particle.formations.operational_status[first] != 0 && final_first > 0.0;
    let opponent_effective =
        engine.particle.formations.operational_status[second] != 0 && final_second > 0.0;
    let exchange = if own_losses > 1.0e-12 {
        opponent_losses / own_losses
    } else if opponent_losses > 0.0 {
        f64::INFINITY
    } else {
        1.0
    };
    Ok(format!(
        "controlled,{seed},{replicate},{side},{experience:.17},0.50000000000000000,{completed},{single_loss:.17},{single_opponent_loss:.17},{},{},{},{exchange:.17},{:.17},{:.17},{:.17},{:.17}",
        u8::from(tactical_win),
        u8::from(combat_effective),
        u8::from(opponent_effective),
        final_first / initial_first,
        final_second / initial_second,
        engine.particle.formations.experience[first],
        engine.particle.formations.experience[second],
    ))
}

fn run_veterancy_controlled(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../veterancy_controlled.csv".to_string());
    let replicates: usize = arg(args, 3, 1024);
    let engagements: usize = arg(args, 4, 12);
    let threads: usize = arg(args, 5, 16);
    let seed_base: u64 = arg(args, 6, 2026110000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let experience_levels = [0.1, 0.3, 0.5, 0.7, 0.9];
    let mut cases = Vec::new();
    for replicate in 0..replicates {
        for side in ["government", "insurgent"] {
            for experience in experience_levels {
                cases.push((replicate, side.to_string(), experience));
            }
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let rows: Vec<Result<String, String>> = pool.install(|| {
        cases
            .par_iter()
            .map(|(replicate, side, experience)| {
                controlled_veterancy_case(*replicate, seed_base, side, *experience, engagements)
            })
            .collect()
    });
    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "assay,seed,replicate,side,initial_experience,opponent_initial_experience,engagements_completed,single_loss_fraction,single_opponent_loss_fraction,single_tactical_win,campaign_combat_effective,campaign_opponent_combat_effective,campaign_loss_exchange_ratio,final_personnel_fraction,opponent_final_personnel_fraction,final_experience,opponent_final_experience")?;
    for row in rows {
        writeln!(
            writer,
            "{}",
            row.map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?
        )?;
    }
    writer.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn naturalistic_veterancy_seed(
    seed: u64,
    agents: usize,
    localities: usize,
    anchor: f64,
    horizon: f64,
) -> Result<Vec<String>, String> {
    let mut config = synthetic_config(seed, agents, localities, horizon);
    config.state_regeneration.enabled = true;
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    engine.configure_particle_execution();
    engine
        .advance_until(anchor)
        .map_err(|error| error.to_string())?;
    #[derive(Clone)]
    struct Anchor {
        formation: usize,
        side: &'static str,
        experience: f64,
        quality: f64,
        personnel: f64,
        readiness: f64,
        cohesion: f64,
        supply_fraction: f64,
        command: f64,
        embeddedness: f64,
        availability: f64,
        cumulative_losses: f64,
    }
    let mut anchors = Vec::new();
    for formation in 0..engine.particle.formations.personnel.len() {
        let organization = engine.particle.formations.organization[formation] as usize;
        let side = if organization == MILITARY {
            "government"
        } else if organization == INSURGENT {
            "insurgent"
        } else {
            continue;
        };
        if engine.particle.formations.active[formation] == 0
            || engine.particle.formations.operational_status[formation] == 0
            || engine.particle.formations.personnel[formation] <= 0.0
            || engine.particle.formations.outside_pineland[formation] != 0
        {
            continue;
        }
        anchors.push(Anchor {
            formation,
            side,
            experience: engine.particle.formations.experience[formation],
            quality: engine.particle.formations.quality[formation],
            personnel: engine.particle.formations.personnel[formation],
            readiness: engine.particle.formations.readiness[formation],
            cohesion: engine.particle.formations.cohesion[formation],
            supply_fraction: engine.particle.formations.supply_fraction(formation),
            command: engine.particle.formations.command[formation],
            embeddedness: engine.particle.formations.embeddedness[formation],
            availability: engine.particle.formations.availability[formation],
            cumulative_losses: engine.particle.formations.cumulative_losses[formation],
        });
    }
    engine
        .advance_until(horizon)
        .map_err(|error| error.to_string())?;
    let mut rows = Vec::with_capacity(anchors.len());
    for a in anchors {
        let exists = a.formation < engine.particle.formations.personnel.len();
        let final_personnel = if exists {
            engine.particle.formations.personnel[a.formation].max(0.0)
        } else {
            0.0
        };
        let final_losses = if exists {
            engine.particle.formations.cumulative_losses[a.formation]
        } else {
            a.cumulative_losses
        };
        let final_experience = if exists {
            engine.particle.formations.experience[a.formation]
        } else {
            0.0
        };
        let effective = exists
            && engine.particle.formations.active[a.formation] != 0
            && engine.particle.formations.operational_status[a.formation] != 0
            && final_personnel > 0.0;
        let personnel_ratio = final_personnel / a.personnel.max(1.0e-12);
        let future_loss_fraction =
            (final_losses - a.cumulative_losses).max(0.0) / a.personnel.max(1.0e-12);
        rows.push(format!(
            "naturalistic,{seed},{},{},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{:.17},{},{:.17},{:.17},{:.17}",
            a.formation,
            a.side,
            a.experience,
            a.quality,
            a.personnel,
            a.readiness,
            a.cohesion,
            a.supply_fraction,
            a.command,
            a.embeddedness,
            a.availability,
            u8::from(effective),
            personnel_ratio,
            future_loss_fraction,
            final_experience,
        ));
    }
    Ok(rows)
}

fn run_veterancy_naturalistic(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../veterancy_naturalistic.csv".to_string());
    let seeds: usize = arg(args, 3, 32);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let anchor: f64 = arg(args, 6, 60.0);
    let horizon: f64 = arg(args, 7, 180.0);
    let threads: usize = arg(args, 8, 16);
    let seed_base: u64 = arg(args, 9, 2026111000u64);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()?;
    let results: Vec<Result<Vec<String>, String>> = pool.install(|| {
        (0..seeds)
            .into_par_iter()
            .map(|index| {
                naturalistic_veterancy_seed(
                    seed_base + index as u64,
                    agents,
                    localities,
                    anchor,
                    horizon,
                )
            })
            .collect()
    });
    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "assay,seed,formation,side,anchor_experience,quality,anchor_personnel,readiness,cohesion,supply_fraction,command,embeddedness,availability,combat_effective_180,personnel_survival_fraction,future_loss_fraction,final_experience")?;
    let mut count = 0usize;
    for result in results {
        for row in result.map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))? {
            writeln!(writer, "{row}")?;
            count += 1;
        }
    }
    writer.flush()?;
    println!("wrote {out} rows={count}");
    Ok(())
}

fn run_state_regeneration(args: &[String]) -> Result<(), Box<dyn Error>> {
    let out = args
        .get(2)
        .cloned()
        .unwrap_or_else(|| "../state_regeneration.csv".to_string());
    let seed_count: usize = arg(args, 3, 8);
    let agents: usize = arg(args, 4, 300);
    let localities: usize = arg(args, 5, 34);
    let focal_count: usize = arg(args, 6, 8);
    let horizon: f64 = arg(args, 7, 180.0);
    let step: f64 = arg(args, 8, 15.0);
    let threads: usize = arg(args, 9, 16);
    if let Some(parent) = Path::new(&out).parent() {
        if !parent.as_os_str().is_empty() {
            create_dir_all(parent)?;
        }
    }

    let capital_values = [0.25, 0.5, 1.0, 2.0, 4.0];
    let shock_values = [0.1, 0.3, 0.5, 1.0];
    let mut cases = Vec::new();
    for seed_index in 0..seed_count {
        let seed = 2026091500u64 + seed_index as u64;
        let mut config = synthetic_config(seed, agents, localities, horizon);
        config.foreign_affairs.enabled = false;
        config.organization_ecology.enabled = false;
        let reference = SimulationEngine::new(config)?;
        let focals = evenly_spaced_capacity_focals(&reference, focal_count);
        for focal in focals {
            for &capital in &capital_values {
                for &shock in &shock_values {
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
                state_regeneration_case(
                    *seed, agents, localities, horizon, step, *focal, *capital, *shock,
                )
            })
            .collect()
    });

    let mut writer = BufWriter::new(File::create(&out)?);
    writeln!(writer, "seed,focal,capital_mult,shock_fraction,base_government_capital,baseline_institution_capacity,baseline_government_effective_control,baseline_structural_admin,time,institution_capacity,institution_reach,institution_integrity,institution_compliance,government_effective_control,government_formal,government_physical,government_administrative,government_legal,government_fiscal,government_social,government_expected,structural_administrative_capacity,government_governance,government_capital,economic_output,infrastructure,population")?;
    for result in results {
        let rows =
            result.map_err(|message| std::io::Error::new(std::io::ErrorKind::Other, message))?;
        for row in rows {
            writeln!(writer, "{row}")?;
        }
    }
    writer.flush()?;
    println!("wrote {out} cases={}", cases.len());
    Ok(())
}

fn usage() {
    eprintln!("pineland-general-theory-probe panel OUT.csv [seeds=16] [agents=300] [localities=34] [horizon=120] [step=30] [seed_base=2026091000] [theory_v2=false] [shared_initialization_seed=dynamic_seed]");
    eprintln!("pineland-general-theory-probe topology OUT.csv [seeds=8] [agents=300] [localities=34] [seed_base=2026101000]");
    eprintln!("pineland-general-theory-probe factorial OUT.csv [seeds=8] [agents=300] [localities=34] [horizon=90]");
    eprintln!("pineland-general-theory-probe criticality OUT.csv [seeds=4] [agents=300] [localities=34] [horizon=180] [step=30]");
    eprintln!("pineland-general-theory-probe reproduction OUT.csv [seeds=8] [agents=300] [localities=17] [horizon=90] [threads=16] [seed_base=2026091300]");
    eprintln!("pineland-general-theory-probe reproduction-first-hazard OUT.csv [seeds=8] [agents=300] [localities=17] [threads=16] [seed_base=2026102000]");
    eprintln!("pineland-general-theory-probe mobilization OUT.csv [seeds=8] [agents=300] [localities=34] [horizon=180] [step=15] [threads=16]");
    eprintln!("pineland-general-theory-probe mobilization-ledger OUT.csv [seeds=8] [agents=300] [localities=34] [horizon=180] [step=15] [threads=16] [seed_base=2026108000]");
    eprintln!("pineland-general-theory-probe state-regeneration OUT.csv [seeds=8] [agents=300] [localities=34] [focals=8] [horizon=180] [step=15] [threads=16]");
    eprintln!("pineland-general-theory-probe state-regeneration-metadata OUT.csv [seeds=8] [agents=300] [localities=34] [focals=8] [seed_base=2026093100]");
    eprintln!("pineland-general-theory-probe veterancy-controlled OUT.csv [replicates=1024] [engagements=12] [threads=16] [seed_base=2026110000]");
    eprintln!("pineland-general-theory-probe veterancy-naturalistic OUT.csv [seeds=32] [agents=300] [localities=34] [anchor=60] [horizon=180] [threads=16] [seed_base=2026111000]");
    eprintln!("pineland-general-theory-probe closure OUT.csv [pool_seeds=24] [agents=300] [localities=34] [anchor=60] [horizon=30] [pairs=24] [branches=32] [threads=16] [candidate=minimal4|core5|core6spatial|operational9|competitive11|competitive11v2|professionalism12v2|veterancy13v2|competitive14v2|renewal15v2|memory15v2|regenerative16v2|transport15v2|reaction_transport17v2|transport12v2|reaction_transport14v2|nettransport12v2|transportnet13v2|rootedstock11v3|rootedstock_hazard12v3|rootedstock_social12v3|rootedstock_net12v3|rootedstock_social_net13v3|rootedstock_hazard_net13v3|rootedstock_transport_net13v3|rootedstock_delay16v4|rootedstock_execnet12v4|rootedstock_execnet_ring1_15v5] [dynamic_seed_base=2026092000] [initialization_seed=2026091900]");
    eprintln!("pineland-general-theory-probe closure-battery OUT_DIR CANDIDATE1,CANDIDATE2 [pool_seeds=48] [agents=300] [localities=34] [anchor=60] [horizon=30] [pairs=24] [branches=32] [threads=16] [dynamic_seed_base=2026092000] [initialization_seed=2026091900] [recruitment_multiplier=1.0] [require_live_anchor=0]");
    eprintln!("pineland-general-theory-probe closure-hidden-diagnostics OUT.csv [pool_seeds=36] [agents=300] [localities=34] [anchor=60] [pairs=24] [threads=8] [candidate=nettransport12v2] [dynamic_seed_base=2026107000] [initialization_seed=2026106900] [recruitment_multiplier=1.0] [require_live_anchor=0]");
    eprintln!("pineland-general-theory-probe closure-stress OUT.csv [seeds=8] [agents=300] [localities=34] [anchor=60] [horizon=30] [focals=3] [branches=32] [threads=16] [block=police_professionalism|government_veterancy|insurgent_veterancy]");
}

fn main() -> Result<(), Box<dyn Error>> {
    let args = env::args().collect::<Vec<_>>();
    match args.get(1).map(String::as_str) {
        Some("panel") => run_panel(&args),
        Some("topology") => run_topology_edges(&args),
        Some("factorial") => run_factorial(&args),
        Some("criticality") => run_criticality(&args),
        Some("reproduction") => run_reproduction_impulse(&args),
        Some("reproduction-first-hazard") => run_reproduction_first_hazard(&args),
        Some("mobilization") => run_mobilization_trap(&args),
        Some("mobilization-ledger") => run_mobilization_resource_ledger(&args),
        Some("state-regeneration") => run_state_regeneration(&args),
        Some("state-regeneration-metadata") => run_state_regeneration_metadata(&args),
        Some("veterancy-controlled") => run_veterancy_controlled(&args),
        Some("veterancy-naturalistic") => run_veterancy_naturalistic(&args),
        Some("closure") => run_distributional_closure(&args),
        Some("closure-battery") => run_distributional_closure_battery(&args),
        Some("closure-hidden-diagnostics") => run_closure_hidden_diagnostics(&args),
        Some("closure-stress") => run_v2_omitted_state_stress(&args),
        _ => {
            usage();
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recruitment_hazard_mass_is_pure_finite_and_nonnegative() {
        let mut engine = SimulationEngine::new(synthetic_config(2026102000, 300, 17, 180.0))
            .expect("hazard diagnostic engine");
        reset_insurgent_reproductive_state(&mut engine);
        let origin = 0usize;
        plant_parent(&mut engine, origin, "M");
        let before = engine.particle.clone();
        let hazard = pineland_model::recruitment::recruitment_hazard_mass_by_locality(
            &engine.particle,
            &engine.topology,
            &engine.config,
            INSURGENT,
        );
        assert_eq!(hazard.len(), engine.topology.locality_count());
        assert!(hazard
            .iter()
            .all(|value| value.is_finite() && *value >= 0.0));
        assert_eq!(
            engine.particle, before,
            "hazard diagnostic mutated model state"
        );
        assert!(rooted_member_mass(&engine.particle, origin) > 0.0);
        let (first_time, propagated) = first_nonzero_recruitment_hazard(&engine, 60.0)
            .expect("first nonzero recruitment hazard");
        assert!(first_time.is_finite());
        assert!(propagated
            .iter()
            .all(|value| value.is_finite() && *value >= 0.0));
        assert!(propagated.iter().sum::<f64>() > 0.0);
    }

    #[test]
    fn closed_mobilization_capital_ledger_conserves() {
        let rows = mobilization_ledger_case(2026108999, 120, 12, 30.0, 15.0, 0.5, 1.0, 1.0)
            .expect("mobilization ledger smoke");
        assert!(!rows.is_empty());
        for row in rows {
            let fields = row.split(',').collect::<Vec<_>>();
            let initial: f64 = fields[5].parse().unwrap();
            let inflow: f64 = fields[9].parse().unwrap();
            let outflow: f64 = fields[10].parse().unwrap();
            let residual: f64 = fields[14].parse().unwrap();
            let scale = initial.abs().max(inflow.abs()).max(outflow.abs()).max(1.0);
            assert!(
                residual.abs() <= 1.0e-8 * scale,
                "residual={residual} scale={scale}"
            );
        }
    }

    #[test]
    fn inbound_transport_pressure_is_pure_and_finite() {
        let mut config = synthetic_config(2026102998, 300, 34, 30.0);
        config.state_regeneration.enabled = true;
        let engine = SimulationEngine::new(config).expect("transport diagnostic engine");
        let before = engine.particle.clone();
        for locality in 0..engine.topology.locality_count() {
            let pressure = pineland_model::movement::inbound_transport_pressure(
                &engine.particle,
                &engine.topology,
                &engine.config,
                locality,
            );
            assert!(pressure.is_finite());
            assert!(pressure >= 0.0);
        }
        assert_eq!(
            engine.particle, before,
            "transport diagnostic mutated particle state"
        );
    }

    #[test]
    fn internal_transport_flux_conserves_effective_strength_in_expectation() {
        let config = synthetic_config(2026110199, 300, 34, 30.0);
        let engine = SimulationEngine::new(config).expect("transport conservation engine");
        let before = engine.particle.clone();
        let net = pineland_model::movement::insurgent_transport_net_pressures(
            &engine.particle,
            &engine.topology,
            &engine.config,
        );
        assert_eq!(
            before, engine.particle,
            "transport flux diagnostic mutated state"
        );
        assert_eq!(net.len(), engine.topology.locality_count());
        assert!(net.iter().all(|value| value.is_finite()));
        let gross = net.iter().map(|value| value.abs()).sum::<f64>();
        let residual = net.iter().sum::<f64>().abs();
        assert!(
            residual <= 1.0e-12 * gross.max(1.0),
            "internal transport failed conservation: residual={residual} gross={gross}"
        );
    }

    #[test]
    fn particle_execution_preserves_decision_state_for_closure_horizon() {
        let config = synthetic_config(2026092999, 300, 34, 30.0);
        let mut forensic = SimulationEngine::new(config.clone()).expect("forensic engine");
        let mut particle = SimulationEngine::new(config).expect("particle engine");
        particle.configure_particle_execution();
        forensic.advance_until(30.0).expect("forensic advance");
        particle.advance_until(30.0).expect("particle advance");
        assert_eq!(forensic.decision_hash(), particle.decision_hash());
        assert_eq!(forensic.particle.rng, particle.particle.rng);

        // The particle profile intentionally drops forensic-only event-count
        // and checkpoint bookkeeping (and may omit measurement-only archives),
        // so the complete Counters struct is not an equivalence target.  The
        // causal counters and every quantity used by the closure experiment
        // must nevertheless be exactly preserved.
        assert_eq!(
            forensic.particle.counters.contacts,
            particle.particle.counters.contacts
        );
        assert_eq!(
            forensic.particle.counters.organized_actions,
            particle.particle.counters.organized_actions
        );
        assert_eq!(
            forensic.particle.counters.recruitment,
            particle.particle.counters.recruitment
        );
        assert_eq!(
            forensic.particle.counters.civilian_harm,
            particle.particle.counters.civilian_harm
        );
        assert_eq!(
            forensic.particle.counters.deaths,
            particle.particle.counters.deaths
        );

        for locality in 0..forensic.topology.locality_count() {
            assert_eq!(
                closure_features(&forensic, locality),
                closure_features(&particle, locality),
                "closure feature mismatch at locality {locality}"
            );
            let a = snapshot_values(&forensic, locality);
            let b = snapshot_values(&particle, locality);
            for name in [
                "e_cum_actions",
                "e_cum_recruits",
                "e_foothold_strength",
                "m_member_depth",
                "f_effective_strength",
                "c_margin",
                "c_gov_effective",
            ] {
                let index = panel_index(name);
                assert_eq!(a[index], b[index], "{name} mismatch at locality {locality}");
            }
        }
    }

    #[test]
    fn closure_future_stream_is_candidate_invariant_for_same_pair() {
        let mut engines = Vec::new();
        for seed in [2026110101u64, 2026110102u64] {
            let mut config = synthetic_config(seed, 120, 17, 8.0);
            config.initialization_seed = Some(2026110100);
            config.state_regeneration.enabled = true;
            let mut engine = SimulationEngine::new(config).expect("closure test engine");
            engine.particle_execution = true;
            engine.advance_until(5.0).expect("anchor advance");
            engines.push((seed, engine));
        }
        let locality = 3usize;
        let pair = ClosurePair {
            pair_id: 0,
            left_engine: 0,
            right_engine: 1,
            left_seed: engines[0].0,
            right_seed: engines[1].0,
            locality,
            distance: 0.0,
            stratum: "mid".to_string(),
            left_pre: closure_features(&engines[0].1, locality),
            right_pre: closure_features(&engines[1].1, locality),
        };
        let a = closure_branch_rows(&pair, &engines, "competitive14v2", 5.0, 3.0, 7)
            .expect("candidate A continuation");
        let b = closure_branch_rows(&pair, &engines, "reaction_transport17v2", 5.0, 3.0, 7)
            .expect("candidate B continuation");
        assert_eq!(a.len(), b.len());
        for (left, right) in a.iter().zip(&b) {
            let mut left_fields = left.split(',').collect::<Vec<_>>();
            let mut right_fields = right.split(',').collect::<Vec<_>>();
            assert!(left_fields.len() > 2 && right_fields.len() > 2);
            left_fields.remove(1); // candidate label
            right_fields.remove(1);
            assert_eq!(left_fields, right_fields);
        }
    }
}
