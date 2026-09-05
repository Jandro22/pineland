"""Spatial, stochastic armed engagements built on prior-phase state.

Combat changes formations, stocks, local violence, and perceived momentum.  It
never writes physical control: the physical model observes the resulting force
availability and derives control on its normal refresh.
"""
from __future__ import annotations

from math import exp, log
import random

from .entities import (ArmedFormation, CausalContribution, Engagement, Observation,
                       OrganizationKind, clamp, logistic)
from .information import get_presence_belief, ingest_observation
from .logistics import choose_withdrawal_order, consume_formation_supply, create_movement_order


def formation_microzone(world, formation: ArmedFormation) -> str:
    if formation.current_microzone_id in world.microzones:
        zone = world.microzones[formation.current_microzone_id]
        if zone.locality_id == formation.locality_id:
            return zone.microzone_id
    patrol = next((p for p in world.patrols.values()
                   if p.formation_id == formation.formation_id and p.locality_id == formation.locality_id), None)
    if patrol is not None:
        return patrol.current_microzone_id
    post = next((p for p in world.security_posts.values()
                 if p.formation_id == formation.formation_id and p.locality_id == formation.locality_id), None)
    if post is not None:
        return post.microzone_id
    zones = sorted((z for z in world.microzones.values() if z.locality_id == formation.locality_id),
                   key=lambda z: (-z.population_share, z.microzone_id))
    return zones[0].microzone_id


def operational_effectiveness(formation: ArmedFormation) -> float:
    return (formation.personnel * formation.availability * formation.quality *
            formation.cohesion * formation.effective_readiness())


def _capability(formation: ArmedFormation, zone, initiative: float) -> float:
    # Terrain operates through exposure, mobility/coherence, and observation;
    # there is deliberately no faction-specific terrain bonus.
    mobility = clamp(formation.mobility / max(.35, zone.terrain_friction), .15, 1.0)
    observation = .35 + .65 * zone.observability
    embedded = .55 + .45 * formation.embeddedness
    return max(1e-9, (max(0.0, formation.available_personnel()) ** .72) *
               formation.quality * max(.05, formation.cohesion) *
               observation *
               (mobility ** .35) * embedded * initiative)


def _event_observation(world, observer: ArmedFormation, target: ArmedFormation,
                       engagement_id: str, microzone_id: str, time: float,
                       signal: float, civilian_harm: float, rng: random.Random) -> Observation:
    oid = f"OBS{world.next_observation_sequence:010d}"
    world.next_observation_sequence += 1
    noise = world.config.reporting_error
    perceived = clamp(signal + rng.normalvariate(0, noise))
    attributed_actor = (observer.organization_id
                         if rng.random() < world.config.information.attribution_error_rate
                         else target.organization_id)
    observation = Observation(
        oid, engagement_id, observer.locality_id, time,
        f"ENGAGEMENT:{engagement_id}", "contact", "engagement_outcome",
        {"momentum": perceived, "civilian_harm": max(0.0, civilian_harm *
         rng.uniform(1 - noise, 1 + noise)),
         "attributed_actor": attributed_actor},
        .84, {"mechanism": "armed_contact", "reported": True},
        observer.organization_id, microzone_id, observer.formation_id, .9, .18,
        target.organization_id, target.formation_id, time,
    )
    world.observations[oid] = observation
    world.observation_index.setdefault((target.organization_id, observer.locality_id,
                                        "engagement_outcome"), []).append(time)
    ingest_observation(world, observation, time)
    return observation


