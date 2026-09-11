from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score


ROOTED = ["M", "MF", "MG", "MFG"]
HORIZONS = [30.0, 90.0, 180.0]
STATIC_HYBRID = [
    "adjacent_origin",
    "distance_km",
    "locality_graph_hops",
    "locality_graph_path_cost",
    "parent_social_exposure_potential",
    "parent_social_min_hops",
    "cross_locality_social_influence",
]
FEATURE_SETS = {
    "adjacency_only": ["adjacent_origin"],
    "first_hazard": ["log1p_first_hazard_mass"],
    "first_hazard_share": ["first_nonzero_hazard_share"],
    "hazard_plus_incubation": ["log1p_first_hazard_mass", "first_nonzero_hazard_time_finite"],
    "static_hybrid": STATIC_HYBRID,
    "static_hybrid_plus_hazard": STATIC_HYBRID + ["log1p_first_hazard_mass"],
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_fold(train: pd.DataFrame, test: pd.DataFrame, features: list[str]):
    x_train = train[features].to_numpy(float, copy=True)
    x_test = test[features].to_numpy(float, copy=True)
    for j, feature in enumerate(features):
        if feature == "adjacent_origin":
            continue
        mu = float(np.mean(x_train[:, j]))
        sd = float(np.std(x_train[:, j], ddof=0))
        if not np.isfinite(sd) or sd < 1e-12:
            sd = 1.0
        x_train[:, j] = (x_train[:, j] - mu) / sd
        x_test[:, j] = (x_test[:, j] - mu) / sd
    return x_train, x_test


def grouped_cv(df: pd.DataFrame, y: np.ndarray, features: list[str]) -> dict:
    seeds = sorted(df.seed.unique())
    pred = np.zeros(len(df), dtype=float)
    for seed in seeds:
        test_mask = df.seed.to_numpy() == seed
        train_mask = ~test_mask
        y_train = y[train_mask]
        prevalence = float(np.clip(y_train.mean(), 1e-9, 1.0 - 1e-9))
        if len(np.unique(y_train)) < 2:
            pred[test_mask] = prevalence
            continue
        x_train, x_test = prepare_fold(df.loc[train_mask], df.loc[test_mask], features)
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000)
        model.fit(x_train, y_train)
        pred[test_mask] = model.predict_proba(x_test)[:, 1]
    pred = np.clip(pred, 1e-9, 1 - 1e-9)
    return {
        "features": features,
        "logloss": float(log_loss(y, pred, labels=[0, 1])),
        "auc": float(roc_auc_score(y, pred)) if len(np.unique(y)) == 2 else None,
    }


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

    horizons = {}
    for horizon in HORIZONS:
        y = (
            (merged.child.to_numpy(int) == 1)
            & np.isfinite(merged.first_time.to_numpy(float))
            & (merged.first_time.to_numpy(float) <= horizon + 1e-12)
        ).astype(int)
        models = {name: grouped_cv(merged, y, features) for name, features in FEATURE_SETS.items()}
        raw_hazard = merged.first_nonzero_hazard_mass.to_numpy(float)
        raw_share = merged.first_nonzero_hazard_share.to_numpy(float)
        horizons[str(int(horizon))] = {
            "positive_children": int(y.sum()),
            "prevalence": float(y.mean()),
            "raw_first_hazard_auc": float(roc_auc_score(y, raw_hazard)) if len(np.unique(y)) == 2 else None,
            "raw_first_hazard_share_auc": float(roc_auc_score(y, raw_share)) if len(np.unique(y)) == 2 else None,
            "models": models,
            "gains_vs_adjacency": {
                name: {
                    "auc_gain": (
                        models[name]["auc"] - models["adjacency_only"]["auc"]
                        if models[name]["auc"] is not None and models["adjacency_only"]["auc"] is not None
                        else None
                    ),
                    "logloss_gain": models["adjacency_only"]["logloss"] - models[name]["logloss"],
                }
                for name in models
                if name != "adjacency_only"
            },
        }

    case_times = hazard[["seed", "origin", "parent_type", "first_nonzero_hazard_time"]].drop_duplicates()
    finite_case_times = case_times[np.isfinite(case_times.first_nonzero_hazard_time)]
    result = {
        "schema_version": "pineland.reproduction_first_hazard_exploratory.v1",
        "status": "EXPLORATORY_ALREADY_OBSERVED_OUTCOME_SUPPORT",
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
                float(finite_case_times.first_nonzero_hazard_time.median()) if len(finite_case_times) else None
            ),
            "p10_days": (
                float(finite_case_times.first_nonzero_hazard_time.quantile(0.10)) if len(finite_case_times) else None
            ),
            "p90_days": (
                float(finite_case_times.first_nonzero_hazard_time.quantile(0.90)) if len(finite_case_times) else None
            ),
        },
        "horizons": horizons,
        "interpretation_guard": (
            "This analysis develops a mechanistic predictor on outcomes already examined in the prior "
            "nonlocal-reproduction confirmation. It cannot confirm the hazard kernel. Any promising "
            "candidate must be frozen and tested on a new seed block."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"incubation": result["incubation"], "horizons": horizons}, indent=2))


if __name__ == "__main__":
    main()
