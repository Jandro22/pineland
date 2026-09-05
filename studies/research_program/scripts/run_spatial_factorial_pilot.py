"""Run the preregistered synthetic spatial factorial in bounded pilot mode.

This runner is deliberately study-layer code.  It does not edit model source,
fit historical outcomes, or silently replace the active core certificate.  The
default invocation runs one matched seed for 14 days in each of the four cells;
``--full`` is explicit and uses the contract's eight seeds and 90-day horizon.
Every cell records the live model hash and the runner fails closed if the hash
changes during execution.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from math import exp
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.historical import morans_i  # noqa: E402
from pineland_sim.logistics import (  # noqa: E402
    _local_armed_footholds,
    _shortest_locality_route_metrics,
    create_movement_order,
    reallocation_decision_probability,
    reallocation_destination_score,
)
from pineland_sim.physical import record_presence_exposure  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    audit_run_manifest,
    build_run_manifest,
    certified_core_status,
    file_sha256,
    model_sha256,
    repository_state,
)

CONTRACT_PATH = ROOT / "studies" / "research_program" / "spatial_factorial_experiment_contract.json"
CHALLENGE_CONTRACT_PATH = ROOT / "studies" / "research_program" / "spatial_factorial_contact_challenge_contract.json"


def _load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> None:
    design = contract.get("design", {})
    factors = design.get("factors", {})
    expected = {
        "presence_memory": ["government_patrol_only", "symmetric_stationary_formation_memory"],
        "destination_choice": ["current_live_policy", "geographic_neighbor_restricted"],
    }
    if contract.get("historical_outcomes_used") or contract.get("historical_parameter_fitting"):
        raise ValueError("factorial runner is synthetic-only; historical fitting is forbidden")
    if contract.get("core_change_licensed"):
        raise ValueError("factorial contract cannot license a core change")
    if factors != expected or design.get("cells") != 4:
        raise ValueError("factor levels do not match the preregistered four-cell design")
    if not design.get("matched_seed_assignment"):
        raise ValueError("matched seeds are required")
    if len(design.get("seeds", [])) != 8:
        raise ValueError("the full design must retain eight preregistered seeds")


class FactorialProcessEngine(ProcessEngine):
    """Process adapter for the two study-layer treatment factors."""

    def __init__(self, world, *, symmetric_memory: bool, neighbor_restricted: bool) -> None:
        super().__init__(world)
        self.symmetric_memory = symmetric_memory
        self.neighbor_restricted = neighbor_restricted
        self._formation_presence_accounted_at: dict[str, float] = {}

    def _advance_symmetric_formation_memory(self, time: float) -> None:
        cfg = self.world.config.physical
        for formation_id, formation in sorted(self.world.formations.items()):
            previous = self._formation_presence_accounted_at.get(formation_id, float(time))
            active = (
                formation.personnel > 0 and not formation.moving and
                not formation.outside_pineland and
                formation.operational_status == "effective" and
                formation.current_microzone_id in self.world.microzones and
                formation.locality_id in self.world.localities
            )
            if active:
                duration = max(0.0, float(time) - previous)
                locality = self.world.localities[formation.locality_id]
                organization = self.world.organizations.get(formation.organization_id)
                if duration > 0 and organization is not None:
                    actor = (
                        "insurgent" if organization.kind is OrganizationKind.INSURGENT
                        else "government"
                    )
                    target = (
                        cfg.formation_presence_gain * formation.effective_strength() /
                        max(250.0, locality.population * .002)
                    )
                    record_presence_exposure(
                        self.world, formation.current_microzone_id, actor,
                        target, duration, float(time),
                    )
            # Inactive or moving formations do not accrue hidden dwell time.
            self._formation_presence_accounted_at[formation_id] = float(time)

    def execute(self, event):
        if self.symmetric_memory:
            # The live engine still invokes patrol-memory accounting.  The
            # treatment sets patrol_memory_gain=0, so this adapter adds only
            # the preregistered stationary-formation channel.
            self._advance_symmetric_formation_memory(self.world.time)
        return super().execute(event)

    def _choose_neighbor_orders(self, time: float, interval_days: float) -> list:
        world = self.world
        orders = []
        maximum_population = max(locality.population for locality in world.localities.values())
        foothold_cache: dict[str, dict[str, float]] = {}
        decision_probability = reallocation_decision_probability(
            world.config.logistics.reallocation_rate, interval_days
        )
        for formation in sorted(world.formations.values(), key=lambda item: item.formation_id):
            if (
                formation.moving or formation.outside_pineland or formation.personnel <= 0 or
                formation.operational_status != "effective" or formation.deployable_personnel() <= 0 or
                any(order.formation_id == formation.formation_id and
                    order.status in {"pending", "moving"}
                    for order in world.movement_orders.values())
            ):
                continue
            if self.rng.random() >= decision_probability:
                continue
            route_metrics = _shortest_locality_route_metrics(
                world, formation.locality_id, formation.mobility
            )
            candidates: list[str] = []
            utilities: list[float] = []
            if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT:
                foothold_cache.setdefault(
                    formation.organization_id,
                    _local_armed_footholds(world, formation.organization_id),
                )
            moving_personnel = formation.personnel * formation.availability
            allowed = {formation.locality_id, *world.adjacency.get(formation.locality_id, {})}
            for locality_id in sorted(allowed):
                route, distance_km, travel_hours = route_metrics[locality_id]
                movement_cost = (
                    moving_personnel * distance_km *
                    world.config.logistics.movement_consumption_per_person_km
                )
                if locality_id != formation.locality_id and movement_cost > formation.supply_stock + 1e-12:
                    continue
                components = reallocation_destination_score(
                    world, formation, locality_id,
                    travel_hours=travel_hours,
                    maximum_population=maximum_population,
                    footholds=foothold_cache.get(formation.organization_id),
                    route=route,
                )
                candidates.append(locality_id)
                utilities.append(exp(max(-8, min(8, components["utility"]))))
            if not candidates:
                continue
            destination = self.rng.choices(candidates, weights=utilities, k=1)[0]
            if destination != formation.locality_id:
                orders.append(create_movement_order(
                    world, formation.formation_id, destination, time, self.rng,
                    purpose="reallocation",
                ))
        return orders

    def on_command(self, event_id: str, event) -> dict[str, Any]:
        if not self.neighbor_restricted:
            return super().on_command(event_id, event)
        orders = self._choose_neighbor_orders(
            self.world.time,
            float(event.payload.get("interval", self.world.config.intervals.command)),
        )
        return {
            "orders_issued": len(orders),
            "orders_failed": sum(order.status == "failed_command" for order in orders),
            "affected_entity_ids": tuple(order.order_id for order in orders),
        }


class FactorialSimulation(Simulation):
    """Simulation wrapper for the declared challenge observation condition."""

    def __init__(self, world, *, force_detection: bool = False) -> None:
        super().__init__(world)
        self.force_detection = force_detection

    def _schedule_contacts(self, *args, **kwargs) -> None:
        super()._schedule_contacts(*args, **kwargs)
        if not self.force_detection:
            return
        # The challenge contract explicitly conditions on focal detection so
        # the contact/presence pathway—not the detection operator—is exercised.
        for event in self.scheduler._queue:
            if event.event_type == "contact":
                event.payload["force_detection"] = True


def _prepare_contact_challenge(world) -> None:
    """Apply only the focal-pair fixture declared by the challenge contract."""
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    for formation in (government, insurgent):
        formation.availability = 1.0
        formation.readiness = 1.0
        formation.command = 1.0
        formation.cohesion = 1.0
        formation.quality = 1.0
        formation.information = 1.0
        formation.fatigue = 0.0
        formation.supply_stock = formation.supply_capacity
        formation.moving = False
        formation.outside_pineland = False
        formation.operational_status = "effective"
    world.organizations["insurgent"].status = "active"
    world.initial_supply_stock = (
        sum(source.stock for source in world.supply_sources.values()) +
        sum(formation.supply_stock for formation in world.formations.values()) +
        world.demobilized_arms +
        sum(
            shipment.quantity_deliverable
            for shipment in world.supply_shipments.values()
            if shipment.status == "in_transit"
        )
    )


def _active_localities(world) -> set[str]:
    active_orgs = {
        organization.organization_id
        for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    }
    return {
        formation.locality_id
        for formation in world.formations.values()
        if formation.organization_id in active_orgs and formation.personnel > 0 and
        formation.operational_status == "effective" and not formation.moving and
        not formation.outside_pineland
    }


def _cell_metrics(world, daily_active: list[dict[str, Any]]) -> dict[str, Any]:
    active_sets = [set(row["active_localities"]) for row in daily_active]
    renewal = {}
    for window in (7, 28):
        eligible = continued = 0
        for index in range(len(active_sets) - window):
            eligible += len(active_sets[index])
            continued += len(active_sets[index] & active_sets[index + window])
        renewal[f"same_locality_renewal_rate_{window}d"] = (
            continued / eligible if eligible else None
        )
    if active_sets:
        final = active_sets[-1]
        values = {locality_id: float(locality_id in final) for locality_id in world.localities}
        moran = morans_i(values, world.adjacency)
    else:
        final = set()
        moran = None
    adjacent = 0
    opportunities = 0
    for before, after in zip(active_sets, active_sets[1:]):
        for locality_id in world.localities:
            if locality_id in before or locality_id in after:
                continue
            opportunities += 1
            if any(neighbor in before for neighbor in world.adjacency.get(locality_id, {})) and locality_id in after:
                adjacent += 1
    summary = world.summary()
    presence_memory = {
        actor: sum(zone.presence_memory.get(actor, 0.0) for zone in world.microzones.values())
        for actor in ("government", "insurgent")
    }
    return {
        **renewal,
        "active_locality_count_final": len(final),
        "daily_active_locality_mean": (
            sum(len(item) for item in active_sets) / len(active_sets) if active_sets else 0.0
        ),
        "adjacent_activation_rate": adjacent / opportunities if opportunities else None,
        "morans_i_final": moran,
        "movement_count": len(world.movement_orders),
        "event_counts": dict(world.event_counts),
        "fielded_insurgent_personnel": summary["active_insurgent_formation_personnel"],
        "mobilized_insurgent_population": summary["mobilized_insurgent_represented_population"],
        "supply_conservation_residual": world.supply_conservation_residual(),
        "contact_count": len(world.contact_event_times),
        "latent_contact_count": len(world.contact_event_times),
        "contact_funnel_failure_reasons": dict(Counter(
            record.get("failure_reason", "unknown")
            for record in world.contact_funnel_records
        )),
        "contact_funnel_records": len(world.contact_funnel_records),
        "presence_memory_total_by_actor": presence_memory,
        "daily_active_localities": daily_active,
    }


def run_cell(*, contract: dict[str, Any], seed: int, presence_memory: str,
             destination_choice: str, horizon_days: float, agent_count: int,
             locality_count: int, challenge: bool = False) -> dict[str, Any]:
    model_before = model_sha256(ROOT)
    config = SimulationConfig(
        seed=seed,
        horizon_days=horizon_days,
        agent_count=agent_count,
        locality_count=locality_count,
        output_mode="ensemble",
        # Keep the base world-generation streams aligned with the simulator's
        # documented synthetic baseline; matched cells differ only through
        # the declared study-layer factors.
        random_stream_namespace="baseline",
    )
    if challenge:
        config.organization_ecology.enabled = False
        config.contact_rate = 5.0
        config.combat.contact_supply_rule = "no_gate"
        config.information.contact_true_positive_rate = 1.0
    if presence_memory == "symmetric_stationary_formation_memory":
        # The adapter supplies the formation channel; zero prevents the live
        # patrol-only channel from being counted twice in the treatment cell.
        config.physical.patrol_memory_gain = 0.0
    world = generate_pineland(config)
    if challenge:
        _prepare_contact_challenge(world)
    simulation = FactorialSimulation(world, force_detection=challenge)
    simulation.processes = FactorialProcessEngine(
        world,
        symmetric_memory=presence_memory == "symmetric_stationary_formation_memory",
        neighbor_restricted=destination_choice == "geographic_neighbor_restricted",
    )
    daily_active: list[dict[str, Any]] = []
    for day in range(1, int(horizon_days) + 1):
        simulation.run(until=float(day))
        daily_active.append({"day": day, "active_localities": sorted(_active_localities(world))})
    model_after = model_sha256(ROOT)
    if model_before != model_after:
        raise RuntimeError("model source changed during factorial cell; cell rejected")
    metrics = _cell_metrics(world, daily_active)
    script_hash = file_sha256(Path(__file__))
    manifest = build_run_manifest(
        config,
        seeds=[seed],
        execution_mode={"kind": "synthetic_spatial_factorial", "status": "pilot_or_full"},
        output_schema={"name": "spatial_factorial_cell", "version": "1.0.0"},
        repo_root=ROOT,
        extra={
            "experiment_id": contract["experiment_id"],
            "presence_memory": presence_memory,
            "destination_choice": destination_choice,
            "script_sha256": script_hash,
            "model_sha256_start": model_before,
            "model_sha256_end": model_after,
            "historical_outcomes_used": False,
            "historical_parameter_fitting": False,
            "core_change_licensed": False,
        },
    )
    manifest_audit = audit_run_manifest(manifest)
    return {
        "seed": seed,
        "presence_memory": presence_memory,
        "destination_choice": destination_choice,
        "horizon_days": horizon_days,
        "agent_count": agent_count,
        "locality_count": locality_count,
        "challenge": challenge,
        "contact_rate": config.contact_rate,
        "metrics": metrics,
        "manifest": manifest,
        "manifest_audit": manifest_audit,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full", action="store_true", help="run all eight seeds for 90 days")
    parser.add_argument("--challenge", action="store_true", help="use the preregistered contact challenge contract")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--days", type=float, default=None)
    parser.add_argument("--agents", type=int, default=None)
    parser.add_argument("--localities", type=int, default=None)
    args = parser.parse_args()
    contract_path = CHALLENGE_CONTRACT_PATH if args.challenge else CONTRACT_PATH
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    validate_contract(contract)
    if args.full:
        certificate_status = certified_core_status(ROOT)
        if not certificate_status["passed"]:
            raise SystemExit(
                "refusing full factorial ensemble: active core certificate does not "
                f"match live source ({certificate_status['reason']}; "
                f"expected={certificate_status.get('expected_model_sha256')}, "
                f"live={certificate_status.get('live_model_sha256')})"
            )
    if args.full:
        seeds = [int(seed) for seed in contract["design"]["seeds"]]
        horizon = float(contract["design"]["horizon_days"])
        agents = int(contract["design"]["agent_count"])
        localities = int(contract["design"]["locality_count"])
    else:
        seeds = [args.seed if args.seed is not None else (8811 if args.challenge else 20260904)]
        horizon = args.days if args.days is not None else 14.0
        agents = args.agents if args.agents is not None else int(contract["design"]["agent_count"])
        localities = args.localities if args.localities is not None else int(contract["design"]["locality_count"])
    cells = [
        (memory, destination)
        for memory in contract["design"]["factors"]["presence_memory"]
        for destination in contract["design"]["factors"]["destination_choice"]
    ]
    before = repository_state(ROOT)
    result = {
        "schema_version": "1.0.0",
        "experiment_id": contract["experiment_id"],
        "status": (
            "contact_challenge_pilot_synthetic_only" if args.challenge and not args.full else
            "contact_challenge_full_synthetic_only" if args.challenge else
            "pilot_synthetic_only" if not args.full else "full_synthetic_only"
        ),
        "challenge": args.challenge,
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "contract_sha256": file_sha256(contract_path),
        "repository_before": before,
        "cells": [],
    }
    for seed in seeds:
        for memory, destination in cells:
            result["cells"].append(run_cell(
                contract=contract,
                seed=seed,
                presence_memory=memory,
                destination_choice=destination,
                horizon_days=horizon,
                agent_count=agents,
                locality_count=localities,
                challenge=args.challenge,
            ))
    after = repository_state(ROOT)
    result["repository_after"] = after
    result["model_hash_stable"] = (
        before.get("commit_hash") == after.get("commit_hash") and
        before.get("tracked_diff_sha256") == after.get("tracked_diff_sha256") and
        all(
            cell["manifest"]["extra"]["model_sha256_start"] ==
            cell["manifest"]["extra"]["model_sha256_end"]
            for cell in result["cells"]
        )
    )
    result["integrity_passed"] = bool(result["model_hash_stable"]) and all(
        cell["manifest_audit"]["valid"] for cell in result["cells"]
    )
    # A short pilot cannot satisfy the preregistered scientific gate: it is
    # shorter than the 28-day renewal estimand and does not recover a known
    # synthetic truth.  Keeping this explicit prevents a provenance pass from
    # being mistaken for evidence that either factor has the predicted effect.
    result["scientific_acceptance_gate_passed"] = False
    result["pilot_limitations"] = (
        [
            "contact challenge conditions on a declared focal pair and forced detection",
            "challenge is not the parent factorial and cannot be pooled with it",
            "no synthetic truth-recovery battery is run by this pilot",
            "pilot is diagnostic only and cannot license historical fitting or a core change",
        ] if args.challenge else [
            "14-day pilot does not identify the preregistered 28-day renewal rate",
            "no synthetic truth-recovery battery is run by this pilot",
            "zero-contact cells cannot assess contact-mediated reproduction",
            "pilot is diagnostic only and cannot license historical fitting or a core change",
        ]
    )
    result["passed"] = False if not args.full else result["integrity_passed"]
    result["interpretation"] = (
        "Synthetic treatment diagnostics only.  No historical fit, transfer, "
        "causal claim, or core-change license is implied."
    )
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    companion = output_path.with_name(output_path.stem + "_manifest.json")
    companion.write_text(json.dumps({
        "schema_version": "1.0.0",
        "status": "synthetic_pilot_provenance_manifest",
        "artifact": output_path.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(output_path),
        "script": Path(__file__).relative_to(ROOT).as_posix(),
        "script_sha256": file_sha256(Path(__file__)),
        "contract": contract_path.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(contract_path),
        "model_hashes": sorted({
            cell["manifest"]["extra"]["model_sha256_start"]
            for cell in result["cells"]
        }),
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "cells": len(result["cells"]),
        "model_hash_stable": result["model_hash_stable"],
        "integrity_passed": result["integrity_passed"],
        "scientific_acceptance_gate_passed": result["scientific_acceptance_gate_passed"],
        "output": output_path.as_posix(),
    }, indent=2))
    return 0 if result["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
