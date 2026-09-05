from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import exp, isfinite, log
from typing import Any


LANGUAGES = ("FS", "AR", "VE", "TA")
CONTROL_DIMENSIONS = ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def logistic(value: float) -> float:
    if value >= 0:
        z = exp(-value)
        return 1.0 / (1.0 + z)
    z = exp(value)
    return z / (1.0 + z)


class OrganizationKind(StrEnum):
    GOVERNMENT = "government"
    MILITARY = "military"
    POLICE = "police"
    INTELLIGENCE = "intelligence"
    PARTY = "party"
    INSURGENT = "insurgent"
    CIVIC = "civic"
    FOREIGN = "foreign"


@dataclass(slots=True)
class ControlVector:
    formal: float = 0.0
    physical: float = 0.0
    administrative: float = 0.0
    legal: float = 0.0
    fiscal: float = 0.0
    social: float = 0.0
    expected: float = 0.0

    def update(self, contributions: dict[str, float]) -> None:
        for key, delta in contributions.items():
            if key not in CONTROL_DIMENSIONS:
                raise KeyError(f"unknown control dimension: {key}")
            setattr(self, key, clamp(getattr(self, key) + delta))

    def effective(self, weights: dict[str, float] | None = None, epsilon: float = 1e-6) -> float:
        """Return the bounded weighted geometric mean of control dimensions.

        ``epsilon`` remains in the signature for API compatibility.  It is
        no longer added to state values because that made an all-zero vector
        positive and an all-one vector exceed the [0, 1] control domain.
        """
        if weights is None:
            weights = {
                key: 1.0 / len(CONTROL_DIMENSIONS) for key in CONTROL_DIMENSIONS
            }
        if set(weights) != set(CONTROL_DIMENSIONS):
            missing = sorted(set(CONTROL_DIMENSIONS) - set(weights))
            extra = sorted(set(weights) - set(CONTROL_DIMENSIONS))
            raise ValueError(
                f"control weights must cover every dimension; missing={missing}, extra={extra}"
            )
        if any(not isinstance(weight, (int, float)) or not isfinite(weight) or weight < 0
               for weight in weights.values()):
            raise ValueError("control weights must be finite nonnegative numbers")
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("control weights must have positive total mass")
        weighted_logs = 0.0
        for key in CONTROL_DIMENSIONS:
            weight = weights[key]
            if weight == 0:
                continue
            value = clamp(getattr(self, key))
            if value <= 0:
                return 0.0
            weighted_logs += (weight / total) * log(value)
        return clamp(exp(weighted_logs))

    def to_dict(self) -> dict[str, float]:
        # This vector is serialized on every observation and event boundary.
        # ``dataclasses.asdict`` recursively walks dataclass metadata and was
        # a measurable hot-path cost in ensemble/calibration runs.  The
        # fields are fixed by ``CONTROL_DIMENSIONS``, so a direct projection
        # is equivalent and avoids the recursive machinery.
        return {
            "formal": self.formal,
            "physical": self.physical,
            "administrative": self.administrative,
            "legal": self.legal,
            "fiscal": self.fiscal,
            "social": self.social,
            "expected": self.expected,
        }


@dataclass(slots=True)
class District:
    district_id: str
    name: str
    population: int
    terrain: str
    urbanization: float
    language_pattern: str
    role: str
    connectivity: float
    locality_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Locality:
    locality_id: str
    district_id: str
    name: str
    kind: str
    population: int
    # Population-scale productive base, in abstract resource-equivalent
    # output units. This is not a liquid account and is therefore not added
    # to person/organization resource stocks in the conservation ledger.
    economic_output: float
    infrastructure: float
    administrative_capacity: float
    terrain_friction: float
    observability: float
    # Administrative role is separate from settlement size.  Empirical case
    # geographies can add many real settlement anchors without implicitly
    # creating a police headquarters at every node.
    administrative_role: str = "administrative_center"
    control: dict[str, ControlVector] = field(default_factory=dict)
    governance: dict[str, float] = field(default_factory=dict)
    violence: float = 0.0
    disruption: float = 0.0
    displaced_population: float = 0.0
    # Synthetic geographic coordinates (kilometres in the generated national
    # reference frame).  They are optional so older case packages remain
    # loadable, but new worlds use them for spatially meaningful connectivity.
    x_km: float = 0.0
    y_km: float = 0.0


