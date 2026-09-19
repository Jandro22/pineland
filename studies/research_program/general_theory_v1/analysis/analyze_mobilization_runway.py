#!/usr/bin/env python3
"""
Scientific Analysis and Evaluation of Mobilization Runway Phase Law
Pineland COIN-SIM Research Program
"""

import sys
import os
import json
import hashlib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
from sklearn.model_selection import GroupKFold

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def compute_calibration(y_true, y_prob):
    # Guard against 0 or 1 probabilities
    p = np.clip(y_prob, 1e-6, 1.0 - 1e-6)
    logit_p = np.log(p / (1.0 - p))
    # Logistic regression of y on logit(p): y ~ sigma(a + b * logit(p))
    lr = LogisticRegression(penalty=None, solver="lbfgs")
    try:
        lr.fit(logit_p.reshape(-1, 1), y_true)
        slope = float(lr.coef_[0][0])
        intercept = float(lr.intercept_[0])
    except Exception:
        slope = float("nan")
        intercept = float("nan")
    return slope, intercept

def bootstrap_seed_metrics(df, pred_col, n_boot=1000, rng_seed=42):
    rng = np.random.default_rng(rng_seed)
    seeds = df["seed"].unique()
    n_seeds = len(seeds)
    aucs = []
    briers = []

    for _ in range(n_boot):
        sample_seeds = rng.choice(seeds, size=n_seeds, replace=True)
        # Gather rows for these seeds
        boot_df = pd.concat([df[df["seed"] == s] for s in sample_seeds], ignore_index=True)
        y = boot_df["capital_collapse_day360"].values
        if len(np.unique(y)) < 2:
            continue
        p = boot_df[pred_col].values
        aucs.append(roc_auc_score(y, p))
        briers.append(brier_score_loss(y, p))

    if len(aucs) == 0:
        return {"auc_ci_lower": float("nan"), "auc_ci_upper": float("nan"), "brier_ci_lower": float("nan"), "brier_ci_upper": float("nan")}

    return {
        "auc_mean": float(np.mean(aucs)),
        "auc_ci_lower": float(np.percentile(aucs, 2.5)),
        "auc_ci_upper": float(np.percentile(aucs, 97.5)),
        "brier_mean": float(np.mean(briers)),
        "brier_ci_lower": float(np.percentile(briers, 2.5)),
        "brier_ci_upper": float(np.percentile(briers, 97.5)),
    }

