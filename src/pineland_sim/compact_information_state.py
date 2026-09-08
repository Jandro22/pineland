"""Persistent structure-of-arrays storage for optimized control beliefs.

The reference information model stores each belief as an ``ActorBelief`` with
an embedded ``ControlVector``.  That representation remains the public and
scientific oracle.  The optimized execution path uses this module as its
authoritative numeric state during fusion and decay, then mirrors the result
back to the oracle objects at the decision boundary.

The layout is intentionally flat and stable so it can be passed directly to
the existing native batch kernel without rebuilding a per-tick payload::

    [formal, physical, administrative, legal, fiscal, social, expected,
     confidence, updated_at, last_reliable_observation_at, evidence_count,
     contradiction_index, violence_estimate]

No model equations live here; the scalar recurrence is the same recurrence as
the reference implementation in :mod:`pineland_sim.information`.
"""
from __future__ import annotations

from array import array
import hashlib
import struct
from math import exp
from typing import Any, Iterable, Mapping, Sequence

from .entities import ActorBelief, CONTROL_DIMENSIONS, clamp


CONTROL_STATE_STRIDE = 13
PRESENCE_STATE_STRIDE = 7
ZONE_STATE_STRIDE = 6
_CONTROL_FIELD_COUNT = len(CONTROL_DIMENSIONS)
_NUMERIC_FIELD_COUNT = CONTROL_STATE_STRIDE


def _state_sha256(tag: bytes, keys: Sequence[tuple[str, ...]],
                  key_to_index: Mapping[tuple[str, ...], int], state: array,
                  stride: int) -> str:
    """Hash a keyed numeric store in canonical key order."""
    digest = hashlib.sha256()
    digest.update(tag)
    row_format = f"!{stride}d"
    for key in sorted(keys):
        encoded = "\x1f".join(key).encode("utf-8")
        digest.update(struct.pack("!I", len(encoded)))
        digest.update(encoded)
        offset = key_to_index[key] * stride
        digest.update(struct.pack(row_format, *state[offset:offset + stride]))
    return digest.hexdigest()


