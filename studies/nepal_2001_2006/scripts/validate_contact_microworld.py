"""Validate the general contact pathway in controlled synthetic micro-worlds.

The experiment changes only a controlled world state and configuration.  It
does not use Nepal observations, fit parameters, or alter the frozen case.
Each trial is a deep clone of one supplied/ready same-microzone pair, so the
reported frequencies can be compared with the hazard recorded by the live
implementation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "results" / "contact_forensic"


def prepared_world(seed: int = 900_000):
    config = SimulationConfig(seed=seed, agent_count=200, locality_count=17,
                              horizon_days=1, output_mode="ensemble")
    config.organization_ecology.enabled = False
    world = generate_pineland(config)
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    insurgent.moving = False
    insurgent.operational_status = "effective"
    insurgent.availability = government.availability = 1.0
    insurgent.readiness = government.readiness = 1.0
    insurgent.command = government.command = 1.0
    insurgent.cohesion = government.cohesion = 1.0
    insurgent.fatigue = government.fatigue = 0.0
    insurgent.supply_stock = insurgent.supply_capacity
    government.supply_stock = government.supply_capacity
    world.organizations["insurgent"].status = "active"
    return world, government.formation_id, insurgent.formation_id


def trial(base, government_id: str, insurgent_id: str, seed: int, *, rate: float,
          force_detection: bool | None, same_zone: bool = True,
          available: bool = True) -> dict:
    world = base.clone()
    world.config.seed = seed
    world.config.contact_rate = rate
    world.config.information.contact_true_positive_rate = 1.0
    government = world.formations[government_id]
    insurgent = world.formations[insurgent_id]
    if not same_zone:
        alternate = next(zone.microzone_id for zone in world.microzones.values()
                         if zone.locality_id == government.locality_id and
                         zone.microzone_id != government.current_microzone_id)
        insurgent.current_microzone_id = alternate
    if not available:
        insurgent.availability = 0.0
    event = ScheduledEvent(0.0, 20, 0, "contact", {
        "locality_id": government.locality_id,
        "microzone_id": government.current_microzone_id,
        "force_detection": force_detection,
    })
    ProcessEngine(world).execute(event)
    trace = world.contact_funnel_records[-1]
    return {
        "seed": seed,
        "rate": rate,
        "force_detection": force_detection,
        "same_zone": same_zone,
        "available": available,
        "realized": int(trace["gate_counts"]["realized_latent_contacts"]),
        "hazard": float(trace.get("contact_hazard", 0.0) or 0.0),
        "detected_sides": trace["gate_counts"]["detected_opponent_sides"],
        "failure_reason": trace["failure_reason"],
    }


def summarize(rows: list[dict]) -> dict:
    grouped = {}
    for key, group in __import__("itertools").groupby(
            sorted(rows, key=lambda item: (str(item["force_detection"]), item["same_zone"],
                                           item["available"], item["rate"])),
            key=lambda item: (item["force_detection"], item["same_zone"], item["available"], item["rate"])):
        group = list(group)
        observed = float(np.mean([item["realized"] for item in group]))
        expected = float(np.mean([item["hazard"] for item in group]))
        grouped[str(key)] = {
            "n": len(group), "observed_contact_probability": observed,
            "mean_recorded_hazard": expected,
            "hazard_frequency_gap": observed - expected,
            "failure_reasons": {
                reason: sum(item["failure_reason"] == reason for item in group)
                for reason in sorted({item["failure_reason"] for item in group})
            },
        }
    return grouped


def main() -> None:
    base, government_id, insurgent_id = prepared_world()
    rows = []
    seeds = range(910_000, 910_128)
    for rate in (0.05, 0.15, 0.30, 0.60):
        for seed in seeds:
            rows.append(trial(base, government_id, insurgent_id, seed, rate=rate,
                              force_detection=True))
    for seed in seeds:
        rows.append(trial(base, government_id, insurgent_id, seed, rate=0.60,
                          force_detection=False))
        rows.append(trial(base, government_id, insurgent_id, seed, rate=0.60,
                          force_detection=True, same_zone=False))
        rows.append(trial(base, government_id, insurgent_id, seed, rate=0.60,
                          force_detection=True, available=False))
    output = {
        "schema_version": "1.0.0",
        "experiment": "controlled_contact_microworld",
        "model_equations_untouched": True,
        "nepal_data_used": False,
        "prepared_pair": {"government_formation_id": government_id,
                           "insurgent_formation_id": insurgent_id},
        "trials": len(rows),
        "summary": summarize(rows),
        "rows": rows,
        "interpretation": "The expected hazard is read from each live trial; no scalar multiplier is fitted. Detection, same-microzone proximity, readiness/availability, and contact_rate are varied independently.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "controlled_contact_microworld.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"trials": len(rows), "output": str(OUT / "controlled_contact_microworld.json")}))


if __name__ == "__main__":
    main()
