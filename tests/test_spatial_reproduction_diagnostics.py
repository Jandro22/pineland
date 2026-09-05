from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "diagnose_spatial_reproduction.py"
SPEC = importlib.util.spec_from_file_location("diagnose_spatial_reproduction", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_persistence_and_neighbor_activation_are_separate_estimands():
    active = {("A", 0), ("A", 1), ("B", 1), ("C", 2)}
    neighbors = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}
    result = MODULE.transition_metrics(active, set(neighbors), neighbors)
    assert result["same_area_renewal_rate"] == 1 / 3
    assert result["neighbor_activation_rate"] == 1.0
    assert result["neighbor_unexposed_activation_rate"] == 0.0
    assert result["neighbor_activation_risk_difference"] == 1.0


def test_neighbor_activation_reports_background_risk_instead_of_implying_contagion():
    # A and C both activate new areas at t+1, but C has no active neighbor at
    # t=0.  The exposed rate alone is therefore not a causal contagion signal.
    active = {("A", 0), ("B", 1), ("C", 1)}
    neighbors = {"A": {"B"}, "B": {"A"}, "C": set()}
    result = MODULE.transition_metrics(active, set(neighbors), neighbors)
    assert result["neighbor_activation_rate"] == 1.0
    assert result["neighbor_unexposed_activation_rate"] == 1.0
    assert result["neighbor_activation_risk_difference"] == 0.0


def test_overlap_reports_zero_intersection_cleanly():
    result = MODULE.overlap_metrics({("A", 1)}, {("B", 1)})
    assert result == {"intersection": 0, "historical_sensitivity": 0.0,
                      "model_precision": 0.0, "jaccard": 0.0}
