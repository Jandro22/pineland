import json
from pathlib import Path

import pytest

from pineland_sim.historical import (active_run_lengths, assert_validation_lock,
                                      burstiness, fano_factor, gini, haversine_km,
                                      load_frozen_split, morans_i,
                                      population_adjusted_hhi, rows_for_purpose,
                                      sha256_file)


ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "studies" / "nepal_2001_2006" / "config" / "split_manifest.json"


def test_nepal_split_is_frozen_and_stable():
    manifest = load_frozen_split(SPLIT)
    assert len(manifest["splits"]) == 4
    assert sha256_file(SPLIT) == "5a0e79f75e8831e31a00514769be59f77b9107d4d580f3bc9878f9597f407392"


def test_calibration_cannot_read_holdout_rows():
    rows = [{"split": "training", "value": 1},
            {"split": "temporal_validation", "value": 2}]
    assert rows_for_purpose(rows, "training", "calibration") == [rows[0]]
    with pytest.raises(PermissionError):
        rows_for_purpose(rows, "temporal_validation", "calibration")


def test_validation_requires_matching_non_refitting_lock():
    digest = sha256_file(SPLIT)
    assert_validation_lock({"status": "locked", "split_manifest_sha256": digest,
                            "refit_permitted": False}, digest)
    with pytest.raises(PermissionError):
        assert_validation_lock({"status": "draft", "split_manifest_sha256": digest,
                                "refit_permitted": False}, digest)
    with pytest.raises(PermissionError):
        assert_validation_lock({"status": "locked", "split_manifest_sha256": "wrong",
                                "refit_permitted": False}, digest)


def test_historical_estimators_include_zeros_and_have_known_values():
    assert fano_factor([0, 0, 2, 2]) == 1.0
    assert active_run_lengths([0, 1, 2, 0, 3]) == [2, 1]
    assert gini([0, 0, 1, 1]) == 0.5
    assert burstiness([1, 1, 1]) == -1.0
    assert population_adjusted_hhi([1, 1], [1, 1]) == 0.0


def test_spatial_estimators_have_sanity_checks():
    values = {"a": 0.0, "b": 1.0, "c": 2.0}
    adjacency = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}
    assert morans_i(values, adjacency) == 0.0
    assert haversine_km((0.0, 0.0), (0.0, 0.0)) == 0.0
    assert 110 < haversine_km((0.0, 0.0), (0.0, 1.0)) < 112