@dataclass(slots=True)
class Household:
    household_id: str
    member_ids: list[str]
    home_locality_id: str
    residence_locality_id: str
    # Derived aggregate of member Person.resources. It is a convenient
    # household/kin-cell view, not an additional independently owned stock.
    resources: float
    dependents: int


@dataclass(slots=True)
class Person:
    person_id: str
    household_id: str
    home_locality_id: str
    residence_locality_id: str
    weight: float
    age: int
    languages: dict[str, float]
    identities: dict[str, float]
    private_preference: dict[str, float]
    public_behavior: str = "neutral"
    grievance: float = 0.1
    fear: float = 0.1
    efficacy: float = 0.5
    expected_control: dict[str, float] = field(default_factory=dict)
    trust: dict[str, float] = field(default_factory=dict)
    # Liquid civilian economic stock represented by this cohort, in the same
    # abstract resource units used by organization/foreign financial accounts.
    # For weighted representatives this is already multiplied by weight;
    # consumers must never multiply it by weight a second time.
    resources: float = 1.0
    organization_id: str | None = None
    # Fraction of this representative person's population mobilized into the
    # armed organization's membership base.  It is not fielded fighter
    # strength: ``fighter_conversion_fraction`` converts changes in this base
    # into formation personnel.  Keeping the fraction explicit prevents one
    # sampled representative from switching its entire represented population
    # in a single recruitment draw.
    armed_fraction: float = 0.0
    displaced: bool = False
    community_id: str | None = None
    social_exposure: dict[str, float] = field(default_factory=dict)
    # Social/political alignment with specific insurgent organizations.  This
    # is distinct from armed membership: an ex-member or civilian sympathizer
    # can retain affinity to one franchise without belonging to it militarily.
    insurgent_affinity: dict[str, float] = field(default_factory=dict)
    state_legitimacy: float = 0.65
    government_legitimacy: float = 0.55
    party_legitimacy: dict[str, float] = field(default_factory=dict)
    political_access: float = 0.45
    external_state_id: str | None = None
    migration_status: str = "resident"
    origin_tie_strength: float = 1.0
    # Destination-specific expectations are sparse and populated for adjacent
    # localities by the scheduled beliefs process.
    expected_control_by_locality: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(slots=True)
class SocialCommunity:
    community_id: str
    locality_id: str
    member_ids: list[str]
    language_profile: dict[str, float]
    cohesion: float
    government_cooperation: float = 0.0
    insurgent_sympathy: float = 0.0
    bridge_member_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SocialEdge:
    person_a_id: str
    person_b_id: str
    layers: tuple[str, ...]
    weight: float
    language_compatibility: float
    trust: float
    represented_relationships: float


@dataclass(slots=True)
class Microzone:
    microzone_id: str
    locality_id: str
    name: str
    population_share: float
    infrastructure: float
    terrain_friction: float
    observability: float
    physical_control: dict[str, float] = field(default_factory=dict)
    presence_memory: dict[str, float] = field(default_factory=dict)
    presence_updated_at: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class PhysicalEdge:
    microzone_a_id: str
    microzone_b_id: str
    distance_km: float
    road_quality: float
    travel_time_hours: float
    disruption: float = 0.0


@dataclass(slots=True)
class SecurityPost:
    post_id: str
    organization_id: str
    locality_id: str
    microzone_id: str
    personnel: float
    fixed_presence: float
    available_fraction: float
    formation_id: str | None = None


@dataclass(slots=True)
class Patrol:
    patrol_id: str
    formation_id: str
    organization_id: str
    locality_id: str
    current_microzone_id: str
    route_history: list[str]
    available_at: float
    response_fraction: float
    # Last calendar time through which this patrol's dwell contribution has
    # been integrated into microzone presence memory.  Kept separate from
    # available_at so response availability and memory accounting cannot
    # silently change one another.
    presence_accounted_at: float | None = None


@dataclass(slots=True)
class ActorZoneBelief:
    actor_id: str
    microzone_id: str
    physical_control_estimate: float
    confidence: float
    updated_at: float
    last_reliable_observation_at: float = -1.0e9
    evidence_count: int = 0
    contradiction_index: float = 0.0


