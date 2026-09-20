//! Dense structure-of-arrays dynamic state.

use crate::rng::RngStreams;
use crate::scheduler::{EventPayload, ScheduledEvent, Scheduler, SchedulerError};
use crate::sha256;
use std::collections::BTreeMap;
use std::fmt;

pub const CONTROL_DIMENSIONS: usize = 7;
pub const INFORMATION_NONE: u32 = u32::MAX;

#[derive(Clone, Debug, Default, PartialEq)]
pub struct LocalityState {
    pub population: Vec<f64>,
    /// Mutable administrative-container population. Python keeps district
    /// population separate from the rounded locality allocation; direct
    /// civilian harm decrements both stocks.
    pub district_population: Vec<f64>,
    /// Python retains integer district populations until the first civilian
    /// harm update.  The type boundary affects Python 3.14's mixed int/float
    /// built-in sum path, so preserve it alongside the numeric value.
    pub district_population_is_integer: Vec<u8>,
    pub economic_output: Vec<f64>,
    pub infrastructure: Vec<f64>,
    pub administrative_capacity: Vec<f64>,
    pub terrain_friction: Vec<f64>,
    pub observability: Vec<f64>,
    pub government_control: Vec<f64>,
    pub insurgent_control: Vec<f64>,
    /// Organization-specific control vectors, stored locality-major then
    /// organization-major.  Python creates these rows lazily as franchise
    /// governance is observed; keeping them explicitly prevents the native
    /// aggregate insurgent view from becoming a lossy substitute.
    pub organization_control: Vec<f64>,
    pub violence: Vec<f64>,
    pub disruption: Vec<f64>,
    pub displaced_population: Vec<f64>,
    pub government_governance: Vec<f64>,
    pub insurgent_governance: Vec<f64>,
    /// Post-parity theory-core state: civilians currently in the domestic
    /// government security training pipeline, by locality.
    pub government_security_recruit_pipeline: Vec<f64>,
    /// Trained but currently unassigned domestic security personnel.
    pub government_security_reserve: Vec<f64>,
    /// Local state penetration of clandestine networks, in [0,1].  This is
    /// distinct from generic observability and actor belief confidence: it is
    /// a persistent institutional intelligence stock produced by policing,
    /// public cooperation, and administrative reach.
    pub government_intelligence_penetration: Vec<f64>,
    /// Causal-accounting diagnostics retained in state so theory experiments
    /// can distinguish recruitment, deployment, rebuilding, and underground
    /// disruption rather than inferring them from end states.
    pub government_cumulative_security_recruits: Vec<f64>,
    pub government_cumulative_security_deployments: Vec<f64>,
    pub government_cumulative_admin_rebuild: Vec<f64>,
    pub government_cumulative_underground_disruption: Vec<f64>,
}

impl LocalityState {
    pub fn new(count: usize) -> Self {
        Self {
            population: vec![0.0; count],
            district_population: vec![0.0; count],
            district_population_is_integer: vec![0; count],
            economic_output: vec![0.0; count],
            infrastructure: vec![0.0; count],
            administrative_capacity: vec![0.0; count],
            terrain_friction: vec![1.0; count],
            observability: vec![0.5; count],
            government_control: vec![0.0; count * CONTROL_DIMENSIONS],
            insurgent_control: vec![0.0; count * CONTROL_DIMENSIONS],
            organization_control: Vec::new(),
            violence: vec![0.0; count],
            disruption: vec![0.0; count],
            displaced_population: vec![0.0; count],
            government_governance: vec![0.0; count],
            insurgent_governance: vec![0.0; count],
            government_security_recruit_pipeline: vec![0.0; count],
            government_security_reserve: vec![0.0; count],
            government_intelligence_penetration: vec![0.0; count],
            government_cumulative_security_recruits: vec![0.0; count],
            government_cumulative_security_deployments: vec![0.0; count],
            government_cumulative_admin_rebuild: vec![0.0; count],
            government_cumulative_underground_disruption: vec![0.0; count],
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

    pub fn with_organizations(mut self, organization_count: usize) -> Self {
        self.organization_control = vec![
            0.0;
            self.population
                .len()
                .saturating_mul(organization_count)
                .saturating_mul(CONTROL_DIMENSIONS)
        ];
        self
    }

    pub fn ensure_organization_capacity(&mut self, organization_count: usize) {
        let locality_count = self.population.len();
        let expected = locality_count
            .saturating_mul(organization_count)
            .saturating_mul(CONTROL_DIMENSIONS);
        if self.organization_control.len() == expected {
            return;
        }
        let old_count = if locality_count == 0 {
            0
        } else {
            self.organization_control.len() / (locality_count * CONTROL_DIMENSIONS)
        };
        let mut replacement = vec![0.0; expected];
        let copied = old_count.min(organization_count);
        for locality in 0..locality_count {
            for organization in 0..copied {
                let old_offset = (locality * old_count + organization) * CONTROL_DIMENSIONS;
                let new_offset =
                    (locality * organization_count + organization) * CONTROL_DIMENSIONS;
                replacement[new_offset..new_offset + CONTROL_DIMENSIONS].copy_from_slice(
                    &self.organization_control[old_offset..old_offset + CONTROL_DIMENSIONS],
                );
            }
        }
        self.organization_control = replacement;
    }

    pub fn organization_control_offset(
        locality: usize,
        organization: usize,
        organization_count: usize,
    ) -> usize {
        (locality * organization_count + organization) * CONTROL_DIMENSIONS
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
    pub party_legitimacy: Vec<f64>,
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
    /// CPython's public-behavior enum encoded as a stable numeric code:
    /// neutral=0, insurgent_sympathy=1, armed_participation=2.
    pub public_behavior: Vec<u8>,
    /// Expected control for government and insurgent actors, two values per
    /// representative person.  This is distinct from the hidden locality
    /// control and from actor-held belief state.
    pub expected_control: Vec<f64>,
    /// Sparse-in-Python destination expectations represented as a dense
    /// person × locality × actor table in the native state.  The companion
    /// mask distinguishes an absent Python mapping entry from a legitimate
    /// zero-valued expectation.
    pub expected_destination_control: Vec<f64>,
    pub expected_destination_control_present: Vec<u8>,
    pub state_legitimacy: Vec<f64>,
    pub government_legitimacy: Vec<f64>,
    pub political_access: Vec<f64>,
    pub displaced: Vec<u8>,
    pub displacement_count: Vec<u32>,
    /// `-1` is the native sentinel for Python's `None` displacement time.
    pub displaced_since: Vec<f64>,
    /// `u32::MAX` is the native sentinel for Python's missing origin ID.
    pub displacement_origin: Vec<u32>,
    pub origin_tie_strength: Vec<f64>,
    /// Foreign-state membership; `u32::MAX` is Python's `None` sentinel.
    pub external_state: Vec<u32>,
    /// Python migration-status enum: resident=0, refuge=1,
    /// temporary_flight=2, economic_migration=3, returned=4.
    pub migration_status: Vec<u8>,
    /// Sparse affinity is dense at the native boundary because the initial
    /// registry has a fixed seven-organization codebook.  Later dynamic
    /// organizations can extend the row count without changing person order.
    pub insurgent_affinity: Vec<f64>,
    /// Persistent social exposure by organization, stored person-major then
    /// organization-major. This mirrors Python's `person.social_exposure`.
    pub social_exposure: Vec<f64>,
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
            party_legitimacy: vec![0.0; count * 3],
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
            public_behavior: vec![0; count],
            expected_control: vec![0.0; count * 2],
            expected_destination_control: Vec::new(),
            expected_destination_control_present: Vec::new(),
            state_legitimacy: vec![0.65; count],
            government_legitimacy: vec![0.55; count],
            political_access: vec![0.45; count],
            displaced: vec![0; count],
            displacement_count: vec![0; count],
            displaced_since: vec![-1.0; count],
            displacement_origin: vec![u32::MAX; count],
            origin_tie_strength: vec![1.0; count],
            external_state: vec![u32::MAX; count],
            migration_status: vec![0; count],
            insurgent_affinity: Vec::new(),
            social_exposure: Vec::new(),
        }
    }

    pub fn with_organizations(mut self, organization_count: usize) -> Self {
        self.insurgent_affinity = vec![0.0; self.locality.len() * organization_count];
        self.social_exposure = vec![0.0; self.locality.len() * organization_count];
        self
    }

    pub fn ensure_organization_capacity(&mut self, organization_count: usize) {
        let people_count = self.locality.len();
        let expected = people_count.saturating_mul(organization_count);
        if self.insurgent_affinity.len() != expected {
            let old_count = self
                .insurgent_affinity
                .len()
                .checked_div(people_count)
                .unwrap_or(0);
            let copied = old_count.min(organization_count);
            let mut replacement = vec![0.0; expected];
            for person in 0..people_count {
                let old_offset = person * old_count;
                let new_offset = person * organization_count;
                replacement[new_offset..new_offset + copied]
                    .copy_from_slice(&self.insurgent_affinity[old_offset..old_offset + copied]);
            }
            self.insurgent_affinity = replacement;
        }
        if self.social_exposure.len() != expected {
            let old_count = self
                .social_exposure
                .len()
                .checked_div(people_count)
                .unwrap_or(0);
            let copied = old_count.min(organization_count);
            let mut replacement = vec![0.0; expected];
            for person in 0..people_count {
                let old_offset = person * old_count;
                let new_offset = person * organization_count;
                replacement[new_offset..new_offset + copied]
                    .copy_from_slice(&self.social_exposure[old_offset..old_offset + copied]);
            }
            self.social_exposure = replacement;
        }
    }

    pub fn with_destination_localities(mut self, locality_count: usize) -> Self {
        self.expected_destination_control = vec![0.0; self.locality.len() * locality_count * 2];
        self.expected_destination_control_present = vec![0; self.locality.len() * locality_count];
        self
    }
}

/// Actor-owned access restrictions on locality corridors. Python stores this
/// as an insertion-ordered sparse map; the native vectors preserve one row
/// per live `(owner, unordered corridor)` key and therefore remain directly
/// serializable and deterministic.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct AccessRestrictionState {
    pub owner: Vec<u32>,
    pub first_locality: Vec<u32>,
    pub second_locality: Vec<u32>,
    pub level: Vec<f64>,
    pub cumulative_effort: Vec<f64>,
    pub updated_at: Vec<f64>,
}

impl AccessRestrictionState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn find(&self, owner: usize, first: usize, second: usize) -> Option<usize> {
        let (first, second) = if first <= second {
            (first as u32, second as u32)
        } else {
            (second as u32, first as u32)
        };
        self.owner
            .iter()
            .zip(&self.first_locality)
            .zip(&self.second_locality)
            .position(|((candidate_owner, candidate_first), candidate_second)| {
                *candidate_owner as usize == owner
                    && *candidate_first == first
                    && *candidate_second == second
            })
    }
}

/// Explicit household topology.  Person rows reference a household index;
/// offsets/indices preserve the Python insertion order without retaining
/// heap-allocated objects in the trajectory state.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct HouseholdState {
    pub locality: Vec<u32>,
    pub residence: Vec<u32>,
    pub resources: Vec<f64>,
    pub dependents: Vec<u32>,
    pub member_offsets: Vec<u32>,
    pub member_indices: Vec<u32>,
}

impl HouseholdState {
    pub fn new(count: usize) -> Self {
        Self {
            locality: vec![0; count],
            residence: vec![0; count],
            resources: vec![0.0; count],
            dependents: vec![0; count],
            member_offsets: vec![0; count + 1],
            member_indices: Vec::new(),
        }
    }
}

/// Explicit community membership and language profile state.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CommunityState {
    pub locality: Vec<u32>,
    pub cohesion: Vec<f64>,
    pub government_cooperation: Vec<f64>,
    pub insurgent_sympathy: Vec<f64>,
    pub language_profile: Vec<f64>,
    pub member_offsets: Vec<u32>,
    pub member_indices: Vec<u32>,
    pub bridge_offsets: Vec<u32>,
    pub bridge_members: Vec<u32>,
}

impl CommunityState {
    pub fn new(count: usize) -> Self {
        Self {
            locality: vec![0; count],
            cohesion: vec![0.0; count],
            government_cooperation: vec![0.0; count],
            insurgent_sympathy: vec![0.0; count],
            language_profile: vec![0.0; count * 4],
            member_offsets: vec![0; count + 1],
            member_indices: Vec::new(),
            bridge_offsets: vec![0; count + 1],
            bridge_members: Vec::new(),
        }
    }
}

/// Proto-organizations are latent, pre-formation organizational attempts.
/// Python retains them after a successful mobilization draw and advances the
/// same rows at each ecology tick until they collapse or mature.  Keeping the
/// founder membership and capital vectors here makes that latent state part of
/// the restart and cross-engine continuation contract rather than an
/// unobservable RNG shim.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ProtoState {
    pub community: Vec<u32>,
    pub locality: Vec<u32>,
    /// 1=mobilizing, 2=matured, 3=collapsed.
    pub status: Vec<u8>,
    pub member_offsets: Vec<u32>,
    pub member_indices: Vec<u32>,
    pub capital_social: Vec<f64>,
    pub capital_political: Vec<f64>,
    pub capital_organizational: Vec<f64>,
    pub capital_material: Vec<f64>,
    pub represented_membership: Vec<f64>,
    pub ideology_reform: Vec<f64>,
    pub ideology_separatism: Vec<f64>,
    pub leadership_potential: Vec<f64>,
    pub created_at: Vec<f64>,
}

