"""Belief-based, budget-constrained organized action support.

The module deliberately reuses Pineland's existing organizational accounts.
Represented membership is *not* added to fighter equivalents: local action
capacity is the sum of unfielded fighter-equivalent pools and locally fielded
personnel exactly once.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, expm1
import random

from .entities import OrganizationKind, clamp
from .relations import organizations_hostile
from .organizational_state import (
    local_operational_knowledge,
    local_organizational_embeddedness,
    local_foothold_strength,
)
from .logistics import shortest_locality_path
from .access import edge_restriction_level


ACTION_ORGANIZATION_KINDS = {
    OrganizationKind.INSURGENT,
    OrganizationKind.MILITARY,
    OrganizationKind.POLICE,
    OrganizationKind.FOREIGN,
}

ACTION_CHANNELS = (
    "wait",
    "armed_confrontation",
    "nonfielded_human_target",
    "asset_violence",
    "coercion",
    "access_restriction",
)
VIOLENT_CHANNELS = {
    "armed_confrontation",
    "nonfielded_human_target",
    "asset_violence",
}


def _local_formations(world, locality_id: str):
    """Iterate one locality's formations using the maintained runtime index."""
    # Particle/core execution routes all relocations through WorldState helpers
    # and can trust the maintained index.  Standard/test worlds intentionally
    # permit direct entity mutation by policy/test hooks; preserve that public
    # fallback semantics by scanning there.
    formation_ids = (
        world.formation_ids_by_locality.get(locality_id)
        if world.execution_profile == "particle"
        else None
    )
    if formation_ids is None:
        return (
            formation for formation in world.formations.values()
            if formation.locality_id == locality_id
        )
    return (
        world.formations[formation_id]
        for formation_id in formation_ids
        if formation_id in world.formations
    )


def operational_reach_candidates(
    world, organization_id: str, source_locality_id: str
) -> list[tuple[str, float]]:
    """Same-locality plus one-hop operational reach using existing mobility.

    This is tactical/operational reach, not strategic relocation.  Adjacent
    reach is attenuated by actual travel time and hostile corridor restriction.
    No new distance coefficient is introduced: one day is the action clock.
    """
    organization = world.organizations[organization_id]
    rows = [(source_locality_id, 1.0)]
    for destination_id in sorted(world.adjacency.get(source_locality_id, {})):
        route, _, travel_hours = shortest_locality_path(
            world,
            source_locality_id,
            destination_id,
            organization.mobility,
        )
        restriction = edge_restriction_level(
            world,
            source_locality_id,
            destination_id,
            organization_id,
        )
        adjusted_hours = travel_hours * (
            1.0
            + world.config.access_restriction.hostile_movement_penalty
            * restriction
        )
        rows.append(
            (destination_id, exp(-max(0.0, adjusted_hours) / 24.0))
        )
    return rows


def _target_belief_weight(
    world,
    organization_id: str,
    locality_id: str,
    channel: str,
) -> float:
    organization = world.organizations[organization_id]
    target_side = _opponent_side(organization.kind)
    belief = world.belief_view(organization_id).locality_control(
        locality_id, target_side
    )
    hostile_beliefs = _evidenced_hostile_control_beliefs(
        world, organization_id, locality_id
    )
    if channel == "nonfielded_human_target":
        signal = clamp((belief.formal + belief.physical) / 2.0)
        if hostile_beliefs:
            signal = max(
                signal,
                max(
                    clamp((item.formal + item.physical) / 2.0)
                    for item in hostile_beliefs
                ),
            )
        return signal
    if channel == "asset_violence":
        return clamp(
            (belief.administrative + belief.legal + belief.fiscal) / 3.0
        )
    return 0.0


def _has_local_target_evidence(
    world,
    organization_id: str,
    locality_id: str,
) -> bool:
    organization = world.organizations[organization_id]
    target_side = _opponent_side(organization.kind)
    targets = {target_side, *_hostile_target_ids(world, organization_id)}
    for target_id in targets:
        belief = world.control_beliefs.get(
            (organization_id, target_id, locality_id)
        )
        if belief is not None and belief.evidence_count > 0:
            return True
    observer_ids = {organization_id}
    observer_ids.update(
        formation.formation_id
        for formation in world.formations.values()
        if formation.organization_id == organization_id
    )
    return any(
        belief.observer_id in observer_ids
        and belief.locality_id == locality_id
        and belief.target_actor_id in targets
        and belief.evidence_count > 0
        for belief in (
            *world.presence_beliefs.values(),
            *world.node_presence_beliefs.values(),
        )
    )


