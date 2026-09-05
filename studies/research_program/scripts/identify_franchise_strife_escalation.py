"""Synthetic, outcome-independent study of insurgent franchise escalation.

Candidate theory: relational bargaining under constituency competition.
The live model already represents contact, ideology, genealogy, constituency
fragmentation, cohesion, resources, and leaders. These variables describe
opportunity, stakes, capacity, and bargaining pressure, but they do not encode
a persistent dyadic history that can distinguish cooperation from hostility.
This module therefore diagnoses, rather than adds, escalation behavior.

All regime scores are dimensionless synthetic contrasts, not probabilities or
calibrated equations.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.organization_ecology import (
    locality_franchise_support_profile,
    organization_contact_overlap,
)

DEFAULT_OUTPUT = ROOT / "studies" / "research_program" / "franchise_strife_escalation.json"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class DyadState:
    contact_overlap: float
    ideological_distance: float
    genealogical_proximity: float
    support_fragmentation: float
    constituency_contest: float
    mean_cohesion: float
    resource_stress: float
    leader_hardline: float
    leader_bargaining_skill: float


def ideological_distance(first, second) -> float:
    keys = set(first.ideology) | set(second.ideology)
    if not keys:
        return 0.0
    return round(_clamp(sum(
        abs(first.ideology.get(key, .5) - second.ideology.get(key, .5))
        for key in keys
    ) / len(keys)), 12)


def genealogical_proximity(world, first_id: str, second_id: str) -> float:
    """Conservative diagnostic kinship from existing organization parent_ids."""
    if first_id == second_id:
        return 1.0
    first = world.organizations[first_id]
    second = world.organizations[second_id]
    p1, p2 = set(first.parent_ids), set(second.parent_ids)
    if first_id in p2 or second_id in p1:
        return 1.0
    if p1 & p2:
        return .75
    gp1 = {
        parent for pid in p1
        for parent in getattr(world.organizations.get(pid), "parent_ids", ())
    }
    gp2 = {
        parent for pid in p2
        for parent in getattr(world.organizations.get(pid), "parent_ids", ())
    }
    if gp1 & gp2 or p1 & gp2 or p2 & gp1:
        return .5
    return 0.0


def _leader_traits(world, organization) -> tuple[float, float]:
    leader = world.leaders.get(organization.leader_id or "")
    if leader is None:
        return .5, .5
    hardline = (
        leader.risk_tolerance
        + leader.ideological_rigidity
        + (1.0 - leader.political_skill)
    ) / 3.0
    return _clamp(hardline), _clamp(leader.political_skill)


def _constituency_state(world, first_id: str, second_id: str) -> tuple[float, float]:
    first = world.organizations[first_id]
    second = world.organizations[second_id]
    first_sites = {
        world.persons[pid].residence_locality_id
        for pid in first.member_ids
        if pid in world.persons
        and world.persons[pid].organization_id == first_id
        and world.persons[pid].armed_fraction > 0
    }
    second_sites = {
        world.persons[pid].residence_locality_id
        for pid in second.member_ids
        if pid in world.persons
        and world.persons[pid].organization_id == second_id
        and world.persons[pid].armed_fraction > 0
    }
    overlap_sites = sorted(first_sites & second_sites)
    if not overlap_sites:
        return 0.0, 0.0

    fragmentation = []
    contest = []
    for locality_id in overlap_sites:
        profile = locality_franchise_support_profile(world, locality_id)
        shares = profile["franchise_support_shares"]
        p = float(shares.get(first_id, 0.0))
        q = float(shares.get(second_id, 0.0))
        fragmentation.append(float(profile["support_fragmentation"]))
        contest.append(_clamp(4.0 * p * q))
    return (
        sum(fragmentation) / len(fragmentation),
        sum(contest) / len(contest),
    )


def extract_dyad_state(world, first_id: str, second_id: str) -> DyadState:
    """Extract only state constructs already represented by the live model."""
    first = world.organizations[first_id]
    second = world.organizations[second_id]
    fragmentation, contest = _constituency_state(world, first_id, second_id)
    hard1, bargain1 = _leader_traits(world, first)
    hard2, bargain2 = _leader_traits(world, second)
    material1 = _clamp(first.capital.get("material", 0.0))
    material2 = _clamp(second.capital.get("material", 0.0))
    return DyadState(
        contact_overlap=_clamp(organization_contact_overlap(world, first, second)),
        ideological_distance=ideological_distance(first, second),
        genealogical_proximity=genealogical_proximity(world, first_id, second_id),
        support_fragmentation=_clamp(fragmentation),
        constituency_contest=_clamp(contest),
        mean_cohesion=_clamp((first.cohesion + second.cohesion) / 2.0),
        resource_stress=_clamp(1.0 - (material1 + material2) / 2.0),
        leader_hardline=_clamp((hard1 + hard2) / 2.0),
        leader_bargaining_skill=_clamp((bargain1 + bargain2) / 2.0),
    )


def diagnostic_indices(
    state: DyadState, relationship_memory: float
) -> dict[str, float]:
    """Directional signatures for a specified dyadic relationship.

    relationship_memory is intentionally not a live state yet:
    -1 = persistently hostile, 0 = unresolved, +1 = cooperative.
    """
    relation = max(-1.0, min(1.0, float(relationship_memory)))
    positive = max(0.0, relation)
    negative = max(0.0, -relation)
    neutral = 1.0 - abs(relation)
    contact = state.contact_overlap
    compatibility = 1.0 - state.ideological_distance
    bargain = (
        .5
        + .25 * state.genealogical_proximity
        + .25 * state.leader_bargaining_skill
    )

    cooperation = contact * compatibility * bargain * (.2 + .8 * positive)
    merger = cooperation * (
        .35
        + .35 * state.resource_stress
        + .30 * (1.0 - state.mean_cohesion)
    )
    rivalry = (
        contact
        * state.constituency_contest
        * (.35 + .65 * neutral)
        * (.5 + .5 * state.ideological_distance)
    )
    defection = (
        contact
        * state.constituency_contest
        * state.resource_stress
        * (1.0 - state.mean_cohesion)
        * (.2 + .8 * negative)
    )
    strife = (
        contact
        * state.constituency_contest
        * (.35 + .65 * state.ideological_distance)
        * (.35 + .65 * state.mean_cohesion)
        * (.25 + .75 * state.leader_hardline)
        * negative
    )
    return {
        "cooperation": _clamp(cooperation),
        "merger": _clamp(merger),
        "nonviolent_rivalry": _clamp(rivalry),
        "defection": _clamp(defection),
        "armed_strife": _clamp(strife),
    }


def synthetic_identification_battery() -> dict[str, Any]:
    """Matched synthetic contrasts that can falsify the candidate theory."""
    base = DyadState(.85, .55, .75, .50, .90, .75, .70, .80, .35)

    def changed(**kwargs) -> DyadState:
        values = asdict(base)
        values.update(kwargs)
        return DyadState(**values)

    relation_sweep = [
        {
            "relationship_memory": relation,
            "indices": diagnostic_indices(base, relation),
        }
        for relation in (-1.0, -.5, 0.0, .5, 1.0)
    ]

    zero_contact = changed(contact_overlap=0.0)
    low_contest = changed(constituency_contest=.05)
    high_contest = changed(constituency_contest=.95)
    close_ideology = changed(ideological_distance=.05)
    far_ideology = changed(ideological_distance=.95)
    soft_leaders = changed(
        leader_hardline=.10, leader_bargaining_skill=.90
    )
    hard_leaders = changed(
        leader_hardline=.90, leader_bargaining_skill=.10
    )

    gates = {
        "contact_is_opportunity_gate": all(
            value == 0.0
            for value in diagnostic_indices(zero_contact, -1.0).values()
        ),
        "balanced_constituency_competition_raises_hostile_strife": (
            diagnostic_indices(high_contest, -1.0)["armed_strife"]
            > diagnostic_indices(low_contest, -1.0)["armed_strife"]
        ),
        "ideological_distance_suppresses_cooperation": (
            diagnostic_indices(close_ideology, 1.0)["cooperation"]
            > diagnostic_indices(far_ideology, 1.0)["cooperation"]
        ),
        "ideological_distance_raises_hostile_strife": (
            diagnostic_indices(far_ideology, -1.0)["armed_strife"]
            > diagnostic_indices(close_ideology, -1.0)["armed_strife"]
        ),
        "hardline_leadership_raises_hostile_strife": (
            diagnostic_indices(hard_leaders, -1.0)["armed_strife"]
            > diagnostic_indices(soft_leaders, -1.0)["armed_strife"]
        ),
        "bargaining_skill_raises_cooperation": (
            diagnostic_indices(soft_leaders, 1.0)["cooperation"]
            > diagnostic_indices(hard_leaders, 1.0)["cooperation"]
        ),
        "relation_memory_changes_regime_with_structure_fixed": (
            diagnostic_indices(base, 1.0)["cooperation"]
            > diagnostic_indices(base, -1.0)["cooperation"]
            and diagnostic_indices(base, -1.0)["armed_strife"]
            > diagnostic_indices(base, 1.0)["armed_strife"]
        ),
    }

    return {
        "candidate_theory": (
            "relational bargaining under constituency competition"
        ),
        "status": "diagnostic_only_no_core_combat_added",
        "base_structural_state": asdict(base),
        "relationship_sweep": relation_sweep,
        "recovery_gates": gates,
        "all_recovery_gates_pass": all(gates.values()),
        "minimal_missing_construct": {
            "name": "persistent_interfranchise_relationship_memory",
            "domain": [-1.0, 1.0],
            "interpretation": (
                "negative=hostile; zero=unresolved; positive=cooperative"
            ),
            "why_needed": (
                "Current live states encode opportunity, stakes, capability, "
                "and bargaining pressure but no dyadic path-dependent "
                "disposition that separates accommodation from hostility."
            ),
            "future_update_evidence": [
                "recruitment displacement or poaching",
                "resource or sanctuary bargains",
                "credible cooperation",
                "leadership succession",
                "split or merger lineage history",
                (
                    "costly hostile interactions only if independently "
                    "justified later"
                ),
            ],
        },
        "live_semantics_audit": {
            "merger": (
                "implemented: compatibility x low-cohesion x "
                "contact-overlap hazard"
            ),
            "nonviolent_rivalry": (
                "implemented implicitly: unaffiliated recruits choose among "
                "accessible franchises"
            ),
            "defection_to_rival": (
                "not implemented: incumbents are restricted to their current "
                "organization in recruitment candidate selection"
            ),
            "armed_interfranchise_strife": (
                "not implemented and not identified by current structural "
                "state alone"
            ),
            "genealogy": (
                "implemented through organization parent_ids and transition "
                "records"
            ),
            "leadership": (
                "implemented per organization, not as persistent dyadic memory"
            ),
        },
        "falsification_program": [
            (
                "Contact intervention: identical dyads with versus without "
                "overlap; direct interaction signatures must vanish without "
                "contact."
            ),
            (
                "Constituency-balance intervention: hold total support fixed "
                "while moving monopoly to 50/50 support; rivalry/hostile "
                "pressure rises only under overlap."
            ),
            (
                "Ideology x genealogy factorial: convergence and shared "
                "lineage favor accommodation but must not force merger."
            ),
            (
                "Stress x cohesion factorial: low-cohesion stress favors "
                "exit/merger pressure; hostile strife also requires negative "
                "relationship memory and sufficient cohesion/capacity."
            ),
            (
                "Leadership substitution: vary only risk, rigidity, and "
                "political skill; hardline leaders raise escalation pressure "
                "while political skill raises accommodation."
            ),
            (
                "Relationship-history intervention: hold every structural "
                "covariate fixed and reverse dyadic memory; regime signatures "
                "must diverge."
            ),
            (
                "Shuffled-dyad placebo: permuting relationship histories "
                "across structurally matched dyads should destroy a genuine "
                "history-outcome association."
            ),
        ],
    }


def build_report() -> dict[str, Any]:
    return synthetic_identification_battery()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "all_recovery_gates_pass": report["all_recovery_gates_pass"],
        "minimal_missing_construct": (
            report["minimal_missing_construct"]["name"]
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
