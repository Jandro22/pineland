"""Endogenous armed-organization birth, adaptation, transition, and death."""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from math import ceil, exp, hypot, sqrt
import random
from typing import Any

from .entities import (ArmedFormation, ControlVector, LANGUAGES, LeadershipAgent, Organization,
                       OrganizationKind, OrganizationTransition, ProtoOrganization,
                       clamp, logistic)
from .logistics import _add_command_edge
from .networks import community_bridge_capacity, language_compatibility
from .relations import (
    ensure_relation,
    inherit_parent_relations,
    relation_status,
    update_relationship_ecology,
)
from .entities import RelationStatus


def armed_organizations(world, active_only: bool = True):
    return [o for o in world.organizations.values()
            if o.kind is OrganizationKind.INSURGENT and (not active_only or o.status == "active")]


def represented_armed_membership(world, organization: Organization) -> float:
    """Represented population fraction actually assigned to an armed group."""
    return sum(
        world.persons[pid].weight * world.persons[pid].armed_fraction
        for pid in organization.member_ids if pid in world.persons
    )


_PROTO_CAPITAL_KEYS = ("social", "political", "organizational", "material")
_PROTO_REPRESENTED_MEMBERSHIP_KEY = "_represented_membership"


def _proto_member_fractions(world, proto: ProtoOrganization) -> dict[str, float]:
    """Return each founder token's represented fractional participation."""
    members = [pid for pid in proto.member_ids if pid in world.persons]
    total_weight = sum(world.persons[pid].weight for pid in members)
    if total_weight <= 0:
        return {}
    target = proto.capital.get(_PROTO_REPRESENTED_MEMBERSHIP_KEY, total_weight)
    scale = clamp(target / total_weight)
    return {pid: scale for pid in members if scale > 0}


def _proto_represented_membership(world, proto: ProtoOrganization) -> float:
    fractions = _proto_member_fractions(world, proto)
    return sum(world.persons[pid].weight * fraction
               for pid, fraction in fractions.items())


def _proto_capital_mean(proto: ProtoOrganization) -> float:
    return sum(proto.capital.get(key, 0.0) for key in _PROTO_CAPITAL_KEYS) / len(_PROTO_CAPITAL_KEYS)


def _set_armed_membership(person, organization: Organization | None, fraction: float) -> None:
    prior_organization_id = person.organization_id
    prior_fraction = person.armed_fraction
    fraction = clamp(fraction)
    person.armed_fraction = fraction
    if organization is None or fraction <= 0:
        person.organization_id = None
        if prior_organization_id and prior_fraction > 0:
            person.insurgent_affinity[prior_organization_id] = max(
                person.insurgent_affinity.get(prior_organization_id, 0.0),
                prior_fraction,
            )
        if person.public_behavior == "armed_participation":
            person.public_behavior = "insurgent_sympathy"
        return
    person.organization_id = organization.organization_id
    # Active membership identifies the currently supported franchise. Keep the
    # affinity state exclusive while armed so stale pre-split affiliations do
    # not make one mobilized cohort broadcast support for rival organizations.
    person.insurgent_affinity = {organization.organization_id: max(fraction, 1e-12)}
    # A fractional representative is a mixture of armed and non-armed people.
    # Only majority-armed representatives expose a fully armed public signal.
    person.public_behavior = "armed_participation" if fraction >= .5 else "insurgent_sympathy"


def _formation_is_local_recruitment_source(formation: ArmedFormation) -> bool:
    """Return whether a formation is physically available as a local foothold."""
    return bool(
        formation.personnel > 0
        and formation.operational_status == "effective"
        and not formation.moving
        and not formation.outside_pineland
    )


def organization_local_rootedness(world, organization: Organization,
                                  locality_id: str) -> dict[str, float]:
    """Return locality-specific constituency rootedness for an armed organization.

    Rootedness is derived from represented *current local armed membership* and
    those members' home origins.  It therefore rises endogenously when an
    externally deployed franchise recruits locals and can fall when its local
    base is replaced by outsiders.  No ethnicity label or empirical case rule
    is hard-coded.
    """
    target = world.localities[locality_id]
    represented_local = 0.0
    home_local = 0.0
    home_district = 0.0
    for person_id in organization.member_ids:
        person = world.persons.get(person_id)
        if (person is None or person.organization_id != organization.organization_id or
                person.armed_fraction <= 0 or person.residence_locality_id != locality_id):
            continue
        represented = person.weight * person.armed_fraction
        represented_local += represented
        if person.home_locality_id == locality_id:
            home_local += represented
        home = world.localities.get(person.home_locality_id)
        if home is not None and home.district_id == target.district_id:
            home_district += represented
    if represented_local <= 1e-12:
        return {
            "represented_local_membership": 0.0,
            "home_locality_share": 0.0,
            "home_district_share": 0.0,
        }
    return {
        "represented_local_membership": represented_local,
        "home_locality_share": clamp(home_local / represented_local),
        "home_district_share": clamp(home_district / represented_local),
    }


def _organization_language_profiles(
    world, organization: Organization
) -> tuple[dict[str, float] | None, dict[str, dict[str, float]]]:
    """Return represented armed-member language profiles globally and by locality.

    Organization has no exogenous ethnicity/language label. Its usable
    recruitment languages therefore emerge from the represented people who are
    currently armed members. The global profile stands in for a fielded
    formation's organizational working-language capacity; locality profiles
    represent the people available as local member/broker recruitment channels.
    """
    global_mass = 0.0
    global_totals = {language: 0.0 for language in LANGUAGES}
    local_mass: dict[str, float] = {}
    local_totals: dict[str, dict[str, float]] = {}
    for person_id in organization.member_ids:
        person = world.persons.get(person_id)
        if (person is None or person.organization_id != organization.organization_id or
                person.armed_fraction <= 0):
            continue
        represented = person.weight * person.armed_fraction
        if represented <= 0:
            continue
        global_mass += represented
        locality_id = person.residence_locality_id
        local_mass[locality_id] = local_mass.get(locality_id, 0.0) + represented
        totals = local_totals.setdefault(
            locality_id, {language: 0.0 for language in LANGUAGES}
        )
        for language in LANGUAGES:
            proficiency = clamp(float(person.languages.get(language, 0.0)))
            global_totals[language] += represented * proficiency
            totals[language] += represented * proficiency
    global_profile = (
        {language: global_totals[language] / global_mass for language in LANGUAGES}
        if global_mass > 1e-12 else None
    )
    locality_profiles = {
        locality_id: {
            language: totals[language] / local_mass[locality_id]
            for language in LANGUAGES
        }
        for locality_id, totals in local_totals.items()
        if local_mass.get(locality_id, 0.0) > 1e-12
    }
    return global_profile, locality_profiles


def organization_language_profile(
    world, organization: Organization, locality_id: str | None = None
) -> dict[str, float] | None:
    """Return the current represented armed-member working-language profile.

    With a locality supplied this is deliberately strict: no local members
    means no local-member language profile. Formation access can instead use
    the global profile, so a deployed outside formation does not become
    linguistically local merely because it is physically present.
    """
    global_profile, locality_profiles = _organization_language_profiles(world, organization)
    return global_profile if locality_id is None else locality_profiles.get(locality_id)


def franchise_language_congruence(
    person, organization_profile: dict[str, float] | None
) -> float:
    """Mutual working-language compatibility for a recruitment channel.

    This reuses the social-network language estimand:
    max_r min(person_r, organization_r). Missing organization language state is
    treated as unknown/neutral rather than as evidence of alienness.
    """
    if organization_profile is None:
        return 1.0
    return language_compatibility(person.languages, organization_profile)


def _recruitment_language_access_factor(
    person, organization_profile: dict[str, float] | None
) -> float:
    """Communication factor for non-network recruitment access.

    The coefficients are not a new fitted parameter: they are exactly the
    existing social-edge communication prior, 0.35 + 0.65 * compatibility.
    The nonzero floor represents crude translation/intermediation rather than
    making linguistic difference an absolute binary barrier.
    """
    return .35 + .65 * franchise_language_congruence(person, organization_profile)


def organization_local_presence_sites(world, organization: Organization) -> set[str]:
    """Return localities where an organization has a live constituency or force."""
    sites = {
        world.persons[person_id].residence_locality_id
        for person_id in organization.member_ids
        if (person_id in world.persons and
            world.persons[person_id].organization_id == organization.organization_id and
            world.persons[person_id].armed_fraction > 0)
    }
    sites.update(
        formation.locality_id
        for formation in world.formations.values()
        if (formation.organization_id == organization.organization_id and
            formation.personnel > 0 and not formation.outside_pineland)
    )
    return sites


def organization_contact_overlap(world, first: Organization,
                                 second: Organization) -> float:
    """Bounded spatial opportunity for inter-organizational negotiation/competition.

    Ideological compatibility is not enough for two armed organizations to
    merge or compete directly: they need some overlapping social/fielded arena.
    Locality nodes are substantive geography, so this metric is invariant to
    representative-agent population resolution.
    """
    first_sites = organization_local_presence_sites(world, first)
    second_sites = organization_local_presence_sites(world, second)
    if not first_sites or not second_sites:
        return 0.0
    overlap = len(first_sites & second_sites)
    return clamp(overlap / max(1, min(len(first_sites), len(second_sites))))


