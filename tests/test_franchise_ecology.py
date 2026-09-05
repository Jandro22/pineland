from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import random

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import Organization, OrganizationKind
from pineland_sim.events import ScheduledEvent
from pineland_sim.organization_ecology import (
    _recruitment_intensity,
    _set_armed_membership,
    locality_franchise_support_profile,
    merge_organizations,
    organization_contact_overlap,
    organization_local_rootedness,
    process_organization_ecology,
    recruit_and_retain,
    split_organization,
)
from pineland_sim.processes import ProcessEngine


class ZeroRng:
    def random(self):
        return 0.0


class MaxChoiceRng:
    def random(self):
        return 0.0

    def choices(self, population, weights=None, k=1):
        if weights is None:
            return [population[0]] * k
        winner = max(range(len(population)), key=lambda index: weights[index])
        return [population[winner]] * k


class LowDrawEcologyRng(random.Random):
    def random(self):
        return 0.0

    def normalvariate(self, mu, sigma):
        return mu

    def uniform(self, a, b):
        return (a + b) / 2


def _organization(organization_id: str) -> Organization:
    return Organization(
        organization_id=organization_id,
        name=organization_id,
        kind=OrganizationKind.INSURGENT,
        resources=100.0,
        cohesion=.6,
        discipline=.6,
        accountability=.5,
        local_knowledge=.5,
        persistence=.6,
        mobility=.5,
        institutional_quality=.5,
        capital={"social": .5, "political": .5, "organizational": .5, "material": .5},
        ideology={"reform": .5, "separatism": 0.0},
    )


def _world(seed: int = 6061):
    world = generate_pineland(SimulationConfig(
        agent_count=320,
        locality_count=24,
        horizon_days=2,
        seed=seed,
        include_insurgency=False,
    ))
    local = _organization("franchise-local")
    outsider = _organization("franchise-outsider")
    world.organizations[local.organization_id] = local
    world.organizations[outsider.organization_id] = outsider
    return world, local, outsider


def _rootedness_fixture(seed: int = 6061):
    world, local, outsider = _world(seed)
    locality_id = next(
        locality_id for locality_id in world.localities
        if sum(p.residence_locality_id == locality_id for p in world.persons.values()) >= 3
    )
    district_id = world.localities[locality_id].district_id
    residents = [
        p for p in world.persons.values()
        if p.residence_locality_id == locality_id
    ]
    candidate, local_member = residents[:2]
    outsider_member = next(
        p for p in world.persons.values()
        if world.localities[p.home_locality_id].district_id != district_id
        and p.person_id not in {candidate.person_id, local_member.person_id}
    )
    outsider_member.residence_locality_id = locality_id
    _set_armed_membership(local_member, local, 1.0)
    local.member_ids.add(local_member.person_id)
    _set_armed_membership(outsider_member, outsider, 1.0)
    outsider.member_ids.add(outsider_member.person_id)
    candidate.grievance = 1.0
    candidate.fear = 0.0
    candidate.political_access = 0.0
    candidate.identities["federal"] = .5
    return world, local, outsider, candidate, local_member, outsider_member, locality_id


def test_local_identity_makes_rooted_franchise_more_recruitable_without_ethnic_rules():
    world, local, outsider, candidate, *_rest, locality_id = _rootedness_fixture()
    candidate.identities["local"] = 1.0
    candidate.identities["district"] = 1.0
    local_root = organization_local_rootedness(world, local, locality_id)
    outsider_root = organization_local_rootedness(world, outsider, locality_id)
    local_intensity = _recruitment_intensity(world, candidate, local, .5, local_root)[0]
    outsider_intensity = _recruitment_intensity(world, candidate, outsider, .5, outsider_root)[0]
    assert local_root["home_locality_share"] == 1.0
    assert outsider_root["home_locality_share"] == 0.0
    assert local_intensity > outsider_intensity

    candidate.identities["local"] = 0.0
    candidate.identities["district"] = 0.0
    local_no_salience = _recruitment_intensity(world, candidate, local, .5, local_root)[0]
    outsider_no_salience = _recruitment_intensity(world, candidate, outsider, .5, outsider_root)[0]
    assert abs(local_no_salience - outsider_no_salience) <= 1e-12


def test_recruiting_indigenous_members_endogenously_localizes_an_outside_franchise():
    world, _local, outsider, candidate, local_member, _outsider_member, locality_id = (
        _rootedness_fixture(seed=6062)
    )
    candidate.identities["local"] = 1.0
    candidate.identities["district"] = 1.0
    before_root = organization_local_rootedness(world, outsider, locality_id)
    before = _recruitment_intensity(world, candidate, outsider, .5, before_root)[0]

    # Reassign an indigenous resident to the outside franchise. The theory
    # should become less "outside" without editing any ethnicity/case field.
    local_member.organization_id = None
    local_member.armed_fraction = 0.0
    world.organizations["franchise-local"].member_ids.discard(local_member.person_id)
    _set_armed_membership(local_member, outsider, 1.0)
    outsider.member_ids.add(local_member.person_id)
    after_root = organization_local_rootedness(world, outsider, locality_id)
    after = _recruitment_intensity(world, candidate, outsider, .5, after_root)[0]
    assert after_root["home_locality_share"] > before_root["home_locality_share"]
    assert after > before


