from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "run_synthetic_reproduction_competitor_smoke.py"
SPEC = importlib.util.spec_from_file_location("synthetic_reproduction_competitor_smoke", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_temporal_split_never_uses_post_cutoff_period_as_training():
    site = pd.DataFrame({
        "period_end_day":[7.0,14.0,21.0,28.0],
        "period_index":[0,1,2,3], "split":["training"]*4,
    })
    aggregate = site.copy()
    episode = pd.DataFrame({
        "activation_day":[2.0,10.0,20.0], "split":["training"]*3,
    })
    split = MODULE._temporal_split_tables(
        {"site_period":site,"aggregate_period":aggregate,"foothold_episode":episode},
        14.0, deepening_horizon=7.0, survival_horizon=7.0,
    )
    assert split["site_period"].split.tolist() == [
        "training", "training", "temporal_validation", "temporal_validation"
    ]
    assert split["aggregate_period"].split.tolist() == [
        "training", "training", "temporal_validation", "temporal_validation"
    ]


def test_episode_target_split_requires_outcome_horizon_before_cutoff(tmp_path):
    episode = pd.DataFrame({
        "run_id":["r"]*3,
        "activation_id":["a","b","c"],
        "locality_id":["L1","L2","L3"],
        "activation_day":[1.0,8.0,18.0],
        "parentage_class":["local_spontaneous_ignition"]*3,
        "deepened_to_fielded_force":[1.0,0.0,1.0],
    })
    scores = MODULE._score_episode_target(
        episode, "deepened_to_fielded_force", cutoff_day=14.0,
        horizon=7.0, out=tmp_path,
    )
    predictions = pd.read_csv(tmp_path / "deepened_to_fielded_force_predictions.csv")
    by_id = predictions.set_index("activation_id").split.to_dict()
    assert by_id["a"] == "training"
    assert by_id["b"] == "temporal_validation"
    assert by_id["c"] == "temporal_validation"
    assert scores is not None
