//! Autonomous Pineland Native simulation engine.
//!
//! The model owns a complete trajectory. Callers provide a configuration and
//! receive a completed boundary/result; no Python object or per-event callback
//! is required.

#![allow(clippy::too_many_arguments)]

pub mod access;
pub mod actions;
pub mod assays;
pub mod beliefs;
pub mod combat;
pub mod economy;
pub mod foreign;
pub mod governance;
pub mod information;
pub mod logistics;
pub mod movement;
pub mod organizations;
pub mod partner_force_formal;
pub mod patrol;
pub mod peace;
pub mod physical;
pub mod political;
pub mod recording;
pub mod recruitment;
pub mod social;
pub mod state_regeneration;
pub mod treatment_gate;

use pineland_core::config::{ConfigError, SimulationConfig};
use pineland_core::json::JsonValue;
use pineland_core::rng::{python_sum, seed_from_namespace, PyRandomCompat, RngStreams};
use pineland_core::scheduler::{EventPayload, ScheduledEvent, SchedulerError};
use pineland_core::sha256;
use pineland_core::state::{
    clamp01, BeliefKey, EventRecord, ForeignSystemState, LogisticsState, OrganizationRelationState,
    ParticleState, PersonState, PoliticalState, SecurityPostState, SocialEdgeState, StateError,
    CONTROL_DIMENSIONS,
};
use pineland_core::topology::StaticTopology;
use std::collections::BTreeSet;
use std::fmt;

/// Cache parity/debug environment flags at their call site.
///
/// Trace configuration is a launch-time concern. Re-querying the Windows
/// process environment from inner loops adds shared runtime overhead when many
/// particles execute concurrently, so each literal flag is resolved once.
#[macro_export]
macro_rules! trace_env {
    ($name:literal) => {{
        static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        *ENABLED.get_or_init(|| std::env::var_os($name).is_some())
    }};
}

pub const GOVERNMENT: usize = 0;
pub const MILITARY: usize = 1;
pub const POLICE: usize = 2;
pub const PARTY_1: usize = 3;
pub const PARTY_2: usize = 4;
pub const PARTY_3: usize = 5;
pub const INSURGENT: usize = 6;
// Foreign expeditionary organizations are not part of the initial Pineland
// organization table.  Keep a non-colliding tag for future extensions.
pub const FOREIGN: usize = 7;

/// Frozen baseline for the behavioral partner-force capability assay.
///
/// The assay intentionally excludes training throughput, logistics throughput,
/// command reliability, and support ledgers because those variables are candidate
/// predictors of autonomy rather than behavioral outcomes.
#[derive(Clone, Debug, PartialEq)]
pub struct CapabilityAssayBaseline {
    pub military_personnel: f64,
    pub operational_formations: usize,
    pub covered_localities: usize,
    pub operational_readiness: f64,
}

/// Behavioral capability assay used for paired SUPPORT_ON/SUPPORT_OFF outcomes.
/// Version: pineland.partner_force_capability_assay.v2
#[derive(Clone, Debug, PartialEq)]
pub struct CapabilityAssayResult {
    pub government_control: f64,
    pub military_personnel_retention: f64,
    pub operational_formation_survival: f64,
    pub geographic_coverage_retention: f64,
    pub operational_readiness_retention: f64,
    pub composite_capability: f64,
    pub composite_capability_v1: f64,
}

impl CapabilityAssayResult {
    pub fn to_json(&self) -> JsonValue {
        let mut o = JsonValue::object();
        o.insert(
            "schema_version",
            JsonValue::string("pineland.partner_force_capability_assay.v2"),
        );
        o.insert(
            "government_control",
            JsonValue::number(self.government_control),
        );
        o.insert(
            "military_personnel_retention",
            JsonValue::number(self.military_personnel_retention),
        );
        o.insert(
            "operational_formation_survival",
            JsonValue::number(self.operational_formation_survival),
        );
        o.insert(
            "geographic_coverage_retention",
            JsonValue::number(self.geographic_coverage_retention),
        );
        o.insert(
            "operational_readiness_retention",
            JsonValue::number(self.operational_readiness_retention),
        );
        o.insert(
            "composite_capability",
            JsonValue::number(self.composite_capability),
        );
        o.insert(
            "composite_capability_v1",
            JsonValue::number(self.composite_capability_v1),
        );
        o
    }
}

/// Time-to-failure dynamic telemetry tracking post-withdrawal collapse trajectory.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DynamicFailureMetrics {
    pub time_to_capability_deficit_90: Option<f64>,
    pub time_to_readiness_collapse: Option<f64>,
    pub time_to_supply_exhaustion: Option<f64>,
    pub time_to_first_formation_loss: Option<f64>,
    pub recovery_time_days: Option<f64>,
}

impl DynamicFailureMetrics {
    pub fn to_json(&self) -> JsonValue {
        let mut o = JsonValue::object();
        o.insert(
            "schema_version",
            JsonValue::string("pineland.partner_force_dynamic_failure.v1"),
        );
        if let Some(t) = self.time_to_capability_deficit_90 {
            o.insert("time_to_capability_deficit_90", JsonValue::number(t));
        }
        if let Some(t) = self.time_to_readiness_collapse {
            o.insert("time_to_readiness_collapse", JsonValue::number(t));
        }
        if let Some(t) = self.time_to_supply_exhaustion {
            o.insert("time_to_supply_exhaustion", JsonValue::number(t));
        }
        if let Some(t) = self.time_to_first_formation_loss {
            o.insert("time_to_first_formation_loss", JsonValue::number(t));
        }
        if let Some(t) = self.recovery_time_days {
            o.insert("recovery_time_days", JsonValue::number(t));
        }
        o
    }
}

fn organization_name(index: usize) -> &'static str {
    match index {
        GOVERNMENT => "government",
        MILITARY => "fdf",
        POLICE => "police",
        PARTY_1 => "party-1",
        PARTY_2 => "party-2",
        PARTY_3 => "party-3",
        INSURGENT => "insurgent",
        _ => "unknown",
    }
}

pub fn organization_name_for_particle(
    particle: &pineland_core::state::ParticleState,
    index: usize,
) -> String {
    match index {
        GOVERNMENT => "government".to_string(),
        MILITARY => "fdf".to_string(),
        POLICE => "police".to_string(),
        PARTY_1 => "party-1".to_string(),
        PARTY_2 => "party-2".to_string(),
        PARTY_3 => "party-3".to_string(),
        INSURGENT => "insurgent".to_string(),
        _ => {
            if particle.organizations.kind.get(index).copied() == Some(3) {
                let dynamic_number = particle.organizations.kind[INSURGENT + 1..index]
                    .iter()
                    .filter(|kind| **kind == 3)
                    .count()
                    + 1;
                return format!("armed-{dynamic_number:03}");
            }
            for (form_org, ext_state) in particle
                .formations
                .organization
                .iter()
                .zip(&particle.formations.external_state)
            {
                if *form_org as usize == index && *ext_state != u32::MAX {
                    return format!("foreign-neighbor-{}", *ext_state + 1);
                }
            }
            for (intervention_idx, force_formation) in particle
                .foreign_interventions
                .force_formation
                .iter()
                .enumerate()
            {
                if let Some(org) = particle
                    .formations
                    .organization
                    .get(*force_formation as usize)
                {
                    if *org as usize == index {
                        let state = particle.foreign_interventions.foreign_state[intervention_idx];
                        return format!("foreign-neighbor-{}", state + 1);
                    }
                }
            }
            format!("foreign-neighbor-{}", index - 6)
        }
    }
}

pub fn organization_index_for_particle(
    particle: &pineland_core::state::ParticleState,
    name: &str,
) -> Option<usize> {
    (0..particle.organizations.kind.len())
        .find(|&i| organization_name_for_particle(particle, i) == name)
}

#[derive(Clone, Debug, PartialEq)]
pub enum ModelError {
    Config(ConfigError),
    State(StateError),
    Scheduler(SchedulerError),
    Invalid(String),
}

impl fmt::Display for ModelError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Config(e) => e.fmt(f),
            Self::State(e) => e.fmt(f),
            Self::Scheduler(e) => e.fmt(f),
            Self::Invalid(e) => f.write_str(e),
        }
    }
}
impl std::error::Error for ModelError {}
impl From<ConfigError> for ModelError {
    fn from(value: ConfigError) -> Self {
        Self::Config(value)
    }
}
impl From<StateError> for ModelError {
    fn from(value: StateError) -> Self {
        Self::State(value)
    }
}
impl From<SchedulerError> for ModelError {
    fn from(value: SchedulerError) -> Self {
        Self::Scheduler(value)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SimulationEngine {
    pub config: SimulationConfig,
    pub topology: StaticTopology,
    pub particle: ParticleState,
    pub model_hash: String,
    pub started_at: f64,
    pub last_boundary: f64,
    /// Runtime-only execution policy used by SMC/ensemble propagation.
    ///
    /// This mirrors Python's ``execution_profile == "particle"`` contract:
    /// output-only archives, false-record generation, scheduled checkpoints,
    /// and expensive end-boundary invariant scans are omitted while latent
    /// transition state and RNG streams remain unchanged.  The default is
    /// false so reference/certification execution preserves the full audit
    /// surface.
    pub particle_execution: bool,
}

impl SimulationEngine {
    pub fn new(config: SimulationConfig) -> Result<Self, ModelError> {
        config.validate()?;
        let initialization_seed = config.initialization_seed.unwrap_or(config.seed);
        let generated = StaticTopology::pineland(&config, initialization_seed);
        let topology = generated.topology;
        let geography_rng = generated.geography_rng.clone();
        let organization_count = 7;
        let total_population: f64 = if topology
            .district_population
            .iter()
            .any(|value| *value > 0.0)
        {
            // Python's generator retains the registry population as the
            // represented-population denominator. Locality integer rounding
            // is a display/state allocation and may sum one person above or
            // below that registry total.
            topology.district_population.iter().sum()
        } else {
            // The small synthetic topology remains available to unit tests and
            // low-dimensional smoke runs.  Its scientific generator is only
            // defined for the 17-district Pineland registry.
            config.agent_count as f64
        };
        let government_formations = if config.force_structure.mode == "legacy" {
            17.min(topology.locality_count()).max(1)
        } else {
            config
                .force_structure
                .maximum_initial_formations_per_side
                .min(topology.locality_count())
                .min(ceil_to_usize(
                    total_population * 0.0025
                        / config.force_structure.government_target_personnel.max(1.0),
                ))
                .max(1)
        };
        let insurgent_formations = if config.include_insurgency {
            if config.force_structure.mode == "legacy" {
                1
            } else {
                config
                    .force_structure
                    .maximum_initial_formations_per_side
                    .min(ceil_to_usize(
                        total_population * config.initial_insurgent_share
                            / config.force_structure.insurgent_target_personnel.max(1.0),
                    ))
                    .max(1)
            }
        } else {
            0
        };
        let formation_count = government_formations + insurgent_formations;
        let foothold_count = organization_count * topology.locality_count();
        let mut particle = ParticleState::new_with_people(
            locality_count(&topology),
            topology.microzone_count(),
            config.agent_count,
            organization_count,
            formation_count,
            foothold_count,
            RngStreams::new(config.seed, config.random_stream_namespace.clone()),
        );
        particle.security_posts =
            SecurityPostState::new(topology.locality_count() + government_formations);
        particle.logistics = LogisticsState::new(17 + insurgent_formations);
        particle.beliefs = make_belief_state(&topology, &config);
        let model_hash = sha256::digest_hex(if config.state_regeneration.enabled {
            &b"pineland-native-v2-competitive-reproduction-core"[..]
        } else {
            &b"pineland-native-v1-frozen-core"[..]
        });
        let mut engine = Self {
            config,
            topology,
            particle,
            model_hash,
            started_at: 0.0,
            last_boundary: 0.0,
            particle_execution: false,
        };
        engine.initialize_world(
            government_formations,
            insurgent_formations,
            initialization_seed,
            generated.world_rng,
            generated.physical_rng,
        )?;
        engine
            .particle
            .rng
            .streams
            .insert("geography-generation".to_string(), geography_rng);
        engine.schedule_initial_events()?;
        Ok(engine)
    }

    pub fn from_particle(
        config: SimulationConfig,
        topology: StaticTopology,
        particle: ParticleState,
    ) -> Result<Self, ModelError> {
        config.validate()?;
        if particle.locality.population.len() != topology.locality_count()
            || particle.zones.population_share.len() != topology.microzone_count()
        {
            return Err(ModelError::Invalid(
                "particle and topology dimensions differ".to_string(),
            ));
        }
        particle.validate()?;
        let model_hash = sha256::digest_hex(if config.state_regeneration.enabled {
            &b"pineland-native-v2-competitive-reproduction-core"[..]
        } else {
            &b"pineland-native-v1-frozen-core"[..]
        });
        Ok(Self {
            config,
            topology,
            particle,
            model_hash,
            started_at: 0.0,
            last_boundary: 0.0,
            particle_execution: false,
        })
    }

    /// Select the same bookkeeping-light execution contract used by Python
    /// particle propagation.  This is deliberately runtime-only: it does not
    /// alter scientific configuration, model hashes, or transition equations.
    pub fn configure_particle_execution(&mut self) {
        self.particle_execution = true;
        self.particle.event_log.clear();
        self.particle.counters.event_counts.clear();
    }

    fn materialize_households(&mut self) {
        let count = self
            .particle
            .people
            .household
            .iter()
            .copied()
            .max()
            .map(|value| value as usize + 1)
            .unwrap_or(0);
        let mut households = pineland_core::state::HouseholdState::new(count);
        for household in 0..count {
            let mut members = Vec::new();
            for person in 0..self.particle.people.locality.len() {
                if self.particle.people.household[person] as usize == household {
                    members.push(person as u32);
                }
            }
            if let Some(&first) = members.first() {
                let first = first as usize;
                households.locality[household] = self.particle.people.home[first];
                households.residence[household] = self.particle.people.residence[first];
            }
            // CPython 3.12+ uses its compensated float-sum path for the
            // built-in sum used by Household. Match it at the boundary.
            let mut resource_values = Vec::with_capacity(members.len());
            let mut dependents = 0u32;
            for &person in &members {
                let person = person as usize;
                resource_values.push(self.particle.people.resources[person]);
                dependents += u32::from(self.particle.people.age[person] < 16);
            }
            households.resources[household] = python_sum(&resource_values);
            households.dependents[household] = dependents;
            households.member_indices.extend(members);
            households.member_offsets[household + 1] = households.member_indices.len() as u32;
        }
        self.particle.households = households;
    }

    fn materialize_communities(&mut self, partition: &CommunityPartition) {
        let mut communities = pineland_core::state::CommunityState::new(partition.groups.len());
        for (index, (locality, members, cohesion)) in partition.groups.iter().enumerate() {
            communities.locality[index] = *locality as u32;
            communities.cohesion[index] = *cohesion;
            // SocialCommunity._language_profile uses Python's built-in sum
            // for both the denominator and each weighted language total.
            let total_weight = python_sum(
                &members
                    .iter()
                    .map(|person| self.particle.people.represented_population[*person])
                    .collect::<Vec<_>>(),
            );
            for language in 0..4 {
                let total = python_sum(
                    &members
                        .iter()
                        .map(|person| {
                            self.particle.people.represented_population[*person]
                                * self.particle.people.languages[*person * 4 + language]
                        })
                        .collect::<Vec<_>>(),
                );
                communities.language_profile[index * 4 + language] = total / total_weight.max(1e-9);
            }
            communities
                .member_indices
                .extend(members.iter().map(|person| *person as u32));
            communities.member_offsets[index + 1] = communities.member_indices.len() as u32;
            communities.bridge_offsets[index + 1] = communities.bridge_members.len() as u32;
        }
        self.particle.communities = communities;
    }

    fn initialize_world(
        &mut self,
        government_formations: usize,
        insurgent_formations: usize,
        initialization_seed: u64,
        mut world_rng: PyRandomCompat,
        mut physical_rng: PyRandomCompat,
    ) -> Result<(), ModelError> {
        let n = self.topology.locality_count();
        // Initialization has its own seed contract. Process streams remain
        // rooted at config.seed, while generated geography/population/forces
        // use initialization_seed exactly like the Python reference.
        let scientific_registry = self
            .topology
            .locality_population
            .iter()
            .any(|value| *value > 0.0);
        let locality_population = if scientific_registry {
            self.topology.locality_population.clone()
        } else {
            // Small synthetic topologies are retained for unit tests and CLI
            // smoke runs. They are deliberately outside the Pineland parity
            // certificate, but still receive a valid conserved population.
            vec![1.0; n]
        };
        self.particle.locality.district_population = if self
            .topology
            .district_population
            .iter()
            .any(|value| *value > 0.0)
        {
            self.topology.district_population.clone()
        } else {
            vec![0.0; self.topology.district_count()]
        };
        self.particle.locality.district_population_is_integer = if self
            .topology
            .district_population
            .iter()
            .any(|value| *value > 0.0)
        {
            vec![1; self.topology.district_count()]
        } else {
            vec![0; self.topology.district_count()]
        };
        let total_population: f64 = if self
            .topology
            .district_population
            .iter()
            .any(|value| *value > 0.0)
        {
            python_sum(&self.topology.district_population)
        } else {
            python_sum(&locality_population)
        };
        for (locality, population) in locality_population.iter().copied().enumerate().take(n) {
            let offset = locality * CONTROL_DIMENSIONS;
            self.particle.locality.population[locality] = population;
            self.particle.locality.economic_output[locality] = if scientific_registry {
                self.topology.locality_economic_output[locality]
            } else {
                population
            };
            self.particle.locality.infrastructure[locality] =
                self.topology.locality_infrastructure[locality];
            self.particle.locality.administrative_capacity[locality] =
                self.topology.locality_administrative_capacity[locality];
            self.particle.locality.terrain_friction[locality] =
                self.topology.locality_terrain_friction[locality];
            self.particle.locality.observability[locality] =
                self.topology.locality_observability[locality];
            let base = [
                0.98,
                0.72,
                self.particle.locality.administrative_capacity[locality],
                self.particle.locality.administrative_capacity[locality] * 0.85,
                self.particle.locality.administrative_capacity[locality] * 0.65,
                0.52,
                0.7,
            ];
            self.particle.locality.government_control[offset..offset + CONTROL_DIMENSIONS]
                .copy_from_slice(&base);
            if self.config.include_insurgency {
                self.particle.locality.insurgent_control[offset..offset + CONTROL_DIMENSIONS]
                    .copy_from_slice(&[0.0, 0.01, 0.0, 0.01, 0.01, 0.04, 0.08]);
                let organization_offset =
                    pineland_core::state::LocalityState::organization_control_offset(
                        locality,
                        INSURGENT,
                        self.particle.organizations.kind.len(),
                    );
                self.particle.locality.organization_control
                    [organization_offset..organization_offset + CONTROL_DIMENSIONS]
                    .copy_from_slice(&[0.0, 0.01, 0.0, 0.01, 0.01, 0.04, 0.08]);
            } else {
                self.particle.locality.insurgent_control[offset..offset + CONTROL_DIMENSIONS]
                    .fill(0.0);
            }
            self.particle.locality.government_governance[locality] =
                self.particle.locality.administrative_capacity[locality];
            self.particle.locality.insurgent_governance[locality] = 0.0;
            let range = self.topology.zones_for_locality(locality.into());
            for zone in range {
                // StaticTopology stores the physical-world quadrature, so the
                // dense particle copies it without consuming a process RNG.
                self.particle.zones.population_share[zone] =
                    self.topology.zone_population_share[zone];
                self.particle.zones.infrastructure[zone] = self.topology.zone_infrastructure[zone];
                self.particle.zones.terrain_friction[zone] =
                    self.topology.zone_terrain_friction[zone];
                self.particle.zones.observability[zone] = self.topology.zone_observability[zone];
                self.particle.zones.government_control[zone] =
                    self.particle.locality.government_control[offset + 1];
            }
        }

        // Organization insertion order and party cohesion draws are part of
        // the Python initialization stream.  The dense native table uses the
        // same seven initial organizations even when the insurgent actor is
        // disabled, so array identities remain stable across experiments.
        let organizations = &mut self.particle.organizations;
        organizations.kind = vec![0, 1, 2, 4, 4, 4, 3];
        organizations.active.fill(1);
        organizations.active[INSURGENT] = u8::from(self.config.include_insurgency);
        organizations.capital = vec![
            2_500_000.0,
            600_000.0,
            350_000.0,
            100_000.0,
            100_000.0,
            100_000.0,
            if self.config.include_insurgency {
                80_000.0
            } else {
                0.0
            },
        ];
        organizations.cohesion = vec![
            0.72,
            0.75,
            0.62,
            world_rng.uniform(0.5, 0.8),
            world_rng.uniform(0.5, 0.8),
            world_rng.uniform(0.5, 0.8),
            0.68,
        ];
        organizations.discipline = vec![0.7, 0.78, 0.62, 0.5, 0.5, 0.5, 0.65];
        organizations.accountability = vec![0.55, 0.58, 0.55, 0.55, 0.55, 0.55, 0.25];
        organizations.local_knowledge = vec![0.55, 0.42, 0.7, 0.6, 0.6, 0.6, 0.72];
        organizations.persistence = vec![0.8, 0.72, 0.78, 0.75, 0.75, 0.75, 0.8];
        organizations.mobility = vec![0.7, 0.75, 0.45, 0.5, 0.5, 0.5, 0.65];
        organizations.institutional_quality = vec![0.7, 0.76, 0.58, 0.6, 0.6, 0.6, 0.52];
        organizations.external_support = vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 10_000.0];
        organizations.member_population.fill(0.0);

        let represented_weight = total_population / self.config.agent_count as f64;
        let language_patterns = &self.topology.district_language_patterns;
        let mut household_index = 0u32;
        let mut person_index = 0usize;
        while person_index < self.config.agent_count {
            let remaining = self.config.agent_count - person_index;
            let household_size = python_round_usize(world_rng.lognormvariate(1.15, 0.35))
                .max(1)
                .min(remaining);
            let locality = world_rng
                .choices_indices(n, Some(&locality_population), 1)
                .map_err(|error| {
                    ModelError::Invalid(format!("population locality draw: {error}"))
                })?[0];
            let district = self.topology.locality_to_district[locality] as usize;
            let pattern = language_patterns
                .get(district)
                .map(String::as_str)
                .unwrap_or("FS");
            for _ in 0..household_size {
                let person = person_index;
                let language_offset = person * 4;
                for language in 0..4 {
                    self.particle.people.languages[language_offset + language] =
                        world_rng.uniform(0.02, 0.3);
                }
                for (position, token) in pattern.split('/').enumerate() {
                    if let Some(language) = language_index(token) {
                        self.particle.people.languages[language_offset + language] =
                            if position == 0 {
                                world_rng.uniform(0.7, 1.0)
                            } else {
                                world_rng.uniform(0.45, 0.9)
                            };
                    }
                }
                let federal_support = world_rng.uniform(0.2, 0.75);
                self.particle.people.languages[language_offset] =
                    self.particle.people.languages[language_offset].max(federal_support);

                let preference_offset = person * 3;
                for party in 0..3 {
                    self.particle.people.preferences[preference_offset + party] =
                        world_rng.random();
                }
                let age = python_round_i64(world_rng.normalvariate(34.0, 18.0)).clamp(1, 90) as u8;
                let identity_offset = person * 3;
                for identity in 0..3 {
                    self.particle.people.identities[identity_offset + identity] =
                        world_rng.random();
                }
                let grievance = world_rng
                    .betavariate(2.0, 9.0)
                    .map_err(|error| ModelError::Invalid(format!("grievance draw: {error}")))?;
                let fear = world_rng
                    .betavariate(2.0, 8.0)
                    .map_err(|error| ModelError::Invalid(format!("fear draw: {error}")))?;
                let efficacy = world_rng
                    .betavariate(4.0, 4.0)
                    .map_err(|error| ModelError::Invalid(format!("efficacy draw: {error}")))?;
                let trust = world_rng.uniform(0.3, 0.8);
                let trust_insurgent = world_rng.uniform(0.05, 0.35);
                let resources = represented_weight * world_rng.lognormvariate(0.0, 0.55);
                self.particle.people.locality[person] = locality as u32;
                self.particle.people.home[person] = locality as u32;
                self.particle.people.residence[person] = locality as u32;
                self.particle.people.represented_population[person] = represented_weight;
                self.particle.people.household[person] = household_index;
                self.particle.people.age[person] = age;
                self.particle.people.grievance[person] = grievance;
                self.particle.people.fear[person] = fear;
                self.particle.people.efficacy[person] = efficacy;
                self.particle.people.trust[person] = trust;
                self.particle.people.trust_insurgent[person] = trust_insurgent;
                self.particle.people.resources[person] = resources;
                self.particle.people.expected_control[person * 2] = 0.7;
                self.particle.people.expected_control[person * 2 + 1] = 0.1;
                self.particle.people.state_legitimacy[person] = 0.65;
                self.particle.people.government_legitimacy[person] = 0.55;
                self.particle.people.political_access[person] = 0.45;
                self.particle.people.origin_tie_strength[person] = 1.0;
                // Initial Python persons have no organization-specific
                // insurgent affinity. Trust in the insurgent side is a
                // separate attribute and must not be copied into sympathy.
                self.particle.people.rebel_sympathy[person] = 0.0;
                person_index += 1;
            }
            household_index += 1;
        }

        // The social generator shuffles household IDs by locality before it
        // forms bounded represented-population communities.  This first native
        // state keeps the exact partition for coarse certification runs and
        // consumes the same stream boundary even when every household already
        // exceeds the configured maximum community mass.
        let mut social_rng = self
            .particle
            .rng
            .get("social-network-generation")
            .cloned()
            .unwrap_or_else(|| {
                PyRandomCompat::from_seed(seed_from_namespace(
                    initialization_seed,
                    &self.config.random_stream_namespace,
                    "social-network-generation",
                ))
            });
        let community_partition = assign_household_communities(
            &mut self.particle.people,
            n,
            self.config.social_network.target_community_size as f64
                * self.config.social_network.community_size_unit_population,
            self.config.social_network.minimum_community_size as f64
                * self.config.social_network.community_size_unit_population,
            self.config.social_network.maximum_community_size as f64
                * self.config.social_network.community_size_unit_population,
            &mut social_rng,
        )?;
        self.materialize_households();
        self.materialize_communities(&community_partition);
        materialize_social_graph(
            &mut self.particle,
            &self.topology,
            &self.config,
            &mut social_rng,
        )?;
        self.particle
            .rng
            .streams
            .insert("social-network-generation".to_string(), social_rng);

        // Force placement is independent of civilian resolution.  The force
        // stream consumes one tie-break draw per locality, then the exact
        // capacity ordering is used for the insurgent origins.
        let mut force_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "force-generation",
        ));
        let mut hubs: Vec<usize> = (0..n).collect();
        hubs.sort_by(|left, right| {
            locality_population[*right]
                .total_cmp(&locality_population[*left])
                .then_with(|| left.cmp(right))
        });
        let mut tie_break = vec![0.0; n];
        for value in &mut tie_break {
            *value = force_rng.random();
        }
        let mut origins: Vec<usize> = (0..n).collect();
        origins.sort_by(|left, right| {
            self.particle.locality.administrative_capacity[*left]
                .total_cmp(&self.particle.locality.administrative_capacity[*right])
                .then_with(|| tie_break[*left].total_cmp(&tie_break[*right]))
                .then_with(|| left.cmp(right))
        });
        let government_strength = total_population * 0.0025;
        let government_personnel = government_strength / government_formations.max(1) as f64;
        for (index, locality) in hubs.iter().take(government_formations).copied().enumerate() {
            self.initialize_formation(index, MILITARY, locality, government_personnel, None);
        }
        if self.config.include_insurgency {
            let insurgent_strength = total_population * self.config.initial_insurgent_share;
            let personnel = insurgent_strength / insurgent_formations.max(1) as f64;
            for index in 0..insurgent_formations {
                let locality = origins[index % origins.len()];
                self.initialize_formation(
                    government_formations + index,
                    INSURGENT,
                    locality,
                    personnel,
                    None,
                );
            }
        }
        self.particle
            .rng
            .streams
            .insert("force-generation".to_string(), force_rng);

