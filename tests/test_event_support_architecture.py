from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/identify_event_support_architecture.py"
SPEC = importlib.util.spec_from_file_location("event_support_architecture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_current_conflict_event_support_is_encounter_limited():
    result = MODULE.run_study(seed=101)
    findings = result["findings"]
    assert findings["insurgent_capacity_present_without_opposing_formation"]
    assert findings["institutional_target_present"]
    assert findings["contact_support_without_opposing_colocated_formation"] == 0
    assert findings["contact_support_with_opposing_colocated_formation"] > 0
    assert result["conclusion"] == "current_conflict_event_support_is_formation_encounter_limited"


def test_zero_violence_does_not_identify_organizational_state():
    result = MODULE.run_study(seed=102)
    findings = result["findings"]
    assert findings["dominance_event_frequency"] == 0.0
    assert findings["absence_event_frequency"] == 0.0
    assert findings["dominance_insurgent_control"] > findings["absence_insurgent_control"]
