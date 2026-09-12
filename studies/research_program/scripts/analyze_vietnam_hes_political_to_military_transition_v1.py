from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[3]
KNOWN = {"A", "B", "C", "D", "E"}
HIGH = {"C", "D", "E"}
LOW = {"A", "B"}


def design(df: pd.DataFrame, provinces: list[str], enhanced: bool) -> np.ndarray:
    m = pd.to_datetime(df.anchor_month).dt.month.to_numpy(float)
    cols = [
        df.military_B_fraction_past3.to_numpy(float),
        np.sin(2 * np.pi * m / 12.0),
        np.cos(2 * np.pi * m / 12.0),
    ]
    pv = df.province_code.astype(str).to_numpy()
    for p in provinces[1:]:
        cols.append((pv == p).astype(float))
    if enhanced:
        cols.append(df.political_high_fraction_past3.to_numpy(float))
    return np.column_stack(cols)


def build_risk() -> pd.DataFrame:
    src = ROOT / "studies/vietnam_1955_1975/data/raw/vietwar_hes70.rds"
    d = pyreadr.read_r(str(src))[None]
    x = d[d.rectp_record_type.eq("Hamlet Record")].copy()
    x["month"] = pd.to_datetime(x.date, errors="coerce").dt.to_period("M").dt.to_timestamp()
    x["hamlet"] = x.us_hamlet_id.astype(str)
    x["province_code"] = x.province_code.astype(str).str.zfill(2)
    x["mil"] = x.mod1a_enemy_military_presence_submodel.astype(str).str.strip().str.upper()
    x["pol"] = x.mod1h_enemy_political_presence_submodel.astype(str).str.strip().str.upper()
    x = x[x.month.notna()].copy()

    # Multiple rows for a hamlet-month would make state ambiguous. Keep only
    # hamlet-months with one unique known military/political state pair.
    agg = (
        x.groupby(["hamlet", "month"], observed=True)
        .agg(
            province_code=("province_code", "first"),
            mil=("mil", lambda s: s.iloc[0] if s.nunique(dropna=False) == 1 else "AMBIG"),
            pol=("pol", lambda s: s.iloc[0] if s.nunique(dropna=False) == 1 else "AMBIG"),
        )
        .reset_index()
    )
    lookup = {(r.hamlet, r.month): (r.mil, r.pol, r.province_code) for r in agg.itertuples()}
    months_by_hamlet = agg.groupby("hamlet", observed=True).month.apply(list)
    rows = []
    for hamlet, months in months_by_hamlet.items():
        for t in months:
            prev = [t - pd.DateOffset(months=i) for i in (2, 1, 0)]
            fut = [t + pd.DateOffset(months=i) for i in (1, 2, 3)]
            if not all((hamlet, m) in lookup for m in prev + fut):
                continue
            prev_states = [lookup[(hamlet, m)] for m in prev]
            fut_states = [lookup[(hamlet, m)] for m in fut]
            mil_prev = [z[0] for z in prev_states]
            pol_prev = [z[1] for z in prev_states]
            mil_fut = [z[0] for z in fut_states]
            if not all(v in LOW for v in mil_prev):
                continue
            if not all(v in KNOWN for v in pol_prev + mil_fut):
                continue
            province = prev_states[-1][2]
            rows.append(
                {
                    "hamlet": hamlet,
                    "province_code": province,
                    "anchor_month": t,
                    "military_B_fraction_past3": sum(v == "B" for v in mil_prev) / 3.0,
                    "political_high_fraction_past3": sum(v in HIGH for v in pol_prev) / 3.0,
                    "y_90d": int(any(v in HIGH for v in mil_fut)),
                    "y_30d": int(mil_fut[0] in HIGH),
                }
            )
    return pd.DataFrame(rows)


def metric(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auc": float(roc_auc_score(y, p)),
        "logloss": float(log_loss(y, p, labels=[0, 1])),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    risk = build_risk()
    train = risk[(risk.anchor_month >= "1970-01-01") & (risk.anchor_month <= "1970-12-01")].copy()
    test = risk[(risk.anchor_month >= "1971-01-01") & (risk.anchor_month <= "1971-12-01")].copy()
    provinces = sorted(train.province_code.astype(str).unique())
    train = train[train.province_code.astype(str).isin(provinces)].copy()
    test = test[test.province_code.astype(str).isin(provinces)].copy()
    ytr = train.y_90d.to_numpy(int)
    yte = test.y_90d.to_numpy(int)

    xbtr = design(train, provinces, False)
    xbte = design(test, provinces, False)
    xetr = design(train, provinces, True)
    xete = design(test, provinces, True)
    base = LogisticRegression(penalty=None, solver="lbfgs", max_iter=5000).fit(xbtr, ytr)
    enh = LogisticRegression(penalty=None, solver="lbfgs", max_iter=5000).fit(xetr, ytr)
    pb = base.predict_proba(xbte)[:, 1]
    pe = enh.predict_proba(xete)[:, 1]
    mb = metric(yte, pb)
    me = metric(yte, pe)
    auc_gain = me["auc"] - mb["auc"]
    ll_gain = mb["logloss"] - me["logloss"]
    coef = float(enh.coef_[0, -1])

    unex = test[test.political_high_fraction_past3.eq(0)]
    exp = test[test.political_high_fraction_past3.ge(2 / 3 - 1e-12)]
    r0 = float(unex.y_90d.mean()) if len(unex) else None
    r1 = float(exp.y_90d.mean()) if len(exp) else None
    rr = float(r1 / r0) if r0 is not None and r0 > 0 and r1 is not None else None

    strata = []
    for v in [0.0, 1 / 3, 2 / 3, 1.0]:
        g = test[np.isclose(test.political_high_fraction_past3, v)]
        strata.append(
            {
                "political_high_fraction": v,
                "n": int(len(g)),
                "transition_risk_90d": float(g.y_90d.mean()) if len(g) else None,
                "transition_risk_30d": float(g.y_30d.mean()) if len(g) else None,
            }
        )

    gates = {
        "heldout_auc_gain_ge_0_02": auc_gain >= 0.02,
        "heldout_logloss_gain_ge_0_005": ll_gain >= 0.005,
        "training_political_presence_coefficient_positive": coef > 0,
        "heldout_unadjusted_risk_ratio_ge_1_25": rr is not None and rr >= 1.25,
    }
    passed = all(gates.values())
    out = {
        "schema_version": "pineland.vietnam_hes_political_to_military_transition_results.v1",
        "status": "POLITICAL_PRESENCE_PRECEDES_MILITARY_DETERIORATION_ON_HELDOUT_HES_SUPPORT" if passed else "POLITICAL_TO_MILITARY_TRANSITION_NOT_CONFIRMED",
        "historical_parameter_fitting_to_pineland": False,
        "latent_state_estimation": False,
        "risk_rows_all_years": int(len(risk)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_positive_rate": float(train.y_90d.mean()),
        "test_positive_rate": float(test.y_90d.mean()),
        "baseline_test": mb,
        "enhanced_test": me,
        "heldout_auc_gain": float(auc_gain),
        "heldout_logloss_gain": float(ll_gain),
        "training_political_presence_coefficient": coef,
        "heldout_unexposed": {"n": int(len(unex)), "risk": r0},
        "heldout_exposed_ge_2_of_3": {"n": int(len(exp)), "risk": r1},
        "heldout_unadjusted_risk_ratio": rr,
        "heldout_exposure_strata": strata,
        "gates": gates,
        "guard": "Same-system HES temporal state-transition test; does not identify Pineland M_star/F or establish independent-source causality."
    }
    Path(ns.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
