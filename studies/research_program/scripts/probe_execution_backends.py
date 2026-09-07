"""Report available execution accelerators without activating any of them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.execution_views import runtime_acceleration_capabilities
from pineland_sim.performance import runtime_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "schema_version": "pineland.performance.backend_probe.v1",
        "scientific_status": "execution-only",
        "runtime": runtime_manifest(),
        "capabilities": runtime_acceleration_capabilities(),
        "promotion_rule": (
            "native/JIT/GPU/free-threaded backends require profiler evidence "
            "and exact or preregistered distributional equivalence"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["capabilities"], sort_keys=True))


if __name__ == "__main__":
    main()
