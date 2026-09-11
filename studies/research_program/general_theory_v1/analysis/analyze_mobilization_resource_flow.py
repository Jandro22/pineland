#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def grouped_loso_auc(df: pd.DataFrame, features: list[str], target: str) -> float:
    ys: list[float] = []
    ps: list[float] = []
    for seed in sorted(df.seed.unique()):
        train = df[df.seed != seed]
        test = df[df.seed == seed]
        ytr = train[target].to_numpy(int)
        if len(np.unique(ytr)) < 2:
            continue
        scaler = StandardScaler().fit(train[features].to_numpy(float))
        xtr = scaler.transform(train[features].to_numpy(float))
        xte = scaler.transform(test[features].to_numpy(float))
        model = LogisticRegression(C=1.0e6, max_iter=10000, solver="lbfgs")
        model.fit(xtr, ytr)
        ys.extend(test[target].to_numpy(int).tolist())
        ps.extend(model.predict_proba(xte)[:, 1].tolist())
    return float(roc_auc_score(ys, ps)) if len(set(ys)) == 2 else float("nan")


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    keys = ["seed", "recruitment_mult", "fielding_mult", "capital_mult"]
    scale = df[["initial_capital", "capital_inflow", "capital_outflow"]].abs().max(axis=1).clip(lower=1.0)
    rel_resid = df.accounting_residual.abs() / scale
    max_rel_resid = float(rel_resid.max())

    early = df[np.isclose(df.time, 30.0)].copy()
    final_time = float(df.time.max())
    final = df[np.isclose(df.time, final_time)].copy()
    merged = early.merge(
        final[keys + ["org_active", "capital", "lambda_k"]],
        on=keys,
        suffixes=("_30", "_final"),
        validate="one_to_one",
    )
    merged["collapse_180"] = (merged.org_active_final < 0.5).astype(int)
    net_burn = (merged.capital_outflow - merged.capital_inflow) / 30.0
    runway = np.where(net_burn > 1.0e-12, merged.capital_30 / net_burn, np.inf)
    merged["early_runway_days"] = runway
    # Preserve runway ordering while mapping +inf to an arbitrarily large
    # finite value for sklearn. The exact value cannot change finite-vs-infinite
    # ranking or the preregistered 150d threshold classification.
    finite = runway[np.isfinite(runway)]
    large = (float(finite.max()) + 1.0e6) if len(finite) else 1.0e9
    merged["neg_runway_score"] = -np.where(np.isfinite(runway), runway, large)
    runway_auc = float(roc_auc_score(merged.collapse_180, merged.neg_runway_score))

    merged["log_recruitment_mult"] = np.log(merged.recruitment_mult)
    merged["log_fielding_mult"] = np.log(merged.fielding_mult)
    merged["log_capital_mult"] = np.log(merged.capital_mult)
    multiplier_auc = grouped_loso_auc(
        merged,
        ["log_recruitment_mult", "log_fielding_mult", "log_capital_mult"],
        "collapse_180",
    )
    auc_regret = float(multiplier_auc - runway_auc)

    merged["predicted_collapse_runway_lt_150"] = (merged.early_runway_days < 150.0).astype(int)
    threshold_accuracy = float((merged.predicted_collapse_runway_lt_150 == merged.collapse_180).mean())
    collapsed = merged[merged.collapse_180 == 1].copy()
    capital_tol = 1.0e-9 * merged.initial_capital.clip(lower=1.0)
    exhausted = collapsed[collapsed.capital_final <= capital_tol.loc[collapsed.index]]
    exhaustion_consistent = bool(
        len(exhausted) == 0 or (exhausted.lambda_k_final >= 1.0 - 1.0e-8).all()
    )

    gates = {
        "conservation_max_relative_residual_le_1e_8": max_rel_resid <= 1.0e-8,
        "capital_exhaustion_consistency": exhaustion_consistent,
        "early_runway_loso_auc_ge_0_95": runway_auc >= 0.95,
        "runway_auc_regret_vs_multiplier_model_le_0_03": auc_regret <= 0.03,
    }
    passed = all(gates.values())

    out = {
        "schema_version": "pineland.mobilization_resource_flow_results.v1",
        "status": "RESOURCE_RUNWAY_COMPRESSION_CONFIRMED_ON_SYNTHETIC_SUPPORT" if passed else "RESOURCE_RUNWAY_PRIMARY_GATES_NOT_ALL_MET",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "integrity": {
            "trajectory_count": int(len(merged)),
            "seed_count": int(merged.seed.nunique()),
            "collapse_count": int(merged.collapse_180.sum()),
            "max_relative_accounting_residual": max_rel_resid,
            "exhausted_collapsed_count": int(len(exhausted)),
        },
        "primary": {
            "early_runway_auc": runway_auc,
            "multiplier_model_loso_auc": multiplier_auc,
            "runway_auc_regret": auc_regret,
            "runway_lt_150_accuracy": threshold_accuracy,
            "median_runway_collapsed": float(collapsed.early_runway_days.replace(np.inf, np.nan).median()),
            "median_runway_survived": float(merged.loc[merged.collapse_180 == 0, "early_runway_days"].replace(np.inf, np.nan).median()),
        },
        "gates": gates,
        "interpretation_guard": "Exact stock-flow accounting and early-runway compression are scoped to the closed synthetic focal-insurgent assay; no historical or cross-topology transport is licensed.",
    }
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
