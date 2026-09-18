from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


CELLS = ("000", "100", "010", "001", "110", "101", "011", "111")
TIMEPOINTS = ("intervention_end", "final")

LOWER_IS_BETTER = {
    "rooted_armed_membership_mass",
    "recruitment_hazard_mass",
    "ecosystem_rooted_membership",
    "ecosystem_recruitment_hazard",
    "fielded_force_personnel",
    "ecosystem_operational_force",
    "foothold_strength_sum",
    "population_weighted_insurgent_control",
    "cumulative_insurgent_actions_since_anchor",
    "government_military_losses_since_anchor",
    "population_loss_since_anchor",
    "displaced_population_fraction",
    "government_capital_outflow_intervention",
}
HIGHER_IS_STATE_PATHWAY = {
    "population_weighted_government_control",
    "mean_local_institution_capacity",
    "mean_intelligence_penetration",
    "cumulative_security_recruits",
    "cumulative_security_deployments",
    "cumulative_admin_rebuild",
    "cumulative_underground_disruption",
}
OUTCOMES = tuple(sorted(LOWER_IS_BETTER | HIGHER_IS_STATE_PATHWAY))


def average(values: list[float]) -> float:
    return statistics.fmean(values)


def paired_summary(values: list[float]) -> dict[str, object]:
    mean = average(values)
    if len(values) > 1:
        se = statistics.stdev(values) / math.sqrt(len(values))
        interval = [mean - 1.96 * se, mean + 1.96 * se]
    else:
        se = None
        interval = None
    return {
        "n": len(values),
        "mean": mean,
        "se": se,
        "normal_95": interval,
    }


