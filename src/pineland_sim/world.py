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
    ForeignState,
    BorderSegment,
    ExternalSupport,
    ExternalTransfer,
    DiasporaLink,
    InterpreterBroker,
    ForeignBelief,
    ForeignIntervention,
    Negotiation,
    PeaceAgreement,
    AgreementProvision,
    PeaceTransition,
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
    StockTransaction,
    StateDelta,
)


@dataclass(slots=True)
class WorldState:
    config: SimulationConfig
    time: float = 0.0
    in_burn_in: bool = False
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
    observation_source_index: dict[tuple[str, str, str], list[tuple[float, str]]] = field(default_factory=dict)
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
    organization_eligibility_log: list[dict[str, Any]] = field(default_factory=list)
    political_institutions: dict[str, PoliticalInstitution] = field(default_factory=dict)
    party_branches: dict[str, PartyBranch] = field(default_factory=dict)
    local_elites: dict[str, LocalElite] = field(default_factory=dict)
    political_transfers: list[PoliticalTransfer] = field(default_factory=list)
    policy_implementations: list[PolicyImplementation] = field(default_factory=list)
    elections: list[Election] = field(default_factory=list)
    ruling_party_id: str | None = None
    private_diversion_stock: float = 0.0
    cumulative_public_spending: float = 0.0
    foreign_states: dict[str, ForeignState] = field(default_factory=dict)
    border_segments: dict[str, BorderSegment] = field(default_factory=dict)
    external_support: list[ExternalSupport] = field(default_factory=list)
    external_transfers: list[ExternalTransfer] = field(default_factory=list)
    diaspora_links: dict[str, DiasporaLink] = field(default_factory=dict)
    interpreter_brokers: dict[str, InterpreterBroker] = field(default_factory=dict)
    foreign_beliefs: dict[tuple[str, str], ForeignBelief] = field(default_factory=dict)
    foreign_interventions: dict[str, ForeignIntervention] = field(default_factory=dict)
    negotiations: dict[str, Negotiation] = field(default_factory=dict)
    peace_agreements: dict[str, PeaceAgreement] = field(default_factory=dict)
    agreement_provisions: dict[str, AgreementProvision] = field(default_factory=dict)
    peace_transitions: list[PeaceTransition] = field(default_factory=list)
    ceasefires: dict[str, str] = field(default_factory=dict)
    demobilized_personnel: float = 0.0
    demobilized_arms: float = 0.0
    cumulative_external_remittances: float = 0.0
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
    cumulative_resource_to_supply: float = 0.0
    cumulative_civilian_harm: float = 0.0
    stock_transactions: list[StockTransaction] = field(default_factory=list)
    state_deltas: list[StateDelta] = field(default_factory=list)
    initial_tracked_stocks: dict[str, float] = field(default_factory=dict)

    @property
    def observation_records(self) -> list[Observation]:
        """Stable list view for analysis code that prefers event-log semantics."""
        return list(self.observations.values())

    @property
    def reports(self) -> list[Observation]:
        return self.observation_records

    def truth_view(self):
        from .views import WorldTruthView
        return WorldTruthView(self)

    def belief_view(self, actor_id: str | None = None):
        from .views import ActorBeliefView
        return ActorBeliefView(self, actor_id)

    def record_view(self):
        from .views import EmpiricalRecordView
        return EmpiricalRecordView(self)

    def weighted_population(self) -> float:
        return sum(person.weight for person in self.persons.values())

    def formation_personnel(self) -> float:
        return sum(formation.personnel for formation in self.formations.values())

    def tracked_stock_totals(self) -> dict[str, float]:
        """Aggregate every tracked material/manpower stock by domain.

        These are deliberately aggregates for cheap event-boundary snapshots;
        detailed entity-level histories remain in the domain ledgers.
        """
        return {
            "person_resources": sum(person.resources for person in self.persons.values()),
            "organization_resources": sum(org.resources for org in self.organizations.values()),
            "institution_resources": sum(item.resources for item in self.political_institutions.values()),
            "party_branch_resources": sum(item.resources + item.patronage_stock
                                           for item in self.party_branches.values()),
            "foreign_resources": sum(state.resources for state in self.foreign_states.values()),
            "private_diversion": self.private_diversion_stock,
            "military_supply": (
                sum(source.stock for source in self.supply_sources.values()) +
                sum(formation.supply_stock for formation in self.formations.values()) +
                self.demobilized_arms +
                sum(shipment.quantity_deliverable for shipment in self.supply_shipments.values()
                    if shipment.status == "in_transit")
            ),
            "formation_personnel": self.formation_personnel(),
            "demobilized_personnel": self.demobilized_personnel,
        }

    def initialize_stock_ledger(self) -> None:
        self.initial_tracked_stocks = self.tracked_stock_totals()

    def record_stock_transactions(self, event_id: str, event_type: str,
                                  before: dict[str, float], after: dict[str, float]) -> None:
        for stock_name in sorted(set(before) | set(after)):
            old, new = before.get(stock_name, 0.0), after.get(stock_name, 0.0)
            delta = new - old
            if abs(delta) <= 1e-12:
                continue
            stock_class = "manpower" if stock_name in {"formation_personnel", "demobilized_personnel"} else "material"
            self.stock_transactions.append(StockTransaction(
                f"ST{len(self.stock_transactions) + 1:012d}", self.time, event_id,
                event_type, stock_class, stock_name, old, new, delta,
                "boundary" if event_type in {"economy", "governance", "political_order", "foreign_affairs"} else "internal",
            ))

    def stock_ledger_residual(self, stock_name: str | None = None) -> float:
        current = self.tracked_stock_totals()
        names = [stock_name] if stock_name else list(current)
        residual = 0.0
        for name in names:
            initial = self.initial_tracked_stocks.get(name, current.get(name, 0.0))
            delta = sum(item.delta for item in self.stock_transactions if item.stock_name == name)
            residual += current.get(name, 0.0) - initial - delta
        return residual

    def stock_ledger_diagnostics(self) -> dict[str, Any]:
        """Return cross-domain ledger coverage and conversion diagnostics."""
        by_class: dict[str, dict[str, float]] = {}
        by_boundary: dict[str, float] = {}
        for item in self.stock_transactions:
            by_class.setdefault(item.stock_class, {"positive": 0.0, "negative": 0.0, "net": 0.0})
            bucket = by_class[item.stock_class]
            bucket["positive" if item.delta >= 0 else "negative"] += abs(item.delta)
            bucket["net"] += item.delta
            by_boundary[item.boundary] = by_boundary.get(item.boundary, 0.0) + item.delta
        return {
            "initial": dict(self.initial_tracked_stocks),
            "current": self.tracked_stock_totals(),
            "residual": self.stock_ledger_residual(),
            "by_class": by_class,
            "by_boundary_net": by_boundary,
            "resource_to_supply_conversion": self.cumulative_resource_to_supply,
            "transaction_count": len(self.stock_transactions),
            "event_coverage": len({item.event_id for item in self.stock_transactions}),
            "warning": ("cross-domain totals are a diagnostic ledger, not a claim that "
                        "every exogenous economic flow is observed"
                        if any(item.boundary == "boundary" for item in self.stock_transactions) else None),
        }

    def record_state_delta(self, event_id: str, event_type: str,
                           before_controls: dict[str, dict[str, dict[str, float]]],
                           before_formations: dict[str, dict[str, Any]] | None = None,
                           organization_ids: tuple[str, ...] = ()) -> None:
        control_changes: dict[str, dict[str, float]] = {}
        for locality_id, locality in self.localities.items():
            for actor, vector in locality.control.items():
                before = before_controls.get(locality_id, {}).get(actor, {})
                for dimension, value in vector.to_dict().items():
                    # A newly created locality/actor has an implicit zero
                    # baseline, so its initial control is an auditable state
                    # change rather than being silently dropped.
                    delta = value - before.get(dimension, 0.0)
                    if abs(delta) > 1e-12:
                        control_changes.setdefault(f"{locality_id}:{actor}", {})[dimension] = delta
        all_formations = {
            formation.formation_id: {
                "organization_id": formation.organization_id,
                "locality_id": formation.locality_id,
                "microzone_id": formation.current_microzone_id,
                "personnel": formation.personnel,
                "supply_stock": formation.supply_stock,
                "readiness": formation.readiness,
                "availability": formation.availability,
            }
            for formation in self.formations.values()
        }
        if before_formations is None:
            formations = all_formations
        else:
            formations = {
                formation_id: state for formation_id, state in all_formations.items()
                if before_formations.get(formation_id) != state
            }
        confidence = [belief.confidence for belief in self.control_beliefs.values()]
        belief_state = {
            "mean_confidence": (sum(confidence) / len(confidence) if confidence else 0.0),
            "belief_count": float(len(self.control_beliefs)),
            "observation_count": float(len(self.observations)),
        }
        self.state_deltas.append(StateDelta(
            event_id, self.time, event_type, control_changes, formations,
            belief_state, tuple(sorted(set(organization_ids))),
        ))

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
            if formation.current_microzone_id is not None:
                if formation.current_microzone_id not in self.microzones:
                    raise AssertionError("formation references missing microzone")
                if self.microzones[formation.current_microzone_id].locality_id != formation.locality_id:
                    raise AssertionError("formation microzone is outside its locality")
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
        if any(state.resources < -tolerance or not 0 <= state.willingness <= 1
               for state in self.foreign_states.values()):
            raise AssertionError("invalid foreign-state stock")
        if any(abs(support.total() - sum(support.components.values())) > tolerance or
               any(value < 0 for value in support.components.values())
               for support in self.external_support):
            raise AssertionError("invalid external-support vector")
        if any(not 0 <= border.legal_permeability <= 1 or
               not 0 <= border.social_permeability <= 1
               for border in self.border_segments.values()):
            raise AssertionError("invalid border permeability")
        if any(not 0 <= item.progress <= item.target + tolerance
               for item in self.agreement_provisions.values()):
            raise AssertionError("agreement provision progress outside bounds")
        if self.demobilized_personnel < -tolerance or self.demobilized_arms < -tolerance:
            raise AssertionError("negative demobilized stock")
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
            if observation.decay_rate < 0 or (observation.timestamp < 0 and not self.in_burn_in):
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
            current_supply += self.demobilized_arms
            current_supply += sum(
                shipment.quantity_deliverable for shipment in self.supply_shipments.values()
                if shipment.status == "in_transit"
            )
            expected_supply = (self.initial_supply_stock + self.cumulative_supply_produced +
                               self.cumulative_resource_to_supply - self.cumulative_supply_consumed -
                               self.cumulative_supply_lost)
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
            "organization_eligibility_periods": len(self.organization_eligibility_log),
            "political_institutions": len(self.political_institutions),
            "party_branches": len(self.party_branches),
            "elections": len(self.elections),
            "ruling_party_id": self.ruling_party_id,
            "foreign_states": len(self.foreign_states),
            "border_segments": len(self.border_segments),
            "external_migrants": sum(person.external_state_id is not None for person in self.persons.values()),
            "foreign_interventions": sum(item.status == "active" for item in self.foreign_interventions.values()),
            "negotiations": len(self.negotiations),
            "peace_agreements": len(self.peace_agreements),
            "active_ceasefires": sum(status == "active" for status in self.ceasefires.values()),
            "demobilized_personnel": self.demobilized_personnel,
            "conflict_recurrences": sum(t.transition_type == "recurrence" for t in self.peace_transitions),
            "formations": len(self.formations),
            "engagements": len(self.engagements),
            "civilian_harm": self.cumulative_civilian_harm,
            "events": len(self.event_log),
            "synthetic_records": sum(record.recorded for record in self.synthetic_records),
            "synthetic_recording_rate": (
                sum(record.recorded for record in self.synthetic_records) /
                max(1, len(self.synthetic_records))
            ),
            "cumulative_resource_to_supply": self.cumulative_resource_to_supply,
            "supply_conservation_residual": self.supply_conservation_residual(),
            "stock_ledger_transactions": len(self.stock_transactions),
            "stock_ledger_residual": self.stock_ledger_residual(),
            "state_delta_records": len(self.state_deltas),
            "mean_government_effective_control": sum(government_control) / len(government_control),
            "mean_insurgent_effective_control": sum(insurgent_control) / len(insurgent_control),
            "detection_counts": dict(self.information_detections),
        }

    def supply_conservation_residual(self) -> float:
        """Current minus expected supply under the explicit stock ledger."""
        current = sum(source.stock for source in self.supply_sources.values())
        current += sum(formation.supply_stock for formation in self.formations.values())
        current += self.demobilized_arms
        current += sum(shipment.quantity_deliverable for shipment in self.supply_shipments.values()
                       if shipment.status == "in_transit")
        expected = (self.initial_supply_stock + self.cumulative_supply_produced +
                    self.cumulative_resource_to_supply - self.cumulative_supply_consumed -
                    self.cumulative_supply_lost)
        return current - expected

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
            "pathology": {
                "patronage_total": sum(branch.patronage_stock for branch in self.party_branches.values()),
                "patronage_max": max((branch.patronage_stock for branch in self.party_branches.values()), default=0.0),
                "belief_mean_confidence": (
                    sum(belief.confidence for belief in self.control_beliefs.values()) /
                    max(1, len(self.control_beliefs))),
                "active_insurgent_organizations": sum(
                    organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
                    for organization in self.organizations.values()),
                "eligibility_periods": len(self.organization_eligibility_log),
                "eligible_periods": sum(row["eligible"] for row in self.organization_eligibility_log),
                "stock_ledger_residual": self.stock_ledger_residual(),
                "supply_residual": self.supply_conservation_residual(),
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
        from .foreign_affairs import foreign_diagnostics
        from .peace_process import peace_diagnostics
        from .recording import recording_diagnostics
        from .integrity import causal_integrity_diagnostics
        from .empirical import recorded_vs_true_metrics, recorded_synthetic_observations

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
        (output / "organization_eligibility.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.organization_eligibility_log),
            encoding="utf-8",
        )
        (output / "political_diagnostics.json").write_text(
            json.dumps(political_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "foreign_diagnostics.json").write_text(
            json.dumps(foreign_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "peace_diagnostics.json").write_text(
            json.dumps(peace_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "peace_transitions.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.peace_transitions),
            encoding="utf-8",
        )
        (output / "recorded_empirical_observations.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in recorded_synthetic_observations(self)),
            encoding="utf-8",
        )
        (output / "recorded_vs_true_metrics.json").write_text(
            json.dumps(recorded_vs_true_metrics(self), indent=2), encoding="utf-8"
        )
        (output / "recording_diagnostics.json").write_text(
            json.dumps(recording_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "causal_integrity_diagnostics.json").write_text(
            json.dumps(causal_integrity_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "stock_transactions.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.stock_transactions),
            encoding="utf-8",
        )
        (output / "state_deltas.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.state_deltas),
            encoding="utf-8",
        )
        (output / "stock_ledger_diagnostics.json").write_text(
            json.dumps(self.stock_ledger_diagnostics(), indent=2),
            encoding="utf-8",
        )
        (output / "peace_agreements.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.peace_agreements.values()),
            encoding="utf-8",
        )
        (output / "external_transfers.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.external_transfers),
            encoding="utf-8",
        )
        (output / "external_support.jsonl").write_text(
            "".join(json.dumps(asdict(item)) + "\n" for item in self.external_support),
            encoding="utf-8",
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
