"""Candidate indigenous autonomy coordinates and prospective model comparisons.

All coordinates use pre-withdrawal partner-owned state/flows only.  External
support quantities are intentionally excluded from the autonomy aggregates and
remain separate dependence covariates.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence
import math
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def _bounded_coverage(stock_plus_flow: np.ndarray, burden: np.ndarray, epsilon: float = 1e-9) -> np.ndarray:
    raw = stock_plus_flow / np.maximum(burden, epsilon)
    raw = np.maximum(raw, 0.0)
    return raw / (1.0 + raw)


def add_candidate_regenerative_coordinates(paired: pd.DataFrame) -> pd.DataFrame:
    out = paired.copy()
    manpower_cover = out["pre_trained_reserve"].to_numpy(float) + out["window_indigenous_graduates"].to_numpy(float)
    manpower_burden = out["window_military_losses"].to_numpy(float)
    out["omega_manpower"] = _bounded_coverage(manpower_cover, manpower_burden)

    logistics_cover = out["pre_supply_stock"].to_numpy(float) + out["window_indigenous_logistics_produced"].to_numpy(float)
    logistics_burden = out["window_indigenous_logistics_consumed"].to_numpy(float)
    out["omega_logistics"] = _bounded_coverage(logistics_cover, logistics_burden)

    rel = np.clip(out["pre_command_reliability"].to_numpy(float), 0.0, 1.0)
    latency = np.maximum(out["pre_command_latency_hours"].to_numpy(float), 0.0)
    out["omega_command"] = rel * np.exp(-latency / 24.0)

    coords = out[["omega_manpower", "omega_logistics", "omega_command"]].to_numpy(float)
    out["omega_min"] = np.min(coords, axis=1)
    out["omega_mean"] = np.mean(coords, axis=1)
    out["omega_geo"] = np.exp(np.mean(np.log(np.clip(coords, 1e-6, 1.0)), axis=1))
    out["regime"] = classify_scenario_regime(out)
    return out


def classify_scenario_regime(df: pd.DataFrame, tolerance: float = 0.05) -> pd.Series:
    """Classify scenario-space regimes for partner-force worlds.

    Regimes:
    - "Quiet": Contacts == 0 or military_losses == 0.
    - "Manpower-Constrained": omega_manpower is the bottleneck channel.
    - "Logistics-Constrained": omega_logistics is the bottleneck channel.
    - "Command-Constrained": omega_command is the bottleneck channel.
    - "Mixed-Binding": Multiple coordinates are tied or within tolerance of the minimum.
    """
    if "omega_manpower" not in df.columns or "omega_logistics" not in df.columns or "omega_command" not in df.columns:
        coords_df = add_candidate_regenerative_coordinates(df)
    else:
        coords_df = df

    # Check for quiet / non-binding regime
    if "window_military_losses" in coords_df.columns:
        losses = coords_df["window_military_losses"].to_numpy(float)
    elif "post_military_losses" in coords_df.columns:
        losses = coords_df["post_military_losses"].to_numpy(float)
    elif "off_post_military_losses" in coords_df.columns:
        losses = coords_df["off_post_military_losses"].to_numpy(float)
    else:
        losses = np.ones(len(coords_df))

    if "contacts" in coords_df.columns:
        contacts = coords_df["contacts"].to_numpy(float)
    elif "pre_recent_actions" in coords_df.columns:
        contacts = coords_df["pre_recent_actions"].to_numpy(float)
    else:
        contacts = np.ones(len(coords_df))

    is_quiet = (contacts <= 0) | (losses <= 0)

    om = coords_df["omega_manpower"].to_numpy(float)
    ol = coords_df["omega_logistics"].to_numpy(float)
    oc = coords_df["omega_command"].to_numpy(float)
    coords = np.column_stack([om, ol, oc])
    min_val = np.min(coords, axis=1)

    regimes = []
    for i in range(len(coords_df)):
        if is_quiet[i]:
            regimes.append("Quiet")
            continue

        m_diff = om[i] - min_val[i]
        l_diff = ol[i] - min_val[i]
        c_diff = oc[i] - min_val[i]

        near_min_count = sum(d <= tolerance for d in [m_diff, l_diff, c_diff])
        if near_min_count > 1:
            regimes.append("Mixed-Binding")
        elif m_diff <= tolerance:
            regimes.append("Manpower-Constrained")
        elif l_diff <= tolerance:
            regimes.append("Logistics-Constrained")
        elif c_diff <= tolerance:
            regimes.append("Command-Constrained")
        else:
            regimes.append("Mixed-Binding")

    return pd.Series(regimes, index=df.index, name="regime")



def _group_splits(groups: Sequence[Any], max_splits: int = 5):
    unique = np.unique(np.asarray(groups))
    if len(unique) < 2:
        return None
    return GroupKFold(n_splits=min(max_splits, len(unique)))


def _cv_isotonic_rmse(x: np.ndarray, y: np.ndarray, groups: np.ndarray) -> float:
    cv = _group_splits(groups)
    if cv is None:
        return float("nan")
    pred = np.full(len(y), np.nan)
    for train, test in cv.split(x.reshape(-1, 1), y, groups):
        xt = x[train]
        if len(np.unique(xt)) < 2:
            pred[test] = float(np.mean(y[train]))
        else:
            model = IsotonicRegression(out_of_bounds="clip").fit(xt, y[train])
            pred[test] = model.predict(x[test])
    return float(np.sqrt(mean_squared_error(y, pred)))


def _cv_ridge(X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> Dict[str, float]:
    cv = _group_splits(groups)
    if cv is None:
        return {"rmse": float("nan"), "r2": float("nan")}
    pred = np.full(len(y), np.nan)
    for train, test in cv.split(X, y, groups):
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        model.fit(X[train], y[train])
        pred[test] = model.predict(X[test])
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "r2": float(r2_score(y, pred)),
    }


def evaluate_bottleneck_competitors(paired: pd.DataFrame) -> Dict[str, Any]:
    df = add_candidate_regenerative_coordinates(paired)
    y = df["autonomy_ratio"].to_numpy(float)
    groups = df["seed"].to_numpy()
    metrics: Dict[str, Any] = {}
    scalar_candidates = ["omega_min", "omega_mean", "omega_geo"]
    if "formal_q_indigenous" in df.columns:
        scalar_candidates.insert(0, "formal_q_indigenous")
    for col in scalar_candidates:
        x_all = df[col].to_numpy(float)
        if col == "formal_q_indigenous":
            valid = np.isfinite(x_all) & (x_all >= 0.0)
        else:
            valid = np.isfinite(x_all)
        x = x_all[valid]
        yy = y[valid]
        gg = groups[valid]
        if len(x) == 0:
            metrics[col] = {
                "grouped_cv_isotonic_rmse": float("nan"),
                "spearman_rho_descriptive": 0.0,
                "n_obs": 0,
                "excluded_no_active_demand": int((~valid).sum()),
            }
            continue
        rho = (
            spearmanr(x, yy).statistic
            if len(np.unique(x)) > 1 and len(np.unique(yy)) > 1
            else 0.0
        )
        if np.isnan(rho):
            rho = 0.0
        metrics[col] = {
            "grouped_cv_isotonic_rmse": _cv_isotonic_rmse(x, yy, gg),
            "spearman_rho_descriptive": float(rho),
            "n_obs": int(len(x)),
            "excluded_no_active_demand": int((~valid).sum()) if col == "formal_q_indigenous" else 0,
        }
    additive = _cv_ridge(
        df[["omega_manpower", "omega_logistics", "omega_command"]].to_numpy(float),
        y,
        groups,
    )
    metrics["regularized_additive"] = additive
    ranked = sorted(
        metrics,
        key=lambda k: metrics[k].get("grouped_cv_isotonic_rmse", metrics[k].get("rmse", float("inf"))),
    )
    return {
        "status": "DISCOVERY_COMPARISON_ONLY",
        "primary_formal_coordinate": "formal_q_indigenous" if "formal_q_indigenous" in df.columns else None,
        "competitor_ranking_by_grouped_cv_rmse": ranked,
        "metrics": metrics,
        "warning": "Do not freeze a winner until discovery data are complete; transport claims require later zero-refit holdouts.",
    }


STOCK_COLUMNS = [
    "pre_military_personnel", "pre_trained_reserve", "pre_recruit_pipeline",
    "pre_readiness", "pre_experience", "pre_supply_stock", "pre_supply_capacity",
    "pre_command_reliability", "pre_command_latency_hours",
]
FLOW_COLUMNS = [
    "window_indigenous_recruits", "window_indigenous_graduates", "window_military_losses",
    "window_indigenous_logistics_produced", "window_indigenous_logistics_delivered",
    "window_indigenous_logistics_consumed",
]


def evaluate_regeneration_vs_stocks(paired: pd.DataFrame, horizons=(90, 180)) -> Dict[str, Any]:
    df = paired[paired["horizon_days"].isin(horizons)].copy()
    if df.empty:
        raise ValueError(f"no rows at requested long horizons {horizons}")
    y = df["autonomy_ratio"].to_numpy(float)
    groups = df["seed"].to_numpy()
    stock = _cv_ridge(df[STOCK_COLUMNS].to_numpy(float), y, groups)
    flow = _cv_ridge(df[FLOW_COLUMNS].to_numpy(float), y, groups)
    combined = _cv_ridge(df[STOCK_COLUMNS + FLOW_COLUMNS].to_numpy(float), y, groups)
    return {
        "status": "DISCOVERY_COMPARISON_ONLY",
        "horizons": list(horizons),
        "stock_only_grouped_cv": stock,
        "flow_only_grouped_cv": flow,
        "stock_plus_flow_grouped_cv": combined,
    }


def evaluate_supported_performance_vs_indigenous_state(paired: pd.DataFrame) -> Dict[str, Any]:
    y = paired["autonomy_ratio"].to_numpy(float)
    groups = paired["seed"].to_numpy()
    supported = _cv_ridge(paired[["pre_supported_capability"]].to_numpy(float), y, groups)
    indigenous = _cv_ridge(paired[STOCK_COLUMNS + FLOW_COLUMNS].to_numpy(float), y, groups)
    return {
        "status": "DISCOVERY_COMPARISON_ONLY",
        "supported_performance_only_grouped_cv": supported,
        "indigenous_state_flow_grouped_cv": indigenous,
    }
