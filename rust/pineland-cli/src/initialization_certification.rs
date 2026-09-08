//! Initialization inventory exported for Python↔Rust equivalence testing.

use super::Arguments;
use pineland_core::json::JsonValue;
use pineland_core::sha256;
use pineland_model::SimulationEngine;
use std::collections::BTreeSet;

pub(crate) fn certify_initialization(arguments: &Arguments) -> Result<(), String> {
    let config = super::config(arguments)?;
    let engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    let mut result = JsonValue::object();
    result.insert(
        "schema",
        JsonValue::string("pineland-initialization-certification-v1"),
    );
    result.insert(
        "configuration_hash",
        JsonValue::string(engine.config.canonical_hash()),
    );
    result.insert("model_hash", JsonValue::string(&engine.model_hash));
    result.insert("counts", counts(&engine));
    result.insert("components", components(&engine));
    // Diagnostics are intentionally outside the canonical component map so a
    // certificate remains compact while an exactness failure can still be
    // localized to the first divergent representative/person/formation.
    result.insert("diagnostics", diagnostics(&engine));
    result.insert("rng_streams", rng_streams(&engine));
    result.insert("scheduler", scheduler(&engine));
    result.insert("state_hash", JsonValue::string(engine.state_hash()));
    result.insert("decision_hash", JsonValue::string(engine.decision_hash()));
    println!("{}", result.to_pretty());
    Ok(())
}

fn counts(engine: &SimulationEngine) -> JsonValue {
    let particle = &engine.particle;
    let households = particle
        .people
        .household
        .iter()
        .copied()
        .collect::<BTreeSet<_>>()
        .len();
    let mut value = JsonValue::object();
    value.insert(
        "people",
        JsonValue::integer(particle.people.locality.len() as u64),
    );
    value.insert("households", JsonValue::integer(households as u64));
    let communities = particle
        .people
        .community
        .iter()
        .filter(|value| **value != u32::MAX)
        .copied()
        .collect::<BTreeSet<_>>()
        .len();
    value.insert("communities", JsonValue::integer(communities as u64));
    value.insert(
        "organizations",
        JsonValue::integer(particle.organizations.kind.len() as u64),
    );
    value.insert(
        "formations",
        JsonValue::integer(particle.formations.organization.len() as u64),
    );
    value.insert(
        "posts",
        JsonValue::integer(particle.security_posts.locality.len() as u64),
    );
    value.insert(
        "patrols",
        JsonValue::integer(
            particle
                .patrols
                .active
                .iter()
                .filter(|active| **active != 0)
                .count() as u64,
        ),
    );
    value.insert(
        "localities",
        JsonValue::integer(engine.topology.locality_count() as u64),
    );
    value.insert(
        "microzones",
        JsonValue::integer(engine.topology.microzone_count() as u64),
    );
    value.insert(
        "footholds",
        JsonValue::integer(
            particle
                .footholds
                .active
                .iter()
                .filter(|active| **active != 0)
                .count() as u64,
        ),
    );
    value.insert("manpower_pools", JsonValue::integer(0));
    value.insert(
        "logistics_sources",
        JsonValue::integer(particle.logistics.source_stock.len() as u64),
    );
    value.insert(
        "belief_state",
        JsonValue::integer(particle.beliefs.keys.len() as u64),
    );
    value.insert(
        "scheduler",
        JsonValue::integer(particle.scheduler.len() as u64),
    );
    value
}

