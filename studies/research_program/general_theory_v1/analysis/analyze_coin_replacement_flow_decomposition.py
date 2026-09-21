from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx = mean(xs)
    my = mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx <= 0.0 or sy <= 0.0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sx * sy)


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seeds = sorted({int(row["seed"]) for row in rows})
    cells = sorted({row["cell"] for row in rows})
    if len(seeds) != 16 or cells != ["000", "001"]:
        raise SystemExit(f"expected 16 seeds and cells 000/001, got {len(seeds)} {cells}")

    table = {
        (int(row["seed"]), row["cell"], row["timepoint"]): row
        for row in rows
    }

    def value(seed: int, cell: str, timepoint: str, key: str) -> float:
        return float(table[(seed, cell, timepoint)][key])

    seed_results: list[dict[str, object]] = []
    for seed in seeds:
        root_final = (
            value(seed, "001", "final", "rooted_armed_membership_mass")
            - value(seed, "000", "final", "rooted_armed_membership_mass")
        )
        disruption = value(
            seed, "001", "intervention_end", "cumulative_underground_disruption"
        )
        recruitment_base_240 = value(
            seed, "000", "intervention_end", "cumulative_recruitment_mass_since_anchor"
        )
        recruitment_u_240 = value(
            seed, "001", "intervention_end", "cumulative_recruitment_mass_since_anchor"
        )
        recruitment_base_360 = value(
            seed, "000", "final", "cumulative_recruitment_mass_since_anchor"
        )
        recruitment_u_360 = value(
            seed, "001", "final", "cumulative_recruitment_mass_since_anchor"
        )
        excess_240 = recruitment_u_240 - recruitment_base_240
        excess_post = (
            (recruitment_u_360 - recruitment_u_240)
            - (recruitment_base_360 - recruitment_base_240)
        )
        replacement_ratio = excess_240 / disruption if disruption > 0.0 else None
        result: dict[str, object] = {
            "seed": seed,
            "rebounded_day360": root_final > 0.0,
            "rooted_effect_day360": root_final,
            "direct_disruption_mass_day240": disruption,
            "baseline_recruited_mass_day240": recruitment_base_240,
            "treatment_recruited_mass_day240": recruitment_u_240,
            "excess_recruited_mass_day240": excess_240,
            "excess_recruited_mass_post_day240_to_day360": excess_post,
            "excess_recruitment_to_disruption_ratio_day240": replacement_ratio,
        }
        for key in (
            "eligible_recruitment_mass",
            "recruitment_hazard_mass",
            "foothold_strength_sum",
            "mean_social_exposure_to_canonical",
            "mean_grievance",
            "mean_fear",
            "mean_political_access",
            "canonical_insurgent_social_capital",
        ):
            for timepoint in ("intervention_end", "final"):
                result[f"{key}_effect_{timepoint}"] = (
                    value(seed, "001", timepoint, key)
                    - value(seed, "000", timepoint, key)
                )
        seed_results.append(result)

    def numeric(name: str) -> list[float]:
        return [
            float(row[name])
            for row in seed_results
            if row[name] is not None
        ]

    primary = {
        "excess_recruited_mass_day240": summarize(
            numeric("excess_recruited_mass_day240")
        ),
        "excess_recruited_mass_post_day240_to_day360": summarize(
            numeric("excess_recruited_mass_post_day240_to_day360")
        ),
        "excess_recruitment_to_disruption_ratio_day240": summarize(
            numeric("excess_recruitment_to_disruption_ratio_day240")
        ),
        "eligible_recruitment_mass_effect_day240": summarize(
            numeric("eligible_recruitment_mass_effect_intervention_end")
        ),
        "eligible_recruitment_mass_effect_day360": summarize(
            numeric("eligible_recruitment_mass_effect_final")
        ),
    }

    groups = {}
    for label, predicate in (
        ("rebound", lambda row: bool(row["rebounded_day360"])),
        ("suppressed", lambda row: not bool(row["rebounded_day360"])),
    ):
        group = [row for row in seed_results if predicate(row)]
        groups[label] = {
            "n": len(group),
            "mean_excess_recruited_mass_day240": mean(
                [float(row["excess_recruited_mass_day240"]) for row in group]
            ),
            "mean_excess_recruited_mass_post_day240_to_day360": mean(
                [
                    float(row["excess_recruited_mass_post_day240_to_day360"])
                    for row in group
                ]
            ),
            "mean_replacement_ratio_day240": mean(
                [
                    float(row["excess_recruitment_to_disruption_ratio_day240"])
                    for row in group
                    if row["excess_recruitment_to_disruption_ratio_day240"] is not None
                ]
            ),
            "mean_hazard_effect_day360": mean(
                [float(row["recruitment_hazard_mass_effect_final"]) for row in group]
            ),
            "mean_foothold_effect_day360": mean(
                [float(row["foothold_strength_sum_effect_final"]) for row in group]
            ),
        }

    root_effects = numeric("rooted_effect_day360")
    correlations = {
        key: correlation(numeric(key), root_effects)
        for key in (
            "excess_recruited_mass_day240",
            "excess_recruited_mass_post_day240_to_day360",
            "excess_recruitment_to_disruption_ratio_day240",
            "eligible_recruitment_mass_effect_intervention_end",
            "recruitment_hazard_mass_effect_intervention_end",
            "recruitment_hazard_mass_effect_final",
            "foothold_strength_sum_effect_final",
            "mean_social_exposure_to_canonical_effect_final",
            "mean_grievance_effect_final",
            "mean_fear_effect_final",
            "mean_political_access_effect_final",
            "canonical_insurgent_social_capital_effect_final",
        )
    }

    payload = {
        "schema_version": "pineland.coin_replacement_flow_decomposition_results.v1",
        "status": "post-outcome_exploratory_mechanistic_decomposition",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "primary": primary,
        "known_outcome_groups": groups,
        "exploratory_correlations_with_day360_rooted_effect": correlations,
        "seed_results": seed_results,
        "interpretation_guard": (
            "Endpoint outcomes on this seed block were known before the new flow "
            "measurements were generated. Relationships discovered here are "
            "mechanistic hypotheses requiring fresh-seed confirmation."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "primary": primary,
                "known_outcome_groups": groups,
                "exploratory_correlations_with_day360_rooted_effect": correlations,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
