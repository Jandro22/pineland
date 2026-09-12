from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[3]
CORE = ["eval_a", "eval_b", "eval_c", "eval_d", "eval_e", "eval_g", "eval_h", "eval_i", "eval_k", "eval_l"]


def month_key(x: pd.Series) -> pd.Series:
    return pd.to_datetime(x).dt.to_period("M").astype(str)


def friendly_casualties(d: pd.DataFrame) -> pd.Series:
    return (
        d.friendly_kia.fillna(0).astype(float)
        + d.friendly_wia.fillna(0).astype(float)
        + d.friendly_mia.fillna(0).astype(float)
    )


def build_linked_panel(include_personnel_anomalies: bool = False) -> tuple[pd.DataFrame, dict]:
    tfes = pd.read_parquet(ROOT / "studies/vietnam_1955_1975/data/derived/tfes_direct_unit_month_1970_1972.parquet")
    vnus = pd.read_parquet(ROOT / "studies/vietnam_1955_1975/data/derived/vnus_direct_unit_month_1971_1972.parquet")

    t = tfes[tfes.stat_code.eq("0")].copy()
    t["month"] = month_key(t.report_month)
    t["key"] = t.district_id.astype(str) + ":" + t.unit_type.astype(str) + ":" + t.unit_series.astype(str)
    valid_core = t[CORE].apply(lambda s: s.isin([1, 2, 3, 4]))
    t["quality_complete"] = valid_core.all(axis=1)
    t["quality_adequate_fraction"] = t[CORE].isin([1, 2]).sum(axis=1) / len(CORE)
    t["personnel_ok"] = t.assigned_total.gt(0)
    if not include_personnel_anomalies:
        t["personnel_ok"] &= t.present_total.le(t.assigned_total)

    # Any candidate identity with >1 active TFES row in a month is excluded
    # rather than arbitrarily resolved after outcomes are observed.
    tfes_mult = t.groupby(["month", "key"], observed=True).size().rename("n_tfes")
    t = t.merge(tfes_mult, on=["month", "key"], how="left")
    t = t[t.n_tfes.eq(1) & t.quality_complete & t.personnel_ok].copy()

    v = vnus[vnus.date_status.eq("valid_source_date")].copy()
    v["month"] = month_key(v.report_date)
    v["key"] = v.logical_unit_id_vnus.astype(str)
    vnus_mult = v.groupby(["month", "key"], observed=True).size().rename("n_vnus")
    v = v.merge(vnus_mult, on=["month", "key"], how="left")
    v = v[v.n_vnus.eq(1)].copy()
    v["friendly_casualties"] = friendly_casualties(v)
    v["contact_ops"] = pd.to_numeric(v.day_night_operations_with_contact, errors="coerce").fillna(0).clip(lower=0)
    v["total_ops"] = pd.to_numeric(v.day_night_operations_total, errors="coerce").fillna(0).clip(lower=0)
    v["enemy_reported_effect"] = (
        pd.to_numeric(v.enemy_kia, errors="coerce").fillna(0).clip(lower=0)
        + pd.to_numeric(v.enemy_captured, errors="coerce").fillna(0).clip(lower=0)
    )

    current_cols = ["month", "key", "friendly_casualties", "contact_ops", "total_ops", "enemy_reported_effect"]
    cur = v[current_cols].rename(columns={
        "friendly_casualties": "current_friendly_casualties",
        "contact_ops": "current_contact_ops",
        "total_ops": "current_total_ops",
        "enemy_reported_effect": "current_enemy_reported_effect",
    })
    fut = v[current_cols].copy()
    fut["month"] = (pd.PeriodIndex(fut.month, freq="M") - 1).astype(str)
    fut = fut.rename(columns={
        "friendly_casualties": "future_friendly_casualties",
        "contact_ops": "future_contact_ops",
        "total_ops": "future_total_ops",
        "enemy_reported_effect": "future_enemy_reported_effect",
    })

    panel = t.merge(cur, on=["month", "key"], how="inner", validate="one_to_one")
    panel = panel.merge(fut, on=["month", "key"], how="inner", validate="one_to_one")
    panel = panel[panel.future_contact_ops.ge(1)].copy()
    panel["y_casualty"] = panel.future_friendly_casualties.gt(0).astype(int)
    panel["log_assigned"] = np.log1p(panel.assigned_total.astype(float))
    panel["log_current_casualties"] = np.log1p(panel.current_friendly_casualties.astype(float))
    panel["log_current_contacts"] = np.log1p(panel.current_contact_ops.astype(float))
    panel["log_future_contacts"] = np.log1p(panel.future_contact_ops.astype(float))
    m = pd.PeriodIndex(panel.month, freq="M").month.astype(float)
    panel["month_sin"] = np.sin(2 * np.pi * m / 12.0)
    panel["month_cos"] = np.cos(2 * np.pi * m / 12.0)

    # Secondary training-memory observation: at least one documented training
    # month lies within the preceding 12 months. Invalid/missing dates remain no
    # evidence, not a negative claim that no training occurred.
    anchor = pd.PeriodIndex(panel.month, freq="M")
    training_cols = [
        "basic_training_month", "refresher_training_month",
        "motivational_training_month", "revolutionary_development_training_month",
    ]
    recent_flags = np.zeros(len(panel), dtype=bool)
    known_training = np.zeros(len(panel), dtype=bool)
    for c in training_cols:
        raw = pd.to_datetime(panel[c], errors="coerce")
        known = raw.notna().to_numpy()
        known_training |= known
        periods = pd.PeriodIndex(raw, freq="M")
        delta = np.array([a.ordinal - b.ordinal if pd.notna(b.start_time) else 9999 for a, b in zip(anchor, periods)])
        recent_flags |= known & (delta >= 0) & (delta <= 12)
    panel["any_training_date_known"] = known_training
    panel["recent_training_within_12m"] = recent_flags

    integrity = {
        "tfes_active_rows_initial": int(tfes.stat_code.eq("0").sum()),
        "tfes_ambiguous_key_month_rows_excluded": int((t.n_tfes.gt(1)).sum()) if "n_tfes" in t else None,
        "linked_contact_exposed_rows": int(len(panel)),
        "unique_units": int(panel.key.nunique()),
        "months": sorted(panel.month.unique().tolist()),
        "personnel_anomalies_included": include_personnel_anomalies,
    }
    return panel, integrity


