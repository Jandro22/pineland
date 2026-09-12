#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def as_collapsed(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    radius = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - radius), min(1.0, center + radius)


def median_or_none(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return None if values.empty else float(values.median())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    d = pd.read_csv(ns.csv)
    required = {
        "seed",
        "recruitment_multiplier",
        "collapsed",
        "collapse_time",
        "collapse_cause",
        "final_capital",
        "final_rooted",
        "final_operational_force",
        "final_cumulative_recruitment",
        "runway_ratio",
        "recruitment_capital_burn",
        "capital_inflow",
    }
    missing = sorted(required - set(d.columns))
    if missing:
        raise SystemExit(f"missing columns: {missing}")

    d = d.copy()
    d["collapsed_bool"] = as_collapsed(d.collapsed)
    rates = sorted(float(x) for x in d.recruitment_multiplier.unique())
    seed_counts = d.groupby("recruitment_multiplier").seed.nunique()
    if len(set(int(x) for x in seed_counts)) != 1:
        raise SystemExit(f"unbalanced seed counts across rates: {seed_counts.to_dict()}")

    cells: list[dict] = []
    for rate in rates:
        g = d[np.isclose(d.recruitment_multiplier.astype(float), rate)].copy()
        collapsed = g[g.collapsed_bool]
        survived = g[~g.collapsed_bool]
        n = len(g)
        k = len(collapsed)
        lo, hi = wilson(k, n)
        cells.append(
            {
                "recruitment_multiplier": rate,
                "n": int(n),
                "collapse_count": int(k),
                "collapse_fraction": float(k / n),
                "collapse_fraction_wilson95": [lo, hi],
                "median_collapse_time_days": median_or_none(collapsed.collapse_time),
                "collapse_causes": {
                    str(k0): int(v0) for k0, v0 in collapsed.collapse_cause.value_counts().items()
                },
                "median_final_rooted_unconditional": median_or_none(g.final_rooted),
                "median_final_rooted_survivors": median_or_none(survived.final_rooted),
                "median_final_operational_force_unconditional": median_or_none(g.final_operational_force),
                "median_final_operational_force_survivors": median_or_none(survived.final_operational_force),
                "median_final_capital": median_or_none(g.final_capital),
                "median_final_cumulative_recruitment": median_or_none(g.final_cumulative_recruitment),
                "median_runway_ratio": median_or_none(g.runway_ratio),
                "median_recruitment_capital_burn": median_or_none(g.recruitment_capital_burn),
                "median_capital_inflow": median_or_none(g.capital_inflow),
            }
        )

    cdf = pd.DataFrame(cells).sort_values("recruitment_multiplier").reset_index(drop=True)
    zero_rates = cdf[cdf.collapse_count == 0].recruitment_multiplier.tolist()
    positive_rates = cdf[cdf.collapse_count > 0].recruitment_multiplier.tolist()
    highest_zero = max(zero_rates) if zero_rates else None
    lowest_positive = min(positive_rates) if positive_rates else None
    transition_band = None
    if highest_zero is not None and lowest_positive is not None and highest_zero < lowest_positive:
        transition_band = [float(highest_zero), float(lowest_positive)]

    # Shared-seed adjacent contrasts preserve the paired design.
    paired_adjacent: list[dict] = []
    for low_rate, high_rate in zip(rates[:-1], rates[1:]):
        low = d[np.isclose(d.recruitment_multiplier.astype(float), low_rate)].set_index("seed")
        high = d[np.isclose(d.recruitment_multiplier.astype(float), high_rate)].set_index("seed")
        common = sorted(set(low.index) & set(high.index))
        low = low.loc[common]
        high = high.loc[common]
        low_c = low.collapsed_bool.astype(bool)
        high_c = high.collapsed_bool.astype(bool)
        both_survive = (~low_c) & (~high_c)
        newly_collapsed = (~low_c) & high_c
        recovered = low_c & (~high_c)
        paired_adjacent.append(
            {
                "lower_rate": low_rate,
                "higher_rate": high_rate,
                "paired_seed_count": int(len(common)),
                "new_collapses_at_higher_rate": int(newly_collapsed.sum()),
                "recoveries_at_higher_rate": int(recovered.sum()),
                "both_survive_count": int(both_survive.sum()),
                "median_rooted_change_higher_minus_lower_among_both_survive": (
                    None
                    if not both_survive.any()
                    else float((high.loc[both_survive, "final_rooted"] - low.loc[both_survive, "final_rooted"]).median())
                ),
                "median_operational_force_change_higher_minus_lower_among_both_survive": (
                    None
                    if not both_survive.any()
                    else float(
                        (
                            high.loc[both_survive, "final_operational_force"]
                            - low.loc[both_survive, "final_operational_force"]
                        ).median()
                    )
                ),
                "median_capital_change_higher_minus_lower_among_both_survive": (
                    None
                    if not both_survive.any()
                    else float((high.loc[both_survive, "final_capital"] - low.loc[both_survive, "final_capital"]).median())
                ),
            }
        )

    # Three-objective Pareto frontier: minimize observed collapse risk, maximize
    # median rooted membership, maximize median fielded force.  No arbitrary
    # weighting is introduced.
    pareto_rates: list[float] = []
    for i, row in cdf.iterrows():
        dominated = False
        for j, other in cdf.iterrows():
            if i == j:
                continue
            weak = (
                float(other.collapse_fraction) <= float(row.collapse_fraction)
                and float(other.median_final_rooted_unconditional) >= float(row.median_final_rooted_unconditional)
                and float(other.median_final_operational_force_unconditional)
                >= float(row.median_final_operational_force_unconditional)
            )
            strict = (
                float(other.collapse_fraction) < float(row.collapse_fraction)
                or float(other.median_final_rooted_unconditional) > float(row.median_final_rooted_unconditional)
                or float(other.median_final_operational_force_unconditional)
                > float(row.median_final_operational_force_unconditional)
            )
            if weak and strict:
                dominated = True
                break
        if not dominated:
            pareto_rates.append(float(row.recruitment_multiplier))

    collapsed = d[d.collapsed_bool]
    capital_collapses = int((collapsed.collapse_cause.astype(str) == "capital").sum())
    result = {
        "schema_version": "pineland.insurgent_mobilization_risk_frontier_results.v1",
        "status": "RISK_FRONTIER_ESTIMATED" if positive_rates else "NO_COLLAPSE_OBSERVED_ON_TESTED_FRONTIER",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(d.seed.nunique()),
        "rate_count": int(len(rates)),
        "cell_summary": cells,
        "observed_transition_band": transition_band,
        "highest_tested_rate_with_zero_observed_collapse": highest_zero,
        "lowest_tested_rate_with_positive_observed_collapse": lowest_positive,
        "pareto_efficient_rates": pareto_rates,
        "paired_adjacent_rate_contrasts": paired_adjacent,
        "aggregate_collapse_count": int(len(collapsed)),
        "aggregate_collapse_causes": {
            str(k): int(v) for k, v in collapsed.collapse_cause.value_counts().items()
        },
        "capital_trigger_share_among_collapses": (
            None if len(collapsed) == 0 else float(capital_collapses / len(collapsed))
        ),
        "interpretation_guard": (
            "The observed transition band brackets a sampled risk transition, not a universal threshold. "
            "Zero observed failures retain nonzero uncertainty. Synthetic rate and capital scales are not historically calibrated."
        ),
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "transition_band": transition_band,
                "highest_zero_collapse_rate": highest_zero,
                "lowest_positive_collapse_rate": lowest_positive,
                "pareto_efficient_rates": pareto_rates,
                "aggregate_collapse_causes": result["aggregate_collapse_causes"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
