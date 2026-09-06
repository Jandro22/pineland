from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/identify_franchise_consequence_symmetry.py"
SPEC = importlib.util.spec_from_file_location("identify_franchise_consequence_symmetry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_matched_worlds_preserve_null_consequences_instead_of_adding_mechanisms():
    result = MODULE.run_study(seed=20260905)
    effects = result["consequence_assessment_direct_rootedness_effect"]
    assert effects["recruitment"] is True
    assert effects["information_access"] is True
    assert all(
        value is False
        for key, value in effects.items()
        if key not in {"recruitment", "information_access"}
    )
    assert result["core_model_modified"] is False
    assert result["historical_outcomes_used"] is False


def test_rootedness_measurement_is_actor_kind_symmetric_but_transitions_are_unresolved():
    result = MODULE.run_study(seed=20260905)
    symmetry = result["measurement_symmetry"]
    assert symmetry["constituency_congruence_operator_kind_invariant"] is True
    assert symmetry["transition_symmetry_established"] is False
    assert set(symmetry["actor_kinds"]) == {
        "insurgent", "government", "military", "police", "foreign", "party", "civic"
    }
