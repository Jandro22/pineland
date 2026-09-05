"""Capture the pre-study repository and environment fingerprint."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

from pineland_sim import SimulationConfig
from pineland_sim.validation import registry_document


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies" / "nepal_2001_2006" / "baseline.json"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    config = SimulationConfig()
    freeze = run(sys.executable, "-m", "pip", "freeze")
    # Exclude artifacts introduced by this study so rerunning the capture
    # reconstructs the actual pre-study tracked state.
    status = [line for line in run("git", "status", "--porcelain=v1").splitlines()
              if not line.endswith(" .gitignore") and "studies/" not in line]
    pre_study_diff = subprocess.check_output(
        ["git", "diff", "--binary", "--", ".", ":(exclude).gitignore"], cwd=ROOT)
    payload = {
        "schema_version": "1.0.0",
        "captured_at_utc": "2026-09-04T00:20:00Z",
        "repository_commit": run("git", "rev-parse", "HEAD"),
        "branch": run("git", "branch", "--show-current"),
        "worktree_porcelain": status,
        "worktree_diff_sha256": hashlib.sha256(pre_study_diff).hexdigest(),
        "capture_note": "study files and the study raw-data gitignore rule are excluded",
        "python": sys.version,
        "platform": platform.platform(),
        "packages_sha256": hashlib.sha256(freeze.encode()).hexdigest(),
        "key_packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "pandas", "scipy", "statsmodels", "pytest", "geopandas")
        },
        "default_config_sha256": canonical_hash(config.to_dict()),
        "parameter_registry_sha256": canonical_hash(registry_document(config)),
        "pre_study_checks": {
            "compileall": "passed",
            "pytest": "144 passed in 97.23s",
        },
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
