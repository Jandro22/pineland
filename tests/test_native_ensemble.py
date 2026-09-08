from __future__ import annotations

import math
import random
from unittest.mock import patch

import pytest

from pineland_sim import (
    NativeEnsembleRunner,
    PackedParticleFilter,
    ParticleBatchState,
    Simulation,
    SimulationConfig,
    SimulationParticle,
    generate_pineland,
)
from pineland_sim.action_model import action_attempt_hazard
from pineland_sim.entities import OrganizationKind
from pineland_sim.native_ensemble import GOVERNMENT_SIDE, INSURGENT_SIDE
from pineland_sim.physical import recompute_contested_controls, response_times
from pineland_sim.reproducibility import (
    decision_state_sha256,
    simulation_execution_sha256,
)


def _particle(seed: int = 92001) -> SimulationParticle:
    world = generate_pineland(
        SimulationConfig(
            seed=seed,
            agent_count=100,
            locality_count=17,
            horizon_days=2.0,
            output_mode="ensemble",
        )
    )
    return SimulationParticle(Simulation(world))


def _ensemble_particle(seed: int = 92101) -> SimulationParticle:
    world = generate_pineland(
        SimulationConfig(
            seed=seed,
            agent_count=80,
            locality_count=17,
            horizon_days=2.0,
            output_mode="ensemble",
        )
    )
    simulation = Simulation(world)
    simulation.configure_execution(
        execution_backend="ensemble",
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    return SimulationParticle(simulation)


def _disable_sparse_clocks(batch: ParticleBatchState) -> None:
    for name in ("information", "force_movement", "logistics"):
        for lane in range(batch.particle_count):
            batch.hot_state.next_clocks[name][lane] = math.inf


def test_packed_action_hazard_matches_reference_equation() -> None:
    particle = _particle()
    batch = ParticleBatchState.from_particles([particle])
    hot = batch.hot_state
    world = particle.world
    for organization_id, organization in world.organizations.items():
        if (
            organization.kind
            not in {
                OrganizationKind.INSURGENT,
                OrganizationKind.MILITARY,
                OrganizationKind.POLICE,
                OrganizationKind.FOREIGN,
            }
            or organization.status != "active"
        ):
            continue
        organization_index = hot.organization_index[organization_id]
        for locality_id in batch.topology.locality_ids:
            locality_index = batch.topology.locality_index[locality_id]
            assert hot.action_attempt_hazard(
                0, organization_index, locality_index
            ) == pytest.approx(
                action_attempt_hazard(
                    world, organization_id, locality_id
                ),
                abs=1e-14,
                rel=0,
            )


def test_packed_response_times_use_cached_topology_exactly() -> None:
    particle = _particle(92002)
    batch = ParticleBatchState.from_particles([particle])
    hot = batch.hot_state
    world = particle.world
    for locality_id in batch.topology.locality_ids:
        locality_index = batch.topology.locality_index[locality_id]
        packed = hot.response_times(
            0,
            locality_index,
            GOVERNMENT_SIDE,
            0.0,
            batch.topology,
        )
        reference = response_times(
            world,
            locality_id,
            "government",
            0.0,
            use_runtime_indexes=False,
        )
        for zone_id, expected in reference.items():
            observed = packed[batch.topology.microzone_index[zone_id]]
            if math.isinf(expected):
                assert math.isinf(observed)
            else:
                assert observed == pytest.approx(expected, abs=1e-14, rel=0)


def test_packed_physical_refresh_matches_reference_all_localities() -> None:
    particle = _particle(92003)
    reference = particle.world.clone()
    batch = ParticleBatchState.from_particles([particle])
    hot = batch.hot_state
    packed = hot.recompute_physical_lane(0, 1.0, batch.topology)
    for locality_id in batch.topology.locality_ids:
        locality_index = batch.topology.locality_index[locality_id]
        expected = recompute_contested_controls(
            reference,
            locality_id,
            1.0,
            use_runtime_indexes=False,
        )
        assert packed[locality_index * 2] == pytest.approx(
            expected["government"], abs=1e-14, rel=0
        )
        assert packed[locality_index * 2 + 1] == pytest.approx(
            expected.get("insurgent", 0.0), abs=1e-14, rel=0
        )


def test_hot_gather_copies_mutable_state_clocks_and_rng() -> None:
    first = _particle(92004)
    second = first.fork(1)
    second.world.formations[
        next(iter(second.world.formations))
    ].personnel += 123.0
    batch = ParticleBatchState.from_particles([first, second])
    hot = batch.hot_state
    formation = 0
    first_value = hot.formation_values[
        hot._fv(0, formation, hot.F_PERSONNEL)
    ]
    second_value = hot.formation_values[
        hot._fv(1, formation, hot.F_PERSONNEL)
    ]
    hot.next_clocks["physical_refresh"][0] = 4.0
    hot.next_clocks["physical_refresh"][1] = 7.0
    hot.rng_states["information"] = (("lane0",), ("lane1",))
    batch.gather((1, 0))
    assert hot.formation_values[
        hot._fv(0, formation, hot.F_PERSONNEL)
    ] == second_value
    assert hot.formation_values[
        hot._fv(1, formation, hot.F_PERSONNEL)
    ] == first_value
    assert tuple(hot.next_clocks["physical_refresh"]) == (7.0, 4.0)
    assert hot.rng_states["information"] == (("lane1",), ("lane0",))


def test_native_runner_never_calls_particle_advance_to() -> None:
    first = _particle(92005)
    second = first.fork(1)
    batch = ParticleBatchState.from_particles([first, second])
    _disable_sparse_clocks(batch)
    runner = NativeEnsembleRunner.from_batch(
        batch,
        enable_information_boundary=False,
        scheduler_oracle=False,
    )
    with patch.object(
        SimulationParticle,
        "advance_to",
        side_effect=AssertionError("legacy particle transition called"),
    ):
        batch.advance_to(0.5, runner=runner)
    assert tuple(batch.times) == (0.5, 0.5)
    diagnostics = runner.diagnostics()
    assert diagnostics["particle_advance_to_calls"] == 0
    assert diagnostics["dijkstra_calls"] == 0
    assert diagnostics["physical_refreshes"] > 0
    assert diagnostics["action_opportunities"] > 0


def test_native_runner_exposes_nonmigrated_boundary_instead_of_fallback() -> None:
    particle = _particle(92006)
    batch = ParticleBatchState.from_particles([particle])
    batch.hot_state.next_clocks["information"][0] = math.inf
    batch.hot_state.next_clocks["logistics"][0] = math.inf
    batch.hot_state.next_clocks["force_movement"][0] = 0.0
    runner = NativeEnsembleRunner.from_batch(
        batch,
        enable_information_boundary=False,
        scheduler_oracle=False,
    )
    with pytest.raises(RuntimeError, match="non-migrated"):
        batch.advance_to(0.0, runner=runner)


def test_packed_filter_can_own_native_runner() -> None:
    first = _particle(92007)
    second = first.fork(1)
    filter_ = PackedParticleFilter.from_particles(
        [first, second],
        rng=random.Random(1),
        native_runner=False,
    )
    filter_.enable_native_runner(
        enable_information_boundary=False,
    ).scheduler_oracle = False
    _disable_sparse_clocks(filter_.batch)
    with patch.object(
        SimulationParticle,
        "advance_to",
        side_effect=AssertionError("legacy particle transition called"),
    ):
        update = filter_.update(
            0.25,
            log_likelihood=(0.0, 0.0),
        )
    assert update.time == 0.25
    assert filter_.runner.diagnostics()["particle_advance_to_calls"] == 0


def test_native_runner_rejects_backward_time() -> None:
    particle = _particle(92008)
    batch = ParticleBatchState.from_particles([particle])
    _disable_sparse_clocks(batch)
    runner = NativeEnsembleRunner.from_batch(
        batch,
        enable_information_boundary=False,
        scheduler_oracle=False,
    )
    batch.times[0] = 1.0
    with pytest.raises(ValueError, match="backward"):
        runner.advance(batch, 1.0, 0.5)


def test_scheduler_oracle_matches_reference_world_and_future_execution() -> None:
    reference = _ensemble_particle(92102)
    native = _ensemble_particle(92102)
    batch = ParticleBatchState.from_particles([native])
    runner = NativeEnsembleRunner.from_batch(batch)

    for horizon in (0.25, 0.5, 1.0):
        reference.advance_to(horizon)
        batch.advance_to(horizon, runner=runner)
        batch.synchronize_lane_to_world(0)
        assert decision_state_sha256(native.world) == decision_state_sha256(
            reference.world
        )
        assert simulation_execution_sha256(
            native.simulation,
            lineage_id=native.lineage_id,
        ) == simulation_execution_sha256(
            reference.simulation,
            lineage_id=reference.lineage_id,
        )


def test_scheduler_oracle_retains_dynamically_created_belief_keys() -> None:
    reference = _ensemble_particle(92103)
    native = _ensemble_particle(92103)
    batch = ParticleBatchState.from_particles([native])
    initial_node_keys = set(batch.node_presence_state.keys)
    runner = NativeEnsembleRunner.from_batch(batch)

    reference.advance_to(0.25)
    batch.advance_to(0.25, runner=runner)
    batch.synchronize_lane_to_world(0)

    created = set(native.world.node_presence_beliefs) - initial_node_keys
    assert created
    assert created.issubset(set(batch.node_presence_state.keys))
    assert decision_state_sha256(native.world) == decision_state_sha256(
        reference.world
    )