@dataclass(slots=True)
class Observation:
    """A source-generated, time-stamped claim about the conflict environment.

    The object deliberately stores an estimated value, never the true state that
    was used to generate it.  ``confidence`` is intrinsic source confidence;
    ``effective_confidence`` applies age decay at the time a recipient consumes
    the observation.
    """

    observation_id: str
    target_id: str | None
    locality_id: str
    timestamp: float
    source_id: str
    source_type: str
    observation_type: str
    estimated_value: dict[str, Any]
    confidence: float
    provenance: dict[str, Any]
    observer_actor_id: str
    microzone_id: str | None = None
    observer_node_id: str | None = None
    quality: float = 0.5
    decay_rate: float = 0.1
    target_actor_id: str | None = None
    target_formation_id: str | None = None
    received_at: float | None = None

    def effective_confidence(self, time: float) -> float:
        elapsed = max(0.0, time - self.timestamp)
        return clamp(self.confidence * self.quality * exp(-max(0.0, self.decay_rate) * elapsed))

    def confidence_at(self, time: float) -> float:
        return self.effective_confidence(time)

    def age(self, time: float) -> float:
        return max(0.0, time - self.timestamp)

    @property
    def source(self) -> str:
        return self.source_id

    @property
    def target(self) -> str | None:
        return self.target_id

    @property
    def subject(self) -> str | None:
        return self.target_id

    @property
    def location(self) -> str:
        return self.microzone_id or self.locality_id

    @property
    def estimated_state(self) -> dict[str, Any]:
        return self.estimated_value

    @property
    def value(self) -> dict[str, Any]:
        return self.estimated_value


@dataclass(slots=True)
class PresenceBelief:
    """Actor- or command-node-local belief about an organization's presence."""

    observer_id: str
    target_actor_id: str
    locality_id: str
    presence_estimate: float = 0.0
    confidence: float = 0.0
    updated_at: float = 0.0
    last_reliable_observation_at: float = -1.0e9
    evidence_count: int = 0
    contradiction_index: float = 0.0
    target_id: str | None = None
    microzone_id: str | None = None
    personnel_estimate: float = 0.0


@dataclass(slots=True)
class InformationRelay:
    """A delayed, probabilistically successful command-network transmission."""

    relay_id: str
    observation_id: str
    organization_id: str
    source_node_id: str
    destination_node_id: str
    route: list[str]
    sent_at: float
    arrives_at: float
    reliability: float
    latency_hours: float
    status: str = "in_transit"
    delivered_at: float | None = None


@dataclass(slots=True)
class CommandEdge:
    node_a_id: str
    node_b_id: str
    organization_id: str
    reliability: float
    latency_hours: float


@dataclass(slots=True)
class SupplySource:
    source_id: str
    organization_id: str
    locality_id: str
    stock: float
    capacity: float
    production_per_day: float
    operational: bool = True


@dataclass(slots=True)
class SupplyShipment:
    shipment_id: str
    organization_id: str
    source_id: str
    formation_id: str
    origin_locality_id: str
    destination_locality_id: str
    route: list[str]
    departed_at: float
    arrives_at: float
    quantity_sent: float
    quantity_deliverable: float
    loss: float
    status: str = "in_transit"


@dataclass(slots=True)
class FormationMovementOrder:
    order_id: str
    formation_id: str
    organization_id: str
    origin_locality_id: str
    destination_locality_id: str
    route: list[str]
    issued_at: float
    execute_at: float
    travel_time_hours: float
    distance_km: float
    supply_cost: float
    command_reliability: float
    command_latency_hours: float
    status: str = "pending"
    arrives_at: float | None = None
    purpose: str = "reallocation"


@dataclass(slots=True)
class ResourceFlow:
    flow_id: str
    time: float
    flow_type: str
    organization_id: str
    locality_id: str
    quantity: float
    source_id: str | None = None
    formation_id: str | None = None


