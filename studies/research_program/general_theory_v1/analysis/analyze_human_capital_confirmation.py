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


def paired_ci(diff: pd.Series) -> dict:
    x = diff.dropna().to_numpy(float)
    if len(x) < 2:
        return {"n": int(len(x)), "mean": float(np.mean(x)) if len(x) else None, "ci95": None}
    mean = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(len(x)))
    return {"n": int(len(x)), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    df["experience_capability_deficit"] = 1.0 - (
        (0.75 + 0.50 * df.mean_experience) /
        (0.75 + 0.50 * df.baseline_experience)
    )
    end = df[np.isclose(df.time, 360.0)].copy()
    slow = end[np.isclose(end.recruitment_mult, 0.5) & np.isclose(end.training_mult, 0.5)].set_index("seed")
    fast = end[np.isclose(end.recruitment_mult, 4.0) & np.isclose(end.training_mult, 4.0)].set_index("seed")
    common = slow.index.intersection(fast.index)
    slow = slow.loc[common]
    fast = fast.loc[common]

    headcount_diff = fast.personnel_recovery_fraction - slow.personnel_recovery_fraction
    deficit_diff = fast.experience_capability_deficit - slow.experience_capability_deficit
    experience_diff = fast.mean_experience - slow.mean_experience

    gates = {
        "fast_minus_slow_headcount_recovery_ge_0_20": float(headcount_diff.mean()) >= 0.20,
        "fast_minus_slow_veterancy_deficit_ge_0_05": float(deficit_diff.mean()) >= 0.05,
        "fast_mean_experience_lower": float(experience_diff.mean()) < 0.0,
    }

    diag = []
    for m in [0.5, 1.0, 2.0, 4.0]:
        g = end[np.isclose(end.recruitment_mult, m) & np.isclose(end.training_mult, m)]
        diag.append({
            "multiplier": m,
            "n": int(len(g)),
            "mean_headcount_recovery": float(g.personnel_recovery_fraction.mean()),
            "mean_experience": float(g.mean_experience.mean()),
            "mean_veterancy_capability_deficit": float(g.experience_capability_deficit.mean()),
        })
    head = [x["mean_headcount_recovery"] for x in diag]
    deficits = [x["mean_veterancy_capability_deficit"] for x in diag]
    monotone = {
        "diagonal_headcount_non_decreasing": all(b >= a - 1e-12 for a, b in zip(head, head[1:])),
        "diagonal_veterancy_deficit_non_decreasing": all(b >= a - 1e-12 for a, b in zip(deficits, deficits[1:])),
    }

    time_path = []
    for time in sorted(df.time.unique()):
        for label, r, t in [("slow_0_5x", 0.5, 0.5), ("fast_4x", 4.0, 4.0)]:
            g = df[np.isclose(df.time, time) & np.isclose(df.recruitment_mult, r) & np.isclose(df.training_mult, t)]
            time_path.append({
                "time": float(time), "cell": label, "n": int(len(g)),
                "mean_headcount_recovery": float(g.personnel_recovery_fraction.mean()),
                "mean_experience": float(g.mean_experience.mean()),
                "mean_veterancy_capability_deficit": float(g.experience_capability_deficit.mean()),
            })

    passed = all(gates.values())
    out = {
        "schema_version": "pineland.human_capital_absorption_confirmation_results.v1",
        "status": "QUANTITY_QUALITY_REGENERATION_TRADEOFF_CONFIRMED_ON_SYNTHETIC_SUPPORT" if passed else "PRIMARY_CONFIRMATION_GATES_NOT_ALL_MET",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "primary_contrast_360d": {
            "slow": {
                "mean_headcount_recovery": float(slow.personnel_recovery_fraction.mean()),
                "mean_experience": float(slow.mean_experience.mean()),
                "mean_veterancy_capability_deficit": float(slow.experience_capability_deficit.mean()),
            },
            "fast": {
                "mean_headcount_recovery": float(fast.personnel_recovery_fraction.mean()),
                "mean_experience": float(fast.mean_experience.mean()),
                "mean_veterancy_capability_deficit": float(fast.experience_capability_deficit.mean()),
            },
            "fast_minus_slow_headcount": paired_ci(headcount_diff),
            "fast_minus_slow_veterancy_deficit": paired_ci(deficit_diff),
            "fast_minus_slow_experience": paired_ci(experience_diff),
        },
        "gates": gates,
        "secondary_diagonal": diag,
        "secondary_monotonicity": monotone,
        "time_path": time_path,
        "interpretation_guard": "Synthetic formation-memory mechanism only; real militaries need not share Pineland's experience or replacement coefficients.",
    }
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "gates": gates, "primary": out["primary_contrast_360d"]}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
