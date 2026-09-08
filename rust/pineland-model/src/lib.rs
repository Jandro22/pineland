//! Autonomous Pineland Native simulation engine.
//!
//! The model owns a complete trajectory. Callers provide a configuration and
//! receive a completed boundary/result; no Python object or per-event callback
//! is required.

pub mod actions;
pub mod beliefs;
pub mod combat;
pub mod economy;
pub mod foreign;
pub mod governance;
pub mod information;
pub mod logistics;
pub mod movement;
pub mod organizations;
pub mod patrol;
pub mod peace;
pub mod physical;
pub mod political;
pub mod recording;
pub mod recruitment;
pub mod social;

use pineland_core::config::{ConfigError, SimulationConfig};
use pineland_core::json::JsonValue;
use pineland_core::rng::{python_sum, seed_from_namespace, PyRandomCompat, RngStreams};
use pineland_core::scheduler::{EventPayload, ScheduledEvent, SchedulerError};
use pineland_core::sha256;
use pineland_core::state::{
    clamp01, BeliefKey, EventRecord, LogisticsState, ParticleState, PersonState, SecurityPostState,
    StateError, CONTROL_DIMENSIONS,
};
use pineland_core::topology::StaticTopology;
use std::fmt;

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
}

impl SimulationEngine {
    pub fn new(config: SimulationConfig) -> Result<Self, ModelError> {
        config.validate()?;
        let initialization_seed = config.initialization_seed.unwrap_or(config.seed);
        let generated = StaticTopology::pineland(&config, initialization_seed);
        let topology = generated.topology;
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
        let mut engine = Self {
            config,
            topology,
            particle,
            model_hash: sha256::digest_hex(b"pineland-native-v1-frozen-core"),
            started_at: 0.0,
            last_boundary: 0.0,
        };
        engine.initialize_world(
            government_formations,
            insurgent_formations,
            initialization_seed,
            generated.world_rng,
            generated.physical_rng,
        )?;
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
        Ok(Self {
            config,
            topology,
            particle,
            model_hash: sha256::digest_hex(b"pineland-native-v1-frozen-core"),
            started_at: 0.0,
            last_boundary: 0.0,
        })
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
        let community_count = assign_household_communities(
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
        let _ = community_count;
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
        for formation in 0..self.particle.formations.personnel.len() {
            if self.particle.formations.active[formation] == 0 {
                continue;
            }
            let organization = self.particle.formations.organization[formation] as usize;
            let org_quality = self.particle.organizations.institutional_quality[organization];
            self.particle.formations.command[formation] = clamp01(
                0.35 + 0.35 * org_quality + 0.3 * self.particle.formations.command[formation],
            );
            let _ = logistics_rng.uniform(0.0, 1.5);
        }
        self.particle
            .rng
            .streams
            .insert("logistics-world-generation".to_string(), logistics_rng);

        initialize_footholds(&mut self.particle, &self.topology, &self.config);

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
        // control construction to seed every observer/zone belief.  The
        // current dense state does not yet expose the full zone-belief table,
        // but the draws still belong to the certified continuation boundary.
        for _observer in 0..self.particle.organizations.kind.len() {
            for _zone in 0..self.topology.microzone_count() {
                let _ = physical_rng.uniform(
                    -self.config.physical.zone_observation_noise,
                    self.config.physical.zone_observation_noise,
                );
            }
        }
        self.particle
            .rng
            .streams
            .insert("physical-world-generation".to_string(), physical_rng);

        // Leader construction is a separate initialization stream. There is
        // no native leader SoA yet, but consuming the exact twelve draws per
        // insurgent organization keeps the certified stream boundary explicit.
        let mut ecology_rng = PyRandomCompat::from_seed(seed_from_namespace(
            initialization_seed,
            &self.config.random_stream_namespace,
            "organization-ecology-generation",
        ));
        if self.config.include_insurgency {
            for _ in 0..6 {
                let _ = ecology_rng.uniform(0.3, 0.8);
            }
            for _ in 0..6 {
                let _ = ecology_rng.normalvariate(0.0, 0.04);
            }
        }
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
            f.cohesion[index] = 0.70;
            f.readiness[index] = 0.75;
            f.sustainment[index] = 0.65;
            f.information[index] = 0.50;
            f.mobility[index] = 0.70;
            f.command[index] = 0.55;
            f.embeddedness[index] = 0.75;
        } else {
            f.quality[index] = 0.72;
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
        while self
            .particle
            .scheduler
            .peek()
            .is_some_and(|event| event.time <= until)
        {
            let event = self.particle.scheduler.pop_next().expect("peeked event");
            self.particle.time = event.time;
            self.particle.counters.record(event.payload.kind());
            let sequence = event.sequence;
            self.process_event(&event)?;
            self.particle.event_log.push(EventRecord {
                time: event.time,
                sequence,
                kind: event.payload.kind().to_string(),
                locality: event_locality(&event),
                value: 1.0,
            });
            self.reschedule_recurring(&event)?;
        }
        self.particle.time = until;
        self.last_boundary = until;
        self.particle.validate()?;
        Ok(())
    }

    fn process_event(&mut self, event: &ScheduledEvent) -> Result<(), ModelError> {
        match &event.payload {
            EventPayload::Patrol { .. } => {
                let mut rng = self.take_rng("patrol");
                patrol::advance(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("patrol", rng);
            }
            EventPayload::PhysicalRefresh => {
                physical::refresh(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::Information => {
                let mut rng = self.take_rng("information");
                information::collect_and_fuse(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("information", rng);
            }
            EventPayload::Beliefs => beliefs::decay_and_propagate(
                &mut self.particle,
                &self.topology,
                &self.config,
                event.time,
            ),
            EventPayload::SocialInfluence => {
                let mut rng = self.take_rng("social-influence");
                social::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("social-influence", rng);
            }
            EventPayload::Mobility => {
                let mut rng = self.take_rng("mobility");
                movement::civilian_mobility(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("mobility", rng);
            }
            EventPayload::Recruitment => {
                let mut rng = self.take_rng("recruitment");
                recruitment::recruit(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("recruitment", rng);
            }
            EventPayload::OrganizedAction { .. } => {
                let mut rng = self.take_rng("organized-action");
                actions::opportunities(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("organized-action", rng);
            }
            EventPayload::ContactScan => {
                let mut rng = self.take_rng("contact");
                combat::schedule_contacts(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                )?;
                self.put_rng("contact", rng);
            }
            EventPayload::Contact {
                first,
                second,
                locality,
                microzone,
            } => {
                let mut rng = self.take_rng("contact");
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
                self.put_rng("contact", rng);
            }
            EventPayload::ForceMovement => {
                movement::command(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::Logistics => {
                let mut rng = self.take_rng("logistics");
                logistics::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("logistics", rng);
            }
            EventPayload::Command => {
                movement::command(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::Governance => {
                governance::update(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::Economy => {
                economy::update(&mut self.particle, &self.topology, &self.config, event.time)
            }
            EventPayload::OrganizationEcology => {
                let mut rng = self.take_rng("organization-ecology-events");
                organizations::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("organization-ecology-events", rng);
            }
            EventPayload::PoliticalOrder => {
                let mut rng = self.take_rng("political");
                political::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("political", rng);
            }
            EventPayload::ForeignAffairs => {
                let mut rng = self.take_rng("foreign");
                foreign::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("foreign", rng);
            }
            EventPayload::PeaceProcess => {
                let mut rng = self.take_rng("peace");
                peace::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("peace", rng);
            }
            EventPayload::RecordingNoise => {
                let mut rng = self.take_rng("recording");
                recording::update(
                    &mut self.particle,
                    &self.topology,
                    &self.config,
                    &mut rng,
                    event.time,
                );
                self.put_rng("recording", rng);
            }
            EventPayload::Checkpoint => {
                self.particle.counters.checkpoints =
                    self.particle.counters.checkpoints.saturating_add(1);
            }
            EventPayload::Custom { .. } => {}
        }
        Ok(())
    }

    fn reschedule_recurring(&mut self, event: &ScheduledEvent) -> Result<(), ModelError> {
        let interval = match event.payload {
            EventPayload::Patrol { .. } => self.config.intervals.patrol,
            EventPayload::Information => self.config.intervals.information,
            EventPayload::Beliefs => self.config.intervals.beliefs,
            EventPayload::PhysicalRefresh => self.config.intervals.physical_refresh,
            EventPayload::SocialInfluence => self.config.intervals.social_influence,
            EventPayload::Mobility => self.config.intervals.mobility,
            EventPayload::Recruitment => self.config.intervals.recruitment,
            EventPayload::OrganizedAction { .. } => self.config.intervals.contact,
            EventPayload::ContactScan => self.config.intervals.contact,
            EventPayload::Logistics => self.config.intervals.logistics,
            EventPayload::ForceMovement => self.config.intervals.force_movement,
            EventPayload::Command => self.config.intervals.command,
            EventPayload::Governance => self.config.intervals.governance,
            EventPayload::Economy => self.config.intervals.economy,
            EventPayload::OrganizationEcology => self.config.organization_ecology.interval_days,
            EventPayload::PoliticalOrder => self.config.political_order.interval_days,
            EventPayload::ForeignAffairs => self.config.foreign_affairs.interval_days,
            EventPayload::PeaceProcess => self.config.peace_process.interval_days,
            EventPayload::RecordingNoise => self.config.intervals.information,
            EventPayload::Checkpoint => self.config.intervals.checkpoint,
            _ => return Ok(()),
        };
        self.schedule(event.time + interval, event.priority, event.payload.clone())?;
        Ok(())
    }

    fn take_rng(&mut self, name: &str) -> PyRandomCompat {
        // Use the stream registry's namespace-derived lazy path for every
        // process.  Falling back directly to config.seed would give
        // resampled siblings identical future draws for a stream that had not
        // yet been touched before the branch.
        self.particle.rng.get_mut(name).clone()
    }
    fn put_rng(&mut self, name: &str, rng: PyRandomCompat) {
        self.particle.rng.streams.insert(name.to_string(), rng);
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
        o.insert("engine", JsonValue::string("pineland-native-v1"));
        o.insert("model_hash", JsonValue::string(&self.model_hash));
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
        o
    }

    pub fn state_hash(&self) -> String {
        self.particle.state_hash()
    }
    pub fn decision_hash(&self) -> String {
        self.particle.decision_hash()
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

fn assign_household_communities(
    people: &mut PersonState,
    locality_count: usize,
    minimum: f64,
    target: f64,
    maximum: f64,
    rng: &mut PyRandomCompat,
) -> Result<usize, ModelError> {
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
            for person in 0..people.locality.len() {
                if group.contains(&(people.household[person] as usize)) {
                    people.community[person] = community;
                }
            }
            // SocialCommunity construction draws cohesion immediately after
            // each group, before the next locality is shuffled.  Keeping this
            // draw at the same boundary is required for subsequent locality
            // partitions to see the identical Python RNG stream.
            let _ = rng.uniform(0.45, 0.85);
            community = community.saturating_add(1);
        }
    }
    Ok(community as usize)
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
    use super::SimulationEngine;
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
}
