#!/usr/bin/env python3
"""Validate and atomically merge Partner-Force ARC CSV shards."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import pandas as pd

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent / "analysis"
sys.path.insert(0, str(ANALYSIS))
from partner_force_metrics import validate_raw_branch_panel


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output-csv", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--expected-tasks", type=int)
    group.add_argument(
        "--expected-task-ids",
        help="Comma-separated exact Slurm array task IDs, for sparse pilot arrays",
    )
    p.add_argument("--metadata-json")
    return p.parse_args()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ns = parse_args()
    if ns.expected_task_ids:
        try:
            expected_ids = {int(x.strip()) for x in ns.expected_task_ids.split(",") if x.strip()}
        except ValueError as exc:
            raise SystemExit(f"invalid --expected-task-ids: {exc}") from exc
        if not expected_ids:
            raise SystemExit("--expected-task-ids must contain at least one integer task id")
        expected_tasks = len(expected_ids)
    else:
        if ns.expected_tasks is None or ns.expected_tasks <= 0:
            raise SystemExit("--expected-tasks must be a positive integer")
        expected_tasks = ns.expected_tasks
        expected_ids = set(range(expected_tasks))

    input_dir = Path(ns.input_dir)
    shards = sorted(input_dir.glob("task_*_cell_*_seed_*.csv"))
    if len(shards) != expected_tasks:
        raise SystemExit(
            f"expected {expected_tasks} completed CSV shards, found {len(shards)} in {input_dir}"
        )

    task_ids = []
    frames = []
    for shard in shards:
        try:
            task_id = int(shard.name.split("_", 2)[1])
        except Exception as exc:
            raise SystemExit(f"cannot parse task id from {shard.name}: {exc}")
        task_ids.append(task_id)
        df = pd.read_csv(shard)
        if len(df) != 8:
            raise SystemExit(f"{shard} has {len(df)} rows; expected 8 (4 horizons x ON/OFF)")
        frames.append(df)

    actual_ids = set(task_ids)
    if len(task_ids) != len(actual_ids):
        raise SystemExit("duplicate ARC task ids detected in shard filenames")
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise SystemExit(f"ARC task-id coverage mismatch; missing={missing[:20]} extra={extra[:20]}")

    merged = pd.concat(frames, ignore_index=True)
    validate_raw_branch_panel(merged)
    merged = merged.sort_values(
        ["cell_id", "seed", "horizon_days", "branch"], kind="mergesort"
    ).reset_index(drop=True)

    output = Path(ns.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    merged.to_csv(tmp, index=False)
    os.replace(tmp, output)

    metadata = {
        "schema_version": "pineland.partner_force_arc_merge.v1",
        "input_directory": str(input_dir),
        "expected_tasks": expected_tasks,
        "expected_task_ids": sorted(expected_ids),
        "merged_rows": int(len(merged)),
        "unique_pairs": int(merged["pair_id"].nunique()),
        "experiment_ids": sorted(merged["experiment_id"].astype(str).unique().tolist()),
        "git_commits": sorted(merged["git_commit"].astype(str).unique().tolist()),
        "output_csv": str(output),
        "output_sha256": file_sha256(output),
    }
    metadata_path = Path(ns.metadata_json) if ns.metadata_json else output.with_suffix(".merge.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