class _CompactBeliefState:
    """Shared append-only keyed storage for compact numeric belief rows."""

    __slots__ = (
        "keys", "key_to_index", "state", "decay_event_positions",
        "decay_events", "logical_time", "default_decay_rate",
        "target_decay_rate",
    )
    STRIDE = 0
    HASH_TAG = b"pineland.compact.belief.v1\0"

    def __init__(
        self,
        keys: Iterable[tuple[str, ...]] = (),
        state: array | None = None,
        decay_event_positions: array | None = None,
        decay_events: Iterable[tuple[float, float, float]] = (),
        logical_time: float = 0.0,
        default_decay_rate: float = 0.0,
        target_decay_rate: float = 0.0,
    ) -> None:
        normalized_keys = list(keys)
        if len(set(normalized_keys)) != len(normalized_keys):
            raise ValueError("compact belief keys must be unique")
        self.keys = normalized_keys
        self.key_to_index = {
            key: index for index, key in enumerate(normalized_keys)
        }
        self.state = array("d") if state is None else state
        if self.state.typecode != "d":
            raise TypeError("compact belief state must be array('d')")
        if len(self.state) != len(self.keys) * self.STRIDE:
            raise ValueError("compact belief state has an invalid row stride")
        self.decay_event_positions = (
            array("I", [0] * len(self.keys))
            if decay_event_positions is None else decay_event_positions
        )
        if len(self.decay_event_positions) != len(self.keys):
            raise ValueError("compact belief decay positions have invalid length")
        if self.decay_event_positions.typecode != "I":
            raise TypeError("compact belief decay positions must be array('I')")
        self.decay_events = tuple(
            (float(elapsed), float(default_rate), float(target_rate))
            for elapsed, default_rate, target_rate in decay_events
        )
        self.logical_time = float(logical_time)
        self.default_decay_rate = float(default_decay_rate)
        self.target_decay_rate = float(target_decay_rate)

    @classmethod
    def from_beliefs(cls, beliefs: Mapping[tuple[str, ...], Any]):
        keys = sorted(beliefs)
        state = array("d")
        for key in keys:
            state.extend(cls._belief_row(beliefs[key]))
        return cls(keys, state)

    def __len__(self) -> int:
        return len(self.keys)

    def index(self, key: tuple[str, ...]) -> int:
        return self.key_to_index[key]

    def ensure(self, key: tuple[str, ...], belief: Any) -> int:
        """Return a row index, appending a dynamically-created belief."""
        index = self.key_to_index.get(key)
        if index is not None:
            return index
        index = len(self.keys)
        self.keys.append(key)
        self.key_to_index[key] = index
        self.state.extend(self._belief_row(belief))
        self.decay_event_positions.append(len(self.decay_events))
        return index

    def row(self, key: tuple[str, ...]) -> tuple[float, ...]:
        self.materialize(key)
        offset = self.index(key) * self.STRIDE
        return tuple(self.state[offset:offset + self.STRIDE])

    def _decay_rate(self, key: tuple[str, ...]) -> float:
        return self.default_decay_rate

    def _event_decay_rate(
        self, key: tuple[str, ...], default_rate: float, target_rate: float
    ) -> float:
        return default_rate

    def configure_decay(self, default_rate: float, target_rate: float = 0.0) -> None:
        self.default_decay_rate = float(default_rate)
        self.target_decay_rate = float(target_rate)

    def set_decay_clock(self, time: float) -> None:
        """Set the initial lazy-decay reference for all existing rows."""
        self.logical_time = float(time)
        self.decay_events = ()
        self.decay_event_positions = array("I", [0] * len(self.keys))

    def advance_decay(self, time: float) -> None:
        """Record an exact decay step without walking the belief population."""
        target_time = float(time)
        elapsed = target_time - self.logical_time
        if elapsed <= 0.0:
            return
        self.decay_events = (*self.decay_events, (
            elapsed, self.default_decay_rate, self.target_decay_rate
        ))
        self.logical_time = target_time

    def materialize(self, key: tuple[str, ...], time: float | None = None) -> None:
        """Apply pending decay steps to one row, preserving eager arithmetic."""
        self.materialize_index(self.index(key), key, time=time)

    def materialize_index(
        self,
        index: int,
        key: tuple[str, ...],
        *,
        time: float | None = None,
    ) -> None:
        """Materialize a known row index without repeating the key lookup."""
        index = int(index)
        event_index = self.decay_event_positions[index]
        if event_index < len(self.decay_events):
            offset = index * self.STRIDE + self.CONFIDENCE_OFFSET
            confidence = self.state[offset]
            for elapsed, default_rate, target_rate in self.decay_events[event_index:]:
                rate = self._event_decay_rate(key, default_rate, target_rate)
                confidence = clamp(confidence * exp(-rate * elapsed))
            self.state[offset] = confidence
            self.decay_event_positions[index] = len(self.decay_events)

    def sync_confidence_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any],
                                   time: float | None = None) -> None:
        """Mirror confidence after decay while preserving all other fields."""
        for key, index in self.key_to_index.items():
            belief = beliefs.get(key)
            if belief is not None:
                self.materialize(key, time)
                belief.confidence = self.state[index * self.STRIDE + self.CONFIDENCE_OFFSET]

    def sync_from_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> None:
        """Reconcile rows after an intentional external object-model edit."""
        if tuple(sorted(beliefs)) != tuple(sorted(self.keys)):
            replacement = type(self).from_beliefs(beliefs)
            self.keys = list(replacement.keys)
            self.key_to_index = replacement.key_to_index
            self.state = replacement.state
            self.decay_event_positions = array(
                "I", [len(self.decay_events)] * len(self.keys)
            )
            return
        for key in self.keys:
            offset = self.key_to_index[key] * self.STRIDE
            self.state[offset:offset + self.STRIDE] = array(
                "d", self._belief_row(beliefs[key])
            )
            self.decay_event_positions[self.key_to_index[key]] = len(self.decay_events)

    def clone(self):
        return type(self)(
            self.keys,
            array("d", self.state),
            array("I", self.decay_event_positions),
            self.decay_events,
            self.logical_time,
            self.default_decay_rate,
            self.target_decay_rate,
        )

    def state_sha256(self) -> str:
        for key in self.keys:
            self.materialize(key)
        return _state_sha256(
            self.HASH_TAG, self.keys, self.key_to_index, self.state,
            self.STRIDE,
        )


