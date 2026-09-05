from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "afghanistan_2004_2021" / "scripts" / "run_control_competitors.py"
SPEC = importlib.util.spec_from_file_location("run_control_competitors", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_holdout_values_never_change_predictions():
    training = [
        {"district_id": "D1", "province_id": "P1", "period": "2016Q1", "split": "training", "control_index": "0.75"},
        {"district_id": "D2", "province_id": "P1", "period": "2016Q1", "split": "training", "control_index": "0.25"},
    ]
    holdout = {"district_id": "D1", "province_id": "P1", "period": "2017Q4", "split": "holdout", "control_index": "1.0"}
    first = MODULE.fit_predict(training + [holdout])
    second = MODULE.fit_predict(training + [{**holdout, "control_index": "0.0"}])
    for model in ("global_training_mean", "province_empirical_bayes", "district_empirical_bayes", "last_training_control"):
        assert first[0][model] == second[0][model]


def test_no_training_data_fails_closed():
    with pytest.raises(ValueError):
        MODULE.fit_predict([{"district_id": "D", "province_id": "P", "period": "t",
                             "split": "holdout", "control_index": "0.5"}])


def test_period_leakage_fails_closed():
    rows = [
        {"district_id": "D1", "province_id": "P", "period": "t", "split": "training", "control_index": "0.5"},
        {"district_id": "D2", "province_id": "P", "period": "t", "split": "holdout", "control_index": "0.5"},
    ]
    with pytest.raises(ValueError):
        MODULE.fit_predict(rows)


def test_future_training_period_cannot_predict_earlier_holdout():
    rows = [
        {"district_id": "D1", "province_id": "P", "period": "2017Q1", "split": "training", "control_index": "0.5"},
        {"district_id": "D2", "province_id": "P", "period": "2016Q4", "split": "holdout", "control_index": "0.5"},
    ]
    with pytest.raises(ValueError, match="future control cannot predict the past"):
        MODULE.fit_predict(rows)


def test_noncanonical_period_fails_closed():
    rows = [
        {"district_id": "D1", "province_id": "P", "period": "early", "split": "training", "control_index": "0.5"},
        {"district_id": "D2", "province_id": "P", "period": "later", "split": "holdout", "control_index": "0.5"},
    ]
    with pytest.raises(ValueError, match="period must be"):
        MODULE.fit_predict(rows)