def locality_franchise_support_profile(world, locality_id: str) -> dict[str, Any]:
    """Represent locality-level insurgent support concentration across franchises."""
    active_ids = {
        organization.organization_id for organization in armed_organizations(world)
    }
    represented_support = {organization_id: 0.0 for organization_id in active_ids}
    unaffiliated_sympathy = 0.0
    for person in world.persons.values():
        if person.residence_locality_id != locality_id:
            continue
        behavior_weight = (
            1.0 if person.public_behavior == "armed_participation"
            else .7 if person.public_behavior == "insurgent_sympathy"
            else 0.0
        )
        if behavior_weight <= 0:
            continue
        affinities = {
            organization_id: max(0.0, float(person.insurgent_affinity.get(organization_id, 0.0)))
            for organization_id in active_ids
            if person.insurgent_affinity.get(organization_id, 0.0) > 0
        }
        total_affinity = sum(affinities.values())
        represented = person.weight * behavior_weight
        if total_affinity <= 1e-12:
            if len(active_ids) == 1:
                represented_support[next(iter(active_ids))] += represented
            else:
                unaffiliated_sympathy += represented
            continue
        for organization_id, affinity in affinities.items():
            represented_support[organization_id] += represented * affinity / total_affinity
    total = sum(represented_support.values())
    shares = {
        organization_id: support / total if total > 0 else 0.0
        for organization_id, support in sorted(represented_support.items())
    }
    concentration = sum(share ** 2 for share in shares.values())
    return {
        "locality_id": locality_id,
        "represented_franchise_support": dict(sorted(represented_support.items())),
        "franchise_support_shares": shares,
        "represented_affiliated_support": total,
        "represented_unaffiliated_insurgent_sympathy": unaffiliated_sympathy,
        "support_concentration_hhi": concentration,
        "support_fragmentation": clamp(1.0 - concentration) if total > 0 else 0.0,
        "supported_franchise_count": sum(support > 0 for support in represented_support.values()),
    }


def franchise_constituency_congruence(world, person, organization: Organization,
                                      locality_id: str,
                                      rootedness: dict[str, float] | None = None) -> float:
    """Centered [-1, 1] match between local identity salience and franchise roots."""
    rootedness = rootedness or organization_local_rootedness(
        world, organization, locality_id
    )
    local_salience = clamp(person.identities.get("local", 0.0))
    district_salience = clamp(person.identities.get("district", 0.0))
    salience_total = local_salience + district_salience
    if salience_total <= 1e-12:
        return 0.0
    rooted_match = (
        local_salience * rootedness["home_locality_share"] +
        district_salience * rootedness["home_district_share"]
    ) / salience_total
    # Identity salience controls how much rootedness matters.  Someone whose
    # self-conception is weakly local should not receive a full outsider penalty.
    salience_strength = clamp(salience_total / 2.0)
    return max(-1.0, min(1.0, (2.0 * rooted_match - 1.0) * salience_strength))


def _recruitment_intensity(world, person, organization: Organization,
                           exposure: float, rootedness: dict[str, float]) -> tuple[float, float, float]:
    """Return recruitment intensity, ideological compatibility, and local congruence."""
    compatibility = 1 - abs(
        person.identities.get("federal", .5) - organization.ideology.get("reform", .5)
    )
    local_congruence = franchise_constituency_congruence(
        world, person, organization, person.residence_locality_id, rootedness
    )
    logit_value = (
        1.5 * person.grievance +
        world.config.social_network.recruitment_exposure_weight * exposure +
        compatibility +
        organization.capital["social"] - person.fear - 2.6 -
        world.config.political_order.peaceful_channel_strength * person.political_access +
        world.config.organization_ecology.local_rootedness_weight * local_congruence
    )
    return logistic(logit_value), compatibility, local_congruence


def _interval_hazard_probability(rate_per_day: float, intensity: float,
                                 interval_days: float) -> float:
    """Convert a nonnegative continuous daily hazard to an interval probability."""
    if interval_days < 0:
        raise ValueError("interval_days cannot be negative")
    hazard = max(0.0, float(rate_per_day)) * max(0.0, float(intensity))
    return 1 - exp(-hazard * interval_days)


_ECOLOGY_REFERENCE_CYCLE_DAYS = 7.0


def _reference_cycle_probability(probability_per_cycle: float,
                                 interval_days: float,
                                 reference_days: float = _ECOLOGY_REFERENCE_CYCLE_DAYS) -> float:
    """Compose a reference-cycle probability over an arbitrary elapsed interval.

    Organization-ecology priors are specified per seven-day reference cycle.
    Composing their survival probability makes scheduler partitioning a
    numerical choice while preserving the exact legacy probability at seven
    days.
    """
    if reference_days <= 0 or interval_days < 0:
        raise ValueError("reference_days must be positive and interval_days nonnegative")
    probability = clamp(float(probability_per_cycle))
    if interval_days == 0 or probability <= 0:
        return 0.0
    if probability >= 1:
        return 1.0
    return 1 - (1 - probability) ** (float(interval_days) / float(reference_days))


def _reference_cycle_survival_factor(loss_fraction_per_cycle: float,
                                     interval_days: float,
                                     reference_days: float = _ECOLOGY_REFERENCE_CYCLE_DAYS) -> float:
    """Compose a per-reference-cycle fractional loss into a survival factor."""
    if reference_days <= 0 or interval_days < 0:
        raise ValueError("reference_days must be positive and interval_days nonnegative")
    loss = clamp(float(loss_fraction_per_cycle))
    return (1 - loss) ** (float(interval_days) / float(reference_days))


def _resize_formation_supply_capacity(world, formation: ArmedFormation) -> None:
    # Changing manpower must never destroy materiel.  Capacity contracts only
    # as existing stock is consumed or transferred away; an overstocked unit
    # is simply treated as fully supplied until stock falls below its new
    # doctrinal carrying requirement.
    doctrinal_capacity = max(
        0.0, formation.personnel * world.config.logistics.formation_supply_days
    )
    formation.supply_capacity = max(doctrinal_capacity, formation.supply_stock)
    formation.sustainment = formation.supply_fraction()


def _formation_distance(world, formation: ArmedFormation, locality_id: str) -> float:
    if formation.locality_id == locality_id:
        return 0.0
    source = world.localities[formation.locality_id]
    target = world.localities[locality_id]
    return hypot(source.x_km - target.x_km, source.y_km - target.y_km)


def _next_recruitment_formation_id(world, organization_id: str) -> str:
    if organization_id == "insurgent":
        used = [int(fid.split("-")[-1]) for fid in world.formations
                if fid.startswith("PRF-") and fid.split("-")[-1].isdigit()]
        return f"PRF-{max(used, default=0) + 1:02d}"
    prefix = f"{organization_id.upper()}-F"
    used = [int(fid[len(prefix):]) for fid in world.formations
            if fid.startswith(prefix) and fid[len(prefix):].isdigit()]
    return f"{prefix}{max(used, default=0) + 1:02d}"


def _create_local_recruitment_formation(world, organization: Organization,
                                        locality_id: str, personnel: float,
                                        startup_stock: float | None = None) -> ArmedFormation:
    peers = [f for f in world.formations.values() if f.organization_id == organization.organization_id]
    if peers:
        mean_trait = lambda name, default: sum(getattr(f, name) for f in peers) / len(peers)
        quality = mean_trait("quality", .4)
        cohesion = mean_trait("cohesion", organization.cohesion)
        readiness = mean_trait("readiness", .55)
        information = mean_trait("information", .45)
        mobility = mean_trait("mobility", organization.mobility)
        command = mean_trait("command", .5)
        embeddedness = mean_trait("embeddedness", organization.local_knowledge)
    else:
        quality, cohesion, readiness = .4, organization.cohesion, .55
        information, mobility, command = .45, organization.mobility, .5
        embeddedness = organization.local_knowledge
    formation = ArmedFormation(
        _next_recruitment_formation_id(world, organization.organization_id),
        organization.organization_id, locality_id, personnel, quality, cohesion,
        readiness, 0.0, information, mobility, command, embeddedness,
        home_locality_id=locality_id, availability=.65,
    )
    _resize_formation_supply_capacity(world, formation)
    # Local formation birth converts existing organizational resources into a
    # small startup stock; it does not inject material from outside the model.
    startup = min(
        formation.supply_capacity * world.config.logistics.initial_supply_fraction,
        organization.resources * world.config.organization_ecology.onset_resource_fraction,
    ) if startup_stock is None else min(formation.supply_capacity, max(0.0, startup_stock))
    formation.supply_stock = startup
    if startup_stock is None:
        organization.resources -= startup
        world.cumulative_resource_to_supply += startup
    formation.sustainment = formation.supply_fraction()
    zones = [z for z in world.microzones.values() if z.locality_id == locality_id]
    if zones:
        formation.current_microzone_id = max(zones, key=lambda z: z.population_share).microzone_id
    world.formations[formation.formation_id] = formation
    _add_command_edge(
        world, f"CMD:{organization.organization_id}", formation.formation_id,
        organization.organization_id,
        clamp(.3 + .35 * organization.phenotype.get("centralization", .5) +
              .25 * organization.institutional_quality),
        10.0 * (1 - organization.phenotype.get("centralization", .5)) + 1.0,
    )
    return formation


