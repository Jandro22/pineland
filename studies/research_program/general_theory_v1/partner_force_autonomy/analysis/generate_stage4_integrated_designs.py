#!/usr/bin/env python3
"""Generate the preregistered Stage-4 integrated-paper experiment contracts.

This generator is deterministic and contains no fitted quantities from Stage-4
outcomes.  Stage-3 is used only for design calibration already documented in
the research-program memo (notably the channel-specific donor-cost anchors and
the need for a more severe force-generation weakness to create a clean binding
constraint).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"

HORIZONS = [7.0, 30.0, 90.0, 180.0, 360.0]
SEEDS = 12

# Stage-3 empirical mean donor expenditure per day for the corresponding heavy
# support profiles.  These are calibration constants, not Stage-4 outcomes.
DAILY_COST_ANCHOR = {
    "forcegen": 1650.0,
    "logistics": 12284.0,
    "command": 2550.0,
}


def base_cell(cell_id: str, profile: str, mults: tuple[float, float, float]) -> dict:
    fg, log, cmd = mults
    return {
        "cell_id": cell_id,
        "support_profile": profile,
        "forcegen_mult": fg,
        "logistics_mult": log,
        "command_mult": cmd,
        "air_intensity": 0.0,
        "air_bonus": 0.0,
        "air_cost_per_contact": 0.0,
        "logistics_rate": 0.0,
        "logistics_capacity": 0.0,
        "logistics_cost_per_unit": 10.0,
        "command_reliability_boost": 0.0,
        "command_latency_reduction_fraction": 0.0,
        "command_floor_hours": 0.5,
        "command_cost_per_formation_day": 240.0,
        "forcegen_training_rate_boost": 0.0,
        "forcegen_cost_per_incremental_trainee": 120.0,
        "development_forcegen_rate_per_30d": 0.0,
        "development_logistics_rate_per_30d": 0.0,
        "development_command_rate_per_30d": 0.0,
        "development_cost_per_day": 0.0,
    }


def apply_balanced_support(cell: dict, intensity: float) -> None:
    if intensity <= 0.0:
        cell["support_profile"] = "none"
        cell["logistics_cost_per_unit"] = 0.0
        cell["command_cost_per_formation_day"] = 0.0
        cell["forcegen_cost_per_incremental_trainee"] = 0.0
        return
    cell["support_profile"] = "stage4_balanced_service_support"
    cell["logistics_rate"] = 450.0 * intensity
    cell["logistics_capacity"] = 700.0 * intensity
    cell["logistics_cost_per_unit"] = 8.0
    cell["command_reliability_boost"] = min(1.0, 0.18 * intensity)
    cell["command_latency_reduction_fraction"] = min(1.0, 0.20 * intensity)
    cell["command_floor_hours"] = 1.0
    cell["command_cost_per_formation_day"] = 80.0
    cell["forcegen_training_rate_boost"] = 0.006 * intensity
    cell["forcegen_cost_per_incremental_trainee"] = 80.0


def apply_targeted_substitution(cell: dict, target: str, intensity: float) -> None:
    if target == "none" or intensity <= 0.0:
        cell["support_profile"] = "none"
        cell["logistics_cost_per_unit"] = 0.0
        cell["command_cost_per_formation_day"] = 0.0
        cell["forcegen_cost_per_incremental_trainee"] = 0.0
        return
    cell["support_profile"] = f"stage4_{target}_substitution"
    if target == "forcegen":
        cell["forcegen_training_rate_boost"] = 0.035 * intensity
        cell["forcegen_cost_per_incremental_trainee"] = 120.0
    elif target == "logistics":
        cell["logistics_rate"] = 1200.0 * intensity
        cell["logistics_capacity"] = 1600.0 * intensity
        cell["logistics_cost_per_unit"] = 10.0
    elif target == "command":
        cell["command_reliability_boost"] = min(1.0, 0.55 * intensity)
        cell["command_latency_reduction_fraction"] = min(1.0, 0.55 * intensity)
        cell["command_floor_hours"] = 0.5
        cell["command_cost_per_formation_day"] = 240.0
    elif target == "balanced":
        apply_balanced_support(cell, intensity)
    else:
        raise ValueError(target)


def apply_development(cell: dict, target: str, intensity: float) -> None:
    # Low/high production-growth doses are intentionally moderate: the high
    # dose compounds to roughly 1.37x endogenous production over the 120-day
    # common supported prehistory under the fixed weekly treatment cadence.
    rate = 0.08 * intensity
    cell[f"development_{target}_rate_per_30d"] = rate
    cell["development_cost_per_day"] = DAILY_COST_ANCHOR[target] * intensity
    cell["support_profile"] = f"stage4_{target}_development"


def contract(
    experiment_id: str,
    name: str,
    description: str,
    seed_base: int,
    cells: list[dict],
    hypotheses: dict,
    primary_estimands: list[str],
    analysis_rules: dict,
) -> dict:
    return {
        "schema_version": "pineland.partner_force_stage4_contract.v1",
        "status": "FROZEN_FOR_PRODUCTION_PENDING_CRYPTOGRAPHIC_FREEZE",
        "historical_outcomes_used": False,
        "production_outcomes_used": False,
        "engineering_calibration": {
            "seed_namespace": "2026290000-series",
            "canonical_slurm_job_id": 886011,
            "purpose": "correctness and treatment-relevance only",
            "decision": "retain the originally specified developmental rate scale unchanged; do not tune to calibration effect direction or magnitude",
            "excluded_from_production_inference": True,
        },
        "experiment_id": experiment_id,
        "name": name,
        "description": description,
        "seed_namespace": f"{experiment_id}-crn-v1",
        "default_seed_count": SEEDS,
        "seed_base": seed_base,
        "horizons_days": HORIZONS,
        "cells_count": len(cells),
        "hypotheses": hypotheses,
        "primary_estimands": primary_estimands,
        "analysis_rules": analysis_rules,
        "cells": cells,
        "environment": {
            "agent_count": 1000,
            "locality_count": 72,
            "withdrawal_time_days": 120.0,
            "observation_start_days": 60.0,
            "development_cadence_days": 7.0,
        },
    }


def phase_map() -> dict:
    structures = {
        "forcegen_constrained": [0.10, 0.15, 0.25, 0.40, 0.60],
        "logistics_constrained": [0.15, 0.25, 0.40, 0.60, 0.80],
        "command_constrained": [0.20, 0.30, 0.40, 0.55, 0.70],
        "balanced_capacity": [0.40, 0.55, 0.70, 0.85, 1.00],
    }
    intensities = [0.0, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00]
    cells: list[dict] = []
    n = 0
    for structure, levels in structures.items():
        for level_index, level in enumerate(levels, 1):
            if structure == "forcegen_constrained":
                mults = (level, 1.4, 1.4)
            elif structure == "logistics_constrained":
                mults = (1.4, level, 1.4)
            elif structure == "command_constrained":
                mults = (1.4, 1.4, level)
            else:
                mults = (level, level, level)
            for intensity in intensities:
                n += 1
                cell = base_cell(f"phase_{n:03d}", "none", mults)
                apply_balanced_support(cell, intensity)
                cell.update(
                    {
                        "factor_structure": structure,
                        "factor_capacity_level": level,
                        "factor_capacity_level_index": level_index,
                        "factor_support_intensity": intensity,
                    }
                )
                cells.append(cell)
    assert len(cells) == 140
    return contract(
        "partner_force_stage4_autonomy_phase_map_v1",
        "Stage 4A: Autonomy-Trap Phase Map",
        "Maps the sign and magnitude of continued-assistance effects across indigenous constraint severity and balanced support intensity.",
        2026200000,
        cells,
        {
            "H_A1": "Continued assistance has heterogeneous effects on terminal indigenous autonomy even when it improves near-term operational capability.",
            "H_A2": "The sign of the autonomy effect varies systematically with starting indigenous constraint severity and support intensity.",
            "H_A3": "Relative indigenous-service growth versus induced demand growth predicts the autonomy-building/autonomy-eroding boundary better than support intensity alone.",
        },
        [
            "delta_composite_capability_h",
            "delta_q_indigenous_h",
            "delta_indigenous_service_by_channel_h",
            "delta_service_demand_by_channel_h",
            "autonomy_regime_class_360",
            "indigenous_response_to_demand_ratio",
        ],
        {
            "phase_boundary": "Estimate autonomy-building / neutral / autonomy-eroding regions using paired SUPPORT_ON minus SUPPORT_OFF outcomes; always report Delta I and Delta D alongside Delta(I/D).",
            "neutral_tolerance": 1e-6,
            "primary_horizon_days": 360.0,
            "early_effect_horizon_days": 30.0,
            "distribution_rule": "Report median, mean, quantiles, and tail outcomes; do not rely on means alone.",
        },
    )


def bottleneck_migration() -> dict:
    structures = {
        "forcegen_constrained": (0.15, 1.4, 1.4),
        "logistics_constrained": (1.4, 0.25, 1.4),
        "command_constrained": (1.4, 1.4, 0.30),
        "near_tie_low": (0.55, 0.55, 0.55),
    }
    targets = ["none", "forcegen", "logistics", "command", "balanced"]
    intensities = [0.50, 1.00, 1.50]
    cells: list[dict] = []
    n = 0
    for structure, mults in structures.items():
        expected = structure.split("_")[0] if structure != "near_tie_low" else "mixed"
        for target in targets:
            target_intensities = [0.0] if target == "none" else intensities
            for intensity in target_intensities:
                n += 1
                cell = base_cell(f"migration_{n:03d}", "none", mults)
                apply_targeted_substitution(cell, target, intensity)
                cell.update(
                    {
                        "factor_starting_structure": structure,
                        "factor_expected_initial_bottleneck": expected,
                        "factor_support_target": target,
                        "factor_support_intensity": intensity,
                    }
                )
                cells.append(cell)
    assert len(cells) == 52
    return contract(
        "partner_force_stage4_bottleneck_migration_v1",
        "Stage 4B: Bottleneck Migration",
        "Tests whether successful relief of a binding indigenous constraint causes scarcity to migrate to another service channel and erodes the marginal return to static assistance.",
        2026210000,
        cells,
        {
            "H_B1": "Support targeted to the empirically binding channel produces a larger immediate capability/service lift than equal-intensity mismatched support.",
            "H_B2": "After successful matched relief, the formal bottleneck migrates to another channel more often and sooner than under no relief or mismatched relief.",
            "H_B3": "The marginal benefit of continuing support to the original channel declines after bottleneck migration.",
        },
        [
            "initial_bottleneck_identity",
            "time_to_first_bottleneck_migration",
            "bottleneck_path_entropy",
            "delta_composite_capability_h",
            "delta_q_indigenous_h",
            "post_migration_marginal_support_effect",
        ],
        {
            "matched_definition": "A cell is matched only when the observed pre-withdrawal formal_bottleneck equals factor_support_target; labels never override observed telemetry.",
            "migration_definition": "First post-split trajectory checkpoint where interval_formal_bottleneck differs from the pre-withdrawal bottleneck for two consecutive checkpoints.",
            "robustness_requirement": "Repeat the bottleneck result using alternative smooth capability aggregators in downstream analysis so the claim is not a tautology of the minimum operator.",
        },
    )


def substitution_development() -> dict:
    structures = {
        "forcegen": {
            "severe": (0.10, 1.4, 1.4),
            "moderate": (0.25, 1.4, 1.4),
        },
        "logistics": {
            "severe": (1.4, 0.15, 1.4),
            "moderate": (1.4, 0.40, 1.4),
        },
        "command": {
            "severe": (1.4, 1.4, 0.20),
            "moderate": (1.4, 1.4, 0.40),
        },
    }
    intensities = [0.50, 1.00]
    cells: list[dict] = []
    n = 0
    for target, severities in structures.items():
        for severity, mults in severities.items():
            # One no-assistance control per target/severity block.
            n += 1
            control = base_cell(f"mechanism_{n:03d}", "none", mults)
            control.update(
                {
                    "factor_target": target,
                    "factor_severity": severity,
                    "factor_assistance_mode": "none",
                    "factor_intensity": 0.0,
                    "nominal_development_budget_per_day": 0.0,
                }
            )
            cells.append(control)

            for intensity in intensities:
                n += 1
                sub = base_cell(f"mechanism_{n:03d}", "none", mults)
                apply_targeted_substitution(sub, target, intensity)
                sub.update(
                    {
                        "factor_target": target,
                        "factor_severity": severity,
                        "factor_assistance_mode": "substitution",
                        "factor_intensity": intensity,
                        "nominal_development_budget_per_day": 0.0,
                    }
                )
                cells.append(sub)

                n += 1
                dev = base_cell(f"mechanism_{n:03d}", "none", mults)
                apply_development(dev, target, intensity)
                dev.update(
                    {
                        "factor_target": target,
                        "factor_severity": severity,
                        "factor_assistance_mode": "development",
                        "factor_intensity": intensity,
                        "nominal_development_budget_per_day": DAILY_COST_ANCHOR[target]
                        * intensity,
                    }
                )
                cells.append(dev)

                n += 1
                hybrid = base_cell(f"mechanism_{n:03d}", "none", mults)
                apply_targeted_substitution(hybrid, target, intensity * 0.5)
                apply_development(hybrid, target, intensity * 0.5)
                hybrid["support_profile"] = f"stage4_{target}_hybrid"
                hybrid.update(
                    {
                        "factor_target": target,
                        "factor_severity": severity,
                        "factor_assistance_mode": "hybrid",
                        "factor_intensity": intensity,
                        "nominal_development_budget_per_day": DAILY_COST_ANCHOR[target]
                        * intensity
                        * 0.5,
                    }
                )
                cells.append(hybrid)
    assert len(cells) == 42
    return contract(
        "partner_force_stage4_substitution_development_v1",
        "Stage 4C: Substitution vs Development",
        "Separates direct external service substitution from persistent growth of indigenous production capacity under matched weak-channel structures.",
        2026220000,
        cells,
        {
            "H_C1": "Direct substitution produces larger immediate external service but weaker growth in partner-owned production than developmental assistance.",
            "H_C2": "Developmental assistance produces higher terminal indigenous autonomy than substitution at comparable nominal channel budgets, even when early operational gains are smaller.",
            "H_C3": "Hybrid assistance improves the capability-autonomy tradeoff by supplying short-run service while building persistent indigenous production.",
        },
        [
            "delta_indigenous_service_by_channel_h",
            "delta_service_demand_by_channel_h",
            "delta_q_indigenous_h",
            "delta_composite_capability_h",
            "cumulative_donor_cost_h",
            "capability_autonomy_frontier_position",
        ],
        {
            "budget_rule": "Developmental cost anchors use Stage-3 mean daily donor costs for the corresponding heavy support profile: forcegen=1650, logistics=12284, command=2550. Hybrid uses half direct dose plus half developmental rate/budget.",
            "calibration_firewall": "A separate 2026290000-series engineering calibration verified correctness and treatment relevance. The originally specified developmental growth-rate scale was retained unchanged. Calibration worlds are excluded from production inference; production seeds and outcomes remained unseen before freeze.",
            "primary_horizon_days": 360.0,
            "early_effect_horizon_days": 30.0,
        },
    )


def write(name: str, payload: dict) -> None:
    path = CONTRACTS / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({payload['cells_count']} cells)")


def main() -> None:
    write("stage4_autonomy_phase_map_v1.json", phase_map())
    write("stage4_bottleneck_migration_v1.json", bottleneck_migration())
    write("stage4_substitution_development_v1.json", substitution_development())


if __name__ == "__main__":
    main()
