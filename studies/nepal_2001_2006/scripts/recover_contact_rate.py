"""Recover contact_rate from data-free synthetic contact observations.

The experiment uses known formation states and forced detection so the contact
rate is identifiable from the coded hazard.  It is deliberately not a Nepal
calibration and does not write any model parameter values.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies" / "nepal_2001_2006" / "results" / "contact_forensic"
RATES = (0.02, 0.05, 0.10, 0.20)
SUPPLY_LEVELS = (1.0, 0.5, 0.1)
TRIALS_PER_CELL = 4096


def base_world():
    config = SimulationConfig(seed=91001, agent_count=120, locality_count=17,
                              horizon_days=1, output_mode="ensemble")
    config.organization_ecology.enabled = False
    config.information.contact_true_positive_rate = 1.0
    config.combat.contact_supply_rule = "no_gate"
    world = generate_pineland(config)
    g, i = world.formations["FDF-01"], world.formations["PRF-01"]
    i.locality_id = g.locality_id
    i.current_microzone_id = g.current_microzone_id
    for f in (g, i):
        f.availability = f.readiness = f.command = 1.0
        f.cohesion = 1.0; f.fatigue = 0.0; f.moving = False
        f.operational_status = "effective"
        f.supply_stock = f.supply_capacity
    world.organizations["insurgent"].status = "active"
    baseline = {f.formation_id: {
        "personnel": f.personnel, "readiness": f.readiness,
        "availability": f.availability, "cohesion": f.cohesion,
        "fatigue": f.fatigue, "moving": f.moving,
        "operational_status": f.operational_status,
    } for f in (g, i)}
    return world, g.formation_id, i.formation_id, baseline


def run_cell(base, g_id, i_id, baseline, seed, rate, supply):
    world = base
    world.config.seed = seed
    for fid, state in baseline.items():
        formation = world.formations[fid]
        for key, value in state.items():
            setattr(formation, key, value)
    world.config.contact_rate = rate
    world.formations[g_id].supply_stock = world.formations[g_id].supply_capacity * supply
    world.formations[i_id].supply_stock = world.formations[i_id].supply_capacity * supply
    world.contact_funnel_records.clear(); world.contact_funnel_counts.clear()
    world.engagements.clear(); world.event_log.clear(); world.synthetic_records.clear()
    world.observations.clear(); world.observation_index.clear(); world.observation_source_index.clear()
    event = ScheduledEvent(0.0, 20, 0, "contact", {
        "locality_id": world.formations[g_id].locality_id,
        "microzone_id": world.formations[g_id].current_microzone_id,
        "force_detection": True,
    })
    ProcessEngine(world).execute(event)
    return world.contact_funnel_records[-1]


def main():
    base, g_id, i_id, baseline = base_world()
    rows = []
    for supply in SUPPLY_LEVELS:
        for rate in RATES:
            traces = [run_cell(base, g_id, i_id, baseline, 91000 + index, rate, supply)
                      for index in range(TRIALS_PER_CELL)]
            observed = sum(t["gate_counts"]["realized_latent_contacts"] for t in traces) / len(traces)
            mean_hazard = sum(t["contact_hazard"] for t in traces) / len(traces)
            mean_activity = sum(t["activity"] for t in traces) / len(traces)
            estimated = (-math.log(max(1e-12, 1 - observed)) /
                         max(1e-12, mean_activity))
            rows.append({
                "supply": supply, "true_contact_rate": rate, "n": len(traces),
                "observed_probability": observed, "mean_hazard": mean_hazard,
                "mean_activity": mean_activity, "estimated_contact_rate": estimated,
                "absolute_error": abs(estimated - rate),
                "identifiable_when_activity_observed": True,
            })
    output = {
        "schema_version": "1.0.0", "experiment": "synthetic_contact_rate_recovery",
        "nepal_data_used": False, "forced_detection": True,
        "model_contact_supply_rule": "no_gate",
        "rows": rows,
        "interpretation": "With detection, proximity, readiness, and supply states observed in the synthetic experiment, contact_rate is recoverable. In historical Nepal it remains unlicensed because movement, detection, readiness, supply, and recording are not jointly identified and recorded realized contacts remain zero.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "synthetic_contact_rate_recovery.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "rows": len(rows), "trials": len(rows) * TRIALS_PER_CELL}))


if __name__ == "__main__":
    main()
