from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProcessIntervals:
    contact: float = 1.0
    command: float = 1.0
    force_movement: float = 0.25
    logistics: float = 1.0
    information: float = 0.25
    patrol: float = 0.25
    physical_refresh: float = 0.25
    beliefs: float = 1.0
    social_influence: float = 1.0
    mobility: float = 1.0
    recruitment: float = 7.0
    governance: float = 30.0
    economy: float = 30.0
    checkpoint: float = 30.0


@dataclass(slots=True)
class SocialNetworkConfig:
    # Community-size controls are stable represented-population units rather
    # than literal sampled-agent counts.  At the default 120 residents/unit,
    # target_community_size=100 means roughly 12,000 represented residents.
    # Keeping the legacy size knobs as units preserves configuration/API
    # compatibility while removing resolution from the substantive partition.
    community_size_unit_population: float = 120.0
    target_community_size: int = 100
    minimum_community_size: int = 50
    maximum_community_size: int = 150
    mean_social_degree: float = 8.0
    maximum_social_degree: int = 24
    bridge_fraction: float = 0.03
    behavior_update_rate: float = 0.12
    household_tie_strength: float = 0.95
    community_tie_strength: float = 0.65
    bridge_tie_strength: float = 0.45
    behavior_exposure_weight: float = 0.35
    recruitment_exposure_weight: float = 0.25
    # When disabled, edge generation preserves topology and tie counts but
    # removes the language-compatibility multiplier.  This supports a clean
    # topology/detection/fusion factorial without changing the latent people.
    language_topology_enabled: bool = True

    def validate(self) -> None:
        if self.community_size_unit_population <= 0:
            raise ValueError("community_size_unit_population must be positive")
        if not 1 <= self.minimum_community_size <= self.target_community_size <= self.maximum_community_size:
            raise ValueError("community sizes must satisfy 1 <= minimum <= target <= maximum")
        if not 1 <= self.mean_social_degree <= self.maximum_social_degree:
            raise ValueError("mean_social_degree must be between 1 and maximum_social_degree")
        for name in ("bridge_fraction", "behavior_update_rate", "household_tie_strength",
                     "community_tie_strength", "bridge_tie_strength"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("behavior_exposure_weight", "recruitment_exposure_weight"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(slots=True)
class PhysicalModelConfig:
    village_microzones: int = 3
    town_microzones: int = 5
    city_microzones: int = 8
    extra_edge_probability: float = 0.22
    presence_memory_days: float = 2.0
    response_decay_hours: float = 0.75
    # Instantaneous fielded-formation occupation and patrol-written memory are
    # distinct mechanisms. Both are dimensionless normalized-strength gains,
    # but only explicit patrol dwell writes the decaying memory stock.
    formation_presence_gain: float = 0.35
    patrol_memory_gain: float = 0.35
    fixed_post_presence_gain: float = 0.25
    zone_observation_noise: float = 0.12
    patrol_route_randomness: float = 0.15
    adaptive_patrol_routing: bool = True

    def validate(self) -> None:
        if not 2 <= self.village_microzones <= self.town_microzones <= self.city_microzones:
            raise ValueError("microzone counts must satisfy 2 <= village <= town <= city")
        for name in ("extra_edge_probability", "formation_presence_gain", "patrol_memory_gain",
                     "fixed_post_presence_gain",
                     "zone_observation_noise", "patrol_route_randomness"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.presence_memory_days <= 0 or self.response_decay_hours <= 0:
            raise ValueError("physical decay time constants must be positive")


@dataclass(slots=True)
class GeographyConfig:
    """Spatial-topology controls for the synthetic national locality graph."""

    nearest_neighbors: int = 2
    district_hub_links: bool = True
    coordinate_jitter_km: float = 18.0
    national_backbone: str = "spatial_mst"

    def validate(self) -> None:
        if self.nearest_neighbors < 1 or self.coordinate_jitter_km < 0:
            raise ValueError("geography neighbour count and coordinate jitter must be nonnegative")
        if self.national_backbone not in {"spatial_mst", "knn"}:
            raise ValueError("unsupported national geography backbone")


@dataclass(slots=True)
class LogisticsConfig:
    formation_supply_days: float = 30.0
    initial_supply_fraction: float = 0.8
    presence_consumption_per_person_day: float = 0.75
    movement_consumption_per_person_km: float = 0.02
    patrol_consumption_per_person_hour: float = 0.002
    source_capacity_per_resident: float = 0.05
    source_daily_production_fraction: float = 0.03
    source_capacity_model: str = "organization_manpower"
    # Ex ante sustainment reserve above stationary presence demand.  This is
    # an engineering prior, not a conflict-event calibration target.
    organization_sustainment_coverage: float = 1.20
    resupply_trigger_fraction: float = 0.45
    resupply_target_fraction: float = 0.85
    shipment_loss_per_travel_hour: float = 0.002
    convoy_speed_factor: float = 0.75
    readiness_degradation_rate: float = 0.08
    readiness_recovery_near_source: float = 0.025
    readiness_recovery_remote: float = 0.006
    availability_recovery_rate: float = 0.03
    reallocation_rate: float = 0.04
    # Ordinary repositioning proceeds one adjacency step per decision. Long
    # routes remain available to explicit withdrawal and historical schedules.
    reallocation_destination_scope: str = "adjacent"
    # Insurgent reallocation is deliberately a mixture of frontier expansion,
    # pre-existing clandestine footholds, stronghold consolidation, and
    # uncertainty-driven exploration.  These are structural theory weights,
    # not case-fitted coefficients.
    insurgent_frontier_weight: float = 0.50
    insurgent_foothold_weight: float = 0.25
    insurgent_stronghold_weight: float = 0.15
    reallocation_exploration_weight: float = 0.10
    # Random-utility scale terms shared by state-aligned and insurgent
    # reallocation.  They are exposed theory priors, not case-fit constants.
    reallocation_strategic_weight: float = 2.0
    reallocation_importance_weight: float = 0.5
    reallocation_travel_time_weight: float = 0.03
    route_interdiction_enabled: bool = False
    route_interdiction_rate: float = 0.0

    def validate(self) -> None:
        for name in ("formation_supply_days", "presence_consumption_per_person_day",
                     "source_capacity_per_resident", "convoy_speed_factor"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("initial_supply_fraction", "source_daily_production_fraction",
                     "resupply_trigger_fraction", "resupply_target_fraction",
                     "readiness_degradation_rate", "readiness_recovery_near_source",
                     "readiness_recovery_remote", "availability_recovery_rate", "reallocation_rate",
                     "insurgent_frontier_weight", "insurgent_foothold_weight",
                     "insurgent_stronghold_weight", "reallocation_exploration_weight"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        insurgent_weights = (
            self.insurgent_frontier_weight + self.insurgent_foothold_weight +
            self.insurgent_stronghold_weight + self.reallocation_exploration_weight
        )
        if abs(insurgent_weights - 1.0) > 1e-9:
            raise ValueError("insurgent reallocation structural weights must sum to 1")
        for name in ("reallocation_strategic_weight", "reallocation_importance_weight",
                     "reallocation_travel_time_weight"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.resupply_target_fraction < self.resupply_trigger_fraction:
            raise ValueError("resupply target must be at least the trigger fraction")
        if self.movement_consumption_per_person_km < 0 or self.patrol_consumption_per_person_hour < 0:
            raise ValueError("movement and patrol consumption cannot be negative")
        if self.shipment_loss_per_travel_hour < 0:
            raise ValueError("shipment loss cannot be negative")
        if self.route_interdiction_rate < 0:
            raise ValueError("route interdiction rate cannot be negative")
        if self.source_capacity_model not in {"organization_manpower", "population_catchment"}:
            raise ValueError("unsupported source capacity model")
        if self.reallocation_destination_scope not in {"adjacent", "national"}:
            raise ValueError("unsupported reallocation destination scope")
        if self.organization_sustainment_coverage <= 0:
            raise ValueError("organization sustainment coverage must be positive")


@dataclass(slots=True)
class ForceStructureConfig:
    """Outcome-independent mapping from represented manpower to force tokens."""

    mode: str = "manpower_decomposition"
    government_target_personnel: float = 3_500.0
    insurgent_target_personnel: float = 1_000.0
    maximum_initial_formations_per_side: int = 64

    def validate(self) -> None:
        if self.mode not in {"legacy", "manpower_decomposition"}:
            raise ValueError("unsupported force-structure mode")
        if min(self.government_target_personnel, self.insurgent_target_personnel) <= 0:
            raise ValueError("target formation personnel must be positive")
        if self.maximum_initial_formations_per_side < 1:
            raise ValueError("maximum initial formations must be positive")


@dataclass(slots=True)
class InformationConfig:
    """Transparent priors for source heterogeneity, detection, and fusion.

    Rates are deliberately exposed as configuration rather than hidden in
    process code so sensitivity analysis can vary information independently of
    force projection and combat.
    """

    prior_confidence: float = 0.28
    default_decay_rate: float = 0.08
    mobile_decay_rate: float = 0.55
    static_decay_rate: float = 0.025
    road_decay_rate: float = 0.045
    formation_decay_rate: float = 0.65
    true_positive_rate: float = 0.72
    false_positive_rate: float = 0.035
    attribution_error_rate: float = 0.08
    contact_true_positive_rate: float = 0.82
    contact_false_positive_rate: float = 0.02
    detection_pressure_bonus: float = 0.65
    detection_exposure_bonus: float = 0.7
    detection_language_bonus: float = 0.5
    detection_observability_bonus: float = 0.7
    detection_terrain_penalty: float = 0.55
    detection_readiness_bonus: float = 0.55
    insurgent_concealment: float = 0.25
    civilian_report_rate: float = 0.18
    social_report_rate: float = 0.22
    administrative_report_rate: float = 0.28
    elite_report_rate: float = 0.16
    member_report_rate: float = 0.35
    fixed_post_report_rate: float = 0.72
    patrol_report_rate: float = 1.0
    interpreter_report_rate: float = 0.72
    relay_base_reliability: float = 0.86
    relay_max_hops: int = 8
    contradiction_penalty: float = 0.45
    contradiction_memory_days: float = 30.0
    language_fusion_weight: float = 1.0
    corroboration_bonus: float = 0.12
    negative_report_confidence: float = 0.52
    positive_report_confidence: float = 0.9
    # Optional bounded-memory retention for long analytical runs.  Zero keeps
    # the complete evidence archive (the historical/default behavior); a
    # positive value is only appropriate when the requested output is an
    # ensemble/target stream and the retained belief state is the estimand.
    observation_retention_days: float = 0.0
    source_trust: dict[str, float] = field(default_factory=lambda: {
        "patrol": 0.88,
        "fixed_post": 0.8,
        "civilian": 0.55,
        "social_network": 0.62,
        "administrative": 0.72,
        "organization_member": 0.76,
        "political_elite": 0.58,
        "interpreter": 0.72,
        "contact": 0.9,
    })
    source_coverage: dict[str, float] = field(default_factory=lambda: {
        "patrol": 0.82,
        "fixed_post": 0.65,
        "civilian": 0.42,
        "social_network": 0.48,
        "administrative": 0.55,
        "organization_member": 0.58,
        "political_elite": 0.35,
        "interpreter": 0.52,
        "contact": 0.95,
    })
    source_latency_hours: dict[str, float] = field(default_factory=lambda: {
        "patrol": 0.2,
        "fixed_post": 0.4,
        "civilian": 8.0,
        "social_network": 5.0,
        "administrative": 12.0,
        "organization_member": 2.0,
        "political_elite": 24.0,
        "interpreter": 10.0,
        "contact": 0.1,
    })
    # Reports sharing a collection pipeline are not fully independent.  These
    # coefficients attenuate corroboration while retaining distinct source
    # identity in the evidence ledger.
    source_correlation: dict[str, float] = field(default_factory=lambda: {
        "patrol": .15, "fixed_post": .25, "civilian": .55,
        "social_network": .65, "administrative": .35,
        "organization_member": .20, "political_elite": .50,
        "interpreter": .30, "contact": .10,
    })

    def validate(self) -> None:
        bounded = (
            "prior_confidence", "true_positive_rate", "false_positive_rate",
            "attribution_error_rate",
            "contact_true_positive_rate", "contact_false_positive_rate",
            "civilian_report_rate", "social_report_rate", "administrative_report_rate",
            "elite_report_rate", "member_report_rate", "fixed_post_report_rate",
            "patrol_report_rate", "interpreter_report_rate", "relay_base_reliability", "contradiction_penalty",
            "corroboration_bonus", "negative_report_confidence", "positive_report_confidence",
        )
        for name in bounded:
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("default_decay_rate", "mobile_decay_rate", "static_decay_rate",
                     "road_decay_rate", "formation_decay_rate", "detection_pressure_bonus",
                     "detection_exposure_bonus", "detection_language_bonus",
                     "detection_observability_bonus", "detection_terrain_penalty",
            "detection_readiness_bonus"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not 0 <= self.insurgent_concealment <= 1:
            raise ValueError("insurgent_concealment must be in [0, 1]")
        if self.contradiction_memory_days <= 0:
            raise ValueError("contradiction_memory_days must be positive")
        if self.observation_retention_days < 0:
            raise ValueError("observation_retention_days cannot be negative")
        if self.language_fusion_weight < 0:
            raise ValueError("language_fusion_weight cannot be negative")
        if self.relay_max_hops < 1:
            raise ValueError("relay_max_hops must be positive")
        for source_map_name in ("source_trust", "source_coverage"):
            source_map = getattr(self, source_map_name)
            for source, value in source_map.items():
                if not 0 <= value <= 1:
                    raise ValueError(f"{source_map_name}[{source}] must be in [0, 1]")
        for source, value in self.source_latency_hours.items():
            if value < 0:
                raise ValueError(f"source_latency_hours[{source}] cannot be negative")
        for source, value in self.source_correlation.items():
            if not 0 <= value <= 1:
                raise ValueError(f"source_correlation[{source}] must be in [0, 1]")


@dataclass(slots=True)
class CombatConfig:
    """Mechanistic priors for a bounded engagement interval."""

    interval_hours: float = 2.0
    base_attrition_rate: float = 0.012
    stochastic_sigma: float = 0.42
    max_loss_fraction: float = 0.12
    cohesion_loss_multiplier: float = 1.8
    readiness_cost_multiplier: float = 1.1
    supply_per_person_hour: float = 0.035
    ineffective_cohesion: float = 0.22
    ineffective_readiness: float = 0.18
    disengagement_base: float = 0.16
    surprise_initiative: float = 0.28
    civilian_exposure_rate: float = 0.00008
    momentum_learning_rate: float = 0.12
    reinforcement_threshold: float = 0.06
    # Contact occurrence is distinct from combat capability.  The repaired
    # default treats supply as a continuous capability constraint rather than
    # a symmetric hard encounter gate; ``hard_gate`` is retained as a forensic
    # counterfactual for provenance.
    contact_supply_rule: str = "no_gate"
    contact_ammunition_floor: float = 0.05
    # Fraction of the physical co-presence rate attributable to accidental
    # encounter rather than deliberate detection and initiation.
    accidental_contact_fraction: float = 0.05
    contact_opportunity_model: str = "directional_pairwise"
    # v5 separates organization/action/event support.  Legacy contact-only
    # scheduling remains available for exact historical/provenance replay.
    organized_action_architecture: str = "multichannel_v5"

    def validate(self) -> None:
        for name in ("interval_hours", "base_attrition_rate", "max_loss_fraction",
                     "cohesion_loss_multiplier", "readiness_cost_multiplier",
                     "supply_per_person_hour", "stochastic_sigma",
                     "civilian_exposure_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in ("ineffective_cohesion", "ineffective_readiness",
                     "disengagement_base", "surprise_initiative",
                     "momentum_learning_rate", "reinforcement_threshold",
                     "accidental_contact_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.contact_supply_rule not in {
            "hard_gate", "no_gate", "continuous", "ammunition_floor",
            "initiation_asymmetry",
        }:
            raise ValueError("unsupported contact_supply_rule")
        if not 0 <= self.contact_ammunition_floor <= 1:
            raise ValueError("contact_ammunition_floor must be in [0, 1]")
        if self.contact_opportunity_model not in {"legacy_symmetric", "directional_pairwise"}:
            raise ValueError("unsupported contact opportunity model")
        if self.organized_action_architecture not in {
            "legacy_contact_only", "multichannel_v5"
        }:
            raise ValueError("unsupported organized action architecture")


@dataclass(slots=True)
class OrganizationEcologyConfig:
    enabled: bool = True
    interval_days: float = 7.0
    proto_base_hazard: float = 0.004
    birth_base_hazard: float = 0.003
    proto_decay_rate: float = 0.08
    split_base_hazard: float = 0.002
    merger_base_hazard: float = 0.015
    collapse_base_hazard: float = 0.004
    succession_base_hazard: float = 0.006
    adaptation_rate: float = 0.12
    mutation_sigma: float = 0.035
    minimum_proto_members: int = 3
    # Backward-compatible serialization field.  It is not used as a
    # substantive onset threshold because raw representative counts are
    # resolution-dependent; use minimum_proto_represented_population.
    minimum_proto_represented_population: float = 1_000.0
    minimum_split_represented_population: float = 1_500.0
    minimum_formation_personnel: float = 75.0
    fighter_conversion_fraction: float = .08
    # A representative person is internally divided into equal recruitment
    # subcohorts.  Recruitment/exit hazards act on those subcohorts rather
    # than on the person's entire represented weight at once.  This is a
    # numerical-resolution control, not an empirical fit parameter.
    recruitment_subcohorts: int = 20
    recruitment_requires_access: bool = True
    # Utility-scale effect of constituency/franchise congruence.  A locally
    # rooted organization is more attractive to civilians whose local/district
    # identities are salient; an externally implanted franchise is less so.
    # This is a general-theory prior, not a case-fit coefficient.
    local_rootedness_weight: float = 0.75
    # Conditional probability that a person who fully exits armed membership
    # retains an insurgent-sympathetic public signal. The default 1.0 preserves
    # the former hard-coded behavior while exposing it as a falsifiable theory.
    exit_sympathy_retention: float = 1.0
    onset_resource_fraction: float = 0.18
    recruitment_diversity_penalty: float = 0.12
    cohesion_loss_memory: float = 0.2
    # Actor-specific existence conditioning for empirical designs. During a
    # supplied interval, identity-changing split, collapse, and merger
    # transitions are suppressed; operations and other internal evolution
    # remain endogenous.
    observed_active_intervals: dict[str, list[list[float]]] = field(default_factory=dict)

    def validate(self) -> None:
        if (self.interval_days <= 0 or self.minimum_proto_members < 1 or
                self.minimum_proto_represented_population <= 0 or
                self.minimum_split_represented_population <= 0 or
                self.minimum_formation_personnel < 0 or
                self.recruitment_subcohorts < 1):
            raise ValueError("invalid organization ecology interval or minimum size")
        if not 0 <= self.local_rootedness_weight <= 3:
            raise ValueError("local_rootedness_weight must be in [0, 3]")
        for name in ("proto_base_hazard", "birth_base_hazard", "proto_decay_rate",
                     "split_base_hazard", "merger_base_hazard", "collapse_base_hazard",
                     "succession_base_hazard",
                     "adaptation_rate", "mutation_sigma", "onset_resource_fraction",
                     "recruitment_diversity_penalty", "cohesion_loss_memory",
                     "fighter_conversion_fraction", "exit_sympathy_retention"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(slots=True)
class PoliticalOrderConfig:
    enabled: bool = True
    interval_days: float = 30.0
    election_interval_days: float = 1460.0
    federal_policy_budget: float = 120_000.0
    public_budget_share: float = 0.68
    patronage_share: float = 0.22
    private_diversion_share: float = 0.10
    capacity_learning_rate: float = 0.012
    capacity_decay_rate: float = 0.008
    patronage_capacity_damage: float = 0.018
    patronage_decay_rate: float = 0.035
    elite_broker_share: float = 0.35
    peaceful_channel_strength: float = 0.5
    election_turnout_sensitivity: float = 1.4

    def validate(self) -> None:
        if self.interval_days <= 0 or self.election_interval_days <= 0 or self.federal_policy_budget < 0:
            raise ValueError("invalid political interval or budget")
        for name in ("public_budget_share", "patronage_share", "private_diversion_share",
                     "capacity_learning_rate", "capacity_decay_rate", "patronage_capacity_damage",
                     "patronage_decay_rate", "elite_broker_share", "peaceful_channel_strength"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if abs(self.public_budget_share + self.patronage_share + self.private_diversion_share - 1) > 1e-9:
            raise ValueError("political budget shares must sum to one")


@dataclass(slots=True)
class RecordingConfig:
    """Observation model for synthetic event-recording, separate from reporting error."""

    enabled: bool = True
    base_logit: float = -1.5
    severity_weight: float = 1.8
    access_weight: float = 1.2
    remoteness_penalty: float = 0.9
    severity_noise: float = 0.12
    geocoding_error_rate: float = 0.12
    geocoding_scale_km: float = 2.0
    false_event_rate: float = 0.0
    # Source-specific observation operators.  Missing channels inherit the
    # top-level defaults, so old scenario files remain valid.
    source_channels: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "default": {"base_logit": -1.5, "severity_weight": 1.8,
                     "access_weight": 1.2, "remoteness_penalty": .9,
                     "severity_noise": .12, "geocoding_error_rate": .12,
                     "geocoding_scale_km": 2.0},
        "contact": {"base_logit": -1.0, "severity_weight": 2.2,
                    "access_weight": 1.3, "remoteness_penalty": .65,
                    "severity_noise": .10, "geocoding_error_rate": .08,
                    "geocoding_scale_km": 1.5},
        "patrol": {"base_logit": -1.35, "severity_weight": 1.7,
                   "access_weight": 1.4, "remoteness_penalty": .7,
                   "severity_noise": .10, "geocoding_error_rate": .06,
                   "geocoding_scale_km": 1.0},
        "administrative": {"base_logit": -1.8, "severity_weight": 1.4,
                           "access_weight": 1.6, "remoteness_penalty": .45,
                           "severity_noise": .15, "geocoding_error_rate": .05,
                           "geocoding_scale_km": .8},
    })

    def validate(self) -> None:
        if self.severity_noise < 0 or self.geocoding_error_rate < 0 or self.geocoding_scale_km <= 0:
            raise ValueError("recording noise parameters cannot be negative")
        if not 0 <= self.geocoding_error_rate <= 1:
            raise ValueError("geocoding_error_rate must be in [0, 1]")
        if not 0 <= self.false_event_rate <= 1:
            raise ValueError("false_event_rate must be in [0, 1]")
        for channel, values in self.source_channels.items():
            for key in ("base_logit", "severity_weight", "access_weight", "remoteness_penalty",
                        "severity_noise", "geocoding_error_rate", "geocoding_scale_km"):
                if key not in values:
                    continue
                value = values[key]
                if key == "geocoding_error_rate" and not 0 <= value <= 1:
                    raise ValueError(f"source_channels[{channel}].{key} must be in [0, 1]")
                if key == "geocoding_scale_km" and value <= 0:
                    raise ValueError(f"source_channels[{channel}].{key} must be positive")
                if key not in {"base_logit", "geocoding_error_rate", "geocoding_scale_km"} and value < 0:
                    raise ValueError(f"source_channels[{channel}].{key} cannot be negative")


@dataclass(slots=True)
class ForeignAffairsConfig:
    enabled: bool = True
    interval_days: float = 30.0
    neighbor_count: int = 5
    migration_rate: float = 0.002
    return_rate: float = 0.015
    diaspora_remittance_rate: float = 0.025
    diaspora_information_rate: float = 0.08
    support_budget_fraction: float = 0.002
    intervention_base_hazard: float = 0.015
    rival_reaction: float = 0.35
    interpreter_effect: float = 0.4
    belief_noise: float = 0.18
    host_transfer_efficiency: float = 0.35
    host_crowding_out: float = 0.25
    willingness_cost_weight: float = 0.35
    willingness_casualty_weight: float = 0.45
    withdrawal_threshold: float = 0.28
    withdrawal_rate: float = 0.2

    def validate(self) -> None:
        if self.interval_days <= 0 or not 4 <= self.neighbor_count <= 6:
            raise ValueError("foreign interval must be positive and neighbor_count in [4, 6]")
        for name in ("migration_rate", "return_rate", "diaspora_remittance_rate",
                     "diaspora_information_rate", "support_budget_fraction",
                     "intervention_base_hazard", "rival_reaction", "interpreter_effect",
                     "belief_noise", "host_transfer_efficiency", "host_crowding_out",
                     "willingness_cost_weight", "willingness_casualty_weight",
                     "withdrawal_threshold", "withdrawal_rate"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(slots=True)
class PeaceProcessConfig:
    enabled: bool = True
    interval_days: float = 30.0
    negotiation_base_hazard: float = 0.08
    agreement_base_hazard: float = 0.12
    ceasefire_violation_rate: float = 0.025
    implementation_rate: float = 0.055
    demobilization_rate: float = 0.10
    recurrence_base_hazard: float = 0.0025
    battlefield_expectation_weight: float = 0.75
    credibility_weight: float = 1.1
    fragmentation_penalty: float = 1.4
    spoiler_penalty: float = 1.0
    foreign_influence_weight: float = 0.6
    political_capital_retention: float = 0.68
    resource_conversion_rate: float = 0.72

    def validate(self) -> None:
        if self.interval_days <= 0:
            raise ValueError("peace-process interval must be positive")
        for name in ("negotiation_base_hazard", "agreement_base_hazard",
                     "ceasefire_violation_rate", "implementation_rate",
                     "demobilization_rate", "recurrence_base_hazard",
                     "battlefield_expectation_weight", "credibility_weight",
                     "fragmentation_penalty", "spoiler_penalty",
                     "foreign_influence_weight", "political_capital_retention",
                     "resource_conversion_rate"):
            if not 0 <= getattr(self, name) <= 1.5:
                raise ValueError(f"{name} must be in [0, 1.5]")


@dataclass(slots=True)
class SimulationConfig:
    seed: int = 20260902
    horizon_days: float = 365.0
    agent_count: int = 75_000
    locality_count: int = 72
    # Library callers default to no warm-up; the bundled baseline scenario
    # opts into a 30-day unrecorded stabilization phase explicitly.
    burn_in_days: float = 0.0
    include_insurgency: bool = True
    initial_insurgent_share: float = 0.001
    observation_noise: float = 0.08
    reporting_error: float = 0.12
    movement_rate: float = 0.015
    recruitment_rate: float = 0.001
    # Membership loss/retention is a distinct organizational process from
    # recruitment.  The baseline prior intentionally matches recruitment_rate
    # to preserve the pre-split numerical baseline while allowing synthetic
    # experiments to vary mobilization and retention independently.
    membership_exit_rate: float = 0.001
    contact_rate: float = 0.08
    random_stream_namespace: str = "baseline"
    # Output fidelity is deliberately orthogonal to the stochastic model.
    # ``forensic`` retains every event/state delta; ``ensemble`` retains
    # compact event summaries; ``calibration`` retains only aggregate counters
    # and target-relevant state.  Process RNG streams remain unchanged.
    output_mode: str = "forensic"
    intervals: ProcessIntervals = field(default_factory=ProcessIntervals)
    social_network: SocialNetworkConfig = field(default_factory=SocialNetworkConfig)
    physical: PhysicalModelConfig = field(default_factory=PhysicalModelConfig)
    geography: GeographyConfig = field(default_factory=GeographyConfig)
    logistics: LogisticsConfig = field(default_factory=LogisticsConfig)
    force_structure: ForceStructureConfig = field(default_factory=ForceStructureConfig)
    information: InformationConfig = field(default_factory=InformationConfig)
    combat: CombatConfig = field(default_factory=CombatConfig)
    organization_ecology: OrganizationEcologyConfig = field(default_factory=OrganizationEcologyConfig)
    political_order: PoliticalOrderConfig = field(default_factory=PoliticalOrderConfig)
    foreign_affairs: ForeignAffairsConfig = field(default_factory=ForeignAffairsConfig)
    peace_process: PeaceProcessConfig = field(default_factory=PeaceProcessConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)

    def validate(self) -> None:
        if self.agent_count < 1:
            raise ValueError("agent_count must be positive")
        if not 17 <= self.locality_count:
            raise ValueError("locality_count must be at least 17")
        if self.horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if self.output_mode not in {"forensic", "ensemble", "calibration"}:
            raise ValueError("output_mode must be forensic, ensemble, or calibration")
        if self.burn_in_days < 0:
            raise ValueError("burn_in_days cannot be negative")
        for name in ("initial_insurgent_share", "observation_noise", "reporting_error"):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in ("movement_rate", "recruitment_rate", "membership_exit_rate",
                     "contact_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name, value in asdict(self.intervals).items():
            if value <= 0:
                raise ValueError(f"interval {name} must be positive")
        self.social_network.validate()
        self.physical.validate()
        self.geography.validate()
        self.logistics.validate()
        self.force_structure.validate()
        self.information.validate()
        self.combat.validate()
        self.organization_ecology.validate()
        self.political_order.validate()
        self.foreign_affairs.validate()
        self.peace_process.validate()
        self.recording.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "SimulationConfig":
        values = dict(values)
        # Legacy configurations used recruitment_rate as the common hazard
        # scale for both joining and exit.  Preserve that exact behavior when
        # reading an old serialized configuration, while new configs can set
        # the two theoretically distinct rates independently.
        if "membership_exit_rate" not in values:
            values["membership_exit_rate"] = float(values.get("recruitment_rate", 0.001))
        if isinstance(values.get("intervals"), dict):
            values["intervals"] = ProcessIntervals(**values["intervals"])
        if isinstance(values.get("social_network"), dict):
            values["social_network"] = SocialNetworkConfig(**values["social_network"])
        if isinstance(values.get("physical"), dict):
            physical_values = dict(values["physical"])
            # Backward-compatible migration from the former single gain.  The
            # old value controlled both current formation presence and patrol
            # memory. Preserve its numeric prior for legacy files while
            # splitting the live mechanisms into independent fields.
            legacy_gain = physical_values.pop("patrol_presence_gain", None)
            if legacy_gain is not None:
                physical_values.setdefault("formation_presence_gain", legacy_gain)
                physical_values.setdefault("patrol_memory_gain", legacy_gain)
            values["physical"] = PhysicalModelConfig(**physical_values)
        if isinstance(values.get("geography"), dict):
            values["geography"] = GeographyConfig(**values["geography"])
        if isinstance(values.get("logistics"), dict):
            values["logistics"] = LogisticsConfig(**values["logistics"])
        if isinstance(values.get("force_structure"), dict):
            values["force_structure"] = ForceStructureConfig(**values["force_structure"])
        if isinstance(values.get("information"), dict):
            values["information"] = InformationConfig(**values["information"])
        if isinstance(values.get("combat"), dict):
            combat_values = dict(values["combat"])
            # Serialized pre-v0.13 configurations had no action-architecture
            # field and therefore describe the contact-only model. Preserve
            # exact replay instead of silently inheriting the new default.
            combat_values.setdefault(
                "organized_action_architecture", "legacy_contact_only"
            )
            values["combat"] = CombatConfig(**combat_values)
        if isinstance(values.get("organization_ecology"), dict):
            values["organization_ecology"] = OrganizationEcologyConfig(**values["organization_ecology"])
        if isinstance(values.get("political_order"), dict):
            values["political_order"] = PoliticalOrderConfig(**values["political_order"])
        if isinstance(values.get("foreign_affairs"), dict):
            values["foreign_affairs"] = ForeignAffairsConfig(**values["foreign_affairs"])
        if isinstance(values.get("peace_process"), dict):
            values["peace_process"] = PeaceProcessConfig(**values["peace_process"])
        if isinstance(values.get("recording"), dict):
            values["recording"] = RecordingConfig(**values["recording"])
        config = cls(**values)
        config.validate()
        return config

    @classmethod
    def load(cls, path: str | Path) -> "SimulationConfig":
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
