from __future__ import annotations

from math import ceil, cos, exp, hypot, pi, sin
import heapq

from .config import SimulationConfig
from .entities import (
    ActorBelief,
    ArmedFormation,
    ControlVector,
    District,
    Household,
    LANGUAGES,
    Locality,
    Organization,
    OrganizationKind,
    Person,
)
from .world import WorldState, seeded_initialization_rng
from typing import Any
from .networks import generate_social_network
from .physical import generate_physical_world
from .logistics import generate_logistics_world
from .information import initialize_information_world
from .organization_ecology import initialize_organization_ecology
from .political_order import initialize_political_order
from .foreign_affairs import initialize_foreign_system
from .relations import initialize_organization_relations


DISTRICT_REGISTRY = (
    ("D01", "Stonebridge Federal", 1_450_000, "metropolitan basin", .82, "FS", "capital and federal hub", .95),
    ("D02", "Northpass", 310_000, "high mountains", .34, "AR", "mining and border trade", .35),
    ("D03", "Highpine", 370_000, "forested mountains", .29, "AR", "forestry and agriculture", .25),
    ("D04", "Ironwood", 460_000, "western upland", .42, "AR/FS", "timber and light industry", .55),
    ("D05", "Westreach", 390_000, "border upland", .31, "AR/VE", "agriculture and border markets", .35),
    ("D06", "Redvale", 540_000, "agricultural valley", .48, "VE/FS", "commercial agriculture", .65),
    ("D07", "Mossfield", 420_000, "wet low valley", .36, "VE", "agriculture and hydropower", .5),
    ("D08", "Cedar", 470_000, "central plain", .45, "FS/VE", "grain and logistics", .75),
    ("D09", "Bracken", 580_000, "mixed central-west", .57, "FS", "manufacturing and universities", .8),
    ("D10", "Greenridge", 440_000, "central plateau", .39, "FS/TA", "livestock and public sector", .55),
    ("D11", "Kestrel", 720_000, "eastern plateau", .64, "TA/FS", "industry and transit", .85),
    ("D12", "Eastmere", 490_000, "dry eastern upland", .41, "TA", "pastoral and border commerce", .5),
    ("D13", "Flint", 330_000, "rocky highland", .28, "TA", "mining and dispersed settlements", .25),
    ("D14", "Juniper", 510_000, "southern valley", .52, "VE/TA/FS", "agriculture and university", .8),
    ("D15", "Lakemarch", 630_000, "southern basin", .61, "VE/FS", "hydropower and industry", .85),
    ("D16", "Dovetail", 340_000, "border hills", .30, "AR/TA", "border markets and farms", .3),
    ("D17", "Alder", 350_000, "north-central plateau", .38, "FS/AR", "agriculture and transport", .7),
)

# A transparent synthetic map.  Coordinates are not a historical claim; they
# provide a stable spatial reference so locality connectivity follows distance
# and terrain rather than identifier order.
DISTRICT_COORDINATES = {
    "D01": (0.0, 0.0), "D02": (-72.0, 64.0), "D03": (-45.0, 86.0),
    "D04": (-54.0, 32.0), "D05": (-82.0, 4.0), "D06": (-38.0, -12.0),
    "D07": (-8.0, -34.0), "D08": (12.0, -8.0), "D09": (-8.0, 28.0),
    "D10": (22.0, 36.0), "D11": (58.0, 34.0), "D12": (78.0, 12.0),
    "D13": (92.0, -18.0), "D14": (50.0, -28.0), "D15": (14.0, -58.0),
    "D16": (-52.0, -66.0), "D17": (18.0, 68.0),
}


def _language_vector(pattern: str, rng) -> dict[str, float]:
    primary = pattern.split("/")[0]
    values = {language: rng.uniform(0.02, 0.3) for language in LANGUAGES}
    values[primary] = rng.uniform(0.7, 1.0)
    if "/" in pattern:
        for language in pattern.split("/")[1:]:
            if language in values:
                values[language] = rng.uniform(0.45, 0.9)
    values["FS"] = max(values["FS"], rng.uniform(0.2, 0.75))
    return values


