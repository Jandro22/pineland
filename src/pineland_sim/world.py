from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import random
from typing import Any

from .config import SimulationConfig
from .entities import (
    ActorBelief,
    ActorZoneBelief,
    ArmedFormation,
    CausalContribution,
    District,
    EventLogEntry,
    Household,
    Locality,
    Organization,
    Microzone,
    Patrol,
    PhysicalEdge,
    Person,
    SocialCommunity,
    SocialEdge,
    SecurityPost,
    SyntheticRecord,
)


@dataclass(slots=True)
class WorldState:
    config: SimulationConfig
    time: float = 0.0
    districts: dict[str, District] = field(default_factory=dict)
    localities: dict[str, Locality] = field(default_factory=dict)
    households: dict[str, Household] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    social_communities: dict[str, SocialCommunity] = field(default_factory=dict)
    social_edges: dict[tuple[str, str], SocialEdge] = field(default_factory=dict)
    social_neighbors: dict[str, list[str]] = field(default_factory=dict)
    microzones: dict[str, Microzone] = field(default_factory=dict)
    physical_edges: dict[tuple[str, str], PhysicalEdge] = field(default_factory=dict)
    physical_neighbors: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    security_posts: dict[str, SecurityPost] = field(default_factory=dict)
    patrols: dict[str, Patrol] = field(default_factory=dict)
    zone_beliefs: dict[tuple[str, str], ActorZoneBelief] = field(default_factory=dict)
    organizations: dict[str, Organization] = field(default_factory=dict)
    formations: dict[str, ArmedFormation] = field(default_factory=dict)
    beliefs: dict[tuple[str, str], ActorBelief] = field(default_factory=dict)
    adjacency: dict[str, dict[str, float]] = field(default_factory=dict)
    event_log: list[EventLogEntry] = field(default_factory=list)
    causal_ledger: list[CausalContribution] = field(default_factory=list)
    synthetic_records: list[SyntheticRecord] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    initial_population: float = 0.0
    cumulative_deaths: float = 0.0
    cumulative_external_inflow: float = 0.0

    def weighted_population(self) -> float:
        return sum(person.weight for person in self.persons.values())

    def formation_personnel(self) -> float:
        return sum(formation.personnel for formation in self.formations.values())

    def assert_invariants(self, tolerance: float = 1e-6) -> None:
        resident = self.weighted_population()
        expected = self.initial_population - self.cumulative_deaths + self.cumulative_external_inflow
        if abs(resident - expected) > max(tolerance, expected * 1e-10):
            raise AssertionError(f"population conservation failed: resident={resident}, expected={expected}")
        for locality in self.localities.values():
            for vector in locality.control.values():
                for value in vector.to_dict().values():
                    if not 0.0 <= value <= 1.0:
                        raise AssertionError("control component outside [0, 1]")
        for formation in self.formations.values():
            if formation.personnel < 0 or formation.sustainment < 0:
                raise AssertionError("negative formation stock")
        for organization in self.organizations.values():
            if organization.resources < -tolerance:
                raise AssertionError("negative organization budget")
        for microzone in self.microzones.values():
            if not 0 <= microzone.population_share <= 1:
                raise AssertionError("microzone population share outside [0, 1]")
            if any(not 0 <= value <= 1 for value in microzone.physical_control.values()):
                raise AssertionError("microzone physical control outside [0, 1]")
            if any(value < 0 for value in microzone.presence_memory.values()):
                raise AssertionError("negative presence memory")
        for locality_id in self.localities:
            share = sum(zone.population_share for zone in self.microzones.values()
                        if zone.locality_id == locality_id)
            if self.microzones and abs(share - 1.0) > 1e-9:
                raise AssertionError(f"microzone population shares do not sum to one: {locality_id}")
        for edge in self.physical_edges.values():
            if edge.travel_time_hours <= 0 or edge.distance_km <= 0:
                raise AssertionError("physical edge has nonpositive distance or travel time")
        for patrol in self.patrols.values():
            if patrol.current_microzone_id not in self.microzones:
                raise AssertionError("patrol references missing microzone")
        for person in self.persons.values():
            if person.community_id not in self.social_communities:
                raise AssertionError(f"person without valid social community: {person.person_id}")
        for key, edge in self.social_edges.items():
            if key != tuple(sorted(key)) or edge.person_a_id not in self.persons or edge.person_b_id not in self.persons:
                raise AssertionError("invalid social edge endpoint or key")
            if not 0 <= edge.weight <= 1 or not 0 <= edge.language_compatibility <= 1 or not 0 <= edge.trust <= 1:
                raise AssertionError("social edge quantity outside [0, 1]")
            if edge.person_b_id not in self.social_neighbors.get(edge.person_a_id, ()):
                raise AssertionError("social adjacency is not symmetric")
            if edge.person_a_id not in self.social_neighbors.get(edge.person_b_id, ()):
                raise AssertionError("social adjacency is not symmetric")

    def summary(self) -> dict[str, Any]:
        government_control = [loc.control["government"].effective() for loc in self.localities.values()]
        insurgent_control = [loc.control.get("insurgent").effective() if "insurgent" in loc.control else 0.0 for loc in self.localities.values()]
        return {
            "time": self.time,
            "districts": len(self.districts),
            "localities": len(self.localities),
            "agents": len(self.persons),
            "represented_population": self.weighted_population(),
            "households": len(self.households),
            "social_communities": len(self.social_communities),
            "social_edges": len(self.social_edges),
            "mean_social_degree": (2 * len(self.social_edges) / len(self.persons)) if self.persons else 0.0,
            "microzones": len(self.microzones),
            "physical_edges": len(self.physical_edges),
            "security_posts": len(self.security_posts),
            "patrols": len(self.patrols),
            "organizations": len(self.organizations),
            "formations": len(self.formations),
            "events": len(self.event_log),
            "synthetic_records": sum(record.recorded for record in self.synthetic_records),
            "mean_government_effective_control": sum(government_control) / len(government_control),
            "mean_insurgent_effective_control": sum(insurgent_control) / len(insurgent_control),
        }

    def checkpoint(self) -> dict[str, Any]:
        snapshot = {
            "time": self.time,
            "summary": self.summary(),
            "control": {
                locality_id: {actor: vector.to_dict() for actor, vector in locality.control.items()}
                for locality_id, locality in self.localities.items()
            },
            "community_state": {
                community_id: {
                    "locality_id": community.locality_id,
                    "government_cooperation": community.government_cooperation,
                    "insurgent_sympathy": community.insurgent_sympathy,
                }
                for community_id, community in self.social_communities.items()
            },
            "rng_namespace": self.config.random_stream_namespace,
            "seed": self.config.seed,
        }
        self.checkpoints.append(snapshot)
        return snapshot

    def write_results(self, output_dir: str | Path) -> None:
        from .networks import network_diagnostics
        from .physical import physical_diagnostics

        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "summary.json").write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        (output / "checkpoints.json").write_text(json.dumps(self.checkpoints, indent=2), encoding="utf-8")
        records = [asdict(record) for record in self.synthetic_records]
        (output / "synthetic_records.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        causal = [asdict(item) for item in self.causal_ledger]
        (output / "causal_ledger.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in causal), encoding="utf-8"
        )
        (output / "network_diagnostics.json").write_text(
            json.dumps(network_diagnostics(self), indent=2), encoding="utf-8"
        )
        (output / "physical_diagnostics.json").write_text(
            json.dumps(physical_diagnostics(self), indent=2), encoding="utf-8"
        )

    def clone(self) -> "WorldState":
        import copy

        return copy.deepcopy(self)


def seeded_rng(config: SimulationConfig, stream: str) -> random.Random:
    # Stable across Python processes, unlike hash().
    token = f"{config.seed}:{config.random_stream_namespace}:{stream}".encode()
    value = int.from_bytes(__import__("hashlib").sha256(token).digest()[:8], "big")
    return random.Random(value)
