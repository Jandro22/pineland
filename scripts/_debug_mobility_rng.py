import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation


def state_digest(rng):
    _, values, gauss_next = rng.getstate()
    payload = bytearray(struct.pack("<624I", *values[:624]))
    payload.extend(struct.pack("<I", values[624]))
    if gauss_next is None:
        payload.append(0)
    else:
        payload.append(1)
        payload.extend(struct.pack("<d", gauss_next))
    return hashlib.sha256(payload).hexdigest()


root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(
    agent_count=300,
    locality_count=34,
    burn_in_days=0.0,
    output_mode="calibration",
    seed=0,
    horizon_days=90.0,
)

with tempfile.TemporaryDirectory(prefix="pineland-mobility-rng-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    config = SimulationConfig.from_dict(base)
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.run(until=90.0, max_events=4540)
    print("PY_RNG_KEYS", sorted(simulation.processes._process_rngs), flush=True)
    print(
        "PY_RNG_DIGESTS",
        {
            f"process:{name}": state_digest(rng)
            for name, rng in sorted(simulation.processes._process_rngs.items())
        },
        flush=True,
    )
    print(
        "PY_PERSONS",
        [
            (
                index,
                person.person_id,
                person.residence_locality_id,
                int(person.displaced),
                person.displaced_since,
                person.displacement_origin_locality_id,
                person.displacement_count,
            )
            for index, person in enumerate(
                world.persons[person_id]
                for person_id in (world.ordered_person_ids or sorted(world.persons))
            )
            if index in (16, 284, 285)
        ],
        flush=True,
    )
    print(
        "PY_DISPLACED",
        [
            (
                index,
                person.person_id,
                person.residence_locality_id,
                person.home_locality_id,
                person.displaced_since,
                person.displacement_origin_locality_id,
                person.displacement_count,
            )
            for index, person in enumerate(
                world.persons[person_id]
                for person_id in (world.ordered_person_ids or sorted(world.persons))
            )
            if person.displaced
        ],
        flush=True,
    )
    os.environ["PINELAND_PY_MOBILITY_TRACE"] = "1"
    python_trace = io.StringIO()
    with contextlib.redirect_stderr(python_trace):
        simulation.run(until=90.0, max_events=1)
    python_lines = [line for line in python_trace.getvalue().splitlines() if line.startswith("MOBILITY_")]
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path), "--seed", "0", "--until", "90", "--max-events", "4541",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PINELAND_TRANSITION_DEBUG": "1",
            "PINELAND_MOBILITY_TRACE_ALL": "1",
        },
        check=True,
    )
    native = json.loads(completed.stdout)
    print("RUST_RNG_DIGESTS", native.get("rng_streams"), flush=True)
    print("RUST_DISPLACED", native["debug_transition_state"]["displaced_people"], flush=True)
    rust_lines = [line for line in completed.stderr.splitlines() if line.startswith("MOBILITY_")]
    py_decisions = []
    for line in python_lines:
        if line.startswith("MOBILITY_DECISION"):
            fields = line.split()
            py_decisions.append((fields[1], *fields[2:]))
    rust_decisions = []
    for line in rust_lines:
        if line.startswith("MOBILITY_DECISION"):
            person = re.search(r"person=(\d+)", line).group(1)
            values = [
                re.search(pattern, line).group(1)
                for pattern in (
                    r"forced_draw=([^ ]+)",
                    r"forced_probability=([^ ]+)",
                    r"voluntary_draw=([^ ]+)",
                    r"voluntary_probability=([^ ]+)",
                    r"forced=([^ ]+)",
                    r"voluntary=([^ ]+)",
                )
            ]
            rust_decisions.append((f"P{int(person):08d}", *values))
    print("TRACE_LINE_COUNTS", len(python_lines), len(rust_lines), flush=True)
    print("DECISION_COUNTS", len(py_decisions), len(rust_decisions), flush=True)
    for index, (python_row, rust_row) in enumerate(zip(py_decisions, rust_decisions)):
        if python_row != rust_row:
            print("FIRST_DECISION_DIFFERENCE", index, python_row, rust_row, flush=True)
            break
    else:
        print("DECISIONS_MATCH_PREFIX", min(len(py_decisions), len(rust_decisions)), flush=True)
    print("PY_TRACE_AROUND", python_lines[max(0, len(py_decisions) * 0):40], flush=True)
    print("RUST_TRACE_AROUND", rust_lines[:40], flush=True)
    print(
        "RUST_PERSONS",
        [
            row
            for index, row in enumerate(native["debug_transition_state"]["residence_state"])
            if index in (16, 284, 285)
        ],
        flush=True,
    )
