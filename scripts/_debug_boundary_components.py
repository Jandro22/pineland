import hashlib
import json
import pathlib
import subprocess
import sys
import struct
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from certify_rust_initialization import python_components
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

with tempfile.TemporaryDirectory(prefix="pineland-boundary-debug-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    for max_events in (4550,):
        config = SimulationConfig.from_dict(base)
        world = generate_pineland(config)
        simulation = Simulation(world)
        simulation.run(until=90.0, max_events=max_events)
        expected = python_components(world, simulation)
        completed = subprocess.run(
            [
                str(root / "rust" / "target" / "release" / "pineland.exe"),
                "certify-trajectory",
                "--config", str(config_path),
                "--seed", "0", "--until", "90",
                "--max-events", str(max_events),
            ],
            cwd=root,
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "PINELAND_TRANSITION_DEBUG": "1",
                "PINELAND_MOBILITY_TRACE": "1",
            },
            check=True,
        )
        native = json.loads(completed.stdout)
        native_debug = native["debug_transition_state"]
        local_ids = sorted(world.localities)
        print(
            "RUST_MOBILITY_TRACE",
            [
                line
                for line in completed.stderr.splitlines()
                if any(f"person={person} " in line for person in (16, 284, 285))
            ],
            flush=True,
        )
        if max_events == 4550:
            pre_config = SimulationConfig.from_dict(base)
            pre_world = generate_pineland(pre_config)
            pre_simulation = Simulation(pre_world)
            pre_simulation.run(until=90.0, max_events=4540)
            pre_persons = [
                pre_world.persons[person_id]
                for person_id in (pre_world.ordered_person_ids or sorted(pre_world.persons))
            ]
            print(
                "PY_MOBILITY_PRE",
                [
                    (
                        index,
                        person.person_id,
                        person.residence_locality_id,
                        list(pre_world.adjacency[person.residence_locality_id].items()),
                    )
                    for index, person in enumerate(pre_persons)
                    if index in (16, 284, 285)
                ],
                flush=True,
            )
            rust_diagnostics = native["diagnostics"]
            rust_offsets = rust_diagnostics["locality_edge_offsets"]
            rust_neighbors = rust_diagnostics["locality_edge_neighbors"]
            print(
                "RUST_MOBILITY_PRE",
                [
                    (
                        index,
                        person.person_id,
                        person.residence_locality_id,
                        [
                            (local_ids[value], rust_diagnostics["locality_edge_weights"][offset])
                            for offset, value in enumerate(
                                rust_neighbors[rust_offsets[local_ids.index(person.residence_locality_id)]:rust_offsets[local_ids.index(person.residence_locality_id) + 1]],
                                start=rust_offsets[local_ids.index(person.residence_locality_id)],
                            )
                        ],
                    )
                    for index, person in enumerate(pre_persons)
                    if index in (16, 284, 285)
                ],
                flush=True,
            )
            destination_values = []
            for index in (16, 284, 285):
                person = pre_persons[index]
                for destination_id, _ in pre_world.adjacency[person.residence_locality_id].items():
                    destination_index = local_ids.index(destination_id)
                    native_mask = index * len(local_ids) + destination_index
                    native_value = native_debug["people_expected_destination_control"][native_mask * 2]
                    native_present = native_debug["people_expected_destination_control_present"][native_mask]
                    python_value = person.expected_control_by_locality.get(destination_id, {}).get(
                        "government", person.expected_control.get("government", 0.5)
                    )
                    destination_values.append(
                        (index, destination_id, python_value, native_value, native_present)
                    )
            print("DESTINATION_CONTROL_VALUES", destination_values, flush=True)
            print(
                "MOBILITY_RNG_STATE",
                state_digest(pre_simulation.processes._process_rngs["mobility"]),
                native["rng_streams"].get("process:mobility"),
                flush=True,
            )
            pre_simulation.run(until=90.0, max_events=1)
            print(
                "PY_MOBILITY_POST",
                [
                    (
                        index,
                        person.person_id,
                        person.residence_locality_id,
                        int(person.displaced),
                        person.displacement_count,
                    )
                    for index, person in enumerate(pre_persons)
                    if index in (16, 284, 285)
                ],
                flush=True,
            )
        actual = dict(native["components"])
        actual["scheduler"] = native.get("scheduler")
        for key in (
            "footholds_active",
            "footholds_strength",
            "footholds_raw_signal",
            "footholds_membership",
            "footholds_embeddedness",
        ):
            print("FOOTHOLD_HASH", key, expected.get(key), actual.get(key), flush=True)
        organization_ids = list(world.organizations)
        py_strength = [
            world.local_footholds[(organization_id, locality_id)].strength
            if (organization_id, locality_id) in world.local_footholds else 0.0
            for organization_id in organization_ids
            for locality_id in local_ids
        ]
        native_strength_all = native_debug["foothold_strength"]
        native_embeddedness_all = native_debug["foothold_embeddedness"]
        print("FOOTHOLD_ORGANIZATIONS", organization_ids, flush=True)
        print("FOOTHOLD_LENGTHS", len(py_strength), len(native_strength_all), flush=True)
        print(
            "FOOTHOLD_NONZERO_PY",
            [(i, value) for i, value in enumerate(py_strength) if value > 0.0],
            flush=True,
        )
        print(
            "FOOTHOLD_NONZERO_NATIVE",
            [(i, value, native_embeddedness_all[i]) for i, value in enumerate(native_strength_all) if value > 0.0],
            flush=True,
        )
        differences = []
        for key in sorted(expected):
            if expected[key] != actual.get(key):
                differences.append((key, expected[key], actual.get(key)))
        print("BOUNDARY", max_events, "difference_count", len(differences), flush=True)
        for key, left, right in differences[:2]:
            print("DIFF", key, left, right, flush=True)
        if differences:
            py_rows = []
            for locality_id in local_ids:
                foothold = world.local_footholds.get(("insurgent", locality_id))
                py_rows.append(
                    (
                        foothold.strength if foothold is not None else 0.0,
                        foothold.raw_signal if foothold is not None else 0.0,
                        foothold.renewal_count if foothold is not None else 0,
                    )
                )
            native_strength = native_debug["foothold_strength"][6 * len(local_ids):7 * len(local_ids)]
            native_raw = native_debug["foothold_raw_signal"][6 * len(local_ids):7 * len(local_ids)]
            native_renewal = native_debug["foothold_renewal_count"][6 * len(local_ids):7 * len(local_ids)]
            rows = []
            for index, (py, rust) in enumerate(zip(py_rows, zip(native_strength, native_raw, native_renewal))):
                if py != rust:
                    rows.append((index, py, rust))
            print("FOOTHOLD_DIFFS", rows[:20], flush=True)
            print(
                "PY_FOOTHOLD_KEYS",
                [key for key in sorted(world.local_footholds) if key[0] == "insurgent"],
                flush=True,
            )
            print(
                "RUST_ACTIVE_FOOTHOLDS",
                [index for index, value in enumerate(native_debug["foothold_strength"]) if value > 0.0],
                flush=True,
            )
            print(
                "RUST_FOOTHOLD_EMBEDDEDNESS_DIFFS",
                [
                    (index, native_debug["foothold_strength"][index], native_debug["foothold_embeddedness"][index])
                    for index in range(len(native_debug["foothold_strength"]))
                    if native_debug["foothold_strength"][index] != native_debug["foothold_embeddedness"][index]
                ][:20],
                flush=True,
            )
            persons = [world.persons[person_id] for person_id in (world.ordered_person_ids or sorted(world.persons))]
            residence_rows = native_debug["residence_state"]
            person_diffs = []
            for index, person in enumerate(persons):
                rust = residence_rows[index]
                py = (int(person.displaced), person.displacement_count, person.residence_locality_id)
                actual = (int(rust["displaced"]), rust["count"], local_ids[rust["residence"]])
                if py != actual:
                    person_diffs.append((index, py, actual, person.person_id))
            print("PERSON_RESIDENCE_DIFFS", person_diffs[:40], flush=True)
