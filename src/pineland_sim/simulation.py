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
        self.scheduler = EventScheduler()
        self.rng = seeded_rng(world.config, "event-scheduling")
        self.processes = ProcessEngine(world)
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        intervals = self.world.config.intervals
        for patrol_id in sorted(self.world.patrols):
            self.scheduler.schedule(0, "patrol", {"patrol_id": patrol_id}, priority=30)
        recurring = [
            ("command", intervals.command, 20),
            ("force_movement", intervals.force_movement, 25),
            ("logistics", intervals.logistics, 27),
            ("information", intervals.information, 38),
            ("physical_refresh", intervals.physical_refresh, 35),
            ("social_influence", intervals.social_influence, 45),
            ("organization_ecology", self.world.config.organization_ecology.interval_days, 58),
            ("political_order", self.world.config.political_order.interval_days, 57),
            ("mobility", intervals.mobility, 50),
            ("governance", intervals.governance, 70),
            ("economy", intervals.economy, 80),
            ("checkpoint", intervals.checkpoint, 90),
        ]
        if any(organization.kind.value == "insurgent" and organization.status == "active"
               for organization in self.world.organizations.values()):
            recurring.append(("recruitment", intervals.recruitment, 60))
        for event_type, interval, priority in recurring:
            self.scheduler.schedule(0, event_type, {"interval": interval}, priority=priority)
        self._initialized = True

    def _reschedule(self, event_type: str, payload: dict, current_time: float) -> None:
        intervals = self.world.config.intervals
        interval = payload.get("interval")
        if event_type == "patrol":
            interval = payload.get("next_interval", intervals.patrol)
        if interval:
            self.scheduler.schedule(current_time + interval, event_type, payload)

    def _schedule_contacts(self, current_time: float) -> None:
        occupied: dict[str, set[str]] = {}
        for formation in self.world.formations.values():
            if formation.moving:
                continue
            occupied.setdefault(formation.locality_id, set()).add(formation.organization_id)
        for locality_id, actors in occupied.items():
            insurgents = {actor for actor in actors
                          if self.world.organizations[actor].kind.value == "insurgent" and
                          self.world.organizations[actor].status == "active"}
            if insurgents and any(actor not in insurgents for actor in actors):
                self.scheduler.schedule(current_time + self.rng.random(), "contact", {"locality_id": locality_id}, priority=20)

    def run(self, until: float | None = None, max_events: int | None = None) -> SimulationResult:
        self.initialize()
        horizon = self.world.config.horizon_days if until is None else until
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