fn components(engine: &SimulationEngine) -> JsonValue {
    let particle = &engine.particle;
    let mut value = JsonValue::object();
    let mut locality_kind_counts = [0u64; 3];
    for kind in &engine.topology.locality_kind {
        if (*kind as usize) < locality_kind_counts.len() {
            locality_kind_counts[*kind as usize] += 1;
        }
    }
    let mut kind_counts = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut kind_counts {
        values.extend(locality_kind_counts.into_iter().map(JsonValue::integer));
    }
    value.insert("locality_kind_counts", kind_counts);
    let mut locality_kinds = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut locality_kinds {
        values.extend(
            engine
                .topology
                .locality_kind
                .iter()
                .map(|kind| JsonValue::integer(*kind as u64)),
        );
    }
    value.insert("locality_kinds", locality_kinds);
    let mut locality_populations = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut locality_populations {
        values.extend(
            engine
                .particle
                .locality
                .population
                .iter()
                .map(|population| JsonValue::number(*population)),
        );
    }
    value.insert("locality_populations", locality_populations);
    let mut locality_districts = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut locality_districts {
        values.extend(
            engine
                .topology
                .locality_to_district
                .iter()
                .map(|district| JsonValue::integer(*district as u64)),
        );
    }
    value.insert("locality_districts", locality_districts);
    let mut zone_share_rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(rows) = &mut zone_share_rows {
        for locality in 0..engine.topology.locality_count() {
            let mut row = JsonValue::Array(Vec::new());
            if let JsonValue::Array(values) = &mut row {
                values.extend(
                    engine
                        .topology
                        .zones_for_locality(locality.into())
                        .map(|zone| JsonValue::number(engine.topology.zone_population_share[zone])),
                );
            }
            rows.push(row);
        }
    }
    value.insert("zone_population_share_rows", zone_share_rows);
    value.insert(
        "zone_population_share",
        JsonValue::string(f64_digest(&particle.zones.population_share)),
    );
    value.insert(
        "zone_infrastructure",
        JsonValue::string(f64_digest(&particle.zones.infrastructure)),
    );
    value.insert(
        "zone_terrain_friction",
        JsonValue::string(f64_digest(&particle.zones.terrain_friction)),
    );
    value.insert(
        "zone_observability",
        JsonValue::string(f64_digest(&particle.zones.observability)),
    );
    value.insert(
        "locality_population",
        JsonValue::string(f64_digest(&particle.locality.population)),
    );
    value.insert(
        "locality_economic_output",
        JsonValue::string(f64_digest(&particle.locality.economic_output)),
    );
    value.insert(
        "locality_infrastructure",
        JsonValue::string(f64_digest(&particle.locality.infrastructure)),
    );
    value.insert(
        "locality_administrative_capacity",
        JsonValue::string(f64_digest(&particle.locality.administrative_capacity)),
    );
    value.insert(
        "locality_terrain_friction",
        JsonValue::string(f64_digest(&particle.locality.terrain_friction)),
    );
    value.insert(
        "locality_observability",
        JsonValue::string(f64_digest(&particle.locality.observability)),
    );
    value.insert(
        "government_control",
        JsonValue::string(f64_digest(&particle.locality.government_control)),
    );
    value.insert(
        "insurgent_control",
        JsonValue::string(f64_digest(&particle.locality.insurgent_control)),
    );
    value.insert(
        "locality_government_governance",
        JsonValue::string(f64_digest(&particle.locality.government_governance)),
    );
    value.insert(
        "locality_insurgent_governance",
        JsonValue::string(f64_digest(&particle.locality.insurgent_governance)),
    );
    value.insert(
        "people_locality",
        JsonValue::string(u32_digest(&particle.people.locality)),
    );
    value.insert(
        "people_home",
        JsonValue::string(u32_digest(&particle.people.home)),
    );
    value.insert(
        "people_residence",
        JsonValue::string(u32_digest(&particle.people.residence)),
    );
    value.insert(
        "people_represented_population",
        JsonValue::string(f64_digest(&particle.people.represented_population)),
    );
    value.insert(
        "people_household",
        JsonValue::string(u32_digest(&particle.people.household)),
    );
    value.insert(
        "people_age",
        JsonValue::string(u8_digest(&particle.people.age)),
    );
    value.insert(
        "people_languages",
        JsonValue::string(f64_digest(&particle.people.languages)),
    );
    value.insert(
        "people_identities",
        JsonValue::string(f64_digest(&particle.people.identities)),
    );
    value.insert(
        "people_preferences",
        JsonValue::string(f64_digest(&particle.people.preferences)),
    );
    value.insert(
        "people_grievance",
        JsonValue::string(f64_digest(&particle.people.grievance)),
    );
    value.insert(
        "people_fear",
        JsonValue::string(f64_digest(&particle.people.fear)),
    );
    value.insert(
        "people_efficacy",
        JsonValue::string(f64_digest(&particle.people.efficacy)),
    );
    value.insert(
        "people_trust",
        JsonValue::string(f64_digest(&particle.people.trust)),
    );
    value.insert(
        "people_trust_insurgent",
        JsonValue::string(f64_digest(&particle.people.trust_insurgent)),
    );
    value.insert(
        "people_resources",
        JsonValue::string(f64_digest(&particle.people.resources)),
    );
    value.insert(
        "people_rebel_sympathy",
        JsonValue::string(f64_digest(&particle.people.rebel_sympathy)),
    );
    value.insert(
        "people_organization",
        JsonValue::string(u32_digest(&particle.people.organization)),
    );
    value.insert(
        "people_armed_fraction",
        JsonValue::string(f64_digest(&particle.people.armed_fraction)),
    );
    value.insert(
        "people_community",
        JsonValue::string(u32_digest(&particle.people.community)),
    );
    value.insert(
        "organizations_kind",
        JsonValue::string(u8_digest(&particle.organizations.kind)),
    );
    value.insert(
        "organizations_active",
        JsonValue::string(u8_digest(&particle.organizations.active)),
    );
    value.insert(
        "organizations_capital",
        JsonValue::string(f64_digest(&particle.organizations.capital)),
    );
    value.insert(
        "organizations_cohesion",
        JsonValue::string(f64_digest(&particle.organizations.cohesion)),
    );
    value.insert(
        "organizations_discipline",
        JsonValue::string(f64_digest(&particle.organizations.discipline)),
    );
    value.insert(
        "organizations_accountability",
        JsonValue::string(f64_digest(&particle.organizations.accountability)),
    );
    value.insert(
        "organizations_local_knowledge",
        JsonValue::string(f64_digest(&particle.organizations.local_knowledge)),
    );
    value.insert(
        "organizations_persistence",
        JsonValue::string(f64_digest(&particle.organizations.persistence)),
    );
    value.insert(
        "organizations_mobility",
        JsonValue::string(f64_digest(&particle.organizations.mobility)),
    );
    value.insert(
        "organizations_institutional_quality",
        JsonValue::string(f64_digest(&particle.organizations.institutional_quality)),
    );
    value.insert(
        "organizations_external_support",
        JsonValue::string(f64_digest(&particle.organizations.external_support)),
    );
    value.insert(
        "organizations_member_population",
        JsonValue::string(f64_digest(&particle.organizations.member_population)),
    );
    value.insert(
        "formations_organization",
        JsonValue::string(u32_digest(&particle.formations.organization)),
    );
    value.insert(
        "formations_locality",
        JsonValue::string(u32_digest(&particle.formations.locality)),
    );
    value.insert(
        "formations_microzone",
        JsonValue::string(u32_digest(&particle.formations.microzone)),
    );
    value.insert(
        "formations_personnel",
        JsonValue::string(f64_digest(&particle.formations.personnel)),
    );
    value.insert(
        "formations_quality",
        JsonValue::string(f64_digest(&particle.formations.quality)),
    );
    value.insert(
        "formations_cohesion",
        JsonValue::string(f64_digest(&particle.formations.cohesion)),
    );
    value.insert(
        "formations_readiness",
        JsonValue::string(f64_digest(&particle.formations.readiness)),
    );
    value.insert(
        "formations_sustainment",
        JsonValue::string(f64_digest(&particle.formations.sustainment)),
    );
    value.insert(
        "formations_information",
        JsonValue::string(f64_digest(&particle.formations.information)),
    );
    value.insert(
        "formations_mobility",
        JsonValue::string(f64_digest(&particle.formations.mobility)),
    );
    value.insert(
        "formations_command",
        JsonValue::string(f64_digest(&particle.formations.command)),
    );
    value.insert(
        "formations_embeddedness",
        JsonValue::string(f64_digest(&particle.formations.embeddedness)),
    );
    value.insert(
        "formations_fatigue",
        JsonValue::string(f64_digest(&particle.formations.fatigue)),
    );
    value.insert(
        "formations_availability",
        JsonValue::string(f64_digest(&particle.formations.availability)),
    );
    value.insert(
        "formations_supply_stock",
        JsonValue::string(f64_digest(&particle.formations.supply_stock)),
    );
    value.insert(
        "formations_supply_capacity",
        JsonValue::string(f64_digest(&particle.formations.supply_capacity)),
    );
    value.insert(
        "formations_home_locality",
        JsonValue::string(u32_digest(&particle.formations.home_locality)),
    );
    value.insert(
        "formations_active",
        JsonValue::string(u8_digest(&particle.formations.active)),
    );
    value.insert(
        "formations_moving",
        JsonValue::string(u8_digest(&particle.formations.moving)),
    );
    value.insert(
        "formations_outside_pineland",
        JsonValue::string(u8_digest(&particle.formations.outside_pineland)),
    );
    value.insert(
        "security_posts_organization",
        JsonValue::string(u32_digest(&particle.security_posts.organization)),
    );
    value.insert(
        "security_posts_locality",
        JsonValue::string(u32_digest(&particle.security_posts.locality)),
    );
    value.insert(
        "security_posts_microzone",
        JsonValue::string(u32_digest(&particle.security_posts.microzone)),
    );
    value.insert(
        "security_posts_personnel",
        JsonValue::string(f64_digest(&particle.security_posts.personnel)),
    );
    value.insert(
        "security_posts_presence",
        JsonValue::string(f64_digest(&particle.security_posts.presence)),
    );
    value.insert(
        "security_posts_available_fraction",
        JsonValue::string(f64_digest(&particle.security_posts.available_fraction)),
    );
    value.insert(
        "security_posts_formation",
        JsonValue::string(u32_digest(&particle.security_posts.formation)),
    );
    value.insert(
        "patrols_formation",
        JsonValue::string(u32_digest(&particle.patrols.formation)),
    );
    value.insert(
        "patrols_active",
        JsonValue::string(u8_digest(&particle.patrols.active)),
    );
    value.insert(
        "patrols_route_position",
        JsonValue::string(u32_digest(&particle.patrols.route_position)),
    );
    value.insert(
        "patrols_route_target",
        JsonValue::string(u32_digest(&particle.patrols.route_target)),
    );
    value.insert(
        "patrols_next_available",
        JsonValue::string(f64_digest(&particle.patrols.next_available)),
    );
    value.insert(
        "footholds_active",
        JsonValue::string(u8_digest(&particle.footholds.active)),
    );
    value.insert(
        "footholds_strength",
        JsonValue::string(f64_digest(&particle.footholds.strength)),
    );
    value.insert(
        "footholds_raw_signal",
        JsonValue::string(f64_digest(&particle.footholds.raw_signal)),
    );
    value.insert(
        "footholds_membership",
        JsonValue::string(f64_digest(&particle.footholds.membership)),
    );
    value.insert(
        "footholds_embeddedness",
        JsonValue::string(f64_digest(&particle.footholds.embeddedness)),
    );
    value.insert(
        "footholds_access",
        JsonValue::string(f64_digest(&particle.footholds.access)),
    );
    value.insert(
        "footholds_target_knowledge",
        JsonValue::string(f64_digest(&particle.footholds.target_knowledge)),
    );
    value.insert(
        "footholds_infrastructure",
        JsonValue::string(f64_digest(&particle.footholds.infrastructure)),
    );
    value.insert(
        "footholds_sustainment",
        JsonValue::string(f64_digest(&particle.footholds.sustainment)),
    );
    value.insert(
        "logistics_source_stock",
        JsonValue::string(f64_digest(&particle.logistics.source_stock)),
    );
    value.insert(
        "logistics_organization",
        JsonValue::string(u32_digest(&particle.logistics.organization)),
    );
    value.insert(
        "logistics_locality",
        JsonValue::string(u32_digest(&particle.logistics.locality)),
    );
    value.insert(
        "logistics_source_capacity",
        JsonValue::string(f64_digest(&particle.logistics.source_capacity)),
    );
    value.insert(
        "logistics_source_production",
        JsonValue::string(f64_digest(&particle.logistics.source_production)),
    );
    value.insert(
        "belief_presence",
        JsonValue::string(f64_digest(&particle.beliefs.presence)),
    );
    value.insert(
        "belief_control",
        JsonValue::string(f64_digest(&particle.beliefs.control)),
    );
    value.insert(
        "belief_confidence",
        JsonValue::string(f64_digest(&particle.beliefs.confidence)),
    );
    value.insert(
        "belief_keys",
        JsonValue::string(belief_key_digest(&particle.beliefs.keys)),
    );
    value
}

