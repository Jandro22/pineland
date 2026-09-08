"""Certify the native RNG against the host CPython random.Random oracle.

The Rust command emits only digests for the long vectors; this script computes
the same vectors independently in CPython and compares both result and full
MT19937 continuation state.  It is intentionally an explicit certification
entry point rather than an ordinary unit test, because it requires a built
Native binary and is part of the R2 release evidence.
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
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUST_MANIFEST = ROOT / "rust" / "Cargo.toml"
DEFAULT_BINARY = ROOT / "rust" / "target" / "release" / (
    "pineland.exe" if os.name == "nt" else "pineland"
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
DRAW_COUNT = 100_000
SAMPLE_ROUNDS = 5_000
SHUFFLE_ROUNDS = 1_000


def state_bytes(state: tuple[object, tuple[int, ...], float | None]) -> bytes:
    version, values, gauss_next = state
    if version != 3 or len(values) != 625:
        raise AssertionError(f"unexpected CPython RNG state shape: {version=}, {len(values)=}")
    payload = bytearray()
    payload.extend(struct.pack("<624I", *values[:624]))
    payload.extend(struct.pack("<I", values[624]))
    if gauss_next is None:
        payload.append(0)
    else:
        payload.append(1)
        payload.extend(struct.pack("<d", gauss_next))
    return bytes(payload)


def state_digest(rng: random.Random) -> str:
    return hashlib.sha256(state_bytes(rng.getstate())).hexdigest()


def digest_bytes(payload: bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def float_vector(seed: int, count: int, draw: Callable[[random.Random], float]) -> dict[str, str]:
    rng = random.Random(seed)
    payload = bytearray()
    for _ in range(count):
        payload.extend(struct.pack("<d", draw(rng)))
    return {"digest": digest_bytes(payload), "state_digest": state_digest(rng)}


def integer_vector(
    seed: int, count: int, draw: Callable[[random.Random], int]
) -> dict[str, str]:
    rng = random.Random(seed)
    payload = bytearray()
    for _ in range(count):
        payload.extend(struct.pack("<Q", draw(rng)))
    return {"digest": digest_bytes(payload), "state_digest": state_digest(rng)}


def sample_vector(seed: int, rounds: int) -> dict[str, str]:
    rng = random.Random(seed)
    payload = bytearray()
    for _ in range(rounds):
        for value in rng.sample(range(1_000), 25):
            payload.extend(struct.pack("<Q", value))
    return {"digest": digest_bytes(payload), "state_digest": state_digest(rng)}


def shuffle_vector(seed: int, rounds: int) -> dict[str, str]:
    rng = random.Random(seed)
    payload = bytearray()
    for _ in range(rounds):
        values = list(range(128))
        rng.shuffle(values)
        for value in values:
            payload.extend(struct.pack("<I", value))
    return {"digest": digest_bytes(payload), "state_digest": state_digest(rng)}


def reference_vectors(draws: int, sample_rounds: int, shuffle_rounds: int) -> dict[int, dict[str, dict[str, str]]]:
    weights = [0.25 + index * 0.125 for index in range(97)]
    result: dict[int, dict[str, dict[str, str]]] = {}
    for seed in SEEDS:
        operations = {
            "random": float_vector(seed, draws, lambda rng: rng.random()),
            "uniform": float_vector(seed, draws, lambda rng: rng.uniform(-17.25, 83.5)),
            "randrange": integer_vector(seed, draws, lambda rng: rng.randrange(17)),
            "choice": integer_vector(seed, draws, lambda rng: rng.choice(range(97))),
            "choices_equal": integer_vector(
                seed, draws, lambda rng: rng.choices(range(97), k=1)[0]
            ),
            "choices_weighted": integer_vector(
                seed, draws, lambda rng: rng.choices(range(97), weights=weights, k=1)[0]
            ),
            "sample": sample_vector(seed, sample_rounds),
            "shuffle": shuffle_vector(seed, shuffle_rounds),
            "gauss": float_vector(seed, draws, lambda rng: rng.gauss(1.25, 0.75)),
            "normalvariate": float_vector(
                seed, draws, lambda rng: rng.normalvariate(-2.0, 1.75)
            ),
            "lognormvariate": float_vector(
                seed, draws, lambda rng: rng.lognormvariate(0.0, 0.55)
            ),
            "expovariate": float_vector(
                seed, draws, lambda rng: rng.expovariate(1.0 / 3.75)
            ),
            "betavariate": float_vector(
                seed, draws, lambda rng: rng.betavariate(2.0, 9.0)
            ),
        }
        result[seed] = operations
    return result


def rust_binary() -> Path:
    configured = os.environ.get("PINELAND_BIN")
    binary = Path(configured) if configured else DEFAULT_BINARY
    if binary.is_file():
        return binary
    command = [
        "cargo",
        "build",
        "--release",
        "--locked",
        "--manifest-path",
        str(RUST_MANIFEST),
        "-p",
        "pineland-cli",
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    if not binary.is_file():
        raise RuntimeError(f"release binary was not produced at {binary}")
    return binary


def run_json(binary: Path, *arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [str(binary), *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"native certification command did not emit JSON: {completed.stdout[:500]}"
        ) from error


def continuation_reference(
    seed: int, draws: int
) -> tuple[dict[str, object], dict[str, str], dict[str, str]]:
    # The prefix creates a non-empty Gaussian spare cache.  That exercises the
    # part of CPython's state tuple most likely to be lost at a serialization
    # boundary.
    prefix = random.Random(seed)
    for _ in range(137):
        prefix.random()
    prefix.gauss(1.25, 0.75)
    prefix_state = prefix.getstate()
    state_document = {
        "version": 3,
        "words": list(prefix_state[1][:624]),
        "index": prefix_state[1][624],
        "gauss_next": prefix_state[2],
    }

    expected = random.Random()
    expected.setstate(prefix_state)
    first_payload = bytearray()
    for _ in range(draws):
        first_payload.extend(struct.pack("<d", expected.gauss(1.25, 0.75)))
    first = {"digest": digest_bytes(first_payload), "state_digest": state_digest(expected)}

    continuation = random.Random()
    continuation.setstate(expected.getstate())
    second_payload = bytearray()
    for _ in range(draws):
        second_payload.extend(struct.pack("<d", continuation.gauss(1.25, 0.75)))
    second = {"digest": digest_bytes(second_payload), "state_digest": state_digest(continuation)}
    return state_document, first, second


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the passed certificate JSON here")
    parser.add_argument("--draws", type=int, default=DRAW_COUNT)
    parser.add_argument("--sample-rounds", type=int, default=SAMPLE_ROUNDS)
    parser.add_argument("--shuffle-rounds", type=int, default=SHUFFLE_ROUNDS)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.draws <= 0 or args.sample_rounds <= 0 or args.shuffle_rounds <= 0:
        parser.error("draw counts must be positive")

    binary = rust_binary()
    native = run_json(
        binary,
        "certify-rng",
        "--draws",
        str(args.draws),
        "--sample-rounds",
        str(args.sample_rounds),
        "--shuffle-rounds",
        str(args.shuffle_rounds),
    )
    expected_vectors = reference_vectors(args.draws, args.sample_rounds, args.shuffle_rounds)
    native_vectors = {
        int(row["seed"]): row["operations"]
        for row in native["vectors"]  # type: ignore[index]
    }
    if sorted(native_vectors) != sorted(SEEDS):
        raise AssertionError(f"native seed list differs: {sorted(native_vectors)}")
    mismatches: list[str] = []
    for seed in SEEDS:
        expected = expected_vectors[seed]
        actual = native_vectors[seed]
        for operation, expected_value in expected.items():
            actual_value = actual[operation]
            for field in ("digest", "state_digest"):
                if actual_value[field] != expected_value[field]:
                    mismatches.append(
                        f"seed={seed} operation={operation} field={field} "
                        f"expected={expected_value[field]} actual={actual_value[field]}"
                    )
    if mismatches:
        raise AssertionError("RNG vector mismatches:\n" + "\n".join(mismatches[:20]))

    continuation_rows = []
    for seed in SEEDS:
        state_document, expected_first, expected_second = continuation_reference(seed, 10_000)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(state_document, handle, separators=(",", ":"))
            state_path = Path(handle.name)
        try:
            actual_first = run_json(
                binary,
                "certify-rng",
                "--state-file",
                str(state_path),
                "--operation",
                "gauss",
                "--draws",
                "10000",
            )
        finally:
            state_path.unlink(missing_ok=True)
        for field in ("digest", "state_digest"):
            if actual_first[field] != expected_first[field]:
                raise AssertionError(
                    f"state handoff mismatch seed={seed} field={field}: "
                    f"expected={expected_first[field]} actual={actual_first[field]}"
                )
        returned_state = actual_first["state"]
        continuation = random.Random()
        continuation.setstate(
            (
                3,
                tuple(returned_state["words"]) + (returned_state["index"],),
                returned_state["gauss_next"],
            )
        )
        payload = bytearray()
        for _ in range(10_000):
            payload.extend(struct.pack("<d", continuation.gauss(1.25, 0.75)))
        actual_second = {"digest": digest_bytes(payload), "state_digest": state_digest(continuation)}
        if actual_second != expected_second:
            raise AssertionError(f"Rust→Python continuation mismatch seed={seed}")
        continuation_rows.append({"seed": seed, "draws": 10_000, "status": "passed"})

    certificate = {
        "schema": "pineland-rng-parity-certificate-v1",
        "status": "passed",
        "python_version": sys.version,
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "seed_count": len(SEEDS),
        "draws_per_operation": args.draws,
        "sample_rounds": args.sample_rounds,
        "shuffle_rounds": args.shuffle_rounds,
        "operations": sorted(next(iter(expected_vectors.values()))),
        "seed_vectors": [
            {"seed": seed, "status": "passed"} for seed in SEEDS
        ],
        "state_handoff": continuation_rows,
        "native_vector_payload": native,
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
