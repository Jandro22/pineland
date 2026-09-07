"""Compact particle-mode observation and relay records.

The reference information pipeline uses rich dataclasses because they are the
best scientific and forensic interface.  Particle propagation has a different
constraint: most reports live only until their relay is delivered.  This
module stores the common report/relay payloads in append-only numeric columns
and exposes small compatibility views only at access boundaries.

The store deliberately does not implement any model equation.  It is a
representation layer, so a view's payload is byte-for-byte equivalent to the
corresponding reference dataclass payload.
"""
from __future__ import annotations

from array import array
from collections.abc import Iterator, MutableMapping
from typing import Any

from .entities import CONTROL_DIMENSIONS, InformationRelay, Observation


_NONE = -1
_DETECTION = 1
_CONTROL = 2
_RELAY_IN_TRANSIT = 0
_RELAY_DELIVERED = 1
_RELAY_DROPPED = 2


class _StringTable:
    __slots__ = ("values", "indices")

    def __init__(self) -> None:
        self.values: list[str | None] = [None]
        self.indices: dict[str, int] = {}

    def code(self, value: str | None) -> int:
        if value is None:
            return _NONE
        index = self.indices.get(value)
        if index is not None:
            return index
        index = len(self.values)
        self.values.append(value)
        self.indices[value] = index
        return index

    def value(self, code: int) -> str | None:
        return self.values[code]

    def clone(self) -> "_StringTable":
        result = type(self)()
        result.values = list(self.values)
        result.indices = dict(self.indices)
        return result


class CompactObservationView:
    """Mutable compatibility view over one compact observation row."""

    __slots__ = ("_store", "_index", "_estimated_cache")

    def __init__(self, store: "CompactObservationStore", index: int) -> None:
        self._store = store
        self._index = index
        self._estimated_cache: dict[str, Any] | None = None

    @property
    def observation_id(self) -> str:
        return self._store.ids[self._index]

    @property
    def target_id(self) -> str | None:
        return self._store._string(self._store.target_codes[self._index])

    @property
    def locality_id(self) -> str:
        return self._store._string(self._store.locality_codes[self._index])  # type: ignore[return-value]

    @property
    def timestamp(self) -> float:
        return self._store.timestamps[self._index]

    @property
    def source_id(self) -> str:
        return self._store._string(self._store.source_codes[self._index])  # type: ignore[return-value]

    @property
    def source_type(self) -> str:
        return self._store._string(self._store.source_type_codes[self._index])  # type: ignore[return-value]

    @property
    def observation_type(self) -> str:
        return self._store._string(self._store.observation_type_codes[self._index])  # type: ignore[return-value]

    @property
    def estimated_value(self) -> dict[str, Any]:
        if self._estimated_cache is None:
            self._estimated_cache = self._store._estimated_value(self._index)
        return self._estimated_cache

    @property
    def confidence(self) -> float:
        return self._store.confidences[self._index]

    @property
    def provenance(self) -> dict[str, Any]:
        return self._store.provenance[self._index]

    @property
    def observer_actor_id(self) -> str:
        return self._store._string(self._store.observer_actor_codes[self._index])  # type: ignore[return-value]

    @property
    def microzone_id(self) -> str | None:
        return self._store._string(self._store.microzone_codes[self._index])

    @property
    def observer_node_id(self) -> str | None:
        return self._store._string(self._store.observer_node_codes[self._index])

    @property
    def quality(self) -> float:
        return self._store.qualities[self._index]

    @property
    def decay_rate(self) -> float:
        return self._store.decay_rates[self._index]

    @property
    def target_actor_id(self) -> str | None:
        return self._store._string(self._store.target_actor_codes[self._index])

    @property
    def target_formation_id(self) -> str | None:
        return self._store._string(self._store.target_formation_codes[self._index])

    @property
    def received_at(self) -> float | None:
        value = self._store.received_at[self._index]
        return None if value < 0.0 else value

    @received_at.setter
    def received_at(self, value: float | None) -> None:
        self._store.received_at[self._index] = -1.0 if value is None else float(value)

    def to_payload(self) -> dict[str, Any]:
        """Return the same field-ordered mapping produced by ``asdict``."""
        return {
            "observation_id": self.observation_id,
            "target_id": self.target_id,
            "locality_id": self.locality_id,
            "timestamp": self.timestamp,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "observation_type": self.observation_type,
            "estimated_value": self.estimated_value,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "observer_actor_id": self.observer_actor_id,
            "microzone_id": self.microzone_id,
            "observer_node_id": self.observer_node_id,
            "quality": self.quality,
            "decay_rate": self.decay_rate,
            "target_actor_id": self.target_actor_id,
            "target_formation_id": self.target_formation_id,
            "received_at": self.received_at,
        }

    def effective_confidence(self, time: float) -> float:
        from .entities import clamp
        from math import exp

        elapsed = max(0.0, time - self.timestamp)
        return clamp(self.confidence * self.quality * exp(-max(0.0, self.decay_rate) * elapsed))

    confidence_at = effective_confidence

    def age(self, time: float) -> float:
        return max(0.0, time - self.timestamp)

    @property
    def source(self) -> str:
        return self.source_id

    @property
    def target(self) -> str | None:
        return self.target_id

    @property
    def subject(self) -> str | None:
        return self.target_id

    @property
    def location(self) -> str:
        return self.microzone_id or self.locality_id

    @property
    def estimated_state(self) -> dict[str, Any]:
        return self.estimated_value

    @property
    def value(self) -> dict[str, Any]:
        return self.estimated_value

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CompactObservationView):
            return self.to_payload() == other.to_payload()
        if isinstance(other, Observation):
            from dataclasses import asdict
            return self.to_payload() == asdict(other)
        return NotImplemented


