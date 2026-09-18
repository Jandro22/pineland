from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


RATES = (0.03125, 0.0625, 0.125)
TIMEPOINTS = ("anchor", "intervention_end", "final")


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
    if len(seeds) != 12:
        raise SystemExit(f"expected 12 seeds, got {len(seeds)}")
    rates = sorted({float(row["recruitment_multiplier"]) for row in rows})
    if rates != list(RATES):
        raise SystemExit(f"unexpected rates {rates}")

    expected_keys = {
        (seed, rate, disruption, timepoint)
        for seed in seeds
        for rate in RATES
        for disruption in (0, 1)
        for timepoint in TIMEPOINTS
    }
    table = {
        (
            int(row["seed"]),
            float(row["recruitment_multiplier"]),
            int(row["underground_disruption"]),
            row["timepoint"],
        ): row
        for row in rows
    }
    missing = sorted(expected_keys - set(table))
    duplicates = len(rows) != len(table)

    anchor_failures = []
    state_columns = [
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "recruitment_hazard_mass",
        "eligible_recruitment_mass",
        "foothold_strength_sum",
        "canonical_insurgent_capital",
        "cumulative_recruitment_mass_since_anchor",
        "cumulative_underground_disruption_since_anchor",
        "canonical_insurgent_active",
    ]
    for seed in seeds:
        reference = table[(seed, RATES[0], 0, "anchor")]
        for rate in RATES:
            for disruption in (0, 1):
                current = table[(seed, rate, disruption, "anchor")]
                different = [
                    column
                    for column in state_columns
                    if current[column] != reference[column]
                ]
                if different:
                    anchor_failures.append(
                        {
                            "seed": seed,
                            "rate": rate,
                            "disruption": disruption,
                            "columns": different,
                        }
                    )

    if missing or duplicates or anchor_failures:
        payload = {
            "status": "INTEGRITY_FAIL",
            "missing": missing,
            "duplicates": duplicates,
            "anchor_failures": anchor_failures,
        }
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
        print(json.dumps(payload, indent=2))
        raise SystemExit(2)

    def value(
        seed: int, rate: float, disruption: int, timepoint: str, key: str
    ) -> float:
        return float(table[(seed, rate, disruption, timepoint)][key])

    outcomes = (
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "recruitment_hazard_mass",
        "eligible_recruitment_mass",
        "foothold_strength_sum",
        "canonical_insurgent_capital",
        "cumulative_recruitment_mass_since_anchor",
        "cumulative_underground_disruption_since_anchor",
    )

    cell_summary: dict[str, object] = {}
    paired_u_effects: dict[str, object] = {}
    for rate in RATES:
        rate_key = f"{rate:.5f}"
        cell_summary[rate_key] = {}
        paired_u_effects[rate_key] = {}
        for disruption in (0, 1):
            cell_key = f"u{disruption}"
            cell_summary[rate_key][cell_key] = {}
            for timepoint in ("intervention_end", "final"):
                cell_summary[rate_key][cell_key][timepoint] = {
                    key: summarize(
                        [
                            value(seed, rate, disruption, timepoint, key)
                            for seed in seeds
                        ]
                    )
                    for key in outcomes
                }
            final_active = [
                value(seed, rate, disruption, "final", "canonical_insurgent_active")
                for seed in seeds
            ]
            final_capital = [
                value(seed, rate, disruption, "final", "canonical_insurgent_capital")
                for seed in seeds
            ]
            cell_summary[rate_key][cell_key]["collapse_fraction"] = (
                sum(
                    active <= 0.0 or capital <= 1.0e-9
                    for active, capital in zip(final_active, final_capital)
                )
                / len(seeds)
            )

        for timepoint in ("intervention_end", "final"):
            paired_u_effects[rate_key][timepoint] = {}
            for key in outcomes:
                effects = [
                    value(seed, rate, 1, timepoint, key)
                    - value(seed, rate, 0, timepoint, key)
                    for seed in seeds
                ]
                paired_u_effects[rate_key][timepoint][key] = summarize(effects)

    no_u_recruitment_means = [
        cell_summary[f"{rate:.5f}"]["u0"]["final"][
            "cumulative_recruitment_mass_since_anchor"
        ]["mean"]
        for rate in RATES
    ]
    day240_root_effects = [
        paired_u_effects[f"{rate:.5f}"]["intervention_end"][
            "rooted_armed_membership_mass"
        ]["mean"]
        for rate in RATES
    ]

    capital_accounting_by_rate = {}
    accounting_pass = True
    for rate in RATES:
        excess_recruits = [
            value(seed, rate, 1, "final", "cumulative_recruitment_mass_since_anchor")
            - value(seed, rate, 0, "final", "cumulative_recruitment_mass_since_anchor")
            for seed in seeds
        ]
        capital_effect = [
            value(seed, rate, 1, "final", "canonical_insurgent_capital")
            - value(seed, rate, 0, "final", "canonical_insurgent_capital")
            for seed in seeds
        ]
        corr = pearson(excess_recruits, capital_effect)
        mean_excess = mean(excess_recruits)
        mean_capital = mean(capital_effect)
        if mean_excess > 0.0 and not (mean_capital < 0.0):
            accounting_pass = False
        capital_accounting_by_rate[f"{rate:.5f}"] = {
            "mean_excess_recruited_mass": mean_excess,
            "mean_capital_effect": mean_capital,
            "pearson_excess_recruitment_vs_capital_effect": corr,
            "mean_first_order_predicted_capital_effect": -1.92 * mean_excess,
        }

    predictions = {
        "u0_recruitment_monotonic_with_rate": (
            no_u_recruitment_means[0]
            < no_u_recruitment_means[1]
            < no_u_recruitment_means[2]
        ),
        "u_root_effect_day240_negative_all_rates": all(
            effect < 0.0 for effect in day240_root_effects
        ),
        "u_root_deficit_larger_at_0_03125_than_0_0625": (
            day240_root_effects[0] < day240_root_effects[1] < 0.0
        ),
        "positive_excess_recruitment_implies_negative_mean_capital_effect": accounting_pass,
    }

    payload = {
        "schema_version": "pineland.coin_pressure_regeneration_metabolic_phase_results.v1",
        "status": "fresh_phase_map",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "integrity_passed": True,
        "prediction_results": predictions,
        "all_directional_predictions_passed": all(predictions.values()),
        "cell_summary": cell_summary,
        "paired_u_effects": paired_u_effects,
        "capital_accounting_by_rate": capital_accounting_by_rate,
        "interpretation_guard": (
            "Fresh synthetic phase map only. Do not rank real strategies or "
            "treat tested recruitment multipliers as empirical estimates."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "prediction_results": predictions,
                "capital_accounting_by_rate": capital_accounting_by_rate,
                "paired_u_root_effect_day240": {
                    f"{rate:.5f}": paired_u_effects[f"{rate:.5f}"][
                        "intervention_end"
                    ]["rooted_armed_membership_mass"]
                    for rate in RATES
                },
                "final_collapse_fraction": {
                    f"{rate:.5f}": {
                        "u0": cell_summary[f"{rate:.5f}"]["u0"]["collapse_fraction"],
                        "u1": cell_summary[f"{rate:.5f}"]["u1"]["collapse_fraction"],
                    }
                    for rate in RATES
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
