//! Dense structure-of-arrays dynamic state.

use crate::rng::RngStreams;
use crate::scheduler::{EventPayload, ScheduledEvent, Scheduler, SchedulerError};
use crate::sha256;
use std::collections::BTreeMap;
use std::fmt;

pub const CONTROL_DIMENSIONS: usize = 7;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct LocalityState {
    pub population: Vec<f64>,
    pub economic_output: Vec<f64>,
    pub infrastructure: Vec<f64>,
    pub administrative_capacity: Vec<f64>,
    pub terrain_friction: Vec<f64>,
    pub observability: Vec<f64>,
    pub government_control: Vec<f64>,
    pub insurgent_control: Vec<f64>,
    pub violence: Vec<f64>,
    pub disruption: Vec<f64>,
    pub displaced_population: Vec<f64>,
    pub government_governance: Vec<f64>,
    pub insurgent_governance: Vec<f64>,
}

impl LocalityState {
    pub fn new(count: usize) -> Self {
        Self {
            population: vec![0.0; count],
            economic_output: vec![0.0; count],
            infrastructure: vec![0.0; count],
            administrative_capacity: vec![0.0; count],
            terrain_friction: vec![1.0; count],
            observability: vec![0.5; count],
            government_control: vec![0.0; count * CONTROL_DIMENSIONS],
            insurgent_control: vec![0.0; count * CONTROL_DIMENSIONS],
            violence: vec![0.0; count],
            disruption: vec![0.0; count],
            displaced_population: vec![0.0; count],
            government_governance: vec![0.0; count],
            insurgent_governance: vec![0.0; count],
        }
    }

    pub fn control_offset(locality: usize) -> usize {
        locality * CONTROL_DIMENSIONS
    }