def _apply_local_fighter_change(world, organization: Organization, locality_id: str,
                                delta: float) -> tuple[float, int]:
    """Apply fighter-equivalent manpower where recruitment/exit occurred.

    Positive manpower goes to an effective formation already in that locality.
    Otherwise it accumulates locally and forms a new unit once the general
    minimum-formation threshold is met.  Negative manpower leaves the local
    pool/formation first and only then the geographically nearest formation.
    """
    if abs(delta) <= 1e-12:
        return 0.0, 0
    requested_delta = delta
    key = (organization.organization_id, locality_id)
    target_size = world.config.force_structure.insurgent_target_personnel
    minimum = world.config.organization_ecology.minimum_formation_personnel
    created = 0
    if delta > 0:
        # Fighter-equivalent recruits are conserved in a local manpower pool.
        # Equipment is a distinct physical stock.  Convert organization
        # resources into a local reserve first, then transfer both manpower and
        # its associated materiel into a formation.  This prevents an
        # unequipped manpower remainder from becoming armed action capacity.
        supply_per_fighter = (
            world.config.logistics.formation_supply_days
            * world.config.logistics.initial_supply_fraction
        )
        pool = world.organization_manpower_pools.get(key, 0.0) + delta
        world.organization_manpower_pools[key] = pool
        reserve = world.organization_manpower_supply_reserves.get(key, 0.0)
        desired_reserve = pool * supply_per_fighter
        converted = min(
            max(0.0, desired_reserve - reserve),
            max(0.0, organization.resources),
        )
        if converted > 0:
            organization.resources -= converted
            world.cumulative_resource_to_supply += converted
            reserve += converted
        if reserve > 1e-12:
            world.organization_manpower_supply_reserves[key] = reserve
        local = [f for f in world.formations.values()
                 if f.organization_id == organization.organization_id and
                 f.locality_id == locality_id and
                 _formation_is_local_recruitment_source(f)]
        if local:
            for formation in sorted(local, key=lambda f: (f.personnel, f.formation_id)):
                room = max(0.0, target_size - formation.personnel)
                equipped = reserve / max(1e-12, supply_per_fighter)
                amount = min(room, pool, equipped)
                if amount > 0:
                    transferred_supply = amount * supply_per_fighter
                    formation.personnel += amount
                    formation.supply_stock += transferred_supply
                    pool -= amount
                    reserve -= transferred_supply
                    _resize_formation_supply_capacity(world, formation)
                if pool <= 1e-12:
                    break
        while pool >= minimum:
            equipped = reserve / max(1e-12, supply_per_fighter)
            size = min(pool, target_size, equipped)
            if size < minimum:
                break
            transferred_supply = size * supply_per_fighter
            _create_local_recruitment_formation(
                world, organization, locality_id, size,
                startup_stock=transferred_supply,
            )
            pool -= size
            reserve -= transferred_supply
            created += 1
        if pool > 1e-12:
            world.organization_manpower_pools[key] = pool
        else:
            world.organization_manpower_pools.pop(key, None)
        if reserve > 1e-12:
            world.organization_manpower_supply_reserves[key] = reserve
        else:
            world.organization_manpower_supply_reserves.pop(key, None)
        return requested_delta, created

    remaining = -delta
    pool = world.organization_manpower_pools.get(key, 0.0)
    from_pool = min(pool, remaining)
    pool -= from_pool
    remaining -= from_pool
    world.organization_manpower_pools[key] = pool
    candidates = [f for f in world.formations.values()
                  if f.organization_id == organization.organization_id and f.personnel > 0]
    candidates.sort(key=lambda f: (_formation_distance(world, f, locality_id), -f.personnel, f.formation_id))
    removed = from_pool
    for formation in candidates:
        if remaining <= 1e-12:
            break
        amount = min(formation.personnel, remaining)
        formation.personnel -= amount
        removed += amount
        remaining -= amount
        _resize_formation_supply_capacity(world, formation)
    return -removed, created


def synchronize_memberships(world) -> int:
    """Reconcile person ownership and organization member sets at a boundary.

    Split/merge/collapse transitions can leave an inactive historical
    organization's member set containing a person who has since exited or
    joined another active organization.  Active organization sets are the
    operational index, while each person's ``organization_id`` is the source
    of ownership truth.  Reconciliation removes stale active entries and adds
    missing reciprocal entries, returning the number of repairs for audit
    callers.  It never assigns a person to a new organization.
    """
    active = {organization.organization_id for organization in armed_organizations(world)}
    repairs = 0
    for organization in armed_organizations(world, active_only=False):
        if organization.status == "active":
            stale = {pid for pid in organization.member_ids
                     if world.persons[pid].organization_id != organization.organization_id}
            if stale:
                organization.member_ids.difference_update(stale)
                repairs += len(stale)
    for person in world.persons.values():
        if person.organization_id in active:
            organization = world.organizations[person.organization_id]
            if person.armed_fraction <= 0:
                # Backward-compatible repair for worlds/checkpoints created
                # before fractional armed membership existed.
                person.armed_fraction = 1.0
            if person.person_id not in organization.member_ids:
                organization.member_ids.add(person.person_id)
                repairs += 1
    return repairs


def initialize_organization_ecology(world) -> None:
    rng = __import__("pineland_sim.world", fromlist=["seeded_initialization_rng"]).seeded_initialization_rng(
        world.config, "organization-ecology-generation")
    for organization in armed_organizations(world, active_only=False):
        if not organization.member_ids:
            formation_localities = {f.locality_id for f in world.formations.values()
                                    if f.organization_id == organization.organization_id}
            # Reconcile represented membership to the already-created physical
            # force, and do it locally.  Fractional assignment makes the target
            # exact rather than requiring one or more whole weighted agents.
            conversion = max(1e-9, world.config.organization_ecology.fighter_conversion_fraction)
            by_locality: dict[str, float] = {}
            for formation in world.formations.values():
                if formation.organization_id == organization.organization_id:
                    by_locality[formation.locality_id] = (
                        by_locality.get(formation.locality_id, 0.0) + formation.personnel / conversion
                    )
            for locality_id, target_weight in sorted(by_locality.items()):
                candidates = [p for p in world.persons.values()
                              if p.residence_locality_id == locality_id and p.organization_id is None]
                remaining = target_weight
                for person in sorted(candidates, key=lambda p: (-p.grievance, p.person_id)):
                    if remaining <= 1e-9:
                        break
                    fraction = min(1.0, remaining / max(1e-9, person.weight))
                    _set_armed_membership(person, organization, fraction)
                    organization.member_ids.add(person.person_id)
                    remaining -= person.weight * fraction
            # Coarse weighted runs can have zero sampled civilians in a
            # formation locality.  Reconcile any unrepresented remainder with
            # the nearest still-unassigned representative populations rather
            # than silently shrinking the organization's social base.
            target_total = sum(by_locality.values())
            remaining_total = max(0.0, target_total - represented_armed_membership(world, organization))
            if remaining_total > 1e-9:
                formation_points = [world.localities[key] for key in formation_localities]
                def distance_to_force(person):
                    locality = world.localities[person.residence_locality_id]
                    return min(hypot(locality.x_km - target.x_km, locality.y_km - target.y_km)
                               for target in formation_points)
                fallback = [p for p in world.persons.values() if p.organization_id is None]
                for person in sorted(fallback, key=lambda p: (distance_to_force(p), -p.grievance, p.person_id)):
                    if remaining_total <= 1e-9:
                        break
                    fraction = min(1.0, remaining_total / max(1e-9, person.weight))
                    _set_armed_membership(person, organization, fraction)
                    organization.member_ids.add(person.person_id)
                    remaining_total -= person.weight * fraction
        organization.capital = {
            "social": clamp(.45 + .35 * organization.local_knowledge),
            "political": .55,
            "organizational": clamp(organization.institutional_quality),
            "material": clamp(organization.resources / 150_000),
        }
        organization.phenotype = {
            "centralization": organization.command if hasattr(organization, "command") else .55,
            "political_investment": .55, "governance_investment": .35,
            "dispersion": .62, "risk_tolerance": .58,
            "discipline": organization.discipline,
            "local_embeddedness": organization.local_knowledge,
            "resource_dependence": clamp(organization.external_support / max(1, organization.resources)),
        }
        organization.ideology = {"reform": .72, "separatism": .22}
        organization.adaptation_rate = world.config.organization_ecology.adaptation_rate
        _create_leader(world, organization, rng)


def _create_leader(world, organization: Organization, rng: random.Random,
                   inherited: LeadershipAgent | None = None) -> LeadershipAgent:
    leader_id = f"LDR{len(world.leaders) + 1:06d}"
    base = (inherited.competence, inherited.charisma, inherited.risk_tolerance,
            inherited.ideological_rigidity, inherited.political_skill,
            inherited.organizational_skill) if inherited else tuple(rng.uniform(.3, .8) for _ in range(6))
    values = tuple(clamp(value + rng.normalvariate(0, .04)) for value in base)
    leader = LeadershipAgent(leader_id, organization.organization_id, *values)
    world.leaders[leader_id] = leader
    organization.leader_id = leader_id
    return leader


def _transition(world, time: float, kind: str, parents, children,
                member_assignments, resource_assignments, formation_assignments, causes):
    record = OrganizationTransition(
        f"OT{len(world.organization_transitions) + 1:08d}", time, kind,
        tuple(parents), tuple(children),
        {key: tuple(sorted(value)) for key, value in member_assignments.items()},
        dict(resource_assignments),
        {key: tuple(sorted(value)) for key, value in formation_assignments.items()},
        {child: dict(world.organizations[child].phenotype) for child in children}, dict(causes),
    )
    world.organization_transitions.append(record)
    return record


