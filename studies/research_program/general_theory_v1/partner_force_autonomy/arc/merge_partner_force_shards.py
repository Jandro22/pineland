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
CONTRACTS = HERE.parent / "contracts"
sys.path.insert(0, str(ANALYSIS))
from partner_force_metrics import validate_raw_branch_panel


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument(
        "--trajectory-output-csv",
        help="If supplied, require, validate, and merge one diagnostic trajectory shard per task",
    )
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


def task_id_from_name(path: Path) -> int:
    try:
        return int(path.name.split("_", 2)[1])
    except Exception as exc:
        raise SystemExit(f"cannot parse task id from {path.name}: {exc}") from exc


def validate_trajectory_shard(path: Path) -> pd.DataFrame:
    schema = json.loads(
        (CONTRACTS / "partner_force_trajectory_schema_v1.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (CONTRACTS / "partner_force_trajectory_contract_v1.json").read_text(encoding="utf-8")
    )
    expected_columns = set(schema["properties"])
    df = pd.read_csv(path)
    if set(df.columns) != expected_columns:
        missing = sorted(expected_columns - set(df.columns))
        extra = sorted(set(df.columns) - expected_columns)
        raise SystemExit(f"{path} trajectory columns mismatch; missing={missing} extra={extra}")
    expected_rows = int(contract["sampling"]["expected_rows_per_world"])
    if len(df) != expected_rows:
        raise SystemExit(f"{path} has {len(df)} trajectory rows; expected {expected_rows}")
    if df.isna().any().any():
        raise SystemExit(f"{path} contains NaN trajectory values")
    if df["world_id"].nunique() != 1 or df["seed"].nunique() != 1 or df["cell_id"].nunique() != 1:
        raise SystemExit(f"{path} trajectory shard mixes more than one world")
    if df.duplicated(["world_id", "phase", "time_days"]).any():
        raise SystemExit(f"{path} contains duplicate trajectory checkpoints")

    pre_expected = {-60, -53, -46, -39, -32, -25, -18, -11, -4, 0}
    post_expected = {
        7, 14, 21, 28, 30, 35, 42, 49, 56, 63, 70, 77, 84, 90,
        91, 98, 105, 112, 119, 126, 133, 140, 147, 154, 161, 168, 175, 180,
    }
    phase_expected = {
        "PRE_SUPPORTED": pre_expected,
        "SUPPORT_ON": post_expected,
        "SUPPORT_OFF": post_expected,
    }
    if set(df["phase"].astype(str)) != set(phase_expected):
        raise SystemExit(f"{path} has incorrect trajectory phase coverage")
    for phase, expected_offsets in phase_expected.items():
        actual = {
            int(round(v))
            for v in df.loc[df["phase"] == phase, "days_from_withdrawal"].to_numpy(float)
        }
        if actual != expected_offsets:
            raise SystemExit(
                f"{path} {phase} checkpoint coverage mismatch; "
                f"missing={sorted(expected_offsets-actual)} extra={sorted(actual-expected_offsets)}"
            )
    return df


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
    shards = sorted(
        p for p in input_dir.glob("task_*_cell_*_seed_*.csv") if ".trajectory.csv" not in p.name
    )
    if len(shards) != expected_tasks:
        raise SystemExit(
            f"expected {expected_tasks} completed CSV shards, found {len(shards)} in {input_dir}"
        )

    task_ids = []
    frames = []
    for shard in shards:
        task_id = task_id_from_name(shard)
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

    trajectory_metadata = {}
    if ns.trajectory_output_csv:
        trajectory_shards = sorted(input_dir.glob("task_*_cell_*_seed_*.trajectory.csv"))
        if len(trajectory_shards) != expected_tasks:
            raise SystemExit(
                f"expected {expected_tasks} trajectory shards, found {len(trajectory_shards)} in {input_dir}"
            )
        trajectory_ids = [task_id_from_name(p) for p in trajectory_shards]
        if len(trajectory_ids) != len(set(trajectory_ids)) or set(trajectory_ids) != expected_ids:
            raise SystemExit("trajectory shard task-id coverage does not match primary shard coverage")
        trajectory_frames = [validate_trajectory_shard(p) for p in trajectory_shards]
        trajectories = pd.concat(trajectory_frames, ignore_index=True)
        trajectories = trajectories.sort_values(
            ["cell_id", "seed", "time_days", "phase"], kind="mergesort"
        ).reset_index(drop=True)
        trajectory_output = Path(ns.trajectory_output_csv)
        trajectory_output.parent.mkdir(parents=True, exist_ok=True)
        trajectory_tmp = trajectory_output.with_name(
            f".{trajectory_output.name}.tmp-{os.getpid()}"
        )
        trajectories.to_csv(trajectory_tmp, index=False)
        os.replace(trajectory_tmp, trajectory_output)
        trajectory_metadata = {
            "trajectory_rows": int(len(trajectories)),
            "trajectory_output_csv": str(trajectory_output),
            "trajectory_output_sha256": file_sha256(trajectory_output),
        }

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
        **trajectory_metadata,
    }
    metadata_path = Path(ns.metadata_json) if ns.metadata_json else output.with_suffix(".merge.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