fn rng_streams(engine: &SimulationEngine) -> JsonValue {
    let mut value = JsonValue::object();
    for (name, rng) in &engine.particle.rng.streams {
        let state = rng.state();
        let mut bytes = Vec::with_capacity(624 * 4 + 13);
        for word in state.words {
            bytes.extend_from_slice(&word.to_le_bytes());
        }
        bytes.extend_from_slice(&state.index.to_le_bytes());
        match state.gauss_next {
            Some(next) => {
                bytes.push(1);
                bytes.extend_from_slice(&next.to_bits().to_le_bytes());
            }
            None => bytes.push(0),
        }
        value.insert(name, JsonValue::string(sha256::digest_hex(&bytes)));
    }
    value
}

fn scheduler(engine: &SimulationEngine) -> JsonValue {
    let mut rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut rows {
        values.extend(
            engine
                .particle
                .scheduler
                .events_sorted()
                .iter()
                .map(|event| {
                    let mut row = JsonValue::object();
                    row.insert("time_bits", JsonValue::integer(event.time.to_bits()));
                    row.insert("priority", JsonValue::integer(event.priority as u64));
                    row.insert("sequence", JsonValue::integer(event.sequence));
                    row.insert("kind", JsonValue::string(event.payload.kind()));
                    row.insert("code", JsonValue::integer(event.payload.code() as u64));
                    row
                }),
        );
    }
    rows
}

