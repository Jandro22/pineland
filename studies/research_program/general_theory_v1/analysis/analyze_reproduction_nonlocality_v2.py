#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold


ROOTED = {"M", "MF", "MG", "MFG"}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cv_logistic(d: pd.DataFrame, feature_names: list[str], y: np.ndarray) -> dict:
    X = pd.get_dummies(d[feature_names], columns=[c for c in feature_names if d[c].dtype == object], drop_first=False)
    X = X.astype(float).to_numpy()
    groups = d.seed.to_numpy()
    pred = np.zeros(len(d), float)
    splitter = GroupKFold(n_splits=min(4, d.seed.nunique()))
    for tr, te in splitter.split(X, y, groups):
        if len(np.unique(y[tr])) < 2:
            pred[te] = float(np.mean(y[tr]))
            continue
        model = LogisticRegression(max_iter=2000, C=1.0)
        model.fit(X[tr], y[tr])
        pred[te] = model.predict_proba(X[te])[:, 1]
    pred = np.clip(pred, 1e-6, 1 - 1e-6)
    return {
        "logloss": float(log_loss(y, pred, labels=[0, 1])),
        "auc": float(roc_auc_score(y, pred)) if len(np.unique(y)) > 1 else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    raw = pd.read_csv(ns.csv)
    d = raw[raw.parent_type.isin(ROOTED)].copy()
    d["distance_100km"] = d.distance_km / 100.0
    d["adjacent"] = d.adjacent_origin.astype(float)
    d["origin_cat"] = d.origin.astype(str)
    d["destination_cat"] = d.destination.astype(str)
    d["parent_cat"] = d.parent_type.astype(str)

    horizons = {}
    for h in [30, 90, 180]:
        y = ((d.child == 1) & (d.first_time <= h)).astype(int).to_numpy()
        prevalence = float(np.mean(y))
        base_pred = np.full(len(y), prevalence)
        models = {
            "intercept": {
                "logloss": float(log_loss(y, np.clip(base_pred, 1e-6, 1 - 1e-6), labels=[0, 1])),
                "auc": 0.5,
            },
            "adjacency_only": cv_logistic(d, ["adjacent"], y),
            "distance_only": cv_logistic(d, ["distance_100km"], y),
            "distance_plus_adjacency": cv_logistic(d, ["distance_100km", "adjacent"], y),
            "spatial_context_full": cv_logistic(
                d,
                ["distance_100km", "adjacent", "origin_cat", "destination_cat", "parent_cat"],
                y,
            ),
        }
        temp = d[["distance_km", "adjacent_origin"]].copy()
        temp["y"] = y
        temp["distance_bin"] = pd.cut(
            temp.distance_km,
            bins=[-1, 25, 50, 75, 100, 150, 200, np.inf],
            labels=["0-25", "25-50", "50-75", "75-100", "100-150", "150-200", "200+"],
        )
        distance_bins = []
        for name, g in temp.groupby("distance_bin", observed=False):
            distance_bins.append({
                "bin_km": str(name),
                "rows": int(len(g)),
                "child_probability": float(g.y.mean()) if len(g) else None,
            })
        positives = temp[temp.y == 1]
        horizons[str(h)] = {
            "rows": int(len(temp)),
            "positive_children": int(y.sum()),
            "prevalence": prevalence,
            "positive_adjacent_fraction": float(positives.adjacent_origin.mean()) if len(positives) else None,
            "positive_nonadjacent_fraction": float(1.0 - positives.adjacent_origin.mean()) if len(positives) else None,
            "positive_median_distance_km": float(positives.distance_km.median()) if len(positives) else None,
            "distance_bins": distance_bins,
            "cv_models": models,
        }

    h180 = horizons["180"]
    adj = h180["cv_models"]["adjacency_only"]["logloss"]
    full = h180["cv_models"]["spatial_context_full"]["logloss"]
    adjacency_regret = float(adj - full)
    nonlocal_fraction = float(h180["positive_nonadjacent_fraction"])
    out = {
        "schema_version": "pineland.reproduction_nonlocality_exploratory.v2",
        "status": "exploratory_synthetic_spatial_structure_analysis",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "scope": "Rooted parent types only (M, MF, MG, MFG); this is exploratory analysis of an already-observed assay and requires an independently preregistered confirmation before promotion.",
        "horizons": horizons,
        "summary_180d": {
            "nonadjacent_child_fraction": nonlocal_fraction,
            "median_child_distance_km": h180["positive_median_distance_km"],
            "adjacency_only_logloss_regret_vs_full_spatial_context": adjacency_regret,
            "nearest_neighbor_wave_description_supported": bool(nonlocal_fraction < 0.50 and adjacency_regret <= 0.02),
        },
        "next_test": "Preregister a kernel-shape confirmation assay comparing graph-hop, metric-distance, and social/mobility connectivity kernels on fresh synthetic seeds and topology families."
    }
    Path(ns.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out["summary_180d"], indent=2))


if __name__ == "__main__":
    main()
