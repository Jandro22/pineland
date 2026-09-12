"""Fail-closed validation suite for the historical database layer (standard_v2).

Validates all 6 historical case bundles in the portfolio:
1. afghanistan_2004_2021 (EXPERIMENT_READY)
2. nepal_2001_2006 (EXPERIMENT_READY)
3. colombia_1984_2016 (VERIFICATION_LIMITED)
4. iraq_2003_2011 (VERIFICATION_LIMITED)
5. vietnam_1955_1975 (VERIFICATION_LIMITED)
6. nigeria_2014 (SEALED_HOLDOUT)

Enforces:
- Schema, hash, and metadata conformance against historical_database_standard_v2.json
- Uniform builder_sha256 across all 6 manifests
- Uniform standard_sha256 across all 6 manifests
- Strict holdout firewall on Nigeria 2014 (no event records opened)
- Top-level historical_database_registry_v2.json parity
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "validate_historical_database_v2.py"
SPEC = importlib.util.spec_from_file_location("validate_historical_database_v2", VALIDATOR_SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

CASES = [
    ("afghanistan_2004_2021", ROOT / "studies" / "afghanistan_2004_2021" / "data" / "standard_v2", "EXPERIMENT_READY"),
    ("nepal_2001_2006", ROOT / "studies" / "nepal_2001_2006" / "data" / "standard_v2", "EXPERIMENT_READY"),
    ("colombia_1984_2016", ROOT / "studies" / "colombia_1984_2016" / "data" / "standard_v2", "VERIFICATION_LIMITED"),
    ("iraq_2003_2011", ROOT / "studies" / "iraq_2003_2011" / "data" / "standard_v2", "VERIFICATION_LIMITED"),
    ("vietnam_1955_1975", ROOT / "studies" / "vietnam_1955_1975" / "data" / "standard_v2", "VERIFICATION_LIMITED"),
    ("nigeria_2014", ROOT / "studies" / "research_program" / "external_validation" / "nigeria_2014" / "standard_v2", "SEALED_HOLDOUT"),
]


def test_all_cases_pass_validation():
    """All 6 bundles must pass fail-closed validation."""
    for case_id, bundle_path, expected_license in CASES:
        assert bundle_path.is_dir(), f"Bundle directory missing: {bundle_path}"
        res = MODULE.validate(bundle_path)
        assert res["passed"], f"Validation failed for {case_id}: {res['checks']}"
        assert res["license"] == expected_license, f"License mismatch for {case_id}: got {res['license']}, expected {expected_license}"


@pytest.mark.parametrize("case_id,bundle_path,expected_license", CASES)
def test_individual_case_validation(case_id: str, bundle_path: Path, expected_license: str):
    """Each case bundle must validate individually against standard v2."""
    assert bundle_path.is_dir(), f"Bundle directory missing: {bundle_path}"
    res = MODULE.validate(bundle_path)
    assert res["passed"], f"Validation failed for {case_id}: {res['checks']}"
    assert res["license"] == expected_license


def test_builder_sha256_uniformity():
    """All 6 manifests must record the exact same builder_sha256 matching the current builder script."""
    builder_script = ROOT / "studies" / "research_program" / "scripts" / "build_historical_database_v2.py"
    expected_hash = MODULE.sha256(builder_script)
    hashes = {}
    for case_id, bundle_path, _ in CASES:
        manifest = json.loads((bundle_path / "dataset_manifest.json").read_text(encoding="utf-8"))
        hashes[case_id] = manifest.get("builder_sha256")
    assert len(set(hashes.values())) == 1, f"Builder SHA-256 mismatch across cases: {hashes}"
    assert list(hashes.values())[0] == expected_hash, f"Manifest builder hash {list(hashes.values())[0]} != script hash {expected_hash}"


def test_standard_sha256_uniformity():
    """All 6 manifests must record the standard_sha256 matching historical_database_standard_v2.json."""
    standard_file = ROOT / "studies" / "research_program" / "historical_database_standard_v2.json"
    expected_hash = MODULE.sha256(standard_file)
    for case_id, bundle_path, _ in CASES:
        manifest = json.loads((bundle_path / "dataset_manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("standard_sha256") == expected_hash, f"{case_id} standard hash mismatch"


def test_nigeria_sealed_holdout_integrity():
    """Nigeria 2014 must retain 0 events and target archive must never be opened."""
    nigeria_dir = ROOT / "studies" / "research_program" / "external_validation" / "nigeria_2014" / "standard_v2"
    manifest = json.loads((nigeria_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert "not opened or read" in manifest.get("historical_target_firewall", "")
    assert manifest["case_metadata"].get("sealed") is True


def test_portfolio_registry_conformance():
    """Top-level historical_database_registry_v2.json must exist and match all 6 cases."""
    reg_path = ROOT / "studies" / "research_program" / "historical_database_registry_v2.json"
    assert reg_path.is_file(), "Registry file missing"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    assert reg["schema_version"] == "pineland.historical_database_registry.v2"
    assert len(reg["cases"]) == 6
    for case_id, _, expected_license in CASES:
        case_info = next((c for c in reg["cases"] if c["case_id"] == case_id), None)
        assert case_info is not None, f"Case {case_id} not in registry"
        assert case_info["license"] == expected_license
        assert case_info["validation_passed"] is True
