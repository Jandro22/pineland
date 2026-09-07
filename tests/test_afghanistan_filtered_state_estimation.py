from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import random
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


def test_compact_mask_descendant_selection_is_exactly_set_equivalent():
    provinces = ("AF01", "AF02", "AF03", "AF04", "AF05")
    bits = {province: 1 << index for index, province in enumerate(provinces)}
    branches = [
        {"AF01", "AF02"},
        {"AF03"},
        {"AF03", "AF04"},
    ]
    observed = frozenset({"AF03", "AF05"})
    masks = [sum(bits[item] for item in branch) for branch in branches]
    observed_mask = sum(bits[item] for item in observed)
    random_module = __import__("random")
    set_result = MODULE._conditioned_branch_index(
        branches, observed, random_module.Random(10)
    )
    mask_result = MODULE._conditioned_branch_mask_index(
        masks, observed_mask, random_module.Random(10)
    )
    assert mask_result == set_result


def test_training_observation_precomputes_compact_province_surface():
    observation = MODULE.load_training_observations()[0]
    assert len(observation.province_bits) == 34
    assert observation.active_mask.bit_count() == len(observation.active_provinces)


def test_compact_forecast_masks_round_trip_to_cell_surface():
    provinces = ("AF01", "AF02", "AF03")
    bits = {province: 1 << index for index, province in enumerate(provinces)}
    masks = {
        53: bits["AF01"] | bits["AF03"],
        54: bits["AF02"],
    }
    assert MODULE._mask_cells(masks, provinces, bits) == {
        ("AF01", 53),
        ("AF03", 53),
        ("AF02", 54),
    }


def test_worker_state_reattachment_preserves_posterior_weights():
    filter_ = MODULE.SequentialParticleFilter(
        [MODULE.Particle("old-a", math.log(0.8)), MODULE.Particle("old-b", math.log(0.2))],
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(2),
        allowed_split="training",
    )
    MODULE._reattach_particle_states(filter_, ["new-a", "new-b"])
    assert [particle.state for particle in filter_.particles] == ["new-a", "new-b"]
    weights = MODULE.particle_weights(filter_.particles)
    assert weights == [0.8, 0.2]


def test_posterior_cache_round_trip_preserves_filter_state(tmp_path):
    filter_ = MODULE.SequentialParticleFilter(
        [MODULE.Particle("a", math.log(0.7)), MODULE.Particle("b", math.log(0.3))],
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(9),
        allowed_split="training",
    )
    filter_.last_time = 364.0
    filter_.frozen = True
    filter_._root_ancestors = [0, 1]
    filter_.nested_propagator_diagnostics = {"nested_propagation_calls": 4}
    cache_key = {"schema_version": MODULE.POSTERIOR_CACHE_SCHEMA, "test": "roundtrip"}
    manifest_path, payload_path = MODULE._save_posterior_cache(
        tmp_path, cache_key, filter_
    )
    assert manifest_path.exists()
    assert payload_path.exists()
    restored, restored_manifest = MODULE._load_posterior_cache(
        tmp_path, cache_key, filter_seed=26
    )
    assert restored_manifest == manifest_path
    assert restored.last_time == 364.0
    assert restored.frozen is True
    assert MODULE.particle_weights(restored.particles) == [0.7, 0.3]
    assert restored.nested_propagator_diagnostics == {
        "nested_propagation_calls": 4
    }
