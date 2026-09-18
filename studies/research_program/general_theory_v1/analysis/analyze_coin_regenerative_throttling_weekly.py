from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


RATES = (0.03125, 0.0625, 0.125)


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


def trapz(times: list[float], values: list[float]) -> float:
    return sum(
        0.5 * (values[i] + values[i - 1]) * (times[i] - times[i - 1])
        for i in range(1, len(times))
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--reference-phase-csv", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seeds = sorted({int(row["seed"]) for row in rows})
    rates = sorted({float(row["recruitment_multiplier"]) for row in rows})
    if len(seeds) != 12 or rates != list(RATES):
        raise SystemExit(f"unexpected support seeds={len(seeds)} rates={rates}")

    by_cell: dict[tuple[int, float, int], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            int(row["seed"]),
            float(row["recruitment_multiplier"]),
            int(row["underground_disruption"]),
        )
        by_cell.setdefault(key, []).append(row)
    for cell_rows in by_cell.values():
        cell_rows.sort(key=lambda row: float(row["time"]))

    anchor_failures = []
    for seed in seeds:
        ref = by_cell[(seed, RATES[0], 0)][0]
        columns = [
            "rooted_armed_membership_mass",
            "fielded_force_personnel",
            "foothold_strength_sum",
            "canonical_insurgent_capital",
            "cumulative_recruitment_mass_since_anchor",
            "cumulative_underground_disruption_since_anchor",
            "canonical_insurgent_active",
            "hazard_mass",
            "eligible_represented_mass",
            "accessible_eligible_represented_mass",
            "mean_social_access",
            "mean_formation_access",
            "mean_member_access",
            "mean_foothold_access",
            "mean_selected_access",
            "mean_base_intensity",
            "mean_combined_intensity",
            "mean_grievance",
            "mean_fear",
            "mean_political_access",
            "mean_local_congruence",
            "canonical_insurgent_social_capital",
        ]
        for rate in RATES:
            for disruption in (0, 1):
                current = by_cell[(seed, rate, disruption)][0]
                differing = [
                    column for column in columns if current[column] != ref[column]
                ]
                # Hazard/intensity legitimately depend on the post-anchor
                # recruitment-rate setting even at the shared state.
                differing = [
                    column
                    for column in differing
                    if column not in {"hazard_mass"}
                ]
                if differing:
                    anchor_failures.append(
                        {
                            "seed": seed,
                            "rate": rate,
                            "disruption": disruption,
                            "columns": differing,
                        }
                    )

    with open(args.reference_phase_csv, newline="", encoding="utf-8-sig") as handle:
        reference_rows = list(csv.DictReader(handle))
    reference = {
        (
            int(row["seed"]),
            float(row["recruitment_multiplier"]),
            int(row["underground_disruption"]),
        ): row
        for row in reference_rows
        if row["timepoint"] == "intervention_end"
    }
    endpoint_mapping = {
        "rooted_armed_membership_mass": "rooted_armed_membership_mass",
        "fielded_force_personnel": "fielded_force_personnel",
        "foothold_strength_sum": "foothold_strength_sum",
        "canonical_insurgent_capital": "canonical_insurgent_capital",
        "cumulative_recruitment_mass_since_anchor": "cumulative_recruitment_mass_since_anchor",
        "cumulative_underground_disruption_since_anchor": "cumulative_underground_disruption_since_anchor",
        "canonical_insurgent_active": "canonical_insurgent_active",
        "hazard_mass": "recruitment_hazard_mass",
        "eligible_represented_mass": "eligible_recruitment_mass",
    }
    endpoint_failures = []
    for key, cell_rows in sorted(by_cell.items()):
        endpoint = cell_rows[-1]
        ref = reference.get(key)
        if ref is None:
            endpoint_failures.append({"key": key, "reason": "missing_reference"})
            continue
        differing = [
            [new_column, old_column, endpoint[new_column], ref[old_column]]
            for new_column, old_column in endpoint_mapping.items()
            if endpoint[new_column] != ref[old_column]
        ]
        if differing:
            endpoint_failures.append({"key": key, "differences": differing})

    if anchor_failures or endpoint_failures:
        payload = {
            "status": "INTEGRITY_FAIL",
            "anchor_failures": anchor_failures,
            "endpoint_failures": endpoint_failures,
        }
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
        print(json.dumps(payload, indent=2))
        raise SystemExit(2)

    metrics = (
        "hazard_mass",
        "eligible_represented_mass",
        "accessible_eligible_represented_mass",
        "mean_social_access",
        "mean_formation_access",
        "mean_member_access",
        "mean_foothold_access",
        "mean_selected_access",
        "mean_base_intensity",
        "mean_combined_intensity",
        "mean_grievance",
        "mean_fear",
        "mean_political_access",
        "mean_local_congruence",
        "dominant_social_fraction",
        "dominant_formation_fraction",
        "dominant_member_fraction",
        "dominant_foothold_fraction",
        "canonical_insurgent_social_capital",
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "foothold_strength_sum",
        "canonical_insurgent_capital",
        "cumulative_recruitment_mass_since_anchor",
    )

    decomposition: dict[str, object] = {}
    for rate in RATES:
        rate_key = f"{rate:.5f}"
        seed_results = []
        for seed in seeds:
            baseline = by_cell[(seed, rate, 0)]
            treatment = by_cell[(seed, rate, 1)]
            times = [float(row["time"]) for row in baseline]
            if times != [float(row["time"]) for row in treatment]:
                raise SystemExit(f"time mismatch seed={seed} rate={rate}")

            effects = {
                metric: [
                    float(trow[metric]) - float(brow[metric])
                    for brow, trow in zip(baseline, treatment)
                ]
                for metric in metrics
            }
            baseline_hazard = [float(row["hazard_mass"]) for row in baseline]
            treatment_hazard = [float(row["hazard_mass"]) for row in treatment]
            hazard_integral_effect = trapz(times, treatment_hazard) - trapz(
                times, baseline_hazard
            )
            realized_recruitment_effect = (
                float(treatment[-1]["cumulative_recruitment_mass_since_anchor"])
                - float(baseline[-1]["cumulative_recruitment_mass_since_anchor"])
            )
            treatment_eligibility_above_baseline = sum(
                value > 0.0 for value in effects["eligible_represented_mass"][1:]
            )
            treatment_intensity_below_baseline = sum(
                value < 0.0 for value in effects["mean_combined_intensity"][1:]
            )
            treatment_hazard_below_baseline = sum(
                value < 0.0 for value in effects["hazard_mass"][1:]
            )
            nonanchor_count = max(len(times) - 1, 1)
            seed_results.append(
                {
                    "seed": seed,
                    "times": times,
                    "effects": effects,
                    "hazard_integral_effect": hazard_integral_effect,
                    "realized_recruitment_effect": realized_recruitment_effect,
                    "fraction_post_anchor_eligibility_above_baseline": (
                        treatment_eligibility_above_baseline / nonanchor_count
                    ),
                    "fraction_post_anchor_intensity_below_baseline": (
                        treatment_intensity_below_baseline / nonanchor_count
                    ),
                    "fraction_post_anchor_hazard_below_baseline": (
                        treatment_hazard_below_baseline / nonanchor_count
                    ),
                }
            )

        endpoint = {
            metric: summarize([result["effects"][metric][-1] for result in seed_results])
            for metric in metrics
        }
        mean_time_series = []
        times = seed_results[0]["times"]
        for index, time in enumerate(times):
            mean_time_series.append(
                {
                    "time": time,
                    **{
                        f"{metric}_effect": mean(
                            [result["effects"][metric][index] for result in seed_results]
                        )
                        for metric in metrics
                    },
                }
            )
        decomposition[rate_key] = {
            "endpoint_effects_day240": endpoint,
            "hazard_integral_effect": summarize(
                [result["hazard_integral_effect"] for result in seed_results]
            ),
            "realized_recruitment_effect": summarize(
                [result["realized_recruitment_effect"] for result in seed_results]
            ),
            "fraction_post_anchor_eligibility_above_baseline": summarize(
                [
                    result["fraction_post_anchor_eligibility_above_baseline"]
                    for result in seed_results
                ]
            ),
            "fraction_post_anchor_intensity_below_baseline": summarize(
                [
                    result["fraction_post_anchor_intensity_below_baseline"]
                    for result in seed_results
                ]
            ),
            "fraction_post_anchor_hazard_below_baseline": summarize(
                [
                    result["fraction_post_anchor_hazard_below_baseline"]
                    for result in seed_results
                ]
            ),
            "mean_time_series": mean_time_series,
            "seed_results": seed_results,
        }

    payload = {
        "schema_version": "pineland.coin_regenerative_throttling_weekly_decomposition_results.v1",
        "status": "post-outcome_mechanistic_decomposition",
        "historical_outcomes_used": False,
        "integrity": {
            "passed": True,
            "anchor_failures": 0,
            "endpoint_failures": 0,
            "seed_count": len(seeds),
        },
        "decomposition": decomposition,
        "interpretation_guard": (
            "Known-seed mechanistic decomposition only. Any mechanism selected "
            "from these measurements requires fresh-seed confirmation."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    compact = {}
    for rate in RATES:
        key = f"{rate:.5f}"
        block = decomposition[key]
        compact[key] = {
            "hazard_integral_effect": block["hazard_integral_effect"],
            "realized_recruitment_effect": block["realized_recruitment_effect"],
            "fraction_eligibility_above": block[
                "fraction_post_anchor_eligibility_above_baseline"
            ],
            "fraction_intensity_below": block[
                "fraction_post_anchor_intensity_below_baseline"
            ],
            "fraction_hazard_below": block[
                "fraction_post_anchor_hazard_below_baseline"
            ],
            "day240_effects": {
                metric: block["endpoint_effects_day240"][metric]
                for metric in (
                    "eligible_represented_mass",
                    "mean_selected_access",
                    "mean_base_intensity",
                    "mean_combined_intensity",
                    "mean_social_access",
                    "mean_formation_access",
                    "mean_member_access",
                    "mean_foothold_access",
                    "mean_local_congruence",
                    "hazard_mass",
                    "cumulative_recruitment_mass_since_anchor",
                )
            },
        }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
