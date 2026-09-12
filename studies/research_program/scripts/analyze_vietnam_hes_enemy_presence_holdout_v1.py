from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


ROOT = Path(__file__).resolve().parents[3]


def parse_distribution(text: str) -> dict[str, int]:
    try:
        raw = json.loads(text)
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        try:
            out[str(k).strip().upper()] = int(v)
        except Exception:
            continue
    return out


def burden(text: str) -> float:
    d = parse_distribution(text)
    good = sum(d.get(k, 0) for k in ["A", "B"])
    bad = sum(d.get(k, 0) for k in ["C", "D", "E", "V"])
    den = good + bad
    return float(bad / den) if den > 0 else np.nan


def build_panel() -> pd.DataFrame:
    base = ROOT / "studies/vietnam_1955_1975/data/standard_v2"
    aux = pd.read_parquet(base / "auxiliary_observations.parquet")
    events = pd.read_parquet(base / "events.parquet")
    unit = pd.read_parquet(base / "unit_time.parquet")

    p = aux[aux.construct.eq("hes_enemy_military_presence_submodel")].copy()
    p["month"] = pd.to_datetime(p.period_start).dt.to_period("M").dt.to_timestamp()
    p["presence_burden"] = p.value_text.map(burden)
    p = p[["unit_id", "month", "presence_burden"]].dropna()

    e = events[events.unit_id.notna() & events.actor_a.eq("Enemy")].copy()
    e["month"] = pd.to_datetime(e.event_date).dt.to_period("M").dt.to_timestamp()
    ec = e.groupby([e.unit_id.astype(str), "month"]).size().rename("enemy_events").reset_index()

    u = unit.copy()
    u["month"] = pd.to_datetime(u.period_start).dt.to_period("M").dt.to_timestamp()
    u = u[~u.observation_status.eq("source_gap")][["unit_id", "month"]].drop_duplicates()
    panel = u.merge(ec, on=["unit_id", "month"], how="left")
    panel["enemy_events"] = panel.enemy_events.fillna(0).astype(int)
    panel = panel.merge(p, on=["unit_id", "month"], how="inner")
    panel = panel.sort_values(["unit_id", "month"]).reset_index(drop=True)

    # Lagged/future windows are built only from explicitly covered event months.
    lookup = {(r.unit_id, r.month): r.enemy_events for r in panel.itertuples()}
    national = panel.groupby("month").enemy_events.sum().to_dict()
    rows = []
    for r in panel.itertuples():
        prev = [r.month - pd.DateOffset(months=i) for i in (1, 2, 3)]
        fut = [r.month + pd.DateOffset(months=i) for i in (1, 2, 3)]
        if not all((r.unit_id, m) in lookup for m in prev + fut):
            continue
        own_prev = sum(lookup[(r.unit_id, m)] for m in prev)
        nat_prev = sum(national.get(m, 0) for m in prev)
        future = sum(lookup[(r.unit_id, m)] for m in fut)
        rows.append({
            "unit_id": r.unit_id,
            "month": r.month,
            "presence_burden": float(r.presence_burden),
            "own_prev3": own_prev,
            "national_prev3": nat_prev,
            "future3": future,
        })
    return pd.DataFrame(rows)


def design(df: pd.DataFrame, units: list[str], enhanced: bool) -> np.ndarray:
    month = pd.to_datetime(df.month).dt.month.to_numpy(float)
    cols = [
        np.log1p(df.own_prev3.to_numpy(float)),
        np.log1p(df.national_prev3.to_numpy(float)),
        np.sin(2 * np.pi * month / 12.0),
        np.cos(2 * np.pi * month / 12.0),
    ]
    # Stable province effects fixed from the training-unit universe. One unit is
    # omitted as reference; unseen units would receive all zeroes.
    for u in units[1:]:
        cols.append((df.unit_id.astype(str).to_numpy() == u).astype(float))
    if enhanced:
        cols.append(df.presence_burden.to_numpy(float))
    return np.column_stack(cols)


def score(y: np.ndarray, pred: np.ndarray) -> dict:
    rho = spearmanr(y, pred).statistic
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "mae": float(mean_absolute_error(y, pred)),
        "spearman": None if not np.isfinite(rho) else float(rho),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    df = build_panel()
    train = df[(df.month >= "1969-07-01") & (df.month <= "1970-12-01")].copy()
    test = df[(df.month >= "1971-01-01") & (df.month <= "1971-12-01")].copy()
    units = sorted(train.unit_id.astype(str).unique())
    train = train[train.unit_id.astype(str).isin(units)]
    test = test[test.unit_id.astype(str).isin(units)]
    ytr = np.log1p(train.future3.to_numpy(float))
    yte = np.log1p(test.future3.to_numpy(float))

    xb_tr = design(train, units, False)
    xb_te = design(test, units, False)
    xe_tr = design(train, units, True)
    xe_te = design(test, units, True)
    baseline = LinearRegression().fit(xb_tr, ytr)
    enhanced = LinearRegression().fit(xe_tr, ytr)
    pb = baseline.predict(xb_te)
    pe = enhanced.predict(xe_te)
    sb = score(yte, pb)
    se = score(yte, pe)
    rmse_red = (sb["rmse"] - se["rmse"]) / sb["rmse"] if sb["rmse"] > 0 else 0.0
    rho_gain = (se["spearman"] or 0.0) - (sb["spearman"] or 0.0)
    presence_coef = float(enhanced.coef_[-1])

    q1 = test.presence_burden.quantile(0.25)
    q3 = test.presence_burden.quantile(0.75)
    lo = test[test.presence_burden <= q1].future3.mean()
    hi = test[test.presence_burden >= q3].future3.mean()
    ratio = float(hi / lo) if lo > 0 else None

    gates = {
        "heldout_rmse_relative_reduction_ge_0_02": rmse_red >= 0.02,
        "heldout_spearman_gain_ge_0_02": rho_gain >= 0.02,
        "training_presence_coefficient_positive": presence_coef > 0,
    }
    passed = all(gates.values())
    out = {
        "schema_version": "pineland.vietnam_hes_enemy_presence_holdout_results.v1",
        "status": "INDEPENDENT_PRESENCE_SIGNAL_ADDS_HELDOUT_PREDICTIVE_INFORMATION" if passed else "INDEPENDENT_PRESENCE_SIGNAL_NOT_CONFIRMED_ON_1971_HOLDOUT",
        "latent_state_estimation": False,
        "historical_parameter_fitting_to_pineland": False,
        "panel_rows": int(len(df)),
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_month_range": [str(train.month.min().date()), str(train.month.max().date())],
        "test_month_range": [str(test.month.min().date()), str(test.month.max().date())],
        "baseline_test": sb,
        "enhanced_test": se,
        "heldout_rmse_relative_reduction": float(rmse_red),
        "heldout_spearman_gain": float(rho_gain),
        "training_presence_coefficient": presence_coef,
        "heldout_presence_burden_quartiles": {
            "q25": float(q1),
            "q75": float(q3),
            "mean_future3_bottom_quartile": float(lo),
            "mean_future3_top_quartile": float(hi),
            "top_to_bottom_future_activity_ratio": ratio,
        },
        "gates": gates,
        "guard": "Independent historical presence-to-future-activity test only; HES is not equated to Pineland M_star or territorial control.",
    }
    Path(ns.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
