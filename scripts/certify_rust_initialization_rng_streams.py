"""Compare consumed Python initialization streams with native continuations.

The long-vector helper certificate proves individual CPython-compatible RNG
operations. This certificate proves the engine consumed those operations on
the same named initialization streams and retained each stream at the same
post-generation state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation
from pineland_sim import (
    foreign_affairs,
    generator,
    logistics,
    networks,
    organization_ecology,
    physical,
    political_order,
    world as world_module,
)


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
STREAMS = (
    "world-generation",
    "geography-generation",
    "force-generation",
    "logistics-world-generation",
    "physical-world-generation",
    "social-network-generation",
    "organization-ecology-generation",
    "political-order-generation",
    "foreign-system-generation",
)
BINARY = ROOT / "rust" / "target" / "release" / (
    "pineland.exe" if os.name == "nt" else "pineland"
)
MANIFEST = ROOT / "rust" / "Cargo.toml"


def state_digest(rng: random.Random) -> str:
    version, values, gauss_next = rng.getstate()
    if version != 3 or len(values) != 625:
        raise AssertionError("unexpected CPython RNG state shape")
    payload = bytearray(struct.pack("<624I", *values[:624]))
    payload.extend(struct.pack("<I", values[624]))
    if gauss_next is None:
        payload.append(0)
    else:
        payload.append(1)
        payload.extend(struct.pack("<d", gauss_next))
    return hashlib.sha256(payload).hexdigest()


def captured_initialization_streams(config: SimulationConfig) -> dict[str, str]:
    captured: dict[str, list[random.Random]] = {}

    def hook(hooked_config: SimulationConfig, stream: str) -> random.Random:
        rng = original(hooked_config, stream)
        captured.setdefault(stream, []).append(rng)
        return rng

    original = world_module.seeded_initialization_rng
    modules = (
        generator,
        networks,
        logistics,
        physical,
        world_module,
    )
    previous = {module: getattr(module, "seeded_initialization_rng") for module in modules}
    for module in modules:
        setattr(module, "seeded_initialization_rng", hook)
    try:
        world = generate_pineland(config)
        simulation = Simulation(world)
        simulation.initialize()
    finally:
        for module, value in previous.items():
            setattr(module, "seeded_initialization_rng", value)

    result: dict[str, str] = {}
    for stream in STREAMS:
        values = captured.get(stream, [])
        if len(values) != 1:
            raise AssertionError(f"expected one Python {stream} stream, found {len(values)}")
        result[stream] = state_digest(values[0])
    return result


def native_streams(binary: Path, config: SimulationConfig) -> dict[str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(config.to_dict(), handle, sort_keys=True, separators=(",", ":"))
        path = Path(handle.name)
    try:
        completed = subprocess.run(
            [
                str(binary),
                "certify-initialization",
                "--config",
                str(path),
                "--seed",
                str(config.seed),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        path.unlink(missing_ok=True)
    return json.loads(completed.stdout)["rng_streams"]


def binary_path() -> Path:
    if BINARY.is_file():
        return BINARY
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
    return BINARY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scenarios" / "baseline.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.config.read_text(encoding="utf-8"))
    base.update(agent_count=300, locality_count=34, burn_in_days=0.0, output_mode="calibration")
    binary = binary_path()
    rows = []
    mismatches = []
    for seed in SEEDS:
        config = SimulationConfig.from_dict({**base, "seed": seed})
        expected = captured_initialization_streams(config)
        actual = native_streams(binary, config)
        differences = {
            stream: {"python": expected[stream], "rust": actual.get(stream)}
            for stream in STREAMS
            if expected[stream] != actual.get(stream)
        }
        row = {"seed": seed, "status": "passed" if not differences else "failed", "mismatches": differences}
        rows.append(row)
        if differences:
            mismatches.append(row)
    certificate = {
        "schema": "pineland-initialization-rng-stream-certificate-v1",
        "status": "passed" if not mismatches else "failed",
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "seed_count": len(SEEDS),
        "streams": list(STREAMS),
        "rows": rows,
        "mismatch_count": len(mismatches),
        "gate": "zero post-initialization stream mismatches required",
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