impl ProtoState {
    pub fn new() -> Self {
        Self {
            member_offsets: vec![0],
            ..Self::default()
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn push(
        &mut self,
        community: u32,
        locality: u32,
        members: &[u32],
        capital: [f64; 4],
        represented_membership: f64,
        ideology: [f64; 2],
        leadership_potential: f64,
        created_at: f64,
    ) {
        self.community.push(community);
        self.locality.push(locality);
        self.status.push(1);
        self.member_indices.extend_from_slice(members);
        self.member_offsets.push(self.member_indices.len() as u32);
        self.capital_social.push(capital[0]);
        self.capital_political.push(capital[1]);
        self.capital_organizational.push(capital[2]);
        self.capital_material.push(capital[3]);
        self.represented_membership.push(represented_membership);
        self.ideology_reform.push(ideology[0]);
        self.ideology_separatism.push(ideology[1]);
        self.leadership_potential.push(leadership_potential);
        self.created_at.push(created_at);
    }

    pub fn count(&self) -> usize {
        self.community.len()
    }

    pub fn members(&self, proto: usize) -> &[u32] {
        let start = self.member_offsets[proto] as usize;
        let end = self.member_offsets[proto + 1] as usize;
        &self.member_indices[start..end]
    }
}

/// Social multiplex edge table. `layers` uses bits household=1,
/// community=2, bridge=4; this is lossless for the current Python schema
/// because layers are a sorted set on every edge.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct SocialEdgeState {
    pub person_a: Vec<u32>,
    pub person_b: Vec<u32>,
    pub layers: Vec<u8>,
    pub weight: Vec<f64>,
    pub language_compatibility: Vec<f64>,
    pub trust: Vec<f64>,
    pub represented_relationships: Vec<f64>,
    pub neighbor_offsets: Vec<u32>,
    pub neighbor_indices: Vec<u32>,
}

impl SocialEdgeState {
    pub fn new(people: usize) -> Self {
        Self {
            person_a: Vec::new(),
            person_b: Vec::new(),
            layers: Vec::new(),
            weight: Vec::new(),
            language_compatibility: Vec::new(),
            trust: Vec::new(),
            represented_relationships: Vec::new(),
            neighbor_offsets: vec![0; people + 1],
            neighbor_indices: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct ZoneBeliefKey {
    pub observer: u32,
    pub zone: u32,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct ZoneBeliefState {
    pub keys: Vec<ZoneBeliefKey>,
    pub estimate: Vec<f64>,
    pub confidence: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub last_reliable_observation_at: Vec<f64>,
    pub evidence_count: Vec<u32>,
    pub contradiction: Vec<f64>,
}

impl ZoneBeliefState {
    pub fn new(keys: Vec<ZoneBeliefKey>) -> Self {
        let count = keys.len();
        Self {
            keys,
            estimate: vec![0.0; count],
            confidence: vec![0.0; count],
            updated_at: vec![0.0; count],
            last_reliable_observation_at: vec![-1.0e9; count],
            evidence_count: vec![0; count],
            contradiction: vec![0.0; count],
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct LeaderState {
    pub organization: Vec<u32>,
    pub competence: Vec<f64>,
    pub charisma: Vec<f64>,
    pub risk_tolerance: Vec<f64>,
    pub ideological_rigidity: Vec<f64>,
    pub political_skill: Vec<f64>,
    pub organizational_skill: Vec<f64>,
    pub active: Vec<u8>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct CommandEdgeState {
    pub organization: Vec<u32>,
    pub formation: Vec<u32>,
    pub reliability: Vec<f64>,
    pub latency_hours: Vec<f64>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct ManpowerState {
    pub organization: Vec<u32>,
    pub locality: Vec<u32>,
    pub pool: Vec<f64>,
    pub supply_reserve: Vec<f64>,
}

/// Dense initialization/state representation of the political institutions,
/// party branches, and sampled elite anchors created by the Python generator.
/// The rows follow Python insertion order; set-valued memberships are stored
/// in canonical person/elite index order through the offset arrays.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct PoliticalState {
    pub institution_type: Vec<u8>,
    pub institution_level: Vec<u8>,
    pub institution_locality: Vec<u32>,
    pub institution_district: Vec<u32>,
    pub institution_capacity: Vec<f64>,
    pub institution_autonomy: Vec<f64>,
    pub institution_compliance: Vec<f64>,
    pub institution_reach: Vec<f64>,
    pub institution_integrity: Vec<f64>,
    pub institution_resources: Vec<f64>,
    pub institution_governing_party: Vec<u32>,
    pub branch_party: Vec<u32>,
    pub branch_locality: Vec<u32>,
    pub branch_resources: Vec<f64>,
    pub branch_patronage: Vec<f64>,
    pub branch_electoral_support: Vec<f64>,
    pub branch_institutional_influence: Vec<f64>,
    pub branch_member_offsets: Vec<u32>,
    pub branch_member_indices: Vec<u32>,
    pub branch_broker_offsets: Vec<u32>,
    pub branch_broker_indices: Vec<u32>,
    pub elite_person: Vec<u32>,
    pub elite_locality: Vec<u32>,
    pub elite_network_centrality: Vec<f64>,
    pub elite_resources: Vec<f64>,
    pub elite_legitimacy: Vec<f64>,
    pub elite_institutional_ties: Vec<f64>,
    pub elite_party_alignment: Vec<u32>,
    pub ruling_party: u32,
    pub private_diversion_stock: f64,
}

impl PoliticalState {
    pub fn new() -> Self {
        Self {
            branch_member_offsets: vec![0],
            branch_broker_offsets: vec![0],
            ruling_party: u32::MAX,
            ..Self::default()
        }
    }
}

/// Foreign-system initialization and mutable state.  The language profiles,
/// border rows, beliefs, and interpreter rows are explicit so the native
/// engine cannot silently replace a foreign channel with a scalar shortcut.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ForeignSystemState {
    pub resources: Vec<f64>,
    pub stability_preference: Vec<f64>,
    pub government_alignment: Vec<f64>,
    pub ideological_alignment: Vec<f64>,
    pub border_security_priority: Vec<f64>,
    pub regional_influence: Vec<f64>,
    pub commercial_interest: Vec<f64>,
    pub humanitarian_preference: Vec<f64>,
    pub cost_sensitivity: Vec<f64>,
    pub domestic_opposition: Vec<f64>,
    pub willingness: Vec<f64>,
    pub language_profile: Vec<f64>,
    pub opportunity: Vec<f64>,
    pub rival_offsets: Vec<u32>,
    pub rival_indices: Vec<u32>,
    pub cumulative_cost: Vec<f64>,
    pub cumulative_casualties: Vec<f64>,
    pub border_foreign_state: Vec<u32>,
    pub border_district: Vec<u32>,
    pub border_locality: Vec<u32>,
    pub border_terrain_friction: Vec<f64>,
    pub border_infrastructure: Vec<f64>,
    pub border_legal_permeability: Vec<f64>,
    pub border_social_permeability: Vec<f64>,
    pub border_language_overlap: Vec<f64>,
    pub border_kinship_overlap: Vec<f64>,
    pub border_state_monitoring: Vec<f64>,
    pub belief_foreign_state: Vec<u32>,
    pub belief_locality: Vec<u32>,
    pub belief_government_control: Vec<f64>,
    pub belief_insurgent_presence: Vec<f64>,
    pub belief_confidence: Vec<f64>,
    pub belief_updated_at: Vec<f64>,
    pub interpreter_person: Vec<u32>,
    pub interpreter_foreign_state: Vec<u32>,
    pub interpreter_locality: Vec<u32>,
    pub interpreter_foreign_language: Vec<f64>,
    pub interpreter_local_language: Vec<f64>,
    pub interpreter_foreign_trust: Vec<f64>,
    pub interpreter_local_trust: Vec<f64>,
    pub interpreter_cultural_knowledge: Vec<f64>,
    /// Diaspora links are kept as insertion-ordered parallel rows so a
    /// migration/resettlement cycle consumes exactly the same RNG positions
    /// as Python's ordered registry.
    pub diaspora_person: Vec<u32>,
    pub diaspora_foreign_state: Vec<u32>,
    pub diaspora_origin_locality: Vec<u32>,
    pub diaspora_social_strength: Vec<f64>,
    pub diaspora_financial_capacity: Vec<f64>,
    pub diaspora_information_reliability: Vec<f64>,
    pub diaspora_created_at: Vec<f64>,
    pub support_foreign_state: Vec<u32>,
    pub support_recipient: Vec<u32>,
    pub support_total: Vec<f64>,
    pub cumulative_external_remittances: f64,
}

impl ForeignSystemState {
    pub fn new() -> Self {
        Self {
            rival_offsets: vec![0],
            ..Self::default()
        }
    }
}

/// Runtime foreign-intervention rows.  Python creates these records lazily
/// when a neighbour deploys an expeditionary command, so they must travel
/// with the particle rather than being reconstructed from the current force
/// table during restart.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ForeignInterventionState {
    pub foreign_state: Vec<u32>,
    pub recipient: Vec<u32>,
    pub started_at: Vec<f64>,
    /// 0=capacity_building, 1=substitution.
    pub mode: Vec<u8>,
    pub provided_capacity: Vec<f64>,
    pub transfer_efficiency: Vec<f64>,
    pub crowding_out: Vec<f64>,
    pub force_formation: Vec<u32>,
    /// 1=active, 2=withdrawing, 3=withdrawn.
    pub status: Vec<u8>,
    pub withdrawal_rate: Vec<f64>,
    pub cumulative_transferred_capacity: Vec<f64>,
    pub cumulative_retained_host_capacity: Vec<f64>,
    pub cumulative_crowding_out: Vec<f64>,
    pub peak_provided_capacity: Vec<f64>,
    pub withdrawn_capacity: Vec<f64>,
}

impl ForeignInterventionState {
    pub fn count(&self) -> usize {
        self.foreign_state.len()
    }

    #[allow(clippy::too_many_arguments)]
    pub fn push(
        &mut self,
        foreign_state: u32,
        recipient: u32,
        started_at: f64,
        mode: u8,
        transfer_efficiency: f64,
        crowding_out: f64,
        force_formation: u32,
    ) {
        self.foreign_state.push(foreign_state);
        self.recipient.push(recipient);
        self.started_at.push(started_at);
        self.mode.push(mode);
        self.provided_capacity.push(0.0);
        self.transfer_efficiency.push(transfer_efficiency);
        self.crowding_out.push(crowding_out);
        self.force_formation.push(force_formation);
        self.status.push(1);
        self.withdrawal_rate.push(0.0);
        self.cumulative_transferred_capacity.push(0.0);
        self.cumulative_retained_host_capacity.push(0.0);
        self.cumulative_crowding_out.push(0.0);
        self.peak_provided_capacity.push(0.0);
        self.withdrawn_capacity.push(0.0);
    }
}

/// Organization-to-organization relation rows.  Status codes are stable:
/// allied=0, cooperative=1, neutral=2, rival=3, hostile=4, ceasefire=5.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct OrganizationRelationState {
    pub organization_a: Vec<u32>,
    pub organization_b: Vec<u32>,
    pub status: Vec<u8>,
    pub rivalry_memory: Vec<f64>,
    pub hostility_memory: Vec<f64>,
    pub cooperation_memory: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub last_interaction_at: Vec<f64>,
    pub has_last_interaction: Vec<u8>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PatrolState {
    pub formation: Vec<u32>,
    pub active: Vec<u8>,
    pub route_position: Vec<u32>,
    pub route_target: Vec<u32>,
    pub last_departure: Vec<f64>,
    pub next_available: Vec<f64>,
    /// Fraction of the parent formation deployed as the mobile patrol.
    /// Python keeps this separate from formation availability and uses it
    /// when integrating patrol presence memory.
    pub response_fraction: Vec<f64>,
    /// Calendar boundary through which patrol dwell has already been
    /// integrated. Python's None is represented by a finite negative
    /// sentinel so the state remains a compact numeric table.
    pub presence_accounted_at: Vec<f64>,
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
            response_fraction: vec![0.3; count],
            presence_accounted_at: vec![-1.0e300; count],
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
    /// Local professional standard of the post: training, procedural
    /// discipline, investigative competence, and institutional behavior.
    /// This is distinct from reliability (whether information is trusted)
    /// and from raw staffing/presence.  It lets a lightly institutionalized
    /// constabulary and a highly professional police unit have different
    /// effects at equal headcount.
    pub professionalism: Vec<f64>,
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
            professionalism: vec![0.5; count],
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
    pub capital_social: Vec<f64>,
    pub capital_political: Vec<f64>,
    pub capital_organizational: Vec<f64>,
    pub capital_material: Vec<f64>,
    /// Eight phenotype dimensions in the Python dictionary insertion order:
    /// centralization, political investment, governance investment,
    /// dispersion, risk tolerance, discipline, local embeddedness, resource
    /// dependence.
    pub phenotype: Vec<f64>,
    /// Two ideology dimensions: reform and separatism.
    pub ideology: Vec<f64>,
    pub external_sanctuary: Vec<f64>,
    pub adaptation_rate: Vec<f64>,
    pub leader: Vec<u32>,
}

impl OrganizationState {
    pub fn new(count: usize) -> Self {
        let mut ideology = vec![0.0; count * 2];
        for organization in 0..count {
            // Python Organization defaults to a neutral reform prior and no
            // separatist prior. The insurgent ecology initializer overwrites
            // its row later; keeping this default here also covers inactive
            // or non-insurgent organizations in exact initialization hashes.
            ideology[organization * 2] = 0.5;
        }
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
            capital_social: vec![0.0; count],
            capital_political: vec![0.0; count],
            capital_organizational: vec![0.0; count],
            capital_material: vec![0.0; count],
            phenotype: vec![0.5; count * 8],
            ideology,
            external_sanctuary: vec![0.0; count],
            adaptation_rate: vec![0.12; count],
            leader: vec![u32::MAX; count],
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
    /// Accumulated formation-level field experience/veterancy.  Quality is
    /// the unit's training/equipment/tactical standard; experience is a
    /// persistent learning stock acquired through service and combat and
    /// diluted when inexperienced replacements enter the formation.
    pub experience: Vec<f64>,
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
    /// The Python reference keeps movement orders as an archive plus an
    /// active-order index.  Native v1 stores the live order fields alongside
    /// each formation; completed/failed status is retained so the order
    /// sequence remains restartable without carrying a second object graph.
    pub movement_destination: Vec<u32>,
    pub movement_origin: Vec<u32>,
    pub movement_execute_at: Vec<f64>,
    pub movement_arrives_at: Vec<f64>,
    pub movement_travel_hours: Vec<f64>,
    pub movement_distance_km: Vec<f64>,
    pub movement_supply_cost: Vec<f64>,
    pub movement_order_sequence: Vec<u64>,
    pub movement_status: Vec<u8>,
    pub movement_purpose: Vec<u8>,
    /// Foreign-state membership; `u32::MAX` is Python's `None` sentinel.
    pub external_state: Vec<u32>,
}

impl FormationState {
    pub fn new(count: usize) -> Self {
        Self {
            organization: vec![0; count],
            locality: vec![0; count],
            microzone: vec![0; count],
            personnel: vec![0.0; count],
            quality: vec![0.5; count],
            experience: vec![0.5; count],
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
            movement_destination: vec![u32::MAX; count],
            movement_origin: vec![u32::MAX; count],
            movement_execute_at: vec![0.0; count],
            movement_arrives_at: vec![-1.0; count],
            movement_travel_hours: vec![0.0; count],
            movement_distance_km: vec![0.0; count],
            movement_supply_cost: vec![0.0; count],
            movement_order_sequence: vec![0; count],
            movement_status: vec![0; count],
            movement_purpose: vec![0; count],
            external_state: vec![u32::MAX; count],
        }
    }

    pub fn supply_fraction(&self, formation: usize) -> f64 {
        if self.supply_capacity[formation] > 0.0 {
            clamp01(self.supply_stock[formation] / self.supply_capacity[formation])
        } else {
            clamp01(self.sustainment[formation])
        }
    }

    pub fn fatigue_adjusted_readiness(&self, formation: usize) -> f64 {
        clamp01(self.readiness[formation] * (1.0 - 0.65 * clamp01(self.fatigue[formation])))
    }

    // Python's ArmedFormation.effective_readiness. Availability is a
    // deployment quantity and is deliberately applied by
    // available_personnel rather than a second time here.
    pub fn effective_readiness(&self, formation: usize) -> f64 {
        let supply_effect = 0.2 + 0.8 * self.supply_fraction(formation);
        clamp01(
            self.fatigue_adjusted_readiness(formation)
                * supply_effect
                * clamp01(self.command[formation]),
        )
    }

    pub fn deployable_personnel(&self, formation: usize) -> f64 {
        if self.moving[formation] != 0
            || self.outside_pineland[formation] != 0
            || self.operational_status[formation] == 0
        {
            return 0.0;
        }
        self.personnel[formation].max(0.0) * clamp01(self.availability[formation])
    }

    pub fn available_personnel(&self, formation: usize) -> f64 {
        self.deployable_personnel(formation) * self.effective_readiness(formation)
    }

    pub fn effective_strength(&self, formation: usize) -> f64 {
        let available = self.available_personnel(formation);
        if available <= 0.0 {
            0.0
        } else {
            available
                * self.quality[formation]
                * self.cohesion[formation]
                * (0.5 + self.information[formation])
        }
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

/// A scalar presence estimate held by an organization or one of its field
/// nodes.  Presence is deliberately separate from the seven-dimensional
/// control belief table: a negative detection is valid evidence of absence,
/// and formation/microzone-specific rows must not overwrite an actor-level
/// control estimate.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct PresenceKey {
    pub observer: u32,
    pub target: u32,
    pub locality: u32,
    pub microzone: u32,
    pub target_formation: u32,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct PresenceState {
    pub keys: Vec<PresenceKey>,
    pub estimate: Vec<f64>,
    pub personnel: Vec<f64>,
    pub confidence: Vec<f64>,
    pub updated_at: Vec<f64>,
    pub last_reliable_observation_at: Vec<f64>,
    pub contradiction: Vec<f64>,
    pub violence: Vec<f64>,
    pub evidence_count: Vec<u32>,
}

impl PresenceState {
    pub fn with_keys(keys: Vec<PresenceKey>) -> Self {
        let count = keys.len();
        Self {
            keys,
            estimate: vec![0.0; count],
            personnel: vec![0.0; count],
            confidence: vec![0.0; count],
            updated_at: vec![0.0; count],
            last_reliable_observation_at: vec![-1.0e9; count],
            contradiction: vec![0.0; count],
            violence: vec![0.2; count],
            evidence_count: vec![0; count],
        }
    }

    pub fn ensure_key(&mut self, key: PresenceKey) -> usize {
        match self.keys.binary_search(&key) {
            Ok(index) => index,
            Err(index) => {
                self.keys.insert(index, key);
                self.estimate.insert(index, 0.0);
                self.personnel.insert(index, 0.0);
                self.confidence.insert(index, 0.0);
                self.updated_at.insert(index, 0.0);
                self.last_reliable_observation_at.insert(index, -1.0e9);
                self.contradiction.insert(index, 0.0);
                self.violence.insert(index, 0.2);
                self.evidence_count.insert(index, 0);
                index
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn fuse(
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
        let old = self.estimate[index];
        let observed = clamp01(presence);
        let contradiction = self.contradiction[index]
            * crate::rng::python_exp(
                -(time - self.updated_at[index]).max(0.0) / memory_days.max(f64::MIN_POSITIVE),
            )
            + weight * (observed - old).abs();
        self.estimate[index] = clamp01((prior * old + weight * observed) / denominator);
        self.personnel[index] =
            (self.personnel[index] * prior + personnel.max(0.0) * weight) / denominator;
        self.confidence[index] = clamp01(
            (prior + weight) / (1.0 + prior + weight)
                * crate::rng::python_exp(-penalty * contradiction),
        );
        self.contradiction[index] = contradiction;
        self.updated_at[index] = time;
        if weight >= 0.12 {
            self.last_reliable_observation_at[index] = time;
        }
        self.evidence_count[index] = self.evidence_count[index].saturating_add(1);
    }

    pub fn fuse_violence(&mut self, index: usize, weight: f64, violence: f64) {
        if index >= self.keys.len() {
            return;
        }
        let prior = self.confidence[index].max(0.02);
        self.violence[index] =
            clamp01((prior * self.violence[index] + weight * clamp01(violence)) / (prior + weight));
    }

    pub fn decay_confidence(&mut self, default_factor: f64, formation_factor: f64) {
        for (index, key) in self.keys.iter().enumerate() {
            let factor = if key.target_formation != INFORMATION_NONE {
                formation_factor
            } else {
                default_factor
            };
            self.confidence[index] = clamp01(self.confidence[index] * factor);
        }
    }
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
        // Fixed rows are created in the Python compatibility order. Dynamic
        // information nodes are appended after those rows, but their native
        // observer codes must be sorted before hashing because Python's
        // control-belief dictionary is canonicalized by numeric node code.
        // Keep the insertion policy here so every producer (patrol,
        // background information, and future relays) shares one boundary.
        let index = if key.kind == 3 {
            let dynamic_start = self
                .keys
                .iter()
                .position(|existing| existing.kind == 3)
                .unwrap_or(self.keys.len());
            dynamic_start + self.keys[dynamic_start..].partition_point(|existing| existing < &key)
        } else {
            self.keys.len()
        };
        self.keys.insert(index, key);
        self.presence.insert(index, 0.0);
        self.control.splice(
            index * CONTROL_DIMENSIONS..index * CONTROL_DIMENSIONS,
            std::iter::repeat_n(0.0, CONTROL_DIMENSIONS),
        );
        self.confidence.insert(index, 0.0);
        self.updated_at.insert(index, 0.0);
        self.last_reliable_observation_at.insert(index, -1.0e9);
        self.contradiction.insert(index, 0.0);
        self.source_confidence.insert(index, 0.0);
        self.evidence_count.insert(index, 0);
        for dirty in &mut self.dirty {
            if *dirty as usize >= index {
                *dirty += 1;
            }
        }
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
        let decay = crate::rng::python_exp(-age / memory_days.max(f64::MIN_POSITIVE));
        let target_belief_trace = crate::trace_env!("PINELAND_TARGET_BELIEF_TRACE")
            && ((self.keys[index].observer == 31
                && self.keys[index].target == 6
                && self.keys[index].locality == 31
                && self.keys[index].kind == 3)
                || (self.keys[index].observer == 19
                    && self.keys[index].target == 6
                    && self.keys[index].locality == 0
                    && self.keys[index].kind == 3));
        if target_belief_trace {
            eprintln!(
                "TARGET_BELIEF_PRE time={:.17} key=({}, {}, {}, {}) weight={:.17} observed={:?} prior_conf={:.17} prior_updated={:.17} prior_contra={:.17}",
                time,
                self.keys[index].observer,
                self.keys[index].target,
                self.keys[index].locality,
                self.keys[index].kind,
                weight,
                observed,
                self.confidence[index],
                self.updated_at[index],
                self.contradiction[index],
            );
        }
        let offset = index * CONTROL_DIMENSIONS;
        let mut contradiction = self.contradiction[index];
        let mut confidence = prior_confidence;
        for (dimension, observed_value) in observed.iter().enumerate() {
            let value = clamp01(*observed_value);
            let old = self.control[offset + dimension];
            self.control[offset + dimension] =
                clamp01((prior * old + weight * value) / denominator);
            // Python's scalar compatibility path decays the running
            // contradiction before each control dimension, not once for the
            // complete vector. Preserve that order because positive-time
            // confidence depends on it.
            contradiction = contradiction * decay + weight * (value - old).abs();
            confidence = clamp01(scale * crate::rng::python_exp(-penalty * contradiction));
        }
        self.confidence[index] = confidence;
        self.updated_at[index] = time;
        if weight >= 0.12 {
            self.last_reliable_observation_at[index] = time;
        }
        self.evidence_count[index] = self.evidence_count[index].saturating_add(1);
        self.contradiction[index] = contradiction;
        if target_belief_trace {
            eprintln!(
                "TARGET_BELIEF_POST time={:.17} key=({}, {}, {}, {}) confidence={:.17} updated={:.17} contra={:.17} evidence={}",
                time,
                self.keys[index].observer,
                self.keys[index].target,
                self.keys[index].locality,
                self.keys[index].kind,
                self.confidence[index],
                self.updated_at[index],
                self.contradiction[index],
                self.evidence_count[index],
            );
        }
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
        let mut contradiction = self.contradiction[index]
            * crate::rng::python_exp(-age / memory_days.max(f64::MIN_POSITIVE));
        contradiction += weight * (clamp01(presence) - old).abs();
        self.presence[index] = clamp01((prior * old + weight * clamp01(presence)) / denominator);
        self.source_confidence[index] =
            (self.source_confidence[index] * prior + weight * personnel.max(0.0)) / denominator;
        self.confidence[index] = clamp01(
            (prior + weight) / (1.0 + prior + weight)
                * crate::rng::python_exp(-penalty * contradiction),
        );
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
    /// Historical supply-shipment rows.  Status 0 is in transit and status 1
    /// is delivered; retaining completed rows preserves the Python audit
    /// boundary while the active subset is selected by status.
    pub shipment_source: Vec<u32>,
    pub shipment_formation: Vec<u32>,
    pub shipment_origin_locality: Vec<u32>,
    pub shipment_destination_locality: Vec<u32>,
    pub shipment_route_offsets: Vec<u32>,
    pub shipment_route_nodes: Vec<u32>,
    pub shipment_departed_at: Vec<f64>,
    pub shipment_arrives_at: Vec<f64>,
    pub shipment_quantity_sent: Vec<f64>,
    pub shipment_quantity_deliverable: Vec<f64>,
    pub shipment_loss: Vec<f64>,
    pub shipment_status: Vec<u8>,
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
            shipment_route_offsets: vec![0],
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

/// Fixed-width observation payload retained while a command-network relay is
/// in flight.  The native engine keeps the reported value, never the hidden
/// truth used to generate it, so a restart can continue the same stochastic
/// information path without reconstructing Python objects.
#[derive(Clone, Debug, PartialEq)]
pub struct InformationObservation {
    pub sequence: u64,
    pub observer: u32,
    pub observer_node: u32,
    pub source: u32,
    pub source_identity: u32,
    pub source_community: u32,
    pub source_formation: u32,
    pub source_type: u8,
    pub observation_type: u8,
    pub target: u32,
    pub target_formation: u32,
    pub locality: u32,
    pub microzone: u32,
    pub time: f64,
    pub quality: f64,
    pub confidence: f64,
    pub decay_rate: f64,
    pub control: [f64; CONTROL_DIMENSIONS],
    pub violence: f64,
    pub presence: f64,
    pub personnel: f64,
    pub detection_probability: f64,
    pub detected: u8,
    /// Engagement-outcome reports carry a noisy momentum signal and a noisy
    /// civilian-harm estimate.  They are deliberately separate from the
    /// presence/control payload because the Python reference does not fuse
    /// this observation type into either belief table.
    pub reported_momentum: f64,
    pub reported_civilian_harm: f64,
    pub attributed_actor: u32,
}

impl InformationObservation {
    pub fn new(sequence: u64) -> Self {
        Self {
            sequence,
            observer: INFORMATION_NONE,
            observer_node: INFORMATION_NONE,
            source: INFORMATION_NONE,
            source_identity: INFORMATION_NONE,
            source_community: INFORMATION_NONE,
            source_formation: INFORMATION_NONE,
            source_type: 0,
            observation_type: 0,
            target: INFORMATION_NONE,
            target_formation: INFORMATION_NONE,
            locality: INFORMATION_NONE,
            microzone: INFORMATION_NONE,
            time: 0.0,
            quality: 0.0,
            confidence: 0.0,
            decay_rate: 0.0,
            control: [0.0; CONTROL_DIMENSIONS],
            violence: 0.0,
            presence: 0.0,
            personnel: 0.0,
            detection_probability: 0.0,
            detected: 0,
            reported_momentum: 0.0,
            reported_civilian_harm: 0.0,
            attributed_actor: INFORMATION_NONE,
        }
    }
}

/// A command-network transmission.  `status` is 0 for in-transit, 1 for
/// delivered, and 2 for dropped. `delivered_at` uses a negative sentinel for
/// Python's None.
#[derive(Clone, Debug, PartialEq)]
pub struct InformationRelay {
    pub sequence: u64,
    pub observation: u64,
    pub organization: u32,
    pub source_node: u32,
    pub destination_node: u32,
    pub route: Vec<u32>,
    pub sent_at: f64,
    pub arrives_at: f64,
    pub reliability: f64,
    pub latency_hours: f64,
    pub status: u8,
    pub delivered_at: f64,
}

/// Bounded source history used by the three-day corroboration operator.
#[derive(Clone, Debug, PartialEq)]
pub struct InformationHistoryEntry {
    pub target: u32,
    pub locality: u32,
    pub observation_type: u8,
    pub time: f64,
    pub source_identity: u32,
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

/// External partner air support ledger.
#[derive(Clone, Debug, PartialEq)]
pub struct AirSupportLedger {
    pub opportunities: u64,
    pub assisted_contacts: u64,
    pub cumulative_intensity: f64,
    pub cumulative_firepower_bonus: f64,
    pub cumulative_donor_cost: f64,
}

impl Default for AirSupportLedger {
    fn default() -> Self {
        Self {
            opportunities: 0,
            assisted_contacts: 0,
            cumulative_intensity: 0.0,
            cumulative_firepower_bonus: 0.0,
            cumulative_donor_cost: 0.0,
        }
    }
}

/// External partner logistics support ledger.
#[derive(Clone, Debug, PartialEq)]
pub struct LogisticsSupportLedger {
    /// Government/military logistics generated by Pineland's endogenous
    /// logistics system. These counters are instrumentation, not assistance.
    pub indigenous_cumulative_produced: f64,
    pub indigenous_cumulative_delivered: f64,
    pub indigenous_cumulative_consumed: f64,
    /// Total military supply requirement presented to the logistics system, including unmet demand.
    pub military_cumulative_demanded: f64,
    pub cumulative_offered: f64,
    pub cumulative_delivered: f64,
    pub cumulative_rejected: f64,
    pub cumulative_lost: f64,
    pub cumulative_donor_cost: f64,
}

impl Default for LogisticsSupportLedger {
    fn default() -> Self {
        Self {
            indigenous_cumulative_produced: 0.0,
            indigenous_cumulative_delivered: 0.0,
            indigenous_cumulative_consumed: 0.0,
            military_cumulative_demanded: 0.0,
            cumulative_offered: 0.0,
            cumulative_delivered: 0.0,
            cumulative_rejected: 0.0,
            cumulative_lost: 0.0,
            cumulative_donor_cost: 0.0,
        }
    }
}

/// External partner command/advisory support ledger.
#[derive(Clone, Debug, PartialEq)]
pub struct CommandSupportLedger {
    /// Military movement-order opportunities, whether or not assistance is enabled.
    pub opportunities: u64,
    pub assisted_events: u64,
    /// Organic timely-success service: reliability * exp(-latency_hours / 24).
    pub cumulative_indigenous_service: f64,
    /// Same command service after any partner advisory overlay.
    pub cumulative_supported_service: f64,
    pub cumulative_reliability_boost: f64,
    pub cumulative_latency_reduction_hours: f64,
    pub cumulative_donor_cost: f64,
}

impl Default for CommandSupportLedger {
    fn default() -> Self {
        Self {
            opportunities: 0,
            assisted_events: 0,
            cumulative_indigenous_service: 0.0,
            cumulative_supported_service: 0.0,
            cumulative_reliability_boost: 0.0,
            cumulative_latency_reduction_hours: 0.0,
            cumulative_donor_cost: 0.0,
        }
    }
}

/// External partner force-generation support ledger.
#[derive(Clone, Debug, PartialEq)]
pub struct ForceGenSupportLedger {
    pub indigenous_recruits: f64,
    pub external_recruits: f64,
    pub indigenous_graduates: f64,
    pub external_incremental_graduates: f64,
    pub cumulative_donor_cost: f64,
}

impl Default for ForceGenSupportLedger {
    fn default() -> Self {
        Self {
            indigenous_recruits: 0.0,
            external_recruits: 0.0,
            indigenous_graduates: 0.0,
            external_incremental_graduates: 0.0,
            cumulative_donor_cost: 0.0,
        }
    }
}

/// Window snapshot for partner support flows across observation windows.
#[derive(Clone, Debug, PartialEq)]
pub struct SupportWindowSnapshot {
    pub time_days: f64,
    pub air_intensity: f64,
    pub air_donor_cost: f64,
    pub logistics_delivered: f64,
    pub logistics_donor_cost: f64,
    pub command_assisted_events: u64,
    pub command_donor_cost: f64,
    pub forcegen_incremental_graduates: f64,
    pub forcegen_donor_cost: f64,
    pub total_donor_cost: f64,
}

/// First-class external partner-support provenance and cost ledger.
///
/// Schema version: pineland.partner_force_support_ledger.v1
#[derive(Clone, Debug, PartialEq)]
pub struct PartnerSupportLedger {
    pub schema_version: String,
    pub support_withdrawn: bool,
    pub withdrawal_time: Option<f64>,
    pub air: AirSupportLedger,
    pub logistics: LogisticsSupportLedger,
    pub command: CommandSupportLedger,
    pub force_generation: ForceGenSupportLedger,
    pub window_snapshots: Vec<SupportWindowSnapshot>,
}

impl Default for PartnerSupportLedger {
    fn default() -> Self {
        Self {
            schema_version: "pineland.partner_force_support_ledger.v1".to_string(),
            support_withdrawn: false,
            withdrawal_time: None,
            air: AirSupportLedger::default(),
            logistics: LogisticsSupportLedger::default(),
            command: CommandSupportLedger::default(),
            force_generation: ForceGenSupportLedger::default(),
            window_snapshots: Vec::new(),
        }
    }
}

impl PartnerSupportLedger {
    pub fn cumulative_donor_cost(&self) -> f64 {
        self.air.cumulative_donor_cost
            + self.logistics.cumulative_donor_cost
            + self.command.cumulative_donor_cost
            + self.force_generation.cumulative_donor_cost
    }

    pub fn take_snapshot(&mut self, time_days: f64) {
        let total_cost = self.cumulative_donor_cost();
        self.window_snapshots.push(SupportWindowSnapshot {
            time_days,
            air_intensity: self.air.cumulative_intensity,
            air_donor_cost: self.air.cumulative_donor_cost,
            logistics_delivered: self.logistics.cumulative_delivered,
            logistics_donor_cost: self.logistics.cumulative_donor_cost,
            command_assisted_events: self.command.assisted_events,
            command_donor_cost: self.command.cumulative_donor_cost,
            forcegen_incremental_graduates: self.force_generation.external_incremental_graduates,
            forcegen_donor_cost: self.force_generation.cumulative_donor_cost,
            total_donor_cost: total_cost,
        });
    }

    pub fn discounted_donor_cost(&self, discount_rate_annual: f64) -> f64 {
        if discount_rate_annual <= 0.0 || self.window_snapshots.is_empty() {
            return self.cumulative_donor_cost();
        }
        let daily_discount = discount_rate_annual / 365.0;
        let mut discounted = 0.0;
        let mut prev_cost = 0.0;
        for snap in &self.window_snapshots {
            let incremental_cost = (snap.total_donor_cost - prev_cost).max(0.0);
            let discount_factor = (-daily_discount * snap.time_days).exp();
            discounted += incremental_cost * discount_factor;
            prev_cost = snap.total_donor_cost;
        }
        let remaining = (self.cumulative_donor_cost() - prev_cost).max(0.0);
        if remaining > 0.0 {
            let last_time = self
                .window_snapshots
                .last()
                .map(|s| s.time_days)
                .unwrap_or(0.0);
            discounted += remaining * (-daily_discount * last_time).exp();
        }
        discounted
    }

    /// External logistics share: external / (indigenous + external).
    /// This is exposure, not structural dependence.
    pub fn external_share_logistics(&self) -> f64 {
        let total =
            self.logistics.indigenous_cumulative_delivered + self.logistics.cumulative_delivered;
        if total > 1e-9 {
            (self.logistics.cumulative_delivered / total).clamp(0.0, 1.0)
        } else {
            0.0
        }
    }

    /// External force-generation share: external / (indigenous + external).
    /// This is exposure, not structural dependence.
    pub fn external_share_forcegen(&self) -> f64 {
        let total = self.force_generation.indigenous_graduates
            + self.force_generation.external_incremental_graduates;
        if total > 1e-9 {
            (self.force_generation.external_incremental_graduates / total).clamp(0.0, 1.0)
        } else {
            0.0
        }
    }

    /// External share of command-service equivalents. This is exposure, not
    /// structural dependence; dependence additionally requires service demand.
    pub fn external_share_command(&self) -> f64 {
        let external = (self.command.cumulative_supported_service
            - self.command.cumulative_indigenous_service)
            .max(0.0);
        if self.command.cumulative_supported_service > 1e-9 {
            (external / self.command.cumulative_supported_service).clamp(0.0, 1.0)
        } else {
            0.0
        }
    }

    /// External air-assistance share among military contact opportunities.
    /// This is exposure, not structural dependence.
    pub fn external_share_air(&self, total_military_contacts: u64) -> f64 {
        let total = total_military_contacts.max(self.air.assisted_contacts);
        if total > 0 {
            (self.air.assisted_contacts as f64 / total as f64).clamp(0.0, 1.0)
        } else {
            0.0
        }
    }

    /// Operational manpower burden ratio: replacement demand / organic replacement capacity.
    pub fn manpower_burden(window_losses: f64, window_graduates: f64) -> f64 {
        window_losses / (window_graduates + 1e-6)
    }

    /// Operational logistics burden ratio: presented military requirement /
    /// endogenous logistics service delivered to military formations.
    pub fn logistics_burden(window_demanded: f64, window_indigenous_delivered: f64) -> f64 {
        window_demanded / (window_indigenous_delivered + 1e-6)
    }

    /// Flow-based regenerative coordinate: 1 / (burden + epsilon).
    pub fn omega_flow(burden: f64) -> f64 {
        1.0 / (burden + 1e-6)
    }

    pub fn to_json(&self) -> crate::json::JsonValue {
        use crate::json::JsonValue;
        let mut root = JsonValue::object();
        root.insert("schema_version", JsonValue::string(&self.schema_version));
        root.insert("support_withdrawn", JsonValue::Bool(self.support_withdrawn));
        if let Some(t) = self.withdrawal_time {
            root.insert("withdrawal_time", JsonValue::number(t));
        }

        let mut air = JsonValue::object();
        air.insert(
            "opportunities",
            JsonValue::number(self.air.opportunities as f64),
        );
        air.insert(
            "assisted_contacts",
            JsonValue::number(self.air.assisted_contacts as f64),
        );
        air.insert(
            "cumulative_intensity",
            JsonValue::number(self.air.cumulative_intensity),
        );
        air.insert(
            "cumulative_firepower_bonus",
            JsonValue::number(self.air.cumulative_firepower_bonus),
        );
        air.insert(
            "cumulative_donor_cost",
            JsonValue::number(self.air.cumulative_donor_cost),
        );
        root.insert("air", air);

        let mut logistics = JsonValue::object();
        logistics.insert(
            "indigenous_cumulative_produced",
            JsonValue::number(self.logistics.indigenous_cumulative_produced),
        );
        logistics.insert(
            "indigenous_cumulative_delivered",
            JsonValue::number(self.logistics.indigenous_cumulative_delivered),
        );
        logistics.insert(
            "indigenous_cumulative_consumed",
            JsonValue::number(self.logistics.indigenous_cumulative_consumed),
        );
        logistics.insert(
            "military_cumulative_demanded",
            JsonValue::number(self.logistics.military_cumulative_demanded),
        );
        logistics.insert(
            "cumulative_offered",
            JsonValue::number(self.logistics.cumulative_offered),
        );
        logistics.insert(
            "cumulative_delivered",
            JsonValue::number(self.logistics.cumulative_delivered),
        );
        logistics.insert(
            "cumulative_rejected",
            JsonValue::number(self.logistics.cumulative_rejected),
        );
        logistics.insert(
            "cumulative_lost",
            JsonValue::number(self.logistics.cumulative_lost),
        );
        logistics.insert(
            "cumulative_donor_cost",
            JsonValue::number(self.logistics.cumulative_donor_cost),
        );
        root.insert("logistics", logistics);

        let mut command = JsonValue::object();
        command.insert(
            "opportunities",
            JsonValue::number(self.command.opportunities as f64),
        );
        command.insert(
            "assisted_events",
            JsonValue::number(self.command.assisted_events as f64),
        );
        command.insert(
            "cumulative_indigenous_service",
            JsonValue::number(self.command.cumulative_indigenous_service),
        );
        command.insert(
            "cumulative_supported_service",
            JsonValue::number(self.command.cumulative_supported_service),
        );
        command.insert(
            "cumulative_reliability_boost",
            JsonValue::number(self.command.cumulative_reliability_boost),
        );
        command.insert(
            "cumulative_latency_reduction_hours",
            JsonValue::number(self.command.cumulative_latency_reduction_hours),
        );
        command.insert(
            "cumulative_donor_cost",
            JsonValue::number(self.command.cumulative_donor_cost),
        );
        root.insert("command", command);

        let mut forcegen = JsonValue::object();
        forcegen.insert(
            "indigenous_recruits",
            JsonValue::number(self.force_generation.indigenous_recruits),
        );
        forcegen.insert(
            "external_recruits",
            JsonValue::number(self.force_generation.external_recruits),
        );
        forcegen.insert(
            "indigenous_graduates",
            JsonValue::number(self.force_generation.indigenous_graduates),
        );
        forcegen.insert(
            "external_incremental_graduates",
            JsonValue::number(self.force_generation.external_incremental_graduates),
        );
        forcegen.insert(
            "cumulative_donor_cost",
            JsonValue::number(self.force_generation.cumulative_donor_cost),
        );
        root.insert("force_generation", forcegen);

        root.insert(
            "cumulative_donor_cost",
            JsonValue::number(self.cumulative_donor_cost()),
        );
        root
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ParticleState {
    pub logical_id: u64,
    pub lineage: String,
    pub time: f64,
    pub locality: LocalityState,
    pub zones: ZoneState,
    pub people: PersonState,
    pub households: HouseholdState,
    pub communities: CommunityState,
    pub protos: ProtoState,
    pub social_edges: SocialEdgeState,
    pub organizations: OrganizationState,
    pub formations: FormationState,
    pub patrols: PatrolState,
    pub security_posts: SecurityPostState,
    pub footholds: FootholdState,
    pub beliefs: BeliefState,
    pub presence_beliefs: PresenceState,
    pub node_presence_beliefs: PresenceState,
    pub zone_beliefs: ZoneBeliefState,
    pub logistics: LogisticsState,
    pub command_edges: CommandEdgeState,
    pub manpower: ManpowerState,
    pub leaders: LeaderState,
    pub political: PoliticalState,
    pub foreign: ForeignSystemState,
    pub foreign_interventions: ForeignInterventionState,
    pub relations: OrganizationRelationState,
    pub access_restrictions: AccessRestrictionState,
    pub scheduler: Scheduler,
    pub rng: RngStreams,
    pub counters: Counters,
    pub observations: Vec<ObservationRecord>,
    pub information_observations: Vec<InformationObservation>,
    pub information_relays: Vec<InformationRelay>,
    pub information_history: Vec<InformationHistoryEntry>,
    pub next_information_observation_sequence: u64,
    pub next_information_relay_sequence: u64,
    pub last_information_decay_at: f64,
    pub movement_order_count: u64,
    pub event_log: Vec<EventRecord>,
    pub weights_log: f64,
    pub ancestry: Vec<u64>,
    pub filter_boundary: u64,
    pub partner_support: PartnerSupportLedger,
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
            locality: LocalityState::new(localities).with_organizations(organizations),
            zones: ZoneState::new(zones),
            people: PersonState::new(0).with_organizations(organizations),
            households: HouseholdState::new(0),
            communities: CommunityState::new(0),
            protos: ProtoState::new(),
            social_edges: SocialEdgeState::new(0),
            organizations: OrganizationState::new(organizations),
            formations: FormationState::new(formations),
            patrols: PatrolState::new(formations),
            security_posts: SecurityPostState::new(localities),
            footholds: FootholdState::new(footholds),
            beliefs: BeliefState::default(),
            presence_beliefs: PresenceState::default(),
            node_presence_beliefs: PresenceState::default(),
            zone_beliefs: ZoneBeliefState::default(),
            logistics: LogisticsState::new(organizations),
            command_edges: CommandEdgeState::default(),
            manpower: ManpowerState::default(),
            leaders: LeaderState::default(),
            political: PoliticalState::new(),
            foreign: ForeignSystemState::new(),
            foreign_interventions: ForeignInterventionState::default(),
            relations: OrganizationRelationState::default(),
            access_restrictions: AccessRestrictionState::new(),
            scheduler: Scheduler::new(),
            rng,
            counters: Counters::default(),
            observations: Vec::new(),
            information_observations: Vec::new(),
            information_relays: Vec::new(),
            information_history: Vec::new(),
            next_information_observation_sequence: 1,
            next_information_relay_sequence: 1,
            last_information_decay_at: 0.0,
            movement_order_count: 0,
            event_log: Vec::new(),
            weights_log: 0.0,
            ancestry: vec![0],
            filter_boundary: 0,
            partner_support: PartnerSupportLedger::default(),
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
        particle.people = PersonState::new(people)
            .with_organizations(organizations)
            .with_destination_localities(localities);
        particle.social_edges = SocialEdgeState::new(people);
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

    pub fn clone_for_child_with_rng(
        &self,
        child_id: u64,
        child_lineage: impl Into<String>,
        rng: crate::rng::RngStreams,
    ) -> Self {
        let child_lineage = child_lineage.into();
        let mut clone = self.clone();
        clone.logical_id = child_id;
        clone.lineage = child_lineage;
        clone.rng = rng;
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
            let rng = source
                .rng
                .fork(&format!("gather-child-{child_id}:parent-{parent}"));
            let child = source.clone_for_child_with_rng(child_id as u64, lineage, rng);
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
            &self.locality.organization_control,
            &self.locality.violence,
            &self.locality.disruption,
            &self.locality.government_security_recruit_pipeline,
            &self.locality.government_security_reserve,
            &self.locality.government_intelligence_penetration,
            &self.formations.personnel,
            &self.formations.experience,
            &self.formations.readiness,
            &self.formations.supply_stock,
            &self.security_posts.professionalism,
            &self.footholds.strength,
            &self.beliefs.presence,
            &self.beliefs.control,
            &self.beliefs.confidence,
        ] {
            append_f64s(&mut material, values);
        }
        append_presence_state(&mut material, &self.presence_beliefs);
        append_presence_state(&mut material, &self.node_presence_beliefs);
        append_f64s(&mut material, &self.people.represented_population);
        append_f64s(&mut material, &self.people.insurgent_affinity);
        append_u8s(&mut material, &self.people.public_behavior);
        append_f64s(&mut material, &self.people.party_legitimacy);
        append_f64s(&mut material, &self.organizations.phenotype);
        append_f64s(&mut material, &self.organizations.ideology);
        append_f64s(&mut material, &self.communities.cohesion);
        append_u32s(&mut material, &self.protos.community);
        append_u32s(&mut material, &self.protos.locality);
        append_u8s(&mut material, &self.protos.status);
        append_u32s(&mut material, &self.protos.member_offsets);
        append_u32s(&mut material, &self.protos.member_indices);
        append_f64s(&mut material, &self.protos.capital_social);
        append_f64s(&mut material, &self.protos.capital_political);
        append_f64s(&mut material, &self.protos.capital_organizational);
        append_f64s(&mut material, &self.protos.capital_material);
        append_f64s(&mut material, &self.protos.represented_membership);
        append_f64s(&mut material, &self.protos.ideology_reform);
        append_f64s(&mut material, &self.protos.ideology_separatism);
        append_f64s(&mut material, &self.protos.leadership_potential);
        append_f64s(&mut material, &self.protos.created_at);
        append_u8s(&mut material, &self.foreign_interventions.status);
        append_u32s(&mut material, &self.foreign_interventions.foreign_state);
        append_u32s(&mut material, &self.foreign_interventions.recipient);
        append_u32s(&mut material, &self.foreign_interventions.force_formation);
        append_f64s(&mut material, &self.foreign_interventions.provided_capacity);
        append_f64s(&mut material, &self.social_edges.weight);
        append_f64s(&mut material, &self.zone_beliefs.estimate);
        append_information_state(&mut material, self);
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
        append_f64s(material, &self.locality.district_population);
        append_u8s(material, &self.locality.district_population_is_integer);
        append_f64s(material, &self.locality.economic_output);
        append_f64s(material, &self.locality.infrastructure);
        append_f64s(material, &self.locality.administrative_capacity);
        append_f64s(
            material,
            &self.locality.government_security_recruit_pipeline,
        );
        append_f64s(material, &self.locality.government_security_reserve);
        append_f64s(material, &self.locality.government_intelligence_penetration);
        append_f64s(
            material,
            &self.locality.government_cumulative_security_recruits,
        );
        append_f64s(
            material,
            &self.locality.government_cumulative_security_deployments,
        );
        append_f64s(material, &self.locality.government_cumulative_admin_rebuild);
        append_f64s(
            material,
            &self.locality.government_cumulative_underground_disruption,
        );
        append_f64s(material, &self.locality.terrain_friction);
        append_f64s(material, &self.locality.observability);
        append_f64s(material, &self.locality.government_control);
        append_f64s(material, &self.locality.insurgent_control);
        append_f64s(material, &self.locality.organization_control);
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
        append_f64s(material, &self.people.party_legitimacy);
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
        append_u8s(material, &self.people.public_behavior);
        append_f64s(material, &self.people.expected_control);
        append_f64s(material, &self.people.expected_destination_control);
        append_u8s(material, &self.people.expected_destination_control_present);
        append_f64s(material, &self.people.state_legitimacy);
        append_f64s(material, &self.people.government_legitimacy);
        append_f64s(material, &self.people.political_access);
        append_u8s(material, &self.people.displaced);
        append_u32s(material, &self.people.displacement_count);
        append_f64s(material, &self.people.displaced_since);
        append_u32s(material, &self.people.displacement_origin);
        append_f64s(material, &self.people.origin_tie_strength);
        append_u32s(material, &self.people.external_state);
        append_u8s(material, &self.people.migration_status);
        append_f64s(material, &self.people.insurgent_affinity);
        append_f64s(material, &self.people.social_exposure);
        append_u32s(material, &self.households.locality);
        append_u32s(material, &self.households.residence);
        append_f64s(material, &self.households.resources);
        append_u32s(material, &self.households.dependents);
        append_u32s(material, &self.households.member_offsets);
        append_u32s(material, &self.households.member_indices);
        append_u32s(material, &self.communities.locality);
        append_f64s(material, &self.communities.cohesion);
        append_f64s(material, &self.communities.government_cooperation);
        append_f64s(material, &self.communities.insurgent_sympathy);
        append_f64s(material, &self.communities.language_profile);
        append_u32s(material, &self.communities.member_offsets);
        append_u32s(material, &self.communities.member_indices);
        append_u32s(material, &self.communities.bridge_offsets);
        append_u32s(material, &self.communities.bridge_members);
        append_u32s(material, &self.protos.community);
        append_u32s(material, &self.protos.locality);
        append_u8s(material, &self.protos.status);
        append_u32s(material, &self.protos.member_offsets);
        append_u32s(material, &self.protos.member_indices);
        append_f64s(material, &self.protos.capital_social);
        append_f64s(material, &self.protos.capital_political);
        append_f64s(material, &self.protos.capital_organizational);
        append_f64s(material, &self.protos.capital_material);
        append_f64s(material, &self.protos.represented_membership);
        append_f64s(material, &self.protos.ideology_reform);
        append_f64s(material, &self.protos.ideology_separatism);
        append_f64s(material, &self.protos.leadership_potential);
        append_f64s(material, &self.protos.created_at);
        append_u32s(material, &self.social_edges.person_a);
        append_u32s(material, &self.social_edges.person_b);
        append_u8s(material, &self.social_edges.layers);
        append_f64s(material, &self.social_edges.weight);
        append_f64s(material, &self.social_edges.language_compatibility);
        append_f64s(material, &self.social_edges.trust);
        append_f64s(material, &self.social_edges.represented_relationships);
        append_u32s(material, &self.social_edges.neighbor_offsets);
        append_u32s(material, &self.social_edges.neighbor_indices);
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
        for key in &self.zone_beliefs.keys {
            material.extend_from_slice(&key.observer.to_le_bytes());
            material.extend_from_slice(&key.zone.to_le_bytes());
        }
        append_f64s(material, &self.zone_beliefs.estimate);
        append_f64s(material, &self.zone_beliefs.confidence);
        append_f64s(material, &self.zone_beliefs.updated_at);
        append_f64s(material, &self.zone_beliefs.last_reliable_observation_at);
        append_u32s(material, &self.zone_beliefs.evidence_count);
        append_f64s(material, &self.zone_beliefs.contradiction);
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
        append_f64s(material, &self.organizations.capital_social);
        append_f64s(material, &self.organizations.capital_political);
        append_f64s(material, &self.organizations.capital_organizational);
        append_f64s(material, &self.organizations.capital_material);
        append_f64s(material, &self.organizations.phenotype);
        append_f64s(material, &self.organizations.ideology);
        append_f64s(material, &self.organizations.external_sanctuary);
        append_f64s(material, &self.organizations.adaptation_rate);
        append_u32s(material, &self.organizations.leader);
        append_u32s(material, &self.formations.organization);
        append_u32s(material, &self.formations.locality);
        append_u32s(material, &self.formations.microzone);
        append_f64s(material, &self.formations.personnel);
        append_f64s(material, &self.formations.quality);
        append_f64s(material, &self.formations.experience);
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
        append_u32s(material, &self.formations.movement_destination);
        append_u32s(material, &self.formations.movement_origin);
        append_f64s(material, &self.formations.movement_execute_at);
        append_f64s(material, &self.formations.movement_arrives_at);
        append_f64s(material, &self.formations.movement_travel_hours);
        append_f64s(material, &self.formations.movement_distance_km);
        append_f64s(material, &self.formations.movement_supply_cost);
        append_u64s(material, &self.formations.movement_order_sequence);
        append_u8s(material, &self.formations.movement_status);
        append_u8s(material, &self.formations.movement_purpose);
        append_u32s(material, &self.formations.external_state);
        material.extend_from_slice(&self.movement_order_count.to_le_bytes());
        append_u32s(material, &self.patrols.formation);
        append_u8s(material, &self.patrols.active);
        append_u32s(material, &self.patrols.route_position);
        append_u32s(material, &self.patrols.route_target);
        append_f64s(material, &self.patrols.last_departure);
        append_f64s(material, &self.patrols.next_available);
        append_f64s(material, &self.patrols.response_fraction);
        append_f64s(material, &self.patrols.presence_accounted_at);
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
        append_f64s(material, &self.security_posts.professionalism);
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
        append_presence_state(material, &self.presence_beliefs);
        append_presence_state(material, &self.node_presence_beliefs);
        append_u32s(material, &self.logistics.organization);
        append_u32s(material, &self.logistics.locality);
        append_f64s(material, &self.logistics.source_stock);
        append_f64s(material, &self.logistics.source_capacity);
        append_f64s(material, &self.logistics.source_production);
        append_u32s(material, &self.logistics.shipment_source);
        append_u32s(material, &self.logistics.shipment_formation);
        append_u32s(material, &self.logistics.shipment_origin_locality);
        append_u32s(material, &self.logistics.shipment_destination_locality);
        append_u32s(material, &self.logistics.shipment_route_offsets);
        append_u32s(material, &self.logistics.shipment_route_nodes);
        append_f64s(material, &self.logistics.shipment_departed_at);
        append_f64s(material, &self.logistics.shipment_arrives_at);
        append_f64s(material, &self.logistics.shipment_quantity_sent);
        append_f64s(material, &self.logistics.shipment_quantity_deliverable);
        append_f64s(material, &self.logistics.shipment_loss);
        append_u8s(material, &self.logistics.shipment_status);
        material.extend_from_slice(&self.logistics.in_transit.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_produced.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_consumed.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_lost.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_shipped.to_bits().to_le_bytes());
        material.extend_from_slice(&self.logistics.cumulative_delivered.to_bits().to_le_bytes());
        append_u32s(material, &self.command_edges.organization);
        append_u32s(material, &self.command_edges.formation);
        append_f64s(material, &self.command_edges.reliability);
        append_f64s(material, &self.command_edges.latency_hours);
        append_u32s(material, &self.manpower.organization);
        append_u32s(material, &self.manpower.locality);
        append_f64s(material, &self.manpower.pool);
        append_f64s(material, &self.manpower.supply_reserve);
        append_u32s(material, &self.leaders.organization);
        append_f64s(material, &self.leaders.competence);
        append_f64s(material, &self.leaders.charisma);
        append_f64s(material, &self.leaders.risk_tolerance);
        append_f64s(material, &self.leaders.ideological_rigidity);
        append_f64s(material, &self.leaders.political_skill);
        append_f64s(material, &self.leaders.organizational_skill);
        append_u8s(material, &self.leaders.active);
        append_u8s(material, &self.political.institution_type);
        append_u8s(material, &self.political.institution_level);
        append_u32s(material, &self.political.institution_locality);
        append_u32s(material, &self.political.institution_district);
        append_f64s(material, &self.political.institution_capacity);
        append_f64s(material, &self.political.institution_autonomy);
        append_f64s(material, &self.political.institution_compliance);
        append_f64s(material, &self.political.institution_reach);
        append_f64s(material, &self.political.institution_integrity);
        append_f64s(material, &self.political.institution_resources);
        append_u32s(material, &self.political.institution_governing_party);
        append_u32s(material, &self.political.branch_party);
        append_u32s(material, &self.political.branch_locality);
        append_f64s(material, &self.political.branch_resources);
        append_f64s(material, &self.political.branch_patronage);
        append_f64s(material, &self.political.branch_electoral_support);
        append_f64s(material, &self.political.branch_institutional_influence);
        append_u32s(material, &self.political.branch_member_offsets);
        append_u32s(material, &self.political.branch_member_indices);
        append_u32s(material, &self.political.branch_broker_offsets);
        append_u32s(material, &self.political.branch_broker_indices);
        append_u32s(material, &self.political.elite_person);
        append_u32s(material, &self.political.elite_locality);
        append_f64s(material, &self.political.elite_network_centrality);
        append_f64s(material, &self.political.elite_resources);
        append_f64s(material, &self.political.elite_legitimacy);
        append_f64s(material, &self.political.elite_institutional_ties);
        append_u32s(material, &self.political.elite_party_alignment);
        material.extend_from_slice(&self.political.ruling_party.to_le_bytes());
        material.extend_from_slice(
            &self
                .political
                .private_diversion_stock
                .to_bits()
                .to_le_bytes(),
        );
        append_f64s(material, &self.foreign.resources);
        append_f64s(material, &self.foreign.stability_preference);
        append_f64s(material, &self.foreign.government_alignment);
        append_f64s(material, &self.foreign.ideological_alignment);
        append_f64s(material, &self.foreign.border_security_priority);
        append_f64s(material, &self.foreign.regional_influence);
        append_f64s(material, &self.foreign.commercial_interest);
        append_f64s(material, &self.foreign.humanitarian_preference);
        append_f64s(material, &self.foreign.cost_sensitivity);
        append_f64s(material, &self.foreign.domestic_opposition);
        append_f64s(material, &self.foreign.willingness);
        append_f64s(material, &self.foreign.language_profile);
        append_f64s(material, &self.foreign.opportunity);
        append_u32s(material, &self.foreign.rival_offsets);
        append_u32s(material, &self.foreign.rival_indices);
        append_f64s(material, &self.foreign.cumulative_cost);
        append_f64s(material, &self.foreign.cumulative_casualties);
        append_u32s(material, &self.foreign.border_foreign_state);
        append_u32s(material, &self.foreign.border_district);
        append_u32s(material, &self.foreign.border_locality);
        append_f64s(material, &self.foreign.border_terrain_friction);
        append_f64s(material, &self.foreign.border_infrastructure);
        append_f64s(material, &self.foreign.border_legal_permeability);
        append_f64s(material, &self.foreign.border_social_permeability);
        append_f64s(material, &self.foreign.border_language_overlap);
        append_f64s(material, &self.foreign.border_kinship_overlap);
        append_f64s(material, &self.foreign.border_state_monitoring);
        append_u32s(material, &self.foreign.belief_foreign_state);
        append_u32s(material, &self.foreign.belief_locality);
        append_f64s(material, &self.foreign.belief_government_control);
        append_f64s(material, &self.foreign.belief_insurgent_presence);
        append_f64s(material, &self.foreign.belief_confidence);
        append_f64s(material, &self.foreign.belief_updated_at);
        append_u32s(material, &self.foreign.interpreter_person);
        append_u32s(material, &self.foreign.interpreter_foreign_state);
        append_u32s(material, &self.foreign.interpreter_locality);
        append_f64s(material, &self.foreign.interpreter_foreign_language);
        append_f64s(material, &self.foreign.interpreter_local_language);
        append_f64s(material, &self.foreign.interpreter_foreign_trust);
        append_f64s(material, &self.foreign.interpreter_local_trust);
        append_f64s(material, &self.foreign.interpreter_cultural_knowledge);
        append_u32s(material, &self.foreign.diaspora_person);
        append_u32s(material, &self.foreign.diaspora_foreign_state);
        append_u32s(material, &self.foreign.diaspora_origin_locality);
        append_f64s(material, &self.foreign.diaspora_social_strength);
        append_f64s(material, &self.foreign.diaspora_financial_capacity);
        append_f64s(material, &self.foreign.diaspora_information_reliability);
        append_f64s(material, &self.foreign.diaspora_created_at);
        append_u32s(material, &self.foreign.support_foreign_state);
        append_u32s(material, &self.foreign.support_recipient);
        append_f64s(material, &self.foreign.support_total);
        material.extend_from_slice(
            &self
                .foreign
                .cumulative_external_remittances
                .to_bits()
                .to_le_bytes(),
        );
        append_u32s(material, &self.foreign_interventions.foreign_state);
        append_u32s(material, &self.foreign_interventions.recipient);
        append_f64s(material, &self.foreign_interventions.started_at);
        append_u8s(material, &self.foreign_interventions.mode);
        append_f64s(material, &self.foreign_interventions.provided_capacity);
        append_f64s(material, &self.foreign_interventions.transfer_efficiency);
        append_f64s(material, &self.foreign_interventions.crowding_out);
        append_u32s(material, &self.foreign_interventions.force_formation);
        append_u8s(material, &self.foreign_interventions.status);
        append_f64s(material, &self.foreign_interventions.withdrawal_rate);
        append_f64s(
            material,
            &self.foreign_interventions.cumulative_transferred_capacity,
        );
        append_f64s(
            material,
            &self.foreign_interventions.cumulative_retained_host_capacity,
        );
        append_f64s(
            material,
            &self.foreign_interventions.cumulative_crowding_out,
        );
        append_f64s(material, &self.foreign_interventions.peak_provided_capacity);
        append_f64s(material, &self.foreign_interventions.withdrawn_capacity);
        append_u32s(material, &self.relations.organization_a);
        append_u32s(material, &self.relations.organization_b);
        append_u8s(material, &self.relations.status);
        append_f64s(material, &self.relations.rivalry_memory);
        append_f64s(material, &self.relations.hostility_memory);
        append_f64s(material, &self.relations.cooperation_memory);
        append_f64s(material, &self.relations.updated_at);
        append_f64s(material, &self.relations.last_interaction_at);
        append_u8s(material, &self.relations.has_last_interaction);
        append_u32s(material, &self.access_restrictions.owner);
        append_u32s(material, &self.access_restrictions.first_locality);
        append_u32s(material, &self.access_restrictions.second_locality);
        append_f64s(material, &self.access_restrictions.level);
        append_f64s(material, &self.access_restrictions.cumulative_effort);
        append_f64s(material, &self.access_restrictions.updated_at);
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
        append_information_state(material, self);
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
        if self.partner_support != PartnerSupportLedger::default() {
            append_u8s(material, &[1]);
            material
                .extend_from_slice(&(self.partner_support.support_withdrawn as u8).to_le_bytes());
            if let Some(wt) = self.partner_support.withdrawal_time {
                material.extend_from_slice(&wt.to_bits().to_le_bytes());
            }
            append_f64s(
                material,
                &[
                    self.partner_support.air.cumulative_intensity,
                    self.partner_support.air.cumulative_donor_cost,
                    self.partner_support.logistics.cumulative_delivered,
                    self.partner_support
                        .logistics
                        .indigenous_cumulative_produced,
                    self.partner_support
                        .logistics
                        .indigenous_cumulative_delivered,
                    self.partner_support
                        .logistics
                        .indigenous_cumulative_consumed,
                    self.partner_support.logistics.military_cumulative_demanded,
                    self.partner_support.logistics.cumulative_donor_cost,
                    self.partner_support.command.cumulative_reliability_boost,
                    self.partner_support.command.cumulative_indigenous_service,
                    self.partner_support.command.cumulative_supported_service,
                    self.partner_support.command.cumulative_donor_cost,
                    self.partner_support
                        .force_generation
                        .external_incremental_graduates,
                    self.partner_support.force_generation.cumulative_donor_cost,
                ],
            );
        }
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
            (
                self.locality.government_security_recruit_pipeline.len(),
                "government security recruit pipeline",
            ),
            (
                self.locality.government_security_reserve.len(),
                "government security reserve",
            ),
            (
                self.locality.government_intelligence_penetration.len(),
                "government intelligence penetration",
            ),
            (
                self.locality.government_cumulative_security_recruits.len(),
                "government cumulative security recruits",
            ),
            (
                self.locality
                    .government_cumulative_security_deployments
                    .len(),
                "government cumulative security deployments",
            ),
            (
                self.locality.government_cumulative_admin_rebuild.len(),
                "government cumulative administrative rebuild",
            ),
            (
                self.locality
                    .government_cumulative_underground_disruption
                    .len(),
                "government cumulative underground disruption",
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
        let expected_organization_controls =
            expected_controls.saturating_mul(self.organizations.kind.len());
        if self.locality.organization_control.len() != expected_organization_controls {
            return Err(StateError::LengthMismatch {
                name: "organization-specific locality control".to_string(),
                left: self.locality.organization_control.len(),
                right: expected_organization_controls,
            });
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
            (self.people.public_behavior.len(), "person public behavior"),
            (
                self.people.state_legitimacy.len(),
                "person state legitimacy",
            ),
            (
                self.people.government_legitimacy.len(),
                "person government legitimacy",
            ),
            (
                self.people.political_access.len(),
                "person political access",
            ),
            (self.people.displaced.len(), "person displaced"),
            (
                self.people.displacement_count.len(),
                "person displacement count",
            ),
            (self.people.displaced_since.len(), "person displaced since"),
            (
                self.people.displacement_origin.len(),
                "person displacement origin",
            ),
            (
                self.people.origin_tie_strength.len(),
                "person origin tie strength",
            ),
            (self.people.external_state.len(), "person external state"),
            (
                self.people.migration_status.len(),
                "person migration status",
            ),
        ] {
            if length != people_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: people_count,
                });
            }
        }
        if self.people.expected_control.len() != people_count * 2 {
            return Err(StateError::LengthMismatch {
                name: "person expected control".to_string(),
                left: self.people.expected_control.len(),
                right: people_count * 2,
            });
        }
        let locality_count = self.locality.population.len();
        if self.people.expected_destination_control.len() != people_count * locality_count * 2 {
            return Err(StateError::LengthMismatch {
                name: "person expected destination control".to_string(),
                left: self.people.expected_destination_control.len(),
                right: people_count * locality_count * 2,
            });
        }
        if self.people.expected_destination_control_present.len() != people_count * locality_count {
            return Err(StateError::LengthMismatch {
                name: "person expected destination control present".to_string(),
                left: self.people.expected_destination_control_present.len(),
                right: people_count * locality_count,
            });
        }
        let organization_count = self.organizations.kind.len();
        if self.people.insurgent_affinity.len() != people_count * organization_count {
            return Err(StateError::LengthMismatch {
                name: "person insurgent affinity".to_string(),
                left: self.people.insurgent_affinity.len(),
                right: people_count * organization_count,
            });
        }
        if self.people.social_exposure.len() != people_count * organization_count {
            return Err(StateError::LengthMismatch {
                name: "person social exposure".to_string(),
                left: self.people.social_exposure.len(),
                right: people_count * organization_count,
            });
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
            (
                self.people.party_legitimacy.len(),
                "person party legitimacy",
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
        let household_count = self.households.locality.len();
        for (length, name) in [
            (self.households.residence.len(), "household residence"),
            (self.households.resources.len(), "household resources"),
            (self.households.dependents.len(), "household dependents"),
        ] {
            if length != household_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: household_count,
                });
            }
        }
        if self.households.member_offsets.len() != household_count + 1 {
            return Err(StateError::LengthMismatch {
                name: "household member offsets".to_string(),
                left: self.households.member_offsets.len(),
                right: household_count + 1,
            });
        }
        if self.households.member_offsets.last().copied().unwrap_or(0) as usize
            != self.households.member_indices.len()
        {
            return Err(StateError::Corrupt(
                "household member offsets do not cover member rows".to_string(),
            ));
        }
        for member in &self.households.member_indices {
            if *member as usize >= people_count {
                return Err(StateError::Corrupt(format!(
                    "household member id {member} is outside {people_count}"
                )));
            }
        }
        let community_count = self.communities.locality.len();
        for (length, name) in [
            (self.communities.cohesion.len(), "community cohesion"),
            (
                self.communities.government_cooperation.len(),
                "community government cooperation",
            ),
            (
                self.communities.insurgent_sympathy.len(),
                "community insurgent sympathy",
            ),
        ] {
            if length != community_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: community_count,
                });
            }
        }
        for (length, name, expected) in [
            (
                self.communities.language_profile.len(),
                "community language profile",
                community_count * 4,
            ),
            (
                self.communities.member_offsets.len(),
                "community member offsets",
                community_count + 1,
            ),
            (
                self.communities.bridge_offsets.len(),
                "community bridge offsets",
                community_count + 1,
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
        if self.communities.member_offsets.last().copied().unwrap_or(0) as usize
            != self.communities.member_indices.len()
            || self.communities.bridge_offsets.last().copied().unwrap_or(0) as usize
                != self.communities.bridge_members.len()
        {
            return Err(StateError::Corrupt(
                "community offsets do not cover member rows".to_string(),
            ));
        }
        for member in self
            .communities
            .member_indices
            .iter()
            .chain(self.communities.bridge_members.iter())
        {
            if *member as usize >= people_count {
                return Err(StateError::Corrupt(format!(
                    "community member id {member} is outside {people_count}"
                )));
            }
        }
        let proto_count = self.protos.community.len();
        for (length, name) in [
            (self.protos.locality.len(), "proto locality"),
            (self.protos.status.len(), "proto status"),
            (self.protos.capital_social.len(), "proto social capital"),
            (
                self.protos.capital_political.len(),
                "proto political capital",
            ),
            (
                self.protos.capital_organizational.len(),
                "proto organizational capital",
            ),
            (self.protos.capital_material.len(), "proto material capital"),
            (
                self.protos.represented_membership.len(),
                "proto represented membership",
            ),
            (self.protos.ideology_reform.len(), "proto reform ideology"),
            (
                self.protos.ideology_separatism.len(),
                "proto separatist ideology",
            ),
            (
                self.protos.leadership_potential.len(),
                "proto leadership potential",
            ),
            (self.protos.created_at.len(), "proto created time"),
        ] {
            if length != proto_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: proto_count,
                });
            }
        }
        if self.protos.member_offsets.len() != proto_count + 1
            || self.protos.member_offsets.last().copied().unwrap_or(0) as usize
                != self.protos.member_indices.len()
        {
            return Err(StateError::Corrupt(
                "proto member offsets do not cover member rows".to_string(),
            ));
        }
        for member in &self.protos.member_indices {
            if *member as usize >= people_count {
                return Err(StateError::Corrupt(format!(
                    "proto member id {member} is outside {people_count}"
                )));
            }
        }
        for (community, locality, status) in self
            .protos
            .community
            .iter()
            .zip(&self.protos.locality)
            .zip(&self.protos.status)
            .map(|((community, locality), status)| (*community, *locality, *status))
        {
            if community as usize >= community_count {
                return Err(StateError::Corrupt(format!(
                    "proto community {community} is outside {community_count}"
                )));
            }
            if locality as usize >= locality_count {
                return Err(StateError::Corrupt(format!(
                    "proto locality {locality} is outside {locality_count}"
                )));
            }
            if !matches!(status, 1..=3) {
                return Err(StateError::Corrupt(format!(
                    "unknown proto status {status}"
                )));
            }
        }
        let edge_count = self.social_edges.person_a.len();
        for (length, name) in [
            (
                self.social_edges.person_b.len(),
                "social edge second endpoint",
            ),
            (self.social_edges.layers.len(), "social edge layers"),
            (self.social_edges.weight.len(), "social edge weight"),
            (
                self.social_edges.language_compatibility.len(),
                "social edge language compatibility",
            ),
            (self.social_edges.trust.len(), "social edge trust"),
            (
                self.social_edges.represented_relationships.len(),
                "social edge represented relationships",
            ),
        ] {
            if length != edge_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: edge_count,
                });
            }
        }
        if self.social_edges.neighbor_offsets.len() != people_count + 1
            || self
                .social_edges
                .neighbor_offsets
                .last()
                .copied()
                .unwrap_or(0) as usize
                != self.social_edges.neighbor_indices.len()
        {
            return Err(StateError::LengthMismatch {
                name: "social neighbor offsets".to_string(),
                left: self.social_edges.neighbor_offsets.len(),
                right: people_count + 1,
            });
        }
        for endpoint in self
            .social_edges
            .person_a
            .iter()
            .chain(self.social_edges.person_b.iter())
            .chain(self.social_edges.neighbor_indices.iter())
        {
            if *endpoint as usize >= people_count {
                return Err(StateError::Corrupt(format!(
                    "social person id {endpoint} is outside {people_count}"
                )));
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
            (
                self.organizations.capital_social.len(),
                "organization social capital",
            ),
            (
                self.organizations.capital_political.len(),
                "organization political capital",
            ),
            (
                self.organizations.capital_organizational.len(),
                "organization organizational capital",
            ),
            (
                self.organizations.capital_material.len(),
                "organization material capital",
            ),
            (
                self.organizations.external_sanctuary.len(),
                "organization sanctuary",
            ),
            (
                self.organizations.adaptation_rate.len(),
                "organization adaptation rate",
            ),
            (self.organizations.leader.len(), "organization leader"),
        ] {
            if length != organization_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: organization_count,
                });
            }
        }
        for (length, name, expected) in [
            (
                self.organizations.phenotype.len(),
                "organization phenotype",
                organization_count * 8,
            ),
            (
                self.organizations.ideology.len(),
                "organization ideology",
                organization_count * 2,
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
        let formation_count = self.formations.organization.len();
        for (length, name) in [
            (self.formations.locality.len(), "formation locality"),
            (self.formations.microzone.len(), "formation microzone"),
            (self.formations.personnel.len(), "formation personnel"),
            (self.formations.quality.len(), "formation quality"),
            (self.formations.experience.len(), "formation experience"),
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
            (
                self.formations.movement_destination.len(),
                "formation movement destination",
            ),
            (
                self.formations.movement_origin.len(),
                "formation movement origin",
            ),
            (
                self.formations.movement_execute_at.len(),
                "formation movement execute time",
            ),
            (
                self.formations.movement_arrives_at.len(),
                "formation movement arrival time",
            ),
            (
                self.formations.movement_travel_hours.len(),
                "formation movement travel time",
            ),
            (
                self.formations.movement_distance_km.len(),
                "formation movement distance",
            ),
            (
                self.formations.movement_supply_cost.len(),
                "formation movement supply cost",
            ),
            (
                self.formations.movement_order_sequence.len(),
                "formation movement order sequence",
            ),
            (
                self.formations.movement_status.len(),
                "formation movement status",
            ),
            (
                self.formations.movement_purpose.len(),
                "formation movement purpose",
            ),
            (
                self.formations.external_state.len(),
                "formation external state",
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
            (
                self.patrols.response_fraction.len(),
                "patrol response fraction",
            ),
            (
                self.patrols.presence_accounted_at.len(),
                "patrol presence timestamp",
            ),
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
                self.security_posts.professionalism.len(),
                "security post professionalism",
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
        for (name, state) in [
            ("presence beliefs", &self.presence_beliefs),
            ("node presence beliefs", &self.node_presence_beliefs),
        ] {
            let presence_count = state.keys.len();
            for (length, field) in [
                (state.estimate.len(), "estimate"),
                (state.personnel.len(), "personnel"),
                (state.confidence.len(), "confidence"),
                (state.updated_at.len(), "timestamps"),
                (
                    state.last_reliable_observation_at.len(),
                    "reliable timestamps",
                ),
                (state.contradiction.len(), "contradiction"),
                (state.violence.len(), "violence"),
                (state.evidence_count.len(), "evidence"),
            ] {
                if length != presence_count {
                    return Err(StateError::LengthMismatch {
                        name: format!("{name} {field}"),
                        left: length,
                        right: presence_count,
                    });
                }
            }
            for key in &state.keys {
                if key.observer as usize >= organization_count && key.observer != INFORMATION_NONE {
                    // Dynamic field-node observer codes are allowed after the
                    // organization rows.  The topology-specific upper bound
                    // is checked by the producer; checkpoint validation only
                    // rejects wrapped numeric IDs.
                    if key.observer >= 0x4000_0000 {
                        return Err(StateError::Corrupt(format!(
                            "{name} observer {} is outside the native node code range",
                            key.observer
                        )));
                    }
                }
                if key.target as usize >= organization_count && key.target != INFORMATION_NONE {
                    return Err(StateError::Corrupt(format!(
                        "{name} target {} is outside {organization_count}",
                        key.target
                    )));
                }
                if key.locality as usize >= locality_count && key.locality != INFORMATION_NONE {
                    return Err(StateError::Corrupt(format!(
                        "{name} locality {} is outside {locality_count}",
                        key.locality
                    )));
                }
                if key.target_formation != INFORMATION_NONE
                    && key.target_formation as usize >= self.formations.personnel.len()
                {
                    return Err(StateError::Corrupt(format!(
                        "{name} formation {} is outside {}",
                        key.target_formation,
                        self.formations.personnel.len()
                    )));
                }
            }
        }
        let zone_belief_count = self.zone_beliefs.keys.len();
        for (length, name) in [
            (self.zone_beliefs.estimate.len(), "zone belief estimate"),
            (self.zone_beliefs.confidence.len(), "zone belief confidence"),
            (self.zone_beliefs.updated_at.len(), "zone belief timestamps"),
            (
                self.zone_beliefs.last_reliable_observation_at.len(),
                "zone belief reliable timestamps",
            ),
            (
                self.zone_beliefs.evidence_count.len(),
                "zone belief evidence",
            ),
            (
                self.zone_beliefs.contradiction.len(),
                "zone belief contradiction",
            ),
        ] {
            if length != zone_belief_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: zone_belief_count,
                });
            }
        }
        for key in &self.zone_beliefs.keys {
            if key.observer as usize >= organization_count || key.zone as usize >= zone_count {
                return Err(StateError::Corrupt(format!(
                    "zone belief key ({}, {}) is outside ({organization_count}, {zone_count})",
                    key.observer, key.zone
                )));
            }
        }
        let leader_count = self.leaders.organization.len();
        for (length, name) in [
            (self.leaders.competence.len(), "leader competence"),
            (self.leaders.charisma.len(), "leader charisma"),
            (self.leaders.risk_tolerance.len(), "leader risk tolerance"),
            (
                self.leaders.ideological_rigidity.len(),
                "leader ideological rigidity",
            ),
            (self.leaders.political_skill.len(), "leader political skill"),
            (
                self.leaders.organizational_skill.len(),
                "leader organizational skill",
            ),
            (self.leaders.active.len(), "leader active"),
        ] {
            if length != leader_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: leader_count,
                });
            }
        }
        let command_count = self.command_edges.organization.len();
        for (length, name) in [
            (self.command_edges.formation.len(), "command edge formation"),
            (
                self.command_edges.reliability.len(),
                "command edge reliability",
            ),
            (
                self.command_edges.latency_hours.len(),
                "command edge latency",
            ),
        ] {
            if length != command_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: command_count,
                });
            }
        }
        let manpower_count = self.manpower.organization.len();
        for (length, name) in [
            (self.manpower.locality.len(), "manpower locality"),
            (self.manpower.pool.len(), "manpower pool"),
            (
                self.manpower.supply_reserve.len(),
                "manpower supply reserve",
            ),
        ] {
            if length != manpower_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: manpower_count,
                });
            }
        }
        let institution_count = self.political.institution_type.len();
        for (length, name) in [
            (self.political.institution_level.len(), "institution level"),
            (
                self.political.institution_locality.len(),
                "institution locality",
            ),
            (
                self.political.institution_district.len(),
                "institution district",
            ),
            (
                self.political.institution_capacity.len(),
                "institution capacity",
            ),
            (
                self.political.institution_autonomy.len(),
                "institution autonomy",
            ),
            (
                self.political.institution_compliance.len(),
                "institution compliance",
            ),
            (self.political.institution_reach.len(), "institution reach"),
            (
                self.political.institution_integrity.len(),
                "institution integrity",
            ),
            (
                self.political.institution_resources.len(),
                "institution resources",
            ),
            (
                self.political.institution_governing_party.len(),
                "institution governing party",
            ),
        ] {
            if length != institution_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: institution_count,
                });
            }
        }
        let branch_count = self.political.branch_party.len();
        for (length, name) in [
            (self.political.branch_locality.len(), "branch locality"),
            (self.political.branch_resources.len(), "branch resources"),
            (self.political.branch_patronage.len(), "branch patronage"),
            (
                self.political.branch_electoral_support.len(),
                "branch electoral support",
            ),
            (
                self.political.branch_institutional_influence.len(),
                "branch institutional influence",
            ),
        ] {
            if length != branch_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: branch_count,
                });
            }
        }
        for (length, name, expected) in [
            (
                self.political.branch_member_offsets.len(),
                "branch member offsets",
                branch_count + 1,
            ),
            (
                self.political.branch_broker_offsets.len(),
                "branch broker offsets",
                branch_count + 1,
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
        if self
            .political
            .branch_member_offsets
            .last()
            .copied()
            .unwrap_or(0) as usize
            != self.political.branch_member_indices.len()
            || self
                .political
                .branch_broker_offsets
                .last()
                .copied()
                .unwrap_or(0) as usize
                != self.political.branch_broker_indices.len()
        {
            return Err(StateError::Corrupt(
                "political branch offsets do not cover membership rows".to_string(),
            ));
        }
        let elite_count = self.political.elite_person.len();
        for (length, name) in [
            (self.political.elite_locality.len(), "elite locality"),
            (
                self.political.elite_network_centrality.len(),
                "elite network centrality",
            ),
            (self.political.elite_resources.len(), "elite resources"),
            (self.political.elite_legitimacy.len(), "elite legitimacy"),
            (
                self.political.elite_institutional_ties.len(),
                "elite institutional ties",
            ),
            (
                self.political.elite_party_alignment.len(),
                "elite party alignment",
            ),
        ] {
            if length != elite_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: elite_count,
                });
            }
        }

        let foreign_state_count = self.foreign.resources.len();
        for (length, name) in [
            (
                self.foreign.stability_preference.len(),
                "foreign stability preference",
            ),
            (
                self.foreign.government_alignment.len(),
                "foreign government alignment",
            ),
            (
                self.foreign.ideological_alignment.len(),
                "foreign ideological alignment",
            ),
            (
                self.foreign.border_security_priority.len(),
                "foreign border security priority",
            ),
            (
                self.foreign.regional_influence.len(),
                "foreign regional influence",
            ),
            (
                self.foreign.commercial_interest.len(),
                "foreign commercial interest",
            ),
            (
                self.foreign.humanitarian_preference.len(),
                "foreign humanitarian preference",
            ),
            (
                self.foreign.cost_sensitivity.len(),
                "foreign cost sensitivity",
            ),
            (
                self.foreign.domestic_opposition.len(),
                "foreign domestic opposition",
            ),
            (self.foreign.willingness.len(), "foreign willingness"),
            (self.foreign.opportunity.len(), "foreign opportunity"),
            (
                self.foreign.cumulative_cost.len(),
                "foreign cumulative cost",
            ),
            (
                self.foreign.cumulative_casualties.len(),
                "foreign cumulative casualties",
            ),
        ] {
            if length != foreign_state_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: foreign_state_count,
                });
            }
        }
        if self.foreign.language_profile.len() != foreign_state_count * 4 {
            return Err(StateError::LengthMismatch {
                name: "foreign language profile".to_string(),
                left: self.foreign.language_profile.len(),
                right: foreign_state_count * 4,
            });
        }
        if self.foreign.rival_offsets.len() != foreign_state_count + 1
            || self.foreign.rival_offsets.last().copied().unwrap_or(0) as usize
                != self.foreign.rival_indices.len()
        {
            return Err(StateError::LengthMismatch {
                name: "foreign rival offsets".to_string(),
                left: self.foreign.rival_offsets.len(),
                right: foreign_state_count + 1,
            });
        }
        let border_count = self.foreign.border_foreign_state.len();
        for (length, name) in [
            (self.foreign.border_district.len(), "border district"),
            (self.foreign.border_locality.len(), "border locality"),
            (
                self.foreign.border_terrain_friction.len(),
                "border terrain friction",
            ),
            (
                self.foreign.border_infrastructure.len(),
                "border infrastructure",
            ),
            (
                self.foreign.border_legal_permeability.len(),
                "border legal permeability",
            ),
            (
                self.foreign.border_social_permeability.len(),
                "border social permeability",
            ),
            (
                self.foreign.border_language_overlap.len(),
                "border language overlap",
            ),
            (
                self.foreign.border_kinship_overlap.len(),
                "border kinship overlap",
            ),
            (
                self.foreign.border_state_monitoring.len(),
                "border state monitoring",
            ),
        ] {
            if length != border_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: border_count,
                });
            }
        }
        let foreign_belief_count = self.foreign.belief_foreign_state.len();
        for (length, name) in [
            (
                self.foreign.belief_locality.len(),
                "foreign belief locality",
            ),
            (
                self.foreign.belief_government_control.len(),
                "foreign belief government control",
            ),
            (
                self.foreign.belief_insurgent_presence.len(),
                "foreign belief insurgent presence",
            ),
            (
                self.foreign.belief_confidence.len(),
                "foreign belief confidence",
            ),
            (
                self.foreign.belief_updated_at.len(),
                "foreign belief timestamp",
            ),
        ] {
            if length != foreign_belief_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: foreign_belief_count,
                });
            }
        }
        let interpreter_count = self.foreign.interpreter_person.len();
        for (length, name) in [
            (
                self.foreign.interpreter_foreign_state.len(),
                "interpreter foreign state",
            ),
            (
                self.foreign.interpreter_locality.len(),
                "interpreter locality",
            ),
            (
                self.foreign.interpreter_foreign_language.len(),
                "interpreter foreign language",
            ),
            (
                self.foreign.interpreter_local_language.len(),
                "interpreter local language",
            ),
            (
                self.foreign.interpreter_foreign_trust.len(),
                "interpreter foreign trust",
            ),
            (
                self.foreign.interpreter_local_trust.len(),
                "interpreter local trust",
            ),
            (
                self.foreign.interpreter_cultural_knowledge.len(),
                "interpreter cultural knowledge",
            ),
        ] {
            if length != interpreter_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: interpreter_count,
                });
            }
        }
        let diaspora_count = self.foreign.diaspora_person.len();
        for (length, name) in [
            (
                self.foreign.diaspora_foreign_state.len(),
                "diaspora foreign state",
            ),
            (
                self.foreign.diaspora_origin_locality.len(),
                "diaspora origin locality",
            ),
            (
                self.foreign.diaspora_social_strength.len(),
                "diaspora social strength",
            ),
            (
                self.foreign.diaspora_financial_capacity.len(),
                "diaspora financial capacity",
            ),
            (
                self.foreign.diaspora_information_reliability.len(),
                "diaspora information reliability",
            ),
            (
                self.foreign.diaspora_created_at.len(),
                "diaspora created timestamp",
            ),
        ] {
            if length != diaspora_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: diaspora_count,
                });
            }
        }
        let support_count = self.foreign.support_foreign_state.len();
        for (length, name) in [
            (self.foreign.support_recipient.len(), "support recipient"),
            (self.foreign.support_total.len(), "support total"),
        ] {
            if length != support_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: support_count,
                });
            }
        }
        let intervention_count = self.foreign_interventions.foreign_state.len();
        for (length, name) in [
            (
                self.foreign_interventions.recipient.len(),
                "intervention recipient",
            ),
            (
                self.foreign_interventions.started_at.len(),
                "intervention start",
            ),
            (self.foreign_interventions.mode.len(), "intervention mode"),
            (
                self.foreign_interventions.provided_capacity.len(),
                "intervention capacity",
            ),
            (
                self.foreign_interventions.transfer_efficiency.len(),
                "intervention transfer efficiency",
            ),
            (
                self.foreign_interventions.crowding_out.len(),
                "intervention crowding out",
            ),
            (
                self.foreign_interventions.force_formation.len(),
                "intervention formation",
            ),
            (
                self.foreign_interventions.status.len(),
                "intervention status",
            ),
            (
                self.foreign_interventions.withdrawal_rate.len(),
                "intervention withdrawal rate",
            ),
            (
                self.foreign_interventions
                    .cumulative_transferred_capacity
                    .len(),
                "intervention transferred capacity",
            ),
            (
                self.foreign_interventions
                    .cumulative_retained_host_capacity
                    .len(),
                "intervention retained capacity",
            ),
            (
                self.foreign_interventions.cumulative_crowding_out.len(),
                "intervention crowding out total",
            ),
            (
                self.foreign_interventions.peak_provided_capacity.len(),
                "intervention peak capacity",
            ),
            (
                self.foreign_interventions.withdrawn_capacity.len(),
                "intervention withdrawn capacity",
            ),
        ] {
            if length != intervention_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: intervention_count,
                });
            }
        }
        for (value, name, bound) in self
            .foreign_interventions
            .foreign_state
            .iter()
            .map(|value| (*value, "intervention foreign state", foreign_state_count))
            .chain(
                self.foreign_interventions
                    .recipient
                    .iter()
                    .map(|value| (*value, "intervention recipient", organization_count)),
            )
            .chain(
                self.foreign_interventions
                    .force_formation
                    .iter()
                    .map(|value| (*value, "intervention formation", formation_count)),
            )
        {
            if value != u32::MAX && value as usize >= bound {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        let relation_count = self.relations.organization_a.len();
        for (length, name) in [
            (
                self.relations.organization_b.len(),
                "relation organization b",
            ),
            (self.relations.status.len(), "relation status"),
            (
                self.relations.rivalry_memory.len(),
                "relation rivalry memory",
            ),
            (
                self.relations.hostility_memory.len(),
                "relation hostility memory",
            ),
            (
                self.relations.cooperation_memory.len(),
                "relation cooperation memory",
            ),
            (self.relations.updated_at.len(), "relation timestamp"),
            (
                self.relations.last_interaction_at.len(),
                "relation last interaction",
            ),
            (
                self.relations.has_last_interaction.len(),
                "relation interaction flag",
            ),
        ] {
            if length != relation_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: relation_count,
                });
            }
        }
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
        let shipment_count = self.logistics.shipment_source.len();
        for (length, name) in [
            (
                self.logistics.shipment_formation.len(),
                "shipment formation",
            ),
            (
                self.logistics.shipment_origin_locality.len(),
                "shipment origin locality",
            ),
            (
                self.logistics.shipment_destination_locality.len(),
                "shipment destination locality",
            ),
            (
                self.logistics.shipment_departed_at.len(),
                "shipment departure",
            ),
            (self.logistics.shipment_arrives_at.len(), "shipment arrival"),
            (
                self.logistics.shipment_quantity_sent.len(),
                "shipment quantity sent",
            ),
            (
                self.logistics.shipment_quantity_deliverable.len(),
                "shipment quantity deliverable",
            ),
            (self.logistics.shipment_loss.len(), "shipment loss"),
            (self.logistics.shipment_status.len(), "shipment status"),
        ] {
            if length != shipment_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: shipment_count,
                });
            }
        }
        if self.logistics.shipment_route_offsets.len() != shipment_count + 1 {
            return Err(StateError::LengthMismatch {
                name: "shipment route offsets".to_string(),
                left: self.logistics.shipment_route_offsets.len(),
                right: shipment_count + 1,
            });
        }
        if self
            .logistics
            .shipment_route_offsets
            .last()
            .copied()
            .unwrap_or(0) as usize
            != self.logistics.shipment_route_nodes.len()
        {
            return Err(StateError::Corrupt(
                "shipment route offsets do not cover route nodes".to_string(),
            ));
        }
        let restriction_count = self.access_restrictions.owner.len();
        for (length, name) in [
            (
                self.access_restrictions.first_locality.len(),
                "access first locality",
            ),
            (
                self.access_restrictions.second_locality.len(),
                "access second locality",
            ),
            (self.access_restrictions.level.len(), "access level"),
            (
                self.access_restrictions.cumulative_effort.len(),
                "access cumulative effort",
            ),
            (
                self.access_restrictions.updated_at.len(),
                "access timestamp",
            ),
        ] {
            if length != restriction_count {
                return Err(StateError::LengthMismatch {
                    name: name.to_string(),
                    left: length,
                    right: restriction_count,
                });
            }
        }
        for (values, name) in [
            (&self.access_restrictions.level, "access level"),
            (
                &self.access_restrictions.cumulative_effort,
                "access cumulative effort",
            ),
            (&self.access_restrictions.updated_at, "access timestamp"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.access_restrictions.level, "access level")?;
        check_nonnegative(
            &self.access_restrictions.cumulative_effort,
            "access cumulative effort",
        )?;
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
                self.formations
                    .external_state
                    .iter()
                    .map(|value| (*value, "formation external state", foreign_state_count)),
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
            let sentinel_allowed = value == u32::MAX
                && matches!(
                    name,
                    "formation home locality" | "formation external state" | "formation microzone"
                );
            if value as usize >= bound && !sentinel_allowed {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        for member in &self.political.branch_member_indices {
            if *member as usize >= people_count {
                return Err(StateError::Corrupt(format!(
                    "political branch member id {member} is outside {people_count}"
                )));
            }
        }
        for broker in &self.political.branch_broker_indices {
            if *broker as usize >= elite_count {
                return Err(StateError::Corrupt(format!(
                    "political branch broker id {broker} is outside {elite_count}"
                )));
            }
        }
        for (value, name, bound) in self
            .political
            .institution_locality
            .iter()
            .map(|value| (*value, "institution locality", locality_count))
            .chain(
                self.political
                    .institution_district
                    .iter()
                    .map(|value| (*value, "institution district", usize::MAX)),
            )
            .chain(
                self.political
                    .branch_locality
                    .iter()
                    .map(|value| (*value, "branch locality", locality_count)),
            )
            .chain(
                self.political
                    .branch_party
                    .iter()
                    .map(|value| (*value, "branch party", organization_count)),
            )
            .chain(
                self.political
                    .institution_governing_party
                    .iter()
                    .map(|value| (*value, "institution governing party", organization_count)),
            )
        {
            if value != u32::MAX && value as usize >= bound {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        for (value, name, bound) in self
            .political
            .elite_person
            .iter()
            .map(|value| (*value, "elite person", people_count))
            .chain(
                self.political
                    .elite_locality
                    .iter()
                    .map(|value| (*value, "elite locality", locality_count)),
            )
            .chain(
                self.political
                    .elite_party_alignment
                    .iter()
                    .map(|value| (*value, "elite party alignment", organization_count)),
            )
        {
            if value != u32::MAX && value as usize >= bound {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        for (value, name, bound) in self
            .foreign
            .rival_indices
            .iter()
            .map(|value| (*value, "foreign rival state", foreign_state_count))
            .chain(
                self.foreign
                    .border_foreign_state
                    .iter()
                    .map(|value| (*value, "border foreign state", foreign_state_count)),
            )
            .chain(
                self.foreign
                    .border_district
                    .iter()
                    .map(|value| (*value, "border district", usize::MAX)),
            )
            .chain(
                self.foreign
                    .border_locality
                    .iter()
                    .map(|value| (*value, "border locality", locality_count)),
            )
            .chain(
                self.foreign
                    .belief_foreign_state
                    .iter()
                    .map(|value| (*value, "foreign belief state", foreign_state_count)),
            )
            .chain(
                self.foreign
                    .belief_locality
                    .iter()
                    .map(|value| (*value, "foreign belief locality", locality_count)),
            )
            .chain(
                self.foreign
                    .interpreter_person
                    .iter()
                    .map(|value| (*value, "interpreter person", people_count)),
            )
            .chain(
                self.foreign
                    .interpreter_foreign_state
                    .iter()
                    .map(|value| (*value, "interpreter foreign state", foreign_state_count)),
            )
            .chain(
                self.foreign
                    .interpreter_locality
                    .iter()
                    .map(|value| (*value, "interpreter locality", locality_count)),
            )
        {
            if value as usize >= bound {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {bound}"
                )));
            }
        }
        for (value, name) in self
            .relations
            .organization_a
            .iter()
            .chain(self.relations.organization_b.iter())
            .map(|value| (*value, "relation organization"))
        {
            if value as usize >= organization_count {
                return Err(StateError::Corrupt(format!(
                    "{name} id {value} is outside {organization_count}"
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
            (&self.locality.district_population, "district population"),
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
            (
                &self.locality.organization_control,
                "organization-specific locality control",
            ),
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
        check_nonnegative(&self.locality.district_population, "district population")?;
        if self.locality.district_population_is_integer.len()
            != self.locality.district_population.len()
        {
            return Err(StateError::Corrupt(
                "district population type flags have the wrong length".to_string(),
            ));
        }
        if self
            .locality
            .district_population_is_integer
            .iter()
            .any(|flag| *flag > 1)
        {
            return Err(StateError::Corrupt(
                "district population type flag is not boolean".to_string(),
            ));
        }
        check_nonnegative(&self.locality.economic_output, "economic output")?;
        check_nonnegative(&self.locality.displaced_population, "displaced population")?;
        for (values, name) in [
            (
                &self.people.represented_population,
                "represented population",
            ),
            (&self.people.languages, "person languages"),
            (&self.people.identities, "person identities"),
            (&self.people.preferences, "person preferences"),
            (&self.people.party_legitimacy, "person party legitimacy"),
            (&self.people.grievance, "person grievance"),
            (&self.people.fear, "person fear"),
            (&self.people.efficacy, "person efficacy"),
            (&self.people.trust, "person trust"),
            (&self.people.trust_insurgent, "person insurgent trust"),
            (&self.people.rebel_sympathy, "person sympathy"),
            (&self.people.expected_control, "person expected control"),
            (&self.people.state_legitimacy, "person state legitimacy"),
            (
                &self.people.government_legitimacy,
                "person government legitimacy",
            ),
            (&self.people.political_access, "person political access"),
            (&self.people.displaced_since, "person displaced since"),
            (
                &self.people.origin_tie_strength,
                "person origin tie strength",
            ),
            (&self.people.insurgent_affinity, "person insurgent affinity"),
            (&self.people.social_exposure, "person social exposure"),
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
            .chain(self.people.social_exposure.iter())
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
            (&self.formations.experience, "formation experience"),
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
            (
                &self.formations.movement_execute_at,
                "formation movement execute time",
            ),
            (
                &self.formations.movement_arrives_at,
                "formation movement arrival time",
            ),
            (
                &self.formations.movement_travel_hours,
                "formation movement travel time",
            ),
            (
                &self.formations.movement_distance_km,
                "formation movement distance",
            ),
            (
                &self.formations.movement_supply_cost,
                "formation movement supply cost",
            ),
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
            (&self.patrols.response_fraction, "patrol response fraction"),
            (
                &self.patrols.presence_accounted_at,
                "patrol presence timestamp",
            ),
            (&self.security_posts.presence, "security post presence"),
            (
                &self.security_posts.detection_rate,
                "security post detection rate",
            ),
            (
                &self.security_posts.reliability,
                "security post reliability",
            ),
            (
                &self.security_posts.professionalism,
                "security post professionalism",
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
            .chain(self.security_posts.professionalism.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for value in self
            .formations
            .quality
            .iter()
            .chain(self.formations.experience.iter())
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
        for value in &self.patrols.response_fraction {
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
        for (values, name) in [
            (&self.presence_beliefs.estimate, "presence estimate"),
            (&self.presence_beliefs.personnel, "presence personnel"),
            (&self.presence_beliefs.confidence, "presence confidence"),
            (&self.presence_beliefs.updated_at, "presence timestamp"),
            (
                &self.presence_beliefs.last_reliable_observation_at,
                "presence reliable timestamp",
            ),
            (
                &self.presence_beliefs.contradiction,
                "presence contradiction",
            ),
            (&self.presence_beliefs.violence, "presence violence"),
            (
                &self.node_presence_beliefs.estimate,
                "node presence estimate",
            ),
            (
                &self.node_presence_beliefs.personnel,
                "node presence personnel",
            ),
            (
                &self.node_presence_beliefs.confidence,
                "node presence confidence",
            ),
            (
                &self.node_presence_beliefs.updated_at,
                "node presence timestamp",
            ),
            (
                &self.node_presence_beliefs.last_reliable_observation_at,
                "node presence reliable timestamp",
            ),
            (
                &self.node_presence_beliefs.contradiction,
                "node presence contradiction",
            ),
            (
                &self.node_presence_beliefs.violence,
                "node presence violence",
            ),
        ] {
            check_finite(values, name)?;
        }
        for value in self
            .presence_beliefs
            .estimate
            .iter()
            .chain(self.presence_beliefs.confidence.iter())
            .chain(self.presence_beliefs.violence.iter())
            .chain(self.node_presence_beliefs.estimate.iter())
            .chain(self.node_presence_beliefs.confidence.iter())
            .chain(self.node_presence_beliefs.violence.iter())
        {
            if !(-1e-12..=1.0 + 1e-12).contains(value) {
                return Err(StateError::OutOfBounds(*value));
            }
        }
        for (values, name) in [
            (&self.households.resources, "household resources"),
            (&self.communities.cohesion, "community cohesion"),
            (
                &self.communities.government_cooperation,
                "community government cooperation",
            ),
            (
                &self.communities.insurgent_sympathy,
                "community insurgent sympathy",
            ),
            (
                &self.communities.language_profile,
                "community language profile",
            ),
            (&self.social_edges.weight, "social edge weight"),
            (
                &self.social_edges.language_compatibility,
                "social edge language compatibility",
            ),
            (&self.social_edges.trust, "social edge trust"),
            (
                &self.social_edges.represented_relationships,
                "social edge represented relationships",
            ),
            (&self.zone_beliefs.estimate, "zone belief estimate"),
            (&self.zone_beliefs.confidence, "zone belief confidence"),
            (&self.zone_beliefs.updated_at, "zone belief timestamp"),
            (
                &self.zone_beliefs.last_reliable_observation_at,
                "zone belief reliable timestamp",
            ),
            (
                &self.zone_beliefs.contradiction,
                "zone belief contradiction",
            ),
            (
                &self.organizations.capital_social,
                "organization social capital",
            ),
            (
                &self.organizations.capital_political,
                "organization political capital",
            ),
            (
                &self.organizations.capital_organizational,
                "organization organizational capital",
            ),
            (
                &self.organizations.capital_material,
                "organization material capital",
            ),
            (&self.organizations.phenotype, "organization phenotype"),
            (&self.organizations.ideology, "organization ideology"),
            (
                &self.organizations.external_sanctuary,
                "organization sanctuary",
            ),
            (
                &self.organizations.adaptation_rate,
                "organization adaptation rate",
            ),
            (&self.leaders.competence, "leader competence"),
            (&self.leaders.charisma, "leader charisma"),
            (&self.leaders.risk_tolerance, "leader risk tolerance"),
            (
                &self.leaders.ideological_rigidity,
                "leader ideological rigidity",
            ),
            (&self.leaders.political_skill, "leader political skill"),
            (
                &self.leaders.organizational_skill,
                "leader organizational skill",
            ),
            (&self.command_edges.reliability, "command reliability"),
            (&self.command_edges.latency_hours, "command latency"),
            (&self.manpower.pool, "manpower pool"),
            (&self.manpower.supply_reserve, "manpower supply reserve"),
            (&self.political.institution_capacity, "institution capacity"),
            (&self.political.institution_autonomy, "institution autonomy"),
            (
                &self.political.institution_compliance,
                "institution compliance",
            ),
            (&self.political.institution_reach, "institution reach"),
            (
                &self.political.institution_integrity,
                "institution integrity",
            ),
            (
                &self.political.institution_resources,
                "institution resources",
            ),
            (&self.political.branch_resources, "branch resources"),
            (&self.political.branch_patronage, "branch patronage"),
            (
                &self.political.branch_electoral_support,
                "branch electoral support",
            ),
            (
                &self.political.branch_institutional_influence,
                "branch institutional influence",
            ),
            (
                &self.political.elite_network_centrality,
                "elite network centrality",
            ),
            (&self.political.elite_resources, "elite resources"),
            (&self.political.elite_legitimacy, "elite legitimacy"),
            (
                &self.political.elite_institutional_ties,
                "elite institutional ties",
            ),
            (&self.foreign.resources, "foreign resources"),
            (
                &self.foreign.stability_preference,
                "foreign stability preference",
            ),
            (
                &self.foreign.government_alignment,
                "foreign government alignment",
            ),
            (
                &self.foreign.ideological_alignment,
                "foreign ideological alignment",
            ),
            (
                &self.foreign.border_security_priority,
                "foreign border security priority",
            ),
            (
                &self.foreign.regional_influence,
                "foreign regional influence",
            ),
            (
                &self.foreign.commercial_interest,
                "foreign commercial interest",
            ),
            (
                &self.foreign.humanitarian_preference,
                "foreign humanitarian preference",
            ),
            (&self.foreign.cost_sensitivity, "foreign cost sensitivity"),
            (
                &self.foreign.domestic_opposition,
                "foreign domestic opposition",
            ),
            (&self.foreign.willingness, "foreign willingness"),
            (&self.foreign.language_profile, "foreign language profile"),
            (&self.foreign.opportunity, "foreign opportunity"),
            (&self.foreign.cumulative_cost, "foreign cumulative cost"),
            (
                &self.foreign.cumulative_casualties,
                "foreign cumulative casualties",
            ),
            (
                &self.foreign.border_terrain_friction,
                "border terrain friction",
            ),
            (&self.foreign.border_infrastructure, "border infrastructure"),
            (
                &self.foreign.border_legal_permeability,
                "border legal permeability",
            ),
            (
                &self.foreign.border_social_permeability,
                "border social permeability",
            ),
            (
                &self.foreign.border_language_overlap,
                "border language overlap",
            ),
            (
                &self.foreign.border_kinship_overlap,
                "border kinship overlap",
            ),
            (
                &self.foreign.border_state_monitoring,
                "border state monitoring",
            ),
            (
                &self.foreign.belief_government_control,
                "foreign belief government control",
            ),
            (
                &self.foreign.belief_insurgent_presence,
                "foreign belief insurgent presence",
            ),
            (&self.foreign.belief_confidence, "foreign belief confidence"),
            (&self.foreign.belief_updated_at, "foreign belief timestamp"),
            (
                &self.foreign.interpreter_foreign_language,
                "interpreter foreign language",
            ),
            (
                &self.foreign.interpreter_local_language,
                "interpreter local language",
            ),
            (
                &self.foreign.interpreter_foreign_trust,
                "interpreter foreign trust",
            ),
            (
                &self.foreign.interpreter_local_trust,
                "interpreter local trust",
            ),
            (
                &self.foreign.interpreter_cultural_knowledge,
                "interpreter cultural knowledge",
            ),
            (
                &self.foreign.diaspora_social_strength,
                "diaspora social strength",
            ),
            (
                &self.foreign.diaspora_financial_capacity,
                "diaspora financial capacity",
            ),
            (
                &self.foreign.diaspora_information_reliability,
                "diaspora information reliability",
            ),
            (
                &self.foreign.diaspora_created_at,
                "diaspora created timestamp",
            ),
            (&self.foreign.support_total, "support total"),
            (&self.relations.rivalry_memory, "relation rivalry memory"),
            (
                &self.relations.hostility_memory,
                "relation hostility memory",
            ),
            (
                &self.relations.cooperation_memory,
                "relation cooperation memory",
            ),
            (&self.relations.updated_at, "relation timestamp"),
            (
                &self.relations.last_interaction_at,
                "relation last interaction",
            ),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(&self.logistics.source_stock, "source stock")?;
        check_nonnegative(&self.logistics.source_capacity, "source capacity")?;
        check_nonnegative(&self.logistics.source_production, "source production")?;
        for (values, name) in [
            (&self.logistics.shipment_departed_at, "shipment departure"),
            (&self.logistics.shipment_arrives_at, "shipment arrival"),
            (
                &self.logistics.shipment_quantity_sent,
                "shipment quantity sent",
            ),
            (
                &self.logistics.shipment_quantity_deliverable,
                "shipment quantity deliverable",
            ),
            (&self.logistics.shipment_loss, "shipment loss"),
        ] {
            check_finite(values, name)?;
        }
        check_nonnegative(
            &self.logistics.shipment_quantity_sent,
            "shipment quantity sent",
        )?;
        check_nonnegative(
            &self.logistics.shipment_quantity_deliverable,
            "shipment quantity deliverable",
        )?;
        check_nonnegative(&self.logistics.shipment_loss, "shipment loss")?;
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
            (
                self.partner_support.air.cumulative_intensity,
                "partner air intensity",
            ),
            (
                self.partner_support.air.cumulative_donor_cost,
                "partner air donor cost",
            ),
            (
                self.partner_support.logistics.cumulative_delivered,
                "partner logistics delivered",
            ),
            (
                self.partner_support.logistics.cumulative_donor_cost,
                "partner logistics donor cost",
            ),
            (
                self.partner_support
                    .logistics
                    .indigenous_cumulative_produced,
                "partner indigenous logistics produced",
            ),
            (
                self.partner_support
                    .logistics
                    .indigenous_cumulative_delivered,
                "partner indigenous logistics delivered",
            ),
            (
                self.partner_support
                    .logistics
                    .indigenous_cumulative_consumed,
                "partner indigenous logistics consumed",
            ),
            (
                self.partner_support.logistics.military_cumulative_demanded,
                "military logistics demanded",
            ),
            (
                self.partner_support.command.cumulative_reliability_boost,
                "partner command reliability boost",
            ),
            (
                self.partner_support.command.cumulative_donor_cost,
                "partner command donor cost",
            ),
            (
                self.partner_support
                    .force_generation
                    .external_incremental_graduates,
                "partner forcegen graduates",
            ),
            (
                self.partner_support.force_generation.cumulative_donor_cost,
                "partner forcegen donor cost",
            ),
        ] {
            if !value.is_finite() {
                return Err(StateError::NonFinite(name));
            }
            // The Python oracle accumulates shipment additions and removals
            // in ordinary binary64 order.  A fully drained shipment ledger
            // can therefore retain a tiny negative cancellation residue
            // (for example -5e-12).  Preserve that exact value for parity,
            // while still rejecting any materially negative balance.
            let tolerated_roundoff = name == "in-transit logistics" && value >= -1.0e-9;
            if value < 0.0 && !tolerated_roundoff {
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

fn append_presence_state(material: &mut Vec<u8>, state: &PresenceState) {
    material.extend_from_slice(&(state.keys.len() as u64).to_le_bytes());
    for key in &state.keys {
        material.extend_from_slice(&key.observer.to_le_bytes());
        material.extend_from_slice(&key.target.to_le_bytes());
        material.extend_from_slice(&key.locality.to_le_bytes());
        material.extend_from_slice(&key.microzone.to_le_bytes());
        material.extend_from_slice(&key.target_formation.to_le_bytes());
    }
    append_f64s(material, &state.estimate);
    append_f64s(material, &state.personnel);
    append_f64s(material, &state.confidence);
    append_f64s(material, &state.updated_at);
    append_f64s(material, &state.last_reliable_observation_at);
    append_f64s(material, &state.contradiction);
    append_f64s(material, &state.violence);
    append_u32s(material, &state.evidence_count);
}

fn append_information_state(material: &mut Vec<u8>, particle: &ParticleState) {
    material.extend_from_slice(&particle.next_information_observation_sequence.to_le_bytes());
    material.extend_from_slice(&particle.next_information_relay_sequence.to_le_bytes());
    material.extend_from_slice(&particle.last_information_decay_at.to_bits().to_le_bytes());
    material.extend_from_slice(&(particle.information_observations.len() as u64).to_le_bytes());
    for observation in &particle.information_observations {
        material.extend_from_slice(&observation.sequence.to_le_bytes());
        for value in [
            observation.observer,
            observation.observer_node,
            observation.source,
            observation.source_identity,
            observation.source_community,
            observation.source_formation,
            observation.target,
            observation.target_formation,
            observation.locality,
            observation.microzone,
        ] {
            material.extend_from_slice(&value.to_le_bytes());
        }
        material.push(observation.source_type);
        material.push(observation.observation_type);
        for value in [
            observation.time,
            observation.quality,
            observation.confidence,
            observation.decay_rate,
        ] {
            material.extend_from_slice(&value.to_bits().to_le_bytes());
        }
        append_f64s(material, &observation.control);
        for value in [
            observation.violence,
            observation.presence,
            observation.personnel,
            observation.detection_probability,
        ] {
            material.extend_from_slice(&value.to_bits().to_le_bytes());
        }
        material.push(observation.detected);
        material.extend_from_slice(&observation.reported_momentum.to_bits().to_le_bytes());
        material.extend_from_slice(&observation.reported_civilian_harm.to_bits().to_le_bytes());
        material.extend_from_slice(&observation.attributed_actor.to_le_bytes());
    }
    material.extend_from_slice(&(particle.information_relays.len() as u64).to_le_bytes());
    for relay in &particle.information_relays {
        material.extend_from_slice(&relay.sequence.to_le_bytes());
        material.extend_from_slice(&relay.observation.to_le_bytes());
        material.extend_from_slice(&relay.organization.to_le_bytes());
        for value in [relay.source_node, relay.destination_node] {
            material.extend_from_slice(&value.to_le_bytes());
        }
        material.extend_from_slice(&(relay.route.len() as u64).to_le_bytes());
        append_u32s(material, &relay.route);
        for value in [
            relay.sent_at,
            relay.arrives_at,
            relay.reliability,
            relay.latency_hours,
            relay.delivered_at,
        ] {
            material.extend_from_slice(&value.to_bits().to_le_bytes());
        }
        material.push(relay.status);
    }
    material.extend_from_slice(&(particle.information_history.len() as u64).to_le_bytes());
    for entry in &particle.information_history {
        material.extend_from_slice(&entry.target.to_le_bytes());
        material.extend_from_slice(&entry.locality.to_le_bytes());
        material.push(entry.observation_type);
        material.extend_from_slice(&entry.time.to_bits().to_le_bytes());
        material.extend_from_slice(&entry.source_identity.to_le_bytes());
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
    buffer.extend_from_slice(&event.elapsed_days.to_bits().to_le_bytes());
    encode_payload(buffer, &event.payload);
}

pub(crate) fn decode_event(reader: &mut ByteReader<'_>) -> Result<ScheduledEvent, StateError> {
    let time = f64::from_bits(reader.u64()?);
    let priority = reader.u16()?;
    let sequence = reader.u64()?;
    let elapsed_days = f64::from_bits(reader.u64()?);
    let payload = decode_payload(reader)?;
    Ok(ScheduledEvent {
        time,
        priority,
        sequence,
        elapsed_days,
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
        22 => EventPayload::StateRegeneration,
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
