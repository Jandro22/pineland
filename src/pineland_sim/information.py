from __future__ import annotations

"""Detection, observation, fusion, and organizational information flow.

This module is intentionally separate from physical control and combat.  It
implements the information chain::

    true state -> heterogeneous observation -> actor-local belief -> decision

Actors receive only the observation and its fused belief.  Truth is used here
only by the environment while sampling an observation, and analyst-only error
is calculated in :func:`information_diagnostics`.
"""

from collections import deque
from array import array
from dataclasses import asdict
from math import exp, log
import random
from typing import Any, Iterable

from .entities import (
    ActorBelief,
    ActorZoneBelief,
    ArmedFormation,
    CONTROL_DIMENSIONS,
    ControlVector,
    InformationRelay,
    Observation,
    OrganizationKind,
    PresenceBelief,
    clamp,
    logistic,
)
from .logistics import command_path
from .timebase import reference_probability
from .world import WorldState, seeded_rng
from .relations import (
    STATE_SECURITY_KINDS,
    organizations_allied,
    organizations_hostile,
)
from .organizational_state import local_organizational_embeddedness
from .native_kernels import (
    available as native_kernels_available,
    control_batch_enabled as native_control_batch_enabled,
    fuse_control7_batch as native_fuse_control7_batch,
)


OBSERVATION_SOURCE_TYPES = (
    "patrol", "fixed_post", "civilian", "social_network", "administrative",
    "organization_member", "political_elite", "interpreter", "contact",
)


def initialize_information_world(world: WorldState) -> None:
    """Create actor priors and clear run-specific observation state."""
    world.observations.clear()
    world.next_observation_sequence = 1
    world.observation_index.clear()
    world.observation_source_index.clear()
    world.information_relays.clear()
    world.next_information_relay_sequence = 1
    world.active_information_relays.clear()
    world.presence_beliefs.clear()
    world.node_presence_beliefs.clear()
    world.control_beliefs.clear()
    world.information_detections = {
        "true_positive": 0,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 0,
    }
    world.information_detection_by_source.clear()
    world.last_information_decay_at = world.time
    for observer_id in (
        world.ordered_organization_ids or tuple(sorted(world.organizations))
    ):
        target_ids = {"government"}
        active_insurgents = (
            world.active_insurgent_organization_ids
            if world.active_insurgent_organization_ids
            else tuple(
                organization.organization_id
                for organization in world.organizations.values()
                if (
                    organization.kind is OrganizationKind.INSURGENT
                    and organization.status == "active"
                )
            )
        )
        target_ids.update(active_insurgents)
        if active_insurgents:
            target_ids.add("insurgent")
        for locality_id in (
            world.ordered_locality_ids or tuple(sorted(world.localities))
        ):
            for target_id in sorted(target_ids):
                belief = ActorBelief(
                    observer_id, locality_id, ControlVector(*([.5] * 7)),
                    world.config.information.prior_confidence, world.time,
                )
                world.control_beliefs[(observer_id, target_id, locality_id)] = belief


def _logit(probability: float) -> float:
    probability = clamp(probability, 1e-6, 1 - 1e-6)
    return log(probability / (1 - probability))


def _target_actors_for_observer(
    world: WorldState, observer_actor_id: str
) -> tuple[str, ...]:
    """Return every strategically hostile target visible to an observer.

    Aggregate side identifiers remain compatibility coalitions. Concrete
    insurgent rivals are preserved so faction-specific beliefs can actually be
    learned rather than existing only as empty prior slots.
    """
    observer = world.organizations.get(observer_actor_id)
    if observer is None:
        return ()
    hostile = sorted(
        (
            organization
            for organization in world.organizations.values()
            if (
                organization.organization_id != observer_actor_id
                and organization.status == "active"
                and organizations_hostile(
                    world, observer_actor_id, organization.organization_id
                )
            )
        ),
        key=lambda item: item.organization_id,
    )
    if observer.kind is OrganizationKind.INSURGENT:
        targets: list[str] = []
        if (
            "government" in world.organizations
            and any(item.kind in STATE_SECURITY_KINDS for item in hostile)
        ):
            targets.append("government")
        targets.extend(
            item.organization_id
            for item in hostile
            if item.kind is OrganizationKind.INSURGENT
        )
        targets.extend(
            item.organization_id
            for item in hostile
            if item.kind not in STATE_SECURITY_KINDS
            and item.kind is not OrganizationKind.INSURGENT
        )
        return tuple(dict.fromkeys(targets))
    insurgents = [
        item.organization_id
        for item in hostile
        if item.kind is OrganizationKind.INSURGENT
    ]
    if not insurgents:
        return ()
    if len(insurgents) == 1 and insurgents[0] == "insurgent":
        return ("insurgent",)
    return tuple(insurgents)


def _target_actor_for_observer(world: WorldState, observer_actor_id: str) -> str | None:
    """Backward-compatible primary-target helper for diagnostics."""
    targets = _target_actors_for_observer(world, observer_actor_id)
    return targets[0] if targets else None


def _is_insurgent_actor(world: WorldState, actor_id: str | None) -> bool:
    """Whether an identifier denotes the insurgent side or a splinter."""
    return bool(actor_id == "insurgent" or
                (actor_id and actor_id in world.organizations and
                 world.organizations[actor_id].kind is OrganizationKind.INSURGENT))


def _formation_matches_target_actor(world: WorldState, formation: ArmedFormation,
                                    target_actor_id: str) -> bool:
    """Match aggregate conflict sides as well as concrete organization IDs."""
    organization = world.organizations.get(formation.organization_id)
    if target_actor_id == "insurgent":
        return bool(organization and organization.kind is OrganizationKind.INSURGENT)
    if target_actor_id == "government":
        return bool(
            organization
            and (
                formation.organization_id == "government"
                or (
                    "government" in world.organizations
                    and organizations_allied(
                        world, formation.organization_id, "government"
                    )
                )
            )
        )
    return formation.organization_id == target_actor_id


def _information_formation_index(world: WorldState) -> dict[tuple[str, str], list[ArmedFormation]]:
    """Index observable stationary formations once per information update."""
    index: dict[tuple[str, str], list[ArmedFormation]] = {}
    for formation in world.formations.values():
        if formation.personnel <= 0 or formation.moving:
            continue
        keys = [(formation.organization_id, formation.locality_id)]
        organization = world.organizations.get(formation.organization_id)
        if organization is not None:
            if organization.kind is OrganizationKind.INSURGENT:
                side = "insurgent"
            elif (
                formation.organization_id == "government"
                or (
                    "government" in world.organizations
                    and organizations_allied(
                        world, formation.organization_id, "government"
                    )
                )
            ):
                side = "government"
            else:
                side = None
            if side is not None and side != formation.organization_id:
                keys.append((side, formation.locality_id))
        for key in keys:
            index.setdefault(key, []).append(formation)
    return index


def _observer_formation(world: WorldState, observer_id: str | None) -> ArmedFormation | None:
    if observer_id is None:
        return None
    return world.formations.get(observer_id)


def language_comprehension(world: WorldState, observer_actor_id: str,
                           locality_id: str, source_type: str,
                           source_id: str | None = None) -> float:
    """Return effective language comprehension, retaining a nonzero floor.

    Civilian and elite channels inherit the local community language profile;
    organization-member channels inherit formation information.  Interpreters
    improve transmission but do not make an otherwise inaccessible report
    perfect.
    """
    organization = world.organizations.get(observer_actor_id)
    if organization is None:
        return 0.25
    cache_key = (
        "language", observer_actor_id, locality_id, source_type, source_id
    )
    if world.information_cache_active:
        cached = world.information_execution_cache.get(cache_key)
        if cached is not None:
            if world.performance_counters is not None:
                world.performance_counters["information_language_cache_hit"] = (
                    world.performance_counters.get("information_language_cache_hit", 0) + 1
                )
            return float(cached)
        if world.performance_counters is not None:
            world.performance_counters["information_language_cache_miss"] = (
                world.performance_counters.get("information_language_cache_miss", 0) + 1
            )
    embeddedness_key = ("embeddedness", observer_actor_id, locality_id)
    local_embeddedness = (
        world.information_execution_cache.get(embeddedness_key)
        if world.information_cache_active else None
    )
    if local_embeddedness is None:
        local_embeddedness = local_organizational_embeddedness(
            world, observer_actor_id, locality_id
        )
        if world.information_cache_active:
            world.information_execution_cache[embeddedness_key] = local_embeddedness
    primary = world.primary_language_by_locality.get(locality_id)
    if primary is None:
        district = world.districts[world.localities[locality_id].district_id]
        primary = district.language_pattern.split("/", 1)[0]
        multilingual = "/" in district.language_pattern
    else:
        multilingual = locality_id in world.multilingual_locality_ids
    if source_type in {"civilian", "social_network", "political_elite", "interpreter"}:
        base = 0.28 + 0.48 * local_embeddedness
        if primary != "FS":
            base -= 0.18
        if multilingual:
            base += 0.07
        if source_type == "interpreter":
            base += 0.2
        # A source community can still have a bilingual bridge member.
        if source_id and source_id in world.social_communities:
            community = world.social_communities[source_id]
            base = 0.22 + 0.62 * max(community.language_profile.values(), default=.2)
            if source_type == "interpreter":
                base += 0.15
        result = clamp(base, .08, 1.0)
    else:
        formation = _observer_formation(world, source_id)
        if formation is not None:
            result = clamp(.35 + .55 * formation.information + .1 * local_embeddedness,
                           .1, 1.0)
        else:
            result = clamp(.45 + .45 * local_embeddedness, .1, 1.0)
    if world.information_cache_active:
        world.information_execution_cache[cache_key] = result
    return result


