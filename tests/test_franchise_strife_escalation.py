from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from pineland_sim.entities import LeadershipAgent, Organization, OrganizationKind

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "studies" / "research_program" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import identify_franchise_strife_escalation as study


def _organization(
    oid: str,
    parents=(),
    ideology=.5,
    material=.5,
    cohesion=.7,
):
    return Organization(
        organization_id=oid,
        name=oid,
        kind=OrganizationKind.INSURGENT,
        resources=100.0,
        cohesion=cohesion,
        discipline=.6,
        accountability=.5,
        local_knowledge=.5,
        persistence=.6,
        mobility=.5,
        institutional_quality=.5,
        capital={
            "social": .5,
            "political": .5,
            "organizational": .5,
            "material": material,
        },
        ideology={"reform": ideology},
        parent_ids=tuple(parents),
        leader_id=f"leader-{oid}",
    )


def _person(pid, oid, locality, affinity_a, affinity_b):
    return SimpleNamespace(
        person_id=pid,
        organization_id=oid,
        armed_fraction=1.0,
        residence_locality_id=locality,
        weight=10.0,
        public_behavior="armed_participation",
        insurgent_affinity={"a": affinity_a, "b": affinity_b},
    )


def _world():
    ancestor = _organization("ancestor")
    ancestor.status = "fragmented"
    a = _organization(
        "a",
        parents=("ancestor",),
        ideology=.2,
        material=.2,
        cohesion=.8,
    )
    b = _organization(
        "b",
        parents=("ancestor",),
        ideology=.8,
        material=.4,
        cohesion=.6,
    )
    people = {
        "pa": _person("pa", "a", "L1", 1.0, 0.0),
        "pb": _person("pb", "b", "L1", 0.0, 1.0),
        "sa": _person("sa", None, "L1", 1.0, 0.0),
        "sb": _person("sb", None, "L1", 0.0, 1.0),
    }
    a.member_ids = {"pa"}
    b.member_ids = {"pb"}
    leaders = {
        "leader-a": LeadershipAgent(
            "leader-a", "a", .5, .5, .8, .8, .2, .5
        ),
        "leader-b": LeadershipAgent(
            "leader-b", "b", .5, .5, .6, .7, .3, .5
        ),
    }
    return SimpleNamespace(
        organizations={"ancestor": ancestor, "a": a, "b": b},
        persons=people,
        formations={},
        leaders=leaders,
    )


def test_extracts_live_dyad_state_and_lineage():
    state = study.extract_dyad_state(_world(), "a", "b")
    assert state.contact_overlap == 1.0
    assert abs(state.ideological_distance - .6) < 1e-12
    assert state.genealogical_proximity == .75
    assert state.constituency_contest > .9
    assert state.support_fragmentation > 0.0
    assert state.resource_stress == .7
    assert 0.0 <= state.leader_hardline <= 1.0


def test_relation_memory_separates_accommodation_from_strife():
    state = study.DyadState(.9, .6, .75, .5, .9, .8, .7, .85, .3)
    cooperative = study.diagnostic_indices(state, 1.0)
    hostile = study.diagnostic_indices(state, -1.0)
    assert cooperative["cooperation"] > hostile["cooperation"]
    assert hostile["armed_strife"] > cooperative["armed_strife"]
    assert cooperative["armed_strife"] == 0.0


def test_contact_is_a_hard_opportunity_gate():
    state = study.DyadState(0.0, .6, .75, .5, .9, .8, .7, .85, .3)
    assert all(
        value == 0.0
        for value in study.diagnostic_indices(state, -1.0).values()
    )


def test_synthetic_battery_recovers_preregistered_signs():
    report = study.synthetic_identification_battery()
    assert report["all_recovery_gates_pass"] is True
    assert all(report["recovery_gates"].values())
    assert (
        report["minimal_missing_construct"]["name"]
        == "persistent_interfranchise_relationship_memory"
    )
    assert report["live_semantics_audit"]["armed_interfranchise_strife"].startswith(
        "not implemented"
    )
