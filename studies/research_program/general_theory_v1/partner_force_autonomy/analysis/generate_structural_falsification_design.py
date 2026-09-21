#!/usr/bin/env python3
"""Generate the prospectively frozen structural-falsification sidecar."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts/structural_falsification_v1.json"


def base(cell_id: str, mults: tuple[float, float, float]) -> dict:
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


def main() -> None:
    cells: list[dict] = []

    c = base("structural_001", (0.10, 4.00, 0.35))
    c.update(
        support_profile="structural_forcegen_substitution",
        forcegen_training_rate_boost=0.035,
        forcegen_cost_per_incremental_trainee=120.0,
        factor_path="forcegen_to_command",
        factor_expected_initial_bottleneck="forcegen",
        factor_expected_post_bottleneck="command",
        factor_treatment_mode="substitution",
    )
    cells.append(c)

    c = base("structural_002", (0.35, 4.00, 0.15))
    c.update(
        support_profile="structural_command_substitution",
        command_reliability_boost=0.55,
        command_latency_reduction_fraction=0.55,
        command_floor_hours=0.5,
        command_cost_per_formation_day=240.0,
        factor_path="command_to_forcegen",
        factor_expected_initial_bottleneck="command",
        factor_expected_post_bottleneck="forcegen",
        factor_treatment_mode="substitution",
    )
    cells.append(c)

    c = base("structural_003", (4.00, 0.25, 0.35))
    c.update(
        support_profile="structural_logistics_development",
        development_logistics_rate_per_30d=0.08,
        development_cost_per_day=12284.0,
        factor_path="logistics_to_command",
        factor_expected_initial_bottleneck="logistics",
        factor_expected_post_bottleneck="command",
        factor_treatment_mode="development",
    )
    cells.append(c)

    c = base("structural_004", (0.35, 0.25, 4.00))
    c.update(
        support_profile="structural_logistics_development",
        development_logistics_rate_per_30d=0.08,
        development_cost_per_day=12284.0,
        factor_path="logistics_to_forcegen",
        factor_expected_initial_bottleneck="logistics",
        factor_expected_post_bottleneck="forcegen",
        factor_treatment_mode="development",
    )
    cells.append(c)

    payload = {
        "schema_version": "pineland.partner_force_stage4_contract.v1",
        "status": "FROZEN_BEFORE_STRUCTURAL_FALSIFICATION_PRODUCTION",
        "historical_outcomes_used": False,
        "production_outcomes_used": False,
        "experiment_id": "partner_force_structural_falsification_v1",
        "name": "Post-Stage-4 Structural Terminal-Constraint Falsification",
        "description": (
            "Adversarial possibility test asking whether non-logistics terminal "
            "constraints are dynamically reachable after targeted relief."
        ),
        "seed_namespace": "partner_force_structural_falsification_v1-crn-v1",
        "default_seed_count": 8,
        "seed_base": 2026235000,
        "horizons_days": [30.0],
        "cells_count": len(cells),
        "hypotheses": {
            "F1": "The runtime permits command to become the post-relief formal bottleneck when logistics is structurally abundant.",
            "F2": "The runtime permits force generation to become the post-relief formal bottleneck when logistics is structurally abundant or successfully developed.",
        },
        "primary_estimands": [
            "pre_observed_bottleneck",
            "support_on_bottleneck_h30",
            "target_match",
            "designated_path_fraction",
        ],
        "analysis_rules": {
            "pre_window_days": [60.0, 120.0],
            "post_horizon_days": 30.0,
            "post_branch": "SUPPORT_ON",
            "artifact_rejection_rule": (
                "Reject unique-logistics-hard-code interpretation if at least one observed-target-matched "
                "world ends in command and at least one ends in forcegen."
            ),
            "no_retuning_after_outcomes": True,
        },
        "cells": cells,
        "environment": {
            "agent_count": 1000,
            "locality_count": 72,
            "withdrawal_time_days": 120.0,
            "observation_start_days": 60.0,
            "development_cadence_days": 7.0,
        },
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(cells)} cells x 8 seeds = {len(cells) * 8} worlds")


if __name__ == "__main__":
    main()