def source_trust(world: WorldState, observer_actor_id: str, source_type: str,
                 locality_id: str, source_id: str | None = None) -> float:
    cache_key = ("trust", observer_actor_id, source_type, locality_id, source_id)
    if world.information_cache_active:
        cached = world.information_execution_cache.get(cache_key)
        if cached is not None:
            if world.performance_counters is not None:
                world.performance_counters["information_trust_cache_hit"] = (
                    world.performance_counters.get("information_trust_cache_hit", 0) + 1
                )
            return float(cached)
        if world.performance_counters is not None:
            world.performance_counters["information_trust_cache_miss"] = (
                world.performance_counters.get("information_trust_cache_miss", 0) + 1
            )
    config = world.config.information
    trust = config.source_trust.get(source_type, .5)
    organization = world.organizations.get(observer_actor_id)
    if organization is not None:
        trust *= .7 + .3 * clamp(organization.accountability)
    if source_type == "civilian" or source_type == "social_network":
        if source_id in world.social_communities:
            community = world.social_communities[source_id]
            cooperation = (community.government_cooperation if not _is_insurgent_actor(world, observer_actor_id)
                           else community.insurgent_sympathy)
            trust *= .7 + .6 * clamp(cooperation)
    result = clamp(trust, .02, 1.0)
    if world.information_cache_active:
        world.information_execution_cache[cache_key] = result
    return result


def source_quality(world: WorldState, observer_actor_id: str, source_type: str,
                   locality_id: str, source_id: str | None = None,
                   rng: random.Random | None = None) -> float:
    config = world.config.information
    quality = config.source_coverage.get(source_type, .4)
    locality = world.localities[locality_id]
    quality *= .55 + .45 * locality.observability
    # Language is applied once during detection and once during fusion.  Keep
    # it out of source quality so a report is not attenuated three times.
    if rng is not None:
        quality *= .85 + .3 * rng.random()
    return clamp(quality)


def _decay_rate(world: WorldState, observation_type: str,
                target_formation_id: str | None = None) -> float:
    config = world.config.information
    if target_formation_id is not None or observation_type in {"presence", "detection"}:
        return config.formation_decay_rate
    if observation_type in {"road", "infrastructure"}:
        return config.road_decay_rate
    if observation_type in {"physical_control", "control"}:
        return config.default_decay_rate
    if observation_type in {"administrative", "governance"}:
        return config.static_decay_rate
    return config.mobile_decay_rate


def _primary_zone(world: WorldState, locality_id: str) -> str | None:
    cached = world.primary_microzone_by_locality.get(locality_id)
    if cached is not None:
        return cached
    zones = [zone for zone in world.microzones.values() if zone.locality_id == locality_id]
    if not zones:
        return None
    cached = max(zones, key=lambda zone: zone.population_share).microzone_id
    world.primary_microzone_by_locality[locality_id] = cached
    return cached


def _actual_target_presence(world: WorldState, target_actor_id: str,
                            locality_id: str, target_formation_id: str | None = None,
                            microzone_id: str | None = None,
                            formation_index: dict[tuple[str, str], list[ArmedFormation]] | None = None,
                            ) -> tuple[bool, float, str | None]:
    candidates = (
        formation_index.get((target_actor_id, locality_id), ())
        if formation_index is not None else
        (formation for formation in world.formations.values()
         if _formation_matches_target_actor(world, formation, target_actor_id)
         and formation.personnel > 0 and not formation.moving
         and formation.locality_id == locality_id)
    )
    personnel = 0.0
    chosen: ArmedFormation | None = None
    for formation in candidates:
        if target_formation_id is not None and formation.formation_id != target_formation_id:
            continue
        if microzone_id is not None and formation.current_microzone_id != microzone_id:
            patrol_ids = world.patrol_ids_by_formation.get(formation.formation_id)
            if patrol_ids is None:
                patrols = (patrol for patrol in world.patrols.values()
                           if patrol.formation_id == formation.formation_id)
            else:
                patrols = (world.patrols[patrol_id] for patrol_id in patrol_ids
                           if patrol_id in world.patrols)
            if not any(patrol.current_microzone_id == microzone_id for patrol in patrols):
                continue
        personnel += formation.personnel
        if chosen is None or formation.personnel > chosen.personnel:
            chosen = formation
    return chosen is not None, personnel, chosen.formation_id if chosen else None


def detection_probability(world: WorldState, observer_id: str,
                          target_formation_id: str | None, locality_id: str,
                          source_type: str = "patrol", microzone_id: str | None = None) -> float:
    """Condition-dependent true-positive probability.

    Pressure/readiness, exposure, language, observability, and terrain all
    enter the logit.  This is a detection model, not a combat model.
    """
    config = world.config.information
    observer_formation = _observer_formation(world, observer_id)
    observer_actor_id = (observer_formation.organization_id if observer_formation
                         else observer_id if observer_id in world.organizations else "government")
    locality = world.localities[locality_id]
    zone_observability = locality.observability
    if microzone_id and microzone_id in world.microzones:
        zone_observability = world.microzones[microzone_id].observability
    readiness = (observer_formation.fatigue_adjusted_readiness() if observer_formation else
                 clamp(world.organizations.get(observer_actor_id).institutional_quality
                       if observer_actor_id in world.organizations else .5))
    target = world.formations.get(target_formation_id) if target_formation_id else None
    target_embeddedness = target.embeddedness if target else .5
    language = language_comprehension(world, observer_actor_id, locality_id,
                                      source_type, observer_id)
    if observer_formation:
        # Search pressure is a deployment/quality quantity. Readiness has its
        # own term above; using effective strength here used to apply readiness,
        # supply, and command a second time inside the same detection model.
        deployment_fraction = (
            observer_formation.deployable_personnel() /
            max(1.0, observer_formation.personnel)
        )
        pressure = clamp(
            deployment_fraction * observer_formation.quality *
            observer_formation.cohesion * (0.5 + observer_formation.information) / 2.0
        )
    else:
        pressure = .5
    exposure = clamp(.35 + .45 * zone_observability - .25 * target_embeddedness)
    terrain_penalty = clamp(locality.terrain_friction / 2.5)
    base = config.contact_true_positive_rate if source_type == "contact" else config.true_positive_rate
    if base <= 0:
        return 0.0
    if base >= 1:
        return 1.0
    score = (_logit(base) + config.detection_pressure_bonus * pressure +
             config.detection_exposure_bonus * exposure +
             config.detection_language_bonus * language +
             config.detection_observability_bonus * zone_observability +
             config.detection_readiness_bonus * readiness -
             config.detection_terrain_penalty * terrain_penalty)
    if target is not None and target.organization_id in world.organizations:
        organization = world.organizations[target.organization_id]
        if organization.kind is OrganizationKind.INSURGENT:
            concealment = config.insurgent_concealment * (
                .5 + .5 * organization.phenotype.get("dispersion", .5))
            score -= .9 * concealment
    return clamp(logistic(score))


def false_positive_probability(world: WorldState, observer_id: str, locality_id: str,
                               source_type: str = "patrol",
                               microzone_id: str | None = None) -> float:
    config = world.config.information
    locality = world.localities[locality_id]
    observability = locality.observability
    if microzone_id and microzone_id in world.microzones:
        observability = world.microzones[microzone_id].observability
    base = config.contact_false_positive_rate if source_type == "contact" else config.false_positive_rate
    if base <= 0:
        return 0.0
    if base >= 1:
        return 1.0
    # Difficult terrain and poor comprehension make ambiguous reports more likely.
    language = language_comprehension(world,
                                      _observer_formation(world, observer_id).organization_id
                                      if _observer_formation(world, observer_id) else observer_id,
                                      locality_id, source_type, observer_id)
    score = _logit(base) + .3 * (1 - observability) + .25 * (1 - language)
    return clamp(logistic(score))