def reachable_target_belief(
    world,
    organization_id: str,
    source_locality_id: str,
    channel: str,
) -> float:
    return max(
        (
            reach
            * (
                _target_belief_weight(
                    world, organization_id, locality_id, channel
                )
                if (
                    locality_id == source_locality_id
                    or _has_local_target_evidence(
                        world, organization_id, locality_id
                    )
                )
                else 0.0
            )
            for locality_id, reach in operational_reach_candidates(
                world, organization_id, source_locality_id
            )
        ),
        default=0.0,
    )


def choose_operational_target_locality(
    world,
    organization_id: str,
    source_locality_id: str,
    channel: str,
    rng: random.Random,
) -> tuple[str, float]:
    candidates = operational_reach_candidates(
        world, organization_id, source_locality_id
    )
    weights = [
        reach
        * (
            _target_belief_weight(
                world, organization_id, locality_id, channel
            )
            if (
                locality_id == source_locality_id
                or _has_local_target_evidence(
                    world, organization_id, locality_id
                )
            )
            else 0.0
        )
        for locality_id, reach in candidates
    ]
    if sum(weights) <= 0:
        return source_locality_id, 1.0
    selected = rng.choices(
        list(range(len(candidates))), weights=weights, k=1
    )[0]
    return candidates[selected]


@dataclass(frozen=True, slots=True)
class LocalActionSupport:
    organization_id: str
    locality_id: str
    unfielded_fighter_equivalents: float
    fielded_fighter_equivalents: float
    nonfielded_target_personnel: float
    asset_target_count: int
    susceptible_population: float
    armed_confrontation: bool
    nonfielded_human_target: bool
    government_asset_target: bool
    civilian_coercion: bool
    access_restriction: bool

    @property
    def total_fighter_equivalents(self) -> float:
        return self.unfielded_fighter_equivalents + self.fielded_fighter_equivalents

    @property
    def nonfielded_government_target(self) -> bool:
        return self.nonfielded_human_target

    @property
    def civilian_coercion_or_extraction(self) -> bool:
        return self.civilian_coercion

    @property
    def government_security_post_personnel(self) -> float:
        return self.nonfielded_target_personnel

    @property
    def government_institution_count(self) -> int:
        return self.asset_target_count

    @property
    def civilian_population(self) -> float:
        return self.susceptible_population


@dataclass(frozen=True, slots=True)
class NonfieldedHumanTarget:
    target_id: str
    target_type: str
    organization_id: str
    personnel: float
    available_fraction: float
    backing_post_id: str | None = None
    backing_pool_key: tuple[str, str] | None = None


def local_fighter_equivalents(world, organization_id: str, locality_id: str) -> tuple[float, float]:
    """Return local *equipped* unfielded and fielded fighter equivalents."""
    pooled_manpower = max(
        0.0,
        float(world.organization_manpower_pools.get((organization_id, locality_id), 0.0)),
    )
    supply_per_fighter = max(
        1e-12,
        float(world.config.logistics.formation_supply_days)
        * float(world.config.logistics.initial_supply_fraction),
    )
    reserve = max(
        0.0,
        float(world.organization_manpower_supply_reserves.get((organization_id, locality_id), 0.0)),
    )
    unfielded = min(pooled_manpower, reserve / supply_per_fighter)
    fielded = sum(
        max(0.0, float(formation.personnel))
        for formation in _local_formations(world, locality_id)
        if formation.organization_id == organization_id
        and not formation.outside_pineland
        and not formation.moving
    )
    return unfielded, fielded


def national_fighter_equivalents(world, organization_id: str) -> float:
    localities = {
        locality_id
        for (owner, locality_id), quantity in world.organization_manpower_pools.items()
        if owner == organization_id and quantity > 0
    }
    pooled = sum(
        local_fighter_equivalents(world, organization_id, locality_id)[0]
        for locality_id in localities
    )
    fielded = sum(
        max(0.0, float(formation.personnel))
        for formation in world.formations.values()
        if formation.organization_id == organization_id
    )
    return pooled + fielded


def capacity_saturation(world, organization_id: str, locality_id: str) -> float:
    """Smooth capability scale; formation thresholds never switch all action on/off."""
    unfielded, fielded = local_fighter_equivalents(world, organization_id, locality_id)
    total = unfielded + fielded
    if total <= 0:
        return 0.0
    scale = max(1e-9, float(world.config.organization_ecology.minimum_formation_personnel))
    return clamp(total / (total + scale))


