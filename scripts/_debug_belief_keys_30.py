import json
import json
import os
import pathlib
import random
import re
import subprocess
import tempfile
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
import pineland_sim.foreign_affairs as foreign_affairs
import pineland_sim.information as information

_original_foreign_belief_update = foreign_affairs._foreign_belief_update


def _trace_foreign_belief_update(world, state, time, rng):
    probe = random.Random()
    probe.setstate(rng.getstate())
    direct = random.Random()
    direct.setstate(rng.getstate())
    print(
        "PY_FOREIGN_PRE",
        state.state_id,
        "next_random", repr(probe.random()),
        "next_normal", repr(probe.normalvariate(0.0, 1.0)),
        "direct_normal", repr(direct.normalvariate(0.0, 1.0)),
    )
    return _original_foreign_belief_update(world, state, time, rng)


foreign_affairs._foreign_belief_update = _trace_foreign_belief_update

_original_fuse_control_immediate = information._fuse_control_immediate


def _trace_fuse_control_immediate(world, observation, recipient_id, time, weight):
    if (
        recipient_id == "PRF-17"
        and observation.target_actor_id == "insurgent"
        and observation.locality_id == "D08-L03"
    ):
        print(
            "PY_PRF17_CONTROL",
            repr(time),
            observation.source_id,
            observation.source_type,
            observation.observer_actor_id,
            observation.observer_node_id,
            repr(weight),
        )
    return _original_fuse_control_immediate(
        world, observation, recipient_id, time, weight
    )


information._fuse_control_immediate = _trace_fuse_control_immediate

_original_observe_from_source = information._observe_from_source
_python_source_trace = []


def _trace_observe_from_source(*args, **kwargs):
    time = args[6] if len(args) > 6 else kwargs.get("time")
    source_id = args[3] if len(args) > 3 else kwargs.get("source_id")
    source_type = args[4] if len(args) > 4 else kwargs.get("source_type")
    rng = args[7] if len(args) > 7 else kwargs.get("rng")
    if time is not None and abs(time - 49.0) < 1.0e-9:
        probe = random.Random()
        probe.setstate(rng.getstate())
        before = probe.random()
        result = _original_observe_from_source(*args, **kwargs)
        after_probe = random.Random()
        after_probe.setstate(rng.getstate())
        _python_source_trace.append(
            (
                source_id,
                source_type,
                args[1] if len(args) > 1 else kwargs.get("observer_actor_id"),
                args[5] if len(args) > 5 else kwargs.get("locality_id"),
                before,
                after_probe.random(),
            )
        )
        return result
    return _original_observe_from_source(*args, **kwargs)


information._observe_from_source = _trace_observe_from_source

_original_observe_target = information.observe_target
_original_observe_control = information.observe_control


def _trace_observe_target(*args, **kwargs):
    source_id = args[3] if len(args) > 3 else kwargs.get("source_id")
    observer = args[1] if len(args) > 1 else kwargs.get("observer_actor_id")
    time = args[7] if len(args) > 7 else kwargs.get("time")
    rng = args[8] if len(args) > 8 else kwargs.get("rng")
    if source_id == "C000038" and observer == "insurgent" and abs(time - 49.0) < 1.0e-9:
        probe = random.Random()
        probe.setstate(rng.getstate())
        before = probe.random()
        result = _original_observe_target(*args, **kwargs)
        after_probe = random.Random()
        after_probe.setstate(rng.getstate())
        print(
            "PY_TARGET_C038",
            repr(before),
            result.observation_type if result else None,
            result.estimated_value if result else None,
            repr(after_probe.random()),
        )
        print("PY_TARGET_C038_ARGS", args[6], args[9] if len(args) > 9 else None)
        return result
    return _original_observe_target(*args, **kwargs)


def _trace_observe_control(*args, **kwargs):
    source_id = args[3] if len(args) > 3 else kwargs.get("source_id")
    observer = args[1] if len(args) > 1 else kwargs.get("observer_actor_id")
    time = args[7] if len(args) > 7 else kwargs.get("time")
    rng = args[8] if len(args) > 8 else kwargs.get("rng")
    if source_id == "C000038" and observer == "insurgent" and abs(time - 49.0) < 1.0e-9:
        probe = random.Random()
        probe.setstate(rng.getstate())
        before = probe.random()
        result = _original_observe_control(*args, **kwargs)
        after_probe = random.Random()
        after_probe.setstate(rng.getstate())
        print("PY_CONTROL_C038", repr(before), repr(after_probe.random()))
        return result
    return _original_observe_control(*args, **kwargs)


information.observe_target = _trace_observe_target
information.observe_control = _trace_observe_control

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
config = SimulationConfig.from_dict(base)
world = generate_pineland(config)
simulation = Simulation(world)
simulation.run(until=90.0, max_events=3553)
person_order = list(world.ordered_person_ids or sorted(world.persons))
person_rows = [world.persons[person_id] for person_id in person_order]
tracked_person_before = person_rows[214]
simulation.run(until=90.0, max_events=1)
tracked_person_after = person_rows[214]

