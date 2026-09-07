from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from .events import CalendarEventScheduler, EventScheduler
from .processes import ProcessEngine
from .world import WorldState, seeded_rng
from .action_model import ACTION_ORGANIZATION_KINDS, local_fighter_equivalents


@dataclass(slots=True)
class SimulationResult:
    world: WorldState
    events_processed: int
    stopped_at: float


PolicyHook = Callable[[WorldState, float], None]
_UNSET_POLICY_HOOK = object()


class Simulation:
    def __init__(
        self,
        world: WorldState,
        policy_hook: PolicyHook | None = None,
        stream_namespace: str = "",
    ) -> None:
        self.world = world
        self.policy_hook = policy_hook
        self.stream_namespace = str(stream_namespace)
        self.scheduler = EventScheduler(allow_negative=True)
        self.rng = seeded_rng(
            world.config,
            self._stream_name("event-scheduling"),
        )
        self.processes = ProcessEngine(
            world,
            stream_namespace=self.stream_namespace,
        )
        self._initialized = False
        self._recruitment_clock_started = False
        # These execution controls affect bookkeeping only.  Defaults retain
        # the historical full-audit/full-archive behavior.
        self._validate_invariants = True
        self._checkpointing = True
        self._retain_output_archives = True

    def _stream_name(self, stream: str) -> str:
        if not self.stream_namespace:
            return stream
        return f"{self.stream_namespace}:{stream}"

    def set_stream_namespace(self, stream_namespace: str) -> None:
        """Fork future transition randomness at the current calendar boundary.

        The world, scheduler, and event counter remain untouched.  Only future
        stochastic streams are re-keyed, which is the distinction needed when
        a particle filter duplicates a latent state after an observation.
        """
        self.stream_namespace = str(stream_namespace)
        self.rng = seeded_rng(
            self.world.config,
            self._stream_name("event-scheduling"),
        )
        self.processes.set_stream_namespace(self.stream_namespace)

    def configure_execution(
        self,
        *,
        validate_invariants: bool | None = None,
        checkpointing: bool | None = None,
        retain_output_archives: bool | None = None,
        scheduler_backend: str | None = None,
        execution_backend: str | None = None,
    ) -> None:
        """Configure a simulation's bookkeeping policy before initialization."""
        if self._initialized and checkpointing is not None and bool(checkpointing) != self._checkpointing:
            raise RuntimeError("checkpointing cannot change after simulation initialization")
        if scheduler_backend is not None:
            if self._initialized:
                raise RuntimeError(
                    "scheduler backend cannot change after simulation initialization"
                )
            if scheduler_backend == "heap":
                self.scheduler = EventScheduler()
            elif scheduler_backend == "calendar":
                self.scheduler = CalendarEventScheduler()
            else:
                raise ValueError(
                    "scheduler_backend must be 'heap' or 'calendar'"
                )
        if execution_backend is not None:
            if execution_backend not in {"reference", "optimized"}:
                raise ValueError(
                    "execution_backend must be 'reference' or 'optimized'"
                )
            self.world.execution_backend = execution_backend
            if execution_backend == "optimized":
                self.world.rebuild_runtime_entity_indexes()
                self.world.rebuild_compact_control_state()
        if validate_invariants is not None:
            self._validate_invariants = bool(validate_invariants)
        if checkpointing is not None:
            self._checkpointing = bool(checkpointing)
        if retain_output_archives is not None:
            self._retain_output_archives = bool(retain_output_archives)
            if not self._retain_output_archives:
                # Case conditioning and scientific fixtures may legitimately
                # mutate entities directly while the world is still in
                # standard mode. Rebuild all derived execution indexes once
                # before any particle hot path begins trusting them.
                self.world.rebuild_runtime_entity_indexes()
                if execution_backend is None:
                    self.world.execution_backend = "optimized"
                    self.world.rebuild_compact_control_state()
            self.world.execution_profile = (
                "particle" if not self._retain_output_archives else "standard"
            )

    def clone(
        self,
        *,
        policy_hook: PolicyHook | None | object = _UNSET_POLICY_HOOK,
        stream_namespace: str | None = None,
        copy_output_archives: bool | None = None,
    ) -> "Simulation":
        """Clone a live simulation, including its pending event queue.

        ``WorldState.clone()`` is intentionally insufficient for a live
        particle: scheduled contacts, recurring clocks, process RNG state,
        and the event counter all affect the future.  This method copies the
        complete simulation object and lets callers provide a separately
        cloned policy hook (for example, a historical stock schedule).

        Passing no hook argument copies the existing callable object.  Passing
        ``policy_hook=None`` explicitly removes it.  Callers that need a
        separately cloneable hook can deep-copy it before passing it here.
        """
        original_hook = self.policy_hook
        original_world = self.world
        original_process_world = self.processes.world
        preserve_archives = (
            self._retain_output_archives
            if copy_output_archives is None else bool(copy_output_archives)
        )
        detached_archives = None if preserve_archives else original_world.detach_particle_archives()
        if not preserve_archives:
            self.world = None  # type: ignore[assignment]
            self.processes.world = None  # type: ignore[assignment]
        # Callable closures are shallowly copied by deepcopy and can retain a
        # mutable schedule in their closure.  Exclude the hook from the main
        # copy; callers can pass a cloneable callable explicitly.
        self.policy_hook = None
        try:
            cloned = copy.deepcopy(self)
            if not preserve_archives:
                cloned.world = original_world.clone(share_static=True)
                cloned.processes.world = cloned.world
        finally:
            self.policy_hook = original_hook
            self.world = original_world
            self.processes.world = original_process_world
            if detached_archives is not None:
                original_world.restore_particle_archives(detached_archives)

        if policy_hook is _UNSET_POLICY_HOOK:
            cloned.policy_hook = copy.deepcopy(original_hook)
        else:
            cloned.policy_hook = policy_hook  # type: ignore[assignment]
        if not preserve_archives:
            cloned.world.execution_profile = "particle"
        if stream_namespace is not None:
            cloned.set_stream_namespace(stream_namespace)
        return cloned

    def initialize(self) -> None:
        if self._initialized:
            return
        self._populate_scheduler(0.0)
        self._initialized = True
        if self.world.config.burn_in_days > 0:
            self._run_burn_in()

    def _populate_scheduler(
        self, start_time: float, *, include_checkpoints: bool | None = None
    ) -> None:
        intervals = self.world.config.intervals
        include_checkpoints = (
            self._checkpointing if include_checkpoints is None else include_checkpoints
        )
        for patrol_id in sorted(self.world.patrols):
            self.scheduler.schedule(start_time, "patrol", {"patrol_id": patrol_id}, priority=30)
        recurring = [
            ("contact_scan", intervals.contact, 19),
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
        ]
        if self.world.execution_profile != "particle":
            # False reports are an observation-layer process with its own
            # calendar clock. Particle propagation does not need this output
            # layer, so it is omitted without touching latent process RNGs.
            recurring.append(("recording_noise", intervals.information, 85))
        if include_checkpoints:
            recurring.append(("checkpoint", intervals.checkpoint, 90))
        for event_type, interval, priority in recurring:
            self.scheduler.schedule(
                start_time,
                event_type,
                {"interval": interval, "elapsed_days": 0.0},
                priority=priority,
            )
        if any(organization.kind.value == "insurgent" and organization.status == "active"
               for organization in self.world.organizations.values()):
            self.scheduler.schedule(
                start_time,
                "recruitment",
                {"interval": intervals.recruitment, "elapsed_days": 0.0},
                priority=60,
            )
            self._recruitment_clock_started = True

    def _run_burn_in(self) -> None:
        """Run an unrecorded stabilization phase before analytical time zero."""
        burn_in = self.world.config.burn_in_days
        scheduler_type = type(self.scheduler)
        self.scheduler = scheduler_type(allow_negative=True)
        self.world.time = -burn_in
        self.world.in_burn_in = True
        self._recruitment_clock_started = False
        self._populate_scheduler(-burn_in, include_checkpoints=self._checkpointing)
        processed = 0
        while len(self.scheduler):
            next_time = self.scheduler.peek_time()
            if next_time is None or next_time > 0:
                break
            event = self.scheduler.pop_next()
            # A realization scheduled by a pre-zero contact window belongs to
            # the burn-in even when it lands exactly on the boundary.  Ordinary
            # recurring clocks at t=0 do not: they are the first observed-run
            # updates and will be scheduled again below after rebaselining.
            # Executing them here as well would mutate the analytical initial
            # condition twice whenever burn-in duration aligns with a cadence.
            if event.time == 0 and event.event_type not in {"contact", "organized_action"}:
                break
            self.world.time = event.time
            if event.event_type == "contact_scan":
                exposure_days = min(float(event.payload["interval"]), max(0.0, -event.time))
                if exposure_days > 0:
                    if self.world.config.combat.organized_action_architecture == "multichannel_v5":
                        self._schedule_organized_actions(
                            event.time, interval_days=exposure_days,
                            realization_time=event.time + exposure_days,
                        )
                    else:
                        self._schedule_contacts(
                            event.time, interval_days=exposure_days,
                            realization_time=event.time + exposure_days,
                        )
                self._reschedule(event.event_type, event.payload, event.time)
                processed += 1
                continue
            self.processes.execute(event)
            if (not self._recruitment_clock_started and
                    any(organization.kind.value == "insurgent" and organization.status == "active"
                        for organization in self.world.organizations.values())):
                self.scheduler.schedule(event.time, "recruitment",
                                        {"interval": self.world.config.intervals.recruitment,
                                         "elapsed_days": 0.0}, priority=60)
                self._recruitment_clock_started = True
            self._reschedule(event.event_type, event.payload, event.time)
            processed += 1
        # Close continuous-time state exactly at the analytical boundary
        # without generating a new stochastic observation/process event.
        # Otherwise a non-aligned burn-in duration leaves patrol memory and
        # information confidence stranded at the final pre-zero scheduler tick.
        from .information import decay_information
        from .physical import advance_patrol_presence_memory

        advance_patrol_presence_memory(self.world, 0.0)
        decay_information(self.world, 0.0)
        # The stabilized state becomes the explicit initial condition for the
        # observed run.  No warm-up event is exposed as an empirical record.
        self.world.time = 0.0
        self.world.in_burn_in = False
        self.world.event_log.clear()
        self.world.event_counts.clear()
        self.world.contact_event_times.clear()
        self.world.contact_event_localities.clear()
        self.world.state_based_event_times.clear()
        self.world.state_based_event_localities.clear()
        self.world.state_based_events.clear()
        self.world.state_based_event_localities_by_week.clear()
        self.world.contact_funnel_records.clear()
        self.world.contact_funnel_counts.clear()
        self.world.action_funnel_counts.clear()
        self.world.action_funnel_by_actor_locality.clear()
        self.world.recruitment_total = 0.0
        self.world.behavior_change_total = 0
        self.world.behavior_change_represented_population = 0.0
        self.world.synthetic_records.clear()
        self.world.causal_ledger.clear()
        self.world.observations.clear()
        self.world.next_observation_sequence = 1
        self.world.observation_index.clear()
        self.world.observation_source_index.clear()
        self.world.information_relays.clear()
        self.world.next_information_relay_sequence = 1
        self.world.active_information_relays.clear()
        self.world.information_relay_due_heap.clear()
        self.world.information_detections = {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "true_negative": 0,
        }
        self.world.information_detection_by_source.clear()
        self.world.organization_transitions.clear()
        self.world.organization_eligibility_log.clear()
        self.world.organization_onset_log.clear()
        # These collections are event/flow histories, not state required for
        # post-burn-in behavior.  Their effects are already embodied in the
        # stabilized stocks, formations, institutions and controls.  Keeping
        # the records would leak negative-time warm-up events into analytical
        # JSONL outputs and diagnostics.
        self.world.resource_flows.clear()
        self.world.engagements.clear()
        self.world.political_transfers.clear()
        self.world.policy_implementations.clear()
        self.world.external_transfers.clear()
        self.world.peace_transitions.clear()
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
            sum(self.world.organization_manpower_supply_reserves.values()) +
            self.world.demobilized_arms +
            sum(shipment.quantity_deliverable for shipment in self.world.supply_shipments.values()
                if shipment.status == "in_transit")
        )
        self.world.cumulative_supply_produced = 0.0
        self.world.cumulative_supply_consumed = 0.0
        self.world.cumulative_supply_lost = 0.0
        self.world.cumulative_resource_to_supply = 0.0
        self.world.cumulative_civilian_harm = 0.0
        self.world.cumulative_civilian_injuries = 0.0
        self.world.cumulative_civilian_resource_loss = 0.0
        self.world.cumulative_civilian_displacement = 0.0
        self.world.civilian_harm_events.clear()
        self.world.cumulative_public_spending = 0.0
        self.world.cumulative_external_remittances = 0.0
        self.world.control_cost_consumed = {
            locality_id: 0.0 for locality_id in self.world.localities
        }
        for formation in self.world.formations.values():
            formation.cumulative_losses = 0.0
        self.world.initialize_stock_ledger()
        self.processes.event_counter = 0
        self.scheduler = scheduler_type(allow_negative=True)
        self._recruitment_clock_started = False
        self._populate_scheduler(0.0, include_checkpoints=self._checkpointing)

    def _reschedule(self, event_type: str, payload: dict, current_time: float) -> None:
        intervals = self.world.config.intervals
        interval = payload.get("interval")
        if event_type == "patrol":
            interval = payload.get("next_interval", intervals.patrol)
        if interval:
            if self.world.performance_counters is not None:
                self.world.performance_counters["scheduler_reschedules"] = (
                    self.world.performance_counters.get(
                        "scheduler_reschedules", 0
                    ) + 1
                )
            next_payload = dict(payload)
            if event_type != "patrol":
                next_payload["elapsed_days"] = float(interval)
            self.scheduler.schedule(current_time + interval, event_type, next_payload)

    def _schedule_contacts(self, current_time: float, *, interval_days: float | None = None,
                           realization_time: float | None = None) -> None:
        interval_days = (
            self.world.config.intervals.contact if interval_days is None
            else max(0.0, float(interval_days))
        )
        contact_time = current_time if realization_time is None else realization_time
        occupied: dict[tuple[str, str], list] = {}
        for formation in self.world.formations.values():
            if (formation.moving or formation.personnel <= 0 or
                    formation.outside_pineland or
                    formation.operational_status != "effective" or
                    formation.current_microzone_id not in self.world.microzones or
                    self.world.microzones[formation.current_microzone_id].locality_id != formation.locality_id):
                continue
            occupied.setdefault((formation.locality_id, formation.current_microzone_id), []).append(formation)
        for (locality_id, microzone_id), formations in occupied.items():
            insurgents = [f for f in formations
                          if self.world.organizations[f.organization_id].kind.value == "insurgent" and
                          self.world.organizations[f.organization_id].status == "active"]
            government = [f for f in formations
                          if self.world.organizations[f.organization_id].kind.value in
                          {"military", "police", "foreign"}]
            if (self.world.config.combat.contact_opportunity_model == "legacy_symmetric" and
                    government and insurgents):
                g, i = max(((g, i) for g in government for i in insurgents),
                           key=lambda pair: pair[0].effective_strength() * pair[1].effective_strength())
                payload = {"locality_id": locality_id, "microzone_id": microzone_id,
                           "government_formation_id": g.formation_id,
                           "insurgent_formation_id": i.formation_id,
                           "interval_days": interval_days}
                self.scheduler.schedule(contact_time, "contact", payload, priority=18)
                continue
            for g in sorted(government, key=lambda f: f.formation_id):
                for i in sorted(insurgents, key=lambda f: f.formation_id):
                    # One opportunity per spatial pair and scan.  The interval
                    # is explicit so the continuous-time hazard is invariant
                    # to scheduler resolution.
                    payload = {"locality_id": locality_id, "microzone_id": microzone_id,
                               "government_formation_id": g.formation_id,
                               "insurgent_formation_id": i.formation_id,
                               "interval_days": interval_days}
                    self.scheduler.schedule(contact_time, "contact", payload, priority=18)

    def _schedule_organized_actions(
        self,
        current_time: float,
        *,
        interval_days: float | None = None,
        realization_time: float | None = None,
    ) -> None:
        interval_days = (
            self.world.config.intervals.contact if interval_days is None
            else max(0.0, float(interval_days))
        )
        action_time = current_time if realization_time is None else realization_time
        self.world.refresh_operational_indexes()
        operational_localities = (
            self.world.operational_locality_ids_by_organization
        )

        for organization_id in self.world.active_organization_ids:
            organization = self.world.organizations[organization_id]
            if organization.kind not in ACTION_ORGANIZATION_KINDS:
                continue
            for locality_id in sorted(
                operational_localities.get(organization.organization_id, ())
            ):
                unfielded, fielded = local_fighter_equivalents(
                    self.world, organization.organization_id, locality_id
                )
                if unfielded + fielded <= 0:
                    continue
                self.scheduler.schedule(
                    action_time,
                    "organized_action",
                    {
                        "organization_id": organization.organization_id,
                        "locality_id": locality_id,
                        "interval_days": interval_days,
                    },
                    priority=18,
                )

    def run(
        self,
        until: float | None = None,
        max_events: int | None = None,
        *,
        validate_invariants: bool | None = None,
        checkpoint: bool | None = None,
    ) -> SimulationResult:
        if validate_invariants is not None:
            self._validate_invariants = bool(validate_invariants)
        if checkpoint is not None:
            self._checkpointing = bool(checkpoint)
        self.initialize()
        horizon = self.world.config.horizon_days if until is None else until
        if horizon < self.world.time - 1e-12:
            raise ValueError(
                f"simulation cannot run backward: current_time={self.world.time}, "
                f"requested_horizon={horizon}"
            )
        intervals = self.world.config.intervals
        processed = 0
        stopped_by_max_events = False
        while len(self.scheduler):
            next_time = self.scheduler.peek_time()
            if max_events is not None and processed >= max_events:
                stopped_by_max_events = True
                break
            if next_time is None or next_time > horizon:
                break
            event = self.scheduler.pop_next()
            if event.event_type == "checkpoint" and not self._checkpointing:
                processed += 1
                continue
            if event.time < self.world.time:
                raise AssertionError("scheduler time moved backward")
            self.world.time = event.time
            if self.policy_hook:
                self.policy_hook(self.world, event.time)
            if event.event_type == "contact_scan":
                exposure_days = min(
                    float(event.payload["interval"]),
                    max(0.0, horizon - event.time),
                )
                if exposure_days > 0:
                    if self.world.config.combat.organized_action_architecture == "multichannel_v5":
                        self._schedule_organized_actions(
                            event.time, interval_days=exposure_days,
                            realization_time=event.time + exposure_days,
                        )
                    else:
                        self._schedule_contacts(
                            event.time, interval_days=exposure_days,
                            realization_time=event.time + exposure_days,
                        )
                self._reschedule(event.event_type, event.payload, event.time)
                processed += 1
                continue
            self.processes.execute(event)
            if (not self._recruitment_clock_started and
                    any(organization.kind.value == "insurgent" and organization.status == "active"
                        for organization in self.world.organizations.values())):
                self.scheduler.schedule(
                    event.time, "recruitment",
                    {"interval": intervals.recruitment, "elapsed_days": 0.0},
                    priority=60,
                )
                self._recruitment_clock_started = True
            self._reschedule(event.event_type, event.payload, event.time)
            processed += 1
        # A horizon is a calendar-time boundary, not merely the timestamp of
        # the last discrete event.  If the queue's next event lies beyond the
        # requested horizon, advance continuous patrol-memory exposure through
        # that boundary and report the world at the requested time.  A
        # max_events stop remains a genuine partial execution and must not be
        # relabelled as a completed horizon.
        if not stopped_by_max_events and self.world.time < horizon:
            from .physical import advance_patrol_presence_memory

            advance_patrol_presence_memory(self.world, horizon)
            self.world.time = horizon
        if self._validate_invariants:
            self.world.assert_invariants()
        if self._checkpointing and (
            not self.world.checkpoints or self.world.checkpoints[-1]["time"] != self.world.time
        ):
            self.world.checkpoint()
        if not self._retain_output_archives:
            self.world.clear_particle_archives()
        return SimulationResult(self.world, processed, self.world.time)


