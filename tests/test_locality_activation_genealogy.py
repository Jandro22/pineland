import importlib.util
from pathlib import Path
import random
import sys

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind, SocialEdge
from pineland_sim.events import ScheduledEvent
from pineland_sim.organization_ecology import (
    _apply_local_fighter_change,
    _set_armed_membership,
)
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "trace_locality_activation_genealogy.py"
SPEC = importlib.util.spec_from_file_location("trace_locality_activation_genealogy", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_genealogy_run_is_observation_only_and_uses_live_viability_thresholds():
    config = SimulationConfig(
        agent_count=300, locality_count=24, horizon_days=3,
        seed=20260905, output_mode="ensemble",
    )
    report = MODULE.trace_simulation(config, until=3)
    assert report["historical_outcomes_used"] is False
    assert report["dynamics_modified"] is False
    assert report["thresholds"]["fielded_force_viable_personnel"] == \
        config.organization_ecology.minimum_formation_personnel
    assert report["thresholds"]["member_foothold_present_represented_population"] == "> 1e-12"
    assert report["episodes"]
    assert all(row["activation_end_day"] is not None for row in report["episodes"])
    assert all(abs(value - 1.0) <= 1e-9
               for value in report["parent_edge_weight_sums"].values())


def test_moving_a_sole_viable_formation_is_classified_as_relocation_not_birth():
    world = generate_pineland(SimulationConfig(
        agent_count=400, locality_count=34, horizon_days=1, seed=20260905
    ))
    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    insurgent_ids = {
        organization.organization_id for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    }
    formation = next(
        formation for formation in world.formations.values()
        if formation.organization_id in insurgent_ids
        and sum(
            other.personnel for other in world.formations.values()
            if other.organization_id in insurgent_ids
            and other.locality_id == formation.locality_id
            and other.operational_status == "effective"
        ) == formation.personnel
    )
    origin = formation.locality_id
    occupied = {
        item.locality_id for item in world.formations.values()
        if item.organization_id in insurgent_ids and item.personnel > 0
        and item.operational_status == "effective"
    }
    target = next(
        locality_id for locality_id in world.localities
        if locality_id not in occupied and locality_id != origin
    )
    before = tracer.capture()
    formation.locality_id = target
    zones = [zone for zone in world.microzones.values() if zone.locality_id == target]
    formation.current_microzone_id = zones[0].microzone_id
    tracer.observe_transition(before, "force_movement", "TEST-MOVE", 1.0)
    target_episode = next(
        row for row in tracer.episodes
        if row.channel == "fielded_force_viable" and row.locality_id == target
    )
    assert target_episode.cause == "formation_relocation"
    assert target_episode.parent_locality_id == origin
    origin_episode = tracer._by_id[target_episode.parent_activation_id]
    assert origin_episode.activation_end_day == 1.0
    edges = [edge for edge in tracer.parent_edges()
             if edge["child_activation_id"] == target_episode.activation_id]
    assert edges == [{
        "child_activation_id": target_episode.activation_id,
        "child_locality_id": target,
        "child_channel": "fielded_force_viable",
        "parent_activation_id": origin_episode.activation_id,
        "parent_locality_id": origin,
        "parent_channel": "fielded_force_viable",
        "weight": 1.0,
        "pathway": "formation_relocation",
    }]


def test_formation_in_transit_is_not_a_viable_locality_presence():
    world = generate_pineland(SimulationConfig(
        agent_count=400, locality_count=34, horizon_days=1, seed=20260905
    ))
    tracer = MODULE.LocalityActivationTracer(world)
    formation = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    )
    locality_id = formation.locality_id
    before = tracer.capture()
    assert before["formation_mass"][locality_id] > 0
    formation.moving = True
    after = tracer.capture()
    remaining = sum(
        item.personnel for item in world.formations.values()
        if item.organization_id == formation.organization_id
        and item.locality_id == locality_id
        and item.formation_id != formation.formation_id
        and item.operational_status == "effective"
        and not item.moving and not item.outside_pineland
    )
    assert after["formation_mass"][locality_id] == remaining


