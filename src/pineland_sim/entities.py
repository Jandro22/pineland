from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import exp, log
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
        weights = weights or {key: 1.0 / len(CONTROL_DIMENSIONS) for key in CONTROL_DIMENSIONS}
        total = sum(weights.values())
        return exp(sum((weights[k] / total) * log(getattr(self, k) + epsilon) for k in CONTROL_DIMENSIONS))

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


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
    economic_output: float
    infrastructure: float
    administrative_capacity: float
    terrain_friction: float
    observability: float
    control: dict[str, ControlVector] = field(default_factory=dict)
    governance: dict[str, float] = field(default_factory=dict)
    violence: float = 0.0
    disruption: float = 0.0
    displaced_population: float = 0.0


@dataclass(slots=True)
class Household:
    household_id: str
    member_ids: list[str]
    home_locality_id: str
    residence_locality_id: str
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
    resources: float = 1.0
    organization_id: str | None = None
    displaced: bool = False
    community_id: str | None = None
    social_exposure: dict[str, float] = field(default_factory=dict)


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


@dataclass(slots=True)
class ActorZoneBelief:
    actor_id: str
    microzone_id: str
    physical_control_estimate: float
    confidence: float
    updated_at: float


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

    def supply_fraction(self) -> float:
        return clamp(self.supply_stock / self.supply_capacity) if self.supply_capacity > 0 else clamp(self.sustainment)

    def effective_readiness(self) -> float:
        supply_effect = 0.2 + 0.8 * self.supply_fraction()
        fatigue_effect = 1.0 - 0.65 * clamp(self.fatigue)
        return clamp(self.readiness * supply_effect * fatigue_effect * clamp(self.command))

    def available_personnel(self) -> float:
        if self.moving:
            return 0.0
        return self.personnel * clamp(self.availability) * self.effective_readiness()

    def effective_strength(self) -> float:
        return max(1e-9, self.available_personnel() * self.quality * self.cohesion * (0.5 + self.information))


@dataclass(slots=True)
class ActorBelief:
    actor_id: str
    locality_id: str
    control_estimate: ControlVector
    confidence: float
    updated_at: float


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
