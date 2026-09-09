import json
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from certify_rust_initialization import python_components
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from pineland_sim.organizational_state import local_organizational_embeddedness


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
    for max_events in (4769,):
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
                    "PINELAND_EVENT_TRACE": "1",
                    "PINELAND_CERT_DEBUG": "1",
                },
            check=True,
        )
        native = json.loads(completed.stdout)
        debug = native["debug_transition_state"]
        native_zones = {
            (int(row["observer"]), int(row["zone"])): row
            for row in native.get("debug_zones", [])
        }
        organization_index = {key: index for index, key in enumerate(world.organizations)}
        microzone_index = {key: index for index, key in enumerate(world.microzones)}
        zone_diffs = []
        for (observer_id, zone_id), belief in world.zone_beliefs.items():
            key = (organization_index[observer_id], microzone_index[zone_id])
            row = native_zones.get(key)
            expected_zone = (
                belief.physical_control_estimate,
                belief.confidence,
                belief.updated_at,
                belief.evidence_count,
                belief.contradiction_index,
            )
            actual_zone = None if row is None else (
                row["estimate"], row["confidence"], row["updated_at"],
                row["evidence_count"], row["contradiction"],
            )
            if expected_zone != actual_zone:
                zone_diffs.append(((observer_id, zone_id), expected_zone, actual_zone))
        print("ZONE_BELIEF_DIFFS", len(zone_diffs), zone_diffs[:20], flush=True)
        native_beliefs = {
            (int(row["observer"]), int(row["target"]), int(row["locality"]), int(row["kind"])): row
            for row in native.get("debug_beliefs", [])
        }
        localities = list(world.localities)
        insurgent_index = organization_index["insurgent"]
        belief_diffs = []
        for observer_id in world.organizations:
            observer = organization_index[observer_id]
            primary = "insurgent" if world.organizations[observer_id].kind.value == "insurgent" else "government"
            opposing = "government" if primary == "insurgent" else "insurgent"
            for locality_id in localities:
                locality = organization_index.get(locality_id)
                del locality
                locality_code = localities.index(locality_id)
                expected_rows = [
                    (0, world.beliefs[(observer_id, locality_id)]),
                    (1, world.control_beliefs[(observer_id, primary, locality_id)]),
                    (2, world.control_beliefs[(observer_id, opposing, locality_id)]),
                ]
                for kind, belief in expected_rows:
                    target = insurgent_index if kind == 0 else organization_index[primary if kind == 1 else opposing]
                    row = native_beliefs.get((observer, target, locality_code, kind))
                    expected_belief = (
                        belief.confidence,
                        belief.updated_at,
                        belief.evidence_count,
                        belief.contradiction_index,
                        tuple(getattr(belief.control_estimate, dimension) for dimension in ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")),
                    )
                    actual_belief = None if row is None else (
                        row["confidence"], row["updated_at"], row["evidence_count"],
                        row["contradiction"], tuple(row["control"]),
                    )
                    if expected_belief != actual_belief:
                        belief_diffs.append(((observer_id, locality_id, kind), expected_belief, actual_belief))
        print("BELIEF_DIFFS", len(belief_diffs), belief_diffs[:20], flush=True)
        persons = [
            world.persons[person_id]
            for person_id in (world.ordered_person_ids or sorted(world.persons))
        ]
        py_control = []
        for person in persons:
            py_control.extend([
                person.expected_control.get("government", 0.2),
                person.expected_control.get("insurgent", 0.2),
            ])
        rust_control = debug.get("people_expected_control", [])
        control_diffs = [
            (index // 2, persons[index // 2].person_id, index % 2, left, right)
            for index, (left, right) in enumerate(zip(py_control, rust_control))
            if left != right
        ]
        print(
            "BOUNDARY",
            max_events,
            "events", native.get("events_processed"),
            "time", native.get("actual_time"),
            "belief_counts", len(world.beliefs), len(world.control_beliefs),
            native["counts"].get("belief_state"),
            len(debug.get("belief_keys", [])),
            "control_diffs", len(control_diffs),
            flush=True,
        )
        print(
            "ORGANIZATIONS_NATIVE",
            debug.get("organizations_kind"),
            debug.get("organizations_active"),
            "python_status",
            [(key, value.status) for key, value in world.organizations.items()],
            flush=True,
        )
        print("CONTROL_DIFFS", control_diffs[:40], flush=True)
        if max_events == 4768:
            local_ids = sorted(world.localities)
            python_insurgent = [
                [
                    getattr(world.localities[locality_id].control.get("insurgent"), dimension, 0.0)
                    for dimension in ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")
                ]
                for locality_id in local_ids
            ]
            native_insurgent = debug.get("insurgent_control", [])
            control_differences = []
            for index, locality_id in enumerate(local_ids):
                left = python_insurgent[index]
                right = native_insurgent[index * 7:(index + 1) * 7]
                if left != right:
                    control_differences.append((locality_id, left, right))
            print("INSURGENT_CONTROL_DIFFS", len(control_differences), control_differences[:20], flush=True)
            print(
                "NATIVE_INSURGENT_FORMATIONS",
                [
                    (
                        row.get("index"), row.get("locality"), row.get("operational_status"),
                        row.get("moving"), row.get("personnel"), row.get("availability"),
                        row.get("command"), row.get("readiness"), row.get("cohesion"),
                        row.get("supply_stock"), row.get("supply_capacity"),
                    )
                    for row in debug.get("formations", [])
                    if row.get("organization") == 6
                ],
                flush=True,
            )
            print(
                "PY_INSURGENT_FORMATIONS",
                [
                    (
                        formation_id, formation.locality_id, formation.operational_status,
                        formation.moving, formation.personnel, formation.availability,
                        formation.command, formation.readiness, formation.cohesion,
                        formation.supply_stock, formation.supply_capacity,
                    )
                    for formation_id, formation in world.formations.items()
                    if formation.organization_id == "insurgent"
                ],
                flush=True,
            )
        print("EVENT_TAIL", completed.stderr.splitlines()[-12:], flush=True)
        print("PHYS_TRACE", [line for line in completed.stderr.splitlines() if line.startswith("PHYS_")], flush=True)
        print(
            "RNG_BELIEFS",
            native.get("rng_streams", {}).get("process:beliefs"),
            flush=True,
        )
        actual = dict(native["components"])
        actual["scheduler"] = native.get("scheduler")
        local_ids = sorted(world.localities)
        organization_ids = list(world.organizations)
        py_footholds = [
            world.local_footholds.get((organization_id, locality_id))
            for organization_id in organization_ids
            for locality_id in local_ids
        ]
        rust_strength = debug.get("foothold_strength", [])
        rust_raw = debug.get("foothold_raw_signal", [])
        rust_renewal = debug.get("foothold_renewal_count", [])
        foothold_diffs = []
        for index, foothold in enumerate(py_footholds):
            python = (
                foothold.strength if foothold is not None else 0.0,
                foothold.raw_signal if foothold is not None else 0.0,
                foothold.renewal_count if foothold is not None else 0,
            )
            rust = (rust_strength[index], rust_raw[index], rust_renewal[index])
            if python != rust:
                foothold_diffs.append((
                    index,
                    organization_ids[index // len(local_ids)],
                    local_ids[index % len(local_ids)],
                    python,
                    rust,
                ))
        print("FOOTHOLD_DIFFS", len(foothold_diffs), foothold_diffs[:40], flush=True)
        if max_events == 4760:
            affected_localities = sorted({row[2] for row in foothold_diffs if row[1] == "insurgent"})
            print(
                "PY_INSURGENT_FORMATIONS",
                [
                    (
                        formation_id,
                        formation.locality_id,
                        formation.operational_status,
                        formation.moving,
                        formation.outside_pineland,
                        formation.personnel,
                        formation.embeddedness,
                    )
                    for formation_id, formation in world.formations.items()
                    if formation.organization_id == "insurgent"
                ],
                flush=True,
            )
            print(
                "RAW_CALC",
                [
                    (locality_id, local_organizational_embeddedness(world, "insurgent", locality_id))
                    for locality_id in affected_localities
                ],
                flush=True,
            )
        print(
            "NATIVE_FOOTHOLD_ACTIVE",
            [
                (index, organization_ids[index // len(local_ids)], local_ids[index % len(local_ids)], value, debug.get("foothold_updated_at", [])[index])
                for index, value in enumerate(debug.get("foothold_active", []))
                if value
            ],
            flush=True,
        )
        print(
            "FOOTHOLD_HASHES",
            expected.get("footholds_strength"),
            actual.get("footholds_strength"),
            flush=True,
        )
        differences = [
            key for key in expected
            if expected[key] != actual.get(key)
        ]
        print("DIFF_KEYS", differences[:40], "count", len(differences), flush=True)
