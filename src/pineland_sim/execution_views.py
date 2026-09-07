"""Compact execution views and trusted-local compute artifacts.

These structures are deliberately derived from WorldState. They provide a
stable migration target for vectorized/native/shared-memory backends without
changing the authoritative scientific object model.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
import hashlib
import importlib.util
import json
from multiprocessing import shared_memory
from pathlib import Path
import pickle
import sys
import zlib
from typing import Any
from collections.abc import Iterator, MutableMapping, Mapping

import numpy as np


PARTICLE_SERIALIZATION_SCHEMA = "pineland.particle.execution.v1"
COMPUTE_ARTIFACT_SCHEMA = "pineland.compute.npz.v1"


class CopyOnWriteMap(MutableMapping):
    """Persistent overlay map for future compact particle-state migration.

    Forking seals the parent so children can safely share it. Children write
    only local overlays/tombstones. This is not yet the authoritative
    WorldState storage; it is a tested execution primitive for migrating hot
    mutable dictionaries incrementally.
    """

    def __init__(self, base: Mapping | None = None) -> None:
        self._base = base or {}
        self._overlay: dict[Any, Any] = {}
        self._deleted: set[Any] = set()
        self._sealed = False

    def fork(self) -> "CopyOnWriteMap":
        self._sealed = True
        return CopyOnWriteMap(self)

    def _ensure_mutable(self) -> None:
        if self._sealed:
            raise RuntimeError("cannot mutate a COW parent after forking")

    def __getitem__(self, key):
        if key in self._deleted:
            raise KeyError(key)
        if key in self._overlay:
            return self._overlay[key]
        return self._base[key]

    def __setitem__(self, key, value) -> None:
        self._ensure_mutable()
        self._deleted.discard(key)
        self._overlay[key] = value

    def __delitem__(self, key) -> None:
        self._ensure_mutable()
        if key not in self:
            raise KeyError(key)
        self._overlay.pop(key, None)
        self._deleted.add(key)

    def __iter__(self) -> Iterator:
        keys = set(self._base)
        keys.update(self._overlay)
        keys.difference_update(self._deleted)
        return iter(sorted(keys, key=str))

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def materialize(self) -> dict:
        return {key: self[key] for key in self}


HOT_WORLD_FIELDS = frozenset({
    "persons", "formations", "organizations", "localities", "beliefs",
    "control_beliefs", "presence_beliefs", "node_presence_beliefs",
    "organization_manpower_pools", "organization_manpower_supply_reserves",
    "active_information_relays", "information_relays", "observations",
})
WARM_WORLD_FIELDS = frozenset({
    "patrols", "security_posts", "supply_sources", "supply_shipments",
    "movement_orders", "access_restrictions", "social_communities",
    "foreign_states", "foreign_interventions", "negotiations",
})
COLD_WORLD_FIELDS = frozenset({
    "districts", "geographic_containers", "district_hierarchy", "adjacency",
    "microzones", "physical_edges", "social_edges", "social_neighbors",
})


@dataclass(frozen=True, slots=True)
class NumericStateView:
    """Read-only structure-of-arrays/compact-ID projection."""

    person_ids: tuple[str, ...]
    locality_ids: tuple[str, ...]
    community_ids: tuple[str, ...]
    person_weight: np.ndarray
    person_residence: np.ndarray
    person_community: np.ndarray
    person_armed_fraction: np.ndarray
    person_grievance: np.ndarray
    social_indptr: np.ndarray
    social_indices: np.ndarray


def build_numeric_state_view(world) -> NumericStateView:
    person_ids = (
        world.ordered_person_ids or tuple(sorted(world.persons))
    )
    locality_ids = (
        world.ordered_locality_ids or tuple(sorted(world.localities))
    )
    community_ids = (
        world.ordered_social_community_ids
        or tuple(sorted(world.social_communities))
    )
    person_index = {person_id: index for index, person_id in enumerate(person_ids)}
    locality_index = {
        locality_id: index for index, locality_id in enumerate(locality_ids)
    }
    community_index = {
        community_id: index for index, community_id in enumerate(community_ids)
    }
    person_weight = np.fromiter(
        (world.persons[person_id].weight for person_id in person_ids),
        dtype=np.float64,
        count=len(person_ids),
    )
    person_residence = np.fromiter(
        (
            locality_index[world.persons[person_id].residence_locality_id]
            for person_id in person_ids
        ),
        dtype=np.int32,
        count=len(person_ids),
    )
    person_community = np.fromiter(
        (
            community_index.get(
                world.persons[person_id].community_id, -1
            )
            for person_id in person_ids
        ),
        dtype=np.int32,
        count=len(person_ids),
    )
    person_armed_fraction = np.fromiter(
        (world.persons[person_id].armed_fraction for person_id in person_ids),
        dtype=np.float64,
        count=len(person_ids),
    )
    person_grievance = np.fromiter(
        (world.persons[person_id].grievance for person_id in person_ids),
        dtype=np.float64,
        count=len(person_ids),
    )
    indptr = np.zeros(len(person_ids) + 1, dtype=np.int64)
    flattened: list[int] = []
    for index, person_id in enumerate(person_ids):
        neighbors = sorted(
            person_index[neighbor]
            for neighbor in world.social_neighbors.get(person_id, ())
            if neighbor in person_index
        )
        flattened.extend(neighbors)
        indptr[index + 1] = len(flattened)
    indices = np.asarray(flattened, dtype=np.int32)
    for array in (
        person_weight, person_residence, person_community,
        person_armed_fraction, person_grievance, indptr, indices,
    ):
        array.flags.writeable = False
    return NumericStateView(
        person_ids,
        locality_ids,
        community_ids,
        person_weight,
        person_residence,
        person_community,
        person_armed_fraction,
        person_grievance,
        indptr,
        indices,
    )


def locality_adjacency_matrix(world) -> tuple[tuple[str, ...], np.ndarray]:
    locality_ids = (
        world.ordered_locality_ids or tuple(sorted(world.localities))
    )
    index = {locality_id: i for i, locality_id in enumerate(locality_ids)}
    matrix = np.full(
        (len(locality_ids), len(locality_ids)),
        np.inf,
        dtype=np.float64,
    )
    np.fill_diagonal(matrix, 0.0)
    for first, neighbors in world.adjacency.items():
        i = index[first]
        for second, cost in neighbors.items():
            matrix[i, index[second]] = float(cost)
    return locality_ids, matrix


@dataclass(slots=True)
class SharedArrayHandle:
    """Descriptor for a read-only numeric array in multiprocessing shm."""

    name: str
    shape: tuple[int, ...]
    dtype: str
    owner: bool = False
    _block: Any = None

    @classmethod
    def create(cls, array: np.ndarray) -> "SharedArrayHandle":
        contiguous = np.ascontiguousarray(array)
        block = shared_memory.SharedMemory(create=True, size=contiguous.nbytes)
        view = np.ndarray(
            contiguous.shape, dtype=contiguous.dtype, buffer=block.buf
        )
        view[:] = contiguous
        name = block.name
        return cls(
            name=name,
            shape=tuple(contiguous.shape),
            dtype=contiguous.dtype.str,
            owner=True,
            _block=block,
        )

    def descriptor(self) -> "SharedArrayHandle":
        """Return the pickle-friendly non-owner descriptor for workers."""
        return SharedArrayHandle(
            name=self.name,
            shape=self.shape,
            dtype=self.dtype,
            owner=False,
        )

    def attach(self) -> tuple[shared_memory.SharedMemory, np.ndarray]:
        block = shared_memory.SharedMemory(name=self.name)
        array = np.ndarray(
            self.shape, dtype=np.dtype(self.dtype), buffer=block.buf
        )
        array.flags.writeable = False
        return block, array

    def unlink(self) -> None:
        if not self.owner:
            return
        try:
            block = self._block or shared_memory.SharedMemory(name=self.name)
            block.unlink()
            block.close()
        except FileNotFoundError:
            pass
        self._block = None
        self.owner = False


def serialize_particle(particle, *, compress: bool = True) -> bytes:
    """Trusted-local versioned particle payload; never a publication artifact."""
    raw = pickle.dumps(particle, protocol=pickle.HIGHEST_PROTOCOL)
    payload = zlib.compress(raw, level=3) if compress else raw
    header = {
        "schema": PARTICLE_SERIALIZATION_SCHEMA,
        "compressed": bool(compress),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    encoded = json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded + payload


def deserialize_particle(data: bytes):
    header_length = int.from_bytes(data[:4], "big")
    header = json.loads(data[4:4 + header_length].decode("utf-8"))
    if header.get("schema") != PARTICLE_SERIALIZATION_SCHEMA:
        raise ValueError("particle serialization schema mismatch")
    payload = data[4 + header_length:]
    if hashlib.sha256(payload).hexdigest() != header.get("payload_sha256"):
        raise ValueError("particle serialization hash mismatch")
    raw = zlib.decompress(payload) if header["compressed"] else payload
    return pickle.loads(raw)


def write_compute_artifact(
    path: Path,
    *,
    arrays: dict[str, np.ndarray],
    metadata: dict[str, Any],
) -> Path:
    """Write a compact internal NPZ separate from archival JSON/CSV outputs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema_version": COMPUTE_ARTIFACT_SCHEMA,
        "canonical_scientific_artifact": False,
        **metadata,
    }
    np.savez_compressed(
        path,
        __metadata__=np.asarray(
            json.dumps(meta, sort_keys=True), dtype=np.str_
        ),
        **arrays,
    )
    return path