class CompactObservationStore(MutableMapping[str, CompactObservationView]):
    """SoA storage for the common particle observation payloads."""

    __slots__ = (
        "ids", "id_to_index", "strings", "target_codes", "locality_codes",
        "source_codes", "source_type_codes", "observation_type_codes",
        "observer_actor_codes", "microzone_codes", "observer_node_codes",
        "target_actor_codes", "target_formation_codes", "timestamps",
        "confidences", "qualities", "decay_rates", "received_at", "kinds",
        "presence", "personnel", "detection_probability", "detected",
        "attribution_confidence", "control", "physical_control", "violence",
        "provenance", "opaque_values", "estimated_value_cache",
    )

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.id_to_index: dict[str, int] = {}
        self.strings = _StringTable()
        self.target_codes = array("i")
        self.locality_codes = array("i")
        self.source_codes = array("i")
        self.source_type_codes = array("i")
        self.observation_type_codes = array("i")
        self.observer_actor_codes = array("i")
        self.microzone_codes = array("i")
        self.observer_node_codes = array("i")
        self.target_actor_codes = array("i")
        self.target_formation_codes = array("i")
        self.timestamps = array("d")
        self.confidences = array("d")
        self.qualities = array("d")
        self.decay_rates = array("d")
        self.received_at = array("d")
        self.kinds = array("B")
        self.presence = array("d")
        self.personnel = array("d")
        self.detection_probability = array("d")
        self.detected = array("B")
        self.attribution_confidence = array("d")
        self.control = array("d")
        self.physical_control = array("d")
        self.violence = array("d")
        self.provenance: list[dict[str, Any]] = []
        self.opaque_values: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
        # Compatibility payloads are lazy and shared by clones. Numeric
        # columns remain authoritative; this cache preserves the old view
        # identity contract without rebuilding dictionaries on every access.
        self.estimated_value_cache: list[dict[str, Any] | None] = []

    def __len__(self) -> int:
        return len(self.ids)

    def __iter__(self) -> Iterator[str]:
        return iter(self.ids)

    def __getitem__(self, key: str) -> CompactObservationView:
        return CompactObservationView(self, self.id_to_index[key])

    def __setitem__(self, key: str, value: CompactObservationView | Observation) -> None:
        if isinstance(value, CompactObservationView):
            value = Observation(**value.to_payload())
        if not isinstance(value, Observation):
            raise TypeError("compact observations accept Observation values")
        if key != value.observation_id:
            raise KeyError("observation key does not match observation_id")
        index = self.id_to_index.get(key)
        if index is not None:
            self._remove_index(index)
        self.add(value)

    def __delitem__(self, key: str) -> None:
        index = self.id_to_index[key]
        self._remove_index(index)

    def values(self):
        for index in range(len(self.ids)):
            yield CompactObservationView(self, index)

    def items(self):
        for index, key in enumerate(self.ids):
            yield key, CompactObservationView(self, index)

    def get(self, key: str, default: Any = None):
        index = self.id_to_index.get(key)
        return default if index is None else CompactObservationView(self, index)

    def add(self, observation: Observation) -> CompactObservationView:
        index = len(self.ids)
        self.ids.append(observation.observation_id)
        self.id_to_index[observation.observation_id] = index
        self.target_codes.append(self.strings.code(observation.target_id))
        self.locality_codes.append(self.strings.code(observation.locality_id))
        self.source_codes.append(self.strings.code(observation.source_id))
        self.source_type_codes.append(self.strings.code(observation.source_type))
        self.observation_type_codes.append(self.strings.code(observation.observation_type))
        self.observer_actor_codes.append(self.strings.code(observation.observer_actor_id))
        self.microzone_codes.append(self.strings.code(observation.microzone_id))
        self.observer_node_codes.append(self.strings.code(observation.observer_node_id))
        self.target_actor_codes.append(self.strings.code(observation.target_actor_id))
        self.target_formation_codes.append(self.strings.code(observation.target_formation_id))
        self.timestamps.append(float(observation.timestamp))
        self.confidences.append(float(observation.confidence))
        self.qualities.append(float(observation.quality))
        self.decay_rates.append(float(observation.decay_rate))
        self.received_at.append(-1.0 if observation.received_at is None else float(observation.received_at))
        kind = self._payload_kind(observation.estimated_value)
        self.kinds.append(kind)
        if kind == _DETECTION:
            value = observation.estimated_value
            self.presence.append(float(value.get("presence", 0.0)))
            self.personnel.append(float(value.get("personnel", 0.0)))
            self.detection_probability.append(float(value.get("detection_probability", 0.0)))
            self.detected.append(1 if bool(value.get("detected", False)) else 0)
            self.attribution_confidence.append(float(value.get("attribution_confidence", 0.0)))
        else:
            self.presence.append(0.0)
            self.personnel.append(0.0)
            self.detection_probability.append(0.0)
            self.detected.append(0)
            self.attribution_confidence.append(0.0)
        if kind == _CONTROL:
            values = observation.estimated_value["control"]
            self.control.extend(float(values[dimension]) for dimension in CONTROL_DIMENSIONS)
            self.physical_control.append(float(observation.estimated_value["physical_control"]))
            self.violence.append(float(observation.estimated_value["violence"]))
        else:
            self.control.extend((0.0,) * len(CONTROL_DIMENSIONS))
            self.physical_control.append(0.0)
            self.violence.append(0.0)
        self.provenance.append(observation.provenance)
        self.estimated_value_cache.append(None)
        if kind == 0:
            self.opaque_values[index] = (
                observation.estimated_value, observation.provenance
            )
        return CompactObservationView(self, index)

    @staticmethod
    def _payload_kind(value: dict[str, Any]) -> int:
        if set(value) == {
            "presence", "personnel", "detection_probability", "detected",
            "attribution_confidence",
        }:
            return _DETECTION
        if set(value) == {"control", "physical_control", "violence"}:
            control = value.get("control")
            if isinstance(control, dict) and tuple(control) == CONTROL_DIMENSIONS:
                return _CONTROL
        return 0

    def _string(self, code: int) -> str | None:
        return None if code == _NONE else self.strings.value(code)

    def _estimated_value(self, index: int) -> dict[str, Any]:
        cached = self.estimated_value_cache[index]
        if cached is not None:
            return cached
        kind = self.kinds[index]
        if kind == _DETECTION:
            value = {
                "presence": self.presence[index],
                "personnel": self.personnel[index],
                "detection_probability": self.detection_probability[index],
                "detected": bool(self.detected[index]),
                "attribution_confidence": self.attribution_confidence[index],
            }
        elif kind == _CONTROL:
            offset = index * len(CONTROL_DIMENSIONS)
            value = {
                "control": {
                    dimension: self.control[offset + position]
                    for position, dimension in enumerate(CONTROL_DIMENSIONS)
                },
                "physical_control": self.physical_control[index],
                "violence": self.violence[index],
            }
        else:
            value = self.opaque_values[index][0]
        self.estimated_value_cache[index] = value
        return value

    def retain(self, keep: set[str]) -> None:
        """Compact rows in place, preserving insertion order of retained IDs."""
        old_opaque = self.opaque_values
        kept_sources = [
            index for index, observation_id in enumerate(self.ids)
            if observation_id in keep
        ]
        write = 0
        original = len(self.ids)
        for read in range(original):
            if self.ids[read] not in keep:
                continue
            if write != read:
                self._copy_row(read, write)
            write += 1
        while len(self.ids) > write:
            self._pop_last()
        self.id_to_index = {key: index for index, key in enumerate(self.ids)}
        self.opaque_values = {
            destination: old_opaque[source]
            for destination, source in enumerate(kept_sources)
            if source in old_opaque
        }

    def _copy_row(self, source: int, destination: int) -> None:
        self.ids[destination] = self.ids[source]
        for column in (
            self.target_codes, self.locality_codes, self.source_codes,
            self.source_type_codes, self.observation_type_codes,
            self.observer_actor_codes, self.microzone_codes,
            self.observer_node_codes, self.target_actor_codes,
            self.target_formation_codes, self.timestamps, self.confidences,
            self.qualities, self.decay_rates, self.received_at, self.kinds,
            self.presence, self.personnel, self.detection_probability,
            self.detected, self.attribution_confidence, self.physical_control,
            self.violence,
        ):
            column[destination] = column[source]
        source_offset = source * len(CONTROL_DIMENSIONS)
        destination_offset = destination * len(CONTROL_DIMENSIONS)
        for position in range(len(CONTROL_DIMENSIONS)):
            self.control[destination_offset + position] = self.control[source_offset + position]
        self.provenance[destination] = self.provenance[source]
        self.estimated_value_cache[destination] = self.estimated_value_cache[source]
        if source in self.opaque_values:
            self.opaque_values[destination] = self.opaque_values[source]
        else:
            self.opaque_values.pop(destination, None)

    def _pop_last(self) -> None:
        index = len(self.ids) - 1
        key = self.ids.pop()
        self.id_to_index.pop(key, None)
        for column in (
            self.target_codes, self.locality_codes, self.source_codes,
            self.source_type_codes, self.observation_type_codes,
            self.observer_actor_codes, self.microzone_codes,
            self.observer_node_codes, self.target_actor_codes,
            self.target_formation_codes, self.timestamps, self.confidences,
            self.qualities, self.decay_rates, self.received_at, self.kinds,
            self.presence, self.personnel, self.detection_probability,
            self.detected, self.attribution_confidence, self.physical_control,
            self.violence,
        ):
            column.pop()
        del self.control[-len(CONTROL_DIMENSIONS):]
        self.provenance.pop()
        self.estimated_value_cache.pop()
        self.opaque_values.pop(index, None)

    def _remove_index(self, index: int) -> None:
        last = len(self.ids) - 1
        if index != last:
            self._copy_row(last, index)
        self._pop_last()
        self.id_to_index = {key: position for position, key in enumerate(self.ids)}

    def clear(self) -> None:
        self.__init__()

    def clone(self) -> "CompactObservationStore":
        result = type(self)()
        for name in self.__slots__:
            value = getattr(self, name)
            if name == "strings":
                value = value.clone()
            elif name == "id_to_index":
                value = dict(value)
            elif name in {"ids", "provenance"}:
                value = list(value)
            elif name == "estimated_value_cache":
                # This is a read-only compatibility cache and can be shared
                # safely by sibling particle stores.
                value = value
            elif name == "opaque_values":
                value = dict(value)
            elif isinstance(value, array):
                value = array(value.typecode, value)
            setattr(result, name, value)
        return result


