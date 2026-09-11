from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler


CONTROLS = [
    "quality",
    "log_anchor_personnel",
    "readiness",
    "cohesion",
    "supply_fraction",
    "command",
    "embeddedness",
    "availability",
]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def controlled_summary(df: pd.DataFrame) -> dict:
    metrics = [
        "single_loss_fraction",
        "single_opponent_loss_fraction",
        "single_tactical_win",
        "campaign_combat_effective",
        "campaign_loss_exchange_ratio",
        "final_personnel_fraction",
    ]
    summary: dict[str, object] = {}
    for side, s in df.groupby("side"):
        levels = {}
        for exp, g in s.groupby("initial_experience"):
            levels[f"{exp:.1f}"] = {
                metric: float(np.mean(g[metric].replace([np.inf, -np.inf], np.nan).dropna()))
                for metric in metrics
            }
            levels[f"{exp:.1f}"]["n"] = int(len(g))
        low = s[np.isclose(s.initial_experience, 0.1)].sort_values("replicate")
        high = s[np.isclose(s.initial_experience, 0.9)].sort_values("replicate")
        paired = low.merge(high, on="replicate", suffixes=("_low", "_high"), validate="one_to_one")
        contrast = {}
        for metric in metrics:
            a = paired[f"{metric}_low"].replace([np.inf, -np.inf], np.nan)
            b = paired[f"{metric}_high"].replace([np.inf, -np.inf], np.nan)
            mask = a.notna() & b.notna()
            delta = b[mask].to_numpy(float) - a[mask].to_numpy(float)
            contrast[metric] = {
                "mean_high_minus_low": float(np.mean(delta)),
                "median_high_minus_low": float(np.median(delta)),
            }
        summary[side] = {"levels": levels, "experience_0_9_minus_0_1": contrast}
    return summary