def _balanced_bounded(values: list[float], target_mean: float,
                      lower: float = 0.0, upper: float = 1.0) -> list[float]:
    """Shift bounded prior draws so their represented mean is exact."""
    if not values:
        return []
    target = max(lower, min(upper, float(target_mean)))
    lo = lower - max(values)
    hi = upper - min(values)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        shifted = [max(lower, min(upper, value + mid)) for value in values]
        if sum(shifted) / len(shifted) < target:
            lo = mid
        else:
            hi = mid
    delta = (lo + hi) / 2.0
    return [max(lower, min(upper, value + delta)) for value in values]


def _empirical_language_prior_means(pattern: str) -> dict[str, float]:
    parts = [part for part in pattern.split("/") if part in LANGUAGES]
    primary = parts[0] if parts else "FS"
    means = {language: .16 for language in LANGUAGES}
    means[primary] = .85
    for language in parts[1:]:
        means[language] = .675
    if primary != "FS":
        means["FS"] = max(means["FS"], .475)
    return means


def _empirical_population_profiles(config: SimulationConfig, locality_id: str,
                                   language_pattern: str, count: int) -> list[dict[str, Any]]:
    """Build case-stable balanced prior quadrature for one empirical locality.

    No historical outcome is consulted. The means are analytical means of the
    pre-existing generic priors, with documented language midpoint semantics.
    Stochastic forecast seeds therefore cannot invent different locality-level
    political psychologies.
    """
    rng = seeded_initialization_rng(config, f"empirical-population:{locality_id}")
    grievance = _balanced_bounded([rng.betavariate(2, 9) for _ in range(count)], 2 / 11)
    fear = _balanced_bounded([rng.betavariate(2, 8) for _ in range(count)], .2)
    efficacy = _balanced_bounded([rng.betavariate(4, 4) for _ in range(count)], .5)
    identities = {
        name: _balanced_bounded([rng.random() for _ in range(count)], .5)
        for name in ("local", "district", "federal")
    }
    preferences = {
        f"party-{index}": _balanced_bounded([rng.random() for _ in range(count)], .5)
        for index in range(1, 4)
    }
    trust = {
        "government": _balanced_bounded(
            [rng.uniform(.3, .8) for _ in range(count)], .55, .3, .8
        ),
        "insurgent": _balanced_bounded(
            [rng.uniform(.05, .35) for _ in range(count)], .20, .05, .35
        ),
    }
    raw_languages = [_language_vector(language_pattern, rng) for _ in range(count)]
    language_means = _empirical_language_prior_means(language_pattern)
    languages = {
        language: _balanced_bounded(
            [row[language] for row in raw_languages], language_means[language]
        )
        for language in LANGUAGES
    }
    raw_resources = [rng.lognormvariate(0, .55) for _ in range(count)]
    target_resource_mean = exp(.5 * .55 ** 2)
    resource_scale = target_resource_mean / max(1e-12, sum(raw_resources) / count)
    resources = [value * resource_scale for value in raw_resources]
    raw_ages = [max(1, min(90, round(rng.normalvariate(34, 18)))) for _ in range(count)]
    if count == 1:
        raw_ages[0] = 34
    return [
        {
            "age": raw_ages[index],
            "languages": {language: languages[language][index] for language in LANGUAGES},
            "identities": {name: identities[name][index] for name in identities},
            "preferences": {name: preferences[name][index] for name in preferences},
            "grievance": grievance[index],
            "fear": fear[index],
            "efficacy": efficacy[index],
            "trust": {name: trust[name][index] for name in trust},
            "resource_per_capita": resources[index],
        }
        for index in range(count)
    ]


