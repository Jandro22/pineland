#!/usr/bin/env python3
"""Generate the post-review demand-clamp mechanism-ablation contract."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts/stage4_autonomy_phase_map_v1.json"
OUT = ROOT / "contracts/mechanism_ablation_v1.json"


SELECT = [
    ("M1", "logistics_constrained", 0.40, 1.00),
    ("M2", "balanced_capacity", 0.40, 1.00),
    ("M3", "forcegen_constrained", 0.25, 2.00),
    ("M4", "command_constrained", 0.40, 2.00),
]


def main() -> None:
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    cells: list[dict] = []
    for scenario, structure, capacity, intensity in SELECT:
        matches = [
            c
            for c in src["cells"]
            if c["factor_structure"] == structure
            and abs(float(c["factor_capacity_level"]) - capacity) < 1e-12
            and abs(float(c["factor_support_intensity"]) - intensity) < 1e-12
        ]
        if len(matches) != 1:
            raise SystemExit(f"expected one source cell for {scenario}, got {len(matches)}")
        source = matches[0]
        for mode, clamp in [("normal", False), ("demand_clamped", True)]:
            c = deepcopy(source)
            c["cell_id"] = f"ablation_{scenario.lower()}_{mode}"
            c["clamp_logistics_demand_to_withdrawal"] = clamp
            c["factor_source_cell_id"] = source["cell_id"]
            c["factor_scenario"] = scenario
            c["factor_ablation_mode"] = mode
            c["factor_demand_clamp"] = clamp
            cells.append(c)

    payload = {
        "schema_version": "pineland.partner_force_stage4_contract.v1",
        "status": "FROZEN_BEFORE_MECHANISM_ABLATION_PRODUCTION",
        "historical_outcomes_used": False,
        "production_outcomes_used": False,
        "experiment_id": "partner_force_mechanism_ablation_v1",
        "name": "Partner-Force Requirement-Expansion Mechanism Ablation",
        "description": (
            "Paired normal versus logistics-demand-clamped replications of four Stage-4 "
            "Phase-Map conditions selected before ablation production."
        ),
        "seed_namespace": "partner_force_mechanism_ablation_v1-crn-v1",
        "default_seed_count": 12,
        "seed_base": 2026240000,
        "horizons_days": [7.0, 30.0, 90.0, 180.0, 360.0],
        "cells_count": len(cells),
        "hypotheses": {
            "M1": "Demand clamping attenuates the terminal indigenous-coverage penalty.",
            "M2": "The magnitude of attenuation quantifies the causal contribution of supported-branch logistics requirement expansion inside the model.",
            "M3": "Coverage attenuation must be interpreted jointly with any change in supported capability.",
        },
        "primary_estimands": [
            "paired_delta_q_h360_attenuation",
            "paired_delta_capability_h30_change",
            "demand_clamp_relative_error",
        ],
        "analysis_rules": {
            "pairing": "Within each scenario and seed, compare demand_clamped minus normal branch contrasts.",
            "manipulation_median_relative_error_max": 0.01,
            "manipulation_fraction_within_5pct_min": 0.95,
            "bootstrap_replicates": 10000,
            "bootstrap_seed": 2026240999,
            "no_significance_language": True,
            "calibration_seed_excluded": 2026999902,
        },
        "cells": cells,
        "environment": deepcopy(src["environment"]),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} with {len(cells)} cells x 12 seeds = {len(cells)*12} worlds")


if __name__ == "__main__":
    main()