def committed_fighter_equivalents(world, organization_id: str, locality_id: str) -> float:
    unfielded, fielded = local_fighter_equivalents(world, organization_id, locality_id)
    total = unfielded + fielded
    return total * capacity_saturation(world, organization_id, locality_id)


def local_action_supply_available(world, organization_id: str, locality_id: str) -> float:
    """Return material stock physically available to this organization locally."""
    formation_stock = sum(
        max(0.0, float(formation.supply_stock))
        for formation in _local_formations(world, locality_id)
        if formation.organization_id == organization_id
        and not formation.outside_pineland
        and not formation.moving
    )
    source_stock = sum(
        max(0.0, float(source.stock))
        for source in world.supply_sources.values()
        if source.organization_id == organization_id
        and source.locality_id == locality_id
    )
    reserve_stock = max(
        0.0,
        float(world.organization_manpower_supply_reserves.get((organization_id, locality_id), 0.0)),
    )
    return formation_stock + source_stock + reserve_stock


def consume_local_action_supply(
    world, organization_id: str, locality_id: str, demand: float
) -> tuple[float, float]:
    """Consume local military material once for a selected non-battle violent action."""
    remaining = max(0.0, float(demand))
    demanded = remaining
    consumed = 0.0
    for formation in sorted(_local_formations(world, locality_id), key=lambda item: item.formation_id):
        if (
            remaining <= 0
            or formation.organization_id != organization_id
            or formation.outside_pineland
            or formation.moving
        ):
            continue
        take = min(max(0.0, formation.supply_stock), remaining)
        formation.supply_stock -= take
        formation.sustainment = formation.supply_fraction()
        consumed += take
        remaining -= take
    for source in sorted(world.supply_sources.values(), key=lambda item: item.source_id):
        if (
            remaining <= 0
            or source.organization_id != organization_id
            or source.locality_id != locality_id
        ):
            continue
        take = min(max(0.0, source.stock), remaining)
        source.stock -= take
        consumed += take
        remaining -= take
    if remaining > 0:
        key = (organization_id, locality_id)
        reserve = max(0.0, world.organization_manpower_supply_reserves.get(key, 0.0))
        take = min(reserve, remaining)
        reserve -= take
        consumed += take
        remaining -= take
        if reserve > 1e-12:
            world.organization_manpower_supply_reserves[key] = reserve
        else:
            world.organization_manpower_supply_reserves.pop(key, None)
    world.cumulative_supply_consumed += consumed
    return consumed, max(0.0, demanded - consumed)


def action_attempt_hazard(world, organization_id: str, locality_id: str) -> float:
    """Return the organized-action opportunity hazard per day.

    This is the intensity already implied by ``organized_action_rate`` and the
    local equipped fighter-equivalent stock.  Keeping the intensity available
    separately lets a filter marginalize multiple opportunities instead of
    estimating their aggregate with a small number of full descendants.
    """
    rate = max(0.0, float(world.config.organized_action_rate))
    # organized_action_rate is an opportunity rate for one minimally viable action
    # unit. Saturation discounts tiny/unformed stocks; committed equivalents
    # then preserve the number of independently usable units. Using saturation
    # alone collapsed 500 and 2,625 fighters to almost the same opportunity
    # rate and severed organizational scale from realized action.
    minimum_unit = max(
        1e-9,
        float(world.config.organization_ecology.minimum_formation_personnel),
    )
    active_units = committed_fighter_equivalents(
        world, organization_id, locality_id
    ) / minimum_unit
    return max(0.0, rate * active_units)


def action_attempt_probability(world, organization_id: str, locality_id: str,
                               interval_days: float) -> float:
    """Continuous-time action opportunity over ``interval_days``.

    The public probability API remains unchanged; its rate form is exposed by
    :func:`action_attempt_hazard` for Rao--Blackwellized filters.
    """
    if interval_days <= 0:
        return 0.0
    return clamp(-expm1(
        -action_attempt_hazard(world, organization_id, locality_id)
        * float(interval_days)
    ))


