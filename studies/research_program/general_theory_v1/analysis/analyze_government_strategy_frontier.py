#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


STRATEGIES = [
    "baseline",
    "clean_governance",
    "spending_surge",
    "clean_spending_surge",
    "security_expansion",
    "police_first",
    "military_first",
    "admin_first",
    "integrated",
    "patronage_heavy",
]

LOWER_BETTER_INSURGENT = [
    "rooted_armed_membership_mass",
    "fielded_force_personnel",
    "foothold_strength_sum",
    "recruitment_hazard_mass",
    "population_weighted_insurgent_control",
    "cumulative_insurgent_actions_since_anchor",
]

HIGHER_BETTER_GOV = [
    "population_weighted_government_control",
    "mean_government_legitimacy",
    "mean_state_legitimacy",
    "mean_local_institution_capacity",
]

LOWER_BETTER_COSTS = [
    "government_military_losses_since_anchor",
    "population_loss_since_anchor",
    "displaced_population_fraction",
    "government_capital_outflow_intervention",
]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mean_ci(x: pd.Series) -> dict:
    a = x.dropna().to_numpy(float)
    if len(a) == 0:
        return {"n": 0, "mean": None, "ci95": None}
    mean = float(a.mean())
    if len(a) == 1:
        return {"n": 1, "mean": mean, "ci95": None}
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return {"n": int(len(a)), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def paired_contrasts(df: pd.DataFrame, timepoint: str) -> dict:
    d = df[df.timepoint.eq(timepoint)].copy()
    base = d[d.strategy.eq("baseline")].set_index("seed")
    result: dict[str, dict] = {}
    for strategy in STRATEGIES:
        g = d[d.strategy.eq(strategy)].set_index("seed")
        common = base.index.intersection(g.index)
        b = base.loc[common]
        s = g.loc[common]
        metrics = {}
        for metric in LOWER_BETTER_INSURGENT + LOWER_BETTER_COSTS:
            # Positive means strategy is better than baseline.
            metrics[metric] = mean_ci(b[metric] - s[metric])
        for metric in HIGHER_BETTER_GOV:
            metrics[metric] = mean_ci(s[metric] - b[metric])
        result[strategy] = metrics
    return result


def strategy_means(df: pd.DataFrame, timepoint: str) -> dict:
    d = df[df.timepoint.eq(timepoint)]
    metrics = LOWER_BETTER_INSURGENT + HIGHER_BETTER_GOV + LOWER_BETTER_COSTS + [
        "government_capital_inflow_intervention",
        "political_order_outflow_intervention",
        "governance_outflow_intervention",
        "state_regeneration_outflow_intervention",
        "other_outflow_intervention",
        "government_capital",
    ]
    out = {}
    for strategy in STRATEGIES:
        g = d[d.strategy.eq(strategy)]
        out[strategy] = {m: float(g[m].mean()) for m in metrics}
    return out


def pareto_front(means: dict[str, dict]) -> tuple[list[str], dict[str, list[str]]]:
    metrics = LOWER_BETTER_INSURGENT + LOWER_BETTER_COSTS + HIGHER_BETTER_GOV

    def oriented(strategy: str) -> np.ndarray:
        vals = []
        for m in LOWER_BETTER_INSURGENT + LOWER_BETTER_COSTS:
            vals.append(means[strategy][m])
        for m in HIGHER_BETTER_GOV:
            vals.append(-means[strategy][m])
        return np.asarray(vals, dtype=float)

    dominates: dict[str, list[str]] = {s: [] for s in STRATEGIES}
    nondominated = []
    for b in STRATEGIES:
        vb = oriented(b)
        beaten_by = []
        for a in STRATEGIES:
            if a == b:
                continue
            va = oriented(a)
            scale = np.maximum(np.maximum(np.abs(va), np.abs(vb)), 1.0)
            tol = 1e-10 * scale
            no_worse = np.all(va <= vb + tol)
            strictly_better = np.any(va < vb - tol)
            if no_worse and strictly_better:
                beaten_by.append(a)
                dominates[a].append(b)
        if not beaten_by:
            nondominated.append(b)
    return nondominated, dominates


def cost_effectiveness(means: dict[str, dict]) -> dict:
    base = means["baseline"]
    out: dict[str, dict] = {}
    for strategy in STRATEGIES:
        if strategy == "baseline":
            continue
        incremental_cost = (
            means[strategy]["government_capital_outflow_intervention"]
            - base["government_capital_outflow_intervention"]
        )
        row = {"incremental_gross_outflow": float(incremental_cost), "outcomes": {}}
        for metric in LOWER_BETTER_INSURGENT:
            improvement = base[metric] - means[strategy][metric]
            if incremental_cost > 1e-12:
                per_million = improvement / incremental_cost * 1_000_000.0
                status = "ratio_defined"
            elif improvement > 0:
                per_million = None
                status = "better_with_no_extra_gross_outflow"
            else:
                per_million = None
                status = "no_positive_incremental_effect"
            row["outcomes"][metric] = {
                "improvement_vs_baseline": float(improvement),
                "improvement_per_1m_incremental_outflow": (
                    float(per_million) if per_million is not None else None
                ),
                "status": status,
            }
        out[strategy] = row
    return out


def durability(end_contrasts: dict, final_contrasts: dict) -> dict:
    out = {}
    for strategy in STRATEGIES:
        if strategy == "baseline":
            continue
        row = {}
        for metric in LOWER_BETTER_INSURGENT:
            end = end_contrasts[strategy][metric]["mean"]
            final = final_contrasts[strategy][metric]["mean"]
            if end is not None and end > 0:
                retained = final / end if final is not None else None
                durable = bool(final is not None and final >= 0.5 * end)
            else:
                retained = None
                durable = False
            row[metric] = {
                "intervention_end_improvement": end,
                "final_improvement": final,
                "retained_fraction": float(retained) if retained is not None else None,
                "durable_by_preregistered_rule": durable,
            }
        out[strategy] = row
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    required_rows = df.seed.nunique() * len(STRATEGIES) * 3
    if len(df) != required_rows:
        raise SystemExit(f"row integrity failed: got {len(df)}, expected {required_rows}")
    if sorted(df.strategy.unique().tolist()) != sorted(STRATEGIES):
        raise SystemExit(f"unexpected strategies: {sorted(df.strategy.unique())}")
    expected_tp = {"anchor", "intervention_end", "final"}
    if set(df.timepoint.unique()) != expected_tp:
        raise SystemExit(f"unexpected timepoints: {set(df.timepoint.unique())}")

    end_means = strategy_means(df, "intervention_end")
    final_means = strategy_means(df, "final")
    end_contrasts = paired_contrasts(df, "intervention_end")
    final_contrasts = paired_contrasts(df, "final")
    nondominated, dominates = pareto_front(final_means)

    domination_counts = {
        s: {
            "strategies_dominated": sorted(dominates[s]),
            "count": len(dominates[s]),
        }
        for s in STRATEGIES
    }

    result = {
        "schema_version": "pineland.government_strategy_frontier_results.v1",
        "status": "SYNTHETIC_POLICY_FRONTIER_MEASURED",
        "historical_outcomes_used": False,
        "scope_guard": "Synthetic Pineland policy comparison only; not a real-world operational recommendation.",
        "input": args.csv,
        "input_sha256": sha256(args.csv),
        "seed_count": int(df.seed.nunique()),
        "strategy_count": len(STRATEGIES),
        "strategy_means_intervention_end": end_means,
        "strategy_means_final": final_means,
        "paired_improvement_vs_baseline_intervention_end": end_contrasts,
        "paired_improvement_vs_baseline_final": final_contrasts,
        "durability": durability(end_contrasts, final_contrasts),
        "cost_effectiveness_final": cost_effectiveness(final_means),
        "pareto_final": {
            "nondominated_strategies": nondominated,
            "domination_counts": domination_counts,
            "rule": "No single utility score. Lower insurgent/resource/loss/harm metrics and higher government control/legitimacy/institution capacity are jointly preferred.",
        },
        "interpretation_guard": "Policy-package differences arise inside the current synthetic mechanisms. They require independent robustness and historical transport before any operational interpretation.",
    }
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {
        "status": result["status"],
        "nondominated": nondominated,
        "domination_counts": {k: v["count"] for k, v in domination_counts.items()},
        "final_rooted_membership_improvements": {
            s: final_contrasts[s]["rooted_armed_membership_mass"]["mean"] for s in STRATEGIES
        },
        "final_recruitment_hazard_improvements": {
            s: final_contrasts[s]["recruitment_hazard_mass"]["mean"] for s in STRATEGIES
        },
        "gross_outflows": {
            s: final_means[s]["government_capital_outflow_intervention"] for s in STRATEGIES
        },
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
