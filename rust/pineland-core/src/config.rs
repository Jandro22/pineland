//! Configuration contract for the standalone runtime.

use crate::json::{self, JsonError, JsonValue};
use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::Path;

#[derive(Clone, Debug, PartialEq)]
pub struct ProcessIntervals {
    pub contact: f64,
    pub command: f64,
    pub force_movement: f64,
    pub logistics: f64,
    pub information: f64,
    pub patrol: f64,
    pub physical_refresh: f64,
    pub beliefs: f64,
    pub social_influence: f64,
    pub mobility: f64,
    pub recruitment: f64,
    pub governance: f64,
    pub economy: f64,
    pub checkpoint: f64,
}

macro_rules! object_f64 { ($( $key:expr => $value:expr ),* $(,)?) => {{ let mut object = JsonValue::object(); $( object.insert($key, JsonValue::number($value)); )* object }}; }

impl Default for ProcessIntervals {
    fn default() -> Self {
        Self {
            contact: 1.0,
            command: 1.0,
            force_movement: 0.25,
            logistics: 1.0,
            information: 0.25,
            patrol: 0.25,
            physical_refresh: 0.25,
            beliefs: 1.0,
            social_influence: 1.0,
            mobility: 1.0,
            recruitment: 7.0,
            governance: 30.0,
            economy: 30.0,
            checkpoint: 30.0,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SocialNetworkConfig {
    pub community_size_unit_population: f64,
    pub target_community_size: usize,
    pub minimum_community_size: usize,
    pub maximum_community_size: usize,
    pub mean_social_degree: f64,
    pub maximum_social_degree: usize,
    pub bridge_fraction: f64,
    pub behavior_update_rate: f64,
    pub household_tie_strength: f64,
    pub community_tie_strength: f64,
    pub bridge_tie_strength: f64,
    pub behavior_exposure_weight: f64,
    pub recruitment_exposure_weight: f64,
    pub language_topology_enabled: bool,
}

impl Default for SocialNetworkConfig {
    fn default() -> Self {
        Self {
            community_size_unit_population: 120.0,
            target_community_size: 100,
            minimum_community_size: 50,
            maximum_community_size: 150,
            mean_social_degree: 8.0,
            maximum_social_degree: 24,
            bridge_fraction: 0.03,
            behavior_update_rate: 0.12,
            household_tie_strength: 0.95,
            community_tie_strength: 0.65,
            bridge_tie_strength: 0.45,
            behavior_exposure_weight: 0.35,
            recruitment_exposure_weight: 1.0,
            language_topology_enabled: true,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PhysicalModelConfig {
    pub village_microzones: usize,
    pub town_microzones: usize,
    pub city_microzones: usize,
    pub extra_edge_probability: f64,
    pub presence_memory_days: f64,
    pub response_decay_hours: f64,
    pub formation_presence_gain: f64,
    pub patrol_memory_gain: f64,
    pub fixed_post_presence_gain: f64,
    pub zone_observation_noise: f64,
    pub patrol_route_randomness: f64,
    pub adaptive_patrol_routing: bool,
}

impl Default for PhysicalModelConfig {
    fn default() -> Self {
        Self {
            village_microzones: 3,
            town_microzones: 5,
            city_microzones: 8,
            extra_edge_probability: 0.22,
            presence_memory_days: 2.0,
            response_decay_hours: 0.75,
            formation_presence_gain: 0.35,
            patrol_memory_gain: 0.35,
            fixed_post_presence_gain: 0.25,
            zone_observation_noise: 0.12,
            patrol_route_randomness: 0.15,
            adaptive_patrol_routing: true,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct GeographyConfig {
    pub nearest_neighbors: usize,
    pub district_hub_links: bool,
    pub coordinate_jitter_km: f64,
    pub national_backbone: String,
}

impl Default for GeographyConfig {
    fn default() -> Self {
        Self {
            nearest_neighbors: 2,
            district_hub_links: true,
            coordinate_jitter_km: 18.0,
            national_backbone: "spatial_mst".to_string(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct LogisticsConfig {
    pub formation_supply_days: f64,
    pub initial_supply_fraction: f64,
    pub presence_consumption_per_person_day: f64,
    pub movement_consumption_per_person_km: f64,
    pub patrol_consumption_per_person_hour: f64,
    pub source_capacity_per_resident: f64,
    pub source_daily_production_fraction: f64,
    pub source_capacity_model: String,
    pub organization_sustainment_coverage: f64,
    pub resupply_trigger_fraction: f64,
    pub resupply_target_fraction: f64,
    pub shipment_loss_per_travel_hour: f64,
    pub convoy_speed_factor: f64,
    pub readiness_degradation_rate: f64,
    pub readiness_recovery_near_source: f64,
    pub readiness_recovery_remote: f64,
    pub availability_recovery_rate: f64,
    pub reallocation_rate: f64,
    pub reallocation_destination_scope: String,
    pub insurgent_frontier_weight: f64,
    pub insurgent_foothold_weight: f64,
    pub insurgent_stronghold_weight: f64,
    pub reallocation_exploration_weight: f64,
    pub reallocation_strategic_weight: f64,
    pub reallocation_importance_weight: f64,
    pub reallocation_travel_time_weight: f64,
    pub route_interdiction_enabled: bool,
    pub route_interdiction_rate: f64,
}

impl Default for LogisticsConfig {
    fn default() -> Self {
        Self {
            formation_supply_days: 30.0,
            initial_supply_fraction: 0.8,
            presence_consumption_per_person_day: 0.75,
            movement_consumption_per_person_km: 0.02,
            patrol_consumption_per_person_hour: 0.002,
            source_capacity_per_resident: 0.05,
            source_daily_production_fraction: 0.03,
            source_capacity_model: "organization_manpower".to_string(),
            organization_sustainment_coverage: 1.20,
            resupply_trigger_fraction: 0.45,
            resupply_target_fraction: 0.85,
            shipment_loss_per_travel_hour: 0.002,
            convoy_speed_factor: 0.75,
            readiness_degradation_rate: 0.08,
            readiness_recovery_near_source: 0.025,
            readiness_recovery_remote: 0.006,
            availability_recovery_rate: 0.03,
            reallocation_rate: 0.04,
            reallocation_destination_scope: "adjacent".to_string(),
            insurgent_frontier_weight: 0.50,
            insurgent_foothold_weight: 0.25,
            insurgent_stronghold_weight: 0.15,
            reallocation_exploration_weight: 0.10,
            reallocation_strategic_weight: 2.0,
            reallocation_importance_weight: 0.5,
            reallocation_travel_time_weight: 0.03,
            route_interdiction_enabled: false,
            route_interdiction_rate: 0.0,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ForceStructureConfig {
    pub mode: String,
    pub government_target_personnel: f64,
    pub insurgent_target_personnel: f64,
    pub maximum_initial_formations_per_side: usize,
}

impl Default for ForceStructureConfig {
    fn default() -> Self {
        Self {
            mode: "manpower_decomposition".to_string(),
            government_target_personnel: 3500.0,
            insurgent_target_personnel: 1000.0,
            maximum_initial_formations_per_side: 64,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct InformationConfig {
    pub prior_confidence: f64,
    pub default_decay_rate: f64,
    pub mobile_decay_rate: f64,
    pub static_decay_rate: f64,
    pub road_decay_rate: f64,
    pub formation_decay_rate: f64,
    pub true_positive_rate: f64,
    pub false_positive_rate: f64,
    pub attribution_error_rate: f64,
    pub contact_true_positive_rate: f64,
    pub contact_false_positive_rate: f64,
    pub detection_pressure_bonus: f64,
    pub detection_exposure_bonus: f64,
    pub detection_language_bonus: f64,
    pub detection_observability_bonus: f64,
    pub detection_terrain_penalty: f64,
    pub detection_readiness_bonus: f64,
    pub insurgent_concealment: f64,
    pub civilian_report_rate: f64,
    pub social_report_rate: f64,
    pub administrative_report_rate: f64,
    pub elite_report_rate: f64,
    pub member_report_rate: f64,
    pub fixed_post_report_rate: f64,
    pub patrol_report_rate: f64,
    pub interpreter_report_rate: f64,
    pub relay_base_reliability: f64,
    pub relay_max_hops: usize,
    pub contradiction_penalty: f64,
    pub contradiction_memory_days: f64,
    pub language_fusion_weight: f64,
    pub corroboration_bonus: f64,
    pub negative_report_confidence: f64,
    pub positive_report_confidence: f64,
    pub observation_retention_days: f64,
    pub source_trust: BTreeMap<String, f64>,
    pub source_coverage: BTreeMap<String, f64>,
    pub source_latency_hours: BTreeMap<String, f64>,
    pub source_correlation: BTreeMap<String, f64>,
}

impl Default for InformationConfig {
    fn default() -> Self {
        let names = [
            "patrol",
            "fixed_post",
            "civilian",
            "social_network",
            "administrative",
            "organization_member",
            "political_elite",
            "interpreter",
            "contact",
        ];
        let trust_values = [0.88, 0.80, 0.55, 0.62, 0.72, 0.76, 0.58, 0.72, 0.90];
        let coverage_values = [0.82, 0.65, 0.42, 0.48, 0.55, 0.58, 0.35, 0.52, 0.95];
        let latency_values = [0.2, 0.4, 8.0, 5.0, 12.0, 2.0, 24.0, 10.0, 0.1];
        let correlation_values = [0.15, 0.25, 0.55, 0.65, 0.35, 0.2, 0.5, 0.3, 0.1];
        let mut source_trust = BTreeMap::new();
        let mut source_coverage = BTreeMap::new();
        let mut source_latency_hours = BTreeMap::new();
        let mut source_correlation = BTreeMap::new();
        for index in 0..names.len() {
            source_trust.insert(names[index].to_string(), trust_values[index]);
            source_coverage.insert(names[index].to_string(), coverage_values[index]);
            source_latency_hours.insert(names[index].to_string(), latency_values[index]);
            source_correlation.insert(names[index].to_string(), correlation_values[index]);
        }
        Self {
            prior_confidence: 0.28,
            default_decay_rate: 0.08,
            mobile_decay_rate: 0.55,
            static_decay_rate: 0.025,
            road_decay_rate: 0.045,
            formation_decay_rate: 0.65,
            true_positive_rate: 0.72,
            false_positive_rate: 0.035,
            attribution_error_rate: 0.08,
            contact_true_positive_rate: 0.82,
            contact_false_positive_rate: 0.02,
            detection_pressure_bonus: 0.65,
            detection_exposure_bonus: 0.7,
            detection_language_bonus: 0.5,
            detection_observability_bonus: 0.7,
            detection_terrain_penalty: 0.55,
            detection_readiness_bonus: 0.55,
            insurgent_concealment: 0.25,
            civilian_report_rate: 0.18,
            social_report_rate: 0.22,
            administrative_report_rate: 0.28,
            elite_report_rate: 0.16,
            member_report_rate: 0.35,
            fixed_post_report_rate: 0.72,
            patrol_report_rate: 1.0,
            interpreter_report_rate: 0.72,
            relay_base_reliability: 0.86,
            relay_max_hops: 8,
            contradiction_penalty: 0.45,
            contradiction_memory_days: 30.0,
            language_fusion_weight: 1.0,
            corroboration_bonus: 0.12,
            negative_report_confidence: 0.52,
            positive_report_confidence: 0.90,
            observation_retention_days: 0.0,
            source_trust,
            source_coverage,
            source_latency_hours,
            source_correlation,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CombatConfig {
    pub interval_hours: f64,
    pub base_attrition_rate: f64,
    pub stochastic_sigma: f64,
    pub max_loss_fraction: f64,
    pub cohesion_loss_multiplier: f64,
    pub readiness_cost_multiplier: f64,
    pub supply_per_person_hour: f64,
    pub ineffective_cohesion: f64,
    pub ineffective_readiness: f64,
    pub disengagement_base: f64,
    pub surprise_initiative: f64,
    pub civilian_exposure_rate: f64,
    pub momentum_learning_rate: f64,
    pub reinforcement_threshold: f64,
    pub contact_supply_rule: String,
    pub contact_ammunition_floor: f64,
    pub accidental_contact_fraction: f64,
    pub contact_opportunity_model: String,
    pub organized_action_architecture: String,
}

impl Default for CombatConfig {
    fn default() -> Self {
        Self {
            interval_hours: 2.0,
            base_attrition_rate: 0.012,
            stochastic_sigma: 0.42,
            max_loss_fraction: 0.12,
            cohesion_loss_multiplier: 1.8,
            readiness_cost_multiplier: 1.1,
            supply_per_person_hour: 0.035,
            ineffective_cohesion: 0.22,
            ineffective_readiness: 0.18,
            disengagement_base: 0.16,
            surprise_initiative: 0.28,
            civilian_exposure_rate: 0.00008,
            momentum_learning_rate: 0.12,
            reinforcement_threshold: 0.06,
            contact_supply_rule: "no_gate".to_string(),
            contact_ammunition_floor: 0.05,
            accidental_contact_fraction: 0.05,
            contact_opportunity_model: "directional_pairwise".to_string(),
            organized_action_architecture: "multichannel_v5".to_string(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct OrganizationEcologyConfig {
    pub enabled: bool,
    pub interval_days: f64,
    pub proto_base_hazard: f64,
    pub birth_base_hazard: f64,
    pub proto_decay_rate: f64,
    pub split_base_hazard: f64,
    pub merger_base_hazard: f64,
    pub collapse_base_hazard: f64,
    pub succession_base_hazard: f64,
    pub adaptation_rate: f64,
    pub mutation_sigma: f64,
    pub minimum_proto_members: usize,
    pub minimum_proto_represented_population: f64,
    pub minimum_split_represented_population: f64,
    pub minimum_formation_personnel: f64,
    pub fighter_conversion_fraction: f64,
    pub recruitment_subcohorts: usize,
    pub recruitment_requires_access: bool,
    pub local_foothold_memory_days: f64,
    pub local_foothold_viability_threshold: f64,
    pub local_rootedness_weight: f64,
    pub exit_sympathy_retention: f64,
    pub onset_resource_fraction: f64,
    pub recruitment_diversity_penalty: f64,
    pub cohesion_loss_memory: f64,
    pub observed_active_intervals: BTreeMap<String, Vec<[f64; 2]>>,
}

impl Default for OrganizationEcologyConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_days: 7.0,
            proto_base_hazard: 0.004,
            birth_base_hazard: 0.003,
            proto_decay_rate: 0.08,
            split_base_hazard: 0.002,
            merger_base_hazard: 0.015,
            collapse_base_hazard: 0.004,
            succession_base_hazard: 0.006,
            adaptation_rate: 0.12,
            mutation_sigma: 0.035,
            minimum_proto_members: 3,
            minimum_proto_represented_population: 1000.0,
            minimum_split_represented_population: 1500.0,
            minimum_formation_personnel: 75.0,
            fighter_conversion_fraction: 0.08,
            recruitment_subcohorts: 20,
            recruitment_requires_access: true,
            local_foothold_memory_days: 45.0,
            local_foothold_viability_threshold: 0.20,
            local_rootedness_weight: 0.75,
            exit_sympathy_retention: 1.0,
            onset_resource_fraction: 0.18,
            recruitment_diversity_penalty: 0.12,
            cohesion_loss_memory: 0.2,
            observed_active_intervals: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RelationshipConfig {
    pub memory_half_life_days: f64,
    pub rivalry_threshold: f64,
    pub hostility_threshold: f64,
    pub escalation_base_hazard: f64,
    pub deescalation_reference_rate: f64,
    pub split_rivalry_memory: f64,
}
impl Default for RelationshipConfig {
    fn default() -> Self {
        Self {
            memory_half_life_days: 90.0,
            rivalry_threshold: 0.22,
            hostility_threshold: 0.58,
            escalation_base_hazard: 0.015,
            deescalation_reference_rate: 0.01,
            split_rivalry_memory: 0.30,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct NonstateGovernanceConfig {
    pub enabled: bool,
    pub gain_per_30_days: f64,
    pub decay_per_30_days: f64,
    pub minimum_local_capacity: f64,
}
impl Default for NonstateGovernanceConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            gain_per_30_days: 0.022,
            decay_per_30_days: 0.035,
            minimum_local_capacity: 0.02,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AccessRestrictionConfig {
    pub enabled: bool,
    pub build_rate: f64,
    pub decay_per_day: f64,
    pub hostile_movement_penalty: f64,
    pub civilian_utility_penalty: f64,
    pub economic_penalty: f64,
}
impl Default for AccessRestrictionConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            build_rate: 0.18,
            decay_per_day: 0.025,
            hostile_movement_penalty: 1.5,
            civilian_utility_penalty: 1.1,
            economic_penalty: 0.004,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CivilianDynamicsConfig {
    pub voluntary_move_given_opportunity: f64,
    pub displacement_violence_threshold: f64,
    pub forced_displacement_reference_rate: f64,
    pub return_reference_rate: f64,
    pub resettlement_reference_rate: f64,
    pub minimum_resettlement_days: f64,
    pub fatality_fraction_of_direct_harm: f64,
    pub injury_fraction_of_direct_harm: f64,
}
impl Default for CivilianDynamicsConfig {
    fn default() -> Self {
        Self {
            voluntary_move_given_opportunity: 0.08,
            displacement_violence_threshold: 0.35,
            forced_displacement_reference_rate: 0.015,
            return_reference_rate: 0.01,
            resettlement_reference_rate: 0.002,
            minimum_resettlement_days: 90.0,
            fatality_fraction_of_direct_harm: 0.20,
            injury_fraction_of_direct_harm: 0.80,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PoliticalOrderConfig {
    pub enabled: bool,
    pub interval_days: f64,
    pub election_interval_days: f64,
    pub federal_policy_budget: f64,
    pub public_budget_share: f64,
    pub patronage_share: f64,
    pub private_diversion_share: f64,
    pub capacity_learning_rate: f64,
    pub capacity_decay_rate: f64,
    pub patronage_capacity_damage: f64,
    pub patronage_decay_rate: f64,
    pub elite_broker_share: f64,
    pub peaceful_channel_strength: f64,
    pub election_turnout_sensitivity: f64,
}
impl Default for PoliticalOrderConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_days: 30.0,
            election_interval_days: 1460.0,
            federal_policy_budget: 120000.0,
            public_budget_share: 0.68,
            patronage_share: 0.22,
            private_diversion_share: 0.10,
            capacity_learning_rate: 0.012,
            capacity_decay_rate: 0.008,
            patronage_capacity_damage: 0.018,
            patronage_decay_rate: 0.035,
            elite_broker_share: 0.35,
            peaceful_channel_strength: 0.5,
            election_turnout_sensitivity: 1.4,
        }
    }
}

/// Endogenous state-capacity regeneration for the post-parity Rust theory core.
///
/// This process is deliberately separate from generic governance output. It
/// represents the stocks that were missing from the parity-era model:
/// recruitment/training of replacement security personnel, rebuilding of
/// local administrative capacity, and police/intelligence penetration of a
/// clandestine insurgent organization.  The default is disabled so archived
/// parity-certified configurations remain reproducible; theory-v2 experiments
/// enable it explicitly.
#[derive(Clone, Debug, PartialEq)]
pub struct StateRegenerationConfig {
    pub enabled: bool,
    pub interval_days: f64,
    /// Daily fraction of local population entering the state security
    /// training pipeline before legitimacy/access gating.
    pub security_recruitment_rate: f64,
    /// First-order daily graduation rate from trainee to trained reserve.
    pub security_training_rate: f64,
    /// Daily reserve loss through aging, attrition, and non-retention.
    pub reserve_attrition_rate: f64,
    /// Cost charged at entry to the training pipeline.
    pub training_cost_per_person: f64,
    /// Cost charged when a trained replacement is assigned to a unit/post.
    pub deployment_cost_per_person: f64,
    /// Share of deployable replacements preferentially assigned to police.
    pub police_allocation_share: f64,
    /// Police target as fraction of locality population, bounded by the
    /// canonical 15--300 post staffing envelope.
    pub police_target_population_fraction: f64,
    /// Multiplier on the configured national military personnel target.
    pub military_target_multiplier: f64,
    /// Daily rate at which damaged administrative capacity rebuilds toward
    /// its static locality ceiling when resources and absorptive conditions
    /// permit.
    pub administrative_rebuild_rate: f64,
    /// Daily conflict-driven decay of administrative capacity.
    pub administrative_decay_rate: f64,
    /// Capital required to restore one unit of administrative capacity for
    /// one represented resident.
    pub administrative_rebuild_cost: f64,
    /// Weights controlling local absorptive capacity for rebuilding.
    pub rebuild_security_weight: f64,
    pub rebuild_integrity_weight: f64,
    pub rebuild_legitimacy_weight: f64,
    /// Daily acquisition and decay rates of state intelligence penetration.
    pub intelligence_gain_rate: f64,
    pub intelligence_decay_rate: f64,
    /// Component weights for police presence, public cooperation, and local
    /// administrative reach in the intelligence target.
    pub intelligence_police_weight: f64,
    pub intelligence_cooperation_weight: f64,
    pub intelligence_administration_weight: f64,
    /// Daily hazard by which intelligence penetration disrupts rooted armed
    /// membership.  This acts on membership, not merely fielded formations.
    pub underground_disruption_rate: f64,
    /// Fraction of disrupted membership retained as latent sympathy rather
    /// than erased from the social state.
    pub disrupted_sympathy_retention: f64,
}

impl Default for StateRegenerationConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            interval_days: 14.0,
            security_recruitment_rate: 2.0e-6,
            security_training_rate: 1.0 / 90.0,
            reserve_attrition_rate: 5.0e-4,
            training_cost_per_person: 8.0,
            deployment_cost_per_person: 12.0,
            police_allocation_share: 0.55,
            police_target_population_fraction: 0.0015,
            military_target_multiplier: 1.0,
            administrative_rebuild_rate: 0.0015,
            administrative_decay_rate: 0.00015,
            administrative_rebuild_cost: 0.20,
            rebuild_security_weight: 0.35,
            rebuild_integrity_weight: 0.35,
            rebuild_legitimacy_weight: 0.30,
            intelligence_gain_rate: 0.010,
            intelligence_decay_rate: 0.003,
            intelligence_police_weight: 0.45,
            intelligence_cooperation_weight: 0.35,
            intelligence_administration_weight: 0.20,
            underground_disruption_rate: 0.002,
            disrupted_sympathy_retention: 0.70,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ForeignAffairsConfig {
    pub enabled: bool,
    pub interval_days: f64,
    pub neighbor_count: usize,
    pub migration_rate: f64,
    pub return_rate: f64,
    pub diaspora_remittance_rate: f64,
    pub diaspora_information_rate: f64,
    pub support_budget_fraction: f64,
    pub intervention_base_hazard: f64,
    pub rival_reaction: f64,
    pub interpreter_effect: f64,
    pub belief_noise: f64,
    pub host_transfer_efficiency: f64,
    pub host_crowding_out: f64,
    pub willingness_cost_weight: f64,
    pub willingness_casualty_weight: f64,
    pub withdrawal_threshold: f64,
    pub withdrawal_rate: f64,
}
impl Default for ForeignAffairsConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_days: 30.0,
            neighbor_count: 5,
            migration_rate: 0.002,
            return_rate: 0.015,
            diaspora_remittance_rate: 0.025,
            diaspora_information_rate: 0.08,
            support_budget_fraction: 0.002,
            intervention_base_hazard: 0.015,
            rival_reaction: 0.35,
            interpreter_effect: 0.4,
            belief_noise: 0.18,
            host_transfer_efficiency: 0.35,
            host_crowding_out: 0.25,
            willingness_cost_weight: 0.35,
            willingness_casualty_weight: 0.45,
            withdrawal_threshold: 0.28,
            withdrawal_rate: 0.2,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PeaceProcessConfig {
    pub enabled: bool,
    pub interval_days: f64,
    pub negotiation_base_hazard: f64,
    pub agreement_base_hazard: f64,
    pub ceasefire_violation_rate: f64,
    pub implementation_rate: f64,
    pub demobilization_rate: f64,
    pub recurrence_base_hazard: f64,
    pub battlefield_expectation_weight: f64,
    pub credibility_weight: f64,
    pub fragmentation_penalty: f64,
    pub spoiler_penalty: f64,
    pub foreign_influence_weight: f64,
    pub political_capital_retention: f64,
    pub resource_conversion_rate: f64,
}
impl Default for PeaceProcessConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            interval_days: 30.0,
            negotiation_base_hazard: 0.08,
            agreement_base_hazard: 0.12,
            ceasefire_violation_rate: 0.025,
            implementation_rate: 0.055,
            demobilization_rate: 0.10,
            recurrence_base_hazard: 0.0025,
            battlefield_expectation_weight: 1.0,
            credibility_weight: 1.1,
            fragmentation_penalty: 1.4,
            spoiler_penalty: 1.0,
            foreign_influence_weight: 0.6,
            political_capital_retention: 0.68,
            resource_conversion_rate: 0.72,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RecordingConfig {
    pub enabled: bool,
    pub base_logit: f64,
    pub severity_weight: f64,
    pub access_weight: f64,
    pub remoteness_penalty: f64,
    pub severity_noise: f64,
    pub geocoding_error_rate: f64,
    pub geocoding_scale_km: f64,
    pub false_event_rate: f64,
    pub source_channels: BTreeMap<String, BTreeMap<String, f64>>,
}
impl Default for RecordingConfig {
    fn default() -> Self {
        let mut default = BTreeMap::new();
        default.insert("base_logit".to_string(), -1.5);
        default.insert("severity_weight".to_string(), 1.8);
        default.insert("access_weight".to_string(), 1.2);
        default.insert("remoteness_penalty".to_string(), 0.9);
        default.insert("severity_noise".to_string(), 0.12);
        default.insert("geocoding_error_rate".to_string(), 0.12);
        default.insert("geocoding_scale_km".to_string(), 2.0);
        let mut channels = BTreeMap::new();
        channels.insert("default".to_string(), default.clone());
        channels.insert("contact".to_string(), default.clone());
        channels.insert("patrol".to_string(), default.clone());
        channels.insert("administrative".to_string(), default.clone());
        channels.insert("organized_action".to_string(), default);
        Self {
            enabled: true,
            base_logit: -1.5,
            severity_weight: 1.8,
            access_weight: 1.2,
            remoteness_penalty: 0.9,
            severity_noise: 0.12,
            geocoding_error_rate: 0.12,
            geocoding_scale_km: 2.0,
            false_event_rate: 0.0,
            source_channels: channels,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct SimulationConfig {
    pub seed: u64,
    pub initialization_seed: Option<u64>,
    pub horizon_days: f64,
    pub agent_count: usize,
    pub locality_count: usize,
    pub burn_in_days: f64,
    pub include_insurgency: bool,
    pub initial_insurgent_share: f64,
    pub observation_noise: f64,
    pub reporting_error: f64,
    pub movement_rate: f64,
    pub recruitment_rate: f64,
    pub membership_exit_rate: f64,
    pub contact_rate: f64,
    pub organized_action_rate: f64,
    pub random_stream_namespace: String,
    pub output_mode: String,
    pub intervals: ProcessIntervals,
    pub social_network: SocialNetworkConfig,
    pub physical: PhysicalModelConfig,
    pub geography: GeographyConfig,
    pub logistics: LogisticsConfig,
    pub force_structure: ForceStructureConfig,
    pub information: InformationConfig,
    pub combat: CombatConfig,
    pub organization_ecology: OrganizationEcologyConfig,
    pub relationships: RelationshipConfig,
    pub nonstate_governance: NonstateGovernanceConfig,
    pub access_restriction: AccessRestrictionConfig,
    pub civilian_dynamics: CivilianDynamicsConfig,
    pub political_order: PoliticalOrderConfig,
    pub state_regeneration: StateRegenerationConfig,
    pub foreign_affairs: ForeignAffairsConfig,
    pub peace_process: PeaceProcessConfig,
    pub recording: RecordingConfig,
    pub extras: BTreeMap<String, JsonValue>,
}

impl Default for SimulationConfig {
    fn default() -> Self {
        Self {
            seed: 20260902,
            initialization_seed: None,
            horizon_days: 365.0,
            agent_count: 75000,
            locality_count: 72,
            burn_in_days: 0.0,
            include_insurgency: true,
            initial_insurgent_share: 0.001,
            observation_noise: 0.08,
            reporting_error: 0.12,
            movement_rate: 0.015,
            recruitment_rate: 0.001,
            membership_exit_rate: 0.001,
            contact_rate: 0.08,
            organized_action_rate: 0.08,
            random_stream_namespace: "baseline".to_string(),
            output_mode: "forensic".to_string(),
            intervals: ProcessIntervals::default(),
            social_network: SocialNetworkConfig::default(),
            physical: PhysicalModelConfig::default(),
            geography: GeographyConfig::default(),
            logistics: LogisticsConfig::default(),
            force_structure: ForceStructureConfig::default(),
            information: InformationConfig::default(),
            combat: CombatConfig::default(),
            organization_ecology: OrganizationEcologyConfig::default(),
            relationships: RelationshipConfig::default(),
            nonstate_governance: NonstateGovernanceConfig::default(),
            access_restriction: AccessRestrictionConfig::default(),
            civilian_dynamics: CivilianDynamicsConfig::default(),
            political_order: PoliticalOrderConfig::default(),
            state_regeneration: StateRegenerationConfig::default(),
            foreign_affairs: ForeignAffairsConfig::default(),
            peace_process: PeaceProcessConfig::default(),
            recording: RecordingConfig::default(),
            extras: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConfigError {
    Json(String),
    Missing(String),
    Invalid(String),
    Io(String),
}
impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Json(v) => write!(f, "configuration JSON: {v}"),
            Self::Missing(v) => write!(f, "missing configuration value: {v}"),
            Self::Invalid(v) => write!(f, "invalid configuration: {v}"),
            Self::Io(v) => write!(f, "configuration I/O: {v}"),
        }
    }
}
impl std::error::Error for ConfigError {}
impl From<JsonError> for ConfigError {
    fn from(value: JsonError) -> Self {
        Self::Json(value.to_string())
    }
}

impl SimulationConfig {
    pub fn load(path: impl AsRef<Path>) -> Result<Self, ConfigError> {
        let text = fs::read_to_string(path.as_ref()).map_err(|e| ConfigError::Io(e.to_string()))?;
        Self::from_json(&json::parse(&text)?)
    }

    pub fn from_json(value: &JsonValue) -> Result<Self, ConfigError> {
        let object = value
            .as_object()
            .ok_or_else(|| ConfigError::Invalid("root must be an object".to_string()))?;
        let mut config = Self::default();
        if let Some(v) = object.get("seed") {
            config.seed = required_u64(v, "seed")?;
        }
        if let Some(v) = object.get("initialization_seed") {
            config.initialization_seed = if matches!(v, JsonValue::Null) {
                None
            } else {
                Some(required_u64(v, "initialization_seed")?)
            };
        }
        set_f64(object, "horizon_days", &mut config.horizon_days)?;
        set_usize(object, "agent_count", &mut config.agent_count)?;
        set_usize(object, "locality_count", &mut config.locality_count)?;
        set_f64(object, "burn_in_days", &mut config.burn_in_days)?;
        set_bool(object, "include_insurgency", &mut config.include_insurgency)?;
        set_f64(
            object,
            "initial_insurgent_share",
            &mut config.initial_insurgent_share,
        )?;
        set_f64(object, "observation_noise", &mut config.observation_noise)?;
        set_f64(object, "reporting_error", &mut config.reporting_error)?;
        set_f64(object, "movement_rate", &mut config.movement_rate)?;
        set_f64(object, "recruitment_rate", &mut config.recruitment_rate)?;
        set_f64(
            object,
            "membership_exit_rate",
            &mut config.membership_exit_rate,
        )?;
        set_f64(object, "contact_rate", &mut config.contact_rate)?;
        set_f64(
            object,
            "organized_action_rate",
            &mut config.organized_action_rate,
        )?;
        set_string(
            object,
            "random_stream_namespace",
            &mut config.random_stream_namespace,
        )?;
        set_string(object, "output_mode", &mut config.output_mode)?;
        if let Some(value) = object.get("intervals") {
            apply_intervals(value, &mut config.intervals)?;
        }
        if let Some(value) = object.get("social_network") {
            apply_social(value, &mut config.social_network)?;
        }
        if let Some(value) = object.get("physical") {
            apply_physical(value, &mut config.physical)?;
        }
        if let Some(value) = object.get("geography") {
            apply_geography(value, &mut config.geography)?;
        }
        if let Some(value) = object.get("logistics") {
            apply_logistics(value, &mut config.logistics)?;
        }
        if let Some(value) = object.get("force_structure") {
            apply_force(value, &mut config.force_structure)?;
        }
        if let Some(value) = object.get("information") {
            apply_information(value, &mut config.information)?;
        }
        if let Some(value) = object.get("combat") {
            apply_combat(value, &mut config.combat)?;
        }
        if let Some(value) = object.get("organization_ecology") {
            apply_ecology(value, &mut config.organization_ecology)?;
        }
        if let Some(value) = object.get("relationships") {
            apply_relationships(value, &mut config.relationships)?;
        }
        if let Some(value) = object.get("nonstate_governance") {
            apply_nonstate(value, &mut config.nonstate_governance)?;
        }
        if let Some(value) = object.get("access_restriction") {
            apply_access(value, &mut config.access_restriction)?;
        }
        if let Some(value) = object.get("civilian_dynamics") {
            apply_civilian(value, &mut config.civilian_dynamics)?;
        }
        if let Some(value) = object.get("political_order") {
            apply_political(value, &mut config.political_order)?;
        }
        if let Some(value) = object.get("state_regeneration") {
            apply_state_regeneration(value, &mut config.state_regeneration)?;
        }
        if let Some(value) = object.get("foreign_affairs") {
            apply_foreign(value, &mut config.foreign_affairs)?;
        }
        if let Some(value) = object.get("peace_process") {
            apply_peace(value, &mut config.peace_process)?;
        }
        if let Some(value) = object.get("recording") {
            apply_recording(value, &mut config.recording)?;
        }
        let known = [
            "seed",
            "initialization_seed",
            "horizon_days",
            "agent_count",
            "locality_count",
            "burn_in_days",
            "include_insurgency",
            "initial_insurgent_share",
            "observation_noise",
            "reporting_error",
            "movement_rate",
            "recruitment_rate",
            "membership_exit_rate",
            "contact_rate",
            "organized_action_rate",
            "random_stream_namespace",
            "output_mode",
            "intervals",
            "social_network",
            "physical",
            "geography",
            "logistics",
            "force_structure",
            "information",
            "combat",
            "organization_ecology",
            "relationships",
            "nonstate_governance",
            "access_restriction",
            "civilian_dynamics",
            "political_order",
            "state_regeneration",
            "foreign_affairs",
            "peace_process",
            "recording",
        ];
        for (key, value) in object {
            if !known.contains(&key.as_str()) {
                config.extras.insert(key.clone(), value.clone());
            }
        }
        config.validate()?;
        Ok(config)
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.agent_count == 0 {
            return Err(ConfigError::Invalid(
                "agent_count must be positive".to_string(),
            ));
        }
        if self.locality_count == 0 {
            return Err(ConfigError::Invalid(
                "locality_count must be positive".to_string(),
            ));
        }
        for (name, value) in [
            ("horizon_days", self.horizon_days),
            ("burn_in_days", self.burn_in_days),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(ConfigError::Invalid(format!(
                    "{name} must be finite and non-negative"
                )));
            }
        }
        if !(0.0..=1.0).contains(&self.initial_insurgent_share)
            || !self.initial_insurgent_share.is_finite()
        {
            return Err(ConfigError::Invalid(
                "initial_insurgent_share must be in [0,1]".to_string(),
            ));
        }
        if !["forensic", "ensemble", "calibration"].contains(&self.output_mode.as_str()) {
            return Err(ConfigError::Invalid(format!(
                "unsupported output_mode {}",
                self.output_mode
            )));
        }
        for (name, value) in self.intervals.as_pairs() {
            if !value.is_finite() || value <= 0.0 {
                return Err(ConfigError::Invalid(format!(
                    "interval {name} must be positive"
                )));
            }
        }
        for (name, value) in [
            (
                "organization_ecology.interval_days",
                self.organization_ecology.interval_days,
            ),
            (
                "political_order.interval_days",
                self.political_order.interval_days,
            ),
            (
                "state_regeneration.interval_days",
                self.state_regeneration.interval_days,
            ),
            (
                "foreign_affairs.interval_days",
                self.foreign_affairs.interval_days,
            ),
            (
                "peace_process.interval_days",
                self.peace_process.interval_days,
            ),
            ("combat.interval_hours", self.combat.interval_hours),
        ] {
            if !value.is_finite() || value <= 0.0 {
                return Err(ConfigError::Invalid(format!("{name} must be positive")));
            }
        }
        if self.physical.village_microzones == 0
            || self.physical.town_microzones == 0
            || self.physical.city_microzones == 0
        {
            return Err(ConfigError::Invalid(
                "physical microzone counts must be positive".to_string(),
            ));
        }
        if self.geography.nearest_neighbors == 0 {
            return Err(ConfigError::Invalid(
                "geography.nearest_neighbors must be positive".to_string(),
            ));
        }
        if self.social_network.minimum_community_size == 0
            || self.social_network.maximum_community_size
                < self.social_network.minimum_community_size
        {
            return Err(ConfigError::Invalid(
                "social community size bounds are invalid".to_string(),
            ));
        }
        for (name, value) in [
            ("initial_insurgent_share", self.initial_insurgent_share),
            ("observation_noise", self.observation_noise),
            ("reporting_error", self.reporting_error),
            ("movement_rate", self.movement_rate),
            ("recruitment_rate", self.recruitment_rate),
            ("membership_exit_rate", self.membership_exit_rate),
            ("contact_rate", self.contact_rate),
            ("organized_action_rate", self.organized_action_rate),
            (
                "state_regeneration.security_recruitment_rate",
                self.state_regeneration.security_recruitment_rate,
            ),
            (
                "state_regeneration.security_training_rate",
                self.state_regeneration.security_training_rate,
            ),
            (
                "state_regeneration.reserve_attrition_rate",
                self.state_regeneration.reserve_attrition_rate,
            ),
            (
                "state_regeneration.training_cost_per_person",
                self.state_regeneration.training_cost_per_person,
            ),
            (
                "state_regeneration.deployment_cost_per_person",
                self.state_regeneration.deployment_cost_per_person,
            ),
            (
                "state_regeneration.police_target_population_fraction",
                self.state_regeneration.police_target_population_fraction,
            ),
            (
                "state_regeneration.military_target_multiplier",
                self.state_regeneration.military_target_multiplier,
            ),
            (
                "state_regeneration.administrative_rebuild_rate",
                self.state_regeneration.administrative_rebuild_rate,
            ),
            (
                "state_regeneration.administrative_decay_rate",
                self.state_regeneration.administrative_decay_rate,
            ),
            (
                "state_regeneration.administrative_rebuild_cost",
                self.state_regeneration.administrative_rebuild_cost,
            ),
            (
                "state_regeneration.intelligence_gain_rate",
                self.state_regeneration.intelligence_gain_rate,
            ),
            (
                "state_regeneration.intelligence_decay_rate",
                self.state_regeneration.intelligence_decay_rate,
            ),
            (
                "state_regeneration.underground_disruption_rate",
                self.state_regeneration.underground_disruption_rate,
            ),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(ConfigError::Invalid(format!(
                    "{name} must be finite and non-negative"
                )));
            }
        }
        for (name, value) in [
            (
                "state_regeneration.police_allocation_share",
                self.state_regeneration.police_allocation_share,
            ),
            (
                "state_regeneration.rebuild_security_weight",
                self.state_regeneration.rebuild_security_weight,
            ),
            (
                "state_regeneration.rebuild_integrity_weight",
                self.state_regeneration.rebuild_integrity_weight,
            ),
            (
                "state_regeneration.rebuild_legitimacy_weight",
                self.state_regeneration.rebuild_legitimacy_weight,
            ),
            (
                "state_regeneration.intelligence_police_weight",
                self.state_regeneration.intelligence_police_weight,
            ),
            (
                "state_regeneration.intelligence_cooperation_weight",
                self.state_regeneration.intelligence_cooperation_weight,
            ),
            (
                "state_regeneration.intelligence_administration_weight",
                self.state_regeneration.intelligence_administration_weight,
            ),
            (
                "state_regeneration.disrupted_sympathy_retention",
                self.state_regeneration.disrupted_sympathy_retention,
            ),
        ] {
            if !value.is_finite() || !(0.0..=1.0).contains(&value) {
                return Err(ConfigError::Invalid(format!(
                    "{name} must be finite and in [0,1]"
                )));
            }
        }
        let rebuild_weight_sum = self.state_regeneration.rebuild_security_weight
            + self.state_regeneration.rebuild_integrity_weight
            + self.state_regeneration.rebuild_legitimacy_weight;
        let intelligence_weight_sum = self.state_regeneration.intelligence_police_weight
            + self.state_regeneration.intelligence_cooperation_weight
            + self.state_regeneration.intelligence_administration_weight;
        for (name, sum) in [
            ("state_regeneration rebuild weights", rebuild_weight_sum),
            ("state_regeneration intelligence weights", intelligence_weight_sum),
        ] {
            if !sum.is_finite() || (sum - 1.0).abs() > 1.0e-9 {
                return Err(ConfigError::Invalid(format!(
                    "{name} must sum to 1.0"
                )));
            }
        }
        validate_json_numbers(&self.to_json(), "config")?;
        if self.locality_count > (u32::MAX as usize) || self.agent_count > (u32::MAX as usize) {
            return Err(ConfigError::Invalid(
                "counts exceed u32 ID space".to_string(),
            ));
        }
        Ok(())
    }

    pub fn to_json(&self) -> JsonValue {
        let mut root = JsonValue::object();
        root.insert("seed", JsonValue::integer(self.seed));
        if let Some(seed) = self.initialization_seed {
            root.insert("initialization_seed", JsonValue::integer(seed));
        } else {
            root.insert("initialization_seed", JsonValue::Null);
        }
        root.insert("horizon_days", JsonValue::number(self.horizon_days));
        root.insert("agent_count", JsonValue::integer(self.agent_count as u64));
        root.insert(
            "locality_count",
            JsonValue::integer(self.locality_count as u64),
        );
        root.insert("burn_in_days", JsonValue::number(self.burn_in_days));
        root.insert(
            "include_insurgency",
            JsonValue::Bool(self.include_insurgency),
        );
        root.insert(
            "initial_insurgent_share",
            JsonValue::number(self.initial_insurgent_share),
        );
        root.insert(
            "observation_noise",
            JsonValue::number(self.observation_noise),
        );
        root.insert("reporting_error", JsonValue::number(self.reporting_error));
        root.insert("movement_rate", JsonValue::number(self.movement_rate));
        root.insert("recruitment_rate", JsonValue::number(self.recruitment_rate));
        root.insert(
            "membership_exit_rate",
            JsonValue::number(self.membership_exit_rate),
        );
        root.insert("contact_rate", JsonValue::number(self.contact_rate));
        root.insert(
            "organized_action_rate",
            JsonValue::number(self.organized_action_rate),
        );
        root.insert(
            "random_stream_namespace",
            JsonValue::string(&self.random_stream_namespace),
        );
        root.insert("output_mode", JsonValue::string(&self.output_mode));
        root.insert("intervals", self.intervals.to_json());
        root.insert("social_network", self.social_network.to_json());
        root.insert("physical", self.physical.to_json());
        root.insert("geography", self.geography.to_json());
        root.insert("logistics", self.logistics.to_json());
        root.insert("force_structure", self.force_structure.to_json());
        root.insert("information", self.information.to_json());
        root.insert("combat", self.combat.to_json());
        root.insert("organization_ecology", self.organization_ecology.to_json());
        root.insert("relationships", self.relationships.to_json());
        root.insert("nonstate_governance", self.nonstate_governance.to_json());
        root.insert("access_restriction", self.access_restriction.to_json());
        root.insert("civilian_dynamics", self.civilian_dynamics.to_json());
        root.insert("political_order", self.political_order.to_json());
        // Preserve the canonical JSON/hash of the archived parity-era model
        // when the post-parity state-regeneration extension is untouched.
        // Any non-default v2 configuration emits the complete section.
        if self.state_regeneration != StateRegenerationConfig::default() {
            root.insert("state_regeneration", self.state_regeneration.to_json());
        }
        root.insert("foreign_affairs", self.foreign_affairs.to_json());
        root.insert("peace_process", self.peace_process.to_json());
        root.insert("recording", self.recording.to_json());
        for (key, value) in &self.extras {
            root.insert(key, value.clone());
        }
        root
    }

    pub fn canonical_hash(&self) -> String {
        crate::sha256::digest_hex(self.to_json().to_compact().as_bytes())
    }
}

impl ProcessIntervals {
    fn as_pairs(&self) -> [(&'static str, f64); 14] {
        [
            ("contact", self.contact),
            ("command", self.command),
            ("force_movement", self.force_movement),
            ("logistics", self.logistics),
            ("information", self.information),
            ("patrol", self.patrol),
            ("physical_refresh", self.physical_refresh),
            ("beliefs", self.beliefs),
            ("social_influence", self.social_influence),
            ("mobility", self.mobility),
            ("recruitment", self.recruitment),
            ("governance", self.governance),
            ("economy", self.economy),
            ("checkpoint", self.checkpoint),
        ]
    }
    fn to_json(&self) -> JsonValue {
        object_f64! { "contact" => self.contact, "command" => self.command, "force_movement" => self.force_movement, "logistics" => self.logistics, "information" => self.information, "patrol" => self.patrol, "physical_refresh" => self.physical_refresh, "beliefs" => self.beliefs, "social_influence" => self.social_influence, "mobility" => self.mobility, "recruitment" => self.recruitment, "governance" => self.governance, "economy" => self.economy, "checkpoint" => self.checkpoint }
    }
}

impl SocialNetworkConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"community_size_unit_population"=>self.community_size_unit_population,"mean_social_degree"=>self.mean_social_degree,"bridge_fraction"=>self.bridge_fraction,"behavior_update_rate"=>self.behavior_update_rate,"household_tie_strength"=>self.household_tie_strength,"community_tie_strength"=>self.community_tie_strength,"bridge_tie_strength"=>self.bridge_tie_strength,"behavior_exposure_weight"=>self.behavior_exposure_weight,"recruitment_exposure_weight"=>self.recruitment_exposure_weight};
        o.insert(
            "target_community_size",
            JsonValue::integer(self.target_community_size as u64),
        );
        o.insert(
            "minimum_community_size",
            JsonValue::integer(self.minimum_community_size as u64),
        );
        o.insert(
            "maximum_community_size",
            JsonValue::integer(self.maximum_community_size as u64),
        );
        o.insert(
            "maximum_social_degree",
            JsonValue::integer(self.maximum_social_degree as u64),
        );
        o.insert(
            "language_topology_enabled",
            JsonValue::Bool(self.language_topology_enabled),
        );
        o
    }
}
impl PhysicalModelConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"extra_edge_probability"=>self.extra_edge_probability,"presence_memory_days"=>self.presence_memory_days,"response_decay_hours"=>self.response_decay_hours,"formation_presence_gain"=>self.formation_presence_gain,"patrol_memory_gain"=>self.patrol_memory_gain,"fixed_post_presence_gain"=>self.fixed_post_presence_gain,"zone_observation_noise"=>self.zone_observation_noise,"patrol_route_randomness"=>self.patrol_route_randomness};
        o.insert(
            "village_microzones",
            JsonValue::integer(self.village_microzones as u64),
        );
        o.insert(
            "town_microzones",
            JsonValue::integer(self.town_microzones as u64),
        );
        o.insert(
            "city_microzones",
            JsonValue::integer(self.city_microzones as u64),
        );
        o.insert(
            "adaptive_patrol_routing",
            JsonValue::Bool(self.adaptive_patrol_routing),
        );
        o
    }
}
impl GeographyConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"coordinate_jitter_km"=>self.coordinate_jitter_km};
        o.insert(
            "nearest_neighbors",
            JsonValue::integer(self.nearest_neighbors as u64),
        );
        o.insert(
            "district_hub_links",
            JsonValue::Bool(self.district_hub_links),
        );
        o.insert(
            "national_backbone",
            JsonValue::string(&self.national_backbone),
        );
        o
    }
}
impl LogisticsConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"formation_supply_days"=>self.formation_supply_days,"initial_supply_fraction"=>self.initial_supply_fraction,"presence_consumption_per_person_day"=>self.presence_consumption_per_person_day,"movement_consumption_per_person_km"=>self.movement_consumption_per_person_km,"patrol_consumption_per_person_hour"=>self.patrol_consumption_per_person_hour,"source_capacity_per_resident"=>self.source_capacity_per_resident,"source_daily_production_fraction"=>self.source_daily_production_fraction,"organization_sustainment_coverage"=>self.organization_sustainment_coverage,"resupply_trigger_fraction"=>self.resupply_trigger_fraction,"resupply_target_fraction"=>self.resupply_target_fraction,"shipment_loss_per_travel_hour"=>self.shipment_loss_per_travel_hour,"convoy_speed_factor"=>self.convoy_speed_factor,"readiness_degradation_rate"=>self.readiness_degradation_rate,"readiness_recovery_near_source"=>self.readiness_recovery_near_source,"readiness_recovery_remote"=>self.readiness_recovery_remote,"availability_recovery_rate"=>self.availability_recovery_rate,"reallocation_rate"=>self.reallocation_rate,"insurgent_frontier_weight"=>self.insurgent_frontier_weight,"insurgent_foothold_weight"=>self.insurgent_foothold_weight,"insurgent_stronghold_weight"=>self.insurgent_stronghold_weight,"reallocation_exploration_weight"=>self.reallocation_exploration_weight,"reallocation_strategic_weight"=>self.reallocation_strategic_weight,"reallocation_importance_weight"=>self.reallocation_importance_weight,"reallocation_travel_time_weight"=>self.reallocation_travel_time_weight,"route_interdiction_rate"=>self.route_interdiction_rate};
        o.insert(
            "source_capacity_model",
            JsonValue::string(&self.source_capacity_model),
        );
        o.insert(
            "reallocation_destination_scope",
            JsonValue::string(&self.reallocation_destination_scope),
        );
        o.insert(
            "route_interdiction_enabled",
            JsonValue::Bool(self.route_interdiction_enabled),
        );
        o
    }
}
impl ForceStructureConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"government_target_personnel"=>self.government_target_personnel,"insurgent_target_personnel"=>self.insurgent_target_personnel};
        o.insert("mode", JsonValue::string(&self.mode));
        o.insert(
            "maximum_initial_formations_per_side",
            JsonValue::integer(self.maximum_initial_formations_per_side as u64),
        );
        o
    }
}
impl CombatConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"interval_hours"=>self.interval_hours,"base_attrition_rate"=>self.base_attrition_rate,"stochastic_sigma"=>self.stochastic_sigma,"max_loss_fraction"=>self.max_loss_fraction,"cohesion_loss_multiplier"=>self.cohesion_loss_multiplier,"readiness_cost_multiplier"=>self.readiness_cost_multiplier,"supply_per_person_hour"=>self.supply_per_person_hour,"ineffective_cohesion"=>self.ineffective_cohesion,"ineffective_readiness"=>self.ineffective_readiness,"disengagement_base"=>self.disengagement_base,"surprise_initiative"=>self.surprise_initiative,"civilian_exposure_rate"=>self.civilian_exposure_rate,"momentum_learning_rate"=>self.momentum_learning_rate,"reinforcement_threshold"=>self.reinforcement_threshold,"contact_ammunition_floor"=>self.contact_ammunition_floor,"accidental_contact_fraction"=>self.accidental_contact_fraction};
        o.insert(
            "contact_supply_rule",
            JsonValue::string(&self.contact_supply_rule),
        );
        o.insert(
            "contact_opportunity_model",
            JsonValue::string(&self.contact_opportunity_model),
        );
        o.insert(
            "organized_action_architecture",
            JsonValue::string(&self.organized_action_architecture),
        );
        o
    }
}
impl InformationConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"prior_confidence"=>self.prior_confidence,"default_decay_rate"=>self.default_decay_rate,"mobile_decay_rate"=>self.mobile_decay_rate,"static_decay_rate"=>self.static_decay_rate,"road_decay_rate"=>self.road_decay_rate,"formation_decay_rate"=>self.formation_decay_rate,"true_positive_rate"=>self.true_positive_rate,"false_positive_rate"=>self.false_positive_rate,"attribution_error_rate"=>self.attribution_error_rate,"contact_true_positive_rate"=>self.contact_true_positive_rate,"contact_false_positive_rate"=>self.contact_false_positive_rate,"detection_pressure_bonus"=>self.detection_pressure_bonus,"detection_exposure_bonus"=>self.detection_exposure_bonus,"detection_language_bonus"=>self.detection_language_bonus,"detection_observability_bonus"=>self.detection_observability_bonus,"detection_terrain_penalty"=>self.detection_terrain_penalty,"detection_readiness_bonus"=>self.detection_readiness_bonus,"insurgent_concealment"=>self.insurgent_concealment,"civilian_report_rate"=>self.civilian_report_rate,"social_report_rate"=>self.social_report_rate,"administrative_report_rate"=>self.administrative_report_rate,"elite_report_rate"=>self.elite_report_rate,"member_report_rate"=>self.member_report_rate,"fixed_post_report_rate"=>self.fixed_post_report_rate,"patrol_report_rate"=>self.patrol_report_rate,"interpreter_report_rate"=>self.interpreter_report_rate,"relay_base_reliability"=>self.relay_base_reliability,"contradiction_penalty"=>self.contradiction_penalty,"contradiction_memory_days"=>self.contradiction_memory_days,"language_fusion_weight"=>self.language_fusion_weight,"corroboration_bonus"=>self.corroboration_bonus,"negative_report_confidence"=>self.negative_report_confidence,"positive_report_confidence"=>self.positive_report_confidence,"observation_retention_days"=>self.observation_retention_days};
        o.insert(
            "relay_max_hops",
            JsonValue::integer(self.relay_max_hops as u64),
        );
        for (k, m) in [
            ("source_trust", &self.source_trust),
            ("source_coverage", &self.source_coverage),
            ("source_latency_hours", &self.source_latency_hours),
            ("source_correlation", &self.source_correlation),
        ] {
            let mut x = JsonValue::object();
            for (a, b) in m {
                x.insert(a, JsonValue::number(*b));
            }
            o.insert(k, x);
        }
        o
    }
}
impl OrganizationEcologyConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"interval_days"=>self.interval_days,"proto_base_hazard"=>self.proto_base_hazard,"birth_base_hazard"=>self.birth_base_hazard,"proto_decay_rate"=>self.proto_decay_rate,"split_base_hazard"=>self.split_base_hazard,"merger_base_hazard"=>self.merger_base_hazard,"collapse_base_hazard"=>self.collapse_base_hazard,"succession_base_hazard"=>self.succession_base_hazard,"adaptation_rate"=>self.adaptation_rate,"mutation_sigma"=>self.mutation_sigma,"minimum_proto_represented_population"=>self.minimum_proto_represented_population,"minimum_split_represented_population"=>self.minimum_split_represented_population,"minimum_formation_personnel"=>self.minimum_formation_personnel,"fighter_conversion_fraction"=>self.fighter_conversion_fraction,"local_foothold_memory_days"=>self.local_foothold_memory_days,"local_foothold_viability_threshold"=>self.local_foothold_viability_threshold,"local_rootedness_weight"=>self.local_rootedness_weight,"exit_sympathy_retention"=>self.exit_sympathy_retention,"onset_resource_fraction"=>self.onset_resource_fraction,"recruitment_diversity_penalty"=>self.recruitment_diversity_penalty,"cohesion_loss_memory"=>self.cohesion_loss_memory};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o.insert(
            "minimum_proto_members",
            JsonValue::integer(self.minimum_proto_members as u64),
        );
        o.insert(
            "recruitment_subcohorts",
            JsonValue::integer(self.recruitment_subcohorts as u64),
        );
        o.insert(
            "recruitment_requires_access",
            JsonValue::Bool(self.recruitment_requires_access),
        );
        let mut intervals = JsonValue::object();
        for (k, ranges) in &self.observed_active_intervals {
            let mut values = JsonValue::Array(Vec::new());
            if let JsonValue::Array(items) = &mut values {
                for range in ranges {
                    let mut pair = JsonValue::Array(Vec::new());
                    if let JsonValue::Array(numbers) = &mut pair {
                        numbers.push(JsonValue::number(range[0]));
                        numbers.push(JsonValue::number(range[1]));
                    }
                    items.push(pair)
                }
            }
            intervals.insert(k, values)
        }
        o.insert("observed_active_intervals", intervals);
        o
    }
}
impl RelationshipConfig {
    fn to_json(&self) -> JsonValue {
        object_f64! {"memory_half_life_days"=>self.memory_half_life_days,"rivalry_threshold"=>self.rivalry_threshold,"hostility_threshold"=>self.hostility_threshold,"escalation_base_hazard"=>self.escalation_base_hazard,"deescalation_reference_rate"=>self.deescalation_reference_rate,"split_rivalry_memory"=>self.split_rivalry_memory}
    }
}
impl NonstateGovernanceConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"gain_per_30_days"=>self.gain_per_30_days,"decay_per_30_days"=>self.decay_per_30_days,"minimum_local_capacity"=>self.minimum_local_capacity};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o
    }
}
impl AccessRestrictionConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"build_rate"=>self.build_rate,"decay_per_day"=>self.decay_per_day,"hostile_movement_penalty"=>self.hostile_movement_penalty,"civilian_utility_penalty"=>self.civilian_utility_penalty,"economic_penalty"=>self.economic_penalty};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o
    }
}
impl CivilianDynamicsConfig {
    fn to_json(&self) -> JsonValue {
        object_f64! {"voluntary_move_given_opportunity"=>self.voluntary_move_given_opportunity,"displacement_violence_threshold"=>self.displacement_violence_threshold,"forced_displacement_reference_rate"=>self.forced_displacement_reference_rate,"return_reference_rate"=>self.return_reference_rate,"resettlement_reference_rate"=>self.resettlement_reference_rate,"minimum_resettlement_days"=>self.minimum_resettlement_days,"fatality_fraction_of_direct_harm"=>self.fatality_fraction_of_direct_harm,"injury_fraction_of_direct_harm"=>self.injury_fraction_of_direct_harm}
    }
}
impl PoliticalOrderConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"interval_days"=>self.interval_days,"election_interval_days"=>self.election_interval_days,"federal_policy_budget"=>self.federal_policy_budget,"public_budget_share"=>self.public_budget_share,"patronage_share"=>self.patronage_share,"private_diversion_share"=>self.private_diversion_share,"capacity_learning_rate"=>self.capacity_learning_rate,"capacity_decay_rate"=>self.capacity_decay_rate,"patronage_capacity_damage"=>self.patronage_capacity_damage,"patronage_decay_rate"=>self.patronage_decay_rate,"elite_broker_share"=>self.elite_broker_share,"peaceful_channel_strength"=>self.peaceful_channel_strength,"election_turnout_sensitivity"=>self.election_turnout_sensitivity};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o
    }
}
impl StateRegenerationConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {
            "interval_days"=>self.interval_days,
            "security_recruitment_rate"=>self.security_recruitment_rate,
            "security_training_rate"=>self.security_training_rate,
            "reserve_attrition_rate"=>self.reserve_attrition_rate,
            "training_cost_per_person"=>self.training_cost_per_person,
            "deployment_cost_per_person"=>self.deployment_cost_per_person,
            "police_allocation_share"=>self.police_allocation_share,
            "police_target_population_fraction"=>self.police_target_population_fraction,
            "military_target_multiplier"=>self.military_target_multiplier,
            "administrative_rebuild_rate"=>self.administrative_rebuild_rate,
            "administrative_decay_rate"=>self.administrative_decay_rate,
            "administrative_rebuild_cost"=>self.administrative_rebuild_cost,
            "rebuild_security_weight"=>self.rebuild_security_weight,
            "rebuild_integrity_weight"=>self.rebuild_integrity_weight,
            "rebuild_legitimacy_weight"=>self.rebuild_legitimacy_weight,
            "intelligence_gain_rate"=>self.intelligence_gain_rate,
            "intelligence_decay_rate"=>self.intelligence_decay_rate,
            "intelligence_police_weight"=>self.intelligence_police_weight,
            "intelligence_cooperation_weight"=>self.intelligence_cooperation_weight,
            "intelligence_administration_weight"=>self.intelligence_administration_weight,
            "underground_disruption_rate"=>self.underground_disruption_rate,
            "disrupted_sympathy_retention"=>self.disrupted_sympathy_retention
        };
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o
    }
}
impl ForeignAffairsConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"interval_days"=>self.interval_days,"migration_rate"=>self.migration_rate,"return_rate"=>self.return_rate,"diaspora_remittance_rate"=>self.diaspora_remittance_rate,"diaspora_information_rate"=>self.diaspora_information_rate,"support_budget_fraction"=>self.support_budget_fraction,"intervention_base_hazard"=>self.intervention_base_hazard,"rival_reaction"=>self.rival_reaction,"interpreter_effect"=>self.interpreter_effect,"belief_noise"=>self.belief_noise,"host_transfer_efficiency"=>self.host_transfer_efficiency,"host_crowding_out"=>self.host_crowding_out,"willingness_cost_weight"=>self.willingness_cost_weight,"willingness_casualty_weight"=>self.willingness_casualty_weight,"withdrawal_threshold"=>self.withdrawal_threshold,"withdrawal_rate"=>self.withdrawal_rate};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o.insert(
            "neighbor_count",
            JsonValue::number(self.neighbor_count as f64),
        );
        o
    }
}
impl PeaceProcessConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"interval_days"=>self.interval_days,"negotiation_base_hazard"=>self.negotiation_base_hazard,"agreement_base_hazard"=>self.agreement_base_hazard,"ceasefire_violation_rate"=>self.ceasefire_violation_rate,"implementation_rate"=>self.implementation_rate,"demobilization_rate"=>self.demobilization_rate,"recurrence_base_hazard"=>self.recurrence_base_hazard,"battlefield_expectation_weight"=>self.battlefield_expectation_weight,"credibility_weight"=>self.credibility_weight,"fragmentation_penalty"=>self.fragmentation_penalty,"spoiler_penalty"=>self.spoiler_penalty,"foreign_influence_weight"=>self.foreign_influence_weight,"political_capital_retention"=>self.political_capital_retention,"resource_conversion_rate"=>self.resource_conversion_rate};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        o
    }
}
impl RecordingConfig {
    fn to_json(&self) -> JsonValue {
        let mut o = object_f64! {"base_logit"=>self.base_logit,"severity_weight"=>self.severity_weight,"access_weight"=>self.access_weight,"remoteness_penalty"=>self.remoteness_penalty,"severity_noise"=>self.severity_noise,"geocoding_error_rate"=>self.geocoding_error_rate,"geocoding_scale_km"=>self.geocoding_scale_km,"false_event_rate"=>self.false_event_rate};
        o.insert("enabled", JsonValue::Bool(self.enabled));
        let mut channels = JsonValue::object();
        for (k, m) in &self.source_channels {
            let mut x = JsonValue::object();
            for (a, b) in m {
                x.insert(a, JsonValue::number(*b));
            }
            channels.insert(k, x);
        }
        o.insert("source_channels", channels);
        o
    }
}