def _rewire_formation_command(world, formation, organization: Organization) -> None:
    _add_command_edge(world, f"CMD:{organization.organization_id}", formation.formation_id,
                      organization.organization_id,
                      clamp(.3 + .35 * organization.phenotype["centralization"] +
                            .25 * organization.institutional_quality),
                      10.0 * (1 - organization.phenotype["centralization"]) + 1.0)


def _transfer_sources(world, parent_ids: set[str], children: list[Organization]) -> None:
    for source in world.supply_sources.values():
        if source.organization_id not in parent_ids:
            continue
        counts = [sum(world.persons[pid].weight * world.persons[pid].armed_fraction
                      for pid in child.member_ids
                      if world.persons[pid].residence_locality_id == source.locality_id)
                  for child in children]
        source.organization_id = children[counts.index(max(counts))].organization_id


def _transfer_manpower_pools(world, parent_ids: set[str], children: list[Organization]) -> float:
    """Transfer local unfielded manpower and its material reserves together."""
    def child_weights(locality_id: str) -> tuple[list[float], float]:
        local_weights = [
            sum(world.persons[pid].weight * world.persons[pid].armed_fraction
                for pid in child.member_ids
                if world.persons[pid].residence_locality_id == locality_id)
            for child in children
        ]
        if sum(local_weights) <= 0:
            local_weights = [represented_armed_membership(world, child) for child in children]
        denominator = sum(local_weights)
        if denominator <= 0:
            local_weights = [1.0 for _ in children]
            denominator = float(len(children))
        return local_weights, denominator

    moved = 0.0
    for stock, count_as_manpower in (
        (world.organization_manpower_pools, True),
        (world.organization_manpower_supply_reserves, False),
    ):
        for (parent_id, locality_id), quantity in list(stock.items()):
            if parent_id not in parent_ids or quantity <= 0:
                continue
            del stock[(parent_id, locality_id)]
            if not children:
                continue
            if len(children) == 1:
                key = (children[0].organization_id, locality_id)
                stock[key] = stock.get(key, 0.0) + quantity
                if count_as_manpower:
                    moved += quantity
                continue
            local_weights, denominator = child_weights(locality_id)
            allocated = 0.0
            for index, (child, weight) in enumerate(zip(children, local_weights)):
                share = (quantity - allocated if index == len(children) - 1
                         else quantity * weight / denominator)
                key = (child.organization_id, locality_id)
                stock[key] = stock.get(key, 0.0) + share
                allocated += share
            if count_as_manpower:
                moved += quantity
    return moved


def _mobilization_score(world, community) -> tuple[float, list]:
    people = [world.persons[pid] for pid in community.member_ids]
    if not people:
        return 0.0, []
    mobilized = [p for p in people if p.organization_id is None and
                 (p.public_behavior in {"protest", "insurgent_sympathy", "armed_participation"}
                  or p.grievance > .55)]
    represented = sum(p.weight for p in people)
    grievance = sum(p.weight * p.grievance for p in people) / max(1e-9, represented)
    represented_people = sum(person.weight for person in people)
    bridge_weight = community_bridge_capacity(world, community)
    reach = min(1.0, bridge_weight / max(1.0, represented_people) * 5)
    access = sum(p.weight * p.political_access for p in people) / max(1e-9, represented)
    score = clamp(.3 * grievance + .3 * community.cohesion + .2 * community.insurgent_sympathy +
                  .2 * reach - world.config.political_order.peaceful_channel_strength * .25 * access)
    return score, mobilized


def _experienced_repression(world, community) -> float:
    """Exposure-side repression generated by realized local experience."""
    locality = world.localities[community.locality_id]
    return clamp(.7 * locality.violence +
                 .3 * (1 - locality.control["government"].physical))


def _expected_repression(world, people, membership_fractions: dict[str, float] | None = None) -> float:
    """Founder expectation inferred from actor-local control beliefs."""
    if not people:
        return .5
    represented = sum(
        person.weight * (membership_fractions.get(person.person_id, 1.0)
                         if membership_fractions is not None else 1.0)
        for person in people
    )
    if represented <= 0:
        return .5
    return clamp(sum(
        person.weight *
        (membership_fractions.get(person.person_id, 1.0)
         if membership_fractions is not None else 1.0) *
        (1 - person.expected_control.get("government", .5))
        for person in people
    ) / represented)


def form_proto_organizations(world, time: float, rng: random.Random,
                             interval_days: float | None = None) -> list[ProtoOrganization]:
    cfg = world.config.organization_ecology
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("organization ecology interval_days must be positive")
    active_communities = {p.community_id for p in world.proto_organizations.values() if p.status == "mobilizing"}
    created = []
    for community in world.social_communities.values():
        if community.community_id in active_communities:
            continue
        score, mobilized = _mobilization_score(world, community)
        mobilized_weight = sum(person.weight for person in mobilized)
        minimum_proto_weight = cfg.minimum_proto_represented_population
        if mobilized_weight < minimum_proto_weight:
            continue
        locality = world.localities[community.locality_id]
        expected_repression = _expected_repression(world, mobilized)
        experienced_repression = _experienced_repression(world, community)
        # Founders act on expected repression.  Experienced repression remains
        # an observed environmental covariate and is logged separately.
        hazard = 1 - exp(
            -cfg.proto_base_hazard *
            exp(2.2 * score - 1.4 * expected_repression) *
            interval_days / _ECOLOGY_REFERENCE_CYCLE_DAYS
        )
        if rng.random() >= hazard:
            continue
        target_weight = max(minimum_proto_weight, mobilized_weight * .5)
        # Founding is a represented-population slice, not a count of sampled
        # representatives.  Fractionally scale the mobilized base so the target
        # is exact and no last sampled node can create resolution-dependent
        # founder overshoot or composition.
        selected = list(mobilized)
        founder_fraction = clamp(target_weight / max(1e-9, mobilized_weight))
        founder_weights = {
            person.person_id: person.weight * founder_fraction
            for person in selected
        }
        selected_weight = sum(founder_weights.values())
        # Person.resources is a represented stock.  Scale that stock by the
        # founder fraction, then divide by represented founder population to
        # recover the per-capita material intensity.
        material_intensity = (
            sum(person.resources * founder_fraction for person in selected) /
            max(1e-9, selected_weight)
        )
        leadership = (
            sum(founder_weights[person.person_id] * person.efficacy
                for person in selected) /
            max(1e-9, selected_weight)
        )
        proto = ProtoOrganization(
            f"PROTO{len(world.proto_organizations) + 1:07d}", community.community_id,
            community.locality_id, {p.person_id for p in selected},
            {"social": community.cohesion, "political": score,
             "organizational": .12 + .25 * community.cohesion,
             "material": clamp(material_intensity / 3),
             _PROTO_REPRESENTED_MEMBERSHIP_KEY: selected_weight},
            {"reform": clamp(.4 + score / 2), "separatism": clamp(.15 + .3 * score)},
            clamp(leadership), time,
        )
        world.proto_organizations[proto.proto_id] = proto
        world.organization_onset_log.append({
            "time": time, "organization_id": proto.proto_id,
            "phase": "proto_formation", "eligible": True,
            "expected_repression": expected_repression,
            "experienced_repression": experienced_repression,
            "hazard": hazard, "score": score,
            "represented_founder_membership": selected_weight,
            "founder_fraction": founder_fraction,
        })
        created.append(proto)
    return created


