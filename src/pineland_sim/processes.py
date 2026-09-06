from __future__ import annotations

from math import exp, log
import random
from typing import Any

from .entities import (
    CausalContribution,
    ControlVector,
    EventLogEntry,
    OrganizationKind,
    SyntheticRecord,
    clamp,
    logistic,
)
from .events import ScheduledEvent
from .networks import edge_between, locality_social_aggregation, refresh_community_aggregates
from .physical import (
    advance_patrol_presence_memory,
    ensure_zone_belief,
    recompute_contested_controls,
)
from .logistics import (
    advance_movement_orders,
    choose_reallocation_orders,
    consume_formation_supply,
    shortest_locality_path,
    update_logistics,
)
from .information import (
    get_presence_belief,
    observe_patrol,
    observe_target,
    process_information,
)
from .world import WorldState, seeded_rng
from .combat import formation_microzone, resolve_engagement
from .action_model import (
    ACTION_ORGANIZATION_KINDS,
    action_attempt_probability,
    apply_nonfielded_target_losses,
    asset_targets,
    available_battle_pairs,
    choose_action,
    committed_fighter_equivalents,
    consume_local_action_supply,
    execution_probability,
    local_action_supply_available,
    local_action_support,
    nonfielded_human_targets,
)
from .organization_ecology import (
    locality_franchise_support_profile,
    organization_local_rootedness,
    process_organization_ecology,
    recruit_and_retain,
)
from .political_order import process_political_order
from .foreign_affairs import process_foreign_affairs
from .peace_process import process_peace
from .timebase import reference_probability, reference_scale
from .access import (
    build_access_restriction,
    decay_access_restrictions,
    edge_restriction_level,
    locality_access_pressure,
)
from .civilian import record_displacement_harm
from .relations import record_relation_harm