// Nested JSON parsing helpers.  Unknown fields are retained at the root for
// forward compatibility; the runtime ignores fields it does not yet need.
fn object<'a>(
    value: &'a JsonValue,
    name: &str,
) -> Result<&'a BTreeMap<String, JsonValue>, ConfigError> {
    value
        .as_object()
        .ok_or_else(|| ConfigError::Invalid(format!("{name} must be an object")))
}
fn required_f64(value: &JsonValue, name: &str) -> Result<f64, ConfigError> {
    value
        .as_f64()
        .ok_or_else(|| ConfigError::Invalid(format!("{name} must be a finite number")))
}
fn required_u64(value: &JsonValue, name: &str) -> Result<u64, ConfigError> {
    value
        .as_u64()
        .ok_or_else(|| ConfigError::Invalid(format!("{name} must be a non-negative integer")))
}
fn required_usize(value: &JsonValue, name: &str) -> Result<usize, ConfigError> {
    required_u64(value, name)?
        .try_into()
        .map_err(|_| ConfigError::Invalid(format!("{name} is too large")))
}
fn required_bool(value: &JsonValue, name: &str) -> Result<bool, ConfigError> {
    value
        .as_bool()
        .ok_or_else(|| ConfigError::Invalid(format!("{name} must be boolean")))
}
fn required_string(value: &JsonValue, name: &str) -> Result<String, ConfigError> {
    value
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| ConfigError::Invalid(format!("{name} must be a string")))
}
fn validate_json_numbers(value: &JsonValue, path: &str) -> Result<(), ConfigError> {
    match value {
        JsonValue::Number(number) if !number.is_finite() => Err(ConfigError::Invalid(format!(
            "{path} must contain only finite numbers"
        ))),
        JsonValue::Array(values) => {
            for (index, item) in values.iter().enumerate() {
                validate_json_numbers(item, &format!("{path}[{index}]"))?;
            }
            Ok(())
        }
        JsonValue::Object(values) => {
            for (key, item) in values {
                validate_json_numbers(item, &format!("{path}.{key}"))?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}
fn set_f64(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
    target: &mut f64,
) -> Result<(), ConfigError> {
    if let Some(v) = object.get(key) {
        *target = required_f64(v, key)?;
    }
    Ok(())
}
fn set_usize(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
    target: &mut usize,
) -> Result<(), ConfigError> {
    if let Some(v) = object.get(key) {
        *target = required_usize(v, key)?;
    }
    Ok(())
}
fn set_bool(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
    target: &mut bool,
) -> Result<(), ConfigError> {
    if let Some(v) = object.get(key) {
        *target = required_bool(v, key)?;
    }
    Ok(())
}
fn set_string(
    object: &BTreeMap<String, JsonValue>,
    key: &str,
    target: &mut String,
) -> Result<(), ConfigError> {
    if let Some(v) = object.get(key) {
        *target = required_string(v, key)?;
    }
    Ok(())
}
macro_rules! apply_fields { ($value:expr, $target:expr, { $( $key:literal => $field:ident : $kind:ident ),* $(,)? }) => {{ let o=object($value,"nested configuration")?; $( if let Some(v)=o.get($key){ $target.$field = $kind(v,$key)?; } )* Ok(()) }}; }
fn apply_intervals(v: &JsonValue, t: &mut ProcessIntervals) -> Result<(), ConfigError> {
    apply_fields!(v,t,{"contact"=>contact:required_f64,"command"=>command:required_f64,"force_movement"=>force_movement:required_f64,"logistics"=>logistics:required_f64,"information"=>information:required_f64,"patrol"=>patrol:required_f64,"physical_refresh"=>physical_refresh:required_f64,"beliefs"=>beliefs:required_f64,"social_influence"=>social_influence:required_f64,"mobility"=>mobility:required_f64,"recruitment"=>recruitment:required_f64,"governance"=>governance:required_f64,"economy"=>economy:required_f64,"checkpoint"=>checkpoint:required_f64})
}
fn apply_social(v: &JsonValue, t: &mut SocialNetworkConfig) -> Result<(), ConfigError> {
    apply_fields!(v,t,{"community_size_unit_population"=>community_size_unit_population:required_f64,"target_community_size"=>target_community_size:required_usize,"minimum_community_size"=>minimum_community_size:required_usize,"maximum_community_size"=>maximum_community_size:required_usize,"mean_social_degree"=>mean_social_degree:required_f64,"maximum_social_degree"=>maximum_social_degree:required_usize,"bridge_fraction"=>bridge_fraction:required_f64,"behavior_update_rate"=>behavior_update_rate:required_f64,"household_tie_strength"=>household_tie_strength:required_f64,"community_tie_strength"=>community_tie_strength:required_f64,"bridge_tie_strength"=>bridge_tie_strength:required_f64,"behavior_exposure_weight"=>behavior_exposure_weight:required_f64,"recruitment_exposure_weight"=>recruitment_exposure_weight:required_f64,"language_topology_enabled"=>language_topology_enabled:required_bool})
}
fn apply_physical(v: &JsonValue, t: &mut PhysicalModelConfig) -> Result<(), ConfigError> {
    apply_fields!(v,t,{"village_microzones"=>village_microzones:required_usize,"town_microzones"=>town_microzones:required_usize,"city_microzones"=>city_microzones:required_usize,"extra_edge_probability"=>extra_edge_probability:required_f64,"presence_memory_days"=>presence_memory_days:required_f64,"response_decay_hours"=>response_decay_hours:required_f64,"formation_presence_gain"=>formation_presence_gain:required_f64,"patrol_memory_gain"=>patrol_memory_gain:required_f64,"fixed_post_presence_gain"=>fixed_post_presence_gain:required_f64,"zone_observation_noise"=>zone_observation_noise:required_f64,"patrol_route_randomness"=>patrol_route_randomness:required_f64,"adaptive_patrol_routing"=>adaptive_patrol_routing:required_bool})
}
fn apply_geography(v: &JsonValue, t: &mut GeographyConfig) -> Result<(), ConfigError> {
    let o = object(v, "geography")?;
    if let Some(x) = o.get("nearest_neighbors") {
        t.nearest_neighbors = required_usize(x, "nearest_neighbors")?
    }
    if let Some(x) = o.get("district_hub_links") {
        t.district_hub_links = required_bool(x, "district_hub_links")?
    }
    if let Some(x) = o.get("coordinate_jitter_km") {
        t.coordinate_jitter_km = required_f64(x, "coordinate_jitter_km")?
    }
    if let Some(x) = o.get("national_backbone") {
        t.national_backbone = required_string(x, "national_backbone")?
    }
    Ok(())
}
fn apply_force(v: &JsonValue, t: &mut ForceStructureConfig) -> Result<(), ConfigError> {
    let o = object(v, "force_structure")?;
    if let Some(x) = o.get("mode") {
        t.mode = required_string(x, "mode")?
    }
    if let Some(x) = o.get("government_target_personnel") {
        t.government_target_personnel = required_f64(x, "government_target_personnel")?
    }
    if let Some(x) = o.get("insurgent_target_personnel") {
        t.insurgent_target_personnel = required_f64(x, "insurgent_target_personnel")?
    }
    if let Some(x) = o.get("maximum_initial_formations_per_side") {
        t.maximum_initial_formations_per_side =
            required_usize(x, "maximum_initial_formations_per_side")?
    }
    Ok(())
}
fn apply_logistics(v: &JsonValue, t: &mut LogisticsConfig) -> Result<(), ConfigError> {
    let o = object(v, "logistics")?;
    macro_rules! fs{($($k:literal=>$f:ident:$knd:ident),*$(,)?)=>{$(if let Some(x)=o.get($k){t.$f=$knd(x,$k)?})*}}
    fs!("formation_supply_days"=>formation_supply_days:required_f64,"initial_supply_fraction"=>initial_supply_fraction:required_f64,"presence_consumption_per_person_day"=>presence_consumption_per_person_day:required_f64,"movement_consumption_per_person_km"=>movement_consumption_per_person_km:required_f64,"patrol_consumption_per_person_hour"=>patrol_consumption_per_person_hour:required_f64,"source_capacity_per_resident"=>source_capacity_per_resident:required_f64,"source_daily_production_fraction"=>source_daily_production_fraction:required_f64,"organization_sustainment_coverage"=>organization_sustainment_coverage:required_f64,"resupply_trigger_fraction"=>resupply_trigger_fraction:required_f64,"resupply_target_fraction"=>resupply_target_fraction:required_f64,"shipment_loss_per_travel_hour"=>shipment_loss_per_travel_hour:required_f64,"convoy_speed_factor"=>convoy_speed_factor:required_f64,"readiness_degradation_rate"=>readiness_degradation_rate:required_f64,"readiness_recovery_near_source"=>readiness_recovery_near_source:required_f64,"readiness_recovery_remote"=>readiness_recovery_remote:required_f64,"availability_recovery_rate"=>availability_recovery_rate:required_f64,"reallocation_rate"=>reallocation_rate:required_f64,"insurgent_frontier_weight"=>insurgent_frontier_weight:required_f64,"insurgent_foothold_weight"=>insurgent_foothold_weight:required_f64,"insurgent_stronghold_weight"=>insurgent_stronghold_weight:required_f64,"reallocation_exploration_weight"=>reallocation_exploration_weight:required_f64,"reallocation_strategic_weight"=>reallocation_strategic_weight:required_f64,"reallocation_importance_weight"=>reallocation_importance_weight:required_f64,"reallocation_travel_time_weight"=>reallocation_travel_time_weight:required_f64,"route_interdiction_enabled"=>route_interdiction_enabled:required_bool,"route_interdiction_rate"=>route_interdiction_rate:required_f64);
    if let Some(x) = o.get("source_capacity_model") {
        t.source_capacity_model = required_string(x, "source_capacity_model")?
    }
    if let Some(x) = o.get("reallocation_destination_scope") {
        t.reallocation_destination_scope = required_string(x, "reallocation_destination_scope")?
    }
    Ok(())
}

fn apply_information(v: &JsonValue, t: &mut InformationConfig) -> Result<(), ConfigError> {
    let o = object(v, "information")?;
    macro_rules! ff{($($k:literal=>$f:ident),*$(,)?)=>{$(if let Some(x)=o.get($k){t.$f=required_f64(x,$k)?})*}}
    ff!("prior_confidence"=>prior_confidence,"default_decay_rate"=>default_decay_rate,"mobile_decay_rate"=>mobile_decay_rate,"static_decay_rate"=>static_decay_rate,"road_decay_rate"=>road_decay_rate,"formation_decay_rate"=>formation_decay_rate,"true_positive_rate"=>true_positive_rate,"false_positive_rate"=>false_positive_rate,"attribution_error_rate"=>attribution_error_rate,"contact_true_positive_rate"=>contact_true_positive_rate,"contact_false_positive_rate"=>contact_false_positive_rate,"detection_pressure_bonus"=>detection_pressure_bonus,"detection_exposure_bonus"=>detection_exposure_bonus,"detection_language_bonus"=>detection_language_bonus,"detection_observability_bonus"=>detection_observability_bonus,"detection_terrain_penalty"=>detection_terrain_penalty,"detection_readiness_bonus"=>detection_readiness_bonus,"insurgent_concealment"=>insurgent_concealment,"civilian_report_rate"=>civilian_report_rate,"social_report_rate"=>social_report_rate,"administrative_report_rate"=>administrative_report_rate,"elite_report_rate"=>elite_report_rate,"member_report_rate"=>member_report_rate,"fixed_post_report_rate"=>fixed_post_report_rate,"patrol_report_rate"=>patrol_report_rate,"interpreter_report_rate"=>interpreter_report_rate,"relay_base_reliability"=>relay_base_reliability,"contradiction_penalty"=>contradiction_penalty,"contradiction_memory_days"=>contradiction_memory_days,"language_fusion_weight"=>language_fusion_weight,"corroboration_bonus"=>corroboration_bonus,"negative_report_confidence"=>negative_report_confidence,"positive_report_confidence"=>positive_report_confidence,"observation_retention_days"=>observation_retention_days);
    if let Some(x) = o.get("relay_max_hops") {
        t.relay_max_hops = required_usize(x, "relay_max_hops")?
    }
    for (field, target) in [
        ("source_trust", &mut t.source_trust),
        ("source_coverage", &mut t.source_coverage),
        ("source_latency_hours", &mut t.source_latency_hours),
        ("source_correlation", &mut t.source_correlation),
    ] {
        if let Some(x) = o.get(field) {
            let map = object(x, field)?;
            for (k, v) in map {
                target.insert(k.clone(), required_f64(v, &format!("{field}.{k}"))?);
            }
        }
    }
    Ok(())
}
fn apply_combat(v: &JsonValue, t: &mut CombatConfig) -> Result<(), ConfigError> {
    let o = object(v, "combat")?;
    macro_rules! ff{($($k:literal=>$f:ident),*$(,)?)=>{$(if let Some(x)=o.get($k){t.$f=required_f64(x,$k)?})*}}
    ff!("interval_hours"=>interval_hours,"base_attrition_rate"=>base_attrition_rate,"stochastic_sigma"=>stochastic_sigma,"max_loss_fraction"=>max_loss_fraction,"cohesion_loss_multiplier"=>cohesion_loss_multiplier,"readiness_cost_multiplier"=>readiness_cost_multiplier,"supply_per_person_hour"=>supply_per_person_hour,"ineffective_cohesion"=>ineffective_cohesion,"ineffective_readiness"=>ineffective_readiness,"disengagement_base"=>disengagement_base,"surprise_initiative"=>surprise_initiative,"civilian_exposure_rate"=>civilian_exposure_rate,"momentum_learning_rate"=>momentum_learning_rate,"reinforcement_threshold"=>reinforcement_threshold,"contact_ammunition_floor"=>contact_ammunition_floor,"accidental_contact_fraction"=>accidental_contact_fraction);
    for (k, f) in [
        ("contact_supply_rule", &mut t.contact_supply_rule),
        (
            "contact_opportunity_model",
            &mut t.contact_opportunity_model,
        ),
        (
            "organized_action_architecture",
            &mut t.organized_action_architecture,
        ),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_string(x, k)?
        }
    }
    Ok(())
}
fn apply_ecology(v: &JsonValue, t: &mut OrganizationEcologyConfig) -> Result<(), ConfigError> {
    let o = object(v, "organization_ecology")?;
    macro_rules! ff{($($k:literal=>$f:ident),*$(,)?)=>{$(if let Some(x)=o.get($k){t.$f=required_f64(x,$k)?})*}}
    ff!("interval_days"=>interval_days,"proto_base_hazard"=>proto_base_hazard,"birth_base_hazard"=>birth_base_hazard,"proto_decay_rate"=>proto_decay_rate,"split_base_hazard"=>split_base_hazard,"merger_base_hazard"=>merger_base_hazard,"collapse_base_hazard"=>collapse_base_hazard,"succession_base_hazard"=>succession_base_hazard,"adaptation_rate"=>adaptation_rate,"mutation_sigma"=>mutation_sigma,"minimum_proto_represented_population"=>minimum_proto_represented_population,"minimum_split_represented_population"=>minimum_split_represented_population,"minimum_formation_personnel"=>minimum_formation_personnel,"fighter_conversion_fraction"=>fighter_conversion_fraction,"local_foothold_memory_days"=>local_foothold_memory_days,"local_foothold_viability_threshold"=>local_foothold_viability_threshold,"local_rootedness_weight"=>local_rootedness_weight,"exit_sympathy_retention"=>exit_sympathy_retention,"onset_resource_fraction"=>onset_resource_fraction,"recruitment_diversity_penalty"=>recruitment_diversity_penalty,"cohesion_loss_memory"=>cohesion_loss_memory);
    for (k, f) in [
        ("enabled", &mut t.enabled),
        (
            "recruitment_requires_access",
            &mut t.recruitment_requires_access,
        ),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_bool(x, k)?
        }
    }
    for (k, f) in [
        ("minimum_proto_members", &mut t.minimum_proto_members),
        ("recruitment_subcohorts", &mut t.recruitment_subcohorts),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_usize(x, k)?
        }
    }
    if let Some(x) = o.get("observed_active_intervals") {
        let map = object(x, "observed_active_intervals")?;
        for (k, v) in map {
            let ranges = v.as_array().ok_or_else(|| {
                ConfigError::Invalid(format!("observed_active_intervals.{k} must be an array"))
            })?;
            let mut parsed = Vec::with_capacity(ranges.len());
            for range in ranges {
                let pair = range.as_array().ok_or_else(|| {
                    ConfigError::Invalid(format!(
                        "observed_active_intervals.{k} range must be an array"
                    ))
                })?;
                if pair.len() != 2 {
                    return Err(ConfigError::Invalid(format!(
                        "observed_active_intervals.{k} ranges need two values"
                    )));
                }
                parsed.push([
                    required_f64(&pair[0], "observed interval start")?,
                    required_f64(&pair[1], "observed interval end")?,
                ]);
            }
            t.observed_active_intervals.insert(k.clone(), parsed);
        }
    }
    Ok(())
}
fn apply_relationships(v: &JsonValue, t: &mut RelationshipConfig) -> Result<(), ConfigError> {
    let o = object(v, "relationships")?;
    for (k, f) in [
        ("memory_half_life_days", &mut t.memory_half_life_days),
        ("rivalry_threshold", &mut t.rivalry_threshold),
        ("hostility_threshold", &mut t.hostility_threshold),
        ("escalation_base_hazard", &mut t.escalation_base_hazard),
        (
            "deescalation_reference_rate",
            &mut t.deescalation_reference_rate,
        ),
        ("split_rivalry_memory", &mut t.split_rivalry_memory),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_nonstate(v: &JsonValue, t: &mut NonstateGovernanceConfig) -> Result<(), ConfigError> {
    let o = object(v, "nonstate_governance")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    for (k, f) in [
        ("gain_per_30_days", &mut t.gain_per_30_days),
        ("decay_per_30_days", &mut t.decay_per_30_days),
        ("minimum_local_capacity", &mut t.minimum_local_capacity),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_access(v: &JsonValue, t: &mut AccessRestrictionConfig) -> Result<(), ConfigError> {
    let o = object(v, "access_restriction")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    for (k, f) in [
        ("build_rate", &mut t.build_rate),
        ("decay_per_day", &mut t.decay_per_day),
        ("hostile_movement_penalty", &mut t.hostile_movement_penalty),
        ("civilian_utility_penalty", &mut t.civilian_utility_penalty),
        ("economic_penalty", &mut t.economic_penalty),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_civilian(v: &JsonValue, t: &mut CivilianDynamicsConfig) -> Result<(), ConfigError> {
    let o = object(v, "civilian_dynamics")?;
    for (k, f) in [
        (
            "voluntary_move_given_opportunity",
            &mut t.voluntary_move_given_opportunity,
        ),
        (
            "displacement_violence_threshold",
            &mut t.displacement_violence_threshold,
        ),
        (
            "forced_displacement_reference_rate",
            &mut t.forced_displacement_reference_rate,
        ),
        ("return_reference_rate", &mut t.return_reference_rate),
        (
            "resettlement_reference_rate",
            &mut t.resettlement_reference_rate,
        ),
        (
            "minimum_resettlement_days",
            &mut t.minimum_resettlement_days,
        ),
        (
            "fatality_fraction_of_direct_harm",
            &mut t.fatality_fraction_of_direct_harm,
        ),
        (
            "injury_fraction_of_direct_harm",
            &mut t.injury_fraction_of_direct_harm,
        ),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_political(v: &JsonValue, t: &mut PoliticalOrderConfig) -> Result<(), ConfigError> {
    let o = object(v, "political_order")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    for (k, f) in [
        ("interval_days", &mut t.interval_days),
        ("election_interval_days", &mut t.election_interval_days),
        ("federal_policy_budget", &mut t.federal_policy_budget),
        ("public_budget_share", &mut t.public_budget_share),
        ("patronage_share", &mut t.patronage_share),
        ("private_diversion_share", &mut t.private_diversion_share),
        ("capacity_learning_rate", &mut t.capacity_learning_rate),
        ("capacity_decay_rate", &mut t.capacity_decay_rate),
        (
            "patronage_capacity_damage",
            &mut t.patronage_capacity_damage,
        ),
        ("patronage_decay_rate", &mut t.patronage_decay_rate),
        ("elite_broker_share", &mut t.elite_broker_share),
        (
            "peaceful_channel_strength",
            &mut t.peaceful_channel_strength,
        ),
        (
            "election_turnout_sensitivity",
            &mut t.election_turnout_sensitivity,
        ),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}

fn apply_state_regeneration(
    v: &JsonValue,
    t: &mut StateRegenerationConfig,
) -> Result<(), ConfigError> {
    let o = object(v, "state_regeneration")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?;
    }
    for (k, f) in [
        ("interval_days", &mut t.interval_days),
        ("security_recruitment_rate", &mut t.security_recruitment_rate),
        ("security_training_rate", &mut t.security_training_rate),
        ("reserve_attrition_rate", &mut t.reserve_attrition_rate),
        ("training_cost_per_person", &mut t.training_cost_per_person),
        ("deployment_cost_per_person", &mut t.deployment_cost_per_person),
        ("police_allocation_share", &mut t.police_allocation_share),
        (
            "police_target_population_fraction",
            &mut t.police_target_population_fraction,
        ),
        ("military_target_multiplier", &mut t.military_target_multiplier),
        (
            "administrative_rebuild_rate",
            &mut t.administrative_rebuild_rate,
        ),
        (
            "administrative_decay_rate",
            &mut t.administrative_decay_rate,
        ),
        (
            "administrative_rebuild_cost",
            &mut t.administrative_rebuild_cost,
        ),
        (
            "rebuild_security_weight",
            &mut t.rebuild_security_weight,
        ),
        (
            "rebuild_integrity_weight",
            &mut t.rebuild_integrity_weight,
        ),
        (
            "rebuild_legitimacy_weight",
            &mut t.rebuild_legitimacy_weight,
        ),
        ("intelligence_gain_rate", &mut t.intelligence_gain_rate),
        ("intelligence_decay_rate", &mut t.intelligence_decay_rate),
        (
            "intelligence_police_weight",
            &mut t.intelligence_police_weight,
        ),
        (
            "intelligence_cooperation_weight",
            &mut t.intelligence_cooperation_weight,
        ),
        (
            "intelligence_administration_weight",
            &mut t.intelligence_administration_weight,
        ),
        (
            "underground_disruption_rate",
            &mut t.underground_disruption_rate,
        ),
        (
            "disrupted_sympathy_retention",
            &mut t.disrupted_sympathy_retention,
        ),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?;
        }
    }
    Ok(())
}
fn apply_foreign(v: &JsonValue, t: &mut ForeignAffairsConfig) -> Result<(), ConfigError> {
    let o = object(v, "foreign_affairs")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    if let Some(x) = o.get("neighbor_count") {
        t.neighbor_count = required_usize(x, "neighbor_count")?
    }
    for (k, f) in [
        ("interval_days", &mut t.interval_days),
        ("migration_rate", &mut t.migration_rate),
        ("return_rate", &mut t.return_rate),
        ("diaspora_remittance_rate", &mut t.diaspora_remittance_rate),
        (
            "diaspora_information_rate",
            &mut t.diaspora_information_rate,
        ),
        ("support_budget_fraction", &mut t.support_budget_fraction),
        ("intervention_base_hazard", &mut t.intervention_base_hazard),
        ("rival_reaction", &mut t.rival_reaction),
        ("interpreter_effect", &mut t.interpreter_effect),
        ("belief_noise", &mut t.belief_noise),
        ("host_transfer_efficiency", &mut t.host_transfer_efficiency),
        ("host_crowding_out", &mut t.host_crowding_out),
        ("willingness_cost_weight", &mut t.willingness_cost_weight),
        (
            "willingness_casualty_weight",
            &mut t.willingness_casualty_weight,
        ),
        ("withdrawal_threshold", &mut t.withdrawal_threshold),
        ("withdrawal_rate", &mut t.withdrawal_rate),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_peace(v: &JsonValue, t: &mut PeaceProcessConfig) -> Result<(), ConfigError> {
    let o = object(v, "peace_process")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    for (k, f) in [
        ("interval_days", &mut t.interval_days),
        ("negotiation_base_hazard", &mut t.negotiation_base_hazard),
        ("agreement_base_hazard", &mut t.agreement_base_hazard),
        ("ceasefire_violation_rate", &mut t.ceasefire_violation_rate),
        ("implementation_rate", &mut t.implementation_rate),
        ("demobilization_rate", &mut t.demobilization_rate),
        ("recurrence_base_hazard", &mut t.recurrence_base_hazard),
        (
            "battlefield_expectation_weight",
            &mut t.battlefield_expectation_weight,
        ),
        ("credibility_weight", &mut t.credibility_weight),
        ("fragmentation_penalty", &mut t.fragmentation_penalty),
        ("spoiler_penalty", &mut t.spoiler_penalty),
        ("foreign_influence_weight", &mut t.foreign_influence_weight),
        (
            "political_capital_retention",
            &mut t.political_capital_retention,
        ),
        ("resource_conversion_rate", &mut t.resource_conversion_rate),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}
fn apply_recording(v: &JsonValue, t: &mut RecordingConfig) -> Result<(), ConfigError> {
    let o = object(v, "recording")?;
    if let Some(x) = o.get("enabled") {
        t.enabled = required_bool(x, "enabled")?
    }
    for (k, f) in [
        ("base_logit", &mut t.base_logit),
        ("severity_weight", &mut t.severity_weight),
        ("access_weight", &mut t.access_weight),
        ("remoteness_penalty", &mut t.remoteness_penalty),
        ("severity_noise", &mut t.severity_noise),
        ("geocoding_error_rate", &mut t.geocoding_error_rate),
        ("geocoding_scale_km", &mut t.geocoding_scale_km),
        ("false_event_rate", &mut t.false_event_rate),
    ] {
        if let Some(x) = o.get(k) {
            *f = required_f64(x, k)?
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{SimulationConfig, StateRegenerationConfig};
    use crate::json::parse;

    #[test]
    fn full_width_seed_survives_json_and_hashing() {
        let value =
            parse(r#"{"seed":18446744073709551615,"agent_count":1,"locality_count":1}"#).unwrap();
        let config = SimulationConfig::from_json(&value).unwrap();
        assert_eq!(config.seed, u64::MAX);
        let encoded = config.to_json().to_compact();
        assert!(encoded.contains("18446744073709551615"));
        let round_trip = SimulationConfig::from_json(&parse(&encoded).unwrap()).unwrap();
        assert_eq!(round_trip, config);
        assert_eq!(round_trip.canonical_hash(), config.canonical_hash());
    }

    #[test]
    fn unknown_root_fields_are_preserved_for_forward_compatibility() {
        let value =
            parse(r#"{"agent_count":1,"locality_count":1,"future_parameter":{"v":3}}"#).unwrap();
        let config = SimulationConfig::from_json(&value).unwrap();
        assert!(config.to_json().get("future_parameter").is_some());
    }

    #[test]
    fn default_state_regeneration_does_not_change_legacy_canonical_json() {
        let config = SimulationConfig::default();
        assert_eq!(config.state_regeneration, StateRegenerationConfig::default());
        assert!(config.to_json().get("state_regeneration").is_none());
    }

    #[test]
    fn enabled_state_regeneration_round_trips_exactly() {
        let mut config = SimulationConfig::default();
        config.state_regeneration.enabled = true;
        config.state_regeneration.security_recruitment_rate = 3.5e-6;
        config.state_regeneration.police_allocation_share = 0.63;
        config.state_regeneration.administrative_rebuild_rate = 0.0021;
        config.state_regeneration.intelligence_gain_rate = 0.017;
        let encoded = config.to_json().to_compact();
        assert!(encoded.contains("state_regeneration"));
        let round_trip = SimulationConfig::from_json(&parse(&encoded).unwrap()).unwrap();
        assert_eq!(round_trip, config);
        assert_eq!(round_trip.canonical_hash(), config.canonical_hash());
    }
}