def naturalistic_side(df: pd.DataFrame) -> dict:
    d = df.copy()
    d["log_anchor_personnel"] = np.log1p(d.anchor_personnel.clip(lower=0))
    q1, q2 = d.anchor_experience.quantile([1 / 3, 2 / 3])
    d["experience_band"] = pd.cut(
        d.anchor_experience,
        [-np.inf, q1, q2, np.inf],
        labels=["low", "mid", "high"],
        include_lowest=True,
    )
    bands = (
        d.groupby("experience_band", observed=True)
        .agg(
            n=("formation", "size"),
            mean_experience=("anchor_experience", "mean"),
            survival_rate=("combat_effective_180", "mean"),
            mean_personnel_survival=("personnel_survival_fraction", "mean"),
            mean_future_loss_fraction=("future_loss_fraction", "mean"),
        )
        .to_dict(orient="index")
    )
    pearson_survival = float(np.corrcoef(d.anchor_experience, d.combat_effective_180)[0, 1]) if d.combat_effective_180.nunique() > 1 else None
    pearson_personnel = float(np.corrcoef(d.anchor_experience, d.personnel_survival_fraction)[0, 1])
    pearson_losses = float(np.corrcoef(d.anchor_experience, d.future_loss_fraction)[0, 1])

    features = ["anchor_experience", *CONTROLS]
    X = d[features].to_numpy(float)
    y = d.combat_effective_180.to_numpy(int)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    adjusted = {}
    experience_range = float(d.anchor_experience.max() - d.anchor_experience.min())
    minority_count = int(min(np.sum(y == 0), np.sum(y == 1))) if len(np.unique(y)) == 2 else 0
    survival_identifiable = len(np.unique(y)) == 2 and minority_count >= 10 and experience_range >= 0.05
    adjusted["survival_identifiability"] = {
        "status": "IDENTIFIABLE_ON_OBSERVED_SUPPORT" if survival_identifiable else "NOT_IDENTIFIABLE_RANGE_OR_CEILING",
        "minority_class_count": minority_count,
        "observed_experience_min": float(d.anchor_experience.min()),
        "observed_experience_max": float(d.anchor_experience.max()),
        "observed_experience_range": experience_range,
    }
    if survival_identifiable:
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=3000).fit(Xs, y)
        adjusted["survival_standardized_experience_coef"] = float(model.coef_[0, 0])
        q10 = float(d.anchor_experience.quantile(0.10))
        q90 = float(d.anchor_experience.quantile(0.90))
        base = d[features].copy()
        low = base.copy(); low["anchor_experience"] = q10
        high = base.copy(); high["anchor_experience"] = q90
        p_low = model.predict_proba(scaler.transform(low.to_numpy(float)))[:, 1]
        p_high = model.predict_proba(scaler.transform(high.to_numpy(float)))[:, 1]
        adjusted["survival_q10_experience"] = q10
        adjusted["survival_q90_experience"] = q90
        adjusted["mean_adjusted_survival_probability_q10"] = float(p_low.mean())
        adjusted["mean_adjusted_survival_probability_q90"] = float(p_high.mean())
        adjusted["adjusted_survival_probability_difference_q90_minus_q10"] = float((p_high - p_low).mean())

        seeds = d.seed.to_numpy(int)
        pred_full = np.zeros(len(d)); pred_controls = np.zeros(len(d))
        for seed in np.unique(seeds):
            test = seeds == seed; train = ~test
            ytr = y[train]
            if len(np.unique(ytr)) < 2:
                pred_full[test] = ytr.mean(); pred_controls[test] = ytr.mean(); continue
            sf = StandardScaler().fit(d.loc[train, features])
            sc = StandardScaler().fit(d.loc[train, CONTROLS])
            mf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=3000).fit(sf.transform(d.loc[train, features]), ytr)
            mc = LogisticRegression(C=1e6, solver="lbfgs", max_iter=3000).fit(sc.transform(d.loc[train, CONTROLS]), ytr)
            pred_full[test] = mf.predict_proba(sf.transform(d.loc[test, features]))[:, 1]
            pred_controls[test] = mc.predict_proba(sc.transform(d.loc[test, CONTROLS]))[:, 1]
        pred_full = np.clip(pred_full, 1e-9, 1 - 1e-9); pred_controls = np.clip(pred_controls, 1e-9, 1 - 1e-9)
        adjusted["loso_auc_full"] = float(roc_auc_score(y, pred_full))
        adjusted["loso_auc_controls_only"] = float(roc_auc_score(y, pred_controls))
        adjusted["loso_auc_gain_from_experience"] = adjusted["loso_auc_full"] - adjusted["loso_auc_controls_only"]
        adjusted["loso_logloss_full"] = float(log_loss(y, pred_full, labels=[0, 1]))
        adjusted["loso_logloss_controls_only"] = float(log_loss(y, pred_controls, labels=[0, 1]))

    q10 = float(d.anchor_experience.quantile(0.10))
    q90 = float(d.anchor_experience.quantile(0.90))
    adjusted["continuous_outcome_q10_experience"] = q10
    adjusted["continuous_outcome_q90_experience"] = q90
    for target in ["personnel_survival_fraction", "future_loss_fraction"]:
        m = LinearRegression().fit(Xs, d[target].to_numpy(float))
        adjusted[f"{target}_standardized_experience_coef"] = float(m.coef_[0])
        low = d[features].copy(); low["anchor_experience"] = q10
        high = d[features].copy(); high["anchor_experience"] = q90
        adjusted[f"{target}_adjusted_q90_minus_q10"] = float(
            np.mean(m.predict(scaler.transform(high)) - m.predict(scaler.transform(low)))
        )
    return {
        "rows": int(len(d)),
        "experience_quantiles": {"q33": float(q1), "q67": float(q2)},
        "bands": bands,
        "raw_correlations": {
            "experience_vs_survival": pearson_survival,
            "experience_vs_personnel_survival": pearson_personnel,
            "experience_vs_future_loss_fraction": pearson_losses,
        },
        "adjusted": adjusted,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("controlled_csv")
    ap.add_argument("--naturalistic")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    controlled = pd.read_csv(args.controlled_csv)
    result = {
        "schema_version": "pineland.veterancy_outcomes_results.v1",
        "historical_outcomes_used": False,
        "controlled_input": str(Path(args.controlled_csv)),
        "controlled_sha256": sha256(args.controlled_csv),
        "controlled": controlled_summary(controlled),
        "interpretation_guard": "Controlled CRN contrasts isolate the synthetic model's causal experience mechanism. Naturalistic associations, when present, do not by themselves identify causality because combat exposure creates experience and survival selects who remains observable.",
    }
    if args.naturalistic:
        natural = pd.read_csv(args.naturalistic)
        result["naturalistic_input"] = str(Path(args.naturalistic))
        result["naturalistic_sha256"] = sha256(args.naturalistic)
        result["naturalistic"] = {
            side: naturalistic_side(group) for side, group in natural.groupby("side")
        }
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"controlled": result["controlled"], "naturalistic": result.get("naturalistic")}, indent=2))


if __name__ == "__main__":
    main()
