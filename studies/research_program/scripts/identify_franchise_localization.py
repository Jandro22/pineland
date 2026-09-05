"""Synthetic identification of insurgent franchise localization and competition.

The study is deliberately case-free.  It asks whether the live model recovers
four general-theory signatures:

1. locally rooted franchises are more recruitable among strongly local-identified
   civilians than otherwise identical externally implanted franchises;
2. that difference vanishes when local/district identity salience is zero;
3. recruiting indigenous members endogenously localizes an outside franchise;
4. social influence and recruitment remain organization-specific when multiple
   insurgent organizations coexist.

No Afghanistan/Nepal outcome or empirical target is read here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "studies" / "research_program" / "franchise_localization.json"

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import Organization, OrganizationKind  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.organization_ecology import (  # noqa: E402
    _recruitment_intensity,
    _set_armed_membership,
    organization_local_rootedness,
    recruit_and_retain,
)
from pineland_sim.processes import ProcessEngine  # noqa: E402


class ZeroRng:
    def random(self) -> float:
        return 0.0


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


def _base_world(seed: int):
    world = generate_pineland(SimulationConfig(
        agent_count=360,
        locality_count=24,
        horizon_days=2,
        seed=seed,
        include_insurgency=False,
    ))
    local = _organization("franchise-local")
    outsider = _organization("franchise-outsider")
    world.organizations[local.organization_id] = local
    world.organizations[outsider.organization_id] = outsider
    locality_id = next(
        locality_id for locality_id in world.localities
        if sum(p.residence_locality_id == locality_id for p in world.persons.values()) >= 5
    )
    district_id = world.localities[locality_id].district_id
    residents = [
        p for p in world.persons.values() if p.residence_locality_id == locality_id
    ]
    candidate = residents[0]
    local_members = residents[1:4]
    outsider_members = [
        p for p in world.persons.values()
        if world.localities[p.home_locality_id].district_id != district_id
        and p.person_id not in {item.person_id for item in residents}
    ][:3]
    if len(outsider_members) < 3:
        raise RuntimeError("synthetic world lacks out-of-district comparison members")
    for member in local_members:
        _set_armed_membership(member, local, 1.0)
        local.member_ids.add(member.person_id)
    for member in outsider_members:
        member.residence_locality_id = locality_id
        _set_armed_membership(member, outsider, 1.0)
        outsider.member_ids.add(member.person_id)
    candidate.grievance = 1.0
    candidate.fear = 0.0
    candidate.political_access = 0.0
    candidate.identities["federal"] = .5
    return world, local, outsider, candidate, local_members, outsider_members, locality_id


def rootedness_contrast(seed: int) -> dict[str, Any]:
    world, local, outsider, candidate, *_rest, locality_id = _base_world(seed)
    candidate.identities["local"] = 1.0
    candidate.identities["district"] = 1.0
    local_root = organization_local_rootedness(world, local, locality_id)
    outsider_root = organization_local_rootedness(world, outsider, locality_id)
    local_high = _recruitment_intensity(world, candidate, local, .5, local_root)[0]
    outsider_high = _recruitment_intensity(world, candidate, outsider, .5, outsider_root)[0]

    candidate.identities["local"] = 0.0
    candidate.identities["district"] = 0.0
    local_zero = _recruitment_intensity(world, candidate, local, .5, local_root)[0]
    outsider_zero = _recruitment_intensity(world, candidate, outsider, .5, outsider_root)[0]
    return {
        "local_rootedness": local_root,
        "outsider_rootedness": outsider_root,
        "high_local_identity": {
            "local_franchise_intensity": local_high,
            "outsider_franchise_intensity": outsider_high,
            "difference": local_high - outsider_high,
        },
        "zero_local_identity": {
            "local_franchise_intensity": local_zero,
            "outsider_franchise_intensity": outsider_zero,
            "difference": local_zero - outsider_zero,
        },
    }


def localization_curve(seed: int) -> list[dict[str, float]]:
    world, _local, outsider, candidate, local_members, outsider_members, locality_id = _base_world(seed)
    candidate.identities["local"] = 1.0
    candidate.identities["district"] = 1.0
    # Start from a completely externally rooted local cell, then replace equal
    # represented slices with indigenous recruits while holding cell size,
    # ideology, social capital, candidate state, and exposure fixed.
    rows = []
    for indigenous_count in range(4):
        trial = deepcopy(world)
        trial_outsider = trial.organizations[outsider.organization_id]
        trial_outsider.member_ids.clear()
        selected_outside = outsider_members[:3 - indigenous_count]
        selected_local = local_members[:indigenous_count]
        for template in selected_outside + selected_local:
            person = trial.persons[template.person_id]
            person.organization_id = None
            person.armed_fraction = 0.0
            _set_armed_membership(person, trial_outsider, 1.0)
            trial_outsider.member_ids.add(person.person_id)
        trial_candidate = trial.persons[candidate.person_id]
        root = organization_local_rootedness(trial, trial_outsider, locality_id)
        intensity = _recruitment_intensity(
            trial, trial_candidate, trial_outsider, .5, root
        )[0]
        rows.append({
            "indigenous_member_share": indigenous_count / 3.0,
            "home_locality_share": root["home_locality_share"],
            "home_district_share": root["home_district_share"],
            "recruitment_intensity": intensity,
        })
    return rows


def franchise_signal_specificity(seed: int) -> dict[str, float]:
    world, local, outsider, *_ = _base_world(seed)
    for person in world.persons.values():
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
    local.member_ids.clear()
    outsider.member_ids.clear()
    edge = next(iter(world.social_edges.values()))
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    _set_armed_membership(source, local, 1.0)
    local.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    world.config.social_network.behavior_update_rate = 0.0
    ProcessEngine(world, random.Random(seed + 77)).on_social_influence(
        "SYN-FRANCHISE-SIGNAL",
        ScheduledEvent(1.0, 0, 1, "social_influence", {"interval": 1.0, "elapsed_days": 1.0}),
    )
    return {
        "generic_insurgent_exposure": target.social_exposure.get("insurgent", 0.0),
        "source_franchise_exposure": target.social_exposure.get(local.organization_id, 0.0),
        "rival_franchise_exposure": target.social_exposure.get(outsider.organization_id, 0.0),
    }


def competing_recruitment_order_invariance(seed: int) -> dict[str, Any]:
    def run(reverse: bool):
        world = generate_pineland(SimulationConfig(
            agent_count=240, locality_count=24, horizon_days=1, seed=seed,
            include_insurgency=False,
        ))
        first = _organization("franchise-a")
        second = _organization("franchise-b")
        if reverse:
            world.organizations[second.organization_id] = second
            world.organizations[first.organization_id] = first
        else:
            world.organizations[first.organization_id] = first
            world.organizations[second.organization_id] = second
        candidate = next(iter(world.persons.values()))
        candidate.social_exposure = {
            "insurgent": 1.0,
            first.organization_id: 1.0,
            second.organization_id: 1.0,
        }
        candidate.identities["local"] = 0.0
        candidate.identities["district"] = 0.0
        world.config.organization_ecology.local_rootedness_weight = 0.0
        world.config.organization_ecology.fighter_conversion_fraction = 0.0
        world.config.organization_ecology.recruitment_subcohorts = 1
        world.config.recruitment_rate = 100.0
        world.config.membership_exit_rate = 0.0
        result = recruit_and_retain(world, 1.0, ZeroRng(), interval_days=1.0)
        return candidate.organization_id, result["contested_recruitment_candidates"]

    normal, normal_contested = run(False)
    reverse, reverse_contested = run(True)
    return {
        "normal_insertion_winner": normal,
        "reverse_insertion_winner": reverse,
        "normal_contested_candidates": normal_contested,
        "reverse_contested_candidates": reverse_contested,
        "invariant": normal == reverse,
    }


def run_study(seed: int = 20260905) -> dict[str, Any]:
    contrast = rootedness_contrast(seed)
    curve = localization_curve(seed + 1)
    signal = franchise_signal_specificity(seed + 2)
    order = competing_recruitment_order_invariance(seed + 3)
    monotone_curve = all(
        right["recruitment_intensity"] >= left["recruitment_intensity"] - 1e-12
        for left, right in zip(curve, curve[1:])
    )
    gates = {
        "rooted_franchise_advantage_when_local_identity_salient":
            contrast["high_local_identity"]["difference"] > 0,
        "rootedness_effect_vanishes_without_local_identity_salience":
            abs(contrast["zero_local_identity"]["difference"]) <= 1e-12,
        "localization_curve_is_monotone": monotone_curve,
        "social_signal_is_franchise_specific":
            signal["source_franchise_exposure"] > 0 and
            signal["rival_franchise_exposure"] == 0,
        "competing_recruitment_is_insertion_order_invariant": order["invariant"],
    }
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_franchise_localization_identification",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "seed": seed,
        "rootedness_contrast": contrast,
        "localization_curve": curve,
        "franchise_signal_specificity": signal,
        "competing_recruitment_order_invariance": order,
        "gates": gates,
        "passed": all(gates.values()),
        "interpretation": (
            "The live model now represents constituency-franchise congruence as an "
            "endogenous locality-specific property of actual membership origins, not "
            "as an ethnicity rule. Outside organizations can localize by recruiting "
            "indigenous members, and multiple insurgent organizations retain distinct "
            "social signals and compete for unaffiliated recruits."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = run_study(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "gates": report["gates"]}, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
