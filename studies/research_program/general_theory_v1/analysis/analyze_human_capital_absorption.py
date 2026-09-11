#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    required = {
        "seed", "recruitment_mult", "training_mult", "time",
        "baseline_personnel", "baseline_experience", "baseline_capability_core",
        "personnel", "mean_experience", "capability_core",
        "personnel_recovery_fraction", "capability_recovery_fraction",
        "headcount_capability_gap",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"missing columns: {missing}")

    # The preregistered primary metric is preserved exactly, even though the
    # P^0.72 combat-power term makes aggregate capability recovery exceed
    # headcount recovery at low personnel.  Do not redefine it post hoc.
    end = df[np.isclose(df.time, 360.0)].copy()
    primary = []
    for (r, t), g in end.groupby(["recruitment_mult", "training_mult"]):
        primary.append({
            "recruitment_mult": float(r),
            "training_mult": float(t),
            "n": int(len(g)),
            "mean_personnel_recovery_fraction": float(g.personnel_recovery_fraction.mean()),
            "mean_capability_recovery_fraction": float(g.capability_recovery_fraction.mean()),
            "mean_headcount_minus_capability_recovery_gap": float(g.headcount_capability_gap.mean()),
            "mean_experience": float(g.mean_experience.mean()),
        })

    # Secondary decomposition, explicitly labelled post-primary: isolate the
    # amount of combat capability lost only because experience has been diluted,
    # holding the realized personnel stock fixed.  In the production combat
    # equation the experience multiplier is g(E)=0.75+0.50E.
    baseline_g = 0.75 + 0.50 * df.baseline_experience
    realized_g = 0.75 + 0.50 * df.mean_experience
    df["experience_capability_ratio_at_same_headcount"] = realized_g / baseline_g
    df["experience_capability_deficit_at_same_headcount"] = 1.0 - df["experience_capability_ratio_at_same_headcount"]
    # Counterfactual aggregate capability at the realized personnel level if
    # veteran experience had remained at baseline; all non-experience factors
    # are held as in the analytic assay core.
    df["veteran_counterfactual_capability_core"] = df.capability_core / df.experience_capability_ratio_at_same_headcount
    df["actual_vs_veteran_same_headcount_capability_ratio"] = (
        df.capability_core / df.veteran_counterfactual_capability_core
    )

    secondary = []
    for (r, t, time), g in df.groupby(["recruitment_mult", "training_mult", "time"]):
        secondary.append({
            "recruitment_mult": float(r),
            "training_mult": float(t),
            "time": float(time),
            "n": int(len(g)),
            "mean_personnel_recovery_fraction": float(g.personnel_recovery_fraction.mean()),
            "mean_experience": float(g.mean_experience.mean()),
            "mean_experience_capability_deficit_at_same_headcount": float(
                g.experience_capability_deficit_at_same_headcount.mean()
            ),
        })

    # Summarize fastest vs slowest regeneration throughput at 360d.  This is
    # descriptive, not a preregistered promotion gate.
    slow = end[(np.isclose(end.recruitment_mult, 0.5)) & (np.isclose(end.training_mult, 0.5))]
    fast = end[(np.isclose(end.recruitment_mult, 4.0)) & (np.isclose(end.training_mult, 4.0))]
    def same_headcount_deficit(x: pd.DataFrame) -> float:
        bg = 0.75 + 0.50 * x.baseline_experience
        rg = 0.75 + 0.50 * x.mean_experience
        return float((1.0 - rg / bg).mean())

    out = {
        "schema_version": "pineland.human_capital_absorption_results.v1",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "preregistered_primary": {
            "status": "PRIMARY_METRIC_SIGN_REVERSED_BY_SUBLINEAR_PERSONNEL_SCALING",
            "interpretation": (
                "The preregistered headcount-minus-total-capability recovery gap is negative on the assay support. "
                "This does not refute veterancy dilution: aggregate capability scales as P^0.72, so capability fraction "
                "can exceed headcount fraction after a personnel shock. The primary metric is retained as a measurement-design falsification."
            ),
            "cells_at_360d": primary,
        },
        "secondary_post_primary_decomposition": {
            "status": "EXPERIENCE_DILUTION_QUANTIFIED_AT_FIXED_REALIZED_HEADCOUNT",
            "definition": "1 - (0.75+0.50*E_actual)/(0.75+0.50*E_baseline)",
            "cells_by_time": secondary,
            "slow_0_5x_0_5x_at_360d": {
                "mean_personnel_recovery_fraction": float(slow.personnel_recovery_fraction.mean()),
                "mean_experience": float(slow.mean_experience.mean()),
                "mean_experience_capability_deficit_at_same_headcount": same_headcount_deficit(slow),
            },
            "fast_4x_4x_at_360d": {
                "mean_personnel_recovery_fraction": float(fast.personnel_recovery_fraction.mean()),
                "mean_experience": float(fast.mean_experience.mean()),
                "mean_experience_capability_deficit_at_same_headcount": same_headcount_deficit(fast),
            },
        },
        "guard": (
            "The secondary decomposition is mechanistic and post-primary. It is not a replacement preregistered endpoint. "
            "A future fresh contract should preregister fixed-headcount veteran-counterfactual capability if that quantity is promoted."
        ),
    }
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary_status": out["preregistered_primary"]["status"],
        "slow": out["secondary_post_primary_decomposition"]["slow_0_5x_0_5x_at_360d"],
        "fast": out["secondary_post_primary_decomposition"]["fast_4x_4x_at_360d"],
    }, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
