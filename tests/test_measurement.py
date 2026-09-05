from __future__ import annotations

import json
from pathlib import Path

import importlib.util
import pytest

from pineland_sim.entities import CONTROL_DIMENSIONS, ControlVector


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "studies" / "afghanistan_2004_2021" / "config" / "control_observation_model.json"
MODULE_PATH = ROOT / "studies" / "afghanistan_2004_2021" / "scripts" / "control_observation.py"
MODULE_SPEC = importlib.util.spec_from_file_location("control_observation", MODULE_PATH)
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(MODULE)
OrdinalControlObservationModel = MODULE.OrdinalControlObservationModel
SIGAR_CATEGORIES = MODULE.SIGAR_CATEGORIES


def model() -> OrdinalControlObservationModel:
    return OrdinalControlObservationModel.from_dict(json.loads(SPEC.read_text(encoding="utf-8")))


def test_control_operator_is_relative_and_monotonic():
    operator = model()
    low = ControlVector(*([0.2] * 7))
    high = ControlVector(*([0.8] * 7))
    assert operator.latent_score(low, high) < 0.5
    assert operator.latent_score(high, low) > 0.5
    assert operator.expected_index(high, low) > operator.expected_index(low, high)


def test_control_operator_does_not_turn_epsilon_advantage_into_full_control():
    """Absolute reach must matter, not only the government/insurgent ratio.

    A ratio-only score maps 0.01 versus 0.00 to the same latent value as
    1.00 versus 0.00.  That is incompatible with an ordinal *control* label:
    vanishing state reach cannot by itself imply GIRoA Control merely because
    modeled insurgent reach is exactly zero.
    """
    operator = model()
    absent = ControlVector(*([0.0] * 7))
    epsilon_government = ControlVector(*([0.01] * 7))
    full_government = ControlVector(*([1.0] * 7))
    assert 0.5 < operator.latent_score(epsilon_government, absent) < 0.55
    assert operator.latent_score(full_government, absent) == pytest.approx(1.0)


def test_control_operator_is_actor_symmetric_around_contested():
    operator = model()
    government = ControlVector(0.9, 0.7, 0.5, 0.8, 0.2, 0.6, 0.4)
    insurgent = ControlVector(0.1, 0.3, 0.4, 0.2, 0.6, 0.2, 0.5)
    assert operator.latent_score(government, insurgent) + operator.latent_score(
        insurgent, government
    ) == pytest.approx(1.0)


def test_probabilities_are_normalized_and_cover_sigar_categories():
    probabilities = model().probabilities(ControlVector(*([0.7] * 7)), ControlVector(*([0.3] * 7)))
    assert tuple(probabilities) == SIGAR_CATEGORIES
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert all(0 <= value <= 1 for value in probabilities.values())


def test_synthetic_category_recovery_passes_declared_gate():
    result = model().synthetic_recovery(samples_per_category=500)
    assert result["status"] == "synthetic_observation_recovery_not_historical_fit"
    assert result["accuracy"] >= 0.75


def test_invalid_operator_fails_closed():
    with pytest.raises(ValueError):
        OrdinalControlObservationModel(
            weights={dimension: 1.0 for dimension in CONTROL_DIMENSIONS[:-1]},
            cutpoints=(0.1, 0.3, 0.6, 0.9),
        )