def _update_perceived_momentum(world, locality_id: str, signal: float,
                               civilian_harm: float, rng: random.Random) -> int:
    config = world.config.combat
    changed = 0
    locality = world.localities[locality_id]
    harm_scale = civilian_harm / max(1.0, locality.population * .001)
    for person in world.persons.values():
        if person.residence_locality_id != locality_id:
            continue
        reach = clamp(.15 + .55 * locality.observability + .3 * person.efficacy)
        if rng.random() > reach:
            continue
        interpretation = clamp(signal + rng.normalvariate(0, world.config.reporting_error))
        # Harm has a political effect only here, after noisy observation and
        # attribution. Discipline reduces attribution to the observer's side.
        government = world.organizations.get("government")
        attribution = harm_scale * (1 - (government.discipline if government else .5))
        old = person.expected_control.get("government", .5)
        person.expected_control["government"] = clamp(
            old + config.momentum_learning_rate * (interpretation - .5) - .04 * attribution
        )
        if any(org.kind is OrganizationKind.INSURGENT and org.status == "active"
               for org in world.organizations.values()):
            old_i = person.expected_control.get("insurgent", .1)
            person.expected_control["insurgent"] = clamp(
                old_i + config.momentum_learning_rate * (.5 - interpretation) + .02 * attribution
            )
        changed += 1
    return changed


def _reinforcement(world, formation: ArmedFormation, opponent: ArmedFormation,
                   loss_fraction: float, time: float, rng: random.Random):
    if loss_fraction < world.config.combat.reinforcement_threshold:
        return None
    candidates = [f for f in world.formations.values()
                   if f.organization_id == formation.organization_id and
                   f.formation_id != formation.formation_id and not f.moving and
                   not f.outside_pineland and f.personnel > 0 and
                   f.deployable_personnel() > 0 and
                   f.locality_id != formation.locality_id and
                   f.operational_status == "effective"]
    if not candidates:
        return None
    candidate = max(candidates, key=operational_effectiveness)
    return create_movement_order(
        world, candidate.formation_id, formation.locality_id, time, rng,
        purpose="reinforcement",
    )


def _perceived_disadvantage(world, observer: ArmedFormation, opponent: ArmedFormation,
                            microzone_id: str, own_personnel_reference: float) -> float:
    """Actor-local estimate of relative manpower for disengagement.

    Contact observations are fused first at the observing formation's command
    node.  Disengagement may consume that estimate, but never the opponent's
    realized personnel/quality/cohesion/readiness.  With no quantitative
    estimate the formation uses a neutral parity prior after directly
    experiencing contact.
    """
    candidates = (
        get_presence_belief(
            world, observer.formation_id, opponent.organization_id,
            observer.locality_id, opponent.formation_id, microzone_id, node=True,
        ),
        get_presence_belief(
            world, observer.formation_id, opponent.organization_id,
            observer.locality_id, None, microzone_id, node=True,
        ),
        get_presence_belief(
            world, observer.organization_id, opponent.organization_id,
            observer.locality_id, opponent.formation_id, microzone_id,
        ),
        get_presence_belief(
            world, observer.organization_id, opponent.organization_id,
            observer.locality_id, None, microzone_id,
        ),
    )
    estimated_personnel = None
    for belief in candidates:
        if (belief is not None and belief.evidence_count > 0 and
                belief.personnel_estimate > 0):
            estimated_personnel = belief.personnel_estimate
            break
    own_reference = max(1.0, own_personnel_reference)
    if estimated_personnel is None:
        estimated_personnel = own_reference
    return max(-3.0, min(3.0, log(max(1.0, estimated_personnel) / own_reference)))


