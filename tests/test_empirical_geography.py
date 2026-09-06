import json
from pathlib import Path

import pytest

from pineland_sim import SimulationConfig, generate_pineland


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "studies" / "nepal_2001_2006" / "config" / "case_environment.json"
REPAIRED_CASE = ROOT / "studies" / "nepal_2001_2006" / "config" / "case_environment_repaired.json"
AFGHAN_CASE = ROOT / "studies" / "afghanistan_2004_2021" / "config" / "case_environment.json"


def _minimal_v3_specification():
    return {
        "schema_version": "3.0.0",
        "geographic_containers": [
            {"container_id": "R1", "name": "Region One", "level": "region"},
            {"container_id": "P1", "name": "Province One", "level": "province",
             "parent_id": "R1"},
        ],
        "districts": [
            {"district_id": f"D{i}", "name": f"District {i}", "population": 1000,
             "container_ids": {"region": "R1", "province": "P1"}}
            for i in range(1, 18)
        ],
        "localities": [
            {"locality_id": f"L{i}", "district_id": f"D{i}", "name": f"Center {i}",
             "kind": "town", "population": 1000, "x_km": float(i), "y_km": 0.0,
             "administrative_role": "district_headquarters"}
            for i in range(1, 18)
        ],
        "adjacency": {
            f"L{i}": [neighbor for neighbor in (f"L{i-1}" if i > 1 else None,
                                                  f"L{i+1}" if i < 17 else None)
                       if neighbor]
            for i in range(1, 18)
        },
    }


def test_nepal_case_geography_instantiates_75_historical_localities():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(agent_count=150, locality_count=75, horizon_days=1, seed=12001)
    world = generate_pineland(config, empirical_geography=specification)
    assert len(world.localities) == 75
    assert len(world.districts) == 5
    assert {locality.name for locality in world.localities.values()} == {
        row["name"] for row in specification["localities"]
    }
    assert round(sum(locality.population for locality in world.localities.values())) == 23_151_423
    assert all(world.adjacency[locality_id] for locality_id in world.localities)
    assert world.formations["PRF-01"].locality_id == specification["initial_insurgent_locality_ids"][0]


def test_empirical_geography_rejects_resolution_mismatch():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="locality_count"):
        generate_pineland(SimulationConfig(agent_count=80, locality_count=72, horizon_days=1),
                          empirical_geography=specification)


def test_logistics_source_uses_full_container_catchment_population():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(agent_count=150, locality_count=75, horizon_days=1, seed=12002)
    config.logistics.source_capacity_model = "population_catchment"
    world = generate_pineland(config, empirical_geography=specification)
    source = world.supply_sources["SUP-fdf-01"]
    container_population = world.districts[world.localities[source.locality_id].district_id].population
    assert source.capacity == max(5_000.0, container_population * config.logistics.source_capacity_per_resident)
    assert source.capacity > world.localities[source.locality_id].population * config.logistics.source_capacity_per_resident


