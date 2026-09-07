import numpy as np

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.execution_views import (
    CopyOnWriteMap,
    SharedArrayHandle,
    build_numeric_state_view,
    deserialize_particle,
    locality_adjacency_matrix,
    read_compute_artifact,
    serialize_particle,
    write_compute_artifact,
)


def test_copy_on_write_overlay_isolates_sibling_particle_mutations():
    parent = CopyOnWriteMap({"a": 1, "b": 2})
    first = parent.fork()
    second = parent.fork()
    first["a"] = 10
    del first["b"]
    second["b"] = 20
    assert first.materialize() == {"a": 10}
    assert second.materialize() == {"a": 1, "b": 20}
    assert parent.materialize() == {"a": 1, "b": 2}


def test_numeric_state_view_round_trips_person_and_csr_identity():
    world = generate_pineland(
        SimulationConfig(agent_count=60, locality_count=17, seed=995)
    )
    view = build_numeric_state_view(world)
    assert len(view.person_ids) == len(world.persons)
    for index, person_id in enumerate(view.person_ids):
        person = world.persons[person_id]
        assert view.person_weight[index] == person.weight
        neighbors = {
            view.person_ids[position]
            for position in view.social_indices[
                view.social_indptr[index]:view.social_indptr[index + 1]
            ]
        }
        assert neighbors == set(world.social_neighbors.get(person_id, ()))


def test_shared_static_adjacency_array_round_trip():
    world = generate_pineland(
        SimulationConfig(agent_count=30, locality_count=17, seed=996)
    )
    _, matrix = locality_adjacency_matrix(world)
    handle = SharedArrayHandle.create(matrix)
    try:
        block, shared = handle.descriptor().attach()
        try:
            assert np.array_equal(shared, matrix)
            assert shared.flags.writeable is False
        finally:
            block.close()
    finally:
        handle.unlink()


def test_compute_artifact_is_npz_not_archival_json(tmp_path):
    path = tmp_path / "compute.npz"
    write_compute_artifact(
        path,
        arrays={"x": np.arange(5, dtype=np.int32)},
        metadata={"purpose": "unit-test"},
    )
    arrays, metadata = read_compute_artifact(path)
    assert arrays["x"].tolist() == [0, 1, 2, 3, 4]
    assert metadata["canonical_scientific_artifact"] is False


def test_compact_particle_serializer_round_trip():
    payload = {"state": [1, 2, 3], "lineage": "x"}
    encoded = serialize_particle(payload)
    assert deserialize_particle(encoded) == payload
