from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from analyze_reproduction_first_hazard_exploratory import (
    FEATURE_SETS,
    HORIZONS,
    ROOTED,
    grouped_cv,
    sha256,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("outcomes_csv")
    ap.add_argument("hazard_csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    outcomes = pd.read_csv(args.outcomes_csv)
    outcomes = outcomes[outcomes.parent_type.isin(ROOTED)].copy()
    hazard = pd.read_csv(args.hazard_csv)
    keys = ["seed", "origin", "destination", "parent_type"]
    merged = outcomes.merge(hazard, on=keys, how="inner", validate="one_to_one")
    if len(merged) != len(outcomes):
        raise SystemExit(f"hazard join incomplete: outcomes={len(outcomes)} merged={len(merged)}")

    merged["log1p_first_hazard_mass"] = np.log1p(
        merged.first_nonzero_hazard_mass.to_numpy(float).clip(min=0.0)
    )
    times = merged.first_nonzero_hazard_time.to_numpy(float)
    finite_times = times[np.isfinite(times)]
    fill = float(finite_times.max() + 7.0) if len(finite_times) else 67.0
    merged["first_nonzero_hazard_time_finite"] = np.where(np.isfinite(times), times, fill)

    horizons: dict[str, dict] = {}
    for horizon in HORIZONS:
        y = (
            (merged.child.to_numpy(int) == 1)
            & np.isfinite(merged.first_time.to_numpy(float))
            & (merged.first_time.to_numpy(float) <= horizon + 1.0e-12)
        ).astype(int)
        models = {name: grouped_cv(merged, y, features) for name, features in FEATURE_SETS.items()}
        static = models["static_hybrid"]
        enhanced = models["static_hybrid_plus_hazard"]
        adjacency = models["adjacency_only"]
        first_hazard = models["first_hazard"]
        horizons[str(int(horizon))] = {
            "positive_children": int(y.sum()),
            "prevalence": float(y.mean()),
            "models": models,
            "hybrid_plus_hazard_vs_static": {
                "auc_gain": enhanced["auc"] - static["auc"],
                "logloss_gain": static["logloss"] - enhanced["logloss"],
            },
            "first_hazard_vs_adjacency": {
                "auc_gain": first_hazard["auc"] - adjacency["auc"],
                "logloss_gain": adjacency["logloss"] - first_hazard["logloss"],
            },
            "raw_hazard_auc": float(roc_auc_score(y, merged.first_nonzero_hazard_mass.to_numpy(float))),
        }

    primary = {}
    for h in [90, 180]:
        gains = horizons[str(h)]["hybrid_plus_hazard_vs_static"]
        primary[str(h)] = {
            "logloss_gain_ge_0_005": gains["logloss_gain"] >= 0.005,
            "auc_gain_ge_0_02": gains["auc_gain"] >= 0.02,
        }
    secondary30 = horizons["30"]["first_hazard_vs_adjacency"]
    secondary = {
        "first_hazard_auc_gain_ge_0_05": secondary30["auc_gain"] >= 0.05,
        "first_hazard_logloss_gain_ge_0_005": secondary30["logloss_gain"] >= 0.005,
    }
    passed = all(all(v.values()) for v in primary.values())

    case_times = hazard[["seed", "origin", "parent_type", "first_nonzero_hazard_time"]].drop_duplicates()
    finite_case_times = case_times[np.isfinite(case_times.first_nonzero_hazard_time)]
    result = {
        "schema_version": "pineland.reproduction_hazard_kernel_confirmation_results.v1",
        "status": (
            "DYNAMIC_RECRUITMENT_HAZARD_KERNEL_SUPPORTED_ON_SYNTHETIC_SUPPORT"
            if passed
            else "DYNAMIC_RECRUITMENT_HAZARD_PRIMARY_GATES_NOT_ALL_MET"
        ),
        "historical_outcomes_used": False,
        "outcomes_input": str(Path(args.outcomes_csv)),
        "outcomes_sha256": sha256(args.outcomes_csv),
        "hazard_input": str(Path(args.hazard_csv)),
        "hazard_sha256": sha256(args.hazard_csv),
        "rows": int(len(merged)),
        "cases": int(len(case_times)),
        "incubation": {
            "finite_fraction": float(np.isfinite(case_times.first_nonzero_hazard_time).mean()),
            "median_days_when_finite": (
                float(finite_case_times.first_nonzero_hazard_time.median())
                if len(finite_case_times)
                else None
            ),
        },
        "horizons": horizons,
        "primary_gates": primary,
        "secondary_30d_gates": secondary,
        "interpretation_guard": (
            "Fresh synthetic confirmation of predictive state relevance only. Recruitment hazard is endogenous and may summarize multiple mechanisms; "
            "this does not establish a universal real-world propagation law."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "primary_gates": primary, "secondary_30d": secondary}, indent=2))


if __name__ == "__main__":
    main()
