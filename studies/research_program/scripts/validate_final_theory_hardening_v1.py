"""Data-free planted-base validation for the final pre-holdout theory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.action_model import (
    action_attempt_probability,
    action_choice_weights,
    execution_probability,
    operational_reach_candidates,
)
from pineland_sim.entities import ActorBelief, ControlVector, OrganizationKind
from pineland_sim.organizational_state import (
    local_operational_knowledge,
    local_organizational_embeddedness,
)

SEEDS = tuple(range(2026090611, 2026090619))


def _organization(world):
    return next(o for o in world.organizations.values()
                if o.kind is OrganizationKind.INSURGENT and o.status == "active")


def _reset(world, organization):
    organization.member_ids.clear()
    for person in world.persons.values():
        if person.organization_id == organization.organization_id:
            person.organization_id, person.armed_fraction = None, 0.0
    for formation in world.formations.values():
        if formation.organization_id == organization.organization_id:
            formation.personnel = 0.0
    for key in list(world.organization_manpower_pools):
        if key[0] == organization.organization_id:
            world.organization_manpower_pools.pop(key, None)
            world.organization_manpower_supply_reserves.pop(key, None)
    for locality in world.localities.values():
        locality.control[organization.organization_id] = ControlVector()


def _pool(world, oid, locality_id, quantity=100.0):
    per_fighter = (world.config.logistics.formation_supply_days
                   * world.config.logistics.initial_supply_fraction)
    world.organization_manpower_pools[(oid, locality_id)] = quantity
    world.organization_manpower_supply_reserves[(oid, locality_id)] = (
        quantity * per_fighter
    )


def _belief(world, oid, locality_id):
    world.control_beliefs[(oid, "government", locality_id)] = ActorBelief(
        oid, locality_id,
        ControlVector(formal=.8, physical=.8, administrative=.8,
                      legal=.8, fiscal=.8, social=.5, expected=.5),
        0.0, 0.0, evidence_count=0,
    )


def _propensity(world, oid, locality_id):
    attempt = action_attempt_probability(world, oid, locality_id, 1.0)
    weights = action_choice_weights(world, oid, locality_id)
    total = sum(max(0.0, value) for value in weights.values())
    choice = max(0.0, weights["nonfielded_human_target"]) / max(1e-12, total)
    execution = execution_probability(
        world, oid, locality_id, .25, 1.0,
        target_organization_id="government",
        target_locality_id=locality_id,
    )
    return {
        "propensity": attempt * choice * execution,
        "embeddedness": local_organizational_embeddedness(
            world, oid, locality_id),
        "knowledge": local_operational_knowledge(
            world, oid, locality_id, "government"),
    }


def run_seed(seed):
    world = generate_pineland(SimulationConfig(
        seed=seed, agent_count=300, locality_count=24,
        horizon_days=2, burn_in_days=0.0))
    organization = _organization(world)
    organization.local_knowledge = .8
    _reset(world, organization)
    localities = sorted({
        post.locality_id for post in world.security_posts.values()
        if post.personnel > 0 and any(
            p.residence_locality_id == post.locality_id
            for p in world.persons.values())
    })
    focal, control = localities[:2]
    for locality_id in (focal, control):
        _belief(world, organization.organization_id, locality_id)
    baseline = {x: _propensity(world, organization.organization_id, x)
                for x in (focal, control)}

    _pool(world, organization.organization_id, focal)
    person = next(p for p in world.persons.values()
                  if p.residence_locality_id == focal)
    desired = world.config.organization_ecology.minimum_proto_represented_population
    person.armed_fraction = min(1.0, desired / max(1e-12, person.weight))
    person.organization_id = organization.organization_id
    person.home_locality_id = focal
    organization.member_ids.add(person.person_id)
    rooted = {x: _propensity(world, organization.organization_id, x)
              for x in (focal, control)}

    quantity = world.organization_manpower_pools.pop(
        (organization.organization_id, focal)
    )
    reserve = world.organization_manpower_supply_reserves.pop(
        (organization.organization_id, focal)
    )
    world.organization_manpower_pools[
        (organization.organization_id, control)
    ] = quantity
    world.organization_manpower_supply_reserves[
        (organization.organization_id, control)
    ] = reserve
    person.residence_locality_id = control
    person.home_locality_id = control
    shuffled = {x: _propensity(world, organization.organization_id, x)
                for x in (focal, control)}

    world.organization_manpower_pools.pop(
        (organization.organization_id, control), None)
    world.organization_manpower_supply_reserves.pop(
        (organization.organization_id, control), None)
    organization.member_ids.clear()
    person.organization_id, person.armed_fraction = None, 0.0
    removed = _propensity(world, organization.organization_id, control)
    reaches = operational_reach_candidates(
        world, organization.organization_id, focal)
    checks = {
        "matched_baseline": abs(
            baseline[focal]["propensity"] - baseline[control]["propensity"]) < 1e-12,
        "rooted_hotspot": rooted[focal]["propensity"] > baseline[focal]["propensity"],
        "untreated_control_zero": rooted[control]["propensity"] == 0.0,
        "hotspot_follows_base": shuffled[control]["propensity"] > shuffled[focal]["propensity"],
        "base_removal_zeroes_risk": removed["propensity"] == 0.0,
        "reach_bounded": all(
            loc == focal or 0.0 < reach < 1.0 for loc, reach in reaches),
    }
    return {"seed": seed, "focal": focal, "control": control,
            "baseline": baseline, "rooted": rooted, "shuffled": shuffled,
            "removed": removed, "checks": checks, "passed": all(checks.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [run_seed(seed) for seed in SEEDS]
    payload = {
        "schema_version": "pineland.final_theory_hardening_recovery.v1",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "war_diary_rows_acquired": False,
        "results": rows,
        "passed": all(row["passed"] for row in rows),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