def _new_observation(world: WorldState, *, observer_actor_id: str, observer_node_id: str | None,
                     target_id: str | None, target_actor_id: str | None,
                     target_formation_id: str | None, locality_id: str,
                     microzone_id: str | None, timestamp: float, source_id: str,
                     source_type: str, observation_type: str,
                     estimated_value: dict[str, Any], quality: float,
                     confidence: float, provenance: dict[str, Any]) -> Observation:
    observation_id = f"OBS{world.next_observation_sequence:010d}"
    world.next_observation_sequence += 1
    observation = Observation(
        observation_id=observation_id,
        target_id=target_id,
        locality_id=locality_id,
        timestamp=timestamp,
        source_id=source_id,
        source_type=source_type,
        observation_type=observation_type,
        estimated_value=estimated_value,
        confidence=clamp(confidence),
        provenance=provenance,
        observer_actor_id=observer_actor_id,
        microzone_id=microzone_id,
        observer_node_id=observer_node_id,
        quality=clamp(quality),
        decay_rate=_decay_rate(world, observation_type, target_formation_id),
        target_actor_id=target_actor_id,
        target_formation_id=target_formation_id,
        received_at=timestamp,
    )
    world.observations[observation_id] = observation
    index_key = (observation.target_actor_id or "*", observation.locality_id,
                 observation.observation_type)
    if world.execution_profile != "particle":
        world.observation_index.setdefault(index_key, []).append(
            observation.timestamp
        )
    source_history = world.observation_source_index.setdefault(index_key, deque())
    source_history.append((observation.timestamp, observation.source_id))
    # Corroboration has a finite three-day memory.  Evicting stale entries at
    # ingestion keeps both memory and fusion cost bounded over multi-year
    # ensemble/calibration runs.
    cutoff = observation.timestamp - 3.0
    while source_history and source_history[0][0] < cutoff:
        source_history.popleft()
    return observation


def _presence_key(observer_id: str, target_actor_id: str, locality_id: str,
                  target_id: str | None, microzone_id: str | None) -> tuple[str, str, str, str]:
    # Keep microzone in the key while allowing an organization-level wildcard.
    location_key = f"{locality_id}:{microzone_id or '*'}"
    return observer_id, target_actor_id, location_key, target_id or "*"


def _fuse_scalar(old: float, prior_confidence: float, value: float, weight: float,
                 contradiction: float, penalty: float) -> tuple[float, float, float]:
    prior = max(.02, prior_confidence)
    new_value = (prior * old + weight * value) / (prior + weight)
    disagreement = abs(value - old)
    contradiction = contradiction + weight * disagreement
    confidence = clamp((prior + weight) / (1.0 + prior + weight) *
                       exp(-penalty * contradiction))
    return clamp(new_value), confidence, contradiction


def _decayed_contradiction(world: WorldState, value: float,
                           updated_at: float, time: float) -> float:
    """Give disagreement finite memory so stale conflicts do not poison beliefs forever."""
    age = max(0.0, time - updated_at)
    return value * exp(-age / world.config.information.contradiction_memory_days)


def _ensure_control_belief(world: WorldState, observer_id: str, target_actor_id: str,
                           locality_id: str) -> ActorBelief:
    key = (observer_id, target_actor_id, locality_id)
    belief = getattr(world, "control_beliefs", {}).get(key)
    if belief is None:
        # Dynamic beliefs begin as an uninformative prior; only a generated
        # observation may move them toward the underlying state.
        belief = ActorBelief(observer_id, locality_id, ControlVector(*([.5] * 7)),
                             world.config.information.prior_confidence, 0.0)
        world.control_beliefs[key] = belief
    return belief


def _fuse_control_immediate(
    world: WorldState,
    observation: Observation,
    recipient_id: str,
    time: float,
    weight: float,
) -> None:
    target_actor_id = observation.target_actor_id
    if target_actor_id is None:
        return
    value = observation.estimated_value
    control_values = value.get("control")
    physical_value = value.get("physical_control")
    if not isinstance(control_values, dict) and physical_value is None:
        return
    belief = _ensure_control_belief(
        world, recipient_id, target_actor_id, observation.locality_id
    )
    if isinstance(control_values, dict):
        values = control_values
    else:
        values = {"physical": physical_value}
    prior_confidence = belief.confidence
    contradiction_decay = exp(
        -max(0.0, time - belief.updated_at)
        / world.config.information.contradiction_memory_days
    )
    penalty = world.config.information.contradiction_penalty
    prior = max(.02, prior_confidence)
    contradiction = belief.contradiction_index
    estimate = belief.control_estimate
    confidence = belief.confidence
    denominator = prior + weight
    confidence_scale = denominator / (1.0 + denominator)
    if (
        len(values) == 7
        and tuple(values) == CONTROL_DIMENSIONS
    ):
        # Canonical background control reports always carry the seven control
        # fields in CONTROL_DIMENSIONS order. Fully unroll this extremely hot
        # path while preserving the exact scalar arithmetic/update sequence.
        observed_value = clamp(float(values["formal"]))
        old = estimate.formal
        estimate.formal = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["physical"]))
        old = estimate.physical
        estimate.physical = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["administrative"]))
        old = estimate.administrative
        estimate.administrative = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["legal"]))
        old = estimate.legal
        estimate.legal = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["fiscal"]))
        old = estimate.fiscal
        estimate.fiscal = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["social"]))
        old = estimate.social
        estimate.social = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )

        observed_value = clamp(float(values["expected"]))
        old = estimate.expected
        estimate.expected = clamp(
            (prior * old + weight * observed_value) / denominator
        )
        contradiction = (
            contradiction * contradiction_decay
            + weight * abs(observed_value - old)
        )
        confidence = clamp(
            confidence_scale * exp(-penalty * contradiction)
        )
    else:
        for dimension, observed in values.items():
            if dimension not in CONTROL_DIMENSIONS:
                continue
            old = getattr(estimate, dimension)
            observed_value = clamp(float(observed))
            new = clamp(
                (prior * old + weight * observed_value) / denominator
            )
            contradiction = (
                contradiction * contradiction_decay
                + weight * abs(observed_value - old)
            )
            confidence = clamp(
                confidence_scale * exp(-penalty * contradiction)
            )
            setattr(estimate, dimension, new)
    belief.confidence = confidence
    belief.contradiction_index = contradiction
    belief.updated_at = time
    belief.evidence_count += 1
    if weight >= .12:
        belief.last_reliable_observation_at = time
    _apply_control_auxiliary(
        world,
        observation,
        recipient_id,
        time,
        weight,
        values,
        belief,
    )


def _apply_control_auxiliary(
    world: WorldState,
    observation: Observation,
    recipient_id: str,
    time: float,
    weight: float,
    values: dict[str, Any],
    belief: ActorBelief,
) -> None:
    target_actor_id = observation.target_actor_id
    if target_actor_id is None:
        return
    if observation.microzone_id and "physical" in values:
        zone_actor = (world.formations[recipient_id].organization_id
                      if recipient_id in world.formations else recipient_id)
        zone_belief = world.zone_beliefs.get((zone_actor, observation.microzone_id))
        if zone_belief is not None:
            old_zone = zone_belief.physical_control_estimate
            prior_zone = max(.02, zone_belief.confidence)
            zone_value, zone_confidence, zone_contradiction = _fuse_scalar(
                old_zone, prior_zone, clamp(float(values["physical"])), weight,
                _decayed_contradiction(world, zone_belief.contradiction_index,
                                       zone_belief.updated_at, time),
                world.config.information.contradiction_penalty,
            )
            zone_belief.physical_control_estimate = zone_value
            zone_belief.confidence = zone_confidence
            zone_belief.contradiction_index = zone_contradiction
            zone_belief.updated_at = time
            zone_belief.evidence_count += 1
            if weight >= .12:
                zone_belief.last_reliable_observation_at = time
    # Existing beliefs remain the backward-compatible perceived state used by
    # the Phase 3 movement policy when the observed actor is the observer's side.
    if (_is_insurgent_actor(world, target_actor_id) and _is_insurgent_actor(world, recipient_id)) or \
            (target_actor_id == "government" and not _is_insurgent_actor(world, recipient_id)):
        legacy = world.beliefs.get((recipient_id, observation.locality_id))
        if legacy is not None:
            legacy.control_estimate.formal = belief.control_estimate.formal
            legacy.control_estimate.physical = belief.control_estimate.physical
            legacy.control_estimate.administrative = belief.control_estimate.administrative
            legacy.control_estimate.legal = belief.control_estimate.legal
            legacy.control_estimate.fiscal = belief.control_estimate.fiscal
            legacy.control_estimate.social = belief.control_estimate.social
            legacy.control_estimate.expected = belief.control_estimate.expected
            legacy.confidence = belief.confidence
            legacy.updated_at = belief.updated_at
            legacy.last_reliable_observation_at = belief.last_reliable_observation_at
            legacy.evidence_count = belief.evidence_count
            legacy.contradiction_index = belief.contradiction_index


