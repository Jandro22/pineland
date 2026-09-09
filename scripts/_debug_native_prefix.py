import json
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
base = json.loads((root / "scenarios" / "baseline.json").read_text())
base.update(agent_count=300, locality_count=34, burn_in_days=0.0,
            output_mode="calibration", seed=0, horizon_days=30.0)
with tempfile.TemporaryDirectory(prefix="pineland-native-prefix-") as directory:
    path = pathlib.Path(directory) / "config.json"
    path.write_text(json.dumps(base))
    result = subprocess.run(
        [str(root / "rust" / "target" / "release" / "pineland.exe"),
         "certify-trajectory", "--config", str(path), "--seed", "0",
         "--until", "30", "--max-events", "1000"],
        cwd=root, capture_output=True, text=True,
    )
    print("returncode", result.returncode)
    print("stdout", result.stdout[:20000])
    print("stderr", result.stderr[:20000])
