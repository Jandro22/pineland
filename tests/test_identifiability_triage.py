from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "build_identifiability_triage.py"
SPEC = importlib.util.spec_from_file_location("build_identifiability_triage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_plan_uses_small_valid_question_specific_parameter_sets():
    plan = json.loads((ROOT / "studies" / "research_program" / "identifiability_plan.json").read_text(encoding="utf-8"))
    report = MODULE.build(plan)
    assert report["valid"]
    assert report["global_calibration_prohibited"]
    assert report["registry_identifiability_counts"]["unassessed"] == report["registry_parameter_count"]
    assert all(1 <= row["active_parameter_count"] <= 15 for row in report["questions"])
    assert report["hard_maximum_active_parameters_per_question"] == 15
    access = next(row for row in report["questions"] if row["question_id"] == "spatial_persistence")
    assert "organization_ecology.recruitment_requires_access" in access["structural_interventions"]
    assert "organization_ecology.recruitment_requires_access" not in access["inferential_parameters"]


def test_unknown_parameter_fails_closed():
    plan = {"maximum_active_parameters_per_question": 15, "global_calibration_prohibited": True,
            "questions": [{"question_id": "bad", "active_parameters": ["not.real"],
                           "estimands": [], "mechanisms": [], "required_recovery": "x"}]}
    assert not MODULE.build(plan)["valid"]


def test_plan_cannot_self_license_global_or_high_dimensional_calibration():
    plan = {"maximum_active_parameters_per_question": 211, "global_calibration_prohibited": False,
            "questions": [{"question_id": "bad", "active_parameters": ["contact_rate"],
                           "estimands": ["incidence"], "mechanisms": ["contact"],
                           "required_recovery": "recover"}]}
    report = MODULE.build(plan)
    assert not report["valid"]
    assert not report["global_calibration_prohibited"]


def test_duplicate_or_content_free_question_fails_closed():
    plan = {"maximum_active_parameters_per_question": 15, "global_calibration_prohibited": True,
            "questions": [
                {"question_id": "dup", "active_parameters": ["contact_rate", "contact_rate"],
                 "estimands": [], "mechanisms": [], "required_recovery": ""},
                {"question_id": "dup", "active_parameters": ["recruitment_rate"],
                 "estimands": ["x"], "mechanisms": ["y"], "required_recovery": "recover"},
            ]}
    report = MODULE.build(plan)
    assert not report["valid"]
    assert any("duplicate_question_id" in error for error in report["errors"])
    assert any("duplicate_active_parameters" in error for error in report["errors"])
    assert any("invalid_estimands" in error for error in report["errors"])