def _canonical_control_tuple(
    observation: Observation,
) -> tuple[float, ...] | None:
    values = observation.estimated_value.get("control")
    if (
        not isinstance(values, dict)
        or len(values) != 7
        or tuple(values) != CONTROL_DIMENSIONS
    ):
        return None
    return (
        float(values["formal"]),
        float(values["physical"]),
        float(values["administrative"]),
        float(values["legal"]),
        float(values["fiscal"]),
        float(values["social"]),
        float(values["expected"]),
    )


def _flush_native_control_chunk(
    world: WorldState,
    chunk: list[tuple[Observation, str, float, float]],
) -> bool:
    if not chunk or not native_kernels_available():
        return False
    belief_by_key: dict[tuple[str, str, str], ActorBelief] = {}
    state_index_by_key: dict[tuple[str, str, str], int] = {}
    state_keys: list[tuple[str, str, str]] = []
    state_payload = array("d")
    update_indices = array("I")
    times = array("d")
    weights = array("d")
    observed = array("d")

    for observation, recipient_id, time, weight in chunk:
        target_actor_id = observation.target_actor_id
        canonical = _canonical_control_tuple(observation)
        if target_actor_id is None or canonical is None:
            return False
        key = (
            recipient_id,
            target_actor_id,
            observation.locality_id,
        )
        index = state_index_by_key.get(key)
        if index is None:
            belief = _ensure_control_belief(
                world,
                recipient_id,
                target_actor_id,
                observation.locality_id,
            )
            index = len(state_keys)
            state_index_by_key[key] = index
            state_keys.append(key)
            belief_by_key[key] = belief
            estimate = belief.control_estimate
            state_payload.extend((
                estimate.formal,
                estimate.physical,
                estimate.administrative,
                estimate.legal,
                estimate.fiscal,
                estimate.social,
                estimate.expected,
                belief.confidence,
                belief.updated_at,
                belief.last_reliable_observation_at,
                float(belief.evidence_count),
                belief.contradiction_index,
            ))
        update_indices.append(index)
        times.append(float(time))
        weights.append(float(weight))
        observed.extend(canonical)

    if not native_fuse_control7_batch(
        state_payload,
        len(state_keys),
        update_indices,
        times,
        weights,
        observed,
        contradiction_memory_days=(
            world.config.information.contradiction_memory_days
        ),
        contradiction_penalty=(
            world.config.information.contradiction_penalty
        ),
    ):
        return False

    for index, key in enumerate(state_keys):
        offset = index * 12
        belief = belief_by_key[key]
        estimate = belief.control_estimate
        estimate.formal = state_payload[offset]
        estimate.physical = state_payload[offset + 1]
        estimate.administrative = state_payload[offset + 2]
        estimate.legal = state_payload[offset + 3]
        estimate.fiscal = state_payload[offset + 4]
        estimate.social = state_payload[offset + 5]
        estimate.expected = state_payload[offset + 6]
        belief.confidence = state_payload[offset + 7]
        belief.updated_at = state_payload[offset + 8]
        belief.last_reliable_observation_at = state_payload[offset + 9]
        belief.evidence_count = int(state_payload[offset + 10])
        belief.contradiction_index = state_payload[offset + 11]

    # Zone beliefs are independent scalar recurrences. Legacy beliefs are
    # mirrors of the actor belief. Apply these in original observation order.
    for observation, recipient_id, time, weight in chunk:
        target_actor_id = observation.target_actor_id
        key = (
            recipient_id,
            target_actor_id,
            observation.locality_id,
        )
        values = observation.estimated_value["control"]
        _apply_control_auxiliary(
            world,
            observation,
            recipient_id,
            time,
            weight,
            values,
            belief_by_key[key],
        )
    return True


def _fuse_control(world: WorldState, observation: Observation, recipient_id: str,
                  time: float, weight: float) -> None:
    if world.defer_control_fusions:
        world.deferred_control_fusions.append(
            (observation, recipient_id, float(time), float(weight))
        )
        return
    _fuse_control_immediate(
        world, observation, recipient_id, time, weight
    )


def _flush_control_fusions(world: WorldState) -> int:
    pending = world.deferred_control_fusions
    if not pending:
        return 0
    world.deferred_control_fusions = []
    prior = world.defer_control_fusions
    world.defer_control_fusions = False
    try:
        native_enabled = (
            world.execution_backend == "optimized"
            and native_control_batch_enabled()
        )
        if not native_enabled:
            for observation, recipient_id, time, weight in pending:
                _fuse_control_immediate(
                    world, observation, recipient_id, time, weight
                )
            return len(pending)

        chunk: list[tuple[Observation, str, float, float]] = []
        for item in pending:
            observation, recipient_id, time, weight = item
            if _canonical_control_tuple(observation) is not None:
                chunk.append(item)
                continue
            if chunk:
                if not _flush_native_control_chunk(world, chunk):
                    for queued in chunk:
                        _fuse_control_immediate(world, *queued)
                chunk = []
            _fuse_control_immediate(
                world, observation, recipient_id, time, weight
            )
        if chunk and not _flush_native_control_chunk(world, chunk):
            for queued in chunk:
                _fuse_control_immediate(world, *queued)
    finally:
        world.defer_control_fusions = prior
    return len(pending)


def _ensure_presence_belief(world: WorldState, observer_id: str, target_actor_id: str,
                            locality_id: str, target_id: str | None,
                            microzone_id: str | None, node: bool) -> PresenceBelief:
    container = world.node_presence_beliefs if node else world.presence_beliefs
    key = _presence_key(observer_id, target_actor_id, locality_id, target_id, microzone_id)
    belief = container.get(key)
    if belief is None:
        belief = PresenceBelief(observer_id, target_actor_id, locality_id,
                                0.0, world.config.information.prior_confidence, 0.0,
                                target_id=target_id, microzone_id=microzone_id)
        container[key] = belief
    return belief


def get_presence_belief(world: WorldState, observer_id: str, target_actor_id: str,
                        locality_id: str, target_id: str | None = None,
                        microzone_id: str | None = None,
                        node: bool = False) -> PresenceBelief | None:
    """Return a fused presence belief using the public key dimensions."""
    container = world.node_presence_beliefs if node else world.presence_beliefs
    return container.get(_presence_key(
        observer_id, target_actor_id, locality_id, target_id, microzone_id
    ))


presence_belief = get_presence_belief


def _fuse_presence(world: WorldState, observation: Observation, recipient_id: str,
                   time: float, weight: float, node: bool = False) -> None:
    target_actor_id = observation.target_actor_id
    if target_actor_id is None or "presence" not in observation.estimated_value:
        return
    target_id = observation.target_id or observation.target_formation_id
    presence = clamp(float(observation.estimated_value.get("presence", 0.0)))
    personnel = max(0.0, float(observation.estimated_value.get("personnel", 0.0)))
    keys = [target_id]
    if target_id is not None:
        keys.append(None)
    for key_target in keys:
        belief = _ensure_presence_belief(
            world, recipient_id, target_actor_id, observation.locality_id,
            key_target, observation.microzone_id, node,
        )
        new, confidence, contradiction = _fuse_scalar(
            belief.presence_estimate, belief.confidence, presence, weight,
            _decayed_contradiction(world, belief.contradiction_index, belief.updated_at, time),
            world.config.information.contradiction_penalty,
        )
        belief.presence_estimate = new
        belief.personnel_estimate = ((belief.personnel_estimate * max(.02, belief.confidence) +
                                      personnel * weight) /
                                     (max(.02, belief.confidence) + weight))
        belief.confidence = confidence
        belief.contradiction_index = contradiction
        belief.updated_at = time
        belief.evidence_count += 1
        if weight >= .12:
            belief.last_reliable_observation_at = time
    # Violence/repression is a separate actor-local belief.  It is updated
    # from the same reported observation operator but is never read from the
    # realized locality state by decision code.
    if "violence" in observation.estimated_value:
        prior = max(.02, belief.confidence)
        observed_violence = clamp(float(observation.estimated_value["violence"]))
        belief.violence_estimate = clamp(
            (prior * belief.violence_estimate + weight * observed_violence) /
            (prior + weight)
        )


