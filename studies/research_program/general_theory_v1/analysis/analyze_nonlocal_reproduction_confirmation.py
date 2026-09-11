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
FEATURE_SETS = {
    "intercept": [],
    "adjacency_only": ["adjacent_origin"],
    "euclidean_only": ["distance_km"],
    "locality_graph": ["locality_graph_hops", "locality_graph_path_cost"],
    "social": [
        "parent_social_exposure_potential",
        "parent_social_min_hops",
        "cross_locality_social_influence",
    ],
    "geographic_combined": [
        "adjacent_origin",
        "distance_km",
        "locality_graph_hops",
        "locality_graph_path_cost",
    ],
    "hybrid": [
        "adjacent_origin",
        "distance_km",
        "locality_graph_hops",
        "locality_graph_path_cost",
        "parent_social_exposure_potential",
        "parent_social_min_hops",
        "cross_locality_social_influence",
    ],
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _prepare_fold(train: pd.DataFrame, test: pd.DataFrame, features: list[str]):
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


def grouped_cv_predictions(df: pd.DataFrame, y: np.ndarray, features: list[str]) -> np.ndarray:
    seeds = sorted(df.seed.unique())
    pred = np.zeros(len(df), dtype=float)
    for seed in seeds:
        test_mask = df.seed.to_numpy() == seed
        train_mask = ~test_mask
        y_train = y[train_mask]
        prevalence = float(np.mean(y_train)) if len(y_train) else 0.5
        prevalence = float(np.clip(prevalence, 1e-9, 1.0 - 1e-9))
        if not features or len(np.unique(y_train)) < 2:
            pred[test_mask] = prevalence
            continue
        train = df.loc[train_mask]
        test = df.loc[test_mask]
        x_train, x_test = _prepare_fold(train, test, features)
        model = LogisticRegression(
            penalty="l2",
            C=1e6,
            solver="lbfgs",
            max_iter=2000,
            random_state=0,
        )
        model.fit(x_train, y_train)
        pred[test_mask] = model.predict_proba(x_test)[:, 1]
    return np.clip(pred, 1e-9, 1.0 - 1e-9)


def evaluate_models(df: pd.DataFrame, y: np.ndarray) -> dict:
    result = {}
    for name, features in FEATURE_SETS.items():
        pred = grouped_cv_predictions(df, y, features)
        auc = float(roc_auc_score(y, pred)) if len(np.unique(y)) == 2 else None
        result[name] = {
            "features": features,
            "logloss": float(log_loss(y, pred, labels=[0, 1])),
            "auc": auc,
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    raw = pd.read_csv(args.csv)
    required = {
        "seed",
        "origin",
        "destination",
        "parent_type",
        "child",
        "first_time",
        "trigger_event",
        "adjacent_origin",
        "distance_km",
        "locality_graph_hops",
        "locality_graph_path_cost",
        "parent_social_exposure_potential",
        "parent_social_min_hops",
        "cross_locality_social_influence",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"missing required columns: {missing}")

    df = raw[raw.parent_type.isin(ROOTED)].copy().reset_index(drop=True)
    numeric_features = sorted(
        set(sum(FEATURE_SETS.values(), [])) - {"adjacent_origin"}
    )
    feature_integrity = {
        feature: {
            "finite_fraction": float(np.isfinite(df[feature].to_numpy(float)).mean()),
            "std": float(np.nanstd(df[feature].to_numpy(float))),
        }
        for feature in numeric_features
    }
    if any(v["finite_fraction"] < 1.0 for v in feature_integrity.values()):
        raise SystemExit("non-finite preregistered predictor present")

    horizons = {}
    for horizon in HORIZONS:
        y = (
            (df.child.to_numpy(int) == 1)
            & np.isfinite(df.first_time.to_numpy(float))
            & (df.first_time.to_numpy(float) <= horizon + 1e-12)
        ).astype(int)
        positive = df.loc[y == 1].copy()
        nonadj = positive[positive.adjacent_origin == 0]
        recruitment_share = None
        if len(nonadj):
            recruitment_share = float(
                nonadj.trigger_event.astype(str).str.lower().eq("recruitment").mean()
            )
        horizons[str(int(horizon))] = {
            "rows": int(len(df)),
            "positive_children": int(y.sum()),
            "prevalence": float(y.mean()),
            "positive_nonadjacent_fraction": (
                float((positive.adjacent_origin == 0).mean()) if len(positive) else None
            ),
            "recruitment_trigger_share_nonadjacent": recruitment_share,
            "models": evaluate_models(df, y),
        }

    y180 = (
        (df.child.to_numpy(int) == 1)
        & np.isfinite(df.first_time.to_numpy(float))
        & (df.first_time.to_numpy(float) <= 180.0 + 1e-12)
    ).astype(int)
    seed_robustness = []
    for seed in sorted(df.seed.unique()):
        mask = df.seed.to_numpy() == seed
        positive = df.loc[mask & (y180 == 1)]
        frac = float((positive.adjacent_origin == 0).mean()) if len(positive) else None
        seed_robustness.append(
            {
                "seed": int(seed),
                "positive_children": int(len(positive)),
                "nonadjacent_fraction": frac,
                "passes": bool(frac is not None and frac > 0.50),
            }
        )

    h180 = horizons["180"]
    nonlocal_gate = bool(
        h180["positive_nonadjacent_fraction"] is not None
        and h180["positive_nonadjacent_fraction"] > 0.50
    )
    recruitment_gate = bool(
        h180["recruitment_trigger_share_nonadjacent"] is not None
        and h180["recruitment_trigger_share_nonadjacent"] >= 0.80
    )
    direction_gate = True
    material_gate = False
    gain_details = {}
    for horizon in [90, 180]:
        models = horizons[str(horizon)]["models"]
        adjacency = models["adjacency_only"]
        social = models["social"]
        hybrid = models["hybrid"]
        direction_gate &= social["logloss"] <= adjacency["logloss"] + 0.005
        candidates = {}
        for name, model in [("social", social), ("hybrid", hybrid)]:
            ll_gain = adjacency["logloss"] - model["logloss"]
            auc_gain = (
                model["auc"] - adjacency["auc"]
                if model["auc"] is not None and adjacency["auc"] is not None
                else None
            )
            candidates[name] = {"logloss_gain": float(ll_gain), "auc_gain": auc_gain}
            if ll_gain >= 0.01 or (auc_gain is not None and auc_gain >= 0.05):
                material_gate = True
        gain_details[str(horizon)] = candidates
    robustness_count = sum(item["passes"] for item in seed_robustness)
    robustness_gate = robustness_count >= 6

    all_gates = all(
        [nonlocal_gate, recruitment_gate, direction_gate, material_gate, robustness_gate]
    )
    if all_gates:
        interpretation = "NETWORK_MEDIATED_NONLOCAL_REPRODUCTION_SUPPORTED"
    elif nonlocal_gate and recruitment_gate:
        interpretation = "NONLOCAL_RECRUITMENT_CONFIRMED_KERNEL_UNRESOLVED"
    else:
        interpretation = "NONLOCAL_REPRODUCTION_NOT_CONFIRMED"

    out = {
        "schema_version": "pineland.nonlocal_reproduction_confirmation_results.v1",
        "status": interpretation,
        "historical_outcomes_used": False,
        "input": str(Path(args.csv)),
        "input_sha256": sha256(args.csv),
        "scope": "Fresh-seed confirmation under nonlocal_reproduction_confirmation_contract_v1.json and its preregistered measurement specification.",
        "integrity": {
            "rows_raw": int(len(raw)),
            "rows_rooted": int(len(df)),
            "seeds": [int(x) for x in sorted(df.seed.unique())],
            "rooted_parent_types": ROOTED,
            "feature_integrity": feature_integrity,
        },
        "horizons": horizons,
        "seed_robustness_180d": {
            "passing_seeds": int(robustness_count),
            "required": 6,
            "details": seed_robustness,
        },
        "material_gain_details": gain_details,
        "gates": {
            "nonadjacent_fraction_180d_gt_0_50": nonlocal_gate,
            "recruitment_trigger_share_nonadjacent_180d_ge_0_80": recruitment_gate,
            "social_kernel_direction_90_180": bool(direction_gate),
            "social_or_hybrid_material_gain": bool(material_gate),
            "seed_robustness_ge_6_of_8": bool(robustness_gate),
            "all_pass": bool(all_gates),
        },
        "interpretation_guard": "This is a synthetic isolated-parent mechanism result. It does not establish historical social-network structure or a universal spatial law.",
    }
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"status": interpretation, "gates": out["gates"]}, indent=2))


if __name__ == "__main__":
    main()
