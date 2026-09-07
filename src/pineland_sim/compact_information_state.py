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
from typing import Any, Iterable, Mapping

from .entities import ActorBelief, CONTROL_DIMENSIONS, clamp


CONTROL_STATE_STRIDE = 13
PRESENCE_STATE_STRIDE = 7
ZONE_STATE_STRIDE = 6
_CONTROL_FIELD_COUNT = len(CONTROL_DIMENSIONS)
_NUMERIC_FIELD_COUNT = CONTROL_STATE_STRIDE


def _state_sha256(tag: bytes, keys: tuple[tuple[str, ...], ...],
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

    __slots__ = ("keys", "key_to_index", "state")
    STRIDE = 0
    HASH_TAG = b"pineland.compact.belief.v1\0"

    def __init__(
        self,
        keys: Iterable[tuple[str, ...]] = (),
        state: array | None = None,
    ) -> None:
        normalized_keys = tuple(keys)
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

    @classmethod
    def from_beliefs(cls, beliefs: Mapping[tuple[str, ...], Any]):
        keys = tuple(sorted(beliefs))
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
        self.keys = (*self.keys, key)
        self.key_to_index[key] = index
        self.state.extend(self._belief_row(belief))
        return index

    def row(self, key: tuple[str, ...]) -> tuple[float, ...]:
        offset = self.index(key) * self.STRIDE
        return tuple(self.state[offset:offset + self.STRIDE])

    def sync_confidence_to_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> None:
        """Mirror confidence after decay while preserving all other fields."""
        for key, index in self.key_to_index.items():
            belief = beliefs.get(key)
            if belief is not None:
                belief.confidence = self.state[index * self.STRIDE + self.CONFIDENCE_OFFSET]

    def sync_from_beliefs(self, beliefs: Mapping[tuple[str, ...], Any]) -> None:
        """Reconcile rows after an intentional external object-model edit."""
        if tuple(sorted(beliefs)) != tuple(sorted(self.keys)):
            replacement = type(self).from_beliefs(beliefs)
            self.keys = replacement.keys
            self.key_to_index = replacement.key_to_index
            self.state = replacement.state
            return
        for key in self.keys:
            offset = self.key_to_index[key] * self.STRIDE
            self.state[offset:offset + self.STRIDE] = array(
                "d", self._belief_row(beliefs[key])
            )

    def clone(self):
        return type(self)(self.keys, array("d", self.state))

    def state_sha256(self) -> str:
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

    def decay(self, elapsed: float, default_rate: float, target_rate: float) -> None:
        if elapsed <= 0.0:
            return
        for index, key in enumerate(self.keys):
            rate = target_rate if key[-1] != "*" else default_rate
            offset = index * self.STRIDE + self.CONFIDENCE_OFFSET
            self.state[offset] = clamp(self.state[offset] * exp(-rate * elapsed))

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
        if elapsed <= 0.0:
            return
        factor = exp(-rate * elapsed)
        for offset in range(self.CONFIDENCE_OFFSET, len(self.state), self.STRIDE):
            self.state[offset] = clamp(self.state[offset] * factor)

    def fuse(
        self,
        key: tuple[str, ...],
        observed: float,
        time: float,
        weight: float,
        contradiction_memory_days: float,
        contradiction_penalty: float,
    ) -> None:
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
        normalized_keys = tuple(keys)
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
        keys = tuple(sorted(beliefs))
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
        self.keys = (*self.keys, key)
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
            self.keys = replacement.keys
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
