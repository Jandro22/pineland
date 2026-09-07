from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "studies"
    / "research_program"
    / "scripts"
    / "run_afghanistan_filtered_prospective_2005.py"
)
SPEC = importlib.util.spec_from_file_location("filtered_2005", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_filtered_runner_uses_only_complete_preboundary_training_weeks():
    observations = MODULE.load_training_observations()
    assert len(observations) == 52
    assert observations[0].week_index == 0
    assert observations[-1].week_index == 51
    assert observations[-1].end_day == 364.0
    assert all(
        observation.end_day <= MODULE.TRAINING_END_DAY
        for observation in observations
    )
    assert all(len(observation.provinces) == 34 for observation in observations)


def test_filtered_likelihood_uses_direct_target_probability_not_measurement_rates():
    assert not hasattr(MODULE, "BernoulliEventObservationModel")
    assert MODULE._jeffreys_branch_probability(0, 3) == 0.125
    assert MODULE._jeffreys_branch_probability(3, 3) == 0.875
    assert MODULE._bernoulli_log_probability(0.75, True) > (
        MODULE._bernoulli_log_probability(0.25, True)
    )


def test_nested_descendant_selection_conditions_on_observed_surface():
    branches = [
        {"AF01", "AF02"},
        {"AF03"},
        {"AF03", "AF04"},
    ]
    selected, mismatch, exact = MODULE._conditioned_branch_index(
        branches,
        frozenset({"AF03"}),
        __import__("random").Random(10),
    )
    assert selected == 1
    assert mismatch == 0
    assert exact is True


def test_nested_descendant_selection_reports_finite_branch_approximation():
    branches = [
        {"AF01", "AF02"},
        {"AF03"},
        {"AF03", "AF04"},
    ]
    selected, mismatch, exact = MODULE._conditioned_branch_index(
        branches,
        frozenset({"AF03", "AF05"}),
        __import__("random").Random(10),
    )
    assert selected in {1, 2}
    assert mismatch == 1
    assert exact is False