def mature_proto(world, proto: ProtoOrganization, time: float, rng: random.Random,
                 interval_days: float | None = None):
    cfg = world.config.organization_ecology
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("organization ecology interval_days must be positive")
    before_stocks = world.tracked_stock_totals()
    capital = _proto_capital_mean(proto)
    locality = world.localities[proto.locality_id]
    members = [world.persons[pid] for pid in proto.member_ids if pid in world.persons]
    founder_fractions = _proto_member_fractions(world, proto)
    expected_repression = _expected_repression(world, members, founder_fractions)
    experienced_repression = clamp(.7 * locality.violence +
                                    .3 * (1 - locality.control["government"].physical))
    hazard = 1 - exp(
        -cfg.birth_base_hazard *
        exp(2.4 * capital + proto.leadership_potential - 1.6 * expected_repression) *
        interval_days / _ECOLOGY_REFERENCE_CYCLE_DAYS
    )
    if rng.random() >= hazard:
        survival = _reference_cycle_survival_factor(
            cfg.proto_decay_rate, interval_days
        )
        for key in _PROTO_CAPITAL_KEYS:
            proto.capital[key] = clamp(proto.capital[key] * survival)
        if _proto_capital_mean(proto) < .08:
            proto.status = "collapsed"
            _transition(world, time, "proto_collapse", (proto.proto_id,), (), {}, {}, {},
                        {"capital": capital, "expected_repression": expected_repression,
                         "experienced_repression": experienced_repression})
        return None
    # Check represented manpower before mutating civilian ownership or
    # transferring resources.  A weighted representative can satisfy a
    # capital/onset draw while still being too small to field a viable
    # formation; that proto must collapse atomically, without leaving people
    # assigned to a non-existent organization or consuming startup resources.
    represented_members = _proto_represented_membership(world, proto)
    personnel = represented_members * cfg.fighter_conversion_fraction
    if personnel < cfg.minimum_formation_personnel:
        proto.status = "collapsed"
        _transition(world, time, "proto_collapse", (proto.proto_id,), (), {}, {}, {},
                    {"reason": "insufficient_represented_manpower", "personnel": personnel,
                     "expected_repression": expected_repression,
                     "experienced_repression": experienced_repression})
        return None
    oid = f"armed-{len([o for o in world.organizations if o.startswith('armed-')]) + 1:03d}"
    contributed = 0.0
    for pid, fraction in founder_fractions.items():
        contribution = world.persons[pid].resources * cfg.onset_resource_fraction * fraction
        contributed += contribution
        world.adjust_person_resources(pid, -contribution)
        _set_armed_membership(world.persons[pid], None, 0.0)
    member_ids = set(founder_fractions)
    organization = Organization(
        oid, f"Emergent Organization {oid[-3:]}", OrganizationKind.INSURGENT,
        contributed, clamp(.35 + .4 * proto.capital["organizational"]), .5, .2,
        proto.capital["social"], .65, .55, .45, member_ids, 0.0,
        {key: proto.capital[key] for key in _PROTO_CAPITAL_KEYS},
        {}, dict(proto.ideology), "active", time, (proto.proto_id,), None,
        cfg.adaptation_rate,
    )
    organization.phenotype = {
        "centralization": rng.uniform(.3, .7), "political_investment": proto.capital["political"],
        "governance_investment": rng.uniform(.2, .6), "dispersion": rng.uniform(.4, .8),
        "risk_tolerance": rng.uniform(.3, .75), "discipline": organization.discipline,
        "local_embeddedness": proto.capital["social"], "resource_dependence": .1,
    }
    world.organizations[oid] = organization
    for other_id in world.organizations:
        if other_id != oid:
            ensure_relation(world, oid, other_id, time)
    for pid, fraction in founder_fractions.items():
        _set_armed_membership(world.persons[pid], organization, fraction)
    for locality in world.localities.values():
        locality.control.setdefault(oid, ControlVector(0, .005, 0, .005, .005, .015, .03))
        locality.control.setdefault("insurgent", ControlVector())
    for zone in world.microzones.values():
        zone.physical_control.setdefault(oid, 0.0)
        zone.physical_control.setdefault("insurgent", 0.0)
    _create_leader(world, organization, rng)
    fid = f"{oid.upper()}-F01"
    formation = ArmedFormation(fid, oid, proto.locality_id, personnel, .35, organization.cohesion,
                               .55, .45, .45, .55, .45, organization.local_knowledge)
    formation.supply_capacity = personnel * world.config.logistics.formation_supply_days
    # Startup materiel is converted from the proto's contributed resources;
    # it is not also injected into the global supply baseline.
    formation.supply_stock = min(formation.supply_capacity * .25, organization.resources)
    organization.resources -= formation.supply_stock
    world.cumulative_resource_to_supply += formation.supply_stock
    formation.sustainment = formation.supply_fraction()
    local_zones = [z for z in world.microzones.values() if z.locality_id == proto.locality_id]
    if local_zones:
        formation.current_microzone_id = max(local_zones, key=lambda z: z.population_share).microzone_id
    world.formations[fid] = formation
    _add_command_edge(world, f"CMD:{oid}", fid, oid, .45, 8.0)
    proto.status = "matured"
    _transition(world, time, "birth", (proto.proto_id,), (oid,), {oid: member_ids},
                {oid: contributed}, {oid: (fid,)},
                {"formation_hazard": hazard,
                 "expected_repression": expected_repression,
                 "experienced_repression": experienced_repression,
                 "represented_founder_membership": represented_members})
    if world.active_event_id is None:
        world.record_stock_transactions(
            f"ONSET-{proto.proto_id}", "organization_ecology",
            before_stocks, world.tracked_stock_totals(),
        )
    return organization


