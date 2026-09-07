import json
import math
import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from pineland_sim import (
    AssimilationObservation,
    Particle,
    SequentialParticleFilter,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.entities import OrganizationKind
from pineland_sim.state_estimation import (
    bounded_process_map,
    Particle,
    PersistentParticlePool,
    effective_sample_size,
    measurement_update,
    normalize_log_weights,
    particle_weights,
    resample_if_degenerate,
    systematic_resample_indices,
)


def _resident_test_propagate(state, time, observation):
    return state + observation, 0.0, {"time": time}


def _resident_test_fork(state, child_index):
    return state + 1000 * child_index


def _resident_test_summary(state):
    return {"value": state}


def test_bounded_process_map_preserves_order_with_a_small_submission_window():
    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(bounded_process_map(
            executor,
            lambda value: value * value,
            range(8),
            max_in_flight=2,
        ))
    assert values == [value * value for value in range(8)]


def test_persistent_particle_pool_keeps_parent_forks_on_their_worker():
    with PersistentParticlePool(
        [0, 1, 2, 3],
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
    ) as pool:
        assert [result[0] for result in pool.propagate(7.0, 10)] == list(range(4))
        pool.resample([3, 3, 0, 1])
        assert pool.snapshot() == [13, 1013, 2010, 3011]


def test_persistent_particle_pool_persists_and_reloads_worker_side(tmp_path):
    with PersistentParticlePool(
        [4, 5, 6, 7],
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
        summarize_state=_resident_test_summary,
    ) as pool:
        rows = pool.persist_states(str(tmp_path), "resident")
        assert [row["slot"] for row in rows] == [0, 1, 2, 3]
        assert all(row["bytes"] > 0 for row in rows)
        paths = [str(row["path"]) for row in rows]

    with PersistentParticlePool(
        state_paths=paths,
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
        summarize_state=_resident_test_summary,
    ) as pool:
        assert pool.summarize() == [
            (0, {"value": 4}),
            (1, {"value": 5}),
            (2, {"value": 6}),
            (3, {"value": 7}),
        ]


def test_persistent_particle_pool_profiled_propagation_reports_workers():
    with PersistentParticlePool(
        [0, 1, 2, 3],
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
    ) as pool:
        results, workers = pool.propagate_profiled(7.0, 10)
        assert [result[0] for result in results] == list(range(4))
        assert len(workers) == 2
        assert sum(item["state_count"] for item in workers) == 4
        assert all(item["wall_seconds"] >= 0 for item in workers)
        assert pool.cpu_seconds() >= 0


def test_persistent_particle_pool_reports_assignment_imbalance_after_resampling():
    with PersistentParticlePool(
        [0, 1, 2, 3],
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
    ) as pool:
        assert pool.assignment_counts() == [2, 2]
        pool.resample([3, 3, 0, 1])
        assert pool.assignment_counts() == [1, 3]


def test_persistent_particle_pool_balanced_resampling_preserves_children():
    with PersistentParticlePool(
        [0, 1, 2, 3],
        propagate=_resident_test_propagate,
        fork_state=_resident_test_fork,
        workers=2,
    ) as pool:
        transport = pool.resample_balanced([3, 3, 3, 3])
        assert pool.assignment_counts() == [2, 2]
        assert transport["migrated_particles"] == 2
        # Every child is still forked from parent value 3 using the child's
        # global slot index, independent of where the child is resident.
        assert pool.snapshot() == [3, 1003, 2003, 3003]


def test_log_weight_normalization_and_ess_are_numerically_stable():
    weights = normalize_log_weights([-10000.0, -10001.0, -10002.0])
    assert sum(weights) == pytest.approx(1.0)
    assert weights[0] > weights[1] > weights[2]
    assert effective_sample_size([.25, .25, .25, .25]) == pytest.approx(4.0)
    assert effective_sample_size([1.0, 0.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_systematic_resampling_is_reproducible():
    weights = [.05, .10, .15, .70]
    first = systematic_resample_indices(weights, random.Random(42))
    second = systematic_resample_indices(weights, random.Random(42))
    assert first == second
    assert first.count(3) >= 2


def test_identical_twin_partial_observation_recovers_hidden_pineland_state():
    config = SimulationConfig(
        seed=2026090609, agent_count=120, locality_count=17, horizon_days=1
    )
    base = generate_pineland(config)
    focal = next(
        formation for formation in base.formations.values()
        if base.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    )
    candidates = sorted(base.localities)[:12]
    true_locality = candidates[7]
    config_before = json.dumps(base.config.to_dict(), sort_keys=True)

    particles = []
    for locality_id in candidates:
        state = base.clone()
        formation = state.formations[focal.formation_id]
        formation.locality_id = locality_id
        zones = [
            zone for zone in state.microzones.values()
            if zone.locality_id == locality_id
        ]
        formation.current_microzone_id = max(
            zones, key=lambda zone: zone.population_share
        ).microzone_id
        particles.append(Particle(state))

    def location_report_log_likelihood(state, observed_locality):
        predicted = state.formations[focal.formation_id].locality_id
        if predicted == observed_locality:
            return math.log(.90)
        return math.log(.10 / (len(candidates) - 1))

    diagnostics = measurement_update(
        particles, true_locality, location_report_log_likelihood
    )
    posterior = particle_weights(particles)
    winner = max(range(len(posterior)), key=posterior.__getitem__)
    assert candidates[winner] == true_locality
    assert posterior[winner] == pytest.approx(.90)
    assert diagnostics["posterior_ess"] < diagnostics["prior_ess"]

    resampled, resampling = resample_if_degenerate(
        particles, random.Random(20260906), ess_fraction=.75
    )
    assert resampling["resampled"] is True
    assert sum(
        particle.state.formations[focal.formation_id].locality_id == true_locality
        for particle in resampled
    ) >= 8
    assert all(
        json.dumps(particle.state.config.to_dict(), sort_keys=True) == config_before
        for particle in resampled
    )


def test_live_simulation_particle_carries_scheduler_and_forks_future_rng_stream():
    config = SimulationConfig(
        seed=2026090610, agent_count=120, locality_count=17, horizon_days=2
    )
    simulation = Simulation(generate_pineland(config))
    simulation.initialize()
    particle = SimulationParticle(simulation)

    first = particle.fork(0)
    second = particle.fork(1)

    assert len(first.simulation.scheduler) == len(simulation.scheduler)
    assert first.time == simulation.world.time == second.time
    assert first.simulation.stream_namespace != second.simulation.stream_namespace
    assert first.simulation.processes.stream_namespace != second.simulation.processes.stream_namespace
    assert first.simulation.rng.getstate() != second.simulation.rng.getstate()


def test_training_only_filter_rejects_holdout_before_advancing_particles():
    particles = [Particle({"location": location}) for location in ("A", "B", "C")]
    advanced = []

    def transition(state, time):
        advanced.append((state["location"], time))

    def likelihood(state, observed):
        return math.log(.9 if state["location"] == observed else .05)

    filter_ = SequentialParticleFilter(
        particles,
        transition=transition,
        log_likelihood=likelihood,
        rng=random.Random(20260906),
        ess_fraction=1.0,
    )
    filter_.assimilate(
        AssimilationObservation(7.0, "B", split="training", observation_id="w1")
    )
    count_before = len(advanced)
    with pytest.raises(ValueError, match="refuses observations"):
        filter_.assimilate(
            AssimilationObservation(14.0, "A", split="holdout", observation_id="w2")
        )
    assert len(advanced) == count_before
    assert filter_.last_time == 7.0


def test_precomputed_propagation_uses_normal_weight_and_resampling_path():
    particles = [Particle({"value": value}) for value in (0, 1, 2, 3)]
    filter_ = SequentialParticleFilter(
        particles,
        transition=lambda state, time: None,
        log_likelihood=lambda state, observed: 0.0,
        rng=random.Random(17),
        ess_fraction=0.1,
    )
    propagated = [
        ({"value": 10}, math.log(.1)),
        ({"value": 11}, math.log(.2)),
        ({"value": 12}, math.log(.3)),
        ({"value": 13}, math.log(.4)),
    ]
    diagnostics = filter_.assimilate_precomputed(
        AssimilationObservation(
            7.0, "unused", split="training", observation_id="precomputed"
        ),
        propagated,
    )
    assert [particle.state["value"] for particle in filter_.particles] == [
        10, 11, 12, 13
    ]
    assert particle_weights(filter_.particles) == pytest.approx([.1, .2, .3, .4])
    assert diagnostics.resampled is False
    assert diagnostics.observation_id == "precomputed"
    assert filter_.last_time == 7.0


def test_synthetic_planted_hotspot_is_recovered_and_improves_forecast_weight():
    """A partial observation must localize a latent hotspot before forecasting."""
    locations = ("A", "B", "C", "D")
    particles = [Particle({"hotspot": location}) for location in locations]
    transitions = []

    def transition(state, time):
        transitions.append((state["hotspot"], time))

    def likelihood(state, observed):
        return math.log(.90 if state["hotspot"] == observed else .10 / 3.0)

    filter_ = SequentialParticleFilter(
        particles,
        transition=transition,
        log_likelihood=likelihood,
        rng=random.Random(2026090615),
        # Keep the posterior weights for the forecast comparison; this test
        # isolates state discrimination from resampling variance.
        ess_fraction=.1,
    )
    filter_.assimilate(
        AssimilationObservation(
            7.0, "C", split="training", observation_id="planted-hotspot"
        )
    )
    posterior = particle_weights(filter_.particles)
    filtered_forecast_weight = sum(
        weight
        for particle, weight in zip(filter_.particles, posterior)
        if particle.state["hotspot"] == "C"
    )
    unfiltered_forecast_weight = 1.0 / len(locations)

    assert filtered_forecast_weight > unfiltered_forecast_weight
    assert filtered_forecast_weight == pytest.approx(.90)
    assert transitions == [(location, 7.0) for location in locations]

    filter_.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        filter_.assimilate(
            AssimilationObservation(14.0, "A", split="training")
        )