def _corroboration_weight(history, timestamp: float, source_id: str,
                          correlation: float) -> float:
    """Exact capped independent-source weight, stopping once it saturates."""
    sources: set[str] = set()
    weight = 0.0
    for stamp, identity in reversed(history):
        if stamp < timestamp - 3.0:
            break
        if identity != source_id and abs(stamp - timestamp) <= 3.0 and identity not in sources:
            sources.add(identity)
            weight += 1.0 - correlation
            if weight >= 3.0:
                return 3.0
    return weight


def fuse_observation(world: WorldState, observation: Observation, recipient_id: str,
                     time: float | None = None, node: bool = False,
                     *, trust_override: float | None = None,
                     language_override: float | None = None) -> float:
    """Fuse one observation into a recipient's local belief state.

    Returns the effective evidence weight used by the estimator.  No world
    truth is consulted here, which makes the function safe for policy code and
    straightforward to unit test with hand-built contradictory reports.
    """
    time = observation.timestamp if time is None else time
    recipient_actor = (recipient_id if recipient_id in world.organizations else
                       world.formations[recipient_id].organization_id
                       if recipient_id in world.formations else observation.observer_actor_id)
    trust = (
        float(trust_override)
        if trust_override is not None
        else source_trust(
            world, recipient_actor, observation.source_type,
            observation.locality_id, observation.source_id,
        )
    )
    language = (
        float(language_override)
        if language_override is not None
        else language_comprehension(
            world, recipient_actor,
            observation.locality_id, observation.source_type,
            observation.source_id,
        )
    )
    age_quality = exp(-observation.decay_rate * max(0.0, time - observation.timestamp))
    # Corroboration counts independent source identities, not repeated
    # observations from one rumor/collection node.
    index_key = (observation.target_actor_id or "*", observation.locality_id,
                 observation.observation_type)
    # Observation histories are append-only and generated in simulation-time
    # order.  The old implementation scanned the complete history for every
    # observation, turning a long run into an O(N²) operation.  Corroboration
    # only has a three-day memory, so scan the recent tail and stop as soon as
    # the lower window bound is crossed.  This preserves the estimator while
    # making long-horizon runs effectively linear in the number of reports.
    # Distinct source IDs remain visible, but correlated collection channels
    # contribute less than independent corroboration.  This prevents a burst
    # of reports copied from one administrative or social pipeline from being
    # treated as independent evidence.
    source_correlation = world.config.information.source_correlation.get(
        observation.source_type, .5)
    history = world.observation_source_index.get(index_key, ())
    corroboration_key = (
        "corroboration",
        observation.observation_id,
        world.next_observation_sequence,
    )
    corroboration = (
        world.information_execution_cache.get(corroboration_key)
        if world.information_cache_active else None
    )
    if corroboration is None:
        corroboration = _corroboration_weight(
            history,
            observation.timestamp,
            observation.source_id,
            source_correlation,
        )
        if world.information_cache_active:
            world.information_execution_cache[corroboration_key] = corroboration
    weight = clamp(observation.confidence * observation.quality * trust *
                   (language ** world.config.information.language_fusion_weight) * age_quality *
                   (1 + world.config.information.corroboration_bonus * min(3, corroboration)))
    if observation.observation_type in {"presence", "detection"}:
        _fuse_presence(world, observation, recipient_id, time, weight, node=node)
    # Detection/presence reports do not carry a control vector.  Avoid the
    # control-belief path entirely for those high-volume reports; this is a
    # pure dispatch optimization and leaves all reported values untouched.
    if ("control" in observation.estimated_value or
            "physical_control" in observation.estimated_value):
        _fuse_control(world, observation, recipient_id, time, weight)
    return weight


def _queue_relay(world: WorldState, observation: Observation, time: float) -> InformationRelay | None:
    observer = observation.observer_actor_id
    destination = f"CMD:{observer}"
    source = observation.observer_node_id or observation.source_id
    if source == destination:
        return None
    route, reliability, latency = command_path(world, observer, source, destination)
    if not route:
        # Reports from civilian, administrative, or elite channels have no
        # explicit node, so use a transparent organization-level fallback.
        route = [source, destination]
        reliability = world.config.information.relay_base_reliability
        organization = world.organizations.get(observer)
        if organization is not None:
            reliability *= .7 + .3 * organization.institutional_quality
        latency = 0.0
    if len(route) - 1 > world.config.information.relay_max_hops:
        route = route[:world.config.information.relay_max_hops + 1]
        reliability = max(.01, reliability)
    latency += world.config.information.source_latency_hours.get(
        observation.source_type, 0.0
    )
    relay_id = f"IR{world.next_information_relay_sequence:010d}"
    world.next_information_relay_sequence += 1
    relay = InformationRelay(
        relay_id, observation.observation_id, observer, source, destination,
        route, time, time + max(0.0, latency) / 24, clamp(reliability),
        max(0.0, latency),
    )
    world.information_relays[relay_id] = relay
    world.active_information_relays.add(relay_id)
    return relay


def ingest_observation(world: WorldState, observation: Observation,
                       time: float | None = None, rng: random.Random | None = None,
                       *, local_trust: float | None = None,
                       local_language: float | None = None) -> float:
    """Deliver an observation locally and enqueue its headquarters relay."""
    time = observation.timestamp if time is None else time
    observation.received_at = time
    headquarters = f"CMD:{observation.observer_actor_id}"
    if observation.observer_node_id and observation.observer_node_id != headquarters:
        # A field node receives the report immediately; headquarters gets only
        # the delayed relay below. This preserves organizational knowledge
        # geography instead of collapsing local and national beliefs.
        local_weight = fuse_observation(
            world, observation, observation.observer_node_id, time, node=True,
            trust_override=local_trust,
            language_override=local_language,
        )
    else:
        local_weight = fuse_observation(
            world, observation, observation.observer_actor_id, time,
            trust_override=local_trust,
            language_override=local_language,
        )
    _queue_relay(world, observation, time)
    return local_weight


def observe_target(world: WorldState, observer_actor_id: str, observer_node_id: str | None,
                   source_id: str, source_type: str, locality_id: str,
                   target_actor_id: str, time: float, rng: random.Random,
                   target_formation_id: str | None = None,
                   microzone_id: str | None = None,
                   record_negative: bool = True,
                   force_detection: bool | None = None,
                   formation_index: dict[tuple[str, str], list[ArmedFormation]] | None = None,
                   ) -> Observation | None:
    """Generate and ingest a positive/negative detection claim.

    Negative claims are retained as low-confidence evidence, allowing
    contradictory reports to increase uncertainty rather than triggering
    last-write-wins updates.  False positives carry no target formation ID and
    therefore never instantiate phantom world entities.
    """
    present, personnel, actual_id = _actual_target_presence(
        world, target_actor_id, locality_id, target_formation_id, microzone_id,
        formation_index,
    )
    if present:
        probability = detection_probability(
            world, observer_node_id or observer_actor_id, actual_id or target_formation_id,
            locality_id, source_type, microzone_id,
        )
    else:
        probability = false_positive_probability(
            world, observer_node_id or observer_actor_id, locality_id, source_type, microzone_id
        )
    detected = force_detection if force_detection is not None else rng.random() < probability
    outcome = (("true_positive" if detected else "false_negative") if present else
               ("false_positive" if detected else "true_negative"))
    if world.execution_profile != "particle":
        world.information_detections[outcome] += 1
        by_source = world.information_detection_by_source.setdefault(
            source_type, {"true_positive": 0, "false_positive": 0,
                          "false_negative": 0, "true_negative": 0}
        )
        by_source[outcome] += 1
    if not detected and not record_negative:
        return None
    quality = source_quality(world, observer_actor_id, source_type, locality_id, source_id, rng)
    trust = source_trust(world, observer_actor_id, source_type, locality_id, source_id)
    confidence = (world.config.information.positive_report_confidence if detected else
                  world.config.information.negative_report_confidence)
    # Personnel estimates are intentionally coarse and noisy; observers never
    # receive the exact formation personnel value.
    estimate = personnel * (0.65 + .7 * rng.random()) if detected else 0.0
    if not present and detected:
        estimate = max(1.0, rng.uniform(20.0, 250.0))
    attribution_mistake = bool(
        present and detected and
        rng.random() < world.config.information.attribution_error_rate
    )
    reported_target_actor = target_actor_id
    if attribution_mistake:
        alternate = "government" if _is_insurgent_actor(world, target_actor_id) else "insurgent"
        if alternate in world.organizations:
            reported_target_actor = alternate
    target_id = (actual_id if present and detected and target_formation_id is not None and
                 not attribution_mistake else target_formation_id
                 if target_formation_id is not None and not attribution_mistake else None)
    estimated = {
        "presence": 1.0 if detected else 0.0,
        "personnel": estimate,
        "detection_probability": probability,
        "detected": detected,
        "attribution_confidence": .25 if attribution_mistake else .9,
    }
    provenance = (
        {}
        if world.execution_profile == "particle"
        else {
            "source_type": source_type,
            "source_trust": trust,
            "language_comprehension": language_comprehension(
                world, observer_actor_id, locality_id, source_type, source_id
            ),
            "conditioned_probability": probability,
            "collection_context": (
                "formation_detection"
                if target_formation_id else "area_report"
            ),
        }
    )
    observation = _new_observation(
        world, observer_actor_id=observer_actor_id,
        observer_node_id=observer_node_id, target_id=target_id,
        target_actor_id=reported_target_actor, target_formation_id=target_id,
        locality_id=locality_id, microzone_id=microzone_id, timestamp=time,
        source_id=source_id, source_type=source_type, observation_type="detection",
        estimated_value=estimated, quality=quality, confidence=confidence,
        provenance=provenance,
    )
    ingest_observation(
        world, observation, time, rng,
        local_trust=trust,
    )
    return observation