def recruit_and_retain(world, time: float, rng: random.Random,
                       interval_days: float | None = None) -> dict[str, Any]:
    """Recruit and retain armed members with explicit franchise competition.

    Access, local constituency rootedness, and membership are frozen at the
    start of the interval.  Unaffiliated cohorts face *competing hazards* from
    every accessible active insurgent organization instead of being claimed by
    whichever organization happens to be iterated first.  Already-affiliated
    cohorts can only deepen membership in their current organization.
    """
    recruits = exits = defections = 0.0
    fighter_recruits = fighter_exits = fighter_defections = 0.0
    formations_created = 0
    contested_candidates = 0
    recruitment_rate = world.config.recruitment_rate
    membership_exit_rate = world.config.membership_exit_rate
    cfg = world.config.organization_ecology
    interval_days = (
        world.config.intervals.recruitment if interval_days is None
        else float(interval_days)
    )
    if interval_days <= 0:
        raise ValueError("recruitment interval_days must be positive")

    organizations = sorted(armed_organizations(world), key=lambda item: item.organization_id)
    organization_by_id = {item.organization_id: item for item in organizations}
    local_formation_personnel: dict[str, dict[str, float]] = {}
    local_member_weight: dict[str, dict[str, float]] = {}
    rootedness_by_org: dict[str, dict[str, dict[str, float]]] = {}
    language_profile_by_org: dict[str, dict[str, float] | None] = {}
    local_language_profile_by_org: dict[str, dict[str, dict[str, float]]] = {}
    franchise_recruits = {item.organization_id: 0.0 for item in organizations}

    # Freeze all local access, rootedness, and language channels at the interval boundary.
    # This prevents same-tick recruits from immediately making their franchise
    # look more indigenous or linguistically adapted to later representatives
    # in the loop.
    for organization in organizations:
        oid = organization.organization_id
        formation_map: dict[str, float] = {}
        for formation in world.formations.values():
            if (formation.organization_id == oid and
                    _formation_is_local_recruitment_source(formation)):
                formation_map[formation.locality_id] = (
                    formation_map.get(formation.locality_id, 0.0) + formation.personnel
                )
        member_map: dict[str, float] = {}
        for pid in organization.member_ids:
            member = world.persons.get(pid)
            if (member is None or member.organization_id != oid or member.armed_fraction <= 0):
                continue
            represented = member.weight * member.armed_fraction
            member_map[member.residence_locality_id] = (
                member_map.get(member.residence_locality_id, 0.0) + represented
            )
        local_formation_personnel[oid] = formation_map
        local_member_weight[oid] = member_map
        rootedness_by_org[oid] = {
            locality_id: organization_local_rootedness(world, organization, locality_id)
            for locality_id in world.localities
        }
        global_language_profile, local_language_profiles = _organization_language_profiles(
            world, organization
        )
        language_profile_by_org[oid] = global_language_profile
        local_language_profile_by_org[oid] = local_language_profiles

    for person in world.persons.values():
        current_org = organization_by_id.get(person.organization_id or "")
        recruited_this_interval = False
        current_fraction = person.armed_fraction if current_org is not None else 0.0
        eligible_recruit_fraction = max(0.0, 1.0 - current_fraction)

        if eligible_recruit_fraction > 1e-12:
            candidate_organizations = (
                [current_org] if current_org is not None else organizations
            )
            candidates: list[tuple[Organization, float, float, float]] = []
            for organization in candidate_organizations:
                if organization is None:
                    continue
                oid = organization.organization_id
                exposure = person.social_exposure.get(
                    oid, person.social_exposure.get("insurgent", 0.0)
                )
                formation_access = clamp(
                    local_formation_personnel[oid].get(person.residence_locality_id, 0.0) /
                    max(1e-9, cfg.minimum_formation_personnel)
                )
                member_access = clamp(
                    local_member_weight[oid].get(person.residence_locality_id, 0.0) /
                    max(1e-9, cfg.minimum_proto_represented_population)
                )
                # Social-edge exposure already travels through the network's
                # language-bearing ties. Non-network access must not bypass
                # communication merely because a force or armed constituency is
                # physically present. Formation access uses the organization's
                # represented working-language profile; local-member access uses
                # the current local armed-membership profile. These are distinct
                # from origin/rootedness, which remains in recruitment utility.
                formation_language_factor = _recruitment_language_access_factor(
                    person, language_profile_by_org[oid]
                )
                member_language_factor = _recruitment_language_access_factor(
                    person,
                    local_language_profile_by_org[oid].get(person.residence_locality_id),
                )
                access_strength = max(
                    clamp(exposure),
                    formation_access * formation_language_factor,
                    member_access * member_language_factor,
                )
                if cfg.recruitment_requires_access and access_strength <= 0:
                    continue
                intensity, compatibility, local_congruence = _recruitment_intensity(
                    world, person, organization, exposure,
                    rootedness_by_org[oid][person.residence_locality_id],
                )
                effective_intensity = (
                    intensity * access_strength if cfg.recruitment_requires_access else intensity
                )
                if effective_intensity > 0:
                    candidates.append(
                        (organization, effective_intensity, compatibility, local_congruence)
                    )

            if candidates:
                if current_org is None and len(candidates) > 1:
                    contested_candidates += 1
                total_intensity = sum(item[1] for item in candidates)
                probability = _interval_hazard_probability(
                    recruitment_rate, total_intensity, interval_days
                )
                n = cfg.recruitment_subcohorts
                available_cohorts = max(
                    0, min(n, ceil(eligible_recruit_fraction * n))
                )
                recruited_cohorts = sum(
                    rng.random() < probability for _ in range(available_cohorts)
                )
                delta_fraction = min(
                    eligible_recruit_fraction, recruited_cohorts / n
                )
                if delta_fraction > 0:
                    if len(candidates) == 1:
                        winner, _, compatibility, _ = candidates[0]
                    else:
                        draw = rng.random() * total_intensity
                        cumulative = 0.0
                        winner, _, compatibility, _ = candidates[-1]
                        for candidate in candidates:
                            cumulative += candidate[1]
                            if draw <= cumulative:
                                winner, _, compatibility, _ = candidate
                                break
                    recruited_this_interval = True
                    winner_fraction = (
                        current_fraction + delta_fraction
                        if person.organization_id == winner.organization_id else delta_fraction
                    )
                    _set_armed_membership(person, winner, winner_fraction)
                    winner.member_ids.add(person.person_id)
                    represented_delta = person.weight * delta_fraction
                    recruits += represented_delta
                    franchise_recruits[winner.organization_id] += represented_delta
                    fighter_delta = represented_delta * cfg.fighter_conversion_fraction
                    applied, created = _apply_local_fighter_change(
                        world, winner, person.residence_locality_id, fighter_delta
                    )
                    fighter_recruits += max(0.0, applied)
                    formations_created += created
                    diversity = abs(compatibility - .5) * 2
                    represented_members = represented_armed_membership(world, winner)
                    winner.cohesion = clamp(
                        winner.cohesion -
                        cfg.recruitment_diversity_penalty * diversity * delta_fraction /
                        max(10.0, represented_members)
                    )

        # Defection is a competing destination for an incumbent cohort.  It
        # reuses the existing membership-exit rate family rather than adding a
        # case-fit "defection rate": a rival must be locally accessible and
        # attractive, and the dyad must already be rival or hostile.
        current_org = organization_by_id.get(person.organization_id or "")
        defected_this_interval = False
        if (
            not recruited_this_interval
            and current_org is not None
            and person.armed_fraction > 0
        ):
            rival_candidates: list[tuple[Organization, float]] = []
            for rival in organizations:
                if rival.organization_id == current_org.organization_id:
                    continue
                status = relation_status(
                    world, current_org.organization_id, rival.organization_id
                )
                if status not in {RelationStatus.RIVAL, RelationStatus.HOSTILE}:
                    continue
                oid = rival.organization_id
                exposure = person.social_exposure.get(
                    oid, person.social_exposure.get("insurgent", 0.0)
                )
                formation_access = clamp(
                    local_formation_personnel[oid].get(
                        person.residence_locality_id, 0.0
                    )
                    / max(1e-9, cfg.minimum_formation_personnel)
                )
                member_access = clamp(
                    local_member_weight[oid].get(
                        person.residence_locality_id, 0.0
                    )
                    / max(1e-9, cfg.minimum_proto_represented_population)
                )
                formation_language_factor = _recruitment_language_access_factor(
                    person, language_profile_by_org[oid]
                )
                member_language_factor = _recruitment_language_access_factor(
                    person,
                    local_language_profile_by_org[oid].get(
                        person.residence_locality_id
                    ),
                )
                access_strength = max(
                    clamp(exposure),
                    formation_access * formation_language_factor,
                    member_access * member_language_factor,
                )
                if cfg.recruitment_requires_access and access_strength <= 0:
                    continue
                intensity, _, _ = _recruitment_intensity(
                    world,
                    person,
                    rival,
                    exposure,
                    rootedness_by_org[oid][person.residence_locality_id],
                )
                relation = ensure_relation(
                    world,
                    current_org.organization_id,
                    rival.organization_id,
                    time,
                )
                rivalry_signal = max(
                    relation.rivalry_memory,
                    relation.hostility_memory,
                    world.config.relationships.rivalry_threshold,
                )
                effective = intensity * access_strength * rivalry_signal
                if effective > 0:
                    rival_candidates.append((rival, effective))
            if rival_candidates:
                total_defection_intensity = sum(
                    intensity for _, intensity in rival_candidates
                )
                defection_probability = _interval_hazard_probability(
                    membership_exit_rate,
                    total_defection_intensity,
                    interval_days,
                )
                if rng.random() < defection_probability:
                    draw = rng.random() * total_defection_intensity
                    cumulative = 0.0
                    winner = rival_candidates[-1][0]
                    for rival, intensity in rival_candidates:
                        cumulative += intensity
                        if draw <= cumulative:
                            winner = rival
                            break
                    represented_delta = person.weight * person.armed_fraction
                    fighter_delta = (
                        represented_delta * cfg.fighter_conversion_fraction
                    )
                    removed, _ = _apply_local_fighter_change(
                        world,
                        current_org,
                        person.residence_locality_id,
                        -fighter_delta,
                    )
                    transferable_fighters = max(0.0, -removed)
                    if transferable_fighters > 0:
                        _apply_local_fighter_change(
                            world,
                            winner,
                            person.residence_locality_id,
                            transferable_fighters,
                        )
                    current_org.member_ids.discard(person.person_id)
                    _set_armed_membership(
                        person, winner, person.armed_fraction
                    )
                    winner.member_ids.add(person.person_id)
                    defections += represented_delta
                    fighter_defections += transferable_fighters
                    defected_this_interval = True

        # Exit hazards act only on the incumbent organization.  A cohort that
        # recruited or defected this interval cannot exit in the same tick.
        current_org = organization_by_id.get(person.organization_id or "")
        if (not recruited_this_interval and current_org is not None and
                not defected_this_interval and person.armed_fraction > 0):
            exit_probability = _interval_hazard_probability(
                membership_exit_rate,
                logistic(person.fear + .7 - current_org.cohesion - person.grievance),
                interval_days,
            )
            n = cfg.recruitment_subcohorts
            active_cohorts = max(1, min(n, ceil(person.armed_fraction * n)))
            exited_cohorts = sum(
                rng.random() < exit_probability for _ in range(active_cohorts)
            )
            exit_fraction = min(person.armed_fraction, exited_cohorts / n)
            if exit_fraction > 0:
                represented_delta = person.weight * exit_fraction
                exits += represented_delta
                fighter_delta = represented_delta * cfg.fighter_conversion_fraction
                applied, _ = _apply_local_fighter_change(
                    world, current_org, person.residence_locality_id, -fighter_delta
                )
                fighter_exits += max(0.0, -applied)
                remaining = person.armed_fraction - exit_fraction
                if remaining <= 1e-12:
                    current_org.member_ids.discard(person.person_id)
                    exited_org_id = current_org.organization_id
                    _set_armed_membership(person, None, 0.0)
                    if (cfg.exit_sympathy_retention < 1.0 and
                            rng.random() >= cfg.exit_sympathy_retention):
                        person.public_behavior = "neutral"
                        person.insurgent_affinity.pop(exited_org_id, None)
                        person.social_exposure.pop(exited_org_id, None)
                        person.social_exposure.pop("insurgent", None)
                else:
                    _set_armed_membership(person, current_org, remaining)

    repairs = synchronize_memberships(world)
    return {"recruits": recruits, "exits": exits,
            "defections": defections,
            "fighter_recruits": fighter_recruits, "fighter_exits": fighter_exits,
            "fighter_defections": fighter_defections,
            "formations_created": formations_created,
            "local_manpower_pools": sum(world.organization_manpower_pools.values()),
            "membership_repairs": repairs,
            "contested_recruitment_candidates": contested_candidates,
            "franchise_recruits": franchise_recruits}


def _observable_peer_profile(world, observer_id: str, peer_id: str):
    """Infer peer practice only from beliefs produced by the observation layer."""
    presence_by_locality = {}
    for belief in world.presence_beliefs.values():
        if (belief.observer_id != observer_id or belief.target_actor_id != peer_id or
                belief.target_id is not None or belief.confidence <= 0):
            continue
        current = presence_by_locality.get(belief.locality_id)
        if current is None or belief.confidence > current.confidence:
            presence_by_locality[belief.locality_id] = belief

    control_by_locality = {
        locality_id: belief
        for (observer, target, locality_id), belief in world.control_beliefs.items()
        if observer == observer_id and target == peer_id and belief.confidence > 0
    }
    if not presence_by_locality and not control_by_locality:
        return None

    targets = {}
    presence_weights = [
        belief.confidence * max(.01, belief.presence_estimate)
        for belief in presence_by_locality.values()
    ]
    total_presence = sum(presence_weights)
    if total_presence > 0:
        targets["dispersion"] = clamp(1 - max(presence_weights) / total_presence)

    if control_by_locality:
        denominator = sum(belief.confidence for belief in control_by_locality.values())

        def control_mean(dimensions):
            dimension_count = float(len(dimensions))
            return clamp(sum(
                belief.confidence *
                (sum(getattr(belief.control_estimate, dimension) for dimension in dimensions) /
                 dimension_count)
                for belief in control_by_locality.values()
            ) / max(1e-9, denominator))

        targets["political_investment"] = control_mean(("formal", "social", "expected"))
        targets["governance_investment"] = control_mean(("administrative", "legal", "fiscal"))
        targets["local_embeddedness"] = control_mean(("social", "expected"))

    observed_personnel = sum(
        belief.confidence * clamp(belief.personnel_estimate / 1_000.0)
        for belief in presence_by_locality.values()
    )
    observed_control = sum(
        belief.confidence * belief.control_estimate.physical
        for belief in control_by_locality.values()
    )
    evidence = (sum(belief.confidence for belief in presence_by_locality.values()) +
                sum(belief.confidence for belief in control_by_locality.values()))
    score = (observed_personnel + observed_control) / max(1e-9, evidence)
    return score, targets


