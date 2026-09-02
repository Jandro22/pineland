from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
import json
from math import ceil
from statistics import mean, median

from .entities import LANGUAGES, SocialCommunity, SocialEdge, clamp
from .world import WorldState, seeded_rng


def language_compatibility(first: dict[str, float], second: dict[str, float]) -> float:
    """Best mutually comprehensible shared language: max_r min(l_ir, l_jr)."""
    return clamp(max(min(first.get(language, 0.0), second.get(language, 0.0)) for language in LANGUAGES))


def _edge_key(person_a_id: str, person_b_id: str) -> tuple[str, str]:
    if person_a_id == person_b_id:
        raise ValueError("self edges are not permitted")
    return tuple(sorted((person_a_id, person_b_id)))


def _add_edge(world: WorldState, person_a_id: str, person_b_id: str, layer: str,
              base_strength: float, trust: float) -> None:
    if person_a_id == person_b_id:
        return
    key = _edge_key(person_a_id, person_b_id)
    first = world.persons[key[0]]
    second = world.persons[key[1]]
    compatibility = language_compatibility(first.languages, second.languages)
    weight = clamp(base_strength * (.35 + .65 * compatibility))
    represented_relationships = 2 * first.weight * second.weight / max(1e-12, first.weight + second.weight)
    existing = world.social_edges.get(key)
    if existing:
        existing.layers = tuple(sorted(set(existing.layers) | {layer}))
        existing.weight = max(existing.weight, weight)
        existing.trust = max(existing.trust, clamp(trust))
        existing.language_compatibility = max(existing.language_compatibility, compatibility)
        existing.represented_relationships = max(existing.represented_relationships, represented_relationships)
        return
    world.social_edges[key] = SocialEdge(
        key[0], key[1], (layer,), weight, compatibility, clamp(trust), represented_relationships
    )
    world.social_neighbors[key[0]].append(key[1])
    world.social_neighbors[key[1]].append(key[0])


def _balanced_household_groups(world: WorldState, household_ids: list[str], minimum: int,
                               target: int, maximum: int, rng) -> list[list[str]]:
    rng.shuffle(household_ids)
    groups: list[list[str]] = []
    current: list[str] = []
    current_size = 0
    for household_id in household_ids:
        household_size = len(world.households[household_id].member_ids)
        if current and current_size + household_size > maximum:
            groups.append(current)
            current = []
            current_size = 0
        current.append(household_id)
        current_size += household_size
        if current_size >= target:
            groups.append(current)
            current = []
            current_size = 0
    if current:
        current_count = sum(len(world.households[h].member_ids) for h in current)
        previous_count = sum(len(world.households[h].member_ids) for h in groups[-1]) if groups else 0
        if groups and current_count < target // 2 and previous_count + current_count <= maximum:
            groups[-1].extend(current)
        else:
            if groups and current_count < minimum:
                while groups[-1] and current_count < minimum:
                    candidate = groups[-1][-1]
                    candidate_size = len(world.households[candidate].member_ids)
                    if previous_count - candidate_size < minimum or current_count + candidate_size > maximum:
                        break
                    groups[-1].pop()
                    current.insert(0, candidate)
                    previous_count -= candidate_size
                    current_count += candidate_size
            groups.append(current)
    return groups


def _language_profile(world: WorldState, member_ids: list[str]) -> dict[str, float]:
    if not member_ids:
        return {language: 0.0 for language in LANGUAGES}
    return {language: mean(world.persons[person_id].languages[language] for person_id in member_ids)
            for language in LANGUAGES}


