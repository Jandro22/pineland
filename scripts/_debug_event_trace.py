import json
import os
import pathlib
import re
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0, output_mode="calibration")
with tempfile.TemporaryDirectory(prefix="pineland-trace-") as directory:
    config_path = pathlib.Path(directory) / "config.json"
    config_path.write_text(json.dumps(base))
    environment = os.environ.copy()
    environment["PINELAND_EVENT_TRACE"] = "1"
    completed = subprocess.run(
        [
            str(root / "rust" / "target" / "release" / "pineland.exe"),
            "certify-trajectory",
            "--config", str(config_path),
            "--seed", "0",
            "--until", "90", "--max-events", "3295",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
events = [line for line in completed.stderr.splitlines() if line.startswith("EVENT ")]
for line in events[-80:]:
    print(line)
print("total", len(events))
