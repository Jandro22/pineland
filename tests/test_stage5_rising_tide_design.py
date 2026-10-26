import importlib.util
import json
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "studies/research_program/general_theory_v1/partner_force_autonomy"
GEN = BASE / "analysis/generate_stage5_rising_tide_design.py"
CONTRACT = BASE / "contracts/stage5_rising_tide_v1.json"


def load_generator():
    spec = importlib.util.spec_from_file_location("stage5_rising_tide_design", GEN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_analyzer():
    path = BASE / "analysis/analyze_stage5_rising_tide.py"
    spec = importlib.util.spec_from_file_location("stage5_rising_tide_analysis", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_stage5_contract_is_deterministic_and_complete():
    mod = load_generator()
    generated = mod.build_contract()
    tracked = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert generated == tracked
    assert tracked["cells_count"] == 92
    assert tracked["default_seed_count"] == 16
    assert tracked["cells_count"] * tracked["default_seed_count"] == 1472

    by_structure = {}
    for cell in tracked["cells"]:
        by_structure.setdefault(cell["factor_starting_structure"], []).append(cell)
    assert set(by_structure) == {
        "forcegen_constrained",
        "logistics_constrained",
        "command_constrained",
        "near_tie_low",
    }
    assert all(len(cells) == 23 for cells in by_structure.values())


def test_equal_total_effort_and_equal_channel_dose_are_distinct():
    d = json.loads(CONTRACT.read_text(encoding="utf-8"))
    cells = d["cells"]
    for structure in {c["factor_starting_structure"] for c in cells}:
        for intensity in (0.5, 1.0):
            pair_fixed = next(
                c
                for c in cells
                if c["factor_starting_structure"] == structure
                and c["factor_channels"] == "forcegen+logistics"
                and c["factor_dose_regime"] == "equal_total_effort"
                and c["factor_intensity"] == intensity
            )
            pair_full = next(
                c
                for c in cells
                if c["factor_starting_structure"] == structure
                and c["factor_channels"] == "forcegen+logistics"
                and c["factor_dose_regime"] == "equal_channel_dose"
                and c["factor_intensity"] == intensity
            )
            assert pair_fixed["factor_normalized_total_effort"] == intensity
            assert pair_full["factor_normalized_total_effort"] == 2 * intensity
            assert pair_fixed["development_forcegen_rate_per_30d"] == 0.08 * intensity / 2
            assert pair_fixed["development_logistics_rate_per_30d"] == 0.08 * intensity / 2
            assert pair_full["development_forcegen_rate_per_30d"] == 0.08 * intensity
            assert pair_full["development_logistics_rate_per_30d"] == 0.08 * intensity


def test_triple_arm_develops_all_three_indigenous_channels():
    d = json.loads(CONTRACT.read_text(encoding="utf-8"))
    triples = [c for c in d["cells"] if c["factor_channels"] == "forcegen+logistics+command"]
    assert len(triples) == 16
    for c in triples:
        assert c["development_forcegen_rate_per_30d"] > 0
        assert c["development_logistics_rate_per_30d"] > 0
        assert c["development_command_rate_per_30d"] > 0
        assert c["logistics_rate"] == 0
        assert c["forcegen_training_rate_boost"] == 0
        assert c["command_reliability_boost"] == 0


def test_precommitted_interaction_and_breadth_formulas():
    mod = load_analyzer()
    rows = []

    def add(channels, regime, q):
        rows.append(
            {
                "factor_starting_structure": "near_tie_low",
                "factor_intensity": 1.0 if channels != "none" else 0.0,
                "factor_channels": channels,
                "factor_dose_regime": regime,
                "seed": 1,
                "q_indigenous_capped": q,
            }
        )

    add("none", "control", 0.10)
    add("forcegen", "single_reference", 0.20)
    add("logistics", "single_reference", 0.30)
    add("command", "single_reference", 0.40)
    add("forcegen+logistics", "equal_channel_dose", 0.50)
    add("forcegen+command", "equal_channel_dose", 0.60)
    add("logistics+command", "equal_channel_dose", 0.70)
    add("forcegen+logistics+command", "equal_channel_dose", 0.90)
    add("forcegen+logistics", "equal_total_effort", 0.36)
    add("forcegen+command", "equal_total_effort", 0.46)
    add("logistics+command", "equal_total_effort", 0.47)
    add("forcegen+logistics+command", "equal_total_effort", 0.52)

    end = pd.DataFrame(rows)
    interactions = mod.factorial_interactions(end)
    pair = interactions[interactions["interaction"].eq("forcegen+logistics")].iloc[0]
    assert abs(pair["mean_interaction_q"] - 0.10) < 1e-12
    triple = interactions[interactions["order"].eq(3)].iloc[0]
    assert abs(triple["mean_interaction_q"] - (-0.10)) < 1e-12

    breadth = mod.breadth_premiums(end)
    pair_breadth = breadth[breadth["channels"].eq("forcegen+logistics")].iloc[0]
    assert abs(pair_breadth["mean_breadth_premium_q"] - 0.06) < 1e-12
    triple_breadth = breadth[breadth["channels"].eq("forcegen+logistics+command")].iloc[0]
    assert abs(triple_breadth["mean_breadth_premium_q"] - 0.12) < 1e-12
