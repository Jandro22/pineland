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
        c = g[g.collapsed_bool]
        rows.append(
            {
                "recruitment_multiplier": float(rate),
                "n": int(len(g)),
                "joint_viability_fraction": float(g.joint_viable.mean()),
                "collapse_fraction": float(g.collapsed_bool.mean()),
                "median_final_rooted": float(g.final_rooted.median()),
                "median_final_operational_force": float(g.final_operational_force.median()),
                "median_final_capital": float(g.final_capital.median()),
                "median_final_cumulative_recruitment": float(g.final_cumulative_recruitment.median()),
                "median_runway_ratio": float(g.runway_ratio.median()),
                "collapse_causes": {str(k): int(v) for k, v in c.collapse_cause.value_counts().items()},
            }
        )
    s = pd.DataFrame(rows).sort_values("recruitment_multiplier")
    q = s.set_index("recruitment_multiplier")
    interior = float(q.loc[[0.03125, 0.0625, 0.125], "joint_viability_fraction"].mean())
    zero = float(q.loc[0.0, "joint_viability_fraction"])
    high = float(q.loc[0.25, "joint_viability_fraction"])

    high_raw = d[d.recruitment_multiplier.eq(0.25) & d.collapsed_bool]
    zero_raw = d[d.recruitment_multiplier.eq(0.0) & d.collapsed_bool]
    high_capital_share = float((high_raw.collapse_cause == "capital").mean()) if len(high_raw) else 0.0
    zero_capital_fraction_all = float(((d.recruitment_multiplier.eq(0.0)) & d.collapsed_bool & d.collapse_cause.eq("capital")).sum() / max((d.recruitment_multiplier.eq(0.0)).sum(), 1))
    zero_causes = zero_raw.collapse_cause.value_counts()
    zero_stochastic_plurality = bool(len(zero_causes) == 0 or zero_causes.get("stochastic", 0) == zero_causes.max())

    gates = {
        "interior_beats_zero_by_0.05": bool(interior - zero >= 0.05 - 1e-12),
        "interior_beats_0.25_by_0.50": bool(interior - high >= 0.50 - 1e-12),
        "0.25_capital_collapse_share_at_least_0.75": bool(high_capital_share >= 0.75),
        "zero_stochastic_plurality": zero_stochastic_plurality,
        "zero_capital_trigger_fraction_at_most_0.25": bool(zero_capital_fraction_all <= 0.25),
    }
    confirmed = all(gates.values())
    result = {
        "schema_version": "pineland.insurgent_mobilization_interior_optimum_confirmation_results.v1",
        "status": "INTERIOR_MOBILIZATION_OPTIMUM_CONFIRMED" if confirmed else "METABOLIC_CEILING_CONFIRMED_INTERIOR_OPTIMUM_NOT_CONFIRMED",
        "historical_outcomes_used": False,
        "input": a.csv,
        "input_sha256": sha256(a.csv),
        "seed_count": int(d.seed.nunique()),
        "cell_summary": s.to_dict("records"),
        "mean_interior_joint_viability": interior,
        "zero_joint_viability": zero,
        "0.25_joint_viability": high,
        "0.25_capital_trigger_share_among_collapses": high_capital_share,
        "zero_capital_trigger_fraction_all_cases": zero_capital_fraction_all,
        "gates": gates,
        "guard": "Fresh synthetic confirmation only; confirms a mechanism band, not an empirical recruitment-rate optimum.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "gates": gates, "interior": interior, "zero": zero, "high": high}, indent=2))


if __name__ == "__main__":
    main()
