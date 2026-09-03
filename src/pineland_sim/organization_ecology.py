"""Endogenous armed-organization birth, adaptation, transition, and death."""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from math import exp
import random

from .entities import (ArmedFormation, ControlVector, LeadershipAgent, Organization,
                       OrganizationKind, OrganizationTransition, ProtoOrganization,
                       clamp, logistic)
from .logistics import _add_command_edge


def armed_organizations(world, active_only: bool = True):
    return [o for o in world.organizations.values()
            if o.kind is OrganizationKind.INSURGENT and (not active_only or o.status == "active")]


def initialize_organization_ecology(world) -> None:
    rng = __import__("pineland_sim.world", fromlist=["seeded_rng"]).seeded_rng(
        world.config, "organization-ecology-generation")
    for organization in armed_organizations(world, active_only=False):
        if not organization.member_ids:
            formation_localities = {f.locality_id for f in world.formations.values()
                                    if f.organization_id == organization.organization_id}
            candidates = [p for p in world.persons.values()
                          if p.residence_locality_id in formation_localities]
            count = min(len(candidates), max(3, round(len(world.persons) *
                                                     world.config.initial_insurgent_share)))
            for person in sorted(candidates, key=lambda p: (-p.grievance, p.person_id))[:count]:
                person.organization_id = organization.organization_id
                person.public_behavior = "armed_participation"
                organization.member_ids.add(person.person_id)
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
        counts = [sum(world.persons[pid].residence_locality_id == source.locality_id
                      for pid in child.member_ids) for child in children]
        source.organization_id = children[counts.index(max(counts))].organization_id


def _mobilization_score(world, community) -> tuple[float, list]:
    people = [world.persons[pid] for pid in community.member_ids]
    if not people:
        return 0.0, []
    mobilized = [p for p in people if p.organization_id is None and
                 (p.public_behavior in {"protest", "insurgent_sympathy", "armed_participation"}
                  or p.grievance > .55)]
    grievance = sum(p.grievance for p in people) / len(people)
    represented_people = sum(person.weight for person in people)
    bridge_weight = sum(world.persons[pid].weight for pid in community.bridge_member_ids
                        if pid in world.persons)
    reach = min(1.0, bridge_weight / max(1.0, represented_people) * 5)
    access = sum(p.political_access for p in people) / len(people)
    score = clamp(.3 * grievance + .3 * community.cohesion + .2 * community.insurgent_sympathy +
                  .2 * reach - world.config.political_order.peaceful_channel_strength * .25 * access)
    return score, mobilized


def _mean_representation_weight(world) -> float:
    return sum(person.weight for person in world.persons.values()) / max(1, len(world.persons))


def form_proto_organizations(world, time: float, rng: random.Random) -> list[ProtoOrganization]:
    cfg = world.config.organization_ecology
    active_communities = {p.community_id for p in world.proto_organizations.values() if p.status == "mobilizing"}
    created = []
    for community in world.social_communities.values():
        if community.community_id in active_communities:
            continue
        score, mobilized = _mobilization_score(world, community)
        mobilized_weight = sum(person.weight for person in mobilized)
        minimum_proto_weight = max(
            cfg.minimum_proto_represented_population,
            cfg.minimum_proto_members * _mean_representation_weight(world),
        )
        if mobilized_weight < minimum_proto_weight:
            continue
        locality = world.localities[community.locality_id]
        repression = locality.control["government"].physical
        hazard = 1 - exp(-cfg.proto_base_hazard * exp(2.2 * score - 1.4 * repression))
        if rng.random() >= hazard:
            continue
        selected = []
        selected_weight = 0.0
        target_weight = max(minimum_proto_weight, mobilized_weight * .5)
        for person in sorted(mobilized, key=lambda p: (-p.grievance, p.person_id)):
            selected.append(person)
            selected_weight += person.weight
            if selected_weight >= target_weight:
                break
        proto = ProtoOrganization(
            f"PROTO{len(world.proto_organizations) + 1:07d}", community.community_id,
            community.locality_id, {p.person_id for p in selected},
            {"social": community.cohesion, "political": score,
             "organizational": .12 + .25 * community.cohesion,
             "material": clamp(sum(p.resources for p in selected) / max(1, len(selected) * 3))},
            {"reform": clamp(.4 + score / 2), "separatism": clamp(.15 + .3 * score)},
            clamp(max((p.efficacy for p in selected), default=.3)), time,
        )
        world.proto_organizations[proto.proto_id] = proto
        created.append(proto)
    return created


