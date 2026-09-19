"""
Partner-Force Regenerative Coordinates Module
============================================
Computes state-space trajectories in (M, F, G, C) coordinates:
- Omega_M: Manpower / Force-Gen regenerative buffer
- Omega_F: Firepower organic autonomy
- Omega_G: Logistics sustainment buffer
- Omega_C: Command transmission integrity

Evaluates Bottleneck (Omega_min), Additive (Omega_mean), and Multiplicative (Omega_geo)
architectures to test hypotheses PF-H2 and PF-H3.

Version: pineland.partner_force_regenerative_coordinates.v1
"""

from __future__ import annotations
import math
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import mean_squared_error


def calculate_regenerative_coordinates(
    stock_manpower: float,
    flow_recruits_graduation: float,
    flow_personnel_losses: float,
    stock_supply: float,
    flow_supply_replenishment: float,
    flow_supply_consumption: float,
    organic_firepower: float,
    external_firepower: float,
    command_reliability: float,
    command_latency_hours: float,
    horizon_days: float,
    epsilon: float = 1e-6
) -> Dict[str, float]:
    """
    Computes audited regenerative coordinates Omega_j = tau_j / h for each subsystem.
    """
    h_hours = max(1.0, horizon_days * 24.0)

    # Manpower: buffer tau_M = (stock + flow_grad * h) / (losses * h + epsilon)
    net_manpower_support = flow_recruits_graduation * horizon_days
    net_manpower_loss = max(epsilon, flow_personnel_losses * horizon_days)
    omega_m = (stock_manpower + net_manpower_support) / net_manpower_loss

    # Logistics: buffer tau_G = (stock + flow_replenish * h) / (consumption * h + epsilon)
    net_supply_flow = flow_supply_replenishment * horizon_days
    net_supply_loss = max(epsilon, flow_supply_consumption * horizon_days)
    omega_g = (stock_supply + net_supply_flow) / net_supply_loss

    # Firepower: organic share vs total combat burden
    total_firepower = organic_firepower + external_firepower
    omega_f = organic_firepower / max(epsilon, total_firepower)

    # Command: transmission reliability penalized by latency relative to tactical reaction time
    latency_penalty = math.exp(-command_latency_hours / 24.0)
    omega_c = command_reliability * latency_penalty

    coords = [omega_m, omega_f, omega_g, omega_c]
    om_min = float(min(coords))
    om_mean = float(np.mean(coords))
    # Geometric mean with positive clipping
    om_geo = float(math.exp(np.mean([math.log(max(1e-4, x)) for x in coords])))

    return {
        "omega_manpower": float(omega_m),
        "omega_firepower": float(omega_f),
        "omega_logistics": float(omega_g),
        "omega_command": float(omega_c),
        "omega_min": om_min,
        "omega_mean": om_mean,
        "omega_geo": om_geo
    }


def evaluate_bottleneck_competitors(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Tests PF-H2: Evaluates predictive power of Omega_min vs Omega_mean vs Omega_geo
    against post-withdrawal autonomy ratio R_h.
    """
    target = df["autonomy_ratio"].to_numpy(dtype=float)
    candidates = {
        "Omega_min": df["omega_min"].to_numpy(dtype=float),
        "Omega_mean": df["omega_mean"].to_numpy(dtype=float),
        "Omega_geo": df["omega_geo"].to_numpy(dtype=float)
    }

    results: Dict[str, Any] = {}
    
    for name, x in candidates.items():
        # Monotonic fit
        iso = IsotonicRegression(out_of_bounds="clip").fit(x, target)
        pred = iso.predict(x)
        rmse = float(np.sqrt(mean_squared_error(target, pred)))
        
        # Correlations
        pr, _ = pearsonr(x, target) if len(np.unique(x)) > 1 else (0.0, 1.0)
        sr, _ = spearmanr(x, target) if len(np.unique(x)) > 1 else (0.0, 1.0)
        
        results[name] = {
            "rmse": rmse,
            "pearson_r": float(pr),
            "spearman_rho": float(sr)
        }

    # Rank by lowest RMSE (best fit)
    ranked = sorted(results.keys(), key=lambda k: results[k]["rmse"])
    
    verdict = {
        "competitor_ranking": ranked,
        "best_predictor": ranked[0],
        "bottleneck_hypothesis_supported": (ranked[0] == "Omega_min" or results["Omega_min"]["spearman_rho"] >= results["Omega_mean"]["spearman_rho"]),
        "metrics": results
    }
    return verdict


def evaluate_regeneration_vs_stocks(df: pd.DataFrame, horizons: List[int] = [90, 180]) -> Dict[str, Any]:
    """
    Tests PF-H3: Evaluates whether long-horizon autonomy retention (90d, 180d) is predicted
    more strongly by endogenous regeneration flows than by withdrawal-day stocks.
    """
    sub_df = df[df["horizon_days"].isin(horizons)]
    if len(sub_df) == 0:
        sub_df = df

    target = sub_df["autonomy_ratio"].to_numpy(dtype=float)

    # Stock group predictors
    stock_pred = sub_df[["organic_personnel_reserve", "mean_formation_readiness"]].mean(axis=1).to_numpy(dtype=float)
    # Flow group predictors
    flow_pred = sub_df[["recruit_graduation_throughput", "indigenous_supply_delivered"]].mean(axis=1).to_numpy(dtype=float)

    sr_stock, _ = spearmanr(stock_pred, target) if len(np.unique(stock_pred)) > 1 else (0.0, 1.0)
    sr_flow, _ = spearmanr(flow_pred, target) if len(np.unique(flow_pred)) > 1 else (0.0, 1.0)

    return {
        "stock_spearman_rho": float(sr_stock),
        "flow_spearman_rho": float(sr_flow),
        "regeneration_dominates_stocks": bool(sr_flow >= sr_stock),
        "horizons_evaluated": horizons
    }