def action_execution_hazard(
    world,
    organization_id: str,
    locality_id: str,
    interval_days: float,
    *,
    execution_probability: float = 1.0,
) -> float:
    """Expected realized-action hazard after an execution gate.

    ``execution_probability`` is conditional on an opportunity and therefore
    multiplies the opportunity intensity exactly once.  Callers that have not
    yet selected a target should use the opportunity hazard and apply the
    target/execution gate later.
    """
    if interval_days <= 0:
        return 0.0
    return action_attempt_hazard(world, organization_id, locality_id) * clamp(
        float(execution_probability)
    )


def _opponent_side(organization_kind: OrganizationKind) -> str:
    return "government" if organization_kind is OrganizationKind.INSURGENT else "insurgent"


def _target_matches_side(world, target_actor_id: str, target_side: str) -> bool:
    if target_actor_id == target_side:
        return True
    target = world.organizations.get(target_actor_id)
    if target is None:
        return False
    if target_side == "insurgent":
        return target.kind is OrganizationKind.INSURGENT and target.status == "active"
    return target.kind in {
        OrganizationKind.GOVERNMENT,
        OrganizationKind.MILITARY,
        OrganizationKind.POLICE,
        OrganizationKind.FOREIGN,
    }


def _hostile_target_ids(world, organization_id: str) -> list[str]:
    return sorted(
        other.organization_id
        for other in world.organizations.values()
        if (
            other.organization_id != organization_id
            and other.status == "active"
            and other.kind in ACTION_ORGANIZATION_KINDS | {OrganizationKind.GOVERNMENT}
            and organizations_hostile(world, organization_id, other.organization_id)
        )
    )


def _evidenced_hostile_control_beliefs(
    world, organization_id: str, locality_id: str
) -> list:
    """Concrete hostile beliefs only when backed by local actor evidence."""
    rows = []
    for target_id in _hostile_target_ids(world, organization_id):
        belief = world.control_beliefs.get(
            (organization_id, target_id, locality_id)
        )
        if belief is not None and belief.evidence_count > 0:
            rows.append(belief.control_estimate)
    return rows


def _opponent_presence_belief(
    world, organization_id: str, locality_id: str, target_side: str
) -> float:
    """Actor-held opponent-presence estimate; never consult target truth."""
    values = []
    observer_ids = {organization_id}
    observer_ids.update(
        formation.formation_id
        for formation in world.formations.values()
        if formation.organization_id == organization_id
    )
    for belief in (*world.presence_beliefs.values(), *world.node_presence_beliefs.values()):
        if (
            belief.observer_id in observer_ids
            and belief.locality_id == locality_id
            and belief.evidence_count > 0
        ):
            if _target_matches_side(world, belief.target_actor_id, target_side):
                values.append(clamp(belief.presence_estimate))
    if values:
        return max(values)
    return clamp(
        world.belief_view(organization_id)
        .locality_control(locality_id, target_side)
        .physical
    )


