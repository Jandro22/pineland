import json
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
from certify_rust_trajectory import _python
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation

base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(
    agent_count=300,
    locality_count=34,
    burn_in_days=0.0,
    output_mode="calibration",
    seed=0,
    horizon_days=90.0,
)
result = _python(SimulationConfig.from_dict(base), 90.0, 4550)
selected = {
    key: result["components"][key]
    for key in (
        "footholds_active",
        "footholds_strength",
        "footholds_raw_signal",
        "footholds_embeddedness",
        "formations_personnel",
        "formations_locality",
        "formations_moving",
        "formations_movement_status",
        "patrols_active",
        "people_locality",
        "people_residence",
        "zone_belief_confidence",
    )
}
print(json.dumps(selected, sort_keys=True))
world = generate_pineland(SimulationConfig.from_dict(base))
simulation = Simulation(world)
simulation.run(until=90.0, max_events=4550)
print(
    json.dumps(
        [
            [key, foothold.strength, foothold.raw_signal]
            for key, foothold in sorted(world.local_footholds.items())
            if foothold.strength > 0.0
        ],
        sort_keys=True,
    )
)
