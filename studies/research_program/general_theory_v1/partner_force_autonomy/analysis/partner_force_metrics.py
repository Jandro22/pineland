"""
Partner-Force Autonomy Metrics Library
=====================================
Calculates paired counterfactual metrics, autonomy retention ratios, decay rates,
substitution indices, and donor cost efficiencies.

Version: pineland.partner_force_metrics.v1
"""

from __future__ import annotations
import math
from typing import Dict, Any, List
import numpy as np
import pandas as pd


def compute_autonomy_ratio(c_off: float, c_on: float, epsilon: float = 1e-6) -> float:
    """
    Computes counterfactual capability retention ratio:
    R_h = C_OFF(T+h) / max(C_ON(T+h), epsilon)
    """
    return float(c_off / max(c_on, epsilon))


def compute_performance_delta(c_on: float, c_off: float) -> float:
    """
    Computes performance loss induced by external support removal:
    Delta_h = C_ON(T+h) - C_OFF(T+h)
    """
    return float(c_on - c_off)


def compute_exponential_decay_rate(r_h: float, horizon_days: float) -> float:
    """
    Estimates the exponential performance decay constant:
    lambda = - (1 / h) * ln(R_h)
    Clips R_h to (1e-6, 1.0] to prevent math domain errors.
    """
    if horizon_days <= 0:
        return 0.0
    r_clipped = max(1e-6, min(1.0, r_h))
    return float(-math.log(r_clipped) / horizon_days)


def compute_substitution_index(
    organic_component: float,
    external_component: float,
    epsilon: float = 1e-6
) -> float:
    """
    Computes the fraction of total delivered capability provided by external assistance:
    sigma = external / (organic + external + epsilon)
    Bounded in [0.0, 1.0].
    """
    total = organic_component + external_component
    if total <= epsilon:
        return 0.0
    return float(min(1.0, max(0.0, external_component / (total + epsilon))))


def compute_donor_cost_efficiency(
    autonomy_ratio: float,
    discounted_donor_cost: float,
    cost_unit: float = 100000.0,
    epsilon: float = 1e-6
) -> float:
    """
    Computes retained autonomy points per unit of discounted donor expenditure:
    E_h = R_h / (discounted_cost / cost_unit)
    """
    norm_cost = max(epsilon, discounted_donor_cost / cost_unit)
    return float(autonomy_ratio / norm_cost)


def analyze_paired_panel(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyzes a paired counterfactual dataset containing SUPPORT_ON and SUPPORT_OFF branches.
    Returns aggregated metrics by architecture and measurement horizon.
    """
    results: Dict[str, Any] = {
        "architectures": {},
        "horizons": sorted([int(x) for x in df["horizon_days"].unique()]),
        "total_pairs": int(df["pair_id"].nunique())
    }

    # If dataset has both branches in rows, group by pair_id or architecture & horizon
    for arch, arch_df in df.groupby("architecture"):
        arch_results: Dict[str, Any] = {"by_horizon": {}}
        for h, h_df in arch_df.groupby("horizon_days"):
            h_int = int(h)
            
            # Autonomy ratios across pairs
            r_vals = h_df["autonomy_ratio"].to_numpy(dtype=float)
            delta_vals = h_df["performance_delta"].to_numpy(dtype=float)
            decay_vals = h_df["decay_rate"].to_numpy(dtype=float)
            cost_vals = h_df["discounted_cost"].to_numpy(dtype=float)

            arch_results["by_horizon"][str(h_int)] = {
                "autonomy_ratio_mean": float(np.mean(r_vals)),
                "autonomy_ratio_median": float(np.median(r_vals)),
                "autonomy_ratio_std": float(np.std(r_vals)),
                "performance_delta_mean": float(np.mean(delta_vals)),
                "decay_rate_mean": float(np.mean(decay_vals)),
                "mean_discounted_cost": float(np.mean(cost_vals)),
                "efficiency_per_100k": float(np.mean(r_vals) / max(1e-6, np.mean(cost_vals) / 100000.0)),
                "n_samples": int(len(r_vals))
            }
        results["architectures"][str(arch)] = arch_results

    return results
