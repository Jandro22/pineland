from argparse import Namespace

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