def action_choice_weights(world, organization_id: str, locality_id: str) -> dict[str, float]:
    """Return actor-facing choice weights using beliefs plus known own capacity only."""
    organization = world.organizations[organization_id]
    if organization.kind not in ACTION_ORGANIZATION_KINDS or organization.status != "active":
        return {channel: float(channel == "wait") for channel in ACTION_CHANNELS}
    unfielded, fielded = local_fighter_equivalents(world, organization_id, locality_id)
    total = unfielded + fielded
    if total <= 0:
        return {channel: float(channel == "wait") for channel in ACTION_CHANNELS}

    target_side = _opponent_side(organization.kind)
    belief = world.belief_view(organization_id).locality_control(locality_id, target_side)
    perceived_presence = _opponent_presence_belief(
        world, organization_id, locality_id, target_side
    )
    hostile_beliefs = _evidenced_hostile_control_beliefs(
        world, organization_id, locality_id
    )
    if hostile_beliefs:
        perceived_presence = max(
            perceived_presence,
            max(clamp(item.physical) for item in hostile_beliefs),
        )
    risk = clamp(organization.phenotype.get("risk_tolerance", 0.5))
    embedded = max(
        local_organizational_embeddedness(world, organization_id, locality_id),
        local_foothold_strength(world, organization_id, locality_id),
    )
    governance = clamp(organization.phenotype.get("governance_investment", 0.5))
    fielded_share = clamp(fielded / max(1e-12, total))

    # A ceasefire changes choice, not physical feasibility.  Existing violation
    # semantics provide the only violent-action suppression term.
    if organization.kind is OrganizationKind.INSURGENT:
        ceasefire_scale = (
            clamp(world.config.peace_process.ceasefire_violation_rate)
            if world.ceasefires.get(organization_id) == "active"
            else 1.0
        )
        human_target_belief = reachable_target_belief(
            world,
            organization_id,
            locality_id,
            "nonfielded_human_target",
        )
        asset_target_belief = reachable_target_belief(
            world,
            organization_id,
            locality_id,
            "asset_violence",
        )
        asset_weight = (
            risk * asset_target_belief * ceasefire_scale
            if "government" in world.organizations
            and organizations_hostile(world, organization_id, "government")
            else 0.0
        )
        coercion_weight = governance * embedded
    else:
        active_insurgents = [
            item for item in world.organizations.values()
            if item.kind is OrganizationKind.INSURGENT and item.status == "active"
        ]
        if active_insurgents:
            ceasefire_share = sum(
                world.ceasefires.get(item.organization_id) == "active"
                for item in active_insurgents
            ) / len(active_insurgents)
        else:
            ceasefire_share = 0.0
        violation = clamp(world.config.peace_process.ceasefire_violation_rate)
        ceasefire_scale = 1.0 - ceasefire_share * (1.0 - violation)
        human_target_belief = clamp((belief.physical + belief.social) / 2.0)
        asset_weight = 0.0
        coercion_weight = 0.0

    access_weight = (
        (0.35 + 0.65 * governance) * fielded_share * (0.5 + 0.5 * risk)
        if world.config.access_restriction.enabled
        and world.adjacency.get(locality_id)
        else 0.0
    )

    return {
        "wait": 1.0,
        "armed_confrontation": (
            risk * fielded_share * perceived_presence * ceasefire_scale
        ),
        "nonfielded_human_target": (
            risk * human_target_belief * ceasefire_scale
        ),
        "asset_violence": asset_weight,
        "coercion": coercion_weight,
        "access_restriction": access_weight,
    }


def choose_action(world, organization_id: str, locality_id: str,
                  rng: random.Random) -> tuple[str, dict[str, float]]:
    weights = action_choice_weights(world, organization_id, locality_id)
    channels = list(ACTION_CHANNELS)
    raw = [max(0.0, float(weights[channel])) for channel in channels]
    if sum(raw) <= 0:
        return "wait", weights
    return rng.choices(channels, weights=raw, k=1)[0], weights


def available_battle_pairs(world, organization_id: str, locality_id: str):
    local_formations = list(_local_formations(world, locality_id))
    own = [
        formation for formation in local_formations
        if formation.organization_id == organization_id
        and formation.personnel > 0
        and not formation.moving
        and not formation.outside_pineland
        and formation.operational_status == "effective"
    ]
    opponents = [
        formation for formation in local_formations
        if formation.personnel > 0
        and not formation.moving
        and not formation.outside_pineland
        and formation.operational_status == "effective"
        and world.organizations[formation.organization_id].status == "active"
        and organizations_hostile(
            world, organization_id, formation.organization_id
        )
    ]
    return [
        (actor_formation, opponent)
        for actor_formation in own
        for opponent in opponents
        if actor_formation.current_microzone_id == opponent.current_microzone_id
    ]


def nonfielded_human_targets(world, organization_id: str, locality_id: str):
    """Explicit nonfielded opponent manpower available at execution time."""
    targets = []
    for (target_org_id, target_locality_id), quantity in sorted(
        world.organization_manpower_pools.items()
    ):
        target_org = world.organizations.get(target_org_id)
        if (
            target_org_id != organization_id
            and target_locality_id == locality_id
            and quantity > 0
            and target_org is not None
            and target_org.status == "active"
            and organizations_hostile(world, organization_id, target_org_id)
        ):
            targets.append(NonfieldedHumanTarget(
                target_id=f"POOL:{target_org_id}:{locality_id}",
                target_type=(
                    "unfielded_insurgent_manpower"
                    if target_org.kind is OrganizationKind.INSURGENT
                    else "unfielded_manpower"
                ),
                organization_id=target_org_id,
                personnel=float(quantity),
                available_fraction=1.0,
                backing_pool_key=(target_org_id, locality_id),
            ))
    for post in world.security_posts.values():
        if (
            post.locality_id != locality_id
            or post.formation_id is not None
            or post.personnel <= 0
        ):
            continue
        target_organization = world.organizations.get(post.organization_id)
        if (
            target_organization is None
            or target_organization.status != "active"
            or not organizations_hostile(
                world, organization_id, post.organization_id
            )
        ):
            continue
        targets.append(NonfieldedHumanTarget(
            target_id=post.post_id,
            target_type="fixed_security_post",
            organization_id=post.organization_id,
            personnel=float(post.personnel),
            available_fraction=float(post.available_fraction),
            backing_post_id=post.post_id,
        ))
    return targets