@dataclass(slots=True)
class Organization:
    organization_id: str
    name: str
    kind: OrganizationKind
    resources: float
    cohesion: float
    discipline: float
    accountability: float
    local_knowledge: float
    persistence: float
    mobility: float
    institutional_quality: float
    member_ids: set[str] = field(default_factory=set)
    external_support: float = 0.0
    capital: dict[str, float] = field(default_factory=lambda: {
        "social": 0.0, "political": 0.0, "organizational": 0.0, "material": 0.0,
    })
    phenotype: dict[str, float] = field(default_factory=lambda: {
        "centralization": .5, "political_investment": .5, "governance_investment": .5,
        "dispersion": .5, "risk_tolerance": .5, "discipline": .5,
        "local_embeddedness": .5, "resource_dependence": .5,
    })
    ideology: dict[str, float] = field(default_factory=lambda: {"reform": .5, "separatism": .0})
    status: str = "active"
    founded_at: float = 0.0
    parent_ids: tuple[str, ...] = ()
    leader_id: str | None = None
    adaptation_rate: float = .12
    succession_count: int = 0
    external_sanctuary: float = 0.0
    sponsor_dependence: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class LeadershipAgent:
    leader_id: str
    organization_id: str
    competence: float
    charisma: float
    risk_tolerance: float
    ideological_rigidity: float
    political_skill: float
    organizational_skill: float
    active: bool = True


@dataclass(slots=True)
class ProtoOrganization:
    proto_id: str
    community_id: str
    locality_id: str
    member_ids: set[str]
    capital: dict[str, float]
    ideology: dict[str, float]
    leadership_potential: float
    created_at: float
    status: str = "mobilizing"


@dataclass(slots=True)
class OrganizationTransition:
    transition_id: str
    time: float
    transition_type: str
    parent_ids: tuple[str, ...]
    child_ids: tuple[str, ...]
    member_assignments: dict[str, tuple[str, ...]]
    resource_assignments: dict[str, float]
    formation_assignments: dict[str, tuple[str, ...]]
    inherited_traits: dict[str, dict[str, float]]
    causes: dict[str, float | str]


@dataclass(slots=True)
class PoliticalInstitution:
    institution_id: str
    name: str
    institution_type: str
    level: str
    locality_id: str | None
    district_id: str | None
    capacity: float
    autonomy: float
    compliance: float
    reach: float
    integrity: float
    resources: float
    governing_party_id: str | None = None


@dataclass(slots=True)
class PartyBranch:
    branch_id: str
    party_id: str
    locality_id: str
    member_ids: set[str]
    resources: float
    patronage_stock: float
    electoral_support: float
    institutional_influence: float
    broker_ids: set[str] = field(default_factory=set)


@dataclass(slots=True)
class LocalElite:
    elite_id: str
    person_id: str
    locality_id: str
    elite_type: str
    network_centrality: float
    # Explicit broker-controlled political resource account. Personal
    # civilian wealth remains in the linked Person.resources account.
    resources: float
    legitimacy: float
    institutional_ties: float
    party_alignment: str | None


@dataclass(slots=True)
class PoliticalTransfer:
    transfer_id: str
    time: float
    transfer_type: str
    source_id: str
    destination_id: str
    locality_id: str | None
    amount: float
    purpose: str


@dataclass(slots=True)
class PolicyImplementation:
    implementation_id: str
    time: float
    institution_id: str
    locality_id: str
    budget: float
    public_spending: float
    patronage: float
    private_diversion: float
    implementation_quality: float
    service_output: dict[str, float]


@dataclass(slots=True)
class Election:
    election_id: str
    time: float
    votes: dict[str, float]
    abstention: float
    winner_party_id: str
    prior_ruling_party_id: str | None


@dataclass(slots=True)
class ForeignState:
    state_id: str
    name: str
    # Population-scale external financial/material resource account.
    resources: float
    stability_preference: float
    government_alignment: float
    ideological_alignment: float
    border_security_priority: float
    regional_influence: float
    commercial_interest: float
    humanitarian_preference: float
    cost_sensitivity: float
    domestic_opposition: float
    willingness: float
    language_profile: dict[str, float]
    opportunity: float
    rival_ids: set[str] = field(default_factory=set)
    cumulative_cost: float = 0.0
    cumulative_casualties: float = 0.0


@dataclass(slots=True)
class BorderSegment:
    border_id: str
    foreign_state_id: str
    district_id: str
    locality_id: str
    terrain_friction: float
    infrastructure: float
    legal_permeability: float
    social_permeability: float
    language_overlap: float
    kinship_overlap: float
    state_monitoring: float


