from argparse import Namespace

import pytest

from studies.research_program.scripts.run_research_v1_repeated_snapshot_recovery import (
    _paired_summary,
)
from studies.research_program.scripts.run_research_v1_repeated_dynamic_recovery import (
    _aggregate as _dynamic_aggregate,
    build_parser as build_dynamic_parser,
)

from studies.research_program.scripts.run_research_v1_synthetic_recovery import (
    DEFAULT_VARIABLES,
    build_parser,
    _run_no_assimilation_baseline,
)


def test_full_rank_profile_has_no_unobserved_subset_metric():
    truth = {
        "A": {variable: 0.5 for variable in DEFAULT_VARIABLES},
    }
    particle = {
        "A": {variable: 0.5 for variable in DEFAULT_VARIABLES},
    }
    args = Namespace(
        days=7.0,
        interval_days=7.0,
        observation_profile="direct-oracle",
        reporting_multiplier=1.0,
        geographic_reporting_bias_strength=0.0,
    )
    result = _run_no_assimilation_baseline(
        {0.0: [particle], 7.0: [particle]},
        {0.0: truth, 7.0: truth},
        args,
    )

    assert result["metric_groups"]["observation_linked_targets"] is not None
    assert result["metric_groups"]["snapshot_unobserved_targets"] is None


def test_parser_accepts_matched_localization_radius_sweep():
    args = build_parser().parse_args([
        "--localization-radius-sweep", "0", "1", "2",
    ])
    assert args.localization_radius_sweep == [0, 1, 2]


def test_parser_accepts_component_state_localization():
    args = build_parser().parse_args(["--state-localization", "component"])
    assert args.state_localization == "component"


def test_repeated_snapshot_summary_uses_world_paired_mse():
    rows = [
        {
            "prior_mse": 4.0,
            "posterior_mse": 1.0,
            "posterior_metrics": {
                "coverage_90": 0.9,
                "confidently_wrong_rate": 0.1,
            },
            "prior_metrics": {"coverage_90": 0.8},
            "mean_local_ess_fraction": 0.5,
            "minimum_local_ess_fraction": 0.25,
        },
        {
            "prior_mse": 1.0,
            "posterior_mse": 2.0,
            "posterior_metrics": {
                "coverage_90": 0.8,
                "confidently_wrong_rate": 0.2,
            },
            "prior_metrics": {"coverage_90": 0.7},
            "mean_local_ess_fraction": 0.75,
            "minimum_local_ess_fraction": 0.5,
        },
    ]
    result = _paired_summary(rows)
    assert result["prior_mse"] == pytest.approx(2.5)
    assert result["posterior_mse"] == pytest.approx(1.5)
    assert result["mse_ratio_vs_prior"] == pytest.approx(0.6)
    assert result["mse_information_gain_fraction"] == pytest.approx(0.4)
    assert result["world_win_rate"] == pytest.approx(0.5)


def test_repeated_dynamic_defaults_to_component_localization():
    args = build_dynamic_parser().parse_args([])
    assert args.state_localization == "component"
    assert args.localization_radius == 0


def test_repeated_dynamic_summary_is_world_paired():
    rows = [
        {
            "prior_mse": 4.0,
            "posterior_mse": 2.0,
            "posterior_coverage_90": 0.9,
            "prior_coverage_90": 0.8,
            "posterior_confidently_wrong_rate": 0.1,
            "mean_ess": 8.0,
            "minimum_ess": 4.0,
            "particles": 16,
        },
        {
            "prior_mse": 2.0,
            "posterior_mse": 1.0,
            "posterior_coverage_90": 0.8,
            "prior_coverage_90": 0.7,
            "posterior_confidently_wrong_rate": 0.2,
            "mean_ess": 12.0,
            "minimum_ess": 2.0,
            "particles": 16,
        },
    ]
    result = _dynamic_aggregate(rows)
    assert result["mse_ratio_vs_prior"] == pytest.approx(0.5)
    assert result["mse_information_gain_fraction"] == pytest.approx(0.5)
    assert result["world_win_rate"] == 1.0
