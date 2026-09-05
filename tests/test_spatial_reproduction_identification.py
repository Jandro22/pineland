from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "identify_spatial_reproduction.py"
SPEC = importlib.util.spec_from_file_location("identify_spatial_reproduction", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_episode_metrics_separate_continuation_from_reactivation_and_censoring():
    active = {("A", 0), ("A", 1), ("A", 3), ("B", 1), ("B", 2), ("B", 3)}
    result = MODULE.episode_metrics(active, {"A", "B"}, first_period=0, last_period=4)
    assert result["episode_count"] == 3
    assert result["reactivation_count"] == 1
    assert result["right_censored_episode_count"] == 0
    assert result["left_censored_episode_count"] == 1
    assert result["mean_completed_episode_duration"] == 2.0


def test_risk_set_retains_neighbor_dose_and_preoutcome_temporal_order():
    active = {("A", 0), ("C", 0), ("B", 1)}
    neighbors = {
        "A": {"B"},
        "B": {"A", "C"},
        "C": {"B"},
        "D": set(),
    }
    rows = MODULE.build_risk_set(active, set(neighbors), neighbors)
    row = next(item for item in rows if item["area"] == "B" and item["period"] == 0)
    assert row["active_neighbor_count"] == 2
    assert row["exposed"] == 1
    assert row["outcome"] == 1
    assert MODULE.dose_response(rows)[2]["activation_rate"] == 1.0


def test_future_neighbor_activity_is_explicitly_a_temporal_placebo_warning():
    active = {("A", 0), ("B", 1), ("C", 2)}
    neighbors = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}
    result = MODULE.lead_placebo_risk_difference(active, set(neighbors), neighbors)
    assert result["causal_claim_licensed"] is False
    assert "temporal placebo" in result["interpretation"]


def test_degree_stratified_history_placebo_preserves_activity_and_degree():
    areas = ["A", "B", "C", "D", "E", "F"]
    neighbors = MODULE.ring_neighbors(areas)
    active = {("A", 0), ("A", 1), ("B", 2), ("D", 0), ("E", 3)}
    import random
    shuffled = MODULE.permute_area_histories(
        active, areas, neighbors, random.Random(7)
    )
    assert len(shuffled) == len(active)
    assert sorted(sum((neighbor in areas) for neighbor in neighbors[area]) for area in areas) == [2] * 6
    assert sorted(period for _, period in shuffled) == sorted(period for _, period in active)


def test_adversarial_synthetic_recovery_battery_passes_without_historical_data():
    result = MODULE.run_synthetic_recovery_battery(seed=20260905)
    assert result["historical_outcomes_used"] is False
    assert result["passed"]
    assert all(result["gates"].values())
    # The deliberately spatially clustered frailty null fools the crude
    # association but largely disappears after conditioning on known synthetic
    # susceptibility strata.  This is the failure mode the case diagnostic
    # must never silently call contagion.
    assert abs(result["metrics"]["frailty_null_crude_risk_difference"]) > 0.04
    assert abs(result["metrics"]["frailty_null_stratified_risk_difference"]) < 0.04
    assert abs(result["metrics"]["degree_null_crude_risk_difference"]) > 0.03
    assert abs(result["metrics"]["degree_null_stratified_risk_difference"]) < 0.025
    assert abs(result["metrics"]["common_shock_null_crude_risk_difference"]) > 0.04
    assert abs(result["metrics"]["common_shock_null_time_stratified_risk_difference"]) < 0.025


def test_factorial_interventional_contrasts_keep_interaction_explicit():
    result = MODULE.factorial_interventional_contrasts({
        (False, False): 1.0,
        (False, True): 1.2,
        (True, False): 1.1,
        (True, True): 1.8,
    })
    assert result["source_effect_path_off"] == pytest.approx(0.1)
    assert result["path_effect_source_off"] == pytest.approx(0.2)
    assert result["interaction"] == pytest.approx(0.5)

