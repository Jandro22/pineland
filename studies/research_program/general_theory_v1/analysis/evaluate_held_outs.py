#!/usr/bin/env python3
"""
Evaluate Held-Out Families H1-H5 Against Frozen Mobilization Runway Phase Law
Zero Refitting Protocol
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

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def compute_calibration(y_true, y_prob):
    p = np.clip(y_prob, 1e-6, 1.0 - 1e-6)
    logit_p = np.log(p / (1.0 - p))
    lr = LogisticRegression(C=1e9, solver="lbfgs")
    try:
        lr.fit(logit_p.reshape(-1, 1), y_true)
        slope = float(lr.coef_[0][0])
        intercept = float(lr.intercept_[0])
    except Exception:
        slope = float("nan")
        intercept = float("nan")
    return slope, intercept

def evaluate_dataframe(df, frozen_law, frozen_baseline):
    # Predict with frozen Omega_K law
    # P(collapse) = 1 / (1 + exp(-(intercept + beta * log_omega)))
    omega = df["omega_k"].values
    log_omega = np.where(np.isinf(omega) | (omega >= 20000.0), 10.0, np.log(np.maximum(omega, 1e-4)))
    log_omega = np.clip(log_omega, -9.21, 10.0)

    intercept_omega = frozen_law["intercept"]
    beta_omega = frozen_law["beta"]
    logit_p_omega = intercept_omega + beta_omega * log_omega
    prob_omega = 1.0 / (1.0 + np.exp(-logit_p_omega))
    df["prob_omega"] = prob_omega

    # Predict with frozen Pi_M baseline
    pi_m = df["pi_m"].values
    log_pi = np.log(np.maximum(pi_m, 1e-6))
    intercept_pi = frozen_baseline["intercept"]
    beta_pi = frozen_baseline["beta"]
    logit_p_pi = intercept_pi + beta_pi * log_pi
    prob_pi = 1.0 / (1.0 + np.exp(-logit_p_pi))
    df["prob_pi"] = prob_pi

    y = df["capital_collapse_day360"].values
    base_rate = float(np.mean(y))
    base_rate_brier = float(np.mean((base_rate - y) ** 2))

    has_both_classes = len(np.unique(y)) > 1
    if has_both_classes:
        auc_omega = float(roc_auc_score(y, prob_omega))
        pr_auc_omega = float(average_precision_score(y, prob_omega))
        slope_omega, inter_omega = compute_calibration(y, prob_omega)

        auc_pi = float(roc_auc_score(y, prob_pi))
        pr_auc_pi = float(average_precision_score(y, prob_pi))
        slope_pi, inter_pi = compute_calibration(y, prob_pi)
    else:
        auc_omega = float("nan")
        pr_auc_omega = float("nan")
        slope_omega = float("nan")
        inter_omega = float("nan")
        auc_pi = float("nan")
        pr_auc_pi = float("nan")
        slope_pi = float("nan")
        inter_pi = float("nan")

    brier_omega = float(brier_score_loss(y, prob_omega))
    loss_omega = float(log_loss(y, prob_omega))

    brier_pi = float(brier_score_loss(y, prob_pi))
    loss_pi = float(log_loss(y, prob_pi))

    # Monotone direction check: correlation between log_omega and y
    corr_omega = float(np.corrcoef(log_omega, y)[0, 1]) if has_both_classes else float("nan")
    monotone_correct = corr_omega < 0.0 if not np.isnan(corr_omega) else True

    return {
        "n": len(df),
        "base_rate": base_rate,
        "base_rate_brier": base_rate_brier,
        "has_both_classes": has_both_classes,
        "omega_k_frozen": {
            "roc_auc": auc_omega,
            "pr_auc": pr_auc_omega,
            "brier_score": brier_omega,
            "brier_relative_to_base_rate": brier_omega - base_rate_brier,
            "log_loss": loss_omega,
            "calibration_slope": slope_omega,
            "calibration_intercept": inter_omega,
            "correlation_with_outcome": corr_omega,
            "monotone_direction_correct": monotone_correct,
        },
        "pi_m_baseline": {
            "roc_auc": auc_pi,
            "pr_auc": pr_auc_pi,
            "brier_score": brier_pi,
            "brier_relative_to_base_rate": brier_pi - base_rate_brier,
            "log_loss": loss_pi,
            "calibration_slope": slope_pi,
            "calibration_intercept": inter_pi,
        },
    }

def main():
    frozen_path = "studies/research_program/general_theory_v1/mobilization_runway_phase_law_frozen_v1.json"
    with open(frozen_path, "r") as f:
        frozen = json.load(f)
    frozen_law = frozen["frozen_logistic_model"]
    frozen_baseline = frozen["frozen_baseline_model"]

    holdout_files = {
        "H1_replenishment": "outputs/coin-mechanisms/mobilization_runway_h1_v1.csv",
        "H2_external_resource": "outputs/coin-mechanisms/mobilization_runway_h2_v1.csv",
        "H3_logistics_cost": "outputs/coin-mechanisms/mobilization_runway_h3_v1.csv",
        "H4_force_structure": "outputs/coin-mechanisms/mobilization_runway_h4_v1.csv",
        "H5_history_shock": "outputs/coin-mechanisms/mobilization_runway_h5_v1.csv",
    }

    family_results = {}
    pooled_dfs = []

    for name, path in holdout_files.items():
        if not os.path.exists(path):
            print(f"Skipping {name} (file not found: {path})")
            continue
        print(f"\nEvaluating Held-out Family: {name} ({path})")
        df_raw = pd.read_csv(path)
        sha = sha256_file(path)
        df = df_raw[df_raw["survived_to_120"] == True].copy()
        res = evaluate_dataframe(df, frozen_law, frozen_baseline)
        res["sha256"] = sha
        res["total_trajectories"] = len(df_raw)
        res["survived_to_120"] = len(df)
        res["excluded_pre_120"] = len(df_raw) - len(df)
        family_results[name] = res
        pooled_dfs.append(df)

        print(f"  Trajectories: {len(df_raw)} (survived 120: {len(df)})")
        print(f"  Base Rate: {res['base_rate']:.4f}")
        print(f"  Omega_K Frozen AUC: {res['omega_k_frozen']['roc_auc']:.4f}, Brier: {res['omega_k_frozen']['brier_score']:.4f} (Base Brier: {res['base_rate_brier']:.4f})")
        print(f"  Omega_K Calib Slope: {res['omega_k_frozen']['calibration_slope']:.4f}")
        print(f"  Pi_M Baseline AUC:  {res['pi_m_baseline']['roc_auc']:.4f}, Brier: {res['pi_m_baseline']['brier_score']:.4f}")

    if pooled_dfs:
        pooled_df = pd.concat(pooled_dfs, ignore_index=True)
        print(f"\n==========================================")
        print(f"POOLED HELD-OUT EVALUATION ({len(pooled_df)} trajectories across {len(pooled_dfs)} families)")
        print(f"==========================================")
        pooled_res = evaluate_dataframe(pooled_df, frozen_law, frozen_baseline)
        print(f"Pooled Base Rate: {pooled_res['base_rate']:.4f}")
        print(f"Pooled Omega_K Frozen ROC AUC: {pooled_res['omega_k_frozen']['roc_auc']:.4f}")
        print(f"Pooled Omega_K PR AUC:        {pooled_res['omega_k_frozen']['pr_auc']:.4f}")
        print(f"Pooled Omega_K Brier Score:   {pooled_res['omega_k_frozen']['brier_score']:.4f} (Base Rate Brier: {pooled_res['base_rate_brier']:.4f})")
        print(f"Pooled Omega_K Calib Slope:   {pooled_res['omega_k_frozen']['calibration_slope']:.4f}, Intercept: {pooled_res['omega_k_frozen']['calibration_intercept']:.4f}")
        print(f"Pooled Pi_M Baseline ROC AUC:  {pooled_res['pi_m_baseline']['roc_auc']:.4f}")
        print(f"Pooled Pi_M Baseline Brier:    {pooled_res['pi_m_baseline']['brier_score']:.4f}")

        # Evaluate Gates
        g1_auc = pooled_res['omega_k_frozen']['roc_auc'] >= 0.85
        g2_brier = pooled_res['omega_k_frozen']['brier_score'] < pooled_res['base_rate_brier']
        slope = pooled_res['omega_k_frozen']['calibration_slope']
        g3_calib = 0.70 <= slope <= 1.30 if not np.isnan(slope) else False
        g4_direction = all(f["omega_k_frozen"]["monotone_direction_correct"] for f in family_results.values())
        families_with_auc_80 = sum(
            1 for f in family_results.values()
            if f["has_both_classes"] and f["omega_k_frozen"]["roc_auc"] >= 0.80
        )
        identifiable_families = sum(1 for f in family_results.values() if f["has_both_classes"])
        g5_families = families_with_auc_80 >= min(4, identifiable_families)
        g6_beats_baseline = (pooled_res['omega_k_frozen']['roc_auc'] > pooled_res['pi_m_baseline']['roc_auc']) or (pooled_res['omega_k_frozen']['brier_score'] < pooled_res['pi_m_baseline']['brier_score'])

        gates = {
            "gate_1_pooled_roc_auc_ge_085": {"passed": bool(g1_auc), "value": pooled_res['omega_k_frozen']['roc_auc'], "threshold": 0.85},
            "gate_2_brier_beats_base_rate": {"passed": bool(g2_brier), "value": pooled_res['omega_k_frozen']['brier_score'], "base_rate_brier": pooled_res['base_rate_brier']},
            "gate_3_calibration_slope_in_range": {"passed": bool(g3_calib), "value": slope, "range": [0.70, 1.30]},
            "gate_4_monotone_direction_all": {"passed": bool(g4_direction)},
            "gate_5_min_families_auc_80": {"passed": bool(g5_families), "families_ge_80": families_with_auc_80, "identifiable_families": identifiable_families},
            "gate_6_beats_crude_baseline": {"passed": bool(g6_beats_baseline), "omega_auc": pooled_res['omega_k_frozen']['roc_auc'], "pi_auc": pooled_res['pi_m_baseline']['roc_auc'], "omega_brier": pooled_res['omega_k_frozen']['brier_score'], "pi_brier": pooled_res['pi_m_baseline']['brier_score']},
        }

        all_passed = all(g["passed"] for g in gates.values())
        print("\n--- Transport Gate Evaluation ---")
        for k, v in gates.items():
            print(f"  {k}: {'PASSED' if v['passed'] else 'FAILED'} ({v})")
        print(f"Overall Transport Claim Status: {'STRONG_SYNTHETIC_TRANSPORT' if all_passed else 'EVALUATE_FALSIFICATION'}")

        output_data = {
            "family_results": family_results,
            "pooled_results": pooled_res,
            "gates": gates,
            "all_gates_passed": all_passed,
        }
        out_json = sys.argv[1] if len(sys.argv) > 1 else "studies/research_program/general_theory_v1/held_out_transport_evaluation_v1.json"
        with open(out_json, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nSaved evaluation to {out_json}")

if __name__ == "__main__":
    main()
