from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/afghanistan_2004_2021/scripts/evaluate_transfer_results.py"
SPEC = importlib.util.spec_from_file_location("evaluate_transfer_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_zero_contact_and_no_control_run_is_held_not_promoted():
    report = {
        "horizon_days": 366.0,
        "run_stage": "staged_custom_horizon",
        "all_structural_gates_passed": True,
        "outcome_licenses": {
            "control_validation": False,
            "latent_violence_dynamics": False,
            "recorded_violence_dynamics": False,
        },
        "violence_counts": {"5000": {"latent_contacts": 0, "recorded_contacts": 0}},
        "scores": [
            {"split": "temporal_validation", "model": "pineland_strength_mixture", "log_score": -1.2},
            {"split": "temporal_validation", "model": "global_rate", "log_score": -0.7},
        ],
    }
    result = MODULE.evaluate(report)
    assert result["decision"] == "HOLD_TRANSFER_AND_DIAGNOSE"
    assert not result["promoted_to_general_transfer"]


def test_unverified_core_provenance_is_an_explicit_promotion_blocker():
    report = {
        "horizon_days": 5036.0,
        "run_stage": "staged_custom_horizon",
        "all_structural_gates_passed": True,
        "provenance": {
            "transfer_claims_licensed": False,
            "run_provenance_captured": False,
            "run_provenance_matches_frozen_certificate": False,
        },
        "outcome_licenses": {
            "control_validation": True,
            "control_validation_target_reached": True,
            "latent_violence_dynamics": True,
            "recorded_violence_dynamics": True,
        },
        "scores": [
            {"split": "temporal_validation", "model": "pineland_strength_mixture", "log_score": -0.5},
            {"split": "temporal_validation", "model": "global_rate", "log_score": -0.7},
        ],
    }
    result = MODULE.evaluate(report)
    assert not result["checks"]["frozen_core_provenance"]
    assert not result["promoted_to_general_transfer"]


def test_missing_predeclared_control_success_gate_is_unassessed_not_falsified():
    report = {
        "horizon_days": 5036.0,
        "run_stage": "full",
        "all_structural_gates_passed": True,
        "provenance": {
            "status": "frozen_core_verified",
            "transfer_claims_licensed": True,
            "run_provenance_captured": True,
            "run_provenance_matches_frozen_certificate": True,
        },
        "outcome_licenses": {
            "control_validation": True,
            "control_measurement_licensed": True,
            "control_validation_assessed": False,
            "control_validation_passed": False,
            "control_validation_target_reached": True,
            "control_validation_gate_statuses": {"7500": "unassessed_missing_predeclared_success_gate"},
            "latent_violence_dynamics": True,
            "recorded_violence_dynamics": True,
        },
        "scores": [
            {"split": "temporal_validation", "model": "pineland_strength_mixture", "log_score": -0.5},
            {"split": "temporal_validation", "model": "global_rate", "log_score": -0.7},
        ],
    }
    result = MODULE.evaluate(report)
    assert result["control_gate_assessment"] == "unassessed_missing_predeclared_success_gate"
    assert not result["promoted_to_general_transfer"]
    assert "Do not classify" in result["next_action"]
