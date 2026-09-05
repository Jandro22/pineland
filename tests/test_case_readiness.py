from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/validate_case_readiness.py"
SPEC = importlib.util.spec_from_file_location("validate_case_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_future_case_scaffold_fails_closed_until_sources_and_holdouts_exist():
    case_root = ROOT / "studies/colombia_1984_2016"
    contract = json.loads((case_root / "config/case_contract.json").read_text(encoding="utf-8"))
    result = MODULE.validate(contract, case_root)
    assert not result["passed"]
    assert "source_manifest_ready" in result["blocked_reasons"]
    assert "acquired_source_hashes_valid" not in result["blocked_reasons"]
    assert "processed_panel_manifest" in result["blocked_reasons"]
    assert "measurement_audit" not in result["blocked_reasons"]
    assert "holdout_manifest_artifact" not in result["blocked_reasons"]
    assert "construct_measurements_declared" not in result["blocked_reasons"]
    assert "holdouts_frozen" not in result["blocked_reasons"]
