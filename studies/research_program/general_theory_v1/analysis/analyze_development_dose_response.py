#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


OUTCOMES = [
    "mean_government_legitimacy",
    "mean_state_legitimacy",
    "mean_political_access",
    "mean_local_institution_capacity",
    "population_weighted_government_control",
]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ci(x: pd.Series) -> dict:
    a = x.dropna().to_numpy(float)
    if not len(a):
        return {"n": 0, "mean": None, "ci95": None}
    m = float(a.mean())
    if len(a) == 1:
        return {"n": 1, "mean": m, "ci95": None}
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return {"n": int(len(a)), "mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    df = pd.read_csv(ns.csv)
    final = df[df.timepoint.eq("final")].copy()
    modes = sorted(final.allocation_mode.unique())
    multipliers = sorted(final.budget_multiplier.unique())
    if modes != ["equal_locality", "marginal_return"]:
        raise SystemExit(f"unexpected modes {modes}")
    if multipliers != [1.0, 5.0, 10.0, 20.0, 40.0, 80.0]:
        raise SystemExit(f"unexpected multipliers {multipliers}")

    curves = {}
    for mode in modes:
        d = final[final.allocation_mode.eq(mode)]
        base = d[d.budget_multiplier.eq(1.0)].set_index("seed")
        rows = []
        for mult in multipliers:
            g = d[d.budget_multiplier.eq(mult)].set_index("seed").loc[base.index]
            inc_cost = g.public_development_outflow - base.public_development_outflow
            row = {
                "budget_multiplier": mult,
                "mean_public_development_outflow": float(g.public_development_outflow.mean()),
                "mean_incremental_public_outflow_vs_1x": float(inc_cost.mean()),
                "outcomes": {},
            }
            for outcome in OUTCOMES:
                delta = g[outcome] - base[outcome]
                c = ci(delta)
                positive_cost = inc_cost > 1.0e-12
                ratios = delta[positive_cost] / inc_cost[positive_cost] * 100_000.0
                c["gain_per_100k_incremental_public_outflow"] = (
                    float(ratios.mean()) if len(ratios) else None
                )
                row["outcomes"][outcome] = c
            rows.append(row)

        # Discrete marginal returns between adjacent frozen doses.
        marginal = []
        for lo, hi in zip(multipliers[:-1], multipliers[1:]):
            a = d[d.budget_multiplier.eq(lo)].set_index("seed")
            b = d[d.budget_multiplier.eq(hi)].set_index("seed").loc[a.index]
            cost = b.public_development_outflow - a.public_development_outflow
            mrow = {"from": lo, "to": hi, "mean_incremental_public_outflow": float(cost.mean()), "outcomes": {}}
            for outcome in OUTCOMES:
                delta = b[outcome] - a[outcome]
                good = cost > 1.0e-12
                ratio = delta[good] / cost[good] * 100_000.0
                mrow["outcomes"][outcome] = {
                    "mean_delta": float(delta.mean()),
                    "mean_gain_per_100k_incremental_public_outflow": float(ratio.mean()) if len(ratio) else None,
                }
            marginal.append(mrow)
        curves[mode] = {"vs_1x": rows, "adjacent_marginal_returns": marginal}

    # Budget-neutral allocation comparison at every dose.
    allocation = []
    for mult in multipliers:
        e = final[(final.allocation_mode.eq("equal_locality")) & final.budget_multiplier.eq(mult)].set_index("seed")
        m = final[(final.allocation_mode.eq("marginal_return")) & final.budget_multiplier.eq(mult)].set_index("seed").loc[e.index]
        row = {"budget_multiplier": mult, "marginal_return_minus_equal": {}}
        for outcome in OUTCOMES:
            row["marginal_return_minus_equal"][outcome] = ci(m[outcome] - e[outcome])
        row["public_outflow_difference"] = ci(m.public_development_outflow - e.public_development_outflow)
        allocation.append(row)

    result = {
        "schema_version": "pineland.development_dose_response_results.v1",
        "status": "SYNTHETIC_DEVELOPMENT_DOSE_RESPONSE_MEASURED",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(final.seed.nunique()),
        "curves": curves,
        "allocation_comparison": allocation,
        "guard": "Internal Pineland capital units are not real dollars. Dose response is synthetic and state-side; insurgent suppression is not inferred from this assay.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {
        mode: [
            {
                "multiplier": r["budget_multiplier"],
                "spend": r["mean_public_development_outflow"],
                "government_legitimacy_gain": r["outcomes"]["mean_government_legitimacy"]["mean"],
                "institution_capacity_gain": r["outcomes"]["mean_local_institution_capacity"]["mean"],
            }
            for r in curves[mode]["vs_1x"]
        ]
        for mode in modes
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