def generate_pineland(config: SimulationConfig | None = None,
                      empirical_geography: dict[str, Any] | None = None) -> WorldState:
    config = config or SimulationConfig()
    config.validate()
    rng = seeded_initialization_rng(config, "world-generation")
    geography_rng = seeded_initialization_rng(config, "geography-generation")
    force_rng = seeded_initialization_rng(config, "force-generation")
    world = WorldState(config=config)

    for row in DISTRICT_REGISTRY:
        district = District(*row)
        world.districts[district.district_id] = district

    remaining = config.locality_count - len(DISTRICT_REGISTRY)
    total_population = sum(row[2] for row in DISTRICT_REGISTRY)
    extra_by_district = {row[0]: 0 for row in DISTRICT_REGISTRY}
    for _ in range(remaining):
        draw = rng.random() * total_population
        cumulative = 0
        for row in DISTRICT_REGISTRY:
            cumulative += row[2]
            if draw <= cumulative:
                extra_by_district[row[0]] += 1
                break

    for row in DISTRICT_REGISTRY:
        district_id, name, population, terrain, urban, _, _, connectivity = row
        count = 1 + extra_by_district[district_id]
        weights = [max(.1, rng.lognormvariate(0, .8)) for _ in range(count)]
        weights[0] *= 2.5 if urban > .55 else 1.4
        denominator = sum(weights)
        for index, weight in enumerate(weights):
            locality_id = f"{district_id}-L{index + 1:02d}"
            share = weight / denominator
            kind = "city" if index == 0 and urban >= .55 else ("town" if index == 0 or share > .18 else "village-cluster")
            capacity = max(.08, min(.95, .25 + .55 * connectivity + rng.uniform(-.12, .12)))
            terrain_friction = max(.6, min(2.4, 2.0 - connectivity + rng.uniform(-.2, .2)))
            locality = Locality(
                locality_id=locality_id,
                district_id=district_id,
                name=name if index == 0 else f"{name} {kind.title()} {index}",
                kind=kind,
                population=round(population * share),
                economic_output=population * share * rng.uniform(.7, 1.3),
                infrastructure=max(.08, min(.98, connectivity + rng.uniform(-.15, .15))),
                administrative_capacity=capacity,
                terrain_friction=terrain_friction,
                observability=max(.1, min(.95, .35 + urban * .5 + rng.uniform(-.1, .1))),
                control={
                    "government": ControlVector(.98, .72, capacity, capacity * .85, capacity * .65, .52, .7),
                },
                governance={"security": .55, "justice": capacity * .75, "administration": capacity,
                             "services": capacity * .8, "representation": .5, "leakage": rng.uniform(.05, .28)},
            )
            center_x, center_y = DISTRICT_COORDINATES[district_id]
            if index == 0:
                locality.x_km, locality.y_km = center_x, center_y
            else:
                angle = 2 * pi * (index - 1) / max(1, count - 1)
                radius = geography_rng.uniform(10.0, max(10.0, config.geography.coordinate_jitter_km))
                locality.x_km = center_x + radius * cos(angle)
                locality.y_km = center_y + radius * sin(angle)
            if config.include_insurgency:
                locality.control["insurgent"] = ControlVector(0, .01, 0, .01, .01, .04, .08)
            world.localities[locality_id] = locality
            world.districts[district_id].locality_ids.append(locality_id)
            world.adjacency[locality_id] = {}

    locality_ids = sorted(world.localities)

    def connect(first_id: str, second_id: str) -> None:
        if first_id == second_id:
            return
        first, second = world.localities[first_id], world.localities[second_id]
        distance = max(.5, hypot(first.x_km - second.x_km, first.y_km - second.y_km))
        terrain = (first.terrain_friction + second.terrain_friction) / 2
        # Retain the historical terrain-cost interface while deriving the
        # distance term from explicit coordinates.
        cost = terrain * (.65 + distance / 55.0)
        world.adjacency[first_id][second_id] = min(world.adjacency[first_id].get(second_id, 1e9), cost)
        world.adjacency[second_id][first_id] = world.adjacency[first_id][second_id]

    if config.geography.national_backbone == "spatial_mst":
        # Spatial minimum-spanning backbone: each locality attaches to the
        # nearest already-connected locality, guaranteeing connectivity without
        # an identifier-order corridor.
        connected = [min(
            locality_ids,
            key=lambda lid: (
                world.localities[lid].x_km ** 2
                + world.localities[lid].y_km ** 2,
                lid,
            ),
        )]
        remaining_ids = [lid for lid in locality_ids if lid not in connected]
        root = connected[0]
        best_edge_by_right: dict[str, tuple[float, str, str]] = {}
        root_locality = world.localities[root]
        for right in remaining_ids:
            right_locality = world.localities[right]
            best_edge_by_right[right] = (
                hypot(
                    root_locality.x_km - right_locality.x_km,
                    root_locality.y_km - right_locality.y_km,
                ),
                root,
                right,
            )
        while remaining_ids:
            # Prim's algorithm with the exact historical tie-breaking, but
            # maintain each unconnected locality's best edge incrementally
            # instead of rescanning every connected/unconnected pair.
            candidate = min(
                best_edge_by_right.values(),
                key=lambda item: (item[0], item[1], item[2]),
            )
            _, left, right = candidate
            connect(left, right)
            connected.append(right)
            remaining_ids.remove(right)
            best_edge_by_right.pop(right, None)
            left_locality = world.localities[right]
            for other in remaining_ids:
                other_locality = world.localities[other]
                new_candidate = (
                    hypot(
                        left_locality.x_km - other_locality.x_km,
                        left_locality.y_km - other_locality.y_km,
                    ),
                    right,
                    other,
                )
                if new_candidate < best_edge_by_right[other]:
                    best_edge_by_right[other] = new_candidate

    # Add local nearest-neighbour roads and optional district hub roads.
    k = config.geography.nearest_neighbors
    for locality_id in locality_ids:
        nearest = sorted(
            (other for other in locality_ids if other != locality_id),
            key=lambda other: (hypot(world.localities[locality_id].x_km - world.localities[other].x_km,
                                     world.localities[locality_id].y_km - world.localities[other].y_km), other),
        )[:k]
        for other in nearest:
            connect(locality_id, other)
    if config.geography.national_backbone == "knn":
        # Pure local kNN graphs can fragment across geographically separated
        # districts.  Bridge only disconnected components, choosing the
        # shortest cross-component pair each time.  This preserves kNN as the
        # topology-generating rule while guaranteeing a usable national graph.
        def components() -> list[set[str]]:
            unseen = set(locality_ids)
            result: list[set[str]] = []
            while unseen:
                root = min(unseen)
                stack = [root]
                component = set()
                while stack:
                    current = stack.pop()
                    if current in component:
                        continue
                    component.add(current)
                    unseen.discard(current)
                    stack.extend(
                        neighbor
                        for neighbor in world.adjacency[current]
                        if neighbor not in component
                    )
                result.append(component)
            return result

        groups = components()
        while len(groups) > 1:
            first = groups[0]
            candidate = min(
                (
                    (
                        hypot(
                            world.localities[left].x_km - world.localities[right].x_km,
                            world.localities[left].y_km - world.localities[right].y_km,
                        ),
                        left,
                        right,
                    )
                    for left in first
                    for group in groups[1:]
                    for right in group
                ),
                key=lambda item: (item[0], item[1], item[2]),
            )
            _, left, right = candidate
            connect(left, right)
            groups = components()
    if config.geography.district_hub_links:
        for district in world.districts.values():
            hub = district.locality_ids[0]
            for locality_id in district.locality_ids[1:]:
                connect(hub, locality_id)

    if empirical_geography is not None:
        total_population = _replace_with_empirical_geography(world, empirical_geography)
        locality_ids = sorted(world.localities)

    government = Organization("government", "Federal Republic", OrganizationKind.GOVERNMENT, 2_500_000, .72, .7, .55, .55, .8, .7, .7)
    military = Organization("fdf", "Federal Defense Force", OrganizationKind.MILITARY, 600_000, .75, .78, .58, .42, .72, .75, .76)
    police = Organization("police", "Federal and District Police", OrganizationKind.POLICE, 350_000, .62, .62, .55, .7, .78, .45, .58)
    world.organizations = {item.organization_id: item for item in (government, military, police)}
    for party_index in range(3):
        party = Organization(f"party-{party_index + 1}", f"National Party {party_index + 1}", OrganizationKind.PARTY,
                             100_000, rng.uniform(.5, .8), .5, .55, .6, .75, .5, .6)
        world.organizations[party.organization_id] = party
    if config.include_insurgency:
        insurgent = Organization("insurgent", "Pineland Renewal Front", OrganizationKind.INSURGENT, 80_000, .68, .65, .25, .72, .8, .65, .52, external_support=10_000)
        world.organizations[insurgent.organization_id] = insurgent

    # Weighted synthetic population with explicit households.  Empirical
    # geography is stratified so every represented locality has civilians and
    # each locality population is conserved exactly rather than only in
    # multinomial expectation.
    person_index = 0
    household_index = 0
    empirical_profiles: dict[str, list[dict[str, Any]]] = {}
    empirical_profile_cursor: dict[str, int] = {}

    def add_household(locality_id: str, size: int, person_weight: float) -> None:
        nonlocal person_index, household_index
        district = world.districts[world.localities[locality_id].district_id]
        household_id = f"H{household_index:07d}"
        member_ids: list[str] = []
        for _ in range(size):
            person_id = f"P{person_index:08d}"
            member_ids.append(person_id)
            profile = None
            if locality_id in empirical_profiles:
                cursor = empirical_profile_cursor.get(locality_id, 0)
                profile = empirical_profiles[locality_id][cursor]
                empirical_profile_cursor[locality_id] = cursor + 1
            languages = (
                dict(profile["languages"]) if profile is not None
                else _language_vector(district.language_pattern, rng)
            )
            preferences = (
                dict(profile["preferences"]) if profile is not None
                else {f"party-{j}": rng.random() for j in range(1, 4)}
            )
            person = Person(
                person_id, household_id, locality_id, locality_id, person_weight,
                (profile["age"] if profile is not None
                 else max(1, min(90, round(rng.normalvariate(34, 18))))),
                languages,
                (dict(profile["identities"]) if profile is not None else
                 {"local": rng.random(), "district": rng.random(), "federal": rng.random()}),
                preferences,
                grievance=(profile["grievance"] if profile is not None
                           else max(0, min(1, rng.betavariate(2, 9)))),
                fear=(profile["fear"] if profile is not None else rng.betavariate(2, 8)),
                efficacy=(profile["efficacy"] if profile is not None else rng.betavariate(4, 4)),
                expected_control={"government": .7, "insurgent": .1},
                trust=(dict(profile["trust"]) if profile is not None else
                       {"government": rng.uniform(.3, .8), "insurgent": rng.uniform(.05, .35)}),
                # Draw a per-capita endowment, then materialize the liquid
                # stock owned by the represented cohort. The old token-level
                # draw made national civilian resources proportional to
                # agent_count rather than represented population.
                resources=person_weight * (
                    profile["resource_per_capita"] if profile is not None
                    else rng.lognormvariate(0, .55)
                ),
            )
            world.persons[person_id] = person
            person_index += 1
        world.households[household_id] = Household(
            household_id, member_ids, locality_id, locality_id,
            sum(world.persons[p].resources for p in member_ids),
            sum(world.persons[p].age < 16 for p in member_ids),
        )
        household_index += 1

    if empirical_geography is not None:
        if config.agent_count < len(locality_ids):
            raise ValueError(
                "empirical geography requires agent_count >= locality_count so every locality "
                "has at least one representative civilian"
            )
        remaining_agents = config.agent_count - len(locality_ids)
        raw_extra = {
            locality_id: remaining_agents * world.localities[locality_id].population / total_population
            for locality_id in locality_ids
        }
        extra = {locality_id: int(raw_extra[locality_id]) for locality_id in locality_ids}
        leftover = remaining_agents - sum(extra.values())
        for locality_id in sorted(
                locality_ids, key=lambda key: (-(raw_extra[key] - extra[key]), key))[:leftover]:
            extra[locality_id] += 1
        for locality_id in locality_ids:
            count = 1 + extra[locality_id]
            empirical_profiles[locality_id] = _empirical_population_profiles(
                config,
                locality_id,
                world.districts[world.localities[locality_id].district_id].language_pattern,
                count,
            )
            empirical_profile_cursor[locality_id] = 0
            person_weight = world.localities[locality_id].population / count
            remaining = count
            while remaining:
                size = min(remaining, max(1, round(rng.lognormvariate(1.15, .35))))
                add_household(locality_id, size, person_weight)
                remaining -= size
    else:
        represented_weight = total_population / config.agent_count
        locality_weights = [world.localities[x].population for x in locality_ids]
        while person_index < config.agent_count:
            size = min(config.agent_count - person_index, max(1, round(rng.lognormvariate(1.15, .35))))
            locality_id = rng.choices(locality_ids, weights=locality_weights, k=1)[0]
            add_household(locality_id, size, represented_weight)

    if empirical_geography is not None and empirical_geography.get("schema_version") in {"2.0.0", "3.0.0"}:
        hubs = sorted(
            (key for key in locality_ids
             if world.localities[key].administrative_role == "district_headquarters"),
            key=lambda key: (world.districts[world.localities[key].district_id].population, key),
            reverse=True,
        )
    else:
        hubs = sorted(locality_ids, key=lambda key: world.localities[key].population, reverse=True)
    government_strength = total_population * .0025
    if config.force_structure.mode == "legacy":
        government_count = min(17, len(hubs))
    else:
        government_count = min(len(hubs), config.force_structure.maximum_initial_formations_per_side,
                               max(1, ceil(government_strength /
                                           config.force_structure.government_target_personnel)))
    per_formation = max(100, government_strength / government_count)
    for index, locality_id in enumerate(hubs[:government_count]):
        formation = ArmedFormation(f"FDF-{index + 1:02d}", "fdf", locality_id, per_formation, .72, .75, .82, .9, .55, .75, .72, .35)
        world.formations[formation.formation_id] = formation
    if config.include_insurgency:
        configured_targets = (empirical_geography or {}).get("initial_insurgent_locality_ids", [])
        strength = total_population * config.initial_insurgent_share
        if config.force_structure.mode == "legacy":
            insurgent_count = 1
        else:
            insurgent_count = min(config.force_structure.maximum_initial_formations_per_side,
                                  max(1, ceil(strength /
                                              config.force_structure.insurgent_target_personnel)))
        # The empirical origin is retained, while additional physical tokens
        # disperse outward from that origin using only the exogenous geography
        # graph.  This prevents equal-capacity case inputs from silently
        # degenerating into identifier/CSV order.  Without a supplied origin,
        # low-capacity placement remains available but ties are seeded-random.
        origins = list(configured_targets)
        if configured_targets:
            distances = {key: float("inf") for key in locality_ids}
            queue: list[tuple[float, str]] = []
            for key in configured_targets:
                if key not in world.localities:
                    raise ValueError(f"unknown initial insurgent locality: {key}")
                distances[key] = 0.0
                heapq.heappush(queue, (0.0, key))
            while queue:
                distance, current = heapq.heappop(queue)
                if distance != distances[current]:
                    continue
                for neighbor, edge_cost in world.adjacency.get(current, {}).items():
                    candidate = distance + float(edge_cost)
                    if candidate < distances[neighbor]:
                        distances[neighbor] = candidate
                        heapq.heappush(queue, (candidate, neighbor))
            origins.extend(key for key in sorted(
                locality_ids, key=lambda key: (distances[key], key)
            ) if key not in origins)
        else:
            # Force placement must not depend on how many civilian
            # representatives happened to consume the population-generation
            # stream.  Keep its tie-breaks on a resolution-independent stream.
            tie_break = {key: force_rng.random() for key in locality_ids}
            origins.extend(sorted(
                locality_ids,
                key=lambda key: (world.localities[key].administrative_capacity, tie_break[key]),
            ))
        for index in range(insurgent_count):
            target = origins[index % len(origins)]
            formation_id = f"PRF-{index + 1:02d}"
            world.formations[formation_id] = ArmedFormation(
                formation_id, "insurgent", target, strength / insurgent_count,
                .45, .7, .75, .65, .5, .7, .55, .75)

    generate_logistics_world(world)
    generate_physical_world(world)
    generate_social_network(world)
    initialize_organization_ecology(world)
    initialize_political_order(world)
    initialize_foreign_system(world)
    initialize_organization_relations(world)

    initialize_information_world(world)
    world.beliefs.clear()
    for organization_id in world.organizations:
        for locality_id, locality in world.localities.items():
            # Actor-facing priors are deliberately uninformative.  They are
            # moved only by observations; hidden control is retained for
            # analyst diagnostics and environmental processes.
            estimate = ControlVector(*([.5] * 7))
            target_actor = ("insurgent" if organization_id in world.organizations and
                            world.organizations[organization_id].kind is OrganizationKind.INSURGENT
                            else "government")
            world.beliefs[(organization_id, locality_id)] = ActorBelief(
                organization_id, locality_id, estimate,
                config.information.prior_confidence, 0,
            )
            world.control_beliefs[(organization_id, target_actor, locality_id)] = ActorBelief(
                organization_id, locality_id, ControlVector(**estimate.to_dict()),
                config.information.prior_confidence, 0,
            )
            # Opposing-side estimates begin as broad priors rather than a hidden
            # copy of truth. They are populated only by source observations.
            opposing_actor = "government" if target_actor == "insurgent" else "insurgent"
            if opposing_actor in world.organizations:
                world.control_beliefs[(organization_id, opposing_actor, locality_id)] = ActorBelief(
                    organization_id, locality_id, ControlVector(*([.5] * 7)),
                    config.information.prior_confidence, 0,
                )

    # All generation layers have now assigned communities, organizations,
    # formations, patrols, and locality membership. Build derived execution
    # indexes once from the complete initialized world.
    world.rebuild_runtime_entity_indexes()
    world.initial_population = world.weighted_population()
    world.initialize_stock_ledger()
    world.assert_invariants()
    return world