organization_ids = list(world.organizations)
locality_ids = list(world.localities)
organization_index = {value: index for index, value in enumerate(organization_ids)}
locality_index = {value: index for index, value in enumerate(locality_ids)}
formation_ids = list(world.formations)
formation_index = {value: index for index, value in enumerate(formation_ids)}
post_ids = list(world.security_posts)
post_index = {value: index for index, value in enumerate(post_ids)}
community_ids = sorted(world.social_communities)
auxiliary_ids = sorted(
    set(community_ids)
    | {f"ADMIN:{locality}" for locality in locality_ids}
    | {f"ELITE:{community}" for community in community_ids}
    | {f"ELITE-CAP:{locality}" for locality in locality_ids}
    | {f"INTERPRETER-CAP:{locality}" for locality in locality_ids}
)
auxiliary_index = {value: index for index, value in enumerate(auxiliary_ids)}
command_ids = sorted(f"CMD:{organization}" for organization in organization_ids)
command_index = {value: index for index, value in enumerate(command_ids)}

def dynamic_observer_code(observer_id):
    if observer_id in formation_index:
        return len(organization_ids) + formation_index[observer_id]
    if observer_id in post_index:
        return len(organization_ids) + len(formation_ids) + post_index[observer_id]
    if observer_id in auxiliary_index:
        return len(organization_ids) + len(formation_ids) + len(post_ids) + auxiliary_index[observer_id]
    if observer_id in command_index:
        return len(organization_ids) + len(formation_ids) + len(post_ids) + len(auxiliary_ids) + command_index[observer_id]
    raise KeyError(observer_id)

fixed = {
    (organization, target, locality)
    for organization in organization_ids
    for locality in locality_ids
    for target in (
        "insurgent" if organization == "insurgent" else "government",
        "government" if organization == "insurgent" else "insurgent",
    )
}
dynamic = sorted(
    (key for key in world.control_beliefs if key not in fixed),
    key=lambda key: (
        dynamic_observer_code(key[0]),
        organization_index[key[1]],
        locality_index[key[2]],
    ),
)
python_keys = [
    (organization_index[organization], organization_index[target], locality_index[locality], kind)
    for organization in organization_ids
    for locality in locality_ids
    for target, kind in (
        ("insurgent", 0),
        (("insurgent" if organization == "insurgent" else "government"), 1),
        (("government" if organization == "insurgent" else "insurgent"), 2),
    )
]
python_keys.extend(
    (dynamic_observer_code(observer), organization_index[target], locality_index[locality], 3)
    for observer, target, locality in dynamic
)