def fit_and_evaluate_discovery(csv_path):
    print(f"Loading discovery data: {csv_path}")
    df_raw = pd.read_csv(csv_path)
    total_raw = len(df_raw)

    # Exclusions per contract: worlds that collapsed before window end (day 120)
    df = df_raw[df_raw["survived_to_120"] == True].copy()
    excluded_count = total_raw - len(df)
    print(f"Total trajectories: {total_raw}, survived to day 120: {len(df)}, excluded (collapsed < 120d): {excluded_count}")

    y = df["capital_collapse_day360"].values
    seeds = df["seed"].values
    base_rate = float(np.mean(y))
    base_rate_brier = float(np.mean((base_rate - y) ** 2))
    print(f"Base rate of capital exhaustion collapse: {base_rate:.4f}, Base-rate Brier score: {base_rate_brier:.4f}")

    # Prepare features:
    # 1. log_omega: log(Omega_K), capped at +10 for infinite / sustainable runway
    omega = df["omega_k"].values
    log_omega = np.where(np.isinf(omega) | (omega >= 20000.0), 10.0, np.log(np.maximum(omega, 1e-4)))
    df["log_omega"] = log_omega

    # 2. log_lambda: log(Lambda_K)
    lambda_k = df["lambda_k"].values
    log_lambda = np.log(np.maximum(lambda_k, 1e-6))
    df["log_lambda"] = log_lambda

    # 3. log_pi_m: crude parameter proxy
    pi_m = df["pi_m"].values
    log_pi_m = np.log(np.maximum(pi_m, 1e-6))
    df["log_pi_m"] = log_pi_m

    # Seed-grouped Cross-Validation (5 folds)
    gkf = GroupKFold(n_splits=5)
    candidates = ["log_omega", "log_lambda", "log_pi_m"]
    results = {}

    for cand in candidates:
        oof_probs = np.zeros(len(df))
        X = df[[cand]].values

        for train_idx, test_idx in gkf.split(X, y, groups=seeds):
            X_train, y_train = X[train_idx], y[train_idx]
            X_test = X[test_idx]
            model = LogisticRegression(penalty=None, solver="lbfgs")
            model.fit(X_train, y_train)
            probs = model.predict_proba(X_test)[:, 1]
            oof_probs[test_idx] = probs

        df[f"prob_{cand}"] = oof_probs
        auc = float(roc_auc_score(y, oof_probs))
        pr_auc = float(average_precision_score(y, oof_probs))
        brier = float(brier_score_loss(y, oof_probs))
        loss = float(log_loss(y, oof_probs))
        slope, intercept = compute_calibration(y, oof_probs)
        boot = bootstrap_seed_metrics(df, f"prob_{cand}")

        results[cand] = {
            "roc_auc": auc,
            "pr_auc": pr_auc,
            "brier_score": brier,
            "log_loss": loss,
            "calibration_slope": slope,
            "calibration_intercept": intercept,
            "brier_relative_to_base_rate": brier - base_rate_brier,
            "bootstrap_ci": boot,
        }
        print(f"\nCandidate {cand}:")
        print(f"  ROC AUC: {auc:.4f} (95% CI: [{boot['auc_ci_lower']:.4f}, {boot['auc_ci_upper']:.4f}])")
        print(f"  PR AUC:  {pr_auc:.4f}")
        print(f"  Brier:   {brier:.4f} (Base rate: {base_rate_brier:.4f})")
        print(f"  Calib slope: {slope:.4f}, intercept: {intercept:.4f}")

    # Fit final frozen model on entire discovery dataset for the primary candidate
    # Omega_K: model is logit(p) = intercept + beta * log(Omega_K)
    final_model_omega = LogisticRegression(penalty=None, solver="lbfgs")
    final_model_omega.fit(df[["log_omega"]].values, y)
    beta_log_omega = float(final_model_omega.coef_[0][0])
    intercept_omega = float(final_model_omega.intercept_[0])

    # Also fit final frozen model for Pi_M baseline
    final_model_pi = LogisticRegression(penalty=None, solver="lbfgs")
    final_model_pi.fit(df[["log_pi_m"]].values, y)
    beta_log_pi = float(final_model_pi.coef_[0][0])
    intercept_pi = float(final_model_pi.intercept_[0])

    print("\n--- Final Frozen Models ---")
    print(f"Omega_K Law: logit(P(collapse)) = {intercept_omega:.6f} + ({beta_log_omega:.6f}) * log(Omega_K)")
    print(f"Pi_M Baseline: logit(P(collapse)) = {intercept_pi:.6f} + ({beta_log_pi:.6f}) * log(Pi_M)")

    # Confusion breakdown by actual collapse cause
    confusion = df.groupby("collapse_cause").agg(
        n=("capital_collapse_day360", "count"),
        actual_capital_collapse=("capital_collapse_day360", "sum"),
        mean_pred_omega=(f"prob_log_omega", "mean"),
        mean_pred_pi=(f"prob_log_pi_m", "mean"),
    ).to_dict(orient="index")

    discovery_summary = {
        "dataset_path": csv_path,
        "dataset_sha256": sha256_file(csv_path),
        "total_trajectories": total_raw,
        "survived_to_120": len(df),
        "excluded_pre_120_collapse": excluded_count,
        "base_rate": base_rate,
        "base_rate_brier": base_rate_brier,
        "cv_results": results,
        "frozen_law_omega": {
            "formula": "P(collapse) = 1 / (1 + exp(-(intercept + beta * log_omega)))",
            "log_omega_formula": "min(max(log(Omega_K), -9.21), 10.0)",
            "intercept": intercept_omega,
            "beta": beta_log_omega,
        },
        "frozen_baseline_pi": {
            "formula": "P(collapse) = 1 / (1 + exp(-(intercept + beta * log_pi_m)))",
            "intercept": intercept_pi,
            "beta": beta_log_pi,
        },
        "collapse_cause_confusion": confusion,
    }
    return discovery_summary

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "../../../../outputs/coin-mechanisms/mobilization_runway_discovery_v1.csv"
    summary = fit_and_evaluate_discovery(path)
    out_json = sys.argv[2] if len(sys.argv) > 2 else "discovery_metrics_temp.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote summary to {out_json}")
