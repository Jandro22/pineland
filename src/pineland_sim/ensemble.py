"""Numeric ensemble execution primitives.

This module is the migration boundary between the object-oriented scientific
oracle and the high-throughput execution representation.  It intentionally
contains no model equations that are not already present in the reference
modules.  The pieces here provide:

* fixed-width numeric information and relay buffers;
* an immutable, integer-coded source/topology plan;
* leading-particle structure-of-arrays belief state; and
* indexed-gather resampling with optional synchronization to legacy worlds.

The public object model remains available for reference runs, forensic output,
and debugging.  A batch caller can keep only the packed state and use the
native fusion kernels without constructing ``Observation`` or
``InformationRelay`` objects for every event.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass, field
import hashlib
from math import exp, inf
from typing import Any, Iterable, Sequence

from .compact_information_state import (
    CONTROL_STATE_STRIDE,
    PRESENCE_STATE_STRIDE,
    ZONE_STATE_STRIDE,
)
from .entities import CONTROL_DIMENSIONS, ControlVector, Observation, InformationRelay


_NONE = 0
_DETECTION = 1
_CONTROL = 2


class NumericIdTable:
    """Stable string-to-integer dictionary used only at static boundaries."""

    __slots__ = ("values", "indices")

    def __init__(self, values: Iterable[str | None] = ()) -> None:
        self.values: list[str | None] = [None]
        self.indices: dict[str, int] = {}
        for value in values:
            self.code(value)

    def code(self, value: str | None) -> int:
        if value is None:
            return _NONE
        result = self.indices.get(value)
        if result is None:
            result = len(self.values)
            self.values.append(str(value))
            self.indices[str(value)] = result
        return result

    def value(self, code: int) -> str | None:
        if int(code) == _NONE:
            return None
        return self.values[int(code)]

    def clone(self) -> "NumericIdTable":
        result = type(self)()
        result.values = list(self.values)
        result.indices = dict(self.indices)
        return result


class InformationEventBuffer:
    """Fixed-width numeric report rows for one information event.

    All per-row model payload is numeric.  Strings are interned once in
    ``ids`` and represented in the row by unsigned integer codes.  The buffer
    never owns ``Observation`` instances; ``append_observation`` is a
    deliberately named compatibility adapter for tests/export boundaries.
    """

    __slots__ = (
        "ids", "id_to_index", "codes", "observer", "node", "source",
        "source_type", "locality", "microzone", "target_actor",
        "target_formation", "timestamp", "confidence", "quality", "kind",
        "presence", "personnel", "detection_probability", "detected",
        "attribution_confidence", "control", "physical_control", "violence",
    )

    def __init__(self, *, codebook: NumericIdTable | None = None) -> None:
        self.ids = array("Q")
        self.id_to_index: dict[int, int] = {}
        self.codes = codebook or NumericIdTable()
        self.observer = array("I")
        self.node = array("I")
        self.source = array("I")
        self.source_type = array("I")
        self.locality = array("I")
        self.microzone = array("I")
        self.target_actor = array("I")
        self.target_formation = array("I")
        self.timestamp = array("d")
        self.confidence = array("d")
        self.quality = array("d")
        self.kind = array("B")
        self.presence = array("d")
        self.personnel = array("d")
        self.detection_probability = array("d")
        self.detected = array("B")
        self.attribution_confidence = array("d")
        self.control = array("d")
        self.physical_control = array("d")
        self.violence = array("d")

    def __len__(self) -> int:
        return len(self.ids)

    @property
    def row_count(self) -> int:
        return len(self.ids)

    def clear(self) -> None:
        self.__init__(codebook=self.codes)

    def _append_common(
        self,
        sequence: int,
        *,
        observer_id: str | None,
        observer_node_id: str | None,
        source_id: str | None,
        source_type: str,
        locality_id: str,
        microzone_id: str | None,
        target_actor_id: str | None,
        target_formation_id: str | None,
        timestamp: float,
        confidence: float,
        quality: float,
        kind: int,
    ) -> int:
        sequence = int(sequence)
        if sequence in self.id_to_index:
            raise ValueError(f"duplicate numeric observation sequence: {sequence}")
        index = len(self.ids)
        self.ids.append(sequence)
        self.id_to_index[sequence] = index
        self.observer.append(self.codes.code(observer_id))
        self.node.append(self.codes.code(observer_node_id))
        self.source.append(self.codes.code(source_id))
        self.source_type.append(self.codes.code(source_type))
        self.locality.append(self.codes.code(locality_id))
        self.microzone.append(self.codes.code(microzone_id))
        self.target_actor.append(self.codes.code(target_actor_id))
        self.target_formation.append(self.codes.code(target_formation_id))
        self.timestamp.append(float(timestamp))
        self.confidence.append(float(confidence))
        self.quality.append(float(quality))
        self.kind.append(int(kind))
        return index

    def append_detection(
        self,
        sequence: int,
        *,
        observer_id: str | None,
        observer_node_id: str | None,
        source_id: str,
        source_type: str,
        locality_id: str,
        microzone_id: str | None,
        target_actor_id: str | None,
        target_formation_id: str | None,
        timestamp: float,
        confidence: float,
        quality: float,
        presence: float,
        personnel: float,
        detection_probability: float,
        detected: bool,
        attribution_confidence: float,
    ) -> int:
        index = self._append_common(
            sequence,
            observer_id=observer_id,
            observer_node_id=observer_node_id,
            source_id=source_id,
            source_type=source_type,
            locality_id=locality_id,
            microzone_id=microzone_id,
            target_actor_id=target_actor_id,
            target_formation_id=target_formation_id,
            timestamp=timestamp,
            confidence=confidence,
            quality=quality,
            kind=_DETECTION,
        )
        self.presence.append(float(presence))
        self.personnel.append(float(personnel))
        self.detection_probability.append(float(detection_probability))
        self.detected.append(1 if detected else 0)
        self.attribution_confidence.append(float(attribution_confidence))
        self.control.extend((0.0,) * len(CONTROL_DIMENSIONS))
        self.physical_control.append(0.0)
        self.violence.append(0.0)
        return index

    def append_control(
        self,
        sequence: int,
        *,
        observer_id: str | None,
        observer_node_id: str | None,
        source_id: str,
        source_type: str,
        locality_id: str,
        microzone_id: str | None,
        target_actor_id: str | None,
        timestamp: float,
        confidence: float,
        quality: float,
        control: Sequence[float],
        physical_control: float,
        violence: float,
    ) -> int:
        if len(control) != len(CONTROL_DIMENSIONS):
            raise ValueError("control payload must contain seven numeric dimensions")
        index = self._append_common(
            sequence,
            observer_id=observer_id,
            observer_node_id=observer_node_id,
            source_id=source_id,
            source_type=source_type,
            locality_id=locality_id,
            microzone_id=microzone_id,
            target_actor_id=target_actor_id,
            target_formation_id=None,
            timestamp=timestamp,
            confidence=confidence,
            quality=quality,
            kind=_CONTROL,
        )
        self.presence.append(0.0)
        self.personnel.append(0.0)
        self.detection_probability.append(0.0)
        self.detected.append(0)
        self.attribution_confidence.append(0.0)
        self.control.extend(float(value) for value in control)
        self.physical_control.append(float(physical_control))
        self.violence.append(float(violence))
        return index

    def append_observation(self, observation: Observation) -> int:
        """Copy a rich report into numeric storage at an API boundary.

        Optimized kernels should call ``append_detection``/``append_control``
        directly.  This method exists for migration, fixtures, and exact
        object-to-SoA comparisons; it is never used by the native engine.
        """
        value = observation.estimated_value
        if set(value) == {
            "presence", "personnel", "detection_probability", "detected",
            "attribution_confidence",
        }:
            return self.append_detection(
                int(observation.observation_id.removeprefix("OBS")),
                observer_id=observation.observer_actor_id,
                observer_node_id=observation.observer_node_id,
                source_id=observation.source_id,
                source_type=observation.source_type,
                locality_id=observation.locality_id,
                microzone_id=observation.microzone_id,
                target_actor_id=observation.target_actor_id,
                target_formation_id=observation.target_formation_id,
                timestamp=observation.timestamp,
                confidence=observation.confidence,
                quality=observation.quality,
                presence=float(value["presence"]),
                personnel=float(value["personnel"]),
                detection_probability=float(value["detection_probability"]),
                detected=bool(value["detected"]),
                attribution_confidence=float(value["attribution_confidence"]),
            )
        control = value.get("control")
        if isinstance(control, dict):
            ordered = tuple(float(control[name]) for name in CONTROL_DIMENSIONS)
            return self.append_control(
                int(observation.observation_id.removeprefix("OBS")),
                observer_id=observation.observer_actor_id,
                observer_node_id=observation.observer_node_id,
                source_id=observation.source_id,
                source_type=observation.source_type,
                locality_id=observation.locality_id,
                microzone_id=observation.microzone_id,
                target_actor_id=observation.target_actor_id,
                timestamp=observation.timestamp,
                confidence=observation.confidence,
                quality=observation.quality,
                control=ordered,
                physical_control=float(value.get("physical_control", ordered[1])),
                violence=float(value.get("violence", 0.0)),
            )
        raise ValueError("unsupported observation payload for numeric buffer")

    def iter_rows(self):
        """Yield primitive row tuples without allocating model objects."""
        control_width = len(CONTROL_DIMENSIONS)
        for index in range(len(self.ids)):
            offset = index * control_width
            yield (
                int(self.ids[index]),
                int(self.observer[index]), int(self.node[index]),
                int(self.source[index]), int(self.source_type[index]),
                int(self.locality[index]), int(self.microzone[index]),
                int(self.target_actor[index]), int(self.target_formation[index]),
                float(self.timestamp[index]), float(self.confidence[index]),
                float(self.quality[index]), int(self.kind[index]),
                tuple(float(item) for item in self.control[offset:offset + control_width]),
                float(self.presence[index]), float(self.personnel[index]),
                float(self.detection_probability[index]), int(self.detected[index]),
                float(self.attribution_confidence[index]),
                float(self.physical_control[index]), float(self.violence[index]),
            )


class RelayBuffer:
    """Fixed-width numeric relay rows with flattened integer-coded routes."""

    __slots__ = (
        "ids", "id_to_index", "codes", "observation_sequence", "organization",
        "source", "destination", "route_offsets", "route_codes", "sent_at",
        "arrives_at", "reliability", "latency_hours", "status", "delivered_at",
    )

    def __init__(self, *, codebook: NumericIdTable | None = None) -> None:
        self.ids = array("Q")
        self.id_to_index: dict[int, int] = {}
        self.codes = codebook or NumericIdTable()
        self.observation_sequence = array("Q")
        self.organization = array("I")
        self.source = array("I")
        self.destination = array("I")
        self.route_offsets = array("Q", [0])
        self.route_codes = array("I")
        self.sent_at = array("d")
        self.arrives_at = array("d")
        self.reliability = array("d")
        self.latency_hours = array("d")
        self.status = array("B")
        self.delivered_at = array("d")

    def __len__(self) -> int:
        return len(self.ids)

    @staticmethod
    def _status_code(status: str) -> int:
        return {"in_transit": 0, "delivered": 1, "dropped": 2}.get(status, 2)

    def append(
        self,
        sequence: int,
        *,
        observation_sequence: int,
        organization_id: str,
        source_node_id: str,
        destination_node_id: str,
        route: Sequence[str],
        sent_at: float,
        arrives_at: float,
        reliability: float,
        latency_hours: float,
        status: str = "in_transit",
        delivered_at: float | None = None,
    ) -> int:
        sequence = int(sequence)
        if sequence in self.id_to_index:
            raise ValueError(f"duplicate numeric relay sequence: {sequence}")
        index = len(self.ids)
        self.ids.append(sequence)
        self.id_to_index[sequence] = index
        self.observation_sequence.append(int(observation_sequence))
        self.organization.append(self.codes.code(organization_id))
        self.source.append(self.codes.code(source_node_id))
        self.destination.append(self.codes.code(destination_node_id))
        self.route_codes.extend(self.codes.code(item) for item in route)
        self.route_offsets.append(len(self.route_codes))
        self.sent_at.append(float(sent_at))
        self.arrives_at.append(float(arrives_at))
        self.reliability.append(float(reliability))
        self.latency_hours.append(float(latency_hours))
        self.status.append(self._status_code(status))
        self.delivered_at.append(-1.0 if delivered_at is None else float(delivered_at))
        return index

    def route_codes_for(self, index: int) -> tuple[int, ...]:
        start = self.route_offsets[index]
        end = self.route_offsets[index + 1]
        return tuple(self.route_codes[start:end])

    def iter_rows(self):
        for index in range(len(self.ids)):
            yield (
                int(self.ids[index]), int(self.observation_sequence[index]),
                int(self.organization[index]), int(self.source[index]),
                int(self.destination[index]), self.route_codes_for(index),
                float(self.sent_at[index]), float(self.arrives_at[index]),
                float(self.reliability[index]), float(self.latency_hours[index]),
                int(self.status[index]), float(self.delivered_at[index]),
            )


@dataclass(slots=True)
class InformationSourcePlan:
    """Integer-coded background information opportunities."""

    codes: NumericIdTable
    observer: array
    node: array
    source: array
    source_type: array
    locality: array
    target_offsets: array
    target_actor: array
    fingerprint: tuple[Any, ...]

    @classmethod
    def from_world(cls, world: Any) -> "InformationSourcePlan":
        # Importing lazily avoids the information/world import cycle.
        from .information import _target_actors_for_observer

        world.refresh_operational_indexes()
        codes = NumericIdTable()
        observer = array("I")
        node = array("I")
        source = array("I")
        source_type = array("I")
        locality = array("I")
        target_offsets = array("Q", [0])
        target_actor = array("I")

        def add(
            observer_id: str,
            node_id: str | None,
            source_id: str,
            source_kind: str,
            locality_id: str,
        ) -> None:
            observer.append(codes.code(observer_id))
            node.append(codes.code(node_id))
            source.append(codes.code(source_id))
            source_type.append(codes.code(source_kind))
            locality.append(codes.code(locality_id))
            target_actor.extend(
                codes.code(item)
                for item in _target_actors_for_observer(world, observer_id)
            )
            target_offsets.append(len(target_actor))

        # This order intentionally mirrors generate_background_observations.
        for post in sorted(world.security_posts.values(), key=lambda item: item.post_id):
            if post.available_fraction <= 0:
                continue
            formation = world.formations.get(post.formation_id) if post.formation_id else None
            if formation is not None and (formation.moving or formation.available_personnel() <= 0):
                continue
            add(post.organization_id, post.formation_id or post.post_id, post.post_id,
                "fixed_post", post.locality_id)

        for locality_id in world.ordered_locality_ids or tuple(sorted(world.localities)):
            community_ids, _ = world.community_selection_weights(locality_id)
            if not community_ids:
                if "government" in world.organizations:
                    add("government", None, f"ADMIN:{locality_id}", "administrative", locality_id)
                    capacity = world.localities[locality_id].governance.get(
                        "elite_access_capacity",
                        1.0 if world.localities[locality_id].population > 0 else 0.0,
                    )
                    if max(0.0, min(1.0, float(capacity))):
                        add("government", None, f"ELITE-CAP:{locality_id}", "political_elite", locality_id)
                    if locality_id in world.multilingual_locality_ids and world.localities[locality_id].population > 0:
                        add("government", None, f"INTERPRETER-CAP:{locality_id}", "interpreter", locality_id)
                continue
            community_id = community_ids[0]
            # The selected community is random at execution time; the plan
            # contains every possible source row and the caller selects the
            # relevant row using the same RNG stream.
            for community_id in community_ids:
                for source_kind in ("civilian", "social_network"):
                    if "government" in world.organizations:
                        add("government", None, community_id, source_kind, locality_id)
                if "government" in world.organizations:
                    add("government", None, f"ADMIN:{locality_id}", "administrative", locality_id)
                    add("government", None, f"ELITE:{community_id}", "political_elite", locality_id)
                for insurgent_id in world.active_insurgent_organization_ids:
                    add(insurgent_id, None, community_id, "civilian", locality_id)
                if locality_id in world.multilingual_locality_ids and "government" in world.organizations:
                    add("government", None, community_id, "interpreter", locality_id)

        for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
            if formation.moving or formation.available_personnel() <= 0:
                continue
            add(formation.organization_id, formation.formation_id, formation.formation_id,
                "organization_member", formation.locality_id)

        fingerprint = (
            tuple(world.ordered_locality_ids or sorted(world.localities)),
            tuple(sorted(world.security_posts)),
            tuple(sorted(world.formations)),
            tuple(world.active_insurgent_organization_ids),
            tuple(sorted(world.social_communities)),
        )
        return cls(codes, observer, node, source, source_type, locality,
                   target_offsets, target_actor, fingerprint)

    def __len__(self) -> int:
        return len(self.observer)

    def targets(self, index: int) -> tuple[int, ...]:
        start = self.target_offsets[index]
        end = self.target_offsets[index + 1]
        return tuple(self.target_actor[start:end])

    def is_current_for(self, world: Any) -> bool:
        current = (
            tuple(world.ordered_locality_ids or sorted(world.localities)),
            tuple(sorted(world.security_posts)),
            tuple(sorted(world.formations)),
            tuple(world.active_insurgent_organization_ids),
            tuple(sorted(world.social_communities)),
        )
        return current == self.fingerprint


@dataclass(slots=True)
class StaticWorldTopology:
    """Immutable integer-coded geography shared by an ensemble."""

    locality_ids: tuple[str, ...]
    microzone_ids: tuple[str, ...]
    organization_ids: tuple[str, ...]
    locality_index: dict[str, int]
    microzone_index: dict[str, int]
    organization_index: dict[str, int]
    microzone_locality: array
    physical_distances: array
    source_plan: InformationSourcePlan
    signature: tuple[Any, ...]

    @classmethod
    def from_world(cls, world: Any) -> "StaticWorldTopology":
        world.rebuild_physical_distance_index()
        locality_ids = tuple(world.ordered_locality_ids or sorted(world.localities))
        microzone_ids = tuple(world.ordered_microzone_ids or sorted(world.microzones))
        organization_ids = tuple(world.ordered_organization_ids or sorted(world.organizations))
        locality_index = {value: index for index, value in enumerate(locality_ids)}
        microzone_index = {value: index for index, value in enumerate(microzone_ids)}
        organization_index = {value: index for index, value in enumerate(organization_ids)}
        microzone_locality = array(
            "I",
            (
                locality_index[world.microzones[zone_id].locality_id]
                for zone_id in microzone_ids
            ),
        )
        distances = array("d")
        for source_id in microzone_ids:
            row = world.physical_distance_cache.get(source_id, {})
            distances.extend(float(row.get(target_id, inf)) for target_id in microzone_ids)
        plan = InformationSourcePlan.from_world(world)
        signature = (
            tuple(world.physical_distance_signature),
            tuple(locality_ids), tuple(microzone_ids), tuple(organization_ids),
        )
        return cls(locality_ids, microzone_ids, organization_ids,
                   locality_index, microzone_index, organization_index,
                   microzone_locality, distances, plan, signature)

    def distance(self, source_microzone_id: str, target_microzone_id: str) -> float:
        source = self.microzone_index[source_microzone_id]
        target = self.microzone_index[target_microzone_id]
        return float(self.physical_distances[source * len(self.microzone_ids) + target])


def _default_row(stride: int, *, prior_confidence: float = 0.35) -> tuple[float, ...]:
    if stride == CONTROL_STATE_STRIDE:
        return (*([0.5] * 7), float(prior_confidence), 0.0, -1.0e9, 0.0, 0.0, 0.0)
    if stride == PRESENCE_STATE_STRIDE:
        return (0.0, float(prior_confidence), 0.0, -1.0e9, 0.0, 0.0, 0.0)
    if stride == ZONE_STATE_STRIDE:
        return (0.5, float(prior_confidence), 0.0, -1.0e9, 0.0, 0.0)
    raise ValueError(f"unsupported ensemble belief stride: {stride}")


@dataclass(slots=True)
class EnsembleBeliefState:
    """Leading-particle numeric rows: ``[particle][entity][field]``."""

    keys: tuple[tuple[str, ...], ...]
    particle_count: int
    stride: int
    state: array
    key_to_index: dict[tuple[str, ...], int] = field(init=False)

    def __post_init__(self) -> None:
        self.keys = tuple(tuple(str(item) for item in key) for key in self.keys)
        self.particle_count = int(self.particle_count)
        self.stride = int(self.stride)
        if self.particle_count < 1:
            raise ValueError("ensemble belief state needs at least one particle")
        if self.stride not in {CONTROL_STATE_STRIDE, PRESENCE_STATE_STRIDE, ZONE_STATE_STRIDE}:
            raise ValueError("unsupported ensemble belief stride")
        if self.state.typecode != "d":
            raise TypeError("ensemble belief state must use array('d')")
        expected = self.particle_count * len(self.keys) * self.stride
        if len(self.state) != expected:
            raise ValueError(f"ensemble state has {len(self.state)} values; expected {expected}")
        if len(set(self.keys)) != len(self.keys):
            raise ValueError("ensemble belief keys must be unique")
        self.key_to_index = {key: index for index, key in enumerate(self.keys)}

    @property
    def entity_count(self) -> int:
        return len(self.keys)

    @property
    def state_count(self) -> int:
        return self.particle_count * self.entity_count

    @classmethod
    def from_rows(
        cls,
        keys: Iterable[tuple[str, ...]],
        rows_by_particle: Sequence[Sequence[Sequence[float]]],
        stride: int,
    ) -> "EnsembleBeliefState":
        normalized_keys = tuple(tuple(key) for key in keys)
        particle_count = len(rows_by_particle)
        if particle_count < 1:
            raise ValueError("ensemble state needs at least one particle")
        state = array("d")
        for rows in rows_by_particle:
            if len(rows) != len(normalized_keys):
                raise ValueError("every particle must provide one row per key")
            for row in rows:
                if len(row) != stride:
                    raise ValueError("ensemble row has an invalid stride")
                state.extend(float(value) for value in row)
        return cls(normalized_keys, particle_count, stride, state)

    @classmethod
    def zeros(
        cls,
        keys: Iterable[tuple[str, ...]],
        particle_count: int,
        stride: int,
        *,
        prior_confidence: float = 0.35,
    ) -> "EnsembleBeliefState":
        normalized = tuple(tuple(key) for key in keys)
        row = _default_row(stride, prior_confidence=prior_confidence)
        return cls.from_rows(normalized, [[row for _ in normalized] for _ in range(particle_count)], stride)

    def offset(self, particle: int, key_or_index: tuple[str, ...] | int) -> int:
        entity = int(key_or_index) if isinstance(key_or_index, int) else self.key_to_index[key_or_index]
        particle = int(particle)
        if not 0 <= particle < self.particle_count:
            raise IndexError("particle index outside ensemble")
        if not 0 <= entity < self.entity_count:
            raise IndexError("entity index outside ensemble")
        return (particle * self.entity_count + entity) * self.stride

    def row(self, particle: int, key_or_index: tuple[str, ...] | int) -> tuple[float, ...]:
        start = self.offset(particle, key_or_index)
        return tuple(self.state[start:start + self.stride])

    def ensure_key(
        self,
        key: tuple[str, ...],
        *,
        rows: Sequence[Sequence[float]] | None = None,
        prior_confidence: float = 0.35,
    ) -> int:
        key = tuple(key)
        existing = self.key_to_index.get(key)
        if existing is not None:
            return existing
        if rows is None:
            default = _default_row(self.stride, prior_confidence=prior_confidence)
            rows = [default] * self.particle_count
        if len(rows) != self.particle_count:
            raise ValueError("dynamic ensemble key needs one row per particle")
        old_entities = self.entity_count
        old_state = self.state
        self.keys = (*self.keys, key)
        self.key_to_index[key] = old_entities
        self.state = array("d")
        for particle in range(self.particle_count):
            start = particle * old_entities * self.stride
            self.state.extend(old_state[start:start + old_entities * self.stride])
            self.state.extend(float(value) for value in rows[particle])
        return old_entities

    def gather(self, parent_indices: Sequence[int]) -> None:
        """Resample rows with an indexed native-style gather."""
        parents = tuple(int(index) for index in parent_indices)
        if not parents or any(index < 0 or index >= self.particle_count for index in parents):
            raise ValueError("parent indices must reference existing ensemble particles")
        block = self.entity_count * self.stride
        old = self.state
        self.state = array("d")
        for parent in parents:
            start = parent * block
            self.state.extend(old[start:start + block])
        self.particle_count = len(parents)

    def clone(self) -> "EnsembleBeliefState":
        return type(self)(self.keys, self.particle_count, self.stride, array("d", self.state))

    def sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(f"pineland.ensemble.belief.v1:{self.stride}".encode())
        for key in self.keys:
            digest.update("\x1f".join(key).encode())
            digest.update(b"\0")
        digest.update(self.state.tobytes())
        return digest.hexdigest()

    def fuse_control(
        self,
        updates: Sequence[tuple[int, tuple[str, ...], float, float, Sequence[float]]],
        *,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> int:
        if self.stride != CONTROL_STATE_STRIDE:
            raise ValueError("control fusions require control rows")
        if not updates:
            return 0
        indices = array("I")
        times = array("d")
        weights = array("d")
        observed = array("d")
        for particle, key, time, weight, values in updates:
            if len(values) != len(CONTROL_DIMENSIONS):
                raise ValueError("control fusion needs seven observed dimensions")
            indices.append(particle * self.entity_count + self.key_to_index[tuple(key)])
            times.append(float(time))
            weights.append(float(weight))
            observed.extend(float(value) for value in values)
        from .native_kernels import fuse_control7_batch
        native = fuse_control7_batch(
            self.state, self.state_count, indices, times, weights, observed,
            contradiction_memory_days=contradiction_memory_days,
            contradiction_penalty=contradiction_penalty,
            state_stride=self.stride,
        )
        if native:
            return len(updates)
        for index, time, weight, values in zip(indices, times, weights, updates):
            start = int(index) * self.stride
            old_confidence = self.state[start + 7]
            prior = max(0.02, old_confidence)
            denominator = prior + float(weight)
            scale = denominator / (1.0 + denominator)
            contradiction = self.state[start + 11]
            decay = exp(-max(0.0, float(time) - self.state[start + 8]) / contradiction_memory_days)
            confidence = old_confidence
            values_row = values[4]
            for dimension, observed_value in enumerate(values_row):
                observed_value = min(1.0, max(0.0, float(observed_value)))
                old_value = self.state[start + dimension]
                self.state[start + dimension] = min(
                    1.0, max(0.0, (prior * old_value + float(weight) * observed_value) / denominator)
                )
                contradiction = contradiction * decay + float(weight) * abs(observed_value - old_value)
                confidence = min(1.0, max(0.0, scale * exp(-contradiction_penalty * contradiction)))
            self.state[start + 7] = confidence
            self.state[start + 8] = float(time)
            if float(weight) >= 0.12:
                self.state[start + 9] = float(time)
            self.state[start + 10] += 1.0
            self.state[start + 11] = contradiction
        return len(updates)

    def fuse_presence(
        self,
        updates: Sequence[tuple[int, tuple[str, ...], float, float, float, float]],
        *,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> int:
        if self.stride != PRESENCE_STATE_STRIDE:
            raise ValueError("presence fusions require presence rows")
        if not updates:
            return 0
        indices = array("I")
        times = array("d")
        weights = array("d")
        presence = array("d")
        personnel = array("d")
        for particle, key, time, weight, observed_presence, observed_personnel in updates:
            indices.append(particle * self.entity_count + self.key_to_index[tuple(key)])
            times.append(float(time)); weights.append(float(weight))
            presence.append(float(observed_presence)); personnel.append(float(observed_personnel))
        from .native_kernels import fuse_presence_batch
        if fuse_presence_batch(
            self.state, self.state_count, indices, times, weights, presence, personnel,
            contradiction_memory_days=contradiction_memory_days,
            contradiction_penalty=contradiction_penalty,
            state_stride=self.stride,
        ):
            return len(updates)
        for index, time, weight, observed, personnel_value in zip(
            indices, times, weights, presence, personnel
        ):
            start = int(index) * self.stride
            old_confidence = self.state[start + 1]
            prior = max(0.02, old_confidence)
            denominator = prior + float(weight)
            old_presence = self.state[start]
            contradiction = self.state[start + 5] * exp(
                -max(0.0, float(time) - self.state[start + 2]) / contradiction_memory_days
            ) + float(weight) * abs(float(observed) - old_presence)
            self.state[start] = min(1.0, max(0.0, (prior * old_presence + float(weight) * float(observed)) / denominator))
            self.state[start + 6] = (
                self.state[start + 6] * max(0.02, old_confidence)
                + float(personnel_value) * float(weight)
            ) / (max(0.02, old_confidence) + float(weight))
            self.state[start + 1] = min(
                1.0,
                max(0.0, (prior + float(weight)) / (1.0 + prior + float(weight)) * exp(-contradiction_penalty * contradiction)),
            )
            self.state[start + 2] = float(time)
            self.state[start + 4] += 1.0
            self.state[start + 5] = contradiction
            if float(weight) >= 0.12:
                self.state[start + 3] = float(time)
        return len(updates)

    def fuse_zone(
        self,
        updates: Sequence[tuple[int, tuple[str, ...], float, float, float]],
        *,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> int:
        if self.stride != ZONE_STATE_STRIDE:
            raise ValueError("zone fusions require zone rows")
        if not updates:
            return 0
        indices = array("I"); times = array("d"); weights = array("d"); observed = array("d")
        for particle, key, time, weight, value in updates:
            indices.append(particle * self.entity_count + self.key_to_index[tuple(key)])
            times.append(float(time)); weights.append(float(weight)); observed.append(float(value))
        from .native_kernels import fuse_zone_batch
        if fuse_zone_batch(
            self.state, self.state_count, indices, times, weights, observed,
            contradiction_memory_days=contradiction_memory_days,
            contradiction_penalty=contradiction_penalty,
            state_stride=self.stride,
        ):
            return len(updates)
        for index, time, weight, observed_value in zip(indices, times, weights, observed):
            start = int(index) * self.stride
            old_confidence = self.state[start + 1]
            prior = max(0.02, old_confidence)
            denominator = prior + float(weight)
            old_value = self.state[start]
            contradiction = self.state[start + 5] * exp(
                -max(0.0, float(time) - self.state[start + 2]) / contradiction_memory_days
            ) + float(weight) * abs(float(observed_value) - old_value)
            self.state[start] = min(1.0, max(0.0, (prior * old_value + float(weight) * float(observed_value)) / denominator))
            self.state[start + 1] = min(
                1.0,
                max(0.0, (prior + float(weight)) / (1.0 + prior + float(weight)) * exp(-contradiction_penalty * contradiction)),
            )
            self.state[start + 2] = float(time)
            self.state[start + 4] += 1.0
            self.state[start + 5] = contradiction
            if float(weight) >= 0.12:
                self.state[start + 3] = float(time)
        return len(updates)


def _compact_rows(world: Any, attribute: str, fallback: Any, stride: int) -> dict[tuple[str, ...], tuple[float, ...]]:
    compact = getattr(world, attribute, None)
    if compact is not None:
        return {tuple(key): tuple(compact.row(key)) for key in compact.keys}
    return {tuple(key): tuple(fallback._belief_row(value)) for key, value in fallback.items()}


@dataclass(slots=True)
class ParticleBatchState:
    """Packed ensemble state with optional reference-world synchronization."""

    topology: StaticWorldTopology
    times: array
    weights: array
    lineage_ids: tuple[str, ...]
    control_state: EnsembleBeliefState
    presence_state: EnsembleBeliefState
    node_presence_state: EnsembleBeliefState
    zone_state: EnsembleBeliefState
    particles: list[Any] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.times = array("d", self.times)
        self.weights = array("d", self.weights)
        if not self.times or len(self.times) != len(self.weights):
            raise ValueError("batch times/weights must match and be nonempty")
        particle_count = len(self.times)
        if len(self.lineage_ids) != particle_count:
            raise ValueError("lineage IDs must match particle count")
        for state in (self.control_state, self.presence_state, self.node_presence_state, self.zone_state):
            if state.particle_count != particle_count:
                raise ValueError("all packed belief states must share the particle dimension")

    @property
    def particle_count(self) -> int:
        return len(self.times)

    @classmethod
    def from_particles(
        cls,
        particles: Sequence[Any],
        *,
        topology: StaticWorldTopology | None = None,
    ) -> "ParticleBatchState":
        if not particles:
            raise ValueError("particle batch needs at least one particle")
        worlds = [item.world for item in particles]
        topology = topology or StaticWorldTopology.from_world(worlds[0])
        control_keys = tuple(sorted({key for world in worlds for key in world.control_beliefs}))
        presence_keys = tuple(sorted({key for world in worlds for key in world.presence_beliefs}))
        node_keys = tuple(sorted({key for world in worlds for key in world.node_presence_beliefs}))
        zone_keys = tuple(sorted({key for world in worlds for key in world.zone_beliefs}))
        rows = []
        for world in worlds:
            compact = getattr(world, "compact_control_state", None)
            rows.append([
                tuple(compact.row(key)) if compact is not None and key in compact.key_to_index
                else tuple(world.compact_control_state._belief_row(world.control_beliefs[key])) if key in world.control_beliefs and compact is not None
                else _default_row(CONTROL_STATE_STRIDE, prior_confidence=world.config.information.prior_confidence)
                for key in control_keys
            ])
        control_state = EnsembleBeliefState.from_rows(control_keys, rows, CONTROL_STATE_STRIDE)

        def presence_rows(worlds: Sequence[Any], attribute: str, fallback_name: str, stride: int):
            result = []
            for world in worlds:
                compact = getattr(world, attribute, None)
                fallback = getattr(world, fallback_name)
                keys = {key for key in (presence_keys if fallback_name == "presence_beliefs" else node_keys if fallback_name == "node_presence_beliefs" else zone_keys)}
                result.append([
                    tuple(compact.row(key)) if compact is not None and key in compact.key_to_index
                    else tuple(compact._belief_row(fallback[key])) if compact is not None and key in fallback
                    else _default_row(stride, prior_confidence=world.config.information.prior_confidence)
                    for key in sorted(keys)
                ])
            return result

        presence_state = EnsembleBeliefState.from_rows(
            presence_keys,
            presence_rows(worlds, "compact_presence_state", "presence_beliefs", PRESENCE_STATE_STRIDE),
            PRESENCE_STATE_STRIDE,
        )
        node_presence_state = EnsembleBeliefState.from_rows(
            node_keys,
            presence_rows(worlds, "compact_node_presence_state", "node_presence_beliefs", PRESENCE_STATE_STRIDE),
            PRESENCE_STATE_STRIDE,
        )
        zone_state = EnsembleBeliefState.from_rows(
            zone_keys,
            presence_rows(worlds, "compact_zone_state", "zone_beliefs", ZONE_STATE_STRIDE),
            ZONE_STATE_STRIDE,
        )
        return cls(
            topology,
            array("d", [float(item.time) for item in particles]),
            array("d", [float(getattr(item, "log_weight", 0.0)) for item in particles]),
            tuple(str(getattr(item, "lineage_id", index)) for index, item in enumerate(particles)),
            control_state, presence_state, node_presence_state, zone_state,
            list(particles),
        )

    def gather(self, parent_indices: Sequence[int], *, clone_reference_states: bool = False) -> None:
        parents = tuple(int(index) for index in parent_indices)
        if not parents or any(index < 0 or index >= self.particle_count for index in parents):
            raise ValueError("invalid particle parent indices")
        for state in (self.control_state, self.presence_state, self.node_presence_state, self.zone_state):
            state.gather(parents)
        old_times = self.times
        old_weights = self.weights
        old_lineages = self.lineage_ids
        self.times = array("d", (old_times[index] for index in parents))
        self.weights = array("d", (old_weights[index] for index in parents))
        self.lineage_ids = tuple(f"{old_lineages[index]}.{child}" for child, index in enumerate(parents))
        if self.particles:
            if clone_reference_states:
                self.particles = [
                    self.particles[parent].fork(child)
                    if hasattr(self.particles[parent], "fork") else self.particles[parent].simulation.clone()
                    for child, parent in enumerate(parents)
                ]
            else:
                self.particles = [self.particles[index] for index in parents]

    def synchronize_to_worlds(self) -> None:
        """Mirror packed rows into legacy objects at an explicit boundary."""
        if not self.particles:
            return
        from .compact_information_state import (
            CompactControlBeliefState, CompactPresenceBeliefState, CompactZoneBeliefState,
        )
        from .entities import ActorBelief, PresenceBelief, ActorZoneBelief
        for particle_index, particle in enumerate(self.particles):
            world = particle.world
            # Controls
            compact = CompactControlBeliefState(self.control_state.keys, array("d"))
            for key in self.control_state.keys:
                compact.state.extend(self.control_state.row(particle_index, key))
                if key not in world.control_beliefs:
                    world.control_beliefs[key] = ActorBelief(
                        key[0], key[2], ControlVector(*([0.5] * 7)),
                        world.config.information.prior_confidence, 0.0,
                    )
            world.compact_control_state = compact
            for key in self.control_state.keys:
                compact.write_to_belief(key, world.control_beliefs[key])

            def sync_presence(state: EnsembleBeliefState, attribute: str, cls_type: Any, node: bool = False):
                compact = CompactPresenceBeliefState(state.keys, array("d"))
                target = getattr(world, attribute)
                for key in state.keys:
                    compact.state.extend(state.row(particle_index, key))
                    if key not in target:
                        location = key[2].split(":", 1)
                        locality_id = location[0]
                        microzone_id = None if len(location) == 1 or location[1] == "*" else location[1]
                        target[key] = PresenceBelief(
                            key[0], key[1], locality_id, microzone_id=microzone_id,
                            target_id=None if key[3] == "*" else key[3],
                            confidence=world.config.information.prior_confidence,
                        )
                setattr(world, "compact_node_presence_state" if node else "compact_presence_state", compact)
                for key in state.keys:
                    compact.write_to_belief(key, target[key])

            sync_presence(self.presence_state, "presence_beliefs", PresenceBelief)
            sync_presence(self.node_presence_state, "node_presence_beliefs", PresenceBelief, node=True)
            compact_zone = CompactZoneBeliefState(self.zone_state.keys, array("d"))
            for key in self.zone_state.keys:
                compact_zone.state.extend(self.zone_state.row(particle_index, key))
                if key not in world.zone_beliefs:
                    world.zone_beliefs[key] = ActorZoneBelief(key[0], key[1], 0.5, world.config.information.prior_confidence, 0.0)
                compact_zone.write_to_belief(key, world.zone_beliefs[key])
            world.compact_zone_state = compact_zone
            world.time = float(self.times[particle_index])

    def state_sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.topology.signature.__repr__().encode())
        digest.update(self.times.tobytes())
        digest.update(self.weights.tobytes())
        for state in (self.control_state, self.presence_state, self.node_presence_state, self.zone_state):
            digest.update(state.sha256().encode())
        return digest.hexdigest()

    def advance_to(self, until: float, *, runner: Any | None = None) -> None:
        """Advance the packed batch through a supplied compiled runner.

        ``runner`` receives this object and the common boundary.  For migration
        and exact comparison, omitting it uses the resident reference particles
        and synchronizes the packed state afterward.  A native/compiled caller
        should keep the packed state authoritative and provide the runner.
        """
        until = float(until)
        if runner is not None:
            runner(self, until)
            self.times = array("d", [until] * self.particle_count)
            return
        if not self.particles:
            raise RuntimeError("a packed batch without resident particles needs a runner")
        for particle in self.particles:
            particle.advance_to(until)
        self.times = array("d", [float(particle.time) for particle in self.particles])
        self.synchronize_to_worlds()


def advance_batch(
    batch: ParticleBatchState,
    until: float,
    *,
    runner: Any | None = None,
) -> ParticleBatchState:
    """Single-call batch boundary used by ensemble filters."""
    batch.advance_to(until, runner=runner)
    return batch


# Explicit aliases used by callers that prefer the handoff terminology.
NumericInformationEventBuffer = InformationEventBuffer
NumericRelayBuffer = RelayBuffer
EnsembleState = ParticleBatchState


__all__ = [
    "EnsembleBeliefState", "EnsembleState", "InformationEventBuffer",
    "InformationSourcePlan", "NumericIdTable", "NumericInformationEventBuffer",
    "NumericRelayBuffer", "ParticleBatchState", "RelayBuffer",
    "StaticWorldTopology", "advance_batch",
]
