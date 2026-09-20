#!/usr/bin/env python3
"""Validate and atomically merge Partner-Force ARC CSV shards."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

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
    p.add_argument(
        "--require-task-metadata",
        action="store_true",
        help="Require and cryptographically validate one ARC task metadata sidecar per shard",
    )
    p.add_argument(
        "--enforce-degeneracy-safeguard",
        action="store_true",
        help="Apply the preregistered ensemble degeneracy gate to the complete merged panel",
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
        (CONTRACTS / "partner_force_trajectory_schema_v2.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (CONTRACTS / "partner_force_trajectory_contract_v2.json").read_text(encoding="utf-8")
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

    sampling = contract["sampling"]
    pre_window = int(sampling["prewithdrawal_window_days"])
    pre_step = int(sampling["prewithdrawal_step_days"])
    post_step = int(sampling["postwithdrawal_step_days"])
    post_max = int(sampling["postwithdrawal_max_day"])
    confirmatory_horizons = {
        int(x) for x in sampling["postwithdrawal_also_includes_confirmatory_horizons_days"]
    }
    pre_expected = set(range(-pre_window, 0, pre_step)) | {0}
    post_expected = set(range(post_step, post_max, post_step)) | confirmatory_horizons | {post_max}
    phase_expected = {
        "PRE_SUPPORTED": pre_expected,
        "SUPPORT_ON": post_expected,
        "SUPPORT_OFF": post_expected,
    }
    if set(df["phase"].astype(str)) != set(phase_expected):
        raise SystemExit(f"{path} has incorrect trajectory phase coverage")
    for phase, expected_offsets in phase_expected.items():
        actual = {
            round(v)
            for v in df.loc[df["phase"] == phase, "days_from_withdrawal"].to_numpy(float)
        }
        if actual != expected_offsets:
            raise SystemExit(
                f"{path} {phase} checkpoint coverage mismatch; "
                f"missing={sorted(expected_offsets-actual)} extra={sorted(actual-expected_offsets)}"
            )
    return df


def enforce_ensemble_degeneracy_safeguard(merged: pd.DataFrame) -> dict:
    """Apply the production degeneracy gate once the full ARC ensemble exists."""
    h180 = merged[
        (merged["support_profile"].astype(str) != "none")
        & (merged["horizon_days"].astype(float) == 180.0)
    ].copy()
    if h180.empty:
        raise SystemExit("degeneracy safeguard found no treated h=180 rows")
    pivot = h180.pivot(index="world_id", columns="branch", values="composite_capability")
    required = {"SUPPORT_ON", "SUPPORT_OFF"}
    if not required.issubset(set(pivot.columns)):
        raise SystemExit(
            "degeneracy safeguard requires paired SUPPORT_ON/SUPPORT_OFF h=180 rows"
        )
    r180 = (
        pivot["SUPPORT_OFF"].to_numpy(float)
        / pivot["SUPPORT_ON"].to_numpy(float).clip(1e-9, None)
    )
    near_zero = (r180 >= 0.995) & (r180 <= 1.005)
    near_zero_fraction = float(near_zero.mean())
    variance = float(r180.var())
    report = {
        "treated_worlds_h180": len(r180),
        "near_zero_worlds": int(near_zero.sum()),
        "near_zero_fraction": near_zero_fraction,
        "mean_r180": float(r180.mean()),
        "variance_r180": variance,
        "status": "PASS",
    }
    if near_zero_fraction > 0.90:
        raise SystemExit(
            "Degeneracy Alarm: "
            f"{near_zero_fraction * 100.0:.1f}% of treated worlds exhibit near-zero response "
            "(|R_180 - 1.0| <= 0.005), exceeding 90% threshold"
        )
    if len(r180) > 1 and variance < 1e-6:
        raise SystemExit(
            "Degeneracy Alarm: R_180 variance is essentially zero (< 1e-6) across treated worlds"
        )
    return report


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
    task_metadata = []
    trajectory_contract = json.loads(
        (CONTRACTS / "partner_force_trajectory_contract_v2.json").read_text(encoding="utf-8")
    )
    expected_horizons = {
        int(x)
        for x in trajectory_contract["sampling"][
            "postwithdrawal_also_includes_confirmatory_horizons_days"
        ]
    }
    expected_primary_rows = 2 * len(expected_horizons)
    for shard in shards:
        task_id = task_id_from_name(shard)
        task_ids.append(task_id)
        metadata = None
        if ns.require_task_metadata:
            metadata_path = shard.with_suffix(".json")
            if not metadata_path.exists():
                raise SystemExit(f"missing ARC task metadata for {shard}: {metadata_path}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("schema_version") not in {
                "pineland.partner_force_arc_task.v1",
                "pineland.partner_force_arc_task.stage4.v1",
            }:
                raise SystemExit(f"{metadata_path} has unexpected schema_version")
            if metadata.get("schema_version") == "pineland.partner_force_arc_task.stage4.v1":
                if int(metadata.get("logical_task_id", -1)) != task_id:
                    raise SystemExit(
                        f"{metadata_path} logical task id does not match shard filename"
                    )
                slurm_task_id = int(metadata.get("slurm_array_task_id", -1))
                task_offset = int(metadata.get("task_offset", -1))
                if slurm_task_id < 0 or task_offset < 0 or slurm_task_id + task_offset != task_id:
                    raise SystemExit(
                        f"{metadata_path} Slurm task id + offset does not reconstruct logical task id"
                    )
            elif int(metadata.get("slurm_array_task_id", -1)) != task_id:
                raise SystemExit(f"{metadata_path} task id does not match shard filename")
            if metadata.get("output_sha256") != file_sha256(shard):
                raise SystemExit(f"{shard} SHA-256 does not match ARC task metadata")
            trajectory_shard = shard.with_name(f"{shard.stem}.trajectory.csv")
            if not trajectory_shard.exists():
                raise SystemExit(f"missing trajectory shard paired with {shard}")
            if metadata.get("trajectory_sha256") != file_sha256(trajectory_shard):
                raise SystemExit(f"{trajectory_shard} SHA-256 does not match ARC task metadata")
        df = pd.read_csv(shard)
        if len(df) != expected_primary_rows:
            raise SystemExit(
                f"{shard} has {len(df)} rows; expected {expected_primary_rows} "
                f"({len(expected_horizons)} horizons x ON/OFF)"
            )
        if {int(x) for x in df["horizon_days"].unique()} != expected_horizons:
            raise SystemExit(
                f"{shard} horizon coverage mismatch; expected={sorted(expected_horizons)} "
                f"got={sorted(int(x) for x in df['horizon_days'].unique())}"
            )
        if set(df["branch"].astype(str)) != {"SUPPORT_ON", "SUPPORT_OFF"}:
            raise SystemExit(f"{shard} does not contain exactly SUPPORT_ON/SUPPORT_OFF branches")
        if metadata is not None:
            commits = set(df["git_commit"].astype(str))
            if commits != {str(metadata.get("git_commit"))}:
                raise SystemExit(
                    f"{shard} git_commit does not match its ARC task metadata: "
                    f"csv={sorted(commits)} meta={metadata.get('git_commit')}"
                )
            task_metadata.append(metadata)
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
    degeneracy_safeguard = (
        enforce_ensemble_degeneracy_safeguard(merged)
        if ns.enforce_degeneracy_safeguard
        else {"status": "NOT_REQUESTED"}
    )
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
            "trajectory_rows": len(trajectories),
            "trajectory_output_csv": str(trajectory_output),
            "trajectory_output_sha256": file_sha256(trajectory_output),
        }

    metadata = {
        "schema_version": "pineland.partner_force_arc_merge.v1",
        "input_directory": str(input_dir),
        "expected_tasks": expected_tasks,
        "expected_task_ids": sorted(expected_ids),
        "merged_rows": len(merged),
        "unique_pairs": int(merged["pair_id"].nunique()),
        "experiment_ids": sorted(merged["experiment_id"].astype(str).unique().tolist()),
        "git_commits": sorted(merged["git_commit"].astype(str).unique().tolist()),
        "source_array_job_ids": sorted(
            {str(m.get("slurm_array_job_id")) for m in task_metadata}
        ),
        "task_metadata_verified": len(task_metadata),
        "output_csv": str(output),
        "output_sha256": file_sha256(output),
        "degeneracy_safeguard": degeneracy_safeguard,
        **trajectory_metadata,
    }
    metadata_path = Path(ns.metadata_json) if ns.metadata_json else output.with_suffix(".merge.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
