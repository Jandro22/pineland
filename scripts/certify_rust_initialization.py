"""Compare the native initialization inventory with Python's world oracle.

This is intentionally a fail-closed gate.  It does not coerce unlike object
graphs into a passing scalar summary: the inventory names every requested
semantic category and reports the first mismatches for each predeclared seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation


SEEDS = [
    0,
    1,
    2,
    3,
    7,
    17,
    42,
    99,
    123,
    314_159,
    8_675_309,
    20_260_902,
    20_011_126,
    2_147_483_647,
    4_294_967_295,
    4_294_967_296,
    281_474_976_723_001,
    9_223_372_036_854_775_807,
    18_446_744_073_709_551_615,
    16_021_456_112_345_678_901,
]
BINARY = ROOT / "rust" / "target" / "release" / (
    "pineland.exe" if os.name == "nt" else "pineland"
)
MANIFEST = ROOT / "rust" / "Cargo.toml"


def binary_path() -> Path:
    configured = os.environ.get("PINELAND_BIN")
    binary = Path(configured) if configured else BINARY
    if not binary.is_file():
        subprocess.run(
            [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                str(MANIFEST),
                "-p",
                "pineland-cli",
            ],
            cwd=ROOT,
            check=True,
        )
    return binary


def python_inventory(config: SimulationConfig) -> dict[str, object]:
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.initialize()
    summary = world.summary()
    counts = {
        "people": summary["agents"],
        "households": summary["households"],
        "communities": summary["social_communities"],
        "organizations": summary["organizations"],
        "formations": summary["formations"],
        "posts": summary["security_posts"],
        "patrols": summary["patrols"],
        "localities": summary["localities"],
        "microzones": summary["microzones"],
        "footholds": summary["local_footholds"],
        "manpower_pools": len(world.organization_manpower_pools),
        "logistics_sources": summary["supply_sources"],
        "belief_state": len(world.beliefs) + len(world.control_beliefs),
        "scheduler": len(simulation.scheduler),
    }
    return {
        "counts": counts,
        "summary": {
            key: summary[key]
            for key in (
                "represented_population",
                "mean_government_effective_control",
                "mean_insurgent_effective_control",
                "active_insurgent_formation_personnel",
                "mean_local_foothold_strength",
            )
        },
        "configuration_hash": hashlib.sha256(
            json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def native_inventory(binary: Path, config_path: Path, seed: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(binary),
            "certify-initialization",
            "--config",
            str(config_path),
            "--seed",
            str(seed),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scenarios" / "baseline.json")
    parser.add_argument("--agent-count", type=int, default=300)
    parser.add_argument("--locality-count", type=int, default=34)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    base = json.loads(args.config.read_text(encoding="utf-8"))
    base.update(
        agent_count=args.agent_count,
        locality_count=args.locality_count,
        burn_in_days=0.0,
        output_mode="calibration",
    )
    config = SimulationConfig.from_dict(base)
    config.validate()
    binary = binary_path()
    mismatches: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(config.to_dict(), handle, sort_keys=True, separators=(",", ":"))
        config_path = Path(handle.name)
    try:
        for seed in SEEDS:
            seeded = SimulationConfig.from_dict({**config.to_dict(), "seed": seed})
            expected = python_inventory(seeded)
            actual = native_inventory(binary, config_path, seed)
            mismatching_fields = {
                key: {
                    "python": expected["counts"].get(key),
                    "rust": actual["counts"].get(key),
                }
                for key in expected["counts"]
                if expected["counts"].get(key) != actual["counts"].get(key)
            }
            row = {"seed": seed, "mismatches": mismatching_fields}
            rows.append(row)
            if mismatching_fields:
                mismatches.append(row)
    finally:
        config_path.unlink(missing_ok=True)

    certificate = {
        "schema": "pineland-initialization-parity-certificate-v1",
        "status": "passed" if not mismatches else "failed",
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "seed_count": len(SEEDS),
        "configuration": {
            "agent_count": args.agent_count,
            "locality_count": args.locality_count,
            "burn_in_days": 0.0,
        },
        "rows": rows,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "gate": "zero semantic discrepancies required",
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if mismatches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