class CompactRelayView:
    """Mutable compatibility view over one compact relay row."""

    __slots__ = ("_store", "_index")

    def __init__(self, store: "CompactRelayStore", index: int) -> None:
        self._store = store
        self._index = index

    @property
    def relay_id(self) -> str:
        return self._store.ids[self._index]

    @property
    def observation_id(self) -> str:
        return self._store.observation_ids[self._index]

    @property
    def organization_id(self) -> str:
        return self._store._string(self._store.organization_codes[self._index])  # type: ignore[return-value]

    @property
    def source_node_id(self) -> str:
        return self._store._string(self._store.source_codes[self._index])  # type: ignore[return-value]

    @property
    def destination_node_id(self) -> str:
        return self._store._string(self._store.destination_codes[self._index])  # type: ignore[return-value]

    @property
    def route(self) -> list[str]:
        return list(self._store.routes[self._index])

    @property
    def sent_at(self) -> float:
        return self._store.sent_at[self._index]

    @property
    def arrives_at(self) -> float:
        return self._store.arrives_at[self._index]

    @property
    def reliability(self) -> float:
        return self._store.reliability[self._index]

    @property
    def latency_hours(self) -> float:
        return self._store.latency_hours[self._index]

    @property
    def status(self) -> str:
        return self._store._status(self._store.status_codes[self._index])

    @status.setter
    def status(self, value: str) -> None:
        self._store.status_codes[self._index] = self._store._status_code(value)

    @property
    def delivered_at(self) -> float | None:
        value = self._store.delivered_at[self._index]
        return None if value < 0.0 else value

    @delivered_at.setter
    def delivered_at(self, value: float | None) -> None:
        self._store.delivered_at[self._index] = -1.0 if value is None else float(value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "relay_id": self.relay_id,
            "observation_id": self.observation_id,
            "organization_id": self.organization_id,
            "source_node_id": self.source_node_id,
            "destination_node_id": self.destination_node_id,
            "route": self.route,
            "sent_at": self.sent_at,
            "arrives_at": self.arrives_at,
            "reliability": self.reliability,
            "latency_hours": self.latency_hours,
            "status": self.status,
            "delivered_at": self.delivered_at,
        }