def test_positive_local_member_mass_is_a_causal_foothold_below_saturated_access():
    world = generate_pineland(SimulationConfig(
        agent_count=400, locality_count=34, horizon_days=1, seed=20260906
    ))
    organization = next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )
    formation_localities = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
        and formation.personnel > 0
    }
    locality_id = next(
        locality_id for locality_id in sorted(world.localities)
        if locality_id not in formation_localities
        and any(person.residence_locality_id == locality_id for person in world.persons.values())
    )
    for person in world.persons.values():
        if (person.residence_locality_id == locality_id and
                person.organization_id == organization.organization_id):
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
    person = next(
        person for person in world.persons.values()
        if person.residence_locality_id == locality_id
    )
    fraction = min(
        0.01,
        world.config.organization_ecology.minimum_proto_represented_population /
        max(person.weight, 1e-12) * 0.1,
    )
    _set_armed_membership(person, organization, fraction)
    organization.member_ids.add(person.person_id)
    tracer = MODULE.LocalityActivationTracer(world)
    snapshot = tracer.capture()
    assert snapshot["states"]["member_foothold_present"][locality_id]
    assert not snapshot["states"]["member_access_saturated"][locality_id]


def test_local_member_foothold_parents_new_fielded_force_activation():
    world = generate_pineland(SimulationConfig(
        agent_count=500, locality_count=34, horizon_days=1, seed=20260907
    ))
    organization = next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )
    occupied = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
        and formation.personnel > 0
    }
    locality_id = next(
        locality_id for locality_id in sorted(world.localities)
        if locality_id not in occupied
        and any(person.residence_locality_id == locality_id for person in world.persons.values())
    )
    for person in world.persons.values():
        if (person.residence_locality_id == locality_id and
                person.organization_id == organization.organization_id):
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
    member = next(
        person for person in world.persons.values()
        if person.residence_locality_id == locality_id
    )
    _set_armed_membership(member, organization, min(0.1, 10.0 / member.weight))
    organization.member_ids.add(member.person_id)
    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    foothold = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
        and episode.locality_id == locality_id
    )
    before = tracer.capture()
    minimum = world.config.organization_ecology.minimum_formation_personnel
    _apply_local_fighter_change(world, organization, locality_id, minimum)
    tracer.observe_transition(before, "recruitment", "TEST-FORCE-BIRTH", 1.0)
    child = next(
        episode for episode in tracer.episodes
        if episode.channel == "fielded_force_viable"
        and episode.locality_id == locality_id
        and episode.cause == "local_member_to_force_generation"
    )
    assert child.parent_channel == "member_foothold_present"
    assert child.parent_activation_id == foothold.activation_id
    edge = next(
        edge for edge in tracer.parent_edges()
        if edge["child_activation_id"] == child.activation_id
    )
    assert edge["parent_activation_id"] == foothold.activation_id
    assert edge["pathway"] == "local_member_to_force_generation"


