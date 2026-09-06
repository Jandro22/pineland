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


def test_filtered_observation_operator_has_explicit_nondegenerate_emissions():
    model = MODULE.BernoulliEventObservationModel()
    assert model.log_probability(True, True) > model.log_probability(True, False)
    assert model.log_probability(False, False) > model.log_probability(False, True)
