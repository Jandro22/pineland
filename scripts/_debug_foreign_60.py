import json
import os
import pathlib
import random
import subprocess
import tempfile
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
import pineland_sim.foreign_affairs as foreign_affairs


original = foreign_affairs._foreign_belief_update


def trace(world, state, time, rng):
    if abs(time - 60.0) < 1.0e-9:
        probe = random.Random()
        probe.setstate(rng.getstate())
        print("PY_FOREIGN_STATE", state.state_id, "next_random", repr(probe.random()))
        for border in world.border_segments.values():
            if border.foreign_state_id != state.state_id:
                continue
            quality = foreign_affairs._interpreter_channel_quality(world, border)
            host = world.belief_view("government").locality_control(
                border.locality_id, "government", "government"
            ).physical
            noise = world.config.foreign_affairs.belief_noise * (
                1 - world.config.foreign_affairs.interpreter_effect * quality
            )
            draws = random.Random()
            draws.setstate(rng.getstate())
            first = draws.normalvariate(0.0, noise)
            second = draws.normalvariate(0.0, noise)
            belief = world.foreign_beliefs[(state.state_id, border.locality_id)]
            print(
                "PY_FOREIGN_PRE",
                state.state_id,
                border.border_id,
                border.locality_id,
                "host", repr(host),
                "quality", repr(quality),
                "noise", repr(noise),
                "prior", repr(belief.government_control_estimate),
                repr(belief.insurgent_presence_estimate),
                "normal", repr(first), repr(second),
            )
    result = original(world, state, time, rng)
    if abs(time - 60.0) < 1.0e-9:
        for border in world.border_segments.values():
            if border.foreign_state_id != state.state_id:
                continue
            belief = world.foreign_beliefs[(state.state_id, border.locality_id)]
            print(
                "PY_FOREIGN_POST",
                state.state_id,
                border.locality_id,
                repr(belief.government_control_estimate),
                repr(belief.insurgent_presence_estimate),
                repr(belief.confidence),
            )
    return result


foreign_affairs._foreign_belief_update = trace

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
simulation.run(until=90.0, max_events=4032)
simulation.run(until=90.0, max_events=1)
print(
    "PY_COUNTS",
    len(world.diaspora_links),
    len(world.external_support),
    len(world.foreign_interventions),
    [round(state.resources, 6) for state in world.foreign_states.values()],
)
for support in world.external_support:
    print("PY_SUPPORT", support)
for organization in world.organizations.values():
    print(
        "PY_ORG",
        organization.organization_id,
        repr(organization.resources),
        repr(organization.external_support),
        repr(organization.external_sanctuary),
        repr(organization.capital),
        repr(organization.phenotype),
        repr(organization.sponsor_dependence),
    )
for formation in world.formations.values():
    if formation.organization_id == "insurgent":
        print(
            "PY_FORMATION",
            formation.formation_id,
            repr(formation.quality),
            repr(formation.cohesion),
            repr(formation.supply_stock),
            repr(formation.supply_capacity),
        )

with tempfile.TemporaryDirectory(prefix="pineland-foreign-debug-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    environment = os.environ.copy()
    environment["PINELAND_FOREIGN_TRACE"] = "1"
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "90",
            "--max-events", "4033",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in completed.stderr.splitlines():
        if line.startswith("FOREIGN_"):
            print("NATIVE", line)
