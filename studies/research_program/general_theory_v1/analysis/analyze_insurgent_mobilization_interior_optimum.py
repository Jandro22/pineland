#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = pd.read_csv(a.csv)
    d["collapsed_bool"] = d.collapsed.astype(str).str.lower().isin(["true", "1"])
    d["joint_viable"] = (
        (~d.collapsed_bool)
        & (d.final_rooted > 0.0)
        & (d.final_operational_force > 0.0)
    )

    rows = []
    for rate, g in d.groupby("recruitment_multiplier"):
        collapsed = g[g.collapsed_bool]
        rows.append(
            {
                "recruitment_multiplier": float(rate),
                "n": int(len(g)),
                "joint_viability_fraction": float(g.joint_viable.mean()),
                "collapse_fraction": float(g.collapsed_bool.mean()),
                "median_collapse_time": None
                if collapsed.empty
                else float(collapsed.collapse_time.median()),
                "median_final_rooted": float(g.final_rooted.median()),
                "median_final_operational_force": float(g.final_operational_force.median()),
                "median_final_capital": float(g.final_capital.median()),
                "median_final_cumulative_recruitment": float(
                    g.final_cumulative_recruitment.median()
                ),
                "median_runway_ratio": float(g.runway_ratio.median()),
                "collapse_causes": {
                    str(k): int(v)
                    for k, v in collapsed.collapse_cause.value_counts().items()
                },
            }
        )
    summary = pd.DataFrame(rows).sort_values("recruitment_multiplier")
    lo = float(summary.recruitment_multiplier.min())
    hi = float(summary.recruitment_multiplier.max())
    endpoints = summary[summary.recruitment_multiplier.isin([lo, hi])]
    interior = summary[
        (summary.recruitment_multiplier > lo) & (summary.recruitment_multiplier < hi)
    ]
    endpoint_best = float(endpoints.joint_viability_fraction.max())
    strict_interior = bool(
        len(interior) and (interior.joint_viability_fraction > endpoint_best).any()
    )
    best = summary.sort_values(
        [
            "joint_viability_fraction",
            "median_final_rooted",
            "median_final_operational_force",
            "median_final_capital",
        ],
        ascending=[False, False, False, False],
    ).iloc[0]
    status = (
        "INTERIOR_MOBILIZATION_OPTIMUM_SUPPORTED"
        if strict_interior
        else "NO_STRICT_INTERIOR_OPTIMUM_ON_TESTED_SUPPORT"
    )
    result = {
        "schema_version": "pineland.insurgent_mobilization_interior_optimum_results.v1",
        "status": status,
        "historical_outcomes_used": False,
        "input": a.csv,
        "input_sha256": sha256(a.csv),
        "seed_count": int(d.seed.nunique()),
        "cell_summary": summary.to_dict("records"),
        "best_tested_cell": best.to_dict(),
        "strict_interior_viability_maximum": strict_interior,
        "guard": "Fresh synthetic mechanism screen only; no empirical mobilization recommendation.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": status, "best_tested_cell": result["best_tested_cell"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
