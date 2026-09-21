#!/usr/bin/env python3
"""Inventory large or publication-sensitive blobs reachable in Git history."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PUBLICATION_SENSITIVE_PATH = re.compile(
    r"^(?:"
    r"artifacts/|"
    r"json/|"
    r"outputs/|"
    r"src/pineland_sim/_native/|"
    r"studies/.+/data/(?:raw|processed|derived|standard_v2)/|"
    r"studies/research_program/source_cache/|"
    r"studies/research_program/external_validation/.+/raw/"
    r")"
)


def git(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def historical_blobs() -> list[dict[str, object]]:
    objects = git("rev-list", "--objects", "--all")
    checked = git(
        "cat-file",
        "--batch-check=%(objecttype) %(objectsize) %(rest)",
        input_text=objects,
    )
    blobs: list[dict[str, object]] = []
    for line in checked.splitlines():
        parts = line.split(" ", 2)
        if len(parts) != 3 or parts[0] != "blob":
            continue
        try:
            size = int(parts[1])
        except ValueError:
            continue
        path = parts[2]
        blobs.append(
            {
                "path": path,
                "bytes": size,
                "mib": round(size / (1024 * 1024), 3),
                "publication_sensitive_path": bool(
                    PUBLICATION_SENSITIVE_PATH.match(path)
                ),
            }
        )
    return blobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--threshold-mib",
        type=float,
        default=10.0,
        help="report blobs at or above this size (default: 10 MiB)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when any threshold/sensitive history candidates exist",
    )
    parser.add_argument("--json", type=Path, dest="json_path")
    args = parser.parse_args()
    if args.threshold_mib < 0:
        parser.error("--threshold-mib must be non-negative")

    threshold = int(args.threshold_mib * 1024 * 1024)
    blobs = historical_blobs()
    candidates = [
        blob
        for blob in blobs
        if int(blob["bytes"]) >= threshold
        or bool(blob["publication_sensitive_path"])
    ]
    candidates.sort(key=lambda item: int(item["bytes"]), reverse=True)

    large = [item for item in candidates if int(item["bytes"]) >= threshold]
    sensitive = [item for item in candidates if item["publication_sensitive_path"]]

    payload = {
        "schema_version": "pineland.git_history_blob_audit.v1",
        "threshold_mib": args.threshold_mib,
        "reachable_blob_count": len(blobs),
        "large_blob_count": len(large),
        "publication_sensitive_path_count": len(sensitive),
        "candidates": candidates,
    }

    print(
        "SUMMARY "
        f"reachable_blobs={len(blobs)} "
        f"large_blobs={len(large)} "
        f"publication_sensitive_paths={len(sensitive)}"
    )
    for item in candidates[:40]:
        flags: list[str] = []
        if int(item["bytes"]) >= threshold:
            flags.append("large")
        if item["publication_sensitive_path"]:
            flags.append("sensitive-path")
        print(
            f"WARN  {float(item['mib']):8.3f} MiB "
            f"[{','.join(flags)}] {item['path']}"
        )
    if len(candidates) > 40:
        print(f"WARN  ... {len(candidates) - 40} additional candidates omitted")

    if args.json_path is not None:
        output = (
            args.json_path
            if args.json_path.is_absolute()
            else ROOT / args.json_path
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.strict and candidates:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
