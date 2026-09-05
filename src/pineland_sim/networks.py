from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
import json
from math import log
import random
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
              base_strength: float, trust: float,
              represented_capacity: float | None = None) -> None:
    if person_a_id == person_b_id:
        return
    key = _edge_key(person_a_id, person_b_id)
    first = world.persons[key[0]]
    second = world.persons[key[1]]
    compatibility = language_compatibility(first.languages, second.languages)
    language_factor = (.35 + .65 * compatibility
                       if world.config.social_network.language_topology_enabled else 1.0)
    weight = clamp(base_strength * language_factor)
    represented_relationships = (
        max(0.0, represented_capacity)
        if represented_capacity is not None else
        2 * first.weight * second.weight / max(1e-12, first.weight + second.weight)
    )
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


def community_bridge_capacity(world: WorldState, community: SocialCommunity) -> float:
    """Represented population mass carrying cross-community brokerage capability.

    bridge_member_ids are sampled anchors for graph topology, not literal
    counts of bridge persons. Capacity is therefore a fractional share of the
    represented community population and is invariant to representative-agent
    resolution.
    """
    represented_population = sum(
        world.persons[person_id].weight for person_id in community.member_ids
        if person_id in world.persons
    )
    return represented_population * clamp(world.config.social_network.bridge_fraction)


def community_represented_population(world: WorldState, community: SocialCommunity) -> float:
    """Represented population carried by a social community."""
    return sum(
        world.persons[person_id].weight for person_id in community.member_ids
        if person_id in world.persons
    )


def bridge_target_community_weights(
    world: WorldState,
    community: SocialCommunity,
    communities_by_locality: dict[str, list[str]] | None = None,
) -> dict[str, float]:
    """Resolution-invariant opportunity mass for cross-community bridge targets.

    The previous implementation selected only same-locality communities whenever
    more than one happened to be sampled, falling back to adjacent localities
    only when no local alternative existed.  As representative resolution grew,
    nearly every locality acquired multiple sampled communities and geographic
    bridge probability collapsed toward zero.  Target opportunity is now based
    on represented population rather than the raw number of sampled communities.

    Same-locality opportunity has unit geographic attenuation.  Adjacent
    opportunity is attenuated by ``1 / (1 + adjacency_cost)`` using the existing
    exogenous locality graph.  Splitting a represented population into more
    sampled communities therefore preserves approximately the same target mass.
    """
    if communities_by_locality is None:
        communities_by_locality = defaultdict(list)
        for candidate in world.social_communities.values():
            communities_by_locality[candidate.locality_id].append(candidate.community_id)

    targets: dict[str, float] = {}
    source_locality = community.locality_id
    locality_ids = [source_locality, *sorted(world.adjacency.get(source_locality, {}))]
    for locality_id in locality_ids:
        attenuation = (
            1.0 if locality_id == source_locality else
            1.0 / (1.0 + max(0.0, world.adjacency[source_locality][locality_id]))
        )
        for candidate_id in communities_by_locality.get(locality_id, ()):
            if candidate_id == community.community_id:
                continue
            candidate = world.social_communities[candidate_id]
            mass = community_represented_population(world, candidate) * attenuation
            if mass > 0:
                targets[candidate_id] = mass
    return targets


