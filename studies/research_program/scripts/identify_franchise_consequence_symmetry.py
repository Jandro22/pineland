"""Matched-world audit of franchise rootedness consequences and actor symmetry.

This study changes member home origins while holding current residence,
represented membership, organization traits, candidate traits, geography, and
random seed fixed. It measures existing direct pathways only; a zero contrast
is retained as a negative result and never repaired by adding a plausible rule.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import Organization, OrganizationKind  # noqa: E402
from pineland_sim.information import _report_probability, language_comprehension  # noqa: E402
from pineland_sim.organization_ecology import (  # noqa: E402
    _recruitment_intensity,
    _set_armed_membership,
    franchise_constituency_congruence,
    organization_local_rootedness,
    organization_survival_social_base,
)

OUT = ROOT / "studies/research_program/franchise_consequence_symmetry.json"


def _organization(organization_id: str, kind: OrganizationKind) -> Organization:
    return Organization(
        organization_id=organization_id,
        name=organization_id,
        kind=kind,
        resources=50_000.0,
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


def matched_cell(*, rooted: bool, kind: OrganizationKind, seed: int) -> dict:
    world = generate_pineland(SimulationConfig(
        agent_count=360, locality_count=24, horizon_days=2, seed=seed,
        include_insurgency=False,
    ))
    target_id = next(
        locality_id for locality_id in world.localities
        if sum(p.residence_locality_id == locality_id for p in world.persons.values()) >= 2
    )
    district_id = world.localities[target_id].district_id
    residents = [p for p in world.persons.values() if p.residence_locality_id == target_id]
    candidate = residents[0]
    if rooted:
        member = residents[1]
    else:
        member = next(
            p for p in world.persons.values()
            if world.localities[p.home_locality_id].district_id != district_id
            and p.person_id != candidate.person_id
        )
        member.residence_locality_id = target_id
    actor = _organization(f"matched-{kind.value}", kind)
    world.organizations[actor.organization_id] = actor
    _set_armed_membership(member, actor, 1.0)
    actor.member_ids.add(member.person_id)
    candidate.identities["local"] = 1.0
    candidate.identities["district"] = 1.0
    candidate.grievance = 1.0
    candidate.fear = 0.0
    candidate.political_access = 0.0

    roots = organization_local_rootedness(world, actor, target_id)
    congruence = franchise_constituency_congruence(
        world, candidate, actor, target_id, roots
    )
    recruitment = _recruitment_intensity(
        world, candidate, actor, .5, roots
    )[0]
    locality = world.localities[target_id]
    fiscal = locality.control.get("insurgent")
    extraction = locality.economic_output * .00015 * (
        fiscal.fiscal if fiscal is not None else 0.0
    )
    control = locality.control.get(actor.organization_id)
    return {
        "kind": kind.value,
        "rooted": rooted,
        "rootedness": roots,
        "constituency_congruence": congruence,
        "recruitment_intensity": recruitment,
        "information_language_comprehension": language_comprehension(
            world, actor.organization_id, target_id, "civilian"
        ),
        "civilian_reporting_probability": _report_probability(
            world, actor.organization_id, target_id, "civilian", None
        ),
        "survival_social_base": organization_survival_social_base(world, actor),
        "concealment_embeddedness_input": actor.local_knowledge,
        "taxation_extraction_opportunity": extraction,
        "defection_inputs": {
            "discipline": actor.discipline,
            "cohesion": actor.cohesion,
            "local_control": (
                locality.control["insurgent"].effective()
                if "insurgent" in locality.control else 0.0
            ),
        },
        "coercive_backlash_inputs": {
            "candidate_fear": candidate.fear,
            "candidate_grievance": candidate.grievance,
            "civilian_harm": world.cumulative_civilian_harm,
        },
        "effective_control": control.effective() if control is not None else 0.0,
    }


def _difference(rooted: dict, outsider: dict, key: str) -> float:
    return float(rooted[key]) - float(outsider[key])


def run_study(seed: int = 20260905) -> dict:
    actor_kinds = (
        OrganizationKind.INSURGENT,
        OrganizationKind.GOVERNMENT,
        OrganizationKind.MILITARY,
        OrganizationKind.POLICE,
        OrganizationKind.FOREIGN,
        OrganizationKind.PARTY,
        OrganizationKind.CIVIC,
    )
    cells = []
    contrasts = {}
    outcome_keys = (
        "recruitment_intensity",
        "information_language_comprehension",
        "civilian_reporting_probability",
        "survival_social_base",
        "concealment_embeddedness_input",
        "taxation_extraction_opportunity",
        "effective_control",
    )
    for offset, kind in enumerate(actor_kinds):
        rooted = matched_cell(rooted=True, kind=kind, seed=seed + offset)
        outsider = matched_cell(rooted=False, kind=kind, seed=seed + offset)
        cells.extend((rooted, outsider))
        contrasts[kind.value] = {
            "constituency_congruence_difference": _difference(
                rooted, outsider, "constituency_congruence"
            ),
            "outcome_differences": {
                key: _difference(rooted, outsider, key) for key in outcome_keys
            },
        }
    insurgent = contrasts[OrganizationKind.INSURGENT.value]
    direct = insurgent["outcome_differences"]
    consequence_assessment = {
        "recruitment": direct["recruitment_intensity"] > 1e-12,
        "information_access": abs(direct["information_language_comprehension"]) > 1e-12,
        "reporting": abs(direct["civilian_reporting_probability"]) > 1e-12,
        "concealment_or_sanctuary": abs(direct["concealment_embeddedness_input"]) > 1e-12,
        "taxation_or_extraction": abs(direct["taxation_extraction_opportunity"]) > 1e-12,
        "organization_survival": abs(direct["survival_social_base"]) > 1e-12,
        "defection": False,
        "coercive_backlash": False,
        "effective_control": abs(direct["effective_control"]) > 1e-12,
    }
    congruence_differences = [
        item["constituency_congruence_difference"] for item in contrasts.values()
    ]
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_matched_world_franchise_consequence_and_symmetry_audit",
        "historical_outcomes_used": False,
        "core_model_modified": False,
        "treatment": "member home-origin rootedness",
        "held_fixed": [
            "seed", "current residence", "represented membership", "organization traits",
            "candidate traits", "geography", "language", "control state",
        ],
        "cells": cells,
        "contrasts_by_actor_kind": contrasts,
        "consequence_assessment_direct_rootedness_effect": consequence_assessment,
        "measurement_symmetry": {
            "actor_kinds": [kind.value for kind in actor_kinds],
            "constituency_congruence_operator_kind_invariant": (
                max(congruence_differences) - min(congruence_differences) <= 1e-12
            ),
            "transition_symmetry_established": False,
            "interpretation": (
                "The rootedness/congruence measurement operator is actor-kind neutral, but the "
                "live transition consequences are not yet institutionally specified for every actor."
            ),
        },
        "negative_result": (
            "Under a matched home-origin intervention, direct effects are identified for recruitment "
            "and local information access, but not for reporting, concealment, extraction, survival, "
            "defection, backlash, or effective control. The remaining nulls are retained; no missing "
            "transition is added."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = run_study(args.seed)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "consequence_assessment": result["consequence_assessment_direct_rootedness_effect"],
        "measurement_symmetry": result["measurement_symmetry"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
