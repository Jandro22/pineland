from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "validate_coin_contract.py"
SPEC = importlib.util.spec_from_file_location("validate_coin_contract", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_preregistered_coin_design_is_structurally_complete():
    result = MODULE.validate(MODULE.load_contract())
    assert result["passed"], result
    assert result["intervention_count"] == 9


def test_coin_design_rejects_violence_only_optimization():
    contract = MODULE.load_contract()
    contract["license"]["optimize_violence_alone"] = True
    result = MODULE.validate(contract)
    assert not result["passed"]
    assert not result["checks"]["violence_only_optimization_forbidden"]
