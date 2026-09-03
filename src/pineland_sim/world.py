from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import random
from typing import Any

from .config import SimulationConfig
from .entities import (
    ActorBelief,
    ActorZoneBelief,
    ArmedFormation,
    CausalContribution,
    CommandEdge,
    District,
    EventLogEntry,
    Household,
    FormationMovementOrder,
    InformationRelay,
    Engagement,
    LeadershipAgent,
    ProtoOrganization,
    OrganizationTransition,
    PoliticalInstitution,
    PartyBranch,
    LocalElite,
    PoliticalTransfer,
    PolicyImplementation,
    Election,
    Locality,
    Organization,
    OrganizationKind,
    Microzone,
    Patrol,
    PhysicalEdge,
    Person,
    SocialCommunity,
    SocialEdge,
    SecurityPost,
    ResourceFlow,
    Observation,
    PresenceBelief,
    SupplyShipment,
    SupplySource,
    SyntheticRecord,
)


@dataclass(slots=True)
class WorldState:
    config: SimulationConfig
    time: float = 0.0
    districts: dict[str, District] = field(default_factory=dict)
    localities: dict[str, Locality] = field(default_factory=dict)
    households: dict[str, Household] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    social_communities: dict[str, SocialCommunity] = field(default_factory=dict)
    social_edges: dict[tuple[str, str], SocialEdge] = field(default_factory=dict)
    social_neighbors: dict[str, list[str]] = field(default_factory=dict)
    microzones: dict[str, Microzone] = field(default_factory=dict)
    physical_edges: dict[tuple[str, str], PhysicalEdge] = field(default_factory=dict)
    physical_neighbors: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    security_posts: dict[str, SecurityPost] = field(default_factory=dict)
    patrols: dict[str, Patrol] = field(default_factory=dict)
    zone_beliefs: dict[tuple[str, str], ActorZoneBelief] = field(default_factory=dict)
    observations: dict[str, Observation] = field(default_factory=dict)
    observation_index: dict[tuple[str, str, str], list[float]] = field(default_factory=dict)
    information_relays: dict[str, InformationRelay] = field(default_factory=dict)
    presence_beliefs: dict[tuple[str, str, str, str], PresenceBelief] = field(default_factory=dict)
    node_presence_beliefs: dict[tuple[str, str, str, str], PresenceBelief] = field(default_factory=dict)
    control_beliefs: dict[tuple[str, str, str], ActorBelief] = field(default_factory=dict)
    information_detections: dict[str, int] = field(default_factory=lambda: {
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 0,
    })
    information_detection_by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    last_information_decay_at: float = 0.0
    command_edges: dict[tuple[str, str], CommandEdge] = field(default_factory=dict)
    supply_sources: dict[str, SupplySource] = field(default_factory=dict)
    supply_shipments: dict[str, SupplyShipment] = field(default_factory=dict)
    movement_orders: dict[str, FormationMovementOrder] = field(default_factory=dict)
    resource_flows: list[ResourceFlow] = field(default_factory=list)
    control_cost_consumed: dict[str, float] = field(default_factory=dict)
    organizations: dict[str, Organization] = field(default_factory=dict)
    formations: dict[str, ArmedFormation] = field(default_factory=dict)
    engagements: dict[str, Engagement] = field(default_factory=dict)
    leaders: dict[str, LeadershipAgent] = field(default_factory=dict)
    proto_organizations: dict[str, ProtoOrganization] = field(default_factory=dict)
    organization_transitions: list[OrganizationTransition] = field(default_factory=list)
    political_institutions: dict[str, PoliticalInstitution] = field(default_factory=dict)
    party_branches: dict[str, PartyBranch] = field(default_factory=dict)
    local_elites: dict[str, LocalElite] = field(default_factory=dict)
    political_transfers: list[PoliticalTransfer] = field(default_factory=list)
    policy_implementations: list[PolicyImplementation] = field(default_factory=list)
    elections: list[Election] = field(default_factory=list)
    ruling_party_id: str | None = None
    private_diversion_stock: float = 0.0
    cumulative_public_spending: float = 0.0
    beliefs: dict[tuple[str, str], ActorBelief] = field(default_factory=dict)
    adjacency: dict[str, dict[str, float]] = field(default_factory=dict)
    event_log: list[EventLogEntry] = field(default_factory=list)
    causal_ledger: list[CausalContribution] = field(default_factory=list)
    synthetic_records: list[SyntheticRecord] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    initial_population: float = 0.0
    cumulative_deaths: float = 0.0
    cumulative_external_inflow: float = 0.0
    initial_supply_stock: float = 0.0
    cumulative_supply_produced: float = 0.0
    cumulative_supply_consumed: float = 0.0
    cumulative_supply_lost: float = 0.0
    cumulative_civilian_harm: float = 0.0

    @property
    def observation_records(self) -> list[Observation]:
        """Stable list view for analysis code that prefers event-log semantics."""
        return list(self.observations.values())

    @property
    def reports(self) -> list[Observation]:
        return self.observation_records

    def weighted_population(self) -> float:
        return sum(person.weight for person in self.persons.values())

    def formation_personnel(self) -> float:
        return sum(formation.personnel for formation in self.formations.values())

    def assert_invariants(self, tolerance: float = 1e-6) -> None:
        resident = self.weighted_population()
        expected = self.initial_population - self.cumulative_deaths + self.cumulative_external_inflow
        if abs(resident - expected) > max(tolerance, expected * 1e-10):
            raise AssertionError(f"population conservation failed: resident={resident}, expected={expected}")
        for locality in self.localities.values():
            for vector in locality.control.values():
                for value in vector.to_dict().values():
                    if not 0.0 <= value <= 1.0:
                        raise AssertionError("control component outside [0, 1]")
        for formation in self.formations.values():
            if (formation.personnel < 0 or formation.sustainment < 0 or formation.supply_stock < 0 or
                    formation.supply_stock > formation.supply_capacity + tolerance):
                raise AssertionError("negative formation stock")
            if (not 0 <= formation.cohesion <= 1 or not 0 <= formation.readiness <= 1 or
                    formation.cumulative_losses < 0):
                raise AssertionError("invalid formation combat state")
        for organization in self.organizations.values():
            if organization.resources < -tolerance:
                raise AssertionError("negative organization budget")
            if any(not 0 <= value <= 1 for value in organization.capital.values()):
                raise AssertionError("organizational capital outside [0, 1]")
            if any(not 0 <= value <= 1 for value in organization.phenotype.values()):
                raise AssertionError("organizational phenotype outside [0, 1]")
            if any(person_id not in self.persons for person_id in organization.member_ids):
                raise AssertionError("organization references missing member")
        memberships = [person_id for organization in self.organizations.values()
                       if organization.status == "active" and organization.kind is OrganizationKind.INSURGENT
                       for person_id in organization.member_ids]
        if len(memberships) != len(set(memberships)):
            raise AssertionError("person belongs to multiple active organizations")
        for organization in self.organizations.values():
            if (organization.status == "active" and organization.kind is OrganizationKind.INSURGENT and any(
                    self.persons[pid].organization_id != organization.organization_id
                    for pid in organization.member_ids)):
                raise AssertionError("active organization membership is not reciprocal")
        if any(institution.resources < -tolerance or not 0 <= institution.capacity <= 1
               for institution in self.political_institutions.values()):
            raise AssertionError("invalid political institution state")
        if any(branch.resources < -tolerance or branch.patronage_stock < -tolerance
               for branch in self.party_branches.values()):
            raise AssertionError("invalid party branch stock")
        for microzone in self.microzones.values():
            if not 0 <= microzone.population_share <= 1:
                raise AssertionError("microzone population share outside [0, 1]")
            if any(not 0 <= value <= 1 for value in microzone.physical_control.values()):
                raise AssertionError("microzone physical control outside [0, 1]")
            if any(value < 0 for value in microzone.presence_memory.values()):
                raise AssertionError("negative presence memory")
        for locality_id in self.localities:
            share = sum(zone.population_share for zone in self.microzones.values()
                        if zone.locality_id == locality_id)
            if self.microzones and abs(share - 1.0) > 1e-9:
                raise AssertionError(f"microzone population shares do not sum to one: {locality_id}")
        for edge in self.physical_edges.values():
            if edge.travel_time_hours <= 0 or edge.distance_km <= 0:
                raise AssertionError("physical edge has nonpositive distance or travel time")
        for patrol in self.patrols.values():
            if patrol.current_microzone_id not in self.microzones:
                raise AssertionError("patrol references missing microzone")
        for edge in self.command_edges.values():
            if not 0 <= edge.reliability <= 1 or edge.latency_hours < 0:
                raise AssertionError("invalid command edge reliability or latency")
        for shipment in self.supply_shipments.values():
            if shipment.quantity_sent < 0 or shipment.quantity_deliverable < 0 or shipment.loss < 0:
                raise AssertionError("negative supply shipment quantity")
            if abs(shipment.quantity_sent - shipment.quantity_deliverable - shipment.loss) > tolerance:
                raise AssertionError("shipment quantities do not reconcile")
        for observation in self.observations.values():
            if not 0 <= observation.confidence <= 1 or observation.quality < 0 or observation.quality > 1:
                raise AssertionError("observation confidence or quality outside [0, 1]")
            if observation.decay_rate < 0 or observation.timestamp < 0:
                raise AssertionError("invalid observation age metadata")
        for relay in self.information_relays.values():
            if not 0 <= relay.reliability <= 1 or relay.arrives_at < relay.sent_at:
                raise AssertionError("invalid information relay")
        for belief in list(self.presence_beliefs.values()) + list(self.node_presence_beliefs.values()):
            if not 0 <= belief.presence_estimate <= 1 or not 0 <= belief.confidence <= 1:
                raise AssertionError("presence belief outside [0, 1]")
        for belief in self.control_beliefs.values():
            if not 0 <= belief.confidence <= 1 or any(
                    not 0 <= value <= 1 for value in belief.control_estimate.to_dict().values()):
                raise AssertionError("control belief outside [0, 1]")
        if any(value < 0 for value in self.information_detections.values()):
            raise AssertionError("negative information detection count")
        if self.supply_sources:
            current_supply = sum(source.stock for source in self.supply_sources.values())
            current_supply += sum(formation.supply_stock for formation in self.formations.values())
            current_supply += sum(
                shipment.quantity_deliverable for shipment in self.supply_shipments.values()
                if shipment.status == "in_transit"
            )
            expected_supply = (self.initial_supply_stock + self.cumulative_supply_produced -
                               self.cumulative_supply_consumed - self.cumulative_supply_lost)
            if abs(current_supply - expected_supply) > max(tolerance, abs(expected_supply) * 1e-9):
                raise AssertionError(
                    f"supply conservation failed: current={current_supply}, expected={expected_supply}"
                )
            if any(source.stock < -tolerance or source.stock > source.capacity + tolerance
                   for source in self.supply_sources.values()):
                raise AssertionError("supply source outside stock bounds")
        for person in self.persons.values():
            if person.community_id not in self.social_communities:
                raise AssertionError(f"person without valid social community: {person.person_id}")
        for key, edge in self.social_edges.items():
            if key != tuple(sorted(key)) or edge.person_a_id not in self.persons or edge.person_b_id not in self.persons:
                raise AssertionError("invalid social edge endpoint or key")
            if not 0 <= edge.weight <= 1 or not 0 <= edge.language_compatibility <= 1 or not 0 <= edge.trust <= 1:
                raise AssertionError("social edge quantity outside [0, 1]")
            if edge.person_b_id not in self.social_neighbors.get(edge.person_a_id, ()):
                raise AssertionError("social adjacency is not symmetric")
            if edge.person_a_id not in self.social_neighbors.get(edge.person_b_id, ()):
                raise AssertionError("social adjacency is not symmetric")

    def summary(self) -> dict[str, Any]:
        government_control = [loc.control["government"].effective() for loc in self.localities.values()]
        insurgent_control = [loc.control.get("insurgent").effective() if "insurgent" in loc.control else 0.0 for loc in self.localities.values()]
        finite_information_ages = [
            max(0.0, self.time - belief.last_reliable_observation_at)
            for belief in self.presence_beliefs.values()
            if belief.last_reliable_observation_at > -1.0e8
        ]
        return {
            "time": self.time,
            "districts": len(self.districts),
            "localities": len(self.localities),
            "agents": len(self.persons),
            "represented_population": self.weighted_population(),
            "households": len(self.households),
            "social_communities": len(self.social_communities),
            "social_edges": len(self.social_edges),
            "mean_social_degree": (2 * len(self.social_edges) / len(self.persons)) if self.persons else 0.0,
            "microzones": len(self.microzones),
            "physical_edges": len(self.physical_edges),
            "security_posts": len(self.security_posts),
            "patrols": len(self.patrols),
            "observations": len(self.observations),
            "mean_effective_observation_confidence": (
                sum(observation.effective_confidence(self.time) for observation in self.observations.values()) /
                len(self.observations) if self.observations else 0.0
            ),
            "mean_information_age_days": (
                sum(finite_information_ages) / len(finite_information_ages)
                if finite_information_ages else None
            ),
            "active_information_relays": sum(relay.status == "in_transit"
                                               for relay in self.information_relays.values()),
            "supply_sources": len(self.supply_sources),
            "active_shipments": sum(shipment.status == "in_transit"
                                    for shipment in self.supply_shipments.values()),
            "movement_orders": len(self.movement_orders),
            "supply_consumed": self.cumulative_supply_consumed,
            "organizations": len(self.organizations),
            "active_armed_organizations": sum(
                organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
                for organization in self.organizations.values()),
            "proto_organizations": sum(proto.status == "mobilizing"
                                        for proto in self.proto_organizations.values()),
            "organization_transitions": len(self.organization_transitions),
            "political_institutions": len(self.political_institutions),
            "party_branches": len(self.party_branches),
            "elections": len(self.elections),
            "ruling_party_id": self.ruling_party_id,
            "formations": len(self.formations),
            "engagements": len(self.engagements),
            "civilian_harm": self.cumulative_civilian_harm,
            "events": len(self.event_log),
            "synthetic_records": sum(record.recorded for record in self.synthetic_records),
            "mean_government_effective_control": sum(government_control) / len(government_control),
            "mean_insurgent_effective_control": sum(insurgent_control) / len(insurgent_control),
            "detection_counts": dict(self.information_detections),
        }

    def checkpoint(self) -> dict[str, Any]:
        snapshot = {
            "time": self.time,
            "summary": self.summary(),
            "control": {
                locality_id: {actor: vector.to_dict() for actor, vector in locality.control.items()}
                for locality_id, locality in self.localities.items()
            },
            "community_state": {
                community_id: {
                    "locality_id": community.locality_id,
                    "government_cooperation": community.government_cooperation,
                    "insurgent_sympathy": community.insurgent_sympathy,
                }
                for community_id, community in self.social_communities.items()
            },
            "rng_namespace": self.config.random_stream_namespace,
            "seed": self.config.seed,
            "information": {
                "observations": len(self.observations),
                "active_relays": sum(relay.status == "in_transit"
                                      for relay in self.information_relays.values()),
            },
        }
        self.checkpoints.append(snapshot)
        return snapshot

    def write_results(self, output_dir: str | Path) -> None:
        from .networks import network_diagnostics
        from .physical import physical_diagnostics
        from .logistics import logistics_diagnostics
        from .information import information_diagnostics
        from .combat import combat_diagnostics
        from .organization_ecology import organization_ecology_diagnostics
        from .political_order import political_diagnostics

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        (output / "checkpoints.json").write_text(json.dumps(self.checkpoints, indent=2), encoding="utf-8")
        records = [asdict(record) for record in self.synthetic_records]
        (output / "synthetic_records.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        causal = [asdict(item) for item in self.causal_ledger]
        (output / "causal_ledger.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in causal), encoding="utf-8"
        )
        (output / "network_diagnostics.json").write_text(
            json.dumps(network_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "physical_diagnostics.json").write_text(
            json.dumps(physical_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "logistics_diagnostics.json").write_text(
            json.dumps(logistics_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "information_diagnostics.json").write_text(
            json.dumps(information_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "combat_diagnostics.json").write_text(
            json.dumps(combat_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "organization_ecology.json").write_text(
            json.dumps(organization_ecology_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "political_diagnostics.json").write_text(
            json.dumps(political_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "political_transfers.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.political_transfers),
            encoding="utf-8",
        )
        (output / "policy_implementations.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.policy_implementations),
            encoding="utf-8",
        )
        (output / "elections.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.elections),
            encoding="utf-8",
        )
        (output / "organization_transitions.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.organization_transitions),
            encoding="utf-8",
        )
        (output / "engagements.jsonl").write_text(
            "".join(json.dumps(asdict(engagement)) + "\n"
                    for engagement in self.engagements.values()), encoding="utf-8"
        )
        (output / "observations.jsonl").write_text(
            "".join(json.dumps(asdict(observation)) + "\n"
                    for observation in self.observations.values()),
            encoding="utf-8",
        )
        (output / "information_relays.jsonl").write_text(
            "".join(json.dumps(asdict(relay)) + "\n"
                    for relay in self.information_relays.values()),
            encoding="utf-8",
        )
        (output / "resource_flows.jsonl").write_text(
            "".join(json.dumps(asdict(flow)) + "\n" for flow in self.resource_flows),
            encoding="utf-8",
        )

    def clone(self) -> "WorldState":
        import copy

        return copy.deepcopy(self)


def seeded_rng(config: SimulationConfig, stream: str) -> random.Random:
    # Stable across Python processes, unlike hash().
    token = f"{config.seed}:{config.random_stream_namespace}:{stream}".encode()
    value = int.from_bytes(__import__("hashlib").sha256(token).digest()[:8], "big")
    return random.Random(value)