        // Local armed membership is fractional and is assigned by grievance
        // within each formation locality, with a deterministic nearest-locality
        // fallback for coarse representative populations.
        // The Python initialization ecology assigns civilian membership only
        // for active insurgent organizations. Government formations are field
        // assets, not a second civilian-membership pass.
        if self.config.include_insurgency {
            let organization = INSURGENT;
            let mut targets_by_locality = std::collections::BTreeMap::<usize, f64>::new();
            for formation in 0..self.particle.formations.personnel.len() {
                if self.particle.formations.active[formation] == 0
                    || self.particle.formations.organization[formation] as usize != organization
                {
                    continue;
                }
                *targets_by_locality
                    .entry(self.particle.formations.locality[formation] as usize)
                    .or_default() += self.particle.formations.personnel[formation]
                    / self
                        .config
                        .organization_ecology
                        .fighter_conversion_fraction
                        .max(1e-9);
            }
            let mut formation_localities = Vec::new();
            for (locality, target) in targets_by_locality {
                formation_localities.push(locality);
                let _ = assign_formation_membership(
                    &mut self.particle.people,
                    organization,
                    locality,
                    target,
                );
            }
            // Python computes the fallback target from the completed local
            // assignments.  Re-summing here with the Python-compatible
            // compensated sum avoids carrying a different sequence of
            // subtraction roundoff through the per-locality helper.
            let target_total = python_sum(
                &self
                    .particle
                    .formations
                    .personnel
                    .iter()
                    .enumerate()
                    .filter(|(formation, _)| {
                        self.particle.formations.active[*formation] != 0
                            && self.particle.formations.organization[*formation] as usize
                                == organization
                    })
                    .map(|(_, personnel)| {
                        *personnel
                            / self
                                .config
                                .organization_ecology
                                .fighter_conversion_fraction
                                .max(1e-9)
                    })
                    .collect::<Vec<_>>(),
            );
            let assigned_mass = python_sum(
                &(0..self.particle.people.locality.len())
                    .filter(|person| {
                        self.particle.people.organization[*person] as usize == organization
                    })
                    .map(|person| {
                        self.particle.people.represented_population[person]
                            * self.particle.people.armed_fraction[person]
                    })
                    .collect::<Vec<_>>(),
            );
            let remaining_total = (target_total - assigned_mass).max(0.0);
            if remaining_total > 1e-12 {
                assign_fallback_membership(
                    &mut self.particle.people,
                    &self.topology,
                    organization,
                    remaining_total,
                    &formation_localities,
                );
            }
        }
        let mut member_masses = vec![Vec::<f64>::new(); self.particle.organizations.kind.len()];
        for person in 0..self.particle.people.locality.len() {
            let organization = self.particle.people.organization[person];
            if organization != u32::MAX {
                let index = organization as usize;
                if let Some(values) = member_masses.get_mut(index) {
                    values.push(
                        self.particle.people.represented_population[person]
                            * self.particle.people.armed_fraction[person],
                    );
                }
            }
        }
        for (organization, masses) in member_masses.into_iter().enumerate() {
            self.particle.organizations.member_population[organization] = python_sum(&masses);
        }

