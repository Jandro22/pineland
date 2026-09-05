"""Observation-only provenance for franchise-specific social exposure.

The live social process stores only the latest scalar exposure on each person.
That is sufficient for actor decisions, but not for later causal attribution:
the source locality that generated an exposure is lost when the next social
tick overwrites ``Person.social_exposure``.  This module reconstructs that
provenance outside actor state and outside the transition RNG stream.

The reconstruction mirrors the live social-influence ordering.  A neighbor
whose person id sorts before the current target has already completed the live
tick, while a later-sorting neighbor is still in its pre-tick state.  That
detail matters because public behavior and franchise affinity can change within
one social-influence event.  Provenance is carried through an unarmed
sympathizer only when that sympathizer's franchise affinity itself has observed
provenance.  Missing provenance is retained as unattributed mass; it is never
replaced by a guessed source locality.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.networks import edge_between  # noqa: E402


OUT = ROOT / "studies" / "research_program" / "social_exposure_provenance.json"


_BEHAVIOR_INSURGENT_SIGNAL = {
    "government_cooperation": 0.0,
    "party_participation": 0.0,
    "civil_society": 0.0,
    "protest": 0.1,
    "insurgent_sympathy": 0.7,
    "armed_participation": 1.0,
    "inactive": 0.0,
    "migration": 0.0,
    "neutral": 0.0,
}


@dataclass(frozen=True)
class ExposureProvenance:
    """Mass decomposition for one stored franchise-specific exposure value."""

    person_id: str
    organization_id: str
    exposure: float
    source_localities: dict[str, float]
    unattributed: float
    event_id: str | None
    time: float
    tick_index: int

    @property
    def attributed(self) -> float:
        return sum(self.source_localities.values())

    @property
    def coverage(self) -> float:
        if self.exposure <= 1e-15:
            return 1.0
        return self.attributed / self.exposure

    def validate(self, tolerance: float = 1e-9) -> None:
        if self.exposure < -tolerance or self.unattributed < -tolerance:
            raise AssertionError("negative social-exposure provenance mass")
        if any(value < -tolerance for value in self.source_localities.values()):
            raise AssertionError("negative source-locality provenance mass")
        accounted = self.attributed + self.unattributed
        if abs(accounted - self.exposure) > tolerance:
            raise AssertionError(
                f"social-exposure provenance mass mismatch for {self.person_id}/"
                f"{self.organization_id}: {accounted} != {self.exposure}"
            )


@dataclass(frozen=True)
class _OriginShares:
    source_localities: dict[str, float]
    unattributed: float

    def validate(self, tolerance: float = 1e-9) -> None:
        total = sum(self.source_localities.values()) + self.unattributed
        if abs(total - 1.0) > tolerance:
            raise AssertionError(f"origin shares do not conserve mass: {total}")


class SocialExposureProvenanceTracer:
    """Reconstruct and retain social-exposure origins without mutating ``world``."""

    def __init__(self, world, *, tolerance: float = 1e-9) -> None:
        self.world = world
        self.tolerance = float(tolerance)
        self.current: dict[tuple[str, str], ExposureProvenance] = {}
        self._affinity_origins: dict[tuple[str, str], _OriginShares] = {}
        self._affinity_values: dict[tuple[str, str], float] = {}
        self._person_organizations: dict[str, str | None] = {}
        self.history: list[ExposureProvenance] = []
        self.tick_index = 0

    def capture(self) -> dict[str, Any]:
        active_insurgents = tuple(sorted(
            organization.organization_id
            for organization in self.world.organizations.values()
            if organization.kind is OrganizationKind.INSURGENT
            and organization.status == "active"
        ))
        return {
            "active_insurgent_ids": active_insurgents,
            "persons": {
                person.person_id: {
                    "locality": person.residence_locality_id,
                    "organization_id": person.organization_id,
                    "armed_fraction": float(person.armed_fraction),
                    "public_behavior": person.public_behavior,
                    "insurgent_affinity": dict(person.insurgent_affinity),
                    "social_exposure": dict(person.social_exposure),
                }
                for person in self.world.persons.values()
            },
        }

    def sources_for(self, person_id: str, organization_id: str) -> ExposureProvenance | None:
        return self.current.get((person_id, organization_id))

    def _origin_for_neighbor(
        self,
        neighbor_id: str,
        organization_id: str,
        *,
        target_id: str,
        prior_affinity_origins: dict[tuple[str, str], _OriginShares],
        current_affinity_origins: dict[tuple[str, str], _OriginShares],
    ) -> _OriginShares:
        # The live loop processes sorted person ids. Earlier neighbors have
        # already completed this tick, while later neighbors still carry the
        # prior tick's affinity state.
        table = (
            current_affinity_origins
            if neighbor_id < target_id else prior_affinity_origins
        )
        origin = table.get((neighbor_id, organization_id))
        if origin is None:
            return _OriginShares({}, 1.0)
        origin.validate(self.tolerance)
        return origin

    @staticmethod
    def _add_origin_mass(
        source_mass: dict[str, float],
        origin: _OriginShares,
        contribution: float,
    ) -> float:
        if contribution <= 0:
            return 0.0
        for locality_id, share in origin.source_localities.items():
            source_mass[locality_id] = source_mass.get(locality_id, 0.0) + contribution * share
        return contribution * origin.unattributed

    def _record(
        self,
        *,
        person_id: str,
        organization_id: str,
        exposure: float,
        source_mass: dict[str, float],
        unattributed: float,
        event_id: str | None,
        time: float,
    ) -> ExposureProvenance | None:
        key = (person_id, organization_id)
        if exposure <= self.tolerance:
            self.current.pop(key, None)
            return None
        # Floating arithmetic in the mirrored normalization can leave a tiny
        # signed residual. Assign only that residual to the unknown bucket;
        # never manufacture a source locality to close the ledger.
        residual = exposure - (sum(source_mass.values()) + unattributed)
        if abs(residual) <= self.tolerance:
            unattributed += residual
        record = ExposureProvenance(
            person_id=person_id,
            organization_id=organization_id,
            exposure=float(exposure),
            source_localities={
                locality_id: float(value)
                for locality_id, value in sorted(source_mass.items())
                if value > self.tolerance
            },
            unattributed=max(0.0, float(unattributed)),
            event_id=event_id,
            time=float(time),
            tick_index=self.tick_index,
        )
        record.validate(self.tolerance * 10)
        self.current[key] = record
        self.history.append(record)
        return record

    @staticmethod
    def _conditional_origin(record: ExposureProvenance | None) -> _OriginShares:
        if record is None or record.exposure <= 1e-15:
            return _OriginShares({}, 1.0)
        return _OriginShares(
            {
                locality_id: value / record.exposure
                for locality_id, value in record.source_localities.items()
            },
            record.unattributed / record.exposure,
        )

    def observe_social_influence(
        self,
        before: dict[str, Any],
        *,
        event_id: str | None,
        time: float,
        elapsed_days: float | None = None,
    ) -> list[ExposureProvenance]:
        """Observe a completed live social tick and reconstruct its provenance.

        ``before`` must come from :meth:`capture` immediately before the live
        ``social_influence`` handler.  The method reads the completed world but
        never mutates it and never touches an RNG.
        """
        if elapsed_days is not None and float(elapsed_days) <= 0.0:
            # The live handler returns before touching social_exposure on its
            # zero-duration scheduler initialization event. Provenance must do
            # the same rather than inventing a social tick that never occurred.
            return []
        after = self.capture()
        active_ids = tuple(before.get("active_insurgent_ids", ()))
        if active_ids != tuple(after.get("active_insurgent_ids", ())):
            raise AssertionError("active insurgent set changed inside social_influence")

        self.tick_index += 1
        # Reconcile provenance against the actual pre-tick affinity state.
        # Recruitment/ecology can legally alter affiliation between social
        # ticks. If a value or membership changed outside this observer, the
        # old origin is no longer identified and is replaced by unknown mass.
        prior_affinity_origins: dict[tuple[str, str], _OriginShares] = {}
        for person_id, row in before["persons"].items():
            organization_unchanged = (
                person_id in self._person_organizations
                and self._person_organizations[person_id] == row.get("organization_id")
            )
            for organization_id, value in row["insurgent_affinity"].items():
                value = float(value)
                if organization_id not in active_ids or value <= 0:
                    continue
                key = (person_id, organization_id)
                previous_value = self._affinity_values.get(key)
                if (
                    organization_unchanged
                    and previous_value is not None
                    and abs(previous_value - value) <= self.tolerance * 10
                    and key in self._affinity_origins
                ):
                    prior_affinity_origins[key] = self._affinity_origins[key]
                else:
                    prior_affinity_origins[key] = _OriginShares({}, 1.0)
        current_affinity_origins: dict[tuple[str, str], _OriginShares] = {}
        tick_records: list[ExposureProvenance] = []

        for person_id in sorted(before["persons"]):
            before_person = before["persons"][person_id]
            after_person = after["persons"][person_id]
            total_weight = 0.0
            org_source_mass = {organization_id: {} for organization_id in active_ids}
            org_unknown_mass = {organization_id: 0.0 for organization_id in active_ids}
            org_numerator = {organization_id: 0.0 for organization_id in active_ids}
            generic_source_mass: dict[str, float] = {}
            generic_unknown_mass = 0.0
            generic_numerator = 0.0

            for neighbor_id in self.world.social_neighbors.get(person_id, ()):
                neighbor = (
                    after["persons"][neighbor_id]
                    if neighbor_id < person_id else before["persons"][neighbor_id]
                )
                edge = edge_between(self.world, person_id, neighbor_id)
                influence = max(
                    0.0,
                    float(edge.weight * edge.trust * edge.represented_relationships),
                )
                total_weight += influence
                if influence <= 0 or not active_ids:
                    continue

                behavior_signal = max(
                    0.0,
                    float(_BEHAVIOR_INSURGENT_SIGNAL.get(neighbor["public_behavior"], 0.0)),
                )
                neighbor_org = self.world.organizations.get(neighbor.get("organization_id") or "")
                is_active_member = (
                    neighbor_org is not None
                    and neighbor_org.kind is OrganizationKind.INSURGENT
                    and neighbor_org.status == "active"
                )
                if is_active_member:
                    generic_signal = max(0.0, float(neighbor["armed_fraction"]))
                    contribution = influence * generic_signal
                    generic_numerator += contribution
                    generic_source_mass[neighbor["locality"]] = (
                        generic_source_mass.get(neighbor["locality"], 0.0) + contribution
                    )
                    organization_id = neighbor_org.organization_id
                    if organization_id in org_numerator:
                        org_numerator[organization_id] += contribution
                        org_source_mass[organization_id][neighbor["locality"]] = (
                            org_source_mass[organization_id].get(neighbor["locality"], 0.0)
                            + contribution
                        )
                    continue

                generic_signal = behavior_signal
                generic_contribution = influence * generic_signal
                generic_numerator += generic_contribution
                if generic_contribution > 0:
                    # With one active franchise the live process maps generic
                    # sympathy to that franchise. Preserve a known prior origin
                    # when one exists; otherwise the causal mass remains unknown.
                    if len(active_ids) == 1:
                        sole = active_ids[0]
                        origin = self._origin_for_neighbor(
                            neighbor_id,
                            sole,
                            target_id=person_id,
                            prior_affinity_origins=prior_affinity_origins,
                            current_affinity_origins=current_affinity_origins,
                        )
                        generic_unknown_mass += self._add_origin_mass(
                            generic_source_mass, origin, generic_contribution
                        )
                    else:
                        generic_unknown_mass += generic_contribution

                if generic_signal <= 0:
                    continue
                active_affinity = {
                    organization_id: max(0.0, float(value))
                    for organization_id, value in neighbor["insurgent_affinity"].items()
                    if organization_id in org_numerator and float(value) > 0
                }
                affinity_total = sum(active_affinity.values())
                if affinity_total <= 0:
                    continue
                for organization_id, affinity in active_affinity.items():
                    contribution = influence * generic_signal * affinity / affinity_total
                    org_numerator[organization_id] += contribution
                    origin = self._origin_for_neighbor(
                        neighbor_id,
                        organization_id,
                        target_id=person_id,
                        prior_affinity_origins=prior_affinity_origins,
                        current_affinity_origins=current_affinity_origins,
                    )
                    org_unknown_mass[organization_id] += self._add_origin_mass(
                        org_source_mass[organization_id], origin, contribution
                    )

            if total_weight > 0:
                for organization_id in active_ids:
                    org_numerator[organization_id] /= total_weight
                    org_source_mass[organization_id] = {
                        locality_id: value / total_weight
                        for locality_id, value in org_source_mass[organization_id].items()
                    }
                    org_unknown_mass[organization_id] /= total_weight
                generic_numerator /= total_weight
                generic_source_mass = {
                    locality_id: value / total_weight
                    for locality_id, value in generic_source_mass.items()
                }
                generic_unknown_mass /= total_weight

            if len(active_ids) == 1:
                sole = active_ids[0]
                org_numerator[sole] = generic_numerator
                org_source_mass[sole] = dict(generic_source_mass)
                org_unknown_mass[sole] = generic_unknown_mass

            records_by_org: dict[str, ExposureProvenance | None] = {}
            for organization_id in active_ids:
                observed = max(
                    0.0,
                    float(after_person["social_exposure"].get(organization_id, 0.0)),
                )
                expected = max(0.0, min(1.0, org_numerator[organization_id]))
                if abs(observed - expected) > self.tolerance * 10:
                    raise AssertionError(
                        f"social provenance reconstruction diverged for {person_id}/"
                        f"{organization_id}: expected {expected}, observed {observed}"
                    )
                record = self._record(
                    person_id=person_id,
                    organization_id=organization_id,
                    exposure=observed,
                    source_mass=org_source_mass[organization_id],
                    unattributed=org_unknown_mass[organization_id],
                    event_id=event_id,
                    time=time,
                )
                records_by_org[organization_id] = record
                if record is not None:
                    tick_records.append(record)

            # Mirror only the provenance semantics of the live affinity update.
            # If this tick supplied franchise signal, the final unarmed
            # sympathizer affinity is sourced by the same incoming exposure.
            # Otherwise preserve prior origin only when the affinity persisted;
            # unknown prior affinity remains explicitly unknown.
            final_affinity = after_person["insurgent_affinity"]
            final_behavior = after_person["public_behavior"]
            is_unarmed_nonmember = after_person.get("organization_id") is None
            if is_unarmed_nonmember and final_affinity:
                incoming_total = sum(org_numerator.values())
                for organization_id, affinity in final_affinity.items():
                    if organization_id not in active_ids or float(affinity) <= 0:
                        continue
                    record = records_by_org.get(organization_id)
                    if (
                        final_behavior in {"insurgent_sympathy", "armed_participation"}
                        and incoming_total > self.tolerance
                        and record is not None
                    ):
                        origin = self._conditional_origin(record)
                    else:
                        origin = prior_affinity_origins.get(
                            (person_id, organization_id), _OriginShares({}, 1.0)
                        )
                    origin.validate(self.tolerance * 10)
                    current_affinity_origins[(person_id, organization_id)] = origin

        self._affinity_origins = current_affinity_origins
        self._affinity_values = {
            (person_id, organization_id): float(value)
            for person_id, row in after["persons"].items()
            for organization_id, value in row["insurgent_affinity"].items()
            if organization_id in active_ids and float(value) > 0
        }
        self._person_organizations = {
            person_id: row.get("organization_id")
            for person_id, row in after["persons"].items()
        }
        for key in list(self.current):
            if key[1] not in active_ids:
                self.current.pop(key, None)
        return tick_records

    def mass_balance(self) -> dict[str, float]:
        records = list(self.current.values())
        exposure = sum(record.exposure for record in records)
        attributed = sum(record.attributed for record in records)
        unattributed = sum(record.unattributed for record in records)
        return {
            "exposure": exposure,
            "attributed": attributed,
            "unattributed": unattributed,
            "error": exposure - attributed - unattributed,
        }

    def history_rows(self) -> list[dict[str, Any]]:
        return [asdict(record) | {"coverage": record.coverage} for record in self.history]


def trace_social_exposure_provenance(
    config: SimulationConfig,
    *,
    until: float | None = None,
) -> dict[str, Any]:
    """Run the live synthetic model with provenance attached as a pure observer."""
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.initialize()
    tracer = SocialExposureProvenanceTracer(world)
    original_execute = simulation.processes.execute

    def traced_execute(event):
        before = tracer.capture() if event.event_type == "social_influence" else None
        event_id = original_execute(event)
        if before is not None:
            tracer.observe_social_influence(
                before,
                event_id=event_id,
                time=world.time,
                elapsed_days=float(event.payload.get(
                    "elapsed_days",
                    event.payload.get("interval", world.config.intervals.social_influence),
                )),
            )
        return event_id

    simulation.processes.execute = traced_execute
    horizon = config.horizon_days if until is None else float(until)
    result = simulation.run(until=horizon)
    history = tracer.history_rows()
    total_exposure = sum(float(row["exposure"]) for row in history)
    attributed = sum(sum(row["source_localities"].values()) for row in history)
    unattributed = sum(float(row["unattributed"]) for row in history)
    return {
        "schema_version": "1.0.0",
        "status": "observation_only_social_exposure_provenance",
        "historical_outcomes_used": False,
        "dynamics_modified": False,
        "seed": config.seed,
        "horizon_days": result.stopped_at,
        "records": history,
        "history_mass_balance": {
            "exposure": total_exposure,
            "attributed": attributed,
            "unattributed": unattributed,
            "error": total_exposure - attributed - unattributed,
        },
        "current_mass_balance": tracer.mass_balance(),
        "fully_attributed_records": sum(row["unattributed"] <= 1e-9 for row in history),
        "partially_or_unattributed_records": sum(row["unattributed"] > 1e-9 for row in history),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace synthetic franchise-specific social-exposure source localities."
    )
    parser.add_argument("--agents", type=int, default=300)
    parser.add_argument("--localities", type=int, default=24)
    parser.add_argument("--days", type=float, default=14.0)
    parser.add_argument("--seed", type=int, default=2026090507)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = trace_social_exposure_provenance(
        SimulationConfig(
            agent_count=args.agents,
            locality_count=args.localities,
            horizon_days=args.days,
            seed=args.seed,
            output_mode="ensemble",
        ),
        until=args.days,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "records": len(report["records"]),
        "history_mass_balance": report["history_mass_balance"],
    }, indent=2))


if __name__ == "__main__":
    main()