def factor(cell: str, position: int) -> int:
    return int(cell[position])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("empty factorial CSV")

    cells = sorted({row["cell"] for row in rows})
    if cells != sorted(CELLS):
        raise SystemExit(f"expected all eight cells, got {cells}")
    seeds = sorted({int(row["seed"]) for row in rows})
    table = {
        (int(row["seed"]), row["cell"], row["timepoint"]): row
        for row in rows
    }
    missing = [
        (seed, cell, timepoint)
        for seed in seeds
        for cell in CELLS
        for timepoint in ("anchor",) + TIMEPOINTS
        if (seed, cell, timepoint) not in table
    ]
    if missing:
        raise SystemExit(f"incomplete factorial; first missing entries: {missing[:8]}")

    cell_means: dict[str, object] = {}
    factorial_contrasts: dict[str, object] = {}
    cell_vs_baseline: dict[str, object] = {}
    u_effect_by_sa: dict[str, object] = {}

    for timepoint in TIMEPOINTS:
        cell_means[timepoint] = {}
        factorial_contrasts[timepoint] = {}
        cell_vs_baseline[timepoint] = {}
        u_effect_by_sa[timepoint] = {}
        for outcome in OUTCOMES:
            def observed(seed: int, cell: str) -> float:
                return float(table[(seed, cell, timepoint)][outcome])

            cell_means[timepoint][outcome] = {
                cell: average([observed(seed, cell) for seed in seeds])
                for cell in CELLS
            }

            per_seed = {
                key: []
                for key in ("S", "A", "U", "SA", "SU", "AU", "SAU")
            }
            for seed in seeds:
                y = {cell: observed(seed, cell) for cell in CELLS}
                per_seed["S"].append(
                    average([y[cell] for cell in CELLS if factor(cell, 0) == 1])
                    - average([y[cell] for cell in CELLS if factor(cell, 0) == 0])
                )
                per_seed["A"].append(
                    average([y[cell] for cell in CELLS if factor(cell, 1) == 1])
                    - average([y[cell] for cell in CELLS if factor(cell, 1) == 0])
                )
                per_seed["U"].append(
                    average([y[cell] for cell in CELLS if factor(cell, 2) == 1])
                    - average([y[cell] for cell in CELLS if factor(cell, 2) == 0])
                )
                per_seed["SA"].append(
                    average(
                        [
                            y[f"11{u}"]
                            - y[f"10{u}"]
                            - y[f"01{u}"]
                            + y[f"00{u}"]
                            for u in (0, 1)
                        ]
                    )
                )
                per_seed["SU"].append(
                    average(
                        [
                            y[f"1{a}1"]
                            - y[f"1{a}0"]
                            - y[f"0{a}1"]
                            + y[f"0{a}0"]
                            for a in (0, 1)
                        ]
                    )
                )
                per_seed["AU"].append(
                    average(
                        [
                            y[f"{s}11"]
                            - y[f"{s}10"]
                            - y[f"{s}01"]
                            + y[f"{s}00"]
                            for s in (0, 1)
                        ]
                    )
                )
                per_seed["SAU"].append(
                    y["111"]
                    - y["110"]
                    - y["101"]
                    - y["011"]
                    + y["100"]
                    + y["010"]
                    + y["001"]
                    - y["000"]
                )

            factorial_contrasts[timepoint][outcome] = {
                name: paired_summary(values)
                for name, values in per_seed.items()
            }
            cell_vs_baseline[timepoint][outcome] = {
                cell: paired_summary(
                    [
                        observed(seed, cell) - observed(seed, "000")
                        for seed in seeds
                    ]
                )
                for cell in CELLS
                if cell != "000"
            }
            u_effect_by_sa[timepoint][outcome] = {}
            for security in (0, 1):
                for administration in (0, 1):
                    low = f"{security}{administration}0"
                    high = f"{security}{administration}1"
                    u_effect_by_sa[timepoint][outcome][
                        f"S{security}A{administration}"
                    ] = paired_summary(
                        [
                            observed(seed, high) - observed(seed, low)
                            for seed in seeds
                        ]
                    )

    relapse: dict[str, object] = {}
    for outcome in OUTCOMES:
        relapse[outcome] = {}
        for cell in CELLS:
            if cell == "000":
                continue
            differences = []
            for seed in seeds:
                cell_final = float(table[(seed, cell, "final")][outcome])
                cell_end = float(table[(seed, cell, "intervention_end")][outcome])
                baseline_final = float(table[(seed, "000", "final")][outcome])
                baseline_end = float(
                    table[(seed, "000", "intervention_end")][outcome]
                )
                differences.append(
                    (cell_final - cell_end) - (baseline_final - baseline_end)
                )
            relapse[outcome][cell] = paired_summary(differences)

    payload = {
        "schema_version": "pineland.coin_pressure_admin_factorial_results.v1",
        "status": "synthetic_development_only",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "cells": list(CELLS),
        "outcome_direction": {
            **{
                key: "lower_is_preferred_for_suppression_or_harm"
                for key in LOWER_IS_BETTER
            },
            **{
                key: "higher_is_more_state_capacity_or_pathway"
                for key in HIGHER_IS_STATE_PATHWAY
            },
        },
        "cell_means": cell_means,
        "factorial_contrasts": factorial_contrasts,
        "cell_vs_baseline": cell_vs_baseline,
        "u_marginal_effect_by_security_admin_stratum": u_effect_by_sa,
        "post_intervention_relapse_difference_in_differences": relapse,
        "interpretation_guard": (
            "Factorial effects diagnose mechanisms in the implemented synthetic "
            "model. Negative SxU/AxU interactions on lower-is-suppression insurgent "
            "outcomes are consistent with more-than-additive suppression but do not "
            "establish real-world policy complementarity."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")

    primary = (
        "rooted_armed_membership_mass",
        "recruitment_hazard_mass",
        "mean_intelligence_penetration",
        "cumulative_underground_disruption",
    )
    compact = {
        timepoint: {
            outcome: {
                effect: round(
                    factorial_contrasts[timepoint][outcome][effect]["mean"], 6
                )
                for effect in ("S", "A", "U", "SU", "AU", "SAU")
            }
            for outcome in primary
        }
        for timepoint in TIMEPOINTS
    }
    print(
        json.dumps(
            {"out": args.out, "seed_count": len(seeds), "primary": compact},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
