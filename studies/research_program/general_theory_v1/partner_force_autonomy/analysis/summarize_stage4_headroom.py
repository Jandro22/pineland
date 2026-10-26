#!/usr/bin/env python3
"""Summarize the post-completion Stage-4 headroom reconstruction.

The input is produced by analyze_stage4_headroom.py from frozen trajectory
telemetry. This script deliberately limits inference to descriptive target and
quartile summaries plus pooled Pearson/Spearman association. It does not turn
headroom into a preregistered Stage-4 estimand.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


TARGETS = ["command", "forcegen", "logistics"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--summary-csv", required=True, type=Path)
    p.add_argument("--global-json", required=True, type=Path)
    return p.parse_args()


def main() -> None:
    ns = parse_args()
    d = pd.read_csv(ns.input)
    m = d[
        d["observed_target_match"].astype(bool)
        & d["factor_support_target"].isin(TARGETS)
        & (d["factor_support_intensity"].astype(float) > 0.0)
    ].copy()
    defined = m[m["pre_headroom"].astype(float) >= 0.0].copy()

    global_summary = {
        "analysis_status": "POST_COMPLETION_DESCRIPTIVE_SYNTHESIS",
        "observed_matched_treated_worlds": int(len(m)),
        "headroom_defined_worlds": int(len(defined)),
        "headroom_undefined_worlds": int(len(m) - len(defined)),
        "pearson_headroom_vs_delta_capability_h30": float(
            defined[["pre_headroom", "delta_composite_capability_h30"]]
            .corr(method="pearson")
            .iloc[0, 1]
        ),
        "spearman_headroom_vs_delta_capability_h30": float(
            defined[["pre_headroom", "delta_composite_capability_h30"]]
            .corr(method="spearman")
            .iloc[0, 1]
        ),
        "interpretation": (
            "Static pre-withdrawal headroom is not a monotonic predictor of realized "
            "+30-day system yield in the dynamic Stage-4 migration worlds."
        ),
    }

    rows: list[dict[str, object]] = []
    for target, g in defined.groupby("factor_support_target", sort=True):
        rows.append(
            {
                "summary_type": "target",
                "group": target,
                "n": len(g),
                "mean_headroom": g["pre_headroom"].mean(),
                "median_headroom": g["pre_headroom"].median(),
                "mean_delta_capability_h30": g["delta_composite_capability_h30"].mean(),
                "mean_delta_q_feasible_h360": g["delta_q_feasible_h360"].mean(),
                "persistent_migration_fraction": g["ever_persistently_migrated"].astype(bool).mean(),
            }
        )

    defined["headroom_quartile"] = pd.qcut(
        defined["pre_headroom"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop"
    )
    for quartile, g in defined.groupby("headroom_quartile", observed=False, sort=True):
        rows.append(
            {
                "summary_type": "quartile",
                "group": str(quartile),
                "n": len(g),
                "mean_headroom": g["pre_headroom"].mean(),
                "median_headroom": g["pre_headroom"].median(),
                "mean_delta_capability_h30": g["delta_composite_capability_h30"].mean(),
                "mean_delta_q_feasible_h360": g["delta_q_feasible_h360"].mean(),
                "persistent_migration_fraction": g["ever_persistently_migrated"].astype(bool).mean(),
            }
        )

    ns.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(ns.summary_csv, index=False)
    ns.global_json.write_text(json.dumps(global_summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(global_summary, indent=2))


if __name__ == "__main__":
    main()
