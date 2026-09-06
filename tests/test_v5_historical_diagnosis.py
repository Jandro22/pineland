from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "studies/research_program/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("v5_diagnosis", SCRIPTS / "diagnose_v5_historical_confrontation.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_auc_handles_ties_and_undefined_classes():
    assert MODULE.auc([0, 1], [1, 1]) == 0.5
    assert MODULE.auc([0, 1], [0, 1]) == 1.0
    assert MODULE.auc([0, 1], [1, 0]) == 0.0
    assert MODULE.auc([0, 0], [0, 1]) is None


def test_identity_guard_rejects_changed_targets_and_competitors():
    frame = pd.DataFrame({"district_id": ["A", "B"], "week_start": ["2001-11-26"] * 2,
        "split": ["training", "holdout"], "observed_active": [0, 1],
        "simple": [0.2, 0.3], "pineland_recorded_ensemble": [0.0, 0.1]})
    MODULE.aligned_frames(frame, frame.iloc[::-1])
    changed = frame.copy()
    changed.loc[0, "observed_active"] = 1
    with pytest.raises(ValueError, match="targets"):
        MODULE.aligned_frames(frame, changed)
    changed = frame.copy()
    changed.loc[0, "simple"] = 0.9
    with pytest.raises(ValueError, match="predictions"):
        MODULE.aligned_frames(frame, changed)


def test_control_signal_never_uses_future_checkpoint():
    axes = ("formal", "physical", "administrative", "legal", "fiscal", "social", "expected")
    def checkpoint(day, value):
        return {"time": day, "control": {"L": {
            "insurgent": dict.fromkeys(axes, value), "government": dict.fromkeys(axes, 0)}}}
    run = {"checkpoints": [checkpoint(0, 0), checkpoint(30, 1)]}
    panel = pd.DataFrame({"district_id": ["A", "A"], "week_start": ["2001-12-24", "2001-12-31"]})
    assert MODULE.control_signal(run, panel, {"L": "A"}).tolist() == [0, 1]