def _balanced_household_groups(world: WorldState, household_ids: list[str], minimum: float,
                               target: float, maximum: float, rng) -> list[list[str]]:
    """Pack indivisible household archetypes by represented population mass."""
    rng.shuffle(household_ids)
    groups: list[list[str]] = []
    current: list[str] = []
    current_size = 0.0

    def household_population(household_id: str) -> float:
        return sum(world.persons[person_id].weight
                   for person_id in world.households[household_id].member_ids)

    for household_id in household_ids:
        household_size = household_population(household_id)
        if current and current_size + household_size > maximum:
            groups.append(current)
            current = []
            current_size = 0.0
        current.append(household_id)
        current_size += household_size
        if current_size >= target:
            groups.append(current)
            current = []
            current_size = 0.0
    if current:
        current_count = sum(household_population(h) for h in current)
        previous_count = sum(household_population(h) for h in groups[-1]) if groups else 0.0
        if groups and current_count < target / 2 and previous_count + current_count <= maximum:
            groups[-1].extend(current)
        else:
            if groups and current_count < minimum:
                while groups[-1] and current_count < minimum:
                    candidate = groups[-1][-1]
                    candidate_size = household_population(candidate)
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
    total_weight = sum(world.persons[person_id].weight for person_id in member_ids)
    return {
        language: sum(world.persons[person_id].weight *
                      world.persons[person_id].languages[language]
                      for person_id in member_ids) / max(1e-9, total_weight)
        for language in LANGUAGES
    }


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
            config.minimum_community_size * config.community_size_unit_population,
            config.target_community_size * config.community_size_unit_population,
            config.maximum_community_size * config.community_size_unit_population, rng,
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

    # Multilingual representatives anchor cross-community information bridges.
    # The role itself is represented social capacity, not a count of literal
    # sampled people. Allocate exactly the configured represented bridge mass
    # across existing representative cohorts, allowing the final anchor to
    # carry only a fractional role capacity.
    for community in world.social_communities.values():
        member_ranking = sorted(
            community.member_ids,
            key=lambda person_id: sorted(world.persons[person_id].languages.values(), reverse=True)[1],
            reverse=True,
        )
        remaining_bridge_capacity = community_bridge_capacity(world, community)
        target_weights = bridge_target_community_weights(
            world, community, communities_by_locality
        )
        if not target_weights or remaining_bridge_capacity <= 0:
            continue
        candidates = sorted(target_weights)
        candidate_weights = [target_weights[candidate_id] for candidate_id in candidates]
        for source_id in member_ranking:
            if remaining_bridge_capacity <= 1e-12:
                break
            source_capacity = min(
                world.persons[source_id].weight, remaining_bridge_capacity
            )
            target_community = world.social_communities[
                rng.choices(candidates, weights=candidate_weights, k=1)[0]
            ]
            target_id = max(target_community.member_ids, key=lambda candidate: language_compatibility(
                world.persons[source_id].languages, world.persons[candidate].languages))
            _add_edge(
                world, source_id, target_id, "bridge", config.bridge_tie_strength, .5,
                represented_capacity=source_capacity,
            )
            community.bridge_member_ids.append(source_id)
            remaining_bridge_capacity -= source_capacity

    for neighbors in world.social_neighbors.values():
        neighbors.sort()