with tempfile.TemporaryDirectory(prefix="pineland-key-debug-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    environment = os.environ.copy()
    environment["PINELAND_CERT_DEBUG"] = "1"
    environment["PINELAND_FOREIGN_TRACE"] = "1"
    environment["PINELAND_PRF17_TRACE"] = "1"
    environment["PINELAND_SOCIAL_TRACE"] = "1"
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "90",
            "--max-events", "3554",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    completed_before = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "90",
            "--max-events", "3553",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
native_payload = json.loads(completed.stdout)
native_before_payload = json.loads(completed_before.stdout)
python_affinity = [
    person.insurgent_affinity.get(organization_id, 0.0)
    for person in person_rows
    for organization_id in organization_ids
]
native_affinity = native_payload["debug_transition_state"]["people_insurgent_affinity"]
affinity_differences = [
    (index, expected, actual)
    for index, (expected, actual) in enumerate(zip(python_affinity, native_affinity))
    if expected != actual
]
print(
    "tracked person 214",
    tracked_person_before.person_id,
    "before",
    tracked_person_before.public_behavior,
    tracked_person_before.organization_id,
    tracked_person_before.insurgent_affinity,
    "after",
    tracked_person_after.public_behavior,
    tracked_person_after.organization_id,
    tracked_person_after.insurgent_affinity,
)
native_people_behavior = native_payload["debug_transition_state"]["people_public_behavior"]
native_people_organization = native_payload["debug_transition_state"]["people_organization"]
behavior_codes = {
    "neutral": 0,
    "insurgent_sympathy": 1,
    "armed_participation": 2,
    "government_cooperation": 3,
    "party_participation": 4,
    "civil_society": 5,
    "protest": 6,
    "inactive": 7,
    "migration": 8,
}
python_people_behavior = [
    behavior_codes[person.public_behavior] for person in person_rows
]
behavior_differences = [
    (index, expected, actual)
    for index, (expected, actual) in enumerate(
        zip(python_people_behavior, native_people_behavior)
    )
    if expected != actual
]
print(
    "native tracked person 214",
    native_people_behavior[214],
    native_people_organization[214],
    native_affinity[214 * len(organization_ids):(214 + 1) * len(organization_ids)],
)
print(
    "native tracked person 214 before",
    native_before_payload["debug_transition_state"]["people_public_behavior"][214],
    native_before_payload["debug_transition_state"]["people_organization"][214],
    native_before_payload["debug_transition_state"]["people_insurgent_affinity"][
        214 * len(organization_ids):(214 + 1) * len(organization_ids)
    ],
)
print("behavior differences", len(behavior_differences), behavior_differences[:10])
print(
    "affinity lengths",
    len(python_affinity),
    len(native_affinity),
    "differences",
    len(affinity_differences),
    "first",
    affinity_differences[:10],
)
native_keys = [
    (row["observer"], row["target"], row["locality"], row["kind"])
    for row in native_payload["debug_transition_state"]["belief_keys"]
]
expected_dynamic = []
for observer, target, locality in dynamic:
    expected_dynamic.append(
        (
            (dynamic_observer_code(observer), organization_index[target], locality_index[locality], 3),
            (observer, target, locality),
        )
    )
native_set = set(native_keys)
expected_set = set(python_keys)
missing = sorted(expected_set - native_set)
extras = sorted(native_set - expected_set)
print(
    "events",
    native_payload.get("events_processed"),
    "counts",
    len(python_keys),
    len(native_keys),
    "fixed",
    len(fixed),
    "dynamic",
    len(dynamic),
)
print(
    "python foreign",
    [
        (
            key,
            belief.government_control_estimate,
            belief.insurgent_presence_estimate,
            belief.confidence,
            belief.updated_at,
        )
        for key, belief in world.foreign_beliefs.items()
    ],
)
print("native foreign trace")
for line in completed.stderr.splitlines():
    if line.startswith("FOREIGN_"):
        print(line)
print("native PRF-17 trace")
native_source_trace = []
for line in completed.stderr.splitlines():
    if (
        line.startswith("PRF17_")
        or line.startswith("SOURCE_TRACE")
        or line.startswith("SOURCE_END")
        or line.startswith("TARGET_C038")
        or line.startswith("CONTROL_C038")
        or line.startswith("SOCIAL_TRACE")
        or line.startswith("SOCIAL_POST")
    ):
        print(line)
    if line.startswith("SOURCE_TRACE"):
        match = re.search(
            r"source=(\S+) time=\S+ observer=(\d+) type=(\S+) locality=(\d+) draw=(\S+)",
            line,
        )
        if match:
            native_source_trace.append(
                (
                    match.group(1),
                    match.group(3),
                    int(match.group(2)),
                    int(match.group(4)),
                    float(match.group(5)),
                )
            )
    if line.startswith("SOURCE_END"):
        match = re.search(
            r"source=(\S+) type=(\S+) locality=(\d+) next=(\S+)",
            line,
        )
        if match:
            for row_index, row in enumerate(native_source_trace):
                if row[0] == match.group(1) and row[1] == match.group(2) and row[3] == int(match.group(3)) and len(row) == 5:
                    native_source_trace[row_index] = (*row, float(match.group(4)))
                    break
print("source trace lengths", len(_python_source_trace), len(native_source_trace))
for index, (python_row, native_row) in enumerate(
    zip(_python_source_trace, native_source_trace)
):
    normalized_python = (
        python_row[0],
        python_row[1],
        organization_index.get(python_row[2], -1),
        locality_index.get(python_row[3], -1),
        python_row[4],
        python_row[5],
    )
    if (
        normalized_python[:4] != native_row[:4]
        or abs(normalized_python[4] - native_row[4]) > 1.0e-15
        or len(native_row) < 6
        or abs(normalized_python[5] - native_row[5]) > 1.0e-15
    ):
        print("first source trace mismatch", index, normalized_python, native_row)
        break
else:
    print("source trace common prefix exact", len(_python_source_trace))
if native_source_trace:
    for index in range(92, min(106, len(native_source_trace), len(_python_source_trace))):
        python_row = _python_source_trace[index]
        print("source trace row", index, python_row, native_source_trace[index])
print("formation count", len(formation_ids), "post count", len(post_ids), "community count", len(community_ids))
print("formations", list(enumerate(formation_ids)))
print("python formation rows", [(index, formation_id, world.formations[formation_id].organization_id,
                                  world.formations[formation_id].locality_id)
                                 for index, formation_id in enumerate(formation_ids)])
print("native formation rows", native_payload["debug_transition_state"].get("formations", []))
print("missing count", len(missing), "missing first", missing[:25])
print("extra count", len(extras), "extra first", extras[:25])
print("missing dynamic identities", [item for item in expected_dynamic if item[0] in set(missing)][:25])
print("native dynamic identities", [item for item in expected_dynamic if item[0] in set(native_keys)][:10])
print("first order mismatch", next(((index, left, right) for index, (left, right) in enumerate(zip(python_keys, native_keys)) if left != right), None))