NUMERIC = [
    "log_assigned", "manning_ratio", "log_current_casualties",
    "log_current_contacts", "log_future_contacts", "month_sin", "month_cos",
]
CATEGORICAL = ["unit_type", "province_code"]


def model(enhanced: bool) -> Pipeline:
    nums = NUMERIC + (["quality_adequate_fraction"] if enhanced else [])
    prep = ColumnTransformer(
        [
            ("num", StandardScaler(), nums),
            ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), CATEGORICAL),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("prep", prep),
        ("logit", LogisticRegression(penalty=None, solver="lbfgs", max_iter=5000)),
    ])


def score(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "auc": float(roc_auc_score(y, p)),
        "logloss": float(log_loss(y, p, labels=[0, 1])),
    }


def run_primary(panel: pd.DataFrame) -> dict:
    train = panel[(panel.month >= "1971-07") & (panel.month <= "1971-12")].copy()
    test = panel[(panel.month >= "1972-01") & (panel.month <= "1972-06")].copy()
    ytr = train.y_casualty.to_numpy(int)
    yte = test.y_casualty.to_numpy(int)
    base = model(False).fit(train, ytr)
    enh = model(True).fit(train, ytr)
    pb = base.predict_proba(test)[:, 1]
    pe = enh.predict_proba(test)[:, 1]
    sb, se = score(yte, pb), score(yte, pe)
    auc_gain = se["auc"] - sb["auc"]
    ll_gain = sb["logloss"] - se["logloss"]

    feature_names = enh.named_steps["prep"].get_feature_names_out().tolist()
    coefs = enh.named_steps["logit"].coef_[0]
    qname = "num__quality_adequate_fraction"
    qcoef = float(coefs[feature_names.index(qname)])

    # Raw heldout quartiles are secondary/descriptive only.
    q = test.quality_adequate_fraction.quantile([0.25, 0.5, 0.75]).to_dict()
    bins = [
        ("q1", test.quality_adequate_fraction <= q[0.25]),
        ("q2", (test.quality_adequate_fraction > q[0.25]) & (test.quality_adequate_fraction <= q[0.5])),
        ("q3", (test.quality_adequate_fraction > q[0.5]) & (test.quality_adequate_fraction <= q[0.75])),
        ("q4", test.quality_adequate_fraction > q[0.75]),
    ]
    quartiles = []
    for name, mask in bins:
        g = test[mask]
        quartiles.append({
            "quartile": name,
            "n": int(len(g)),
            "mean_quality": float(g.quality_adequate_fraction.mean()) if len(g) else None,
            "casualty_incidence": float(g.y_casualty.mean()) if len(g) else None,
            "mean_future_contacts": float(g.future_contact_ops.mean()) if len(g) else None,
        })

    train_known = train[train.any_training_date_known]
    test_known = test[test.any_training_date_known]
    training_secondary = {
        "train_known_rows": int(len(train_known)),
        "test_known_rows": int(len(test_known)),
        "test_recent_training_rows": int(test_known.recent_training_within_12m.sum()),
        "test_casualty_risk_recent_training": float(test_known.loc[test_known.recent_training_within_12m, "y_casualty"].mean()) if test_known.recent_training_within_12m.any() else None,
        "test_casualty_risk_no_recent_documented_training": float(test_known.loc[~test_known.recent_training_within_12m, "y_casualty"].mean()) if (~test_known.recent_training_within_12m).any() else None,
    }

    gates = {
        "heldout_auc_gain_ge_0_015": auc_gain >= 0.015,
        "heldout_logloss_gain_ge_0_003": ll_gain >= 0.003,
        "training_quality_coefficient_negative": qcoef < 0,
    }
    return {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_units": int(train.key.nunique()),
        "test_units": int(test.key.nunique()),
        "train_casualty_rate": float(train.y_casualty.mean()),
        "test_casualty_rate": float(test.y_casualty.mean()),
        "baseline_test": sb,
        "enhanced_test": se,
        "heldout_auc_gain": float(auc_gain),
        "heldout_logloss_gain": float(ll_gain),
        "standardized_quality_coefficient": qcoef,
        "heldout_quality_quartiles": quartiles,
        "training_recency_secondary": training_secondary,
        "gates": gates,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    panel, integrity = build_linked_panel(False)
    primary = run_primary(panel)
    sens_panel, sens_integrity = build_linked_panel(True)
    sensitivity = run_primary(sens_panel)
    passed = all(primary["gates"].values())
    result = {
        "schema_version": "pineland.vietnam_tfes_quality_survival_results.v1",
        "status": "TFES_QUALITY_ADDS_HELDOUT_SURVIVAL_INFORMATION_BEYOND_HEADCOUNT" if passed else "TFES_QUALITY_SURVIVAL_INCREMENT_NOT_CONFIRMED",
        "historical_parameter_fitting_to_pineland": False,
        "latent_veterancy_estimation": False,
        "primary_integrity": integrity,
        "primary": primary,
        "source_anomaly_sensitivity_including_present_gt_assigned": {
            "integrity": sens_integrity,
            "result": sensitivity,
            "promotion_effect": "NONE; sensitivity can never replace primary result"
        },
        "guard": "TFES evaluation quality is a historical archival quality construct, not Pineland V_G. VNUS reporting error is not identified; body-count variables are not promotion endpoints."
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "primary": primary}, indent=2))


if __name__ == "__main__":
    main()
