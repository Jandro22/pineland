import json
import contextlib
import io
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from pineland_sim import combat, logistics

for limit in (1879, 1880):
    base = json.loads((root / "scenarios" / "baseline.json").read_text())
    base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
                output_mode="calibration", seed=0, horizon_days=30.0)
    config = SimulationConfig.from_dict(base)
    world = generate_pineland(config)
    simulation = Simulation(world)
    original_score = logistics.reallocation_destination_score
    original_withdrawal = combat.choose_withdrawal_order

    def traced_score(
        world_arg, formation_arg, locality_id, original_score=original_score, **kwargs
    ):
        result = original_score(world_arg, formation_arg, locality_id, **kwargs)
        if (formation_arg.formation_id == "FDF-06"
                and abs(world_arg.time - 27.0) < 1.0e-12):
            print(
                "PY_SCORE", locality_id,
                repr(result["utility"]), repr(result["strategic"]),
                repr(result["importance"]), repr(result["travel_hours"]),
                repr(result["own_control"]), repr(result["opponent_control"]),
                repr(result["uncertainty"]),
            )
        return result

    logistics.reallocation_destination_score = traced_score

    def traced_withdrawal(
        world_arg, formation_id, time, rng, original_withdrawal=original_withdrawal
    ):
        if formation_id == "FDF-06" and abs(time - 28.0) < 1.0e-12:
            formation = world_arg.formations[formation_id]
            route_metrics = logistics._shortest_locality_route_metrics(
                world_arg, formation.locality_id, max(.05, formation.mobility)
            )
            footholds = logistics._local_armed_footholds(
                world_arg, formation.organization_id
            )
            insurgent = (
                world_arg.organizations[formation.organization_id].kind.value
                == "insurgent"
            )
            own_target, opponent_targets = logistics._reallocation_targets(
                world_arg, formation.organization_id
            )
            risk_tolerance = logistics.clamp(
                world_arg.organizations[formation.organization_id]
                .phenotype.get("risk_tolerance", .5)
            )
            rows = []
            for locality_id in sorted(world_arg.localities):
                if locality_id == formation.locality_id:
                    continue
                route, distance_km, travel_hours = route_metrics[locality_id]
                movement_cost = (
                    formation.personnel * formation.availability * distance_km
                    * world_arg.config.logistics.movement_consumption_per_person_km
                )
                if movement_cost > formation.supply_stock + 1e-12:
                    continue
                _, own_control, own_confidence = logistics._control_belief_value(
                    world_arg, formation.organization_id, own_target, locality_id,
                    legacy_fallback=True,
                )
                _, opponent_control, opponent_confidence, _ = (
                    logistics._opponent_control_belief(
                        world_arg, formation.organization_id, opponent_targets,
                        locality_id,
                    )
                )
                uncertainty = 1.0 - min(own_confidence, opponent_confidence)
                refuge = (
                    .45 * own_control + .30 * (1.0 - opponent_control)
                    + .20 * footholds.get(locality_id, 0.0) + .05 * uncertainty
                )
                sanctuary = logistics._sanctuary_access(
                    world_arg, formation.organization_id, locality_id,
                    mobility=formation.mobility,
                ) if insurgent else 0.0
                route_risk = logistics._believed_route_risk(
                    world_arg, formation.organization_id, opponent_targets, route
                )
                score = (
                    2.2 * refuge + 1.6 * sanctuary - .04 * travel_hours
                    - (1.0 - risk_tolerance) * route_risk
                )
                if locality_id in {"D01-L01", "D09-L01", "D10-L01", "D14-L01"}:
                    rows.append((
                        locality_id, repr(score), repr(own_control),
                        repr(own_confidence), repr(opponent_control),
                        repr(opponent_confidence), repr(footholds.get(locality_id, 0.0)),
                        repr(uncertainty), repr(route_risk), repr(travel_hours),
                        repr(movement_cost),
                    ))
            print("PY_WITHDRAWAL_CANDIDATES", rows)
        result = original_withdrawal(world_arg, formation_id, time, rng)
        if formation_id == "FDF-06" and abs(time - 28.0) < 1.0e-12:
            print("PY_WITHDRAWAL_SELECTED", result.destination_locality_id if result else None)
        return result

    combat.choose_withdrawal_order = traced_withdrawal
    os.environ["PINELAND_COMMAND_TRACE"] = "1"
    python_trace = io.StringIO()
    with contextlib.redirect_stderr(python_trace):
        simulation.run(until=30.0, max_events=limit)
    logistics.reallocation_destination_score = original_score
    combat.choose_withdrawal_order = original_withdrawal
    print("LIMIT", limit, "PY_TIME", world.time)
    print("PY_COMMAND_TRACE", [
        line for line in python_trace.getvalue().splitlines()
        if "time=28" in line or "formation=FDF-06" in line
    ])
    print("PY_ORDERS_LAST", [
        (order.order_id, order.formation_id, order.status,
         order.origin_locality_id, order.destination_locality_id,
         tuple(order.route),
         repr(order.issued_at), order.purpose,
         repr(order.distance_km),
         repr(order.supply_cost), repr(order.travel_time_hours),
         repr(order.execute_at), repr(order.arrives_at))
        for order in list(world.movement_orders.values())[-8:]
    ])
    py_forms = list(world.formations.values())
    print("PY_FORMS_SELECTED", [
        (i, f.formation_id, repr(f.supply_stock), repr(f.supply_capacity),
         f.moving, f.locality_id, f.current_microzone_id,
         repr(f.personnel), repr(f.availability), repr(f.mobility))
        for i, f in enumerate(py_forms)
        if i in {0, 2, 3, 5, 7, 14, 16, 18, 21}
    ])
    with tempfile.TemporaryDirectory(prefix="pineland-force-debug-") as directory:
        config_path = pathlib.Path(directory) / "config.json"
        config_path.write_text(json.dumps(base))
        environment = os.environ.copy()
        environment["PINELAND_CERT_DEBUG"] = "1"
        environment["PINELAND_COMMAND_TRACE"] = "1"
        environment["PINELAND_COMMAND_CANDIDATE_TRACE"] = "1"
        environment["PINELAND_WITHDRAWAL_TRACE"] = "1"
        completed = subprocess.run(
            [str(root / "rust" / "target" / "release" / "pineland.exe"),
             "certify-trajectory", "--config", str(config_path), "--seed", "0",
             "--until", "30", "--max-events", str(limit)],
            cwd=root, env=environment, capture_output=True, text=True, check=True,
        )
        native = json.loads(completed.stdout)["debug_transition_state"]
        print("RS_COMMAND_METRICS", [
            line for line in completed.stderr.splitlines()
            if "WITHDRAWAL_" in line or "COMMAND_CANDIDATE" in line
            or ("COMMAND_ORDER" in line and "distance_km" in line)
        ])
    print("RS_FORMS_SELECTED", [
        (row["index"], repr(row["supply_stock"]), repr(row["supply_capacity"]),
         row["moving"], row["locality"], row["microzone"],
         row["movement_status"], row.get("movement_origin"),
         row.get("movement_destination"),
         repr(row.get("movement_distance_km")),
         repr(row.get("movement_travel_hours")),
         repr(row.get("movement_supply_cost")),
         repr(row.get("movement_execute_at")),
         repr(row.get("movement_arrives_at")),
         row.get("movement_order_sequence"), row.get("movement_purpose"),
         repr(row.get("personnel")), repr(row.get("availability")),
         repr(row.get("mobility")))
        for row in native["formations"]
        if row["index"] in {0, 2, 3, 5, 7, 14, 16, 18, 21}
    ])