def observe_control(world: WorldState, observer_actor_id: str, observer_node_id: str | None,
                    source_id: str, source_type: str, locality_id: str,
                    target_actor_id: str, time: float, rng: random.Random,
                    microzone_id: str | None = None) -> Observation:
    vector = world.localities[locality_id].control.get(target_actor_id, ControlVector())
    quality = source_quality(world, observer_actor_id, source_type, locality_id, source_id, rng)
    trust = source_trust(world, observer_actor_id, source_type, locality_id, source_id)
    language = language_comprehension(world, observer_actor_id, locality_id, source_type, source_id)
    noise = world.config.observation_noise * (1.35 - .55 * quality * language)
    # Preserve the historical dimension/RNG order without allocating an
    # intermediate ControlVector dictionary.
    estimated_control = {
        "formal": clamp(vector.formal + rng.uniform(-noise, noise)),
        "physical": clamp(vector.physical + rng.uniform(-noise, noise)),
        "administrative": clamp(
            vector.administrative + rng.uniform(-noise, noise)
        ),
        "legal": clamp(vector.legal + rng.uniform(-noise, noise)),
        "fiscal": clamp(vector.fiscal + rng.uniform(-noise, noise)),
        "social": clamp(vector.social + rng.uniform(-noise, noise)),
        "expected": clamp(vector.expected + rng.uniform(-noise, noise)),
    }
    observation = _new_observation(
        world, observer_actor_id=observer_actor_id,
        observer_node_id=observer_node_id, target_id=target_actor_id,
        target_actor_id=target_actor_id, target_formation_id=None,
        locality_id=locality_id, microzone_id=microzone_id, timestamp=time,
        source_id=source_id, source_type=source_type,
        observation_type="physical_control",
        estimated_value={"control": estimated_control,
                         "physical_control": estimated_control["physical"],
                         # Violence is a reported environmental signal, not a
                         # direct truth read by downstream political actors.
                         "violence": clamp(world.localities[locality_id].violence +
                                            rng.uniform(-noise, noise))},
        quality=quality, confidence=clamp(.45 + .45 * trust),
        provenance=(
            {}
            if world.execution_profile == "particle"
            else {
                "source_type": source_type,
                "source_trust": trust,
                "language_comprehension": language,
                "estimated_from": "locality_or_microzone_field",
            }
        ),
    )
    ingest_observation(
        world, observation, time, rng,
        local_trust=trust,
        local_language=language,
    )
    return observation


def observe_patrol(world: WorldState, patrol_id: str, time: float,
                   rng: random.Random) -> list[Observation]:
    patrol = world.patrols[patrol_id]
    formation = world.formations.get(patrol.formation_id)
    if formation is None or formation.moving:
        return []
    observer = formation.organization_id
    target_actors = _target_actors_for_observer(world, observer)
    observations: list[Observation] = []
    collect = rng.random() < world.config.information.patrol_report_rate
    if collect:
        for target_actor in target_actors:
            targets = [
                item for item in world.formations.values()
                if _formation_matches_target_actor(world, item, target_actor)
                and item.personnel > 0
                and item.locality_id == formation.locality_id
                and not item.moving
            ]
            if targets:
                for target in targets:
                    observation = observe_target(
                        world, observer, formation.formation_id, patrol_id, "patrol",
                        formation.locality_id, target_actor, time, rng,
                        target.formation_id, patrol.current_microzone_id, True,
                    )
                    if observation:
                        observations.append(observation)
            else:
                observation = observe_target(
                    world, observer, formation.formation_id, patrol_id, "patrol",
                    formation.locality_id, target_actor, time, rng,
                    None, patrol.current_microzone_id, True,
                )
                if observation:
                    observations.append(observation)
    if collect:
        observations.append(observe_control(
            world, observer, formation.formation_id, patrol_id, "patrol",
            formation.locality_id,
            ("insurgent" if _is_insurgent_actor(world, observer) else "government"),
            time, rng, microzone_id=patrol.current_microzone_id,
        ))
    return observations


def _report_probability(world: WorldState, observer_actor_id: str, locality_id: str,
                        source_type: str, source_id: str | None) -> float:
    cache_key = ("report", observer_actor_id, locality_id, source_type, source_id)
    if world.information_cache_active:
        cached = world.information_execution_cache.get(cache_key)
        if cached is not None:
            if world.performance_counters is not None:
                world.performance_counters["information_report_cache_hit"] = (
                    world.performance_counters.get("information_report_cache_hit", 0) + 1
                )
            return float(cached)
        if world.performance_counters is not None:
            world.performance_counters["information_report_cache_miss"] = (
                world.performance_counters.get("information_report_cache_miss", 0) + 1
            )
    config = world.config.information
    rates = {
        "civilian": config.civilian_report_rate,
        "social_network": config.social_report_rate,
        "administrative": config.administrative_report_rate,
        "political_elite": config.elite_report_rate,
        "organization_member": config.member_report_rate,
        "fixed_post": config.fixed_post_report_rate,
        "interpreter": config.interpreter_report_rate,
    }
    probability = rates.get(source_type, .2)
    locality = world.localities[locality_id]
    if source_type == "administrative":
        probability *= .35 + .95 * clamp(locality.administrative_capacity)
    elif source_type == "political_elite":
        elite_access = clamp(
            locality.governance.get(
                "elite_access_capacity", 1.0 if locality.population > 0 else 0.0
            )
        )
        probability *= (
            (.45 + .65 * clamp(locality.governance.get("representation", .5))) *
            elite_access
        )
    if source_id in world.social_communities:
        community = world.social_communities[source_id]
        cooperation = (community.government_cooperation if not _is_insurgent_actor(world, observer_actor_id)
                       else community.insurgent_sympathy)
        probability *= .35 + 1.1 * clamp(cooperation)
    # Source-availability priors were introduced on the original six-hour
    # information collection cycle.  Preserve that reference-period meaning
    # when the numerical information scheduler is refined or coarsened.
    result = reference_probability(
        clamp(probability),
        world.config.intervals.information,
        0.25,
    )
    if world.information_cache_active:
        world.information_execution_cache[cache_key] = result
    return result


def _observe_from_source(world: WorldState, observer_actor_id: str, observer_node_id: str | None,
                         source_id: str, source_type: str, locality_id: str,
                         time: float, rng: random.Random,
                         formation_index: dict[tuple[str, str], list[ArmedFormation]] | None = None,
                         target_actor_cache: dict[str, tuple[str, ...]] | None = None,
                         ) -> list[Observation]:
    target_actors = (
        target_actor_cache.get(observer_actor_id)
        if target_actor_cache is not None else None
    )
    if target_actors is None:
        target_actors = _target_actors_for_observer(world, observer_actor_id)
        if target_actor_cache is not None:
            target_actor_cache[observer_actor_id] = target_actors
    local_node = observer_node_id or source_id
    if rng.random() >= _report_probability(
            world, observer_actor_id, locality_id, source_type, source_id):
        return []
    if not target_actors:
        # A no-insurgency world still has administrative and physical
        # information; it simply cannot emit a claim about a nonexistent
        # opposing organization.
        target_control = (observer_actor_id if observer_actor_id in
                          world.localities[locality_id].control else "government")
        return [observe_control(
            world, observer_actor_id, local_node, source_id, source_type,
            locality_id, target_control, time, rng, _primary_zone(world, locality_id),
        )]
    microzone = _primary_zone(world, locality_id)
    observations: list[Observation] = []
    for target_actor in target_actors:
        targets = (
            list(formation_index.get((target_actor, locality_id), ()))
            if formation_index is not None
            else [
                formation for formation in world.formations.values()
                if _formation_matches_target_actor(world, formation, target_actor)
                and formation.personnel > 0
                and formation.locality_id == locality_id
                and not formation.moving
            ]
        )
        target_id = (
            targets[0].formation_id
            if targets and source_type in {"organization_member", "interpreter"}
            else None
        )
        observations.append(observe_target(
            world, observer_actor_id, local_node, source_id, source_type,
            locality_id, target_actor, time, rng, target_id, microzone, True,
            formation_index=formation_index,
        ))
    observations.append(observe_control(
        world, observer_actor_id, local_node, source_id, source_type,
        locality_id, observer_actor_id if observer_actor_id in world.localities[locality_id].control
        else "government", time, rng, microzone,
    ))
    return [observation for observation in observations if observation is not None]