def generate_social_network(world: WorldState) -> None:
    """Build household, community, and cross-community information/social ties."""
    config = world.config.social_network
    rng = seeded_rng(world.config, "social-network-generation")
    world.social_communities.clear()
    world.social_edges.clear()
    world.social_neighbors = {person_id: [] for person_id in world.persons}

    households_by_locality: dict[str, list[str]] = defaultdict(list)
    for household in world.households.values():
        households_by_locality[household.home_locality_id].append(household.household_id)

    community_index = 0
    for locality_id in sorted(world.localities):
        groups = _balanced_household_groups(
            world, sorted(households_by_locality[locality_id]),
            config.minimum_community_size, config.target_community_size,
            config.maximum_community_size, rng,
        )
        for household_ids in groups:
            member_ids = [person_id for household_id in household_ids
                          for person_id in world.households[household_id].member_ids]
            community_id = f"C{community_index:06d}"
            community_index += 1
            community = SocialCommunity(
                community_id, locality_id, member_ids, _language_profile(world, member_ids),
                cohesion=rng.uniform(.45, .85),
            )
            world.social_communities[community_id] = community
            for person_id in member_ids:
                world.persons[person_id].community_id = community_id

    # Household multiplex layer: dense strong ties within small resource-pooling units.
    for household in world.households.values():
        members = household.member_ids
        for index, first in enumerate(members):
            for second in members[index + 1:]:
                _add_edge(world, first, second, "household", config.household_tie_strength, .9)

    # Community layer: guaranteed connected ring plus heterogeneous sparse extra ties.
    for community in world.social_communities.values():
        members = list(community.member_ids)
        rng.shuffle(members)
        if len(members) > 1:
            for index, first in enumerate(members):
                _add_edge(world, first, members[(index + 1) % len(members)], "community",
                          config.community_tie_strength, community.cohesion)
        for person_id in members:
            target_degree = max(2, min(config.maximum_social_degree,
                                       round(rng.normalvariate(config.mean_social_degree, 2.0))))
            attempts = 0
            while len(world.social_neighbors[person_id]) < target_degree and attempts < target_degree * 5:
                attempts += 1
                candidate = rng.choice(members)
                if candidate != person_id and len(world.social_neighbors[candidate]) < config.maximum_social_degree:
                    _add_edge(world, person_id, candidate, "community",
                              config.community_tie_strength * rng.uniform(.7, 1.0), community.cohesion)

    communities_by_locality: dict[str, list[str]] = defaultdict(list)
    for community in world.social_communities.values():
        communities_by_locality[community.locality_id].append(community.community_id)

    # Multilingual agents preferentially become cross-community information bridges.
    for community in world.social_communities.values():
        member_ranking = sorted(
            community.member_ids,
            key=lambda person_id: sorted(world.persons[person_id].languages.values(), reverse=True)[1],
            reverse=True,
        )
        bridge_count = min(4, max(1, ceil(len(member_ranking) * config.bridge_fraction)))
        candidates = [cid for cid in communities_by_locality[community.locality_id] if cid != community.community_id]
        if not candidates:
            for neighbor_locality in world.adjacency[community.locality_id]:
                candidates.extend(communities_by_locality[neighbor_locality])
        if not candidates:
            continue
        for source_id in member_ranking[:bridge_count]:
            target_community = world.social_communities[rng.choice(candidates)]
            sample = rng.sample(target_community.member_ids, min(12, len(target_community.member_ids)))
            target_id = max(sample, key=lambda candidate: language_compatibility(
                world.persons[source_id].languages, world.persons[candidate].languages))
            _add_edge(world, source_id, target_id, "bridge", config.bridge_tie_strength, .5)
            community.bridge_member_ids.append(source_id)

    for neighbors in world.social_neighbors.values():
        neighbors.sort()


def edge_between(world: WorldState, first_id: str, second_id: str) -> SocialEdge:
    return world.social_edges[_edge_key(first_id, second_id)]


def refresh_community_aggregates(world: WorldState) -> None:
    for community in world.social_communities.values():
        total = sum(world.persons[person_id].weight for person_id in community.member_ids)
        if total <= 0:
            continue
        community.government_cooperation = sum(
            world.persons[person_id].weight for person_id in community.member_ids
            if world.persons[person_id].public_behavior == "government_cooperation"
        ) / total
        community.insurgent_sympathy = sum(
            world.persons[person_id].weight for person_id in community.member_ids
            if world.persons[person_id].public_behavior in {"insurgent_sympathy", "armed_participation"}
        ) / total


def locality_social_aggregation(world: WorldState, locality_id: str) -> dict[str, float]:
    communities = [community for community in world.social_communities.values()
                   if community.locality_id == locality_id]
    represented = [sum(world.persons[person_id].weight for person_id in community.member_ids)
                   for community in communities]
    total = sum(represented)
    if total <= 0:
        return {"government_cooperation": 0.0, "insurgent_sympathy": 0.0,
                "community_variance": 0.0}
    government = sum(community.government_cooperation * weight
                     for community, weight in zip(communities, represented)) / total
    insurgent = sum(community.insurgent_sympathy * weight
                    for community, weight in zip(communities, represented)) / total
    variance = sum(weight * (community.government_cooperation - government) ** 2
                   for community, weight in zip(communities, represented)) / total
    return {"government_cooperation": government, "insurgent_sympathy": insurgent,
            "community_variance": variance}


