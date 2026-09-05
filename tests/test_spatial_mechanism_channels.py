import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "diagnose_spatial_mechanism_channels.py"
SPEC = importlib.util.spec_from_file_location("diagnose_spatial_mechanism_channels", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_live_reallocation_directions_are_exposed_without_historical_fit():
    result = MODULE.diagnose(seed=20260904)
    assert result["historical_outcomes_used"] is False
    assert result["empirical_parameter_fitting"] is False
    assert result["core_change_licensed"] is False
    movement = result["movement_policy"]
    assert movement["insurgent_mixed_policy_confirmed"]
    government = movement["government"]
    assert government["target_selected_when_favored"] == (
        government["favorable_choice"] == government["controlled_target_locality_id"]
    )
    assert government["target_rejected_when_disfavored"] == (
        government["unfavorable_choice"] != government["controlled_target_locality_id"]
    )
    assert movement["government_gap_filling_confirmed"] == (
        government["target_selected_when_favored"] and
        government["target_rejected_when_disfavored"]
    )
    assert abs(sum(movement["insurgent"]["weights"].values()) - 1.0) < 1e-9


def test_patrol_memory_channel_is_not_silently_treated_as_symmetric_formation_memory():
    result = MODULE.presence_memory_diagnostic(seed=20260904)
    assert result["insurgent_direct_physical_control_after_refresh"] > 0
    assert result["insurgent_memory_after_stationary_physical_refresh"] == 0
    assert result["insurgent_patrol_object_count"] == 0
    if result["government_memory_after_patrol"] > 0:
        assert result["patrol_memory_channel_asymmetry_confirmed"]
        assert "patrol-written" in result["interpretation"]
    else:
        assert not result["patrol_memory_channel_asymmetry_confirmed"]
        assert "not confirm" in result["interpretation"]
