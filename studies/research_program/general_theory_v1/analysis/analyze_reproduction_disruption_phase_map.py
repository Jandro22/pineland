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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    df = pd.read_csv(ns.csv)
    expected = df.seed.nunique() * 25 * 3
    if len(df) != expected:
        raise SystemExit(f"row integrity failed: got {len(df)}, expected {expected}")
    final = df[np.isclose(df.time, 360.0)].copy()
    final["live"] = (
        (final.rooted_armed_membership_mass > 0.0)
        & (final.recruitment_hazard_mass > 0.0)
        & (final.fielded_force_personnel > 0.0)
    )
    rows = []
    for (r, d), g in final.groupby(["recruitment_multiplier", "disruption_multiplier"]):
        rows.append({
            "recruitment_multiplier": float(r),
            "disruption_multiplier": float(d),
            "n": int(len(g)),
            "live_fraction": float(g.live.mean()),
            "median_rooted": float(g.rooted_armed_membership_mass.median()),
            "median_hazard": float(g.recruitment_hazard_mass.median()),
            "median_force": float(g.fielded_force_personnel.median()),
            "median_insurgent_control": float(g.population_weighted_insurgent_control.median()),
            "median_cumulative_disruption": float(g.cumulative_underground_disruption.median()),
            "median_intelligence": float(g.population_weighted_intelligence_penetration.median()),
        })
    summary = pd.DataFrame(rows).sort_values(["recruitment_multiplier", "disruption_multiplier"])

    finite = summary[summary.disruption_multiplier > 0].copy()
    finite["rate_ratio"] = finite.recruitment_multiplier / finite.disruption_multiplier
    mixed = summary[(summary.live_fraction > 0.0) & (summary.live_fraction < 1.0)].copy()
    # Descriptive transition brackets only.  These are not a universal R0 and
    # the raw config-rate ratio ignores endogenous access/intelligence factors.
    live_cells = finite[finite.live_fraction > 0.0]
    dead_cells = finite[finite.live_fraction < 1.0]
    transition = {
        "mixed_cell_count": int(len(mixed)),
        "minimum_rate_ratio_with_any_live": (
            float(live_cells.rate_ratio.min()) if len(live_cells) else None
        ),
        "maximum_rate_ratio_with_any_dead": (
            float(dead_cells.rate_ratio.max()) if len(dead_cells) else None
        ),
        "all_zero_disruption_live_fractions": {
            f"R{r:g}": float(g.live_fraction.iloc[0])
            for r, g in summary[summary.disruption_multiplier.eq(0.0)].groupby("recruitment_multiplier")
        },
    }

    # Suggest support cells for a future fresh-seed policy experiment only if
    # the screen actually spans weak/moderate/strong persistence levels.
    targets = {"weak": 0.25, "moderate": 0.50, "strong": 0.75}
    selected = {}
    for name, target in targets.items():
        q = summary.copy()
        q["distance"] = (q.live_fraction - target).abs()
        row = q.sort_values(
            ["distance", "disruption_multiplier", "recruitment_multiplier"],
            ascending=[True, False, True],
        ).iloc[0]
        selected[name] = row.to_dict()
    span_ok = (
        summary.live_fraction.min() <= 0.25
        and summary.live_fraction.max() >= 0.75
        and len(summary.live_fraction.unique()) >= 3
    )
    result = {
        "schema_version": "pineland.reproduction_disruption_phase_map_results.v1",
        "status": (
            "REPRODUCTION_DISRUPTION_TRANSITION_SPANNED"
            if span_ok
            else "FROZEN_GRID_DID_NOT_SPAN_TRANSITION"
        ),
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(final.seed.nunique()),
        "cell_summary": summary.to_dict("records"),
        "transition_descriptors": transition,
        "candidate_future_support_cells": selected if span_ok else None,
        "firewall": "This seed block is baseline-policy mechanism mapping only. Any policy comparison must use fresh seeds and frozen selected cells.",
        "interpretation_guard": "The config-rate ratio is not a reproduction number. Effective recruitment depends on access, social exposure, ideology, grievance, fear, political access, and rootedness; effective disruption depends on intelligence, security, and administration.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "transition_descriptors": transition,
        "candidate_future_support_cells": result["candidate_future_support_cells"],
    }, indent=2))


if __name__ == "__main__":
    main()
