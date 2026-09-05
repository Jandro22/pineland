from __future__ import annotations

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import ArmedFormation, LANGUAGES, Organization, OrganizationKind
from pineland_sim.events import ScheduledEvent
from pineland_sim.networks import edge_between, generate_social_network
from pineland_sim.organization_ecology import (
    _recruitment_intensity,
    _recruitment_language_access_factor,
    _set_armed_membership,
    franchise_constituency_congruence,
    franchise_language_congruence,
    organization_language_profile,
    organization_local_rootedness,
    recruit_and_retain,
)
from pineland_sim.processes import ProcessEngine


class ConstantRng:
    def __init__(self, value: float):
        self.value = value

    def random(self):
        return self.value


def _language_vector(language: str) -> dict[str, float]:
    return {item: 1.0 if item == language else 0.0 for item in LANGUAGES}


def _organization(organization_id: str = "outside-franchise") -> Organization:
    return Organization(
        organization_id=organization_id,
        name=organization_id,
        kind=OrganizationKind.INSURGENT,
        resources=10_000.0,
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


def _outside_fixture(channel: str, compatible: bool, seed: int = 7311):
    world = generate_pineland(SimulationConfig(
        agent_count=320,
        locality_count=24,
        horizon_days=2,
        seed=seed,
        include_insurgency=False,
    ))
    target_id = next(
        locality_id for locality_id in world.localities
        if sum(person.residence_locality_id == locality_id
               for person in world.persons.values()) >= 2
    )
    target_district = world.localities[target_id].district_id
    residents = [
        person for person in world.persons.values()
        if person.residence_locality_id == target_id
    ]
    candidate = residents[0]
    member = next(
        person for person in world.persons.values()
        if world.localities[person.home_locality_id].district_id != target_district
        and person.person_id != candidate.person_id
    )

    organization = _organization()
    world.organizations[organization.organization_id] = organization
    candidate.languages = _language_vector("FS")
    candidate.identities["local"] = 0.0
    candidate.identities["district"] = 0.0
    candidate.identities["federal"] = .5
    candidate.grievance = .5
    candidate.fear = 0.0
    candidate.political_access = 0.0
    candidate.social_exposure = {}
    candidate.organization_id = None
    candidate.armed_fraction = 0.0

    member.languages = _language_vector("FS" if compatible else "AR")
    if channel == "member":
        member.residence_locality_id = target_id
    elif channel != "formation":
        raise ValueError(channel)
    _set_armed_membership(member, organization, 1.0)
    organization.member_ids.add(member.person_id)

    if channel == "formation":
        minimum = world.config.organization_ecology.minimum_formation_personnel
        world.formations["OUTSIDE-F"] = ArmedFormation(
            formation_id="OUTSIDE-F",
            organization_id=organization.organization_id,
            locality_id=target_id,
            personnel=minimum,
            quality=.5,
            cohesion=.6,
            readiness=.6,
            sustainment=.6,
            information=.5,
            mobility=.5,
            command=.5,
            embeddedness=.2,
        )

    world.config.organization_ecology.recruitment_subcohorts = 1
    world.config.organization_ecology.fighter_conversion_fraction = 0.0
    world.config.recruitment_rate = 2.0
    world.config.membership_exit_rate = 0.0
    return world, organization, candidate, member, target_id


def test_language_access_factor_reuses_existing_social_communication_equation():
    world, organization, candidate, _member, _target = _outside_fixture(
        "formation", compatible=True
    )
    compatible_profile = organization_language_profile(world, organization)
    assert franchise_language_congruence(candidate, compatible_profile) == 1.0
    assert _recruitment_language_access_factor(candidate, compatible_profile) == 1.0

    alien_profile = _language_vector("AR")
    assert franchise_language_congruence(candidate, alien_profile) == 0.0
    assert _recruitment_language_access_factor(candidate, alien_profile) == .35

    half_profile = {language: 0.0 for language in LANGUAGES}
    half_profile["FS"] = .5
    assert franchise_language_congruence(candidate, half_profile) == .5
    assert _recruitment_language_access_factor(candidate, half_profile) == .675


def test_social_edge_path_already_attenuates_linguistically_alien_franchise_signal():
    def exposure(compatible: bool) -> tuple[float, float]:
        world = generate_pineland(SimulationConfig(
            agent_count=320,
            locality_count=24,
            horizon_days=2,
            seed=73115,
            include_insurgency=False,
        ))
        target = next(
            person for person in world.persons.values()
            if len(world.social_neighbors[person.person_id]) >= 2
        )
        source_id = world.social_neighbors[target.person_id][0]
        source = world.persons[source_id]
        for person in world.persons.values():
            person.organization_id = None
            person.armed_fraction = 0.0
            person.public_behavior = "neutral"
            person.insurgent_affinity.clear()
        target.languages = _language_vector("FS")
        source.languages = _language_vector("FS" if compatible else "AR")
        generate_social_network(world)
        assert source.person_id in world.social_neighbors[target.person_id]

        organization = _organization()
        world.organizations[organization.organization_id] = organization
        _set_armed_membership(source, organization, 1.0)
        organization.member_ids.add(source.person_id)
        source.public_behavior = "armed_participation"
        world.config.social_network.behavior_update_rate = 0.0
        ProcessEngine(world, ConstantRng(.5)).on_social_influence(
            "SYN-LANGUAGE-SOCIAL",
            ScheduledEvent(
                1.0, 0, 1, "social_influence",
                {"elapsed_days": 1.0, "interval": 1.0},
            ),
        )
        edge = edge_between(world, target.person_id, source.person_id)
        return target.social_exposure[organization.organization_id], edge.weight

    compatible_exposure, compatible_weight = exposure(True)
    alien_exposure, alien_weight = exposure(False)
    assert compatible_weight > alien_weight
    assert compatible_exposure > alien_exposure


def test_formation_access_distinguishes_compatible_from_linguistically_alien_outside_franchise():
    compatible, _org_c, candidate_c, _member_c, _target_c = _outside_fixture(
        "formation", compatible=True, seed=7312
    )
    alien, _org_a, candidate_a, _member_a, _target_a = _outside_fixture(
        "formation", compatible=False, seed=7312
    )

    recruit_and_retain(compatible, 1.0, ConstantRng(.4), interval_days=1.0)
    recruit_and_retain(alien, 1.0, ConstantRng(.4), interval_days=1.0)

    assert candidate_c.organization_id == "outside-franchise"
    assert candidate_c.armed_fraction == 1.0
    assert candidate_a.organization_id is None
    assert candidate_a.armed_fraction == 0.0


def test_local_member_access_distinguishes_language_without_making_outsider_indigenous():
    compatible, org_c, candidate_c, _member_c, target_c = _outside_fixture(
        "member", compatible=True, seed=7313
    )
    alien, org_a, candidate_a, _member_a, target_a = _outside_fixture(
        "member", compatible=False, seed=7313
    )

    root_c = organization_local_rootedness(compatible, org_c, target_c)
    root_a = organization_local_rootedness(alien, org_a, target_a)
    assert root_c["home_locality_share"] == root_a["home_locality_share"] == 0.0
    assert root_c["home_district_share"] == root_a["home_district_share"] == 0.0
    assert franchise_constituency_congruence(
        compatible, candidate_c, org_c, target_c, root_c
    ) == 0.0
    assert franchise_constituency_congruence(
        alien, candidate_a, org_a, target_a, root_a
    ) == 0.0

    recruit_and_retain(compatible, 1.0, ConstantRng(.4), interval_days=1.0)
    recruit_and_retain(alien, 1.0, ConstantRng(.4), interval_days=1.0)
    assert candidate_c.organization_id == "outside-franchise"
    assert candidate_a.organization_id is None


def test_linguistic_localization_can_change_without_origin_rootedness_changing():
    world, organization, candidate, first_member, target_id = _outside_fixture(
        "member", compatible=False, seed=7314
    )
    target_district = world.localities[target_id].district_id
    second_member = next(
        person for person in world.persons.values()
        if person.person_id not in {candidate.person_id, first_member.person_id}
        and world.localities[person.home_locality_id].district_id != target_district
    )
    second_member.residence_locality_id = target_id
    second_member.languages = _language_vector("FS")
    second_member.weight = first_member.weight

    before_root = organization_local_rootedness(world, organization, target_id)
    before_profile = organization_language_profile(world, organization, target_id)
    before_language = franchise_language_congruence(candidate, before_profile)

    _set_armed_membership(second_member, organization, 1.0)
    organization.member_ids.add(second_member.person_id)
    after_root = organization_local_rootedness(world, organization, target_id)
    after_profile = organization_language_profile(world, organization, target_id)
    after_language = franchise_language_congruence(candidate, after_profile)

    assert before_root["home_locality_share"] == after_root["home_locality_share"] == 0.0
    assert before_root["home_district_share"] == after_root["home_district_share"] == 0.0
    assert before_language == 0.0
    assert after_language == .5


def test_zero_local_identity_keeps_rootedness_out_of_recruitment_utility():
    world, organization, candidate, _member, target_id = _outside_fixture(
        "member", compatible=True, seed=7315
    )
    outsider_root = organization_local_rootedness(world, organization, target_id)
    counterfactual_local_root = {
        "represented_local_membership": outsider_root["represented_local_membership"],
        "home_locality_share": 1.0,
        "home_district_share": 1.0,
    }
    outsider = _recruitment_intensity(
        world, candidate, organization, 0.0, outsider_root
    )[0]
    local = _recruitment_intensity(
        world, candidate, organization, 0.0, counterfactual_local_root
    )[0]
    assert franchise_constituency_congruence(
        world, candidate, organization, target_id, outsider_root
    ) == 0.0
    assert franchise_constituency_congruence(
        world, candidate, organization, target_id, counterfactual_local_root
    ) == 0.0
    assert outsider == local
