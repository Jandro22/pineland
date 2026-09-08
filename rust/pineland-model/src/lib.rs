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
use pineland_core::rng::{PyRandomCompat, RngStreams};
use pineland_core::scheduler::{EventPayload, ScheduledEvent, SchedulerError};
use pineland_core::sha256;
use pineland_core::state::{
    clamp01, BeliefKey, EventRecord, ParticleState, StateError, CONTROL_DIMENSIONS,
};
use pineland_core::topology::StaticTopology;
use std::fmt;

pub const GOVERNMENT: usize = 0;
pub const MILITARY: usize = 1;
pub const POLICE: usize = 2;
pub const INSURGENT: usize = 3;
pub const FOREIGN: usize = 4;

const PRIORITY_PHYSICAL: u16 = 10;
const PRIORITY_PATROL: u16 = 20;
const PRIORITY_INFORMATION: u16 = 30;
const PRIORITY_BELIEFS: u16 = 40;
const PRIORITY_SOCIAL: u16 = 50;
const PRIORITY_MOBILITY: u16 = 60;
const PRIORITY_RECRUITMENT: u16 = 70;
const PRIORITY_ACTION: u16 = 80;
const PRIORITY_CONTACT_SCAN: u16 = 90;
const PRIORITY_LOGISTICS: u16 = 110;
const PRIORITY_COMMAND: u16 = 120;
const PRIORITY_GOVERNANCE: u16 = 130;
const PRIORITY_ECONOMY: u16 = 140;
const PRIORITY_ORGANIZATION: u16 = 150;
const PRIORITY_POLITICAL: u16 = 160;
const PRIORITY_FOREIGN: u16 = 170;
const PRIORITY_PEACE: u16 = 180;
const PRIORITY_RECORDING: u16 = 190;
const PRIORITY_CHECKPOINT: u16 = 200;

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
        let topology = StaticTopology::synthetic(
            config.locality_count,
            config.physical.town_microzones.clamp(1, 8),
        );
        let organization_count = 5;
        let government_formations = config
            .force_structure
            .maximum_initial_formations_per_side
            .min(config.locality_count.max(1))
            .max(1);
        let insurgent_formations = if config.include_insurgency {
            (government_formations / 2).max(1)
        } else {
            0
        };
        let formation_count = government_formations + insurgent_formations;
        let foothold_count = organization_count * topology.locality_count();
        let mut particle = ParticleState::new_with_people(
            locality_count(&topology),
            topology.microzone_count(),
            topology.locality_count(),
            organization_count,
            formation_count,
            foothold_count,
            RngStreams::new(config.seed, config.random_stream_namespace.clone()),
        );
        particle.beliefs = make_belief_state(&topology, &config);
        let initialization_seed = config.initialization_seed.unwrap_or(config.seed);
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
    ) -> Result<(), ModelError> {
        let n = self.topology.locality_count();
        // Initialization has its own seed contract.  Process streams remain
        // rooted at config.seed, while generated geography/population/forces
        // use initialization_seed exactly like the Python reference.
        let initialization_streams = RngStreams::new(
            initialization_seed,
            self.config.random_stream_namespace.clone(),
        );
        let mut world_rng = initialization_streams
            .get("world-generation")
            .cloned()
            .unwrap_or_else(|| PyRandomCompat::from_seed(initialization_seed));
        let total_population = 6_900_000.0;
        let mut weights = Vec::with_capacity(n);
        for _ in 0..n {
            weights.push(world_rng.lognormal(0.0, 0.55));
        }
        let total_weight: f64 = weights.iter().sum();
        for (locality, weight) in weights.iter().enumerate() {
            let population = total_population * *weight / total_weight.max(f64::MIN_POSITIVE);
            let connectivity = clamp01(0.35 + 0.35 * ((locality * 13 % 17) as f64 / 16.0));
            let urban = clamp01(0.2 + 0.75 * ((locality * 7 % 19) as f64 / 18.0));
            let offset = locality * CONTROL_DIMENSIONS;
            self.particle.locality.population[locality] = population;
            self.particle.locality.economic_output[locality] =
                population * (0.7 + 0.6 * world_rng.random());
            self.particle.locality.infrastructure[locality] = connectivity;
            self.particle.locality.administrative_capacity[locality] =
                clamp01(0.25 + 0.55 * connectivity + world_rng.uniform(-0.08, 0.08));
            self.particle.locality.terrain_friction[locality] = 0.8 + 1.7 * (1.0 - connectivity);
            self.particle.locality.observability[locality] =
                clamp01(0.35 + urban * 0.5 + world_rng.uniform(-0.08, 0.08));
            let base = [
                0.92,
                0.62,
                self.particle.locality.administrative_capacity[locality],
                0.58,
                0.5,
                0.5,
                0.7,
            ];
            self.particle.locality.government_control[offset..offset + CONTROL_DIMENSIONS]
                .copy_from_slice(&base);
            self.particle.locality.insurgent_control[offset..offset + CONTROL_DIMENSIONS].fill(0.0);
            self.particle.locality.government_governance[locality] =
                self.particle.locality.administrative_capacity[locality];
            self.particle.locality.insurgent_governance[locality] = 0.0;
            self.particle.people.locality[locality] = locality as u32;
            self.particle.people.represented_population[locality] = population;
            self.particle.people.home[locality] = locality as u32;
            self.particle.people.residence[locality] = locality as u32;
            self.particle.people.grievance[locality] = clamp01(
                0.28 + 0.45 * (1.0 - self.particle.locality.government_control[offset + 6]),
            );
            self.particle.people.fear[locality] =
                clamp01(0.12 + 0.2 * self.particle.locality.violence[locality]);
            self.particle.people.efficacy[locality] =
                clamp01(0.35 + 0.4 * self.particle.locality.government_control[offset]);
            self.particle.people.trust[locality] =
                clamp01(0.3 + 0.45 * self.particle.locality.government_control[offset + 3]);
            self.particle.people.rebel_sympathy[locality] = if self.config.include_insurgency {
                self.config.initial_insurgent_share
            } else {
                0.0
            };
            let range = self.topology.zones_for_locality(locality.into());
            let share = 1.0 / range.len() as f64;
            for zone in range {
                self.particle.zones.population_share[zone] = share;
                self.particle.zones.infrastructure[zone] =
                    self.particle.locality.infrastructure[locality];
                self.particle.zones.terrain_friction[zone] =
                    self.particle.locality.terrain_friction[locality];
                self.particle.zones.observability[zone] =
                    self.particle.locality.observability[locality];
                self.particle.zones.government_control[zone] =
                    self.particle.locality.government_control[offset + 1];
            }
        }
        self.particle
            .rng
            .streams
            .insert("world-generation".to_string(), world_rng);

        self.particle.organizations.kind = vec![0, 1, 2, 3, 4];
        self.particle.organizations.active.fill(1);
        if !self.config.include_insurgency {
            self.particle.organizations.active[INSURGENT] = 0;
        }
        self.particle.organizations.capital = vec![
            100.0,
            75.0,
            60.0,
            if self.config.include_insurgency {
                90.0
            } else {
                0.0
            },
            0.0,
        ];
        self.particle.organizations.cohesion = vec![0.85, 0.78, 0.72, 0.62, 0.8];
        self.particle.organizations.discipline = vec![0.86, 0.82, 0.72, 0.58, 0.8];
        self.particle.organizations.accountability = vec![0.68, 0.6, 0.52, 0.4, 0.7];
        self.particle.organizations.local_knowledge = vec![0.65, 0.6, 0.58, 0.35, 0.2];
        self.particle.organizations.persistence = vec![0.9, 0.85, 0.72, 0.58, 0.8];
        self.particle.organizations.mobility = vec![0.45, 0.65, 0.6, 0.75, 0.5];
        self.particle.organizations.institutional_quality = vec![0.7, 0.5, 0.42, 0.2, 0.55];
        let total_population = total_or_population(&self.particle);
        self.particle.organizations.member_population[0] = total_population;
        self.particle.organizations.member_population[1] = total_population * 0.003;
        self.particle.organizations.member_population[2] = total_population * 0.002;
        self.particle.organizations.member_population[3] = if self.config.include_insurgency {
            total_population * self.config.initial_insurgent_share
        } else {
            0.0
        };

        let mut force_rng = initialization_streams
            .get("force-generation")
            .cloned()
            .unwrap_or_else(|| PyRandomCompat::from_seed(initialization_seed));
        let total_gov = self
            .config
            .force_structure
            .government_target_personnel
            .max(1.0);
        for formation in 0..government_formations {
            self.initialize_formation(
                formation,
                MILITARY,
                formation % n,
                total_gov / government_formations as f64,
                &mut force_rng,
            );
        }
        if self.config.include_insurgency {
            let total_ins = self
                .config
                .force_structure
                .insurgent_target_personnel
                .max(1.0);
            for index in 0..insurgent_formations {
                self.initialize_formation(
                    government_formations + index,
                    INSURGENT,
                    (index * 3 + 1) % n,
                    total_ins / insurgent_formations as f64,
                    &mut force_rng,
                );
            }
        } else {
            for formation in government_formations..self.particle.formations.organization.len() {
                self.particle.formations.active[formation] = 0;
            }
        }
        self.particle
            .rng
            .streams
            .insert("force-generation".to_string(), force_rng);
        for organization in 0..self.particle.logistics.source_stock.len() {
            let mut personnel = 0.0;
            for formation in 0..self.particle.formations.organization.len() {
                if self.particle.formations.active[formation] != 0
                    && self.particle.formations.organization[formation] as usize == organization
                {
                    personnel += self.particle.formations.personnel[formation];
                }
            }
            self.particle.logistics.source_capacity[organization] =
                personnel * self.config.logistics.source_capacity_per_resident;
            self.particle.logistics.source_stock[organization] = personnel
                * self.config.logistics.formation_supply_days
                * self.config.logistics.presence_consumption_per_person_day
                * self.config.logistics.initial_supply_fraction;
            self.particle.logistics.source_production[organization] =
                self.particle.logistics.source_capacity[organization]
                    * self.config.logistics.source_daily_production_fraction;
        }
        for organization in 0..5 {
            for locality in 0..n {
                let index = organization * n + locality;
                if organization == INSURGENT && !self.config.include_insurgency {
                    self.particle.footholds.active[index] = 0;
                }
                self.particle.footholds.organization[index] = organization as u32;
                self.particle.footholds.locality[index] = locality as u32;
                self.particle.footholds.access[index] =
                    if organization == INSURGENT { 0.4 } else { 0.8 };
                self.particle.footholds.infrastructure[index] =
                    self.particle.locality.infrastructure[locality];
                self.particle.footholds.target_knowledge[index] =
                    if organization == INSURGENT { 0.25 } else { 0.5 };
                if organization == INSURGENT && self.config.include_insurgency {
                    let signal = self.particle.locality.population[locality]
                        * self.config.initial_insurgent_share
                        / n as f64;
                    self.particle.footholds.strength[index] = signal;
                    self.particle.footholds.membership[index] = clamp01(signal / 1000.0);
                    self.particle.footholds.embeddedness[index] = 0.12;
                    self.particle.footholds.sustainment[index] = 0.35;
                }
            }
        }
        for locality in 0..n {
            self.particle.security_posts.organization[locality] = POLICE as u32;
            self.particle.security_posts.locality[locality] = locality as u32;
            self.particle.security_posts.microzone[locality] = self.topology.primary_zone[locality];
            self.particle.security_posts.presence[locality] = 0.65;
            self.particle.security_posts.detection_rate[locality] =
                self.config.information.fixed_post_report_rate;
            self.particle.security_posts.reliability[locality] =
                self.config.information.prior_confidence;
            self.particle.security_posts.staffed[locality] = 1;
        }
        Ok(())
    }

    fn initialize_formation(
        &mut self,
        index: usize,
        organization: usize,
        locality: usize,
        personnel: f64,
        rng: &mut PyRandomCompat,
    ) {
        let zone = self.topology.primary_zone[locality] as usize;
        let f = &mut self.particle.formations;
        f.organization[index] = organization as u32;
        f.locality[index] = locality as u32;
        f.microzone[index] = zone as u32;
        f.home_locality[index] = locality as u32;
        f.personnel[index] = personnel;
        f.quality[index] = clamp01(0.55 + rng.uniform(-0.12, 0.12));
        f.cohesion[index] = clamp01(0.65 + rng.uniform(-0.1, 0.1));
        f.readiness[index] = clamp01(0.85 + rng.uniform(-0.08, 0.08));
        f.sustainment[index] = 0.8;
        f.information[index] = 0.5;
        f.mobility[index] = clamp01(0.55 + rng.uniform(-0.1, 0.1));
        f.command[index] = clamp01(0.75 + rng.uniform(-0.08, 0.08));
        f.embeddedness[index] = if organization == INSURGENT { 0.25 } else { 0.1 };
        f.supply_capacity[index] = personnel
            * self.config.logistics.formation_supply_days
            * self.config.logistics.presence_consumption_per_person_day;
        f.supply_stock[index] =
            f.supply_capacity[index] * self.config.logistics.initial_supply_fraction;
        f.active[index] = 1;
        f.operational_status[index] = 1;
        self.particle.patrols.formation[index] = index as u32;
        self.particle.patrols.route_position[index] = zone as u32;
        self.particle.patrols.route_target[index] = zone as u32;
    }

    fn schedule_initial_events(&mut self) -> Result<(), ModelError> {
        let (
            contact,
            command,
            movement,
            logistics_interval,
            information,
            patrol,
            physical,
            beliefs,
            social,
            mobility,
            recruitment,
            governance,
            economy,
            checkpoint,
        ) = {
            let i = &self.config.intervals;
            (
                i.contact,
                i.command,
                i.force_movement,
                i.logistics,
                i.information,
                i.patrol,
                i.physical_refresh,
                i.beliefs,
                i.social_influence,
                i.mobility,
                i.recruitment,
                i.governance,
                i.economy,
                i.checkpoint,
            )
        };
        self.schedule(0.0, PRIORITY_PHYSICAL, EventPayload::PhysicalRefresh)?;
        self.schedule(
            patrol,
            PRIORITY_PATROL,
            EventPayload::Patrol {
                patrol: 0u32.into(),
            },
        )?;
        self.schedule(information, PRIORITY_INFORMATION, EventPayload::Information)?;
        self.schedule(beliefs, PRIORITY_BELIEFS, EventPayload::Beliefs)?;
        self.schedule(social, PRIORITY_SOCIAL, EventPayload::SocialInfluence)?;
        self.schedule(mobility, PRIORITY_MOBILITY, EventPayload::Mobility)?;
        self.schedule(recruitment, PRIORITY_RECRUITMENT, EventPayload::Recruitment)?;
        self.schedule(contact, PRIORITY_CONTACT_SCAN, EventPayload::ContactScan)?;
        self.schedule(
            logistics_interval,
            PRIORITY_LOGISTICS,
            EventPayload::Logistics,
        )?;
        self.schedule(command, PRIORITY_COMMAND, EventPayload::Command)?;
        self.schedule(governance, PRIORITY_GOVERNANCE, EventPayload::Governance)?;
        self.schedule(economy, PRIORITY_ECONOMY, EventPayload::Economy)?;
        self.schedule(
            physical.max(movement),
            PRIORITY_PHYSICAL,
            EventPayload::ForceMovement,
        )?;
        self.schedule(
            self.config.organization_ecology.interval_days,
            PRIORITY_ORGANIZATION,
            EventPayload::OrganizationEcology,
        )?;
        self.schedule(
            self.config.political_order.interval_days,
            PRIORITY_POLITICAL,
            EventPayload::PoliticalOrder,
        )?;
        self.schedule(
            self.config.foreign_affairs.interval_days,
            PRIORITY_FOREIGN,
            EventPayload::ForeignAffairs,
        )?;
        self.schedule(
            self.config.peace_process.interval_days,
            PRIORITY_PEACE,
            EventPayload::PeaceProcess,
        )?;
        self.schedule(checkpoint, PRIORITY_CHECKPOINT, EventPayload::Checkpoint)?;
        self.schedule(
            information,
            PRIORITY_RECORDING,
            EventPayload::RecordingNoise,
        )?;
        self.schedule(
            contact,
            PRIORITY_ACTION,
            EventPayload::OrganizedAction {
                organization: (INSURGENT as u32).into(),
                locality: 0u32.into(),
            },
        )?;
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

fn make_belief_state(
    topology: &StaticTopology,
    config: &SimulationConfig,
) -> pineland_core::state::BeliefState {
    let mut keys = Vec::new();
    for observer in 0..5 {
        for locality in 0..topology.locality_count() {
            keys.push(BeliefKey {
                observer: observer as u32,
                target: INSURGENT as u32,
                locality: locality as u32,
                kind: 0,
            });
            keys.push(BeliefKey {
                observer: observer as u32,
                target: INSURGENT as u32,
                locality: locality as u32,
                kind: 1,
            });
        }
    }
    let mut state = pineland_core::state::BeliefState::with_keys(keys);
    for i in 0..state.keys.len() {
        state.confidence[i] = config.information.prior_confidence;
        state.updated_at[i] = 0.0;
    }
    state
}
fn total_or_population(p: &ParticleState) -> f64 {
    p.locality.population.iter().sum()
}
fn locality_count(topology: &StaticTopology) -> usize {
    topology.locality_count()
}
fn event_locality(event: &ScheduledEvent) -> u32 {
    match event.payload {
        EventPayload::OrganizedAction { locality, .. } => locality.get(),
        EventPayload::Contact { locality, .. } => locality.get(),
        _ => u32::MAX,
    }
}
trait PyRandomExtras {
    fn lognormal(&mut self, mu: f64, sigma: f64) -> f64;
}
impl PyRandomExtras for PyRandomCompat {
    fn lognormal(&mut self, mu: f64, sigma: f64) -> f64 {
        (mu + sigma * self.normalvariate(0.0, 1.0)).exp()
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
        assert_eq!(engine.particle.people.locality.len(), 4);
        assert_eq!(
            engine.particle.patrols.formation.len(),
            engine.particle.formations.organization.len()
        );
        assert_eq!(engine.particle.security_posts.locality.len(), 4);
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
        assert_ne!(
            a.particle.locality.population,
            c.particle.locality.population
        );
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
