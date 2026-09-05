from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/run_aligned_predictive_competition.py"
SPEC = importlib.util.spec_from_file_location("aligned_predictive_competition", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_candidate_join_preserves_cell_identity_after_competitor_sort():
    panel = pd.DataFrame({"u": ["A", "A", "B", "B"], "t": [0, 1, 0, 1],
                          "pineland_latent_ensemble": [0.1, 0.2, 0.3, 0.4]})
    predictions = pd.DataFrame({"u": ["A", "B", "A", "B"], "t": [0, 0, 1, 1]})
    result = MODULE.attach_candidate_predictions(predictions, panel, "u", "t")
    assert result.pineland_latent_ensemble.tolist() == [0.1, 0.3, 0.2, 0.4]
    with pytest.raises(ValueError):
        MODULE.attach_candidate_predictions(predictions.iloc[:3], panel, "u", "t")


def test_ensemble_probability_is_exact_member_frequency():
    panel = pd.DataFrame({"u": ["A", "B"], "historical_time": ["x", "y"], "sim_t": [1, 1]})
    members = [{("A", 1)}, {("A", 1), ("B", 1)}, set(), {("B", 1)}]
    assert MODULE.ensemble_probability(panel, "u", "sim_t", members) == [0.5, 0.5]


def test_decision_fails_closed_for_incomplete_ensemble():
    scores = pd.DataFrame([
        {"split":"temporal_validation","model":"pineland_recorded_ensemble","log_score":-0.1,"brier":0.05},
        {"split":"temporal_validation","model":"global_rate","log_score":-0.2,"brier":0.10},
    ])
    result = MODULE.decision(scores, complete=False, member_count=4, expected_members=8, final_stage=True)
    assert result["verdict"] == "provisional_incomplete_ensemble"
    assert result["scientific_verdict_licensed"] is False
    assert result["coin_science_authorized"] is False


def test_nonfinal_horizon_cannot_issue_transfer_verdict():
    scores = pd.DataFrame([
        {"split":"temporal_validation","model":"pineland_recorded_ensemble","log_score":-0.1,"brier":0.05},
        {"split":"temporal_validation","model":"global_rate","log_score":-0.2,"brier":0.10},
    ])
    result = MODULE.decision(scores, complete=True, member_count=1, expected_members=1, final_stage=False)
    assert result["verdict"] == "diagnostic_nonfinal_horizon"
    assert result["scientific_verdict_licensed"] is False


def test_province_adjacency_aggregates_cross_province_district_edges(tmp_path):
    processed = tmp_path / "data/processed"; processed.mkdir(parents=True)
    pd.DataFrame([
        {"district_id":"D1","province_id":"P1"},
        {"district_id":"D2","province_id":"P1"},
        {"district_id":"D3","province_id":"P2"},
    ]).to_csv(processed / "districts.csv", index=False)
    (processed / "district_adjacency.json").write_text(
        '{"neighbors":{"D1":["D2"],"D2":["D1","D3"],"D3":["D2"]}}'
    )
    assert MODULE.province_adjacency(tmp_path) == {"P1":["P2"], "P2":["P1"]}
