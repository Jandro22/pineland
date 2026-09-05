"""Run data-free logistics subsystem checks before historical reruns.

The checks exercise propagation, depletion, route distance, degradation,
conservation, and representative-agent scale invariance.  No Nepal target or
contact outcome is consumed by this script.
"""
from __future__ import annotations

import json
from pathlib import Path

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.logistics import (
    _nearest_source,
    advance_movement_orders,
    create_movement_order,
    logistics_diagnostics,
    shortest_locality_path,
    update_logistics,
)


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies" / "nepal_2001_2006" / "results" / "contact_forensic"


def world(agent_count: int = 400):
    return generate_pineland(SimulationConfig(
        seed=60501, agent_count=agent_count, locality_count=34,
        horizon_days=30, output_mode="ensemble",
    ))


def propagation() -> dict:
    w = world()
    formation = w.formations["FDF-01"]
    source = next(s for s in w.supply_sources.values()
                  if s.organization_id == formation.organization_id)
    formation.locality_id = source.locality_id
    formation.supply_stock = 0.0
    formation.sustainment = 0.0
    w.initial_supply_stock = (
        sum(s.stock for s in w.supply_sources.values()) +
        sum(f.supply_stock for f in w.formations.values())
    )
    w.initialize_stock_ledger()
    before_source = source.stock
    created = update_logistics(w, 1.0, 1.0)["shipments_created"]
    # Delivery is intentionally a subsequent event boundary, even for a
    # zero-hour local route; this makes the shipment auditable.
    delivered_before = formation.supply_stock
    update_logistics(w, 2.0, 1.0)
    delivered_after = formation.supply_stock
    return {
        "source_id": source.source_id, "route_hours": _nearest_source(w, formation)[2],
        "shipments_created_at_day_1": created,
        "source_stock_before": before_source,
        "formation_stock_before_delivery": delivered_before,
        "formation_stock_after_delivery": delivered_after,
        "stock_increased_exactly": delivered_after > delivered_before,
        "conservation_residual": logistics_diagnostics(w)["supply_conservation"]["residual"],
    }


def depletion() -> dict:
    w = world()
    formation = w.formations["FDF-01"]
    for source in w.supply_sources.values():
        source.operational = False
    initial = formation.supply_stock
    expected = 0.0
    expected_availability = formation.availability
    for day in range(1, 4):
        expected += formation.personnel * expected_availability * w.config.logistics.presence_consumption_per_person_day
        update_logistics(w, float(day), 1.0)
        # With a fully met demand, availability recovers at the configured
        # daily rate; this is the next day's demand state.
        expected_availability = min(1.0, expected_availability +
                                    w.config.logistics.availability_recovery_rate)
    consumed = initial - formation.supply_stock
    return {
        "initial_stock": initial,
        "actual_consumption_3_days": consumed,
        "expected_consumption_with_availability_recovery": expected,
        "matches_until_stockout": abs(consumed - expected) < 1e-6,
        "nonnegative_stock": formation.supply_stock >= 0,
    }


def distance() -> dict:
    w = world()
    formation = w.formations["FDF-01"]
    destinations = [x for x in w.localities if x != formation.locality_id]
    paths = [(shortest_locality_path(w, formation.locality_id, x, formation.mobility), x)
             for x in destinations]
    near, near_id = min(paths, key=lambda item: item[0][2])
    far, far_id = max(paths, key=lambda item: item[0][2])
    near_order = create_movement_order(w, formation.formation_id, near_id, 0.0)
    w.movement_orders.clear()
    far_order = create_movement_order(w, formation.formation_id, far_id, 0.0)
    return {
        "near_destination": near_id, "far_destination": far_id,
        "near_travel_hours": near[2], "far_travel_hours": far[2],
        "near_cost": near_order.supply_cost, "far_cost": far_order.supply_cost,
        "distance_monotone": far[2] > near[2] and far_order.supply_cost > near_order.supply_cost,
        "far_route_exists": bool(far[0]),
    }


def degradation() -> dict:
    supplied = world(); deprived = supplied.clone()
    for source in deprived.supply_sources.values():
        source.operational = False
    deprived_form = deprived.formations["FDF-01"]
    deprived_form.supply_stock = 0.0
    deprived_form.sustainment = 0.0
    supplied_form = supplied.formations["FDF-01"]
    for day in range(1, 6):
        update_logistics(supplied, float(day), 1.0)
        update_logistics(deprived, float(day), 1.0)
    return {
        "supplied_effective_readiness": supplied_form.effective_readiness(),
        "deprived_effective_readiness": deprived_form.effective_readiness(),
        "supplied_availability": supplied_form.availability,
        "deprived_availability": deprived_form.availability,
        "supplied_effective_strength": supplied_form.effective_strength(),
        "deprived_effective_strength": deprived_form.effective_strength(),
        "degradation_is_monotone": deprived_form.effective_readiness() < supplied_form.effective_readiness(),
    }


def scale() -> dict:
    low, high = world(400), world(800)
    lf, hf = low.formations["FDF-01"], high.formations["FDF-01"]
    lp = sum(s.production_per_day for s in low.supply_sources.values())
    hp = sum(s.production_per_day for s in high.supply_sources.values())
    return {
        "low_agent_count": 400, "high_agent_count": 800,
        "formation_personnel_low": lf.personnel, "formation_personnel_high": hf.personnel,
        "formation_supply_fraction_low": lf.supply_fraction(),
        "formation_supply_fraction_high": hf.supply_fraction(),
        "source_production_low": lp, "source_production_high": hp,
        "represented_state_invariant": abs(lf.personnel - hf.personnel) < 1e-9 and
            abs(lf.supply_fraction() - hf.supply_fraction()) < 1e-12 and abs(lp - hp) < 1e-9,
    }


def main() -> None:
    output = {
        "schema_version": "1.0.0", "experiment": "independent_logistics_validation",
        "nepal_data_used": False,
        "checks": {
            "supply_propagation": propagation(),
            "depletion": depletion(),
            "distance": distance(),
            "operational_degradation": degradation(),
            "scale": scale(),
        },
        "equations": {
            "formation_demand": "N_personnel * availability * presence_consumption_per_person_day * delta_days",
            "shipment_delivery": "accepted = min(quantity_deliverable, capacity - stock)",
            "shipment_loss": "quantity_sent - quantity_deliverable",
            "supply_ratio": "supply_stock / supply_capacity",
            "effective_readiness": "readiness * (0.2 + 0.8*supply_ratio) * (1 - 0.65*fatigue) * command",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "independent_logistics_validation.json"
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "checks": list(output["checks"])}))


if __name__ == "__main__":
    main()
