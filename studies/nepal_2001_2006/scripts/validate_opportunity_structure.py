"""Data-free validation of opportunity scaling, time units, and equilibrium."""
from __future__ import annotations

import copy
import json
from math import log
from pathlib import Path

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.logistics import update_logistics
from pineland_sim.processes import ProcessEngine

ROOT = Path(__file__).resolve().parents[3]
CASE = ROOT / "studies/nepal_2001_2006/config/case_environment_repaired.json"
OUT = ROOT / "studies/nepal_2001_2006/results/post_structural_repair/opportunity_structure"


def prepared():
    cfg = SimulationConfig(seed=81231, agent_count=120, locality_count=17,
                           horizon_days=1, output_mode="calibration")
    cfg.organization_ecology.enabled = False
    world = generate_pineland(cfg)
    g, i = world.formations["FDF-01"], world.formations["PRF-01"]
    i.locality_id, i.current_microzone_id = g.locality_id, g.current_microzone_id
    for f in (g, i):
        f.availability = f.readiness = f.command = f.cohesion = 1.0
        f.fatigue = 0.0; f.moving = False; f.operational_status = "effective"
        f.supply_stock = f.supply_capacity
    return world, g, i


def interval_test():
    base, g, i = prepared()
    rows = []
    for dt in (.25, .5, 1.0, 2.0, 7.0):
        world = base.clone()
        ProcessEngine(world).execute(ScheduledEvent(0, 20, 0, "contact", {
            "locality_id": g.locality_id, "microzone_id": g.current_microzone_id,
            "government_formation_id": g.formation_id,
            "insurgent_formation_id": i.formation_id, "force_detection": True,
            "interval_days": dt}))
        p = world.contact_funnel_records[-1]["contact_hazard"]
        rows.append({"dt_days": dt, "hazard": p, "implied_rate_per_day": -log(1-p)/dt})
    return rows


def pair_envelope():
    base, g, i = prepared()
    rows = []
    for n in (1, 5, 10):
        world = base.clone(); world.formations.clear()
        for side, original in (("FDF", g), ("PRF", i)):
            for index in range(n):
                f = copy.deepcopy(original); f.formation_id = f"{side}-X{index:02d}"
                world.formations[f.formation_id] = f
        sim = Simulation(world); sim._schedule_contacts(0)
        opportunities = sum(e.event_type == "contact" for e in sim.scheduler._queue)
        rows.append({"formations_per_side": n, "candidate_pairs": n*n,
                     "scheduled_opportunities": opportunities})
    return rows


def equilibrium():
    case = json.loads(CASE.read_text())
    rows = []
    for model in ("population_catchment", "organization_manpower"):
        cfg = SimulationConfig(seed=81232, agent_count=len(case["localities"]), locality_count=len(case["localities"]),
                               horizon_days=1825, output_mode="calibration")
        cfg.logistics.source_capacity_model = model
        world = generate_pineland(cfg, empirical_geography=case)
        for day in range(1, 1826):
            update_logistics(world, float(day), 1.0)
        for org in ("fdf", "insurgent"):
            forms = [f for f in world.formations.values() if f.organization_id == org]
            rows.append({"model": model, "organization": org,
                         "mean_supply_fraction": sum(f.supply_fraction() for f in forms)/len(forms),
                         "mean_readiness": sum(f.readiness for f in forms)/len(forms),
                         "mean_availability": sum(f.availability for f in forms)/len(forms)})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"parameter_fit": False, "uses_historical_outcomes": False,
               "interval_invariance": interval_test(), "pair_envelope": pair_envelope(),
               "five_year_no_combat_equilibrium": equilibrium()}
    path = OUT / "synthetic_opportunity_validation.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
