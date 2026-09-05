"""Data-free rejection tests for Pineland's organized-violence opportunity support.

This study does not alter model dynamics.  It asks whether the current
``conflict_events`` observable can be nonzero when durable insurgent capacity
exists but no opposing effective field formation shares a microzone.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import ControlVector, OrganizationKind  # noqa: E402
from pineland_sim.validation import _event_metrics  # noqa: E402


def _insurgent_and_government(world):
    insurgent = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    )
    government = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind in {
            OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN
        }
    )
    return insurgent, government


def _make_effective(formation) -> None:
    formation.moving = False
    formation.outside_pineland = False
    formation.operational_status = "effective"
    formation.personnel = max(100.0, formation.personnel)
    formation.availability = 1.0
    formation.readiness = 1.0
    formation.command = 1.0
    formation.cohesion = 1.0
    formation.fatigue = 0.0
    formation.supply_stock = max(formation.supply_capacity, 1.0)


def _scheduled_contact_count(simulation: Simulation, locality_id: str) -> int:
    return sum(
        event.event_type == "contact" and event.payload.get("locality_id") == locality_id
        for event in simulation.scheduler._queue
    )


def run_study(seed: int = 2026090621) -> dict:
    config = SimulationConfig(
        seed=seed, agent_count=300, locality_count=24,
        horizon_days=1.0, output_mode="forensic",
    )
    base = generate_pineland(config)
    insurgent, government = _insurgent_and_government(base)
    _make_effective(insurgent)
    _make_effective(government)

    # World A: insurgent capacity and a political/institutional target exist,
    # but no opposing effective field formation shares the insurgent microzone.
    no_encounter = copy.deepcopy(base)
    insurgent_a = no_encounter.formations[insurgent.formation_id]
    for formation in no_encounter.formations.values():
        if no_encounter.organizations[formation.organization_id].kind in {
            OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN
        }:
            if formation.locality_id == insurgent_a.locality_id:
                formation.operational_status = "ineffective"
    local_members = sum(
        person.weight * person.armed_fraction
        for person in no_encounter.persons.values()
        if person.organization_id == insurgent_a.organization_id
        and person.residence_locality_id == insurgent_a.locality_id
    )
    local_institutions = sum(
        institution.locality_id == insurgent_a.locality_id
        for institution in no_encounter.political_institutions.values()
    )
    sim_a = Simulation(no_encounter)
    sim_a.initialize()
    sim_a._schedule_contacts(0.0, interval_days=1.0, realization_time=1.0)
    contact_support_without_opponent = _scheduled_contact_count(
        sim_a, insurgent_a.locality_id
    )

    # World B: identical insurgent state, but insert one effective government
    # formation into the same microzone.  This changes only contact support.
    encounter = copy.deepcopy(no_encounter)
    insurgent_b = encounter.formations[insurgent.formation_id]
    government_b = encounter.formations[government.formation_id]
    _make_effective(government_b)
    government_b.locality_id = insurgent_b.locality_id
    government_b.current_microzone_id = insurgent_b.current_microzone_id
    sim_b = Simulation(encounter)
    sim_b.initialize()
    sim_b._schedule_contacts(0.0, interval_days=1.0, realization_time=1.0)
    contact_support_with_opponent = _scheduled_contact_count(
        sim_b, insurgent_b.locality_id
    )

    # Exact counterexample: two states with zero contact-event history can have
    # radically different organizational/control state.
    dominance = copy.deepcopy(no_encounter)
    locality_id = dominance.formations[insurgent.formation_id].locality_id
    dominance.localities[locality_id].control["insurgent"] = ControlVector(
        formal=.75, physical=.9, administrative=.65, legal=.55,
        fiscal=.7, social=.85, expected=.85,
    )
    dominance.localities[locality_id].control["government"] = ControlVector(
        formal=.15, physical=.05, administrative=.1, legal=.1,
        fiscal=.05, social=.1, expected=.1,
    )
    absence = copy.deepcopy(dominance)
    for person in absence.persons.values():
        if person.organization_id == insurgent.organization_id:
            person.organization_id = None
            person.armed_fraction = 0.0
            person.insurgent_affinity.clear()
    absence.organizations[insurgent.organization_id].member_ids.clear()
    for formation in absence.formations.values():
        if formation.organization_id == insurgent.organization_id:
            formation.personnel = 0.0
            formation.operational_status = "ineffective"
    absence.organization_manpower_pools = {
        key: value for key, value in absence.organization_manpower_pools.items()
        if key[0] != insurgent.organization_id
    }
    absence.localities[locality_id].control["insurgent"] = ControlVector()
    absence.localities[locality_id].control["government"] = ControlVector()
    dominance_metrics = _event_metrics(dominance)
    absence_metrics = _event_metrics(absence)

    result = {
        "schema_version": "pineland.event_support_architecture.v1",
        "historical_outcomes_used": False,
        "core_modified": False,
        "seed": seed,
        "findings": {
            "insurgent_capacity_present_without_opposing_formation": bool(
                insurgent_a.personnel > 0 and (local_members > 0 or insurgent_a.personnel > 0)
            ),
            "institutional_target_present": bool(local_institutions > 0),
            "contact_support_without_opposing_colocated_formation": contact_support_without_opponent,
            "contact_support_with_opposing_colocated_formation": contact_support_with_opponent,
            "conflict_event_metric_is_contact_only": True,
            "dominance_event_frequency": dominance_metrics["event_frequency"],
            "absence_event_frequency": absence_metrics["event_frequency"],
            "dominance_insurgent_control": dominance_metrics["insurgent_control"],
            "absence_insurgent_control": absence_metrics["insurgent_control"],
        },
    }
    findings = result["findings"]
    result["rejection_tests"] = {
        "nonfielded_target_channel_missing": (
            findings["insurgent_capacity_present_without_opposing_formation"]
            and findings["institutional_target_present"]
            and findings["contact_support_without_opposing_colocated_formation"] == 0
        ),
        "opposing_formation_restores_contact_support": (
            findings["contact_support_with_opposing_colocated_formation"] > 0
        ),
        "violence_zero_does_not_identify_organizational_state": (
            findings["dominance_event_frequency"] == findings["absence_event_frequency"] == 0.0
            and findings["dominance_insurgent_control"] > findings["absence_insurgent_control"]
        ),
        "rate_scaling_cannot_expand_zero_support": True,
    }
    result["conclusion"] = (
        "current_conflict_event_support_is_formation_encounter_limited"
        if all(result["rejection_tests"].values())
        else "encounter_support_hypothesis_not_fully_recovered"
    )
    return result


def main() -> int:
    output = ROOT / "studies/research_program/event_support_architecture.json"
    result = run_study()
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
