from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "studies" / "research_program" / "simple_competitors.py"
SPEC = importlib.util.spec_from_file_location("simple_competitors", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def binary_panel() -> pd.DataFrame:
    rows = []
    for t in range(8):
        for unit in ("A", "B", "C"):
            split = "training" if t < 4 and unit != "C" else (
                "geographic_validation" if unit == "C" and t < 4 else
                "strict_joint_holdout" if unit == "C" else "temporal_validation"
            )
            y = int((unit == "A" and t in {1,2,4,5}) or (unit == "B" and t in {3,6}) or (unit == "C" and t in {2,5}))
            rows.append({"unit": unit, "time": t, "split": split, "y": y,
                         "terrain": {"A":0.1,"B":0.5,"C":0.9}[unit],
                         "force_ratio": 0.2 + 0.08*t + (0.1 if unit == "A" else 0.0)})
    return pd.DataFrame(rows)


def test_binary_suite_contains_required_simple_challengers_and_scores():
    frame = binary_panel()
    spec = MODULE.PanelSpec(
        "unit", "time", "y", "binary",
        adjacency={"A":["B"], "B":["A","C"], "C":["B"]},
        covariate_cols=("terrain",), force_ratio_col="force_ratio",
    )
    predictions, metadata = MODULE.predictions_for_panel(frame, spec)
    required = {
        "global_rate", "unit_empirical_bayes", "markov_persistence",
        "dynamic_occupancy", "local_persistence_only",
        "time_since_last_event_logit", "rolling_conflict_history_logit",
        "local_neighbor_diffusion", "temporal_hawkes", "spatiotemporal_hawkes",
        "static_covariate_logit", "persistence_force_logit",
    }
    assert required <= set(predictions.columns)
    for column in required:
        assert predictions[column].between(0, 1).all()
    assert metadata["holdout_target_updates"] is False
    scores = MODULE.score_predictions(predictions, spec)
    assert set(scores.model) == required
    assert {"training", "temporal_validation", "geographic_validation", "strict_joint_holdout"} <= set(scores.split)


def test_holdout_targets_cannot_change_recursive_predictions():
    frame = binary_panel()
    spec = MODULE.PanelSpec(
        "unit", "time", "y", "binary",
        adjacency={"A":["B"], "B":["A","C"], "C":["B"]},
    )
    first, _ = MODULE.predictions_for_panel(frame, spec)
    mutated = frame.copy()
    holdout = mutated.split != "training"
    mutated.loc[holdout, "y"] = 1 - mutated.loc[holdout, "y"]
    second, _ = MODULE.predictions_for_panel(mutated, spec)
    for model in ("global_rate", "unit_empirical_bayes", "markov_persistence",
                  "dynamic_occupancy", "local_persistence_only", "local_neighbor_diffusion",
                  "temporal_hawkes", "spatiotemporal_hawkes",
                  "time_since_last_event_logit", "rolling_conflict_history_logit"):
        np.testing.assert_allclose(first.loc[holdout, model], second.loc[holdout, model])


def test_geographic_holdout_never_contributes_to_unit_fit():
    frame = binary_panel()
    spec = MODULE.PanelSpec("unit", "time", "y", "binary")
    first, _ = MODULE.predictions_for_panel(frame, spec)
    mutated = frame.copy()
    mutated.loc[mutated.unit == "C", "y"] = 1
    second, _ = MODULE.predictions_for_panel(mutated, spec)
    c = first.unit == "C"
    np.testing.assert_allclose(first.loc[c, "unit_empirical_bayes"], second.loc[c, "unit_empirical_bayes"])


def test_count_suite_runs_autoregressive_and_spatial_models_without_holdout_leakage():
    frame = binary_panel().rename(columns={"y":"events"})
    frame["events"] = frame["events"] * 2 + ((frame.time % 3) == 0).astype(int)
    frame["exposure"] = 1.0
    spec = MODULE.PanelSpec(
        "unit", "time", "events", "count", exposure_col="exposure",
        adjacency={"A":["B"], "B":["A","C"], "C":["B"]},
        covariate_cols=("terrain",),
    )
    predictions, _ = MODULE.predictions_for_panel(frame, spec)
    required = {"pooled_poisson", "unit_shrunk_poisson", "spatial_lag_poisson",
                "count_ar1_poisson", "count_spatial_ar_poisson",
                "branching_immigration", "branching_spatial_immigration",
                "static_covariate_poisson", "rolling_conflict_history_poisson"}
    assert required <= set(predictions.columns)
    assert (predictions[list(required)] > 0).all().all()
    mutated = frame.copy(); mutated.loc[mutated.split != "training", "events"] += 20
    second, _ = MODULE.predictions_for_panel(mutated, spec)
    holdout = frame.split != "training"
    for model in required:
        np.testing.assert_allclose(predictions.loc[holdout, model], second.loc[holdout, model])


def test_continuous_control_suite_includes_persistence_and_force_balance():
    frame = binary_panel().rename(columns={"y":"control"})
    frame["control"] = 0.2 + 0.1*frame.time + 0.15*(frame.unit == "A")
    spec = MODULE.PanelSpec(
        "unit", "time", "control", "continuous", force_ratio_col="force_ratio",
        covariate_cols=("terrain",)
    )
    predictions, _ = MODULE.predictions_for_panel(frame, spec)
    required = {"global_training_mean", "unit_shrunk_mean",
                "last_observation_carried_forward", "control_ar1",
                "force_ratio_only", "persistence_plus_force_ratio",
                "static_covariate_ridge"}
    assert required <= set(predictions.columns)
    mutated = frame.copy(); mutated.loc[mutated.split != "training", "control"] += 100
    second, _ = MODULE.predictions_for_panel(mutated, spec)
    holdout = frame.split != "training"
    for model in required:
        np.testing.assert_allclose(predictions.loc[holdout, model], second.loc[holdout, model])


def test_panel_contract_rejects_duplicate_cells_and_missing_training():
    frame = binary_panel()
    spec = MODULE.PanelSpec("unit", "time", "y", "binary")
    with pytest.raises(ValueError, match="one row per unit/time"):
        MODULE.prepare_panel(pd.concat([frame, frame.iloc[[0]]]), spec)
    no_train = frame.copy(); no_train["split"] = "holdout"
    with pytest.raises(ValueError, match="no training rows"):
        MODULE.prepare_panel(no_train, spec)


def test_registry_covers_persistence_diffusion_hawkes_force_and_control_baselines():
    registry = {row["model"] for row in MODULE.competitor_registry()}
    assert {"markov_persistence", "dynamic_occupancy", "local_persistence_only",
            "time_since_last_event_logit", "rolling_conflict_history_logit",
            "local_neighbor_diffusion", "spatiotemporal_hawkes", "branching_immigration",
            "persistence_force_logit", "last_observation_carried_forward",
            "persistence_plus_force_ratio"} <= registry