@dataclass(slots=True)
class ExternalSupport:
    support_id: str
    time: float
    foreign_state_id: str
    recipient_id: str
    components: dict[str, float]
    strategic_alignment: float
    delivered: bool = True

    def total(self) -> float:
        return sum(self.components.values())


@dataclass(slots=True)
class ExternalTransfer:
    transfer_id: str
    time: float
    transfer_type: str
    source_id: str
    destination_id: str
    amount: float
    border_id: str | None
    causal_event_id: str


@dataclass(slots=True)
class DiasporaLink:
    link_id: str
    person_id: str
    foreign_state_id: str
    origin_locality_id: str
    social_strength: float
    # Represented-cohort remittance capacity in resource units, not a
    # per-agent or per-capita scalar.
    financial_capacity: float
    information_reliability: float
    created_at: float


@dataclass(slots=True)
class InterpreterBroker:
    interpreter_id: str
    person_id: str
    foreign_state_id: str
    locality_id: str
    foreign_language: float
    local_language: float
    foreign_trust: float
    local_trust: float
    cultural_knowledge: float


@dataclass(slots=True)
class ForeignBelief:
    foreign_state_id: str
    locality_id: str
    government_control_estimate: float
    insurgent_presence_estimate: float
    confidence: float
    updated_at: float


@dataclass(slots=True)
class ForeignIntervention:
    intervention_id: str
    foreign_state_id: str
    recipient_id: str
    started_at: float
    mode: str
    provided_capacity: float
    transfer_efficiency: float
    crowding_out: float
    force_formation_ids: set[str] = field(default_factory=set)
    status: str = "active"
    withdrawal_rate: float = 0.0
    cumulative_transferred_capacity: float = 0.0
    cumulative_retained_host_capacity: float = 0.0
    cumulative_crowding_out: float = 0.0
    peak_provided_capacity: float = 0.0
    withdrawn_capacity: float = 0.0


@dataclass(slots=True)
class Negotiation:
    negotiation_id: str
    government_id: str
    insurgent_ids: tuple[str, ...]
    initiated_at: float
    war_values: dict[str, float]
    peace_values: dict[str, float]
    bargaining_surplus: dict[str, float]
    credibility: float
    fragmentation: float
    foreign_mediator_ids: tuple[str, ...] = ()
    status: str = "active"
    concluded_at: float | None = None


@dataclass(slots=True)
class AgreementProvision:
    provision_id: str
    agreement_id: str
    provision_type: str
    target: float
    progress: float
    government_will: float
    insurgent_will: float
    institutional_resistance: float
    monitoring: float
    status: str = "pending"


@dataclass(slots=True)
class PeaceAgreement:
    agreement_id: str
    negotiation_id: str
    signed_at: float
    government_id: str
    signatory_ids: tuple[str, ...]
    rejecting_faction_ids: tuple[str, ...]
    provision_ids: tuple[str, ...]
    credibility: float
    foreign_guarantor_ids: tuple[str, ...] = ()
    status: str = "signed"
    completed_at: float | None = None
    failed_at: float | None = None