def test_social_influence_is_franchise_specific_when_multiple_insurgencies_exist():
    world, local, outsider = _world(seed=6063)
    edge = next(iter(world.social_edges.values()))
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    for person in world.persons.values():
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
    local.member_ids.clear()
    outsider.member_ids.clear()
    _set_armed_membership(source, local, 1.0)
    local.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    source.grievance = 1.0
    source.fear = 0.0
    source.efficacy = 0.0
    source.political_access = 0.0
    source.expected_control["government"] = 0.0
    source.expected_control["insurgent"] = 1.0
    source.private_preference = {key: 0.0 for key in source.private_preference}
    source.grievance = 1.0
    source.fear = 0.0
    source.efficacy = 0.0
    source.political_access = 0.0
    source.expected_control["government"] = 0.0
    source.expected_control["insurgent"] = 1.0
    source.private_preference = {key: 0.0 for key in source.private_preference}
    world.config.social_network.behavior_update_rate = 0.0
    ProcessEngine(world, random.Random(1)).on_social_influence(
        "SYN-FRANCHISE-SOCIAL",
        ScheduledEvent(1.0, 0, 1, "social_influence", {"elapsed_days": 1.0, "interval": 1.0}),
    )
    assert target.social_exposure["insurgent"] > 0.0
    assert target.social_exposure[local.organization_id] > 0.0
    assert target.social_exposure[outsider.organization_id] == 0.0


def test_ex_member_sympathy_retains_franchise_identity_in_social_transmission():
    world, local, outsider = _world(seed=6064)
    edge = next(iter(world.social_edges.values()))
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    for person in world.persons.values():
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
    local.member_ids.clear()
    outsider.member_ids.clear()
    _set_armed_membership(source, local, 1.0)
    local.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    local.member_ids.discard(source.person_id)
    _set_armed_membership(source, None, 0.0)
    assert source.public_behavior == "insurgent_sympathy"
    assert source.insurgent_affinity[local.organization_id] > 0.0
    world.config.social_network.behavior_update_rate = 0.0
    ProcessEngine(world, random.Random(2)).on_social_influence(
        "SYN-EXMEMBER-SOCIAL",
        ScheduledEvent(1.0, 0, 1, "social_influence", {"elapsed_days": 1.0, "interval": 1.0}),
    )
    assert target.social_exposure[local.organization_id] > 0.0
    assert target.social_exposure[outsider.organization_id] == 0.0


def test_social_control_credit_is_franchise_specific_not_generic_only():
    world, local, outsider = _world(seed=60641)
    edge = next(iter(world.social_edges.values()))
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    for person in world.persons.values():
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
    local.member_ids.clear()
    outsider.member_ids.clear()
    _set_armed_membership(source, local, 1.0)
    local.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    source.grievance = 1.0
    source.fear = 0.0
    source.efficacy = 0.0
    source.political_access = 0.0
    source.expected_control["government"] = 0.0
    source.expected_control["insurgent"] = 1.0
    source.private_preference = {key: 0.0 for key in source.private_preference}
    target.grievance = 1.0
    target.fear = 0.0
    target.efficacy = 0.0
    target.political_access = 0.0
    target.expected_control["government"] = 0.0
    target.expected_control["insurgent"] = 1.0
    target.private_preference = {key: 0.0 for key in target.private_preference}
    world.config.social_network.behavior_update_rate = 1.0
    locality_id = target.residence_locality_id
    before_local = world.localities[locality_id].control.get(
        local.organization_id
    ).social if local.organization_id in world.localities[locality_id].control else 0.0
    before_outsider = world.localities[locality_id].control.get(
        outsider.organization_id
    ).social if outsider.organization_id in world.localities[locality_id].control else 0.0
    ProcessEngine(world, MaxChoiceRng()).on_social_influence(
        "SYN-FRANCHISE-CONTROL",
        ScheduledEvent(1.0, 0, 1, "social_influence", {"elapsed_days": 1.0, "interval": 1.0}),
    )
    assert target.public_behavior in {"insurgent_sympathy", "armed_participation"}
    assert target.insurgent_affinity.get(local.organization_id, 0.0) > 0.0
    assert world.localities[locality_id].control[local.organization_id].social > before_local
    after_outsider = (
        world.localities[locality_id].control[outsider.organization_id].social
        if outsider.organization_id in world.localities[locality_id].control else 0.0
    )
    assert after_outsider == before_outsider


