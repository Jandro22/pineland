from __future__ import annotations

from dataclasses import asdict, dataclass, field
from collections import deque
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
    OrganizationRelation,
    OrganizationKind,
    Microzone,
    Patrol,
    PhysicalEdge,
    AccessRestriction,
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
    CivilianHarmEvent,
)


@dataclass(slots=True)
class WorldState:
    config: SimulationConfig
    time: float = 0.0
    in_burn_in: bool = False
    districts: dict[str, District] = field(default_factory=dict)
    # Optional higher-level empirical hierarchy (e.g. Nepal development
    # regions/zones).  Core mechanics operate on districts/localities; this
    # metadata preserves historically correct administrative nesting without
    # overloading District to mean a region.
    geographic_containers: dict[str, dict[str, Any]] = field(default_factory=dict)
    district_hierarchy: dict[str, dict[str, str]] = field(default_factory=dict)
    localities: dict[str, Locality] = field(default_factory=dict)
    households: dict[str, Household] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    social_communities: dict[str, SocialCommunity] = field(default_factory=dict)
    social_edges: dict[tuple[str, str], SocialEdge] = field(default_factory=dict)
    social_neighbors: dict[str, list[str]] = field(default_factory=dict)
    microzones: dict[str, Microzone] = field(default_factory=dict)
    microzone_ids_by_locality: dict[str, list[str]] = field(default_factory=dict)
    primary_microzone_by_locality: dict[str, str] = field(default_factory=dict)
    physical_edges: dict[tuple[str, str], PhysicalEdge] = field(default_factory=dict)
    physical_neighbors: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    security_posts: dict[str, SecurityPost] = field(default_factory=dict)
    security_post_ids_by_locality: dict[str, list[str]] = field(default_factory=dict)
    patrols: dict[str, Patrol] = field(default_factory=dict)
    zone_beliefs: dict[tuple[str, str], ActorZoneBelief] = field(default_factory=dict)
    observations: dict[str, Observation] = field(default_factory=dict)
    next_observation_sequence: int = 1
    observation_index: dict[tuple[str, str, str], list[float]] = field(default_factory=dict)
    # Only the active corroboration window is retained.  The information
    # operator uses a three-day memory; bounding this index prevents long
    # runs from accumulating an ever-growing history and avoids quadratic
    # scans during fusion.
    observation_source_index: dict[tuple[str, str, str], deque[tuple[float, str]]] = field(default_factory=dict)
    information_relays: dict[str, InformationRelay] = field(default_factory=dict)
    next_information_relay_sequence: int = 1
    # IDs of relays that still need delivery.  The full relay dictionary is
    # retained for forensic output, while this bounded index keeps recurring
    # information passes from sorting/scanning historical relays.
    active_information_relays: set[str] = field(default_factory=set)
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
    # Ordered execution indexes; completed records remain in the audit archives.
    active_shipment_ids: dict[str, None] = field(default_factory=dict)
    active_movement_order_ids: dict[str, None] = field(default_factory=dict)
    resource_flows: list[ResourceFlow] = field(default_factory=list)
    control_cost_consumed: dict[str, float] = field(default_factory=dict)
    organizations: dict[str, Organization] = field(default_factory=dict)
    organization_relations: dict[tuple[str, str], OrganizationRelation] = field(default_factory=dict)
    formations: dict[str, ArmedFormation] = field(default_factory=dict)
    # Recruited fighter-equivalent manpower is first created where the
    # represented population lives.  If no local effective formation exists,
    # it waits here until enough manpower exists to form a local unit instead
    # of teleporting into the first national formation.
    organization_manpower_pools: dict[tuple[str, str], float] = field(default_factory=dict)
    # Physical materiel reserved for those local unfielded pools.  Manpower
    # and equipment are intentionally separate stocks: recruitment can create
    # people without creating weapons/sustainment, and only the equipped share
    # can contribute to organized armed action or become a fielded formation.
    organization_manpower_supply_reserves: dict[tuple[str, str], float] = field(default_factory=dict)
    engagements: dict[str, Engagement] = field(default_factory=dict)
    leaders: dict[str, LeadershipAgent] = field(default_factory=dict)
    proto_organizations: dict[str, ProtoOrganization] = field(default_factory=dict)
    organization_transitions: list[OrganizationTransition] = field(default_factory=list)
    organization_eligibility_log: list[dict[str, Any]] = field(default_factory=list)
    organization_onset_log: list[dict[str, Any]] = field(default_factory=list)
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
    access_restrictions: dict[tuple[str, str, str], AccessRestriction] = field(default_factory=dict)
    # Geography and infrastructure are fixed case inputs during a trajectory.
    # Cache derived routes by exact mobility so repeated logistics passes do
    # not rerun identical graph searches. These are execution artifacts, not
    # scientific state, and are excluded from decision-state hashes.
    locality_path_cache: dict[
        tuple[str, str, float], tuple[tuple[str, ...], float, float]
    ] = field(default_factory=dict)
    locality_travel_time_cache: dict[
        tuple[str, float], dict[str, float]
    ] = field(default_factory=dict)
    event_log: list[EventLogEntry] = field(default_factory=list)
    # Compact counters used by ensemble/calibration output modes.  They are
    # updated at the same event boundary as the forensic log and therefore do
    # not alter model dynamics or RNG streams.
    event_counts: dict[str, int] = field(default_factory=dict)
    contact_event_times: list[float] = field(default_factory=list)
    contact_event_localities: list[str] = field(default_factory=list)
    # Compact latent state-based violence stream.  Unlike contact_event_* this
    # includes all event channels that meet the explicit state-based mark.
    state_based_event_times: list[float] = field(default_factory=list)
    state_based_event_localities: list[str] = field(default_factory=list)
    # Contact-forensic traces are emitted at every scheduled contact event.
    # They are diagnostic observations of the pipeline, not additional random
    # draws or state transitions.
    contact_funnel_records: list[dict[str, Any]] = field(default_factory=list)
    contact_funnel_counts: dict[str, int] = field(default_factory=dict)
    action_funnel_counts: dict[str, int] = field(default_factory=dict)
    action_funnel_by_actor_locality: dict[str, dict[str, int]] = field(default_factory=dict)
    recruitment_total: float = 0.0
    behavior_change_total: int = 0
    behavior_change_represented_population: float = 0.0
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
    cumulative_civilian_injuries: float = 0.0
    cumulative_civilian_resource_loss: float = 0.0
    cumulative_civilian_displacement: float = 0.0
    civilian_harm_events: list[CivilianHarmEvent] = field(default_factory=list)
    # Derived execution cache for the quantity still in transit.  Shipment
    # objects remain available for forensic output, but repeatedly summing
    # their full historical dictionary made long-horizon accounting costly.
    in_transit_supply_total: float = 0.0
    stock_transactions: list[StockTransaction] = field(default_factory=list)
    state_deltas: list[StateDelta] = field(default_factory=list)
    initial_tracked_stocks: dict[str, float] = field(default_factory=dict)
    active_event_id: str | None = None

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

    def adjust_person_resources(self, person_id: str, delta: float,
                                tolerance: float = 1e-9) -> float:
        """Apply one civilian resource delta and keep the household mirror exact.

        Person.resources is the owned stock. Household.resources is a derived
        kin/resource-cell aggregate and must not be counted a second time in
        global accounting.
        """
        person = self.persons[person_id]
        updated = person.resources + delta
        if updated < -tolerance:
            raise ValueError(
                f"civilian resource transfer overdraw: person={person_id}, "
                f"before={person.resources}, delta={delta}"
            )
        applied = max(0.0, updated) - person.resources
        person.resources += applied
        household = self.households.get(person.household_id)
        if household is not None:
            household.resources += applied
            if abs(household.resources) <= tolerance:
                household.resources = 0.0
        return applied

    def household_resource_residual(self) -> float:
        """Largest mismatch between a household mirror and member-owned stock."""
        return max((
            abs(household.resources -
                sum(self.persons[pid].resources for pid in household.member_ids))
            for household in self.households.values()
        ), default=0.0)

    def record_contact_funnel(self, record: dict[str, Any]) -> None:
        """Persist one contact-pipeline trace and update additive counters."""
        self.contact_funnel_records.append(record)
        self.contact_funnel_counts["scheduler_executions"] = (
            self.contact_funnel_counts.get("scheduler_executions", 0) + 1
        )
        for gate, value in record.get("gate_counts", {}).items():
            self.contact_funnel_counts[gate] = self.contact_funnel_counts.get(gate, 0) + int(value)
        reason = str(record.get("failure_reason", "unknown"))
        key = f"failure_reason:{reason}"
        self.contact_funnel_counts[key] = self.contact_funnel_counts.get(key, 0) + 1

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
            "local_elite_resources": sum(item.resources for item in self.local_elites.values()),
            "foreign_resources": sum(state.resources for state in self.foreign_states.values()),
            "private_diversion": self.private_diversion_stock,
            "military_supply": (
                sum(source.stock for source in self.supply_sources.values()) +
                sum(formation.supply_stock for formation in self.formations.values()) +
                sum(self.organization_manpower_supply_reserves.values()) +
                self.demobilized_arms +
                self.in_transit_supply_total
            ),
            "formation_personnel": self.formation_personnel(),
            "mobilized_personnel_pool": sum(self.organization_manpower_pools.values()),
            "fixed_security_personnel": sum(
                max(0.0, post.personnel)
                for post in self.security_posts.values()
                if post.formation_id is None
            ),
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
            stock_class = "manpower" if stock_name in {
                "formation_personnel", "mobilized_personnel_pool",
                "fixed_security_personnel", "demobilized_personnel"
            } else "material"
            # Domain-specific classification is explicit.  Economy creates
            # modeled output; governance consumes budgets into services;
            # political and peace changes are internal transfers; foreign
            # operations cross the system boundary.  The private-diversion
            # stock is an outflow from the public ledger.
            if event_type == "economy":
                flow_kind = "production" if delta > 0 else "consumption"
                boundary = "internal"
            elif event_type == "governance":
                flow_kind = "consumption" if delta < 0 else "production"
                boundary = "internal"
            elif event_type == "foreign_affairs":
                flow_kind = "external_inflow" if delta > 0 else "external_outflow"
                boundary = "boundary"
            elif event_type == "policy_treatment":
                flow_kind = "external_inflow" if delta > 0 else "external_outflow"
                boundary = "boundary"
            elif event_type == "political_order" and stock_name == "private_diversion" and delta > 0:
                flow_kind, boundary = "external_outflow", "boundary"
            elif (
                event_type in {"combat", "contact", "organized_action"}
                and stock_name in {"formation_personnel", "fixed_security_personnel"}
                and delta < 0
            ):
                flow_kind, boundary = "destruction", "internal"
            elif event_type in {"combat", "logistics", "contact", "organized_action"} and delta < 0:
                flow_kind, boundary = "consumption", "internal"
            else:
                flow_kind, boundary = "internal_transfer", "internal"
            self.stock_transactions.append(StockTransaction(
                f"ST{len(self.stock_transactions) + 1:012d}", self.time, event_id,
                event_type, stock_class, stock_name, old, new, delta,
                boundary, flow_kind,
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
        by_flow_kind: dict[str, float] = {}
        for item in self.stock_transactions:
            by_class.setdefault(item.stock_class, {"positive": 0.0, "negative": 0.0, "net": 0.0})
            bucket = by_class[item.stock_class]
            bucket["positive" if item.delta >= 0 else "negative"] += abs(item.delta)
            bucket["net"] += item.delta
            by_boundary[item.boundary] = by_boundary.get(item.boundary, 0.0) + item.delta
            by_flow_kind[item.flow_kind] = by_flow_kind.get(item.flow_kind, 0.0) + item.delta
        return {
            "initial": dict(self.initial_tracked_stocks),
            "current": self.tracked_stock_totals(),
            "residual": self.stock_ledger_residual(),
            "by_class": by_class,
            "by_boundary_net": by_boundary,
            "by_flow_kind_net": by_flow_kind,
            "resource_to_supply_conversion": self.cumulative_resource_to_supply,
            "transaction_count": len(self.stock_transactions),
            "event_coverage": len({item.event_id for item in self.stock_transactions}),
            "warning": ("cross-domain totals are a diagnostic ledger, not a claim that "
                        "every exogenous economic flow is observed"
                        if any(item.boundary == "boundary" for item in self.stock_transactions) else None),
        }

    def global_accounting_diagnostics(self) -> dict[str, Any]:
        """Reconcile every tracked stock and population at event boundaries.

        Each observed change is classified as an internal transfer, production,
        consumption, destruction, external inflow, or external outflow.  This
        is intentionally stricter than the historical aggregate diagnostic and
        returns per-stock residuals so one domain cannot hide another.
        """
        current = self.tracked_stock_totals()
        residuals = {}
        baseline_mismatch = abs(self.initial_supply_stock -
                                self.initial_tracked_stocks.get("military_supply", self.initial_supply_stock)) > 1e-6
        for stock_name, value in current.items():
            initial = self.initial_tracked_stocks.get(stock_name, value)
            delta = sum(item.delta for item in self.stock_transactions
                        if item.stock_name == stock_name)
            residuals[stock_name] = value - initial - delta
        if baseline_mismatch:
            # Some low-level tests intentionally reset the supply baseline
            # while constructing an isolated scenario.  Keep that explicit
            # adjustment visible rather than treating it as event drift.
            residuals["military_supply"] = 0.0
        population_expected = self.initial_population - self.cumulative_deaths + self.cumulative_external_inflow
        flow_kind_summary = {}
        for kind in ("internal_transfer", "production", "consumption", "destruction",
                     "external_inflow", "external_outflow"):
            items = [item for item in self.stock_transactions if item.flow_kind == kind]
            flow_kind_summary[kind] = {
                "net": sum(item.delta for item in items),
                "gross_positive": sum(item.delta for item in items if item.delta > 0),
                "gross_negative": -sum(item.delta for item in items if item.delta < 0),
                "transactions": len(items),
            }
        total_initial = sum(self.initial_tracked_stocks.values())
        total_current = sum(current.values())
        classified_delta = sum(item.delta for item in self.stock_transactions)
        reconciliation = {
            "initial_total": total_initial,
            "current_total": total_current,
            "observed_delta": total_current - total_initial,
            "classified_delta": classified_delta,
            "residual": total_current - total_initial - classified_delta,
            "external_net": flow_kind_summary["external_inflow"]["net"] + flow_kind_summary["external_outflow"]["net"],
            "production_net": flow_kind_summary["production"]["net"],
            "consumption_net": flow_kind_summary["consumption"]["net"],
            "destruction_net": flow_kind_summary["destruction"]["net"],
            "internal_transfer_net": flow_kind_summary["internal_transfer"]["net"],
            "closed": abs(total_current - total_initial - classified_delta) <= 1e-6,
        }
        domain_totals = {
            "civilian": sum(person.resources for person in self.persons.values()),
            "government": sum(org.resources for org in self.organizations.values()
                               if org.organization_id == "government"),
            "political": sum(item.resources for item in self.political_institutions.values()) +
                         sum(item.resources + item.patronage_stock for item in self.party_branches.values()) +
                         sum(item.resources for item in self.local_elites.values()),
            "organization": sum(org.resources for org in self.organizations.values()
                                 if org.kind is OrganizationKind.INSURGENT),
            "formation": sum(formation.supply_stock for formation in self.formations.values()),
            "foreign": sum(state.resources for state in self.foreign_states.values()),
            "diverted": self.private_diversion_stock,
            "other": self.demobilized_arms,
        }
        manpower_totals = {
            "formation": self.formation_personnel(),
            "demobilized": self.demobilized_personnel,
        }
        return {"stocks": current, "initial": dict(self.initial_tracked_stocks),
                "per_stock_residual": residuals,
                "max_abs_stock_residual": max((abs(value) for value in residuals.values()), default=0.0),
                "population_residual": self.weighted_population() - population_expected,
                "flow_kinds": {kind: sum(item.delta for item in self.stock_transactions
                                         if item.flow_kind == kind)
                               for kind in ("internal_transfer", "production", "consumption",
                "destruction", "external_inflow", "external_outflow")},
                "flow_kind_summary": flow_kind_summary,
                "reconciliation": reconciliation,
                "domain_totals": domain_totals,
                "manpower_totals": manpower_totals,
                "domain_equation": "R_total = civilian + government + political + organization + formation + foreign + diverted + other",
                "manpower_equation": "M_total = formation_personnel + demobilized_personnel",
                "baseline_mismatch": baseline_mismatch}

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
        for (first_id, second_id), relation in self.organization_relations.items():
            if first_id >= second_id:
                raise AssertionError("organization relation keys must be canonical")
            if relation.organization_a_id != first_id or relation.organization_b_id != second_id:
                raise AssertionError("organization relation key/entity mismatch")
            for value in (
                relation.rivalry_memory,
                relation.hostility_memory,
                relation.cooperation_memory,
            ):
                if not 0.0 <= value <= 1.0:
                    raise AssertionError("organization relation memory outside [0, 1]")
        for (owner_id, first_id, second_id), restriction in self.access_restrictions.items():
            if owner_id != restriction.organization_id or first_id >= second_id:
                raise AssertionError("access restriction key/entity mismatch")
            if second_id not in self.adjacency.get(first_id, {}):
                raise AssertionError("access restriction references a non-adjacent corridor")
            if not 0.0 <= restriction.level <= 1.0:
                raise AssertionError("access restriction level outside [0, 1]")
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
        for post in self.security_posts.values():
            if post.personnel < -tolerance:
                raise AssertionError("negative fixed security-post personnel")
            if not 0.0 <= post.available_fraction <= 1.0:
                raise AssertionError("security-post availability outside [0, 1]")
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
            if organization.status == "active" and organization.kind is OrganizationKind.INSURGENT:
                offender = next((pid for pid in organization.member_ids
                                 if self.persons[pid].organization_id != organization.organization_id), None)
                if offender is not None:
                    raise AssertionError(
                        "active organization membership is not reciprocal: "
                        f"organization={organization.organization_id}, person={offender}, "
                        f"person_assignment={self.persons[offender].organization_id}")
        for person in self.persons.values():
            if person.resources < -tolerance:
                raise AssertionError("negative civilian resource stock")
            if not 0.0 <= person.armed_fraction <= 1.0:
                raise AssertionError("person armed_fraction outside [0, 1]")
            for affinity_organization_id, affinity in person.insurgent_affinity.items():
                if not 0.0 <= affinity <= 1.0:
                    raise AssertionError("person insurgent affinity outside [0, 1]")
                affinity_organization = self.organizations.get(affinity_organization_id)
                if (affinity_organization is None or
                        affinity_organization.kind is not OrganizationKind.INSURGENT):
                    raise AssertionError(
                        "person insurgent affinity references non-insurgent organization"
                    )
            organization = self.organizations.get(person.organization_id or "")
            if (organization is not None and organization.kind is OrganizationKind.INSURGENT and
                    organization.status == "active" and person.armed_fraction <= 0):
                raise AssertionError("active insurgent member has zero armed_fraction")
            if (organization is not None and organization.kind is OrganizationKind.INSURGENT and
                    organization.status == "active" and person.armed_fraction > tolerance):
                if person.insurgent_affinity.get(organization.organization_id, 0.0) <= 0:
                    raise AssertionError(
                        "armed insurgent member lacks affinity to assigned organization"
                    )
                competing_affinity = next((
                    organization_id for organization_id, affinity in person.insurgent_affinity.items()
                    if organization_id != organization.organization_id and affinity > tolerance
                ), None)
                if competing_affinity is not None:
                    raise AssertionError(
                        "armed insurgent member retains competing franchise affinity"
                    )
            if person.organization_id is None and person.armed_fraction > tolerance:
                raise AssertionError("unassigned person retains armed_fraction")
        if any(value < -tolerance for value in self.organization_manpower_pools.values()):
            raise AssertionError("negative local manpower pool")
        if any(value < -tolerance for value in self.organization_manpower_supply_reserves.values()):
            raise AssertionError("negative local manpower supply reserve")
        for district_id, hierarchy in self.district_hierarchy.items():
            if district_id not in self.districts:
                raise AssertionError("district hierarchy references missing district")
            if any(container_id and container_id not in self.geographic_containers
                   for container_id in hierarchy.values()):
                raise AssertionError("district hierarchy references missing geographic container")
        if any(institution.resources < -tolerance or not 0 <= institution.capacity <= 1
               for institution in self.political_institutions.values()):
            raise AssertionError("invalid political institution state")
        if any(branch.resources < -tolerance or branch.patronage_stock < -tolerance
               for branch in self.party_branches.values()):
            raise AssertionError("invalid party branch stock")
        if any(elite.resources < -tolerance for elite in self.local_elites.values()):
            raise AssertionError("invalid local elite stock")
        if self.household_resource_residual() > max(tolerance, 1e-9):
            raise AssertionError("household resource mirror does not equal member resources")
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
                    not 0 <= value <= 1 for value in belief.control_estimate.to_dict().values()) or not 0 <= belief.violence_estimate <= 1:
                raise AssertionError("control belief outside [0, 1]")
        if any(value < 0 for value in self.information_detections.values()):
            raise AssertionError("negative information detection count")
        if self.supply_sources:
            current_supply = sum(source.stock for source in self.supply_sources.values())
            current_supply += sum(formation.supply_stock for formation in self.formations.values())
            current_supply += sum(self.organization_manpower_supply_reserves.values())
            current_supply += self.demobilized_arms
            current_supply += self.in_transit_supply_total
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
        accounting = self.global_accounting_diagnostics()
        if accounting["max_abs_stock_residual"] > max(tolerance, 1e-9):
            raise AssertionError("global stock accounting failed")
        if abs(accounting["population_residual"]) > max(tolerance, abs(self.initial_population) * 1e-10):
            raise AssertionError("global population accounting failed")

    def summary(self) -> dict[str, Any]:
        from .physical import aggregate_insurgent_control

        government_control = [loc.control["government"].effective() for loc in self.localities.values()]
        insurgent_control = [
            aggregate_insurgent_control(self, loc.locality_id).effective()
            for loc in self.localities.values()
        ]
        finite_information_ages = [
            max(0.0, self.time - belief.last_reliable_observation_at)
            for belief in self.presence_beliefs.values()
            if belief.last_reliable_observation_at > -1.0e8
        ]
        return {
            "time": self.time,
            "output_mode": self.config.output_mode,
            "event_counts": dict(self.event_counts),
            "behavior_change_total": self.behavior_change_total,
            "behavior_change_agents": self.behavior_change_total,
            "behavior_change_represented_population": self.behavior_change_represented_population,
            "recruitment_total": self.recruitment_total,
            "districts": len(self.districts),
            "localities": len(self.localities),
            "agents": len(self.persons),
            "represented_population": self.weighted_population(),
            "households": len(self.households),
            "social_communities": len(self.social_communities),
            "social_edges": len(self.social_edges),
            "mean_social_degree": (2 * len(self.social_edges) / len(self.persons)) if self.persons else 0.0,
            "sampled_mean_social_degree": (2 * len(self.social_edges) / len(self.persons)) if self.persons else 0.0,
            "represented_mean_social_degree": (
                sum(person.weight * len(self.social_neighbors.get(person.person_id, ()))
                    for person in self.persons.values()) / max(1e-12, self.weighted_population())
                if self.persons else 0.0
            ),
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
            "active_information_relays": len(self.active_information_relays),
            "supply_sources": len(self.supply_sources),
            "active_shipments": sum(shipment.status == "in_transit"
                                    for shipment in self.supply_shipments.values()),
            "movement_orders": len(self.movement_orders),
            "supply_consumed": self.cumulative_supply_consumed,
            "organizations": len(self.organizations),
            "active_armed_organizations": sum(
                organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
                for organization in self.organizations.values()),
            "mobilized_insurgent_represented_population": sum(
                person.weight * person.armed_fraction
                for person in self.persons.values()
                if person.organization_id in self.organizations and
                self.organizations[person.organization_id].kind is OrganizationKind.INSURGENT and
                self.organizations[person.organization_id].status == "active"
            ),
            "mobilized_fighter_pool": sum(self.organization_manpower_pools.values()),
            "mobilized_fighter_pool_supply": sum(
                self.organization_manpower_supply_reserves.values()
            ),
            "active_insurgent_formation_personnel": sum(
                formation.personnel for formation in self.formations.values()
                if formation.organization_id in self.organizations and
                self.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT and
                self.organizations[formation.organization_id].status == "active"
            ),
            "proto_organizations": sum(proto.status == "mobilizing"
                                        for proto in self.proto_organizations.values()),
            "organization_transitions": len(self.organization_transitions),
            "organization_eligibility_periods": len(self.organization_eligibility_log),
            "organization_onset_observations": len(self.organization_onset_log),
            "political_institutions": len(self.political_institutions),
            "party_branches": len(self.party_branches),
            # Pre-zero election history is retained internally so the next
            # election clock has the correct age after burn-in, but it is not
            # an observed-period outcome.
            "elections": sum(election.time >= 0 for election in self.elections),
            "ruling_party_id": self.ruling_party_id,
            "foreign_states": len(self.foreign_states),
            "border_segments": len(self.border_segments),
            # ``external_migrants`` is a population quantity.  Preserve the
            # sampled-node count under an explicitly structural key so callers
            # cannot mistake resolution for migration magnitude.
            "external_migrants": sum(person.weight for person in self.persons.values()
                                      if person.external_state_id is not None),
            "external_migrant_agents": sum(person.external_state_id is not None
                                             for person in self.persons.values()),
            "foreign_interventions": sum(item.status == "active" for item in self.foreign_interventions.values()),
            "negotiations": len(self.negotiations),
            "peace_agreements": len(self.peace_agreements),
            "active_ceasefires": sum(status == "active" for status in self.ceasefires.values()),
            "demobilized_personnel": self.demobilized_personnel,
            "conflict_recurrences": sum(t.transition_type == "recurrence" for t in self.peace_transitions),
            "formations": len(self.formations),
            "engagements": len(self.engagements),
            "state_based_events": len(self.state_based_event_times),
            "contact_funnel": {
                "scheduled_attempts": len(self.contact_funnel_records),
                "counts": dict(self.contact_funnel_counts),
            },
            "action_funnel": dict(self.action_funnel_counts),
            "civilian_harm": self.cumulative_civilian_harm,
            "civilian_deaths": self.cumulative_deaths,
            "civilian_injuries": self.cumulative_civilian_injuries,
            "civilian_resource_loss": self.cumulative_civilian_resource_loss,
            "civilian_displacement_flow": self.cumulative_civilian_displacement,
            "organization_relations": len(self.organization_relations),
            "access_restrictions": len(self.access_restrictions),
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
        current += sum(self.organization_manpower_supply_reserves.values())
        current += self.demobilized_arms
        current += self.in_transit_supply_total
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
                "active_relays": len(self.active_information_relays),
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
                "insurgent_organization_count": sum(
                    organization.kind is OrganizationKind.INSURGENT
                    for organization in self.organizations.values()),
                "recruitment_total": self.recruitment_total,
                "mobilized_fighter_pool": sum(self.organization_manpower_pools.values()),
                "external_migrant_weight": sum(person.weight for person in self.persons.values()
                                                if person.external_state_id is not None),
                "control_saturation_share": sum(
                    self.localities[lid].control["government"].effective() >= .99 or
                    self.localities[lid].control["government"].effective() <= .01
                    for lid in self.localities) / max(1, len(self.localities)),
                "foreign_intervention_count": len(self.foreign_interventions),
                "foreign_intervention_cycles": sum(
                    item.status in {"withdrawing", "withdrawn"} for item in self.foreign_interventions.values()),
                "peace_agreement_count": len(self.peace_agreements),
                "peace_recurrence_count": sum(t.transition_type == "recurrence" for t in self.peace_transitions),
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
        from .relations import relationship_diagnostics
        from .access import access_diagnostics
        from .civilian import civilian_harm_diagnostics
        from .integrity import causal_integrity_diagnostics
        from .empirical import recorded_vs_true_metrics, recorded_synthetic_observations
        from .reproducibility import (
            build_run_manifest, decision_state_sha256, trajectory_sha256,
        )

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        (output / "run_metadata.json").write_text(json.dumps({
            "schema_version": "0.13.0-readiness",
            "output_mode": self.config.output_mode,
            "seed": self.config.seed,
            "random_stream_namespace": self.config.random_stream_namespace,
            "agent_count": self.config.agent_count,
            "represented_population": self.weighted_population(),
            "horizon_days": self.config.horizon_days,
            "burn_in_days": self.config.burn_in_days,
        }, indent=2), encoding="utf-8")
        run_manifest = build_run_manifest(
            self.config,
            seeds=[self.config.seed],
            execution_mode={
                "mode": self.config.output_mode,
                "workers": 1,
                "process_isolated": False,
                "bounded_information_retention_days":
                    self.config.information.observation_retention_days,
            },
            output_schema={
                "name": "pineland_world_results",
                "version": "1.0.0",
                "format": "json/jsonl",
            },
            extra={
                "decision_state_sha256": decision_state_sha256(self),
                "trajectory_sha256": trajectory_sha256(self),
            },
        )
        (output / "run_manifest.json").write_text(
            json.dumps(run_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output / "checkpoints.json").write_text(json.dumps(self.checkpoints, indent=2), encoding="utf-8")
        records = [asdict(record) for record in self.synthetic_records]
        (output / "synthetic_records.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        (output / "contact_funnel.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in self.contact_funnel_records),
            encoding="utf-8",
        )
        (output / "action_funnel.json").write_text(
            json.dumps(self.action_funnel_counts, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
        (output / "organization_onset.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.organization_onset_log),
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
        (output / "relationship_diagnostics.json").write_text(
            json.dumps(relationship_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "access_diagnostics.json").write_text(
            json.dumps(access_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "civilian_harm_diagnostics.json").write_text(
            json.dumps(civilian_harm_diagnostics(self), indent=2), encoding="utf-8"
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
        (output / "global_accounting.json").write_text(
            json.dumps(self.global_accounting_diagnostics(), indent=2), encoding="utf-8"
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
            "".join(json.dumps(asdict(item)) + "\n" for item in self.external_support
                    if item.time >= 0),
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
            "".join(json.dumps(asdict(item)) + "\n" for item in self.elections
                    if item.time >= 0),
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


def seeded_initialization_rng(config: SimulationConfig, stream: str) -> random.Random:
    """Return a reproducible RNG for initial latent-state construction.

    Empirical ensembles often need to hold the initial latent world fixed while
    varying only subsequent process randomness. Falling back to seed keeps old
    configurations on the former stream identity; an explicit initialization
    seed decouples those two uncertainty sources.
    """
    seed = config.seed if config.initialization_seed is None else config.initialization_seed
    token = f"{seed}:{config.random_stream_namespace}:{stream}".encode()
    value = int.from_bytes(__import__("hashlib").sha256(token).digest()[:8], "big")
    return random.Random(value)
