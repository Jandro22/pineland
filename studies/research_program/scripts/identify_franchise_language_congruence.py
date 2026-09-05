"""Synthetic identification battery for franchise language congruence.

This script isolates language from origin/rootedness in recruitment access.
It does not read empirical case inputs or historical outcomes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import ArmedFormation, LANGUAGES, Organization, OrganizationKind  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.networks import edge_between, generate_social_network  # noqa: E402
from pineland_sim.organization_ecology import (  # noqa: E402
    _interval_hazard_probability,
    _recruitment_intensity,
    _recruitment_language_access_factor,
    _set_armed_membership,
    franchise_constituency_congruence,
    franchise_language_congruence,
    organization_language_profile,
    organization_local_rootedness,
    recruit_and_retain,
)
from pineland_sim.processes import ProcessEngine  # noqa: E402


OUT = ROOT / "studies" / "research_program" / "franchise_language_congruence.json"
EPS = 1e-12


class ConstantRng:
    def __init__(self, value: float):
        self.value = value

    def random(self):
        return self.value


def language_vector(language: str) -> dict[str, float]:
    return {item: 1.0 if item == language else 0.0 for item in LANGUAGES}


def organization() -> Organization:
    return Organization(
        organization_id="outside-franchise",
        name="outside-franchise",
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


def build_fixture(channel: str, compatible: bool, seed: int):
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
    candidate = next(
        person for person in world.persons.values()
        if person.residence_locality_id == target_id
    )
    member = next(
        person for person in world.persons.values()
        if person.person_id != candidate.person_id
        and world.localities[person.home_locality_id].district_id != target_district
    )
    actor = organization()
    world.organizations[actor.organization_id] = actor

    candidate.languages = language_vector("FS")
    candidate.identities["local"] = 0.0
    candidate.identities["district"] = 0.0
    candidate.identities["federal"] = .5
    candidate.grievance = .5
    candidate.fear = 0.0
    candidate.political_access = 0.0
    candidate.social_exposure = {}
    candidate.organization_id = None
    candidate.armed_fraction = 0.0

    member.languages = language_vector("FS" if compatible else "AR")
    if channel == "member":
        member.residence_locality_id = target_id
    elif channel != "formation":
        raise ValueError(channel)
    _set_armed_membership(member, actor, 1.0)
    actor.member_ids.add(member.person_id)

    if channel == "formation":
        world.formations["OUTSIDE-F"] = ArmedFormation(
            formation_id="OUTSIDE-F",
            organization_id=actor.organization_id,
            locality_id=target_id,
            personnel=world.config.organization_ecology.minimum_formation_personnel,
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
    return world, actor, candidate, member, target_id


def cell(channel: str, compatible: bool, seed: int) -> dict:
    world, actor, candidate, _member, target_id = build_fixture(channel, compatible, seed)
    rootedness = organization_local_rootedness(world, actor, target_id)
    global_profile = organization_language_profile(world, actor)
    local_profile = organization_language_profile(world, actor, target_id)
    formation_access = (
        1.0 if channel == "formation" else 0.0
    )
    member_access = (
        min(
            1.0,
            rootedness["represented_local_membership"] /
            world.config.organization_ecology.minimum_proto_represented_population,
        )
        if channel == "member" else 0.0
    )
    formation_factor = _recruitment_language_access_factor(candidate, global_profile)
    member_factor = _recruitment_language_access_factor(candidate, local_profile)
    access_strength = max(
        formation_access * formation_factor,
        member_access * member_factor,
    )
    intensity, ideological_compatibility, root_congruence = _recruitment_intensity(
        world, candidate, actor, 0.0, rootedness
    )
    effective_intensity = intensity * access_strength
    probability = _interval_hazard_probability(
        world.config.recruitment_rate, effective_intensity, 1.0
    )
    recruit_and_retain(world, 1.0, ConstantRng(.4), interval_days=1.0)
    return {
        "channel": channel,
        "language_condition": "compatible" if compatible else "alien",
        "outside_origin": rootedness["home_locality_share"] == 0.0
        and rootedness["home_district_share"] == 0.0,
        "local_identity_salience": {
            "local": 0.0,
            "district": 0.0,
        },
        "rootedness": rootedness,
        "root_congruence": root_congruence,
        "global_language_profile": global_profile,
        "local_member_language_profile": local_profile,
        "language_congruence_global": franchise_language_congruence(
            candidate, global_profile
        ),
        "language_congruence_local_member": franchise_language_congruence(
            candidate, local_profile
        ),
        "formation_access": formation_access,
        "member_access": member_access,
        "formation_language_factor": formation_factor,
        "member_language_factor": member_factor,
        "access_strength": access_strength,
        "ideological_compatibility": ideological_compatibility,
        "recruitment_intensity_before_access": intensity,
        "effective_recruitment_intensity": effective_intensity,
        "one_day_recruitment_probability": probability,
        "constant_draw": .4,
        "candidate_recruited": candidate.organization_id == actor.organization_id,
    }


def language_localization_probe(seed: int) -> dict:
    world, actor, candidate, first_member, target_id = build_fixture(
        "member", compatible=False, seed=seed
    )
    target_district = world.localities[target_id].district_id
    second_member = next(
        person for person in world.persons.values()
        if person.person_id not in {candidate.person_id, first_member.person_id}
        and world.localities[person.home_locality_id].district_id != target_district
    )
    second_member.residence_locality_id = target_id
    second_member.languages = language_vector("FS")
    second_member.weight = first_member.weight

    before_root = organization_local_rootedness(world, actor, target_id)
    before_profile = organization_language_profile(world, actor, target_id)
    before_language = franchise_language_congruence(candidate, before_profile)
    _set_armed_membership(second_member, actor, 1.0)
    actor.member_ids.add(second_member.person_id)
    after_root = organization_local_rootedness(world, actor, target_id)
    after_profile = organization_language_profile(world, actor, target_id)
    after_language = franchise_language_congruence(candidate, after_profile)
    return {
        "all_members_remain_outside_origin": (
            before_root["home_locality_share"] == 0.0
            and before_root["home_district_share"] == 0.0
            and after_root["home_locality_share"] == 0.0
            and after_root["home_district_share"] == 0.0
        ),
        "before_rootedness": before_root,
        "after_rootedness": after_root,
        "before_local_language_profile": before_profile,
        "after_local_language_profile": after_profile,
        "before_language_congruence": before_language,
        "after_language_congruence": after_language,
    }


def zero_identity_rootedness_probe(seed: int) -> dict:
    world, actor, candidate, _member, target_id = build_fixture(
        "member", compatible=True, seed=seed
    )
    outsider_root = organization_local_rootedness(world, actor, target_id)
    local_root = {
        "represented_local_membership": outsider_root["represented_local_membership"],
        "home_locality_share": 1.0,
        "home_district_share": 1.0,
    }
    outsider = _recruitment_intensity(world, candidate, actor, 0.0, outsider_root)
    local = _recruitment_intensity(world, candidate, actor, 0.0, local_root)
    return {
        "outside_rootedness_intensity": outsider[0],
        "counterfactual_local_rootedness_intensity": local[0],
        "absolute_difference": abs(outsider[0] - local[0]),
        "outside_root_congruence": franchise_constituency_congruence(
            world, candidate, actor, target_id, outsider_root
        ),
        "local_root_congruence": franchise_constituency_congruence(
            world, candidate, actor, target_id, local_root
        ),
    }


def social_edge_probe(seed: int) -> dict:
    def run(compatible: bool) -> dict:
        world = generate_pineland(SimulationConfig(
            agent_count=320,
            locality_count=24,
            horizon_days=2,
            seed=seed,
            include_insurgency=False,
        ))
        target = next(
            person for person in world.persons.values()
            if len(world.social_neighbors[person.person_id]) >= 2
        )
        source = world.persons[world.social_neighbors[target.person_id][0]]
        for person in world.persons.values():
            person.organization_id = None
            person.armed_fraction = 0.0
            person.public_behavior = "neutral"
            person.insurgent_affinity.clear()
        target.languages = language_vector("FS")
        source.languages = language_vector("FS" if compatible else "AR")
        generate_social_network(world)
        actor = organization()
        world.organizations[actor.organization_id] = actor
        _set_armed_membership(source, actor, 1.0)
        actor.member_ids.add(source.person_id)
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
        return {
            "language_condition": "compatible" if compatible else "alien",
            "source_edge_weight": edge.weight,
            "franchise_social_exposure": target.social_exposure[actor.organization_id],
        }

    return {
        "compatible": run(True),
        "alien": run(False),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()

    cells = [
        cell("formation", True, 2026090511),
        cell("formation", False, 2026090511),
        cell("member", True, 2026090512),
        cell("member", False, 2026090512),
    ]
    by_key = {
        (row["channel"], row["language_condition"]): row
        for row in cells
    }
    localization = language_localization_probe(2026090513)
    zero_identity = zero_identity_rootedness_probe(2026090514)
    social = social_edge_probe(2026090515)

    rejection_tests = {
        "formation_access_language_separation": (
            by_key[("formation", "compatible")]["access_strength"]
            > by_key[("formation", "alien")]["access_strength"] + EPS
        ),
        "member_access_language_separation": (
            by_key[("member", "compatible")]["access_strength"]
            > by_key[("member", "alien")]["access_strength"] + EPS
        ),
        "formation_recruitment_draw_separation": (
            by_key[("formation", "compatible")]["candidate_recruited"]
            and not by_key[("formation", "alien")]["candidate_recruited"]
        ),
        "member_recruitment_draw_separation": (
            by_key[("member", "compatible")]["candidate_recruited"]
            and not by_key[("member", "alien")]["candidate_recruited"]
        ),
        "outside_origin_held_fixed": all(row["outside_origin"] for row in cells),
        "zero_identity_rootedness_null_preserved": (
            zero_identity["absolute_difference"] <= EPS
            and zero_identity["outside_root_congruence"] == 0.0
            and zero_identity["local_root_congruence"] == 0.0
        ),
        "language_localization_without_origin_localization": (
            localization["all_members_remain_outside_origin"]
            and localization["after_language_congruence"]
            > localization["before_language_congruence"] + EPS
        ),
        "exact_reused_communication_prior": (
            abs(by_key[("formation", "compatible")]["formation_language_factor"] - 1.0) <= EPS
            and abs(by_key[("formation", "alien")]["formation_language_factor"] - .35) <= EPS
            and abs(by_key[("member", "compatible")]["member_language_factor"] - 1.0) <= EPS
            and abs(by_key[("member", "alien")]["member_language_factor"] - .35) <= EPS
        ),
        "social_edge_language_mechanism_remains_active": (
            social["compatible"]["source_edge_weight"]
            > social["alien"]["source_edge_weight"] + EPS
            and social["compatible"]["franchise_social_exposure"]
            > social["alien"]["franchise_social_exposure"] + EPS
        ),
    }

    payload = {
        "study": "synthetic franchise language congruence identification",
        "empirical_outcomes_used": False,
        "equations": {
            "language_congruence": "L_io = max_r min(l_ir, lbar_or)",
            "communication_factor": "g(L_io) = 0.35 + 0.65 L_io",
            "access": (
                "A_io = max(E_io, F_io*g(L_io^org), "
                "M_io*g(L_io^local-members))"
            ),
            "recruitment_intensity": (
                "I_io = logistic(1.5*grievance + E_io + ideological_compatibility "
                "+ social_capital - fear - 2.6 - peaceful_channel_penalty "
                "+ local_rootedness_weight*root_congruence)"
            ),
            "interval_probability": "p_io = 1 - exp(-recruitment_rate*I_io*A_io*dt)",
        },
        "identification_logic": {
            "formation_channel": (
                "Hold outside origin, ideology, grievance, fear, local identity, "
                "formation strength, and RNG draw fixed; change only armed-member language."
            ),
            "member_channel": (
                "Hold outside origin and represented local armed membership fixed; "
                "change only the local member working language."
            ),
            "rootedness_placebo": (
                "Set local and district identity salience to zero and replace outsider "
                "rootedness with a fully local counterfactual; recruitment utility must not move."
            ),
            "localization_probe": (
                "Add an outside-origin local-language member; language congruence may rise "
                "while origin rootedness remains exactly zero."
            ),
            "social_edge_control": (
                "Hold graph-generation seed and source behavior fixed while changing only "
                "source/target language compatibility; the pre-existing social-edge path "
                "must already attenuate alien-franchise exposure."
            ),
        },
        "cells": cells,
        "social_edge_probe": social,
        "language_localization_probe": localization,
        "zero_identity_rootedness_probe": zero_identity,
        "rejection_tests": rejection_tests,
        "all_rejection_tests_pass": all(rejection_tests.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "all_rejection_tests_pass": payload["all_rejection_tests_pass"],
        "rejection_tests": rejection_tests,
    }, indent=2))
    if not payload["all_rejection_tests_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