def test_competing_recruitment_is_independent_of_organization_insertion_order():
    def run(reverse: bool):
        world, local, outsider = _world(seed=6065)
        if reverse:
            non_insurgent = [
                (key, value) for key, value in world.organizations.items()
                if value.kind is not OrganizationKind.INSURGENT
            ]
            world.organizations = OrderedDict(
                non_insurgent + [
                    (outsider.organization_id, outsider),
                    (local.organization_id, local),
                ]
            )
        candidate = next(iter(world.persons.values()))
        candidate.organization_id = None
        candidate.armed_fraction = 0.0
        candidate.social_exposure = {
            "insurgent": 1.0,
            local.organization_id: 1.0,
            outsider.organization_id: 1.0,
        }
        candidate.identities["local"] = 0.0
        candidate.identities["district"] = 0.0
        world.config.organization_ecology.local_rootedness_weight = 0.0
        world.config.organization_ecology.fighter_conversion_fraction = 0.0
        world.config.organization_ecology.recruitment_subcohorts = 1
        world.config.recruitment_rate = 100.0
        world.config.membership_exit_rate = 0.0
        result = recruit_and_retain(world, 1.0, ZeroRng(), interval_days=1.0)
        return candidate.organization_id, result

    first_winner, first = run(False)
    second_winner, second = run(True)
    assert first_winner == second_winner == "franchise-local"
    assert first["contested_recruitment_candidates"] == 1
    assert second["contested_recruitment_candidates"] == 1


def test_interorganizational_contact_requires_shared_local_arena():
    world, local, outsider = _world(seed=6066)
    people = list(world.persons.values())
    first = people[0]
    second = next(
        person for person in people
        if person.residence_locality_id != first.residence_locality_id
    )
    _set_armed_membership(first, local, 1.0)
    local.member_ids.add(first.person_id)
    _set_armed_membership(second, outsider, 1.0)
    outsider.member_ids.add(second.person_id)
    assert organization_contact_overlap(world, local, outsider) == 0.0

    second.residence_locality_id = first.residence_locality_id
    assert organization_contact_overlap(world, local, outsider) == 1.0


def test_merger_hazard_requires_real_local_contact_opportunity():
    def configure(co_located: bool):
        world, local, outsider = _world(seed=60661)
        people = list(world.persons.values())
        first = people[0]
        second = next(
            person for person in people
            if person.residence_locality_id != first.residence_locality_id
        )
        if co_located:
            second.residence_locality_id = first.residence_locality_id
        _set_armed_membership(first, local, 1.0)
        local.member_ids.add(first.person_id)
        _set_armed_membership(second, outsider, 1.0)
        outsider.member_ids.add(second.person_id)
        cfg = world.config.organization_ecology
        cfg.proto_base_hazard = 0.0
        cfg.birth_base_hazard = 0.0
        cfg.split_base_hazard = 0.0
        cfg.collapse_base_hazard = 0.0
        cfg.succession_base_hazard = 0.0
        cfg.merger_base_hazard = 1.0
        return world

    disjoint = configure(False)
    disjoint_result = process_organization_ecology(
        disjoint, 7.0, LowDrawEcologyRng(1), interval_days=7.0
    )
    assert disjoint_result["mergers"] == 0
    assert len([
        organization for organization in disjoint.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    ]) == 2

    co_located = configure(True)
    colocated_result = process_organization_ecology(
        co_located, 7.0, LowDrawEcologyRng(1), interval_days=7.0
    )
    assert colocated_result["mergers"] == 1
    assert len([
        organization for organization in co_located.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    ]) == 1


def test_locality_support_profile_detects_fragmented_insurgent_constituency():
    world, local, outsider, _candidate, local_member, outsider_member, locality_id = (
        _rootedness_fixture(seed=6067)
    )
    local_member.public_behavior = "armed_participation"
    outsider_member.public_behavior = "armed_participation"
    profile = locality_franchise_support_profile(world, locality_id)
    assert profile["supported_franchise_count"] == 2
    assert profile["represented_franchise_support"][local.organization_id] > 0
    assert profile["represented_franchise_support"][outsider.organization_id] > 0
    assert 0 < profile["support_fragmentation"] <= 0.5
    assert profile["support_concentration_hhi"] < 1.0


def test_split_and_merge_rewrite_member_affinity_to_live_descendant_franchise():
    world = generate_pineland(SimulationConfig(
        agent_count=500, locality_count=24, horizon_days=2,
        seed=6068, include_insurgency=True,
    ))
    children = split_organization(world, "insurgent", 1.0, random.Random(3))
    assert len(children) == 2
    for child in children:
        for person_id in child.member_ids:
            person = world.persons[person_id]
            assert person.organization_id == child.organization_id
            assert set(person.insurgent_affinity) == {child.organization_id}

    merged = merge_organizations(
        world, children[0].organization_id, children[1].organization_id,
        2.0, random.Random(4),
    )
    for person_id in merged.member_ids:
        person = world.persons[person_id]
        assert person.organization_id == merged.organization_id
        assert set(person.insurgent_affinity) == {merged.organization_id}
