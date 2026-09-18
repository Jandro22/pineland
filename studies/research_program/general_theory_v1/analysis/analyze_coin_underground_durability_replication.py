from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def paired_summary(values: list[float]) -> dict[str, object]:
    m = mean(values)
    if len(values) > 1:
        se = statistics.stdev(values) / math.sqrt(len(values))
        normal_95 = [m - 1.96 * se, m + 1.96 * se]
    else:
        se = None
        normal_95 = None
    return {"n": len(values), "mean": m, "se": se, "normal_95": normal_95}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seeds = sorted({int(row["seed"]) for row in rows})
    if len(seeds) != 16:
        raise SystemExit(f"expected 16 seeds, got {len(seeds)}")

    table = {
        (int(row["seed"]), row["cell"], row["timepoint"]): row
        for row in rows
    }

    def value(seed: int, cell: str, timepoint: str, key: str) -> float:
        return float(table[(seed, cell, timepoint)][key])

    seed_results = []
    for seed in seeds:
        b240_root = value(seed, "000", "intervention_end", "rooted_armed_membership_mass")
        u240_root = value(seed, "001", "intervention_end", "rooted_armed_membership_mass")
        b360_root = value(seed, "000", "final", "rooted_armed_membership_mass")
        u360_root = value(seed, "001", "final", "rooted_armed_membership_mass")
        b240_force = value(seed, "000", "intervention_end", "fielded_force_personnel")
        u240_force = value(seed, "001", "intervention_end", "fielded_force_personnel")
        b360_force = value(seed, "000", "final", "fielded_force_personnel")
        u360_force = value(seed, "001", "final", "fielded_force_personnel")
        direct = value(
            seed,
            "001",
            "intervention_end",
            "cumulative_underground_disruption",
        )

        root_effect_240 = u240_root - b240_root
        root_effect_360 = u360_root - b360_root
        force_effect_240 = u240_force - b240_force
        force_effect_360 = u360_force - b360_force
        root_prop_240 = root_effect_240 / max(b240_root, 1e-12)
        root_prop_360 = root_effect_360 / max(b360_root, 1e-12)
        force_prop_240 = force_effect_240 / max(b240_force, 1e-12)
        force_prop_360 = force_effect_360 / max(b360_force, 1e-12)
        amplification = (-root_effect_360 / direct) if direct > 0.0 else None
        persistence = (
            (-root_effect_360 / -root_effect_240)
            if root_effect_240 < 0.0
            else None
        )

        seed_results.append(
            {
                "seed": seed,
                "root_effect_day240": root_effect_240,
                "root_effect_day360": root_effect_360,
                "root_proportional_effect_day240": root_prop_240,
                "root_proportional_effect_day360": root_prop_360,
                "fielded_force_effect_day240": force_effect_240,
                "fielded_force_effect_day360": force_effect_360,
                "fielded_force_proportional_effect_day240": force_prop_240,
                "fielded_force_proportional_effect_day360": force_prop_360,
                "direct_disruption_mass_day240": direct,
                "amplification_ratio_day360": amplification,
                "persistence_ratio": persistence,
                "deepened_after_removal": (
                    root_prop_240 < 0.0
                    and root_prop_360 < 0.0
                    and abs(root_prop_360) > abs(root_prop_240)
                ),
                "rebounded_above_baseline_day360": root_effect_360 > 0.0,
            }
        )

    root_240 = [row["root_effect_day240"] for row in seed_results]
    root_360 = [row["root_effect_day360"] for row in seed_results]
    root_prop_240 = [
        row["root_proportional_effect_day240"] for row in seed_results
    ]
    root_prop_360 = [
        row["root_proportional_effect_day360"] for row in seed_results
    ]
    force_prop_240 = [
        row["fielded_force_proportional_effect_day240"] for row in seed_results
    ]
    force_prop_360 = [
        row["fielded_force_proportional_effect_day360"] for row in seed_results
    ]
    amplification = [
        row["amplification_ratio_day360"]
        for row in seed_results
        if row["amplification_ratio_day360"] is not None
    ]

    predictions = {
        "mean_rooted_effect_day240_negative": mean(root_240) < 0.0,
        "rooted_suppression_at_least_12_of_16_day240": (
            sum(effect < 0.0 for effect in root_240) >= 12
        ),
        "mean_rooted_effect_day360_negative": mean(root_360) < 0.0,
        "rooted_suppression_at_least_10_of_16_day360": (
            sum(effect < 0.0 for effect in root_360) >= 10
        ),
        "day240_force_proportional_effect_smaller_than_rooted": (
            abs(mean(force_prop_240)) < abs(mean(root_prop_240))
        ),
        "fielded_force_effect_more_negative_by_day360": (
            mean(force_prop_360) < mean(force_prop_240)
        ),
        "median_day360_amplification_exceeds_one": (
            statistics.median(amplification) > 1.0
        ),
        "deepened_suppression_at_least_8_of_16": (
            sum(row["deepened_after_removal"] for row in seed_results) >= 8
        ),
    }

    outcomes = {}
    for key in (
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "recruitment_hazard_mass",
        "foothold_strength_sum",
        "population_weighted_insurgent_control",
        "ecosystem_rooted_membership",
        "ecosystem_operational_force",
        "ecosystem_recruitment_hazard",
        "mean_intelligence_penetration",
        "mean_local_institution_capacity",
    ):
        outcomes[key] = {}
        for timepoint in ("intervention_end", "final"):
            effects = [
                value(seed, "001", timepoint, key)
                - value(seed, "000", timepoint, key)
                for seed in seeds
            ]
            outcomes[key][timepoint] = paired_summary(effects)

    payload = {
        "schema_version": "pineland.coin_underground_durability_replication_results.v1",
        "status": "fresh_seed_replication",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "primary_prediction_results": predictions,
        "all_primary_predictions_passed": all(predictions.values()),
        "descriptive": {
            "rooted_effect_day240": paired_summary(root_240),
            "rooted_effect_day360": paired_summary(root_360),
            "rooted_proportional_effect_day240": paired_summary(root_prop_240),
            "rooted_proportional_effect_day360": paired_summary(root_prop_360),
            "fielded_force_proportional_effect_day240": paired_summary(
                force_prop_240
            ),
            "fielded_force_proportional_effect_day360": paired_summary(
                force_prop_360
            ),
            "median_amplification_ratio_day360": statistics.median(amplification),
            "rooted_suppression_seeds_day240": sum(
                effect < 0.0 for effect in root_240
            ),
            "rooted_suppression_seeds_day360": sum(
                effect < 0.0 for effect in root_360
            ),
            "rebound_above_baseline_seeds_day360": sum(
                row["rebounded_above_baseline_day360"]
                for row in seed_results
            ),
            "deepened_after_removal_seeds": sum(
                row["deepened_after_removal"] for row in seed_results
            ),
        },
        "secondary_outcomes": outcomes,
        "seed_results": seed_results,
        "interpretation_guard": (
            "Fresh-seed synthetic replication of a Pineland mechanism only. "
            "Passing predictions supports the implemented reproductive-pool/"
            "lagged-force mechanism, not a real-world operational prescription."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "all_primary_predictions_passed": all(predictions.values()),
                "primary_prediction_results": predictions,
                "descriptive": payload["descriptive"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