@dataclass(slots=True)
class PeaceTransition:
    transition_id: str
    time: float
    transition_type: str
    agreement_id: str | None
    actor_ids: tuple[str, ...]
    personnel: float = 0.0
    arms: float = 0.0
    resources: float = 0.0
    causes: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class ArmedFormation:
    formation_id: str
    organization_id: str
    locality_id: str
    personnel: float
    quality: float
    cohesion: float
    readiness: float
    sustainment: float
    information: float
    mobility: float
    command: float
    embeddedness: float
    fatigue: float = 0.0
    availability: float = 0.85
    supply_stock: float = 0.0
    supply_capacity: float = 0.0
    home_locality_id: str = ""
    moving: bool = False
    operational_status: str = "effective"
    cumulative_losses: float = 0.0
    external_state_id: str | None = None
    outside_pineland: bool = False
    current_microzone_id: str | None = None

    def supply_fraction(self) -> float:
        return clamp(self.supply_stock / self.supply_capacity) if self.supply_capacity > 0 else clamp(self.sustainment)

    def fatigue_adjusted_readiness(self) -> float:
        """Stored readiness after fatigue, before logistics/command multipliers.

        This is useful for mechanisms such as local sensing where supply stock
        and headquarters connectivity must not be silently re-applied through
        the composite effective-readiness term.
        """
        fatigue_effect = 1.0 - 0.65 * clamp(self.fatigue)
        return clamp(self.readiness * fatigue_effect)

    def effective_readiness(self) -> float:
        supply_effect = 0.2 + 0.8 * self.supply_fraction()
        return clamp(self.fatigue_adjusted_readiness() * supply_effect * clamp(self.command))

    def deployable_personnel(self) -> float:
        """Personnel physically available before readiness/capability effects."""
        if self.moving or self.outside_pineland or self.operational_status == "ineffective":
            return 0.0
        return max(0.0, self.personnel) * clamp(self.availability)

    def available_personnel(self) -> float:
        return self.deployable_personnel() * self.effective_readiness()

    def effective_strength(self) -> float:
        available = self.available_personnel()
        if available <= 0:
            return 0.0
        return available * self.quality * self.cohesion * (0.5 + self.information)


@dataclass(slots=True)
class Engagement:
    engagement_id: str
    event_id: str
    time: float
    locality_id: str
    microzone_id: str
    formation_a_id: str
    formation_b_id: str
    detected_by: tuple[str, ...]
    initiative: dict[str, float]
    effective_capability: dict[str, float]
    personnel_losses: dict[str, float]
    cohesion_losses: dict[str, float]
    readiness_losses: dict[str, float]
    supply_consumed: dict[str, float]
    civilian_harm: float
    disengaged: tuple[str, ...]
    ineffective: tuple[str, ...]
    reinforcement_order_ids: tuple[str, ...]
    perceived_momentum_signal: float
    initiator_organization_id: str | None = None
    contact_cause: str = "unspecified"
    withdrawal_order_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ActorBelief:
    actor_id: str
    locality_id: str
    control_estimate: ControlVector
    confidence: float
    updated_at: float
    last_reliable_observation_at: float = -1.0e9
    evidence_count: int = 0
    contradiction_index: float = 0.0
    # Actor-local estimate of recent violence/repression.  This is deliberately
    # separate from realized locality violence so political decisions can use
    # experienced/reported conditions rather than hidden truth.
    violence_estimate: float = 0.2


@dataclass(slots=True)
class CausalContribution:
    time: float
    locality_id: str
    dimension: str
    amount: float
    mechanism: str
    event_id: str


@dataclass(slots=True)
class SyntheticRecord:
    event_id: str
    time: float
    locality_id: str | None
    event_type: str
    recorded: bool
    reported_severity: float
    reported_actor: str | None
    geocoding_error: bool
    geocoding_error_distance_km: float = 0.0
    source_type: str = "process_event"


@dataclass(slots=True)
class EventLogEntry:
    event_id: str
    time: float
    event_type: str
    locality_id: str | None
    actor_ids: tuple[str, ...]
    affected_entity_ids: tuple[str, ...]
    true_state_delta: dict[str, Any]
    causal_parent_ids: tuple[str, ...]
    observations_by_actor: dict[str, dict[str, Any]]
    synthetic_record: SyntheticRecord | None
    random_stream_id: str
    parameter_snapshot_id: str


@dataclass(slots=True)
class StockTransaction:
    """Cross-domain material/manpower delta recorded at event boundaries.

    A transaction is an audit record, not a second source of truth.  It makes
    conversions (for example civilian resources to formation supply) visible
    across ledgers and lets validation reconcile all stocks without guessing
    which subsystem performed a mutation.
    """

    transaction_id: str
    time: float
    event_id: str
    event_type: str
    stock_class: str
    stock_name: str
    before: float
    after: float
    delta: float
    boundary: str = "internal"
    flow_kind: str = "internal_transfer"


@dataclass(slots=True)
class StateDelta:
    """Sparse event-time state needed for causal-microscope reconstruction."""

    event_id: str
    time: float
    event_type: str
    control_changes: dict[str, dict[str, float]]
    formation_state: dict[str, dict[str, Any]]
    belief_state: dict[str, float]
    organization_ids: tuple[str, ...]