def asset_targets(world, organization_id: str, locality_id: str):
    if (
        "government" not in world.organizations
        or not organizations_hostile(world, organization_id, "government")
    ):
        return []
    return [
        institution for institution in world.political_institutions.values()
        if institution.locality_id == locality_id
        and institution.capacity > 0
        and institution.reach > 0
    ]


def local_action_support(world, organization_id: str, locality_id: str) -> LocalActionSupport:
    organization = world.organizations[organization_id]
    if organization.kind not in ACTION_ORGANIZATION_KINDS:
        raise ValueError("organization has no armed organized-action role")
    unfielded, fielded = local_fighter_equivalents(world, organization_id, locality_id)
    human_targets = nonfielded_human_targets(world, organization_id, locality_id)
    institutions = asset_targets(world, organization_id, locality_id)
    total = unfielded + fielded
    return LocalActionSupport(
        organization_id=organization_id,
        locality_id=locality_id,
        unfielded_fighter_equivalents=unfielded,
        fielded_fighter_equivalents=fielded,
        nonfielded_target_personnel=sum(
            max(0.0, target.personnel) * clamp(target.available_fraction)
            for target in human_targets
        ),
        asset_target_count=len(institutions),
        susceptible_population=max(0.0, world.localities[locality_id].population),
        armed_confrontation=bool(available_battle_pairs(world, organization_id, locality_id)),
        nonfielded_human_target=(total > 0 and bool(human_targets)),
        government_asset_target=(total > 0 and bool(institutions)),
        civilian_coercion=(
            organization.kind is OrganizationKind.INSURGENT
            and total > 0
            and world.localities[locality_id].population > 0
        ),
        access_restriction=(
            total > 0
            and world.config.access_restriction.enabled
            and bool(world.adjacency.get(locality_id))
        ),
    )


def apply_nonfielded_target_losses(world, target: NonfieldedHumanTarget, losses: float) -> float:
    losses = max(0.0, min(float(losses), target.personnel))
    if target.backing_post_id is not None:
        post = world.security_posts[target.backing_post_id]
        realized = min(losses, post.personnel)
        post.personnel -= realized
        return realized
    if target.backing_pool_key is not None:
        available = max(0.0, world.organization_manpower_pools.get(target.backing_pool_key, 0.0))
        realized = min(losses, available)
        remaining = available - realized
        if remaining > 0:
            world.organization_manpower_pools[target.backing_pool_key] = remaining
        else:
            world.organization_manpower_pools.pop(target.backing_pool_key, None)
        reserve = max(
            0.0,
            world.organization_manpower_supply_reserves.get(target.backing_pool_key, 0.0),
        )
        if available > 0 and reserve > 0 and realized > 0:
            lost_supply = reserve * (realized / available)
            reserve -= lost_supply
            world.cumulative_supply_lost += lost_supply
            if reserve > 1e-12:
                world.organization_manpower_supply_reserves[target.backing_pool_key] = reserve
            else:
                world.organization_manpower_supply_reserves.pop(target.backing_pool_key, None)
        return realized
    return 0.0


def execution_probability(
    world,
    organization_id: str,
    locality_id: str,
    target_resistance: float,
    material_fraction: float = 1.0,
    target_organization_id: str | None = None,
    target_locality_id: str | None = None,
) -> float:
    """Execution feasibility from capacity, knowledge, target, and local supply.

    ``material_fraction`` is the fraction of the action's physical requirement
    present in the locality. Organization cash/material capital finances that
    stock upstream; multiplying by it again made converted or delivered supply
    unusable and charged the same constraint twice.
    """
    capacity = capacity_saturation(world, organization_id, locality_id)
    knowledge = local_operational_knowledge(
        world,
        organization_id,
        target_locality_id or locality_id,
        target_organization_id,
    )
    vulnerability = 1.0 - clamp(target_resistance)
    factors = (capacity, knowledge, vulnerability, clamp(material_fraction))
    if any(value <= 0 for value in factors):
        return 0.0
    product = 1.0
    for value in factors:
        product *= value
    return clamp(product ** (1.0 / len(factors)))

