import json
import os
import pathlib
import subprocess
import tempfile

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
import pineland_sim.information as information_module

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0, output_mode="calibration", seed=0)
config = SimulationConfig.from_dict(base)
world = generate_pineland(config)
simulation = Simulation(world)

_original_fuse_control = information_module._fuse_control


def _trace_fuse_control(world, observation, recipient_id, time, weight):
    if (
        observation.source_id == "C000069"
        and observation.locality_id == "D14-L01"
        and abs(float(time) - 8.25) < 1e-9
    ):
        key = (recipient_id, observation.target_actor_id, observation.locality_id)
        prior = world.control_beliefs.get(key)
        print(
            "PY_FUSE",
            "recipient", recipient_id,
            "target", observation.target_actor_id,
            "type", observation.source_type,
            "obs_time", repr(observation.timestamp),
            "quality", repr(observation.quality),
            "confidence", repr(observation.confidence),
            "weight", repr(weight),
            "weight_hex", float(weight).hex(),
            "trust", repr(information_module.source_trust(
                world, observation.observer_actor_id, observation.source_type,
                observation.locality_id, observation.source_id,
            )),
            "language", repr(information_module.language_comprehension(
                world, observation.observer_actor_id, observation.locality_id,
                observation.source_type, observation.source_id,
            )),
            "control", [float(value).hex() for value in observation.estimated_value["control"].values()],
            "prior_conf", repr(prior.confidence) if prior else None,
            "prior_conf_hex", prior.confidence.hex() if prior else None,
            "prior_updated", repr(prior.updated_at) if prior else None,
            "prior_contra", repr(prior.contradiction_index) if prior else None,
        )
        history_key = (
            observation.target_actor_id,
            observation.locality_id,
            observation.observation_type,
        )
        print(
            "PY_HISTORY",
            list(world.observation_source_index.get(history_key, ())),
        )
        history = world.observation_source_index.get(history_key, ())
        print(
            "PY_CORR",
            information_module._corroboration_weight(
                history,
                observation.timestamp,
                observation.source_id,
                world.config.information.source_correlation.get(
                    observation.source_type, 0.5,
                ),
            ),
            "PY_UNIQUE",
            list(dict.fromkeys(
                source
                for stamp, source in reversed(history)
                if stamp >= observation.timestamp - 3.0
                and source != observation.source_id
            )),
        )
    result = _original_fuse_control(world, observation, recipient_id, time, weight)
    if (
        observation.source_id == "C000069"
        and observation.locality_id == "D14-L01"
        and abs(float(time) - 8.25) < 1e-9
    ):
        key = (recipient_id, observation.target_actor_id, observation.locality_id)
        post = world.control_beliefs.get(key)
        print(
            "PY_FUSE_POST",
            "recipient", recipient_id,
            "confidence", repr(post.confidence) if post else None,
            "confidence_hex", post.confidence.hex() if post else None,
            "updated", repr(post.updated_at) if post else None,
            "contra", repr(post.contradiction_index) if post else None,
            "evidence", post.evidence_count if post else None,
        )
    return result


information_module._fuse_control = _trace_fuse_control
simulation.run(until=10.0, max_events=561)

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
expected = []
for organization in organization_ids:
    for locality in locality_ids:
        base_belief = world.beliefs[(organization, locality)]
        expected.append(((organization_index[organization], organization_index["insurgent"], locality_index[locality], 0), base_belief.confidence))
        target = "insurgent" if organization == "insurgent" else "government"
        opposing = "government" if organization == "insurgent" else "insurgent"
        expected.append(((organization_index[organization], organization_index[target], locality_index[locality], 1), world.control_beliefs[(organization, target, locality)].confidence))
        expected.append(((organization_index[organization], organization_index[opposing], locality_index[locality], 2), world.control_beliefs[(organization, opposing, locality)].confidence))
for observer, target, locality in dynamic:
    expected.append(((dynamic_observer_code(observer), organization_index[target], locality_index[locality], 3), world.control_beliefs[(observer, target, locality)].confidence))

with tempfile.TemporaryDirectory(prefix="pineland-belief-debug-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    environment = os.environ.copy()
    environment["PINELAND_CERT_DEBUG"] = "1"
    environment["PINELAND_INFO_TRACE"] = "1"
    environment["PINELAND_HISTORY_TRACE"] = "1"
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "10",
            "--max-events", "561",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
native_payload = json.loads(completed.stdout)
print("NATIVE_TRACE")
for line in completed.stderr.splitlines():
    if (
        "NATIVE_CONTROL" in line
        or "HISTORY_TRACE" in line
        or "PATROL_ID" in line
    ):
        print(line)
native_rows = native_payload["debug_beliefs"]
actual = [
    ((row["observer"], row["target"], row["locality"], row["kind"]), row["confidence"])
    for row in native_rows
]
print("times", simulation.world.time, native_payload["actual_time"], "counts", len(expected), len(actual))
print("first key mismatch", next(((index, left[0], right[0]) for index, (left, right) in enumerate(zip(expected, actual)) if left[0] != right[0]), None))
confidence_mismatches = []
for index, (left, right) in enumerate(zip(expected, actual)):
    if left[1] != right[1]:
        confidence_mismatches.append((index, left[0], left[1], right[1], float(left[1]).hex(), float(right[1]).hex()))
print("confidence mismatch count", len(confidence_mismatches))
print("confidence mismatches first", confidence_mismatches[:20])
print("semantic mismatches", [
    (row[0], next((semantic for semantic in dynamic if dynamic_observer_code(semantic[0]) == row[1][0]), None))
    for row in confidence_mismatches
])
