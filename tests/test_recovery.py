import random

import pytest

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.recovery import (
    ObservationChannel,
    ObservationProcessConfig,
    PosteriorPoint,
    evaluate_recovery,
    extract_pineland_latent_state,
    generate_observations,
    direct_hidden_war_channels,
    observation_batch_log_likelihood,
    observation_design_diagnostics,
    posterior_identifiability,
    summarize_posterior_field,
)


def test_observation_likelihood_prefers_the_generating_hidden_state():
    truth = {
        "A": {"insurgent.physical": 0.8},
        "B": {"insurgent.physical": 0.2},
    }
    wrong = {
        "A": {"insurgent.physical": 0.1},
        "B": {"insurgent.physical": 0.9},
    }
    channel = ObservationChannel(
        "physical",
        (("insurgent.physical", 1.0),),
        measurement_sd=0.05,
        reporting_probability=1.0,
    )
    observations = generate_observations(
        truth,
        state_time=7.0,
        channels=(channel,),
        process=ObservationProcessConfig(
            geolocation_error_probability=0.0,
            maximum_delay_days=0.0,
        ),
        adjacency={"A": ("B",), "B": ("A",)},
        rng=random.Random(4),
    )
    assert len(observations) == 2
    true_score = observation_batch_log_likelihood(
        truth,
        observations,
        channels=(channel,),
        adjacency={"A": ("B",), "B": ("A",)},
    )
    wrong_score = observation_batch_log_likelihood(
        wrong,
        observations,
        channels=(channel,),
        adjacency={"A": ("B",), "B": ("A",)},
    )
    assert true_score > wrong_score


def test_spatial_likelihood_can_account_for_geolocation_error():
    state = {
        "A": {"x": 0.9},
        "B": {"x": 0.1},
    }
    channel = ObservationChannel(
        "x-report",
        (("x", 1.0),),
        measurement_sd=0.04,
        reporting_probability=1.0,
    )
    observations = generate_observations(
        state,
        state_time=0.0,
        channels=(channel,),
        process=ObservationProcessConfig(
            geolocation_error_probability=1.0,
            maximum_delay_days=0.0,
        ),
        adjacency={"A": ("B",), "B": ("A",)},
        rng=random.Random(10),
    )
    mixture = observation_batch_log_likelihood(
        state,
        observations,
        channels=(channel,),
        adjacency={"A": ("B",), "B": ("A",)},
        assumed_geolocation_error_probability=1.0,
    )
    exact = observation_batch_log_likelihood(
        state,
        observations,
        channels=(channel,),
        adjacency={"A": ("B",), "B": ("A",)},
        assumed_geolocation_error_probability=0.0,
    )
    assert mixture > exact
    assert all(observation.geolocation_error for observation in observations)


def test_posterior_summary_reports_calibrated_intervals_and_failures():
    truth = {"A": {"x": 0.5}}
    fields = [
        {"A": {"x": 0.4}},
        {"A": {"x": 0.5}},
        {"A": {"x": 0.6}},
    ]
    points = summarize_posterior_field(
        truth,
        fields,
        [0.25, 0.5, 0.25],
        time=7.0,
    )
    assert len(points) == 1
    assert points[0].mean == pytest.approx(0.5)
    metrics = evaluate_recovery(points)
    assert metrics.rmse == pytest.approx(0.0)
    assert metrics.coverage_90 == 1.0
    assert metrics.confidently_wrong_rate == 0.0


def test_identifiability_flags_posterior_collinearity():
    fields = [
        {"A": {"x": 0.1, "y": 0.2}},
        {"A": {"x": 0.3, "y": 0.6}},
        {"A": {"x": 0.5, "y": 1.0}},
    ]
    report = posterior_identifiability(
        fields,
        [1 / 3, 1 / 3, 1 / 3],
        variables=("x", "y"),
        correlation_threshold=0.95,
    )
    assert len(report["warning_pairs"]) == 1
    assert report["warning_pairs"][0]["left"] == "x"
    assert report["warning_pairs"][0]["right"] == "y"


def test_live_pineland_truth_projection_contains_control_and_organization_state():
    world = generate_pineland(SimulationConfig(
        seed=19,
        agent_count=60,
        locality_count=17,
        horizon_days=1,
    ))
    field = extract_pineland_latent_state(world)
    assert len(field) == 17
    row = next(iter(field.values()))
    assert "government.administrative" in row
    assert "insurgent.physical" in row
    assert "insurgent.foothold" in row
    assert "insurgent.embeddedness" in row
    assert "insurgent.fighter_capacity" in row
    assert "insurgent.supply_capacity" in row
    assert all(0.0 <= value <= 1.0 for value in row.values())


def test_change_detection_reports_non_detection_instead_of_hiding_it():
    points = [
        PosteriorPoint(0, "A", "x", 0.1, 0.1, 0.1, 0.05, 0.15, 0.0, 0.2, 0.0, 0.2, 0.05),
        PosteriorPoint(7, "A", "x", 0.5, 0.12, 0.12, 0.07, 0.17, 0.02, 0.22, 0.02, 0.22, 0.05),
        PosteriorPoint(14, "A", "x", 0.6, 0.15, 0.15, 0.10, 0.20, 0.05, 0.25, 0.05, 0.25, 0.05),
    ]
    metrics = evaluate_recovery(points, change_threshold=0.2)
    assert metrics.change_events == 1
    assert metrics.detected_change_events == 0
    assert metrics.change_detection_rate == 0.0
    assert metrics.mean_detection_lag_days is None


def test_observation_design_reports_rank_deficiency_and_unobserved_variables():
    channels = (
        ObservationChannel("a", (("x", 1.0),), measurement_sd=0.1),
        ObservationChannel("b", (("x", 1.0), ("y", 1.0)), measurement_sd=0.1),
    )
    report = observation_design_diagnostics(channels, ("x", "y", "z"))
    assert report["snapshot_design_rank"] == 2
    assert report["snapshot_nullity"] == 1
    assert report["full_snapshot_identification_possible"] is False
    assert report["snapshot_unobserved_variables"] == ["z"]


def test_direct_oracle_measurement_design_is_full_rank():
    variables = ("a", "b", "c")
    report = observation_design_diagnostics(
        direct_hidden_war_channels(variables), variables
    )
    assert report["snapshot_design_rank"] == 3
    assert report["snapshot_nullity"] == 0
    assert report["full_snapshot_identification_possible"] is True


def test_geographic_reporting_bias_changes_collection_probability():
    state = {"A": {"x": 0.5}, "B": {"x": 0.5}}
    channel = ObservationChannel(
        "x", (("x", 1.0),), measurement_sd=0.1, reporting_probability=0.5
    )
    observations = generate_observations(
        state,
        state_time=0.0,
        channels=(channel,),
        process=ObservationProcessConfig(
            geographic_reporting_bias_strength=1.0,
            maximum_delay_days=0.0,
        ),
        adjacency={"A": ("B",), "B": ("A",)},
        rng=random.Random(2),
        unit_reporting_multipliers={"A": 0.0, "B": 2.0},
    )
    assert all(observation.true_unit_id == "B" for observation in observations)
