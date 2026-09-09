import json
import os
import pathlib
import subprocess
import tempfile
import sys

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from pineland_sim.organizational_state import local_organizational_embeddedness

base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
            output_mode="calibration", seed=0, horizon_days=13.0)
config = SimulationConfig.from_dict(base)
world = generate_pineland(config)
simulation = Simulation(world)
os.environ["PINELAND_COMMAND_TRACE"] = "1"
python_result = simulation.run(until=13.0, max_events=681)
print("python result", python_result.events_processed, python_result.stopped_at)
org_ids = list(world.organizations)
loc_ids = list(world.localities)
print("formation index map", list(enumerate(world.formations)))
print("python time", world.time, "events", len(world.event_log))
for oi, org in enumerate(org_ids):
    for li, loc in enumerate(loc_ids):
        foothold = world.local_footholds.get((org, loc))
        if foothold and (foothold.raw_signal or foothold.strength or foothold.cumulative_arrivals):
            print("PY", oi, li, org, loc, repr(foothold.raw_signal), repr(foothold.strength), foothold.cumulative_arrivals, foothold.renewal_count)
print("python formations")
for index, formation in enumerate(world.formations.values()):
    if formation.organization_id == "insurgent":
        print("FORMPY", index, formation.formation_id, formation.locality_id,
              formation.current_microzone_id, formation.personnel,
              formation.operational_status, formation.moving,
              getattr(formation, "movement_status", None), formation.embeddedness,
              getattr(formation, "operational_posture", "portfolio"))
print("python raw recomputed", repr(local_organizational_embeddedness(world, "insurgent", "D02-L02")))
print("python active orders", [
    (order.order_id, order.formation_id, order.destination_locality_id,
     order.status, order.execute_at, order.arrives_at)
    for order in world.movement_orders.values()
    if order.status in {"pending", "moving"}
])
print("python all orders", [
    (order.order_id, order.formation_id, order.destination_locality_id,
     order.status, order.execute_at, order.arrives_at)
    for order in world.movement_orders.values()
])
print("python matching forms", [
    (f.formation_id, f.organization_id, f.locality_id, f.personnel, f.moving,
     f.outside_pineland, f.operational_status, f.embeddedness)
    for f in world.formations.values()
    if f.organization_id == "insurgent" and f.locality_id == "D02-L02"
])

with tempfile.TemporaryDirectory(prefix="pineland-foothold-debug-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    environment = os.environ.copy()
    environment["PINELAND_CERT_DEBUG"] = "1"
    environment["PINELAND_COMMAND_TRACE"] = "1"
    completed = subprocess.run(
        [str(root / "rust" / "target" / "release" / "pineland.exe"),
         "certify-trajectory", "--config", str(config_path), "--seed", "0",
         "--until", "13", "--max-events", "681"],
        cwd=root, env=environment, capture_output=True, text=True, check=True)
native_payload = json.loads(completed.stdout)
print("native command trace")
for line in completed.stderr.splitlines():
    if line.startswith("COMMAND_"):
        print(line)
print("native top", native_payload.get("events_processed"), native_payload.get("actual_time"), native_payload.get("time"))
native = native_payload["debug_transition_state"]
print("native formations")
for row in native["formations"]:
    if row["organization"] == 6:
        print("FORM", row)
raw = native["foothold_raw_signal"]
strength = native["foothold_strength"]
arrivals = native["foothold_cumulative_arrivals"]
renewals = native["foothold_renewal_count"]
for oi, org in enumerate(org_ids):
    for li, loc in enumerate(loc_ids):
        index = oi * len(loc_ids) + li
        if raw[index] or strength[index] or arrivals[index]:
            print("RS", oi, li, org, loc, repr(raw[index]), repr(strength[index]), arrivals[index], renewals[index])
print("python and native nonzero counts", len(world.local_footholds), len(raw))