@dataclass(slots=True)
class SimulationParticle:
    """A live simulation lineage used by sequential state estimation.

    The wrapped simulation contains the full latent world, scheduler/event
    queue, current time, and process RNG states.  ``lineage_id`` is metadata
    for reproducibility; it is also included in the future stream namespace
    after resampling so duplicated parents do not produce identical children.
    """

    simulation: Simulation
    lineage_id: str = "root"
    generation: int = 0

    @property
    def world(self) -> WorldState:
        return self.simulation.world

    @property
    def time(self) -> float:
        return self.simulation.world.time

    def advance_to(self, until: float) -> SimulationResult:
        return self.simulation.run(until=until)

    def fork(self, child_index: int) -> "SimulationParticle":
        child_lineage = f"{self.lineage_id}.{child_index}"
        parent_hook = self.simulation.policy_hook
        hook = (
            parent_hook.clone()
            if parent_hook is not None and callable(getattr(parent_hook, "clone", None))
            else copy.deepcopy(parent_hook)
        )
        cloned = self.simulation.clone(
            policy_hook=hook,
            stream_namespace=f"particle:{child_lineage}",
            copy_output_archives=self.simulation._retain_output_archives,
        )
        return type(self)(cloned, child_lineage, self.generation + 1)

    def consume_fork(self, child_index: int) -> "SimulationParticle":
        """Turn this disposable parent into one exact child in place.

        This is valid only when the caller will never use the parent lineage
        again. It performs the same future-stream rekey as fork without
        copying the world and scheduler first.
        """
        child_lineage = f"{self.lineage_id}.{child_index}"
        self.simulation.set_stream_namespace(
            f"particle:{child_lineage}"
        )
        self.lineage_id = child_lineage
        self.generation += 1
        return self