class CompactRelayStore(MutableMapping[str, CompactRelayView]):
    """Compact particle relay records with the same mapping interface."""

    __slots__ = (
        "ids", "id_to_index", "observation_ids", "strings", "organization_codes",
        "source_codes", "destination_codes", "routes", "sent_at", "arrives_at",
        "reliability", "latency_hours", "status_codes", "delivered_at",
    )

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.id_to_index: dict[str, int] = {}
        self.observation_ids: list[str] = []
        self.strings = _StringTable()
        self.organization_codes = array("i")
        self.source_codes = array("i")
        self.destination_codes = array("i")
        self.routes: list[tuple[str, ...]] = []
        self.sent_at = array("d")
        self.arrives_at = array("d")
        self.reliability = array("d")
        self.latency_hours = array("d")
        self.status_codes = array("B")
        self.delivered_at = array("d")

    def __len__(self) -> int:
        return len(self.ids)

    def __iter__(self) -> Iterator[str]:
        return iter(self.ids)

    def __getitem__(self, key: str) -> CompactRelayView:
        return CompactRelayView(self, self.id_to_index[key])

    def __setitem__(self, key: str, value: CompactRelayView | InformationRelay) -> None:
        if isinstance(value, CompactRelayView):
            value = InformationRelay(**value.to_payload())
        if not isinstance(value, InformationRelay):
            raise TypeError("compact relays accept InformationRelay values")
        if key != value.relay_id:
            raise KeyError("relay key does not match relay_id")
        if key in self.id_to_index:
            self._remove_index(self.id_to_index[key])
        self.add(value)

    def __delitem__(self, key: str) -> None:
        self._remove_index(self.id_to_index[key])

    def values(self):
        for index in range(len(self.ids)):
            yield CompactRelayView(self, index)

    def items(self):
        for index, key in enumerate(self.ids):
            yield key, CompactRelayView(self, index)

    def get(self, key: str, default: Any = None):
        index = self.id_to_index.get(key)
        return default if index is None else CompactRelayView(self, index)

    def add(self, relay: InformationRelay) -> CompactRelayView:
        index = len(self.ids)
        self.ids.append(relay.relay_id)
        self.id_to_index[relay.relay_id] = index
        self.observation_ids.append(relay.observation_id)
        self.organization_codes.append(self.strings.code(relay.organization_id))
        self.source_codes.append(self.strings.code(relay.source_node_id))
        self.destination_codes.append(self.strings.code(relay.destination_node_id))
        self.routes.append(tuple(relay.route))
        self.sent_at.append(float(relay.sent_at))
        self.arrives_at.append(float(relay.arrives_at))
        self.reliability.append(float(relay.reliability))
        self.latency_hours.append(float(relay.latency_hours))
        self.status_codes.append(self._status_code(relay.status))
        self.delivered_at.append(-1.0 if relay.delivered_at is None else float(relay.delivered_at))
        return CompactRelayView(self, index)

    @staticmethod
    def _status_code(status: str) -> int:
        return {
            "in_transit": _RELAY_IN_TRANSIT,
            "delivered": _RELAY_DELIVERED,
            "dropped": _RELAY_DROPPED,
        }.get(status, _RELAY_DROPPED)

    @staticmethod
    def _status(code: int) -> str:
        return ("in_transit", "delivered", "dropped")[code]

    def _string(self, code: int) -> str | None:
        return None if code == _NONE else self.strings.value(code)

    def retain(self, keep: set[str]) -> None:
        write = 0
        original = len(self.ids)
        for read in range(original):
            if self.ids[read] not in keep:
                continue
            if write != read:
                self._copy_row(read, write)
            write += 1
        while len(self.ids) > write:
            self._pop_last()
        self.id_to_index = {key: index for index, key in enumerate(self.ids)}

    def _copy_row(self, source: int, destination: int) -> None:
        self.ids[destination] = self.ids[source]
        self.observation_ids[destination] = self.observation_ids[source]
        self.routes[destination] = self.routes[source]
        for column in (
            self.organization_codes, self.source_codes, self.destination_codes,
            self.sent_at, self.arrives_at, self.reliability, self.latency_hours,
            self.status_codes, self.delivered_at,
        ):
            column[destination] = column[source]

    def _pop_last(self) -> None:
        index = len(self.ids) - 1
        key = self.ids.pop()
        self.id_to_index.pop(key, None)
        self.observation_ids.pop()
        self.routes.pop()
        for column in (
            self.organization_codes, self.source_codes, self.destination_codes,
            self.sent_at, self.arrives_at, self.reliability, self.latency_hours,
            self.status_codes, self.delivered_at,
        ):
            column.pop()

    def _remove_index(self, index: int) -> None:
        last = len(self.ids) - 1
        if index != last:
            self._copy_row(last, index)
        self._pop_last()
        self.id_to_index = {key: position for position, key in enumerate(self.ids)}

    def clear(self) -> None:
        self.__init__()

    def clone(self) -> "CompactRelayStore":
        result = type(self)()
        for name in self.__slots__:
            value = getattr(self, name)
            if name == "strings":
                value = value.clone()
            elif name == "id_to_index":
                value = dict(value)
            elif name in {"ids", "observation_ids", "routes"}:
                value = list(value)
            elif isinstance(value, array):
                value = array(value.typecode, value)
            setattr(result, name, value)
        return result
