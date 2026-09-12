from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


ROOT = Path(__file__).resolve().parents[3]

CASE_RULES = {
    "afghanistan_2004_2021": lambda d: d.actor_a.eq("Taleban") | d.actor_b.eq("Taleban"),
    "nepal_2001_2006": lambda d: d.actor_a.eq("CPN-M") | d.actor_b.eq("CPN-M"),
    "colombia_1984_2016": lambda d: (
        d.actor_a.fillna("").str.split(",").map(lambda xs: "FARC" in [x.strip() for x in xs])
        | d.actor_b.fillna("").str.split(",").map(lambda xs: "FARC" in [x.strip() for x in xs])
    ),
    "iraq_2003_2011": lambda d: d.actor_a.eq("IS") | d.actor_b.eq("IS"),
    "vietnam_1955_1975": lambda d: d.actor_a.eq("Enemy"),
}

HORIZONS = {"30d": 1, "90d": 3, "365d": 12}
QUIET = 12
RECENT = 3


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    r = 6371.0088
    la = np.radians(lat)[:, None]
    lo = np.radians(lon)[:, None]
    dla = la.T - la
    dlo = lo.T - lo
    a = np.sin(dla / 2) ** 2 + np.cos(la) * np.cos(la.T) * np.sin(dlo / 2) ** 2
    return 2 * r * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def month_start(x: pd.Series) -> pd.Series:
    return pd.to_datetime(x).dt.to_period("M").dt.to_timestamp()


def monthly_coverage(unit: pd.DataFrame, unit_ids: list[str], months: pd.DatetimeIndex) -> np.ndarray:
    u = unit.copy()
    u["month"] = month_start(u.period_start)
    u["covered"] = ~u.observation_status.eq("source_gap")
    # A month is covered only if every standardized observation row that falls
    # in it is covered. This is conservative for weekly cases and exact for
    # monthly Vietnam/Colombia/Iraq panels.
    g = u.groupby(["unit_id", "month"], observed=True).covered.all()
    mi = pd.MultiIndex.from_product([unit_ids, months], names=["unit_id", "month"])
    return g.reindex(mi, fill_value=False).to_numpy(bool).reshape(len(unit_ids), len(months))


def auc_safe(y: np.ndarray, score: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, score))