def _adapt(world, organization: Organization, rng: random.Random,
           interval_days: float | None = None) -> None:
    cfg = world.config.organization_ecology
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("organization ecology interval_days must be positive")
    observed = []
    for peer in armed_organizations(world):
        if peer.organization_id == organization.organization_id:
            continue
        profile = _observable_peer_profile(
            world, organization.organization_id, peer.organization_id
        )
        if profile is not None:
            observed.append((profile[0], peer.organization_id, profile[1]))
    targets = max(observed, key=lambda item: (item[0], item[1]))[2] if observed else {}
    reference_learning = clamp(
        organization.adaptation_rate * (.4 + .6 * organization.institutional_quality)
    )
    learning = _reference_cycle_probability(reference_learning, interval_days)
    # Mutation/interpretation noise is an innovation around the adaptation
    # target.  Compose its state-space variance together with the AR(1)
    # learning coefficient so subdividing the ecology clock does not inject
    # extra stochastic phenotype diffusion.
    if learning > 0 and reference_learning > 0:
        phi_reference = 1.0 - reference_learning
        phi_interval = 1.0 - learning
        reference_state_variance = (
            reference_learning * cfg.mutation_sigma
        ) ** 2
        denominator = max(1e-15, 1.0 - phi_reference ** 2)
        interval_state_variance = (
            reference_state_variance *
            (1.0 - phi_interval ** 2) /
            denominator
        )
        perceived_sigma = sqrt(max(0.0, interval_state_variance)) / learning
    else:
        perceived_sigma = 0.0
    for trait, value in organization.phenotype.items():
        # Only traits inferable from fused observations imitate a peer signal.
        # Latent traits experiment around the organization's own state instead
        # of reading another actor's exact hidden phenotype.
        perceived = targets.get(trait, value) + rng.normalvariate(
            0, perceived_sigma
        )
        organization.phenotype[trait] = clamp(value + learning * (perceived - value))
    organization.discipline = organization.phenotype["discipline"]
    organization.local_knowledge = organization.phenotype["local_embeddedness"]


def split_organization(world, organization_id: str, time: float, rng: random.Random):
    synchronize_memberships(world)
    parent = world.organizations[organization_id]
    members = list(parent.member_ids)
    total_weight = sum(world.persons[pid].weight * world.persons[pid].armed_fraction
                       for pid in members if pid in world.persons)
    if total_weight <= 0 or len(members) < 2:  # raw count is only a data-structure safety check
        return ()
    # Factions follow geographic/social community structure, not equal slicing.
    groups: dict[str, list[str]] = {}
    for pid in members:
        person = world.persons[pid]
        groups.setdefault(person.community_id or person.residence_locality_id, []).append(pid)
    ordered = sorted(groups.values(), key=lambda group: (-sum(
        world.persons[pid].weight * world.persons[pid].armed_fraction for pid in group
    ), group[0]))
    faction_a = set(ordered[0])
    faction_b = set(members) - faction_a
    if not faction_b:
        # Weighted fallback: allocate roughly one third of represented people
        # to the second faction rather than slicing by sampled-agent count.
        target_weight = total_weight / 3
        faction_b = set()
        running = 0.0
        for pid in sorted(members, key=lambda item: (
                world.persons[item].weight * world.persons[item].armed_fraction, item), reverse=True):
            faction_b.add(pid)
            running += world.persons[pid].weight * world.persons[pid].armed_fraction
            if running >= target_weight:
                break
        faction_a = set(members) - faction_b
        if not faction_a:
            return ()
    shares = [sum(world.persons[pid].weight * world.persons[pid].armed_fraction for pid in faction) / max(1e-9, total_weight)
              for faction in (faction_a, faction_b)]
    children = []
    parent_leader = world.leaders.get(parent.leader_id or "")
    for index, (faction, share) in enumerate(zip((faction_a, faction_b), shares), 1):
        child = deepcopy(parent)
        child.organization_id = f"{organization_id}-s{len(world.organization_transitions)+1}-{index}"
        child.name = f"{parent.name} Faction {index}"
        child.resources = parent.resources * share
        child.member_ids = faction
        child.parent_ids = (organization_id,)
        child.founded_at = time
        child.status = "active"
        child.cohesion = clamp(parent.cohesion * (.72 + .18 * share))
        child.phenotype = {k: clamp(v + rng.normalvariate(0, .04)) for k, v in parent.phenotype.items()}
        world.organizations[child.organization_id] = child
        for locality in world.localities.values():
            inherited_control = locality.control.get(organization_id,
                                                     locality.control.get("insurgent", ControlVector()))
            locality.control[child.organization_id] = deepcopy(inherited_control)
        for zone in world.microzones.values():
            zone.physical_control[child.organization_id] = zone.physical_control.get(
                organization_id, zone.physical_control.get("insurgent", 0.0))
        _create_leader(world, child, rng, parent_leader)
        for pid in faction:
            person = world.persons[pid]
            _set_armed_membership(person, child, person.armed_fraction)
        children.append(child)
    formations = [f for f in world.formations.values() if f.organization_id == organization_id]
    assignments = {c.organization_id: [] for c in children}
    for formation in formations:
        local_counts = [sum(world.persons[pid].weight * world.persons[pid].armed_fraction
                            for pid in child.member_ids
                            if world.persons[pid].residence_locality_id == formation.locality_id)
                        for child in children]
        child = children[local_counts.index(max(local_counts))]
        formation.organization_id = child.organization_id
        assignments[child.organization_id].append(formation.formation_id)
        _rewire_formation_command(world, formation, child)
    _transfer_sources(world, {organization_id}, children)
    _transfer_manpower_pools(world, {organization_id}, children)
    parent.resources = 0.0
    parent.member_ids.clear()
    parent.status = "fragmented"
    _transition(world, time, "split", (organization_id,), tuple(c.organization_id for c in children),
                {c.organization_id: c.member_ids for c in children},
                {c.organization_id: c.resources for c in children}, assignments,
                {"cohesion": parent.cohesion, "military_losses": sum(f.cumulative_losses for f in formations)})
    inherit_parent_relations(
        world, (organization_id,), tuple(c.organization_id for c in children), time
    )
    return tuple(children)


def merge_organizations(world, first_id: str, second_id: str, time: float, rng: random.Random):
    first, second = world.organizations[first_id], world.organizations[second_id]
    child = deepcopy(first)
    child.organization_id = f"merged-{len(world.organization_transitions)+1:03d}"
    child.name = f"{first.name}–{second.name} Coalition"
    total = first.resources + second.resources
    child.resources = total
    child.member_ids = set(first.member_ids) | set(second.member_ids)
    child.parent_ids = (first_id, second_id)
    child.founded_at = time
    child.cohesion = clamp((first.cohesion + second.cohesion) / 2 - .08)
    child.phenotype = {key: clamp((first.phenotype[key] + second.phenotype[key]) / 2 +
                                  rng.normalvariate(0, .02)) for key in first.phenotype}
    child.ideology = {key: (first.ideology.get(key, .5) + second.ideology.get(key, .5)) / 2
                       for key in set(first.ideology) | set(second.ideology)}
    world.organizations[child.organization_id] = child
    for locality in world.localities.values():
        first_control = locality.control.get(first_id, locality.control.get("insurgent", ControlVector()))
        second_control = locality.control.get(second_id, locality.control.get("insurgent", ControlVector()))
        locality.control[child.organization_id] = ControlVector(**{
            key: (first_control.to_dict()[key] + second_control.to_dict()[key]) / 2
            for key in first_control.to_dict()
        })
    for zone in world.microzones.values():
        zone.physical_control[child.organization_id] = (
            zone.physical_control.get(first_id, zone.physical_control.get("insurgent", 0.0)) +
            zone.physical_control.get(second_id, zone.physical_control.get("insurgent", 0.0))) / 2
    _create_leader(world, child, rng, world.leaders.get(first.leader_id or ""))
    formations = []
    for formation in world.formations.values():
        if formation.organization_id in {first_id, second_id}:
            formation.organization_id = child.organization_id
            formations.append(formation.formation_id)
            _rewire_formation_command(world, formation, child)
    _transfer_sources(world, {first_id, second_id}, [child])
    _transfer_manpower_pools(world, {first_id, second_id}, [child])
    for pid in child.member_ids:
        person = world.persons[pid]
        _set_armed_membership(person, child, person.armed_fraction)
    for parent in (first, second):
        parent.resources = 0.0
        parent.member_ids.clear()
        parent.status = "merged"
    _transition(world, time, "merge", (first_id, second_id), (child.organization_id,),
                {child.organization_id: child.member_ids}, {child.organization_id: total},
                {child.organization_id: formations}, {"integration_cost": .08})
    inherit_parent_relations(
        world, (first_id, second_id), (child.organization_id,), time
    )
    return child


def collapse_organization(world, organization_id: str, time: float, reason: str):
    organization = world.organizations[organization_id]
    former = set(organization.member_ids)
    for pid in former:
        # A stale inactive-organization membership can overlap a later active
        # assignment after split/merge transitions.  Never clear ownership
        # belonging to another organization; the member-set cleanup below is
        # sufficient for the collapsing organization and preserves reciprocal
        # membership invariants.
        if world.persons[pid].organization_id == organization_id:
            _set_armed_membership(world.persons[pid], None, 0.0)
    organization.member_ids.clear()
    organization.status = "collapsed"
    pooled_demobilized = 0.0
    for key, quantity in list(world.organization_manpower_pools.items()):
        if key[0] == organization_id:
            pooled_demobilized += quantity
            del world.organization_manpower_pools[key]
    pooled_arms = 0.0
    for key, quantity in list(world.organization_manpower_supply_reserves.items()):
        if key[0] == organization_id:
            pooled_arms += quantity
            del world.organization_manpower_supply_reserves[key]
    world.demobilized_personnel += pooled_demobilized
    world.demobilized_arms += pooled_arms
    formations = []
    for formation in world.formations.values():
        if formation.organization_id == organization_id:
            formation.operational_status = "ineffective"
            formation.availability = 0.0
            formations.append(formation.formation_id)
    return _transition(world, time, "collapse", (organization_id,), (), {}, {},
                       {organization_id: formations}, {"reason": reason,
                                                       "nonzero_manpower": sum(world.formations[f].personnel for f in formations),
                                                       "pooled_demobilized": pooled_demobilized,
                                                       "pooled_demobilized_arms": pooled_arms})


