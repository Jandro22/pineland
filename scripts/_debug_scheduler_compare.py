import json
import os
import pathlib
import subprocess
import struct
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation

event_codes = {
    "patrol": 1, "contact_scan": 2, "command": 3,
    "force_movement": 4, "logistics": 5, "information": 6,
    "beliefs": 7, "physical_refresh": 8, "social_influence": 9,
    "mobility": 10, "recruitment": 11, "organization_ecology": 12,
    "governance": 13, "economy": 14, "political_order": 15,
    "foreign_affairs": 16, "peace_process": 17, "recording_noise": 18,
    "checkpoint": 19, "organized_action": 20, "contact": 21,
}

for limit in (1280, 1290):
    base = json.loads((root / "scenarios" / "baseline.json").read_text())
    base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
                output_mode="calibration", seed=0, horizon_days=30.0)
    config = SimulationConfig.from_dict(base)
    world = generate_pineland(config)
    simulation = Simulation(world)
    original_reschedule = Simulation._reschedule

    def traced_reschedule(self, event_type, payload, current_time):
        if event_type == "patrol" and 18.0 <= current_time <= 20.0:
            patrol = self.world.patrols.get(payload.get("patrol_id"))
            formation = self.world.formations.get(patrol.formation_id) if patrol else None
            print(
                "PY_SCHED_RESCHEDULE",
                repr(current_time), payload.get("patrol_id"),
                "next_interval", repr(payload.get("next_interval")),
                "available_at", repr(patrol.available_at if patrol else None),
                "moving", formation.moving if formation else None,
                "status", formation.operational_status if formation else None,
            )
        return original_reschedule(self, event_type, payload, current_time)

    Simulation._reschedule = traced_reschedule
    simulation.run(until=30.0, max_events=limit)
    Simulation._reschedule = original_reschedule
    python_rows = [
        {
            "time_bits": struct.unpack("<Q", struct.pack("<d", event.time))[0],
            "priority": event.priority,
            "sequence": event.sequence,
            "kind": event.event_type,
            "code": event_codes[event.event_type],
        }
        for event in simulation.scheduler.pending_events()
    ]
    with tempfile.TemporaryDirectory(prefix="pineland-scheduler-debug-") as directory:
        config_path = pathlib.Path(directory) / "config.json"
        config_path.write_text(json.dumps(base))
        environment = os.environ.copy()
        environment["PINELAND_SCHED_TRACE"] = "1"
        completed = subprocess.run(
            [str(root / "rust" / "target" / "release" / "pineland.exe"),
             "certify-trajectory", "--config", str(config_path), "--seed", "0",
             "--until", "30", "--max-events", str(limit)],
            cwd=root, env=environment, capture_output=True, text=True, check=True,
        )
    native_trace = [line for line in completed.stderr.splitlines()
                    if line.startswith("SCHED_RESCHEDULE")]
    for line in native_trace:
        print("NATIVE_" + line)
    native = json.loads(completed.stdout)
    native_rows = native["scheduler"]
    first = next(
        ((index, left, right) for index, (left, right)
         in enumerate(zip(python_rows, native_rows)) if left != right),
        None,
    )
    if first is None and len(python_rows) != len(native_rows):
        first = (min(len(python_rows), len(native_rows)),
                 len(python_rows), len(native_rows))
    print("limit", limit, "actual", native["actual_time"],
          "events", native["events_processed"], "first", first)
    if first is not None:
        index = first[0]
        print("python around", python_rows[max(0, index - 3):index + 4])
        print("native around", native_rows[max(0, index - 3):index + 4])
