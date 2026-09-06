from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "diagnose_v5_afghanistan_confrontation.py"
SPEC = importlib.util.spec_from_file_location("diagnose_v5_afghanistan_confrontation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_auc_is_tie_aware_and_perfect_when_ranked():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.8, 0.9])
    assert MODULE.auc(y, p) == 1.0


def test_auc_is_undefined_with_one_outcome_class():
    assert MODULE.auc(np.array([0, 0]), np.array([0.1, 0.2])) is None


def test_brier_and_log_score_reward_better_probabilities():
    y = np.array([0, 1, 1, 0])
    good = np.array([0.1, 0.9, 0.8, 0.2])
    bad = np.array([0.8, 0.2, 0.3, 0.7])
    assert MODULE.brier(y, good) < MODULE.brier(y, bad)
    assert MODULE.log_score(y, good) > MODULE.log_score(y, bad)
