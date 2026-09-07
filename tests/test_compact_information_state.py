from array import array

import pytest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.compact_information_state import (
    CONTROL_STATE_STRIDE,
    CompactPresenceBeliefState,
    CompactControlBeliefState,
    CompactZoneBeliefState,
)
from pineland_sim.entities import ActorBelief, ControlVector, Observation
from pineland_sim.information import fuse_observation
from pineland_sim.native_kernels import (
    available as native_available,
    fuse_control7_batch,
)
from pineland_sim.reproducibility import decision_state_sha256


def test_compact_control_state_is_exact_and_key_order_independent():
    world = generate_pineland(
        SimulationConfig(agent_count=40, locality_count=17, seed=2301)
    )
    compact = CompactControlBeliefState.from_beliefs(world.control_beliefs)
    assert compact.equivalent_to_beliefs(world.control_beliefs)

    reversed_store = CompactControlBeliefState.from_beliefs(
        dict(reversed(tuple(world.control_beliefs.items())))
    )
    assert reversed_store.state_sha256() == compact.state_sha256()


def test_optimized_control_fusion_uses_persistent_rows_and_matches_oracle():
    config = SimulationConfig(
        agent_count=40, locality_count=17, horizon_days=1, seed=2302
    )
    reference = generate_pineland(config)
    optimized = reference.clone()
    Simulation(optimized).configure_execution(execution_backend="optimized")

    locality_id = next(iter(reference.localities))
    value = {
        "formal": 0.2,
        "physical": 0.7,
        "administrative": 0.4,
        "legal": 0.3,
        "fiscal": 0.6,
        "social": 0.5,
        "expected": 0.8,
    }
    observation = Observation(
        observation_id="compact-test",
        target_id="government",
        locality_id=locality_id,
        timestamp=0.0,
        source_id="test-source",
        source_type="patrol",
        observation_type="physical_control",
        estimated_value={"control": value},
        confidence=0.7,
        provenance={},
        observer_actor_id="fdf",
    )
    fuse_observation(
        reference, observation, "fdf", 1.0,
        trust_override=1.0, language_override=1.0,
    )
    fuse_observation(
        optimized, observation, "fdf", 1.0,
        trust_override=1.0, language_override=1.0,
    )

    assert decision_state_sha256(reference) == decision_state_sha256(optimized)
    compact = optimized.compact_control_state
    assert compact is not None
    assert compact.equivalent_to_beliefs(optimized.control_beliefs)
    assert compact.state_sha256() == CompactControlBeliefState.from_beliefs(
        optimized.control_beliefs
    ).state_sha256()


def test_compact_store_can_append_a_new_target_without_reindexing_existing_rows():
    belief = ActorBelief(
        "observer", "L1", ControlVector(*([0.5] * 7)), 0.25, 0.0
    )
    first = ("observer", "government", "L1")
    second = ("observer", "new-target", "L1")
    compact = CompactControlBeliefState.from_beliefs({first: belief})
    first_index = compact.index(first)
    compact.ensure(second, belief)
    assert compact.index(first) == first_index
    assert len(compact.state) == 2 * CONTROL_STATE_STRIDE


def test_optimized_presence_and_zone_rows_match_the_object_oracle_exactly():
    config = SimulationConfig(
        agent_count=40, locality_count=17, horizon_days=1, seed=2303
    )
    reference = generate_pineland(config)
    optimized = reference.clone()
    Simulation(optimized).configure_execution(execution_backend="optimized")

    locality_id = next(iter(reference.localities))
    microzone_id = next(
        zone.microzone_id for zone in reference.microzones.values()
        if zone.locality_id == locality_id
    )
    observation = Observation(
        observation_id="compact-presence-test",
        target_id="insurgent",
        locality_id=locality_id,
        timestamp=0.0,
        source_id="test-source",
        source_type="patrol",
        observation_type="presence",
        estimated_value={
            "presence": 0.8,
            "personnel": 17.0,
            "control": {"physical": 0.65},
        },
        confidence=0.7,
        provenance={},
        observer_actor_id="fdf",
        target_actor_id="insurgent",
        microzone_id=microzone_id,
    )
    for world in (reference, optimized):
        fuse_observation(
            world, observation, "fdf", 1.0,
            trust_override=1.0, language_override=1.0,
        )

    assert decision_state_sha256(reference) == decision_state_sha256(optimized)
    assert optimized.compact_presence_state.equivalent_to_beliefs(
        optimized.presence_beliefs
    )
    assert optimized.compact_node_presence_state.equivalent_to_beliefs(
        optimized.node_presence_beliefs
    )
    assert optimized.compact_zone_state.equivalent_to_beliefs(
        optimized.zone_beliefs
    )
    assert CompactPresenceBeliefState.from_beliefs(
        dict(reversed(tuple(optimized.presence_beliefs.items())))
    ).state_sha256() == optimized.compact_presence_state.state_sha256()
    assert CompactZoneBeliefState.from_beliefs(
        dict(reversed(tuple(optimized.zone_beliefs.items())))
    ).state_sha256() == optimized.compact_zone_state.state_sha256()


def test_compact_information_rows_are_independent_across_particle_clones():
    optimized = generate_pineland(
        SimulationConfig(agent_count=40, locality_count=17, seed=2304)
    )
    Simulation(optimized).configure_execution(execution_backend="optimized")
    clone = optimized.clone()
    key = next(iter(optimized.compact_zone_state.keys))
    clone.compact_zone_state.state[0] += 0.1
    assert clone.compact_zone_state.row(key) != optimized.compact_zone_state.row(key)


@pytest.mark.skipif(not native_available(), reason="native kernel is optional")
def test_native_control_kernel_accepts_persistent_stride_thirteen_rows():
    states = array("d", [0.5] * CONTROL_STATE_STRIDE)
    states[7] = 0.25
    states[8] = 0.0
    states[10] = 0.0
    states[11] = 0.0
    states[12] = 0.73
    indices = array("I", [0])
    times = array("d", [2.0])
    weights = array("d", [0.4])
    observed = array("d", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    assert fuse_control7_batch(
        states,
        1,
        indices,
        times,
        weights,
        observed,
        contradiction_memory_days=10.0,
        contradiction_penalty=0.2,
        state_stride=CONTROL_STATE_STRIDE,
    )
    assert states[12] == pytest.approx(0.73)
    assert states[8] == pytest.approx(2.0)
    assert states[10] == pytest.approx(1.0)
