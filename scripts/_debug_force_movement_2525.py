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
from pineland_sim import logistics

for limit in (1879, 1880):
    base = json.loads((root / "scenarios" / "baseline.json").read_text())
    base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
                output_mode="calibration", seed=0, horizon_days=30.0)
    config = SimulationConfig.from_dict(base)
    world = generate_pineland(config)
    simulation = Simulation(world)
    original_score = logistics.reallocation_destination_score

    def traced_score(world_arg, formation_arg, locality_id, **kwargs):
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
    os.environ["PINELAND_COMMAND_TRACE"] = "1"
    python_trace = io.StringIO()
    with contextlib.redirect_stderr(python_trace):
        simulation.run(until=30.0, max_events=limit)
    logistics.reallocation_destination_score = original_score
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
        completed = subprocess.run(
            [str(root / "rust" / "target" / "release" / "pineland.exe"),
             "certify-trajectory", "--config", str(config_path), "--seed", "0",
             "--until", "30", "--max-events", str(limit)],
            cwd=root, env=environment, capture_output=True, text=True, check=True,
        )
        native = json.loads(completed.stdout)["debug_transition_state"]
        print("RS_COMMAND_METRICS", [
            line for line in completed.stderr.splitlines()
            if "COMMAND_CANDIDATE" in line
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
