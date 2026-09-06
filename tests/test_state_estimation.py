import json
import math
import random

import pytest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.state_estimation import (
    Particle,
    effective_sample_size,
    measurement_update,
    normalize_log_weights,
    particle_weights,
    resample_if_degenerate,
    systematic_resample_indices,
)


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
