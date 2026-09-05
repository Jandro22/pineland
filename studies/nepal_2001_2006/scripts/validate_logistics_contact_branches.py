"""Compare general contact/logistics formulations in a data-free micro-world.

This is a theory/implementation experiment, not a Nepal fit.  Each branch uses
the same prepared formations, seeds, detection, and contact rate; only the
general contact-supply rule and supply ladder vary.
"""
from __future__ import annotations

import json
from pathlib import Path

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies" / "nepal_2001_2006" / "results" / "contact_forensic"
SUPPLY_LEVELS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
SCENARIOS = {
    "mutual_encounter": (None, "g", "i"),
    "government_initiation": ("g", "g", "i"),
    "insurgent_initiation": ("i", "g", "i"),
    "government_attacks_undersupplied_defender": ("g", "g", "i"),
    "two_undersupplied_encounter": (None, "g", "i"),
}
RULES = ("hard_gate", "no_gate", "continuous", "ammunition_floor", "initiation_asymmetry")


def prepared_world(seed: int, rule: str):
    config = SimulationConfig(seed=seed, agent_count=120, locality_count=17,
                              horizon_days=1, output_mode="ensemble")
    config.organization_ecology.enabled = False
    config.contact_rate = 0.6
    config.information.contact_true_positive_rate = 1.0
    config.combat.contact_supply_rule = rule
    world = generate_pineland(config)
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    for formation in (government, insurgent):
        formation.availability = formation.readiness = formation.command = 1.0
        formation.cohesion = 1.0
        formation.fatigue = 0.0
        formation.supply_stock = formation.supply_capacity
        formation.moving = False
        formation.operational_status = "effective"
    world.organizations["insurgent"].status = "active"
    baseline = {
        "formations": {
            f.formation_id: {
                "personnel": f.personnel, "supply_stock": f.supply_stock,
                "readiness": f.readiness, "availability": f.availability,
                "cohesion": f.cohesion, "fatigue": f.fatigue,
                "moving": f.moving, "operational_status": f.operational_status,
            }
            for f in (government, insurgent)
        },
        "sources": {s.source_id: (s.stock, s.capacity, s.production_per_day)
                    for s in world.supply_sources.values()},
        "expected_control": {
            pid: dict(person.expected_control) for pid, person in world.persons.items()
        },
    }
    return world, government.formation_id, insurgent.formation_id, baseline


def trial(base_world, government_id: str, insurgent_id: str, baseline: dict,
          seed: int, rule: str, scenario: str, supply: float) -> dict:
    initiator, attacker, defender = SCENARIOS[scenario]
    world = base_world
    world.config.seed = seed
    for formation_id, state in baseline["formations"].items():
        formation = world.formations[formation_id]
        for key, value in state.items():
            setattr(formation, key, value)
    for source_id, state in baseline["sources"].items():
        source = world.supply_sources[source_id]
        source.stock, source.capacity, source.production_per_day = state
    for pid, expected in baseline["expected_control"].items():
        world.persons[pid].expected_control = dict(expected)
    world.engagements.clear()
    world.contact_funnel_records.clear()
    world.contact_funnel_counts.clear()
    world.event_log.clear()
    world.synthetic_records.clear()
    world.observations.clear()
    world.observation_index.clear()
    world.observation_source_index.clear()
    world.causal_ledger.clear()
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    if scenario == "government_attacks_undersupplied_defender":
        government_supply, insurgent_supply = 1.0, supply
    elif scenario == "two_undersupplied_encounter":
        government_supply = insurgent_supply = supply
    else:
        government_supply = insurgent_supply = supply
    government.supply_stock = government.supply_capacity * government_supply
    insurgent.supply_stock = insurgent.supply_capacity * insurgent_supply
    payload = {"locality_id": government.locality_id,
               "microzone_id": government.current_microzone_id,
               "force_detection": True}
    if initiator is not None:
        payload["initiator_organization_id"] = (
            government.organization_id if initiator == "g" else insurgent.organization_id
        )
    ProcessEngine(world).execute(ScheduledEvent(0.0, 20, 0, "contact", payload))
    trace = world.contact_funnel_records[-1]
    realized = bool(trace["gate_counts"]["realized_latent_contacts"])
    engagement = next(iter(world.engagements.values()), None)
    return {
        "realized": realized,
        "hazard": trace.get("contact_hazard", 0.0),
        "failure_reason": trace.get("failure_reason"),
        "supply_factor": trace.get("supply_factor", 1.0),
        "casualties": (sum(engagement.personnel_losses.values()) if engagement else 0.0),
        "disengaged": len(engagement.disengaged) if engagement else 0,
        "post_readiness": {
            government_id: government.effective_readiness(),
            insurgent_id: insurgent.effective_readiness(),
        },
    }


def main() -> None:
    rows = []
    bases = {}
    for rule in RULES:
        base, government_id, insurgent_id, baseline = prepared_world(710000, rule)
        bases[rule] = (base, government_id, insurgent_id, baseline)
    for rule in RULES:
        base, government_id, insurgent_id, baseline = bases[rule]
        for scenario in SCENARIOS:
            for supply in SUPPLY_LEVELS:
                trials = [trial(base, government_id, insurgent_id, baseline,
                                710000 + index, rule, scenario, supply)
                          for index in range(128)]
                rows.append({
                    "rule": rule, "scenario": scenario, "supply": supply, "n": len(trials),
                    "contact_probability": sum(t["realized"] for t in trials) / len(trials),
                    "mean_hazard": sum(t["hazard"] for t in trials) / len(trials),
                    "mean_casualties_if_contact": (
                        sum(t["casualties"] for t in trials if t["realized"]) /
                        max(1, sum(t["realized"] for t in trials))
                    ),
                    "mean_disengaged_if_contact": (
                        sum(t["disengaged"] for t in trials if t["realized"]) /
                        max(1, sum(t["realized"] for t in trials))
                    ),
                    "mean_post_readiness": sum(
                        sum(t["post_readiness"].values()) / 2 for t in trials
                    ) / len(trials),
                    "failure_reasons": {
                        reason: sum(t["failure_reason"] == reason for t in trials)
                        for reason in sorted({t["failure_reason"] for t in trials})
                    },
                })
    output = {
        "schema_version": "1.0.0", "experiment": "logistics_contact_branch_comparison",
        "nepal_data_used": False, "contact_rate": 0.6, "forced_detection": True,
        "supply_levels": list(SUPPLY_LEVELS), "rules": list(RULES),
        "scenarios": list(SCENARIOS), "trials_per_cell": 128,
        "theory_guard": {
            "no_gate": "physical contact remains possible; supply acts through readiness, capability, expenditure, disengagement, and endurance",
            "continuous": "contact hazard is smoothly attenuated by min-side supply with f(0)=0.2",
            "hard_gate": "legacy counterfactual retained only for diagnosis",
            "ammunition_floor": "hard threshold is interpreted as a specific minimum material floor, not general sustainment",
            "initiation_asymmetry": "only an explicitly identified initiator is supply-gated; unidentified encounters remain possible",
        },
        "rows": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "logistics_contact_branch_comparison.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cells": len(rows), "trials": len(rows) * 128, "output": str(path)}))


if __name__ == "__main__":
    main()