def test_repaired_nepal_geography_has_real_hierarchy_and_named_settlements():
    specification = json.loads(REPAIRED_CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(agent_count=300, locality_count=len(specification["localities"]),
                              horizon_days=1, seed=12003)
    world = generate_pineland(config, empirical_geography=specification)
    assert len(world.districts) == 75
    assert len(world.localities) == 300
    assert len(world.geographic_containers) == 19  # 5 regions + 14 zones
    assert len(world.district_hierarchy) == 75
    assert world.district_hierarchy["NP-D53"]["region_id"] == "NP-R4"
    assert world.geographic_containers[world.district_hierarchy["NP-D53"]["zone_id"]]["name"] == "Rapti Zone"
    assert world.geographic_containers[world.district_hierarchy["NP-D53"]["zone_id"]]["region_id"] == "NP-R4"
    assert sum(locality.administrative_role == "district_headquarters"
               for locality in world.localities.values()) == 75
    assert sum(post.organization_id == "police" for post in world.security_posts.values()) == 75
    manang_post = world.security_posts["POST-NP-D41-HQ-POLICE"]
    manang_district = world.districts["NP-D41"]
    assert manang_post.personnel == pytest.approx(
        max(15.0, min(300.0, manang_district.population * .0015))
    )
    assert world.localities["NP-D53-HQ"].name == "Liwang"
    assert world.localities["NP-D53-HQ"].kind == "town"
    assert world.localities["NP-D27-HQ"].kind == "city"
    assert world.localities["NP-D53-HQ"].district_id == "NP-D53"
    assert world.formations["PRF-01"].locality_id == "NP-D53-HQ"
    assert all(
        world.localities[formation.locality_id].administrative_role == "district_headquarters"
        for formation in world.formations.values() if formation.organization_id == "fdf"
    )
    assert all(
        world.localities[source.locality_id].administrative_role == "district_headquarters"
        for source in world.supply_sources.values()
        if source.organization_id in {"fdf", "police"}
    )
    world.assert_invariants()


def test_empirical_population_is_stratified_and_conserves_every_locality():
    specification = json.loads(REPAIRED_CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(agent_count=len(specification["localities"]),
                              locality_count=len(specification["localities"]),
                              horizon_days=1, seed=12005)
    world = generate_pineland(config, empirical_geography=specification)
    represented = {}
    counts = {}
    for person in world.persons.values():
        represented[person.residence_locality_id] = (
            represented.get(person.residence_locality_id, 0.0) + person.weight
        )
        counts[person.residence_locality_id] = counts.get(person.residence_locality_id, 0) + 1
    assert set(represented) == set(world.localities)
    assert all(count == 1 for count in counts.values())
    for locality_id, locality in world.localities.items():
        assert represented[locality_id] == pytest.approx(locality.population)


def test_empirical_geography_rejects_fewer_agents_than_localities():
    specification = json.loads(REPAIRED_CASE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="agent_count >= locality_count"):
        generate_pineland(
            SimulationConfig(agent_count=len(specification["localities"]) - 1,
                             locality_count=len(specification["localities"]), horizon_days=1),
            empirical_geography=specification,
        )


def test_empirical_geography_rejects_district_population_mismatch():
    specification = json.loads(REPAIRED_CASE.read_text(encoding="utf-8"))
    specification["localities"][0]["population"] += 1
    with pytest.raises(ValueError, match="do not sum to district population"):
        generate_pineland(
            SimulationConfig(agent_count=len(specification["localities"]),
                             locality_count=len(specification["localities"]), horizon_days=1),
            empirical_geography=specification,
        )


def test_schema_v3_supports_generic_region_province_district_hierarchy():
    # SimulationConfig intentionally enforces a minimum world size of 17
    # localities.  Exercise the generic hierarchy adapter at that supported
    # boundary rather than weakening the global simulator invariant merely to
    # create a one-node unit fixture.
    specification = _minimal_v3_specification()
    config = SimulationConfig(agent_count=17, locality_count=17, horizon_days=1,
                              include_insurgency=False, seed=12006)
    world = generate_pineland(config, empirical_geography=specification)
    assert world.district_hierarchy["D1"] == {"region": "R1", "province": "P1"}
    assert world.geographic_containers["P1"]["parent_id"] == "R1"
    world.assert_invariants()


def test_empirical_initialization_seed_separates_initial_state_from_process_seed():
    specification = _minimal_v3_specification()
    worlds = []
    for seed in (12061, 99881):
        config = SimulationConfig(
            agent_count=68, locality_count=17, horizon_days=1,
            include_insurgency=False, seed=seed, initialization_seed=777,
        )
        worlds.append(generate_pineland(config, empirical_geography=specification))
    first, second = worlds
    person_state = lambda world: [
        (
            person.person_id, person.residence_locality_id, person.weight,
            person.grievance, person.fear, person.efficacy,
            tuple(sorted(person.identities.items())),
            tuple(sorted(person.languages.items())),
            tuple(sorted(person.trust.items())),
            person.resources, person.community_id,
        )
        for person in world.persons.values()
    ]
    edge_state = lambda world: [
        (
            key, edge.layers, edge.weight, edge.trust,
            edge.language_compatibility, edge.represented_relationships,
        )
        for key, edge in sorted(world.social_edges.items())
    ]
    zone_state = lambda world: [
        (
            zone.microzone_id, zone.population_share, zone.infrastructure,
            zone.terrain_friction, zone.observability,
        )
        for zone in sorted(world.microzones.values(), key=lambda item: item.microzone_id)
    ]
    assert person_state(first) == person_state(second)
    assert edge_state(first) == edge_state(second)
    assert zone_state(first) == zone_state(second)


def test_empirical_population_prior_means_are_resolution_stable():
    specification = _minimal_v3_specification()
    worlds = []
    for agents in (17, 68):
        config = SimulationConfig(
            agent_count=agents, locality_count=17, horizon_days=1,
            include_insurgency=False, seed=12062, initialization_seed=777,
        )
        worlds.append(generate_pineland(config, empirical_geography=specification))
    targets = {"grievance": 2 / 11, "fear": .2, "efficacy": .5}
    for world in worlds:
        for locality_id in world.localities:
            residents = [
                person for person in world.persons.values()
                if person.residence_locality_id == locality_id
            ]
            represented = sum(person.weight for person in residents)
            for field, target in targets.items():
                mean = sum(
                    person.weight * getattr(person, field) for person in residents
                ) / represented
                assert mean == pytest.approx(target, abs=1e-12)
            for identity in ("local", "district", "federal"):
                mean = sum(
                    person.weight * person.identities[identity] for person in residents
                ) / represented
                assert mean == pytest.approx(.5, abs=1e-12)
            assert sum(person.resources for person in residents) / represented == pytest.approx(
                1.0 * __import__("math").exp(.5 * .55 ** 2), abs=1e-12
            )


def test_repaired_initial_force_dispersion_is_geographic_not_identifier_order():
    specification = json.loads(REPAIRED_CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(agent_count=300, locality_count=len(specification["localities"]),
                              horizon_days=1, seed=12004)
    world = generate_pineland(config, empirical_geography=specification)
    insurgent_districts = {world.localities[f.locality_id].district_id
                           for f in world.formations.values()
                           if f.organization_id == "insurgent"}
    # The old tie bug placed almost every token into NP-D01..NP-D23.  The
    # repaired rule must remain centered on the declared Rolpa origin.
    assert "NP-D53" in insurgent_districts
    assert len(insurgent_districts & {f"NP-D{i:02d}" for i in range(1, 17)}) < 4
