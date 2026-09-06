"""Belief-based, budget-constrained organized action support.

The module deliberately reuses Pineland's existing organizational accounts.
Represented membership is *not* added to fighter equivalents: local action
capacity is the sum of unfielded fighter-equivalent pools and locally fielded
personnel exactly once.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp
import random

from .entities import OrganizationKind, clamp


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
)
VIOLENT_CHANNELS = {
    "armed_confrontation",
    "nonfielded_human_target",
    "asset_violence",
}


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
        for formation in world.formations.values()
        if formation.organization_id == organization_id
        and formation.locality_id == locality_id
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
        for formation in world.formations.values()
        if formation.organization_id == organization_id
        and formation.locality_id == locality_id
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
    for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
        if (
            remaining <= 0
            or formation.organization_id != organization_id
            or formation.locality_id != locality_id
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


def action_attempt_probability(world, organization_id: str, locality_id: str,
                               interval_days: float) -> float:
    """Continuous-time common action opportunity using the existing rate scale."""
    if interval_days <= 0:
        return 0.0
    rate = max(0.0, float(world.config.contact_rate))
    # ``contact_rate`` is an opportunity rate for one minimally viable action
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
    intensity = rate * active_units
    return clamp(1.0 - exp(-intensity * interval_days))


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
    risk = clamp(organization.phenotype.get("risk_tolerance", 0.5))
    embedded = clamp(organization.phenotype.get("local_embeddedness", 0.5))
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
        human_target_belief = clamp((belief.formal + belief.physical) / 2.0)
        asset_target_belief = clamp(
            (belief.administrative + belief.legal + belief.fiscal) / 3.0
        )
        asset_weight = risk * asset_target_belief * ceasefire_scale
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
    organization = world.organizations[organization_id]
    own = [
        formation for formation in world.formations.values()
        if formation.organization_id == organization_id
        and formation.locality_id == locality_id
        and formation.personnel > 0
        and not formation.moving
        and not formation.outside_pineland
        and formation.operational_status == "effective"
    ]
    if organization.kind is OrganizationKind.INSURGENT:
        opponent_kinds = {
            OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN
        }
    else:
        opponent_kinds = {OrganizationKind.INSURGENT}
    opponents = [
        formation for formation in world.formations.values()
        if formation.locality_id == locality_id
        and formation.personnel > 0
        and not formation.moving
        and not formation.outside_pineland
        and formation.operational_status == "effective"
        and world.organizations[formation.organization_id].kind in opponent_kinds
        and world.organizations[formation.organization_id].status == "active"
    ]
    return [
        (actor_formation, opponent)
        for actor_formation in own
        for opponent in opponents
        if actor_formation.current_microzone_id == opponent.current_microzone_id
    ]


def nonfielded_human_targets(world, organization_id: str, locality_id: str):
    """Explicit nonfielded opponent manpower available at execution time."""
    organization = world.organizations[organization_id]
    targets = []
    if organization.kind is not OrganizationKind.INSURGENT:
        for (target_org_id, target_locality_id), quantity in sorted(
            world.organization_manpower_pools.items()
        ):
            target_org = world.organizations.get(target_org_id)
            if (
                target_locality_id == locality_id
                and quantity > 0
                and target_org is not None
                and target_org.kind is OrganizationKind.INSURGENT
                and target_org.status == "active"
            ):
                targets.append(NonfieldedHumanTarget(
                    target_id=f"POOL:{target_org_id}:{locality_id}",
                    target_type="unfielded_insurgent_manpower",
                    organization_id=target_org_id,
                    personnel=float(quantity),
                    available_fraction=1.0,
                    backing_pool_key=(target_org_id, locality_id),
                ))
        return targets
    for post in world.security_posts.values():
        if (
            post.locality_id != locality_id
            or post.formation_id is not None
            or post.personnel <= 0
        ):
            continue
        organization = world.organizations.get(post.organization_id)
        if organization is not None and organization.kind is OrganizationKind.INSURGENT:
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
    if world.organizations[organization_id].kind is not OrganizationKind.INSURGENT:
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
) -> float:
    """Execution feasibility from capacity, knowledge, target, and local supply.

    ``material_fraction`` is the fraction of the action's physical requirement
    present in the locality. Organization cash/material capital finances that
    stock upstream; multiplying by it again made converted or delivered supply
    unusable and charged the same constraint twice.
    """
    organization = world.organizations[organization_id]
    capacity = capacity_saturation(world, organization_id, locality_id)
    knowledge = clamp(organization.local_knowledge)
    vulnerability = 1.0 - clamp(target_resistance)
    factors = (capacity, knowledge, vulnerability, clamp(material_fraction))
    if any(value <= 0 for value in factors):
        return 0.0
    product = 1.0
    for value in factors:
        product *= value
    return clamp(product ** (1.0 / len(factors)))