def read_compute_artifact(path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    with np.load(path, allow_pickle=False) as payload:
        metadata = json.loads(str(payload["__metadata__"]))
        if metadata.get("schema_version") != COMPUTE_ARTIFACT_SCHEMA:
            raise ValueError("compute artifact schema mismatch")
        arrays = {
            key: payload[key].copy()
            for key in payload.files
            if key != "__metadata__"
        }
    return arrays, metadata


def runtime_acceleration_capabilities() -> dict[str, Any]:
    """Cheap capability probe; does not import optional accelerator stacks."""
    gil_probe = getattr(sys, "_is_gil_enabled", None)
    return {
        "numpy": True,
        "numba": importlib.util.find_spec("numba") is not None,
        "cupy": importlib.util.find_spec("cupy") is not None,
        "torch": importlib.util.find_spec("torch") is not None,
        "free_threaded_python": (
            bool(gil_probe is not None and not gil_probe())
        ),
        "python_cache_tag": sys.implementation.cache_tag,
    }


def world_state_tier_counts(world) -> dict[str, int]:
    result = {"hot": 0, "warm": 0, "cold": 0, "other": 0}
    for item in fields(world):
        field_name = item.name
        value = getattr(world, field_name)
        tier = (
            "hot" if field_name in HOT_WORLD_FIELDS
            else "warm" if field_name in WARM_WORLD_FIELDS
            else "cold" if field_name in COLD_WORLD_FIELDS
            else "other"
        )
        try:
            result[tier] += len(value)
        except TypeError:
            result[tier] += 1
    return result
