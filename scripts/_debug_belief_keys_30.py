import json
import os
import pathlib
import subprocess
import tempfile

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(
    agent_count=300,
    locality_count=34,
    burn_in_days=0.0,
    output_mode="calibration",
    seed=0,
    horizon_days=10.0,
)
config = SimulationConfig.from_dict(base)
world = generate_pineland(config)
simulation = Simulation(world)
simulation.run(until=10.0)

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
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "10",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
native_payload = json.loads(completed.stdout)
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
expected_set = {key for key, _ in expected_dynamic}
missing = [(semantic, key) for key, semantic in expected_dynamic if key not in native_set]
extras = sorted(native_set - expected_set)
print("counts", len(python_keys), len(native_keys), "fixed", len(fixed), "dynamic", len(dynamic))
print("formation count", len(formation_ids), "post count", len(post_ids), "community count", len(community_ids))
print("formations", list(enumerate(formation_ids)))
print("missing count", len(missing), "missing first", missing[:25])
print("extra count", len(extras), "extra first", extras[:25])
print("first order mismatch", next(((index, left, right) for index, (left, right) in enumerate(zip(python_keys, native_keys)) if left != right), None))
