"""Certify Rust scheduler ordering against the Python reference scheduler."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.events import EventScheduler


MANIFEST = ROOT / "rust" / "Cargo.toml"
BINARY = ROOT / "rust" / "target" / "release" / (
    "pineland.exe" if os.name == "nt" else "pineland"
)
BULK_EVENTS = 12_000
PREFIX_EVENTS = 64
KINDS = [
    "patrol",
    "contact_scan",
    "command",
    "force_movement",
    "logistics",
    "information",
    "beliefs",
    "physical_refresh",
    "social_influence",
    "mobility",
    "recruitment",
    "organization_ecology",
    "governance",
    "economy",
    "political_order",
    "foreign_affairs",
    "peace_process",
    "recording_noise",
    "checkpoint",
    "organized_action",
    "contact",
    "custom",
]
EVENT_CODES = {kind: index + 1 for index, kind in enumerate(KINDS[:-1])}
EVENT_CODES["custom"] = 99


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
    if not binary.is_file():
        raise RuntimeError(f"native binary was not produced at {binary}")
    return binary


def schedule_reference(scheduler: EventScheduler, time: float, priority: int, kind: str) -> None:
    scheduler.schedule(time, kind, priority=priority)


def python_reference() -> dict[str, object]:
    scheduler = EventScheduler()
    initial_count = len(KINDS) + BULK_EVENTS
    for index, kind in enumerate(KINDS):
        schedule_reference(
            scheduler,
            0.0 if index % 3 == 0 else (index % 5) * 0.25,
            10 + (index * 11) % 17,
            kind,
        )
    for index in range(BULK_EVENTS):
        schedule_reference(
            scheduler,
            ((index * 37) % 251) / 4.0,
            10 + (index * 11 + 5) % 17,
            KINDS[(index * 7 + 3) % len(KINDS)],
        )

    digest_material = bytearray()
    prefix: list[dict[str, int | str]] = []
    popped = 0
    while len(scheduler):
        event = scheduler.pop_next()
        digest_material.extend(
            struct.pack(
                "<dHQH",
                event.time,
                event.priority,
                event.sequence,
                EVENT_CODES[event.event_type],
            )
        )
        if popped < PREFIX_EVENTS:
            prefix.append(
                {
                    "time_bits": struct.unpack("<Q", struct.pack("<d", event.time))[0],
                    "priority": event.priority,
                    "sequence": event.sequence,
                    "kind": event.event_type,
                    "code": EVENT_CODES[event.event_type],
                }
            )
        if event.sequence < initial_count:
            for branch in range(2):
                child_kind = KINDS[(event.sequence * 5 + branch * 7 + 3) % len(KINDS)]
                offset = (
                    0.0
                    if branch == 0 and event.sequence % 5 == 0
                    else (branch + 1) * 0.125
                )
                child_priority = 10 + (event.priority + branch * 3 + event.sequence) % 17
                schedule_reference(scheduler, event.time + offset, child_priority, child_kind)
        popped += 1

    return {
        "schema": "pineland-scheduler-certification-v1",
        "initial_events": initial_count,
        "scheduled_events": initial_count * 3,
        "popped_events": popped,
        "next_sequence": initial_count * 3,
        "processed": popped,
        "pending": 0,
        "ordering_key": "(time, priority, sequence)",
        "pop_digest": hashlib.sha256(digest_material).hexdigest(),
        "prefix": prefix,
    }


def native_reference(binary: Path) -> dict[str, object]:
    completed = subprocess.run(
        [str(binary), "certify-scheduler"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    binary = binary_path()
    expected = python_reference()
    actual = native_reference(binary)
    for key in (
        "schema",
        "initial_events",
        "scheduled_events",
        "popped_events",
        "next_sequence",
        "processed",
        "pending",
        "ordering_key",
        "pop_digest",
        "prefix",
    ):
        if actual.get(key) != expected[key]:
            raise AssertionError(
                f"scheduler mismatch in {key}: expected={expected[key]!r} actual={actual.get(key)!r}"
            )
    certificate = {
        "schema": "pineland-scheduler-parity-certificate-v1",
        "status": "passed",
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "events_popped": expected["popped_events"],
        "ordering_key": expected["ordering_key"],
        "tie_and_insertion_cases": [
            "time ties",
            "priority ties",
            "sequence ties",
            "recurring/newly inserted events",
            "contact events",
            "organized-action events",
            "checkpoint events",
        ],
        "pop_digest": expected["pop_digest"],
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