def mature_proto(world, proto: ProtoOrganization, time: float, rng: random.Random):
    cfg = world.config.organization_ecology
    capital = sum(proto.capital.values()) / 4
    locality = world.localities[proto.locality_id]
    hazard = 1 - exp(-cfg.birth_base_hazard * exp(2.4 * capital + proto.leadership_potential -
                                                   1.6 * locality.control["government"].physical))
    if rng.random() >= hazard:
        for key in proto.capital:
            proto.capital[key] = clamp(proto.capital[key] * (1 - cfg.proto_decay_rate * cfg.interval_days / 7))
        if sum(proto.capital.values()) / 4 < .08:
            proto.status = "collapsed"
            _transition(world, time, "proto_collapse", (proto.proto_id,), (), {}, {}, {},
                        {"capital": capital})
        return None
    # Check represented manpower before mutating civilian ownership or
    # transferring resources.  A weighted representative can satisfy a
    # capital/onset draw while still being too small to field a viable
    # formation; that proto must collapse atomically, without leaving people
    # assigned to a non-existent organization or consuming startup resources.
    represented_members = sum(world.persons[pid].weight for pid in proto.member_ids)
    personnel = represented_members * cfg.fighter_conversion_fraction
    if personnel < cfg.minimum_formation_personnel:
        proto.status = "collapsed"
        _transition(world, time, "proto_collapse", (proto.proto_id,), (), {}, {}, {},
                    {"reason": "insufficient_represented_manpower", "personnel": personnel})
        return None
    oid = f"armed-{len([o for o in world.organizations if o.startswith('armed-')]) + 1:03d}"
    contributed = sum(world.persons[pid].resources * cfg.onset_resource_fraction for pid in proto.member_ids)
    for pid in proto.member_ids:
        world.persons[pid].resources -= world.persons[pid].resources * cfg.onset_resource_fraction
        world.persons[pid].organization_id = oid
    organization = Organization(
        oid, f"Emergent Organization {oid[-3:]}", OrganizationKind.INSURGENT,
        contributed, clamp(.35 + .4 * proto.capital["organizational"]), .5, .2,
        proto.capital["social"], .65, .55, .45, set(proto.member_ids), 0.0,
        dict(proto.capital), {}, dict(proto.ideology), "active", time, (proto.proto_id,), None,
        cfg.adaptation_rate,
    )
    organization.phenotype = {
        "centralization": rng.uniform(.3, .7), "political_investment": proto.capital["political"],
        "governance_investment": rng.uniform(.2, .6), "dispersion": rng.uniform(.4, .8),
        "risk_tolerance": rng.uniform(.3, .75), "discipline": organization.discipline,
        "local_embeddedness": proto.capital["social"], "resource_dependence": .1,
    }
    world.organizations[oid] = organization
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
    _transition(world, time, "birth", (proto.proto_id,), (oid,), {oid: proto.member_ids},
                {oid: contributed}, {oid: (fid,)}, {"formation_hazard": hazard})
    return organization


def recruit_and_retain(world, time: float, rng: random.Random) -> dict[str, float]:
    recruits = exits = 0.0
    rate = world.config.recruitment_rate
    cfg = world.config.organization_ecology
    for organization in armed_organizations(world):
        formations = [f for f in world.formations.values() if f.organization_id == organization.organization_id]
        for person in world.persons.values():
            if person.organization_id is None:
                exposure = person.social_exposure.get(organization.organization_id,
                                                       person.social_exposure.get("insurgent", 0.0))
                compatibility = 1 - abs(person.identities.get("federal", .5) - organization.ideology.get("reform", .5))
                probability = rate * logistic(1.5 * person.grievance + exposure + compatibility +
                                              organization.capital["social"] - person.fear - 2.6 -
                                              world.config.political_order.peaceful_channel_strength * person.political_access)
                if rng.random() < probability:
                    person.organization_id = organization.organization_id
                    organization.member_ids.add(person.person_id)
                    recruits += person.weight
                    diversity = abs(compatibility - .5) * 2
                    organization.cohesion = clamp(organization.cohesion -
                                                  cfg.recruitment_diversity_penalty * diversity /
                                                  max(10, len(organization.member_ids)))
                    if formations:
                        formations[0].personnel += person.weight * cfg.fighter_conversion_fraction
            elif person.organization_id == organization.organization_id:
                if rng.random() < rate * logistic(person.fear + .7 - organization.cohesion - person.grievance):
                    person.organization_id = None
                    organization.member_ids.discard(person.person_id)
                    exits += person.weight
                    if formations:
                        formations[0].personnel = max(
                            0, formations[0].personnel - person.weight * cfg.fighter_conversion_fraction)
    return {"recruits": recruits, "exits": exits}


