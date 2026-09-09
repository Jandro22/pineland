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
    if std::env::var_os("PINELAND_CERT_DEBUG").is_some() {
        result.insert("debug_beliefs", debug_beliefs(&engine));
    }
    result.insert("state_hash", JsonValue::string(engine.state_hash()));
    result.insert("decision_hash", JsonValue::string(engine.decision_hash()));
    println!("{}", result.to_pretty());
    Ok(())
}

/// Export the same component inventory after a deterministic native
/// trajectory.  Keeping this boundary identical to the initialization
/// certificate makes the first divergent process/state field observable to
/// the Python oracle instead of hiding it behind one opaque state hash.
pub(crate) fn certify_trajectory(arguments: &Arguments) -> Result<(), String> {
    let mut config = super::config(arguments)?;
    if let Some(until) = arguments.value("until") {
        config.horizon_days = until
            .parse::<f64>()
            .map_err(|_| "--until must be a number".to_string())?;
        config.validate().map_err(|error| error.to_string())?;
    }
    let target = config.horizon_days;
    let mut engine = SimulationEngine::new(config).map_err(|error| error.to_string())?;
    let processed = if let Some(value) = arguments.value("max-events") {
        let limit = value
            .parse::<usize>()
            .map_err(|_| "--max-events must be an integer".to_string())?;
        engine
            .advance_until_limited(target, Some(limit))
            .map_err(|error| error.to_string())?
    } else {
        engine.run().map_err(|error| error.to_string())?;
        engine.particle.scheduler.processed as usize
    };
    if arguments.value("max-events").is_none() && (engine.particle.time - target).abs() > 1e-10 {
        return Err(format!(
            "native trajectory stopped at {}, expected {target}",
            engine.particle.time
        ));
    }
    let mut result = JsonValue::object();
    result.insert(
        "schema",
        JsonValue::string("pineland-trajectory-certification-v1"),
    );
    result.insert(
        "configuration_hash",
        JsonValue::string(engine.config.canonical_hash()),
    );
    result.insert("target_time", JsonValue::number(target));
    result.insert("actual_time", JsonValue::number(engine.particle.time));
    result.insert("events_processed", JsonValue::integer(processed as u64));
    result.insert("counts", counts(&engine));
    result.insert("components", components(&engine));
    result.insert("diagnostics", diagnostics(&engine));
    result.insert("rng_streams", rng_streams(&engine));
    result.insert("scheduler", scheduler(&engine));
    if std::env::var_os("PINELAND_CERT_DEBUG").is_some() {
        result.insert("debug_beliefs", debug_beliefs(&engine));
    }
    result.insert("state_hash", JsonValue::string(engine.state_hash()));
    result.insert("decision_hash", JsonValue::string(engine.decision_hash()));
    println!("{}", result.to_pretty());
    Ok(())
}