class ProcessEngine:
    """State transitions. Every control mutation is mirrored in the causal ledger."""

    def __init__(self, world: WorldState, rng: random.Random | None = None) -> None:
        self.world = world
        self._injected_rng = rng
        self._process_rngs: dict[str, random.Random] = {}
        # Synthetic recording is an observation/output operator and must not
        # advance the latent transition stream.  Keeping it in an independent
        # deterministic namespace makes logging/recording settings
        # scientifically non-substantive while preserving reproducibility.
        self._recording_rngs: dict[str, random.Random] = {}
        self._recording_rng = seeded_rng(world.config, "recording:process-default")
        self.rng = rng or seeded_rng(world.config, "process-default")
        self.event_counter = 0

    def execute(self, event: ScheduledEvent) -> str:
        self.event_counter += 1
        event_id = f"E{self.event_counter:010d}"
        handler = getattr(self, f"on_{event.event_type}", None)
        if handler is None:
            raise KeyError(f"no process handler for {event.event_type}")
        # Close patrol-memory exposure windows before any handler that can
        # change formation strength, availability, location, or operational
        # status. This makes the memory source piecewise exact at causal event
        # boundaries rather than dependent on the next physical-refresh tick.
        if event.event_type in {
            "physical_refresh", "force_movement", "logistics", "contact",
            "organized_action",
            "recruitment", "organization_ecology", "foreign_affairs",
            "peace_process",
        }:
            advance_patrol_presence_memory(self.world, self.world.time)
        if self._injected_rng is None:
            self.rng = self._process_rngs.setdefault(
                event.event_type, seeded_rng(self.world.config, f"process:{event.event_type}")
            )
        self._recording_rng = self._recording_rngs.setdefault(
            event.event_type, seeded_rng(self.world.config, f"recording:{event.event_type}")
        )
        self.world.active_event_id = event_id
        before_stocks = self.world.tracked_stock_totals()
        forensic = self.world.config.output_mode == "forensic"
        before_controls = ({
            locality_id: {actor: vector.to_dict() for actor, vector in locality.control.items()}
            for locality_id, locality in self.world.localities.items()
        } if forensic else {})
        before_formations = ({
            formation.formation_id: {
                "organization_id": formation.organization_id,
                "locality_id": formation.locality_id,
                "microzone_id": formation.current_microzone_id,
                "personnel": formation.personnel,
                "supply_stock": formation.supply_stock,
                "readiness": formation.readiness,
                "availability": formation.availability,
            }
            for formation in self.world.formations.values()
        } if forensic else {})
        try:
            result = handler(event_id, event) or {}
        except BaseException:
            # A failed handler must not leak the event context into a later
            # direct mutation (which would otherwise be mistaken for an
            # already-captured event-boundary transaction).
            self.world.active_event_id = None
            raise
        raw_result = dict(result)
        self.world.event_counts[event.event_type] = self.world.event_counts.get(event.event_type, 0) + 1
        if event.event_type == "organized_action":
            channel = str(raw_result.get("action_channel", "unknown"))
            reason = str(raw_result.get("failure_reason") or "realized")
            actor_locality_key = (
                f"{event.payload.get('organization_id', 'unknown')}|"
                f"{raw_result.get('locality_id', event.payload.get('locality_id', 'unknown'))}"
            )
            local_funnel = self.world.action_funnel_by_actor_locality.setdefault(
                actor_locality_key, {}
            )
            for key in (
                "scheduled",
                f"channel:{channel}",
                f"outcome:{reason}",
            ):
                self.world.action_funnel_counts[key] = (
                    self.world.action_funnel_counts.get(key, 0) + 1
                )
                local_funnel[key] = local_funnel.get(key, 0) + 1
            if bool(raw_result.get("latent_event", False)):
                self.world.action_funnel_counts["latent_events"] = (
                    self.world.action_funnel_counts.get("latent_events", 0) + 1
                )
                local_funnel["latent_events"] = local_funnel.get("latent_events", 0) + 1
            if float(raw_result.get("state_based_violence_event", 0.0)) > 0:
                self.world.action_funnel_counts["state_based_violence_events"] = (
                    self.world.action_funnel_counts.get("state_based_violence_events", 0) + 1
                )
                local_funnel["state_based_violence_events"] = (
                    local_funnel.get("state_based_violence_events", 0) + 1
                )
        if event.event_type == "contact" and float(raw_result.get("contact", 0.0)) > 0:
            self.world.contact_event_times.append(self.world.time)
            locality = raw_result.get("locality_id", event.payload.get("locality_id"))
            if locality is not None:
                self.world.contact_event_localities.append(str(locality))
                self.world.state_based_event_times.append(self.world.time)
                self.world.state_based_event_localities.append(str(locality))
        if (
            event.event_type == "organized_action"
            and float(raw_result.get("state_based_violence_event", 0.0)) > 0
        ):
            locality = raw_result.get("locality_id", event.payload.get("locality_id"))
            if locality is not None:
                self.world.state_based_event_times.append(self.world.time)
                self.world.state_based_event_localities.append(str(locality))
        if event.event_type == "recruitment":
            self.world.recruitment_total += float(raw_result.get("recruits", 0.0))
        if event.event_type == "social_influence":
            self.world.behavior_change_total += int(raw_result.get("behavior_changes", 0))
            self.world.behavior_change_represented_population += float(
                raw_result.get("behavior_changed_population", 0.0)
            )
        locality_id = result.pop("locality_id", event.payload.get("locality_id"))
        actors = tuple(result.pop("actor_ids", ()))
        affected = tuple(result.pop("affected_entity_ids", ()))
        observations = result.pop("observations_by_actor", {})
        record_event_type = str(result.pop("record_event_type", event.event_type))
        record_source_override = result.pop("record_source_type", None)
        severity = float(result.pop("severity", 0.0 if event.event_type == "contact" else
                                    sum(abs(v) for v in result.values() if isinstance(v, (int, float)))))
        observation_ids = [observation_id for ids in observations.values() for observation_id in ids]
        source_types = {self.world.observations[observation_id].source_type
                        for observation_id in observation_ids if observation_id in self.world.observations}
        source_type = (next(iter(source_types)) if len(source_types) == 1 else
                       "mixed" if source_types else "process_event")
        if record_source_override is not None:
            source_type = str(record_source_override)
        synthetic = self._synthetic_record(
            event_id, record_event_type, locality_id, severity,
            actors[0] if actors else None, source_type,
        )
        if event.event_type == "contact":
            # Recording is an observation-layer decision made after the
            # contact handler. Attach it to the same forensic trace without
            # drawing another random number or altering the event result.
            funnel = next((item for item in reversed(self.world.contact_funnel_records)
                           if item.get("event_id") == event_id), None)
            if funnel is not None:
                draw_pass = int(bool(synthetic.recorded))
                latent = int(float(raw_result.get("contact", 0.0)) > 0)
                recorded = draw_pass * latent
                # Preserve the draw (and RNG stream) for common-random-number
                # experiments, but a failed opportunity is not an observable
                # engagement.
                synthetic.recorded = bool(recorded)
                funnel["gate_counts"]["recording_draw_passes"] = draw_pass
                funnel["gate_counts"]["recorded_engagements"] = recorded
                funnel["gate_counts"]["recorded_contacts"] = recorded  # compatibility alias
                funnel["recording_draw_passed"] = bool(draw_pass)
                funnel["recorded"] = bool(recorded)
                for key, value in (("recording_draw_passes", draw_pass),
                                   ("recorded_engagements", recorded),
                                   ("recorded_contacts", recorded)):
                    if value:
                        self.world.contact_funnel_counts[key] = (
                            self.world.contact_funnel_counts.get(key, 0) + value)
        elif event.event_type == "organized_action":
            # Planning/failed execution/wait states are latent process records,
            # not historical events.  The recording operator is strictly
            # downstream of a realized action outcome.
            if not bool(raw_result.get("latent_event", False)):
                synthetic.recorded = False
        if self.world.config.output_mode == "forensic":
            log_entry = EventLogEntry(
                event_id, event.time, event.event_type, locality_id, actors, affected, result,
                event.causal_parent_ids, observations, synthetic,
                f"{self.world.config.random_stream_namespace}:process:{event.event_type}", "v0.1-defaults",
            )
            self.world.event_log.append(log_entry)
            self.world.synthetic_records.append(synthetic)
        elif self.world.config.output_mode == "ensemble":
            # Keep a compact event record for target extraction while avoiding
            # the large observation/state-delta payloads used in forensic mode.
            if event.event_type != "organized_action" or bool(raw_result.get("latent_event", False)):
                self.world.event_log.append(EventLogEntry(
                    event_id, event.time, event.event_type, locality_id, actors, affected, result,
                    event.causal_parent_ids, {}, synthetic,
                    f"{self.world.config.random_stream_namespace}:process:{event.event_type}", "v0.1-defaults",
                ))
                self.world.synthetic_records.append(synthetic)
        elif (
            self.world.config.output_mode == "calibration"
            and (
                event.event_type == "contact"
                or (
                    event.event_type == "organized_action"
                    and bool(raw_result.get("latent_event", False))
                )
            )
        ):
            # Long empirical runs do not need every scheduled process event,
            # but they do need the recording-layer contact observation used
            # for event-panel scoring.  Retaining only this compact record is
            # an output-policy change; all process/recording RNG draws above
            # are identical to forensic and ensemble modes.
            self.world.synthetic_records.append(synthetic)
        # False recorded events are generated by the observation operator,
        # never inserted into latent event truth or the causal ledger.
        if (self.world.config.recording.enabled and
                self.world.config.recording.false_event_rate > 0 and
                self._recording_rng.random() < self.world.config.recording.false_event_rate):
            false_record = SyntheticRecord(
                f"{event_id}-FP", self.world.time, locality_id, "false_event", True,
                self._recording_rng.uniform(0.05, .7), None, False, 0.0, "false_event")
            if self.world.config.output_mode in {"forensic", "ensemble"}:
                self.world.synthetic_records.append(false_record)
        self.world.record_stock_transactions(event_id, event.event_type, before_stocks,
                                             self.world.tracked_stock_totals())
        if forensic:
            self.world.record_state_delta(event_id, event.event_type, before_controls, before_formations, actors)
        self.world.active_event_id = None
        return event_id

    def _control(self, event_id: str, locality_id: str, actor: str, mechanism: str, **changes: float) -> None:
        vector = self.world.localities[locality_id].control.setdefault(actor, ControlVector())
        before = vector.to_dict()
        vector.update(changes)
        for dimension, old in before.items():
            realized = getattr(vector, dimension) - old
            if realized:
                self.world.causal_ledger.append(
                    CausalContribution(self.world.time, locality_id, dimension, realized, mechanism, event_id)
                )

    def _set_control_dimension(self, event_id: str, locality_id: str, actor: str,
                               dimension: str, target: float, mechanism: str) -> None:
        vector = self.world.localities[locality_id].control.setdefault(actor, ControlVector())
        old = getattr(vector, dimension)
        new = clamp(target)
        setattr(vector, dimension, new)
        if new != old:
            self.world.causal_ledger.append(
                CausalContribution(self.world.time, locality_id, dimension, new - old, mechanism, event_id)
            )

    def _refresh_aggregate_insurgent_control(
        self, event_id: str, locality_id: str, dimensions: tuple[str, ...]
    ) -> None:
        """Maintain the legacy aggregate insurgent view from live franchises."""
        active_ids = sorted(
            organization.organization_id
            for organization in self.world.organizations.values()
            if (
                organization.kind is OrganizationKind.INSURGENT
                and organization.status == "active"
            )
        )
        if not active_ids or active_ids == ["insurgent"]:
            return
        locality = self.world.localities[locality_id]
        locality.control.setdefault("insurgent", ControlVector())
        for dimension in dimensions:
            complement = 1.0
            for organization_id in active_ids:
                vector = locality.control.get(organization_id)
                value = getattr(vector, dimension) if vector is not None else 0.0
                complement *= 1.0 - clamp(value)
            self._set_control_dimension(
                event_id,
                locality_id,
                "insurgent",
                dimension,
                1.0 - complement,
                "derived_franchise_aggregate",
            )

    def _synthetic_record(self, event_id: str, event_type: str, locality_id: str | None,
                          severity: float, actor: str | None,
                          source_type: str = "process_event") -> SyntheticRecord:
        cfg = self.world.config.recording
        if not cfg.enabled:
            return SyntheticRecord(event_id, self.world.time, locality_id, event_type, False,
                                   0.0, actor, False, 0.0, source_type)
        channel = dict(cfg.source_channels.get("default", {}))
        channel.update(cfg.source_channels.get(source_type, {}))
        base_logit = channel.get("base_logit", cfg.base_logit)
        severity_weight = channel.get("severity_weight", cfg.severity_weight)
        access_weight = channel.get("access_weight", cfg.access_weight)
        remoteness_penalty = channel.get("remoteness_penalty", cfg.remoteness_penalty)
        severity_noise = channel.get("severity_noise", cfg.severity_noise)
        geocoding_error_rate = channel.get("geocoding_error_rate", cfg.geocoding_error_rate)
        geocoding_scale_km = channel.get("geocoding_scale_km", cfg.geocoding_scale_km)
        if locality_id is None:
            access = .5
            remoteness = .5
        else:
            locality = self.world.localities[locality_id]
            access = locality.observability
            remoteness = clamp(locality.terrain_friction / 2.5)
        probability = logistic(base_logit + severity_weight * min(1, severity) +
                               access_weight * access - remoteness_penalty * remoteness)
        recorded = self._recording_rng.random() < probability
        error = severity_noise
        geocoding_error = recorded and self._recording_rng.random() < geocoding_error_rate
        geocoding_distance = (self._recording_rng.expovariate(1 / max(.1, geocoding_scale_km * (1 + 2 * remoteness)))
                              if geocoding_error else 0.0)
        return SyntheticRecord(event_id, self.world.time, locality_id, event_type, recorded,
                               max(0, severity * self._recording_rng.uniform(1 - error, 1 + error)), actor,
                               geocoding_error, geocoding_distance, source_type)

    def on_patrol(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        patrol_id = event.payload["patrol_id"]
        patrol = self.world.patrols.get(patrol_id)
        if patrol is None:
            return {"affected_entity_ids": (patrol_id,)}
        formation = self.world.formations.get(patrol.formation_id)
        if (formation is None or formation.personnel <= 0 or
                formation.operational_status == "ineffective" or formation.outside_pineland):
            return {"affected_entity_ids": (patrol_id, patrol.formation_id)}
        if formation.moving:
            event.payload["next_interval"] = self.world.config.intervals.patrol
            return {"locality_id": formation.locality_id,
                    "actor_ids": (formation.organization_id,),
                    "affected_entity_ids": (patrol_id, formation.formation_id),
                    "unavailable_in_transit": 1.0}
        locality = self.world.localities[patrol.locality_id]
        current_zone = self.world.microzones[patrol.current_microzone_id]
        presence = advance_patrol_presence_memory(
            self.world, self.world.time, patrol_id=patrol_id
        )
        observations = observe_patrol(self.world, patrol.patrol_id, self.world.time, self.rng)
        belief = ensure_zone_belief(
            self.world, formation.organization_id,
            current_zone.microzone_id, self.world.time,
        )

        candidates = sorted(self.world.physical_neighbors[current_zone.microzone_id])
        moved_to = current_zone.microzone_id
        travel_hours = self.world.config.intervals.patrol * 24
        if candidates:
            weights = []
            for candidate in candidates:
                zone_belief = ensure_zone_belief(
                    self.world, formation.organization_id, candidate, self.world.time
                )
                edge = self.world.physical_edges[self.world.physical_neighbors[current_zone.microzone_id][candidate]]
                perceived_need = (((1 - zone_belief.physical_control_estimate) *
                                   (.55 + .45 * zone_belief.confidence) +
                                   .18 * (1 - zone_belief.confidence))
                                  if self.world.config.physical.adaptive_patrol_routing else .5)
                route_noise = self.rng.uniform(0, self.world.config.physical.patrol_route_randomness)
                score = 2.5 * perceived_need - edge.travel_time_hours / self.world.config.physical.response_decay_hours + route_noise
                weights.append(exp(max(-8, min(8, score))))
            moved_to = self.rng.choices(candidates, weights=weights, k=1)[0]
            edge = self.world.physical_edges[self.world.physical_neighbors[current_zone.microzone_id][moved_to]]
            travel_hours = edge.travel_time_hours * (1 + edge.disruption) / max(.2, formation.mobility)
            patrol.current_microzone_id = moved_to
            patrol.route_history.append(moved_to)
            patrol.available_at = self.world.time + travel_hours / 24
            patrol.presence_accounted_at = patrol.available_at
        event.payload["next_interval"] = max(self.world.config.intervals.patrol, travel_hours / 24)
        supply_demand = (formation.available_personnel() *
                         self.world.config.logistics.patrol_consumption_per_person_hour * travel_hours)
        supply_use, supply_shortfall = consume_formation_supply(
            self.world, formation.formation_id, supply_demand, "patrol_activity",
            locality.locality_id, self.world.time,
        )
        if supply_shortfall:
            formation.readiness = clamp(formation.readiness - .01 * supply_shortfall / max(1, supply_demand))
        formation.fatigue = clamp(formation.fatigue + .0008 * travel_hours)
        formation.readiness = clamp(formation.readiness - .0003 * travel_hours)
        return {"locality_id": locality.locality_id, "actor_ids": (formation.organization_id,),
                "affected_entity_ids": (patrol_id, formation.formation_id), "presence": presence,
                "sustainment": -supply_use, "from_microzone": current_zone.microzone_id,
                "to_microzone": moved_to, "travel_time_hours": travel_hours, "severity": presence,
                "observation_ids": tuple(item.observation_id for item in observations),
                "observations_by_actor": {
                    formation.organization_id: tuple(item.observation_id for item in observations)
                }}

    def on_command(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.command),
        ))
        if elapsed_days <= 0:
            return {"orders_issued": 0, "orders_failed": 0,
                    "affected_entity_ids": ()}
        orders = choose_reallocation_orders(
            self.world, self.world.time, self.rng,
            interval_days=elapsed_days,
        )
        return {"orders_issued": len(orders),
                "orders_failed": sum(order.status == "failed_command" for order in orders),
                "affected_entity_ids": tuple(order.order_id for order in orders)}

    def on_force_movement(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        return advance_movement_orders(self.world, self.world.time)

    def on_logistics(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(
            event.payload.get("elapsed_days", event.payload["interval"])
        )
        expired = decay_access_restrictions(
            self.world, self.world.time, elapsed_days
        )
        result = update_logistics(
            self.world,
            self.world.time,
            elapsed_days,
        )
        result["access_restrictions_expired"] = expired
        result["active_access_restrictions"] = len(self.world.access_restrictions)
        return result

    def on_physical_refresh(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        changed = 0
        total = 0.0
        for locality_id in sorted(self.world.localities):
            aggregates = recompute_contested_controls(self.world, locality_id, self.world.time)
            for actor, aggregate in aggregates.items():
                before = self.world.localities[locality_id].control.setdefault(
                    actor, ControlVector()).physical
                def matches_actor(formation) -> bool:
                    organization = self.world.organizations[formation.organization_id]
                    if actor == "government":
                        return organization.kind is not OrganizationKind.INSURGENT
                    if actor == "insurgent":
                        return (
                            organization.kind is OrganizationKind.INSURGENT and
                            organization.status == "active"
                        )
                    return formation.organization_id == actor

                formations = [formation for formation in self.world.formations.values()
                              if formation.locality_id == locality_id and matches_actor(formation)]
                constrained = any(formation.moving or formation.supply_fraction() < .4 or
                                  formation.command < .5 or formation.availability < .5
                                  for formation in formations)
                if actor not in {"government", "insurgent"}:
                    mechanism = (
                        "logistics_constrained_franchise_physical_aggregation"
                        if constrained else "franchise_microzone_physical_aggregation"
                    )
                else:
                    mechanism = (f"logistics_constrained_{actor}_physical_aggregation"
                                 if constrained else f"{actor}_microzone_physical_aggregation")
                self._set_control_dimension(event_id, locality_id, actor, "physical", aggregate,
                                            mechanism)
                changed += aggregate != before
                if actor == "government":
                    total += aggregate
        return {"localities_changed": changed,
                "mean_physical_control": total / max(1, len(self.world.localities))}

    def on_governance(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.governance),
        ))
        cycle_scale = reference_scale(elapsed_days, 30.0)
        total = 0.0
        government = self.world.organizations["government"]
        for locality in self.world.localities.values():
            capacity = locality.administrative_capacity
            leakage = locality.governance["leakage"]
            reference_need = locality.economic_output * .01
            interval_need = reference_need * cycle_scale
            allocation = min(
                government.resources / max(1, len(self.world.localities)),
                interval_need,
            )
            production = min(
                allocation / max(1e-12, interval_need), capacity
            ) * (1 - leakage) if cycle_scale > 0 else 0.0
            cost = allocation * .02
            government.resources = max(0, government.resources - cost)
            total += production * cycle_scale
            self._control(event_id, locality.locality_id, "government", "governance",
                          administrative=.006 * production * cycle_scale,
                          legal=.004 * production * cycle_scale,
                          fiscal=.003 * production * cycle_scale,
                          social=.003 * production * cycle_scale,
                          expected=.002 * production * cycle_scale)
        nonstate_updates = 0
        active_insurgents = [
            organization
            for organization in self.world.organizations.values()
            if (
                organization.kind is OrganizationKind.INSURGENT
                and organization.status == "active"
            )
        ]
        if self.world.config.nonstate_governance.enabled and elapsed_days > 0:
            cfg = self.world.config.nonstate_governance
            decay_fraction = reference_probability(
                cfg.decay_per_30_days, elapsed_days, 30.0
            )
            gain_fraction = reference_probability(
                cfg.gain_per_30_days, elapsed_days, 30.0
            )
            for organization in active_insurgents:
                for locality in self.world.localities.values():
                    rootedness = organization_local_rootedness(
                        self.world, organization, locality.locality_id
                    )
                    member_capacity = clamp(
                        rootedness["represented_local_membership"]
                        / max(
                            1e-12,
                            self.world.config.organization_ecology.minimum_proto_represented_population,
                        )
                    )
                    force_capacity = clamp(
                        committed_fighter_equivalents(
                            self.world,
                            organization.organization_id,
                            locality.locality_id,
                        )
                        / max(
                            1e-12,
                            self.world.config.organization_ecology.minimum_formation_personnel,
                        )
                    )
                    local_capacity = max(member_capacity, force_capacity)
                    rooted_share = max(
                        rootedness["home_locality_share"],
                        rootedness["home_district_share"],
                    )
                    institutional_capacity = clamp(
                        0.5 * organization.institutional_quality
                        + 0.5 * organization.capital.get("organizational", 0.0)
                    )
                    investment = clamp(
                        organization.phenotype.get("governance_investment", 0.0)
                    )
                    support = clamp(
                        local_capacity
                        * (0.5 + 0.5 * rooted_share)
                        * institutional_capacity
                        * investment
                    )
                    vector = locality.control.setdefault(
                        organization.organization_id, ControlVector()
                    )
                    for dimension in (
                        "administrative", "legal", "fiscal", "expected"
                    ):
                        old = getattr(vector, dimension)
                        retained = old * (1.0 - decay_fraction)
                        gain = (
                            gain_fraction * support * (1.0 - retained)
                            if local_capacity >= cfg.minimum_local_capacity
                            else 0.0
                        )
                        target = clamp(retained + gain)
                        nonstate_updates += int(abs(target - old) > 1e-15)
                        self._set_control_dimension(
                            event_id,
                            locality.locality_id,
                            organization.organization_id,
                            dimension,
                            target,
                            "persistent_nonstate_governance",
                        )
            for locality_id in self.world.localities:
                self._refresh_aggregate_insurgent_control(
                    event_id,
                    locality_id,
                    ("administrative", "legal", "fiscal", "social", "expected"),
                )
        return {
            "actor_ids": tuple(
                ["government"]
                + [organization.organization_id for organization in active_insurgents]
            ),
            "governance_production": total,
            "nonstate_governance_updates": nonstate_updates,
        }

    def on_economy(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.economy),
        ))
        cycle_scale = reference_scale(elapsed_days, 30.0)
        net = 0.0
        revenue = 0.0
        external_support_inflow = 0.0
        government = self.world.organizations["government"]
        insurgents = [organization for organization in self.world.organizations.values()
                      if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"]
        for locality in self.world.localities.values():
            security = locality.control["government"].physical
            access_pressure = locality_access_pressure(
                self.world, locality.locality_id
            )
            reference_net_fraction = (
                (.002 + .004 * locality.infrastructure) * (0.5 + .5 * security)
                - (.003 * locality.violence + .002 * locality.disruption)
                - self.world.config.access_restriction.economic_penalty * access_pressure
                - .001
            )
            growth_factor = max(0.0, 1.0 + reference_net_fraction) ** cycle_scale
            delta = locality.economic_output * (growth_factor - 1.0)
            locality.economic_output = max(1, locality.economic_output + delta)
            net += delta
            tax = (
                locality.economic_output * .0005 *
                locality.control["government"].fiscal * cycle_scale
            )
            government.resources += tax
            revenue += tax
            for insurgent in insurgents:
                extraction = (
                    locality.economic_output * .00015 *
                    locality.control.get(
                        insurgent.organization_id, ControlVector()
                    ).fiscal * cycle_scale
                )
                insurgent.resources += extraction
        # Organization.external_support is an organization-level annual
        # support flow. Credit it once per organization, not once per locality.
        for insurgent in insurgents:
            inflow = insurgent.external_support / 12 * cycle_scale
            insurgent.resources += inflow
            external_support_inflow += inflow
        return {"actor_ids": tuple(x for x in ("government", "insurgent") if x in self.world.organizations),
                "net_output": net, "government_revenue": revenue,
                "external_support_inflow": external_support_inflow}

    def on_mobility(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        moved = 0.0
        displaced = 0.0
        returned = 0.0
        resettled = 0.0
        displaced_by_origin: dict[str, float] = {}
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.mobility),
        ))
        if elapsed_days <= 0:
            return {"affected_entity_ids": (), "moved_population": 0.0,
                    "new_displaced_population": 0.0}
        cfg = self.world.config.civilian_dynamics
        voluntary_probability = reference_probability(
            clamp(
                self.world.config.movement_rate
                * cfg.voluntary_move_given_opportunity
            ),
            elapsed_days,
            1.0,
        )
        belief_view = self.world.belief_view()
        for person in self.world.persons.values():
            if person.external_state_id is not None or person.weight <= 0:
                continue
            origin = person.residence_locality_id
            neighbors = self.world.adjacency[origin]
            if not neighbors:
                continue
            if person.displaced:
                if person.home_locality_id == origin:
                    person.displaced = False
                    person.displaced_since = None
                    person.displacement_origin_locality_id = None
                else:
                    home_belief = person.expected_control_by_locality.get(
                        person.home_locality_id, {}
                    ).get(
                        "government",
                        person.expected_control.get("government", .5),
                    )
                    return_probability = reference_probability(
                        clamp(cfg.return_reference_rate * (.5 + .5 * home_belief)),
                        elapsed_days,
                        1.0,
                    )
                    if self.rng.random() < return_probability:
                        route, _, _ = shortest_locality_path(
                            self.world, origin, person.home_locality_id, 1.0
                        )
                        if len(route) > 1:
                            destination = route[1]
                            person.residence_locality_id = destination
                            moved += person.weight
                            returned += person.weight
                            if destination == person.home_locality_id:
                                person.displaced = False
                                person.displaced_since = None
                                person.displacement_origin_locality_id = None
                            continue
                    displacement_age = (
                        max(0.0, self.world.time - person.displaced_since)
                        if person.displaced_since is not None else 0.0
                    )
                    if displacement_age >= cfg.minimum_resettlement_days:
                        resettlement_probability = reference_probability(
                            cfg.resettlement_reference_rate, elapsed_days, 1.0
                        )
                        if self.rng.random() < resettlement_probability:
                            person.displaced = False
                            person.displaced_since = None
                            person.displacement_origin_locality_id = None
                            person.home_locality_id = origin
                            resettled += person.weight

            origin_locality = self.world.localities[origin]
            violence_pressure = clamp(
                (origin_locality.violence - cfg.displacement_violence_threshold)
                / max(1e-12, 1.0 - cfg.displacement_violence_threshold)
            )
            access_pressure = locality_access_pressure(self.world, origin)
            forced_probability = reference_probability(
                clamp(
                    cfg.forced_displacement_reference_rate
                    * max(violence_pressure, access_pressure)
                ),
                elapsed_days,
                1.0,
            )
            forced = self.rng.random() < forced_probability
            voluntary = (
                not forced and self.rng.random() < voluntary_probability
            )
            if not forced and not voluntary:
                continue
            candidates = list(neighbors)
            utilities = []
            for destination in candidates:
                locality = self.world.localities[destination]
                # Mobility is a policy response to the person's belief, not a
                # hidden read of realized destination control.
                security = belief_view.expected_destination_control(person.person_id, destination, "government")
                livelihood = log(max(2, locality.economic_output / max(1, locality.population)))
                restriction = edge_restriction_level(
                    self.world, origin, destination, None
                )
                utility = (
                    1.2 * security + .1 * livelihood - neighbors[destination]
                    - self.world.config.access_restriction.civilian_utility_penalty
                    * restriction
                )
                utilities.append(exp(max(-10, min(10, utility))))
            destination = self.rng.choices(candidates, weights=utilities, k=1)[0]
            person.residence_locality_id = destination
            moved += person.weight
            if forced and destination != person.home_locality_id:
                if not person.displaced:
                    person.displaced_since = self.world.time
                    person.displacement_origin_locality_id = origin
                    person.displacement_count += 1
                person.displaced = True
                displaced += person.weight
                displaced_by_origin[origin] = (
                    displaced_by_origin.get(origin, 0.0) + person.weight
                )
            elif destination == person.home_locality_id:
                person.displaced = False
                person.displaced_since = None
                person.displacement_origin_locality_id = None
        # ``displaced_population`` is a stock, not the number/mass of agents
        # sampled by this mobility event.  Recompute it from every displaced
        # representative so low movement rates cannot silently erase most of
        # the represented displaced population from locality state.
        displaced_by_locality = {locality_id: 0.0 for locality_id in self.world.localities}
        for person in self.world.persons.values():
            if (person.external_state_id is None and person.displaced and
                    person.residence_locality_id in displaced_by_locality):
                displaced_by_locality[person.residence_locality_id] += person.weight
        for locality_id, population in displaced_by_locality.items():
            self.world.localities[locality_id].displaced_population = population
        for household in self.world.households.values():
            by_locality: dict[str, float] = {}
            for person_id in household.member_ids:
                member = self.world.persons.get(person_id)
                if (
                    member is None or member.external_state_id is not None
                    or member.weight <= 0
                ):
                    continue
                by_locality[member.residence_locality_id] = (
                    by_locality.get(member.residence_locality_id, 0.0)
                    + member.weight
                )
            if by_locality:
                household.residence_locality_id = max(
                    by_locality,
                    key=lambda locality_id: (by_locality[locality_id], locality_id),
                )
        for origin_locality_id, quantity in displaced_by_origin.items():
            record_displacement_harm(
                self.world, event_id, origin_locality_id, quantity
            )
        return {
            "affected_entity_ids": (),
            "moved_population": moved,
            "new_displaced_population": displaced,
            "returned_population": returned,
            "resettled_population": resettled,
        }

    def on_beliefs(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        # Beliefs are updated from local social signals only.  Realized control
        # is intentionally unavailable to this actor-facing process.
        updates = 0
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.beliefs),
        ))
        if elapsed_days <= 0:
            return {"belief_updates": 0, "relays_delivered": 0,
                    "relays_dropped": 0}
        noise = self.world.config.observation_noise
        perceived_actors = ["government"]
        active_insurgent_ids = sorted(
            organization.organization_id
            for organization in self.world.organizations.values()
            if (
                organization.kind is OrganizationKind.INSURGENT
                and organization.status == "active"
            )
        )
        if active_insurgent_ids:
            perceived_actors.append("insurgent")
            perceived_actors.extend(
                organization_id
                for organization_id in active_insurgent_ids
                if organization_id != "insurgent"
            )
        locality_signals = {}
        for locality_id in self.world.localities:
            aggregate = locality_social_aggregation(self.world, locality_id)
            franchise_profile = locality_franchise_support_profile(
                self.world, locality_id
            ) if active_insurgent_ids else {
                "represented_franchise_support": {}
            }
            for actor in perceived_actors:
                # Communities are graph/mesoscale partitions, not equal-size
                # population bins.  Destination beliefs therefore consume the
                # represented-population aggregation rather than giving each
                # sampled community one equal vote.
                if actor == "government":
                    signal = aggregate["government_cooperation"]
                elif actor == "insurgent":
                    signal = aggregate["insurgent_sympathy"]
                else:
                    signal = clamp(
                        franchise_profile["represented_franchise_support"].get(
                            actor, 0.0
                        )
                        / max(1.0, self.world.localities[locality_id].population)
                    )
                locality_signals[(locality_id, actor)] = signal
        for person in self.world.persons.values():
            community = self.world.social_communities.get(person.community_id)
            if community is None:
                continue
            for actor in perceived_actors:
                if actor == "government":
                    signal = community.government_cooperation
                elif actor == "insurgent":
                    signal = community.insurgent_sympathy
                else:
                    signal = locality_signals.get(
                        (person.residence_locality_id, actor), 0.0
                    )
                observed = clamp(signal + self.rng.normalvariate(0, noise))
                trust = person.trust.get(
                    actor,
                    person.trust.get("insurgent", .2)
                    if actor not in {"government", "insurgent"} else .2,
                )
                old = person.expected_control.get(
                    actor,
                    person.expected_control.get("insurgent", .2)
                    if actor not in {"government", "insurgent"} else .2,
                )
                learning = reference_probability(
                    clamp(.12 * trust), elapsed_days, 1.0
                )
                person.expected_control[actor] = clamp(
                    old + learning * (observed - old)
                )
                # Store only adjacent destination beliefs; this keeps the
                # representation sparse while making mobility genuinely
                # destination-specific and still belief-driven.
                for destination in self.world.adjacency.get(person.residence_locality_id, {}):
                    destination_signal = locality_signals.get((destination, actor))
                    if destination_signal is None:
                        continue
                    prior = person.expected_control_by_locality.setdefault(
                        destination, {}).get(actor, person.expected_control.get(actor, .5))
                    person.expected_control_by_locality[destination][actor] = clamp(
                        prior + learning * (destination_signal - prior))
                updates += 1
        return {"belief_updates": updates, "relays_delivered": 0,
                "relays_dropped": 0}

    def on_information(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        result = process_information(self.world, self.world.time, self.rng)
        observations_by_actor: dict[str, tuple[str, ...]] = {}
        for observation_id in result["observation_ids"]:
            observation = self.world.observations[observation_id]
            observations_by_actor.setdefault(observation.observer_actor_id, tuple())
            observations_by_actor[observation.observer_actor_id] += (observation_id,)
        return {"information_generated": result["generated"],
                "observation_ids": result["observation_ids"],
                "relays_delivered": result["relays_delivered"],
                "relays_dropped": result["relays_dropped"],
                "active_relays": result["active_relays"],
                "observations_by_actor": observations_by_actor}

    def on_social_influence(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        """Translate explicit neighbor signals into exposure and observable behavior."""
        rng = self.rng
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.social_influence),
        ))
        if elapsed_days <= 0:
            represented_population = max(1e-12, self.world.weighted_population())
            represented_mean_degree = sum(
                person.weight * len(
                    self.world.social_neighbors.get(person.person_id, ())
                )
                for person in self.world.persons.values()
            ) / represented_population
            return {"behavior_changes": 0, "behavior_changed_population": 0.0,
                    "mean_degree": 2 * len(self.world.social_edges) / max(1, len(self.world.persons)),
                    "represented_mean_degree": represented_mean_degree,
                    "affected_localities": 0}
        behavior_probability = reference_probability(
            self.world.config.social_network.behavior_update_rate,
            elapsed_days,
            1.0,
        )
        behavior_changes = 0
        behavior_changed_population = 0.0
        locality_government_shift: dict[str, float] = {}
        locality_insurgent_shift: dict[str, float] = {}
        locality_franchise_shift: dict[tuple[str, str], float] = {}
        behavior_score = {
            "government_cooperation": (1.0, 0.0),
            "party_participation": (.25, 0.0),
            "civil_society": (.15, 0.0),
            "protest": (-.15, .1),
            "insurgent_sympathy": (-.4, .7),
            "armed_participation": (-.7, 1.0),
            "inactive": (0.0, 0.0),
            "migration": (0.0, 0.0),
            "neutral": (0.0, 0.0),
        }
        active_insurgent_ids = sorted(
            organization.organization_id
            for organization in self.world.organizations.values()
            if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
        )
        insurgent_available = bool(active_insurgent_ids)
        for person_id in sorted(self.world.persons):
            person = self.world.persons[person_id]
            old_affinity = dict(person.insurgent_affinity)
            neighbors = self.world.social_neighbors.get(person_id, ())
            government_signal = 0.0
            insurgent_signal = 0.0
            insurgent_signal_by_org = {organization_id: 0.0
                                       for organization_id in active_insurgent_ids}
            total_weight = 0.0
            for neighbor_id in neighbors:
                neighbor = self.world.persons[neighbor_id]
                edge = edge_between(self.world, person_id, neighbor_id)
                # Edge weight already contains language attenuation. Multiplicity
                # makes unequal representative weights explicit; normalization
                # below prevents agent resolution from becoming raw influence.
                influence = edge.weight * edge.trust * edge.represented_relationships
                neighbor_government, neighbor_insurgent = behavior_score.get(neighbor.public_behavior, (0.0, 0.0))
                neighbor_org = self.world.organizations.get(neighbor.organization_id or "")
                if (neighbor_org is not None and
                        neighbor_org.kind is OrganizationKind.INSURGENT and
                        neighbor_org.status == "active"):
                    # A weighted representative can contain only a fractional
                    # armed cohort.  Do not let a 5% armed fraction broadcast
                    # the same network signal as a fully mobilized population.
                    neighbor_insurgent = max(
                        neighbor.armed_fraction, neighbor_insurgent * neighbor.armed_fraction
                    )
                    if neighbor_org.organization_id in insurgent_signal_by_org:
                        insurgent_signal_by_org[neighbor_org.organization_id] += (
                            influence * neighbor_insurgent
                        )
                elif neighbor_insurgent > 0 and neighbor.insurgent_affinity:
                    # Unarmed sympathizers and ex-members can retain allegiance
                    # to a specific franchise. Split their insurgent signal by
                    # active affinity mass instead of making every franchise an
                    # interchangeable beneficiary of generic sympathy.
                    active_affinity = {
                        oid: max(0.0, float(value))
                        for oid, value in neighbor.insurgent_affinity.items()
                        if oid in insurgent_signal_by_org and value > 0
                    }
                    affinity_total = sum(active_affinity.values())
                    if affinity_total > 0:
                        for oid, affinity in active_affinity.items():
                            insurgent_signal_by_org[oid] += (
                                influence * neighbor_insurgent * affinity / affinity_total
                            )
                if not insurgent_available:
                    neighbor_insurgent = 0.0
                government_signal += influence * max(0.0, neighbor_government)
                insurgent_signal += influence * neighbor_insurgent
                total_weight += influence
            if total_weight:
                government_signal /= total_weight
                insurgent_signal /= total_weight
                for organization_id in insurgent_signal_by_org:
                    insurgent_signal_by_org[organization_id] /= total_weight
            if len(active_insurgent_ids) == 1:
                # Preserve the legacy one-insurgent interpretation of generic
                # sympathy exactly: with no rival franchise, all insurgent
                # social exposure belongs to the sole active organization.
                insurgent_signal_by_org[active_insurgent_ids[0]] = insurgent_signal
            person.social_exposure = {
                "government": clamp(government_signal),
                "insurgent": clamp(insurgent_signal),
                **{organization_id: clamp(value)
                   for organization_id, value in insurgent_signal_by_org.items()},
            }
            if (person.organization_id is None and
                    person.public_behavior in {"insurgent_sympathy", "armed_participation"}):
                affinity_total = sum(insurgent_signal_by_org.values())
                if affinity_total > 0:
                    person.insurgent_affinity = {
                        oid: clamp(value / affinity_total)
                        for oid, value in insurgent_signal_by_org.items() if value > 0
                    }
            if rng.random() >= behavior_probability:
                continue
            party_affinity = max(person.private_preference.values(), default=.5)
            expected_government = person.expected_control.get("government", .5)
            expected_insurgent = person.expected_control.get("insurgent", .1)
            member_org = self.world.organizations.get(person.organization_id or "")
            armed_membership_utility = (-1.5 + 3.0 * person.armed_fraction
                                        if member_org is not None and
                                        member_org.kind is OrganizationKind.INSURGENT else -1.5)
            utilities = {
                "inactive": .7 + person.fear - person.efficacy,
                "government_cooperation": (party_affinity + expected_government +
                                           self.world.config.social_network.behavior_exposure_weight * government_signal -
                                           person.grievance - .4 * person.fear),
                "party_participation": party_affinity + person.efficacy + person.political_access - .5 * person.fear,
                "civil_society": .5 + person.efficacy + .6 * person.political_access - .3 * person.fear,
                "protest": 1.2 * person.grievance + person.efficacy + .25 * person.political_access - person.fear,
                "insurgent_sympathy": (1.2 * person.grievance + expected_insurgent +
                                       self.world.config.social_network.behavior_exposure_weight * insurgent_signal - person.fear),
                "armed_participation": (armed_membership_utility +
                                        person.grievance +
                                        self.world.config.social_network.behavior_exposure_weight * insurgent_signal - person.fear -
                                        self.world.config.political_order.peaceful_channel_strength * person.political_access),
                "migration": (1.4 if person.displaced else -.8) + person.fear - expected_government,
            }
            if not insurgent_available:
                utilities.pop("insurgent_sympathy")
                utilities.pop("armed_participation")
            peak = max(utilities.values())
            choices = list(utilities)
            weights = [exp(utilities[choice] - peak) for choice in choices]
            new_behavior = rng.choices(choices, weights=weights, k=1)[0]
            old_behavior = person.public_behavior
            if new_behavior == old_behavior:
                continue
            old_government, old_insurgent = behavior_score.get(old_behavior, (0.0, 0.0))
            new_government, new_insurgent = behavior_score[new_behavior]
            locality_id = person.residence_locality_id
            locality_government_shift[locality_id] = locality_government_shift.get(locality_id, 0.0) + person.weight * (new_government - old_government)
            locality_insurgent_shift[locality_id] = locality_insurgent_shift.get(locality_id, 0.0) + person.weight * (new_insurgent - old_insurgent)
            person.public_behavior = new_behavior
            if person.organization_id is None:
                if new_behavior in {"insurgent_sympathy", "armed_participation"}:
                    affinity_total = sum(insurgent_signal_by_org.values())
                    if affinity_total > 0:
                        person.insurgent_affinity = {
                            oid: clamp(value / affinity_total)
                            for oid, value in insurgent_signal_by_org.items() if value > 0
                        }
                else:
                    person.insurgent_affinity.clear()
            def affinity_shares(values: dict[str, float], behavior: str) -> dict[str, float]:
                positive = {
                    oid: max(0.0, float(values.get(oid, 0.0)))
                    for oid in active_insurgent_ids
                    if values.get(oid, 0.0) > 0
                }
                total = sum(positive.values())
                if total > 0:
                    return {oid: value / total for oid, value in positive.items()}
                if (len(active_insurgent_ids) == 1 and
                        behavior in {"insurgent_sympathy", "armed_participation"}):
                    return {active_insurgent_ids[0]: 1.0}
                return {}

            old_shares = affinity_shares(old_affinity, old_behavior)
            new_shares = affinity_shares(person.insurgent_affinity, new_behavior)
            for organization_id in active_insurgent_ids:
                old_specific = old_insurgent * old_shares.get(organization_id, 0.0)
                new_specific = new_insurgent * new_shares.get(organization_id, 0.0)
                specific_shift = person.weight * (new_specific - old_specific)
                if specific_shift:
                    key = (locality_id, organization_id)
                    locality_franchise_shift[key] = (
                        locality_franchise_shift.get(key, 0.0) + specific_shift
                    )
            behavior_changes += 1
            behavior_changed_population += person.weight

        for locality_id in set(locality_government_shift) | set(locality_insurgent_shift):
            population = max(1, self.world.localities[locality_id].population)
            government_delta = .01 * locality_government_shift.get(locality_id, 0.0) / population
            insurgent_delta = .01 * locality_insurgent_shift.get(locality_id, 0.0) / population
            self._control(event_id, locality_id, "government", "social_network_influence", social=government_delta)
            if insurgent_available:
                self._control(event_id, locality_id, "insurgent", "social_network_influence", social=insurgent_delta)
        for (locality_id, organization_id), represented_shift in locality_franchise_shift.items():
            population = max(1, self.world.localities[locality_id].population)
            self._control(
                event_id, locality_id, organization_id,
                "franchise_social_network_influence",
                social=.01 * represented_shift / population,
            )
        refresh_community_aggregates(self.world)
        represented_population = max(1e-12, self.world.weighted_population())
        represented_mean_degree = sum(
            person.weight * len(self.world.social_neighbors.get(person.person_id, ()))
            for person in self.world.persons.values()
        ) / represented_population
        return {"behavior_changes": behavior_changes,
                "behavior_changed_population": behavior_changed_population,
                "mean_degree": 2 * len(self.world.social_edges) / max(1, len(self.world.persons)),
                "represented_mean_degree": represented_mean_degree,
                "affected_localities": len(set(locality_government_shift) | set(locality_insurgent_shift))}

    def on_recruitment(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get("interval", self.world.config.intervals.recruitment),
        ))
        if elapsed_days <= 0:
            return {
                "recruits": 0.0, "exits": 0.0,
                "fighter_recruits": 0.0, "fighter_exits": 0.0,
                "formations_created": 0,
                "local_manpower_pools": sum(self.world.organization_manpower_pools.values()),
                "membership_repairs": 0,
                "actor_ids": tuple(
                    o.organization_id for o in self.world.organizations.values()
                    if o.kind is OrganizationKind.INSURGENT and o.status == "active"
                ),
            }
        result = recruit_and_retain(
            self.world,
            self.world.time,
            self.rng,
            interval_days=elapsed_days,
        )
        result["actor_ids"] = tuple(o.organization_id for o in self.world.organizations.values()
                                    if o.kind is OrganizationKind.INSURGENT and o.status == "active")
        return result

    def on_organization_ecology(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        elapsed_days = float(event.payload.get(
            "elapsed_days",
            event.payload.get(
                "interval", self.world.config.organization_ecology.interval_days
            ),
        ))
        if elapsed_days <= 0:
            return {
                "proto_created": 0, "births": 0, "splits": 0, "mergers": 0,
                "collapses": 0,
                "active_armed_organizations": sum(
                    o.kind is OrganizationKind.INSURGENT and o.status == "active"
                    for o in self.world.organizations.values()
                ),
                "affected_entity_ids": (),
            }
        result = process_organization_ecology(
            self.world,
            self.world.time,
            self.rng,
            interval_days=elapsed_days,
        )
        result["affected_entity_ids"] = tuple(
            transition.transition_id for transition in self.world.organization_transitions
            if transition.time == self.world.time
        )
        return result

    def on_political_order(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        result = process_political_order(
            self.world, self.world.time, event_id, self.rng,
            interval_days=float(event.payload.get(
                "elapsed_days",
                event.payload.get(
                    "interval", self.world.config.political_order.interval_days
                ),
            )),
        )
        result["actor_ids"] = tuple(filter(None, ("government", self.world.ruling_party_id)))
        return result

    def on_foreign_affairs(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        result = process_foreign_affairs(
            self.world, self.world.time, event_id, self.rng,
            interval_days=float(event.payload.get(
                "elapsed_days",
                event.payload.get(
                    "interval", self.world.config.foreign_affairs.interval_days
                ),
            )),
        )
        result["actor_ids"] = tuple(sorted(self.world.foreign_states))
        return result

    def on_peace_process(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        result = process_peace(
            self.world, self.world.time, event_id, self.rng,
            interval_days=float(event.payload.get(
                "elapsed_days",
                event.payload.get(
                    "interval", self.world.config.peace_process.interval_days
                ),
            )),
        )
        result["actor_ids"] = tuple(sorted({actor for item in self.world.negotiations.values()
                                            for actor in (item.government_id, *item.insurgent_ids)}))
        return result

    def on_contact(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        locality_id = event.payload["locality_id"]
        microzone_id = event.payload.get("microzone_id")
        trace = {
            "event_id": event_id,
            "time": self.world.time,
            "week_index": int(self.world.time // 7),
            "locality_id": locality_id,
            "microzone_id": microzone_id,
            "government_formation_ids": [],
            "insurgent_formation_ids": [],
            "candidate_pairs": [],
            "detected_by": [],
            "gate_counts": {
                "opposing_armed_organizations": 0,
                "opposing_formation_candidate_pairs": 0,
                "same_locality_candidate_pairs": 0,
                "microzone_eligible_candidate_pairs": 0,
                "proximity_qualified_pairs": 0,
                "true_target_presence_cases": 0,
                "detected_opponent_sides": 0,
                "failed_detection_sides": 0,
                "willingness_decisions": 0,
                "readiness_available_pairs": 0,
                "supply_eligible_pairs": 0,
                "command_eligible_pairs": 0,
                "engagement_hazard_draws": 0,
                "engagement_hazard_passes": 0,
                "realized_latent_contacts": 0,
                "recorded_contacts": 0,
                "recording_draw_passes": 0,
                "recorded_engagements": 0,
            },
            "failure_reason": "not_reached",
        }

        def finish(result: dict[str, Any], reason: str) -> dict[str, Any]:
            trace["failure_reason"] = reason
            self.world.record_contact_funnel(trace)
            result["contact_funnel"] = trace
            return result

        if self.world.config.contact_rate <= 0:
            return finish({"locality_id": locality_id, "contact": 0.0}, "contact_rate_disabled")
        local = [f for f in self.world.formations.values()
                 if f.locality_id == locality_id and f.personnel > 0 and not f.moving and
                 not f.outside_pineland and f.operational_status == "effective"]
        government = [f for f in local if self.world.organizations[f.organization_id].kind in
                      {OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN}]
        insurgents = [f for f in local if self.world.organizations[f.organization_id].kind is OrganizationKind.INSURGENT
                      and self.world.organizations[f.organization_id].status == "active"]
        trace["government_formation_ids"] = sorted(f.formation_id for f in government)
        trace["insurgent_formation_ids"] = sorted(f.formation_id for f in insurgents)
        trace["gate_counts"]["opposing_armed_organizations"] = int(bool(government and insurgents))
        trace["gate_counts"]["opposing_formation_candidate_pairs"] = len(government) * len(insurgents)
        trace["gate_counts"]["same_locality_candidate_pairs"] = len(government) * len(insurgents)
        candidate_pairs = [(g, i) for g in government for i in insurgents]
        trace["candidate_pairs"] = [
            {"government_formation_id": g.formation_id, "insurgent_formation_id": i.formation_id,
             "government_microzone_id": formation_microzone(self.world, g),
             "insurgent_microzone_id": formation_microzone(self.world, i)}
            for g, i in candidate_pairs
        ]
        microzone_pairs = [(g, i) for g, i in candidate_pairs
                           if formation_microzone(self.world, g) == formation_microzone(self.world, i) and
                           (microzone_id is None or formation_microzone(self.world, g) == microzone_id)]
        trace["gate_counts"]["microzone_eligible_candidate_pairs"] = len(microzone_pairs)
        trace["gate_counts"]["proximity_qualified_pairs"] = len(microzone_pairs)
        if not government or not insurgents:
            reason = ("no_active_government_formation" if not government else
                      "no_active_insurgent_formation")
            return finish({"locality_id": locality_id, "contact": 0.0}, reason)
        if not microzone_pairs:
            return finish({"locality_id": locality_id, "contact": 0.0,
                           "actor_ids": (government[0].organization_id, insurgents[0].organization_id)},
                          "no_microzone_proximity")
        requested_g = event.payload.get("government_formation_id")
        requested_i = event.payload.get("insurgent_formation_id")
        selected = [(g, i) for g, i in microzone_pairs
                    if (requested_g is None or g.formation_id == requested_g) and
                    (requested_i is None or i.formation_id == requested_i)]
        if not selected:
            return finish({"locality_id": locality_id, "contact": 0.0}, "scheduled_pair_unavailable")
        # Direct calls without pair IDs remain supported for component tests;
        # the production scheduler always supplies an exact pair.
        g, i = sorted(selected, key=lambda pair: (pair[0].formation_id, pair[1].formation_id))[0]
        trace["selected_government_formation_id"] = g.formation_id
        trace["selected_insurgent_formation_id"] = i.formation_id
        locality = self.world.localities[locality_id]
        trace["gate_counts"]["true_target_presence_cases"] = 2
        forced_detection = event.payload.get("force_detection")
        legacy_contact = self.world.config.combat.contact_opportunity_model == "legacy_symmetric"
        g_observation = i_observation = None

        def local_presence_signal(observer, target) -> float:
            """Actionable actor-local belief that the target is present.

            Production contact scheduling must not create a new sensing draw
            merely because its numerical scan cadence changed.  Detection is
            owned by the information process; contact consumes the most
            specific local belief already available to the formation.
            """
            candidates = (
                get_presence_belief(
                    self.world, observer.formation_id, target.organization_id,
                    locality_id, target.formation_id, microzone_id, node=True,
                ),
                get_presence_belief(
                    self.world, observer.formation_id, target.organization_id,
                    locality_id, None, microzone_id, node=True,
                ),
                get_presence_belief(
                    self.world, observer.organization_id, target.organization_id,
                    locality_id, target.formation_id, microzone_id,
                ),
                get_presence_belief(
                    self.world, observer.organization_id, target.organization_id,
                    locality_id, None, microzone_id,
                ),
            )
            usable = [belief for belief in candidates
                      if belief is not None and belief.evidence_count > 0]
            if not usable:
                return 0.0
            belief = max(
                usable,
                key=lambda item: (
                    item.updated_at,
                    item.confidence,
                    item.evidence_count,
                ),
            )
            return clamp(belief.presence_estimate)

        # Explicitly forced detection is retained for controlled component
        # tests. Legacy contact retains its historical contact-source draw.
        # Directional production contact consumes prior actor-local beliefs,
        # so changing only contact_scan cadence does not manufacture extra
        # detection opportunities.
        if forced_detection is not None or legacy_contact:
            g_observation = observe_target(
                self.world, g.organization_id, g.formation_id,
                f"CONTACT:{g.formation_id}:{i.formation_id}",
                "contact", locality_id, i.organization_id, self.world.time, self.rng,
                i.formation_id, microzone_id=microzone_id,
                force_detection=forced_detection,
            )
            i_observation = observe_target(
                self.world, i.organization_id, i.formation_id,
                f"CONTACT:{i.formation_id}:{g.formation_id}",
                "contact", locality_id, g.organization_id, self.world.time, self.rng,
                g.formation_id, microzone_id=microzone_id,
                force_detection=forced_detection,
            )
            detection_signal_g = float(bool(
                g_observation and g_observation.estimated_value.get("detected", False)
            ))
            detection_signal_i = float(bool(
                i_observation and i_observation.estimated_value.get("detected", False)
            ))
            detection_source = (
                "forced_contact_observation" if forced_detection is not None
                else "legacy_contact_observation"
            )
        else:
            detection_signal_g = local_presence_signal(g, i)
            detection_signal_i = local_presence_signal(i, g)
            detection_source = "actor_local_presence_belief"

        detection_g = detection_signal_g >= 0.5
        detection_i = detection_signal_i >= 0.5
        detected_by = tuple(
            actor for actor, detected in ((g.organization_id, detection_g),
                                          (i.organization_id, detection_i))
            if detected
        )
        trace["detected_by"] = list(detected_by)
        trace["detection_source"] = detection_source
        trace["detection_signal"] = {
            g.formation_id: detection_signal_g,
            i.formation_id: detection_signal_i,
        }
        trace["gate_counts"]["detected_opponent_sides"] = len(detected_by)
        trace["gate_counts"]["failed_detection_sides"] = 2 - len(detected_by)
        interval_days = max(0.0, float(event.payload.get("interval_days", 1.0)))
        proximity = 1.0  # candidate scheduler currently emits same-locality pairs
        detection_factor = (detection_signal_g + detection_signal_i) / 2.0
        supply_rule = self.world.config.combat.contact_supply_rule
        supply_level = min(g.supply_fraction(), i.supply_fraction())
        accidental = self.world.config.combat.accidental_contact_fraction

        def directional_supply_factor(formation) -> float:
            if supply_rule == "continuous":
                # Only the prospective initiator's stock affects its deliberate
                # initiation rate.  The target's stock cannot suppress being
                # found or attacked.
                return 0.2 + 0.8 * formation.supply_fraction() ** .5
            if supply_rule == "initiation_asymmetry":
                return float(formation.supply_fraction() > 0)
            return 1.0

        supply_g = directional_supply_factor(g)
        supply_i = directional_supply_factor(i)
        # Detection owns readiness/search effectiveness.  Once a target has
        # actually been detected, deliberate initiation uses availability and
        # command once each; supply enters only through an explicitly selected
        # contact-supply theory branch.
        activity_g = clamp(g.availability) * clamp(g.command)
        activity_i = clamp(i.availability) * clamp(i.command)
        initiation_g = activity_g * detection_signal_g * supply_g
        initiation_i = activity_i * detection_signal_i * supply_i
        pair_supply_factor = 1.0
        if supply_rule == "continuous":
            pair_supply_factor = 0.2 + 0.8 * supply_level ** .5

        lambda_accidental = 0.0
        if legacy_contact:
            lambda_gi = lambda_ig = 0.0
            legacy_activity = clamp(g.effective_readiness() * i.effective_readiness())
            contact_hazard_rate = (
                self.world.config.contact_rate * proximity * detection_factor *
                legacy_activity * pair_supply_factor
            )
            contact_hazard = 1 - exp(-contact_hazard_rate * interval_days)
        else:
            # contact_rate is a per-pair, per-day hazard scale.  The two
            # directional deliberate components share the non-accidental
            # portion, so a fully active/detecting pair never silently turns a
            # nominal per-pair rate into twice that rate.
            pair_rate = self.world.config.contact_rate * proximity
            deliberate_share = 1.0 - accidental
            lambda_gi = pair_rate * deliberate_share * 0.5 * initiation_g
            lambda_ig = pair_rate * deliberate_share * 0.5 * initiation_i
            lambda_accidental = pair_rate * accidental
            contact_hazard_rate = lambda_gi + lambda_ig + lambda_accidental
            contact_hazard = 1 - exp(-contact_hazard_rate * interval_days)
        trace["proximity"] = proximity
        trace["detection_factor"] = detection_factor
        trace["activity"] = {g.formation_id: activity_g, i.formation_id: activity_i}
        trace["directional_hazards_per_day"] = {g.formation_id: lambda_gi, i.formation_id: lambda_ig}
        trace["accidental_hazard_per_day"] = lambda_accidental
        trace["contact_hazard_rate_per_day"] = contact_hazard_rate
        trace["interval_days"] = interval_days
        trace["contact_hazard"] = contact_hazard
        trace["supply_contact_rule"] = supply_rule
        trace["supply_factor"] = pair_supply_factor
        trace["directional_supply_factors"] = {
            g.formation_id: supply_g, i.formation_id: supply_i,
        }
        trace["contact_supply_threshold"] = (
            self.world.config.combat.contact_ammunition_floor
            if supply_rule == "ammunition_floor" else 0.0
        )
        readiness_g = g.fatigue_adjusted_readiness()
        readiness_i = i.fatigue_adjusted_readiness()
        readiness_available = (
            (readiness_g > 0 and readiness_i > 0 and
             g.availability > 0 and i.availability > 0)
            if legacy_contact else
            ((readiness_g > 0 and g.availability > 0) or
             (readiness_i > 0 and i.availability > 0))
        )
        if supply_rule == "hard_gate":
            supply_eligible = supply_level > 0
        elif supply_rule == "ammunition_floor":
            supply_eligible = supply_level >= self.world.config.combat.contact_ammunition_floor
        else:
            supply_eligible = True
        command_eligible = ((g.command > 0 and i.command > 0) if legacy_contact else
                            ((activity_g > 0 and detection_signal_g > 0) or
                             (activity_i > 0 and detection_signal_i > 0) or accidental > 0))
        trace["readiness"] = {g.formation_id: g.effective_readiness(), i.formation_id: i.effective_readiness()}
        trace["fatigue_adjusted_readiness"] = {
            g.formation_id: readiness_g, i.formation_id: readiness_i,
        }
        trace["availability"] = {g.formation_id: g.availability, i.formation_id: i.availability}
        trace["supply_fraction"] = {g.formation_id: g.supply_fraction(), i.formation_id: i.supply_fraction()}
        trace["command"] = {g.formation_id: g.command, i.formation_id: i.command}
        trace["gate_counts"]["readiness_available_pairs"] = int(readiness_available)
        trace["gate_counts"]["supply_eligible_pairs"] = int(supply_eligible)
        trace["gate_counts"]["command_eligible_pairs"] = int(command_eligible)
        trace["gate_counts"]["willingness_decisions"] = (
            int(detection_signal_g > 0) + int(detection_signal_i > 0)
        )
        hazard_draw = None
        hazard_pass = False
        if contact_hazard > 0 and (bool(detected_by) or not legacy_contact):
            hazard_draw = self.rng.random()
            hazard_pass = hazard_draw < contact_hazard
            trace["gate_counts"]["engagement_hazard_draws"] = 1
            trace["gate_counts"]["engagement_hazard_passes"] = int(hazard_pass)
        trace["hazard_draw"] = hazard_draw
        trace["willingness_model"] = "directional competing initiation hazards plus accidental co-presence"
        if legacy_contact:
            blocked = (not hazard_pass or not readiness_available or
                       not supply_eligible or not command_eligible)
        else:
            # Directional initiation factors are already inside the hazard.
            # Do not post-hoc multiply readiness/availability/command again.
            # Only explicit pair-level supply-floor experiments remain gates.
            blocked = not hazard_pass or not supply_eligible
        if blocked:
            reason = ("failed_detection" if legacy_contact and not detected_by else
                      "readiness_or_availability" if legacy_contact and not readiness_available else
                      "supply_exclusion" if not supply_eligible else
                      "command_exclusion" if legacy_contact and not command_eligible else
                      "no_contact_hazard" if contact_hazard <= 0 else
                      "engagement_hazard_draw")
            return finish({"locality_id": locality_id, "actor_ids": (g.organization_id, i.organization_id),
                    "contact": 0.0, "detected_by": detected_by,
                    "proximity": proximity, "detection_factor": detection_factor,
                    "contact_hazard": contact_hazard,
                    "disengaged": 0.0,
                    "information_asymmetry": float(len(detected_by) == 1),
                    "observation_ids": tuple(item.observation_id for item in (g_observation, i_observation)
                                              if item is not None),
                    "observations_by_actor": {
                        g.organization_id: tuple(item.observation_id for item in (g_observation,) if item),
                        i.organization_id: tuple(item.observation_id for item in (i_observation,) if item),
                    }}, reason)

        initiator_organization_id = None
        contact_cause = "legacy_detected_contact" if legacy_contact else "accidental"
        if not legacy_contact:
            cause_rates = (
                ("government_initiated", g.organization_id, lambda_gi),
                ("insurgent_initiated", i.organization_id, lambda_ig),
                ("accidental", None, lambda_accidental),
            )
            total_rate = sum(rate for _, _, rate in cause_rates)
            cause_draw = self.rng.random() * total_rate
            running = 0.0
            for cause, initiator_id, rate in cause_rates:
                running += rate
                if cause_draw <= running:
                    contact_cause = cause
                    initiator_organization_id = initiator_id
                    break
            trace["contact_cause_draw"] = cause_draw
        trace["contact_cause"] = contact_cause
        trace["initiator_organization_id"] = initiator_organization_id
        engagement, outcome_observations = resolve_engagement(
            self.world, event_id, g, i, detected_by, self.world.time, self.rng,
            initiator_organization_id=initiator_organization_id,
            contact_cause=contact_cause,
        )
        all_observations = tuple(item for item in (g_observation, i_observation) if item is not None) + outcome_observations
        trace["gate_counts"]["realized_latent_contacts"] = 1
        trace["failure_reason"] = "realized"
        self.world.record_contact_funnel(trace)
        return {"locality_id": locality_id, "actor_ids": (g.organization_id, i.organization_id),
                "affected_entity_ids": (g.formation_id, i.formation_id), "contact": 1.0,
                "engagement_id": engagement.engagement_id,
                "government_losses": -engagement.personnel_losses[g.formation_id],
                "insurgent_losses": -engagement.personnel_losses[i.formation_id],
                "civilian_harm": engagement.civilian_harm,
                "detected_by": detected_by, "contact_hazard": contact_hazard,
                "contact_hazard_rate_per_day": contact_hazard_rate,
                "initiator_organization_id": initiator_organization_id,
                "contact_cause": contact_cause,
                "proximity": proximity, "detection_factor": detection_factor,
                "surprise_information_asymmetry": float(len(detected_by) == 1),
                "information_asymmetry": float(len(detected_by) == 1),
                "disengaged": engagement.disengaged,
                "ineffective": engagement.ineffective,
                "reinforcement_order_ids": engagement.reinforcement_order_ids,
                "observation_ids": tuple(item.observation_id for item in all_observations),
                "observations_by_actor": {
                    g.organization_id: tuple(item.observation_id for item in all_observations
                                             if item.observer_actor_id == g.organization_id),
                    i.organization_id: tuple(item.observation_id for item in all_observations
                                             if item.observer_actor_id == i.organization_id),
                    },
                "severity": min(1.0, sum(engagement.personnel_losses.values()) /
                                max(1.0, g.personnel + i.personnel)),
                "contact_funnel": trace}

    def on_organized_action(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        """Choose one action from beliefs/own capacity, then execute against truth.

        One scheduled event is the shared local personnel/time budget for the
        organization over the interval.  It can produce at most one action
        channel, preventing simultaneous channels from reusing the same local
        capacity.
        """
        organization_id = str(event.payload["organization_id"])
        locality_id = str(event.payload["locality_id"])
        interval_days = max(0.0, float(event.payload.get("interval_days", 1.0)))
        organization = self.world.organizations.get(organization_id)
        base = {
            "locality_id": locality_id,
            "actor_ids": (organization_id,),
            "latent_event": 0.0,
            "state_based_violence_event": 0.0,
            "record_source_type": "organized_action",
        }
        if (
            organization is None
            or organization.kind not in ACTION_ORGANIZATION_KINDS
            or organization.status != "active"
        ):
            return {**base, "action_channel": "wait", "failure_reason": "inactive_organization"}

        support = local_action_support(self.world, organization_id, locality_id)
        if support.total_fighter_equivalents <= 0:
            return {**base, "action_channel": "wait", "failure_reason": "no_local_fighter_capacity"}

        attempt_probability = action_attempt_probability(
            self.world, organization_id, locality_id, interval_days
        )
        attempt_draw = self.rng.random()
        if attempt_draw >= attempt_probability:
            return {
                **base,
                "action_channel": "wait",
                "failure_reason": "no_action_opportunity",
                "attempt_probability": attempt_probability,
                "attempt_draw": attempt_draw,
            }

        channel, choice_weights = choose_action(
            self.world, organization_id, locality_id, self.rng
        )
        common = {
            **base,
            "action_channel": channel,
            "failure_reason": None,
            "attempt_probability": attempt_probability,
            "attempt_draw": attempt_draw,
            "choice_weights": choice_weights,
            "committed_fighter_equivalents": committed_fighter_equivalents(
                self.world, organization_id, locality_id
            ),
            "support": {
                "armed_confrontation": support.armed_confrontation,
                "nonfielded_human_target": support.nonfielded_human_target,
                "asset_violence": support.government_asset_target,
                "coercion": support.civilian_coercion,
                "access_restriction": support.access_restriction,
            },
        }
        if channel == "wait":
            return {**common, "failure_reason": "actor_selected_wait"}

        if channel == "armed_confrontation":
            pairs = available_battle_pairs(self.world, organization_id, locality_id)
            if not pairs:
                return {**common, "failure_reason": "believed_battle_target_absent"}
            actor_formation, target_formation = self.rng.choice(pairs)
            actor_kind = self.world.organizations[actor_formation.organization_id].kind
            target_kind = self.world.organizations[target_formation.organization_id].kind
            # The initiator selected this target family from its beliefs and is
            # therefore aware of the intended target.  Defender awareness is
            # execution-time information and may differ.
            detected_by = (organization_id,)
            defender_beliefs = [
                belief for belief in self.world.presence_beliefs.values()
                if (
                    belief.observer_id == target_formation.organization_id
                    and belief.locality_id == locality_id
                    and belief.evidence_count > 0
                    and belief.presence_estimate >= 0.5
                )
            ]
            if defender_beliefs:
                detected_by = (organization_id, target_formation.organization_id)
            engagement, observations = resolve_engagement(
                self.world,
                event_id,
                actor_formation,
                target_formation,
                detected_by,
                self.world.time,
                self.rng,
                initiator_organization_id=organization_id,
                contact_cause="organized_action_armed_confrontation",
            )
            losses = sum(engagement.personnel_losses.values())
            severity = min(
                1.0,
                losses / max(
                    1.0,
                    actor_formation.personnel + target_formation.personnel,
                ),
            )
            government_losses = 0.0
            insurgent_losses = 0.0
            if (
                actor_kind is OrganizationKind.INSURGENT
                and target_kind is not OrganizationKind.INSURGENT
            ):
                insurgent_losses = -engagement.personnel_losses[
                    actor_formation.formation_id
                ]
                government_losses = -engagement.personnel_losses[
                    target_formation.formation_id
                ]
            elif (
                target_kind is OrganizationKind.INSURGENT
                and actor_kind is not OrganizationKind.INSURGENT
            ):
                insurgent_losses = -engagement.personnel_losses[
                    target_formation.formation_id
                ]
                government_losses = -engagement.personnel_losses[
                    actor_formation.formation_id
                ]
            return {
                **common,
                "actor_ids": (
                    actor_formation.organization_id,
                    target_formation.organization_id,
                ),
                "affected_entity_ids": (
                    actor_formation.formation_id,
                    target_formation.formation_id,
                ),
                "latent_event": 1.0,
                "state_based_violence_event": 1.0,
                "record_event_type": "state_based_violence",
                "target_type": "fielded_armed_formation",
                "target_id": target_formation.formation_id,
                "engagement_id": engagement.engagement_id,
                "government_losses": government_losses,
                "insurgent_losses": insurgent_losses,
                "personnel_losses": {
                    formation_id: -quantity
                    for formation_id, quantity in engagement.personnel_losses.items()
                },
                "civilian_harm": engagement.civilian_harm,
                "observations_by_actor": {
                    actor: tuple(
                        item.observation_id for item in observations
                        if item.observer_actor_id == actor
                    )
                    for actor in {
                        actor_formation.organization_id,
                        target_formation.organization_id,
                    }
                },
                "severity": severity,
            }

        committed = max(
            0.0,
            float(common["committed_fighter_equivalents"]),
        )

        if channel == "nonfielded_human_target":
            targets = nonfielded_human_targets(
                self.world, organization_id, locality_id
            )
            if not targets:
                return {**common, "failure_reason": "believed_human_target_absent"}
            target = self.rng.choices(
                targets,
                weights=[
                    max(1e-9, post.personnel * clamp(post.available_fraction))
                    for post in targets
                ],
                k=1,
            )[0]
            exposed = max(0.0, target.personnel * clamp(target.available_fraction))
            resistance = exposed / max(1e-12, committed + exposed)
            supply_demand = (
                committed
                * self.world.config.combat.supply_per_person_hour
                * self.world.config.combat.interval_hours
            )
            available_supply = local_action_supply_available(
                self.world, organization_id, locality_id
            )
            supply_fraction = (
                min(1.0, available_supply / max(1e-12, supply_demand))
                if supply_demand > 0 else 1.0
            )
            probability = execution_probability(
                self.world, organization_id, locality_id, resistance, supply_fraction
            )
            consumed_supply, unmet_supply = consume_local_action_supply(
                self.world, organization_id, locality_id, supply_demand
            )
            draw = self.rng.random()
            if draw >= probability:
                return {
                    **common,
                    "target_type": target.target_type,
                    "target_id": target.target_id,
                    "execution_probability": probability,
                    "execution_draw": draw,
                    "supply_consumed": consumed_supply,
                    "unmet_supply": unmet_supply,
                    "failure_reason": "execution_failed",
                }
            loss_fraction = min(
                self.world.config.combat.max_loss_fraction,
                self.world.config.combat.base_attrition_rate * (1.0 + probability),
            )
            losses = min(target.personnel, exposed * loss_fraction)
            if losses <= 0:
                return {**common, "failure_reason": "no_exposed_target_personnel"}
            realized_losses = apply_nonfielded_target_losses(
                self.world, target, losses
            )
            if realized_losses <= 0:
                return {**common, "failure_reason": "target_stock_changed_before_execution"}
            intensity = min(1.0, realized_losses / max(1.0, exposed))
            locality = self.world.localities[locality_id]
            locality.violence = clamp(locality.violence * .85 + .25 * intensity)
            record_relation_harm(
                self.world,
                organization_id,
                target.organization_id,
                intensity,
                self.world.time,
            )
            return {
                **common,
                "affected_entity_ids": (target.target_id,),
                "latent_event": 1.0,
                "state_based_violence_event": 1.0,
                "record_event_type": "state_based_violence",
                "target_type": target.target_type,
                "target_id": target.target_id,
                "execution_probability": probability,
                "execution_draw": draw,
                "supply_consumed": consumed_supply,
                "unmet_supply": unmet_supply,
                "target_personnel_losses": -realized_losses,
                "severity": intensity,
            }

        if channel == "asset_violence":
            targets = asset_targets(self.world, organization_id, locality_id)
            if not targets:
                return {**common, "failure_reason": "believed_asset_target_absent"}
            target = self.rng.choices(
                targets,
                weights=[
                    max(1e-9, institution.capacity * institution.reach)
                    for institution in targets
                ],
                k=1,
            )[0]
            hardness = clamp((target.capacity + target.integrity + target.reach) / 3.0)
            supply_demand = (
                committed
                * self.world.config.combat.supply_per_person_hour
                * self.world.config.combat.interval_hours
            )
            available_supply = local_action_supply_available(
                self.world, organization_id, locality_id
            )
            supply_fraction = (
                min(1.0, available_supply / max(1e-12, supply_demand))
                if supply_demand > 0 else 1.0
            )
            probability = execution_probability(
                self.world, organization_id, locality_id, hardness, supply_fraction
            )
            consumed_supply, unmet_supply = consume_local_action_supply(
                self.world, organization_id, locality_id, supply_demand
            )
            draw = self.rng.random()
            if draw >= probability:
                return {
                    **common,
                    "target_type": "political_institution",
                    "target_id": target.institution_id,
                    "execution_probability": probability,
                    "execution_draw": draw,
                    "supply_consumed": consumed_supply,
                    "unmet_supply": unmet_supply,
                    "failure_reason": "execution_failed",
                }
            damage = clamp(self.world.config.combat.base_attrition_rate * probability)
            target.capacity = clamp(target.capacity * (1.0 - damage))
            target.integrity = clamp(target.integrity * (1.0 - damage))
            target.reach = clamp(target.reach * (1.0 - damage))
            locality = self.world.localities[locality_id]
            locality.violence = clamp(locality.violence * .85 + .25 * damage)
            return {
                **common,
                "affected_entity_ids": (target.institution_id,),
                "latent_event": 1.0,
                "state_based_violence_event": 0.0,
                "record_event_type": "asset_violence",
                "target_type": "political_institution",
                "target_id": target.institution_id,
                "execution_probability": probability,
                "execution_draw": draw,
                "supply_consumed": consumed_supply,
                "unmet_supply": unmet_supply,
                "institutional_damage": damage,
                "severity": damage,
            }

        if channel == "coercion":
            if self.world.localities[locality_id].population <= 0:
                return {**common, "failure_reason": "no_susceptible_population"}
            # Compliance is a substantive outcome but is not allowed to create
            # fiscal resources until a separate stock-flow mechanism is
            # independently justified.  This prevents a new event channel
            # from inventing material capacity.
            embedded = clamp(organization.phenotype.get("local_embeddedness", 0.5))
            social = clamp(organization.capital.get("social", 0.0))
            capacity = clamp(
                committed / max(
                    1e-12,
                    committed
                    + self.world.config.organization_ecology.minimum_formation_personnel,
                )
            )
            probability = clamp((max(1e-12, embedded * social * capacity)) ** (1.0 / 3.0))
            complied = self.rng.random() < probability
            return {
                **common,
                "latent_event": 1.0,
                "state_based_violence_event": 0.0,
                "record_event_type": "nonviolent_coercion",
                "target_type": "civilian_population",
                "compliance_probability": probability,
                "complied": bool(complied),
                "severity": probability if complied else 0.0,
            }

        if channel == "access_restriction":
            candidates = sorted(self.world.adjacency.get(locality_id, {}))
            if not candidates:
                return {**common, "failure_reason": "no_adjacent_corridor"}
            target_side = (
                "government"
                if organization.kind is OrganizationKind.INSURGENT
                else "insurgent"
            )
            weights = []
            for destination in candidates:
                belief = self.world.belief_view(
                    organization_id
                ).locality_control(destination, target_side)
                strategic = clamp(
                    (belief.physical + belief.expected + belief.fiscal) / 3.0
                )
                weights.append(
                    exp(max(
                        -8.0,
                        min(
                            8.0,
                            strategic
                            - self.world.adjacency[locality_id][destination],
                        ),
                    ))
                )
            destination = self.rng.choices(
                candidates, weights=weights, k=1
            )[0]
            capacity = clamp(
                committed
                / max(
                    1e-12,
                    committed
                    + self.world.config.organization_ecology.minimum_formation_personnel,
                )
            )
            supply_demand = (
                committed
                * self.world.config.logistics.presence_consumption_per_person_day
                * max(interval_days, 1e-9)
            )
            consumed_supply, unmet_supply = consume_local_action_supply(
                self.world, organization_id, locality_id, supply_demand
            )
            supply_fraction = (
                consumed_supply / max(1e-12, supply_demand)
                if supply_demand > 0 else 1.0
            )
            effort = capacity * clamp(supply_fraction)
            if effort <= 0:
                return {
                    **common,
                    "target_type": "locality_corridor",
                    "target_id": destination,
                    "supply_consumed": consumed_supply,
                    "unmet_supply": unmet_supply,
                    "failure_reason": "insufficient_access_effort",
                }
            restriction = build_access_restriction(
                self.world,
                organization_id,
                locality_id,
                destination,
                effort,
                self.world.time,
            )
            return {
                **common,
                "affected_entity_ids": (
                    f"{restriction.locality_a_id}|{restriction.locality_b_id}",
                ),
                "latent_event": 1.0,
                "state_based_violence_event": 0.0,
                "record_event_type": "access_restriction",
                "target_type": "locality_corridor",
                "target_id": destination,
                "access_level": restriction.level,
                "access_effort": effort,
                "supply_consumed": consumed_supply,
                "unmet_supply": unmet_supply,
                "severity": restriction.level,
            }

        return {**common, "failure_reason": "unsupported_action_channel"}

    def on_checkpoint(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        self.world.assert_invariants()
        self.world.checkpoint()
        return {"checkpoint": 1.0}