def test_stored_cross_local_social_exposure_parents_new_member_foothold():
    world = generate_pineland(SimulationConfig(
        agent_count=800, locality_count=24, horizon_days=1, seed=741
    ))
    organization = next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )
    edge = next(
        edge for edge in world.social_edges.values()
        if "bridge" in edge.layers and
        world.persons[edge.person_a_id].residence_locality_id !=
        world.persons[edge.person_b_id].residence_locality_id
    )
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    target_locality = target.residence_locality_id
    for person in world.persons.values():
        if (person.residence_locality_id == target_locality and
                person.organization_id == organization.organization_id):
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
    _set_armed_membership(source, organization, 1.0)
    organization.member_ids.add(source.person_id)
    _set_armed_membership(target, None, 0.0)
    source.public_behavior = "armed_participation"
    target.public_behavior = "neutral"
    world.config.social_network.behavior_update_rate = 0.0
    for formation in world.formations.values():
        if (
            formation.organization_id == organization.organization_id
            and formation.locality_id == target_locality
        ):
            formation.personnel = 0.0
    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    source_episode = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
        and episode.locality_id == source.residence_locality_id
    )
    social_before = tracer.social_provenance.capture()
    ProcessEngine(world, random.Random(741)).on_social_influence(
        "TEST-SOCIAL-TICK",
        ScheduledEvent(
            0.5, 0, 0, "social_influence",
            {"elapsed_days": 1.0, "interval": 1.0},
        ),
    )
    tracer.social_provenance.observe_social_influence(
        social_before, event_id="TEST-SOCIAL-TICK", time=0.5
    )
    assert target.social_exposure[organization.organization_id] > 0.0
    before = tracer.capture()
    _set_armed_membership(target, organization, min(0.1, 10.0 / target.weight))
    organization.member_ids.add(target.person_id)
    tracer.observe_transition(before, "recruitment", "TEST-SOCIAL-SEED", 1.0)
    child = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
        and episode.locality_id == target_locality
        and episode.activation_day == 1.0
    )
    assert child.cause == "stored_social_exposure_recruitment"
    assert child.parent_activation_id == source_episode.activation_id


def test_current_sympathizer_chain_without_stored_provenance_does_not_guess_parent():
    world = generate_pineland(SimulationConfig(
        agent_count=800, locality_count=24, horizon_days=1, seed=742
    ))
    organization = next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )
    people = list(world.persons.values())
    source = people[0]
    target = next(
        person for person in people
        if person.residence_locality_id != source.residence_locality_id
    )
    middle = next(
        person for person in people
        if person.person_id not in {source.person_id, target.person_id}
    )

    # Isolate a three-node causal chain. All other insurgent memberships and
    # sympathetic states are removed so no shorter parent path can exist.
    for person in world.persons.values():
        if person.organization_id == organization.organization_id:
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
    _set_armed_membership(source, organization, 1.0)
    organization.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    middle.public_behavior = "insurgent_sympathy"
    middle.insurgent_affinity = {organization.organization_id: 1.0}
    _set_armed_membership(target, None, 0.0)
    for formation in world.formations.values():
        if (
            formation.organization_id == organization.organization_id
            and formation.locality_id == target.residence_locality_id
        ):
            formation.personnel = 0.0

    # Remove all existing incident edges for the three actors and insert only
    # source--middle--target. This makes the shortest social genealogy known.
    selected = {source.person_id, middle.person_id, target.person_id}
    for key, edge in list(world.social_edges.items()):
        if edge.person_a_id in selected or edge.person_b_id in selected:
            del world.social_edges[key]
    for person_id in selected:
        world.social_neighbors[person_id] = []
    for first, second in ((source, middle), (middle, target)):
        key = tuple(sorted((first.person_id, second.person_id)))
        world.social_edges[key] = SocialEdge(
            key[0], key[1], ("bridge",), 1.0, 1.0, 1.0, 1.0
        )
        world.social_neighbors[first.person_id].append(second.person_id)
        world.social_neighbors[second.person_id].append(first.person_id)
    for person_id in selected:
        world.social_neighbors[person_id].sort()

    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    source_episode = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
        and episode.locality_id == source.residence_locality_id
    )
    before = tracer.capture()
    _set_armed_membership(target, organization, min(0.1, 10.0 / target.weight))
    organization.member_ids.add(target.person_id)
    tracer.observe_transition(before, "recruitment", "TEST-SYMPATHIZER-CHAIN", 1.0)
    child = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
        and episode.locality_id == target.residence_locality_id
        and episode.activation_day == 1.0
    )
    assert source_episode.activation_id
    assert child.cause == "local_recruitment_unattributed_provenance"
    assert child.parent_locality_id is None
    assert child.parent_activation_id is None
    assert not any(
        edge["child_activation_id"] == child.activation_id
        for edge in tracer.parent_edges()
    )


