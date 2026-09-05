"""Trace endogenous insurgent locality activation episodes without changing dynamics.

The tracer is an observation-only wrapper around ``ProcessEngine.execute``. It
does not draw random numbers, mutate actor-facing state, or inspect historical
case outcomes. Three activation channels use thresholds that already have live
model semantics:

* ``member_foothold_present``: positive represented armed membership exists in
  the locality. This is not an invented viability cutoff: any positive member
  mass creates a positive ``member_access`` term in the live recruitment
  equation, so it is the lowest causally active clandestine foothold state;

* ``member_access_saturated``: local represented armed membership reaches the
  existing ``minimum_proto_represented_population`` denominator at which the
  local member-access recruitment channel saturates at 1;
* ``fielded_force_viable``: effective local insurgent formation personnel reach
  the existing ``minimum_formation_personnel`` force-generation threshold.

Episodes retain parent locality/channel attribution where the event transition
provides it. This supports gross-versus-net locality reproduction estimands and
prevents simple force relocation from being mislabeled as insurgent offspring.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "studies" / "research_program" / "locality_activation_genealogy.json"

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    audit_run_manifest,
    build_run_manifest,
    file_sha256,
)
from identify_social_exposure_provenance import (  # noqa: E402
    SocialExposureProvenanceTracer,
)


PARENTAGE_CLASSES = (
    "local_spontaneous_ignition",
    "social_network_seeded",
    "migrating_member_seeded",
    "formation_recruitment_seeded",
    "formation_relocation",
    "organizational_split_offspring",
    "sanctuary_external_seeded",
    "unresolved",
)


def classify_parentage(cause: str, event_type: str) -> str:
    """Normalize every non-root foothold into the causal parentage ontology."""
    cause = str(cause or "").lower()
    event_type = str(event_type or "").lower()
    if cause == "initial_condition":
        return "initial_condition"
    if cause == "formation_relocation":
        return "formation_relocation"
    if cause == "armed_member_migration":
        return "migrating_member_seeded"
    if cause == "stored_social_exposure_recruitment":
        return "social_network_seeded"
    if cause == "formation_seeded_local_recruitment":
        return "formation_recruitment_seeded"
    if "split" in cause or "offspring" in cause:
        return "organizational_split_offspring"
    if any(token in cause or token in event_type for token in (
        "sanctuary", "external", "foreign", "diaspora",
    )):
        return "sanctuary_external_seeded"
    if cause in {"local_recruitment", "local_force_generation"}:
        return "local_spontaneous_ignition"
    return "unresolved"


@dataclass
class ActivationEpisode:
    activation_id: str
    channel: str
    locality_id: str
    activation_day: float
    activation_end_day: float | None
    observation_end_day: float | None
    viable: bool
    cause: str
    event_type: str
    event_id: str | None
    parentage_class: str
    parent_locality_id: str | None = None
    parent_channel: str | None = None
    parent_activation_id: str | None = None
    parent_weight: float = 1.0
    parent_weights: dict[str, float] | None = None
    parent_activation_ids: dict[str, str | None] | None = None
    parent_unattributed_weight: float = 0.0
    censored: bool = False


class LocalityActivationTracer:
    CHANNELS = (
        "member_foothold_present",
        "member_access_saturated",
        "fielded_force_viable",
    )

    def __init__(self, world) -> None:
        self.world = world
        self.social_provenance = SocialExposureProvenanceTracer(world)
        self.episodes: list[ActivationEpisode] = []
        self.current: dict[tuple[str, str], str] = {}
        self.latest: dict[tuple[str, str], str] = {}
        self._by_id: dict[str, ActivationEpisode] = {}
        self._sequence = 0

    def _active_insurgent_ids(self) -> set[str]:
        return {
            organization.organization_id
            for organization in self.world.organizations.values()
            if organization.kind is OrganizationKind.INSURGENT
            and organization.status == "active"
        }

    def capture(self) -> dict[str, Any]:
        insurgents = self._active_insurgent_ids()
        persons = {
            person.person_id: {
                "locality": person.residence_locality_id,
                "organization_id": person.organization_id,
                "armed_fraction": person.armed_fraction,
                "public_behavior": person.public_behavior,
                "insurgent_affinity": dict(person.insurgent_affinity),
                "social_exposure": dict(person.social_exposure),
                "represented_armed": (
                    person.weight * person.armed_fraction
                    if person.organization_id in insurgents else 0.0
                ),
            }
            for person in self.world.persons.values()
        }
        formations = {
            formation.formation_id: {
                "locality": formation.locality_id,
                "organization_id": formation.organization_id,
                "personnel": formation.personnel,
                "effective": bool(
                    formation.organization_id in insurgents
                    and formation.personnel > 0
                    and formation.operational_status == "effective"
                    and not formation.outside_pineland
                    and not formation.moving
                ),
            }
            for formation in self.world.formations.values()
        }
        member_mass = {locality_id: 0.0 for locality_id in self.world.localities}
        formation_mass = {locality_id: 0.0 for locality_id in self.world.localities}
        for row in persons.values():
            member_mass[row["locality"]] += float(row["represented_armed"])
        for row in formations.values():
            if row["effective"]:
                formation_mass[row["locality"]] += float(row["personnel"])
        cfg = self.world.config.organization_ecology
        states = {
            "member_foothold_present": {
                locality_id: mass > 1e-12
                for locality_id, mass in member_mass.items()
            },
            "member_access_saturated": {
                locality_id: mass + 1e-12 >= cfg.minimum_proto_represented_population
                for locality_id, mass in member_mass.items()
            },
            "fielded_force_viable": {
                locality_id: mass + 1e-12 >= cfg.minimum_formation_personnel
                for locality_id, mass in formation_mass.items()
            },
        }
        return {
            "active_insurgent_ids": tuple(sorted(insurgents)),
            "persons": persons,
            "formations": formations,
            "member_mass": member_mass,
            "formation_mass": formation_mass,
            "states": states,
        }

    def initialize(self, time: float = 0.0) -> None:
        snapshot = self.capture()
        for channel in self.CHANNELS:
            for locality_id, active in snapshot["states"][channel].items():
                if active:
                    self._open(
                        channel, locality_id, time,
                        cause="initial_condition", event_type="initial_condition",
                        event_id=None, parent_sources={}, parent_channel=None,
                    )

    def _open(
        self,
        channel: str,
        locality_id: str,
        time: float,
        *,
        cause: str,
        event_type: str,
        event_id: str | None,
        parent_sources: dict[str, float],
        parent_channel: str | None,
        parent_unattributed_mass: float = 0.0,
    ) -> ActivationEpisode:
        self._sequence += 1
        activation_id = f"ACT-{self._sequence:08d}"
        parent_locality = (
            max(parent_sources, key=lambda key: (parent_sources[key], key))
            if parent_sources else None
        )
        parent_activation = None
        parent_activation_ids: dict[str, str | None] = {}
        if parent_channel:
            for source_locality in parent_sources:
                if cause == "stored_social_exposure_recruitment":
                    # Stored exposure identifies the ultimate source locality,
                    # not necessarily which of several historical activation
                    # episodes at that locality generated the lineage. Resolve
                    # an episode only when the observed genealogy makes it
                    # unique; after deactivation/reactivation, choosing
                    # current or latest would manufacture precision.
                    candidates = [
                        episode.activation_id
                        for episode in self.episodes
                        if episode.channel == parent_channel
                        and episode.locality_id == source_locality
                        and episode.activation_day <= float(time) + 1e-12
                    ]
                    source_activation = (
                        candidates[0] if len(candidates) == 1 else None
                    )
                else:
                    source_activation = self.current.get(
                        (parent_channel, source_locality)
                    )
                    if source_activation is None:
                        source_activation = self.latest.get(
                            (parent_channel, source_locality)
                        )
                parent_activation_ids[source_locality] = source_activation
        if parent_locality and parent_channel:
            parent_activation = parent_activation_ids.get(parent_locality)
        total_parent_weight = (
            sum(parent_sources.values()) + max(0.0, float(parent_unattributed_mass))
        )
        episode = ActivationEpisode(
            activation_id=activation_id,
            channel=channel,
            locality_id=locality_id,
            activation_day=float(time),
            activation_end_day=None,
            observation_end_day=None,
            viable=True,
            cause=cause,
            event_type=event_type,
            event_id=event_id,
            parentage_class=classify_parentage(cause, event_type),
            parent_locality_id=parent_locality,
            parent_channel=parent_channel if parent_locality else None,
            parent_activation_id=parent_activation,
            parent_weight=(
                parent_sources[parent_locality] / total_parent_weight
                if parent_locality and total_parent_weight > 0 else 1.0
            ),
            parent_weights=(
                {key: value / total_parent_weight for key, value in sorted(parent_sources.items())}
                if total_parent_weight > 0 else {}
            ),
            parent_activation_ids=parent_activation_ids,
            parent_unattributed_weight=(
                max(0.0, float(parent_unattributed_mass)) / total_parent_weight
                if total_parent_weight > 0 else 0.0
            ),
        )
        self.episodes.append(episode)
        self._by_id[activation_id] = episode
        self.current[(channel, locality_id)] = activation_id
        self.latest[(channel, locality_id)] = activation_id
        return episode

    def _close(self, channel: str, locality_id: str, time: float) -> None:
        activation_id = self.current.pop((channel, locality_id), None)
        if activation_id is None:
            return
        self._by_id[activation_id].activation_end_day = float(time)

    def _moved_formation_sources(self, before: dict, after: dict, locality_id: str) -> dict[str, float]:
        sources: dict[str, float] = {}
        for formation_id, new in after["formations"].items():
            old = before["formations"].get(formation_id)
            if old is None or not new["effective"] or new["locality"] != locality_id:
                continue
            if old["locality"] != locality_id:
                sources[old["locality"]] = sources.get(old["locality"], 0.0) + float(new["personnel"])
        return sources

    def _moved_member_sources(self, before: dict, after: dict, locality_id: str) -> dict[str, float]:
        sources: dict[str, float] = {}
        for person_id, new in after["persons"].items():
            old = before["persons"].get(person_id)
            if old is None or new["locality"] != locality_id or new["represented_armed"] <= 0:
                continue
            if old["locality"] != locality_id and old["represented_armed"] > 0:
                sources[old["locality"]] = (
                    sources.get(old["locality"], 0.0) + float(new["represented_armed"])
                )
        return sources

    def _stored_social_recruitment_sources(
        self,
        before: dict,
        after: dict,
        locality_id: str,
    ) -> tuple[dict[str, float], float, str]:
        """Recover recruitment origins from the exposure that actors actually used.

        The live recruitment decision reads the latest stored social exposure,
        which can have been generated several events earlier.  Contemporary
        graph paths are therefore not valid substitutes for provenance.  This
        observer accepts parentage only when every newly armed represented
        cohort in the activation has a mass-conserving, fully attributed stored
        exposure record.  Otherwise it deliberately leaves parentage unknown.
        """
        sources: dict[str, float] = {}
        total_gain = 0.0
        unattributed_gain = 0.0
        social_used_gain = 0.0
        for person_id, new in after["persons"].items():
            old = before["persons"].get(person_id)
            if old is None or new["locality"] != locality_id:
                continue
            armed_gain = float(new["represented_armed"]) - float(old["represented_armed"])
            if armed_gain <= 1e-12:
                continue
            total_gain += armed_gain
            organization_id = new.get("organization_id")
            if not organization_id:
                continue
            used_exposure = max(0.0, float(
                (old.get("social_exposure") or {}).get(
                    organization_id,
                    (old.get("social_exposure") or {}).get("insurgent", 0.0),
                )
            ))
            record = self.social_provenance.sources_for(person_id, organization_id)
            if used_exposure <= 1e-12:
                unattributed_gain += armed_gain
                continue
            social_used_gain += armed_gain
            if record is None or abs(record.exposure - used_exposure) > 1e-9:
                unattributed_gain += armed_gain
                continue
            for source_locality, exposure_mass in record.source_localities.items():
                sources[source_locality] = (
                    sources.get(source_locality, 0.0)
                    + armed_gain * exposure_mass / record.exposure
                )
            unattributed_gain += armed_gain * record.unattributed / record.exposure

        if total_gain <= 1e-12:
            return {}, 0.0, "none"
        if before["formation_mass"][locality_id] > 1e-12:
            if social_used_gain > 1e-12:
                return {}, total_gain, "competing_formation_access"
            return {}, total_gain, "formation_only"
        known_gain = sum(sources.values())
        residual = total_gain - known_gain - unattributed_gain
        if abs(residual) <= 1e-9:
            unattributed_gain += residual
        if known_gain > 1e-12:
            return (
                sources,
                max(0.0, unattributed_gain),
                "complete" if unattributed_gain <= 1e-9 else "partial",
            )
        return {}, total_gain, "incomplete"

    def _activation_attribution(
        self, channel: str, locality_id: str, before: dict, after: dict, event_type: str
    ) -> tuple[str, dict[str, float], str | None, float]:
        if channel == "fielded_force_viable":
            moved = self._moved_formation_sources(before, after, locality_id)
            if moved:
                return "formation_relocation", moved, "fielded_force_viable", 0.0
            new_formations = [
                formation_id for formation_id, row in after["formations"].items()
                if formation_id not in before["formations"] and row["locality"] == locality_id
                and row["effective"]
            ]
            if new_formations:
                # Local fielded force is generated from represented fighter
                # conversion/manpower accumulated by local armed membership.
                # The foothold channel is deliberately below the saturated
                # access threshold, so a force born around the 75 / .08 =
                # 937.5 represented-member point still has a causal parent.
                if after["states"]["member_foothold_present"][locality_id]:
                    return (
                        "local_member_to_force_generation",
                        {locality_id: max(after["member_mass"][locality_id], 1e-12)},
                        "member_foothold_present",
                        0.0,
                    )
                return "local_force_generation", {}, None, 0.0

        if channel == "member_access_saturated":
            if after["states"]["member_foothold_present"][locality_id]:
                return (
                    "member_foothold_maturation",
                    {locality_id: max(after["member_mass"][locality_id], 1e-12)},
                    "member_foothold_present",
                    0.0,
                )
            return event_type, {}, None, 0.0

        if channel == "member_foothold_present":
            moved = self._moved_member_sources(before, after, locality_id)
            if moved:
                return "armed_member_migration", moved, "member_foothold_present", 0.0
            social, social_unknown, provenance_status = self._stored_social_recruitment_sources(
                before, after, locality_id
            )
            if provenance_status in {"complete", "partial"}:
                return (
                    "stored_social_exposure_recruitment",
                    social,
                    "member_foothold_present",
                    social_unknown,
                )
            if provenance_status == "competing_formation_access":
                return (
                    "local_recruitment_competing_access",
                    {},
                    None,
                    social_unknown,
                )
            # A pre-existing fielded formation is itself a local access channel
            # in recruit_and_retain. If a locality with zero armed residents
            # gains its first member while a viable local formation was already
            # present, attribute that foothold to the fielded-force episode.
            if before["states"]["fielded_force_viable"][locality_id]:
                return (
                    "formation_seeded_local_recruitment",
                    {locality_id: max(before["formation_mass"][locality_id], 1e-12)},
                    "fielded_force_viable",
                    0.0,
                )
            if after["member_mass"][locality_id] > before["member_mass"][locality_id] + 1e-12:
                if provenance_status in {"incomplete", "formation_only"}:
                    return (
                        "local_recruitment_unattributed_provenance",
                        {},
                        None,
                        social_unknown,
                    )
                return "local_recruitment", {}, None, 0.0
        return event_type, {}, None, 0.0

    def observe_transition(
        self,
        before: dict,
        event_type: str,
        event_id: str | None,
        time: float,
    ) -> None:
        after = self.capture()
        for channel in self.CHANNELS:
            before_state = before["states"][channel]
            after_state = after["states"][channel]
            for locality_id in sorted(self.world.localities):
                was_active = bool(before_state[locality_id])
                is_active = bool(after_state[locality_id])
                if was_active and not is_active:
                    self._close(channel, locality_id, time)
                elif not was_active and is_active:
                    cause, sources, parent_channel, parent_unattributed_mass = self._activation_attribution(
                        channel, locality_id, before, after, event_type
                    )
                    self._open(
                        channel, locality_id, time, cause=cause,
                        event_type=event_type, event_id=event_id,
                        parent_sources=sources, parent_channel=parent_channel,
                        parent_unattributed_mass=parent_unattributed_mass,
                    )

    def finalize(self, observation_end_day: float) -> list[dict[str, Any]]:
        for activation_id in list(self.current.values()):
            episode = self._by_id[activation_id]
            episode.activation_end_day = float(observation_end_day)
            episode.censored = True
        self.current.clear()
        rows = []
        for episode in self.episodes:
            episode.observation_end_day = float(observation_end_day)
            rows.append(asdict(episode))
        return rows

    def parent_edges(self) -> list[dict[str, Any]]:
        """Return probability-mass-conserving child→candidate-parent edges."""
        edges: list[dict[str, Any]] = []
        for episode in self.episodes:
            weights = episode.parent_weights or {}
            activation_ids = episode.parent_activation_ids or {}
            if not weights:
                continue
            if abs(
                sum(weights.values()) + episode.parent_unattributed_weight - 1.0
            ) > 1e-9:
                raise AssertionError(
                    f"parent attribution mass does not conserve: {episode.activation_id}"
                )
            for locality_id, weight in sorted(weights.items()):
                edges.append({
                    "child_activation_id": episode.activation_id,
                    "child_locality_id": episode.locality_id,
                    "child_channel": episode.channel,
                    "parent_activation_id": activation_ids.get(locality_id),
                    "parent_locality_id": locality_id,
                    "parent_channel": episode.parent_channel,
                    "weight": float(weight),
                    "pathway": episode.cause,
                })
        return edges


def trace_simulation(config: SimulationConfig, *, until: float | None = None) -> dict[str, Any]:
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.initialize()
    tracer = LocalityActivationTracer(world)
    tracer.initialize(world.time)
    original_execute = simulation.processes.execute

    def traced_execute(event):
        before = tracer.capture()
        social_before = (
            tracer.social_provenance.capture()
            if event.event_type == "social_influence" else None
        )
        event_id = original_execute(event)
        if social_before is not None:
            tracer.social_provenance.observe_social_influence(
                social_before,
                event_id=event_id,
                time=world.time,
                elapsed_days=float(event.payload.get(
                    "elapsed_days",
                    event.payload.get("interval", world.config.intervals.social_influence),
                )),
            )
        tracer.observe_transition(before, event.event_type, event_id, world.time)
        return event_id

    simulation.processes.execute = traced_execute
    horizon = config.horizon_days if until is None else float(until)
    result = simulation.run(until=horizon)
    episodes = tracer.finalize(result.stopped_at)
    parent_edges = tracer.parent_edges()
    return {
        "schema_version": "1.5.0",
        "status": "observation_only_synthetic_activation_genealogy",
        "historical_outcomes_used": False,
        "dynamics_modified": False,
        "seed": config.seed,
        "horizon_days": result.stopped_at,
        "thresholds": {
            "member_foothold_present_represented_population": "> 1e-12",
            "member_access_saturated_represented_population":
                config.organization_ecology.minimum_proto_represented_population,
            "fielded_force_viable_personnel":
                config.organization_ecology.minimum_formation_personnel,
        },
        "episodes": episodes,
        "parent_edges": parent_edges,
        "social_exposure_provenance": {
            "records_observed": len(tracer.social_provenance.history),
            "current_mass_balance": tracer.social_provenance.mass_balance(),
            "fully_attributed_records": sum(
                record.unattributed <= 1e-9
                for record in tracer.social_provenance.history
            ),
            "unattributed_records": sum(
                record.unattributed > 1e-9
                for record in tracer.social_provenance.history
            ),
        },
        "parent_edge_weight_sums": {
            activation_id: sum(
                edge["weight"] for edge in parent_edges
                if edge["child_activation_id"] == activation_id
            )
            for activation_id in sorted({edge["child_activation_id"] for edge in parent_edges})
        },
        "parentage_coverage": {
            "root_initial_condition_episodes": sum(
                row["cause"] == "initial_condition" for row in episodes
            ),
            "nonroot_episodes": sum(
                row["cause"] != "initial_condition" for row in episodes
            ),
            "parented_nonroot_episodes": sum(
                row["cause"] != "initial_condition" and
                any(edge["child_activation_id"] == row["activation_id"]
                    and edge.get("parent_activation_id")
                    for edge in parent_edges)
                for row in episodes
            ),
            "classified_nonroot_episodes": sum(
                row["cause"] != "initial_condition"
                and row["parentage_class"] in PARENTAGE_CLASSES
                for row in episodes
            ),
            "unresolved_nonroot_episodes": sum(
                row["cause"] != "initial_condition"
                and row["parentage_class"] == "unresolved"
                for row in episodes
            ),
        },
        "episode_counts": {
            channel: sum(row["channel"] == channel for row in episodes)
            for channel in LocalityActivationTracer.CHANNELS
        },
        "cause_counts": {
            cause: sum(row["cause"] == cause for row in episodes)
            for cause in sorted({row["cause"] for row in episodes})
        },
        "parentage_class_counts": {
            parentage: sum(
                row["parentage_class"] == parentage for row in episodes
            )
            for parentage in PARENTAGE_CLASSES
        },
        "parentage_ontology": list(PARENTAGE_CLASSES),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=800)
    parser.add_argument("--localities", type=int, default=34)
    parser.add_argument("--days", type=float, default=90.0)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    config = SimulationConfig(
        agent_count=args.agents,
        locality_count=args.localities,
        horizon_days=args.days,
        seed=args.seed,
        output_mode="ensemble",
    )
    report = trace_simulation(config, until=args.days)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = build_run_manifest(
        config,
        seeds=[args.seed],
        execution_mode="observation_only_activation_genealogy",
        output_schema={"name": "locality_activation_genealogy", "version": "1.0.0"},
        repo_root=ROOT,
        extra={
            "stage": "synthetic_locality_activation_genealogy",
            "historical_outcomes_used": False,
            "dynamics_modified": False,
            "artifacts": {
                output.relative_to(ROOT).as_posix(): file_sha256(output),
            },
        },
    )
    audit = audit_run_manifest(manifest)
    if not audit["valid"]:
        raise RuntimeError(f"genealogy manifest failed reproducibility contract: {audit}")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "episode_counts": report["episode_counts"],
        "cause_counts": report["cause_counts"],
        "episodes": len(report["episodes"]),
        "output": str(output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
