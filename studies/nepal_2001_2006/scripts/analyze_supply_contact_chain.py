"""Reconstruct the logistics-to-contact causal chain for one frozen case run.

This diagnostic records every formation at each logistics update and joins the
contact-denial records by formation.  It is descriptive: it does not alter the
model equations, fit parameters, or consume historical target outcomes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.logistics import _nearest_source
from pineland_sim.simulation import Simulation


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "results" / "contact_forensic"
CASE = STUDY / "config" / "case_environment.json"
START = date(2001, 11, 26)


def initial_snapshot(world) -> tuple[list[dict], list[dict]]:
    forms = []
    for f in sorted(world.formations.values(), key=lambda x: x.formation_id):
        source, route, hours = _nearest_source(world, f)
        forms.append({
            "formation_id": f.formation_id, "organization_id": f.organization_id,
            "locality_id": f.locality_id, "personnel": f.personnel,
            "supply_stock": f.supply_stock, "supply_capacity": f.supply_capacity,
            "supply_ratio": f.supply_fraction(), "initial_days_of_supply": (
                f.supply_stock / max(1e-12, f.personnel * f.availability *
                                     world.config.logistics.presence_consumption_per_person_day)
            ),
            "readiness": f.readiness, "effective_readiness": f.effective_readiness(),
            "availability": f.availability, "mobility": f.mobility,
            "nearest_source_id": source.source_id if source else None,
            "route": route, "travel_hours": hours,
        })
    sources = []
    for s in sorted(world.supply_sources.values(), key=lambda x: x.source_id):
        district = world.districts[world.localities[s.locality_id].district_id]
        sources.append({
            "source_id": s.source_id, "organization_id": s.organization_id,
            "locality_id": s.locality_id, "container_id": district.district_id,
            "catchment_population": district.population,
            "stock": s.stock, "capacity": s.capacity,
            "production_per_day": s.production_per_day, "operational": s.operational,
        })
    return forms, sources


def run() -> dict:
    case = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(seed=20_011_126, agent_count=750, locality_count=75,
                              horizon_days=365, output_mode="ensemble")
    world = generate_pineland(config, empirical_geography=case)
    initial_forms, initial_sources = initial_snapshot(world)
    cfg = world.config.logistics
    initial_demand = sum(f.personnel * f.availability * cfg.presence_consumption_per_person_day
                         for f in world.formations.values())
    corrected_production = sum(s.production_per_day for s in world.supply_sources.values())
    locality_basis_production = sum(
        min(
            max(5_000.0, world.localities[s.locality_id].population * cfg.source_capacity_per_resident),
            max(5_000.0, world.localities[s.locality_id].population * cfg.source_capacity_per_resident)
        ) * cfg.source_daily_production_fraction
        for s in world.supply_sources.values()
    )
    # The expression above is intentionally explicit: under the pre-repair
    # adapter, source capacity and production were based on hub-locality
    # population rather than container catchment population.
    locality_basis_production = sum(
        max(5_000.0, world.localities[s.locality_id].population * cfg.source_capacity_per_resident)
        * cfg.source_daily_production_fraction
        for s in world.supply_sources.values()
    )

    traces: list[dict] = []
    original_update = __import__("pineland_sim.processes", fromlist=["update_logistics"]).update_logistics
    process_module = __import__("pineland_sim.processes", fromlist=["update_logistics"])

    def traced_update(state, time, delta_days):
        before_forms = {
            f.formation_id: {
                "stock": f.supply_stock, "capacity": f.supply_capacity,
                "personnel": f.personnel, "availability": f.availability,
                "readiness": f.readiness, "supply_ratio": f.supply_fraction(),
            }
            for f in state.formations.values()
        }
        before_sources = {s.source_id: {"stock": s.stock, "capacity": s.capacity}
                          for s in state.supply_sources.values()}
        flow_start = len(state.resource_flows)
        result = original_update(state, time, delta_days)
        new_flows = state.resource_flows[flow_start:]
        by_formation: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for flow in new_flows:
            if flow.formation_id:
                by_formation[flow.formation_id][flow.flow_type] += flow.quantity
        for f in sorted(state.formations.values(), key=lambda x: x.formation_id):
            before = before_forms[f.formation_id]
            source, route, hours = _nearest_source(state, f)
            source_before = before_sources.get(source.source_id, {}) if source else {}
            blocked = sum(
                order.status == "blocked_supply" and order.formation_id == f.formation_id
                for order in state.movement_orders.values()
            )
            traces.append({
                "time": time, "date": (START + timedelta(days=int(time))).isoformat(), "delta_days": delta_days,
                "formation_id": f.formation_id, "organization_id": f.organization_id,
                "locality_id": f.locality_id, "stock_before": before["stock"],
                "stock_after": f.supply_stock, "capacity": f.supply_capacity,
                "personnel": before["personnel"],
                "demand": before["personnel"] * before["availability"] *
                          cfg.presence_consumption_per_person_day * delta_days,
                "consumption": sum(by_formation[f.formation_id].values()),
                "sustained_presence_consumption": by_formation[f.formation_id].get("sustained_presence", 0.0),
                "incoming_delivery": by_formation[f.formation_id].get("delivery", 0.0),
                "shipment_departure": by_formation[f.formation_id].get("shipment_departure", 0.0),
                "failed_or_blocked_movement_orders": blocked,
                "source_id": source.source_id if source else None,
                "source_stock_before": source_before.get("stock"),
                "source_stock_after": source.stock if source else None,
                "source_capacity": source.capacity if source else None,
                "route": route, "travel_hours": hours,
                "route_state": "available" if source else "no_operational_source",
                "supply_ratio_before": before["supply_ratio"],
                "supply_ratio_after": f.supply_fraction(),
                "readiness_before": before["readiness"],
                "readiness_after": f.readiness,
                "availability_before": before["availability"],
                "availability_after": f.availability,
                "contact_supply_threshold": (
                    state.config.combat.contact_ammunition_floor
                    if state.config.combat.contact_supply_rule == "ammunition_floor" else 0.0
                ),
                "contact_supply_rule": state.config.combat.contact_supply_rule,
            })
        return result

    process_module.update_logistics = traced_update
    try:
        final_world = Simulation(world).run().world
    finally:
        process_module.update_logistics = original_update

    contact_denials: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in final_world.contact_funnel_records:
        reason = record.get("failure_reason", "unknown")
        for formation_id in (record.get("selected_government_formation_id"),
                             record.get("selected_insurgent_formation_id")):
            if formation_id:
                contact_denials[formation_id][reason] += 1
    by_formation = {}
    for f in final_world.formations.values():
        rows = [x for x in traces if x["formation_id"] == f.formation_id]
        by_formation[f.formation_id] = {
            "updates": len(rows),
            "minimum_supply_ratio": min((x["supply_ratio_after"] for x in rows), default=f.supply_fraction()),
            "minimum_readiness": min((x["readiness_after"] for x in rows), default=f.readiness),
            "minimum_availability": min((x["availability_after"] for x in rows), default=f.availability),
            "total_presence_consumption": sum(x["sustained_presence_consumption"] for x in rows),
            "total_incoming_delivery": sum(x["incoming_delivery"] for x in rows),
            "total_shipment_departure": sum(x["shipment_departure"] for x in rows),
            "contact_denials": dict(contact_denials.get(f.formation_id, {})),
        }
    return {
        "schema_version": "1.0.0", "experiment": "supply_to_contact_chain_reconstruction",
        "nepal_data_used": False, "seed": config.seed, "horizon_days": config.horizon_days,
        "configuration": {
            "formation_supply_days": cfg.formation_supply_days,
            "initial_supply_fraction": cfg.initial_supply_fraction,
            "presence_consumption_per_person_day": cfg.presence_consumption_per_person_day,
            "source_capacity_per_resident": cfg.source_capacity_per_resident,
            "source_daily_production_fraction": cfg.source_daily_production_fraction,
            "resupply_trigger_fraction": cfg.resupply_trigger_fraction,
            "resupply_target_fraction": cfg.resupply_target_fraction,
            "logistics_interval_days": config.intervals.logistics,
            "contact_supply_rule": config.combat.contact_supply_rule,
            "contact_ammunition_floor": config.combat.contact_ammunition_floor,
        },
        "units": {
            "formation_supply_stock": "abstract person-sustainment units",
            "formation_supply_capacity": "abstract person-sustainment units (person * supply_days)",
            "presence_consumption": "units/person-day",
            "source_capacity": "units/resident of source catchment",
            "source_production": "units/day",
            "formation_personnel": "represented armed personnel",
            "readiness": "dimensionless [0,1]",
            "availability": "dimensionless [0,1]",
            "supply_ratio": "dimensionless stock/capacity",
            "contact_threshold": "dimensionless supply ratio when a hard branch is selected",
        },
        "causal_chain": [
            {"function": "generate_logistics_world", "effect": "initial formation stocks/capacities, source stocks/capacities/production, command edges"},
            {"function": "update_logistics", "effect": "production, delivery, sustained-presence consumption, readiness/availability/fatigue, shipment creation"},
            {"function": "ArmedFormation.supply_fraction", "equation": "stock / capacity"},
            {"function": "ArmedFormation.effective_readiness", "equation": "readiness * (0.2 + 0.8*supply_ratio) * (1 - 0.65*fatigue) * command"},
            {"function": "ArmedFormation.available_personnel", "equation": "personnel * availability * effective_readiness unless moving/ineffective"},
            {"function": "ProcessEngine.on_contact", "effect": "spatial/detection/readiness/contact-supply policy/hazard/engagement"},
            {"function": "resolve_engagement", "effect": "combat capability, losses, combat supply expenditure, disengagement, readiness/cohesion damage"},
        ],
        "initial_formations": initial_forms, "initial_sources": initial_sources,
        "initial_demand_units_per_day": initial_demand,
        "source_production_units_per_day_after_catchment_fix": corrected_production,
        "source_production_units_per_day_under_old_hub_locality_basis": locality_basis_production,
        "production_to_initial_demand_after_catchment_fix": corrected_production / max(1e-12, initial_demand),
        "production_to_initial_demand_under_old_basis": locality_basis_production / max(1e-12, initial_demand),
        "trajectory_by_formation": by_formation,
        "trajectory_records": traces,
        "contact_denials_by_formation": {k: dict(v) for k, v in contact_denials.items()},
        "final_contact_funnel_counts": final_world.contact_funnel_counts,
        "final_logistics_diagnostics": __import__("pineland_sim.logistics", fromlist=["logistics_diagnostics"]).logistics_diagnostics(final_world),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = run()
    path = OUT / "supply_contact_chain_diagnosis.json"
    path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "formations": len(result["initial_formations"]),
                      "trajectory_records": len(result["trajectory_records"]),
                      "initial_demand": result["initial_demand_units_per_day"],
                      "production_after_fix": result["source_production_units_per_day_after_catchment_fix"],
                      "production_old_basis": result["source_production_units_per_day_under_old_hub_locality_basis"]}))


if __name__ == "__main__":
    main()
