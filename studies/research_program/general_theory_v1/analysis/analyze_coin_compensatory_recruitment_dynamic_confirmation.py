from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def summarize(values: list[float]) -> dict[str, object]:
    m = mean(values)
    if len(values) > 1:
        se = statistics.stdev(values) / math.sqrt(len(values))
        ci = [m - 1.96 * se, m + 1.96 * se]
    else:
        se = None
        ci = None
    return {
        "n": len(values),
        "mean": m,
        "median": statistics.median(values),
        "se": se,
        "normal_95": ci,
        "minimum": min(values),
        "maximum": max(values),
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = mean(xs)
    my = mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0.0 or sy <= 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seeds = sorted({int(row["seed"]) for row in rows})
    cells = sorted({row["cell"] for row in rows})
    timepoints = sorted({row["timepoint"] for row in rows})
    if len(seeds) != 24:
        raise SystemExit(f"expected 24 seeds, got {len(seeds)}")
    if cells != ["000", "001"]:
        raise SystemExit(f"expected cells 000/001, got {cells}")
    if timepoints != ["anchor", "final", "intervention_end"]:
        raise SystemExit(f"unexpected timepoints {timepoints}")

    table = {
        (int(row["seed"]), row["cell"], row["timepoint"]): row
        for row in rows
    }

    def value(seed: int, cell: str, timepoint: str, key: str) -> float:
        return float(table[(seed, cell, timepoint)][key])

    seed_results = []
    for seed in seeds:
        root_240 = (
            value(seed, "001", "intervention_end", "rooted_armed_membership_mass")
            - value(seed, "000", "intervention_end", "rooted_armed_membership_mass")
        )
        root_360 = (
            value(seed, "001", "final", "rooted_armed_membership_mass")
            - value(seed, "000", "final", "rooted_armed_membership_mass")
        )
        hazard_240 = (
            value(seed, "001", "intervention_end", "recruitment_hazard_mass")
            - value(seed, "000", "intervention_end", "recruitment_hazard_mass")
        )
        hazard_360 = (
            value(seed, "001", "final", "recruitment_hazard_mass")
            - value(seed, "000", "final", "recruitment_hazard_mass")
        )
        eligible_240 = (
            value(seed, "001", "intervention_end", "eligible_recruitment_mass")
            - value(seed, "000", "intervention_end", "eligible_recruitment_mass")
        )
        eligible_360 = (
            value(seed, "001", "final", "eligible_recruitment_mass")
            - value(seed, "000", "final", "eligible_recruitment_mass")
        )
        foothold_360 = (
            value(seed, "001", "final", "foothold_strength_sum")
            - value(seed, "000", "final", "foothold_strength_sum")
        )
        fielded_360 = (
            value(seed, "001", "final", "fielded_force_personnel")
            - value(seed, "000", "final", "fielded_force_personnel")
        )
        b240_recruits = value(
            seed, "000", "intervention_end", "cumulative_recruitment_mass_since_anchor"
        )
        u240_recruits = value(
            seed, "001", "intervention_end", "cumulative_recruitment_mass_since_anchor"
        )
        b360_recruits = value(
            seed, "000", "final", "cumulative_recruitment_mass_since_anchor"
        )
        u360_recruits = value(
            seed, "001", "final", "cumulative_recruitment_mass_since_anchor"
        )
        excess_240 = u240_recruits - b240_recruits
        excess_post = (u360_recruits - u240_recruits) - (b360_recruits - b240_recruits)
        seed_results.append(
            {
                "seed": seed,
                "rooted_effect_day240": root_240,
                "rooted_effect_day360": root_360,
                "rebounded_day360": root_360 > 0.0,
                "hazard_effect_day240": hazard_240,
                "hazard_effect_day360": hazard_360,
                "eligible_effect_day240": eligible_240,
                "eligible_effect_day360": eligible_360,
                "foothold_effect_day360": foothold_360,
                "fielded_force_effect_day360": fielded_360,
                "excess_recruited_mass_day240": excess_240,
                "excess_recruited_mass_post_day240_to_day360": excess_post,
            }
        )

    def vals(key: str) -> list[float]:
        return [float(row[key]) for row in seed_results]

    post_flow = vals("excess_recruited_mass_post_day240_to_day360")
    root_360 = vals("rooted_effect_day360")
    flow_root_correlation = pearson(post_flow, root_360)

    positive_group = [
        row for row in seed_results
        if float(row["excess_recruited_mass_post_day240_to_day360"]) > 0.0
    ]
    nonpositive_group = [
        row for row in seed_results
        if float(row["excess_recruited_mass_post_day240_to_day360"]) <= 0.0
    ]

    def rebound_fraction(group: list[dict[str, object]]) -> float | None:
        if not group:
            return None
        return sum(bool(row["rebounded_day360"]) for row in group) / len(group)

    positive_rebound_fraction = rebound_fraction(positive_group)
    nonpositive_rebound_fraction = rebound_fraction(nonpositive_group)
    risk_difference = (
        positive_rebound_fraction - nonpositive_rebound_fraction
        if positive_rebound_fraction is not None
        and nonpositive_rebound_fraction is not None
        else None
    )

    predictions = {
        "mean_rooted_effect_day240_negative": mean(vals("rooted_effect_day240")) < 0.0,
        "mean_rooted_effect_day360_negative": mean(vals("rooted_effect_day360")) < 0.0,
        "mean_hazard_effect_day360_positive": mean(vals("hazard_effect_day360")) > 0.0,
        "mean_eligible_effect_day360_positive": mean(vals("eligible_effect_day360")) > 0.0,
        "post_flow_rooted_effect_correlation_above_0_50": (
            flow_root_correlation is not None and flow_root_correlation > 0.50
        ),
        "positive_post_flow_has_higher_rebound_fraction": (
            risk_difference is not None and risk_difference > 0.0
        ),
    }

    payload = {
        "schema_version": "pineland.coin_compensatory_recruitment_dynamic_confirmation_results.v1",
        "status": "fresh_seed_dynamic_confirmation",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "primary_prediction_results": predictions,
        "all_primary_predictions_passed": all(predictions.values()),
        "summaries": {
            "rooted_effect_day240": summarize(vals("rooted_effect_day240")),
            "rooted_effect_day360": summarize(vals("rooted_effect_day360")),
            "hazard_effect_day240": summarize(vals("hazard_effect_day240")),
            "hazard_effect_day360": summarize(vals("hazard_effect_day360")),
            "eligible_effect_day240": summarize(vals("eligible_effect_day240")),
            "eligible_effect_day360": summarize(vals("eligible_effect_day360")),
            "foothold_effect_day360": summarize(vals("foothold_effect_day360")),
            "fielded_force_effect_day360": summarize(vals("fielded_force_effect_day360")),
            "excess_recruited_mass_day240": summarize(vals("excess_recruited_mass_day240")),
            "excess_recruited_mass_post_day240_to_day360": summarize(post_flow),
        },
        "flow_rebound_test": {
            "pearson_post_flow_vs_day360_rooted_effect": flow_root_correlation,
            "positive_post_flow_n": len(positive_group),
            "positive_post_flow_rebound_fraction": positive_rebound_fraction,
            "nonpositive_post_flow_n": len(nonpositive_group),
            "nonpositive_post_flow_rebound_fraction": nonpositive_rebound_fraction,
            "rebound_risk_difference": risk_difference,
        },
        "seed_results": seed_results,
        "interpretation_guard": "Fresh synthetic confirmation only; no historical or operational inference."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "all_primary_predictions_passed": payload["all_primary_predictions_passed"],
                "primary_prediction_results": predictions,
                "summaries": payload["summaries"],
                "flow_rebound_test": payload["flow_rebound_test"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