def generate_background_observations(world: WorldState, time: float,
                                     rng: random.Random | None = None) -> list[Observation]:
    """Generate fixed-post, civilian, social, administrative, elite, and member reports."""
    rng = rng or seeded_rng(world.config, f"information:{time:.6f}")
    observations: list[Observation] = []
    formation_index = _information_formation_index(world)
    target_actor_cache: dict[str, tuple[str, ...]] = {}
    active_insurgent_ids = (
        world.active_insurgent_organization_ids
        if world.execution_profile == "particle"
        else tuple(sorted(
            organization.organization_id
            for organization in world.organizations.values()
            if (
                organization.kind is OrganizationKind.INSURGENT
                and organization.status == "active"
            )
        ))
    )
    for post in sorted(world.security_posts.values(), key=lambda item: item.post_id):
        if post.available_fraction <= 0:
            continue
        observer = post.organization_id
        formation = world.formations.get(post.formation_id) if post.formation_id else None
        if formation and (formation.moving or formation.available_personnel() <= 0):
            continue
        observations.extend(_observe_from_source(
            world, observer, post.formation_id or post.post_id, post.post_id,
            "fixed_post", post.locality_id, time, rng,
            formation_index, target_actor_cache,
        ))

    for locality_id in (
        world.ordered_locality_ids or tuple(sorted(world.localities))
    ):
        community_ids = world.social_community_ids_by_locality.get(locality_id)
        communities = (
            [world.social_communities[community_id] for community_id in community_ids]
            if community_ids is not None else
            [community for community in world.social_communities.values()
             if community.locality_id == locality_id]
        )
        if not communities:
            # Administrative, elite-brokerage, and interpretation channels are
            # locality capabilities, not literal sampled civilians.  Preserve
            # them in populated coarse-resolution localities even when no
            # representative resident/community happened to be instantiated.
            if "government" in world.organizations:
                observations.extend(_observe_from_source(
                    world, "government", None, f"ADMIN:{locality_id}",
                    "administrative", locality_id, time, rng,
                    formation_index, target_actor_cache,
                ))
                if clamp(world.localities[locality_id].governance.get(
                        "elite_access_capacity",
                        1.0 if world.localities[locality_id].population > 0 else 0.0)):
                    observations.extend(_observe_from_source(
                        world, "government", None, f"ELITE-CAP:{locality_id}",
                        "political_elite", locality_id, time, rng,
                        formation_index, target_actor_cache,
                    ))
                if (
                    locality_id in world.multilingual_locality_ids
                    and world.localities[locality_id].population > 0
                ):
                    observations.extend(_observe_from_source(
                        world, "government", None, f"INTERPRETER-CAP:{locality_id}",
                        "interpreter", locality_id, time, rng,
                        formation_index, target_actor_cache,
                    ))
            continue
        if len(communities) == 1:
            # random.choices on a one-element population still consumes one
            # RNG draw even though the result cannot vary. Preserve that draw
            # exactly while avoiding a pointless represented-weight reduction.
            rng.random()
            community = communities[0]
        else:
            community = rng.choices(
                communities,
                weights=[
                    max(
                        1.0,
                        world.represented_weight_by_community.get(
                            item.community_id,
                            sum(
                                world.persons[pid].weight
                                for pid in item.member_ids
                            ),
                        ),
                    )
                    for item in communities
                ],
                k=1,
            )[0]
        # Civilian and social channels are deliberately independent: cooperation
        # improves source access, but neither channel creates physical presence.
        for source_type in ("civilian", "social_network"):
            if "government" in world.organizations:
                observations.extend(_observe_from_source(
                    world, "government", None, community.community_id, source_type,
                    locality_id, time, rng,
                    formation_index, target_actor_cache,
                ))
        if "government" in world.organizations:
            for source_type, source_id in (
                ("administrative", f"ADMIN:{locality_id}"),
                ("political_elite", f"ELITE:{community.community_id}"),
            ):
                observations.extend(_observe_from_source(
                    world, "government", None, source_id, source_type,
                    locality_id, time, rng,
                    formation_index, target_actor_cache,
                ))
        for insurgent_id in active_insurgent_ids:
            observations.extend(_observe_from_source(
                world, insurgent_id, None, community.community_id, "civilian",
                locality_id, time, rng,
                formation_index, target_actor_cache,
            ))
        # A bridge/interpreter channel is only sampled where language diversity
        # makes it meaningful; it degrades less than an untranslated report.
        if (
            locality_id in world.multilingual_locality_ids
            and "government" in world.organizations
        ):
            observations.extend(_observe_from_source(
                world, "government", None, community.community_id, "interpreter",
                locality_id, time, rng,
                formation_index, target_actor_cache,
            ))

    for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
        if formation.moving or formation.available_personnel() <= 0:
            continue
        observations.extend(_observe_from_source(
            world, formation.organization_id, formation.formation_id,
            formation.formation_id, "organization_member", formation.locality_id,
            time, rng,
            formation_index, target_actor_cache,
        ))
    return observations


def _decay_belief_container(container: dict, time: float, rate: float) -> None:
    for belief in container.values():
        if not hasattr(belief, "confidence"):
            continue
        # The caller supplies the elapsed interval externally; this function is
        # retained for readable separation in decay_information.
        belief.confidence = clamp(belief.confidence * exp(-rate))


def decay_information(world: WorldState, time: float) -> None:
    """Age confidence without overwriting the estimate itself."""
    previous = getattr(world, "last_information_decay_at", 0.0)
    elapsed = max(0.0, time - previous)
    if elapsed <= 0:
        return
    config = world.config.information
    default_factor = exp(-config.default_decay_rate * elapsed)
    formation_factor = exp(-config.formation_decay_rate * elapsed)
    for belief in world.beliefs.values():
        belief.confidence = clamp(belief.confidence * default_factor)
    for belief in getattr(world, "control_beliefs", {}).values():
        belief.confidence = clamp(belief.confidence * default_factor)
    for belief in world.zone_beliefs.values():
        belief.confidence = clamp(belief.confidence * formation_factor)
    for belief in world.presence_beliefs.values():
        factor = formation_factor if belief.target_id else default_factor
        belief.confidence = clamp(belief.confidence * factor)
    for belief in world.node_presence_beliefs.values():
        factor = formation_factor if belief.target_id else default_factor
        belief.confidence = clamp(belief.confidence * factor)
    world.last_information_decay_at = time


