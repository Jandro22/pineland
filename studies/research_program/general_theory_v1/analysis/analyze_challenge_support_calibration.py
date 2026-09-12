#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cell_id(share: float, resource: float) -> str:
    return f"S{share:.4f}_R{resource:g}"


def choose(summary: pd.DataFrame, target: float, prefer_rooted: bool = False) -> dict:
    q = summary.copy()
    q["distance"] = (q.live_fraction - target).abs()
    sort_cols = ["distance"]
    ascending = [True]
    if prefer_rooted:
        sort_cols.append("median_rooted")
        ascending.append(False)
    sort_cols += ["resource_multiplier", "initial_insurgent_share", "cell"]
    ascending += [True, True, True]
    row = q.sort_values(sort_cols, ascending=ascending).iloc[0]
    return row.to_dict()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    df = pd.read_csv(ns.csv)
    final = df[df.time.eq(360.0)].copy()
    final["live"] = (
        (final.rooted_armed_membership_mass > 0.0)
        & (final.recruitment_hazard_mass > 0.0)
        & (final.fielded_force_personnel > 0.0)
    )
    final["cell"] = [cell_id(s, r) for s, r in zip(final.initial_insurgent_share, final.resource_multiplier)]
    rows = []
    for cell, g in final.groupby("cell"):
        rows.append({
            "cell": cell,
            "initial_insurgent_share": float(g.initial_insurgent_share.iloc[0]),
            "resource_multiplier": float(g.resource_multiplier.iloc[0]),
            "n": int(len(g)),
            "live_fraction": float(g.live.mean()),
            "median_rooted": float(g.rooted_armed_membership_mass.median()),
            "median_hazard": float(g.recruitment_hazard_mass.median()),
            "median_force": float(g.fielded_force_personnel.median()),
            "median_insurgent_control": float(g.population_weighted_insurgent_control.median()),
        })
    summary = pd.DataFrame(rows)
    selected = {
        "weak": choose(summary, 0.25),
        "moderate": choose(summary, 0.50),
        "strong": choose(summary, 0.75, prefer_rooted=True),
    }
    result = {
        "schema_version": "pineland.insurgency_challenge_support_calibration_results.v1",
        "status": "DESIGN_SUPPORT_CALIBRATED_BASELINE_ONLY",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(final.seed.nunique()),
        "cell_summary": summary.sort_values(["initial_insurgent_share", "resource_multiplier"]).to_dict("records"),
        "selected_regimes": selected,
        "firewall": "Selection uses baseline-policy persistence only. Policy ranking on this seed block is forbidden.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected_regimes": selected}, indent=2))


if __name__ == "__main__":
    main()
