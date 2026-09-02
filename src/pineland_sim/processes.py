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
from .networks import edge_between, refresh_community_aggregates
from .physical import record_presence, recompute_microzone_control
from .logistics import (
    advance_movement_orders,
    choose_reallocation_orders,
    consume_formation_supply,
    update_logistics,
)
from .world import WorldState, seeded_rng


class ProcessEngine:
    """State transitions. Every control mutation is mirrored in the causal ledger."""

    def __init__(self, world: WorldState, rng: random.Random | None = None) -> None:
        self.world = world
        self._injected_rng = rng
        self._process_rngs: dict[str, random.Random] = {}
        self.rng = rng or seeded_rng(world.config, "process-default")
        self.event_counter = 0

    def execute(self, event: ScheduledEvent) -> str:
        self.event_counter += 1
        event_id = f"E{self.event_counter:010d}"
        handler = getattr(self, f"on_{event.event_type}", None)
        if handler is None:
            raise KeyError(f"no process handler for {event.event_type}")
        if self._injected_rng is None:
            self.rng = self._process_rngs.setdefault(
                event.event_type, seeded_rng(self.world.config, f"process:{event.event_type}")
            )
        result = handler(event_id, event) or {}
        locality_id = result.pop("locality_id", event.payload.get("locality_id"))
        actors = tuple(result.pop("actor_ids", ()))
        affected = tuple(result.pop("affected_entity_ids", ()))
        observations = result.pop("observations_by_actor", {})
        severity = float(result.pop("severity", sum(abs(v) for v in result.values() if isinstance(v, (int, float)))))
        synthetic = self._synthetic_record(event_id, event.event_type, locality_id, severity, actors[0] if actors else None)
        log_entry = EventLogEntry(
            event_id, event.time, event.event_type, locality_id, actors, affected, result,
            event.causal_parent_ids, observations, synthetic,
            f"{self.world.config.random_stream_namespace}:process:{event.event_type}", "v0.1-defaults",
        )
        self.world.event_log.append(log_entry)
        self.world.synthetic_records.append(synthetic)
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

    def _synthetic_record(self, event_id: str, event_type: str, locality_id: str | None,
                          severity: float, actor: str | None) -> SyntheticRecord:
        if locality_id is None:
            access = .5
            remoteness = .5
        else:
            locality = self.world.localities[locality_id]
            access = locality.observability
            remoteness = clamp(locality.terrain_friction / 2.5)
        probability = logistic(-1.5 + 1.8 * min(1, severity) + 1.2 * access - .9 * remoteness)
        recorded = self.rng.random() < probability
        error = self.world.config.reporting_error
        return SyntheticRecord(event_id, self.world.time, locality_id, event_type, recorded,
                               max(0, severity * self.rng.uniform(1 - error, 1 + error)), actor,
                               recorded and self.rng.random() < error)

    def on_patrol(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        patrol_id = event.payload["patrol_id"]
        patrol = self.world.patrols.get(patrol_id)
        if patrol is None:
            return {"affected_entity_ids": (patrol_id,)}
        formation = self.world.formations.get(patrol.formation_id)
        if formation is None or formation.personnel <= 0:
            return {"affected_entity_ids": (patrol_id, patrol.formation_id)}
        if formation.moving:
            event.payload["next_interval"] = self.world.config.intervals.patrol
            return {"locality_id": formation.locality_id,
                    "actor_ids": (formation.organization_id,),
                    "affected_entity_ids": (patrol_id, formation.formation_id),
                    "unavailable_in_transit": 1.0}
        locality = self.world.localities[patrol.locality_id]
        current_zone = self.world.microzones[patrol.current_microzone_id]
        actual_control = current_zone.physical_control.get("government", 0.0)
        belief = self.world.zone_beliefs[(formation.organization_id, current_zone.microzone_id)]
        observed = clamp(actual_control + self.rng.normalvariate(
            0, self.world.config.physical.zone_observation_noise * (1 - current_zone.observability)
        ))
        alpha = .25 + .35 * current_zone.observability
        belief.physical_control_estimate = clamp(
            belief.physical_control_estimate + alpha * (observed - belief.physical_control_estimate)
        )
        belief.confidence = clamp(belief.confidence + .08 * current_zone.observability)
        belief.updated_at = self.world.time
        presence = (self.world.config.physical.patrol_presence_gain * formation.effective_strength() /
                    max(250.0, locality.population * .002))
        record_presence(self.world, current_zone.microzone_id, "government", presence, self.world.time)

        candidates = sorted(self.world.physical_neighbors[current_zone.microzone_id])
        moved_to = current_zone.microzone_id
        travel_hours = self.world.config.intervals.patrol * 24
        if candidates:
            weights = []
            for candidate in candidates:
                zone_belief = self.world.zone_beliefs[(formation.organization_id, candidate)]
                edge = self.world.physical_edges[self.world.physical_neighbors[current_zone.microzone_id][candidate]]
                perceived_need = 1 - zone_belief.physical_control_estimate
                route_noise = self.rng.uniform(0, self.world.config.physical.patrol_route_randomness)
                score = 2.5 * perceived_need - edge.travel_time_hours / self.world.config.physical.response_decay_hours + route_noise
                weights.append(exp(max(-8, min(8, score))))
            moved_to = self.rng.choices(candidates, weights=weights, k=1)[0]
            edge = self.world.physical_edges[self.world.physical_neighbors[current_zone.microzone_id][moved_to]]
            travel_hours = edge.travel_time_hours * (1 + edge.disruption) / max(.2, formation.mobility)
            patrol.current_microzone_id = moved_to
            patrol.route_history.append(moved_to)
            patrol.available_at = self.world.time + travel_hours / 24
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
                "to_microzone": moved_to, "travel_time_hours": travel_hours, "severity": presence}

    def on_command(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        orders = choose_reallocation_orders(self.world, self.world.time, self.rng)
        return {"orders_issued": len(orders),
                "orders_failed": sum(order.status == "failed_command" for order in orders),
                "affected_entity_ids": tuple(order.order_id for order in orders)}

    def on_force_movement(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        return advance_movement_orders(self.world, self.world.time)

    def on_logistics(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        return update_logistics(self.world, self.world.time, event.payload["interval"])

    def on_physical_refresh(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        changed = 0
        total = 0.0
        for locality_id in sorted(self.world.localities):
            aggregate = recompute_microzone_control(
                self.world, locality_id, "government", self.world.time
            )
            before = self.world.localities[locality_id].control["government"].physical
            formations = [formation for formation in self.world.formations.values()
                          if formation.locality_id == locality_id and formation.organization_id != "insurgent"]
            reallocated = any(
                post.locality_id == locality_id and post.formation_id and
                (self.world.formations[post.formation_id].moving or
                 self.world.formations[post.formation_id].locality_id != locality_id)
                for post in self.world.security_posts.values()
            )
            constrained = any(formation.moving or formation.supply_fraction() < .4 or
                              formation.command < .5 or formation.availability < .5
                              for formation in formations)
            mechanism = ("force_projection_reallocation" if reallocated else
                         "logistics_constrained_physical_aggregation" if constrained else
                         "microzone_physical_aggregation")
            self._set_control_dimension(
                event_id, locality_id, "government", "physical", aggregate,
                mechanism,
            )
            changed += aggregate != before
            total += aggregate
        return {"localities_changed": changed,
                "mean_physical_control": total / max(1, len(self.world.localities))}

    def on_governance(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        total = 0.0
        government = self.world.organizations["government"]
        for locality in self.world.localities.values():
            capacity = locality.administrative_capacity
            leakage = locality.governance["leakage"]
            allocation = min(government.resources / max(1, len(self.world.localities)), locality.economic_output * .01)
            production = min(allocation / max(1, locality.economic_output * .01), capacity) * (1 - leakage)
            cost = allocation * .02
            government.resources = max(0, government.resources - cost)
            total += production
            self._control(event_id, locality.locality_id, "government", "governance",
                          administrative=.006 * production, legal=.004 * production,
                          fiscal=.003 * production, social=.003 * production, expected=.002 * production)
        return {"actor_ids": ("government",), "governance_production": total}

    def on_economy(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        net = 0.0
        revenue = 0.0
        government = self.world.organizations["government"]
        insurgent = self.world.organizations.get("insurgent")
        for locality in self.world.localities.values():
            security = locality.control["government"].physical
            production = locality.economic_output * (.002 + .004 * locality.infrastructure) * (0.5 + .5 * security)
            damage = locality.economic_output * (.003 * locality.violence + .002 * locality.disruption)
            depreciation = locality.economic_output * .001
            delta = production - damage - depreciation
            locality.economic_output = max(1, locality.economic_output + delta)
            net += delta
            tax = locality.economic_output * .0005 * locality.control["government"].fiscal
            government.resources += tax
            revenue += tax
            if insurgent:
                extraction = locality.economic_output * .00015 * locality.control["insurgent"].fiscal
                insurgent.resources += extraction + insurgent.external_support / 12
        return {"actor_ids": tuple(x for x in ("government", "insurgent") if x in self.world.organizations),
                "net_output": net, "government_revenue": revenue}

    def on_mobility(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        moved = 0.0
        displaced = 0.0
        rate = self.world.config.movement_rate
        displaced_by_locality = {locality_id: 0.0 for locality_id in self.world.localities}
        for person in self.world.persons.values():
            if self.rng.random() >= rate:
                continue
            origin = person.residence_locality_id
            neighbors = self.world.adjacency[origin]
            if not neighbors:
                continue
            candidates = list(neighbors)
            utilities = []
            for destination in candidates:
                locality = self.world.localities[destination]
                security = person.expected_control.get("government", .5) * locality.control["government"].physical
                livelihood = log(max(2, locality.economic_output / max(1, locality.population)))
                utilities.append(exp(max(-10, min(10, 1.2 * security + .1 * livelihood - neighbors[destination]))))
            destination = self.rng.choices(candidates, weights=utilities, k=1)[0]
            origin_locality = self.world.localities[origin]
            forced = origin_locality.violence > .35 and self.rng.random() < origin_locality.violence
            if forced or self.rng.random() < .08:
                person.residence_locality_id = destination
                person.displaced = forced and destination != person.home_locality_id
                moved += person.weight
                displaced += person.weight if person.displaced else 0
            if person.displaced:
                displaced_by_locality[person.residence_locality_id] += person.weight
        for locality_id, population in displaced_by_locality.items():
            self.world.localities[locality_id].displaced_population = population
        return {"affected_entity_ids": (), "moved_population": moved, "new_displaced_population": displaced}

    def on_beliefs(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        updates = 0
        error_total = 0.0
        noise = self.world.config.observation_noise
        for (actor_id, locality_id), belief in self.world.beliefs.items():
            truth_actor = "insurgent" if actor_id == "insurgent" else "government"
            truth = self.world.localities[locality_id].control[truth_actor]
            organization = self.world.organizations[actor_id]
            access = clamp(.25 + .5 * organization.local_knowledge)
            alpha = .08 + .25 * access
            for dimension, true_value in truth.to_dict().items():
                observed = clamp(true_value + self.rng.normalvariate(0, noise * (1.1 - access)))
                old = getattr(belief.control_estimate, dimension)
                setattr(belief.control_estimate, dimension, clamp(old + alpha * (observed - old)))
                error_total += abs(getattr(belief.control_estimate, dimension) - true_value)
                updates += 1
            belief.confidence = clamp(belief.confidence + .01 * access)
            belief.updated_at = self.world.time
        # Civilian expected control updates through trusted, imperfect local observations.
        perceived_actors = ["government"]
        if "insurgent" in self.world.organizations:
            perceived_actors.append("insurgent")
        for person in self.world.persons.values():
            locality = self.world.localities[person.residence_locality_id]
            for actor in perceived_actors:
                observed = clamp(locality.control[actor].expected + self.rng.normalvariate(0, noise))
                trust = person.trust.get(actor, .2)
                old = person.expected_control.get(actor, .2)
                person.expected_control[actor] = clamp(old + .12 * trust * (observed - old))
        return {"belief_updates": updates, "mean_absolute_error": error_total / max(1, updates)}

    def on_social_influence(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        """Translate explicit neighbor signals into exposure and observable behavior."""
        rng = self.rng
        behavior_changes = 0
        locality_government_shift: dict[str, float] = {}
        locality_insurgent_shift: dict[str, float] = {}
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
        insurgent_available = "insurgent" in self.world.organizations
        for person_id in sorted(self.world.persons):
            person = self.world.persons[person_id]
            neighbors = self.world.social_neighbors.get(person_id, ())
            government_signal = 0.0
            insurgent_signal = 0.0
            total_weight = 0.0
            for neighbor_id in neighbors:
                neighbor = self.world.persons[neighbor_id]
                edge = edge_between(self.world, person_id, neighbor_id)
                # Edge weight already contains language attenuation. Multiplicity
                # makes unequal representative weights explicit; normalization
                # below prevents agent resolution from becoming raw influence.
                influence = edge.weight * edge.trust * edge.represented_relationships
                neighbor_government, neighbor_insurgent = behavior_score.get(neighbor.public_behavior, (0.0, 0.0))
                if neighbor.organization_id == "insurgent":
                    neighbor_insurgent = max(1.0, neighbor_insurgent)
                if not insurgent_available:
                    neighbor_insurgent = 0.0
                government_signal += influence * max(0.0, neighbor_government)
                insurgent_signal += influence * neighbor_insurgent
                total_weight += influence
            if total_weight:
                government_signal /= total_weight
                insurgent_signal /= total_weight
            person.social_exposure = {"government": clamp(government_signal),
                                      "insurgent": clamp(insurgent_signal)}
            if rng.random() >= self.world.config.social_network.behavior_update_rate:
                continue
            party_affinity = max(person.private_preference.values(), default=.5)
            expected_government = person.expected_control.get("government", .5)
            expected_insurgent = person.expected_control.get("insurgent", .1)
            utilities = {
                "inactive": .7 + person.fear - person.efficacy,
                "government_cooperation": (party_affinity + expected_government +
                                           self.world.config.social_network.behavior_exposure_weight * government_signal -
                                           person.grievance - .4 * person.fear),
                "party_participation": party_affinity + person.efficacy - .5 * person.fear,
                "civil_society": .5 + person.efficacy - .3 * person.fear,
                "protest": 1.2 * person.grievance + person.efficacy - person.fear,
                "insurgent_sympathy": (1.2 * person.grievance + expected_insurgent +
                                       self.world.config.social_network.behavior_exposure_weight * insurgent_signal - person.fear),
                "armed_participation": ((1.5 if person.organization_id == "insurgent" else -1.5) +
                                        person.grievance +
                                        self.world.config.social_network.behavior_exposure_weight * insurgent_signal - person.fear),
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
            behavior_changes += 1

        for locality_id in set(locality_government_shift) | set(locality_insurgent_shift):
            population = max(1, self.world.localities[locality_id].population)
            government_delta = .01 * locality_government_shift.get(locality_id, 0.0) / population
            insurgent_delta = .01 * locality_insurgent_shift.get(locality_id, 0.0) / population
            self._control(event_id, locality_id, "government", "social_network_influence", social=government_delta)
            if insurgent_available:
                self._control(event_id, locality_id, "insurgent", "social_network_influence", social=insurgent_delta)
        refresh_community_aggregates(self.world)
        return {"behavior_changes": behavior_changes,
                "mean_degree": 2 * len(self.world.social_edges) / max(1, len(self.world.persons)),
                "affected_localities": len(set(locality_government_shift) | set(locality_insurgent_shift))}

    def on_recruitment(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        insurgent = self.world.organizations.get("insurgent")
        if insurgent is None:
            return {"recruits": 0.0, "exits": 0.0}
        recruits = 0.0
        exits = 0.0
        rate = self.world.config.recruitment_rate
        for person in self.world.persons.values():
            if person.organization_id is None:
                network = min(1, len(insurgent.member_ids) / max(1, len(self.world.persons)) * 15)
                explicit_exposure = person.social_exposure.get("insurgent", 0.0)
                recruitment_capability = clamp(.35 + .35 * insurgent.cohesion + .3 * min(1, insurgent.resources / 100_000))
                utility = (2 * person.grievance + person.expected_control.get("insurgent", .1) +
                           network + self.world.config.social_network.recruitment_exposure_weight * explicit_exposure +
                           recruitment_capability - person.fear - 2.4)
                if self.rng.random() < rate * logistic(utility):
                    person.organization_id = "insurgent"
                    insurgent.member_ids.add(person.person_id)
                    recruits += person.weight
            elif person.organization_id == "insurgent":
                exit_probability = rate * logistic(person.fear + .7 - insurgent.cohesion - person.grievance)
                if self.rng.random() < exit_probability:
                    person.organization_id = None
                    insurgent.member_ids.discard(person.person_id)
                    exits += person.weight
        if "PRF-01" in self.world.formations:
            formation = self.world.formations["PRF-01"]
            formation.personnel = max(0, formation.personnel + recruits - exits)
        return {"actor_ids": ("insurgent",), "recruits": recruits, "exits": exits}

    def on_contact(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        locality_id = event.payload["locality_id"]
        local = [f for f in self.world.formations.values()
                 if f.locality_id == locality_id and f.personnel > 0 and not f.moving]
        government = [f for f in local if self.world.organizations[f.organization_id].kind in {OrganizationKind.MILITARY, OrganizationKind.POLICE}]
        insurgents = [f for f in local if self.world.organizations[f.organization_id].kind is OrganizationKind.INSURGENT]
        if not government or not insurgents:
            return {"locality_id": locality_id, "contact": 0.0}
        g = max(government, key=lambda f: f.effective_strength())
        i = max(insurgents, key=lambda f: f.effective_strength())
        locality = self.world.localities[locality_id]
        detection = logistic(-2 + 1.2 * g.information + locality.observability + g.embeddedness - i.embeddedness)
        if self.rng.random() >= detection * self.world.config.contact_rate:
            return {"locality_id": locality_id, "actor_ids": (g.organization_id, i.organization_id), "contact": 0.0}
        advantage = log(g.effective_strength()) - log(i.effective_strength()) + self.rng.normalvariate(0, .35)
        government_wins = self.rng.random() < logistic(advantage)
        intensity = min(.08, .005 + self.rng.expovariate(45))
        g_loss = g.personnel * intensity * (.55 if government_wins else 1.0)
        i_loss = i.personnel * intensity * (1.0 if government_wins else .55)
        g.personnel = max(0, g.personnel - g_loss)
        i.personnel = max(0, i.personnel - i_loss)
        g.readiness = clamp(g.readiness - intensity * .7)
        i.readiness = clamp(i.readiness - intensity * .7)
        locality.violence = clamp(locality.violence * .85 + intensity * 3)
        shift = intensity * (.8 if government_wins else -.8)
        # Phase 2 physical control is generated only by microzone occupation.
        # Coarse combat retains perception/social effects until combat is given
        # an explicit microzone location in a later phase.
        self._control(event_id, locality_id, "government", "combat", expected=shift * .6, social=-abs(shift) * .1)
        self._control(event_id, locality_id, "insurgent", "combat", expected=-shift * .6)
        return {"locality_id": locality_id, "actor_ids": (g.organization_id, i.organization_id),
                "affected_entity_ids": (g.formation_id, i.formation_id), "contact": 1.0,
                "government_losses": -g_loss, "insurgent_losses": -i_loss, "control_shift": shift,
                "severity": intensity * 10}

    def on_checkpoint(self, event_id: str, event: ScheduledEvent) -> dict[str, Any]:
        self.world.assert_invariants()
        self.world.checkpoint()
        return {"checkpoint": 1.0}
