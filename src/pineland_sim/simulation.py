from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .events import EventScheduler
from .processes import ProcessEngine
from .world import WorldState, seeded_rng


@dataclass(slots=True)
class SimulationResult:
    world: WorldState
    events_processed: int
    stopped_at: float


PolicyHook = Callable[[WorldState, float], None]


class Simulation:
    def __init__(self, world: WorldState, policy_hook: PolicyHook | None = None) -> None:
        self.world = world
        self.policy_hook = policy_hook
        self.scheduler = EventScheduler(allow_negative=True)
        self.rng = seeded_rng(world.config, "event-scheduling")
        self.processes = ProcessEngine(world)
        self._initialized = False
        self._recruitment_clock_started = False

    def initialize(self) -> None:
        if self._initialized:
            return
        self._populate_scheduler(0.0)
        self._initialized = True
        if self.world.config.burn_in_days > 0:
            self._run_burn_in()

    def _populate_scheduler(self, start_time: float) -> None:
        intervals = self.world.config.intervals
        for patrol_id in sorted(self.world.patrols):
            self.scheduler.schedule(start_time, "patrol", {"patrol_id": patrol_id}, priority=30)
        recurring = [
            ("command", intervals.command, 20),
            ("force_movement", intervals.force_movement, 25),
            ("logistics", intervals.logistics, 27),
            ("information", intervals.information, 38),
            ("beliefs", intervals.beliefs, 42),
            ("physical_refresh", intervals.physical_refresh, 35),
            ("social_influence", intervals.social_influence, 45),
            ("organization_ecology", self.world.config.organization_ecology.interval_days, 58),
            ("political_order", self.world.config.political_order.interval_days, 57),
            ("foreign_affairs", self.world.config.foreign_affairs.interval_days, 59),
            ("peace_process", self.world.config.peace_process.interval_days, 61),
            ("mobility", intervals.mobility, 50),
            ("governance", intervals.governance, 70),
            ("economy", intervals.economy, 80),
            ("checkpoint", intervals.checkpoint, 90),
        ]
        for event_type, interval, priority in recurring:
            self.scheduler.schedule(start_time, event_type, {"interval": interval}, priority=priority)
        if any(organization.kind.value == "insurgent" and organization.status == "active"
               for organization in self.world.organizations.values()):
            self.scheduler.schedule(start_time, "recruitment", {"interval": intervals.recruitment}, priority=60)
            self._recruitment_clock_started = True

    def _run_burn_in(self) -> None:
        """Run an unrecorded stabilization phase before analytical time zero."""
        burn_in = self.world.config.burn_in_days
        self.scheduler = EventScheduler(allow_negative=True)
        self.world.time = -burn_in
        self.world.in_burn_in = True
        self._recruitment_clock_started = False
        self._populate_scheduler(-burn_in)
        processed = 0
        last_contact_day = None
        while len(self.scheduler):
            next_time = self.scheduler.peek_time()
            if next_time is None or next_time > 0:
                break
            event = self.scheduler.pop_next()
            self.world.time = event.time
            self.processes.execute(event)
            if (not self._recruitment_clock_started and
                    any(organization.kind.value == "insurgent" and organization.status == "active"
                        for organization in self.world.organizations.values())):
                self.scheduler.schedule(event.time, "recruitment",
                                        {"interval": self.world.config.intervals.recruitment}, priority=60)
                self._recruitment_clock_started = True
            self._reschedule(event.event_type, event.payload, event.time)
            day = int(event.time)
            if day != last_contact_day:
                self._schedule_contacts(event.time)
                last_contact_day = day
            processed += 1
        # The stabilized state becomes the explicit initial condition for the
        # observed run.  No warm-up event is exposed as an empirical record.
        self.world.time = 0.0
        self.world.in_burn_in = False
        self.world.event_log.clear()
        self.world.synthetic_records.clear()
        self.world.causal_ledger.clear()
        self.world.observations.clear()
        self.world.observation_index.clear()
        self.world.observation_source_index.clear()
        self.world.information_relays.clear()
        self.world.organization_transitions.clear()
        self.world.organization_eligibility_log.clear()
        self.world.stock_transactions.clear()
        self.world.state_deltas.clear()
        self.world.checkpoints.clear()
        # Reset conservation baselines to the stabilized state, retaining all
        # state variables but excluding warm-up flows from analytical totals.
        self.world.initial_population = self.world.weighted_population()
        self.world.cumulative_deaths = 0.0
        self.world.cumulative_external_inflow = 0.0
        self.world.initial_supply_stock = (
            sum(source.stock for source in self.world.supply_sources.values()) +
            sum(formation.supply_stock for formation in self.world.formations.values()) +
            self.world.demobilized_arms +
            sum(shipment.quantity_deliverable for shipment in self.world.supply_shipments.values()
                if shipment.status == "in_transit")
        )
        self.world.cumulative_supply_produced = 0.0
        self.world.cumulative_supply_consumed = 0.0
        self.world.cumulative_supply_lost = 0.0
        self.world.cumulative_resource_to_supply = 0.0
        self.world.initialize_stock_ledger()
        self.processes.event_counter = 0
        self.scheduler = EventScheduler(allow_negative=True)
        self._recruitment_clock_started = False
        self._populate_scheduler(0.0)

    def _reschedule(self, event_type: str, payload: dict, current_time: float) -> None:
        intervals = self.world.config.intervals
        interval = payload.get("interval")
        if event_type == "patrol":
            interval = payload.get("next_interval", intervals.patrol)
        if interval:
            self.scheduler.schedule(current_time + interval, event_type, payload)

    def _schedule_contacts(self, current_time: float) -> None:
        occupied: dict[tuple[str, str], set[str]] = {}
        for formation in self.world.formations.values():
            if formation.moving or formation.current_microzone_id not in self.world.microzones:
                continue
            occupied.setdefault((formation.locality_id, formation.current_microzone_id), set()).add(
                formation.organization_id)
        for (locality_id, microzone_id), actors in occupied.items():
            insurgents = {actor for actor in actors
                          if self.world.organizations[actor].kind.value == "insurgent" and
                          self.world.organizations[actor].status == "active"}
            if insurgents and any(actor not in insurgents for actor in actors):
                self.scheduler.schedule(
                    current_time + self.rng.random(), "contact",
                    {"locality_id": locality_id, "microzone_id": microzone_id}, priority=20)

    def run(self, until: float | None = None, max_events: int | None = None) -> SimulationResult:
        self.initialize()
        horizon = self.world.config.horizon_days if until is None else until
        intervals = self.world.config.intervals
        processed = 0
        last_contact_day = -1
        while len(self.scheduler):
            next_time = self.scheduler.peek_time()
            if next_time is None or next_time > horizon or (max_events is not None and processed >= max_events):
                break
            event = self.scheduler.pop_next()
            if event.time < self.world.time:
                raise AssertionError("scheduler time moved backward")
            self.world.time = event.time
            if self.policy_hook:
                self.policy_hook(self.world, event.time)
            self.processes.execute(event)
            if (not self._recruitment_clock_started and
                    any(organization.kind.value == "insurgent" and organization.status == "active"
                        for organization in self.world.organizations.values())):
                self.scheduler.schedule(event.time, "recruitment", {"interval": intervals.recruitment}, priority=60)
                self._recruitment_clock_started = True
            self._reschedule(event.event_type, event.payload, event.time)
            day = int(event.time)
            if day != last_contact_day:
                self._schedule_contacts(event.time)
                last_contact_day = day
            processed += 1
        self.world.time = min(horizon, self.world.time)
        self.world.assert_invariants()
        if not self.world.checkpoints or self.world.checkpoints[-1]["time"] != self.world.time:
            self.world.checkpoint()
        return SimulationResult(self.world, processed, self.world.time)
