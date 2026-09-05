from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "studies" / "research_program"
SCRIPT = PROGRAM / "scripts" / "scaffold_case.py"
SPEC = importlib.util.spec_from_file_location("scaffold_case", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_generated_contract_validates_and_prohibits_calibration():
    schema = json.loads((PROGRAM / "case_contract.schema.json").read_text(encoding="utf-8"))
    payload = MODULE.contract("example", "transfer", "2000-01-01", "2001-01-01")
    jsonschema.validate(payload, schema)
    assert payload["calibration"] == {
        "licensed": False, "training_only": True, "holdout_refit": False
    }


def test_transport_rules_keep_core_shared_and_uncertainty_decomposed():
    rules = json.loads((PROGRAM / "transport_rules.json").read_text(encoding="utf-8"))
    assert rules["classes"]["shared_core"]["may_vary_by_case"] is False
    assert "holdout refitting" in rules["forbidden"]
    assert len(rules["uncertainty_decomposition"]) == 6
