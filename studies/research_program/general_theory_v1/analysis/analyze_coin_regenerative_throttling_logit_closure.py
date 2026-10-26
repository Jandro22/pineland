from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path


RATE = 0.125
COMPONENTS = {
    "grievance": ("mean_grievance", 1.5),
    "social_exposure": ("mean_social_access", 1.0),
    "compatibility": ("mean_compatibility", 1.0),
    "social_capital": ("canonical_insurgent_social_capital", 1.0),
    "fear": ("mean_fear", -1.0),
    "political_access": ("mean_political_access", -0.5),
    "rootedness_congruence": ("mean_local_congruence", 0.75),
}


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--reference-weekly-csv", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    seeds = sorted({int(row["seed"]) for row in rows})
    rates = sorted({float(row["recruitment_multiplier"]) for row in rows})
    if len(seeds) != 12 or rates != [RATE]:
        raise SystemExit(f"unexpected support seeds={len(seeds)} rates={rates}")

    table: dict[tuple[int, int], list[dict[str, str]]] = {}
    for row in rows:
        key = (int(row["seed"]), int(row["underground_disruption"]))
        table.setdefault(key, []).append(row)
    for cell_rows in table.values():
        cell_rows.sort(key=lambda row: float(row["time"]))

    with open(args.reference_weekly_csv, newline="", encoding="utf-8-sig") as handle:
        reference_rows = list(csv.DictReader(handle))
    reference = {
        (int(row["seed"]), int(row["underground_disruption"]), float(row["time"])): row
        for row in reference_rows
        if abs(float(row["recruitment_multiplier"]) - RATE) <= 1.0e-12
    }
    shared_columns = [
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "foothold_strength_sum",
        "canonical_insurgent_capital",
        "cumulative_recruitment_mass_since_anchor",
        "cumulative_underground_disruption_since_anchor",
        "canonical_insurgent_active",
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
    state_failures = []
    max_hazard_difference = 0.0
    for (seed, disruption), cell_rows in table.items():
        for row in cell_rows:
            key = (seed, disruption, float(row["time"]))
            ref = reference.get(key)
            if ref is None:
                state_failures.append({"key": key, "reason": "missing_reference"})
                continue
            differing = [
                column
                for column in shared_columns
                if row[column] != ref[column]
            ]
            hazard_difference = abs(float(row["hazard_mass"]) - float(ref["hazard_mass"]))
            max_hazard_difference = max(max_hazard_difference, hazard_difference)
            if hazard_difference > 1.0e-12:
                differing.append("hazard_mass")
            if differing:
                state_failures.append({"key": key, "columns": differing})

    identity_failures = []
    for row in rows:
        implied = (
            1.5 * float(row["mean_grievance"])
            + float(row["mean_social_access"])
            + float(row["mean_compatibility"])
            + float(row["canonical_insurgent_social_capital"])
            - float(row["mean_fear"])
            - 2.6
            - 0.5 * float(row["mean_political_access"])
            + 0.75 * float(row["mean_local_congruence"])
        )
        difference = abs(float(row["mean_logit"]) - implied)
        if difference > 1.0e-12:
            identity_failures.append(
                {
                    "seed": int(row["seed"]),
                    "disruption": int(row["underground_disruption"]),
                    "time": float(row["time"]),
                    "difference": difference,
                }
            )

    if state_failures or identity_failures:
        payload = {
            "status": "INTEGRITY_FAIL",
            "state_failures": state_failures,
            "identity_failures": identity_failures,
            "maximum_hazard_difference": max_hazard_difference,
        }
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
        print(json.dumps(payload, indent=2))
        raise SystemExit(2)

    seed_results = []
    pooled_component_effects = {name: [] for name in COMPONENTS}
    pooled_logit_effects = []
    pooled_base_intensity_effects = []
    for seed in seeds:
        baseline = table[(seed, 0)]
        treatment = table[(seed, 1)]
        times = [float(row["time"]) for row in baseline]
        if times != [float(row["time"]) for row in treatment]:
            raise SystemExit(f"time mismatch seed={seed}")
        component_effects = {name: [] for name in COMPONENTS}
        logit_effects = []
        base_intensity_effects = []
        compatibility_effects = []
        rootedness_effects = []
        for index, (brow, trow) in enumerate(zip(baseline, treatment)):
            component_sum = 0.0
            for name, (column, coefficient) in COMPONENTS.items():
                effect = coefficient * (float(trow[column]) - float(brow[column]))
                component_effects[name].append(effect)
                component_sum += effect
                if index > 0:
                    pooled_component_effects[name].append(effect)
            logit_effect = float(trow["mean_logit"]) - float(brow["mean_logit"])
            base_effect = float(trow["mean_base_intensity"]) - float(
                brow["mean_base_intensity"]
            )
            if abs(component_sum - logit_effect) > 1.0e-12:
                raise SystemExit(
                    f"paired logit identity mismatch seed={seed} time={times[index]}"
                )
            logit_effects.append(logit_effect)
            base_intensity_effects.append(base_effect)
            compatibility_effects.append(component_effects["compatibility"][-1])
            rootedness_effects.append(component_effects["rootedness_congruence"][-1])
            if index > 0:
                pooled_logit_effects.append(logit_effect)
                pooled_base_intensity_effects.append(base_effect)

        seed_results.append(
            {
                "seed": seed,
                "times": times,
                "component_effects": component_effects,
                "logit_effects": logit_effects,
                "base_intensity_effects": base_intensity_effects,
                "post_anchor_mean_component_effects": {
                    name: mean(values[1:]) for name, values in component_effects.items()
                },
                "post_anchor_mean_logit_effect": mean(logit_effects[1:]),
                "post_anchor_mean_base_intensity_effect": mean(
                    base_intensity_effects[1:]
                ),
            }
        )

    pooled_component_summary = {
        name: summarize(values) for name, values in pooled_component_effects.items()
    }
    absolute_mean_order = sorted(
        (
            (name, abs(summary["mean"]))
            for name, summary in pooled_component_summary.items()
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    endpoint_component_summary = {
        name: summarize(
            [result["component_effects"][name][-1] for result in seed_results]
        )
        for name in COMPONENTS
    }
    correlations = {
        "rootedness_contribution_vs_logit_effect_pooled": correlation(
            pooled_component_effects["rootedness_congruence"], pooled_logit_effects
        ),
        "compatibility_contribution_vs_logit_effect_pooled": correlation(
            pooled_component_effects["compatibility"], pooled_logit_effects
        ),
        "mean_logit_effect_vs_base_intensity_effect_pooled": correlation(
            pooled_logit_effects, pooled_base_intensity_effects
        ),
    }
    decision = {
        "largest_absolute_post_anchor_mean_component": absolute_mean_order[0][0],
        "rootedness_absolute_mean": abs(
            pooled_component_summary["rootedness_congruence"]["mean"]
        ),
        "compatibility_absolute_mean": abs(
            pooled_component_summary["compatibility"]["mean"]
        ),
        "rootedness_larger_than_compatibility": (
            abs(pooled_component_summary["rootedness_congruence"]["mean"])
            > abs(pooled_component_summary["compatibility"]["mean"])
        ),
    }

    payload = {
        "schema_version": "pineland.coin_regenerative_throttling_logit_closure_results.v1",
        "status": "post-outcome_logit_closure",
        "historical_outcomes_used": False,
        "integrity": {
            "passed": True,
            "state_failures": 0,
            "identity_failures": 0,
            "maximum_hazard_absolute_difference": max_hazard_difference,
        },
        "pooled_post_anchor_component_effects": pooled_component_summary,
        "endpoint_day240_component_effects": endpoint_component_summary,
        "absolute_mean_component_order": absolute_mean_order,
        "correlations": correlations,
        "decision": decision,
        "seed_results": seed_results,
        "interpretation_guard": (
            "Known-seed logit closure only. It selects the mechanism to test "
            "prospectively; it is not fresh confirmation."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "integrity": payload["integrity"],
                "pooled_post_anchor_component_effects": pooled_component_summary,
                "endpoint_day240_component_effects": endpoint_component_summary,
                "absolute_mean_component_order": absolute_mean_order,
                "correlations": correlations,
                "decision": decision,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
