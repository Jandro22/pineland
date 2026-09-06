from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "validate_estimand_registry.py"
SPEC = importlib.util.spec_from_file_location("validate_estimand_registry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_estimand_registry_gate_is_structurally_complete():
    result = MODULE.validate(MODULE.load_registry())
    assert result["passed"], result
    assert result["outcome_count"] == 7
    assert result["quiet_state_count"] == 6
    assert result["intervention_resource_contract_count"] == 9
    assert result["evaluation_horizons_days"] == [30, 90, 365]


def test_registry_rejects_hidden_truth_policy_access():
    registry = copy.deepcopy(MODULE.load_registry())
    registry["causal_policy_estimand"]["policy_information_set"]["simulated_hidden_truth_access"] = True
    result = MODULE.validate(registry)
    assert not result["passed"]
    assert not result["checks"]["adaptive_policy_uses_measured_history_only"]


def test_registry_rejects_post_fit_recurrence_window_change():
    registry = copy.deepcopy(MODULE.load_registry())
    registry["time_contract"]["recurrence"]["followup_days"] = 180
    result = MODULE.validate(registry)
    assert not result["passed"]
    assert not result["checks"]["recurrence_window_predeclared"]


def test_registry_rejects_missing_quiet_state():
    registry = copy.deepcopy(MODULE.load_registry())
    del registry["quiet_state_registry"]["reporting_failure"]
    result = MODULE.validate(registry)
    assert not result["passed"]
    assert not result["checks"]["six_quiet_states_distinguished"]


def test_registry_requires_resource_contract_for_every_intervention():
    registry = copy.deepcopy(MODULE.load_registry())
    del registry["causal_policy_estimand"]["intervention_resource_constraints"]["withdrawal"]
    result = MODULE.validate(registry)
    assert not result["passed"]
    assert not result["checks"]["resource_constraints_cover_all_interventions"]


def test_registry_forbids_implicit_violence_welfare_scalarization():
    registry = copy.deepcopy(MODULE.load_registry())
    registry["causal_policy_estimand"]["welfare"]["lower_violence_implies_higher_welfare"] = True
    result = MODULE.validate(registry)
    assert not result["passed"]
    assert not result["checks"]["scalar_welfare_not_implicit"]
