from __future__ import annotations

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
from .world import WorldState, seeded_rng
from math import cos, pi, sin, hypot
from .networks import generate_social_network
from .physical import generate_physical_world
from .logistics import generate_logistics_world
from .information import initialize_information_world
from .organization_ecology import initialize_organization_ecology
from .political_order import initialize_political_order
from .foreign_affairs import initialize_foreign_system


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


def generate_pineland(config: SimulationConfig | None = None) -> WorldState:
    config = config or SimulationConfig()
    config.validate()
    rng = seeded_rng(config, "world-generation")
    geography_rng = seeded_rng(config, "geography-generation")
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

    # Spatial minimum-spanning backbone: each locality attaches to the nearest
    # already-connected locality, guaranteeing connectivity without an
    # identifier-order corridor.
    connected = [min(locality_ids, key=lambda lid: (world.localities[lid].x_km ** 2 +
                                                    world.localities[lid].y_km ** 2, lid))]
    remaining_ids = [lid for lid in locality_ids if lid not in connected]
    while remaining_ids:
        candidate = min(
            ((hypot(world.localities[left].x_km - world.localities[right].x_km,
                    world.localities[left].y_km - world.localities[right].y_km), left, right)
             for right in remaining_ids for left in connected),
            key=lambda item: (item[0], item[1], item[2]),
        )
        _, left, right = candidate
        connect(left, right)
        connected.append(right)
        remaining_ids.remove(right)

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
    if config.geography.district_hub_links:
        for district in world.districts.values():
            hub = district.locality_ids[0]
            for locality_id in district.locality_ids[1:]:
                connect(hub, locality_id)

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

    # Weighted synthetic population, explicit households, and sparse activity implied by adjacency.
    represented_weight = total_population / config.agent_count
    locality_weights = [world.localities[x].population for x in locality_ids]
    person_index = 0
    household_index = 0
    while person_index < config.agent_count:
        size = min(config.agent_count - person_index, max(1, round(rng.lognormvariate(1.15, .35))))
        locality_id = rng.choices(locality_ids, weights=locality_weights, k=1)[0]
        district = world.districts[world.localities[locality_id].district_id]
        household_id = f"H{household_index:07d}"
        member_ids: list[str] = []
        for _ in range(size):
            person_id = f"P{person_index:08d}"
            member_ids.append(person_id)
            languages = _language_vector(district.language_pattern, rng)
            preferences = {f"party-{j}": rng.random() for j in range(1, 4)}
            person = Person(
                person_id, household_id, locality_id, locality_id, represented_weight,
                max(1, min(90, round(rng.normalvariate(34, 18)))), languages,
                {"local": rng.random(), "district": rng.random(), "federal": rng.random()}, preferences,
                grievance=max(0, min(1, rng.betavariate(2, 9))), fear=rng.betavariate(2, 8),
                efficacy=rng.betavariate(4, 4), expected_control={"government": .7, "insurgent": .1},
                trust={"government": rng.uniform(.3, .8), "insurgent": rng.uniform(.05, .35)},
                resources=rng.lognormvariate(0, .55),
            )
            world.persons[person_id] = person
            person_index += 1
        world.households[household_id] = Household(household_id, member_ids, locality_id, locality_id,
                                                    sum(world.persons[p].resources for p in member_ids),
                                                    sum(world.persons[p].age < 16 for p in member_ids))
        household_index += 1

    hubs = sorted(locality_ids, key=lambda key: world.localities[key].population, reverse=True)
    per_formation = max(100, total_population * .0025 / min(17, len(hubs)))
    for index, locality_id in enumerate(hubs[:17]):
        formation = ArmedFormation(f"FDF-{index + 1:02d}", "fdf", locality_id, per_formation, .72, .75, .82, .9, .55, .75, .72, .35)
        world.formations[formation.formation_id] = formation
    if config.include_insurgency:
        target = min(locality_ids, key=lambda key: world.localities[key].administrative_capacity)
        strength = total_population * config.initial_insurgent_share
        world.formations["PRF-01"] = ArmedFormation("PRF-01", "insurgent", target, strength, .45, .7, .75, .65, .5, .7, .55, .75)

    generate_logistics_world(world)
    generate_physical_world(world)
    generate_social_network(world)
    initialize_organization_ecology(world)
    initialize_political_order(world)
    initialize_foreign_system(world)

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

    world.initial_population = world.weighted_population()
    world.initialize_stock_ledger()
    world.assert_invariants()
    return world
