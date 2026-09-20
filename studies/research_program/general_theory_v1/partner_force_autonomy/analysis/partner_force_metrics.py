"""Paired counterfactual metrics for Partner-Force Autonomy Stage 3.

Raw branch rows never contain R_h or Delta_h.  This module validates that each
pair has exactly one SUPPORT_ON and one SUPPORT_OFF observation with identical
pre-withdrawal metadata, then derives the counterfactual quantities.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable
import math
import numpy as np
import pandas as pd


RAW_SCHEMA_VERSION = "pineland.partner_force_autonomy_raw_branch.v2"
RAW_SCHEMA_VERSION_V3 = "pineland.partner_force_autonomy_raw_branch.v3"
ALLOWED_SCHEMA_VERSIONS = {RAW_SCHEMA_VERSION, RAW_SCHEMA_VERSION_V3}

PAIR_INVARIANT_COLUMNS = [
    "experiment_id", "design_version", "git_commit", "world_id", "cell_id",
    "support_profile", "seed", "withdrawal_time_days", "horizon_days",
    "indigenous_forcegen_multiplier", "indigenous_logistics_multiplier",
    "indigenous_command_multiplier", "pre_insurgent_personnel",
    "pre_insurgent_active_formations", "pre_insurgent_territorial_control",
    "pre_recent_actions", "pre_contested_localities",
    "pre_supported_capability", "pre_government_control", "pre_military_personnel",
    "pre_trained_reserve", "pre_recruit_pipeline", "pre_readiness", "pre_experience",
    "pre_supply_stock", "pre_supply_capacity", "pre_command_reliability",
    "pre_command_latency_hours", "window_indigenous_recruits",
    "window_indigenous_graduates", "window_military_losses",
    "window_indigenous_logistics_produced", "window_indigenous_logistics_delivered",
    "window_indigenous_logistics_consumed", "window_external_air_intensity",
    "window_external_logistics_offered", "window_external_logistics_delivered",
    "window_external_logistics_rejected", "window_external_logistics_lost",
    "window_external_command_events", "window_command_latency_hours_saved",
    "window_external_forcegen_graduates", "window_donor_cost_air",
    "window_donor_cost_logistics", "window_donor_cost_command",
    "window_donor_cost_forcegen", "window_donor_cost", "support_air_intensity",
    "support_air_bonus", "support_logistics_rate", "support_command_reliability_boost",
    "support_command_latency_reduction_fraction", "support_forcegen_training_rate_boost",
]

V3_PAIR_INVARIANT_COLUMNS = [
    "dependence_logistics", "dependence_forcegen", "dependence_command", "dependence_air",
    "manpower_burden", "logistics_burden", "omega_flow",
]

BOUNDED_ZERO_ONE_COLUMNS = [
    "pre_insurgent_territorial_control", "pre_supported_capability", "pre_government_control",
    "pre_readiness", "pre_experience", "pre_command_reliability",
    "support_air_intensity", "support_command_reliability_boost",
    "support_command_latency_reduction_fraction", "c_government_control",
    "c_military_personnel_retention", "c_operational_formation_survival",
    "c_geographic_coverage_retention", "composite_capability",
]

NON_NEGATIVE_COLUMNS = [
    "indigenous_forcegen_multiplier", "indigenous_logistics_multiplier", "indigenous_command_multiplier",
    "pre_insurgent_personnel", "pre_insurgent_active_formations", "pre_recent_actions", "pre_contested_localities",
    "pre_military_personnel", "pre_trained_reserve", "pre_recruit_pipeline", "pre_supply_stock",
    "pre_supply_capacity", "pre_command_latency_hours", "window_indigenous_recruits",
    "window_indigenous_graduates", "window_military_losses", "window_indigenous_logistics_produced",
    "window_indigenous_logistics_delivered", "window_indigenous_logistics_consumed",
    "window_external_air_intensity", "window_external_logistics_offered", "window_external_logistics_delivered",
    "window_external_logistics_rejected", "window_external_logistics_lost", "window_external_command_events",
    "window_command_latency_hours_saved", "window_external_forcegen_graduates", "window_donor_cost_air",
    "window_donor_cost_logistics", "window_donor_cost_command", "window_donor_cost_forcegen",
    "window_donor_cost", "support_air_bonus", "support_logistics_rate", "support_forcegen_training_rate_boost",
    "post_indigenous_recruits", "post_indigenous_graduates", "post_military_losses",
    "post_indigenous_logistics_produced", "post_indigenous_logistics_consumed",
    "post_donor_cost_air", "post_donor_cost_logistics", "post_donor_cost_command",
    "post_donor_cost_forcegen", "post_donor_cost",
]


def _require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"raw panel missing required columns: {missing}")


def validate_raw_branch_panel(df: pd.DataFrame) -> None:
    is_v3 = "dependence_logistics" in df.columns
    active_invariants = list(PAIR_INVARIANT_COLUMNS)
    if is_v3:
        active_invariants.extend(V3_PAIR_INVARIANT_COLUMNS)

    required = [
        "schema_version", "pair_id", "run_id", "branch", "composite_capability",
        "c_government_control", "c_military_personnel_retention",
        "c_operational_formation_survival", "c_geographic_coverage_retention",
        "post_indigenous_recruits", "post_indigenous_graduates", "post_military_losses",
        "post_indigenous_logistics_produced", "post_indigenous_logistics_consumed",
        "post_donor_cost_air", "post_donor_cost_logistics", "post_donor_cost_command",
        "post_donor_cost_forcegen", "post_donor_cost",
        *active_invariants,
    ]
    if is_v3:
        required.extend(["t_c_deficit_90", "t_readiness_collapse", "t_supply_exhaustion", "t_first_formation_loss"])

    _require_columns(df, required)
    versions = set(df["schema_version"].astype(str))
    if not versions.issubset(ALLOWED_SCHEMA_VERSIONS):
        raise ValueError(f"expected only schemas {ALLOWED_SCHEMA_VERSIONS}, found {sorted(versions)}")
    if df["run_id"].duplicated().any():
        dup = df.loc[df["run_id"].duplicated(), "run_id"].iloc[0]
        raise ValueError(f"duplicate run_id: {dup}")

    # Check finite and ranges
    bounded_cols = list(BOUNDED_ZERO_ONE_COLUMNS)
    if is_v3:
        bounded_cols.extend(["dependence_logistics", "dependence_forcegen", "dependence_command", "dependence_air"])
    for col in bounded_cols:
        vals = df[col].to_numpy(float)
        if not np.all(np.isfinite(vals)):
            raise ValueError(f"column {col} contains non-finite values (NaN or Inf)")
        if np.any((vals < -1e-6) | (vals > 1.0 + 1e-6)):
            raise ValueError(f"column {col} has values outside [0, 1]: min={vals.min()}, max={vals.max()}")

    non_neg_cols = list(NON_NEGATIVE_COLUMNS)
    if is_v3:
        non_neg_cols.extend(["manpower_burden", "logistics_burden", "omega_flow"])
    for col in non_neg_cols:
        vals = df[col].to_numpy(float)
        if not np.all(np.isfinite(vals)):
            raise ValueError(f"column {col} contains non-finite values (NaN or Inf)")
        if np.any(vals < -1e-6):
            raise ValueError(f"column {col} has negative values: min={vals.min()}")

    for pair_id, g in df.groupby("pair_id", sort=False):
        if len(g) != 2:
            raise ValueError(f"pair {pair_id} has {len(g)} rows; expected exactly 2")
        branches = set(g["branch"].astype(str))
        if branches != {"SUPPORT_ON", "SUPPORT_OFF"}:
            raise ValueError(f"pair {pair_id} branches are {sorted(branches)}")
        on = g[g["branch"] == "SUPPORT_ON"].iloc[0]
        off = g[g["branch"] == "SUPPORT_OFF"].iloc[0]
        for col in active_invariants:
            a, b = on[col], off[col]
            if pd.isna(a) and pd.isna(b):
                continue
            if isinstance(a, (float, np.floating)) or isinstance(b, (float, np.floating)):
                if not math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError(f"pair {pair_id} invariant mismatch in {col}: {a} != {b}")
            elif a != b:
                raise ValueError(f"pair {pair_id} invariant mismatch in {col}: {a!r} != {b!r}")


def pair_counterfactual_rows(df: pd.DataFrame, epsilon: float = 1e-9) -> pd.DataFrame:
    validate_raw_branch_panel(df)
    is_v3 = "dependence_logistics" in df.columns
    active_invariants = list(PAIR_INVARIANT_COLUMNS)
    if is_v3:
        active_invariants.extend(V3_PAIR_INVARIANT_COLUMNS)

    rows = []
    for pair_id, g in df.groupby("pair_id", sort=False):
        on = g[g["branch"] == "SUPPORT_ON"].iloc[0]
        off = g[g["branch"] == "SUPPORT_OFF"].iloc[0]
        c_on = float(on["composite_capability"])
        c_off = float(off["composite_capability"])
        row = {col: on[col] for col in active_invariants}
        row.update({
            "pair_id": pair_id,
            "c_on": c_on,
            "c_off": c_off,
            "autonomy_ratio": c_off / max(c_on, epsilon),
            "performance_delta": c_on - c_off,
            "on_government_control": float(on["c_government_control"]),
            "off_government_control": float(off["c_government_control"]),
            "on_personnel_retention": float(on["c_military_personnel_retention"]),
            "off_personnel_retention": float(off["c_military_personnel_retention"]),
            "on_formation_survival": float(on["c_operational_formation_survival"]),
            "off_formation_survival": float(off["c_operational_formation_survival"]),
            "on_coverage_retention": float(on["c_geographic_coverage_retention"]),
            "off_coverage_retention": float(off["c_geographic_coverage_retention"]),
            "on_post_indigenous_recruits": float(on["post_indigenous_recruits"]),
            "off_post_indigenous_recruits": float(off["post_indigenous_recruits"]),
            "on_post_indigenous_graduates": float(on["post_indigenous_graduates"]),
            "off_post_indigenous_graduates": float(off["post_indigenous_graduates"]),
            "on_post_military_losses": float(on["post_military_losses"]),
            "off_post_military_losses": float(off["post_military_losses"]),
            "on_post_indigenous_logistics_produced": float(on["post_indigenous_logistics_produced"]),
            "off_post_indigenous_logistics_produced": float(off["post_indigenous_logistics_produced"]),
            "on_post_indigenous_logistics_consumed": float(on["post_indigenous_logistics_consumed"]),
            "off_post_indigenous_logistics_consumed": float(off["post_indigenous_logistics_consumed"]),
            "on_post_donor_cost_air": float(on["post_donor_cost_air"]),
            "off_post_donor_cost_air": float(off["post_donor_cost_air"]),
            "on_post_donor_cost_logistics": float(on["post_donor_cost_logistics"]),
            "off_post_donor_cost_logistics": float(off["post_donor_cost_logistics"]),
            "on_post_donor_cost_command": float(on["post_donor_cost_command"]),
            "off_post_donor_cost_command": float(off["post_donor_cost_command"]),
            "on_post_donor_cost_forcegen": float(on["post_donor_cost_forcegen"]),
            "off_post_donor_cost_forcegen": float(off["post_donor_cost_forcegen"]),
            "on_post_donor_cost": float(on["post_donor_cost"]),
            "off_post_donor_cost": float(off["post_donor_cost"]),
        })
        if is_v3:
            row.update({
                "off_t_c_deficit_90": float(off["t_c_deficit_90"]),
                "off_t_readiness_collapse": float(off["t_readiness_collapse"]),
                "off_t_supply_exhaustion": float(off["t_supply_exhaustion"]),
                "off_t_first_formation_loss": float(off["t_first_formation_loss"]),
            })
        rows.append(row)
    paired = pd.DataFrame(rows)
    if paired.empty:
        raise ValueError("raw panel contains no counterfactual pairs")
    return paired


def analyze_paired_panel(paired: pd.DataFrame) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "total_pairs": int(len(paired)),
        "unique_worlds": int(paired["world_id"].nunique()),
        "seed_count": int(paired["seed"].nunique()),
        "by_support_profile": {},
    }
    for profile, p in paired.groupby("support_profile"):
        result["by_support_profile"][str(profile)] = {}
        for h, hdf in p.groupby("horizon_days"):
            r = hdf["autonomy_ratio"].to_numpy(float)
            d = hdf["performance_delta"].to_numpy(float)
            result["by_support_profile"][str(profile)][str(int(h))] = {
                "n": int(len(hdf)),
                "autonomy_ratio_mean": float(np.mean(r)),
                "autonomy_ratio_median": float(np.median(r)),
                "autonomy_ratio_sd": float(np.std(r, ddof=1)) if len(r) > 1 else 0.0,
                "performance_delta_mean": float(np.mean(d)),
                "c_on_mean": float(hdf["c_on"].mean()),
                "c_off_mean": float(hdf["c_off"].mean()),
            }
    return result