def network_diagnostics(world: WorldState, clustering_sample: int = 1_000) -> dict[str, float | int]:
    degrees = [len(world.social_neighbors[person_id]) for person_id in sorted(world.persons)]
    if not degrees:
        return {"nodes": 0, "edges": 0, "communities": 0, "components": 0,
                "mean_degree": 0.0, "median_degree": 0.0, "mean_language_compatibility": 0.0,
                "bridge_edges": 0, "sampled_clustering": 0.0}
    unseen = set(world.persons)
    components = 0
    while unseen:
        components += 1
        queue = deque([unseen.pop()])
        while queue:
            for neighbor in world.social_neighbors[queue.popleft()]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
    coefficients: list[float] = []
    for person_id in sorted(world.persons)[:clustering_sample]:
        neighbors = world.social_neighbors[person_id]
        possible = len(neighbors) * (len(neighbors) - 1) / 2
        if possible <= 0:
            continue
        neighbor_set = set(neighbors)
        closed = sum(1 for index, first in enumerate(neighbors)
                     for second in neighbors[index + 1:] if second in world.social_neighbors[first])
        coefficients.append(closed / possible)
    return {
        "nodes": len(world.persons),
        "edges": len(world.social_edges),
        "communities": len(world.social_communities),
        "components": components,
        "mean_degree": mean(degrees),
        "median_degree": median(degrees),
        "mean_language_compatibility": mean(edge.language_compatibility for edge in world.social_edges.values()),
        "bridge_edges": sum("bridge" in edge.layers for edge in world.social_edges.values()),
        "sampled_clustering": mean(coefficients) if coefficients else 0.0,
    }


def network_snapshot(world: WorldState, agent_ids: list[str] | None = None,
                     community_ids: list[str] | None = None,
                     default_agent_limit: int = 5,
                     default_community_limit: int = 2) -> dict:
    """Produce an opt-in, human-readable debug view; never emitted by default."""
    selected_agents = agent_ids or sorted(world.persons)[:default_agent_limit]
    selected_communities = list(community_ids or sorted(world.social_communities)[:default_community_limit])
    for person_id in selected_agents:
        if person_id in world.persons:
            community_id = world.persons[person_id].community_id
            if community_id and community_id not in selected_communities:
                selected_communities.append(community_id)
    missing_agents = [person_id for person_id in selected_agents if person_id not in world.persons]
    missing_communities = [community_id for community_id in selected_communities
                           if community_id not in world.social_communities]
    if missing_agents or missing_communities:
        raise KeyError({"missing_agents": missing_agents, "missing_communities": missing_communities})
    agents: dict[str, dict] = {}
    for person_id in selected_agents:
        person = world.persons[person_id]
        neighbors = []
        for neighbor_id in world.social_neighbors[person_id]:
            edge = edge_between(world, person_id, neighbor_id)
            neighbors.append({
                "person_id": neighbor_id,
                "layers": list(edge.layers),
                "trust": edge.trust,
                "language_compatibility": edge.language_compatibility,
                "effective_edge_weight": edge.weight,
                "represented_relationships": edge.represented_relationships,
                "influence_numerator": edge.weight * edge.trust * edge.represented_relationships,
            })
        agents[person_id] = {
            "household_id": person.household_id,
            "community_id": person.community_id,
            "home_locality_id": person.home_locality_id,
            "residence_locality_id": person.residence_locality_id,
            "representative_weight": person.weight,
            "languages": dict(person.languages),
            "public_behavior": person.public_behavior,
            "social_exposure": dict(person.social_exposure),
            "neighbors": neighbors,
        }
    return {
        "time": world.time,
        "edge_semantics": "sampled aggregate channel of social influence, not one literal relationship",
        "agents": agents,
        "communities": {community_id: asdict(world.social_communities[community_id])
                        for community_id in selected_communities},
    }


def write_network_snapshot(world: WorldState, path, agent_ids: list[str] | None = None,
                           community_ids: list[str] | None = None) -> None:
    from pathlib import Path

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(network_snapshot(world, agent_ids, community_ids), indent=2), encoding="utf-8"
    )