def organization_survival_social_base(world, organization: Organization) -> float:
    """Return a bounded, resolution-safe measure of embedded organizational base.

    Survival should depend on the organization's represented constituency and
    local embeddedness, not on how many unrelated civilians exist elsewhere in
    the synthetic country.  Membership therefore saturates against the same
    represented-population scale used for viable proto-organizations, with an
    additional local-depth term and the organization's explicit social /
    embeddedness state.
    """
    by_locality: dict[str, float] = {}
    total = 0.0
    for person_id in organization.member_ids:
        person = world.persons.get(person_id)
        if (person is None or person.organization_id != organization.organization_id or
                person.armed_fraction <= 0):
            continue
        represented = person.weight * person.armed_fraction
        total += represented
        by_locality[person.residence_locality_id] = (
            by_locality.get(person.residence_locality_id, 0.0) + represented
        )
    scale = max(
        1e-9, world.config.organization_ecology.minimum_proto_represented_population
    )

    def saturating(quantity: float) -> float:
        return quantity / (quantity + scale) if quantity > 0 else 0.0

    represented_base = saturating(total)
    local_depth = max((saturating(quantity) for quantity in by_locality.values()),
                      default=0.0)
    return clamp(
        .50 * represented_base +
        .25 * local_depth +
        .125 * organization.capital.get("social", 0.0) +
        .125 * organization.phenotype.get("local_embeddedness",
                                           organization.local_knowledge)
    )


def process_organization_ecology(world, time: float, rng: random.Random,
                                 interval_days: float | None = None) -> dict:
    cfg = world.config.organization_ecology
    if not cfg.enabled:
        return {"births": 0, "splits": 0, "mergers": 0, "collapses": 0}
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("organization ecology interval_days must be positive")
    created = form_proto_organizations(world, time, rng, interval_days=interval_days)
    births = sum(mature_proto(world, proto, time, rng, interval_days=interval_days) is not None
                 for proto in list(world.proto_organizations.values()) if proto.status == "mobilizing")
    splits = collapses = mergers = 0
    for organization in list(armed_organizations(world)):
        conditioned_active = any(
            float(start) <= time <= float(end)
            for start, end in cfg.observed_active_intervals.get(organization.organization_id, [])
        )
        formations = [f for f in world.formations.values() if f.organization_id == organization.organization_id]
        losses = sum(f.cumulative_losses for f in formations) / max(1, sum(f.personnel + f.cumulative_losses for f in formations))
        member_people = [world.persons[pid] for pid in organization.member_ids]
        represented_weight = sum(p.weight * p.armed_fraction for p in member_people)
        mean_identity = (sum(p.weight * p.armed_fraction * p.identities.get("federal", .5)
                             for p in member_people) /
                         max(1e-9, represented_weight))
        identity_variance = (sum(p.weight * p.armed_fraction *
                                 (p.identities.get("federal", .5) - mean_identity) ** 2
                                 for p in member_people) /
                             max(1e-9, represented_weight))
        cycle_scale = interval_days / _ECOLOGY_REFERENCE_CYCLE_DAYS
        organization.cohesion = clamp(
            organization.cohesion + cycle_scale * (
                .025 * organization.capital["social"] -
                cfg.cohesion_loss_memory * losses -
                .02 * identity_variance
            )
        )
        organization.capital["material"] = clamp(organization.resources / 150_000)
        _adapt(world, organization, rng, interval_days=interval_days)
        for formation in formations:
            formation.embeddedness = organization.phenotype["local_embeddedness"]
            formation.mobility = clamp(.35 + .5 * organization.phenotype["dispersion"])
            _rewire_formation_command(world, formation, organization)
        succession_probability = _reference_cycle_probability(
            cfg.succession_base_hazard * (1.4 - organization.cohesion),
            interval_days,
        )
        if rng.random() < succession_probability:
            previous = world.leaders.get(organization.leader_id or "")
            if previous is not None:
                previous.active = False
            successor = _create_leader(world, organization, rng, previous)
            organization.succession_count += 1
            organization.phenotype["risk_tolerance"] = clamp(
                (organization.phenotype["risk_tolerance"] + successor.risk_tolerance) / 2)
            _transition(world, time, "succession", (organization.organization_id,),
                        (organization.organization_id,),
                        {organization.organization_id: organization.member_ids},
                        {organization.organization_id: organization.resources},
                        {organization.organization_id: tuple(f.formation_id for f in formations)},
                        {"previous_leader": previous.leader_id if previous else "",
                         "new_leader": successor.leader_id})
        split_hazard = 1 - exp(
            -cfg.split_base_hazard *
            exp(2 * identity_variance + 3 * losses - 2 * organization.cohesion) *
            interval_days / _ECOLOGY_REFERENCE_CYCLE_DAYS
        )
        split_eligible = represented_weight >= cfg.minimum_split_represented_population
        split_draw = rng.random() if split_eligible else None
        world.organization_eligibility_log.append({
            "time": time, "organization_id": organization.organization_id,
            "eligible": split_eligible, "represented_members": represented_weight,
            "identity_variance": identity_variance, "losses": losses,
            "cohesion": organization.cohesion, "split_hazard": split_hazard,
            "draw": split_draw,
            "split": bool(split_draw is not None and split_draw < split_hazard),
        })
        if split_eligible and split_draw < split_hazard and not conditioned_active:
            split_organization(world, organization.organization_id, time, rng)
            splits += 1
            continue
        social_base = organization_survival_social_base(world, organization)
        collapse_hazard = 1 - exp(
            -cfg.collapse_base_hazard *
            exp(2 * (1 - organization.cohesion) + 2 * losses - 3 * social_base -
                1.5 * organization.external_sanctuary) *
            interval_days / _ECOLOGY_REFERENCE_CYCLE_DAYS
        )
        reason = ("resource_insolvency" if organization.resources <= 0 else
                  "cohesion_collapse" if organization.cohesion < .12 else
                  "social_base_loss" if represented_weight <= 1e-9 else None)
        collapse_draw = rng.random()
        if not conditioned_active and (reason or collapse_draw < collapse_hazard):
            collapse_organization(world, organization.organization_id, time, reason or "sustained_degradation")
            collapses += 1
    active = armed_organizations(world)
    if len(active) >= 2:
        candidates = []
        for first, second in combinations(active, 2):
            if any(any(float(start) <= time <= float(end) for start, end in
                       cfg.observed_active_intervals.get(actor.organization_id, []))
                   for actor in (first, second)):
                continue
            keys = set(first.ideology) | set(second.ideology)
            compatibility = 1 - sum(abs(first.ideology.get(k, .5) - second.ideology.get(k, .5))
                                    for k in keys) / max(1, len(keys))
            contact_overlap = organization_contact_overlap(world, first, second)
            hazard = _reference_cycle_probability(
                cfg.merger_base_hazard * compatibility *
                (2 - first.cohesion - second.cohesion) / 2 * contact_overlap,
                interval_days,
            )
            candidates.append((hazard, first.organization_id, second.organization_id))
        if candidates:
            hazard, first_id, second_id = max(candidates, key=lambda item: (item[0], item[1], item[2]))
            if rng.random() < hazard:
                merge_organizations(world, first_id, second_id, time, rng)
                mergers = 1
    relation_updates = update_relationship_ecology(
        world, time, interval_days, rng
    )
    synchronize_memberships(world)
    return {"proto_created": len(created), "births": births, "splits": splits,
            "mergers": mergers, "collapses": collapses,
            "active_armed_organizations": len(armed_organizations(world)),
            "relationship_updates": relation_updates}


def genealogy(world, organization_id: str) -> dict:
    organization = world.organizations[organization_id]
    children = [o.organization_id for o in world.organizations.values()
                if organization_id in o.parent_ids]
    return {"organization_id": organization_id, "parents": organization.parent_ids,
            "children": tuple(children), "status": organization.status,
            "founded_at": organization.founded_at,
            "phenotype": dict(organization.phenotype)}


def organization_ecology_diagnostics(world) -> dict:
    return {
        "active": [o.organization_id for o in armed_organizations(world)],
        "proto_organizations": len(world.proto_organizations),
        "transition_counts": {kind: sum(t.transition_type == kind for t in world.organization_transitions)
                              for kind in ("birth", "proto_collapse", "split", "merge", "collapse")},
        "eligibility": {
            "periods": len(world.organization_eligibility_log),
            "eligible_periods": sum(row["eligible"] for row in world.organization_eligibility_log),
            "splits_given_eligible": (
                sum(row["split"] for row in world.organization_eligibility_log if row["eligible"]) /
                max(1, sum(row["eligible"] for row in world.organization_eligibility_log))
            ),
        },
        "genealogy": {o.organization_id: genealogy(world, o.organization_id)
                      for o in world.organizations.values() if o.kind is OrganizationKind.INSURGENT},
        "franchise_support_by_locality": {
            locality_id: locality_franchise_support_profile(world, locality_id)
            for locality_id in world.localities
        },
    }