fn debug_beliefs(engine: &SimulationEngine) -> JsonValue {
    let beliefs = &engine.particle.beliefs;
    let mut rows = JsonValue::Array(Vec::new());
    if let JsonValue::Array(values) = &mut rows {
        for index in 0..beliefs.keys.len() {
            let key = &beliefs.keys[index];
            let mut row = JsonValue::object();
            row.insert("observer", JsonValue::integer(key.observer as u64));
            row.insert("target", JsonValue::integer(key.target as u64));
            row.insert("locality", JsonValue::integer(key.locality as u64));
            row.insert("kind", JsonValue::integer(key.kind as u64));
            row.insert("confidence", JsonValue::number(beliefs.confidence[index]));
            row.insert("updated_at", JsonValue::number(beliefs.updated_at[index]));
            row.insert("presence", JsonValue::number(beliefs.presence[index]));
            row.insert(
                "contradiction",
                JsonValue::number(beliefs.contradiction[index]),
            );
            row.insert(
                "evidence_count",
                JsonValue::integer(beliefs.evidence_count[index] as u64),
            );
            values.push(row);
        }
    }
    rows
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
    value.insert(
        "manpower_pools",
        JsonValue::integer(particle.manpower.pool.len() as u64),
    );
    value.insert(
        "logistics_sources",
        JsonValue::integer(particle.logistics.source_stock.len() as u64),
    );
    value.insert(
        "belief_state",
        JsonValue::integer(particle.beliefs.keys.len() as u64),
    );
    value.insert(
        "zone_belief_state",
        JsonValue::integer(particle.zone_beliefs.keys.len() as u64),
    );
    value.insert(
        "social_edges",
        JsonValue::integer(particle.social_edges.person_a.len() as u64),
    );
    value.insert(
        "command_edges",
        JsonValue::integer(particle.command_edges.organization.len() as u64),
    );
    value.insert(
        "leaders",
        JsonValue::integer(particle.leaders.organization.len() as u64),
    );
    value.insert(
        "political_institutions",
        JsonValue::integer(particle.political.institution_type.len() as u64),
    );
    value.insert(
        "party_branches",
        JsonValue::integer(particle.political.branch_party.len() as u64),
    );
    value.insert(
        "local_elites",
        JsonValue::integer(particle.political.elite_person.len() as u64),
    );
    value.insert(
        "foreign_states",
        JsonValue::integer(particle.foreign.resources.len() as u64),
    );
    value.insert(
        "border_segments",
        JsonValue::integer(particle.foreign.border_foreign_state.len() as u64),
    );
    value.insert(
        "foreign_beliefs",
        JsonValue::integer(particle.foreign.belief_foreign_state.len() as u64),
    );
    value.insert(
        "interpreter_brokers",
        JsonValue::integer(particle.foreign.interpreter_person.len() as u64),
    );
    value.insert(
        "organization_relations",
        JsonValue::integer(particle.relations.organization_a.len() as u64),
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
        "people_public_behavior",
        JsonValue::string(u8_digest(&particle.people.public_behavior)),
    );
    value.insert(
        "people_expected_control",
        JsonValue::string(f64_digest(&particle.people.expected_control)),
    );
    value.insert(
        "people_party_legitimacy",
        JsonValue::string(f64_digest(&particle.people.party_legitimacy)),
    );
    value.insert(
        "people_state_legitimacy",
        JsonValue::string(f64_digest(&particle.people.state_legitimacy)),
    );
    value.insert(
        "people_government_legitimacy",
        JsonValue::string(f64_digest(&particle.people.government_legitimacy)),
    );
    value.insert(
        "people_political_access",
        JsonValue::string(f64_digest(&particle.people.political_access)),
    );
    value.insert(
        "people_displaced",
        JsonValue::string(u8_digest(&particle.people.displaced)),
    );
    value.insert(
        "people_displacement_count",
        JsonValue::string(u32_digest(&particle.people.displacement_count)),
    );
    value.insert(
        "people_origin_tie_strength",
        JsonValue::string(f64_digest(&particle.people.origin_tie_strength)),
    );
    value.insert(
        "people_insurgent_affinity",
        JsonValue::string(f64_digest(&particle.people.insurgent_affinity)),
    );
    value.insert(
        "households_locality",
        JsonValue::string(u32_digest(&particle.households.locality)),
    );
    value.insert(
        "households_residence",
        JsonValue::string(u32_digest(&particle.households.residence)),
    );
    value.insert(
        "households_resources",
        JsonValue::string(f64_digest(&particle.households.resources)),
    );
    value.insert(
        "households_dependents",
        JsonValue::string(u32_digest(&particle.households.dependents)),
    );
    value.insert(
        "households_member_offsets",
        JsonValue::string(u32_digest(&particle.households.member_offsets)),
    );
    value.insert(
        "households_member_indices",
        JsonValue::string(u32_digest(&particle.households.member_indices)),
    );
    value.insert(
        "communities_locality",
        JsonValue::string(u32_digest(&particle.communities.locality)),
    );
    value.insert(
        "communities_cohesion",
        JsonValue::string(f64_digest(&particle.communities.cohesion)),
    );
    value.insert(
        "communities_language_profile",
        JsonValue::string(f64_digest(&particle.communities.language_profile)),
    );
    value.insert(
        "communities_member_offsets",
        JsonValue::string(u32_digest(&particle.communities.member_offsets)),
    );
    value.insert(
        "communities_member_indices",
        JsonValue::string(u32_digest(&particle.communities.member_indices)),
    );
    value.insert(
        "communities_bridge_offsets",
        JsonValue::string(u32_digest(&particle.communities.bridge_offsets)),
    );
    value.insert(
        "communities_bridge_members",
        JsonValue::string(u32_digest(&particle.communities.bridge_members)),
    );
    value.insert(
        "social_edges_person_a",
        JsonValue::string(u32_digest(&particle.social_edges.person_a)),
    );
    value.insert(
        "social_edges_person_b",
        JsonValue::string(u32_digest(&particle.social_edges.person_b)),
    );
    value.insert(
        "social_edges_layers",
        JsonValue::string(u8_digest(&particle.social_edges.layers)),
    );
    value.insert(
        "social_edges_weight",
        JsonValue::string(f64_digest(&particle.social_edges.weight)),
    );
    value.insert(
        "social_edges_language_compatibility",
        JsonValue::string(f64_digest(&particle.social_edges.language_compatibility)),
    );
    value.insert(
        "social_edges_trust",
        JsonValue::string(f64_digest(&particle.social_edges.trust)),
    );
    value.insert(
        "social_edges_represented_relationships",
        JsonValue::string(f64_digest(&particle.social_edges.represented_relationships)),
    );
    value.insert(
        "social_edges_neighbor_offsets",
        JsonValue::string(u32_digest(&particle.social_edges.neighbor_offsets)),
    );
    value.insert(
        "social_edges_neighbor_indices",
        JsonValue::string(u32_digest(&particle.social_edges.neighbor_indices)),
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
        "organizations_capital_social",
        JsonValue::string(f64_digest(&particle.organizations.capital_social)),
    );
    value.insert(
        "organizations_capital_political",
        JsonValue::string(f64_digest(&particle.organizations.capital_political)),
    );
    value.insert(
        "organizations_capital_organizational",
        JsonValue::string(f64_digest(&particle.organizations.capital_organizational)),
    );
    value.insert(
        "organizations_capital_material",
        JsonValue::string(f64_digest(&particle.organizations.capital_material)),
    );
    value.insert(
        "organizations_phenotype",
        JsonValue::string(f64_digest(&particle.organizations.phenotype)),
    );
    value.insert(
        "organizations_ideology",
        JsonValue::string(f64_digest(&particle.organizations.ideology)),
    );
    value.insert(
        "organizations_external_sanctuary",
        JsonValue::string(f64_digest(&particle.organizations.external_sanctuary)),
    );
    value.insert(
        "organizations_adaptation_rate",
        JsonValue::string(f64_digest(&particle.organizations.adaptation_rate)),
    );
    value.insert(
        "organizations_leader",
        JsonValue::string(u32_digest(&particle.organizations.leader)),
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
    value.insert(
        "zone_belief_keys",
        JsonValue::string(zone_belief_key_digest(&particle.zone_beliefs.keys)),
    );
    value.insert(
        "zone_belief_estimate",
        JsonValue::string(f64_digest(&particle.zone_beliefs.estimate)),
    );
    value.insert(
        "zone_belief_confidence",
        JsonValue::string(f64_digest(&particle.zone_beliefs.confidence)),
    );
    value.insert(
        "zone_belief_updated_at",
        JsonValue::string(f64_digest(&particle.zone_beliefs.updated_at)),
    );
    value.insert(
        "zone_belief_reliable_at",
        JsonValue::string(f64_digest(
            &particle.zone_beliefs.last_reliable_observation_at,
        )),
    );
    value.insert(
        "zone_belief_evidence",
        JsonValue::string(u32_digest(&particle.zone_beliefs.evidence_count)),
    );
    value.insert(
        "zone_belief_contradiction",
        JsonValue::string(f64_digest(&particle.zone_beliefs.contradiction)),
    );
    value.insert(
        "command_edges_organization",
        JsonValue::string(u32_digest(&particle.command_edges.organization)),
    );
    value.insert(
        "command_edges_formation",
        JsonValue::string(u32_digest(&particle.command_edges.formation)),
    );
    value.insert(
        "command_edges_reliability",
        JsonValue::string(f64_digest(&particle.command_edges.reliability)),
    );
    value.insert(
        "command_edges_latency_hours",
        JsonValue::string(f64_digest(&particle.command_edges.latency_hours)),
    );
    value.insert(
        "manpower_organization",
        JsonValue::string(u32_digest(&particle.manpower.organization)),
    );
    value.insert(
        "manpower_locality",
        JsonValue::string(u32_digest(&particle.manpower.locality)),
    );
    value.insert(
        "manpower_pool",
        JsonValue::string(f64_digest(&particle.manpower.pool)),
    );
    value.insert(
        "manpower_supply_reserve",
        JsonValue::string(f64_digest(&particle.manpower.supply_reserve)),
    );
    value.insert(
        "leaders_organization",
        JsonValue::string(u32_digest(&particle.leaders.organization)),
    );
    value.insert(
        "leaders_competence",
        JsonValue::string(f64_digest(&particle.leaders.competence)),
    );
    value.insert(
        "leaders_charisma",
        JsonValue::string(f64_digest(&particle.leaders.charisma)),
    );
    value.insert(
        "leaders_risk_tolerance",
        JsonValue::string(f64_digest(&particle.leaders.risk_tolerance)),
    );
    value.insert(
        "leaders_ideological_rigidity",
        JsonValue::string(f64_digest(&particle.leaders.ideological_rigidity)),
    );
    value.insert(
        "leaders_political_skill",
        JsonValue::string(f64_digest(&particle.leaders.political_skill)),
    );
    value.insert(
        "leaders_organizational_skill",
        JsonValue::string(f64_digest(&particle.leaders.organizational_skill)),
    );
    value.insert(
        "leaders_active",
        JsonValue::string(u8_digest(&particle.leaders.active)),
    );
    value.insert(
        "political_institution_type",
        JsonValue::string(u8_digest(&particle.political.institution_type)),
    );
    value.insert(
        "political_institution_level",
        JsonValue::string(u8_digest(&particle.political.institution_level)),
    );
    value.insert(
        "political_institution_locality",
        JsonValue::string(u32_digest(&particle.political.institution_locality)),
    );
    value.insert(
        "political_institution_district",
        JsonValue::string(u32_digest(&particle.political.institution_district)),
    );
    value.insert(
        "political_institution_capacity",
        JsonValue::string(f64_digest(&particle.political.institution_capacity)),
    );
    value.insert(
        "political_institution_autonomy",
        JsonValue::string(f64_digest(&particle.political.institution_autonomy)),
    );
    value.insert(
        "political_institution_compliance",
        JsonValue::string(f64_digest(&particle.political.institution_compliance)),
    );
    value.insert(
        "political_institution_reach",
        JsonValue::string(f64_digest(&particle.political.institution_reach)),
    );
    value.insert(
        "political_institution_integrity",
        JsonValue::string(f64_digest(&particle.political.institution_integrity)),
    );
    value.insert(
        "political_institution_resources",
        JsonValue::string(f64_digest(&particle.political.institution_resources)),
    );
    value.insert(
        "political_institution_governing_party",
        JsonValue::string(u32_digest(&particle.political.institution_governing_party)),
    );
    value.insert(
        "political_branch_party",
        JsonValue::string(u32_digest(&particle.political.branch_party)),
    );
    value.insert(
        "political_branch_locality",
        JsonValue::string(u32_digest(&particle.political.branch_locality)),
    );
    value.insert(
        "political_branch_resources",
        JsonValue::string(f64_digest(&particle.political.branch_resources)),
    );
    value.insert(
        "political_branch_patronage",
        JsonValue::string(f64_digest(&particle.political.branch_patronage)),
    );
    value.insert(
        "political_branch_electoral_support",
        JsonValue::string(f64_digest(&particle.political.branch_electoral_support)),
    );
    value.insert(
        "political_branch_institutional_influence",
        JsonValue::string(f64_digest(
            &particle.political.branch_institutional_influence,
        )),
    );
    value.insert(
        "political_branch_member_offsets",
        JsonValue::string(u32_digest(&particle.political.branch_member_offsets)),
    );
    value.insert(
        "political_branch_member_indices",
        JsonValue::string(u32_digest(&particle.political.branch_member_indices)),
    );
    value.insert(
        "political_branch_broker_offsets",
        JsonValue::string(u32_digest(&particle.political.branch_broker_offsets)),
    );
    value.insert(
        "political_branch_broker_indices",
        JsonValue::string(u32_digest(&particle.political.branch_broker_indices)),
    );
    value.insert(
        "political_elite_person",
        JsonValue::string(u32_digest(&particle.political.elite_person)),
    );
    value.insert(
        "political_elite_locality",
        JsonValue::string(u32_digest(&particle.political.elite_locality)),
    );
    value.insert(
        "political_elite_network_centrality",
        JsonValue::string(f64_digest(&particle.political.elite_network_centrality)),
    );
    value.insert(
        "political_elite_resources",
        JsonValue::string(f64_digest(&particle.political.elite_resources)),
    );
    value.insert(
        "political_elite_legitimacy",
        JsonValue::string(f64_digest(&particle.political.elite_legitimacy)),
    );
    value.insert(
        "political_elite_institutional_ties",
        JsonValue::string(f64_digest(&particle.political.elite_institutional_ties)),
    );
    value.insert(
        "political_elite_party_alignment",
        JsonValue::string(u32_digest(&particle.political.elite_party_alignment)),
    );
    value.insert(
        "political_ruling_party",
        JsonValue::string(u32_digest(&[particle.political.ruling_party])),
    );
    value.insert(
        "political_private_diversion_stock",
        JsonValue::string(f64_digest(&[particle.political.private_diversion_stock])),
    );
    value.insert(
        "foreign_resources",
        JsonValue::string(f64_digest(&particle.foreign.resources)),
    );
    value.insert(
        "foreign_stability_preference",
        JsonValue::string(f64_digest(&particle.foreign.stability_preference)),
    );
    value.insert(
        "foreign_government_alignment",
        JsonValue::string(f64_digest(&particle.foreign.government_alignment)),
    );
    value.insert(
        "foreign_ideological_alignment",
        JsonValue::string(f64_digest(&particle.foreign.ideological_alignment)),
    );
    value.insert(
        "foreign_border_security_priority",
        JsonValue::string(f64_digest(&particle.foreign.border_security_priority)),
    );
    value.insert(
        "foreign_regional_influence",
        JsonValue::string(f64_digest(&particle.foreign.regional_influence)),
    );
    value.insert(
        "foreign_commercial_interest",
        JsonValue::string(f64_digest(&particle.foreign.commercial_interest)),
    );
    value.insert(
        "foreign_humanitarian_preference",
        JsonValue::string(f64_digest(&particle.foreign.humanitarian_preference)),
    );
    value.insert(
        "foreign_cost_sensitivity",
        JsonValue::string(f64_digest(&particle.foreign.cost_sensitivity)),
    );
    value.insert(
        "foreign_domestic_opposition",
        JsonValue::string(f64_digest(&particle.foreign.domestic_opposition)),
    );
    value.insert(
        "foreign_willingness",
        JsonValue::string(f64_digest(&particle.foreign.willingness)),
    );
    value.insert(
        "foreign_language_profile",
        JsonValue::string(f64_digest(&particle.foreign.language_profile)),
    );
    value.insert(
        "foreign_opportunity",
        JsonValue::string(f64_digest(&particle.foreign.opportunity)),
    );
    value.insert(
        "foreign_rival_offsets",
        JsonValue::string(u32_digest(&particle.foreign.rival_offsets)),
    );
    value.insert(
        "foreign_rival_indices",
        JsonValue::string(u32_digest(&particle.foreign.rival_indices)),
    );
    value.insert(
        "foreign_cumulative_cost",
        JsonValue::string(f64_digest(&particle.foreign.cumulative_cost)),
    );
    value.insert(
        "foreign_cumulative_casualties",
        JsonValue::string(f64_digest(&particle.foreign.cumulative_casualties)),
    );
    value.insert(
        "foreign_border_foreign_state",
        JsonValue::string(u32_digest(&particle.foreign.border_foreign_state)),
    );
    value.insert(
        "foreign_border_district",
        JsonValue::string(u32_digest(&particle.foreign.border_district)),
    );
    value.insert(
        "foreign_border_locality",
        JsonValue::string(u32_digest(&particle.foreign.border_locality)),
    );
    value.insert(
        "foreign_border_terrain_friction",
        JsonValue::string(f64_digest(&particle.foreign.border_terrain_friction)),
    );
    value.insert(
        "foreign_border_infrastructure",
        JsonValue::string(f64_digest(&particle.foreign.border_infrastructure)),
    );
    value.insert(
        "foreign_border_legal_permeability",
        JsonValue::string(f64_digest(&particle.foreign.border_legal_permeability)),
    );
    value.insert(
        "foreign_border_social_permeability",
        JsonValue::string(f64_digest(&particle.foreign.border_social_permeability)),
    );
    value.insert(
        "foreign_border_language_overlap",
        JsonValue::string(f64_digest(&particle.foreign.border_language_overlap)),
    );
    value.insert(
        "foreign_border_kinship_overlap",
        JsonValue::string(f64_digest(&particle.foreign.border_kinship_overlap)),
    );
    value.insert(
        "foreign_border_state_monitoring",
        JsonValue::string(f64_digest(&particle.foreign.border_state_monitoring)),
    );
    value.insert(
        "foreign_belief_foreign_state",
        JsonValue::string(u32_digest(&particle.foreign.belief_foreign_state)),
    );
    value.insert(
        "foreign_belief_locality",
        JsonValue::string(u32_digest(&particle.foreign.belief_locality)),
    );
    value.insert(
        "foreign_belief_government_control",
        JsonValue::string(f64_digest(&particle.foreign.belief_government_control)),
    );
    value.insert(
        "foreign_belief_insurgent_presence",
        JsonValue::string(f64_digest(&particle.foreign.belief_insurgent_presence)),
    );
    value.insert(
        "foreign_belief_confidence",
        JsonValue::string(f64_digest(&particle.foreign.belief_confidence)),
    );
    value.insert(
        "foreign_belief_updated_at",
        JsonValue::string(f64_digest(&particle.foreign.belief_updated_at)),
    );
    value.insert(
        "foreign_interpreter_person",
        JsonValue::string(u32_digest(&particle.foreign.interpreter_person)),
    );
    value.insert(
        "foreign_interpreter_foreign_state",
        JsonValue::string(u32_digest(&particle.foreign.interpreter_foreign_state)),
    );
    value.insert(
        "foreign_interpreter_locality",
        JsonValue::string(u32_digest(&particle.foreign.interpreter_locality)),
    );
    value.insert(
        "foreign_interpreter_foreign_language",
        JsonValue::string(f64_digest(&particle.foreign.interpreter_foreign_language)),
    );
    value.insert(
        "foreign_interpreter_local_language",
        JsonValue::string(f64_digest(&particle.foreign.interpreter_local_language)),
    );
    value.insert(
        "foreign_interpreter_foreign_trust",
        JsonValue::string(f64_digest(&particle.foreign.interpreter_foreign_trust)),
    );
    value.insert(
        "foreign_interpreter_local_trust",
        JsonValue::string(f64_digest(&particle.foreign.interpreter_local_trust)),
    );
    value.insert(
        "foreign_interpreter_cultural_knowledge",
        JsonValue::string(f64_digest(&particle.foreign.interpreter_cultural_knowledge)),
    );
    value.insert(
        "relations_organization_a",
        JsonValue::string(u32_digest(&particle.relations.organization_a)),
    );
    value.insert(
        "relations_organization_b",
        JsonValue::string(u32_digest(&particle.relations.organization_b)),
    );
    value.insert(
        "relations_status",
        JsonValue::string(u8_digest(&particle.relations.status)),
    );
    value.insert(
        "relations_rivalry_memory",
        JsonValue::string(f64_digest(&particle.relations.rivalry_memory)),
    );
    value.insert(
        "relations_hostility_memory",
        JsonValue::string(f64_digest(&particle.relations.hostility_memory)),
    );
    value.insert(
        "relations_cooperation_memory",
        JsonValue::string(f64_digest(&particle.relations.cooperation_memory)),
    );
    value.insert(
        "relations_updated_at",
        JsonValue::string(f64_digest(&particle.relations.updated_at)),
    );
    value.insert(
        "relations_last_interaction_at",
        JsonValue::string(f64_digest(&particle.relations.last_interaction_at)),
    );
    value.insert(
        "relations_has_last_interaction",
        JsonValue::string(u8_digest(&particle.relations.has_last_interaction)),
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

fn zone_belief_key_digest(values: &[pineland_core::state::ZoneBeliefKey]) -> String {
    let mut bytes = Vec::with_capacity(values.len() * 8);
    for key in values {
        bytes.extend_from_slice(&key.observer.to_le_bytes());
        bytes.extend_from_slice(&key.zone.to_le_bytes());
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
    value.insert("formation_fatigue", f64_array(&particle.formations.fatigue));
    value.insert(
        "formation_readiness",
        f64_array(&particle.formations.readiness),
    );
    value.insert(
        "formation_availability",
        f64_array(&particle.formations.availability),
    );
    value.insert(
        "formation_supply_stock",
        f64_array(&particle.formations.supply_stock),
    );
    value.insert(
        "formation_cohesion",
        f64_array(&particle.formations.cohesion),
    );
    value.insert(
        "patrol_route_position",
        u32_array(&particle.patrols.route_position),
    );
    value.insert(
        "patrol_route_target",
        u32_array(&particle.patrols.route_target),
    );
    value.insert(
        "patrol_next_available",
        f64_array(&particle.patrols.next_available),
    );
    value.insert(
        "patrol_last_departure",
        f64_array(&particle.patrols.last_departure),
    );
    value.insert(
        "zone_belief_observer",
        u32_array(
            &particle
                .zone_beliefs
                .keys
                .iter()
                .map(|key| key.observer)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "zone_belief_zone",
        u32_array(
            &particle
                .zone_beliefs
                .keys
                .iter()
                .map(|key| key.zone)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "zone_belief_estimate",
        f64_array(&particle.zone_beliefs.estimate),
    );
    value.insert(
        "zone_belief_confidence",
        f64_array(&particle.zone_beliefs.confidence),
    );
    value.insert(
        "zone_belief_updated_at",
        f64_array(&particle.zone_beliefs.updated_at),
    );
    value.insert(
        "zone_belief_contradiction",
        f64_array(&particle.zone_beliefs.contradiction),
    );
    value.insert(
        "zone_belief_evidence",
        u32_array(&particle.zone_beliefs.evidence_count),
    );
    value.insert(
        "belief_observer",
        u32_array(
            &particle
                .beliefs
                .keys
                .iter()
                .map(|key| key.observer)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "belief_target",
        u32_array(
            &particle
                .beliefs
                .keys
                .iter()
                .map(|key| key.target)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "belief_locality",
        u32_array(
            &particle
                .beliefs
                .keys
                .iter()
                .map(|key| key.locality)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "belief_kind",
        u32_array(
            &particle
                .beliefs
                .keys
                .iter()
                .map(|key| key.kind as u32)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert("belief_presence", f64_array(&particle.beliefs.presence));
    value.insert("belief_control", f64_array(&particle.beliefs.control));
    value.insert("belief_confidence", f64_array(&particle.beliefs.confidence));
    value.insert("belief_updated_at", f64_array(&particle.beliefs.updated_at));
    value.insert(
        "belief_reliable_at",
        f64_array(&particle.beliefs.last_reliable_observation_at),
    );
    value.insert(
        "belief_contradiction",
        f64_array(&particle.beliefs.contradiction),
    );
    value.insert(
        "belief_evidence",
        u32_array(&particle.beliefs.evidence_count),
    );
    value.insert(
        "formation_personnel",
        f64_array(&particle.formations.personnel),
    );
    value.insert(
        "formation_personnel_bits",
        u64_array(&particle.formations.personnel),
    );
    value.insert(
        "formation_organization",
        u32_array(&particle.formations.organization),
    );
    let mut organization_personnel = vec![0.0; particle.organizations.kind.len()];
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.active[formation] != 0 {
            let organization = particle.formations.organization[formation] as usize;
            if let Some(total) = organization_personnel.get_mut(organization) {
                *total += particle.formations.personnel[formation].max(0.0);
            }
        }
    }
    value.insert("organization_personnel", f64_array(&organization_personnel));
    value.insert(
        "logistics_capacity",
        f64_array(&particle.logistics.source_capacity),
    );
    value.insert(
        "logistics_organization",
        u32_array(&particle.logistics.organization),
    );
    value.insert(
        "logistics_locality",
        u32_array(&particle.logistics.locality),
    );
    value.insert(
        "logistics_production",
        f64_array(&particle.logistics.source_production),
    );
    value.insert(
        "logistics_production_bits",
        u64_array(&particle.logistics.source_production),
    );
    value.insert(
        "logistics_stock",
        f64_array(&particle.logistics.source_stock),
    );
    value.insert(
        "household_resources",
        f64_array(&particle.households.resources),
    );
    value.insert(
        "community_language_profile",
        f64_array(&particle.communities.language_profile),
    );
    value.insert(
        "community_member_indices",
        u32_array(&particle.communities.member_indices),
    );
    value.insert(
        "community_member_offsets",
        u32_array(&particle.communities.member_offsets),
    );
    value.insert(
        "community_bridge_members",
        u32_array(&particle.communities.bridge_members),
    );
    value.insert(
        "community_bridge_offsets",
        u32_array(&particle.communities.bridge_offsets),
    );
    value.insert("people_resources", f64_array(&particle.people.resources));
    let mut locality_edge_neighbors = Vec::new();
    let mut locality_edge_weights = Vec::new();
    let mut locality_edge_offsets = vec![0u32];
    for locality in 0..engine.topology.locality_count() {
        for (neighbor, weight) in engine.topology.locality_edges.neighbors(locality) {
            locality_edge_neighbors.push(neighbor);
            locality_edge_weights.push(weight);
        }
        locality_edge_offsets.push(locality_edge_neighbors.len() as u32);
    }
    value.insert(
        "locality_edge_neighbors",
        u32_array(&locality_edge_neighbors),
    );
    value.insert("locality_edge_weights", f64_array(&locality_edge_weights));
    value.insert("locality_edge_offsets", u32_array(&locality_edge_offsets));
    value.insert(
        "organization_capital_social",
        f64_array(&particle.organizations.capital_social),
    );
    value.insert(
        "organization_capital_political",
        f64_array(&particle.organizations.capital_political),
    );
    value.insert(
        "organization_capital_organizational",
        f64_array(&particle.organizations.capital_organizational),
    );
    value.insert(
        "organization_capital_material",
        f64_array(&particle.organizations.capital_material),
    );
    value.insert(
        "organization_phenotype",
        f64_array(&particle.organizations.phenotype),
    );
    value.insert(
        "organization_ideology",
        f64_array(&particle.organizations.ideology),
    );
    value.insert(
        "people_state_legitimacy",
        f64_array(&particle.people.state_legitimacy),
    );
    value.insert(
        "people_government_legitimacy",
        f64_array(&particle.people.government_legitimacy),
    );
    value.insert(
        "people_political_access",
        f64_array(&particle.people.political_access),
    );
    value.insert(
        "people_public_behavior",
        u32_array(
            &particle
                .people
                .public_behavior
                .iter()
                .map(|value| *value as u32)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "people_insurgent_affinity",
        f64_array(&particle.people.insurgent_affinity),
    );
    value.insert(
        "social_edge_person_a",
        u32_array(&particle.social_edges.person_a),
    );
    value.insert(
        "social_edge_person_b",
        u32_array(&particle.social_edges.person_b),
    );
    value.insert(
        "social_edge_layers",
        u32_array(
            &particle
                .social_edges
                .layers
                .iter()
                .map(|value| *value as u32)
                .collect::<Vec<_>>(),
        ),
    );
    value.insert(
        "social_edge_weight",
        f64_array(&particle.social_edges.weight),
    );
    value.insert(
        "social_edge_language_compatibility",
        f64_array(&particle.social_edges.language_compatibility),
    );
    value.insert("social_edge_trust", f64_array(&particle.social_edges.trust));
    value.insert(
        "social_edge_represented_relationships",
        f64_array(&particle.social_edges.represented_relationships),
    );
    value.insert(
        "social_neighbor_offsets",
        u32_array(&particle.social_edges.neighbor_offsets),
    );
    value.insert(
        "social_neighbor_indices",
        u32_array(&particle.social_edges.neighbor_indices),
    );
    value.insert(
        "zone_belief_estimate",
        f64_array(&particle.zone_beliefs.estimate),
    );
    value.insert(
        "command_edge_latency",
        f64_array(&particle.command_edges.latency_hours),
    );
    value.insert(
        "leader_traits",
        f64_array(&[
            particle.leaders.competence.first().copied().unwrap_or(0.0),
            particle.leaders.charisma.first().copied().unwrap_or(0.0),
            particle
                .leaders
                .risk_tolerance
                .first()
                .copied()
                .unwrap_or(0.0),
            particle
                .leaders
                .ideological_rigidity
                .first()
                .copied()
                .unwrap_or(0.0),
            particle
                .leaders
                .political_skill
                .first()
                .copied()
                .unwrap_or(0.0),
            particle
                .leaders
                .organizational_skill
                .first()
                .copied()
                .unwrap_or(0.0),
        ]),
    );
    value
}

fn f64_array(values: &[f64]) -> JsonValue {
    JsonValue::Array(values.iter().copied().map(JsonValue::number).collect())
}

fn u32_array(values: &[u32]) -> JsonValue {
    JsonValue::Array(values.iter().copied().map(JsonValue::integer).collect())
}

fn u64_array(values: &[f64]) -> JsonValue {
    JsonValue::Array(
        values
            .iter()
            .map(|value| JsonValue::integer(value.to_bits()))
            .collect(),
    )
}
