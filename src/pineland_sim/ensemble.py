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
from collections import deque
from dataclasses import dataclass, field
import hashlib
from math import exp, inf, isfinite, log
from typing import Any, Iterable, Sequence

from .compact_information_state import (
    CONTROL_STATE_STRIDE,
    PRESENCE_STATE_STRIDE,
    ZONE_STATE_STRIDE,
)
from .entities import CONTROL_DIMENSIONS, ControlVector, Observation, OrganizationKind


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

    def _append_common_codes(
        self,
        sequence: int,
        *,
        observer: int,
        node: int,
        source: int,
        source_type: int,
        locality: int,
        microzone: int,
        target_actor: int,
        target_formation: int,
        timestamp: float,
        confidence: float,
        quality: float,
        kind: int,
    ) -> int:
        """Append a row from already-interned numeric codes."""
        sequence = int(sequence)
        if sequence in self.id_to_index:
            raise ValueError(f"duplicate numeric observation sequence: {sequence}")
        index = len(self.ids)
        self.ids.append(sequence)
        self.id_to_index[sequence] = index
        self.observer.append(int(observer))
        self.node.append(int(node))
        self.source.append(int(source))
        self.source_type.append(int(source_type))
        self.locality.append(int(locality))
        self.microzone.append(int(microzone))
        self.target_actor.append(int(target_actor))
        self.target_formation.append(int(target_formation))
        self.timestamp.append(float(timestamp))
        self.confidence.append(float(confidence))
        self.quality.append(float(quality))
        self.kind.append(int(kind))
        return index

    def append_detection_codes(
        self,
        sequence: int,
        *,
        observer: int,
        node: int,
        source: int,
        source_type: int,
        locality: int,
        microzone: int,
        target_actor: int,
        target_formation: int,
        timestamp: float,
        confidence: float,
        quality: float,
        presence: float,
        personnel: float,
        detection_probability: float,
        detected: bool,
        attribution_confidence: float,
    ) -> int:
        """Numeric-only detection append used by the compiled event path."""
        index = self._append_common_codes(
            sequence,
            observer=observer,
            node=node,
            source=source,
            source_type=source_type,
            locality=locality,
            microzone=microzone,
            target_actor=target_actor,
            target_formation=target_formation,
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

    def append_control_codes(
        self,
        sequence: int,
        *,
        observer: int,
        node: int,
        source: int,
        source_type: int,
        locality: int,
        microzone: int,
        target_actor: int,
        timestamp: float,
        confidence: float,
        quality: float,
        control: Sequence[float],
        physical_control: float,
        violence: float,
    ) -> int:
        """Numeric-only control append used by the compiled event path."""
        if len(control) != len(CONTROL_DIMENSIONS):
            raise ValueError("control payload must contain seven numeric dimensions")
        index = self._append_common_codes(
            sequence,
            observer=observer,
            node=node,
            source=source,
            source_type=source_type,
            locality=locality,
            microzone=microzone,
            target_actor=target_actor,
            target_formation=0,
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
        # Scientific fixtures sometimes use human-readable IDs rather than
        # the production ``OBS0000000001`` namespace.  The packed engine only
        # needs a stable per-buffer sequence, so retain the production number
        # when present and otherwise allocate the next unused integer.
        raw_sequence = observation.observation_id.removeprefix("OBS")
        try:
            sequence = int(raw_sequence)
        except ValueError:
            sequence = max(self.id_to_index, default=0) + 1
        if set(value) == {
            "presence", "personnel", "detection_probability", "detected",
            "attribution_confidence",
        }:
            return self.append_detection(
                sequence,
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
                sequence,
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

    def append_codes(
        self,
        sequence: int,
        *,
        observation_sequence: int,
        organization: int,
        source: int,
        destination: int,
        route: Sequence[int],
        sent_at: float,
        arrives_at: float,
        reliability: float,
        latency_hours: float,
        status: int = 0,
        delivered_at: float | None = None,
    ) -> int:
        """Append a relay whose identities and route are already numeric."""
        sequence = int(sequence)
        if sequence in self.id_to_index:
            raise ValueError(f"duplicate numeric relay sequence: {sequence}")
        index = len(self.ids)
        self.ids.append(sequence)
        self.id_to_index[sequence] = index
        self.observation_sequence.append(int(observation_sequence))
        self.organization.append(int(organization))
        self.source.append(int(source))
        self.destination.append(int(destination))
        self.route_codes.extend(int(item) for item in route)
        self.route_offsets.append(len(self.route_codes))
        self.sent_at.append(float(sent_at))
        self.arrives_at.append(float(arrives_at))
        self.reliability.append(float(reliability))
        self.latency_hours.append(float(latency_hours))
        self.status.append(int(status))
        self.delivered_at.append(-1.0 if delivered_at is None else float(delivered_at))
        return index

    def route_codes_for(self, index: int) -> tuple[int, ...]:
        start = self.route_offsets[index]
        end = self.route_offsets[index + 1]
        return tuple(self.route_codes[start:end])

    def retain_active(self) -> None:
        """Drop delivered/dropped rows while preserving in-flight relays.

        Relay status is the only mutable per-row field after enqueue. Compacting
        at an information boundary keeps delivery scans proportional to the
        number of live relays rather than to the full run history.
        """
        keep = tuple(
            index for index, status in enumerate(self.status)
            if int(status) == 0
        )
        if len(keep) == len(self.ids):
            return
        old = {
            "ids": self.ids,
            "observation_sequence": self.observation_sequence,
            "organization": self.organization,
            "source": self.source,
            "destination": self.destination,
            "route_offsets": self.route_offsets,
            "route_codes": self.route_codes,
            "sent_at": self.sent_at,
            "arrives_at": self.arrives_at,
            "reliability": self.reliability,
            "latency_hours": self.latency_hours,
            "status": self.status,
            "delivered_at": self.delivered_at,
        }
        self.ids = array("Q")
        self.id_to_index = {}
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
        for index in keep:
            new_index = len(self.ids)
            relay_id = int(old["ids"][index])
            self.ids.append(relay_id)
            self.id_to_index[relay_id] = new_index
            self.observation_sequence.append(old["observation_sequence"][index])
            self.organization.append(old["organization"][index])
            self.source.append(old["source"][index])
            self.destination.append(old["destination"][index])
            start = int(old["route_offsets"][index])
            end = int(old["route_offsets"][index + 1])
            self.route_codes.extend(old["route_codes"][start:end])
            self.route_offsets.append(len(self.route_codes))
            self.sent_at.append(old["sent_at"][index])
            self.arrives_at.append(old["arrives_at"][index])
            self.reliability.append(old["reliability"][index])
            self.latency_hours.append(old["latency_hours"][index])
            self.status.append(old["status"][index])
            self.delivered_at.append(old["delivered_at"][index])

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
    locality_ids: tuple[str, ...]
    locality_source_groups: tuple[tuple[tuple[int, ...], ...], ...]
    locality_fallback_sources: tuple[tuple[int, ...], ...]
    locality_community_ids: tuple[tuple[int, ...], ...]
    locality_cumulative_weights: tuple[tuple[float, ...], ...]
    always_sources: tuple[int, ...]
    fingerprint: tuple[Any, ...]
    # Optional per-target/per-source overrides used by patrol/contact-sized
    # compiled events.  Background plans leave these empty and retain the
    # reference defaults.
    target_formation: array = field(default_factory=lambda: array("I"))
    source_microzone: array = field(default_factory=lambda: array("I"))
    source_zone_actor: array = field(default_factory=lambda: array("I"))
    # Flattened selection metadata for the optional one-call native event
    # ABI. These arrays are compiled once with the source plan; no source
    # objects or Python selection lists are created at each information tick.
    native_initial_sources: array = field(default_factory=lambda: array("I"))
    native_member_sources: array = field(default_factory=lambda: array("I"))
    native_locality_group_offsets: array = field(default_factory=lambda: array("Q", [0]))
    native_group_source_offsets: array = field(default_factory=lambda: array("Q", [0]))
    native_group_sources: array = field(default_factory=lambda: array("I"))
    native_locality_cumulative_offsets: array = field(default_factory=lambda: array("Q", [0]))
    native_cumulative_weights: array = field(default_factory=lambda: array("d"))
    native_locality_fallback_offsets: array = field(default_factory=lambda: array("Q", [0]))
    native_fallback_sources: array = field(default_factory=lambda: array("I"))

    @classmethod
    def from_world(
        cls,
        world: Any,
        *,
        codebook: NumericIdTable | None = None,
    ) -> "InformationSourcePlan":
        # Importing lazily avoids the information/world import cycle.
        from .information import _target_actors_for_observer

        world.refresh_operational_indexes()
        # A runtime may recompile its active source plan while reports from an
        # older plan are still in flight. Reusing the codebook keeps those
        # numeric relay rows decodable without retaining the old source graph.
        codes = codebook if codebook is not None else NumericIdTable()
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
        ) -> int:
            index = len(observer)
            observer.append(codes.code(observer_id))
            # ``_observe_from_source`` uses the explicit formation/post node
            # when present and otherwise falls back to the source identity.
            # Store that effective local recipient in the numeric plan so
            # locality channels retain the same actor-local belief topology.
            node.append(codes.code(node_id or source_id))
            source.append(codes.code(source_id))
            source_type.append(codes.code(source_kind))
            locality.append(codes.code(locality_id))
            target_actor.extend(
                codes.code(item)
                for item in _target_actors_for_observer(world, observer_id)
            )
            target_offsets.append(len(target_actor))
            return index

        always_sources: list[int] = []
        locality_ids = tuple(
            world.ordered_locality_ids or tuple(sorted(world.localities))
        )
        locality_source_groups: list[tuple[tuple[int, ...], ...]] = []
        locality_fallback_sources: list[tuple[int, ...]] = []
        locality_community_ids: list[tuple[int, ...]] = []
        locality_cumulative_weights: list[tuple[float, ...]] = []

        # This order intentionally mirrors generate_background_observations.
        for post in sorted(world.security_posts.values(), key=lambda item: item.post_id):
            # Compile source identity/order once. Availability is dynamic and
            # is filtered immediately before the RNG boundary.
            always_sources.append(add(
                post.organization_id, post.formation_id or post.post_id,
                post.post_id, "fixed_post", post.locality_id,
            ))

        for locality_id in locality_ids:
            community_ids, cumulative_weights = world.community_selection_weights(locality_id)
            locality_community_ids.append(tuple(codes.code(item) for item in community_ids))
            locality_cumulative_weights.append(tuple(float(item) for item in cumulative_weights))
            if not community_ids:
                fallback: list[int] = []
                if "government" in world.organizations:
                    fallback.append(add(
                        "government", None, f"ADMIN:{locality_id}",
                        "administrative", locality_id,
                    ))
                    capacity = world.localities[locality_id].governance.get(
                        "elite_access_capacity",
                        1.0 if world.localities[locality_id].population > 0 else 0.0,
                    )
                    if max(0.0, min(1.0, float(capacity))):
                        fallback.append(add(
                            "government", None, f"ELITE-CAP:{locality_id}",
                            "political_elite", locality_id,
                        ))
                    if locality_id in world.multilingual_locality_ids and world.localities[locality_id].population > 0:
                        fallback.append(add(
                            "government", None, f"INTERPRETER-CAP:{locality_id}",
                            "interpreter", locality_id,
                        ))
                locality_source_groups.append(())
                locality_fallback_sources.append(tuple(fallback))
                continue
            groups: list[tuple[int, ...]] = []
            # The selected community is random at execution time. Compile one
            # numeric group per possible community so the runtime executes only
            # the selected group and consumes exactly the reference RNG draws.
            for community_id in community_ids:
                group: list[int] = []
                for source_kind in ("civilian", "social_network"):
                    if "government" in world.organizations:
                        group.append(add(
                            "government", None, community_id, source_kind,
                            locality_id,
                        ))
                if "government" in world.organizations:
                    group.append(add(
                        "government", None, f"ADMIN:{locality_id}",
                        "administrative", locality_id,
                    ))
                    group.append(add(
                        "government", None, f"ELITE:{community_id}",
                        "political_elite", locality_id,
                    ))
                active_insurgent_ids = (
                    world.active_insurgent_organization_ids
                    if world.execution_profile == "particle"
                    else tuple(sorted(
                        organization.organization_id
                        for organization in world.organizations.values()
                        if organization.kind is OrganizationKind.INSURGENT
                        and organization.status == "active"
                    ))
                )
                for insurgent_id in active_insurgent_ids:
                    group.append(add(
                        insurgent_id, None, community_id, "civilian", locality_id,
                    ))
                if locality_id in world.multilingual_locality_ids and "government" in world.organizations:
                    group.append(add(
                        "government", None, community_id, "interpreter", locality_id,
                    ))
                groups.append(tuple(group))
            locality_source_groups.append(tuple(groups))
            locality_fallback_sources.append(())

        for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
            # Moving/personnel eligibility is also dynamic. Keeping every
            # formation in the compiled plan avoids rebuilding source topology
            # merely because a unit moves between information ticks.
            always_sources.append(add(
                formation.organization_id, formation.formation_id,
                formation.formation_id, "organization_member", formation.locality_id,
            ))

        # Compile the nested locality selection graph into flat numeric
        # buffers. The native event kernel uses these ranges to reproduce the
        # reference source order without materializing a selected-source list
        # in Python. ``always_sources`` is split at the same boundary as
        # ``iter_selected_source_indices``: fixed posts first, members last.
        initial_sources = array("I")
        member_sources = array("I")
        has_locality_groups = any(locality_source_groups)
        for source_index in always_sources:
            source_kind = codes.value(source_type[source_index])
            if source_kind == "organization_member":
                member_sources.append(source_index)
            elif source_kind == "fixed_post" or not has_locality_groups:
                initial_sources.append(source_index)

        locality_group_offsets = array("Q", [0])
        group_source_offsets = array("Q", [0])
        group_sources = array("I")
        locality_cumulative_offsets = array("Q", [0])
        cumulative_weights = array("d")
        locality_fallback_offsets = array("Q", [0])
        fallback_sources = array("I")
        for locality_index, groups in enumerate(locality_source_groups):
            for group in groups:
                group_sources.extend(int(item) for item in group)
                group_source_offsets.append(len(group_sources))
            locality_group_offsets.append(len(group_source_offsets) - 1)
            cumulative_weights.extend(
                float(item) for item in locality_cumulative_weights[locality_index]
            )
            locality_cumulative_offsets.append(len(cumulative_weights))
            fallback_sources.extend(
                int(item) for item in locality_fallback_sources[locality_index]
            )
            locality_fallback_offsets.append(len(fallback_sources))

        fingerprint = (
            tuple(world.ordered_locality_ids or sorted(world.localities)),
            tuple(sorted(world.security_posts)),
            tuple(sorted(world.formations)),
            tuple(
                world.active_insurgent_organization_ids
                if world.execution_profile == "particle"
                else sorted(
                    organization.organization_id
                    for organization in world.organizations.values()
                    if organization.kind is OrganizationKind.INSURGENT
                    and organization.status == "active"
                )
            ),
            tuple(sorted(world.social_communities)),
        )
        return cls(
            codes, observer, node, source, source_type, locality,
            target_offsets, target_actor, locality_ids,
            tuple(locality_source_groups), tuple(locality_fallback_sources),
            tuple(locality_community_ids), tuple(locality_cumulative_weights),
            tuple(always_sources), fingerprint,
            native_initial_sources=initial_sources,
            native_member_sources=member_sources,
            native_locality_group_offsets=locality_group_offsets,
            native_group_source_offsets=group_source_offsets,
            native_group_sources=group_sources,
            native_locality_cumulative_offsets=locality_cumulative_offsets,
            native_cumulative_weights=cumulative_weights,
            native_locality_fallback_offsets=locality_fallback_offsets,
            native_fallback_sources=fallback_sources,
        )

    def __len__(self) -> int:
        return len(self.observer)

    def targets(self, index: int) -> tuple[int, ...]:
        start = self.target_offsets[index]
        end = self.target_offsets[index + 1]
        return tuple(self.target_actor[start:end])

    def source_enabled(self, world: Any, source_index: int) -> bool:
        """Return dynamic source eligibility without consuming randomness."""
        source_index = int(source_index)
        kind = self.codes.value(self.source_type[source_index])
        source_id = self.codes.value(self.source[source_index])
        if source_id is None:
            return False
        if kind == "fixed_post":
            post = world.security_posts.get(source_id)
            if post is None or post.available_fraction <= 0:
                return False
            formation = (
                world.formations.get(post.formation_id)
                if post.formation_id else None
            )
            return not (
                formation is not None
                and (formation.moving or formation.available_personnel() <= 0)
            )
        if kind == "organization_member":
            formation = world.formations.get(source_id)
            return bool(
                formation is not None
                and not formation.moving
                and formation.available_personnel() > 0
            )
        return True

    def dynamic_boundary_sources(
        self, world: Any
    ) -> tuple[array, array]:
        """Filter posts/members before any report-gate RNG draw."""
        return (
            array(
                "I",
                (
                    int(index) for index in self.native_initial_sources
                    if self.source_enabled(world, int(index))
                ),
            ),
            array(
                "I",
                (
                    int(index) for index in self.native_member_sources
                    if self.source_enabled(world, int(index))
                ),
            ),
        )

    def selected_source_indices(
        self, rng: Any, world: Any | None = None
    ) -> tuple[int, ...]:
        """Select exact background source rows using the reference draw order.

        This materialized convenience API is useful for diagnostics.  The
        event engine uses :meth:`iter_selected_source_indices` so each
        locality choice occurs at the same point as the reference source's
        report/detection draws.
        """
        return tuple(self.iter_selected_source_indices(rng, world=world))

    def iter_selected_source_indices(
        self, rng: Any, world: Any | None = None
    ):
        """Yield sources while preserving the reference interleaving.

        Community selection is deliberately lazy.  In the reference engine,
        fixed-post reports run before the first locality is sampled, and each
        subsequent locality is sampled only after the preceding locality's
        report work has consumed its RNG draws.
        """
        selected = self.always_sources
        for item in selected:
            source_kind = self.codes.value(self.source_type[item])
            if source_kind == "fixed_post" or (
                source_kind != "organization_member"
                and not any(self.locality_source_groups)
            ):
                if world is None or self.source_enabled(world, item):
                    yield item
        for index, groups in enumerate(self.locality_source_groups):
            if groups:
                if len(groups) == 1:
                    # random.choices over a singleton consumes one draw in the
                    # reference implementation and must do so here as well.
                    rng.random()
                    yield from groups[0]
                else:
                    weights = self.locality_cumulative_weights[index]
                    choice = rng.choices(
                        range(len(groups)), cum_weights=weights, k=1
                    )[0]
                    yield from groups[int(choice)]
            else:
                yield from self.locality_fallback_sources[index]
        for item in selected:
            if self.codes.value(self.source_type[item]) == "organization_member":
                if world is None or self.source_enabled(world, item):
                    yield item

    def is_current_for(self, world: Any) -> bool:
        current = (
            tuple(world.ordered_locality_ids or sorted(world.localities)),
            tuple(sorted(world.security_posts)),
            tuple(sorted(world.formations)),
            tuple(
                world.active_insurgent_organization_ids
                if world.execution_profile == "particle"
                else sorted(
                    organization.organization_id
                    for organization in world.organizations.values()
                    if organization.kind is OrganizationKind.INSURGENT
                    and organization.status == "active"
                )
            ),
            tuple(sorted(world.social_communities)),
        )
        return current == self.fingerprint


def _numeric_event_weight(
    world: Any | None,
    *,
    codes: NumericIdTable,
    observer_code: int,
    recipient_code: int,
    source_code: int,
    source_type_code: int,
    locality_code: int,
    target_actor_code: int,
    target_formation_code: int,
    timestamp: float,
    observation_type: str,
    confidence: float,
    quality: float,
    fallback: float,
    current_time: float | None = None,
) -> float:
    """Return the object-free equivalent of local ``fuse_observation`` weight."""
    if world is None:
        return fallback
    from .information import (
        _corroboration_weight,
        _decay_rate,
        language_comprehension,
        source_trust,
    )

    recipient_id = codes.value(recipient_code)
    source_id = codes.value(source_code) or ""
    source_type = codes.value(source_type_code) or ""
    locality_id = codes.value(locality_code)
    target_actor_id = codes.value(target_actor_code) or "*"
    if recipient_id is None or locality_id is None:
        return fallback
    observer_id = codes.value(observer_code)
    recipient_actor = (
        recipient_id
        if recipient_id in world.organizations
        else world.formations[recipient_id].organization_id
        if recipient_id in world.formations
        else observer_id or recipient_id
    )
    history_key = (target_actor_id, locality_id, observation_type)
    history = world.observation_source_index.get(history_key, ())
    correlation = world.config.information.source_correlation.get(source_type, 0.5)
    corroboration = _corroboration_weight(
        history, timestamp, source_id, correlation
    )
    age_quality = exp(
        -_decay_rate(
            world,
            observation_type,
            codes.value(target_formation_code) if target_formation_code else None,
        ) * max(
            0.0,
            float(timestamp if current_time is None else current_time) - float(timestamp),
        )
    )
    trust = source_trust(
        world, recipient_actor, source_type, locality_id, source_id
    )
    language = language_comprehension(
        world, recipient_actor, locality_id, source_type, source_id
    )
    return max(
        0.0,
        min(
            1.0,
            float(confidence) * float(quality) * trust
            * (language ** world.config.information.language_fusion_weight)
            * age_quality
            * (1.0 + world.config.information.corroboration_bonus
               * min(3.0, corroboration)),
        ),
    )


def _record_numeric_history(
    world: Any | None,
    *,
    codes: NumericIdTable,
    source_code: int,
    source_type_code: int,
    locality_code: int,
    target_actor_code: int,
    timestamp: float,
    observation_type: str,
) -> None:
    """Append one bounded source-history row without creating an observation."""
    if world is None:
        return
    source_id = codes.value(source_code) or ""
    locality_id = codes.value(locality_code)
    target_actor_id = codes.value(target_actor_code) or "*"
    if locality_id is None:
        return
    key = (target_actor_id, locality_id, observation_type)
    history = world.observation_source_index.setdefault(key, deque())
    entry = (float(timestamp), source_id)
    # Keep one history entry per emitted report.  Corroboration itself counts
    # distinct source identities, so duplicates do not change the estimator,
    # but retaining them preserves the reference archive's observable order
    # (two channels may intentionally share a source ID at one timestamp).
    history.append(entry)
    cutoff = float(timestamp) - 3.0
    while history and history[0][0] < cutoff:
        history.popleft()


@dataclass(slots=True)
class NumericInformationEventEngine:
    """Execute a compiled information event without report objects.

    The source/target arrays are a dynamic numeric snapshot of one world. The
    static source order and community selection live in
    :class:`InformationSourcePlan`; this class performs report gates, noisy
    payload generation, numeric event appends, and optional packed-state
    fusions. Its per-row inputs are fixed-width arrays, so the optional native
    event ABI and the exact Python fallback share one representation.
    """

    plan: InformationSourcePlan
    report_probability: array
    source_quality_base: array
    source_trust: array
    language: array
    source_microzone: array
    source_control_target: array
    source_zone_actor: array
    source_control: array
    source_violence: array
    target_present: array
    target_personnel: array
    target_detection_probability: array
    target_formation: array
    target_alternate_actor: array
    relay_route_offsets: array
    relay_route_codes: array
    relay_source: array
    relay_destination: array
    relay_reliability: array
    relay_latency: array
    observation_noise: float = 0.08
    positive_report_confidence: float = 0.9
    negative_report_confidence: float = 0.52
    attribution_error_rate: float = 0.08
    language_fusion_weight: float = 1.0
    contradiction_memory_days: float = 30.0
    contradiction_penalty: float = 0.45
    next_sequence: int = 1
    next_relay_sequence: int = 1

    def __post_init__(self) -> None:
        source_count = len(self.plan)
        for name in (
            "report_probability", "source_quality_base", "source_trust",
            "language", "source_microzone", "source_control_target",
            "source_zone_actor", "source_violence",
        ):
            if len(getattr(self, name)) != source_count:
                raise ValueError(f"{name} must contain one value per source")
        for name in (
            "target_present", "target_personnel", "target_detection_probability",
            "target_formation", "target_alternate_actor",
        ):
            if len(getattr(self, name)) != len(self.plan.target_actor):
                raise ValueError(f"{name} must contain one value per target row")
        if len(self.source_control) != source_count * len(CONTROL_DIMENSIONS):
            raise ValueError("source_control must contain seven values per source")
        if len(self.relay_route_offsets) != source_count + 1:
            raise ValueError("relay_route_offsets must contain one interval per source")
        for name in (
            "relay_source", "relay_destination", "relay_reliability", "relay_latency",
        ):
            if len(getattr(self, name)) != source_count:
                raise ValueError(f"{name} must contain one value per source")
        if float(self.contradiction_memory_days) <= 0.0:
            raise ValueError("contradiction_memory_days must be positive")

    @classmethod
    def from_world(
        cls,
        world: Any,
        *,
        plan: InformationSourcePlan | None = None,
    ) -> "NumericInformationEventEngine":
        """Compile current world inputs while consuming no stochastic draws."""
        from .information import (
            _actual_target_presence,
            _information_formation_index,
            _is_insurgent_actor,
            _report_probability,
            detection_probability,
            false_positive_probability,
            language_comprehension,
            source_quality,
            source_trust,
        )
        from .logistics import command_path

        plan = plan or InformationSourcePlan.from_world(world)
        codes = plan.codes
        source_count = len(plan)
        report_probability = array("d")
        source_quality_base = array("d")
        source_trust_values = array("d")
        language = array("d")
        source_microzone = array("I")
        source_control_target = array("I")
        source_zone_actor = array("I")
        source_control = array("d")
        source_violence = array("d")
        target_present = array("B")
        target_personnel = array("d")
        target_detection_probability = array("d")
        target_formation = array("I")
        target_alternate_actor = array("I")
        relay_route_offsets = array("Q", [0])
        relay_route_codes = array("I")
        relay_source = array("I")
        relay_destination = array("I")
        relay_reliability = array("d")
        relay_latency = array("d")
        formation_index = _information_formation_index(world)

        for source_index in range(source_count):
            observer_id = codes.value(plan.observer[source_index])
            source_id = codes.value(plan.source[source_index])
            source_type = codes.value(plan.source_type[source_index])
            locality_id = codes.value(plan.locality[source_index])
            if observer_id is None or source_id is None or source_type is None or locality_id is None:
                raise ValueError("compiled source plan contains a missing identity")
            report_probability.append(float(_report_probability(
                world, observer_id, locality_id, source_type, source_id,
            )))
            source_quality_base.append(float(source_quality(
                world, observer_id, source_type, locality_id, source_id, None,
            )))
            source_trust_values.append(float(source_trust(
                world, observer_id, source_type, locality_id, source_id,
            )))
            language.append(float(language_comprehension(
                world, observer_id, locality_id, source_type, source_id,
            )))
            # ``_primary_zone`` is the reference resolver.  The cache is
            # normally populated by generation, but compiled callers must
            # also work with hand-built worlds and freshly-mutated worlds.
            from .information import _primary_zone
            primary_microzone = _primary_zone(world, locality_id)
            if len(plan.source_microzone) == source_count:
                source_microzone.append(int(plan.source_microzone[source_index]))
            else:
                source_microzone.append(codes.code(primary_microzone))
            control_target = (
                observer_id
                if observer_id in world.localities[locality_id].control
                else "government"
            )
            source_control_target.append(codes.code(control_target))
            node_id = codes.value(plan.node[source_index])
            zone_actor = (
                world.formations[node_id].organization_id
                if node_id in world.formations
                else node_id or observer_id
            )
            if len(plan.source_zone_actor) == source_count:
                source_zone_actor.append(int(plan.source_zone_actor[source_index]))
            else:
                source_zone_actor.append(codes.code(zone_actor))
            vector = world.localities[locality_id].control.get(control_target, ControlVector())
            source_control.extend(float(getattr(vector, dimension)) for dimension in CONTROL_DIMENSIONS)
            source_violence.append(float(world.localities[locality_id].violence))

            destination_id = f"CMD:{observer_id}"
            relay_source_id = codes.value(plan.node[source_index]) or source_id
            route, reliability, latency = command_path(
                world, observer_id, relay_source_id, destination_id
            )
            if not route:
                route = [relay_source_id, destination_id]
                reliability = float(world.config.information.relay_base_reliability)
                organization = world.organizations.get(observer_id)
                if organization is not None:
                    reliability *= 0.7 + 0.3 * organization.institutional_quality
                latency = 0.0
            latency += float(
                world.config.information.source_latency_hours.get(source_type, 0.0)
            )
            if len(route) - 1 > world.config.information.relay_max_hops:
                route = route[:world.config.information.relay_max_hops + 1]
                reliability = max(0.01, reliability)
            relay_route_codes.extend(codes.code(item) for item in route)
            relay_route_offsets.append(len(relay_route_codes))
            relay_source.append(codes.code(relay_source_id))
            relay_destination.append(codes.code(destination_id))
            relay_reliability.append(max(0.0, min(1.0, float(reliability))))
            relay_latency.append(max(0.0, float(latency)))

            start = plan.target_offsets[source_index]
            end = plan.target_offsets[source_index + 1]
            for target_index in range(start, end):
                target_actor = codes.value(plan.target_actor[target_index])
                if target_actor is None:
                    raise ValueError("compiled target plan contains a missing actor")
                formation_id: str | None = None
                if len(plan.target_formation) == len(plan.target_actor):
                    formation_id = codes.value(plan.target_formation[target_index])
                if formation_id is None and source_type in {"organization_member", "interpreter"}:
                    formations = formation_index.get((target_actor, locality_id), ())
                    if formations:
                        formation_id = formations[0].formation_id
                # Background channels use the locality's primary zone, while
                # a patrol/contact-sized plan carries the observer's actual
                # current zone. The reference resolver uses that observation
                # microzone for presence, detection, and conditional
                # attribution draws; collapsing every source to the primary
                # zone changes both the payload and the RNG stream.
                microzone_id = (
                    codes.value(source_microzone[source_index])
                    or primary_microzone
                )
                present, personnel, actual_id = _actual_target_presence(
                    world, target_actor, locality_id, formation_id, microzone_id,
                    formation_index,
                )
                if present:
                    probability = detection_probability(
                        world,
                        codes.value(plan.node[source_index]) or observer_id,
                        actual_id or formation_id,
                        locality_id,
                        source_type,
                        microzone_id,
                    )
                else:
                    probability = false_positive_probability(
                        world,
                        codes.value(plan.node[source_index]) or observer_id,
                        locality_id,
                        source_type,
                        microzone_id,
                    )
                target_present.append(1 if present else 0)
                target_personnel.append(float(personnel))
                target_detection_probability.append(float(probability))
                target_formation.append(codes.code(formation_id))
                alternate = None
                if _is_insurgent_actor(world, target_actor):
                    if "government" in world.organizations:
                        alternate = "government"
                elif "insurgent" in world.organizations:
                    alternate = "insurgent"
                target_alternate_actor.append(codes.code(alternate))

        return cls(
            plan,
            report_probability,
            source_quality_base,
            source_trust_values,
            language,
            source_microzone,
            source_control_target,
            source_zone_actor,
            source_control,
            source_violence,
            target_present,
            target_personnel,
            target_detection_probability,
            target_formation,
            target_alternate_actor,
            relay_route_offsets,
            relay_route_codes,
            relay_source,
            relay_destination,
            relay_reliability,
            relay_latency,
            observation_noise=float(world.config.observation_noise),
            positive_report_confidence=float(world.config.information.positive_report_confidence),
            negative_report_confidence=float(world.config.information.negative_report_confidence),
            attribution_error_rate=float(world.config.information.attribution_error_rate),
            language_fusion_weight=float(world.config.information.language_fusion_weight),
            contradiction_memory_days=float(world.config.information.contradiction_memory_days),
            contradiction_penalty=float(world.config.information.contradiction_penalty),
            next_sequence=int(world.next_observation_sequence),
            next_relay_sequence=int(world.next_information_relay_sequence),
        )

    def process(
        self,
        rng: Any,
        time: float,
        *,
        event_buffer: InformationEventBuffer | None = None,
        control_state: EnsembleBeliefState | None = None,
        presence_state: EnsembleBeliefState | None = None,
        node_presence_state: EnsembleBeliefState | None = None,
        zone_state: EnsembleBeliefState | None = None,
        relay_buffer: RelayBuffer | None = None,
        record_negative: bool = True,
        world: Any | None = None,
    ) -> dict[str, int | float | InformationEventBuffer | RelayBuffer]:
        """Run one event using CPython ``random.Random`` draw order.

        The normal path is a fixed-width Python numeric fallback.  When the
        optional DLL exposes the compiled-plan ABI, the complete source
        selection/report-draw pass crosses the Python/native boundary once.
        The grouped ABI remains available as an exact compatibility fallback:
        each locality choice is made immediately before its selected sources,
        exactly where the reference generator makes it, so native report draws
        cannot perturb later community selection draws.
        """
        buffer = (
            event_buffer
            if event_buffer is not None
            else InformationEventBuffer(codebook=self.plan.codes)
        )
        if buffer.codes is not self.plan.codes:
            raise ValueError("event buffer must use the compiled source codebook")
        control_updates: list[tuple[int, tuple[str, ...], float, float, Sequence[float]]] = []
        presence_updates: list[tuple[int, tuple[str, ...], float, float, float, float]] = []
        node_updates: list[tuple[int, tuple[str, ...], float, float, float, float]] = []
        zone_updates: list[tuple[int, tuple[str, ...], float, float, float]] = []
        prior_confidence = (
            float(world.config.information.prior_confidence)
            if world is not None else 0.35
        )
        source_attempts = 0
        reported_sources = 0
        detection_rows = 0
        control_rows = 0
        detected_rows = 0
        relay_rows = 0

        def append_relay(source_index: int, observation_sequence: int) -> None:
            nonlocal relay_rows
            if relay_buffer is None:
                return
            source_code = int(self.relay_source[source_index])
            destination_code = int(self.relay_destination[source_index])
            if source_code == destination_code:
                return
            start = int(self.relay_route_offsets[source_index])
            end = int(self.relay_route_offsets[source_index + 1])
            latency = float(self.relay_latency[source_index])
            relay_buffer.append_codes(
                self.next_relay_sequence,
                observation_sequence=observation_sequence,
                organization=int(self.plan.observer[source_index]),
                source=source_code,
                destination=destination_code,
                route=self.relay_route_codes[start:end],
                sent_at=float(time),
                arrives_at=float(time) + latency / 24.0,
                reliability=float(self.relay_reliability[source_index]),
                latency_hours=latency,
            )
            self.next_relay_sequence += 1
            relay_rows += 1

        def consume_detection(
            source_index: int,
            *,
            target_actor_code: int,
            target_formation_code: int,
            target_present: bool,
            probability: float,
            detected: bool,
            quality: float,
            confidence: float,
            presence: float,
            personnel: float,
            attribution_confidence: float,
        ) -> None:
            nonlocal detection_rows, detected_rows
            observer_code = int(self.plan.observer[source_index])
            node_code = int(self.plan.node[source_index])
            source_code = int(self.plan.source[source_index])
            source_type_code = int(self.plan.source_type[source_index])
            locality_code = int(self.plan.locality[source_index])
            microzone_code = int(self.source_microzone[source_index])
            source_type = self.plan.codes.value(source_type_code)
            trust = float(self.source_trust[source_index])
            language = float(self.language[source_index])
            recipient_code = node_code or observer_code
            observation_sequence = self.next_sequence
            buffer.append_detection_codes(
                observation_sequence,
                observer=observer_code,
                node=node_code,
                source=source_code,
                source_type=source_type_code,
                locality=locality_code,
                microzone=microzone_code,
                target_actor=int(target_actor_code),
                target_formation=int(target_formation_code),
                timestamp=time,
                confidence=float(confidence),
                quality=float(quality),
                presence=float(presence),
                personnel=float(personnel),
                detection_probability=float(probability),
                detected=bool(detected),
                attribution_confidence=float(attribution_confidence),
            )
            append_relay(source_index, observation_sequence)
            self.next_sequence += 1
            detection_rows += 1
            detected_rows += int(detected)
            weight = _numeric_event_weight(
                world,
                codes=self.plan.codes,
                observer_code=observer_code,
                recipient_code=recipient_code,
                source_code=source_code,
                source_type_code=source_type_code,
                locality_code=locality_code,
                target_actor_code=int(target_actor_code),
                target_formation_code=int(target_formation_code),
                timestamp=float(time),
                observation_type="detection",
                confidence=float(confidence),
                quality=float(quality),
                fallback=max(
                    0.0,
                    min(
                        1.0,
                        float(confidence) * float(quality) * trust
                        * (language ** self.language_fusion_weight),
                    ),
                ),
            )
            _record_numeric_history(
                world,
                codes=self.plan.codes,
                source_code=source_code,
                source_type_code=source_type_code,
                locality_code=locality_code,
                target_actor_code=int(target_actor_code),
                timestamp=float(time),
                observation_type="detection",
            )
            if world is not None and world.execution_profile != "particle":
                outcome = (
                    "true_positive" if target_present and detected else
                    "false_negative" if target_present else
                    "false_positive" if detected else "true_negative"
                )
                world.information_detections[outcome] = (
                    world.information_detections.get(outcome, 0) + 1
                )
                by_source = world.information_detection_by_source.setdefault(
                    source_type or "unknown",
                    {"true_positive": 0, "false_positive": 0,
                     "false_negative": 0, "true_negative": 0},
                )
                by_source[outcome] += 1
            if presence_state is None and node_presence_state is None:
                return
            observer_id = self.plan.codes.value(recipient_code)
            target_actor_id = self.plan.codes.value(int(target_actor_code))
            locality_id = self.plan.codes.value(locality_code)
            location_id = self.plan.codes.value(microzone_code) or "*"
            target_id = self.plan.codes.value(int(target_formation_code)) or "*"
            if observer_id is None or target_actor_id is None or locality_id is None:
                return
            update = (
                0,
                (observer_id, target_actor_id, f"{locality_id}:{location_id}", target_id),
                float(time), weight, float(presence), float(personnel),
            )
            wildcard = None
            # A report is fused into exactly one local belief namespace: the
            # field node when it exists, otherwise the observer actor.  Do
            # not provision the unused namespace merely because a numeric row
            # carries a formation target; doing so creates inert default rows
            # that the reference pipeline never creates and bloats every
            # packed lane.
            target_state = (
                node_presence_state if node_code else presence_state
            )
            if target_state is not None:
                if target_formation_code:
                    update_key = update[1]
                    wildcard = (update_key[0], update_key[1], update_key[2], "*")
                    target_state.ensure_key(
                        wildcard, prior_confidence=prior_confidence
                    )
                    target_state.ensure_key(
                        update_key, prior_confidence=prior_confidence
                    )
                else:
                    target_state.ensure_key(
                        update[1], prior_confidence=prior_confidence
                    )
            if node_code:
                if node_presence_state is not None:
                    node_updates.append(update)
                    if wildcard is not None:
                        node_updates.append((0, wildcard, float(time), weight, float(presence), float(personnel)))
            elif presence_state is not None:
                presence_updates.append(update)
                if wildcard is not None:
                    presence_updates.append((0, wildcard, float(time), weight, float(presence), float(personnel)))

        def consume_control(
            source_index: int,
            *,
            estimated_control: Sequence[float],
            quality: float,
            confidence: float,
            violence: float,
        ) -> None:
            nonlocal control_rows
            observer_code = int(self.plan.observer[source_index])
            node_code = int(self.plan.node[source_index])
            source_code = int(self.plan.source[source_index])
            source_type_code = int(self.plan.source_type[source_index])
            locality_code = int(self.plan.locality[source_index])
            microzone_code = int(self.source_microzone[source_index])
            trust = float(self.source_trust[source_index])
            language = float(self.language[source_index])
            recipient_code = node_code or observer_code
            control_target = int(self.source_control_target[source_index])
            observation_sequence = self.next_sequence
            buffer.append_control_codes(
                observation_sequence,
                observer=observer_code,
                node=node_code,
                source=source_code,
                source_type=source_type_code,
                locality=locality_code,
                microzone=microzone_code,
                target_actor=control_target,
                timestamp=time,
                confidence=float(confidence),
                quality=float(quality),
                control=estimated_control,
                physical_control=float(estimated_control[1]),
                violence=float(violence),
            )
            append_relay(source_index, observation_sequence)
            self.next_sequence += 1
            control_rows += 1
            weight = _numeric_event_weight(
                world,
                codes=self.plan.codes,
                observer_code=observer_code,
                recipient_code=recipient_code,
                source_code=source_code,
                source_type_code=source_type_code,
                locality_code=locality_code,
                target_actor_code=control_target,
                target_formation_code=0,
                timestamp=float(time),
                observation_type="physical_control",
                confidence=float(confidence),
                quality=float(quality),
                fallback=max(
                    0.0,
                    min(
                        1.0,
                        float(confidence) * float(quality) * trust
                        * (language ** self.language_fusion_weight),
                    ),
                ),
            )
            _record_numeric_history(
                world,
                codes=self.plan.codes,
                source_code=source_code,
                source_type_code=source_type_code,
                locality_code=locality_code,
                target_actor_code=control_target,
                timestamp=float(time),
                observation_type="physical_control",
            )
            if control_state is not None:
                observer_id = self.plan.codes.value(recipient_code)
                target_id = self.plan.codes.value(control_target)
                locality_id = self.plan.codes.value(locality_code)
                if observer_id is not None and target_id is not None and locality_id is not None:
                    key = (observer_id, target_id, locality_id)
                    control_state.ensure_key(key, prior_confidence=prior_confidence)
                    control_updates.append((0, key, float(time), weight, estimated_control))
            if zone_state is not None and microzone_code:
                recipient_id = self.plan.codes.value(
                    self.source_zone_actor[source_index]
                ) or self.plan.codes.value(recipient_code)
                microzone_id = self.plan.codes.value(microzone_code)
                if recipient_id is not None and microzone_id is not None:
                    zone_key = (recipient_id, microzone_id)
                    # The reference auxiliary zone recurrence only updates an
                    # already represented actor/zone state; it does not
                    # invent a zone row for every administrative/community
                    # report. Preserve that sparse topology in the numeric
                    # runtime as well.
                    if zone_key in zone_state.key_to_index:
                        zone_updates.append(
                            (0, zone_key, float(time), weight,
                             float(estimated_control[1]))
                        )

        def consume_native_rows(native_result: Any) -> int:
            reported = set()
            for row_index in range(native_result.row_count):
                source_index = int(native_result.source_index[row_index])
                reported.add(source_index)
                if int(native_result.kind[row_index]) == 1:
                    consume_detection(
                        source_index,
                        target_actor_code=int(native_result.target_actor[row_index]),
                        target_formation_code=int(native_result.target_formation[row_index]),
                        target_present=bool(native_result.target_present[row_index]),
                        probability=float(native_result.detection_probability[row_index]),
                        detected=bool(native_result.detected[row_index]),
                        quality=float(native_result.quality[row_index]),
                        confidence=float(native_result.confidence[row_index]),
                        presence=float(native_result.presence[row_index]),
                        personnel=float(native_result.personnel[row_index]),
                        attribution_confidence=float(native_result.attribution_confidence[row_index]),
                    )
                else:
                    offset = row_index * len(CONTROL_DIMENSIONS)
                    consume_control(
                        source_index,
                        estimated_control=tuple(float(value) for value in native_result.control[offset:offset + len(CONTROL_DIMENSIONS)]),
                        quality=float(native_result.quality[row_index]),
                        confidence=float(native_result.confidence[row_index]),
                        violence=float(native_result.violence[row_index]),
                    )
            return len(reported)

        def native_rng_compatible() -> bool:
            if not hasattr(rng, "getstate") or not hasattr(rng, "setstate"):
                return False
            state = rng.getstate()
            return (
                isinstance(state, tuple) and len(state) == 3
                and state[0] == 3
                and isinstance(state[1], tuple) and len(state[1]) == 625
            )

        native_enabled = False
        native_plan_enabled = False
        if native_rng_compatible():
            from .native_kernels import (
                information_event_enabled,
                information_event_plan_enabled,
            )

            native_enabled = information_event_enabled()
            native_plan_enabled = (
                native_enabled
                and information_event_plan_enabled()
                and len(self.plan.native_locality_group_offsets)
                == len(self.plan.locality_ids) + 1
                and len(self.plan.native_locality_cumulative_offsets)
                == len(self.plan.locality_ids) + 1
                and len(self.plan.native_locality_fallback_offsets)
                == len(self.plan.locality_ids) + 1
            )

        if native_enabled:
            from .native_kernels import native_information_event_batch

            if world is not None:
                dynamic_initial, dynamic_members = (
                    self.plan.dynamic_boundary_sources(world)
                )
                initial_sources = tuple(int(item) for item in dynamic_initial)
                member_sources = tuple(int(item) for item in dynamic_members)
            else:
                initial_sources = tuple(int(item) for item in self.plan.native_initial_sources)
                member_sources = tuple(int(item) for item in self.plan.native_member_sources)
            def process_native_batch(batch: Sequence[int]) -> None:
                nonlocal source_attempts, reported_sources
                source_attempts += len(batch)
                native_result = native_information_event_batch(
                    rng,
                    selected_sources=array("I", batch),
                    source_observer=self.plan.observer,
                    source_node=self.plan.node,
                    source=self.plan.source,
                    source_type=self.plan.source_type,
                    source_locality=self.plan.locality,
                    source_microzone=self.source_microzone,
                    source_control_target=self.source_control_target,
                    source_control=self.source_control,
                    source_violence=self.source_violence,
                    report_probability=self.report_probability,
                    source_quality_base=self.source_quality_base,
                    source_trust=self.source_trust,
                    language=self.language,
                    target_offsets=self.plan.target_offsets,
                    target_actor=self.plan.target_actor,
                    target_present=self.target_present,
                    target_personnel=self.target_personnel,
                    target_detection_probability=self.target_detection_probability,
                    target_formation=self.target_formation,
                    target_alternate_actor=self.target_alternate_actor,
                    time=float(time),
                    observation_noise=self.observation_noise,
                    positive_report_confidence=self.positive_report_confidence,
                    negative_report_confidence=self.negative_report_confidence,
                    attribution_error_rate=self.attribution_error_rate,
                    record_negative=record_negative,
                    next_sequence=self.next_sequence,
                )
                if native_result is None:
                    raise RuntimeError("native information event lost RNG compatibility")
                reported_sources += consume_native_rows(native_result)
                if native_result.next_sequence != self.next_sequence:
                    raise RuntimeError("native information sequence disagrees with emitted rows")

            if native_plan_enabled:
                from .native_kernels import native_information_event_plan

                native_result = native_information_event_plan(
                    rng,
                    initial_sources=array("I", initial_sources),
                    member_sources=array("I", member_sources),
                    locality_group_offsets=self.plan.native_locality_group_offsets,
                    group_source_offsets=self.plan.native_group_source_offsets,
                    group_sources=self.plan.native_group_sources,
                    locality_cumulative_offsets=(
                        self.plan.native_locality_cumulative_offsets
                    ),
                    cumulative_weights=self.plan.native_cumulative_weights,
                    locality_fallback_offsets=(
                        self.plan.native_locality_fallback_offsets
                    ),
                    fallback_sources=self.plan.native_fallback_sources,
                    source_observer=self.plan.observer,
                    source_node=self.plan.node,
                    source=self.plan.source,
                    source_type=self.plan.source_type,
                    source_locality=self.plan.locality,
                    source_microzone=self.source_microzone,
                    source_control_target=self.source_control_target,
                    source_control=self.source_control,
                    source_violence=self.source_violence,
                    report_probability=self.report_probability,
                    source_quality_base=self.source_quality_base,
                    source_trust=self.source_trust,
                    language=self.language,
                    target_offsets=self.plan.target_offsets,
                    target_actor=self.plan.target_actor,
                    target_present=self.target_present,
                    target_personnel=self.target_personnel,
                    target_detection_probability=self.target_detection_probability,
                    target_formation=self.target_formation,
                    target_alternate_actor=self.target_alternate_actor,
                    time=float(time),
                    observation_noise=self.observation_noise,
                    positive_report_confidence=self.positive_report_confidence,
                    negative_report_confidence=self.negative_report_confidence,
                    attribution_error_rate=self.attribution_error_rate,
                    record_negative=record_negative,
                    next_sequence=self.next_sequence,
                )
                if native_result is None:
                    raise RuntimeError("native information plan lost RNG compatibility")
                source_attempts += int(native_result.source_attempts)
                reported_sources += consume_native_rows(native_result)
                if native_result.next_sequence != self.next_sequence:
                    raise RuntimeError("native information sequence disagrees with emitted rows")
            else:
                # Do not construct the complete batch list first: locality
                # selection draws must occur after fixed-post report draws and
                # before the selected locality's report draws.
                if initial_sources:
                    process_native_batch(initial_sources)
                for locality_index, groups in enumerate(self.plan.locality_source_groups):
                    if groups:
                        if len(groups) == 1:
                            # random.choices over one item still consumes one draw.
                            rng.random()
                            batch = groups[0]
                        else:
                            choice = rng.choices(
                                range(len(groups)),
                                cum_weights=self.plan.locality_cumulative_weights[locality_index],
                                k=1,
                            )[0]
                            batch = groups[int(choice)]
                    else:
                        batch = self.plan.locality_fallback_sources[locality_index]
                    if batch:
                        process_native_batch(batch)
                if member_sources:
                    process_native_batch(member_sources)
        else:
            for source_index in self.plan.iter_selected_source_indices(
                rng, world=world
            ):
                source_attempts += 1
                if rng.random() >= self.report_probability[source_index]:
                    continue
                reported_sources += 1
                quality_base = float(self.source_quality_base[source_index])
                trust = float(self.source_trust[source_index])
                language = float(self.language[source_index])
                start = self.plan.target_offsets[source_index]
                end = self.plan.target_offsets[source_index + 1]
                for target_index in range(start, end):
                    present = bool(self.target_present[target_index])
                    probability = float(self.target_detection_probability[target_index])
                    detected = bool(rng.random() < probability)
                    if not detected and not record_negative:
                        continue
                    quality = max(0.0, min(1.0, quality_base * (0.85 + 0.3 * rng.random())))
                    personnel = float(self.target_personnel[target_index])
                    if detected:
                        estimate = personnel * (0.65 + 0.7 * rng.random())
                        if not present:
                            estimate = max(1.0, rng.uniform(20.0, 250.0))
                    else:
                        estimate = 0.0
                    attribution_mistake = bool(
                        present and detected
                        and rng.random() < self.attribution_error_rate
                    )
                    reported_actor = (
                        int(self.target_alternate_actor[target_index])
                        if attribution_mistake and self.target_alternate_actor[target_index]
                        else int(self.plan.target_actor[target_index])
                    )
                    formation = int(self.target_formation[target_index])
                    reported_formation = 0 if attribution_mistake else formation
                    consume_detection(
                        source_index,
                        target_actor_code=reported_actor,
                        target_formation_code=reported_formation,
                        target_present=present,
                        probability=probability,
                        detected=detected,
                        quality=quality,
                        confidence=(
                            self.positive_report_confidence
                            if detected else self.negative_report_confidence
                        ),
                        presence=1.0 if detected else 0.0,
                        personnel=estimate,
                        attribution_confidence=0.25 if attribution_mistake else 0.9,
                    )
                control_quality = max(
                    0.0,
                    min(1.0, quality_base * (0.85 + 0.3 * rng.random())),
                )
                noise = float(self.observation_noise) * (
                    1.35 - 0.55 * control_quality * language
                )
                control_offset = source_index * len(CONTROL_DIMENSIONS)
                estimated_control = tuple(
                    max(
                        0.0,
                        min(
                            1.0,
                            float(self.source_control[control_offset + dimension])
                            + rng.uniform(-noise, noise),
                        ),
                    )
                    for dimension in range(len(CONTROL_DIMENSIONS))
                )
                violence = max(
                    0.0,
                    min(
                        1.0,
                        float(self.source_violence[source_index])
                        + rng.uniform(-noise, noise),
                    ),
                )
                consume_control(
                    source_index,
                    estimated_control=estimated_control,
                    quality=control_quality,
                    confidence=max(0.0, min(1.0, 0.45 + 0.45 * trust)),
                    violence=violence,
                )

        if control_state is not None:
            control_state.fuse_control(
                control_updates,
                contradiction_memory_days=self.contradiction_memory_days,
                contradiction_penalty=self.contradiction_penalty,
            )
        if presence_state is not None:
            presence_state.fuse_presence(
                presence_updates,
                contradiction_memory_days=self.contradiction_memory_days,
                contradiction_penalty=self.contradiction_penalty,
            )
        if node_presence_state is not None:
            node_presence_state.fuse_presence(
                node_updates,
                contradiction_memory_days=self.contradiction_memory_days,
                contradiction_penalty=self.contradiction_penalty,
            )
        if zone_state is not None:
            zone_state.fuse_zone(
                zone_updates,
                contradiction_memory_days=self.contradiction_memory_days,
                contradiction_penalty=self.contradiction_penalty,
            )
        return {
            "source_attempts": source_attempts,
            "reported_sources": reported_sources,
            "detection_rows": detection_rows,
            "detected_rows": detected_rows,
            "control_rows": control_rows,
            "relay_rows": relay_rows,
            "event_rows": len(buffer),
            "event_buffer": buffer,
            **({"relay_buffer": relay_buffer} if relay_buffer is not None else {}),
        }


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
        return (*([0.5] * 7), float(prior_confidence), 0.0, -1.0e9, 0.0, 0.0, 0.2)
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
    # A one-lane runtime can borrow the authoritative compact world's numeric
    # array instead of copying it into a second SoA and then mirroring every
    # row back after each information/patrol clock.  Multi-particle packed
    # ensembles deliberately leave this unset and own their storage outright.
    compact_backing: Any | None = field(default=None, repr=False)
    # Dirty keys are an execution boundary, not scientific state.  They let a
    # one-lane numeric runtime update only oracle objects that were actually
    # touched by fusion, rather than rewriting tens of thousands of beliefs on
    # every patrol report.
    dirty_keys: set[tuple[int, tuple[str, ...]]] = field(
        default_factory=set, repr=False
    )

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
        if self.compact_backing is not None and particle == 0:
            if isinstance(key_or_index, int):
                key = self.keys[int(key_or_index)]
            else:
                key = tuple(key_or_index)
            if hasattr(self.compact_backing, "materialize"):
                self.compact_backing.materialize(key)
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
        if self.compact_backing is not None:
            if self.particle_count != 1:
                raise RuntimeError(
                    "a compact-backed ensemble state must contain one lane"
                )
            # Append the raw row directly to the backing store.  This mirrors
            # Compact*State.ensure without requiring a rich belief object to be
            # constructed merely to allocate numeric storage.
            backing = self.compact_backing
            index = len(backing.keys)
            backing.keys.append(key)
            backing.key_to_index[key] = index
            backing.state.extend(float(value) for value in rows[0])
            if hasattr(backing, "decay_event_positions"):
                backing.decay_event_positions.append(
                    len(getattr(backing, "decay_events", ()))
                )
            self.keys = tuple(backing.keys)
            self.key_to_index = dict(backing.key_to_index)
            self.state = backing.state
            self.dirty_keys.add((0, key))
            return index
        old_entities = self.entity_count
        old_state = self.state
        self.keys = (*self.keys, key)
        self.key_to_index[key] = old_entities
        self.state = array("d")
        for particle in range(self.particle_count):
            start = particle * old_entities * self.stride
            self.state.extend(old_state[start:start + old_entities * self.stride])
            self.state.extend(float(value) for value in rows[particle])
            self.dirty_keys.add((particle, key))
        return old_entities

    def _materialize_keys(self, updates: Sequence[tuple[Any, ...]]) -> None:
        """Materialize lazy compact confidence only for rows being fused."""
        backing = self.compact_backing
        if backing is None or not hasattr(backing, "materialize"):
            return
        seen: set[tuple[str, ...]] = set()
        for update in updates:
            key = tuple(update[1])
            if key not in seen and key in backing.key_to_index:
                backing.materialize(key)
                seen.add(key)

    def mark_dirty(self, updates: Sequence[tuple[Any, ...]]) -> None:
        for update in updates:
            self.dirty_keys.add((int(update[0]), tuple(update[1])))

    def consume_dirty(self, particle: int = 0) -> tuple[tuple[str, ...], ...]:
        """Return and clear dirty keys for one packed lane in key order."""
        particle = int(particle)
        keys = sorted(
            key for lane, key in self.dirty_keys if lane == particle
        )
        self.dirty_keys = {
            item for item in self.dirty_keys if item[0] != particle
        }
        return tuple(keys)

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
        # Gather changes lane identity; stale dirty-lane metadata cannot be
        # meaningfully remapped and is unnecessary because packed filters do
        # not synchronize through one-lane oracle boundaries here.
        self.dirty_keys.clear()

    def clone(self) -> "EnsembleBeliefState":
        return type(self)(
            self.keys, self.particle_count, self.stride,
            array("d", self.state), None, set(self.dirty_keys)
        )

    def sha256(self) -> str:
        if self.compact_backing is not None and hasattr(
            self.compact_backing, "materialize"
        ):
            for key in self.keys:
                self.compact_backing.materialize(key)
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
        self._materialize_keys(updates)
        self.mark_dirty(updates)
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
        from .native_kernels import control_batch_enabled, fuse_control7_batch
        native = (
            control_batch_enabled()
            and fuse_control7_batch(
                self.state, self.state_count, indices, times, weights, observed,
                contradiction_memory_days=contradiction_memory_days,
                contradiction_penalty=contradiction_penalty,
                state_stride=self.stride,
            )
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
        self._materialize_keys(updates)
        self.mark_dirty(updates)
        indices = array("I")
        times = array("d")
        weights = array("d")
        presence = array("d")
        personnel = array("d")
        for particle, key, time, weight, observed_presence, observed_personnel in updates:
            indices.append(particle * self.entity_count + self.key_to_index[tuple(key)])
            times.append(float(time)); weights.append(float(weight))
            presence.append(float(observed_presence)); personnel.append(float(observed_personnel))
        from .native_kernels import fuse_presence_batch, information_batch_enabled
        if information_batch_enabled() and fuse_presence_batch(
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
        self._materialize_keys(updates)
        self.mark_dirty(updates)
        indices = array("I"); times = array("d"); weights = array("d"); observed = array("d")
        for particle, key, time, weight, value in updates:
            indices.append(particle * self.entity_count + self.key_to_index[tuple(key)])
            times.append(float(time)); weights.append(float(weight)); observed.append(float(value))
        from .native_kernels import fuse_zone_batch, information_batch_enabled
        if information_batch_enabled() and fuse_zone_batch(
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


def _numeric_world_belief_state(
    world: Any,
    *,
    compact_attribute: str,
    belief_attribute: str,
    stride: int,
) -> EnsembleBeliefState:
    """Load one world into a leading-dimension numeric belief state."""
    from .compact_information_state import (
        CompactControlBeliefState,
        CompactPresenceBeliefState,
        CompactZoneBeliefState,
    )

    compact = getattr(world, compact_attribute, None)
    beliefs = getattr(world, belief_attribute)
    # The optimized/ensemble world already owns a persistent compact numeric
    # representation.  Borrow that array directly whenever its key universe is
    # coherent with the oracle mapping.  This removes the former
    # compact->tuple->EnsembleBeliefState copy on every patrol/information
    # event.  Lazy presence/zone confidence is materialized per touched key by
    # ``EnsembleBeliefState`` before fusion.
    if compact is not None and set(compact.keys) == set(beliefs):
        return EnsembleBeliefState(
            tuple(compact.keys), 1, stride, compact.state,
            compact_backing=compact,
        )
    keys = tuple(sorted(set(compact.keys if compact is not None else ()) | set(beliefs)))
    if stride == CONTROL_STATE_STRIDE:
        row_factory = CompactControlBeliefState._belief_row
    elif stride == PRESENCE_STATE_STRIDE:
        row_factory = CompactPresenceBeliefState._belief_row
    else:
        row_factory = CompactZoneBeliefState._belief_row
    rows = []
    for key in keys:
        if compact is not None and key in compact.key_to_index:
            rows.append(compact.row(key))
        elif key in beliefs:
            rows.append(row_factory(beliefs[key]))
        else:
            rows.append(_default_row(
                stride,
                prior_confidence=world.config.information.prior_confidence,
            ))
    return EnsembleBeliefState.from_rows(keys, [rows], stride)


def _sync_numeric_world_state(
    world: Any,
    state: EnsembleBeliefState,
    *,
    compact_attribute: str,
    belief_attribute: str,
    keys: Sequence[tuple[str, ...]] | None = None,
) -> None:
    """Mirror one packed lane to the object model at an explicit boundary."""
    from .compact_information_state import (
        CompactControlBeliefState,
        CompactPresenceBeliefState,
        CompactZoneBeliefState,
    )
    from .entities import ActorBelief, ActorZoneBelief, PresenceBelief
    from .information import _is_insurgent_actor

    if state.particle_count != 1:
        raise ValueError("world synchronization requires exactly one packed lane")
    selected_keys = tuple(state.keys if keys is None else keys)
    backing = state.compact_backing
    if backing is not None and backing is getattr(world, compact_attribute, None):
        beliefs = getattr(world, belief_attribute)

        def ensure_control(key: tuple[str, ...]):
            if key not in beliefs:
                beliefs[key] = ActorBelief(
                    key[0], key[2], ControlVector(*([0.5] * 7)),
                    world.config.information.prior_confidence, 0.0,
                )

        def ensure_presence(key: tuple[str, ...]):
            if key not in beliefs:
                location = key[2].split(":", 1)
                locality_id = location[0]
                microzone_id = (
                    None if len(location) == 1 or location[1] == "*"
                    else location[1]
                )
                beliefs[key] = PresenceBelief(
                    key[0], key[1], locality_id,
                    target_id=None if key[3] == "*" else key[3],
                    microzone_id=microzone_id,
                    confidence=world.config.information.prior_confidence,
                )

        def ensure_zone(key: tuple[str, ...]):
            if key not in beliefs:
                beliefs[key] = ActorZoneBelief(
                    key[0], key[1], 0.5,
                    world.config.information.prior_confidence, 0.0,
                )

        for raw_key in selected_keys:
            key = tuple(raw_key)
            if key not in backing.key_to_index:
                continue
            if hasattr(backing, "materialize"):
                backing.materialize(key)
            if state.stride == CONTROL_STATE_STRIDE:
                ensure_control(key)
            elif state.stride == PRESENCE_STATE_STRIDE:
                ensure_presence(key)
            else:
                ensure_zone(key)
            backing.write_to_belief(key, beliefs[key])
            if state.stride == CONTROL_STATE_STRIDE:
                # Preserve the legacy same-side projection used by logistics.
                legacy = getattr(world, "beliefs", {}).get((key[0], key[2]))
                mirrors_legacy = (
                    _is_insurgent_actor(world, key[1])
                    and _is_insurgent_actor(world, key[0])
                ) or (
                    key[1] == "government"
                    and not _is_insurgent_actor(world, key[0])
                )
                if legacy is not None and mirrors_legacy:
                    belief = beliefs[key]
                    legacy.control_estimate = ControlVector(
                        *[
                            getattr(belief.control_estimate, dimension)
                            for dimension in CONTROL_DIMENSIONS
                        ]
                    )
                    legacy.confidence = belief.confidence
                    legacy.updated_at = belief.updated_at
                    legacy.last_reliable_observation_at = (
                        belief.last_reliable_observation_at
                    )
                    legacy.evidence_count = belief.evidence_count
                    legacy.contradiction_index = belief.contradiction_index
        return
    if state.stride == CONTROL_STATE_STRIDE:
        compact = CompactControlBeliefState(
            state.keys,
            array("d", (
                value for key in state.keys for value in state.row(0, key)
            )),
        )
        beliefs = getattr(world, belief_attribute)
        for key in state.keys:
            if key not in beliefs:
                beliefs[key] = ActorBelief(
                    key[0], key[2], ControlVector(*([0.5] * 7)),
                    world.config.information.prior_confidence, 0.0,
                )
            compact.write_to_belief(key, beliefs[key])
            # Keep the historical same-side movement signal synchronized.  It
            # is a read-only view of actor-resolved control evidence, not a
            # second estimator.
            # ``world.beliefs`` is the historical same-side projection, not a
            # second copy of every actor-resolved row.  The object fusion path
            # updates it only for insurgent-side reports received by an
            # insurgent observer or government-side reports received by a
            # non-insurgent observer.  Applying that predicate here prevents
            # a later default/insurgent row from overwriting the government
            # mirror for the same observer/locality.
            legacy = getattr(world, "beliefs", {}).get((key[0], key[2]))
            mirrors_legacy = (
                _is_insurgent_actor(world, key[1])
                and _is_insurgent_actor(world, key[0])
            ) or (
                key[1] == "government"
                and not _is_insurgent_actor(world, key[0])
            )
            if legacy is not None and mirrors_legacy:
                legacy.control_estimate = ControlVector(
                    *[getattr(beliefs[key].control_estimate, dimension)
                      for dimension in CONTROL_DIMENSIONS]
                )
                legacy.confidence = beliefs[key].confidence
                legacy.updated_at = beliefs[key].updated_at
                legacy.last_reliable_observation_at = (
                    beliefs[key].last_reliable_observation_at
                )
                legacy.evidence_count = beliefs[key].evidence_count
                legacy.contradiction_index = beliefs[key].contradiction_index
        setattr(world, compact_attribute, compact)
        return

    if state.stride == PRESENCE_STATE_STRIDE:
        compact = CompactPresenceBeliefState(
            state.keys,
            array("d", (
                value for key in state.keys for value in state.row(0, key)
            )),
        )
        beliefs = getattr(world, belief_attribute)
        for key in state.keys:
            if key not in beliefs:
                location = key[2].split(":", 1)
                locality_id = location[0]
                microzone_id = (
                    None if len(location) == 1 or location[1] == "*"
                    else location[1]
                )
                beliefs[key] = PresenceBelief(
                    key[0], key[1], locality_id,
                    target_id=None if key[3] == "*" else key[3],
                    microzone_id=microzone_id,
                    confidence=world.config.information.prior_confidence,
                )
            compact.write_to_belief(key, beliefs[key])
        compact.configure_decay(
            world.config.information.default_decay_rate,
            world.config.information.formation_decay_rate,
        )
        compact.set_decay_clock(world.last_information_decay_at)
        setattr(world, compact_attribute, compact)
        return

    compact = CompactZoneBeliefState(
        state.keys,
        array("d", (
            value for key in state.keys for value in state.row(0, key)
        )),
    )
    beliefs = getattr(world, belief_attribute)
    for key in state.keys:
        if key not in beliefs:
            beliefs[key] = ActorZoneBelief(
                key[0], key[1], 0.5,
                world.config.information.prior_confidence, 0.0,
            )
        compact.write_to_belief(key, beliefs[key])
    compact.configure_decay(world.config.information.formation_decay_rate)
    compact.set_decay_clock(world.last_information_decay_at)
    setattr(world, compact_attribute, compact)


def _numeric_relay_weight(
    world: Any,
    row: tuple[Any, ...],
    recipient_id: str,
    time: float,
) -> float:
    """Compute the object-free equivalent of ``fuse_observation`` weight."""
    from .information import (
        _corroboration_weight,
        _decay_rate,
        language_comprehension,
        source_trust,
    )

    codes = world.numeric_information_runtime.engine.plan.codes
    source_id = codes.value(row[3]) or ""
    source_type = codes.value(row[4]) or ""
    locality_id = codes.value(row[5])
    target_actor_id = codes.value(row[7]) or "*"
    if locality_id is None:
        return 0.0
    observation_type = "detection" if int(row[12]) == _DETECTION else "physical_control"
    history_key = (target_actor_id, locality_id, observation_type)
    history = world.observation_source_index.get(history_key, ())
    correlation = world.config.information.source_correlation.get(source_type, 0.5)
    corroboration = _corroboration_weight(
        history, float(row[9]), source_id, correlation
    )
    age_quality = exp(-_decay_rate(
        world, observation_type,
        codes.value(row[8]) if int(row[8]) else None,
    ) * max(0.0, float(time) - float(row[9])))
    # ``fuse_observation`` evaluates trust and language for the organization
    # represented by a formation endpoint, while retaining the endpoint ID as
    # the belief-state recipient key.  A numeric relay row must resolve that
    # same actor before calling the scalar helper; otherwise command-node
    # deliveries silently receive the unknown-recipient fallback (0.25
    # language / unadjusted trust) and diverge from the object path.
    recipient_actor = recipient_id
    if recipient_id not in world.organizations:
        formation = world.formations.get(recipient_id)
        if formation is not None:
            recipient_actor = formation.organization_id
        else:
            recipient_actor = codes.value(row[1]) or recipient_id
    trust = source_trust(
        world, recipient_actor, source_type, locality_id, source_id
    )
    language = language_comprehension(
        world, recipient_actor, locality_id, source_type, source_id
    )
    weight = (
        float(row[10]) * float(row[11]) * trust
        * (language ** world.config.information.language_fusion_weight)
        * age_quality
        * (1.0 + world.config.information.corroboration_bonus
           * min(3.0, corroboration))
    )
    return max(0.0, min(1.0, weight))


@dataclass(slots=True)
class NumericInformationRuntime:
    """Object-free information clock for a single packed world lane.

    The runtime keeps only fixed-width report rows and flattened relay rows.
    Legacy ``Observation`` and ``InformationRelay`` objects are created only
    if a caller explicitly synchronizes through the reference backend.
    """

    engine: NumericInformationEventEngine
    event_buffer: InformationEventBuffer
    relay_buffer: RelayBuffer
    event_rows: dict[int, tuple[Any, ...]]
    control_state: EnsembleBeliefState
    presence_state: EnsembleBeliefState
    node_presence_state: EnsembleBeliefState
    zone_state: EnsembleBeliefState
    last_time: float = 0.0

    @classmethod
    def from_world(cls, world: Any) -> "NumericInformationRuntime":
        engine = NumericInformationEventEngine.from_world(world)
        return cls(
            engine,
            InformationEventBuffer(codebook=engine.plan.codes),
            RelayBuffer(codebook=engine.plan.codes),
            {},
            _numeric_world_belief_state(
                world, compact_attribute="compact_control_state",
                belief_attribute="control_beliefs", stride=CONTROL_STATE_STRIDE,
            ),
            _numeric_world_belief_state(
                world, compact_attribute="compact_presence_state",
                belief_attribute="presence_beliefs", stride=PRESENCE_STATE_STRIDE,
            ),
            _numeric_world_belief_state(
                world, compact_attribute="compact_node_presence_state",
                belief_attribute="node_presence_beliefs", stride=PRESENCE_STATE_STRIDE,
            ),
            _numeric_world_belief_state(
                world, compact_attribute="compact_zone_state",
                belief_attribute="zone_beliefs", stride=ZONE_STATE_STRIDE,
            ),
            float(world.time),
        )

    def _refresh_belief_aliases(self, world: Any) -> None:
        """Rebind only when an external process replaced/extended compact rows."""
        specifications = (
            ("control_state", "compact_control_state", "control_beliefs", CONTROL_STATE_STRIDE),
            ("presence_state", "compact_presence_state", "presence_beliefs", PRESENCE_STATE_STRIDE),
            ("node_presence_state", "compact_node_presence_state", "node_presence_beliefs", PRESENCE_STATE_STRIDE),
            ("zone_state", "compact_zone_state", "zone_beliefs", ZONE_STATE_STRIDE),
        )
        for runtime_name, compact_name, belief_name, stride in specifications:
            current = getattr(self, runtime_name)
            compact = getattr(world, compact_name, None)
            beliefs = getattr(world, belief_name)
            keys = tuple(compact.keys) if compact is not None else tuple(sorted(beliefs))
            if (
                current.compact_backing is compact
                and current.state is getattr(compact, "state", None)
                and tuple(current.keys) == keys
                and set(keys) == set(beliefs)
            ):
                continue
            setattr(
                self,
                runtime_name,
                _numeric_world_belief_state(
                    world,
                    compact_attribute=compact_name,
                    belief_attribute=belief_name,
                    stride=stride,
                ),
            )

    def _refresh(self, world: Any) -> None:
        if not self.engine.plan.is_current_for(world):
            # Source opportunities can change when formations move, become
            # ineffective, or an insurgent organization activates. Relays
            # generated under the previous plan remain scientifically live;
            # retain their numeric buffers and extend the shared codebook for
            # the new plan instead of forcing a rich-object fallback.
            plan = InformationSourcePlan.from_world(
                world, codebook=self.engine.plan.codes
            )
            self.engine = NumericInformationEventEngine.from_world(
                world, plan=plan
            )
        else:
            self.engine = NumericInformationEventEngine.from_world(
                world, plan=self.engine.plan
            )
        self.engine.next_sequence = int(world.next_observation_sequence)
        self.engine.next_relay_sequence = int(world.next_information_relay_sequence)
        self._refresh_belief_aliases(world)

    def _record_rows(self, world: Any, *, append_history: bool = True) -> None:
        rows_by_sequence = {
            int(row[0]): row for row in self.event_buffer.iter_rows()
        }
        for index in range(len(self.relay_buffer)):
            sequence = int(self.relay_buffer.observation_sequence[index])
            row = rows_by_sequence.get(sequence)
            if row is not None:
                self.event_rows[sequence] = row
        if not append_history:
            return
        # The bounded source-history index is the only information memory
        # needed for corroboration; it stores codes/strings, never reports.
        for row in rows_by_sequence.values():
            actor = self.engine.plan.codes.value(row[7]) or "*"
            locality = self.engine.plan.codes.value(row[5])
            source = self.engine.plan.codes.value(row[3]) or ""
            if locality is None:
                continue
            kind = "detection" if int(row[12]) == _DETECTION else "physical_control"
            key = (actor, locality, kind)
            history = world.observation_source_index.setdefault(key, deque())
            entry = (float(row[9]), source)
            # Preserve one source-history record for each report.  Distinct
            # channel rows can share an identity and timestamp; the
            # corroboration helper de-duplicates identities only while
            # evaluating evidence.
            history.append(entry)
            cutoff = float(row[9]) - 3.0
            while history and history[0][0] < cutoff:
                history.popleft()

    def _patrol_plan(self, world: Any, patrol_id: str) -> InformationSourcePlan:
        """Compile the one-source plan used by a patrol report clock."""
        from .information import (
            _formation_matches_target_actor,
            _target_actors_for_observer,
        )

        patrol = world.patrols[patrol_id]
        formation = world.formations[patrol.formation_id]
        codes = self.engine.plan.codes
        observer_id = formation.organization_id
        locality_id = formation.locality_id
        observer = array("I", [codes.code(observer_id)])
        node = array("I", [codes.code(formation.formation_id)])
        source = array("I", [codes.code(patrol_id)])
        source_type = array("I", [codes.code("patrol")])
        locality = array("I", [codes.code(locality_id)])
        target_offsets = array("Q", [0])
        target_actor = array("I")
        target_formation = array("I")
        for actor in _target_actors_for_observer(world, observer_id):
            targets = [
                item for item in world.formations.values()
                if _formation_matches_target_actor(world, item, actor)
                and item.personnel > 0
                and item.locality_id == locality_id
                and not item.moving
            ]
            if targets:
                for target in targets:
                    target_actor.append(codes.code(actor))
                    target_formation.append(codes.code(target.formation_id))
            else:
                target_actor.append(codes.code(actor))
                target_formation.append(0)
        # ``InformationSourcePlan.target_offsets`` is CSR-style: one interval
        # per *source*, not one interval per target actor.  A patrol plan has
        # exactly one source, so even a no-target patrol must terminate that
        # source with a second offset.  The previous implementation appended
        # inside the actor loop, which produced an empty offsets interval when
        # no opposing actor existed and multiple intervals when several actors
        # existed.  Both cases are incompatible with ``from_world``'s
        # source-indexed traversal.
        target_offsets.append(len(target_actor))
        current_zone = codes.code(patrol.current_microzone_id)
        return InformationSourcePlan(
            codes,
            observer,
            node,
            source,
            source_type,
            locality,
            target_offsets,
            target_actor,
            (locality_id,),
            ((),),
            ((),),
            ((),),
            ((),),
            (0,),
            ("patrol", patrol_id, formation.formation_id, locality_id),
            target_formation=target_formation,
            source_microzone=array("I", [current_zone]),
            source_zone_actor=array("I", [codes.code(observer_id)]),
            native_initial_sources=array("I", [0]),
            native_member_sources=array("I"),
            native_locality_group_offsets=array("Q", [0, 0]),
            native_group_source_offsets=array("Q", [0]),
            native_group_sources=array("I"),
            native_locality_cumulative_offsets=array("Q", [0, 0]),
            native_cumulative_weights=array("d"),
            native_locality_fallback_offsets=array("Q", [0, 0]),
            native_fallback_sources=array("I"),
        )

    def process_patrol(self, world: Any, patrol_id: str, time: float, rng: Any) -> dict[str, Any]:
        """Generate patrol detections/control rows without rich observations."""
        world.numeric_information_runtime = self
        self._refresh_belief_aliases(world)
        plan = self._patrol_plan(world, patrol_id)
        world.information_execution_cache.clear()
        world.information_cache_active = True
        try:
            patrol_engine = NumericInformationEventEngine.from_world(world, plan=plan)
            patrol_engine.report_probability[0] = float(
                world.config.information.patrol_report_rate
            )
            patrol_engine.next_sequence = int(world.next_observation_sequence)
            patrol_engine.next_relay_sequence = int(world.next_information_relay_sequence)
            self.event_buffer.clear()
            result = patrol_engine.process(
                rng,
                float(time),
                event_buffer=self.event_buffer,
                control_state=self.control_state,
                presence_state=self.presence_state,
                node_presence_state=self.node_presence_state,
                zone_state=self.zone_state,
                relay_buffer=self.relay_buffer,
                record_negative=True,
                world=world,
            )
            self._record_rows(world, append_history=False)
        finally:
            world.information_execution_cache.clear()
            world.information_cache_active = False
        self.relay_buffer.retain_active()
        for state, compact_name, belief_name in (
            (self.control_state, "compact_control_state", "control_beliefs"),
            (self.presence_state, "compact_presence_state", "presence_beliefs"),
            (self.node_presence_state, "compact_node_presence_state", "node_presence_beliefs"),
            (self.zone_state, "compact_zone_state", "zone_beliefs"),
        ):
            dirty = state.consume_dirty(0)
            if dirty:
                _sync_numeric_world_state(
                    world, state,
                    compact_attribute=compact_name,
                    belief_attribute=belief_name,
                    keys=dirty,
                )
        world.next_observation_sequence = int(patrol_engine.next_sequence)
        world.next_information_relay_sequence = int(patrol_engine.next_relay_sequence)
        return {
            "generated": int(result["event_rows"]),
            "observation_ids": tuple(int(item) for item in self.event_buffer.ids),
            "relays_delivered": 0,
            "relays_dropped": 0,
            "active_relays": sum(
                int(status == 0) for status in self.relay_buffer.status
            ),
            "numeric": True,
            "event_buffer": self.event_buffer,
            "relay_buffer": self.relay_buffer,
        }

    def _apply_row(
        self,
        world: Any,
        row: tuple[Any, ...],
        recipient_id: str,
        *,
        node: bool,
        time: float,
    ) -> None:
        codes = self.engine.plan.codes
        actor = codes.value(row[7])
        locality = codes.value(row[5])
        microzone = codes.value(row[6])
        if actor is None or locality is None:
            return
        weight = _numeric_relay_weight(world, row, recipient_id, time)
        if int(row[12]) == _DETECTION:
            target_id = codes.value(row[8])
            state = self.node_presence_state if node else self.presence_state
            keys = (target_id, None) if target_id is not None else (None,)
            for target in keys:
                key = (
                    recipient_id, actor, f"{locality}:{microzone or '*'}",
                    target or "*",
                )
                state.ensure_key(
                    key,
                    prior_confidence=world.config.information.prior_confidence,
                )
                # Presence rows use the same recurrence for positive and
                # negative detection claims.
                if node:
                    updates = [(0, key, time, weight, float(row[14]), float(row[15]))]
                    self.node_presence_state.fuse_presence(
                        updates,
                        contradiction_memory_days=world.config.information.contradiction_memory_days,
                        contradiction_penalty=world.config.information.contradiction_penalty,
                    )
                else:
                    updates = [(0, key, time, weight, float(row[14]), float(row[15]))]
                    self.presence_state.fuse_presence(
                        updates,
                        contradiction_memory_days=world.config.information.contradiction_memory_days,
                        contradiction_penalty=world.config.information.contradiction_penalty,
                    )
            return
        key = (recipient_id, actor, locality)
        self.control_state.ensure_key(
            key, prior_confidence=world.config.information.prior_confidence
        )
        self.control_state.fuse_control(
            [(0, key, time, weight, row[13])],
            contradiction_memory_days=world.config.information.contradiction_memory_days,
            contradiction_penalty=world.config.information.contradiction_penalty,
        )
        if microzone is not None:
            zone_key = (recipient_id, microzone)
            if zone_key in self.zone_state.key_to_index:
                self.zone_state.fuse_zone(
                    [(0, zone_key, time, weight, float(row[19]))],
                    contradiction_memory_days=world.config.information.contradiction_memory_days,
                    contradiction_penalty=world.config.information.contradiction_penalty,
                )

    def _deliver(self, world: Any, time: float, rng: Any) -> tuple[int, int, tuple[int, ...]]:
        delivered = 0
        dropped = 0
        delivered_sequences: list[int] = []
        for index in range(len(self.relay_buffer)):
            if int(self.relay_buffer.status[index]) != 0:
                continue
            if float(self.relay_buffer.arrives_at[index]) > float(time) + 1e-12:
                continue
            sequence = int(self.relay_buffer.observation_sequence[index])
            row = self.event_rows.get(sequence)
            reliability = float(self.relay_buffer.reliability[index])
            if row is None or not (rng.random() <= reliability):
                self.relay_buffer.status[index] = 2
                dropped += 1
                self.event_rows.pop(sequence, None)
                continue
            organization = self.engine.plan.codes.value(
                self.relay_buffer.organization[index]
            )
            if organization is not None:
                self._apply_row(world, row, organization, node=False, time=time)
            destination = self.engine.plan.codes.value(
                self.relay_buffer.destination[index]
            )
            if destination is not None:
                # The command endpoint is a field-node namespace in the
                # reference delivery contract, so it receives a second
                # (node=True) fusion rather than a second actor-level fusion.
                self._apply_row(world, row, destination, node=True, time=time)
            source_actor = self.engine.plan.codes.value(row[1])
            source_org = world.organizations.get(source_actor) if source_actor else None
            if (
                source_org is not None
                and source_org.kind is not OrganizationKind.INSURGENT
                and "government" in world.organizations
            ):
                # Government headquarters also receives subordinate
                # non-insurgent reports, exactly as ``process_information``.
                self._apply_row(world, row, "government", node=False, time=time)
            self.relay_buffer.status[index] = 1
            self.relay_buffer.delivered_at[index] = float(time)
            delivered += 1
            delivered_sequences.append(sequence)
            self.event_rows.pop(sequence, None)
        return delivered, dropped, tuple(delivered_sequences)

    def process(self, world: Any, time: float, rng: Any) -> dict[str, Any]:
        from .information import decay_information

        decay_information(world, float(time))
        world.numeric_information_runtime = self
        world.information_execution_cache.clear()
        world.information_cache_active = True
        try:
            self._refresh(world)
            self.event_buffer.clear()
            result = self.engine.process(
                rng,
                float(time),
                event_buffer=self.event_buffer,
                control_state=self.control_state,
                presence_state=self.presence_state,
                node_presence_state=self.node_presence_state,
                zone_state=self.zone_state,
                relay_buffer=self.relay_buffer,
                record_negative=True,
                world=world,
            )
            self._record_rows(world, append_history=False)
            delivered, dropped, delivered_sequences = self._deliver(
                world, time, rng
            )
        finally:
            world.information_execution_cache.clear()
            world.information_cache_active = False
        self.relay_buffer.retain_active()
        for state, compact_name, belief_name in (
            (self.control_state, "compact_control_state", "control_beliefs"),
            (self.presence_state, "compact_presence_state", "presence_beliefs"),
            (self.node_presence_state, "compact_node_presence_state", "node_presence_beliefs"),
            (self.zone_state, "compact_zone_state", "zone_beliefs"),
        ):
            dirty = state.consume_dirty(0)
            if dirty:
                _sync_numeric_world_state(
                    world, state,
                    compact_attribute=compact_name,
                    belief_attribute=belief_name,
                    keys=dirty,
                )
        world.next_observation_sequence = int(self.engine.next_sequence)
        world.next_information_relay_sequence = int(self.engine.next_relay_sequence)
        world.last_information_decay_at = float(time)
        self.last_time = float(time)
        active = tuple(
            int(self.relay_buffer.observation_sequence[index])
            for index in range(len(self.relay_buffer))
            if int(self.relay_buffer.status[index]) == 0
        )
        return {
            "generated": int(result["event_rows"]),
            "observation_ids": tuple(int(item) for item in self.event_buffer.ids),
            "relays_delivered": delivered,
            "delivered_observation_ids": delivered_sequences,
            "relays_dropped": dropped,
            "active_relays": len(active),
            "control_fusions": 0,
            "presence_fusions": 0,
            "numeric": True,
            "event_buffer": self.event_buffer,
            "relay_buffer": self.relay_buffer,
        }


def process_information_numeric(
    world: Any,
    time: float,
    rng: Any,
    *,
    runtime: NumericInformationRuntime | None = None,
) -> dict[str, Any]:
    """Run one numeric information event and retain only in-flight rows."""
    if runtime is None:
        runtime = getattr(world, "numeric_information_runtime", None)
    if runtime is None:
        runtime = NumericInformationRuntime.from_world(world)
        world.numeric_information_runtime = runtime
    return runtime.process(world, time, rng)


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
        from .compact_information_state import (
            CompactControlBeliefState,
            CompactPresenceBeliefState,
            CompactZoneBeliefState,
        )
        rows = []
        for world in worlds:
            compact = getattr(world, "compact_control_state", None)
            rows.append([
                tuple(compact.row(key)) if compact is not None and key in compact.key_to_index
                else CompactControlBeliefState._belief_row(world.control_beliefs[key]) if key in world.control_beliefs
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
                row_factory = (
                    CompactPresenceBeliefState._belief_row
                    if stride == PRESENCE_STATE_STRIDE
                    else CompactZoneBeliefState._belief_row
                )
                result.append([
                    tuple(compact.row(key)) if compact is not None and key in compact.key_to_index
                    else row_factory(fallback[key]) if key in fallback
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
        # A resampled ensemble has equal posterior mass. Keeping the selected
        # parents' old log weights would double-count the previous likelihood
        # at the next update.
        self.weights = array("d", [0.0] * len(parents))
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
            compact = CompactControlBeliefState(
                self.control_state.keys,
                array("d", (
                    value
                    for key in self.control_state.keys
                    for value in self.control_state.row(particle_index, key)
                )),
            )
            for key in self.control_state.keys:
                if key not in world.control_beliefs:
                    world.control_beliefs[key] = ActorBelief(
                        key[0], key[2], ControlVector(*([0.5] * 7)),
                        world.config.information.prior_confidence, 0.0,
                    )
            world.compact_control_state = compact
            for key in self.control_state.keys:
                compact.write_to_belief(key, world.control_beliefs[key])

            def sync_presence(state: EnsembleBeliefState, attribute: str, cls_type: Any, node: bool = False):
                compact = CompactPresenceBeliefState(
                    state.keys,
                    array("d", (
                        value
                        for key in state.keys
                        for value in state.row(particle_index, key)
                    )),
                )
                target = getattr(world, attribute)
                for key in state.keys:
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
            compact_zone = CompactZoneBeliefState(
                self.zone_state.keys,
                array("d", (
                    value
                    for key in self.zone_state.keys
                    for value in self.zone_state.row(particle_index, key)
                )),
            )
            for key in self.zone_state.keys:
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


@dataclass(frozen=True, slots=True)
class PackedFilterUpdate:
    """Compact diagnostics for one packed SMC boundary."""

    time: float
    prior_ess: float
    posterior_ess: float
    maximum_posterior_weight: float
    resampled: bool
    unique_parent_particles: int
    parent_indices: tuple[int, ...]
    resampling_events: int


@dataclass(slots=True)
class PackedParticleFilter:
    """Sequential Monte Carlo over one leading particle dimension.

    The transition callback owns model propagation and receives the packed
    :class:`ParticleBatchState`. A likelihood callback receives
    ``(batch, particle_index, observation)`` and returns a log likelihood.
    Optional transition/proposal log densities are added as the standard
    guided-SMC importance correction ``log p + log L - log q``.
    """

    batch: ParticleBatchState
    rng: Any
    ess_fraction: float = 0.5
    strict_support: bool = True
    resampling_events: int = 0
    history: list[PackedFilterUpdate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 < float(self.ess_fraction) <= 1.0:
            raise ValueError("ess_fraction must be in (0, 1]")

    @classmethod
    def from_particles(
        cls,
        particles: Sequence[Any],
        *,
        rng: Any,
        ess_fraction: float = 0.5,
        topology: StaticWorldTopology | None = None,
    ) -> "PackedParticleFilter":
        return cls(
            ParticleBatchState.from_particles(particles, topology=topology),
            rng,
            ess_fraction=ess_fraction,
        )

    @property
    def particle_count(self) -> int:
        return self.batch.particle_count

    def normalized_weights(self) -> tuple[float, ...]:
        from .state_estimation import normalize_log_weights

        return tuple(normalize_log_weights(
            self.batch.weights, strict=self.strict_support
        ))

    @staticmethod
    def _per_particle(
        value: Sequence[float] | float | Callable[[int], float] | None,
        count: int,
        *,
        name: str,
    ) -> list[float]:
        if value is None:
            return [0.0] * count
        if callable(value):
            return [float(value(index)) for index in range(count)]
        if isinstance(value, (int, float)):
            return [float(value)] * count
        if len(value) != count:
            raise ValueError(f"{name} must contain one value per particle")
        return [float(item) for item in value]

    def update(
        self,
        until: float,
        observation: Any = None,
        *,
        runner: Callable[[ParticleBatchState, float], Any] | None = None,
        log_likelihood: Callable[[ParticleBatchState, int, Any], float]
        | Sequence[float] | None = None,
        log_transition_density: Sequence[float] | float | Callable[[int], float]
        | None = None,
        log_proposal_density: Sequence[float] | float | Callable[[int], float]
        | None = None,
    ) -> PackedFilterUpdate:
        """Propagate, score, and ESS-resample one packed boundary."""
        from .state_estimation import (
            effective_sample_size,
            normalize_log_weights,
            systematic_resample_indices,
        )

        if runner is not None:
            self.batch.advance_to(float(until), runner=runner)
        else:
            if float(until) < min(self.batch.times):
                raise ValueError("packed filter boundary cannot move backward")
            self.batch.advance_to(float(until))
        count = self.particle_count
        prior = list(normalize_log_weights(
            self.batch.weights, strict=self.strict_support
        ))
        if log_likelihood is None:
            likelihoods = [0.0] * count
        elif callable(log_likelihood):
            likelihoods = [
                float(log_likelihood(self.batch, index, observation))
                for index in range(count)
            ]
        else:
            if len(log_likelihood) != count:
                raise ValueError("log_likelihood must contain one value per particle")
            likelihoods = [float(item) for item in log_likelihood]
        transitions = self._per_particle(
            log_transition_density, count, name="log_transition_density"
        )
        proposals = self._per_particle(
            log_proposal_density, count, name="log_proposal_density"
        )
        raw_weights = []
        for prior_weight, transition, likelihood, proposal in zip(
            prior, transitions, likelihoods, proposals
        ):
            raw_weights.append(
                log(prior_weight) + transition + likelihood - proposal
                if prior_weight > 0.0 and all(isfinite(item) for item in (
                    transition, likelihood, proposal
                )) else -inf
            )
        posterior = normalize_log_weights(
            raw_weights, strict=self.strict_support
        )
        self.batch.weights = array(
            "d", (log(weight) if weight > 0.0 else -inf for weight in posterior)
        )
        prior_ess = effective_sample_size(prior)
        posterior_ess = effective_sample_size(posterior)
        threshold = float(self.ess_fraction) * count
        resampled = posterior_ess < threshold
        parents = tuple(range(count))
        unique = count
        if resampled:
            parents = tuple(systematic_resample_indices(posterior, self.rng))
            unique = len(set(parents))
            self.batch.gather(parents)
            self.resampling_events += 1
        result = PackedFilterUpdate(
            float(until), prior_ess, posterior_ess, max(posterior),
            resampled, unique, parents, self.resampling_events,
        )
        self.history.append(result)
        return result


# Naming aliases for callers that use either the execution or filtering term.
EnsembleParticleFilter = PackedParticleFilter


# Explicit aliases used by callers that prefer the handoff terminology.
NumericInformationEventBuffer = InformationEventBuffer
NumericRelayBuffer = RelayBuffer
EnsembleState = ParticleBatchState


__all__ = [
    "EnsembleBeliefState", "EnsembleParticleFilter", "EnsembleState",
    "InformationEventBuffer",
    "InformationSourcePlan", "NumericIdTable", "NumericInformationEventBuffer",
    "NumericInformationEventEngine", "NumericInformationRuntime",
    "NumericRelayBuffer", "PackedFilterUpdate", "PackedParticleFilter",
    "ParticleBatchState", "RelayBuffer",
    "StaticWorldTopology", "advance_batch", "process_information_numeric",
]