        // Sources are one administrative center per district for state forces
        // and one home locality per insurgent formation. This is the 17+9 = 26
        // source boundary in the default 34-locality factorial configuration.
        let district_count = self.topology.district_count();
        let mut source_rows: Vec<(usize, usize)> =
            Vec::with_capacity(district_count + insurgent_formations);
        for district in 0..district_count {
            let locality = (0..n)
                .find(|index| self.topology.locality_to_district[*index] as usize == district)
                .unwrap_or(district.min(n - 1));
            source_rows.push((MILITARY, locality));
        }
        let mut insurgent_source_localities = Vec::new();
        for formation in government_formations..government_formations + insurgent_formations {
            if self.particle.formations.active[formation] != 0 {
                insurgent_source_localities
                    .push(self.particle.formations.home_locality[formation] as usize);
            }
        }
        insurgent_source_localities.sort_unstable();
        insurgent_source_localities.dedup();
        source_rows.extend(
            insurgent_source_localities
                .into_iter()
                .map(|locality| (INSURGENT, locality)),
        );
        self.particle.logistics = LogisticsState::new(source_rows.len());
        let mut logistics_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "logistics-world-generation",
        ));
        let mut formations_by_organization =
            vec![Vec::<usize>::new(); self.particle.organizations.kind.len()];
        for formation in 0..self.particle.formations.personnel.len() {
            let organization = self.particle.formations.organization[formation] as usize;
            if self.particle.formations.active[formation] != 0 {
                formations_by_organization[organization].push(formation);
            }
        }
        for (source, (organization, locality)) in source_rows.iter().copied().enumerate() {
            self.particle.logistics.organization[source] = organization as u32;
            self.particle.logistics.locality[source] = locality as u32;
            let formation_ids = formations_by_organization
                .get(organization)
                .cloned()
                .unwrap_or_default();
            let organization_personnel = python_sum(
                &formation_ids
                    .iter()
                    .map(|formation| self.particle.formations.personnel[*formation])
                    .collect::<Vec<_>>(),
            );
            let organization_daily_requirement = organization_personnel
                * self.config.logistics.presence_consumption_per_person_day
                * self.config.logistics.organization_sustainment_coverage;
            let catchment_weights = if organization == MILITARY {
                source_rows
                    .iter()
                    .filter(|(candidate, _)| *candidate == organization)
                    .map(|(_, source_locality)| {
                        self.topology
                            .district_population
                            .get(self.topology.locality_to_district[*source_locality] as usize)
                            .copied()
                            .unwrap_or(locality_population[*source_locality])
                    })
                    .collect::<Vec<_>>()
            } else {
                let insurgent_sources = source_rows
                    .iter()
                    .filter(|(candidate, _)| *candidate == organization)
                    .map(|(_, source_locality)| *source_locality)
                    .collect::<Vec<_>>();
                insurgent_sources
                    .iter()
                    .map(|source_locality| {
                        python_sum(
                            &formation_ids
                                .iter()
                                .filter(|formation| {
                                    self.particle.formations.home_locality[**formation] as usize
                                        == *source_locality
                                })
                                .map(|formation| self.particle.formations.personnel[*formation])
                                .collect::<Vec<_>>(),
                        )
                    })
                    .collect::<Vec<_>>()
            };
            let total_weight = python_sum(&catchment_weights);
            let source_index = source_rows[..source]
                .iter()
                .filter(|(candidate, _)| *candidate == organization)
                .count();
            let weight = catchment_weights.get(source_index).copied().unwrap_or(0.0);
            let production = organization_daily_requirement * weight / total_weight.max(1.0);
            let capacity = if self.config.logistics.source_capacity_model == "organization_manpower"
            {
                (production
                    / self
                        .config
                        .logistics
                        .source_daily_production_fraction
                        .max(1e-12))
                .max(5_000.0)
            } else {
                let catchment = if organization == MILITARY {
                    self.topology
                        .district_population
                        .get(self.topology.locality_to_district[locality] as usize)
                        .copied()
                        .unwrap_or(locality_population[locality])
                } else {
                    weight
                };
                (catchment * self.config.logistics.source_capacity_per_resident).max(5_000.0)
            };
            self.particle.logistics.source_capacity[source] = capacity;
            self.particle.logistics.source_stock[source] = capacity * 0.7;
            self.particle.logistics.source_production[source] =
                capacity * self.config.logistics.source_daily_production_fraction;
        }
        let mut command_edges = pineland_core::state::CommandEdgeState::default();
        for formation in 0..self.particle.formations.personnel.len() {
            if self.particle.formations.active[formation] == 0 {
                continue;
            }
            let organization = self.particle.formations.organization[formation] as usize;
            let org_quality = self.particle.organizations.institutional_quality[organization];
            self.particle.formations.command[formation] = clamp01(
                0.35 + 0.35 * org_quality + 0.3 * self.particle.formations.command[formation],
            );
            let district = self.topology.locality_to_district
                [self.particle.formations.locality[formation] as usize]
                as usize;
            let connectivity = self
                .topology
                .district_connectivity
                .get(district)
                .copied()
                .unwrap_or(0.5);
            let latency = 1.0 + 6.0 * (1.0 - connectivity) + logistics_rng.uniform(0.0, 1.5);
            command_edges.organization.push(organization as u32);
            command_edges.formation.push(formation as u32);
            command_edges
                .reliability
                .push(self.particle.formations.command[formation]);
            command_edges.latency_hours.push(latency);
        }
        self.particle.command_edges = command_edges;
        self.particle.manpower = pineland_core::state::ManpowerState::default();
        self.particle
            .rng
            .streams
            .insert("logistics-world-generation".to_string(), logistics_rng);

        let post_count = n + government_formations;
        self.particle.security_posts = SecurityPostState::new(post_count);
        for (locality, population) in locality_population.iter().copied().enumerate().take(n) {
            self.particle.security_posts.organization[locality] = POLICE as u32;
            self.particle.security_posts.locality[locality] = locality as u32;
            self.particle.security_posts.microzone[locality] =
                self.topology.locality_central_zone[locality];
            let personnel = (population * 0.0015).clamp(15.0, 300.0);
            self.particle.security_posts.personnel[locality] = personnel;
            self.particle.security_posts.presence[locality] = (personnel / 250.0).clamp(0.0, 1.0);
            self.particle.security_posts.available_fraction[locality] = 0.65;
            self.particle.security_posts.detection_rate[locality] =
                self.config.information.fixed_post_report_rate;
            self.particle.security_posts.reliability[locality] =
                self.config.information.prior_confidence;
            self.particle.security_posts.professionalism[locality] = clamp01(
                0.40 * self.particle.organizations.institutional_quality[POLICE]
                    + 0.30 * self.particle.organizations.discipline[POLICE]
                    + 0.30 * self.particle.organizations.accountability[POLICE],
            );
            self.particle.security_posts.staffed[locality] = 1;
        }
        for formation in 0..government_formations {
            let post = n + formation;
            self.particle.security_posts.organization[post] = MILITARY as u32;
            self.particle.security_posts.locality[post] =
                self.particle.formations.locality[formation];
            self.particle.security_posts.microzone[post] =
                self.particle.formations.microzone[formation];
            self.particle.security_posts.personnel[post] =
                self.particle.formations.personnel[formation];
            self.particle.security_posts.presence[post] =
                (self.particle.formations.personnel[formation] / 2_000.0).clamp(0.0, 1.0);
            self.particle.security_posts.available_fraction[post] = 0.4;
            self.particle.security_posts.formation[post] = formation as u32;
            self.particle.security_posts.detection_rate[post] =
                self.config.information.fixed_post_report_rate;
            self.particle.security_posts.reliability[post] =
                self.config.information.prior_confidence;
            self.particle.security_posts.professionalism[post] = clamp01(
                0.40 * self.particle.organizations.institutional_quality[MILITARY]
                    + 0.30 * self.particle.organizations.discipline[MILITARY]
                    + 0.30 * self.particle.organizations.accountability[MILITARY],
            );
            self.particle.security_posts.staffed[post] = 1;
        }

        // Physical initialization is an authoritative part of the Python
        // world generator, not a later approximation.  Recompute each side's
        // raw zone reach from fixed posts and formation response sources,
        // solve local physical response times on the generated graph, then
        // apply the same zone-level contestation operator before writing the
        // locality physical-control component.
        initialize_physical_control(&mut self.particle, &self.topology, &self.config);

        // Python continues the physical-world RNG after topology, posts, and
        // control construction to seed every observer/zone belief. Store the
        // complete table rather than retaining only the stream continuation.
        let observer_count = if self.config.include_insurgency {
            self.particle.organizations.kind.len()
        } else {
            self.particle.organizations.kind.len().saturating_sub(1)
        };
        let mut zone_keys = Vec::with_capacity(observer_count * self.topology.microzone_count());
        let mut zone_beliefs = pineland_core::state::ZoneBeliefState::new(Vec::new());
        for observer in 0..observer_count {
            for zone in 0..self.topology.microzone_count() {
                let actor = if self.particle.organizations.kind[observer] == 3 {
                    INSURGENT
                } else {
                    GOVERNMENT
                };
                let truth = if actor == INSURGENT {
                    self.particle.zones.insurgent_control[zone]
                } else {
                    self.particle.zones.government_control[zone]
                };
                let noise = physical_rng.uniform(
                    -self.config.physical.zone_observation_noise,
                    self.config.physical.zone_observation_noise,
                );
                zone_keys.push(pineland_core::state::ZoneBeliefKey {
                    observer: observer as u32,
                    zone: zone as u32,
                });
                zone_beliefs.estimate.push(clamp01(truth + noise));
                zone_beliefs.confidence.push(0.35);
                zone_beliefs.updated_at.push(0.0);
                zone_beliefs.last_reliable_observation_at.push(-1.0e9);
                zone_beliefs.evidence_count.push(0);
                zone_beliefs.contradiction.push(0.0);
            }
        }
        zone_beliefs.keys = zone_keys;
        self.particle.zone_beliefs = zone_beliefs;
        self.particle
            .rng
            .streams
            .insert("physical-world-generation".to_string(), physical_rng);

        // Python's organization-ecology initializer materializes capital,
        // phenotype, ideology, and one leader for each active insurgent
        // organization. Keep those values in explicit native state; they are
        // decision inputs, not merely audit metadata.
        if self.config.include_insurgency {
            let organization = INSURGENT;
            let resources = self.particle.organizations.capital[organization];
            let knowledge = self.particle.organizations.local_knowledge[organization];
            let quality = self.particle.organizations.institutional_quality[organization];
            self.particle.organizations.capital_social[organization] =
                clamp01(0.45 + 0.35 * knowledge);
            self.particle.organizations.capital_political[organization] = 0.55;
            self.particle.organizations.capital_organizational[organization] = clamp01(quality);
            self.particle.organizations.capital_material[organization] =
                clamp01(resources / 150_000.0);
            let phenotype = organization * 8;
            self.particle.organizations.phenotype[phenotype] = 0.55;
            self.particle.organizations.phenotype[phenotype + 1] = 0.55;
            self.particle.organizations.phenotype[phenotype + 2] = 0.35;
            self.particle.organizations.phenotype[phenotype + 3] = 0.62;
            self.particle.organizations.phenotype[phenotype + 4] = 0.58;
            self.particle.organizations.phenotype[phenotype + 5] =
                self.particle.organizations.discipline[organization];
            self.particle.organizations.phenotype[phenotype + 6] = knowledge;
            self.particle.organizations.phenotype[phenotype + 7] = clamp01(
                self.particle.organizations.external_support[organization] / resources.max(1.0),
            );
            self.particle.organizations.ideology[organization * 2] = 0.72;
            self.particle.organizations.ideology[organization * 2 + 1] = 0.22;
            self.particle.organizations.adaptation_rate[organization] =
                self.config.organization_ecology.adaptation_rate;
        }

        let mut ecology_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "organization-ecology-generation",
        ));
        if self.config.include_insurgency {
            let mut base = [0.0; 6];
            for value in &mut base {
                *value = ecology_rng.uniform(0.3, 0.8);
            }
            let mut leader = pineland_core::state::LeaderState::default();
            leader.organization.push(INSURGENT as u32);
            let values = (0..6)
                .map(|index| clamp01(base[index] + ecology_rng.normalvariate(0.0, 0.04)))
                .collect::<Vec<_>>();
            leader.competence.push(values[0]);
            leader.charisma.push(values[1]);
            leader.risk_tolerance.push(values[2]);
            leader.ideological_rigidity.push(values[3]);
            leader.political_skill.push(values[4]);
            leader.organizational_skill.push(values[5]);
            leader.active.push(1);
            self.particle.organizations.leader[INSURGENT] = 0;
            self.particle.leaders = leader;
        }
        // The Python generator initializes political institutions after
        // ecology. Materialize the complete political state here, including
        // branch memberships and sampled elite anchors. This is part of the
        // initialization boundary, not optional audit metadata.
        let mut political_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "political-order-generation",
        ));
        let mut political = PoliticalState::new();
        let mut branch_members = vec![Vec::<u32>::new(); n * 3];
        let mut branch_brokers = vec![Vec::<u32>::new(); n * 3];
        for kind in 0..6 {
            let base = if kind == 4 || kind == 0 { 0.68 } else { 0.55 };
            political.institution_type.push(kind as u8);
            political.institution_level.push(0);
            political.institution_locality.push(u32::MAX);
            political.institution_district.push(u32::MAX);
            political
                .institution_capacity
                .push(clamp01(base + political_rng.uniform(-0.08, 0.08)));
            political.institution_autonomy.push(0.25);
            political.institution_compliance.push(0.72);
            political.institution_reach.push(0.72);
            political
                .institution_integrity
                .push(clamp01(0.62 + political_rng.uniform(-0.1, 0.1)));
            political.institution_resources.push(0.0);
            political.institution_governing_party.push(PARTY_1 as u32);
        }
        for district in 0..self.topology.district_count() {
            let connectivity = self
                .topology
                .district_connectivity
                .get(district)
                .copied()
                .unwrap_or(0.5);
            political.institution_type.push(6);
            political.institution_level.push(1);
            political.institution_locality.push(u32::MAX);
            political.institution_district.push(district as u32);
            political
                .institution_capacity
                .push(clamp01(0.35 + 0.4 * connectivity));
            political
                .institution_autonomy
                .push(political_rng.uniform(0.45, 0.8));
            political
                .institution_compliance
                .push(political_rng.uniform(0.5, 0.9));
            political.institution_reach.push(connectivity);
            political
                .institution_integrity
                .push(political_rng.uniform(0.45, 0.8));
            political.institution_resources.push(0.0);
            political.institution_governing_party.push(PARTY_1 as u32);
        }
        for locality in 0..n {
            let capacity = self.particle.locality.administrative_capacity[locality];
            let district = self.topology.locality_to_district[locality];
            political.institution_type.push(7);
            political.institution_level.push(2);
            political.institution_locality.push(locality as u32);
            political.institution_district.push(district);
            political.institution_capacity.push(capacity);
            political
                .institution_autonomy
                .push(political_rng.uniform(0.35, 0.8));
            political
                .institution_compliance
                .push(political_rng.uniform(0.45, 0.9));
            political.institution_reach.push(clamp01(
                0.35 + 0.55 * self.particle.locality.infrastructure[locality],
            ));
            political
                .institution_integrity
                .push(political_rng.uniform(0.35, 0.8));
            political.institution_resources.push(0.0);
            political.institution_governing_party.push(PARTY_1 as u32);
            for party in 0..3 {
                political.branch_party.push((PARTY_1 + party) as u32);
                political.branch_locality.push(locality as u32);
                political.branch_resources.push(0.0);
                political.branch_patronage.push(0.0);
                political
                    .branch_electoral_support
                    .push(political_rng.uniform(0.1, 0.5));
                political
                    .branch_institutional_influence
                    .push(political_rng.uniform(0.05, 0.35));
                political.branch_member_offsets.push(0);
                political.branch_broker_offsets.push(0);
            }
        }
        for person in 0..self.particle.people.locality.len() {
            for party in 0..3 {
                self.particle.people.party_legitimacy[person * 3 + party] =
                    political_rng.uniform(0.2, 0.75);
            }
            self.particle.people.state_legitimacy[person] =
                clamp01(0.5 + 0.25 * self.particle.people.trust[person]);
            self.particle.people.government_legitimacy[person] =
                clamp01(0.35 + 0.3 * self.particle.people.trust[person]);
            self.particle.people.political_access[person] =
                clamp01(0.25 + 0.35 * self.particle.people.efficacy[person]);
            if political_rng.random() < 0.28 {
                let preference_offset = person * 3;
                let mut preferred = 0usize;
                for party in 1..3 {
                    // Python's max() retains the first party on exact ties.
                    if self.particle.people.preferences[preference_offset + party]
                        > self.particle.people.preferences[preference_offset + preferred]
                    {
                        preferred = party;
                    }
                }
                let locality = self.particle.people.residence[person] as usize;
                branch_members[locality * 3 + preferred].push(person as u32);
            }
        }
        // LocalElite creation happens after all person-level affiliation
        // draws in Python.  These two uniforms therefore must remain in a
        // separate pass; consuming them while creating the locality rows
        // shifts every subsequent seed stream.
        for locality in 0..n {
            let mut candidate: Option<usize> = None;
            for person in 0..self.particle.people.locality.len() {
                if self.particle.people.residence[person] as usize != locality {
                    continue;
                }
                let degree = self.particle.social_edges.neighbor_offsets[person + 1]
                    - self.particle.social_edges.neighbor_offsets[person];
                if candidate.is_none()
                    || degree
                        > self.particle.social_edges.neighbor_offsets[candidate.unwrap() + 1]
                            - self.particle.social_edges.neighbor_offsets[candidate.unwrap()]
                {
                    candidate = Some(person);
                }
            }
            if let Some(person) = candidate {
                let mut aligned = 0usize;
                for party in 1..3 {
                    if self.particle.people.party_legitimacy[person * 3 + party]
                        > self.particle.people.party_legitimacy[person * 3 + aligned]
                    {
                        aligned = party;
                    }
                }
                let elite = political.elite_person.len();
                political.elite_person.push(person as u32);
                political.elite_locality.push(locality as u32);
                let degree = self.particle.social_edges.neighbor_offsets[person + 1]
                    - self.particle.social_edges.neighbor_offsets[person];
                political
                    .elite_network_centrality
                    .push(clamp01(degree as f64 / 20.0));
                political.elite_resources.push(0.0);
                political
                    .elite_legitimacy
                    .push(political_rng.uniform(0.35, 0.8));
                political
                    .elite_institutional_ties
                    .push(political_rng.uniform(0.3, 0.85));
                political
                    .elite_party_alignment
                    .push((PARTY_1 + aligned) as u32);
                branch_brokers[locality * 3 + aligned].push(elite as u32);
            }
        }
        let mut member_indices = Vec::new();
        let mut broker_indices = Vec::new();
        political.branch_member_offsets.clear();
        political.branch_member_offsets.push(0);
        political.branch_broker_offsets.clear();
        political.branch_broker_offsets.push(0);
        for branch in 0..branch_members.len() {
            member_indices.extend(branch_members[branch].iter().copied());
            political
                .branch_member_offsets
                .push(member_indices.len() as u32);
            broker_indices.extend(branch_brokers[branch].iter().copied());
            political
                .branch_broker_offsets
                .push(broker_indices.len() as u32);
        }
        political.branch_member_indices = member_indices;
        political.branch_broker_indices = broker_indices;
        political.ruling_party = PARTY_1 as u32;
        self.particle.political = political;
        self.particle
            .rng
            .streams
            .insert("political-order-generation".to_string(), political_rng);

        // Foreign initialization follows political initialization in the
        // Python generator. It has its own deterministic stream and retains
        // state rows for every neighbor, border, belief, and interpreter.
        let mut foreign_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "foreign-system-generation",
        ));
        let mut foreign = ForeignSystemState::new();
        let patterns = ["FS", "AR", "VE", "TA", "FS/AR", "VE/TA"];
        let foreign_count = self.config.foreign_affairs.neighbor_count;
        for index in 0..foreign_count {
            let primary = patterns.get(index).copied().unwrap_or("FS");
            for language in ["FS", "AR", "VE", "TA"] {
                foreign
                    .language_profile
                    .push(if primary.contains(language) {
                        0.85
                    } else {
                        0.12
                    });
            }
            foreign
                .resources
                .push(foreign_rng.uniform(600_000.0, 1_800_000.0));
            foreign
                .stability_preference
                .push(foreign_rng.uniform(0.3, 0.9));
            foreign
                .government_alignment
                .push(foreign_rng.uniform(-0.7, 0.9));
            foreign
                .ideological_alignment
                .push(foreign_rng.uniform(-0.8, 0.8));
            foreign
                .border_security_priority
                .push(foreign_rng.uniform(0.35, 0.9));
            foreign
                .regional_influence
                .push(foreign_rng.uniform(0.25, 0.85));
            foreign
                .commercial_interest
                .push(foreign_rng.uniform(0.2, 0.8));
            foreign
                .humanitarian_preference
                .push(foreign_rng.uniform(0.2, 0.85));
            foreign
                .cost_sensitivity
                .push(foreign_rng.uniform(0.3, 0.85));
            foreign
                .domestic_opposition
                .push(foreign_rng.uniform(0.15, 0.65));
            foreign.willingness.push(foreign_rng.uniform(0.35, 0.8));
            foreign.opportunity.push(foreign_rng.uniform(0.4, 0.9));
            foreign.cumulative_cost.push(0.0);
            foreign.cumulative_casualties.push(0.0);
        }
        foreign.rival_offsets.clear();
        foreign.rival_offsets.push(0);
        if foreign_count > 0 {
            for index in 0..foreign_count {
                foreign
                    .rival_indices
                    .push(((index + 1) % foreign_count) as u32);
                foreign
                    .rival_offsets
                    .push(foreign.rival_indices.len() as u32);
            }
        }
        for district in 0..self.topology.district_count() {
            let state = if foreign_count == 0 {
                0
            } else {
                district % foreign_count
            };
            let start = self
                .topology
                .locality_to_district
                .iter()
                .position(|value| *value as usize == district)
                .unwrap_or(0);
            let mut locality = start;
            for candidate in start..n {
                if self.topology.locality_to_district[candidate] as usize != district {
                    continue;
                }
                if self.topology.locality_terrain_friction[candidate]
                    > self.topology.locality_terrain_friction[locality]
                {
                    locality = candidate;
                }
            }
            let pattern = self
                .topology
                .district_language_patterns
                .get(district)
                .map(String::as_str)
                .unwrap_or("FS");
            let overlap = pattern
                .split('/')
                .filter_map(|language| {
                    ["FS", "AR", "VE", "TA"]
                        .iter()
                        .position(|item| *item == language)
                })
                .map(|language| foreign.language_profile[state * 4 + language])
                .fold(0.0, f64::max);
            foreign.border_foreign_state.push(state as u32);
            foreign.border_district.push(district as u32);
            foreign.border_locality.push(locality as u32);
            foreign
                .border_terrain_friction
                .push(self.topology.locality_terrain_friction[locality]);
            foreign
                .border_infrastructure
                .push(self.topology.locality_infrastructure[locality]);
            foreign
                .border_legal_permeability
                .push(foreign_rng.uniform(0.15, 0.8));
            foreign
                .border_social_permeability
                .push(foreign_rng.uniform(0.25, 0.95));
            foreign.border_language_overlap.push(overlap);
            foreign
                .border_kinship_overlap
                .push(foreign_rng.uniform(0.2, 0.85));
            foreign
                .border_state_monitoring
                .push(foreign_rng.uniform(0.25, 0.85));
            foreign.belief_foreign_state.push(state as u32);
            foreign.belief_locality.push(locality as u32);
            foreign.belief_government_control.push(0.5);
            foreign.belief_insurgent_presence.push(0.2);
            foreign.belief_confidence.push(0.12);
            foreign.belief_updated_at.push(0.0);

            let mut candidate: Option<usize> = None;
            for person in 0..self.particle.people.locality.len() {
                if self.particle.people.residence[person] as usize != locality {
                    continue;
                }
                let degree = self.particle.social_edges.neighbor_offsets[person + 1]
                    - self.particle.social_edges.neighbor_offsets[person];
                if candidate.is_none()
                    || degree
                        > self.particle.social_edges.neighbor_offsets[candidate.unwrap() + 1]
                            - self.particle.social_edges.neighbor_offsets[candidate.unwrap()]
                {
                    candidate = Some(person);
                }
            }
            if let Some(person) = candidate {
                let foreign_language = (0..4)
                    .map(|language| {
                        self.particle.people.languages[person * 4 + language]
                            * foreign.language_profile[state * 4 + language]
                    })
                    .collect::<Vec<_>>();
                let local_language = (0..4)
                    .map(|language| self.particle.people.languages[person * 4 + language])
                    .fold(0.0, f64::max);
                let degree = self.particle.social_edges.neighbor_offsets[person + 1]
                    - self.particle.social_edges.neighbor_offsets[person];
                foreign.interpreter_person.push(person as u32);
                foreign.interpreter_foreign_state.push(state as u32);
                foreign.interpreter_locality.push(locality as u32);
                foreign
                    .interpreter_foreign_language
                    .push(python_sum(&foreign_language).max(0.05).clamp(0.0, 1.0));
                foreign.interpreter_local_language.push(local_language);
                foreign.interpreter_foreign_trust.push(0.55);
                foreign
                    .interpreter_local_trust
                    .push(clamp01(0.35 + 0.5 * self.particle.people.trust[person]));
                foreign
                    .interpreter_cultural_knowledge
                    .push(clamp01(0.35 + degree as f64 / 25.0));
            }
        }
        self.particle.foreign = foreign;
        self.particle
            .rng
            .streams
            .insert("foreign-system-generation".to_string(), foreign_rng);

        // Relations are initialized last among the auxiliary generators and
        // are canonicalized by the same lexicographic organization IDs as
        // Python's combinations(sorted(active), 2).
        let mut relation = OrganizationRelationState::default();
        let mut active_ids: Vec<usize> = (0..self.particle.organizations.kind.len())
            .filter(|index| self.particle.organizations.active[*index] != 0)
            .collect();
        active_ids.sort_by_key(|index| organization_name(*index));
        for left in 0..active_ids.len() {
            for right in left + 1..active_ids.len() {
                let first = active_ids[left];
                let second = active_ids[right];
                relation.organization_a.push(first as u32);
                relation.organization_b.push(second as u32);
                let hostile = (first == INSURGENT
                    && matches!(second, GOVERNMENT | MILITARY | POLICE))
                    || (second == INSURGENT && matches!(first, GOVERNMENT | MILITARY | POLICE));
                let allied = matches!(first, GOVERNMENT | MILITARY | POLICE)
                    && matches!(second, GOVERNMENT | MILITARY | POLICE);
                let status = if hostile {
                    4
                } else if allied {
                    0
                } else {
                    2
                };
                relation.status.push(status);
                relation.rivalry_memory.push(0.0);
                relation
                    .hostility_memory
                    .push(if hostile { 1.0 } else { 0.0 });
                relation
                    .cooperation_memory
                    .push(if allied { 1.0 } else { 0.0 });
                relation.updated_at.push(0.0);
                relation.last_interaction_at.push(0.0);
                relation.has_last_interaction.push(0);
            }
        }
        self.particle.relations = relation;
        initialize_footholds(&mut self.particle, &self.topology, &self.config);
        self.particle
            .rng
            .streams
            .insert("organization-ecology-generation".to_string(), ecology_rng);
        self.particle
            .rng
            .streams
            .insert("world-generation".to_string(), world_rng);
        Ok(())
    }

    fn initialize_formation(
        &mut self,
        index: usize,
        organization: usize,
        locality: usize,
        personnel: f64,
        _rng: Option<&mut PyRandomCompat>,
    ) {
        let zone = self.topology.locality_post_zone[locality] as usize;
        let f = &mut self.particle.formations;
        f.organization[index] = organization as u32;
        f.locality[index] = locality as u32;
        f.microzone[index] = zone as u32;
        f.home_locality[index] = locality as u32;
        f.personnel[index] = personnel;
        if organization == INSURGENT {
            f.quality[index] = 0.45;
            f.experience[index] = 0.45;
            f.cohesion[index] = 0.70;
            f.readiness[index] = 0.75;
            f.sustainment[index] = 0.65;
            f.information[index] = 0.50;
            f.mobility[index] = 0.70;
            f.command[index] = 0.55;
            f.embeddedness[index] = 0.75;
        } else {
            f.quality[index] = 0.72;
            f.experience[index] = 0.55;
            f.cohesion[index] = 0.75;
            f.readiness[index] = 0.82;
            f.sustainment[index] = 0.90;
            f.information[index] = 0.55;
            f.mobility[index] = 0.75;
            f.command[index] = 0.72;
            f.embeddedness[index] = 0.35;
        }
        f.supply_capacity[index] = personnel * self.config.logistics.formation_supply_days;
        f.supply_stock[index] =
            f.supply_capacity[index] * self.config.logistics.initial_supply_fraction;
        f.sustainment[index] = self.config.logistics.initial_supply_fraction;
        f.availability[index] = 0.85;
        f.active[index] = u8::from(organization != INSURGENT || self.config.include_insurgency);
        f.operational_status[index] = 1;
        self.particle.patrols.formation[index] = index as u32;
        self.particle.patrols.active[index] = u8::from(organization != INSURGENT);
        self.particle.patrols.route_position[index] =
            u32::from(organization != INSURGENT) * zone as u32;
        self.particle.patrols.route_target[index] =
            u32::from(organization != INSURGENT) * zone as u32;
    }

    fn schedule_initial_events(&mut self) -> Result<(), ModelError> {
        // Match Simulation._populate_scheduler exactly: all initial events
        // are placed at t=0 and their sequence number is the final tie-break.
        // The current Python configuration uses the following priorities.
        for patrol in 0..self.particle.formations.personnel.len() {
            if self.particle.patrols.active[patrol] != 0 {
                self.schedule(
                    0.0,
                    30,
                    EventPayload::Patrol {
                        patrol: (patrol as u32).into(),
                    },
                )?;
            }
        }
        self.schedule(0.0, 19, EventPayload::ContactScan)?;
        self.schedule(0.0, 20, EventPayload::Command)?;
        self.schedule(0.0, 25, EventPayload::ForceMovement)?;
        self.schedule(0.0, 27, EventPayload::Logistics)?;
        self.schedule(0.0, 38, EventPayload::Information)?;
        self.schedule(0.0, 42, EventPayload::Beliefs)?;
        self.schedule(0.0, 35, EventPayload::PhysicalRefresh)?;
        self.schedule(0.0, 45, EventPayload::SocialInfluence)?;
        self.schedule(0.0, 58, EventPayload::OrganizationEcology)?;
        self.schedule(0.0, 57, EventPayload::PoliticalOrder)?;
        self.schedule(0.0, 59, EventPayload::ForeignAffairs)?;
        self.schedule(0.0, 61, EventPayload::PeaceProcess)?;
        self.schedule(0.0, 50, EventPayload::Mobility)?;
        self.schedule(0.0, 70, EventPayload::Governance)?;
        if self.config.state_regeneration.enabled {
            // State regeneration is a distinct causal transition between
            // political allocation and generic governance/economy output.
            self.schedule(0.0, 68, EventPayload::StateRegeneration)?;
        }
        self.schedule(0.0, 80, EventPayload::Economy)?;
        self.schedule(0.0, 85, EventPayload::RecordingNoise)?;
        self.schedule(0.0, 90, EventPayload::Checkpoint)?;
        if self.config.include_insurgency {
            self.schedule(0.0, 60, EventPayload::Recruitment)?;
        }
        Ok(())
    }

    pub fn schedule(
        &mut self,
        time: f64,
        priority: u16,
        payload: EventPayload,
    ) -> Result<u64, ModelError> {
        Ok(self.particle.scheduler.schedule(time, priority, payload)?)
    }

    pub fn advance_until(&mut self, until: f64) -> Result<(), ModelError> {
        self.advance_until_limited(until, None).map(|_| ())
    }

    /// Advance through at most `max_events` events when a limit is supplied.
    ///
    /// The bounded form is a certification/diagnostic boundary: it lets the
    /// Python oracle compare the state immediately after each typed process
    /// without weakening the production `advance_until` contract.
    pub fn advance_until_limited(
        &mut self,
        until: f64,
        max_events: Option<usize>,
    ) -> Result<usize, ModelError> {
        if !until.is_finite() {
            return Err(ModelError::Invalid(
                "target time must be finite".to_string(),
            ));
        }
        if until < self.particle.time {
            return Err(ModelError::Invalid(format!(
                "cannot advance backward from {} to {until}",
                self.particle.time
            )));
        }
        let mut processed = 0usize;
        while self
            .particle
            .scheduler
            .peek()
            .is_some_and(|event| event.time <= until)
            && max_events.is_none_or(|limit| processed < limit)
        {
            let event = self.particle.scheduler.pop_next().expect("peeked event");
            self.particle.time = event.time;
            if crate::trace_env!("PINELAND_MANPOWER_TRACE")
                && event.time >= 69.0
                && event.time <= 70.0
            {
                eprintln!(
                    "MANPOWER_EVENT_BEGIN processed={} time={:.17} kind={} pools={:?}",
                    processed + 1,
                    event.time,
                    event.payload.kind(),
                    (0..self.particle.manpower.pool.len())
                        .map(|index| (
                            self.particle.manpower.organization[index],
                            self.particle.manpower.locality[index],
                            self.particle.manpower.pool[index],
                            self.particle.manpower.supply_reserve[index],
                        ))
                        .collect::<Vec<_>>()
                );
            }
            if crate::trace_env!("PINELAND_EVENT_TRACE") {
                eprintln!(
                    "EVENT {} time={:.17} kind={}",
                    processed + 1,
                    event.time,
                    event.payload.kind()
                );
            }
            if !self.particle_execution {
                self.particle.counters.record(event.payload.kind());
            }
            let sequence = event.sequence;
            // Python closes patrol presence-memory intervals before every
            // boundary that can change a formation's strength, location,
            // availability, or status.  The physical refresh repeats the
            // operation idempotently, but the pre-handler pass is essential
            // for force movement, logistics, contact, and action events.
            let closes_patrol_memory = matches!(
                event.payload,
                EventPayload::PhysicalRefresh
                    | EventPayload::ForceMovement
                    | EventPayload::Logistics
                    | EventPayload::Contact { .. }
                    | EventPayload::OrganizedAction { .. }
                    | EventPayload::Recruitment
                    | EventPayload::OrganizationEcology
                    | EventPayload::ForeignAffairs
                    | EventPayload::PeaceProcess
            );
            if closes_patrol_memory {
                patrol::advance_all_presence_memory(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    event.time,
                );
            }
            let advances_footholds = matches!(
                event.payload,
                EventPayload::ForceMovement
                    | EventPayload::OrganizedAction { .. }
                    | EventPayload::Recruitment
                    | EventPayload::OrganizationEcology
                    | EventPayload::PhysicalRefresh
            );
            if advances_footholds {
                organizations::advance_footholds(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    event.time,
                );
            }
            let formation7_stock_before_event = self
                .particle
                .formations
                .supply_stock
                .get(7)
                .copied()
                .unwrap_or(0.0);
            // Foothold membership is a deterministic projection of four
            // mutable inputs only: person organization, person residence,
            // person armed fraction, and locality population.  Recomputing
            // the full organization × locality × person surface after every
            // scheduler event is therefore redundant for the overwhelming
            // majority of events.  Keep the Python-compatible projection at
            // every boundary that can mutate one of those inputs (directly or
            // through combat/ecology), and skip it elsewhere.
            let refresh_foothold_membership = matches!(
                event.payload,
                EventPayload::Mobility
                    | EventPayload::Recruitment
                    | EventPayload::OrganizationEcology
                    | EventPayload::ForeignAffairs
                    | EventPayload::OrganizedAction { .. }
                    | EventPayload::Contact { .. }
            );
            self.process_event(&event)?;
            if crate::trace_env!("PINELAND_LOGISTICS_FORMATION_TRACE")
                && self
                    .particle
                    .formations
                    .supply_stock
                    .get(7)
                    .copied()
                    .unwrap_or(0.0)
                    != formation7_stock_before_event
            {
                eprintln!(
                    "EVENT_FORMATION7_SUPPLY time={:.17} kind={} before={:.17} after={:.17} before_bits={} after_bits={}",
                    event.time,
                    event.payload.kind(),
                    formation7_stock_before_event,
                    self.particle.formations.supply_stock[7],
                    formation7_stock_before_event.to_bits(),
                    self.particle.formations.supply_stock[7].to_bits()
                );
            }
            if crate::trace_env!("PINELAND_MANPOWER_TRACE")
                && event.time >= 69.0
                && event.time <= 70.0
            {
                eprintln!(
                    "MANPOWER_EVENT_END processed={} time={:.17} kind={} pools={:?}",
                    processed + 1,
                    event.time,
                    event.payload.kind(),
                    (0..self.particle.manpower.pool.len())
                        .map(|index| (
                            self.particle.manpower.organization[index],
                            self.particle.manpower.locality[index],
                            self.particle.manpower.pool[index],
                            self.particle.manpower.supply_reserve[index],
                        ))
                        .collect::<Vec<_>>()
                );
            }
            // Keep the compact foothold projection synchronized exactly when
            // its source state can have changed.  The mask above is audited
            // against all runtime writes to people.organization,
            // people.residence, people.armed_fraction, and
            // locality.population; initialization writes occur before the
            // event loop and are handled during world construction.
            if refresh_foothold_membership {
                recruitment::refresh_foothold_memberships(&mut self.particle, &self.topology);
            }
            if crate::trace_env!("PINELAND_BELIEF_TRACE")
                && matches!(event.payload, EventPayload::Information)
                && event.time >= 3.5
            {
                for (index, key) in self.particle.beliefs.keys.iter().enumerate() {
                    eprintln!(
                        "BTRACE observer={} target={} locality={} kind={} confidence={:.17} presence={:.17} control={:?}",
                        key.observer,
                        key.target,
                        key.locality,
                        key.kind,
                        self.particle.beliefs.confidence[index],
                        self.particle.beliefs.presence[index],
                        &self.particle.beliefs.control[index * CONTROL_DIMENSIONS
                            ..(index + 1) * CONTROL_DIMENSIONS]
                    );
                }
            }
            if advances_footholds {
                organizations::advance_footholds(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    event.time,
                );
            }
            if !self.particle_execution {
                self.particle.event_log.push(EventRecord {
                    time: event.time,
                    sequence,
                    kind: event.payload.kind().to_string(),
                    locality: event_locality(&event),
                    value: 1.0,
                });
            }
            self.reschedule_recurring(&event)?;
            processed += 1;
        }
        let stopped_at_limit = max_events.is_some_and(|limit| {
            processed >= limit
                && self
                    .particle
                    .scheduler
                    .peek()
                    .is_some_and(|event| event.time <= until)
        });
        if !stopped_at_limit {
            self.particle.time = until;
        }
        self.last_boundary = until;
        if !self.particle_execution {
            self.particle.validate()?;
        }
        Ok(processed)
    }

    fn process_event(&mut self, event: &ScheduledEvent) -> Result<(), ModelError> {
        match &event.payload {
            EventPayload::Patrol { .. } => {
                let (rng_key, mut rng) = self.take_rng("process:patrol");
                patrol::advance(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    match &event.payload {
                        EventPayload::Patrol { patrol } => patrol.get() as usize,
                        _ => unreachable!("patrol handler received non-patrol payload"),
                    },
                    event.time,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::PhysicalRefresh => {
                physical::refresh(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::Information => {
                let (rng_key, mut rng) = self.take_rng("process:information");
                information::collect_and_fuse(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.elapsed_days,
                    event.time,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::Beliefs => {
                let (rng_key, mut rng) = self.take_rng("process:beliefs");
                beliefs::decay_and_propagate(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::SocialInfluence => {
                let (rng_key, mut rng) = self.take_rng("process:social_influence");
                social::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::Mobility => {
                let (rng_key, mut rng) = self.take_rng("process:mobility");
                movement::civilian_mobility(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::Recruitment => {
                let (rng_key, mut rng) = self.take_rng("process:recruitment");
                recruitment::recruit(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::OrganizedAction {
                organization,
                locality,
            } => {
                let (rng_key, mut rng) = self.take_rng("process:organized_action");
                actions::opportunities(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    organization.get() as usize,
                    locality.get() as usize,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::ContactScan => {
                let (rng_key, mut rng) = self.take_rng("process:contact_scan");
                let exposure_days = self.config.intervals.contact;
                if self.config.combat.organized_action_architecture == "multichannel_v5" {
                    self.schedule_organized_actions(event.time + exposure_days, exposure_days)?;
                } else {
                    combat::schedule_contacts(
                        &mut self.particle,
                        &self.topology,
                        &self.config,
                        &mut rng,
                        event.time,
                    )?;
                }
                self.put_rng(rng_key, rng);
            }
            EventPayload::Contact {
                first,
                second,
                locality,
                microzone,
            } => {
                let (rng_key, mut rng) = self.take_rng("process:contact");
                combat::resolve_contact(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    first.get() as usize,
                    second.get() as usize,
                    locality.get() as usize,
                    microzone.get() as usize,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::ForceMovement => {
                let arrived = movement::advance_movement_orders(
                    &mut self.particle,
                    &self.topology,
                    event.time,
                );
                for formation in arrived {
                    organizations::record_foothold_arrival(
                        &mut self.particle,
                        &self.topology,
                        &self.config,
                        formation,
                    );
                }
            }
            EventPayload::Logistics => {
                let (rng_key, mut rng) = self.take_rng("process:logistics");
                logistics::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.elapsed_days,
                    event.time,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::Command => {
                let (rng_key, mut rng) = self.take_rng("process:command");
                movement::command(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                )
                .map_err(|error| ModelError::Invalid(format!("movement command: {error}")))?;
                self.put_rng(rng_key, rng);
            }
            EventPayload::Governance => governance::update(
                &mut self.particle,
                &self.topology,
                &self.config,
                event.time,
                event.elapsed_days,
            ),
            EventPayload::StateRegeneration => {
                state_regeneration::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    event.time,
                    event.elapsed_days,
                );
            }
            EventPayload::Economy => economy::update(
                &mut self.particle,
                &self.topology,
                &self.config,
                event.time,
                event.elapsed_days,
            ),
            EventPayload::OrganizationEcology => {
                let (rng_key, mut rng) = self.take_rng("process:organization_ecology");
                organizations::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::PoliticalOrder => {
                let (rng_key, mut rng) = self.take_rng("process:political_order");
                political::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::ForeignAffairs => {
                let (rng_key, mut rng) = self.take_rng("process:foreign_affairs");
                foreign::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::PeaceProcess => {
                let (rng_key, mut rng) = self.take_rng("process:peace_process");
                peace::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::RecordingNoise => {
                if self.particle_execution {
                    return Ok(());
                }
                let (rng_key, mut rng) = self.take_rng("process:recording_noise");
                recording::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                    event.elapsed_days,
                );
                self.put_rng(rng_key, rng);
            }
            EventPayload::Checkpoint => {
                if !self.particle_execution {
                    self.particle.counters.checkpoints =
                        self.particle.counters.checkpoints.saturating_add(1);
                }
            }
            EventPayload::Custom { .. } => {}
        }
        Ok(())
    }

    /// Schedule the one-shot organized-action opportunities emitted by a
    /// multichannel contact scan.  The Python scheduler emits these in active
    /// organization order, then sorted locality order, before it reschedules
    /// the scan itself; preserving that insertion order is part of the event
    /// continuation contract.
    fn schedule_organized_actions(
        &mut self,
        action_time: f64,
        interval_days: f64,
    ) -> Result<(), ModelError> {
        if !self.config.include_insurgency {
            return Ok(());
        }
        let locality_count = self.topology.locality_count();
        for organization in 0..self.particle.organizations.kind.len() {
            let kind = self.particle.organizations.kind[organization];
            let action_kind = matches!(kind, 1 | 2 | 3 | 5);
            if !action_kind
                || self
                    .particle
                    .organizations
                    .active
                    .get(organization)
                    .copied()
                    != Some(1)
            {
                continue;
            }
            for locality in 0..locality_count {
                let (unfielded, fielded) = actions::local_fighter_equivalents(
                    &self.particle,
                    organization,
                    locality,
                    &self.config,
                );
                if unfielded + fielded <= 0.0 {
                    continue;
                }
                self.particle.scheduler.schedule_with_elapsed(
                    action_time,
                    18,
                    interval_days,
                    EventPayload::OrganizedAction {
                        organization: (organization as u32).into(),
                        locality: (locality as u32).into(),
                    },
                )?;
            }
        }
        Ok(())
    }

    fn reschedule_recurring(&mut self, event: &ScheduledEvent) -> Result<(), ModelError> {
        if self.particle_execution
            && matches!(
                event.payload,
                EventPayload::RecordingNoise | EventPayload::Checkpoint
            )
        {
            return Ok(());
        }
        let interval = match event.payload {
            EventPayload::Patrol { patrol } => {
                let patrol = patrol.get() as usize;
                // Python's handler writes a base interval when the patrol's
                // formation is unavailable or moving.  Only a successfully
                // executed patrol route can lengthen the recurrence by its
                // travel time; reusing a stale next_available value here
                // would move an unavailable patrol into the future.
                let base_interval = self.config.intervals.patrol;
                let can_execute = self.particle.patrols.active.get(patrol).copied() == Some(1)
                    && self
                        .particle
                        .patrols
                        .formation
                        .get(patrol)
                        .copied()
                        .and_then(|formation| {
                            self.particle
                                .formations
                                .personnel
                                .get(formation as usize)
                                .map(|personnel| {
                                    let invalid = *personnel <= 0.0
                                        || self
                                            .particle
                                            .formations
                                            .active
                                            .get(formation as usize)
                                            .copied()
                                            != Some(1)
                                        || self
                                            .particle
                                            .formations
                                            .outside_pineland
                                            .get(formation as usize)
                                            .copied()
                                            != Some(0)
                                        || self
                                            .particle
                                            .formations
                                            .moving
                                            .get(formation as usize)
                                            .copied()
                                            != Some(0)
                                        || self
                                            .particle
                                            .formations
                                            .operational_status
                                            .get(formation as usize)
                                            .copied()
                                            != Some(1);
                                    !invalid
                                })
                        })
                        .unwrap_or(false);
                if !can_execute {
                    if crate::trace_env!("PINELAND_SCHED_TRACE")
                        && (18.0..=20.0).contains(&event.time)
                    {
                        eprintln!(
                            "SCHED_RESCHEDULE event_seq={} time={:.17} patrol={} can_execute=0 interval={:.17} next_available={:.17}",
                            event.sequence,
                            event.time,
                            patrol,
                            base_interval,
                            self.particle.patrols.next_available.get(patrol).copied().unwrap_or(0.0)
                        );
                    }
                    base_interval
                } else {
                    let travel_interval = self
                        .particle
                        .patrols
                        .next_available
                        .get(patrol)
                        .copied()
                        .map(|available_at| (available_at - event.time).max(0.0))
                        .unwrap_or(0.0);
                    let interval = base_interval.max(travel_interval);
                    if crate::trace_env!("PINELAND_SCHED_TRACE")
                        && (18.0..=20.0).contains(&event.time)
                    {
                        eprintln!(
                            "SCHED_RESCHEDULE event_seq={} time={:.17} patrol={} can_execute=1 interval={:.17} next_available={:.17}",
                            event.sequence,
                            event.time,
                            patrol,
                            interval,
                            self.particle.patrols.next_available.get(patrol).copied().unwrap_or(0.0)
                        );
                    }
                    interval
                }
            }
            EventPayload::Information => self.config.intervals.information,
            EventPayload::Beliefs => self.config.intervals.beliefs,
            EventPayload::PhysicalRefresh => self.config.intervals.physical_refresh,
            EventPayload::SocialInfluence => self.config.intervals.social_influence,
            EventPayload::Mobility => self.config.intervals.mobility,
            EventPayload::Recruitment => self.config.intervals.recruitment,
            // Organized actions are one-shot realizations emitted by a
            // contact scan. The scan owns the recurring clock; rescheduling
            // an action here would duplicate future opportunities.
            EventPayload::OrganizedAction { .. } => return Ok(()),
            EventPayload::ContactScan => self.config.intervals.contact,
            EventPayload::Logistics => self.config.intervals.logistics,
            EventPayload::ForceMovement => self.config.intervals.force_movement,
            EventPayload::Command => self.config.intervals.command,
            EventPayload::Governance => self.config.intervals.governance,
            EventPayload::StateRegeneration => self.config.state_regeneration.interval_days,
            EventPayload::Economy => self.config.intervals.economy,
            EventPayload::OrganizationEcology => self.config.organization_ecology.interval_days,
            EventPayload::PoliticalOrder => self.config.political_order.interval_days,
            EventPayload::ForeignAffairs => self.config.foreign_affairs.interval_days,
            EventPayload::PeaceProcess => self.config.peace_process.interval_days,
            EventPayload::RecordingNoise => self.config.intervals.information,
            EventPayload::Checkpoint => self.config.intervals.checkpoint,
            _ => return Ok(()),
        };
        // Python's Simulation._reschedule calls scheduler.schedule without a
        // priority argument.  Recurrences therefore use the scheduler
        // default (100), even though their initial t=0 event has a process
        // priority.  Preserving that distinction is required for exact
        // same-time ordering after the first recurrence.
        self.particle.scheduler.schedule_with_elapsed(
            event.time + interval,
            100,
            interval,
            event.payload.clone(),
        )?;
        Ok(())
    }

    fn take_rng(&mut self, name: &str) -> (String, PyRandomCompat) {
        // Use the stream registry's namespace-derived lazy path for every
        // process.  Falling back directly to config.seed would give
        // resampled siblings identical future draws for a stream that had not
        // yet been touched before the branch.
        self.particle.rng.take_owned(name)
    }
    fn put_rng(&mut self, key: String, rng: PyRandomCompat) {
        self.particle.rng.put_owned(key, rng);
    }

    pub fn run(&mut self) -> Result<JsonValue, ModelError> {
        let horizon = self.config.horizon_days;
        if self.config.burn_in_days > 0.0 {
            // The Python reference treats burn-in as an unrecorded negative
            // time phase.  Rebase the already initialized calendar, execute
            // it through analytical time zero, and clear boundary products so
            // only the scientific run appears in output files.
            let burn_in = self.config.burn_in_days;
            self.particle.scheduler.shift_times(-burn_in)?;
            self.particle.time = -burn_in;
            self.advance_until(0.0)?;
            self.particle.event_log.clear();
            self.particle.observations.clear();
            self.particle.counters.event_counts.clear();
            self.particle.counters.contacts = 0;
            self.particle.counters.organized_actions = 0;
            self.particle.counters.recorded_events = 0;
            self.particle.counters.observations = 0;
            self.particle.counters.recruitment = 0.0;
            self.particle.counters.civilian_harm = 0.0;
            self.particle.counters.deaths = 0.0;
            self.particle.counters.checkpoints = 0;
            self.last_boundary = 0.0;
        }
        if horizon < self.particle.time {
            return Err(ModelError::Invalid(format!(
                "horizon {horizon} precedes current time {}",
                self.particle.time
            )));
        }
        self.advance_until(horizon)?;
        Ok(self.summary())
    }

    pub fn summary(&self) -> JsonValue {
        let n = self.topology.locality_count();
        let mut gov = 0.0;
        let mut ins = 0.0;
        for l in 0..n {
            gov += self.particle.locality.effective_control(l, 0);
            ins += self.particle.locality.effective_control(l, 1);
        }
        gov /= n as f64;
        ins /= n as f64;
        let mut o = JsonValue::object();
        o.insert(
            "engine",
            JsonValue::string(if self.config.state_regeneration.enabled {
                "pineland-native-v2-theory"
            } else {
                "pineland-native-v1-compatible"
            }),
        );
        o.insert("model_hash", JsonValue::string(&self.model_hash));
        o.insert(
            "state_regeneration_enabled",
            JsonValue::Bool(self.config.state_regeneration.enabled),
        );
        o.insert("time_days", JsonValue::number(self.particle.time));
        o.insert("localities", JsonValue::number(n as f64));
        o.insert(
            "microzones",
            JsonValue::number(self.topology.microzone_count() as f64),
        );
        o.insert(
            "formations",
            JsonValue::number(self.particle.formations.personnel.len() as f64),
        );
        o.insert("government_control", JsonValue::number(gov));
        o.insert("insurgent_control", JsonValue::number(ins));
        if self.config.state_regeneration.enabled {
            let mean = |values: &[f64]| {
                if values.is_empty() {
                    0.0
                } else {
                    values.iter().sum::<f64>() / values.len() as f64
                }
            };
            let weighted_formation_experience = |organization: usize| {
                let mut numerator = 0.0;
                let mut denominator = 0.0;
                for formation in 0..self.particle.formations.personnel.len() {
                    if self.particle.formations.organization[formation] as usize != organization {
                        continue;
                    }
                    let weight = self.particle.formations.personnel[formation].max(0.0);
                    numerator += weight * self.particle.formations.experience[formation];
                    denominator += weight;
                }
                if denominator > 1.0e-12 {
                    numerator / denominator
                } else {
                    0.0
                }
            };
            let mut police_prof_num = 0.0;
            let mut police_prof_den = 0.0;
            for post in 0..self.particle.security_posts.personnel.len() {
                if self.particle.security_posts.organization[post] as usize != POLICE {
                    continue;
                }
                let weight = self.particle.security_posts.personnel[post].max(0.0);
                police_prof_num += weight * self.particle.security_posts.professionalism[post];
                police_prof_den += weight;
            }
            o.insert(
                "state_security_recruit_pipeline_mean",
                JsonValue::number(mean(
                    &self.particle.locality.government_security_recruit_pipeline,
                )),
            );
            o.insert(
                "state_security_reserve_mean",
                JsonValue::number(mean(&self.particle.locality.government_security_reserve)),
            );
            o.insert(
                "state_intelligence_penetration_mean",
                JsonValue::number(mean(
                    &self.particle.locality.government_intelligence_penetration,
                )),
            );
            o.insert(
                "police_professionalism_mean",
                JsonValue::number(if police_prof_den > 1.0e-12 {
                    police_prof_num / police_prof_den
                } else {
                    0.0
                }),
            );
            o.insert(
                "government_military_experience_mean",
                JsonValue::number(weighted_formation_experience(MILITARY)),
            );
            o.insert(
                "insurgent_formation_experience_mean",
                JsonValue::number(weighted_formation_experience(INSURGENT)),
            );
            o.insert(
                "state_cumulative_security_recruits",
                JsonValue::number(
                    self.particle
                        .locality
                        .government_cumulative_security_recruits
                        .iter()
                        .sum::<f64>(),
                ),
            );
            o.insert(
                "state_cumulative_security_deployments",
                JsonValue::number(
                    self.particle
                        .locality
                        .government_cumulative_security_deployments
                        .iter()
                        .sum::<f64>(),
                ),
            );
            o.insert(
                "state_cumulative_admin_rebuild",
                JsonValue::number(
                    self.particle
                        .locality
                        .government_cumulative_admin_rebuild
                        .iter()
                        .sum::<f64>(),
                ),
            );
            o.insert(
                "state_cumulative_underground_disruption",
                JsonValue::number(
                    self.particle
                        .locality
                        .government_cumulative_underground_disruption
                        .iter()
                        .sum::<f64>(),
                ),
            );
        }
        o.insert(
            "contacts",
            JsonValue::number(self.particle.counters.contacts as f64),
        );
        o.insert(
            "organized_actions",
            JsonValue::number(self.particle.counters.organized_actions as f64),
        );
        o.insert(
            "recorded_events",
            JsonValue::number(self.particle.counters.recorded_events as f64),
        );
        o.insert(
            "observations",
            JsonValue::number(self.particle.counters.observations as f64),
        );
        o.insert(
            "recruitment",
            JsonValue::number(self.particle.counters.recruitment),
        );
        o.insert(
            "civilian_harm",
            JsonValue::number(self.particle.counters.civilian_harm),
        );
        o.insert("deaths", JsonValue::number(self.particle.counters.deaths));
        o.insert("state_hash", JsonValue::string(self.particle.state_hash()));
        o.insert(
            "decision_hash",
            JsonValue::string(self.particle.decision_hash()),
        );
        o.insert(
            "scheduler_events_remaining",
            JsonValue::number(self.particle.scheduler.len() as f64),
        );
        let mut counts = JsonValue::object();
        for (k, v) in &self.particle.counters.event_counts {
            counts.insert(k, JsonValue::number(*v as f64));
        }
        o.insert("event_counts", counts);
        if self.config.partner_force_support.enabled
            || self.particle.partner_support
                != pineland_core::state::PartnerSupportLedger::default()
        {
            o.insert(
                "partner_support_ledger",
                self.particle.partner_support.to_json(),
            );
            o.insert("indigenous_metrics", self.indigenous_state_flow_metrics());
        }
        o
    }

    pub fn state_hash(&self) -> String {
        self.particle.state_hash()
    }
    pub fn decision_hash(&self) -> String {
        self.particle.decision_hash()
    }

    pub fn withdraw_external_partner_support(&mut self) {
        let p = &self.config.partner_force_support;
        if !p.enabled
            || !(p.air.enabled
                || p.logistics.enabled
                || p.command.enabled
                || p.force_generation.enabled)
        {
            return;
        }
        self.particle
            .partner_support
            .take_snapshot(self.particle.time);
        self.particle.partner_support.support_withdrawn = true;
        self.particle.partner_support.withdrawal_time = Some(self.particle.time);
    }

    /// Capture the denominators for the frozen behavioral capability assay at
    /// withdrawal time T.  Both counterfactual branches must use the same copy.
    pub fn capability_assay_baseline(&self) -> CapabilityAssayBaseline {
        let mut military_personnel = 0.0;
        let mut operational_formations = 0usize;
        let mut covered_localities = BTreeSet::new();
        let mut weighted_readiness_sum = 0.0;
        for formation in 0..self.particle.formations.personnel.len() {
            if self.particle.formations.organization[formation] as usize != MILITARY
                || self.particle.formations.active[formation] == 0
                || self.particle.formations.operational_status[formation] == 0
                || self.particle.formations.outside_pineland[formation] != 0
            {
                continue;
            }
            let personnel = self.particle.formations.personnel[formation].max(0.0);
            if personnel <= 0.0 {
                continue;
            }
            military_personnel += personnel;
            operational_formations += 1;
            covered_localities.insert(self.particle.formations.locality[formation]);
            let deployable_readiness =
                (pineland_core::state::clamp01(self.particle.formations.availability[formation])
                    * self.particle.formations.effective_readiness(formation))
                .clamp(0.0, 1.0);
            weighted_readiness_sum += personnel * deployable_readiness;
        }
        let operational_readiness = if military_personnel > 1.0e-12 {
            (weighted_readiness_sum / military_personnel).clamp(0.0, 1.0)
        } else {
            0.0
        };
        CapabilityAssayBaseline {
            military_personnel,
            operational_formations,
            covered_localities: covered_localities.len(),
            operational_readiness,
        }
    }

    /// Measure outcome-facing military capability without reusing autonomy
    /// predictors.  Each component is bounded to [0,1]; the composite is their
    /// geometric mean, so a near-zero behavioral dimension cannot be hidden by
    /// arithmetic compensation in another dimension.
    pub fn capability_assay(&self, baseline: &CapabilityAssayBaseline) -> CapabilityAssayResult {
        let locality_count = self.topology.locality_count().max(1);
        let government_control = (0..locality_count)
            .map(|l| self.particle.locality.effective_control(l, 0))
            .sum::<f64>()
            / locality_count as f64;

        let mut military_personnel = 0.0;
        let mut operational_formations = 0usize;
        let mut covered_localities = BTreeSet::new();
        let mut weighted_readiness_sum = 0.0;
        for formation in 0..self.particle.formations.personnel.len() {
            if self.particle.formations.organization[formation] as usize != MILITARY
                || self.particle.formations.active[formation] == 0
                || self.particle.formations.operational_status[formation] == 0
                || self.particle.formations.outside_pineland[formation] != 0
            {
                continue;
            }
            let personnel = self.particle.formations.personnel[formation].max(0.0);
            if personnel <= 0.0 {
                continue;
            }
            military_personnel += personnel;
            operational_formations += 1;
            covered_localities.insert(self.particle.formations.locality[formation]);
            let deployable_readiness =
                (pineland_core::state::clamp01(self.particle.formations.availability[formation])
                    * self.particle.formations.effective_readiness(formation))
                .clamp(0.0, 1.0);
            weighted_readiness_sum += personnel * deployable_readiness;
        }

        let bounded_ratio = |value: f64, denominator: f64| -> f64 {
            if denominator <= 1.0e-12 {
                0.0
            } else {
                (value / denominator).clamp(0.0, 1.0)
            }
        };
        let personnel_retention = bounded_ratio(military_personnel, baseline.military_personnel);
        let formation_survival = bounded_ratio(
            operational_formations as f64,
            baseline.operational_formations as f64,
        );
        let coverage_retention = bounded_ratio(
            covered_localities.len() as f64,
            baseline.covered_localities as f64,
        );
        let current_readiness = if military_personnel > 1.0e-12 {
            weighted_readiness_sum / military_personnel
        } else {
            0.0
        };
        let readiness_retention = bounded_ratio(current_readiness, baseline.operational_readiness);

        let components_v1 = [
            government_control.clamp(0.0, 1.0),
            personnel_retention,
            formation_survival,
            coverage_retention,
        ];
        let composite_capability_v1 = components_v1.iter().product::<f64>().powf(0.25);

        let components_v2 = [
            government_control.clamp(0.0, 1.0),
            personnel_retention,
            formation_survival,
            coverage_retention,
            readiness_retention,
        ];
        let composite_capability = components_v2.iter().product::<f64>().powf(0.2);

        CapabilityAssayResult {
            government_control: components_v2[0],
            military_personnel_retention: personnel_retention,
            operational_formation_survival: formation_survival,
            geographic_coverage_retention: coverage_retention,
            operational_readiness_retention: readiness_retention,
            composite_capability,
            composite_capability_v1,
        }
    }

    pub fn mean_military_readiness(&self) -> f64 {
        let mut sum = 0.0;
        let mut count = 0usize;
        for i in 0..self.particle.formations.readiness.len() {
            if self.particle.formations.organization[i] as usize == MILITARY
                && self.particle.formations.active[i] != 0
                && self.particle.formations.operational_status[i] != 0
            {
                sum += self.particle.formations.readiness[i];
                count += 1;
            }
        }
        if count > 0 {
            sum / count as f64
        } else {
            0.0
        }
    }

    pub fn min_operational_military_supply_stock(&self) -> f64 {
        let mut min_supply = f64::MAX;
        let mut found = false;
        for i in 0..self.particle.formations.supply_stock.len() {
            if self.particle.formations.organization[i] as usize == MILITARY
                && self.particle.formations.active[i] != 0
                && self.particle.formations.operational_status[i] != 0
            {
                if self.particle.formations.supply_stock[i] < min_supply {
                    min_supply = self.particle.formations.supply_stock[i];
                }
                found = true;
            }
        }
        if found {
            min_supply
        } else {
            0.0
        }
    }

    pub fn active_operational_military_formations(&self) -> usize {
        (0..self.particle.formations.organization.len())
            .filter(|&i| {
                self.particle.formations.organization[i] as usize == MILITARY
                    && self.particle.formations.active[i] != 0
                    && self.particle.formations.operational_status[i] != 0
                    && self.particle.formations.outside_pineland[i] == 0
                    && self.particle.formations.personnel[i] > 0.0
            })
            .count()
    }

    pub fn indigenous_state_flow_metrics(&self) -> JsonValue {
        let mut obj = JsonValue::object();
        let total_air_intensity = self.config.combat.government_air_support_intensity;
        let partner_air_intensity = if self.config.partner_force_support.enabled
            && self.config.partner_force_support.air.enabled
        {
            self.config.partner_force_support.air.intensity
        } else {
            0.0
        };
        obj.insert(
            "indigenous_air_intensity_baseline",
            JsonValue::number(total_air_intensity),
        );
        obj.insert(
            "partner_air_intensity_overlay",
            JsonValue::number(partner_air_intensity),
        );
        obj.insert(
            "partner_air_assisted_contacts",
            JsonValue::number(self.particle.partner_support.air.assisted_contacts as f64),
        );
        obj.insert(
            "partner_air_delivered_intensity",
            JsonValue::number(self.particle.partner_support.air.cumulative_intensity),
        );

        let indigenous_production = self
            .particle
            .partner_support
            .logistics
            .indigenous_cumulative_produced;
        let partner_logistics_delivered =
            self.particle.partner_support.logistics.cumulative_delivered;
        obj.insert(
            "indigenous_logistics_cumulative_produced",
            JsonValue::number(indigenous_production),
        );
        obj.insert(
            "indigenous_logistics_cumulative_delivered",
            JsonValue::number(
                self.particle
                    .partner_support
                    .logistics
                    .indigenous_cumulative_delivered,
            ),
        );
        obj.insert(
            "indigenous_logistics_cumulative_consumed",
            JsonValue::number(
                self.particle
                    .partner_support
                    .logistics
                    .indigenous_cumulative_consumed,
            ),
        );
        obj.insert(
            "partner_logistics_cumulative_delivered",
            JsonValue::number(partner_logistics_delivered),
        );

        let indigenous_graduates = self
            .particle
            .partner_support
            .force_generation
            .indigenous_graduates;
        let incremental_graduates = self
            .particle
            .partner_support
            .force_generation
            .external_incremental_graduates;
        obj.insert(
            "indigenous_graduates",
            JsonValue::number(indigenous_graduates),
        );
        obj.insert(
            "external_incremental_graduates",
            JsonValue::number(incremental_graduates),
        );

        let recruit_pipeline: f64 = self
            .particle
            .locality
            .government_security_recruit_pipeline
            .iter()
            .sum();
        let trained_reserve: f64 = self
            .particle
            .locality
            .government_security_reserve
            .iter()
            .sum();
        obj.insert(
            "recruit_pipeline_stock",
            JsonValue::number(recruit_pipeline),
        );
        obj.insert("trained_reserve_stock", JsonValue::number(trained_reserve));

        let mut military_personnel = 0.0;
        let mut readiness_weighted = 0.0;
        let mut experience_weighted = 0.0;
        let mut supply_stock = 0.0;
        let mut supply_capacity = 0.0;
        for formation in 0..self.particle.formations.personnel.len() {
            if self.particle.formations.organization[formation] as usize != MILITARY {
                continue;
            }
            let personnel = self.particle.formations.personnel[formation].max(0.0);
            military_personnel += personnel;
            readiness_weighted += personnel * self.particle.formations.readiness[formation];
            experience_weighted += personnel * self.particle.formations.experience[formation];
            supply_stock += self.particle.formations.supply_stock[formation].max(0.0);
            supply_capacity += self.particle.formations.supply_capacity[formation].max(0.0);
        }
        obj.insert("military_personnel", JsonValue::number(military_personnel));
        obj.insert(
            "military_readiness_personnel_weighted",
            JsonValue::number(if military_personnel > 1.0e-12 {
                readiness_weighted / military_personnel
            } else {
                0.0
            }),
        );
        obj.insert(
            "military_experience_personnel_weighted",
            JsonValue::number(if military_personnel > 1.0e-12 {
                experience_weighted / military_personnel
            } else {
                0.0
            }),
        );
        obj.insert("military_supply_stock", JsonValue::number(supply_stock));
        obj.insert(
            "military_supply_capacity",
            JsonValue::number(supply_capacity),
        );

        let mut command_edges = 0usize;
        let mut command_reliability = 0.0;
        let mut command_latency = 0.0;
        for edge in 0..self.particle.command_edges.organization.len() {
            if self.particle.command_edges.organization[edge] as usize != MILITARY {
                continue;
            }
            command_edges += 1;
            command_reliability += self.particle.command_edges.reliability[edge];
            command_latency += self.particle.command_edges.latency_hours[edge];
        }
        obj.insert(
            "indigenous_command_reliability_mean",
            JsonValue::number(if command_edges > 0 {
                command_reliability / command_edges as f64
            } else {
                0.0
            }),
        );
        obj.insert(
            "indigenous_command_latency_hours_mean",
            JsonValue::number(if command_edges > 0 {
                command_latency / command_edges as f64
            } else {
                0.0
            }),
        );

        let donor_total_cost = self.particle.partner_support.cumulative_donor_cost();
        obj.insert("cumulative_donor_cost", JsonValue::number(donor_total_cost));
        obj.insert(
            "support_withdrawn",
            JsonValue::Bool(self.particle.partner_support.support_withdrawn),
        );
        if let Some(wt) = self.particle.partner_support.withdrawal_time {
            obj.insert("withdrawal_time", JsonValue::number(wt));
        }
        obj
    }
}

fn python_effective_readiness(particle: &ParticleState, formation: usize) -> f64 {
    let supply_fraction = if particle.formations.supply_capacity[formation] > 0.0 {
        clamp01(
            particle.formations.supply_stock[formation]
                / particle.formations.supply_capacity[formation],
        )
    } else {
        clamp01(particle.formations.sustainment[formation])
    };
    let fatigue_effect = 1.0 - 0.65 * clamp01(particle.formations.fatigue[formation]);
    let fatigue_adjusted = clamp01(particle.formations.readiness[formation] * fatigue_effect);
    let supply_effect = 0.2 + 0.8 * supply_fraction;
    clamp01(fatigue_adjusted * supply_effect * clamp01(particle.formations.command[formation]))
}

fn python_effective_strength(particle: &ParticleState, formation: usize) -> f64 {
    let available = particle.formations.personnel[formation].max(0.0)
        * clamp01(particle.formations.availability[formation])
        * python_effective_readiness(particle, formation);
    if available <= 0.0 {
        0.0
    } else {
        available
            * particle.formations.quality[formation]
            * particle.formations.cohesion[formation]
            * (0.5 + particle.formations.information[formation])
    }
}

fn organization_matches_side(organization: usize, actor: usize) -> bool {
    match actor {
        GOVERNMENT => matches!(organization, GOVERNMENT | MILITARY | POLICE),
        INSURGENT => organization == INSURGENT,
        _ => false,
    }
}

fn local_response_distances(
    particle: &ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    locality: usize,
    actor: usize,
) -> Vec<f64> {
    let zones = topology
        .zones_for_locality(locality.into())
        .collect::<Vec<_>>();
    let mut distances = vec![f64::INFINITY; topology.microzone_count()];
    let mut source_delays = Vec::<(usize, f64)>::new();

    for post in 0..particle.security_posts.locality.len() {
        if particle.security_posts.locality[post] as usize != locality {
            continue;
        }
        let organization = particle.security_posts.organization[post] as usize;
        if !organization_matches_side(organization, actor) {
            continue;
        }
        let mut available = particle.security_posts.available_fraction[post];
        let formation = particle.security_posts.formation[post];
        if formation != u32::MAX {
            let formation = formation as usize;
            if particle.formations.moving[formation] != 0
                || particle.formations.outside_pineland[formation] != 0
                || particle.formations.operational_status[formation] != 1
                || particle.formations.locality[formation] as usize != locality
            {
                available = 0.0;
            } else {
                available *= particle.formations.availability[formation]
                    * python_effective_readiness(particle, formation);
            }
        }
        if available > 0.0 {
            source_delays.push((
                particle.security_posts.microzone[post] as usize,
                (1.0 - available) * config.physical.response_decay_hours,
            ));
        }
    }

    // The Python response operator includes both a formation source and its
    // patrol source.  They have the same opening-day .30 dispatch fraction;
    // retaining one minimum source per formation is numerically equivalent
    // while avoiding a duplicate queue entry.
    for formation in 0..particle.formations.personnel.len() {
        if particle.formations.locality[formation] as usize != locality
            || particle.formations.active[formation] == 0
            || particle.formations.moving[formation] != 0
            || particle.formations.outside_pineland[formation] != 0
            || particle.formations.operational_status[formation] != 1
            || particle.formations.personnel[formation] <= 0.0
            || !organization_matches_side(
                particle.formations.organization[formation] as usize,
                actor,
            )
        {
            continue;
        }
        let effective_fraction = 0.30
            * particle.formations.availability[formation]
            * python_effective_readiness(particle, formation);
        if effective_fraction > 0.0 {
            source_delays.push((
                particle.formations.microzone[formation] as usize,
                (1.0 - effective_fraction) * config.physical.response_decay_hours,
            ));
        }
    }

    // Match Python's cached response operator exactly: first compute
    // topology-only shortest paths from each source with a zero origin, then
    // add the dispatch delay to the completed path.  Seeding Dijkstra with a
    // dispatch delay would reassociate floating-point additions as
    // ``(delay + edge_1) + edge_2`` instead of Python's
    // ``delay + (edge_1 + edge_2)``.
    let mut topology_distances = Vec::with_capacity(source_delays.len());
    for (source, _) in &source_delays {
        let source = *source;
        let mut path = vec![f64::INFINITY; topology.microzone_count()];
        if source >= path.len() || topology.microzone_to_locality[source] as usize != locality {
            topology_distances.push(path);
            continue;
        }
        path[source] = 0.0;
        let mut settled = vec![false; topology.microzone_count()];
        loop {
            let next = zones
                .iter()
                .copied()
                .filter(|zone| !settled[*zone] && path[*zone].is_finite())
                .min_by(|left, right| {
                    path[*left]
                        .total_cmp(&path[*right])
                        .then_with(|| left.cmp(right))
                });
            let Some(zone) = next else { break };
            settled[zone] = true;
            let base = path[zone];
            for (neighbor, travel_time) in topology.physical_edges.neighbors(zone) {
                let neighbor = neighbor as usize;
                if topology.microzone_to_locality[neighbor] as usize != locality
                    || settled[neighbor]
                {
                    continue;
                }
                let candidate = base + travel_time;
                if candidate < path[neighbor] {
                    path[neighbor] = candidate;
                }
            }
        }
        topology_distances.push(path);
    }
    for target in zones {
        let mut best = f64::INFINITY;
        for (index, (_, delay)) in source_delays.iter().enumerate() {
            let candidate = *delay + topology_distances[index][target];
            if candidate < best {
                best = candidate;
            }
        }
        distances[target] = best;
    }
    distances
}

fn initialize_physical_control(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
) {
    let zone_count = topology.microzone_count();
    let locality_count = topology.locality_count();
    let mut raw_government = vec![0.0; zone_count];
    let mut raw_insurgent = vec![0.0; zone_count];

    for locality in 0..locality_count {
        let response_government =
            local_response_distances(particle, topology, config, locality, GOVERNMENT);
        let response_insurgent =
            local_response_distances(particle, topology, config, locality, INSURGENT);
        let zones = topology
            .zones_for_locality(locality.into())
            .collect::<Vec<_>>();

        for zone in zones {
            let mut post_values = [0.0f64; 2];
            for post in 0..particle.security_posts.locality.len() {
                if particle.security_posts.locality[post] as usize != locality
                    || particle.security_posts.microzone[post] as usize != zone
                {
                    continue;
                }
                let organization = particle.security_posts.organization[post] as usize;
                let actor_index = if organization_matches_side(organization, GOVERNMENT) {
                    Some(0)
                } else if organization_matches_side(organization, INSURGENT) {
                    Some(1)
                } else {
                    None
                };
                let Some(actor_index) = actor_index else {
                    continue;
                };
                let mut effective_presence = particle.security_posts.presence[post];
                let formation = particle.security_posts.formation[post];
                if formation != u32::MAX {
                    let formation = formation as usize;
                    if particle.formations.moving[formation] != 0
                        || particle.formations.outside_pineland[formation] != 0
                        || particle.formations.operational_status[formation] != 1
                        || particle.formations.locality[formation] as usize != locality
                    {
                        effective_presence = 0.0;
                    } else {
                        effective_presence *= particle.formations.availability[formation]
                            * python_effective_readiness(particle, formation);
                    }
                }
                post_values[actor_index] += effective_presence;
            }
            let mut formation_values = [0.0f64; 2];
            let denominator = (250.0f64).max(particle.locality.population[locality] * 0.002);
            for formation in 0..particle.formations.personnel.len() {
                if particle.formations.locality[formation] as usize != locality
                    || particle.formations.active[formation] == 0
                    || particle.formations.moving[formation] != 0
                    || particle.formations.outside_pineland[formation] != 0
                    || particle.formations.operational_status[formation] != 1
                    || particle.formations.personnel[formation] <= 0.0
                {
                    continue;
                }
                let actor_index = if organization_matches_side(
                    particle.formations.organization[formation] as usize,
                    GOVERNMENT,
                ) {
                    Some(0)
                } else if organization_matches_side(
                    particle.formations.organization[formation] as usize,
                    INSURGENT,
                ) {
                    Some(1)
                } else {
                    None
                };
                let Some(actor_index) = actor_index else {
                    continue;
                };
                if particle.formations.microzone[formation] as usize == zone {
                    formation_values[actor_index] += config.physical.formation_presence_gain
                        * python_effective_strength(particle, formation)
                        / denominator;
                }
            }
            let government_presence = 1.0
                - (-(config.physical.fixed_post_presence_gain * post_values[0]
                    + formation_values[0]))
                    .exp();
            let insurgent_presence = 1.0
                - (-(config.physical.fixed_post_presence_gain * post_values[1]
                    + formation_values[1]))
                    .exp();
            let government_response = response_government[zone];
            let insurgent_response = response_insurgent[zone];
            raw_government[zone] = clamp01(
                0.55 * government_presence
                    + 0.45
                        * if government_response.is_infinite() {
                            0.0
                        } else {
                            (-government_response / config.physical.response_decay_hours).exp()
                        },
            );
            raw_insurgent[zone] = clamp01(
                0.55 * insurgent_presence
                    + 0.45
                        * if insurgent_response.is_infinite() {
                            0.0
                        } else {
                            (-insurgent_response / config.physical.response_decay_hours).exp()
                        },
            );
        }
    }

    for locality in 0..locality_count {
        let mut government = 0.0;
        let mut insurgent = 0.0;
        for zone in topology.zones_for_locality(locality.into()) {
            let government_value =
                clamp01(raw_government[zone] * (1.0 - 0.35 * raw_insurgent[zone]));
            let insurgent_value =
                clamp01(raw_insurgent[zone] * (1.0 - 0.35 * raw_government[zone]));
            particle.zones.government_control[zone] = government_value;
            particle.zones.insurgent_control[zone] = insurgent_value;
            government += particle.zones.population_share[zone] * government_value;
            insurgent += particle.zones.population_share[zone] * insurgent_value;
        }
        let offset = locality * CONTROL_DIMENSIONS;
        particle.locality.government_control[offset + 1] = clamp01(government);
        particle.locality.insurgent_control[offset + 1] = clamp01(insurgent);
    }
}

fn make_belief_state(
    topology: &StaticTopology,
    config: &SimulationConfig,
) -> pineland_core::state::BeliefState {
    let mut keys = Vec::new();
    for observer in 0..7 {
        for locality in 0..topology.locality_count() {
            keys.push(BeliefKey {
                observer: observer as u32,
                target: INSURGENT as u32,
                locality: locality as u32,
                kind: 0,
            });
            keys.push(BeliefKey {
                observer: observer as u32,
                target: if observer == INSURGENT {
                    INSURGENT as u32
                } else {
                    GOVERNMENT as u32
                },
                locality: locality as u32,
                kind: 1,
            });
            keys.push(BeliefKey {
                observer: observer as u32,
                target: if observer == INSURGENT {
                    GOVERNMENT as u32
                } else {
                    INSURGENT as u32
                },
                locality: locality as u32,
                kind: 2,
            });
        }
    }
    let mut state = pineland_core::state::BeliefState::with_keys(keys);
    for i in 0..state.keys.len() {
        state.confidence[i] = config.information.prior_confidence;
        state.control[i * CONTROL_DIMENSIONS..(i + 1) * CONTROL_DIMENSIONS].fill(0.5);
        state.updated_at[i] = 0.0;
    }
    state
}
fn locality_count(topology: &StaticTopology) -> usize {
    topology.locality_count()
}

fn ceil_to_usize(value: f64) -> usize {
    if !value.is_finite() || value <= 0.0 {
        0
    } else {
        value.ceil() as usize
    }
}

fn python_round_i64(value: f64) -> i64 {
    if !value.is_finite() {
        return 0;
    }
    let lower = value.floor();
    let fraction = value - lower;
    if fraction < 0.5 {
        lower as i64
    } else if fraction > 0.5 {
        lower as i64 + 1
    } else if (lower as i64) % 2 == 0 {
        lower as i64
    } else {
        lower as i64 + 1
    }
}

fn python_round_usize(value: f64) -> usize {
    python_round_i64(value).max(0) as usize
}

fn language_index(value: &str) -> Option<usize> {
    match value {
        "FS" => Some(0),
        "AR" => Some(1),
        "VE" => Some(2),
        "TA" => Some(3),
        _ => None,
    }
}

#[derive(Clone, Debug)]
struct CommunityPartition {
    /// `(locality, person rows in Python community.member_ids order, cohesion)`.
    groups: Vec<(usize, Vec<usize>, f64)>,
}

fn assign_household_communities(
    people: &mut PersonState,
    locality_count: usize,
    minimum: f64,
    target: f64,
    maximum: f64,
    rng: &mut PyRandomCompat,
) -> Result<CommunityPartition, ModelError> {
    let mut households_by_locality: Vec<Vec<usize>> =
        (0..locality_count).map(|_| Vec::new()).collect();
    let mut household_members: std::collections::BTreeMap<usize, Vec<f64>> =
        std::collections::BTreeMap::new();
    for person in 0..people.locality.len() {
        let household = people.household[person] as usize;
        household_members
            .entry(household)
            .or_default()
            .push(people.represented_population[person]);
        let locality = people.locality[person] as usize;
        if locality < locality_count && !households_by_locality[locality].contains(&household) {
            households_by_locality[locality].push(household);
        }
    }
    let household_mass = household_members
        .into_iter()
        .map(|(household, members)| (household, python_sum(&members)))
        .collect::<std::collections::BTreeMap<_, _>>();
    let mut community = 0u32;
    let mut partition = CommunityPartition { groups: Vec::new() };
    for households in &mut households_by_locality {
        households.sort_unstable();
        rng.shuffle_indices(households)
            .map_err(|error| ModelError::Invalid(format!("community shuffle: {error}")))?;
        let mut groups: Vec<Vec<usize>> = Vec::new();
        let mut current: Vec<usize> = Vec::new();
        let mut current_mass = 0.0;
        for household in households.iter().copied() {
            let mass = household_mass.get(&household).copied().unwrap_or(0.0);
            if !current.is_empty() && current_mass + mass > maximum {
                groups.push(std::mem::take(&mut current));
                current_mass = 0.0;
            }
            current.push(household);
            current_mass += mass;
            if current_mass >= target {
                groups.push(std::mem::take(&mut current));
                current_mass = 0.0;
            }
        }
        if !current.is_empty() {
            let mut current_count = current_mass;
            let mut previous_count = groups
                .last()
                .map(|group| {
                    python_sum(
                        &group
                            .iter()
                            .map(|household| household_mass.get(household).copied().unwrap_or(0.0))
                            .collect::<Vec<_>>(),
                    )
                })
                .unwrap_or(0.0);
            if !groups.is_empty()
                && current_count < target / 2.0
                && previous_count + current_count <= maximum
            {
                groups
                    .last_mut()
                    .expect("group exists")
                    .append(&mut current);
            } else {
                if !groups.is_empty() && current_count < minimum {
                    loop {
                        if groups.last().is_none_or(Vec::is_empty) || current_count >= minimum {
                            break;
                        }
                        let candidate = *groups.last().and_then(|group| group.last()).unwrap();
                        let candidate_mass = household_mass.get(&candidate).copied().unwrap_or(0.0);
                        if previous_count - candidate_mass < minimum
                            || current_count + candidate_mass > maximum
                        {
                            break;
                        }
                        groups.last_mut().expect("group exists").pop();
                        current.insert(0, candidate);
                        previous_count -= candidate_mass;
                        current_count += candidate_mass;
                    }
                }
                groups.push(current);
            }
        }
        for group in groups {
            let mut members = Vec::new();
            for household in &group {
                for person in 0..people.locality.len() {
                    if people.household[person] as usize == *household {
                        members.push(person);
                    }
                }
            }
            for person in 0..people.locality.len() {
                if group.contains(&(people.household[person] as usize)) {
                    people.community[person] = community;
                }
            }
            // SocialCommunity construction draws cohesion immediately after
            // each group, before the next locality is shuffled.  Keeping this
            // draw at the same boundary is required for subsequent locality
            // partitions to see the identical Python RNG stream.
            let cohesion = rng.uniform(0.45, 0.85);
            let locality = members
                .first()
                .map(|person| people.locality[*person] as usize)
                .unwrap_or(0);
            partition.groups.push((locality, members, cohesion));
            community = community.saturating_add(1);
        }
    }
    debug_assert_eq!(community as usize, partition.groups.len());
    Ok(partition)
}

fn social_language_compatibility(particle: &ParticleState, first: usize, second: usize) -> f64 {
    let mut result: f64 = 0.0;
    for language in 0..4 {
        result = result.max(
            particle.people.languages[first * 4 + language]
                .min(particle.people.languages[second * 4 + language]),
        );
    }
    clamp01(result)
}

fn social_layer_bit(layer: u8) -> u8 {
    match layer {
        0 => 1, // household
        1 => 2, // community
        2 => 4, // bridge
        _ => 0,
    }
}

#[allow(clippy::too_many_arguments)]
fn add_social_edge(
    particle: &mut ParticleState,
    edge_index: &mut std::collections::BTreeMap<(usize, usize), usize>,
    neighbors: &mut [Vec<usize>],
    first: usize,
    second: usize,
    layer: u8,
    base_strength: f64,
    trust: f64,
    represented_capacity: Option<f64>,
    language_topology_enabled: bool,
) {
    if first == second {
        return;
    }
    let (first, second) = if first < second {
        (first, second)
    } else {
        (second, first)
    };
    let compatibility = social_language_compatibility(particle, first, second);
    let language_factor = if language_topology_enabled {
        0.35 + 0.65 * compatibility
    } else {
        1.0
    };
    let weight = clamp01(base_strength * language_factor);
    let represented_relationships = represented_capacity.unwrap_or_else(|| {
        2.0 * particle.people.represented_population[first]
            * particle.people.represented_population[second]
            / (particle.people.represented_population[first]
                + particle.people.represented_population[second])
                .max(1e-12)
    });
    if let Some(index) = edge_index.get(&(first, second)).copied() {
        particle.social_edges.layers[index] |= social_layer_bit(layer);
        particle.social_edges.weight[index] = particle.social_edges.weight[index].max(weight);
        particle.social_edges.trust[index] = particle.social_edges.trust[index].max(clamp01(trust));
        particle.social_edges.language_compatibility[index] =
            particle.social_edges.language_compatibility[index].max(compatibility);
        particle.social_edges.represented_relationships[index] =
            particle.social_edges.represented_relationships[index]
                .max(represented_relationships.max(0.0));
        return;
    }
    let index = particle.social_edges.person_a.len();
    edge_index.insert((first, second), index);
    particle.social_edges.person_a.push(first as u32);
    particle.social_edges.person_b.push(second as u32);
    particle.social_edges.layers.push(social_layer_bit(layer));
    particle.social_edges.weight.push(weight);
    particle
        .social_edges
        .language_compatibility
        .push(compatibility);
    particle.social_edges.trust.push(clamp01(trust));
    particle
        .social_edges
        .represented_relationships
        .push(represented_relationships.max(0.0));
    neighbors[first].push(second);
    neighbors[second].push(first);
}

fn locality_adjacency_from_topology(
    topology: &StaticTopology,
) -> Vec<std::collections::BTreeMap<usize, f64>> {
    let mut adjacency = (0..topology.locality_count())
        .map(|_| std::collections::BTreeMap::new())
        .collect::<Vec<_>>();
    for (locality, neighbors) in adjacency
        .iter_mut()
        .enumerate()
        .take(topology.locality_count())
    {
        for (neighbor, cost) in topology.locality_edges.neighbors(locality) {
            neighbors.insert(neighbor as usize, cost);
        }
    }
    adjacency
}

fn materialize_social_graph(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
    rng: &mut PyRandomCompat,
) -> Result<(), ModelError> {
    let people_count = particle.people.locality.len();
    particle.social_edges = SocialEdgeState::new(people_count);
    let mut edge_index = std::collections::BTreeMap::<(usize, usize), usize>::new();
    let mut neighbors = (0..people_count).map(|_| Vec::new()).collect::<Vec<_>>();
    let language_enabled = config.social_network.language_topology_enabled;

    // Household multiplex layer. Household rows preserve Python's person
    // insertion order, which is also the order used by the pair loop.
    for household in 0..particle.households.locality.len() {
        let start = particle.households.member_offsets[household] as usize;
        let end = particle.households.member_offsets[household + 1] as usize;
        let members = particle.households.member_indices[start..end].to_vec();
        for (index, first) in members.iter().enumerate() {
            for second in members.iter().skip(index + 1) {
                add_social_edge(
                    particle,
                    &mut edge_index,
                    &mut neighbors,
                    *first as usize,
                    *second as usize,
                    0,
                    config.social_network.household_tie_strength,
                    0.9,
                    None,
                    language_enabled,
                );
            }
        }
    }

    // Community multiplex layer. The shuffle is performed on the temporary
    // member list, just as Python shuffles a list copy, so canonical member
    // order remains available for later bridge ranking.
    for community in 0..particle.communities.locality.len() {
        let start = particle.communities.member_offsets[community] as usize;
        let end = particle.communities.member_offsets[community + 1] as usize;
        let mut members = particle.communities.member_indices[start..end]
            .iter()
            .map(|value| *value as usize)
            .collect::<Vec<_>>();
        let community_cohesion = particle.communities.cohesion[community];
        rng.shuffle_indices(&mut members)
            .map_err(|error| ModelError::Invalid(format!("community member shuffle: {error}")))?;
        if members.len() > 1 {
            for index in 0..members.len() {
                add_social_edge(
                    particle,
                    &mut edge_index,
                    &mut neighbors,
                    members[index],
                    members[(index + 1) % members.len()],
                    1,
                    config.social_network.community_tie_strength,
                    community_cohesion,
                    None,
                    language_enabled,
                );
            }
        }
        for person in members.iter().copied() {
            let target_degree =
                (python_round_i64(rng.normalvariate(config.social_network.mean_social_degree, 2.0))
                    .max(2) as usize)
                    .min(config.social_network.maximum_social_degree);
            let mut attempts = 0usize;
            while neighbors[person].len() < target_degree && attempts < target_degree * 5 {
                attempts += 1;
                let candidate = rng
                    .choice_index(members.len())
                    .map_err(|error| ModelError::Invalid(format!("community choice: {error}")))?;
                let candidate = members[candidate];
                if candidate != person
                    && neighbors[candidate].len() < config.social_network.maximum_social_degree
                {
                    add_social_edge(
                        particle,
                        &mut edge_index,
                        &mut neighbors,
                        person,
                        candidate,
                        1,
                        config.social_network.community_tie_strength * rng.uniform(0.7, 1.0),
                        community_cohesion,
                        None,
                        language_enabled,
                    );
                }
            }
        }
    }

    // Keep the Python insertion order of communities by locality, then use
    // the same represented-mass opportunity weights for cross-community
    // bridges. Cross-locality adjacency is read from the shared generated
    // topology; no identifier-order geography is introduced here.
    let mut communities_by_locality = (0..topology.locality_count())
        .map(|_| Vec::<usize>::new())
        .collect::<Vec<_>>();
    for community in 0..particle.communities.locality.len() {
        communities_by_locality[particle.communities.locality[community] as usize].push(community);
    }
    let locality_adjacency = locality_adjacency_from_topology(topology);
    for community in 0..particle.communities.locality.len() {
        let source_locality = particle.communities.locality[community] as usize;
        let start = particle.communities.member_offsets[community] as usize;
        let end = particle.communities.member_offsets[community + 1] as usize;
        let source_members = particle.communities.member_indices[start..end]
            .iter()
            .map(|value| *value as usize)
            .collect::<Vec<_>>();
        let represented_population = python_sum(
            &source_members
                .iter()
                .map(|person| particle.people.represented_population[*person])
                .collect::<Vec<_>>(),
        );
        let mut target_ids = Vec::new();
        let mut target_weights = Vec::new();
        let mut locality_ids = vec![source_locality];
        locality_ids.extend(locality_adjacency[source_locality].keys().copied());
        for locality in locality_ids {
            let attenuation = if locality == source_locality {
                1.0
            } else {
                1.0 / (1.0 + locality_adjacency[source_locality][&locality].max(0.0))
            };
            for candidate in communities_by_locality[locality].iter().copied() {
                if candidate == community {
                    continue;
                }
                let target_start = particle.communities.member_offsets[candidate] as usize;
                let target_end = particle.communities.member_offsets[candidate + 1] as usize;
                let mass = python_sum(
                    &particle.communities.member_indices[target_start..target_end]
                        .iter()
                        .map(|person| particle.people.represented_population[*person as usize])
                        .collect::<Vec<_>>(),
                ) * attenuation;
                if mass > 0.0 {
                    target_ids.push(candidate);
                    target_weights.push(mass);
                }
            }
        }
        // Python sorts the dictionary keys before passing candidates and
        // weights to random.choices.  Locality traversal is intentionally
        // source-first, so sort the accumulated community IDs separately and
        // carry their weights with them.
        let mut targets = target_ids
            .into_iter()
            .zip(target_weights)
            .collect::<Vec<_>>();
        targets.sort_by_key(|(candidate, _)| *candidate);
        let (target_ids, target_weights): (Vec<_>, Vec<_>) = targets.into_iter().unzip();
        let mut ranking = source_members;
        ranking.sort_by(|left, right| {
            let mut left_languages = (0..4)
                .map(|language| particle.people.languages[*left * 4 + language])
                .collect::<Vec<_>>();
            let mut right_languages = (0..4)
                .map(|language| particle.people.languages[*right * 4 + language])
                .collect::<Vec<_>>();
            left_languages.sort_by(|a, b| b.total_cmp(a));
            right_languages.sort_by(|a, b| b.total_cmp(a));
            // Python's list.sort is stable.  Equal second-language scores
            // therefore retain the community member insertion order; adding
            // an identifier tie-break here changes the RNG-consuming bridge
            // sequence even though the ordering looks deterministic.
            right_languages[1].total_cmp(&left_languages[1])
        });
        let mut remaining = represented_population * clamp01(config.social_network.bridge_fraction);
        if target_ids.is_empty() || remaining <= 0.0 {
            particle.communities.bridge_offsets[community + 1] =
                particle.communities.bridge_members.len() as u32;
            continue;
        }
        for source in ranking {
            if remaining <= 1e-12 {
                break;
            }
            let source_capacity = particle.people.represented_population[source].min(remaining);
            let target_index = rng
                .choices_indices(target_ids.len(), Some(&target_weights), 1)
                .map_err(|error| ModelError::Invalid(format!("bridge target choice: {error}")))?[0];
            let target_community = target_ids[target_index];
            let target_start = particle.communities.member_offsets[target_community] as usize;
            let target_end = particle.communities.member_offsets[target_community + 1] as usize;
            // Python's max returns the first item on a tie.  A hand-written
            // strict comparison preserves that behavior (Iterator::max_by
            // is allowed to retain the later equal item).
            let target = particle.communities.member_indices[target_start..target_end]
                .iter()
                .copied()
                .fold(None, |best: Option<(u32, f64)>, candidate| {
                    let score = social_language_compatibility(particle, source, candidate as usize);
                    match best {
                        None => Some((candidate, score)),
                        Some((_best_candidate, best_score)) if score > best_score => {
                            Some((candidate, score))
                        }
                        Some(existing) => Some(existing),
                    }
                })
                .map(|(candidate, _)| candidate as usize)
                .unwrap_or(0);
            add_social_edge(
                particle,
                &mut edge_index,
                &mut neighbors,
                source,
                target,
                2,
                config.social_network.bridge_tie_strength,
                0.5,
                Some(source_capacity),
                language_enabled,
            );
            particle.communities.bridge_members.push(source as u32);
            remaining -= source_capacity;
        }
        particle.communities.bridge_offsets[community + 1] =
            particle.communities.bridge_members.len() as u32;
    }

    for row in &mut neighbors {
        row.sort_unstable();
    }
    let mut graph = SocialEdgeState::new(people_count);
    graph.person_a = std::mem::take(&mut particle.social_edges.person_a);
    graph.person_b = std::mem::take(&mut particle.social_edges.person_b);
    graph.layers = std::mem::take(&mut particle.social_edges.layers);
    graph.weight = std::mem::take(&mut particle.social_edges.weight);
    graph.language_compatibility =
        std::mem::take(&mut particle.social_edges.language_compatibility);
    graph.trust = std::mem::take(&mut particle.social_edges.trust);
    graph.represented_relationships =
        std::mem::take(&mut particle.social_edges.represented_relationships);
    let mut cursor = 0u32;
    for (person, row) in neighbors.into_iter().enumerate() {
        graph
            .neighbor_indices
            .extend(row.iter().map(|value| *value as u32));
        cursor += row.len() as u32;
        graph.neighbor_offsets[person + 1] = cursor;
    }
    particle.social_edges = graph;
    Ok(())
}

fn locality_distance(topology: &StaticTopology, left: usize, right: usize) -> f64 {
    let dx = topology.x_km[left] - topology.x_km[right];
    let dy = topology.y_km[left] - topology.y_km[right];
    (dx * dx + dy * dy).sqrt()
}

fn assign_formation_membership(
    people: &mut PersonState,
    organization: usize,
    locality: usize,
    target: f64,
) -> f64 {
    if target <= 0.0 {
        return 0.0;
    }
    let mut candidates: Vec<usize> = (0..people.locality.len())
        .filter(|person| {
            people.organization[*person] == u32::MAX
                && people.locality[*person] as usize == locality
        })
        .collect();
    candidates.sort_by(|left, right| {
        people.grievance[*right]
            .total_cmp(&people.grievance[*left])
            .then_with(|| left.cmp(right))
    });
    let mut remaining = target;
    for person in candidates {
        if remaining <= 1e-12 {
            break;
        }
        let represented = people.represented_population[person].max(1e-12);
        let fraction = (remaining / represented).min(1.0);
        people.organization[person] = organization as u32;
        people.armed_fraction[person] = fraction;
        people.rebel_sympathy[person] = fraction;
        let organization_count = people
            .insurgent_affinity
            .len()
            .checked_div(people.locality.len().max(1))
            .unwrap_or(0);
        if organization < organization_count {
            people.insurgent_affinity[person * organization_count + organization] = fraction;
        }
        people.public_behavior[person] = if fraction >= 0.5 { 2 } else { 1 };
        remaining -= represented * fraction;
    }
    remaining.max(0.0)
}

fn assign_fallback_membership(
    people: &mut PersonState,
    topology: &StaticTopology,
    organization: usize,
    target: f64,
    formation_localities: &[usize],
) {
    if target <= 0.0 || formation_localities.is_empty() {
        return;
    }
    let mut candidates: Vec<usize> = (0..people.locality.len())
        .filter(|person| people.organization[*person] == u32::MAX)
        .collect();
    candidates.sort_by(|left, right| {
        let left_distance = formation_localities
            .iter()
            .map(|locality| locality_distance(topology, people.locality[*left] as usize, *locality))
            .min_by(|a, b| a.total_cmp(b))
            .unwrap_or(f64::INFINITY);
        let right_distance = formation_localities
            .iter()
            .map(|locality| {
                locality_distance(topology, people.locality[*right] as usize, *locality)
            })
            .min_by(|a, b| a.total_cmp(b))
            .unwrap_or(f64::INFINITY);
        left_distance
            .total_cmp(&right_distance)
            .then_with(|| people.grievance[*right].total_cmp(&people.grievance[*left]))
            .then_with(|| left.cmp(right))
    });
    let mut remaining = target;
    for person in candidates {
        if remaining <= 1e-12 {
            break;
        }
        let represented = people.represented_population[person].max(1e-12);
        let fraction = (remaining / represented).min(1.0);
        people.organization[person] = organization as u32;
        people.armed_fraction[person] = fraction;
        people.rebel_sympathy[person] = fraction;
        let organization_count = people
            .insurgent_affinity
            .len()
            .checked_div(people.locality.len().max(1))
            .unwrap_or(0);
        if organization < organization_count {
            people.insurgent_affinity[person * organization_count + organization] = fraction;
        }
        people.public_behavior[person] = if fraction >= 0.5 { 2 } else { 1 };
        remaining -= represented * fraction;
    }
}

fn initialize_footholds(
    particle: &mut ParticleState,
    topology: &StaticTopology,
    config: &SimulationConfig,
) {
    let n = topology.locality_count();
    particle.footholds.active.fill(0);
    for organization in 0..particle.organizations.kind.len() {
        for locality in 0..n {
            let index = organization * n + locality;
            particle.footholds.organization[index] = organization as u32;
            particle.footholds.locality[index] = locality as u32;
            particle.footholds.access[index] = if organization == INSURGENT { 0.4 } else { 0.8 };
            particle.footholds.infrastructure[index] = particle.locality.infrastructure[locality];
            particle.footholds.target_knowledge[index] =
                if organization == INSURGENT { 0.25 } else { 0.5 };
            particle.footholds.sustainment[index] =
                if organization == INSURGENT { 0.65 } else { 0.9 };
            if organization != INSURGENT || !config.include_insurgency {
                continue;
            }
            particle.footholds.active[index] = 1;
            let mut local_membership = 0.0;
            let mut home_locality = 0.0;
            let mut home_district = 0.0;
            for person in 0..particle.people.locality.len() {
                if particle.people.organization[person] != organization as u32
                    || particle.people.locality[person] as usize != locality
                    || particle.people.armed_fraction[person] <= 0.0
                {
                    continue;
                }
                let represented = particle.people.represented_population[person]
                    * particle.people.armed_fraction[person];
                local_membership += represented;
                if particle.people.home[person] as usize == locality {
                    home_locality += represented;
                }
                if topology.locality_to_district[particle.people.home[person] as usize]
                    == topology.locality_to_district[locality]
                {
                    home_district += represented;
                }
            }
            let member_depth = clamp01(
                local_membership
                    / config
                        .organization_ecology
                        .minimum_proto_represented_population
                        .max(1e-12),
            );
            let origin_depth = if local_membership > 0.0 {
                clamp01((home_locality / local_membership + home_district / local_membership) / 2.0)
            } else {
                0.0
            };
            let member_channel = member_depth * (0.5 + 0.5 * origin_depth);
            let formation_indices: Vec<usize> = (0..particle.formations.personnel.len())
                .filter(|formation| {
                    particle.formations.active[*formation] != 0
                        && particle.formations.organization[*formation] == organization as u32
                        && particle.formations.locality[*formation] as usize == locality
                })
                .collect();
            let fielded: f64 = formation_indices
                .iter()
                .map(|formation| particle.formations.personnel[*formation])
                .sum();
            let mean_embeddedness = if fielded > 0.0 {
                formation_indices
                    .iter()
                    .map(|formation| {
                        particle.formations.personnel[*formation]
                            * particle.formations.embeddedness[*formation]
                    })
                    .sum::<f64>()
                    / fielded
            } else {
                0.0
            };
            let formation_channel = clamp01(
                fielded
                    / config
                        .organization_ecology
                        .minimum_formation_personnel
                        .max(1.0),
            ) * mean_embeddedness;
            let offset = locality * CONTROL_DIMENSIONS;
            let institutional_channel = clamp01(
                (particle.locality.insurgent_control[offset + 5]
                    + particle.locality.insurgent_control[offset + 2]
                    + particle.locality.insurgent_control[offset + 6])
                    / 3.0,
            );
            let raw = 1.0
                - (1.0 - member_channel)
                    * (1.0 - formation_channel)
                    * (1.0 - institutional_channel);
            particle.footholds.strength[index] = raw;
            particle.footholds.raw_signal[index] = raw;
            particle.footholds.membership[index] =
                clamp01(local_membership / particle.locality.population[locality].max(1e-12));
            particle.footholds.embeddedness[index] = raw;
            let viable = raw
                >= config
                    .organization_ecology
                    .local_foothold_viability_threshold;
            particle.footholds.first_activated_at[index] = if viable { 0.0 } else { -1.0e9 };
            particle.footholds.last_activated_at[index] =
                particle.footholds.first_activated_at[index];
            particle.footholds.viable_activation_count[index] = u32::from(viable);
        }
    }
}

fn event_locality(event: &ScheduledEvent) -> u32 {
    match event.payload {
        EventPayload::OrganizedAction { locality, .. } => locality.get(),
        EventPayload::Contact { locality, .. } => locality.get(),
        _ => u32::MAX,
    }
}
#[cfg(test)]
mod tests {
    use super::{CapabilityAssayBaseline, SimulationEngine};
    use pineland_core::checkpoint::CheckpointStore;
    use pineland_core::config::SimulationConfig;
    use pineland_core::topology::StaticTopology;

    #[test]
    fn native_engine_has_dense_population_patrol_and_post_state() {
        let config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            ..Default::default()
        };
        let engine = SimulationEngine::new(config).unwrap();
        assert_eq!(engine.particle.people.locality.len(), 100);
        assert_eq!(
            engine.particle.patrols.formation.len(),
            engine.particle.formations.organization.len()
        );
        assert!(engine.particle.security_posts.locality.len() >= 4);
        assert!(engine.particle.validate().is_ok());
    }

    #[test]
    fn initialization_seed_is_independent_from_process_seed() {
        let first = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            seed: 11,
            initialization_seed: Some(22),
            ..Default::default()
        };
        let mut second = first.clone();
        second.seed = 33;
        let a = SimulationEngine::new(first).unwrap();
        let b = SimulationEngine::new(second).unwrap();
        assert_eq!(
            a.particle.locality.population,
            b.particle.locality.population
        );
        assert_ne!(a.particle.rng, b.particle.rng);
        let mut changed_initialization = a.config.clone();
        changed_initialization.initialization_seed = Some(44);
        let c = SimulationEngine::new(changed_initialization).unwrap();
        assert_ne!(a.particle.people.grievance, c.particle.people.grievance);
    }

    #[test]
    fn theory_v2_has_distinct_identity_and_exposes_new_theory_state() {
        let legacy_config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            ..Default::default()
        };
        let legacy = SimulationEngine::new(legacy_config.clone()).unwrap();
        let mut theory_config = legacy_config;
        theory_config.state_regeneration.enabled = true;
        let theory = SimulationEngine::new(theory_config).unwrap();
        assert_ne!(legacy.model_hash, theory.model_hash);
        let summary = theory.summary();
        for key in [
            "state_security_recruit_pipeline_mean",
            "state_security_reserve_mean",
            "state_intelligence_penetration_mean",
            "police_professionalism_mean",
            "government_military_experience_mean",
            "insurgent_formation_experience_mean",
        ] {
            assert!(
                summary.get(key).is_some(),
                "missing theory-v2 summary key {key}"
            );
        }
    }

    #[test]
    fn encoded_checkpoint_continuation_is_identical_to_uninterrupted_run() {
        let config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            ..Default::default()
        };
        let mut continuous = SimulationEngine::new(config.clone()).unwrap();
        continuous.advance_until(2.0).unwrap();

        let mut split = SimulationEngine::new(config.clone()).unwrap();
        split.advance_until(1.0).unwrap();
        let bytes = CheckpointStore::encode_particle(&split.particle).unwrap();
        let restored_particle = CheckpointStore::decode_particle(&bytes).unwrap();
        let topology = StaticTopology::synthetic(4, config.physical.town_microzones);
        let mut restored =
            SimulationEngine::from_particle(config, topology, restored_particle).unwrap();
        restored.advance_until(2.0).unwrap();
        assert_eq!(continuous.decision_hash(), restored.decision_hash());
        assert_eq!(continuous.state_hash(), restored.state_hash());
    }

    #[test]
    fn state_regeneration_scheduler_and_checkpoint_continuation_are_exact() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 30.0,
            ..Default::default()
        };
        config.state_regeneration.enabled = true;
        config.state_regeneration.interval_days = 5.0;
        config.state_regeneration.security_recruitment_rate = 2.0e-5;
        config.state_regeneration.security_training_rate = 0.08;
        config.state_regeneration.military_target_multiplier = 0.0;

        let mut continuous = SimulationEngine::new(config.clone()).unwrap();
        for post in 0..continuous.particle.security_posts.personnel.len() {
            if continuous.particle.security_posts.organization[post] as usize == super::POLICE {
                continuous.particle.security_posts.personnel[post] *= 0.5;
                continuous.particle.security_posts.presence[post] =
                    (continuous.particle.security_posts.personnel[post] / 250.0).clamp(0.0, 1.0);
            }
        }
        let starting_particle = continuous.particle.clone();
        continuous.advance_until(30.0).unwrap();
        assert!(
            continuous
                .particle
                .counters
                .event_counts
                .get("state_regeneration")
                .copied()
                .unwrap_or(0)
                > 0
        );
        assert!(
            continuous
                .particle
                .locality
                .government_cumulative_security_recruits
                .iter()
                .sum::<f64>()
                > 0.0
        );

        let topology = continuous.topology.clone();
        let mut split =
            SimulationEngine::from_particle(config.clone(), topology.clone(), starting_particle)
                .unwrap();
        split.advance_until(15.0).unwrap();
        let bytes = CheckpointStore::encode_particle(&split.particle).unwrap();
        let restored_particle = CheckpointStore::decode_particle(&bytes).unwrap();
        let mut restored =
            SimulationEngine::from_particle(config, topology, restored_particle).unwrap();
        restored.advance_until(30.0).unwrap();
        assert_eq!(continuous.decision_hash(), restored.decision_hash());
        assert_eq!(continuous.state_hash(), restored.state_hash());
    }

    #[test]
    fn every_native_process_is_reachable_from_the_typed_calendar() {
        let mut config = SimulationConfig {
            locality_count: 3,
            agent_count: 60,
            burn_in_days: 0.0,
            horizon_days: 8.0,
            ..Default::default()
        };
        config.intervals.governance = 1.0;
        config.intervals.economy = 1.0;
        config.organization_ecology.interval_days = 1.0;
        config.political_order.interval_days = 1.0;
        config.state_regeneration.enabled = true;
        config.state_regeneration.interval_days = 1.0;
        config.foreign_affairs.interval_days = 1.0;
        config.peace_process.interval_days = 1.0;
        let mut engine = SimulationEngine::new(config).unwrap();
        engine.run().unwrap();
        for kind in [
            "physical_refresh",
            "patrol",
            "information",
            "beliefs",
            "social_influence",
            "mobility",
            "recruitment",
            "contact_scan",
            "logistics",
            "command",
            "governance",
            "economy",
            "organization_ecology",
            "political_order",
            "state_regeneration",
            "foreign_affairs",
            "peace_process",
            "recording_noise",
        ] {
            assert!(
                engine.particle.counters.event_counts.contains_key(kind),
                "missing typed process {kind}"
            );
        }
    }

    #[test]
    fn default_partner_force_support_is_exact_noop() {
        let config_baseline = SimulationConfig {
            locality_count: 3,
            agent_count: 60,
            burn_in_days: 0.0,
            horizon_days: 10.0,
            ..Default::default()
        };
        let mut config_partner = config_baseline.clone();
        config_partner.partner_force_support =
            pineland_core::config::PartnerForceSupportConfig::default();

        let mut engine_baseline = SimulationEngine::new(config_baseline).unwrap();
        let mut engine_partner = SimulationEngine::new(config_partner).unwrap();

        let summary_baseline = engine_baseline.run().unwrap();
        let summary_partner = engine_partner.run().unwrap();

        assert_eq!(engine_baseline.state_hash(), engine_partner.state_hash());
        assert_eq!(
            engine_baseline.decision_hash(),
            engine_partner.decision_hash()
        );
        assert_eq!(summary_baseline, summary_partner);
    }

    #[test]
    fn partner_support_channels_can_be_isolated() {
        let mut config_air = SimulationConfig {
            locality_count: 3,
            agent_count: 60,
            burn_in_days: 0.0,
            horizon_days: 10.0,
            ..Default::default()
        };
        config_air.partner_force_support.enabled = true;
        config_air.partner_force_support.air.enabled = true;
        config_air.partner_force_support.air.intensity = 0.8;
        config_air.partner_force_support.air.firepower_bonus = 0.5;
        config_air
            .partner_force_support
            .air
            .cost_per_assisted_contact = 500.0;

        let mut engine_air = SimulationEngine::new(config_air).unwrap();
        engine_air.run().unwrap();

        assert_eq!(
            engine_air
                .particle
                .partner_support
                .logistics
                .cumulative_donor_cost,
            0.0
        );
        assert_eq!(
            engine_air
                .particle
                .partner_support
                .command
                .cumulative_donor_cost,
            0.0
        );
        assert_eq!(
            engine_air
                .particle
                .partner_support
                .force_generation
                .cumulative_donor_cost,
            0.0
        );
        assert_eq!(
            engine_air
                .particle
                .partner_support
                .logistics
                .cumulative_delivered,
            0.0
        );
        assert_eq!(
            engine_air.particle.partner_support.command.assisted_events,
            0
        );
        assert_eq!(
            engine_air
                .particle
                .partner_support
                .force_generation
                .external_incremental_graduates,
            0.0
        );
    }

    #[test]
    fn partner_support_withdrawal_immediate_diff_allowlist() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 30.0,
            ..Default::default()
        };
        config.partner_force_support.enabled = true;
        config.partner_force_support.air.enabled = true;
        config.partner_force_support.air.intensity = 0.8;
        config.partner_force_support.logistics.enabled = true;
        config.partner_force_support.logistics.daily_delivery_rate = 50.0;
        config.partner_force_support.command.enabled = true;
        config.partner_force_support.command.reliability_boost = 0.2;
        config.partner_force_support.force_generation.enabled = true;
        config
            .partner_force_support
            .force_generation
            .training_rate_boost = 0.05;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.advance_until(15.0).unwrap();

        let mut withdrawn_engine = engine.clone();
        withdrawn_engine.withdraw_external_partner_support();

        // ALLOWLIST: Only partner_support.support_withdrawn, withdrawal_time, and snapshots may change
        assert!(!engine.particle.partner_support.support_withdrawn);
        assert_eq!(engine.particle.partner_support.withdrawal_time, None);
        assert!(withdrawn_engine.particle.partner_support.support_withdrawn);
        assert_eq!(
            withdrawn_engine.particle.partner_support.withdrawal_time,
            Some(15.0)
        );
        assert_eq!(
            withdrawn_engine
                .particle
                .partner_support
                .window_snapshots
                .len(),
            1
        );

        // STRICT FORBIDDEN LIST: Every other indigenous field MUST BE EXACTLY IDENTICAL
        assert_eq!(
            engine.particle.formations,
            withdrawn_engine.particle.formations
        );
        assert_eq!(engine.particle.people, withdrawn_engine.particle.people);
        assert_eq!(
            engine.particle.organizations,
            withdrawn_engine.particle.organizations
        );
        assert_eq!(engine.particle.leaders, withdrawn_engine.particle.leaders);
        assert_eq!(
            engine.particle.social_edges,
            withdrawn_engine.particle.social_edges
        );
        assert_eq!(
            engine.particle.command_edges,
            withdrawn_engine.particle.command_edges
        );
        assert_eq!(engine.particle.manpower, withdrawn_engine.particle.manpower);
        assert_eq!(
            engine.particle.political,
            withdrawn_engine.particle.political
        );
        assert_eq!(engine.particle.foreign, withdrawn_engine.particle.foreign);
        assert_eq!(
            engine.particle.relations,
            withdrawn_engine.particle.relations
        );
        assert_eq!(
            engine.particle.logistics,
            withdrawn_engine.particle.logistics
        );
        assert_eq!(
            engine.particle.security_posts,
            withdrawn_engine.particle.security_posts
        );
        assert_eq!(
            engine.particle.footholds,
            withdrawn_engine.particle.footholds
        );
        assert_eq!(engine.particle.locality, withdrawn_engine.particle.locality);
        assert_eq!(engine.particle.zones, withdrawn_engine.particle.zones);
        assert_eq!(engine.particle.counters, withdrawn_engine.particle.counters);
        assert_eq!(engine.particle.rng, withdrawn_engine.particle.rng);
    }

    #[test]
    fn paired_counterfactual_cloning_and_branch_determinism() {
        let mut config = SimulationConfig {
            locality_count: 3,
            agent_count: 80,
            burn_in_days: 0.0,
            horizon_days: 20.0,
            ..Default::default()
        };
        config.partner_force_support.enabled = true;
        config.partner_force_support.air.enabled = true;
        config.partner_force_support.air.intensity = 0.8;
        config.partner_force_support.logistics.enabled = true;
        config.partner_force_support.logistics.daily_delivery_rate = 100.0;
        config
            .partner_force_support
            .logistics
            .cost_per_supply_delivered = 10.0;
        config.partner_force_support.command.enabled = true;
        config.partner_force_support.command.cost_per_formation_day = 50.0;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.advance_until(10.0).unwrap();

        let mut engine_on = engine.clone();
        let mut engine_off_1 = engine.clone();
        let mut engine_off_2 = engine.clone();

        engine_off_1.withdraw_external_partner_support();
        engine_off_2.withdraw_external_partner_support();

        engine_on.advance_until(20.0).unwrap();
        engine_off_1.advance_until(20.0).unwrap();
        engine_off_2.advance_until(20.0).unwrap();

        assert_eq!(engine_off_1.state_hash(), engine_off_2.state_hash());
        assert_eq!(engine_off_1.decision_hash(), engine_off_2.decision_hash());
        assert_eq!(engine_off_1.summary(), engine_off_2.summary());

        assert_ne!(engine_on.state_hash(), engine_off_1.state_hash());
        assert!(
            engine_on
                .particle
                .partner_support
                .logistics
                .cumulative_delivered
                > engine_off_1
                    .particle
                    .partner_support
                    .logistics
                    .cumulative_delivered
        );
        assert!(
            engine_on.particle.partner_support.cumulative_donor_cost()
                > engine_off_1
                    .particle
                    .partner_support
                    .cumulative_donor_cost()
        );
    }

    #[test]
    fn partner_support_accounting_identities() {
        let mut config = SimulationConfig {
            locality_count: 3,
            agent_count: 80,
            burn_in_days: 0.0,
            horizon_days: 15.0,
            ..Default::default()
        };
        config.partner_force_support.enabled = true;
        config.partner_force_support.air.enabled = true;
        config.partner_force_support.air.intensity = 0.8;
        config.partner_force_support.air.cost_per_assisted_contact = 100.0;
        config.partner_force_support.logistics.enabled = true;
        config.partner_force_support.logistics.daily_delivery_rate = 50.0;
        config
            .partner_force_support
            .logistics
            .cost_per_supply_delivered = 5.0;
        config.partner_force_support.command.enabled = true;
        config.partner_force_support.command.cost_per_formation_day = 20.0;
        config.state_regeneration.enabled = true;
        config.partner_force_support.force_generation.enabled = true;
        config
            .partner_force_support
            .force_generation
            .training_rate_boost = 0.04;
        config
            .partner_force_support
            .force_generation
            .cost_per_incremental_trainee = 25.0;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.run().unwrap();

        let ledger = &engine.particle.partner_support;
        let channel_sum = ledger.air.cumulative_donor_cost
            + ledger.logistics.cumulative_donor_cost
            + ledger.command.cumulative_donor_cost
            + ledger.force_generation.cumulative_donor_cost;
        assert!((ledger.cumulative_donor_cost() - channel_sum).abs() < 1.0e-9);

        let log_sum = ledger.logistics.cumulative_delivered
            + ledger.logistics.cumulative_rejected
            + ledger.logistics.cumulative_lost;
        assert!((ledger.logistics.cumulative_offered - log_sum).abs() < 1.0e-9);
    }

    #[test]
    fn post_withdrawal_indigenous_instrumentation_continues() {
        let mut config = SimulationConfig {
            locality_count: 3,
            agent_count: 80,
            burn_in_days: 0.0,
            horizon_days: 25.0,
            ..Default::default()
        };
        config.state_regeneration.enabled = true;
        config.partner_force_support.enabled = true;
        config.partner_force_support.force_generation.enabled = true;
        config
            .partner_force_support
            .force_generation
            .training_rate_boost = 0.05;
        config
            .partner_force_support
            .force_generation
            .cost_per_incremental_trainee = 50.0;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.advance_until(10.0).unwrap();

        let l_at_t = engine.particle.partner_support.clone();
        engine.withdraw_external_partner_support();

        engine.advance_until(25.0).unwrap();
        let l_post = &engine.particle.partner_support;

        // Indigenous instrumentation continues post-withdrawal
        assert!(
            l_post.force_generation.indigenous_recruits
                >= l_at_t.force_generation.indigenous_recruits
        );
        assert!(
            l_post.force_generation.indigenous_graduates
                >= l_at_t.force_generation.indigenous_graduates
        );

        // External contributions and donor costs stop permanently
        assert_eq!(
            l_post.force_generation.external_incremental_graduates,
            l_at_t.force_generation.external_incremental_graduates
        );
        assert_eq!(
            l_post.cumulative_donor_cost(),
            l_at_t.cumulative_donor_cost()
        );
    }

    #[test]
    fn indigenous_logistics_excludes_insurgents_and_conserves_external() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 20.0,
            ..Default::default()
        };
        config.partner_force_support.enabled = true;
        config.partner_force_support.logistics.enabled = true;
        config.partner_force_support.logistics.daily_delivery_rate = 60.0;
        config
            .partner_force_support
            .logistics
            .cost_per_supply_delivered = 5.0;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.run().unwrap();

        let l = &engine.particle.partner_support.logistics;
        let global = &engine.particle.logistics;

        // Indigenous logistics strictly subsets global logistics (excludes non-government/insurgent)
        assert!(l.indigenous_cumulative_produced <= global.cumulative_produced + 1.0e-9);
        assert!(l.indigenous_cumulative_delivered <= global.cumulative_delivered + 1.0e-9);
        assert!(l.indigenous_cumulative_consumed <= global.cumulative_consumed + 1.0e-9);

        // External conservation identity
        let external_delivered_sum =
            l.cumulative_delivered + l.cumulative_rejected + l.cumulative_lost;
        assert!((l.cumulative_offered - external_delivered_sum).abs() < 1.0e-9);
    }

    #[test]
    fn degenerate_baseline_yields_zero_retention() {
        let config = SimulationConfig {
            locality_count: 3,
            agent_count: 80,
            ..Default::default()
        };
        let engine = SimulationEngine::new(config).unwrap();

        // Baseline with 0 operational formations
        let baseline_zero_formations = CapabilityAssayBaseline {
            military_personnel: 100.0,
            operational_formations: 0,
            covered_localities: 2,
            operational_readiness: 0.8,
        };
        let assay = engine.capability_assay(&baseline_zero_formations);
        assert_eq!(assay.operational_formation_survival, 0.0);
        assert_eq!(assay.composite_capability, 0.0);
        assert_eq!(assay.composite_capability_v1, 0.0);

        // Baseline with 0 military personnel
        let baseline_zero_personnel = CapabilityAssayBaseline {
            military_personnel: 0.0,
            operational_formations: 2,
            covered_localities: 2,
            operational_readiness: 0.8,
        };
        let assay_p = engine.capability_assay(&baseline_zero_personnel);
        assert_eq!(assay_p.military_personnel_retention, 0.0);
        assert_eq!(assay_p.composite_capability, 0.0);
        assert_eq!(assay_p.composite_capability_v1, 0.0);
    }

    #[test]
    fn negative_control_no_support_cells_are_identical_across_branches() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 35.0,
            ..Default::default()
        };
        // All assistance channels disabled (negative control cell)
        config.partner_force_support.enabled = true;
        config.partner_force_support.air.enabled = false;
        config.partner_force_support.logistics.enabled = false;
        config.partner_force_support.command.enabled = false;
        config.partner_force_support.force_generation.enabled = false;

        let mut engine = SimulationEngine::new(config).unwrap();
        engine.advance_until(10.0).unwrap();

        let baseline = engine.capability_assay_baseline();
        let mut engine_on = engine.clone();
        let mut engine_off = engine.clone();
        let hash_at_t = engine_off.state_hash();
        engine_off.withdraw_external_partner_support();
        assert_eq!(engine_off.state_hash(), hash_at_t);
        assert!(!engine_off.particle.partner_support.support_withdrawn);
        assert_eq!(engine_off.particle.partner_support.withdrawal_time, None);

        // Advance to 7-day horizon (17d) and 20-day horizon (30d)
        for target in [17.0, 30.0] {
            engine_on.advance_until(target).unwrap();
            engine_off.advance_until(target).unwrap();

            // Indigenous arrays must remain bit-for-bit identical
            assert_eq!(
                engine_on.particle.formations,
                engine_off.particle.formations
            );
            assert_eq!(engine_on.particle.people, engine_off.particle.people);
            assert_eq!(engine_on.particle.logistics, engine_off.particle.logistics);
            assert_eq!(engine_on.particle.locality, engine_off.particle.locality);
            assert_eq!(engine_on.particle.zones, engine_off.particle.zones);

            let assay_on = engine_on.capability_assay(&baseline);
            let assay_off = engine_off.capability_assay(&baseline);
            assert_eq!(assay_on, assay_off);
        }
    }

    #[test]
    fn hostility_relationships_verified() {
        let config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            ..Default::default()
        };
        let engine = SimulationEngine::new(config).unwrap();
        let particle = &engine.particle;
        assert!(crate::combat::organizations_hostile(
            particle,
            crate::MILITARY,
            crate::INSURGENT
        ));
        assert!(crate::combat::organizations_hostile(
            particle,
            crate::INSURGENT,
            crate::MILITARY
        ));
        assert!(crate::combat::organizations_hostile(
            particle,
            crate::POLICE,
            crate::INSURGENT
        ));
        assert!(crate::combat::organizations_hostile(
            particle,
            crate::INSURGENT,
            crate::POLICE
        ));
        assert!(!crate::combat::organizations_hostile(
            particle,
            crate::MILITARY,
            crate::POLICE
        ));
        assert!(!crate::combat::organizations_hostile(
            particle,
            crate::MILITARY,
            crate::GOVERNMENT
        ));
        assert!(!crate::combat::organizations_hostile(
            particle,
            crate::INSURGENT,
            crate::INSURGENT
        ));
    }

    #[test]
    fn end_to_end_combat_liveness_test() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 10.0,
            ..Default::default()
        };
        config.partner_force_support.enabled = true;
        config.partner_force_support.air.enabled = true;
        config.partner_force_support.air.intensity = 0.5;
        config.partner_force_support.air.firepower_bonus = 0.4;
        config.partner_force_support.air.cost_per_assisted_contact = 500.0;

        let mut engine = SimulationEngine::new(config).unwrap();

        // Identify one military formation and one insurgent formation
        let mil_opt = (0..engine.particle.formations.personnel.len())
            .find(|&f| engine.particle.formations.organization[f] as usize == crate::MILITARY);
        let ins_opt = (0..engine.particle.formations.personnel.len())
            .find(|&f| engine.particle.formations.organization[f] as usize == crate::INSURGENT);

        assert!(mil_opt.is_some(), "military formation must exist");
        assert!(ins_opt.is_some(), "insurgent formation must exist");
        let mil = mil_opt.unwrap();
        let ins = ins_opt.unwrap();

        // Place both formations in the same locality and primary microzone
        let target_loc = 0;
        let target_zone = engine.topology.primary_zone[target_loc];
        engine.particle.formations.locality[mil] = target_loc as u32;
        engine.particle.formations.locality[ins] = target_loc as u32;
        engine.particle.formations.microzone[mil] = target_zone;
        engine.particle.formations.microzone[ins] = target_zone;
        engine.particle.formations.moving[mil] = 0;
        engine.particle.formations.moving[ins] = 0;
        engine.particle.formations.outside_pineland[mil] = 0;
        engine.particle.formations.outside_pineland[ins] = 0;
        engine.particle.formations.operational_status[mil] = 1;
        engine.particle.formations.operational_status[ins] = 1;

        let initial_mil_pers = engine.particle.formations.personnel[mil];
        let initial_ins_pers = engine.particle.formations.personnel[ins];
        let initial_contacts = engine.particle.counters.contacts;

        // Resolve an organized engagement between them
        let mut rng = pineland_core::rng::PyRandomCompat::from_seed(42);
        crate::combat::resolve_organized_engagement(
            &mut engine.particle,
            &engine.topology,
            &engine.config,
            &mut rng,
            1.0,
            ins,
            mil,
            crate::INSURGENT,
            true,
        );

        // Assert contacts incremented
        assert_eq!(engine.particle.counters.contacts, initial_contacts + 1);
        // Assert personnel losses occurred
        assert!(engine.particle.formations.personnel[mil] < initial_mil_pers);
        assert!(engine.particle.formations.personnel[ins] < initial_ins_pers);
        assert!(engine.particle.formations.cumulative_losses[mil] > 0.0);
        assert!(engine.particle.formations.cumulative_losses[ins] > 0.0);

        // Assert partner air support was invoked for the military formation
        assert_eq!(engine.particle.partner_support.air.assisted_contacts, 1);
        assert!(
            engine
                .particle
                .partner_support
                .air
                .cumulative_firepower_bonus
                > 0.0
        );
        assert!(engine.particle.partner_support.air.cumulative_donor_cost > 0.0);
    }

    #[test]
    fn spatial_encounter_liveness_test() {
        let mut config = SimulationConfig {
            locality_count: 4,
            agent_count: 100,
            burn_in_days: 0.0,
            horizon_days: 60.0,
            ..Default::default()
        };
        config.logistics.reallocation_rate = 0.5;
        config.include_insurgency = true;

        let mut engine = SimulationEngine::new(config).unwrap();

        let mil = (0..engine.particle.formations.personnel.len())
            .find(|&f| engine.particle.formations.organization[f] as usize == crate::MILITARY)
            .expect("military formation must exist");
        let ins = (0..engine.particle.formations.personnel.len())
            .find(|&f| engine.particle.formations.organization[f] as usize == crate::INSURGENT)
            .expect("insurgent formation must exist");

        // Start them in separated localities with ample movement logistics
        engine.particle.formations.locality[mil] = 0;
        engine.particle.formations.microzone[mil] = engine.topology.primary_zone[0];
        engine.particle.formations.supply_capacity[mil] = 1000.0;
        engine.particle.formations.supply_stock[mil] = 1000.0;

        engine.particle.formations.locality[ins] = 1;
        engine.particle.formations.microzone[ins] = engine.topology.primary_zone[1];
        engine.particle.formations.home_locality[ins] = 1;
        engine.particle.formations.supply_capacity[ins] = 1000.0;
        engine.particle.formations.supply_stock[ins] = 1000.0;

        engine.advance_until(45.0).unwrap();

        let final_mil_loc = engine.particle.formations.locality[mil];
        let final_ins_loc = engine.particle.formations.locality[ins];
        let moved = final_mil_loc != 0 || final_ins_loc != 1;
        assert!(
            moved,
            "operational reallocation must move forces from static garrison"
        );
    }
}
