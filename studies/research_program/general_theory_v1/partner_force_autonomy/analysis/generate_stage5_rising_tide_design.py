#!/usr/bin/env python3
"""Generate the prospective coordinated-development follow-up experiment.

This design is explicitly post-Stage-4.  It was motivated by the completed
Stage-4 finding that narrow development can improve a targeted subsystem while
whole-system autonomy remains constrained elsewhere.  No Stage-5 outcomes are
used to choose cells, doses, hypotheses, or estimands.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"

CHANNELS = ("forcegen", "logistics", "command")
HORIZONS = [7.0, 30.0, 90.0, 180.0, 360.0]
SEEDS = 16
BASE_RATE_PER_30D = 0.08
INTENSITIES = (0.50, 1.00)

# Stage-3 heavy-profile mean daily donor-cost anchors.  These are used only to
# report the nominal cost implied by a chosen developmental dose.  They do not
# alter the developmental production response.
DAILY_COST_ANCHOR = {
    "forcegen": 1650.0,
    "logistics": 12284.0,
    "command": 2550.0,
}

STRUCTURES = {
    "forcegen_constrained": (0.15, 1.40, 1.40),
    "logistics_constrained": (1.40, 0.25, 1.40),
    "command_constrained": (1.40, 1.40, 0.30),
    "near_tie_low": (0.55, 0.55, 0.55),
}


def base_cell(cell_id: str, mults: tuple[float, float, float]) -> dict:
    fg, log, cmd = mults
    return {
        "cell_id": cell_id,
        "support_profile": "none",
        "forcegen_mult": fg,
        "logistics_mult": log,
        "command_mult": cmd,
        "air_intensity": 0.0,
        "air_bonus": 0.0,
        "air_cost_per_contact": 0.0,
        "logistics_rate": 0.0,
        "logistics_capacity": 0.0,
        "logistics_cost_per_unit": 0.0,
        "command_reliability_boost": 0.0,
        "command_latency_reduction_fraction": 0.0,
        "command_floor_hours": 0.5,
        "command_cost_per_formation_day": 0.0,
        "forcegen_training_rate_boost": 0.0,
        "forcegen_cost_per_incremental_trainee": 0.0,
        "development_forcegen_rate_per_30d": 0.0,
        "development_logistics_rate_per_30d": 0.0,
        "development_command_rate_per_30d": 0.0,
        "development_cost_per_day": 0.0,
    }


def channel_sets() -> list[tuple[str, ...]]:
    out: list[tuple[str, ...]] = []
    for k in (1, 2, 3):
        out.extend(combinations(CHANNELS, k))
    return out


def apply_development(
    cell: dict,
    channels: tuple[str, ...],
    intensity: float,
    dose_regime: str,
) -> None:
    k = len(channels)
    if k < 1:
        raise ValueError("development arm must contain at least one channel")
    if dose_regime == "single_reference":
        if k != 1:
            raise ValueError("single_reference is only valid for one-channel arms")
        normalized_dose_each = intensity
    elif dose_regime == "equal_total_effort":
        normalized_dose_each = intensity / k
    elif dose_regime == "equal_channel_dose":
        normalized_dose_each = intensity
    else:
        raise ValueError(dose_regime)

    total_cost = 0.0
    for channel in channels:
        cell[f"development_{channel}_rate_per_30d"] = (
            BASE_RATE_PER_30D * normalized_dose_each
        )
        total_cost += DAILY_COST_ANCHOR[channel] * normalized_dose_each
    label = "+".join(channels)
    cell["support_profile"] = f"stage5_development_{label}_{dose_regime}"
    cell["development_cost_per_day"] = total_cost
    cell["factor_channels"] = label
    cell["factor_channel_count"] = k
    cell["factor_dose_regime"] = dose_regime
    cell["factor_intensity"] = intensity
    cell["factor_normalized_total_effort"] = normalized_dose_each * k
    cell["factor_nominal_development_cost_per_day"] = total_cost


def build_contract() -> dict:
    cells: list[dict] = []
    n = 0
    for structure, mults in STRUCTURES.items():
        n += 1
        control = base_cell(f"rising_{n:03d}", mults)
        control.update(
            {
                "factor_starting_structure": structure,
                "factor_channels": "none",
                "factor_channel_count": 0,
                "factor_dose_regime": "control",
                "factor_intensity": 0.0,
                "factor_normalized_total_effort": 0.0,
                "factor_nominal_development_cost_per_day": 0.0,
            }
        )
        cells.append(control)

        for intensity in INTENSITIES:
            for channels in channel_sets():
                regimes = (
                    ("single_reference",)
                    if len(channels) == 1
                    else ("equal_total_effort", "equal_channel_dose")
                )
                for regime in regimes:
                    n += 1
                    cell = base_cell(f"rising_{n:03d}", mults)
                    apply_development(cell, channels, intensity, regime)
                    cell["factor_starting_structure"] = structure
                    cells.append(cell)

    assert len(cells) == 92
    return {
        # Reuse the frozen Stage-4 contract schema because the execution binary
        # already supports simultaneous developmental rates in all channels.
        "schema_version": "pineland.partner_force_stage4_contract.v1",
        "program_stage": "stage5_post_stage4_followup",
        "status": "PROSPECTIVE_DESIGN_PENDING_CRYPTOGRAPHIC_FREEZE",
        "historical_outcomes_used": False,
        "stage4_outcomes_used_for_motivation": True,
        "stage5_outcomes_used": False,
        "experiment_id": "partner_force_stage5_rising_tide_v1",
        "name": "Stage 5: Coordinated Indigenous Development",
        "description": (
            "Tests whether simultaneous indigenous development across complementary "
            "military services can lift whole-system autonomy, whether gains are "
            "superadditive at equal per-channel dose, and whether broader development "
            "improves allocation efficiency when total normalized effort is fixed."
        ),
        "design_disclosure": (
            "Designed after Stage-4 results were known. Stage-4 motivated the questions "
            "about headroom, complementarity, and coordinated development. All Stage-5 "
            "cells, hypotheses, estimands, and analysis rules are frozen before any "
            "Stage-5 production outcome is observed."
        ),
        "seed_namespace": "partner-force-stage5-rising-tide-crn-v1",
        "default_seed_count": SEEDS,
        "seed_base": 2026300000,
        "horizons_days": HORIZONS,
        "cells_count": len(cells),
        "hypotheses": {
            "H_D1": (
                "At equal per-channel dose, multi-channel indigenous development "
                "produces positive complementarity interactions in terminal retained "
                "whole-system autonomy when multiple services are jointly constraining."
            ),
            "H_D2": (
                "At fixed total normalized development effort, allocating development "
                "across multiple near-binding services can outperform concentrating the "
                "same effort in one service when initial constraint headroom is small."
            ),
            "H_D3": (
                "The benefit of broader development is larger in near-tie systems than "
                "in systems with one dominant bottleneck and large headroom to the next constraint."
            ),
            "H_D4": (
                "Broader indigenous development reduces or delays bottleneck migration "
                "and increases the fraction of capability retained after development stops."
            ),
        },
        "primary_estimands": [
            "retained_q_indigenous_support_off_h360_minus_control",
            "retained_composite_capability_support_off_h360_minus_control",
            "equal_channel_factorial_interaction_q_h360",
            "equal_total_effort_breadth_premium_q_h360",
            "bottleneck_migration_or_persistence_through_h360",
            "channel_specific_indigenous_coverage_h360",
        ],
        "analysis_rules": {
            "primary_branch": "SUPPORT_OFF",
            "primary_horizon_days": 360.0,
            "early_capability_horizon_days": 30.0,
            "retention_interpretation": (
                "SUPPORT_OFF at +360 days measures capability and indigenous coverage "
                "retained after the common 120-day developmental prehistory ends."
            ),
            "equal_total_effort_rule": (
                "For k active channels, each receives intensity/k normalized developmental "
                "dose so total normalized effort equals the single-channel reference."
            ),
            "equal_channel_dose_rule": (
                "Every active channel receives the same normalized dose as its corresponding "
                "single-channel arm. Pair and triple arms therefore use more total effort."
            ),
            "pairwise_factorial_interaction": "Q_AB - Q_A - Q_B + Q_control",
            "triple_factorial_interaction": (
                "Q_ABC - Q_AB - Q_AC - Q_BC + Q_A + Q_B + Q_C - Q_control"
            ),
            "equal_total_effort_breadth_premium": (
                "Q_multichannel - max(Q_single among included channels), using matched "
                "structure, seed, intensity, and SUPPORT_OFF horizon."
            ),
            "multiple_testing": (
                "Report all preregistered structure-by-intensity contrasts with bootstrap "
                "95 percent intervals. Emphasize sign consistency and effect magnitude; do "
                "not select only favorable cells."
            ),
            "common_random_numbers": (
                "All arms within a starting structure use identical seed identities. "
                "Contrasts are paired by seed."
            ),
        },
        "environment": {
            "agent_count": 1000,
            "locality_count": 72,
            "withdrawal_time_days": 120.0,
            "observation_start_days": 60.0,
            "development_cadence_days": 7.0,
        },
        "cells": cells,
    }


def main() -> None:
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    out = CONTRACTS / "stage5_rising_tide_v1.json"
    payload = build_contract()
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({payload['cells_count']} cells, {SEEDS} seeds, {payload['cells_count'] * SEEDS} worlds)")


if __name__ == "__main__":
    main()
