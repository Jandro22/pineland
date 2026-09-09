import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

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
    horizon_days=90.0,
)
seeds = [
    0, 1, 2, 3, 7, 17, 42, 99, 123, 314159, 8675309, 20260902,
    20011126, 2147483647, 4294967295, 4294967296, 281474976723001,
    9223372036854775807, 18446744073709551615, 16021456112345678901,
]
for seed in seeds:
    values = dict(base, seed=seed)
    config = SimulationConfig.from_dict(values)
    world = generate_pineland(config)
    Simulation(world).run(until=90.0)
    print(
        seed,
        "migrants", sum(person.external_state_id is not None for person in world.persons.values()),
        "diaspora", len(world.diaspora_links),
        "interventions", len(world.foreign_interventions),
        "supports", len(world.external_support),
        "formations", len(world.formations),
        "organizations", len(world.organizations),
    )
