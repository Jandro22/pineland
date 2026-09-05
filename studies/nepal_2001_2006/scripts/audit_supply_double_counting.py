"""Audit that default contact supply effects are not counted twice.

This is a data-free implementation check.  In the default ``no_gate`` branch,
supply may affect contact through effective readiness/activity, while the
contact hazard must not receive a second direct supply multiplier.  Combat
expenditure is a post-realization flow and is kept distinct from sustained
presence consumption.
"""
from __future__ import annotations

import json
import random
from math import exp
from pathlib import Path

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.combat import resolve_engagement
from pineland_sim.logistics import update_logistics
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies" / "nepal_2001_2006" / "results" / "contact_forensic"


def prepared(seed: int):
    config = SimulationConfig(seed=seed, agent_count=120, locality_count=17,
                              horizon_days=1, output_mode="ensemble")
    config.organization_ecology.enabled = False
    config.combat.contact_supply_rule = "no_gate"
    config.contact_rate = 0.6
    world = generate_pineland(config)
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    world.organizations["insurgent"].status = "active"
    for formation in (government, insurgent):
        formation.availability = formation.readiness = formation.command = 1.0
        formation.cohesion = 1.0
        formation.fatigue = 0.0
        formation.supply_stock = formation.supply_capacity
        formation.moving = False
        formation.operational_status = "effective"
    return world, government.formation_id, insurgent.formation_id


def trial(seed: int, supply: float) -> dict:
    world, government_id, insurgent_id = prepared(seed)
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    for formation in (government, insurgent):
        formation.supply_stock = formation.supply_capacity * supply
    event = ScheduledEvent(0.0, 20, 0, "contact", {
        "locality_id": government.locality_id,
        "microzone_id": government.current_microzone_id,
        "force_detection": True,
    })
    ProcessEngine(world).execute(event)
    trace = world.contact_funnel_records[-1]
    expected = 1 - exp(-world.config.contact_rate * trace["proximity"] *
                       trace["detection_factor"] * trace["activity"] *
                       trace["supply_factor"])
    return {
        "supply": supply,
        "supply_factor": trace["supply_factor"],
        "hazard": trace["contact_hazard"],
        "expected_hazard_from_single_activity_factor": expected,
        "absolute_residual": abs(trace["contact_hazard"] - expected),
        "flow_types": sorted({flow.flow_type for flow in world.resource_flows}),
    }


def flow_type_check() -> list[str]:
    world, government_id, insurgent_id = prepared(98200)
    update_logistics(world, 1.0, 1.0)
    resolve_engagement(
        world, "DOUBLE-COUNT-AUDIT", world.formations[government_id],
        world.formations[insurgent_id], ("fdf", "insurgent"), 1.0,
        random.Random(98201),
    )
    return sorted({flow.flow_type for flow in world.resource_flows})


def main() -> None:
    rows = [trial(98100 + i, supply) for i, supply in enumerate((0.0, 0.5, 1.0))]
    max_residual = max(row["absolute_residual"] for row in rows)
    flow_types = flow_type_check()
    presence_flow_observed = "sustained_presence" in flow_types
    combat_flow_observed = "combat_expenditure" in flow_types
    output = {
        "schema_version": "1.0.0",
        "experiment": "supply_double_counting_audit",
        "nepal_data_used": False,
        "default_contact_supply_rule": "no_gate",
        "checks": {
            "default_has_no_direct_contact_supply_multiplier": all(
                row["supply_factor"] == 1.0 for row in rows),
            "hazard_matches_activity_only_equation": max_residual <= 1e-12,
            "presence_and_combat_flows_are_distinct": {
                "sustained_presence": presence_flow_observed,
                "combat_expenditure": combat_flow_observed,
                "distinct": presence_flow_observed and combat_flow_observed,
            },
        },
        "max_hazard_residual": max_residual,
        "flow_types_observed": flow_types,
        "rows": rows,
        "interpretation": (
            "In the default no_gate branch, supply enters contact occurrence once through "
            "effective-readiness activity; combat_expenditure is a post-realization supply "
            "flow and sustained_presence is a separate logistics flow. Continuous and hard "
            "branches are explicit counterfactual policies, not hidden second multipliers."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "supply_double_counting_audit.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "max_hazard_residual": max_residual}))


if __name__ == "__main__":
    main()
