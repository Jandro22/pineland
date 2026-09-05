from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/evaluate_predictive_competition_gate.py"
SPEC = importlib.util.spec_from_file_location("evaluate_predictive_competition_gate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_gate_requires_six_challengers_and_identical_holdouts():
    result = MODULE.evaluate()
    assert set(result["required_competitors"]) == {
        "national_manpower", "violence_autoregression", "local_persistence_only",
        "static_geography", "government_force_ratio", "simple_spatial_diffusion",
    }
    assert result["candidate_requirements"]["same_holdout_rows_as_competitors"] is False
    assert result["gate_passed"] is False
    assert result["coin_science_authorized"] is False