fn f64_digest(values: &[f64]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 8);
    for value in values {
        bytes.extend_from_slice(&value.to_bits().to_le_bytes());
    }
    sha256::digest_hex(&bytes)
}

fn u32_digest(values: &[u32]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 4);
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    sha256::digest_hex(&bytes)
}

fn u8_digest(values: &[u8]) -> String {
    sha256::digest_hex(values)
}

fn belief_key_digest(values: &[pineland_core::state::BeliefKey]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 13);
    for key in values {
        bytes.extend_from_slice(&key.observer.to_le_bytes());
        bytes.extend_from_slice(&key.target.to_le_bytes());
        bytes.extend_from_slice(&key.locality.to_le_bytes());
        bytes.push(key.kind);
    }
    sha256::digest_hex(&bytes)
}

fn diagnostics(engine: &SimulationEngine) -> JsonValue {
    let particle = &engine.particle;
    let mut value = JsonValue::object();
    value.insert(
        "people_organization",
        u32_array(&particle.people.organization),
    );
    value.insert(
        "people_armed_fraction",
        f64_array(&particle.people.armed_fraction),
    );
    value.insert(
        "people_rebel_sympathy",
        f64_array(&particle.people.rebel_sympathy),
    );
    value.insert("people_community", u32_array(&particle.people.community));
    value.insert(
        "government_control",
        f64_array(&particle.locality.government_control),
    );
    value.insert(
        "insurgent_control",
        f64_array(&particle.locality.insurgent_control),
    );
    value.insert(
        "formation_locality",
        u32_array(&particle.formations.locality),
    );
    value.insert(
        "formation_personnel",
        f64_array(&particle.formations.personnel),
    );
    value.insert(
        "logistics_capacity",
        f64_array(&particle.logistics.source_capacity),
    );
    value.insert(
        "logistics_production",
        f64_array(&particle.logistics.source_production),
    );
    value.insert(
        "logistics_stock",
        f64_array(&particle.logistics.source_stock),
    );
    value
}

fn f64_array(values: &[f64]) -> JsonValue {
    JsonValue::Array(values.iter().copied().map(JsonValue::number).collect())
}

fn u32_array(values: &[u32]) -> JsonValue {
    JsonValue::Array(values.iter().copied().map(JsonValue::integer).collect())
}
