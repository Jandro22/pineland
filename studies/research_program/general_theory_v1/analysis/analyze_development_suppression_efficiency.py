#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


LOWER_IS_BETTER = [
    "recruitment_hazard_mass",
    "cumulative_recruitment_since_anchor",
    "rooted_armed_membership_mass",
    "active_owner_fielded_force_personnel",
    "foothold_strength_sum",
    "cumulative_insurgent_actions_since_anchor",
    "population_weighted_insurgent_control",
    "government_military_losses_since_anchor",
    "population_loss_since_anchor",
    "displaced_population_fraction",
]

HIGHER_IS_BETTER = [
    "population_weighted_government_control",
    "mean_government_legitimacy",
    "mean_political_access",
    "mean_local_institution_capacity",
]

INSURGENT_OUTCOMES = [
    "recruitment_hazard_mass",
    "cumulative_recruitment_since_anchor",
    "rooted_armed_membership_mass",
    "active_owner_fielded_force_personnel",
    "foothold_strength_sum",
    "cumulative_insurgent_actions_since_anchor",
    "population_weighted_insurgent_control",
]

MODES = ["equal_locality", "marginal_return", "need_weighted", "threat_weighted"]
MULTIPLIERS = [1.0, 2.0, 5.0, 10.0, 20.0]
NORMALIZED_COST = 1200.0  # 1% of one default monthly 120,000 policy budget.


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ci(values: pd.Series) -> dict:
    a = values.dropna().to_numpy(float)
    if not len(a):
        return {"n": 0, "mean": None, "ci95": None}
    mean = float(a.mean())
    if len(a) == 1:
        return {"n": 1, "mean": mean, "ci95": None}
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return {"n": int(len(a)), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def improvement(treatment: pd.Series, baseline: pd.Series, outcome: str) -> pd.Series:
    if outcome in LOWER_IS_BETTER:
        return baseline - treatment
    return treatment - baseline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    df = pd.read_csv(ns.csv)
    modes = sorted(df.allocation_mode.unique().tolist())
    multipliers = sorted(df.budget_multiplier.unique().tolist())
    if modes != MODES:
        raise SystemExit(f"unexpected modes {modes}")
    if multipliers != MULTIPLIERS:
        raise SystemExit(f"unexpected multipliers {multipliers}")

    anchor = df[df.timepoint.eq("anchor")].copy()
    anchor_one = anchor[(anchor.allocation_mode.eq("equal_locality")) & anchor.budget_multiplier.eq(1.0)]
    anchor_live_fraction = float((anchor_one.canonical_insurgent_active.astype(int) != 0).mean())
    anchor_rooted_fraction = float((anchor_one.rooted_armed_membership_mass > 1e-9).mean())

    by_timepoint: dict[str, dict] = {}
    for timepoint in ["intervention_end", "final"]:
        tp = df[df.timepoint.eq(timepoint)].copy()
        curves = {}
        for mode in MODES:
            d = tp[tp.allocation_mode.eq(mode)]
            base = d[d.budget_multiplier.eq(1.0)].set_index("seed")
            cells = []
            for mult in MULTIPLIERS:
                g = d[d.budget_multiplier.eq(mult)].set_index("seed").loc[base.index]
                incremental_cost = (
                    g.public_development_outflow_intervention
                    - base.public_development_outflow_intervention
                )
                cell = {
                    "budget_multiplier": mult,
                    "mean_public_development_outflow": float(
                        g.public_development_outflow_intervention.mean()
                    ),
                    "mean_incremental_public_outflow_vs_1x": float(incremental_cost.mean()),
                    "canonical_insurgent_active_fraction": float(
                        (g.canonical_insurgent_active.astype(int) != 0).mean()
                    ),
                    "outcomes": {},
                }
                for outcome in LOWER_IS_BETTER + HIGHER_IS_BETTER:
                    imp = improvement(g[outcome], base[outcome], outcome)
                    good = incremental_cost > 1e-12
                    per_unit = imp[good] / incremental_cost[good] * NORMALIZED_COST
                    record = ci(imp)
                    record["mean_improvement_per_1200_incremental_public_capital"] = (
                        float(per_unit.mean()) if len(per_unit) else None
                    )
                    cell["outcomes"][outcome] = record
                cells.append(cell)
            curves[mode] = cells

        allocation = []
        for mult in MULTIPLIERS:
            equal = tp[
                (tp.allocation_mode.eq("equal_locality"))
                & tp.budget_multiplier.eq(mult)
            ].set_index("seed")
            row = {"budget_multiplier": mult, "modes_vs_equal": {}}
            for mode in MODES:
                g = tp[
                    (tp.allocation_mode.eq(mode))
                    & tp.budget_multiplier.eq(mult)
                ].set_index("seed").loc[equal.index]
                rec = {
                    "public_outflow_difference": ci(
                        g.public_development_outflow_intervention
                        - equal.public_development_outflow_intervention
                    ),
                    "outcomes": {},
                }
                for outcome in LOWER_IS_BETTER + HIGHER_IS_BETTER:
                    rec["outcomes"][outcome] = ci(improvement(g[outcome], equal[outcome], outcome))
                row["modes_vs_equal"][mode] = rec
            allocation.append(row)
        by_timepoint[timepoint] = {"dose_curves": curves, "allocation_comparison": allocation}

    # Durability: compare the same paired dose-vs-1x improvement at end and final.
    durability = {}
    end = df[df.timepoint.eq("intervention_end")]
    final = df[df.timepoint.eq("final")]
    for mode in MODES:
        durability[mode] = []
        for mult in MULTIPLIERS[1:]:
            e_t = end[(end.allocation_mode.eq(mode)) & end.budget_multiplier.eq(mult)].set_index("seed")
            e_b = end[(end.allocation_mode.eq(mode)) & end.budget_multiplier.eq(1.0)].set_index("seed").loc[e_t.index]
            f_t = final[(final.allocation_mode.eq(mode)) & final.budget_multiplier.eq(mult)].set_index("seed").loc[e_t.index]
            f_b = final[(final.allocation_mode.eq(mode)) & final.budget_multiplier.eq(1.0)].set_index("seed").loc[e_t.index]
            outcome_rows = {}
            for outcome in INSURGENT_OUTCOMES:
                end_imp = improvement(e_t[outcome], e_b[outcome], outcome)
                final_imp = improvement(f_t[outcome], f_b[outcome], outcome)
                ratios = []
                for a, b in zip(end_imp.to_numpy(float), final_imp.to_numpy(float)):
                    if abs(a) > 1e-12:
                        ratios.append(b / a)
                outcome_rows[outcome] = {
                    "intervention_end_improvement": ci(end_imp),
                    "final_improvement": ci(final_imp),
                    "mean_retention_ratio_final_over_end": float(np.mean(ratios)) if ratios else None,
                }
            durability[mode].append({"budget_multiplier": mult, "outcomes": outcome_rows})

    result = {
        "schema_version": "pineland.development_suppression_efficiency_results.v1",
        "status": "SYNTHETIC_DEVELOPMENT_SUPPRESSION_EFFICIENCY_MEASURED",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(df.seed.nunique()),
        "anchor_support": {
            "canonical_insurgent_active_fraction": anchor_live_fraction,
            "rooted_positive_fraction": anchor_rooted_fraction,
        },
        "normalized_cost_unit": {
            "pineland_capital": NORMALIZED_COST,
            "meaning": "1% of the default one-month 120,000 federal policy-budget ceiling",
            "real_dollar_formula": "If one default monthly federal policy budget is B dollars, multiply Pineland capital by B/120000 to obtain the chosen dollar-equivalent reporting scale.",
        },
        "results": by_timepoint,
        "durability": durability,
        "guard": "Synthetic model ROI only. Internal capital is not USD and no empirical aid-effect size is claimed.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    # Compact decision-oriented printout.
    compact = {}
    for timepoint in ["intervention_end", "final"]:
        rows = []
        for mode, cells in by_timepoint[timepoint]["dose_curves"].items():
            for cell in cells[1:]:
                rows.append(
                    {
                        "mode": mode,
                        "multiplier": cell["budget_multiplier"],
                        "incremental_public_outflow": cell["mean_incremental_public_outflow_vs_1x"],
                        "recruits_prevented_per_1pct_monthly_budget": cell["outcomes"]["cumulative_recruitment_since_anchor"]["mean_improvement_per_1200_incremental_public_capital"],
                        "hazard_reduction_per_1pct_monthly_budget": cell["outcomes"]["recruitment_hazard_mass"]["mean_improvement_per_1200_incremental_public_capital"],
                        "rooted_reduction_per_1pct_monthly_budget": cell["outcomes"]["rooted_armed_membership_mass"]["mean_improvement_per_1200_incremental_public_capital"],
                    }
                )
        compact[timepoint] = rows
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
