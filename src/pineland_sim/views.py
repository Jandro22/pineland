"""Explicit truth/belief/record access boundaries.

The mutable :class:`WorldState` remains the authoritative state container, but
decision code should request the narrowest view it needs.  These lightweight
facades are intentionally read-only and make truth-firewall tests possible
without introducing a framework or duplicating state.
"""
from __future__ import annotations

from dataclasses import asdict
from types import MappingProxyType
from typing import Any

from .entities import ControlVector


class WorldTruthView:
    """Privileged analyst/environment view of realized state."""

    def __init__(self, world) -> None:
        self._world = world

    def control(self, locality_id: str, actor_id: str) -> ControlVector:
        return ControlVector(**self._world.localities[locality_id].control.get(
            actor_id, ControlVector()).to_dict())

    def formation_position(self, formation_id: str) -> dict[str, Any]:
        formation = self._world.formations[formation_id]
        return {"locality_id": formation.locality_id,
                "microzone_id": formation.current_microzone_id,
                "moving": formation.moving,
                "personnel": formation.personnel}

    def microzone_control(self, microzone_id: str, actor_id: str) -> float:
        return self._world.microzones[microzone_id].physical_control.get(actor_id, 0.0)


class ActorBeliefView:
    """Read-only actor-facing beliefs with no access to realized controls."""

    def __init__(self, world, actor_id: str | None = None) -> None:
        self._world = world
        self.actor_id = actor_id

    def expected_control(self, person_id: str, actor_id: str = "government") -> float:
        person = self._world.persons[person_id]
        return float(person.expected_control.get(actor_id, .5))

    def expected_destination_control(self, person_id: str, locality_id: str,
                                     actor_id: str = "government") -> float:
        person = self._world.persons[person_id]
        destination = person.expected_control_by_locality.get(locality_id, {})
        return float(destination.get(actor_id, person.expected_control.get(actor_id, .5)))

    def locality_control(self, locality_id: str, target_actor_id: str,
                         actor_id: str | None = None) -> ControlVector:
        observer = actor_id or self.actor_id
        if observer is not None:
            belief = self._world.control_beliefs.get((observer, target_actor_id, locality_id))
            if belief is not None:
                return ControlVector(**belief.control_estimate.to_dict())
            legacy = self._world.beliefs.get((observer, locality_id))
            if legacy is not None:
                return ControlVector(**legacy.control_estimate.to_dict())
        return ControlVector(*([.5] * 7))

    def locality_violence(self, locality_id: str, actor_id: str | None = None,
                          target_actor_id: str = "government") -> float:
        """Return an actor-local violence estimate, never realized violence.

        The estimate is carried alongside the actor's control belief and is
        updated by reported physical-control observations.  Missing beliefs
        intentionally fall back to an uninformative prior.
        """
        observer = actor_id or self.actor_id
        if observer is not None:
            belief = self._world.control_beliefs.get((observer, target_actor_id, locality_id))
            if belief is not None:
                return float(belief.violence_estimate)
        return 0.2

    def microzone_control(self, actor_id: str, microzone_id: str) -> float:
        belief = self._world.zone_beliefs.get((actor_id, microzone_id))
        return float(belief.physical_control_estimate if belief is not None else .5)


class EmpiricalRecordView:
    """Researcher-facing recorded layer, separate from latent truth."""

    def __init__(self, world) -> None:
        self._records = tuple(_freeze(asdict(record)) for record in world.synthetic_records
                              if record.recorded)

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        return self._records

    def by_event_type(self, event_type: str) -> tuple[dict[str, Any], ...]:
        return tuple(record for record in self._records if record["event_type"] == event_type)


def _freeze(value: Any) -> Any:
    """Recursively make a recorded value immutable for actor/research views."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value
