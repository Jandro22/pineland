#!/usr/bin/env python3
"""Frozen analysis for the integrated Stage-4 partner-force paper program.

The script is deliberately shared across the Phase-Map, Bottleneck-Migration,
and Substitution-vs-Development modules.  Factor labels are read from the
preregistered Stage-4 contract and joined by cell_id; treatment labels never
override observed simulator telemetry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


COMMAND_REQUIREMENT_PER_ORDER = 0.5
EPS = 1.0e-6
CONFIRMATORY_HORIZONS = (7.0, 30.0, 90.0, 180.0, 360.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--primary-csv", required=True)
    p.add_argument("--trajectory-csv", required=True)
    p.add_argument("--contract", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def load_contract(path: Path) -> tuple[dict, pd.DataFrame]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != "pineland.partner_force_stage4_contract.v1":
        raise ValueError("expected pineland.partner_force_stage4_contract.v1")
    cells = pd.DataFrame(contract["cells"])
    if cells["cell_id"].duplicated().any():
        raise ValueError("Stage-4 contract contains duplicate cell_id values")
    factor_cols = [c for c in cells.columns if c.startswith("factor_")]
    extra = ["cell_id", *factor_cols]
    if "nominal_development_budget_per_day" in cells.columns:
        extra.append("nominal_development_budget_per_day")
    return contract, cells[extra].copy()


def validate_inputs(primary: pd.DataFrame, trajectory: pd.DataFrame, contract: dict) -> None:
    expected_id = contract["experiment_id"]
    ids = set(primary["experiment_id"].astype(str))
    tids = set(trajectory["experiment_id"].astype(str))
    if ids != {expected_id} or tids != {expected_id}:
        raise ValueError(f"experiment mismatch: contract={expected_id}, primary={ids}, trajectory={tids}")
    expected_worlds = int(contract["cells_count"]) * int(contract["default_seed_count"])
    worlds = primary[["cell_id", "seed"]].drop_duplicates()
    if len(worlds) != expected_worlds:
        raise ValueError(f"expected {expected_worlds} worlds, found {len(worlds)}")
    if primary.duplicated(["cell_id", "seed", "horizon_days", "branch"]).any():
        raise ValueError("duplicate primary branch rows")
    if trajectory.duplicated(["cell_id", "seed", "days_from_withdrawal", "phase"]).any():
        raise ValueError("duplicate trajectory checkpoints")


def add_channel_metrics(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["fg_indigenous"] = x["interval_indigenous_graduates"].astype(float)
    x["fg_demand"] = x["interval_military_losses"].astype(float)
    x["log_indigenous"] = x["interval_indigenous_logistics_delivered"].astype(float)
    x["log_demand"] = x["interval_military_logistics_demanded"].astype(float)
    x["cmd_indigenous"] = x["interval_command_indigenous_service"].astype(float)
    x["cmd_demand"] = (
        x["interval_command_opportunities"].astype(float) * COMMAND_REQUIREMENT_PER_ORDER
    )
    ratios = []
    for channel in ("fg", "log", "cmd"):
        demand = x[f"{channel}_demand"].to_numpy(dtype=float)
        supply = x[f"{channel}_indigenous"].to_numpy(dtype=float)
        ratio = np.full(len(x), np.nan)
        active = demand > 0.0
        ratio[active] = supply[active] / demand[active]
        x[f"{channel}_ratio"] = ratio
        ratios.append(ratio)
    arr = np.vstack(ratios).T
    smooth = np.clip(arr, 1.0e-9, 4.0)
    active_n = np.sum(np.isfinite(arr), axis=1)
    x["smooth_q_arithmetic"] = np.divide(
        np.nansum(arr, axis=1), active_n, out=np.full(len(x), np.nan), where=active_n > 0
    )
    x["smooth_q_geometric"] = np.exp(
        np.divide(
            np.nansum(np.log(smooth), axis=1),
            active_n,
            out=np.full(len(x), np.nan),
            where=active_n > 0,
        )
    )
    inv = np.where(np.isfinite(smooth), 1.0 / smooth, np.nan)
    x["smooth_q_harmonic"] = np.divide(
        active_n,
        np.nansum(inv, axis=1),
        out=np.full(len(x), np.nan),
        where=(active_n > 0) & (np.nansum(inv, axis=1) > 0),
    )
    return x


def cumulative_post_flows(trajectory: pd.DataFrame) -> pd.DataFrame:
    post = trajectory[
        trajectory["phase"].isin(["SUPPORT_ON", "SUPPORT_OFF"])
        & (trajectory["days_from_withdrawal"].astype(float) > 0.0)
    ].copy()
    post = add_channel_metrics(post)
    post = post.sort_values(["cell_id", "seed", "phase", "days_from_withdrawal"], kind="mergesort")
    cumulative_fields = [
        "fg_indigenous",
        "fg_demand",
        "log_indigenous",
        "log_demand",
        "cmd_indigenous",
        "cmd_demand",
        "interval_donor_cost",
    ]
    for field in cumulative_fields:
        post[f"cum_{field}"] = post.groupby(["cell_id", "seed", "phase"], sort=False)[
            field
        ].cumsum()
    return post


def pair_trajectory(post: pd.DataFrame) -> pd.DataFrame:
    horizons = post[post["days_from_withdrawal"].astype(float).isin(CONFIRMATORY_HORIZONS)].copy()
    on = horizons[horizons["phase"] == "SUPPORT_ON"].copy()
    off = horizons[horizons["phase"] == "SUPPORT_OFF"].copy()
    key = ["cell_id", "seed", "days_from_withdrawal"]
    keep = [
        "interval_formal_q_indigenous",
        "composite_capability",
        "smooth_q_arithmetic",
        "smooth_q_geometric",
        "smooth_q_harmonic",
        "cum_fg_indigenous",
        "cum_fg_demand",
        "cum_log_indigenous",
        "cum_log_demand",
        "cum_cmd_indigenous",
        "cum_cmd_demand",
        "cum_interval_donor_cost",
    ]
    merged = on[key + keep].merge(off[key + keep], on=key, suffixes=("_on", "_off"), validate="one_to_one")
    merged = merged.rename(columns={"days_from_withdrawal": "horizon_days"})
    for field in keep:
        merged[f"delta_{field}"] = merged[f"{field}_on"] - merged[f"{field}_off"]
    merged["q_feasible_on"] = np.minimum(merged["interval_formal_q_indigenous_on"], 1.0)
    merged["q_feasible_off"] = np.minimum(merged["interval_formal_q_indigenous_off"], 1.0)
    merged["delta_q_feasible"] = merged["q_feasible_on"] - merged["q_feasible_off"]
    return merged


def migration_summary(primary: pd.DataFrame, post: pd.DataFrame) -> pd.DataFrame:
    pre = (
        primary.sort_values(["cell_id", "seed", "horizon_days", "branch"], kind="mergesort")
        .drop_duplicates(["cell_id", "seed"])
        [["cell_id", "seed", "formal_bottleneck"]]
        .rename(columns={"formal_bottleneck": "pre_bottleneck"})
    )
    rows = []
    for (cell_id, seed), g in post[post["phase"] == "SUPPORT_ON"].groupby(["cell_id", "seed"], sort=False):
        g = g.sort_values("days_from_withdrawal", kind="mergesort")
        pre_b = pre.loc[(pre["cell_id"] == cell_id) & (pre["seed"] == seed), "pre_bottleneck"].iloc[0]
        seq = [str(v) for v in g["interval_formal_bottleneck"]]
        times = [float(v) for v in g["days_from_withdrawal"]]
        first = math.nan
        for i in range(len(seq) - 1):
            if seq[i] != pre_b and seq[i + 1] != pre_b:
                first = times[i]
                break
        counts = Counter(seq)
        total = sum(counts.values())
        entropy = -sum((n / total) * math.log(n / total) for n in counts.values()) if total else math.nan
        rows.append(
            {
                "cell_id": cell_id,
                "seed": seed,
                "pre_bottleneck": pre_b,
                "first_persistent_migration_days": first,
                "ever_persistently_migrated": math.isfinite(first),
                "bottleneck_path_entropy": entropy,
                "modal_post_bottleneck": counts.most_common(1)[0][0] if counts else "none",
            }
        )
    return pd.DataFrame(rows)


def world_summary(paired: pd.DataFrame, migration: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    wide_fields = [
        "delta_composite_capability",
        "delta_q_feasible",
        "delta_interval_formal_q_indigenous",
        "delta_cum_fg_indigenous",
        "delta_cum_fg_demand",
        "delta_cum_log_indigenous",
        "delta_cum_log_demand",
        "delta_cum_cmd_indigenous",
        "delta_cum_cmd_demand",
        "delta_cum_interval_donor_cost",
        "delta_smooth_q_arithmetic",
        "delta_smooth_q_geometric",
        "delta_smooth_q_harmonic",
    ]
    parts = []
    for horizon in CONFIRMATORY_HORIZONS:
        x = paired[paired["horizon_days"] == horizon][["cell_id", "seed", *wide_fields]].copy()
        x = x.rename(columns={field: f"{field}_h{int(horizon)}" for field in wide_fields})
        parts.append(x.set_index(["cell_id", "seed"]))
    out = pd.concat(parts, axis=1).reset_index()
    out = out.merge(migration, on=["cell_id", "seed"], how="left", validate="one_to_one")
    out = out.merge(factors, on="cell_id", how="left", validate="many_to_one")
    out["initially_effective"] = out["delta_composite_capability_h30"] > EPS
    dq = out["delta_q_feasible_h360"]
    dc = out["delta_composite_capability_h360"]
    out["autonomy_class_360"] = np.select(
        [
            (dc > EPS) & (dq > EPS),
            (dc > EPS) & (dq < -EPS),
            (dc < -EPS) & (dq > EPS),
            (dc < -EPS) & (dq < -EPS),
        ],
        ["productive_autonomy", "dependency_gain", "contraction_autonomy", "double_harm"],
        default="neutral_or_mixed",
    )
    return out


def grouped_summary(worlds: pd.DataFrame, factor_cols: list[str]) -> list[dict]:
    if not factor_cols:
        return []
    rows = []
    for keys, g in worlds.groupby(factor_cols, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {k: v for k, v in zip(factor_cols, keys)}
        row.update(
            {
                "n": int(len(g)),
                "mean_delta_capability_h30": float(g["delta_composite_capability_h30"].mean()),
                "mean_delta_capability_h360": float(g["delta_composite_capability_h360"].mean()),
                "median_delta_q_feasible_h360": float(g["delta_q_feasible_h360"].median()),
                "mean_delta_q_feasible_h360": float(g["delta_q_feasible_h360"].mean()),
                "fraction_initially_effective": float(g["initially_effective"].mean()),
                "fraction_dependency_gain": float((g["autonomy_class_360"] == "dependency_gain").mean()),
                "fraction_productive_autonomy": float((g["autonomy_class_360"] == "productive_autonomy").mean()),
                "fraction_persistent_migration": float(g["ever_persistently_migrated"].fillna(False).mean()),
            }
        )
        rows.append(row)
    return rows


def main() -> None:
    ns = args()
    primary_path = Path(ns.primary_csv)
    trajectory_path = Path(ns.trajectory_csv)
    contract_path = Path(ns.contract)
    outdir = Path(ns.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    contract, factors = load_contract(contract_path)
    primary = pd.read_csv(primary_path)
    trajectory = pd.read_csv(trajectory_path)
    validate_inputs(primary, trajectory, contract)
    post = cumulative_post_flows(trajectory)
    paired = pair_trajectory(post)
    paired = paired.merge(factors, on="cell_id", how="left", validate="many_to_one")
    migration = migration_summary(primary, post)
    worlds = world_summary(paired, migration, factors)

    paired_path = outdir / "stage4_paired_trajectory_metrics_v1.csv"
    world_path = outdir / "stage4_world_summary_v1.csv"
    paired.to_csv(paired_path, index=False)
    worlds.to_csv(world_path, index=False)

    factor_cols = [c for c in factors.columns if c.startswith("factor_")]
    summary = {
        "schema_version": "pineland.partner_force_stage4_integrated_analysis.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PREREGISTERED_ANALYSIS_OUTPUT",
        "source_primary_csv": str(primary_path),
        "source_primary_sha256": sha256(primary_path),
        "source_trajectory_csv": str(trajectory_path),
        "source_trajectory_sha256": sha256(trajectory_path),
        "contract": str(contract_path),
        "contract_sha256": sha256(contract_path),
        "worlds": int(len(worlds)),
        "paired_horizon_rows": int(len(paired)),
        "classification_rule": {
            "epsilon": EPS,
            "autonomy_primary": "delta(min(interval_formal_q_indigenous,1.0)) at 360d",
            "effectiveness_primary": "delta composite_capability at 30d > epsilon",
            "raw_q_also_reported": True,
        },
        "bottleneck_migration_rule": contract.get("analysis_rules", {}).get("migration_definition"),
        "factor_columns": factor_cols,
        "grouped_summary": grouped_summary(worlds, factor_cols),
        "autonomy_class_counts": {
            str(k): int(v) for k, v in worlds["autonomy_class_360"].value_counts().items()
        },
        "paired_output": str(paired_path),
        "paired_output_sha256": sha256(paired_path),
        "world_output": str(world_path),
        "world_output_sha256": sha256(world_path),
    }
    summary_path = outdir / "stage4_analysis_summary_v1.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