    pub fn effective_control(&self, locality: usize, actor: u8) -> f64 {
        let controls = if actor == 0 {
            &self.government_control
        } else {
            &self.insurgent_control
        };
        let offset = Self::control_offset(locality);
        let weights = [1.0, 1.0, 0.8, 0.7, 0.6, 0.9, 1.1];
        let mut numerator = 0.0;
        let mut denominator = 0.0;
        for index in 0..CONTROL_DIMENSIONS {
            numerator += controls[offset + index] * weights[index];
            denominator += weights[index];
        }
        if denominator == 0.0 {
            0.0
        } else {
            numerator / denominator
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct ZoneState {
    pub population_share: Vec<f64>,
    pub infrastructure: Vec<f64>,
    pub terrain_friction: Vec<f64>,
    pub observability: Vec<f64>,
    pub government_control: Vec<f64>,
    pub insurgent_control: Vec<f64>,
    pub government_presence: Vec<f64>,
    pub insurgent_presence: Vec<f64>,
    pub government_presence_updated_at: Vec<f64>,
    pub insurgent_presence_updated_at: Vec<f64>,
}

impl ZoneState {
    pub fn new(count: usize) -> Self {
        Self {
            population_share: vec![1.0; count],
            infrastructure: vec![0.5; count],
            terrain_friction: vec![1.0; count],
            observability: vec![0.5; count],
            government_control: vec![0.0; count],
            insurgent_control: vec![0.0; count],
            government_presence: vec![0.0; count],
            insurgent_presence: vec![0.0; count],
            government_presence_updated_at: vec![0.0; count],
            insurgent_presence_updated_at: vec![0.0; count],
        }
    }
}

/// Weighted population cells used by the native engine.  A cell keeps the
/// individual-level dimensions needed by social, mobility, grievance, and
/// recruitment processes without forcing those processes to cross a Python
/// object boundary.  Production cases can choose the cell count at
/// initialization; the default engine uses one cell per locality.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PersonState {
    pub locality: Vec<u32>,
    pub represented_population: Vec<f64>,
    pub household: Vec<u32>,
    pub age: Vec<u8>,
    /// Flattened language, identity, and party-preference rows.  The fixed
    /// widths are the Pineland schema: four languages, three identity
    /// dimensions, and three party preferences per representative person.
    pub languages: Vec<f64>,
    pub identities: Vec<f64>,
    pub preferences: Vec<f64>,
    pub grievance: Vec<f64>,
    pub fear: Vec<f64>,
    pub efficacy: Vec<f64>,
    pub trust: Vec<f64>,
    pub trust_insurgent: Vec<f64>,
    pub resources: Vec<f64>,
    pub home: Vec<u32>,
    pub residence: Vec<u32>,
    pub rebel_sympathy: Vec<f64>,
    pub organization: Vec<u32>,
    pub armed_fraction: Vec<f64>,
    pub community: Vec<u32>,
}

impl PersonState {
    pub fn new(count: usize) -> Self {
        Self {
            locality: vec![0; count],
            represented_population: vec![0.0; count],
            household: (0..count).map(|value| value as u32).collect(),
            age: vec![0; count],
            languages: vec![0.0; count * 4],
            identities: vec![0.0; count * 3],
            preferences: vec![0.0; count * 3],
            grievance: vec![0.0; count],
            fear: vec![0.0; count],
            efficacy: vec![0.5; count],
            trust: vec![0.5; count],
            trust_insurgent: vec![0.2; count],
            resources: vec![0.0; count],
            home: vec![0; count],
            residence: vec![0; count],
            rebel_sympathy: vec![0.0; count],
            organization: vec![u32::MAX; count],
            armed_fraction: vec![0.0; count],
            community: vec![u32::MAX; count],
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PatrolState {
    pub formation: Vec<u32>,
    pub active: Vec<u8>,
    pub route_position: Vec<u32>,
    pub route_target: Vec<u32>,
    pub last_departure: Vec<f64>,
    pub next_available: Vec<f64>,
    pub detections: Vec<u32>,
}

impl PatrolState {
    pub fn new(count: usize) -> Self {
        Self {
            formation: (0..count).map(|value| value as u32).collect(),
            active: vec![1; count],
            route_position: vec![0; count],
            route_target: vec![0; count],
            last_departure: vec![-1.0e9; count],
            next_available: vec![0.0; count],
            detections: vec![0; count],
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct SecurityPostState {
    pub organization: Vec<u32>,
    pub locality: Vec<u32>,
    pub microzone: Vec<u32>,
    pub personnel: Vec<f64>,
    pub presence: Vec<f64>,
    pub available_fraction: Vec<f64>,
    pub formation: Vec<u32>,
    pub detection_rate: Vec<f64>,
    pub reliability: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub staffed: Vec<u8>,
}

impl SecurityPostState {
    pub fn new(count: usize) -> Self {
        Self {
            organization: vec![0; count],
            locality: (0..count).map(|value| value as u32).collect(),
            microzone: vec![0; count],
            personnel: vec![0.0; count],
            presence: vec![0.0; count],
            available_fraction: vec![0.0; count],
            formation: vec![u32::MAX; count],
            detection_rate: vec![0.5; count],
            reliability: vec![0.5; count],
            updated_at: vec![0.0; count],
            staffed: vec![1; count],
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct OrganizationState {
    pub kind: Vec<u8>,
    pub active: Vec<u8>,
    pub capital: Vec<f64>,
    pub cohesion: Vec<f64>,
    pub discipline: Vec<f64>,
    pub accountability: Vec<f64>,
    pub local_knowledge: Vec<f64>,
    pub persistence: Vec<f64>,
    pub mobility: Vec<f64>,
    pub institutional_quality: Vec<f64>,
    pub external_support: Vec<f64>,
    pub member_population: Vec<f64>,
    pub founded_at: Vec<f64>,
    pub succession_count: Vec<u32>,
}

impl OrganizationState {
    pub fn new(count: usize) -> Self {
        Self {
            kind: vec![0; count],
            active: vec![1; count],
            capital: vec![0.0; count],
            cohesion: vec![0.5; count],
            discipline: vec![0.5; count],
            accountability: vec![0.5; count],
            local_knowledge: vec![0.5; count],
            persistence: vec![0.5; count],
            mobility: vec![0.5; count],
            institutional_quality: vec![0.5; count],
            external_support: vec![0.0; count],
            member_population: vec![0.0; count],
            founded_at: vec![0.0; count],
            succession_count: vec![0; count],
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct FormationState {
    pub organization: Vec<u32>,
    pub locality: Vec<u32>,
    pub microzone: Vec<u32>,
    pub personnel: Vec<f64>,
    pub quality: Vec<f64>,
    pub cohesion: Vec<f64>,
    pub readiness: Vec<f64>,
    pub sustainment: Vec<f64>,
    pub information: Vec<f64>,
    pub mobility: Vec<f64>,
    pub command: Vec<f64>,
    pub embeddedness: Vec<f64>,
    pub fatigue: Vec<f64>,
    pub availability: Vec<f64>,
    pub supply_stock: Vec<f64>,
    pub supply_capacity: Vec<f64>,
    pub home_locality: Vec<u32>,
    pub active: Vec<u8>,
    pub moving: Vec<u8>,
    pub operational_status: Vec<u8>,
    pub cumulative_losses: Vec<f64>,
    pub outside_pineland: Vec<u8>,
    pub operational_posture: Vec<u8>,
}

impl FormationState {
    pub fn new(count: usize) -> Self {
        Self {
            organization: vec![0; count],
            locality: vec![0; count],
            microzone: vec![0; count],
            personnel: vec![0.0; count],
            quality: vec![0.5; count],
            cohesion: vec![0.5; count],
            readiness: vec![1.0; count],
            sustainment: vec![1.0; count],
            information: vec![0.5; count],
            mobility: vec![0.5; count],
            command: vec![0.8; count],
            embeddedness: vec![0.0; count],
            fatigue: vec![0.0; count],
            availability: vec![1.0; count],
            supply_stock: vec![0.0; count],
            supply_capacity: vec![0.0; count],
            home_locality: vec![0; count],
            active: vec![1; count],
            moving: vec![0; count],
            operational_status: vec![1; count],
            cumulative_losses: vec![0.0; count],
            outside_pineland: vec![0; count],
            operational_posture: vec![0; count],
        }
    }

    pub fn effective_readiness(&self, formation: usize) -> f64 {
        clamp01(
            self.readiness[formation]
                * self.availability[formation]
                * (1.0 - 0.45 * self.fatigue[formation]),
        )
    }

    pub fn effective_strength(&self, formation: usize) -> f64 {
        self.personnel[formation]
            * self.quality[formation].max(0.0)
            * self.effective_readiness(formation)
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct FootholdState {
    pub organization: Vec<u32>,
    pub locality: Vec<u32>,
    pub strength: Vec<f64>,
    pub raw_signal: Vec<f64>,
    pub membership: Vec<f64>,
    pub embeddedness: Vec<f64>,
    pub access: Vec<f64>,
    pub target_knowledge: Vec<f64>,
    pub infrastructure: Vec<f64>,
    pub sustainment: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub first_activated_at: Vec<f64>,
    pub last_activated_at: Vec<f64>,
    pub cumulative_active_days: Vec<f64>,
    pub cumulative_arrivals: Vec<f64>,
    pub cumulative_recruits: Vec<f64>,
    pub cumulative_actions: Vec<f64>,
    pub viable_activation_count: Vec<u32>,
    pub renewal_count: Vec<u32>,
    pub active: Vec<u8>,
}

impl FootholdState {
    pub fn new(count: usize) -> Self {
        Self {
            organization: vec![0; count],
            locality: vec![0; count],
            strength: vec![0.0; count],
            raw_signal: vec![0.0; count],
            membership: vec![0.0; count],
            embeddedness: vec![0.0; count],
            access: vec![0.0; count],
            target_knowledge: vec![0.0; count],
            infrastructure: vec![0.0; count],
            sustainment: vec![0.0; count],
            updated_at: vec![0.0; count],
            first_activated_at: vec![-1.0e9; count],
            last_activated_at: vec![-1.0e9; count],
            cumulative_active_days: vec![0.0; count],
            cumulative_arrivals: vec![0.0; count],
            cumulative_recruits: vec![0.0; count],
            cumulative_actions: vec![0.0; count],
            viable_activation_count: vec![0; count],
            renewal_count: vec![0; count],
            active: vec![1; count],
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct BeliefKey {
    pub observer: u32,
    pub target: u32,
    pub locality: u32,
    pub kind: u8,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct BeliefState {
    pub keys: Vec<BeliefKey>,
    pub presence: Vec<f64>,
    pub control: Vec<f64>,
    pub confidence: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub last_reliable_observation_at: Vec<f64>,
    pub contradiction: Vec<f64>,
    pub source_confidence: Vec<f64>,
    pub evidence_count: Vec<u32>,
    pub dirty: Vec<u32>,
}

impl BeliefState {
    pub fn with_keys(keys: Vec<BeliefKey>) -> Self {
        let count = keys.len();
        Self {
            keys,
            presence: vec![0.0; count],
            control: vec![0.0; count * CONTROL_DIMENSIONS],
            confidence: vec![0.0; count],
            updated_at: vec![0.0; count],
            last_reliable_observation_at: vec![-1.0e9; count],
            contradiction: vec![0.0; count],
            source_confidence: vec![0.0; count],
            evidence_count: vec![0; count],
            dirty: Vec::new(),
        }
    }

    pub fn ensure_key(&mut self, key: BeliefKey) -> usize {
        if let Some(index) = self.keys.iter().position(|existing| existing == &key) {
            return index;
        }
        let index = self.keys.len();
        self.keys.push(key);
        self.presence.push(0.0);
        self.control
            .extend(std::iter::repeat_n(0.0, CONTROL_DIMENSIONS));
        self.confidence.push(0.0);
        self.updated_at.push(0.0);
        self.last_reliable_observation_at.push(-1.0e9);
        self.contradiction.push(0.0);
        self.source_confidence.push(0.0);
        self.evidence_count.push(0);
        index
    }

    pub fn fuse_control(
        &mut self,
        index: usize,
        time: f64,
        weight: f64,
        observed: &[f64; CONTROL_DIMENSIONS],
        memory_days: f64,
        penalty: f64,
    ) {
        if index >= self.keys.len() {
            return;
        }
        let prior_confidence = self.confidence[index];
        let prior = prior_confidence.max(0.02);
        let denominator = prior + weight;
        let scale = denominator / (1.0 + denominator);
        let age = (time - self.updated_at[index]).max(0.0);
        let decay = (-age / memory_days.max(f64::MIN_POSITIVE)).exp();
        let offset = index * CONTROL_DIMENSIONS;
        let mut contradiction = self.contradiction[index] * decay;
        let mut confidence = prior_confidence;
        for (dimension, observed_value) in observed.iter().enumerate() {
            let value = clamp01(*observed_value);
            let old = self.control[offset + dimension];
            self.control[offset + dimension] =
                clamp01((prior * old + weight * value) / denominator);
            contradiction += weight * (value - old).abs();
            confidence = clamp01(scale * (-penalty * contradiction).exp());
        }
        self.confidence[index] = confidence;
        self.updated_at[index] = time;
        if weight >= 0.12 {
            self.last_reliable_observation_at[index] = time;
        }
        self.evidence_count[index] = self.evidence_count[index].saturating_add(1);
        self.contradiction[index] = contradiction;
        self.source_confidence[index] = self.source_confidence[index].max(weight);
        self.dirty.push(index as u32);
    }

    #[allow(clippy::too_many_arguments)]
    pub fn fuse_presence(
        &mut self,
        index: usize,
        time: f64,
        weight: f64,
        presence: f64,
        personnel: f64,
        memory_days: f64,
        penalty: f64,
    ) {
        if index >= self.keys.len() {
            return;
        }
        let prior_confidence = self.confidence[index];
        let prior = prior_confidence.max(0.02);
        let denominator = prior + weight;
        let old = self.presence[index];
        let age = (time - self.updated_at[index]).max(0.0);
        let mut contradiction =
            self.contradiction[index] * (-age / memory_days.max(f64::MIN_POSITIVE)).exp();
        contradiction += weight * (clamp01(presence) - old).abs();
        self.presence[index] = clamp01((prior * old + weight * clamp01(presence)) / denominator);
        self.source_confidence[index] =
            (self.source_confidence[index] * prior + weight * personnel.max(0.0)) / denominator;
        self.confidence[index] =
            clamp01((prior + weight) / (1.0 + prior + weight) * (-penalty * contradiction).exp());
        self.updated_at[index] = time;
        if weight >= 0.12 {
            self.last_reliable_observation_at[index] = time;
        }
        self.evidence_count[index] = self.evidence_count[index].saturating_add(1);
        self.contradiction[index] = contradiction;
        self.dirty.push(index as u32);
    }

    pub fn take_dirty(&mut self) -> Vec<usize> {
        let mut result: Vec<usize> = self.dirty.drain(..).map(|value| value as usize).collect();
        result.sort_unstable();
        result.dedup();
        result
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct LogisticsState {
    pub organization: Vec<u32>,
    pub locality: Vec<u32>,
    pub source_stock: Vec<f64>,
    pub source_capacity: Vec<f64>,
    pub source_production: Vec<f64>,
    pub in_transit: f64,
    pub cumulative_produced: f64,
    pub cumulative_consumed: f64,
    pub cumulative_lost: f64,
    pub cumulative_shipped: f64,
    pub cumulative_delivered: f64,
}

impl LogisticsState {
    pub fn new(count: usize) -> Self {
        Self {
            organization: vec![0; count],
            locality: vec![0; count],
            source_stock: vec![0.0; count],
            source_capacity: vec![0.0; count],
            source_production: vec![0.0; count],
            ..Self::default()
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Counters {
    pub event_counts: BTreeMap<String, u64>,
    pub contacts: u64,
    pub organized_actions: u64,
    pub recorded_events: u64,
    pub observations: u64,
    pub recruitment: f64,
    pub civilian_harm: f64,
    pub deaths: f64,
    pub checkpoints: u64,
}

impl Counters {
    pub fn record(&mut self, kind: &str) {
        *self.event_counts.entry(kind.to_string()).or_default() += 1;
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ObservationRecord {
    pub time: f64,
    pub kind: u8,
    pub locality: u32,
    pub actor: u32,
    pub value: f64,
    pub confidence: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct EventRecord {
    pub time: f64,
    pub sequence: u64,
    pub kind: String,
    pub locality: u32,
    pub value: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ParticleState {
    pub logical_id: u64,
    pub lineage: String,
    pub time: f64,
    pub locality: LocalityState,
    pub zones: ZoneState,
    pub people: PersonState,
    pub organizations: OrganizationState,
    pub formations: FormationState,
    pub patrols: PatrolState,
    pub security_posts: SecurityPostState,
    pub footholds: FootholdState,
    pub beliefs: BeliefState,
    pub logistics: LogisticsState,
    pub scheduler: Scheduler,
    pub rng: RngStreams,
    pub counters: Counters,
    pub observations: Vec<ObservationRecord>,
    pub event_log: Vec<EventRecord>,
    pub weights_log: f64,
    pub ancestry: Vec<u64>,
    pub filter_boundary: u64,
}

impl ParticleState {
    pub fn new(
        localities: usize,
        zones: usize,
        organizations: usize,
        formations: usize,
        footholds: usize,
        rng: RngStreams,
    ) -> Self {
        Self {
            logical_id: 0,
            lineage: "root.0".to_string(),
            time: 0.0,
            locality: LocalityState::new(localities),
            zones: ZoneState::new(zones),
            people: PersonState::new(0),
            organizations: OrganizationState::new(organizations),
            formations: FormationState::new(formations),
            patrols: PatrolState::new(formations),
            security_posts: SecurityPostState::new(localities),
            footholds: FootholdState::new(footholds),
            beliefs: BeliefState::default(),
            logistics: LogisticsState::new(organizations),
            scheduler: Scheduler::new(),
            rng,
            counters: Counters::default(),
            observations: Vec::new(),
            event_log: Vec::new(),
            weights_log: 0.0,
            ancestry: vec![0],
            filter_boundary: 0,
        }
    }

    pub fn new_with_people(
        localities: usize,
        zones: usize,
        people: usize,
        organizations: usize,
        formations: usize,
        footholds: usize,
        rng: RngStreams,
    ) -> Self {
        let mut particle = Self::new(localities, zones, organizations, formations, footholds, rng);
        particle.people = PersonState::new(people);
        particle
    }

    pub fn clone_for_child(&self, child_id: u64, child_lineage: impl Into<String>) -> Self {
        let child_lineage = child_lineage.into();
        let mut clone = self.clone();
        clone.logical_id = child_id;
        clone.lineage = child_lineage.clone();
        // A cloned particle is a new stochastic trajectory.  Deriving its
        // stream from the parent lineage keeps branching deterministic while
        // preventing siblings from sharing future random draws.
        clone.rng = self.rng.fork(&format!("child:{child_lineage}"));
        clone.ancestry.push(self.logical_id);
        clone
    }

    pub fn gather(states: &[Self], parents: &[usize]) -> Result<Vec<Self>, StateError> {
        let mut result = Vec::with_capacity(parents.len());
        for (child_id, parent) in parents.iter().copied().enumerate() {
            let source = states
                .get(parent)
                .ok_or(StateError::ParentOutOfBounds(parent))?;
            let lineage = format!("{}.{}", source.lineage, child_id);
            let mut child = source.clone_for_child(child_id as u64, lineage);
            child.rng = source
                .rng
                .fork(&format!("gather-child-{child_id}:parent-{parent}"));
            result.push(child);
        }
        Ok(result)
    }

    pub fn state_hash(&self) -> String {
        let mut material = Vec::new();
        self.append_hash_material(&mut material);
        sha256::digest_hex(&material)
    }

    pub fn decision_hash(&self) -> String {
        let mut material = Vec::new();
        material.extend_from_slice(&self.time.to_bits().to_le_bytes());
        for values in [
            &self.locality.government_control,
            &self.locality.insurgent_control,
            &self.locality.violence,
            &self.locality.disruption,
            &self.formations.personnel,
            &self.formations.readiness,
            &self.formations.supply_stock,
            &self.footholds.strength,
            &self.beliefs.presence,
            &self.beliefs.control,
            &self.beliefs.confidence,
        ] {
            append_f64s(&mut material, values);
        }
        sha256::digest_hex(&material)
    }

    fn append_hash_material(&self, material: &mut Vec<u8>) {
        material.extend_from_slice(&self.logical_id.to_le_bytes());
        material.extend_from_slice(&self.time.to_bits().to_le_bytes());
        append_string(material, &self.lineage);

        // The execution hash is deliberately broader than the decision hash:
        // it includes every mutable array and continuation datum that can
        // affect a future event.  This is the hash used for restart and
        // distributed-equivalence certification.
        append_f64s(material, &self.locality.population);
        append_f64s(material, &self.locality.economic_output);
        append_f64s(material, &self.locality.infrastructure);
        append_f64s(material, &self.locality.administrative_capacity);
        append_f64s(material, &self.locality.terrain_friction);
        append_f64s(material, &self.locality.observability);
        append_f64s(material, &self.locality.government_control);
        append_f64s(material, &self.locality.insurgent_control);
        append_f64s(material, &self.locality.violence);
        append_f64s(material, &self.locality.disruption);
        append_f64s(material, &self.locality.displaced_population);
        append_f64s(material, &self.locality.government_governance);
        append_f64s(material, &self.locality.insurgent_governance);
        append_u32s(material, &self.people.locality);
        append_f64s(material, &self.people.represented_population);
        append_u32s(material, &self.people.household);
        append_u8s(material, &self.people.age);
        append_f64s(material, &self.people.languages);
        append_f64s(material, &self.people.identities);
        append_f64s(material, &self.people.preferences);
        append_f64s(material, &self.people.grievance);
        append_f64s(material, &self.people.fear);
        append_f64s(material, &self.people.efficacy);
        append_f64s(material, &self.people.trust);
        append_f64s(material, &self.people.trust_insurgent);
        append_f64s(material, &self.people.resources);
        append_u32s(material, &self.people.home);
        append_u32s(material, &self.people.residence);
        append_f64s(material, &self.people.rebel_sympathy);
        append_u32s(material, &self.people.organization);
        append_f64s(material, &self.people.armed_fraction);
        append_u32s(material, &self.people.community);
        append_f64s(material, &self.zones.population_share);
        append_f64s(material, &self.zones.infrastructure);
        append_f64s(material, &self.zones.terrain_friction);
        append_f64s(material, &self.zones.observability);
        append_f64s(material, &self.zones.government_control);
        append_f64s(material, &self.zones.insurgent_control);
        append_f64s(material, &self.zones.government_presence);
        append_f64s(material, &self.zones.insurgent_presence);
        append_f64s(material, &self.zones.government_presence_updated_at);
        append_f64s(material, &self.zones.insurgent_presence_updated_at);
        append_u8s(material, &self.organizations.kind);
        append_u8s(material, &self.organizations.active);
        append_f64s(material, &self.organizations.capital);
        append_f64s(material, &self.organizations.cohesion);
        append_f64s(material, &self.organizations.discipline);
        append_f64s(material, &self.organizations.accountability);
        append_f64s(material, &self.organizations.local_knowledge);
        append_f64s(material, &self.organizations.persistence);
        append_f64s(material, &self.organizations.mobility);
        append_f64s(material, &self.organizations.institutional_quality);
        append_f64s(material, &self.organizations.external_support);
        append_f64s(material, &self.organizations.member_population);
        append_f64s(material, &self.organizations.founded_at);
        append_u32s(material, &self.organizations.succession_count);
        append_u32s(material, &self.formations.organization);
        append_u32s(material, &self.formations.locality);
        append_u32s(material, &self.formations.microzone);
        append_f64s(material, &self.formations.personnel);
        append_f64s(material, &self.formations.quality);
        append_f64s(material, &self.formations.cohesion);
        append_f64s(material, &self.formations.readiness);
        append_f64s(material, &self.formations.sustainment);
        append_f64s(material, &self.formations.information);
        append_f64s(material, &self.formations.mobility);
        append_f64s(material, &self.formations.command);
        append_f64s(material, &self.formations.embeddedness);
        append_f64s(material, &self.formations.fatigue);
        append_f64s(material, &self.formations.availability);
        append_f64s(material, &self.formations.supply_stock);
        append_f64s(material, &self.formations.supply_capacity);
        append_u32s(material, &self.formations.home_locality);
        append_u8s(material, &self.formations.active);
        append_u8s(material, &self.formations.moving);
        append_u8s(material, &self.formations.operational_status);
        append_f64s(material, &self.formations.cumulative_losses);
        append_u8s(material, &self.formations.outside_pineland);
        append_u8s(material, &self.formations.operational_posture);
        append_u32s(material, &self.patrols.formation);
        append_u8s(material, &self.patrols.active);
        append_u32s(material, &self.patrols.route_position);
        append_u32s(material, &self.patrols.route_target);
        append_f64s(material, &self.patrols.last_departure);
        append_f64s(material, &self.patrols.next_available);
        append_u32s(material, &self.patrols.detections);
        append_u32s(material, &self.security_posts.organization);
        append_u32s(material, &self.security_posts.locality);
        append_u32s(material, &self.security_posts.microzone);
        append_f64s(material, &self.security_posts.personnel);
        append_f64s(material, &self.security_posts.presence);
        append_f64s(material, &self.security_posts.available_fraction);
        append_u32s(material, &self.security_posts.formation);
        append_f64s(material, &self.security_posts.detection_rate);
        append_f64s(material, &self.security_posts.reliability);
        append_f64s(material, &self.security_posts.updated_at);
        append_u8s(material, &self.security_posts.staffed);
        append_u32s(material, &self.footholds.organization);
        append_u32s(material, &self.footholds.locality);
        append_f64s(material, &self.footholds.strength);
        append_f64s(material, &self.footholds.raw_signal);
        append_f64s(material, &self.footholds.membership);
        append_f64s(material, &self.footholds.embeddedness);
        append_f64s(material, &self.footholds.access);
        append_f64s(material, &self.footholds.target_knowledge);
        append_f64s(material, &self.footholds.infrastructure);
        append_f64s(material, &self.footholds.sustainment);
        append_f64s(material, &self.footholds.updated_at);
        append_f64s(material, &self.footholds.first_activated_at);
        append_f64s(material, &self.footholds.last_activated_at);
        append_f64s(material, &self.footholds.cumulative_active_days);
        append_f64s(material, &self.footholds.cumulative_arrivals);
        append_f64s(material, &self.footholds.cumulative_recruits);
        append_f64s(material, &self.footholds.cumulative_actions);
        append_u32s(material, &self.footholds.viable_activation_count);
        append_u32s(material, &self.footholds.renewal_count);
        append_u8s(material, &self.footholds.active);
        for key in &self.beliefs.keys {
            material.extend_from_slice(&key.observer.to_le_bytes());
            material.extend_from_slice(&key.target.to_le_bytes());
            material.extend_from_slice(&key.locality.to_le_bytes());
            material.push(key.kind);
        }
        material.extend_from_slice(&(self.beliefs.keys.len() as u64).to_le_bytes());
        append_f64s(material, &self.beliefs.presence);
        append_f64s(material, &self.beliefs.control);
        append_f64s(material, &self.beliefs.confidence);
        append_f64s(material, &self.beliefs.updated_at);
        append_f64s(material, &self.beliefs.last_reliable_observation_at);
        append_f64s(material, &self.beliefs.contradiction);
        append_f64s(material, &self.beliefs.source_confidence);
        append_u32s(material, &self.beliefs.evidence_count);
        append_u32s(material, &self.beliefs.dirty);
        append_u32s(material, &self.logistics.organization);
        append_u32s(material, &self.logistics.locality);
        append_f64s(material, &self.logistics.source_stock);
        append_f64s(material, &self.logistics.source_capacity);
        append_f64s(material, &self.logistics.source_production);
        material.extend_from_slice(&self.logistics.in_transit.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_produced.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_consumed.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_lost.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_shipped.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_delivered.to_bits().to_le_bytes());
        for event in self.scheduler.events_sorted() {
            encode_event(material, &event);
        }
        material.extend_from_slice(&self.scheduler.next_sequence.to_le_bytes());
        material.extend_from_slice(&self.scheduler.processed.to_le_bytes());
        material.extend_from_slice(&self.rng.state_digest_material());
        material.extend_from_slice(&self.weights_log.to_bits().to_le_bytes());
        append_u64s(material, &self.ancestry);
        material.extend_from_slice(&self.filter_boundary.to_le_bytes());
        material.extend_from_slice(&(self.observations.len() as u64).to_le_bytes());
        for observation in &self.observations {
            material.extend_from_slice(&observation.time.to_bits().to_le_bytes());
            material.push(observation.kind);
            material.extend_from_slice(&observation.locality.to_le_bytes());
            material.extend_from_slice(&observation.actor.to_le_bytes());
            material.extend_from_slice(&observation.value.to_bits().to_le_bytes());
            material.extend_from_slice(&observation.confidence.to_bits().to_le_bytes());
        }
        material.extend_from_slice(&(self.event_log.len() as u64).to_le_bytes());
        for event in &self.event_log {
            material.extend_from_slice(&event.time.to_bits().to_le_bytes());
            material.extend_from_slice(&event.sequence.to_le_bytes());
            append_string(material, &event.kind);
            material.extend_from_slice(&event.locality.to_le_bytes());
            material.extend_from_slice(&event.value.to_bits().to_le_bytes());
        }
        for (name, count) in &self.counters.event_counts {
            append_string(material, name);
            material.extend_from_slice(&count.to_le_bytes());
        }
        material.extend_from_slice(&(self.counters.event_counts.len() as u64).to_le_bytes());
        material.extend_from_slice(&self.counters.contacts.to_le_bytes());
        material.extend_from_slice(&self.counters.organized_actions.to_le_bytes());
        material.extend_from_slice(&self.counters.recorded_events.to_le_bytes());
        material.extend_from_slice(&self.counters.observations.to_le_bytes());
        material.extend_from_slice(&self.counters.recruitment.to_bits().to_le_bytes());
        material.extend_from_slice(&self.counters.civilian_harm.to_bits().to_le_bytes());
        material.extend_from_slice(&self.counters.deaths.to_bits().to_le_bytes());
        material.extend_from_slice(&self.counters.checkpoints.to_le_bytes());
    }

    pub fn validate(&self) -> Result<(), StateError> {
        let locality_count = self.locality.population.len();
        for (length, name) in [
            (
                self.locality.economic_output.len(),
                "locality economic output",
            ),
            (
                self.locality.infrastructure.len(),
                "locality infrastructure",
            ),
            (
                self.locality.administrative_capacity.len(),
                "locality administrative capacity",
            ),
            (
                self.locality.terrain_friction.len(),
                "locality terrain friction",
            ),
            (self.locality.observability.len(), "locality observability"),
            (self.locality.violence.len(), "locality violence"),
            (self.locality.disruption.len(), "locality disruption"),
            (
                self.locality.displaced_population.len(),
                "locality displaced population",
            ),
            (
                self.locality.government_governance.len(),
                "government governance",
            ),
            (
                self.locality.insurgent_governance.len(),
                "insurgent governance",
            ),
        ] {
            if length != locality_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: locality_count,
                });
            }
        }
        let expected_controls = locality_count.saturating_mul(CONTROL_DIMENSIONS);
        for (length, name) in [
            (self.locality.government_control.len(), "government control"),
            (self.locality.insurgent_control.len(), "insurgent control"),
        ] {
            if length != expected_controls {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: expected_controls,
                });
            }
        }
        let people_count = self.people.locality.len();
        for (length, name) in [
            (
                self.people.represented_population.len(),
                "represented population",
            ),
            (self.people.household.len(), "person household"),
            (self.people.age.len(), "person age"),
            (self.people.grievance.len(), "person grievance"),
            (self.people.fear.len(), "person fear"),
            (self.people.efficacy.len(), "person efficacy"),
            (self.people.trust.len(), "person trust"),
            (self.people.trust_insurgent.len(), "person insurgent trust"),
            (self.people.resources.len(), "person resources"),
            (self.people.home.len(), "person home"),
            (self.people.residence.len(), "person residence"),
            (self.people.rebel_sympathy.len(), "person sympathy"),
            (self.people.organization.len(), "person organization"),
            (self.people.armed_fraction.len(), "person armed fraction"),
            (self.people.community.len(), "person community"),
        ] {
            if length != people_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: people_count,
                });
            }
        }
        for (length, name, expected) in [
            (
                self.people.languages.len(),
                "person languages",
                people_count * 4,
            ),
            (
                self.people.identities.len(),
                "person identities",
                people_count * 3,
            ),
            (
                self.people.preferences.len(),
                "person preferences",
                people_count * 3,
            ),
        ] {
            if length != expected {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: expected,
                });
            }
        }
        let zone_count = self.zones.population_share.len();
        for (length, name) in [
            (self.zones.infrastructure.len(), "zone infrastructure"),
            (self.zones.terrain_friction.len(), "zone terrain friction"),
            (self.zones.observability.len(), "zone observability"),
            (
                self.zones.government_control.len(),
                "zone government control",
            ),
            (self.zones.insurgent_control.len(), "zone insurgent control"),
            (
                self.zones.government_presence.len(),
                "zone government presence",
            ),
            (
                self.zones.insurgent_presence.len(),
                "zone insurgent presence",
            ),
            (
                self.zones.government_presence_updated_at.len(),
                "government presence timestamps",
            ),
            (
                self.zones.insurgent_presence_updated_at.len(),
                "insurgent presence timestamps",
            ),
        ] {
            if length != zone_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: zone_count,
                });
            }
        }
        let organization_count = self.organizations.kind.len();
        for (length, name) in [
            (self.organizations.active.len(), "organization active"),
            (self.organizations.capital.len(), "organization capital"),
            (self.organizations.cohesion.len(), "organization cohesion"),
            (
                self.organizations.discipline.len(),
                "organization discipline",
            ),
            (
                self.organizations.accountability.len(),
                "organization accountability",
            ),
            (
                self.organizations.local_knowledge.len(),
                "organization knowledge",
            ),
            (
                self.organizations.persistence.len(),
                "organization persistence",
            ),
            (self.organizations.mobility.len(), "organization mobility"),
            (
                self.organizations.institutional_quality.len(),
                "organization quality",
            ),
            (
                self.organizations.external_support.len(),
                "organization support",
            ),
            (
                self.organizations.member_population.len(),
                "organization population",
            ),
            (
                self.organizations.founded_at.len(),
                "organization founding times",
            ),
            (
                self.organizations.succession_count.len(),
                "organization succession",
            ),
        ] {
            if length != organization_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: organization_count,
                });
            }
        }
        let formation_count = self.formations.organization.len();
        for (length, name) in [
            (self.formations.locality.len(), "formation locality"),
            (self.formations.microzone.len(), "formation microzone"),
            (self.formations.personnel.len(), "formation personnel"),
            (self.formations.quality.len(), "formation quality"),
            (self.formations.cohesion.len(), "formation cohesion"),
            (self.formations.readiness.len(), "formation readiness"),
            (self.formations.sustainment.len(), "formation sustainment"),
            (self.formations.information.len(), "formation information"),
            (self.formations.mobility.len(), "formation mobility"),
            (self.formations.command.len(), "formation command"),
            (self.formations.embeddedness.len(), "formation embeddedness"),
            (self.formations.fatigue.len(), "formation fatigue"),
            (self.formations.availability.len(), "formation availability"),
            (self.formations.supply_stock.len(), "formation supply"),
            (
                self.formations.supply_capacity.len(),
                "formation supply capacity",
            ),
            (
                self.formations.home_locality.len(),
                "formation home locality",
            ),
            (self.formations.active.len(), "formation active"),
            (self.formations.moving.len(), "formation moving"),
            (self.formations.operational_status.len(), "formation status"),
            (self.formations.cumulative_losses.len(), "formation losses"),
            (
                self.formations.outside_pineland.len(),
                "formation border status",
            ),
            (
                self.formations.operational_posture.len(),
                "formation posture",
            ),
        ] {
            if length != formation_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: formation_count,
                });
            }
        }
        for (length, name) in [
            (self.patrols.formation.len(), "patrol formation"),
            (self.patrols.active.len(), "patrol active"),
            (self.patrols.route_position.len(), "patrol route position"),
            (self.patrols.route_target.len(), "patrol route target"),
            (self.patrols.last_departure.len(), "patrol departure"),
            (self.patrols.next_available.len(), "patrol availability"),
            (self.patrols.detections.len(), "patrol detections"),
        ] {
            if length != formation_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: formation_count,
                });
            }
        }
        let post_count = self.security_posts.locality.len();
        for (length, name) in [
            (
                self.security_posts.organization.len(),
                "security post organization",
            ),
            (
                self.security_posts.microzone.len(),
                "security post microzone",
            ),
            (
                self.security_posts.personnel.len(),
                "security post personnel",
            ),
            (self.security_posts.presence.len(), "security post presence"),
            (
                self.security_posts.available_fraction.len(),
                "security post availability",
            ),
            (
                self.security_posts.formation.len(),
                "security post formation",
            ),
            (
                self.security_posts.detection_rate.len(),
                "security post detection rate",
            ),
            (
                self.security_posts.reliability.len(),
                "security post reliability",
            ),
            (
                self.security_posts.updated_at.len(),
                "security post timestamp",
            ),
            (self.security_posts.staffed.len(), "security post staffing"),
        ] {
            if length != post_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: post_count,
                });
            }
        }
        let foothold_count = self.footholds.organization.len();
        for (length, name) in [
            (self.footholds.locality.len(), "foothold locality"),
            (self.footholds.strength.len(), "foothold strength"),
            (self.footholds.raw_signal.len(), "foothold signal"),
            (self.footholds.membership.len(), "foothold membership"),
            (self.footholds.embeddedness.len(), "foothold embeddedness"),
            (self.footholds.access.len(), "foothold access"),
            (
                self.footholds.target_knowledge.len(),
                "foothold target knowledge",
            ),
            (
                self.footholds.infrastructure.len(),
                "foothold infrastructure",
            ),
            (self.footholds.sustainment.len(), "foothold sustainment"),
            (self.footholds.updated_at.len(), "foothold timestamps"),
            (
                self.footholds.first_activated_at.len(),
                "foothold first activation",
            ),
            (
                self.footholds.last_activated_at.len(),
                "foothold last activation",
            ),
            (
                self.footholds.cumulative_active_days.len(),
                "foothold active days",
            ),
            (
                self.footholds.cumulative_arrivals.len(),
                "foothold arrivals",
            ),
            (
                self.footholds.cumulative_recruits.len(),
                "foothold recruits",
            ),
            (self.footholds.cumulative_actions.len(), "foothold actions"),
            (
                self.footholds.viable_activation_count.len(),
                "foothold viability count",
            ),
            (self.footholds.renewal_count.len(), "foothold renewal count"),
            (self.footholds.active.len(), "foothold active"),
        ] {
            if length != foothold_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: foothold_count,
                });
            }
        }
        let belief_count = self.beliefs.keys.len();
        for (length, name) in [
            (self.beliefs.presence.len(), "belief presence"),
            (self.beliefs.confidence.len(), "belief confidence"),
            (self.beliefs.updated_at.len(), "belief timestamps"),
            (
                self.beliefs.last_reliable_observation_at.len(),
                "belief reliable timestamps",
            ),
            (self.beliefs.contradiction.len(), "belief contradiction"),
            (
                self.beliefs.source_confidence.len(),
                "belief source confidence",
            ),
            (self.beliefs.evidence_count.len(), "belief evidence"),
        ] {
            if length != belief_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: belief_count,
                });
            }
        }
        let expected_belief_controls = belief_count.saturating_mul(CONTROL_DIMENSIONS);
        if self.beliefs.control.len() != expected_belief_controls {
            return Err(StateError::LengthMismatch {
                name: "belief control".to_string(),
                left: self.beliefs.control.len(),
                right: expected_belief_controls,
            });
        }
        let organization_count = self.organizations.kind.len();
        let source_count = self.logistics.source_stock.len();
        for (length, name) in [
            (self.logistics.organization.len(), "source organization"),
            (self.logistics.locality.len(), "source locality"),
            (self.logistics.source_stock.len(), "source stock"),
            (self.logistics.source_capacity.len(), "source capacity"),
            (self.logistics.source_production.len(), "source production"),
        ] {
            if length != source_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: source_count,
                });
            }
        }
        for (value, name, bound) in self
            .people
            .locality
            .iter()
            .map(|value| (*value, "person locality", locality_count))
            .chain(
                self.people
                    .home
                    .iter()
                    .map(|value| (*value, "person home", locality_count)),
            )
            .chain(
                self.people
                    .residence
                    .iter()
                    .map(|value| (*value, "person residence", locality_count)),
            )
            .chain(
                self.formations
                    .organization
                    .iter()
                    .map(|value| (*value, "formation organization", organization_count)),
            )
            .chain(
                self.formations
                    .locality
                    .iter()
                    .map(|value| (*value, "formation locality", locality_count)),
            )
            .chain(
                self.formations
                    .microzone
                    .iter()
                    .map(|value| (*value, "formation microzone", zone_count)),
            )
            .chain(
                self.formations
                    .home_locality
                    .iter()
                    .map(|value| (*value, "formation home locality", locality_count)),
            )
            .chain(
                self.patrols
                    .formation
                    .iter()
                    .map(|value| (*value, "patrol formation", formation_count)),
            )
            .chain(
                self.patrols
                    .route_position
                    .iter()
                    .map(|value| (*value, "patrol route position", zone_count)),
            )
            .chain(
                self.patrols
                    .route_target
                    .iter()
                    .map(|value| (*value, "patrol route target", zone_count)),
            )
            .chain(
                self.security_posts
                    .organization
                    .iter()
                    .map(|value| (*value, "security post organization", organization_count)),
            )
            .chain(
                self.security_posts
                    .locality
                    .iter()
                    .map(|value| (*value, "security post locality", locality_count)),
            )
            .chain(
                self.security_posts
                    .microzone
                    .iter()
                    .map(|value| (*value, "security post microzone", zone_count)),
            )
            .chain(
                self.logistics
                    .locality
                    .iter()
                    .map(|value| (*value, "source locality", locality_count)),
            )
            .chain(
                self.footholds
                    .organization
                    .iter()
                    .map(|value| (*value, "foothold organization", organization_count)),
            )
            .chain(
                self.footholds
                    .locality
                    .iter()
                    .map(|value| (*value, "foothold locality", locality_count)),
            )
        {
            if value as usize >= bound {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        for index in &self.beliefs.dirty {
            if *index as usize >= belief_count {
                return Err(StateError::Corrupt(format!(
                    "belief dirty index {index} is outside {belief_count}"
                )));
            }
        }
        if !self.time.is_finite() {
            return Err(StateError::NonFinite("particle time"));
        }
        for (values, name) in [
            (&self.locality.population, "locality population"),
            (&self.locality.economic_output, "economic output"),
            (&self.locality.infrastructure, "infrastructure"),
            (
                &self.locality.administrative_capacity,
                "administrative capacity",
            ),
            (&self.locality.terrain_friction, "terrain friction"),
            (&self.locality.observability, "observability"),
            (&self.locality.government_control, "government control"),
            (&self.locality.insurgent_control, "insurgent control"),
            (&self.locality.violence, "violence"),
            (&self.locality.disruption, "disruption"),
            (&self.locality.displaced_population, "displaced population"),
            (
                &self.locality.government_governance,
                "government governance",
            ),
            (&self.locality.insurgent_governance, "insurgent governance"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.locality.population, "locality population")?;
        check_nonnegative(&self.locality.economic_output, "economic output")?;
        check_nonnegative(&self.locality.displaced_population, "displaced population")?;
        for (values, name) in [
            (
                &self.people.represented_population,
                "represented population",
            ),
            (&self.people.grievance, "person grievance"),
            (&self.people.fear, "person fear"),
            (&self.people.efficacy, "person efficacy"),
            (&self.people.trust, "person trust"),
            (&self.people.rebel_sympathy, "person sympathy"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(
            &self.people.represented_population,
            "represented population",
        )?;
        for value in self
            .people
            .grievance
            .iter()
            .chain(self.people.fear.iter())
            .chain(self.people.efficacy.iter())
            .chain(self.people.trust.iter())
            .chain(self.people.rebel_sympathy.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for value in self
            .locality
            .government_control
            .iter()
            .chain(self.locality.insurgent_control.iter())
            .chain(self.locality.infrastructure.iter())
            .chain(self.locality.administrative_capacity.iter())
            .chain(self.locality.observability.iter())
            .chain(self.locality.violence.iter())
            .chain(self.locality.disruption.iter())
            .chain(self.locality.government_governance.iter())
            .chain(self.locality.insurgent_governance.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for (values, name) in [
            (&self.zones.population_share, "zone population share"),
            (&self.zones.infrastructure, "zone infrastructure"),
            (&self.zones.terrain_friction, "zone terrain friction"),
            (&self.zones.observability, "zone observability"),
            (&self.zones.government_control, "zone government control"),
            (&self.zones.insurgent_control, "zone insurgent control"),
            (&self.zones.government_presence, "zone government presence"),
            (&self.zones.insurgent_presence, "zone insurgent presence"),
            (
                &self.zones.government_presence_updated_at,
                "zone government timestamp",
            ),
            (
                &self.zones.insurgent_presence_updated_at,
                "zone insurgent timestamp",
            ),
        ] {
            check_finite(values, name)?;
        }
        for value in self
            .zones
            .infrastructure
            .iter()
            .chain(self.zones.observability.iter())
            .chain(self.zones.government_control.iter())
            .chain(self.zones.insurgent_control.iter())
            .chain(self.zones.government_presence.iter())
            .chain(self.zones.insurgent_presence.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for (values, name) in [
            (&self.organizations.capital, "organization capital"),
            (&self.organizations.cohesion, "organization cohesion"),
            (&self.organizations.discipline, "organization discipline"),
            (
                &self.organizations.accountability,
                "organization accountability",
            ),
            (
                &self.organizations.local_knowledge,
                "organization knowledge",
            ),
            (&self.organizations.persistence, "organization persistence"),
            (&self.organizations.mobility, "organization mobility"),
            (
                &self.organizations.institutional_quality,
                "organization quality",
            ),
            (&self.organizations.external_support, "organization support"),
            (
                &self.organizations.member_population,
                "organization population",
            ),
            (&self.organizations.founded_at, "organization founding time"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.organizations.capital, "organization capital")?;
        check_nonnegative(&self.organizations.external_support, "organization support")?;
        check_nonnegative(
            &self.organizations.member_population,
            "organization population",
        )?;
        for (values, name) in [
            (&self.formations.personnel, "formation personnel"),
            (&self.formations.quality, "formation quality"),
            (&self.formations.cohesion, "formation cohesion"),
            (&self.formations.readiness, "formation readiness"),
            (&self.formations.sustainment, "formation sustainment"),
            (&self.formations.information, "formation information"),
            (&self.formations.mobility, "formation mobility"),
            (&self.formations.command, "formation command"),
            (&self.formations.embeddedness, "formation embeddedness"),
            (&self.formations.fatigue, "formation fatigue"),
            (&self.formations.availability, "formation availability"),
            (&self.formations.supply_stock, "formation supply"),
            (
                &self.formations.supply_capacity,
                "formation supply capacity",
            ),
            (&self.formations.cumulative_losses, "formation losses"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.formations.personnel, "formation personnel")?;
        check_nonnegative(&self.formations.supply_stock, "formation supply")?;
        check_nonnegative(
            &self.formations.supply_capacity,
            "formation supply capacity",
        )?;
        check_nonnegative(&self.formations.cumulative_losses, "formation losses")?;
        for (values, name) in [
            (&self.patrols.last_departure, "patrol departure"),
            (&self.patrols.next_available, "patrol availability"),
            (&self.security_posts.presence, "security post presence"),
            (
                &self.security_posts.detection_rate,
                "security post detection rate",
            ),
            (
                &self.security_posts.reliability,
                "security post reliability",
            ),
            (&self.security_posts.updated_at, "security post timestamp"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.security_posts.presence, "security post presence")?;
        for value in self
            .security_posts
            .presence
            .iter()
            .chain(self.security_posts.detection_rate.iter())
            .chain(self.security_posts.reliability.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for value in self
            .formations
            .quality
            .iter()
            .chain(self.formations.cohesion.iter())
            .chain(self.formations.readiness.iter())
            .chain(self.formations.sustainment.iter())
            .chain(self.formations.information.iter())
            .chain(self.formations.mobility.iter())
            .chain(self.formations.command.iter())
            .chain(self.formations.embeddedness.iter())
            .chain(self.formations.availability.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for (values, name) in [
            (&self.footholds.strength, "foothold strength"),
            (&self.footholds.raw_signal, "foothold signal"),
            (&self.footholds.membership, "foothold membership"),
            (&self.footholds.embeddedness, "foothold embeddedness"),
            (&self.footholds.access, "foothold access"),
            (
                &self.footholds.target_knowledge,
                "foothold target knowledge",
            ),
            (&self.footholds.infrastructure, "foothold infrastructure"),
            (&self.footholds.sustainment, "foothold sustainment"),
            (&self.footholds.updated_at, "foothold timestamp"),
            (
                &self.footholds.first_activated_at,
                "foothold first activation",
            ),
            (
                &self.footholds.last_activated_at,
                "foothold last activation",
            ),
            (
                &self.footholds.cumulative_active_days,
                "foothold active days",
            ),
            (&self.footholds.cumulative_arrivals, "foothold arrivals"),
            (&self.footholds.cumulative_recruits, "foothold recruits"),
            (&self.footholds.cumulative_actions, "foothold actions"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.footholds.strength, "foothold strength")?;
        check_nonnegative(&self.footholds.raw_signal, "foothold signal")?;
        check_nonnegative(
            &self.footholds.cumulative_active_days,
            "foothold active days",
        )?;
        check_nonnegative(&self.footholds.cumulative_arrivals, "foothold arrivals")?;
        check_nonnegative(&self.footholds.cumulative_recruits, "foothold recruits")?;
        check_nonnegative(&self.footholds.cumulative_actions, "foothold actions")?;
        for value in self
            .footholds
            .membership
            .iter()
            .chain(self.footholds.embeddedness.iter())
            .chain(self.footholds.access.iter())
            .chain(self.footholds.target_knowledge.iter())
            .chain(self.footholds.infrastructure.iter())
            .chain(self.footholds.sustainment.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for (values, name) in [
            (&self.beliefs.presence, "belief presence"),
            (&self.beliefs.control, "belief control"),
            (&self.beliefs.confidence, "belief confidence"),
            (&self.beliefs.updated_at, "belief timestamp"),
            (
                &self.beliefs.last_reliable_observation_at,
                "belief reliable timestamp",
            ),
            (&self.beliefs.contradiction, "belief contradiction"),
            (&self.beliefs.source_confidence, "belief source confidence"),
            (&self.logistics.source_stock, "source stock"),
            (&self.logistics.source_capacity, "source capacity"),
            (&self.logistics.source_production, "source production"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.logistics.source_stock, "source stock")?;
        check_nonnegative(&self.logistics.source_capacity, "source capacity")?;
        check_nonnegative(&self.logistics.source_production, "source production")?;
        for (value, name) in [
            (self.logistics.in_transit, "in-transit logistics"),
            (self.logistics.cumulative_produced, "produced logistics"),
            (self.logistics.cumulative_consumed, "consumed logistics"),
            (self.logistics.cumulative_lost, "lost logistics"),
            (self.logistics.cumulative_shipped, "shipped logistics"),
            (self.logistics.cumulative_delivered, "delivered logistics"),
            (self.counters.recruitment, "recruitment counter"),
            (self.counters.civilian_harm, "civilian harm counter"),
            (self.counters.deaths, "deaths counter"),
        ] {
            if !value.is_finite() {
                return Err(StateError::NonFinite(name));
            }
            if value < 0.0 {
                return Err(StateError::Corrupt(format!("{name} must be non-negative")));
            }
        }
        if self.weights_log.is_nan() {
            return Err(StateError::NonFinite("log weight"));
        }
        for record in &self.observations {
            if !record.time.is_finite()
                || !record.value.is_finite()
                || !record.confidence.is_finite()
            {
                return Err(StateError::NonFinite("observation record"));
            }
        }
        for record in &self.event_log {
            if !record.time.is_finite() || !record.value.is_finite() {
                return Err(StateError::NonFinite("event record"));
            }
        }
        for value in self
            .beliefs
            .presence
            .iter()
            .chain(self.beliefs.control.iter())
            .chain(self.beliefs.confidence.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        if self.rng.streams.values().any(|rng| {
            rng.state()
                .gauss_next
                .is_some_and(|value| !value.is_finite())
        }) {
            return Err(StateError::NonFinite("cached gaussian"));
        }
        for event in self.scheduler.events_sorted() {
            if !event.time.is_finite() {
                return Err(StateError::NonFinite("scheduled event time"));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum StateError {
    ParentOutOfBounds(usize),
    LengthMismatch {
        name: String,
        left: usize,
        right: usize,
    },
    NonFinite(&'static str),
    OutOfBounds(f64),
    Corrupt(String),
    Scheduler(SchedulerError),
}

impl fmt::Display for StateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ParentOutOfBounds(index) => {
                write!(formatter, "particle parent {index} is out of bounds")
            }
            Self::LengthMismatch { name, left, right } => {
                write!(formatter, "{name} length mismatch: {left} != {right}")
            }
            Self::NonFinite(name) => write!(formatter, "non-finite {name}"),
            Self::OutOfBounds(value) => write!(formatter, "state value {value} is outside [0, 1]"),
            Self::Corrupt(message) => write!(formatter, "corrupt state: {message}"),
            Self::Scheduler(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for StateError {}

impl From<SchedulerError> for StateError {
    fn from(value: SchedulerError) -> Self {
        Self::Scheduler(value)
    }
}

pub fn clamp01(value: f64) -> f64 {
    if value.is_nan() {
        0.0
    } else {
        value.clamp(0.0, 1.0)
    }
}

pub fn append_f64s(buffer: &mut Vec<u8>, values: &[f64]) {
    buffer.extend_from_slice(&(values.len() as u64).to_le_bytes());
    for value in values {
        buffer.extend_from_slice(&value.to_bits().to_le_bytes());
    }
}

pub fn append_u32s(buffer: &mut Vec<u8>, values: &[u32]) {
    buffer.extend_from_slice(&(values.len() as u64).to_le_bytes());
    for value in values {
        buffer.extend_from_slice(&value.to_le_bytes());
    }
}

pub fn append_u8s(buffer: &mut Vec<u8>, values: &[u8]) {
    buffer.extend_from_slice(&(values.len() as u64).to_le_bytes());
    buffer.extend_from_slice(values);
}

pub fn append_u64s(buffer: &mut Vec<u8>, values: &[u64]) {
    buffer.extend_from_slice(&(values.len() as u64).to_le_bytes());
    for value in values {
        buffer.extend_from_slice(&value.to_le_bytes());
    }
}

fn append_string(buffer: &mut Vec<u8>, value: &str) {
    buffer.extend_from_slice(&(value.len() as u64).to_le_bytes());
    buffer.extend_from_slice(value.as_bytes());
}

fn check_finite(values: &[f64], name: &'static str) -> Result<(), StateError> {
    if values.iter().any(|value| !value.is_finite()) {
        return Err(StateError::NonFinite(name));
    }
    Ok(())
}

fn check_nonnegative(values: &[f64], name: &'static str) -> Result<(), StateError> {
    if values.iter().any(|value| *value < 0.0) {
        return Err(StateError::Corrupt(format!("{name} must be non-negative")));
    }
    Ok(())
}

// Kept in this module so checkpoint code can use a single, explicit payload
// codec without serializing Rust object memory.
pub(crate) fn encode_event(buffer: &mut Vec<u8>, event: &ScheduledEvent) {
    buffer.extend_from_slice(&event.time.to_bits().to_le_bytes());
    buffer.extend_from_slice(&event.priority.to_le_bytes());
    buffer.extend_from_slice(&event.sequence.to_le_bytes());
    encode_payload(buffer, &event.payload);
}

pub(crate) fn decode_event(reader: &mut ByteReader<'_>) -> Result<ScheduledEvent, StateError> {
    let time = f64::from_bits(reader.u64()?);
    let priority = reader.u16()?;
    let sequence = reader.u64()?;
    let payload = decode_payload(reader)?;
    Ok(ScheduledEvent {
        time,
        priority,
        sequence,
        payload,
    })
}

fn encode_payload(buffer: &mut Vec<u8>, payload: &EventPayload) {
    buffer.extend_from_slice(&payload.code().to_le_bytes());
    match payload {
        EventPayload::Patrol { patrol } => buffer.extend_from_slice(&patrol.get().to_le_bytes()),
        EventPayload::OrganizedAction {
            organization,
            locality,
        } => {
            buffer.extend_from_slice(&organization.get().to_le_bytes());
            buffer.extend_from_slice(&locality.get().to_le_bytes());
        }
        EventPayload::Contact {
            first,
            second,
            locality,
            microzone,
        } => {
            buffer.extend_from_slice(&first.get().to_le_bytes());
            buffer.extend_from_slice(&second.get().to_le_bytes());
            buffer.extend_from_slice(&locality.get().to_le_bytes());
            buffer.extend_from_slice(&microzone.get().to_le_bytes());
        }
        EventPayload::Custom { value, .. } => buffer.extend_from_slice(&value.to_le_bytes()),
        _ => {}
    }
}

fn decode_payload(reader: &mut ByteReader<'_>) -> Result<EventPayload, StateError> {
    let code = reader.u16()?;
    Ok(match code {
        1 => EventPayload::Patrol {
            patrol: reader.u32()?.into(),
        },
        2 => EventPayload::ContactScan,
        3 => EventPayload::Command,
        4 => EventPayload::ForceMovement,
        5 => EventPayload::Logistics,
        6 => EventPayload::Information,
        7 => EventPayload::Beliefs,
        8 => EventPayload::PhysicalRefresh,
        9 => EventPayload::SocialInfluence,
        10 => EventPayload::Mobility,
        11 => EventPayload::Recruitment,
        12 => EventPayload::OrganizationEcology,
        13 => EventPayload::Governance,
        14 => EventPayload::Economy,
        15 => EventPayload::PoliticalOrder,
        16 => EventPayload::ForeignAffairs,
        17 => EventPayload::PeaceProcess,
        18 => EventPayload::RecordingNoise,
        19 => EventPayload::Checkpoint,
        20 => EventPayload::OrganizedAction {
            organization: reader.u32()?.into(),
            locality: reader.u32()?.into(),
        },
        21 => EventPayload::Contact {
            first: reader.u32()?.into(),
            second: reader.u32()?.into(),
            locality: reader.u32()?.into(),
            microzone: reader.u32()?.into(),
        },
        other => EventPayload::Custom {
            code: other,
            value: reader.u64()?,
        },
    })
}

#[allow(clippy::items_after_test_module)]
#[cfg(test)]
mod tests {
    use super::ParticleState;
    use crate::rng::RngStreams;

    #[test]
    fn gather_preserves_parent_lineage_and_forks_siblings() {
        let mut first = ParticleState::new(2, 2, 1, 1, 1, RngStreams::new(7, "test"));
        first.logical_id = 4;
        first.lineage = "root.4".to_string();
        let mut second = first.clone();
        second.logical_id = 9;
        second.lineage = "root.9".to_string();
        let children = ParticleState::gather(&[first, second], &[1, 1, 0]).unwrap();
        assert_eq!(children[0].lineage, "root.9.0");
        assert_eq!(children[1].lineage, "root.9.1");
        assert_eq!(children[2].lineage, "root.4.2");
        assert_ne!(children[0].rng, children[1].rng);
        assert_ne!(children[0].rng, children[2].rng);
        assert_eq!(children[0].ancestry.last(), Some(&9));
    }
}

pub(crate) struct ByteReader<'a> {
    bytes: &'a [u8],
    position: usize,
}

impl<'a> ByteReader<'a> {
    pub(crate) fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, position: 0 }
    }
    pub(crate) fn remaining(&self) -> usize {
        self.bytes.len().saturating_sub(self.position)
    }
    pub(crate) fn take(&mut self, count: usize) -> Result<&'a [u8], StateError> {
        let end = self
            .position
            .checked_add(count)
            .ok_or_else(|| StateError::Corrupt("length overflow".to_string()))?;
        if end > self.bytes.len() {
            return Err(StateError::Corrupt("truncated binary state".to_string()));
        }
        let result = &self.bytes[self.position..end];
        self.position = end;
        Ok(result)
    }
    pub(crate) fn u8(&mut self) -> Result<u8, StateError> {
        Ok(self.take(1)?[0])
    }
    pub(crate) fn u16(&mut self) -> Result<u16, StateError> {
        Ok(u16::from_le_bytes(self.take(2)?.try_into().unwrap()))
    }
    pub(crate) fn u32(&mut self) -> Result<u32, StateError> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()))
    }
    pub(crate) fn u64(&mut self) -> Result<u64, StateError> {
        Ok(u64::from_le_bytes(self.take(8)?.try_into().unwrap()))
    }
    pub(crate) fn f64(&mut self) -> Result<f64, StateError> {
        Ok(f64::from_bits(self.u64()?))
    }
    pub(crate) fn string(&mut self) -> Result<String, StateError> {
        let length = self.u64()? as usize;
        let bytes = self.take(length)?;
        String::from_utf8(bytes.to_vec())
            .map_err(|_| StateError::Corrupt("invalid UTF-8".to_string()))
    }
}