def test_partial_parent_provenance_preserves_known_mass_and_unknown_remainder():
    world = generate_pineland(SimulationConfig(
        agent_count=300, locality_count=24, horizon_days=1, seed=743
    ))
    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    source_episode = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
    )
    child_locality = next(
        locality_id for locality_id in world.localities
        if locality_id != source_episode.locality_id
    )
    child = tracer._open(
        "member_foothold_present",
        child_locality,
        1.0,
        cause="stored_social_exposure_recruitment",
        event_type="recruitment",
        event_id="TEST-PARTIAL",
        parent_sources={source_episode.locality_id: 0.4},
        parent_channel="member_foothold_present",
        parent_unattributed_mass=0.6,
    )
    assert abs(child.parent_weights[source_episode.locality_id] - 0.4) <= 1e-12
    assert abs(child.parent_unattributed_weight - 0.6) <= 1e-12
    edges = [
        edge for edge in tracer.parent_edges()
        if edge["child_activation_id"] == child.activation_id
    ]
    assert len(edges) == 1
    assert abs(edges[0]["weight"] - 0.4) <= 1e-12
    assert edges[0]["parent_activation_id"] == source_episode.activation_id


def test_social_locality_provenance_does_not_guess_between_reactivation_episodes():
    world = generate_pineland(SimulationConfig(
        agent_count=300, locality_count=24, horizon_days=1, seed=744
    ))
    tracer = MODULE.LocalityActivationTracer(world)
    tracer.initialize(0.0)
    source_episode = next(
        episode for episode in tracer.episodes
        if episode.channel == "member_foothold_present"
    )
    source_locality = source_episode.locality_id
    tracer._close("member_foothold_present", source_locality, 0.5)
    second_source = tracer._open(
        "member_foothold_present",
        source_locality,
        0.75,
        cause="local_recruitment",
        event_type="recruitment",
        event_id="TEST-REACTIVATION",
        parent_sources={},
        parent_channel=None,
    )
    child_locality = next(
        locality_id for locality_id in world.localities
        if locality_id != source_locality
    )
    child = tracer._open(
        "member_foothold_present",
        child_locality,
        1.0,
        cause="stored_social_exposure_recruitment",
        event_type="recruitment",
        event_id="TEST-DELAYED-SOCIAL",
        parent_sources={source_locality: 1.0},
        parent_channel="member_foothold_present",
    )
    assert second_source.activation_id != source_episode.activation_id
    assert child.parent_locality_id == source_locality
    assert child.parent_activation_id is None
    assert child.parent_activation_ids == {source_locality: None}
    edges = [
        edge for edge in tracer.parent_edges()
        if edge["child_activation_id"] == child.activation_id
    ]
    assert len(edges) == 1
    assert edges[0]["parent_locality_id"] == source_locality
    assert edges[0]["parent_activation_id"] is None
    assert edges[0]["weight"] == 1.0


def test_parentage_ontology_covers_all_declared_foothold_origins_and_fails_closed():
    cases = {
        ("local_recruitment", "recruitment"): "local_spontaneous_ignition",
        ("stored_social_exposure_recruitment", "recruitment"): "social_network_seeded",
        ("armed_member_migration", "mobility"): "migrating_member_seeded",
        ("formation_seeded_local_recruitment", "recruitment"): "formation_recruitment_seeded",
        ("formation_relocation", "force_movement"): "formation_relocation",
        ("organization_split_offspring", "organization_ecology"): "organizational_split_offspring",
        ("external_sanctuary_seed", "foreign_affairs"): "sanctuary_external_seeded",
        ("local_recruitment_unattributed_provenance", "recruitment"): "unresolved",
    }
    assert {
        MODULE.classify_parentage(cause, event_type)
        for cause, event_type in cases
    } == set(MODULE.PARENTAGE_CLASSES)
    for inputs, expected in cases.items():
        assert MODULE.classify_parentage(*inputs) == expected
