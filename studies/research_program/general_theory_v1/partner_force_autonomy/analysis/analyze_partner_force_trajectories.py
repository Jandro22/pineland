#!/usr/bin/env python3
"""Diagnostic-only analysis for Partner-Force Autonomy trajectory sidecars.

This module does not select, fit, refit, or score the preregistered Stage-3
predictor.  It converts longitudinal telemetry into descriptive mechanism and
timing summaries so null or heterogeneous confirmatory results remain
scientifically interpretable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
CONTRACTS = BASE / "contracts"
CELLS = BASE / "configs" / "stage3_discovery_cells_v1.csv"


STATE_TREND_COLUMNS = [
    "government_control",
    "military_personnel",
    "trained_reserve",
    "recruit_pipeline",
    "readiness",
    "experience",
    "supply_stock",
    "command_reliability",
    "command_latency_hours",
    "insurgent_personnel",
    "insurgent_territorial_control",
]

FLOW_COLUMNS = [
    "interval_indigenous_recruits",
    "interval_indigenous_graduates",
    "interval_security_deployments",
    "interval_military_losses",
    "interval_indigenous_logistics_produced",
    "interval_indigenous_logistics_delivered",
    "interval_indigenous_logistics_consumed",
    "interval_logistics_system_lost",
    "interval_contacts",
    "interval_organized_actions",
    "interval_external_air_assisted_contacts",
    "interval_external_air_intensity",
    "interval_external_air_firepower_bonus",
    "interval_external_logistics_offered",
    "interval_external_logistics_delivered",
    "interval_external_logistics_rejected",
    "interval_external_logistics_lost",
    "interval_external_command_events",
    "interval_command_reliability_boost",
    "interval_command_latency_hours_saved",
    "interval_external_forcegen_graduates",
    "interval_donor_cost_air",
    "interval_donor_cost_logistics",
    "interval_donor_cost_command",
    "interval_donor_cost_forcegen",
    "interval_donor_cost",
]


def _slope(x: Iterable[float], y: Iterable[float]) -> float:
    xv = np.asarray(list(x), dtype=float)
    yv = np.asarray(list(y), dtype=float)
    if len(xv) < 2 or np.allclose(xv, xv[0]):
        return 0.0
    return float(np.polyfit(xv, yv, 1)[0])


def validate_trajectory_panel(df: pd.DataFrame) -> None:
    schema = json.loads(
        (CONTRACTS / "partner_force_trajectory_schema_v1.json").read_text(encoding="utf-8")
    )
    contract = json.loads(
        (CONTRACTS / "partner_force_trajectory_contract_v1.json").read_text(encoding="utf-8")
    )
    expected_columns = set(schema["properties"])
    if set(df.columns) != expected_columns:
        raise ValueError(
            f"trajectory columns do not match frozen schema; "
            f"missing={sorted(expected_columns-set(df.columns))}, "
            f"extra={sorted(set(df.columns)-expected_columns)}"
        )
    if df.isna().any().any():
        raise ValueError("trajectory panel contains NaN values")
    expected_rows = int(contract["sampling"]["expected_rows_per_world"])
    counts = df.groupby("world_id", sort=False).size()
    if not (counts == expected_rows).all():
        bad = counts[counts != expected_rows].to_dict()
        raise ValueError(f"trajectory world row counts differ from {expected_rows}: {bad}")


def build_pair_trajectory(df: pd.DataFrame) -> pd.DataFrame:
    post = df[df["phase"].isin(["SUPPORT_ON", "SUPPORT_OFF"])].copy()
    key = ["world_id", "cell_id", "support_profile", "seed", "days_from_withdrawal"]
    fields = [
        "composite_capability",
        "government_control",
        "military_personnel",
        "operational_formations",
        "covered_localities",
        "trained_reserve",
        "recruit_pipeline",
        "readiness",
        "experience",
        "supply_stock",
        "command_reliability",
        "command_latency_hours",
        "insurgent_personnel",
        "insurgent_territorial_control",
    ]
    wide = post.pivot(index=key, columns="phase", values=fields)
    wide.columns = [f"{name}_{phase.lower()}" for name, phase in wide.columns]
    wide = wide.reset_index()
    on = wide["composite_capability_support_on"].to_numpy(float)
    off = wide["composite_capability_support_off"].to_numpy(float)
    wide["autonomy_ratio"] = off / np.maximum(on, 1.0e-12)
    wide["capability_gap"] = on - off
    return wide.sort_values(["world_id", "days_from_withdrawal"], kind="mergesort")


def build_world_summary(df: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    rows = []
    cell_manifest = pd.read_csv(CELLS)
    cell_meta = cell_manifest.drop_duplicates("cell_id").set_index("cell_id")
    for world_id, g in paired.groupby("world_id", sort=False):
        g = g.sort_values("days_from_withdrawal")
        x = g["days_from_withdrawal"].to_numpy(float)
        gap = g["capability_gap"].to_numpy(float)
        ratio = g["autonomy_ratio"].to_numpy(float)
        max_gap_idx = int(np.argmax(gap))
        min_ratio_idx = int(np.argmin(ratio))
        row = {
            "world_id": world_id,
            "cell_id": str(g["cell_id"].iloc[0]),
            "support_profile": str(g["support_profile"].iloc[0]),
            "seed": int(g["seed"].iloc[0]),
            "integrated_capability_gap_0_180": float(np.trapezoid(np.maximum(gap, 0.0), x)),
            "max_capability_gap": float(gap[max_gap_idx]),
            "day_of_max_capability_gap": float(x[max_gap_idx]),
            "minimum_autonomy_ratio": float(ratio[min_ratio_idx]),
            "day_of_minimum_autonomy_ratio": float(x[min_ratio_idx]),
        }
        for horizon in (7, 30, 90, 180):
            hg = g[np.isclose(g["days_from_withdrawal"].to_numpy(float), horizon)]
            if len(hg) != 1:
                raise ValueError(f"{world_id} missing unique h={horizon} trajectory row")
            row[f"autonomy_ratio_h{horizon}"] = float(hg["autonomy_ratio"].iloc[0])
            row[f"capability_gap_h{horizon}"] = float(hg["capability_gap"].iloc[0])

        pre = df[(df["world_id"] == world_id) & (df["phase"] == "PRE_SUPPORTED")]
        pre = pre.sort_values("days_from_withdrawal")
        for col in STATE_TREND_COLUMNS:
            row[f"pre_slope_{col}_per_day"] = _slope(
                pre["days_from_withdrawal"], pre[col]
            )

        for phase in ("SUPPORT_ON", "SUPPORT_OFF"):
            pg = df[(df["world_id"] == world_id) & (df["phase"] == phase)]
            suffix = phase.lower()
            for col in FLOW_COLUMNS:
                row[f"post_total_{col}_{suffix}"] = float(pg[col].sum())

        cell_id = row["cell_id"]
        if cell_id in cell_meta.index:
            meta = cell_meta.loc[cell_id]
            for col in ("forcegen_mult", "logistics_mult", "command_mult"):
                if col in meta.index:
                    row[col] = meta[col]
            row["capacity_profile"] = (
                f"fg{float(meta['forcegen_mult']):.4g}_"
                f"log{float(meta['logistics_mult']):.4g}_"
                f"cmd{float(meta['command_mult']):.4g}"
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["cell_id", "seed"], kind="mergesort")


def quantile_summary(worlds: pd.DataFrame) -> dict:
    metrics = [
        "integrated_capability_gap_0_180",
        "max_capability_gap",
        "minimum_autonomy_ratio",
        "autonomy_ratio_h90",
        "autonomy_ratio_h180",
    ]

    def summarize(group: pd.DataFrame) -> dict:
        result = {"n_worlds": int(len(group))}
        for metric in metrics:
            x = group[metric].to_numpy(float)
            result[metric] = {
                "median": float(np.median(x)),
                "q25": float(np.quantile(x, 0.25)),
                "q75": float(np.quantile(x, 0.75)),
            }
        return result

    out = {"overall": summarize(worlds), "by_support_profile": {}, "by_capacity_profile": {}}
    for name, group in worlds.groupby("support_profile", sort=True):
        out["by_support_profile"][str(name)] = summarize(group)
    if "capacity_profile" in worlds.columns:
        for name, group in worlds.groupby("capacity_profile", sort=True):
            out["by_capacity_profile"][str(name)] = summarize(group)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--trajectory-csv", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    trajectory_path = Path(args.trajectory_csv)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(trajectory_path)
    validate_trajectory_panel(df)
    paired = build_pair_trajectory(df)
    worlds = build_world_summary(df, paired)

    paired_path = outdir / "partner_force_trajectory_pairs_v1.csv"
    worlds_path = outdir / "partner_force_trajectory_world_summary_v1.csv"
    summary_path = outdir / "partner_force_trajectory_diagnostics_v1.json"
    paired.to_csv(paired_path, index=False)
    worlds.to_csv(worlds_path, index=False)
    summary = {
        "schema_version": "pineland.partner_force_trajectory_diagnostics.v1",
        "status": "DIAGNOSTIC_ONLY_NOT_A_CONFIRMATORY_MODEL_SELECTION_RESULT",
        "source_trajectory_csv": str(trajectory_path),
        "worlds": int(worlds["world_id"].nunique()),
        "trajectory_rows": int(len(df)),
        "paired_postwithdrawal_rows": int(len(paired)),
        "summaries": quantile_summary(worlds),
        "interpretation_firewall": (
            "These summaries diagnose timing, mechanism flows, and heterogeneity. "
            "They do not redefine or refit the preregistered H1/H2/H3 predictor."
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
