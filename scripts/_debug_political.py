import json
import os
import pathlib
import subprocess
import tempfile

os.environ["PINELAND_POLITICAL_TRACE"] = "1"

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
            output_mode="calibration", seed=0, horizon_days=30.0)

import sys
sys.path.insert(0, str(root / "src"))
from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation

for limit in (1995,):
    config = SimulationConfig.from_dict(base)
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.run(until=30.0, max_events=limit)
    py = [
        getattr(world.localities[locality_id].control["government"], dimension)
        for locality_id in sorted(world.localities)
        for dimension in ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")
    ]
    print("PY", limit, "time", world.time, "controls", [(i, repr(py[i])) for i in range(len(py)) if py[i] != 0.0][:12])
    print("PY_DELTA", limit, [(i, repr(py[i])) for i in range(len(py)) if i >= 34 * 7 - 30])

    with tempfile.TemporaryDirectory(prefix="pineland-political-debug-") as directory:
        config_path = pathlib.Path(directory) / "config.json"
        config_path.write_text(json.dumps(base))
        environment = os.environ.copy()
        environment["PINELAND_CERT_DEBUG"] = "1"
        environment["PINELAND_POLITICAL_TRACE"] = "1"
        completed = subprocess.run(
            [str(root / "rust" / "target" / "release" / "pineland.exe"),
             "certify-trajectory", "--config", str(config_path), "--seed", "0",
             "--until", "30", "--max-events", str(limit)],
            cwd=root, env=environment, capture_output=True, text=True, check=True,
        )
        native = json.loads(completed.stdout)["debug_transition_state"]
        print("RS_TRACE", limit, [line for line in completed.stderr.splitlines() if line.startswith("POLITICAL")])
    rs = native["government_control"]
    print("RS", limit, "controls", [(i, repr(rs[i])) for i in range(len(rs)) if rs[i] != 0.0][:12])
    print("RS_DELTA", limit, [(i, repr(rs[i])) for i in range(len(rs)) if i >= 34 * 7 - 30])
    print("DIFF", limit, [(i, repr(py[i]), repr(rs[i])) for i in range(min(len(py), len(rs))) if py[i] != rs[i]][:30])
