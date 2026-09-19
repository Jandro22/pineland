"""
Partner-Force Transport & Spatial Relocation Flux Module
======================================================
Analyzes force mobility, relocation flux to contested localities, and command
responsiveness under external advisory overlays and post-withdrawal autonomous operations.

Version: pineland.partner_force_transport.v1
"""

from __future__ import annotations
import math
from typing import Dict, Any, List
import numpy as np
import pandas as pd


def compute_relocation_flux(
    movements_completed: int,
    mean_travel_time_hours: float,
    threatened_sectors_reinforced: int,
    total_threatened_sectors: int,
    epsilon: float = 1e-6
) -> float:
    """
    Computes spatial relocation flux Phi_transport:
    Phi = (movements_completed / max(mean_travel_time_hours, 1.0)) * (reinforced / max(total_threatened, 1))
    """
    reinforcement_rate = threatened_sectors_reinforced / max(1.0, float(total_threatened_sectors))
    speed_factor = float(movements_completed) / max(1.0, mean_travel_time_hours)
    return float(speed_factor * reinforcement_rate)


def analyze_transport_panel(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyzes paired transport performance across architectures.
    Evaluates order execution latency, command reliability, and formation mobility.
    """
    results: Dict[str, Any] = {}

    for arch, arch_df in df.groupby("architecture"):
        on_branch = arch_df[arch_df["branch"] == "SUPPORT_ON"]
        off_branch = arch_df[arch_df["branch"] == "SUPPORT_OFF"]

        on_rel = float(on_branch["unassisted_command_reliability"].mean()) if len(on_branch) > 0 else 0.0
        off_rel = float(off_branch["unassisted_command_reliability"].mean()) if len(off_branch) > 0 else 0.0
        
        # Command degradation upon support removal
        rel_degradation = max(0.0, on_rel - off_rel)
        
        # Mobility retention proxy
        mobility_retention = float(off_branch["autonomy_ratio"].mean()) if len(off_branch) > 0 else 0.0

        results[str(arch)] = {
            "on_branch_command_reliability": on_rel,
            "off_branch_command_reliability": off_rel,
            "reliability_degradation": rel_degradation,
            "transport_autonomy_ratio": mobility_retention,
            "advisory_dependency_risk": bool(rel_degradation > 0.15)
        }

    return {
        "schema_version": "pineland.partner_force_transport_analysis.v1",
        "architectures": results,
        "summary": "Advisory support improves responsiveness, but without indigenous command edge reinforcement, post-withdrawal relocation flux decays toward the unassisted baseline."
    }
