"""Promotion tests for the synthetic insurgent portfolio robustness study."""

import json
import math

import pytest

from studies.research_program.scripts.insurgent_portfolio_synthetic_validation import (
    CENTROID_WEIGHTS,
    EXPECTED_DESIGN_POINTS,
    REFERENCE_WEIGHTS,
    SIMPLEX_LATTICE_POINTS,
    run_validation,
    weight_covering_design,
)


@pytest.fixture(scope="module")
def validation_artifact():
    return run_validation(20260905)


def test_preregistered_cover_spans_full_simplex_lattice_and_ex_ante_anchors():
    design = weight_covering_design()
    assert SIMPLEX_LATTICE_POINTS == 286
    assert len(design) == EXPECTED_DESIGN_POINTS == 288
    assert len(set(design)) == len(design)
    assert REFERENCE_WEIGHTS in design
    assert CENTROID_WEIGHTS in design

    vertices = {
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    }
    assert vertices.issubset(set(design))
    assert all(
        all(0.0 <= value <= 1.0 for value in weights)
        and math.isclose(sum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12)
        for weights in design
    )


def test_synthetic_portfolio_meets_every_quantitative_promotion_gate(
    validation_artifact,
):
    artifact = validation_artifact
    assert artifact["promotion"] is True, artifact["failures"]
    assert artifact["failures"] == []
    assert all(artifact["gates"].values())

    stage = artifact["metrics"]["stage_separation"]
    assert stage["pass_rate"] == 1.0
    assert stage["checks"] == EXPECTED_DESIGN_POINTS * 4
    assert stage["max_weight_recovery_error"] <= 1e-9
    assert stage["max_cross_channel_component_change"] <= 1e-9
    assert stage["uncertainty_frontier_cross_effect"] <= 1e-9
    assert stage["frontier_uncertainty_cross_effect"] <= 1e-9
    assert stage["min_active_utility_gain"] > 0.0

    sanctuary = artifact["metrics"]["sanctuary"]
    assert sanctuary["pass_rate"] == 1.0
    assert sanctuary["access_gap"] > 0.0
    assert sanctuary["min_utility_gain"] > 0.0

    route_risk = artifact["metrics"]["route_risk"]
    assert route_risk["pass_rate"] == 1.0
    assert route_risk["min_utility_drop"] > 0.0
    assert route_risk["max_penalty_identity_error"] <= 1e-9

    candidate_stay = artifact["metrics"]["candidate_stay"]
    assert candidate_stay["candidate_sets_identical"]
    assert candidate_stay["stay_available_all"]
    assert candidate_stay["stay_choice_produces_no_order"]
    assert candidate_stay[
        "only_stay_feasible_when_nonlocal_moves_unaffordable"
    ]


def test_validation_artifact_is_compact_synthetic_only_and_json_serializable(
    validation_artifact,
):
    artifact = validation_artifact
    assert artifact["schema_version"] == (
        "pineland.insurgent_portfolio.synthetic_validation.v1"
    )
    assert artifact["provenance"]["synthetic_only"] is True
    assert artifact["provenance"]["historical_outcomes_used"] is False
    assert artifact["provenance"]["tuning_performed"] is False
    assert artifact["design"]["point_count"] == EXPECTED_DESIGN_POINTS

    # The artifact records aggregate causal checks rather than one record per
    # weight vector, keeping study outputs compact and comparison-friendly.
    assert "points" not in artifact["design"]
    payload = json.dumps(artifact, sort_keys=True)
    assert len(payload) < 10_000