def process_information(world: WorldState, time: float,
                        rng: random.Random | None = None) -> dict[str, Any]:
    """Age beliefs, generate reports, and deliver due command-network relays."""
    rng = rng or seeded_rng(world.config, f"information-process:{time:.6f}")
    if world.execution_profile == "particle":
        world.refresh_operational_indexes()
    world.information_execution_cache.clear()
    world.information_cache_active = True
    batch_control = (
        world.execution_backend == "optimized"
        and world.execution_profile == "particle"
        and native_control_batch_enabled()
    )
    world.defer_control_fusions = batch_control
    world.deferred_control_fusions.clear()
    try:
        decay_information(world, time)
        generated = generate_background_observations(world, time, rng)
        delivered = dropped = 0
        delivered_ids: list[str] = []
        for relay_id in sorted(world.active_information_relays):
            relay = world.information_relays.get(relay_id)
            if relay is None or relay.status != "in_transit":
                world.active_information_relays.discard(relay_id)
                continue
            if relay.arrives_at > time:
                continue
            observation = world.observations.get(relay.observation_id)
            if observation is None:
                relay.status = "dropped"
                world.active_information_relays.discard(relay_id)
                dropped += 1
                continue
            if rng.random() <= relay.reliability:
                relay.status = "delivered"
                world.active_information_relays.discard(relay_id)
                relay.delivered_at = time
                observation.received_at = time
                fuse_observation(world, observation, relay.organization_id, time)
                fuse_observation(world, observation, relay.destination_node_id, time, node=True)
                source_org = world.organizations.get(observation.observer_actor_id)
                if (source_org is not None and source_org.kind is not OrganizationKind.INSURGENT and
                        "government" in world.organizations):
                    # Government headquarters receives subordinate security reports
                    # through the command relay; it does not read the hidden state.
                    fuse_observation(world, observation, "government", time)
                delivered += 1
                delivered_ids.append(observation.observation_id)
            else:
                relay.status = "dropped"
                world.active_information_relays.discard(relay_id)
                dropped += 1
        flushed_control_fusions = _flush_control_fusions(world)
        _prune_information_history(world, time)
        return {"generated": len(generated),
                "observation_ids": tuple(item.observation_id for item in generated),
                "relays_delivered": delivered,
                "delivered_observation_ids": tuple(delivered_ids),
                "relays_dropped": dropped,
                "active_relays": len(world.active_information_relays),
                "control_fusions": flushed_control_fusions}
    finally:
        world.defer_control_fusions = False
        world.deferred_control_fusions.clear()
        world.information_execution_cache.clear()
        world.information_cache_active = False


def _prune_information_history(world: WorldState, time: float) -> None:
    """Bound optional evidence storage without changing beliefs or RNG draws.

    Reports remain available until their configured retention horizon and all
    in-transit relays are retained.  The default horizon is zero (no pruning),
    preserving forensic behavior.  This is used by long ensemble runs where
    the estimand is recorded target streams and checkpoint state, not an
    unbounded raw evidence archive.
    """
    retention = world.config.information.observation_retention_days
    if retention <= 0 or time <= retention:
        return
    # Information updates can run several times per simulated day.  Pruning
    # every update repeatedly scanned the complete 90-day archive and made
    # long trajectories superlinear in wall time.  Integer-day pruning keeps
    # the same bounded archive at daily checkpoints/final integer horizons,
    # while retention remains an output-only concern.
    if abs(time - round(time)) > 1e-9:
        return
    cutoff = time - retention
    pending_observations = {
        world.information_relays[relay_id].observation_id
        for relay_id in world.active_information_relays
        if relay_id in world.information_relays
    }
    # Observations and relays are inserted in scheduler-time order.  Stop at
    # the first retained timestamp instead of scanning the entire live window.
    stale = []
    for observation_id, observation in world.observations.items():
        if observation.timestamp >= cutoff:
            break
        if observation_id not in pending_observations:
            stale.append(observation_id)
    for observation_id in stale:
        world.observations.pop(observation_id, None)
    for key, timestamps in list(world.observation_index.items()):
        world.observation_index[key] = [stamp for stamp in timestamps if stamp >= cutoff]
        if not world.observation_index[key]:
            world.observation_index.pop(key, None)
    for key, history in list(world.observation_source_index.items()):
        while history and history[0][0] < cutoff:
            history.popleft()
        if not history:
            world.observation_source_index.pop(key, None)
    stale_relays = []
    for relay_id, relay in world.information_relays.items():
        if relay.sent_at >= cutoff:
            break
        if relay.status in {"delivered", "dropped"}:
            stale_relays.append(relay_id)
    for relay_id in stale_relays:
        world.information_relays.pop(relay_id, None)


def information_age(world: WorldState, observer_id: str, locality_id: str,
                    target_actor_id: str | None = None, target_id: str | None = None,
                    time: float | None = None, node: bool = False) -> float:
    """Return age in days of the last reliable observation, or infinity."""
    time = world.time if time is None else time
    target_actor_id = target_actor_id or _target_actor_for_observer(world, observer_id)
    if target_actor_id is None:
        return float("inf")
    container = world.node_presence_beliefs if node else world.presence_beliefs
    candidates = [belief for belief in container.values()
                  if belief.observer_id == observer_id and
                  belief.target_actor_id == target_actor_id and
                  belief.locality_id == locality_id and
                  (target_id is None or belief.target_id == target_id)]
    if not candidates:
        belief = world.control_beliefs.get((observer_id, target_actor_id, locality_id)) \
            if hasattr(world, "control_beliefs") else None
        last = belief.last_reliable_observation_at if belief else -1.0e9
    else:
        last = max(item.last_reliable_observation_at for item in candidates)
    return float("inf") if last < -1.0e8 else max(0.0, time - last)


def _true_presence(world: WorldState, target_actor_id: str, locality_id: str) -> float:
    present, _, _ = _actual_target_presence(world, target_actor_id, locality_id)
    return 1.0 if present else 0.0


def belief_error(world: WorldState, observer_id: str, locality_id: str,
                 target_actor_id: str | None = None) -> float:
    """Analyst-only mean absolute error for a locality belief."""
    target_actor_id = target_actor_id or _target_actor_for_observer(world, observer_id)
    if target_actor_id is None:
        return 0.0
    control = world.localities[locality_id].control.get(target_actor_id, ControlVector())
    belief = (world.control_beliefs.get((observer_id, target_actor_id, locality_id))
              if hasattr(world, "control_beliefs") else None)
    if belief is None:
        return 1.0
    dimensions = control.to_dict()
    estimate = belief.control_estimate.to_dict()
    return sum(abs(estimate[key] - dimensions[key]) for key in dimensions) / len(dimensions)


def _belief_record(belief: Any, time: float) -> dict[str, Any]:
    last = getattr(belief, "last_reliable_observation_at", -1.0e9)
    return {
        "estimate": (belief.presence_estimate if hasattr(belief, "presence_estimate")
                     else belief.control_estimate.to_dict()),
        "confidence": belief.confidence,
        "updated_at": belief.updated_at,
        "last_reliable_observation_at": None if last < -1.0e8 else last,
        "age_days": None if last < -1.0e8 else max(0.0, time - last),
        "evidence_count": belief.evidence_count,
        "contradiction_index": belief.contradiction_index,
    }


def information_diagnostics(world: WorldState) -> dict[str, Any]:
    """Return analyst-facing information age, error, source, and relay measures."""
    by_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for observation in world.observations.values():
        by_type[observation.observation_type] = by_type.get(observation.observation_type, 0) + 1
        by_source[observation.source_type] = by_source.get(observation.source_type, 0) + 1
    ages: dict[str, dict[str, float]] = {}
    node_ages: dict[str, dict[str, float]] = {}
    errors: dict[str, dict[str, float]] = {}
    confidence: dict[str, dict[str, float]] = {}
    for observer_id in sorted(world.organizations):
        ages[observer_id] = {}
        errors[observer_id] = {}
        confidence[observer_id] = {}
        for locality_id in sorted(world.localities):
            age = information_age(world, observer_id, locality_id, time=world.time)
            ages[observer_id][locality_id] = age
            errors[observer_id][locality_id] = belief_error(world, observer_id, locality_id)
            target = _target_actor_for_observer(world, observer_id)
            belief = (world.control_beliefs.get((observer_id, target, locality_id))
                      if target and hasattr(world, "control_beliefs") else None)
            confidence[observer_id][locality_id] = belief.confidence if belief else 0.0
    for belief in world.node_presence_beliefs.values():
        last = belief.last_reliable_observation_at
        age = float("inf") if last < -1.0e8 else max(0.0, world.time - last)
        node_ages.setdefault(belief.observer_id, {})[belief.locality_id] = min(
            age, node_ages.get(belief.observer_id, {}).get(belief.locality_id, float("inf"))
        )
    return {
        "observations": len(world.observations),
        "observations_by_type": by_type,
        "observations_by_source": by_source,
        "relays": {relay_id: asdict(relay)
                    for relay_id, relay in world.information_relays.items()},
        "active_relays": sum(relay.status == "in_transit"
                              for relay in world.information_relays.values()),
        "information_age": ages,
        "node_information_age": node_ages,
        "belief_error": errors,
        "belief_confidence": confidence,
        "control_beliefs": {
            ":".join(key): _belief_record(belief, world.time)
            for key, belief in world.control_beliefs.items()
        },
        "detection_counts": dict(world.information_detections),
        "detection_counts_by_source": {
            source: dict(counts)
            for source, counts in world.information_detection_by_source.items()
        },
        "presence_beliefs": {
            ":".join(key): _belief_record(belief, world.time)
            for key, belief in world.presence_beliefs.items()
        },
        "node_presence_beliefs": {
            ":".join(key): _belief_record(belief, world.time)
            for key, belief in world.node_presence_beliefs.items()
        },
    }
