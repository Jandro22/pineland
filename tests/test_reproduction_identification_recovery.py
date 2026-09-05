from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "studies" / "research_program" / "scripts"
    / "validate_reproduction_identification.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_reproduction_identification", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_complete_data_free_reproduction_identification_gate_passes():
    result = MODULE.run(seed=20260905)
    assert result["historical_outcomes_used"] is False
    assert result["empirical_parameter_fitting"] is False
    assert result["passed"]
    assert all(result["gates"].values())
    assert result["R_I_censoring"]["ipw_R_I"] != \
        result["R_I_censoring"]["complete_case_R_I"]