def analyze_case(case: str) -> dict:
    base = ROOT / "studies" / case / "data" / "standard_v2"
    geo = pd.read_parquet(base / "geography.parquet")
    events = pd.read_parquet(base / "events.parquet")
    unit = pd.read_parquet(base / "unit_time.parquet")

    geo = geo.dropna(subset=["centroid_latitude", "centroid_longitude"]).copy()
    ids = geo.unit_id.astype(str).tolist()
    idx = {u: i for i, u in enumerate(ids)}
    dist = haversine_matrix(geo.centroid_latitude.to_numpy(float), geo.centroid_longitude.to_numpy(float))
    d_no_self = dist.copy()
    np.fill_diagonal(d_no_self, np.inf)
    nearest = d_no_self.min(axis=1)
    L = float(np.median(nearest[np.isfinite(nearest)]))
    maxd = float(np.nanmax(dist))

    unit_months = month_start(unit.period_start)
    start = unit_months.min()
    end = unit_months.max()
    months = pd.date_range(start, end, freq="MS")
    covered = monthly_coverage(unit, ids, months)

    e = events[events.unit_id.notna()].copy()
    e = e[e.unit_id.astype(str).isin(idx)].copy()
    e = e[CASE_RULES[case](e)].copy()
    e["month"] = month_start(e.event_date)
    counts = np.zeros((len(ids), len(months)), dtype=np.int32)
    month_idx = {m: i for i, m in enumerate(months)}
    for (uid, m), n in e.groupby([e.unit_id.astype(str), "month"]).size().items():
        if uid in idx and m in month_idx:
            counts[idx[uid], month_idx[m]] = int(n)

    # Geography-only kernel scale. Diagonal is zeroed because the theory claim
    # being confronted is nonlocal propagation from OTHER units.
    kernel = np.exp(-dist / max(L, 1e-9))
    np.fill_diagonal(kernel, 0.0)

    rows = []
    max_h = max(HORIZONS.values())
    for t in range(QUIET, len(months) - max_h):
        quiet_cov = covered[:, t - QUIET : t].all(axis=1)
        quiet_zero = counts[:, t - QUIET : t].sum(axis=1) == 0
        future_cov = covered[:, t : t + max_h + 1].all(axis=1)
        eligible = quiet_cov & quiet_zero & covered[:, t] & future_cov
        if not eligible.any():
            continue
        recent = counts[:, max(0, t - RECENT) : t].sum(axis=1).astype(float)
        source = recent > 0
        if source.any():
            nearest_active = np.min(np.where(source[None, :], dist, np.inf), axis=1)
            # Exclude self from source influence even if a coding edge-case
            # reaches here; quiet eligibility normally ensures self is inactive.
            dynamic_h = kernel @ np.log1p(recent)
        else:
            nearest_active = np.full(len(ids), maxd + L)
            dynamic_h = np.zeros(len(ids))
        nearest_active[~np.isfinite(nearest_active)] = maxd + L

        elig_idx = np.where(eligible)[0]
        for i in elig_idx:
            r = {
                "unit_id": ids[i],
                "anchor_month": str(months[t].date()),
                "nearest_active_distance_km": float(nearest_active[i]),
                "dynamic_nonlocal_pressure": float(dynamic_h[i]),
            }
            for label, h in HORIZONS.items():
                r[f"y_{label}"] = int(counts[i, t + 1 : t + h + 1].sum() > 0)
            rows.append(r)

    risk = pd.DataFrame(rows)
    if risk.empty:
        return {"case_id": case, "status": "NO_ELIGIBLE_RISK_ROWS"}

    horizons = {}
    for label in HORIZONS:
        y = risk[f"y_{label}"].to_numpy(int)
        auc_d = auc_safe(y, -risk.nearest_active_distance_km.to_numpy(float))
        auc_h = auc_safe(y, risk.dynamic_nonlocal_pressure.to_numpy(float))
        positive = risk[y == 1]
        nonlocal_share = (
            float((positive.nearest_active_distance_km > 2 * L).mean()) if len(positive) else None
        )
        horizons[label] = {
            "n": int(len(risk)),
            "positives": int(y.sum()),
            "prevalence": float(y.mean()),
            "auc_nearest_active_distance": auc_d,
            "auc_dynamic_nonlocal_pressure": auc_h,
            "auc_gain_dynamic_minus_distance": None if auc_d is None or auc_h is None else float(auc_h - auc_d),
            "positive_onset_share_nearest_source_farther_than_2L": nonlocal_share,
            "positive_onset_median_nearest_source_km": float(positive.nearest_active_distance_km.median()) if len(positive) else None,
        }

    return {
        "case_id": case,
        "status": "OK",
        "canonical_units": len(ids),
        "case_length_scale_L_km": L,
        "principal_actor_event_rows": int(len(e)),
        "risk_rows": int(len(risk)),
        "horizons": horizons,
        "input_sha256": {
            "geography": sha256(base / "geography.parquet"),
            "events": sha256(base / "events.parquet"),
            "unit_time": sha256(base / "unit_time.parquet"),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--risk-dir", default=None)
    args = ap.parse_args()

    cases = list(CASE_RULES)
    results = [analyze_case(c) for c in cases]
    gains = [
        r["horizons"]["90d"]["auc_gain_dynamic_minus_distance"]
        for r in results
        if r.get("status") == "OK" and r["horizons"]["90d"]["auc_gain_dynamic_minus_distance"] is not None
    ]
    positive_cases = sum(g > 0 for g in gains)
    bad_cases = sum(g <= -0.02 for g in gains)
    median_gain = float(np.median(gains)) if gains else None
    gates = {
        "cases_with_positive_90d_auc_gain_ge_4": positive_cases >= 4,
        "median_90d_auc_gain_ge_0_02": median_gain is not None and median_gain >= 0.02,
        "cases_with_auc_gain_le_minus_0_02_eq_0": bad_cases == 0,
    }
    passed = all(gates.values())
    out = {
        "schema_version": "pineland.historical_nonlocal_reproduction_results.v1",
        "status": "HISTORICAL_OBSERVABLE_IMPLICATION_SUPPORTED_ACROSS_CASES" if passed else "HISTORICAL_OBSERVABLE_IMPLICATION_NOT_TRANSPORTED",
        "latent_state_estimation": False,
        "historical_parameter_fitting": False,
        "cases": results,
        "cross_case": {
            "n_scored_cases": len(gains),
            "cases_with_positive_90d_auc_gain": positive_cases,
            "cases_with_auc_gain_le_minus_0_02": bad_cases,
            "median_90d_auc_gain": median_gain,
            "gates": gates,
        },
        "guard": "Observable event-process confrontation only; does not estimate M_star or historical recruitment hazard.",
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "cross_case": out["cross_case"]}, indent=2))


if __name__ == "__main__":
    main()
