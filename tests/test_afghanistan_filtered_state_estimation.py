from __future__ import annotations

import importlib.util
from dataclasses import dataclass
import math
from pathlib import Path
import random
import sys
from unittest.mock import patch


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


@dataclass
class DummyParticleState:
    value: int
    lineage_id: str

    def fork(self, child_index: int):
        return DummyParticleState(
            self.value,
            f"{self.lineage_id}.{child_index}",
        )


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


def test_training_restart_round_trip_selects_latest_valid_boundary(tmp_path):
    filter_ = MODULE.SequentialParticleFilter(
        [MODULE.Particle("a", math.log(0.6)), MODULE.Particle("b", math.log(0.4))],
        transition=lambda state, time: None,
        log_likelihood=lambda state, observation: 0.0,
        rng=random.Random(11),
        allowed_split="training",
    )
    filter_._root_ancestors = [0, 1]
    filter_.nested_propagator_diagnostics = {
        "nested_propagation_calls": 8,
        "exact_descendant_match_calls": 2,
        "mean_minimum_descendant_hamming_mismatch": 1.25,
        "maximum_minimum_descendant_hamming_mismatch": 3,
    }
    cache_key = {
        "schema_version": MODULE.POSTERIOR_CACHE_SCHEMA,
        "test": "restart-roundtrip",
    }
    filter_.last_time = 28.0
    MODULE._save_training_restart(
        tmp_path,
        cache_key,
        filter_,
        completed_week_index=3,
    )
    filter_.last_time = 91.0
    latest_manifest, _ = MODULE._save_training_restart(
        tmp_path,
        cache_key,
        filter_,
        completed_week_index=12,
    )
    restored, manifest, completed_week = MODULE._load_latest_training_restart(
        tmp_path,
        cache_key,
        filter_seed=27,
    )
    assert manifest == latest_manifest
    assert completed_week == 12
    assert restored is not None
    assert restored.last_time == 91.0
    assert restored.frozen is False
    assert MODULE.particle_weights(restored.particles) == [0.6, 0.4]
    assert restored.nested_propagator_diagnostics[
        "nested_propagation_calls"
    ] == 8


def test_training_restart_resume_matches_uninterrupted_filter(tmp_path):
    observations = [
        MODULE.ProvinceWeekObservation(
            start_day=float(index),
            end_day=float(index + 1),
            week_index=index,
            active_provinces=frozenset(),
            provinces=("P1",),
        )
        for index in range(3)
    ]

    def fake_nested_job(job):
        state, _, observation, _, _ = job
        next_state = DummyParticleState(
            state.value + observation.week_index + 1,
            state.lineage_id,
        )
        likelihood = -abs(next_state.value - 3) * 0.1
        return next_state, likelihood, {
            "nested_propagation_calls": 1,
            "exact_descendant_match_calls": 1,
            "mean_minimum_descendant_hamming_mismatch": 0.0,
            "maximum_minimum_descendant_hamming_mismatch": 0,
        }

    def initial_particles():
        return [
            MODULE.Particle(DummyParticleState(0, "a")),
            MODULE.Particle(DummyParticleState(1, "b")),
        ]

    cache_key = {
        "schema_version": MODULE.POSTERIOR_CACHE_SCHEMA,
        "test": "resume-equivalence",
    }
    with patch.object(MODULE, "_nested_particle_job", side_effect=fake_nested_job):
        uninterrupted = MODULE.run_training_filter(
            initial_particles(),
            observations,
            filter_seed=77,
            likelihood_branches=1,
            workers=1,
        )
        MODULE.run_training_filter(
            initial_particles(),
            observations[:1],
            filter_seed=77,
            likelihood_branches=1,
            workers=1,
            restart_cache_dir=tmp_path,
            restart_cache_key=cache_key,
            restart_every_weeks=1,
        )
        resumed_filter, _, completed_week = MODULE._load_latest_training_restart(
            tmp_path,
            cache_key,
            filter_seed=77,
        )
        assert completed_week == 0
        resumed = MODULE.run_training_filter(
            [],
            observations,
            filter_seed=77,
            likelihood_branches=1,
            workers=1,
            resume_filter=resumed_filter,
        )

    assert [
        (particle.state.value, particle.state.lineage_id, particle.log_weight)
        for particle in resumed.particles
    ] == [
        (particle.state.value, particle.state.lineage_id, particle.log_weight)
        for particle in uninterrupted.particles
    ]
    assert resumed.history == uninterrupted.history
    assert resumed._root_ancestors == uninterrupted._root_ancestors
    assert resumed._resampling_events == uninterrupted._resampling_events
    assert resumed.nested_propagator_diagnostics == (
        uninterrupted.nested_propagator_diagnostics
    )