def _adapt(world, organization: Organization, rng: random.Random) -> None:
    peers = [o for o in armed_organizations(world) if o.organization_id != organization.organization_id]
    if not peers:
        return
    success = lambda o: sum(f.effective_strength() for f in world.formations.values()
                            if f.organization_id == o.organization_id) + o.resources / 100
    exemplar = max(peers, key=success)
    learning = organization.adaptation_rate * (.4 + .6 * organization.institutional_quality)
    for trait, value in organization.phenotype.items():
        perceived = exemplar.phenotype[trait] + rng.normalvariate(0, world.config.organization_ecology.mutation_sigma)
        organization.phenotype[trait] = clamp(value + learning * (perceived - value))
    organization.discipline = organization.phenotype["discipline"]
    organization.local_knowledge = organization.phenotype["local_embeddedness"]


def split_organization(world, organization_id: str, time: float, rng: random.Random):
    parent = world.organizations[organization_id]
    members = list(parent.member_ids)
    if len(members) < 2:
        return ()
    # Factions follow geographic/social community structure, not equal slicing.
    groups: dict[str, list[str]] = {}
    for pid in members:
        person = world.persons[pid]
        groups.setdefault(person.community_id or person.residence_locality_id, []).append(pid)
    ordered = sorted(groups.values(), key=lambda group: (-sum(world.persons[pid].weight for pid in group), group[0]))
    faction_a = set(ordered[0])
    faction_b = set(members) - faction_a
    if not faction_b:
        pivot = max(1, len(members) // 3)
        faction_a, faction_b = set(sorted(members)[:-pivot]), set(sorted(members)[-pivot:])
    total_weight = sum(world.persons[pid].weight for pid in members)
    shares = [sum(world.persons[pid].weight for pid in faction) / max(1e-9, total_weight)
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
            world.persons[pid].organization_id = child.organization_id
        children.append(child)
    formations = [f for f in world.formations.values() if f.organization_id == organization_id]
    assignments = {c.organization_id: [] for c in children}
    for formation in formations:
        local_counts = [sum(world.persons[pid].residence_locality_id == formation.locality_id
                            for pid in child.member_ids) for child in children]
        child = children[local_counts.index(max(local_counts))]
        formation.organization_id = child.organization_id
        assignments[child.organization_id].append(formation.formation_id)
        _rewire_formation_command(world, formation, child)
    _transfer_sources(world, {organization_id}, children)
    parent.resources = 0.0
    parent.member_ids.clear()
    parent.status = "fragmented"
    _transition(world, time, "split", (organization_id,), tuple(c.organization_id for c in children),
                {c.organization_id: c.member_ids for c in children},
                {c.organization_id: c.resources for c in children}, assignments,
                {"cohesion": parent.cohesion, "military_losses": sum(f.cumulative_losses for f in formations)})
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
    for pid in child.member_ids:
        world.persons[pid].organization_id = child.organization_id
    for parent in (first, second):
        parent.resources = 0.0
        parent.member_ids.clear()
        parent.status = "merged"
    _transition(world, time, "merge", (first_id, second_id), (child.organization_id,),
                {child.organization_id: child.member_ids}, {child.organization_id: total},
                {child.organization_id: formations}, {"integration_cost": .08})
    return child


def collapse_organization(world, organization_id: str, time: float, reason: str):
    organization = world.organizations[organization_id]
    former = set(organization.member_ids)
    for pid in former:
        world.persons[pid].organization_id = None
    organization.member_ids.clear()
    organization.status = "collapsed"
    formations = []
    for formation in world.formations.values():
        if formation.organization_id == organization_id:
            formation.operational_status = "ineffective"
            formation.availability = 0.0
            formations.append(formation.formation_id)
    return _transition(world, time, "collapse", (organization_id,), (), {}, {},
                       {organization_id: formations}, {"reason": reason,
                                                       "nonzero_manpower": sum(world.formations[f].personnel for f in formations)})


def process_organization_ecology(world, time: float, rng: random.Random) -> dict:
    cfg = world.config.organization_ecology
    if not cfg.enabled:
        return {"births": 0, "splits": 0, "mergers": 0, "collapses": 0}
    created = form_proto_organizations(world, time, rng)
    births = sum(mature_proto(world, proto, time, rng) is not None
                 for proto in list(world.proto_organizations.values()) if proto.status == "mobilizing")
    splits = collapses = mergers = 0
    for organization in list(armed_organizations(world)):
        formations = [f for f in world.formations.values() if f.organization_id == organization.organization_id]
        losses = sum(f.cumulative_losses for f in formations) / max(1, sum(f.personnel + f.cumulative_losses for f in formations))
        member_people = [world.persons[pid] for pid in organization.member_ids]
        represented_weight = sum(p.weight for p in member_people)
        mean_identity = (sum(p.weight * p.identities.get("federal", .5) for p in member_people) /
                         max(1e-9, represented_weight))
        identity_variance = (sum(p.weight * (p.identities.get("federal", .5) - mean_identity) ** 2
                                 for p in member_people) /
                             max(1e-9, represented_weight))
        organization.cohesion = clamp(organization.cohesion +
                                      .025 * organization.capital["social"] -
                                      cfg.cohesion_loss_memory * losses - .02 * identity_variance)
        organization.capital["material"] = clamp(organization.resources / 150_000)
        _adapt(world, organization, rng)
        for formation in formations:
            formation.embeddedness = organization.phenotype["local_embeddedness"]
            formation.mobility = clamp(.35 + .5 * organization.phenotype["dispersion"])
            _rewire_formation_command(world, formation, organization)
        if rng.random() < cfg.succession_base_hazard * (1.4 - organization.cohesion):
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
        split_hazard = 1 - exp(-cfg.split_base_hazard * exp(2 * identity_variance + 3 * losses -
                                                            2 * organization.cohesion))
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
        if split_eligible and split_draw < split_hazard:
            split_organization(world, organization.organization_id, time, rng)
            splits += 1
            continue
        social_base = represented_weight / max(1e-9, sum(person.weight for person in world.persons.values()))
        collapse_hazard = 1 - exp(-cfg.collapse_base_hazard * exp(2 * (1 - organization.cohesion) +
                                                                      2 * losses - 3 * social_base -
                                                                      1.5 * organization.external_sanctuary))
        reason = ("resource_insolvency" if organization.resources <= 0 else
                  "cohesion_collapse" if organization.cohesion < .12 else
                  "social_base_loss" if not organization.member_ids else None)
        if reason or rng.random() < collapse_hazard:
            collapse_organization(world, organization.organization_id, time, reason or "sustained_degradation")
            collapses += 1
    active = armed_organizations(world)
    if len(active) >= 2:
        candidates = []
        for first, second in combinations(active, 2):
            keys = set(first.ideology) | set(second.ideology)
            compatibility = 1 - sum(abs(first.ideology.get(k, .5) - second.ideology.get(k, .5))
                                    for k in keys) / max(1, len(keys))
            hazard = cfg.merger_base_hazard * compatibility * (2 - first.cohesion - second.cohesion) / 2
            candidates.append((hazard, first.organization_id, second.organization_id))
        hazard, first_id, second_id = max(candidates, key=lambda item: (item[0], item[1], item[2]))
        if rng.random() < hazard:
            merge_organizations(world, first_id, second_id, time, rng)
            mergers = 1
    return {"proto_created": len(created), "births": births, "splits": splits,
            "mergers": mergers, "collapses": collapses,
            "active_armed_organizations": len(armed_organizations(world))}


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
    }
