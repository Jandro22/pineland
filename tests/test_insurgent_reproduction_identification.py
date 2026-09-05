from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "estimate_insurgent_reproduction.py"
SPEC = importlib.util.spec_from_file_location("estimate_insurgent_reproduction_hardened", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def row(
    activation_id,
    locality,
    day,
    end,
    *,
    viable=True,
    followup_probability=None,
    run_id=None,
):
    result = {
        "activation_id": activation_id,
        "locality_id": locality,
        "activation_day": day,
        "observation_end_day": end,
        "parent_locality_id": None,
        "viable": viable,
    }
    if followup_probability is not None:
        result["followup_inclusion_probability"] = followup_probability
    if run_id is not None:
        result["run_id"] = run_id
    return result


def test_parent_edge_pathways_are_reported_as_competing_reproduction_routes():
    rows = [
        row("A1", "A", 0, 100),
        row("B1", "B", 0, 100),
        row("C1", "C", 10, 20),
        row("D1", "D", 12, 20),
        row("E1", "E", 15, 20),
    ]
    edges = [
        {"child_activation_id": "C1", "parent_activation_id": "A1",
         "weight": 0.5, "pathway": "social_bridge"},
        {"child_activation_id": "D1", "parent_activation_id": "A1",
         "weight": 0.5, "pathway": "formation_movement"},
        {"child_activation_id": "E1", "parent_activation_id": "B1",
         "weight": 1.0, "pathway": "social_bridge"},
    ]
    result = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0
    )
    assert result["eligible_parent_activations"] == 2
    assert result["estimate"] == pytest.approx(1.0)
    assert result["estimate_by_pathway"]["social_bridge"] == pytest.approx(0.75)
    assert result["estimate_by_pathway"]["formation_movement"] == pytest.approx(0.25)
    assert sum(result["estimate_by_pathway"].values()) == pytest.approx(result["estimate"])
    assert result["gross_estimate_by_pathway"] == result["estimate_by_pathway"]


def test_ipw_censoring_adjustment_uses_declared_followup_probabilities():
    rows = [
        row("A1", "A", 0, 100, followup_probability=0.25),
        row("B1", "B", 0, 100, followup_probability=1.0),
        row("C1", "C", 10, 20),
        row("D1", "D", 12, 20),
    ]
    edges = [
        {"child_activation_id": "C1", "parent_activation_id": "A1", "weight": 1.0},
        {"child_activation_id": "D1", "parent_activation_id": "A1", "weight": 1.0},
    ]
    complete = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0
    )
    adjusted = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0,
        censoring_adjustment="ipw",
    )
    assert complete["estimate"] == pytest.approx(1.0)
    assert adjusted["estimate"] == pytest.approx(1.6)
    assert adjusted["censoring_adjustment"] == "ipw"
    assert adjusted["right_censored_parent_activations"] == 2


def test_ipw_fails_closed_without_valid_followup_probability():
    rows = [row("A1", "A", 0, 100)]
    with pytest.raises(ValueError, match="followup_inclusion_probability"):
        MODULE.estimate(
            rows, horizon_days=30, bootstrap=0,
            censoring_adjustment="ipw",
        )


def test_cluster_bootstrap_is_licensed_only_when_cluster_unit_is_declared():
    rows = [
        row("A1", "A", 0, 100, run_id="run-1"),
        row("B1", "B", 0, 100, run_id="run-1"),
        row("C1", "C", 0, 100, run_id="run-2"),
        row("D1", "D", 0, 100, run_id="run-2"),
        row("E1", "E", 10, 20),
        row("F1", "F", 12, 20),
    ]
    edges = [
        {"child_activation_id": "E1", "parent_activation_id": "A1", "weight": 1.0},
        {"child_activation_id": "F1", "parent_activation_id": "C1", "weight": 1.0},
    ]
    result = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=100,
        cluster_field="run_id", seed=11,
    )
    assert result["bootstrap_method"] == "cluster_bootstrap_parent_activations"
    assert result["bootstrap_cluster_field"] == "run_id"
    assert result["bootstrap_cluster_count"] == 2
    assert result["bootstrap_inferential_license"] is True


def test_observation_only_genealogy_json_is_directly_consumable(tmp_path):
    payload = {
        "historical_outcomes_used": False,
        "episodes": [
            row("A1", "A", 0, 100),
            row("B1", "B", 10, 20),
        ],
        "parent_edges": [{
            "child_activation_id": "B1",
            "parent_activation_id": "A1",
            "weight": 1.0,
            "pathway": "social_bridge",
        }],
    }
    path = tmp_path / "genealogy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rows, edges = MODULE._read_genealogy(path)
    result = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0
    )
    assert result["estimate"] == pytest.approx(1.0)
    assert result["estimate_by_pathway"]["social_bridge"] == pytest.approx(1.0)


def test_genealogy_json_fails_closed_without_synthetic_firewall(tmp_path):
    path = tmp_path / "bad_genealogy.json"
    path.write_text(json.dumps({
        "historical_outcomes_used": True,
        "episodes": [],
        "parent_edges": [],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="historical_outcomes_used=false"):
        MODULE._read_genealogy(path)