def degree_preserving_rewire(world: WorldState, seed: int,
                             swaps: int | None = None,
                             preserve_attributes: bool = True) -> dict[str, int | float]:
    """Randomize endpoints with double-edge swaps while preserving degrees.

    The operation mutates only the social graph.  Person attributes, community
    membership, all process RNG streams, and edge-count/degree sequences remain
    unchanged.  When ``preserve_attributes`` is true, the multiset of tie
    strengths/trust/layers is retained and reassigned to the new endpoints;
    otherwise a generic random-mixing edge attribute is used.
    """
    rng = random.Random(seed)
    original = list(world.social_edges.values())
    if len(original) < 2:
        return {"attempts": 0, "accepted_swaps": 0, "edges": len(original)}
    target = swaps if swaps is not None else max(1_000, 10 * len(original))
    endpoints = [
        [edge.person_a_id, edge.person_b_id, edge]
        for edge in original
    ]
    edge_keys = {_edge_key(row[0], row[1]) for row in endpoints}
    accepted = attempts = 0
    max_attempts = max(target * 4, 100)
    while attempts < max_attempts and accepted < target:
        attempts += 1
        first_index, second_index = rng.sample(range(len(endpoints)), 2)
        first = endpoints[first_index]
        second = endpoints[second_index]
        a, b, c, d = first[0], first[1], second[0], second[1]
        if rng.random() < .5:
            candidates = ((a, d), (c, b))
        else:
            candidates = ((a, c), (b, d))
        if any(x == y for x, y in candidates):
            continue
        keys = [_edge_key(*pair) for pair in candidates]
        if keys[0] == keys[1] or any(key in edge_keys and key not in {
                _edge_key(a, b), _edge_key(c, d)} for key in keys):
            continue
        edge_keys.remove(_edge_key(a, b)); edge_keys.remove(_edge_key(c, d))
        edge_keys.update(keys)
        first[0], first[1] = keys[0]
        second[0], second[1] = keys[1]
        accepted += 1

    world.social_edges.clear()
    world.social_neighbors = {person_id: [] for person_id in world.persons}
    for index, (a, b, old_edge) in enumerate(endpoints):
        key = _edge_key(a, b)
        if preserve_attributes:
            edge = SocialEdge(key[0], key[1], old_edge.layers, old_edge.weight,
                              old_edge.language_compatibility, old_edge.trust,
                              2 * world.persons[key[0]].weight * world.persons[key[1]].weight /
                              max(1e-12, world.persons[key[0]].weight + world.persons[key[1]].weight))
        else:
            compatibility = language_compatibility(world.persons[key[0]].languages,
                                                    world.persons[key[1]].languages)
            edge = SocialEdge(key[0], key[1], ("random_mix",),
                              clamp(.5 * (.35 + .65 * compatibility)),
                              compatibility, .5,
                              2 * world.persons[key[0]].weight * world.persons[key[1]].weight /
                              max(1e-12, world.persons[key[0]].weight + world.persons[key[1]].weight))
        world.social_edges[key] = edge
        world.social_neighbors[key[0]].append(key[1])
        world.social_neighbors[key[1]].append(key[0])
    for neighbors in world.social_neighbors.values():
        neighbors.sort()
    return {"attempts": attempts, "accepted_swaps": accepted,
            "edges": len(world.social_edges),
            "degree_sequence_hash": sum(len(neighbors) ** 2 for neighbors in world.social_neighbors.values())}


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
                "represented_mean_degree": 0.0,
                "represented_mean_language_compatibility": 0.0,
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
    represented_population = sum(person.weight for person in world.persons.values())
    represented_degree = sum(
        world.persons[person_id].weight * len(world.social_neighbors[person_id])
        for person_id in world.persons
    ) / max(1e-12, represented_population)
    relationship_mass = sum(edge.represented_relationships for edge in world.social_edges.values())
    represented_language = (
        sum(edge.language_compatibility * edge.represented_relationships
            for edge in world.social_edges.values()) / max(1e-12, relationship_mass)
    )
    bridge_edges = [edge for edge in world.social_edges.values() if "bridge" in edge.layers]
    cross_local_bridge_edges = [
        edge for edge in bridge_edges
        if world.persons[edge.person_a_id].residence_locality_id !=
        world.persons[edge.person_b_id].residence_locality_id
    ]
    bridge_relationship_mass = sum(edge.represented_relationships for edge in bridge_edges)
    cross_local_bridge_relationship_mass = sum(
        edge.represented_relationships for edge in cross_local_bridge_edges
    )
    return {
        "nodes": len(world.persons),
        "edges": len(world.social_edges),
        "communities": len(world.social_communities),
        "components": components,
        "mean_degree": mean(degrees),
        "median_degree": median(degrees),
        "mean_language_compatibility": mean(edge.language_compatibility for edge in world.social_edges.values()),
        "represented_mean_degree": represented_degree,
        "represented_mean_language_compatibility": represented_language,
        "bridge_edges": len(bridge_edges),
        "cross_local_bridge_edges": len(cross_local_bridge_edges),
        "cross_local_bridge_edge_share": (
            len(cross_local_bridge_edges) / len(bridge_edges) if bridge_edges else 0.0
        ),
        "represented_bridge_relationship_mass": bridge_relationship_mass,
        "represented_cross_local_bridge_relationship_mass": cross_local_bridge_relationship_mass,
        "represented_cross_local_bridge_share": (
            cross_local_bridge_relationship_mass / bridge_relationship_mass
            if bridge_relationship_mass > 0 else 0.0
        ),
        "sampled_clustering": mean(coefficients) if coefficients else 0.0,
        # A transparent small-world path-length proxy keeps the resolution
        # battery tractable at 250k nodes.  Exact sampled BFS path lengths can
        # be requested from network snapshots for a focused graph study.
        "path_length_proxy": log(max(2, len(world.persons))) /
        log(max(2.0, mean(degrees))) if mean(degrees) > 1 else float(len(world.persons)),
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