def _replace_with_empirical_geography(world: WorldState,
                                      specification: dict[str, Any]) -> int:
    """Replace synthetic geography with a provenance-built case environment.

    The adapter changes case inputs only: locality identity, population,
    coordinates, adjacency, and explicitly supplied physical covariates. It
    does not change any model equation or introduce case-specific bonuses.
    """
    schema = specification.get("schema_version")
    if schema not in {"1.0.0", "2.0.0", "3.0.0"}:
        raise ValueError("unsupported empirical geography schema")
    localities = specification.get("localities", [])
    containers = (specification.get("districts", []) if schema in {"2.0.0", "3.0.0"}
                  else specification.get("containers", []))
    if not localities or not containers:
        raise ValueError("empirical geography needs district containers and localities")
    if world.config.locality_count != len(localities):
        raise ValueError("config.locality_count must match empirical localities")

    world.districts.clear(); world.localities.clear(); world.adjacency.clear()
    world.geographic_containers.clear()
    world.district_hierarchy.clear()
    if schema == "2.0.0":
        for row in specification.get("regions", []):
            world.geographic_containers[row["region_id"]] = dict(row)
        for row in specification.get("zones", []):
            world.geographic_containers[row["zone_id"]] = dict(row)
    elif schema == "3.0.0":
        for row in specification.get("geographic_containers", []):
            container_id = row.get("container_id")
            if not container_id:
                raise ValueError("schema-v3 geographic container missing container_id")
            if container_id in world.geographic_containers:
                raise ValueError(f"duplicate geographic container: {container_id}")
            world.geographic_containers[container_id] = dict(row)
        for container_id, row in world.geographic_containers.items():
            parent_id = row.get("parent_id")
            if parent_id and parent_id not in world.geographic_containers:
                raise ValueError(
                    f"geographic container references missing parent: {container_id}->{parent_id}"
                )
    for row in containers:
        district = District(
            row.get("district_id", row.get("container_id")), row["name"], int(row["population"]),
            row.get("terrain", "empirical mixed terrain"),
            float(row.get("urbanization", .35)), row.get("language_pattern", "FS"),
            row.get("role", "empirical geographic container"),
            float(row.get("connectivity", .5)),
            empirical_covariates={
                str(key): float(value)
                for key, value in dict(row.get("empirical_covariates", {})).items()
            },
        )
        world.districts[district.district_id] = district
        if schema == "2.0.0":
            world.district_hierarchy[district.district_id] = {
                "region_id": str(row.get("region_id", "")),
                "zone_id": str(row.get("zone_id", "")),
            }
        elif schema == "3.0.0":
            hierarchy = {str(key): str(value) for key, value in
                         dict(row.get("container_ids", {})).items() if value}
            if any(value not in world.geographic_containers for value in hierarchy.values()):
                raise ValueError(f"district hierarchy references missing container: {district.district_id}")
            world.district_hierarchy[district.district_id] = hierarchy
    for row in localities:
        container_id = row.get("district_id", row.get("container_id"))
        if container_id not in world.districts:
            raise ValueError(f"unknown empirical district: {container_id}")
        capacity = float(row.get("administrative_capacity", .5))
        locality = Locality(
            locality_id=row["locality_id"], district_id=container_id, name=row["name"],
            kind=row.get("kind", "historical-district"), population=int(row["population"]),
            economic_output=float(row.get("economic_output", row["population"])),
            infrastructure=float(row.get("infrastructure", .5)),
            administrative_capacity=capacity,
            terrain_friction=float(row.get("terrain_friction", 1.0)),
            observability=float(row.get("observability", .5)),
            administrative_role=row.get("administrative_role", "administrative_center"),
            control={"government": ControlVector(.98, .72, capacity, capacity * .85,
                                                   capacity * .65, .52, .7)},
            governance={"security": .55, "justice": capacity * .75,
                        "administration": capacity, "services": capacity * .8,
                        "representation": .5, "leakage": .15},
            x_km=float(row["x_km"]), y_km=float(row["y_km"]),
        )
        if world.config.include_insurgency:
            locality.control["insurgent"] = ControlVector(0, .01, 0, .01, .01, .04, .08)
        world.localities[locality.locality_id] = locality
        world.districts[container_id].locality_ids.append(locality.locality_id)
        world.adjacency[locality.locality_id] = {}
    for district in world.districts.values():
        represented_population = sum(world.localities[locality_id].population
                                     for locality_id in district.locality_ids)
        if represented_population != district.population:
            raise ValueError(
                f"empirical locality populations do not sum to district population: "
                f"{district.district_id} localities={represented_population} district={district.population}"
            )

    def add_edge(first_id: str, second_id: str) -> None:
        if first_id not in world.localities or second_id not in world.localities:
            raise ValueError(f"empirical edge references unknown locality: {first_id}, {second_id}")
        first, second = world.localities[first_id], world.localities[second_id]
        distance = max(.5, hypot(first.x_km - second.x_km, first.y_km - second.y_km))
        terrain = (first.terrain_friction + second.terrain_friction) / 2
        cost = terrain * (.65 + distance / 55.0)
        world.adjacency[first_id][second_id] = cost
        world.adjacency[second_id][first_id] = cost

    seen = set()
    for first_id, neighbors in specification.get("adjacency", {}).items():
        for second_id in neighbors:
            edge = tuple(sorted((first_id, second_id)))
            if first_id != second_id and edge not in seen:
                add_edge(*edge); seen.add(edge)
    if not seen or any(not neighbors for neighbors in world.adjacency.values()):
        raise ValueError("empirical adjacency is empty or contains isolated localities")
    return sum(locality.population for locality in world.localities.values())