class CompactPresenceBeliefState(_CompactBeliefState):
    """Persistent numeric rows for actor and command-node presence beliefs."""

    STRIDE = PRESENCE_STATE_STRIDE
    CONFIDENCE_OFFSET = 1
    HASH_TAG = b"pineland.compact.presence.v1\0"

    @staticmethod
    def _belief_row(belief: Any) -> tuple[float, ...]:
        return (
            float(belief.presence_estimate),
            float(belief.confidence),
            float(belief.updated_at),
            float(belief.last_reliable_observation_at),
            float(belief.evidence_count),
            float(belief.contradiction_index),
            float(belief.personnel_estimate),
        )

    def write_to_belief(self, key: tuple[str, ...], belief: Any) -> None:
        offset = self.index(key) * self.STRIDE
        belief.presence_estimate = self.state[offset]
        belief.confidence = self.state[offset + 1]
        belief.updated_at = self.state[offset + 2]
        belief.last_reliable_observation_at = self.state[offset + 3]
        belief.evidence_count = int(self.state[offset + 4])
        belief.contradiction_index = self.state[offset + 5]
        belief.personnel_estimate = self.state[offset + 6]

    def sync_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> None:
        for key in self.keys:
            belief = beliefs.get(key)
            if belief is not None:
                self.write_to_belief(key, belief)

    def _decay_rate(self, key: tuple[str, ...]) -> float:
        return self.target_decay_rate if key[-1] != "*" else self.default_decay_rate

    def _event_decay_rate(
        self, key: tuple[str, ...], default_rate: float, target_rate: float
    ) -> float:
        return target_rate if key[-1] != "*" else default_rate

    def decay(self, elapsed: float, default_rate: float, target_rate: float) -> None:
        """Compatibility entry point; advance a lazy confidence clock."""
        self.configure_decay(default_rate, target_rate)
        self.advance_decay(self.logical_time + max(0.0, float(elapsed)))

    def fuse(
        self,
        key: tuple[str, ...],
        presence: float,
        personnel: float,
        time: float,
        weight: float,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> None:
        # A fusion itself does not advance the reference model's confidence
        # clock. ``decay_information`` advances ``logical_time`` explicitly;
        # use that clock here so direct/API fusions retain oracle semantics.
        self.materialize(key)
        offset = self.index(key) * self.STRIDE
        old_confidence = self.state[offset + 1]
        prior = max(.02, old_confidence)
        denominator = prior + weight
        old_presence = self.state[offset]
        contradiction = self.state[offset + 5] * exp(
            -max(0.0, time - self.state[offset + 2]) /
            contradiction_memory_days
        )
        contradiction += weight * abs(presence - old_presence)
        self.state[offset] = clamp(
            (prior * old_presence + weight * presence) / denominator
        )
        self.state[offset + 6] = (
            self.state[offset + 6] * max(.02, old_confidence) +
            personnel * weight
        ) / (max(.02, old_confidence) + weight)
        self.state[offset + 1] = clamp(
            (prior + weight) / (1.0 + prior + weight) *
            exp(-contradiction_penalty * contradiction)
        )
        self.state[offset + 2] = time
        self.state[offset + 4] += 1.0
        self.state[offset + 5] = contradiction
        if weight >= .12:
            self.state[offset + 3] = time

    def equivalent_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> bool:
        return (
            set(self.keys) == set(beliefs) and
            all(self.row(key) == self._belief_row(beliefs[key]) for key in self.keys)
        )


class CompactZoneBeliefState(_CompactBeliefState):
    """Persistent numeric rows for microzone routing beliefs."""

    STRIDE = ZONE_STATE_STRIDE
    CONFIDENCE_OFFSET = 1
    HASH_TAG = b"pineland.compact.zone.v1\0"

    @staticmethod
    def _belief_row(belief: Any) -> tuple[float, ...]:
        return (
            float(belief.physical_control_estimate),
            float(belief.confidence),
            float(belief.updated_at),
            float(belief.last_reliable_observation_at),
            float(belief.evidence_count),
            float(belief.contradiction_index),
        )

    def write_to_belief(self, key: tuple[str, ...], belief: Any) -> None:
        offset = self.index(key) * self.STRIDE
        belief.physical_control_estimate = self.state[offset]
        belief.confidence = self.state[offset + 1]
        belief.updated_at = self.state[offset + 2]
        belief.last_reliable_observation_at = self.state[offset + 3]
        belief.evidence_count = int(self.state[offset + 4])
        belief.contradiction_index = self.state[offset + 5]

    def sync_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> None:
        for key in self.keys:
            belief = beliefs.get(key)
            if belief is not None:
                self.write_to_belief(key, belief)

    def decay(self, elapsed: float, rate: float) -> None:
        """Compatibility entry point; advance a lazy confidence clock."""
        self.configure_decay(rate)
        self.advance_decay(self.logical_time + max(0.0, float(elapsed)))

    def fuse(
        self,
        key: tuple[str, ...],
        observed: float,
        time: float,
        weight: float,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> None:
        # Confidence decay is advanced explicitly by ``decay_information``;
        # an observation timestamp alone is not a decay event.
        self.materialize(key)
        offset = self.index(key) * self.STRIDE
        old_confidence = self.state[offset + 1]
        prior = max(.02, old_confidence)
        denominator = prior + weight
        old_value = self.state[offset]
        contradiction = self.state[offset + 5] * exp(
            -max(0.0, time - self.state[offset + 2]) /
            contradiction_memory_days
        ) + weight * abs(observed - old_value)
        self.state[offset] = clamp(
            (prior * old_value + weight * observed) / denominator
        )
        self.state[offset + 1] = clamp(
            (prior + weight) / (1.0 + prior + weight) *
            exp(-contradiction_penalty * contradiction)
        )
        self.state[offset + 2] = time
        self.state[offset + 4] += 1.0
        self.state[offset + 5] = contradiction
        if weight >= .12:
            self.state[offset + 3] = time

    def equivalent_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> bool:
        return (
            set(self.keys) == set(beliefs) and
            all(self.row(key) == self._belief_row(beliefs[key]) for key in self.keys)
        )


class CompactControlBeliefState:
    """Persistent numeric control-belief store keyed by public belief keys.

    ``state`` is the authoritative optimized representation.  The mapping of
    keys to rows is deterministic for generated priors and append-only for
    dynamically discovered targets.  Appending keeps existing native indices
    stable across an information tick and avoids copying the hot state array.
    """

    __slots__ = ("keys", "key_to_index", "state")

    def __init__(
        self,
        keys: Iterable[tuple[str, str, str]] = (),
        state: array | None = None,
    ) -> None:
        normalized_keys = list(keys)
        if len(set(normalized_keys)) != len(normalized_keys):
            raise ValueError("compact control-belief keys must be unique")
        self.keys = normalized_keys
        self.key_to_index = {
            key: index for index, key in enumerate(normalized_keys)
        }
        self.state = array("d") if state is None else state
        if self.state.typecode != "d":
            raise TypeError("compact control-belief state must be array('d')")
        if len(self.state) != len(self.keys) * CONTROL_STATE_STRIDE:
            raise ValueError(
                "compact control-belief state has an invalid row stride"
            )

    @classmethod
    def from_beliefs(
        cls, beliefs: Mapping[tuple[str, str, str], ActorBelief]
    ) -> "CompactControlBeliefState":
        keys = sorted(beliefs)
        state = array("d")
        for key in keys:
            state.extend(cls._belief_row(beliefs[key]))
        return cls(keys, state)

    @staticmethod
    def _belief_row(belief: ActorBelief) -> tuple[float, ...]:
        estimate = belief.control_estimate
        return (
            float(estimate.formal),
            float(estimate.physical),
            float(estimate.administrative),
            float(estimate.legal),
            float(estimate.fiscal),
            float(estimate.social),
            float(estimate.expected),
            float(belief.confidence),
            float(belief.updated_at),
            float(belief.last_reliable_observation_at),
            float(belief.evidence_count),
            float(belief.contradiction_index),
            float(belief.violence_estimate),
        )

    def __len__(self) -> int:
        return len(self.keys)

    def clone(self) -> "CompactControlBeliefState":
        """Copy row storage for an independent particle/world clone."""
        return type(self)(self.keys, array("d", self.state))

    def index(self, key: tuple[str, str, str]) -> int:
        return self.key_to_index[key]

    def ensure(
        self,
        key: tuple[str, str, str],
        belief: ActorBelief,
    ) -> int:
        """Return a row index, appending a newly-created belief if needed."""
        index = self.key_to_index.get(key)
        if index is not None:
            return index
        index = len(self.keys)
        self.keys.append(key)
        self.key_to_index[key] = index
        self.state.extend(self._belief_row(belief))
        return index

    def row(self, key: tuple[str, str, str]) -> tuple[float, ...]:
        offset = self.index(key) * CONTROL_STATE_STRIDE
        return tuple(self.state[offset:offset + CONTROL_STATE_STRIDE])

    def write_to_belief(
        self,
        key: tuple[str, str, str],
        belief: ActorBelief,
    ) -> None:
        """Mirror one authoritative row into the scientific oracle object."""
        offset = self.index(key) * CONTROL_STATE_STRIDE
        estimate = belief.control_estimate
        estimate.formal = self.state[offset]
        estimate.physical = self.state[offset + 1]
        estimate.administrative = self.state[offset + 2]
        estimate.legal = self.state[offset + 3]
        estimate.fiscal = self.state[offset + 4]
        estimate.social = self.state[offset + 5]
        estimate.expected = self.state[offset + 6]
        belief.confidence = self.state[offset + 7]
        belief.updated_at = self.state[offset + 8]
        belief.last_reliable_observation_at = self.state[offset + 9]
        belief.evidence_count = int(self.state[offset + 10])
        belief.contradiction_index = self.state[offset + 11]
        belief.violence_estimate = self.state[offset + 12]

    def sync_to_beliefs(
        self,
        beliefs: Mapping[tuple[str, str, str], ActorBelief],
    ) -> None:
        for key in self.keys:
            belief = beliefs.get(key)
            if belief is not None:
                self.write_to_belief(key, belief)

    def sync_confidence_to_beliefs(
        self,
        beliefs: Mapping[tuple[str, str, str], ActorBelief],
    ) -> None:
        """Mirror only confidence after decay, preserving untouched metadata."""
        for key, index in self.key_to_index.items():
            belief = beliefs.get(key)
            if belief is not None:
                belief.confidence = self.state[
                    index * CONTROL_STATE_STRIDE + 7
                ]

    def sync_from_beliefs(
        self,
        beliefs: Mapping[tuple[str, str, str], ActorBelief],
    ) -> None:
        """Reconcile after a deliberate external object-model mutation.

        Normal optimized runs do not need this copy: all control-belief
        writes go through this store.  It is exposed for conditioning code and
        tests that intentionally edit the reference objects before switching
        execution backends.
        """
        if tuple(sorted(beliefs)) != tuple(sorted(self.keys)):
            replacement = type(self).from_beliefs(beliefs)
            self.keys = list(replacement.keys)
            self.key_to_index = replacement.key_to_index
            self.state = replacement.state
            return
        for key in self.keys:
            belief = beliefs[key]
            offset = self.key_to_index[key] * CONTROL_STATE_STRIDE
            self.state[offset:offset + CONTROL_STATE_STRIDE] = array(
                "d", self._belief_row(belief)
            )

    def decay(self, elapsed: float, rate: float) -> None:
        """Apply exact confidence decay to every compact control belief."""
        if elapsed <= 0.0:
            return
        factor = exp(-rate * elapsed)
        for offset in range(7, len(self.state), CONTROL_STATE_STRIDE):
            self.state[offset] = clamp(self.state[offset] * factor)

    def fuse(
        self,
        key: tuple[str, str, str],
        values: Mapping[str, float],
        time: float,
        weight: float,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> None:
        """Apply the reference control recurrence directly to one row."""
        offset = self.index(key) * CONTROL_STATE_STRIDE
        prior_confidence = self.state[offset + 7]
        contradiction_decay = exp(
            -max(0.0, time - self.state[offset + 8])
            / contradiction_memory_days
        )
        prior = max(0.02, prior_confidence)
        contradiction = self.state[offset + 11]
        denominator = prior + weight
        confidence_scale = denominator / (1.0 + denominator)
        confidence = prior_confidence
        if len(values) == _CONTROL_FIELD_COUNT and tuple(values) == CONTROL_DIMENSIONS:
            dimensions = enumerate(CONTROL_DIMENSIONS)
        else:
            dimensions = (
                (CONTROL_DIMENSIONS.index(dimension), dimension)
                for dimension in values
                if dimension in CONTROL_DIMENSIONS
            )
        for dimension_index, dimension in dimensions:
            old = self.state[offset + dimension_index]
            observed = clamp(float(values[dimension]))
            self.state[offset + dimension_index] = clamp(
                (prior * old + weight * observed) / denominator
            )
            contradiction = (
                contradiction * contradiction_decay
                + weight * abs(observed - old)
            )
            confidence = clamp(
                confidence_scale * exp(-contradiction_penalty * contradiction)
            )
        self.state[offset + 7] = confidence
        self.state[offset + 8] = time
        if weight >= 0.12:
            self.state[offset + 9] = time
        self.state[offset + 10] += 1.0
        self.state[offset + 11] = contradiction

    def equivalent_to_beliefs(
        self,
        beliefs: Mapping[tuple[str, str, str], ActorBelief],
    ) -> bool:
        """Return exact field equality against the object-model oracle."""
        if set(self.keys) != set(beliefs):
            return False
        for key in self.keys:
            if self.row(key) != self._belief_row(beliefs[key]):
                return False
        return True

    def state_sha256(self) -> str:
        """Hash keys and numeric rows in canonical key order for diagnostics."""
        digest = hashlib.sha256()
        digest.update(b"pineland.compact.control.v1\0")
        for key in sorted(self.keys):
            encoded = "\x1f".join(key).encode("utf-8")
            digest.update(struct.pack("!I", len(encoded)))
            digest.update(encoded)
            digest.update(struct.pack(
                "!13d", *self.row(key)
            ))
        return digest.hexdigest()