def resolve_engagement(world, event_id: str, a: ArmedFormation, b: ArmedFormation,
                       detected_by: tuple[str, ...], time: float,
                       rng: random.Random, *, initiator_organization_id: str | None = None,
                       contact_cause: str = "unspecified") -> tuple[Engagement, tuple[Observation, ...]]:
    cfg = world.config.combat
    for formation in (a, b):
        if (formation.operational_status != "effective" or formation.personnel <= 0 or
                formation.moving or formation.outside_pineland):
            raise ValueError(
                f"combat-ineligible formation: {formation.formation_id} "
                f"status={formation.operational_status} "
                f"personnel={formation.personnel:.6f} moving={formation.moving} "
                f"outside_pineland={formation.outside_pineland} "
                f"effective_readiness={formation.effective_readiness():.6f}"
            )
    if a.locality_id != b.locality_id:
        raise ValueError("combat-ineligible formations are not in the same locality")
    zone_id = formation_microzone(world, a)
    if formation_microzone(world, b) != zone_id:
        raise ValueError("combat-ineligible formations are not in the same microzone")
    zone = world.microzones[zone_id]
    aware_a = a.organization_id in detected_by
    aware_b = b.organization_id in detected_by
    initiative_a = 1 + (cfg.surprise_initiative if aware_a and not aware_b else 0)
    initiative_b = 1 + (cfg.surprise_initiative if aware_b and not aware_a else 0)
    cap_a = _capability(a, zone, initiative_a)
    cap_b = _capability(b, zone, initiative_b)
    advantage = log(cap_a) - log(cap_b)

    # Exposure rises in observable, accessible terrain. Lognormal noise yields
    # outcome distributions while relative capability shifts their center.
    exposure = clamp(zone.observability / max(.55, zone.terrain_friction), .2, 1.35)
    frac_a = cfg.base_attrition_rate * exposure * exp(-.45 * advantage + rng.normalvariate(0, cfg.stochastic_sigma))
    frac_b = cfg.base_attrition_rate * exposure * exp(.45 * advantage + rng.normalvariate(0, cfg.stochastic_sigma))
    frac_a = min(cfg.max_loss_fraction, frac_a)
    frac_b = min(cfg.max_loss_fraction, frac_b)
    # Availability constrains what a formation can put into the fight, not
    # whether its assigned personnel can be struck.  Applying availability a
    # second time to casualties would perversely make an unready/resting target
    # safer from an involuntary attack.
    losses = {
        a.formation_id: min(a.personnel, a.personnel * frac_a),
        b.formation_id: min(b.personnel, b.personnel * frac_b),
    }

    before_cohesion = {a.formation_id: a.cohesion, b.formation_id: b.cohesion}
    before_readiness = {a.formation_id: a.readiness, b.formation_id: b.readiness}
    supply_used: dict[str, float] = {}
    disengaged: list[str] = []
    ineffective: list[str] = []
    for formation, opponent in ((a, b), (b, a)):
        formation.personnel -= losses[formation.formation_id]
        formation.cumulative_losses += losses[formation.formation_id]
        realized_fraction = losses[formation.formation_id] / max(
            1e-12, formation.personnel + losses[formation.formation_id]
        )
        cohesion_loss = cfg.cohesion_loss_multiplier * realized_fraction * (1.25 - formation.quality)
        formation.cohesion = clamp(formation.cohesion - cohesion_loss)
        formation.readiness = clamp(
            formation.readiness - cfg.readiness_cost_multiplier * realized_fraction
        )
        demand = (max(0.0, formation.personnel) * clamp(formation.availability) *
                  cfg.interval_hours *
                  cfg.supply_per_person_hour * (.7 + .3 * exposure))
        consumed, shortfall = consume_formation_supply(
            world, formation.formation_id, demand, "combat_expenditure", formation.locality_id, time)
        supply_used[formation.formation_id] = consumed
        if shortfall:
            formation.readiness = clamp(formation.readiness - .08 * shortfall / max(1.0, demand))
            formation.cohesion = clamp(formation.cohesion - .04 * shortfall / max(1.0, demand))
        own_personnel_reference = max(
            1.0, (formation.personnel + losses[formation.formation_id]) *
            clamp(formation.availability)
        )
        perceived_disadvantage = _perceived_disadvantage(
            world, formation, opponent, zone_id, own_personnel_reference
        )
        # Command is already part of effective readiness. Adding it again here
        # double-counted command connectivity in the disengagement decision.
        remain = logistic(1.1 * formation.cohesion + formation.effective_readiness() -
                          2.1 * realized_fraction - perceived_disadvantage)
        if rng.random() < cfg.disengagement_base + (1 - remain) * .55:
            disengaged.append(formation.formation_id)
            formation.availability = clamp(formation.availability - .12)
        if (formation.personnel <= 0 or formation.cohesion <= cfg.ineffective_cohesion or
                formation.effective_readiness() <= cfg.ineffective_readiness):
            formation.operational_status = "ineffective"
            formation.availability = min(formation.availability, .08)
            ineffective.append(formation.formation_id)
        world.causal_ledger.extend((
            CausalContribution(time, formation.locality_id, "formation_personnel",
                               -losses[formation.formation_id], "combat", event_id),
            CausalContribution(time, formation.locality_id, "formation_cohesion",
                               formation.cohesion - before_cohesion[formation.formation_id],
                               "combat", event_id),
            CausalContribution(time, formation.locality_id, "formation_readiness",
                               formation.readiness - before_readiness[formation.formation_id],
                               "combat", event_id),
        ))

    locality = world.localities[a.locality_id]
    intensity = min(1.0, (frac_a + frac_b) / max(.001, 2 * cfg.base_attrition_rate))
    locality.violence = clamp(locality.violence * .85 + .25 * intensity)
    civilian_harm = (locality.population * zone.population_share * cfg.civilian_exposure_rate *
                     intensity * exposure * rng.expovariate(1.0))
    world.cumulative_civilian_harm += civilian_harm
    signal = logistic((frac_b - frac_a) * 18 + .35 * advantage)
    withdrawal_ids = []
    for formation_id in disengaged:
        order = choose_withdrawal_order(world, formation_id, time, rng)
        if order is not None:
            withdrawal_ids.append(order.order_id)
    reinforcement_ids = []
    for formation, opponent in ((a, b), (b, a)):
        loss_fraction = losses[formation.formation_id] / max(
            1e-12, formation.personnel + losses[formation.formation_id]
        )
        order = _reinforcement(world, formation, opponent, loss_fraction, time, rng)
        if order is not None:
            reinforcement_ids.append(order.order_id)
    engagement_id = f"ENG{len(world.engagements) + 1:010d}"
    observations = (
        _event_observation(world, a, b, engagement_id, zone_id, time, signal, civilian_harm, rng),
        _event_observation(world, b, a, engagement_id, zone_id, time, 1 - signal, civilian_harm, rng),
    )
    # Population response consumes the reported values, not the true tactical
    # state. The two audiences can therefore interpret the same event differently.
    # Convert each audience's noisy report into a common government-advantage
    # frame before pooling.  Averaging opposing audience perspectives directly
    # would mechanically cancel the signal toward 0.5.
    government_signals = []
    for observation in observations:
        organization = world.organizations.get(observation.observer_actor_id)
        value = float(observation.estimated_value["momentum"])
        if organization is not None and organization.kind is OrganizationKind.INSURGENT:
            value = 1 - value
        government_signals.append(value)
    reported_signal = sum(government_signals) / max(1, len(government_signals))
    reported_harm = sum(float(o.estimated_value["civilian_harm"]) for o in observations) / max(1, len(observations))
    _update_perceived_momentum(world, locality.locality_id, reported_signal, reported_harm, rng)
    engagement = Engagement(
        engagement_id, event_id, time, locality.locality_id, zone_id,
        a.formation_id, b.formation_id, detected_by,
        {a.formation_id: initiative_a, b.formation_id: initiative_b},
        {a.formation_id: cap_a, b.formation_id: cap_b}, losses,
        {fid: before_cohesion[fid] - world.formations[fid].cohesion for fid in before_cohesion},
        {fid: before_readiness[fid] - world.formations[fid].readiness for fid in before_readiness},
        supply_used, civilian_harm, tuple(disengaged), tuple(ineffective),
        tuple(reinforcement_ids), signal, initiator_organization_id, contact_cause,
        tuple(withdrawal_ids),
    )
    world.engagements[engagement_id] = engagement
    return engagement, observations


def combat_diagnostics(world) -> dict:
    return {
        "engagements": len(world.engagements),
        "civilian_harm": world.cumulative_civilian_harm,
        "personnel_losses": {f.formation_id: f.cumulative_losses for f in world.formations.values()},
        "ineffective_formations": [f.formation_id for f in world.formations.values()
                                    if f.operational_status == "ineffective"],
        "records": [
            {"engagement_id": e.engagement_id, "time": e.time,
             "locality_id": e.locality_id, "microzone_id": e.microzone_id,
             "losses": e.personnel_losses, "disengaged": e.disengaged,
             "civilian_harm": e.civilian_harm,
             "reinforcement_order_ids": e.reinforcement_order_ids,
             "withdrawal_order_ids": e.withdrawal_order_ids}
            for e in world.engagements.values()
        ],
    }
