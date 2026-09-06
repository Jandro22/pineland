"""Synthetic causal decomposition of connected insurgent spatial reproduction."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind, clamp  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.logistics import advance_movement_orders, create_movement_order  # noqa: E402
from pineland_sim.networks import edge_between  # noqa: E402
from pineland_sim.organization_ecology import (  # noqa: E402
    _apply_local_fighter_change, _set_armed_membership, recruit_and_retain,
)
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256  # noqa: E402
from estimate_insurgent_reproduction import estimate  # noqa: E402
from trace_locality_activation_genealogy import LocalityActivationTracer  # noqa: E402

OUT = ROOT / "studies" / "research_program" / "spatial_reproduction_bottlenecks.json"
EPS = 1e-12
STAGE_ORDER = (
    "contact_information_exposure", "recruitment_response",
    "local_fighter_conversion", "formation_birth",
    "movement_relocation", "survival_after_birth",
)
CORE_SOURCE_PATHS = (
    "src/pineland_sim/config.py",
    "src/pineland_sim/generator.py",
    "src/pineland_sim/processes.py",
    "src/pineland_sim/simulation.py",
    "src/pineland_sim/organization_ecology.py",
    "src/pineland_sim/logistics.py",
    "src/pineland_sim/networks.py",
)


def _core_source_hashes() -> dict[str, str]:
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in CORE_SOURCE_PATHS
    }


def _active_insurgent_ids(world) -> set[str]:
    return {o.organization_id for o in world.organizations.values()
            if o.kind is OrganizationKind.INSURGENT and o.status == "active"}


def _snapshot(world) -> dict[str, Any]:
    insurgents = _active_insurgent_ids(world)
    localities = world.localities
    member = {lid: 0.0 for lid in localities}
    fielded = {lid: 0.0 for lid in localities}
    fighter = {lid: 0.0 for lid in localities}
    exposure = {lid: 0.0 for lid in localities}
    effective_ids = {lid: set() for lid in localities}
    formation_locality: dict[str, str] = {}
    for person in world.persons.values():
        lid = person.residence_locality_id
        if person.organization_id in insurgents and person.armed_fraction > 0:
            member[lid] += person.weight * person.armed_fraction
        signal = float(person.social_exposure.get("insurgent", 0.0))
        for oid in insurgents:
            signal = max(signal, float(person.social_exposure.get(oid, 0.0)))
        exposure[lid] = max(exposure[lid], clamp(signal))
    for formation in world.formations.values():
        if formation.organization_id not in insurgents or formation.personnel <= 0:
            continue
        formation_locality[formation.formation_id] = formation.locality_id
        fighter[formation.locality_id] += float(formation.personnel)
        if (formation.operational_status == "effective" and not formation.moving
                and not formation.outside_pineland):
            fielded[formation.locality_id] += float(formation.personnel)
            effective_ids[formation.locality_id].add(formation.formation_id)
    for (oid, lid), quantity in world.organization_manpower_pools.items():
        if oid in insurgents:
            fighter[lid] += float(quantity)
    cfg = world.config.organization_ecology
    access = {lid: max(
        exposure[lid],
        clamp(member[lid] / max(EPS, cfg.minimum_proto_represented_population)),
        clamp(fielded[lid] / max(EPS, cfg.minimum_formation_personnel)),
    ) for lid in localities}
    return {"member": member, "fielded": fielded, "fighter": fighter,
            "exposure": exposure, "access": access,
            "effective_ids": effective_ids, "formation_locality": formation_locality}


def _eligible_recruit_mass(world, target: str, insurgents: set[str]) -> float:
    total = 0.0
    for person in world.persons.values():
        if person.residence_locality_id != target:
            continue
        if person.organization_id is not None and person.organization_id not in insurgents:
            continue
        current = person.armed_fraction if person.organization_id in insurgents else 0.0
        total += person.weight * max(0.0, 1.0 - current)
    return total


def _source_connected_exposure(world, target: str, sources: tuple[str, ...]) -> bool:
    """Require target exposure to have a live armed social bridge from a source."""
    insurgents = _active_insurgent_ids(world)
    source_set = set(sources)
    for person in world.persons.values():
        if person.residence_locality_id != target:
            continue
        if person.organization_id is not None and person.organization_id not in insurgents:
            continue
        exposure = float(person.social_exposure.get("insurgent", 0.0))
        for oid in insurgents:
            exposure = max(exposure, float(person.social_exposure.get(oid, 0.0)))
        if exposure <= EPS:
            continue
        for neighbor_id in world.social_neighbors.get(person.person_id, ()):
            neighbor = world.persons[neighbor_id]
            if (neighbor.residence_locality_id not in source_set
                    or neighbor.organization_id not in insurgents
                    or neighbor.armed_fraction <= EPS):
                continue
            edge = edge_between(world, person.person_id, neighbor_id)
            if edge.weight * edge.trust * edge.represented_relationships > EPS:
                return True
    return False


def _initial_frontier(world, snap: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    minimum = world.config.organization_ecology.minimum_formation_personnel
    occupied = {lid for lid, mass in snap["fielded"].items() if mass + EPS >= minimum}
    insurgents = _active_insurgent_ids(world)
    parents: dict[str, set[str]] = {}
    for source in occupied:
        for target in world.adjacency.get(source, {}):
            if (target not in occupied
                    and snap["member"][target] <= EPS
                    and _eligible_recruit_mass(world, target, insurgents) > EPS):
                parents.setdefault(target, set()).add(source)
    return {target: tuple(sorted(sources)) for target, sources in sorted(parents.items())}


class FrontierCohortObserver:
    """Observation-only opportunity accounting on the initial synthetic frontier."""

    def __init__(self, world, survival_window_days: float = 14.0) -> None:
        self.world = world
        self.survival_window_days = float(survival_window_days)
        initial = _snapshot(world)
        self.frontier = _initial_frontier(world, initial)
        self.rows = {target: {
            "target_locality_id": target, "source_locality_ids": list(sources),
            "exposure_seen": _source_connected_exposure(world, target, sources),
            "access_seen": initial["access"][target] > EPS,
            "recruitment_seen": False, "fighter_conversion_seen": False,
            "local_birth_day": None, "local_birth_ids": [],
            "relocation_seen": False, "relocation_day": None,
            "birth_complete_followup": False, "birth_survived_window": False,
        } for target, sources in self.frontier.items()}

    def observe_transition(self, before: dict[str, Any], event_type: str, time: float) -> None:
        after = _snapshot(self.world)
        for target, row in self.rows.items():
            source_exposed_now = _source_connected_exposure(
                self.world, target, tuple(row["source_locality_ids"])
            )
            if source_exposed_now:
                row["exposure_seen"] = True
            if event_type == "recruitment":
                if before["access"][target] > EPS:
                    row["access_seen"] = True
                member_gain = after["member"][target] - before["member"][target]
                fighter_gain = after["fighter"][target] - before["fighter"][target]
                if source_exposed_now and member_gain > EPS:
                    row["recruitment_seen"] = True
                if source_exposed_now and member_gain > EPS and fighter_gain > EPS:
                    row["fighter_conversion_seen"] = True
                new_ids = after["effective_ids"][target] - before["effective_ids"][target]
                created = [fid for fid in sorted(new_ids)
                           if fid not in before["formation_locality"]]
                if (created and source_exposed_now
                        and member_gain > EPS and fighter_gain > EPS):
                    if row["local_birth_day"] is None:
                        row["local_birth_day"] = float(time)
                    row["local_birth_ids"] = sorted(set(row["local_birth_ids"]) | set(created))
            elif event_type == "force_movement":
                arrived = after["effective_ids"][target] - before["effective_ids"][target]
                relocated = [fid for fid in arrived
                             if fid in before["formation_locality"]
                             and before["formation_locality"][fid] != target]
                if relocated:
                    row["relocation_seen"] = True
                    row["relocation_day"] = (float(time) if row["relocation_day"] is None
                                              else min(row["relocation_day"], float(time)))
            birth_day = row["local_birth_day"]
            if birth_day is not None and time + EPS >= birth_day + self.survival_window_days:
                row["birth_complete_followup"] = True
                if any(
                    formation_id in after["effective_ids"][target]
                    for formation_id in row["local_birth_ids"]
                ):
                    row["birth_survived_window"] = True

    def finalize(self, observation_end_day: float) -> list[dict[str, Any]]:
        final = _snapshot(self.world)
        for target, row in self.rows.items():
            birth_day = row["local_birth_day"]
            if (birth_day is not None and observation_end_day + EPS >=
                    birth_day + self.survival_window_days):
                row["birth_complete_followup"] = True
                if any(
                    formation_id in final["effective_ids"][target]
                    for formation_id in row["local_birth_ids"]
                ):
                    row["birth_survived_window"] = True
        return list(self.rows.values())


def _stage_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    definitions = {
        "contact_information_exposure": (
            rows, lambda r: bool(r["exposure_seen"]),
            "initial road-adjacent unoccupied frontier localities"),
        "recruitment_response": (
            [r for r in rows if r["exposure_seen"]], lambda r: bool(r["recruitment_seen"]),
            "frontier localities with source-attributed cross-local insurgent social exposure"),
        "local_fighter_conversion": (
            [r for r in rows if r["exposure_seen"] and r["recruitment_seen"]],
            lambda r: bool(r["fighter_conversion_seen"]),
            "frontier localities with positive represented armed recruitment"),
        "formation_birth": (
            [r for r in rows if r["exposure_seen"] and r["recruitment_seen"]
             and r["fighter_conversion_seen"]],
            lambda r: r["local_birth_day"] is not None,
            "frontier localities with positive recruitment-induced fighter conversion"),
        "movement_relocation": (
            rows, lambda r: bool(r["relocation_seen"]),
            "initial frontier localities; competing gross-spread route"),
        "survival_after_birth": (
            [r for r in rows if r["exposure_seen"] and r["recruitment_seen"]
             and r["fighter_conversion_seen"] and r["local_birth_day"] is not None
             and r["birth_complete_followup"]],
            lambda r: bool(r["birth_survived_window"]),
            "recruitment-born frontier locality activations with a complete survival follow-up window"),
    }
    result = {}
    for stage in STAGE_ORDER:
        eligible, success, denominator_definition = definitions[stage]
        denominator = len(eligible)
        numerator = sum(bool(success(row)) for row in eligible)
        result[stage] = {
            "opportunity_denominator": denominator,
            "realized_numerator": numerator,
            "lost_opportunities": denominator - numerator,
            "loss_fraction": ((denominator - numerator) / denominator if denominator else None),
            "identified": denominator > 0,
            "denominator_definition": denominator_definition,
        }
    return result


def rank_stage_losses(stage_counts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    identified = [(stage, row) for stage, row in stage_counts.items()
                  if row.get("identified") and row.get("loss_fraction") is not None]
    identified.sort(key=lambda item: (-float(item[1]["loss_fraction"]), order[item[0]]))
    return [{"rank": i, "stage": stage, "loss_fraction": row["loss_fraction"],
             "lost_opportunities": row["lost_opportunities"],
             "opportunity_denominator": row["opportunity_denominator"]}
            for i, (stage, row) in enumerate(identified, 1)]


def _genealogy_estimates(episodes: list[dict], edges: list[dict], horizon_days: float) -> dict:
    if not episodes or horizon_days <= 0:
        return {"identified": False, "reason": "no activation episodes or follow-up"}
    window = max(1.0, min(30.0, horizon_days / 2.0))
    gross = estimate(episodes, parent_edges=edges, horizon_days=window, bootstrap=0)
    net_edges = [edge for edge in edges if edge.get("pathway") != "formation_relocation"]
    net = estimate(episodes, parent_edges=net_edges, horizon_days=window, bootstrap=0)
    return {
        "identified": bool(gross["eligible_parent_activations"]),
        "followup_days": window,
        "gross_R_I": gross["estimate"],
        "net_R_I_excluding_relocation_edges": net["estimate"],
        "gross_by_pathway": gross.get("estimate_by_pathway", {}),
        "note": "Supplementary observation-only genealogy; ranking uses frontier opportunities.",
    }


def run_frontier_cohort(*, seed: int, horizon_days: float = 60.0,
                        agent_count: int = 900, locality_count: int = 24,
                        survival_window_days: float = 14.0) -> dict[str, Any]:
    config = SimulationConfig(seed=seed, horizon_days=horizon_days,
                              agent_count=agent_count, locality_count=locality_count,
                              output_mode="calibration")
    world = generate_pineland(config)
    simulation = Simulation(world)
    observer = FrontierCohortObserver(world, survival_window_days)
    tracer = LocalityActivationTracer(world)
    tracer.initialize(0.0)
    original_execute = simulation.processes.execute

    def observed_execute(event):
        before_observer = _snapshot(world)
        before_genealogy = tracer.capture()
        event_id = original_execute(event)
        observer.observe_transition(before_observer, event.event_type, world.time)
        tracer.observe_transition(before_genealogy, event.event_type, event_id, world.time)
        return event_id

    simulation.processes.execute = observed_execute
    result = simulation.run(until=horizon_days)
    rows = observer.finalize(result.stopped_at)
    episodes = tracer.finalize(result.stopped_at)
    edges = tracer.parent_edges()
    return {"seed": seed, "horizon_days": result.stopped_at,
            "frontier_opportunity_count": len(rows), "opportunities": rows,
            "stage_counts": _stage_counts(rows),
            "genealogy": _genealogy_estimates(episodes, edges, result.stopped_at)}


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    pooled = [row for run in runs for row in run["opportunities"]]
    counts = _stage_counts(pooled)
    ranking = rank_stage_losses(counts)
    local_ranking = [
        row for row in ranking if row["stage"] != "movement_relocation"
    ]
    return {"frontier_opportunity_count": len(pooled), "stage_counts": counts,
            "ranking_by_conditional_loss_fraction": ranking,
            "largest_identified_bottleneck": ranking[0]["stage"] if ranking else None,
            "largest_local_reproduction_bottleneck": (
                local_ranking[0]["stage"] if local_ranking else None
            ),
            "interpretation_rule": (
                "Rank identified stages by conditional loss fraction. Movement is a competing "
                "gross-spread route and is excluded from net genealogy R_I.")}

class _ZeroDrawRng:
    @staticmethod
    def random() -> float:
        return 0.0

    @staticmethod
    def choices(population, weights, k):
        return [population[0]]

    @staticmethod
    def normalvariate(mu, sigma):
        return mu

    @staticmethod
    def uniform(low, high):
        return low


def _target_member_mass(world, target: str) -> float:
    insurgents = _active_insurgent_ids(world)
    return sum(person.weight * person.armed_fraction for person in world.persons.values()
               if person.residence_locality_id == target
               and person.organization_id in insurgents)


def _clean_target(world, target: str) -> None:
    insurgents = _active_insurgent_ids(world)
    for person in world.persons.values():
        if person.residence_locality_id != target:
            continue
        if person.organization_id in insurgents:
            world.organizations[person.organization_id].member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
        person.social_exposure["insurgent"] = 0.0
        for oid in insurgents:
            person.social_exposure[oid] = 0.0


def run_matched_recovery_tests(seed: int = 20260905) -> dict[str, Any]:
    """Matched synthetic falsification/recovery tests for all six stages."""
    config = SimulationConfig(seed=seed, horizon_days=1.0, agent_count=600,
                              locality_count=24, output_mode="calibration")
    base = generate_pineland(config)
    # Matched stage-recovery tests condition on a nonbinding common resource
    # budget so they isolate exposure, recruitment, conversion, and birth.
    for organization in base.organizations.values():
        if organization.kind is OrganizationKind.INSURGENT:
            organization.resources = max(organization.resources, 1_000_000.0)
    frontier = _initial_frontier(base, _snapshot(base))
    if not frontier:
        return {"passed": False, "historical_outcomes_used": False,
                "empirical_parameter_fitting": False,
                "reason": "generated world had no initial frontier"}
    insurgents = _active_insurgent_ids(base)
    pair = None
    for target, sources in frontier.items():
        source_set = set(sources)
        for person in base.persons.values():
            if person.residence_locality_id != target:
                continue
            for neighbor_id in base.social_neighbors.get(person.person_id, ()):
                neighbor = base.persons[neighbor_id]
                if neighbor.residence_locality_id in source_set:
                    pair = (target, neighbor.residence_locality_id,
                            person.person_id, neighbor_id)
                    break
            if pair:
                break
        if pair:
            break
    if pair is None:
        return {"passed": False, "historical_outcomes_used": False,
                "empirical_parameter_fitting": False,
                "reason": "generated frontier had no cross-local social bridge"}
    target, source, target_person_id, source_person_id = pair
    organization_id = next(f.organization_id for f in base.formations.values()
                           if f.locality_id == source and f.organization_id in insurgents)

    # Contact/information exposure: same generated world, same source and
    # target, with only the focal cross-local bridge deleted in the placebo.
    exposure_world = deepcopy(base)
    _clean_target(exposure_world, target)
    source_person = exposure_world.persons[source_person_id]
    if source_person.organization_id and source_person.organization_id in exposure_world.organizations:
        exposure_world.organizations[source_person.organization_id].member_ids.discard(
            source_person.person_id)
    _set_armed_membership(source_person, exposure_world.organizations[organization_id], 1.0)
    exposure_world.organizations[organization_id].member_ids.add(source_person.person_id)
    source_person.public_behavior = "armed_participation"
    target_person = exposure_world.persons[target_person_id]
    for neighbor_id in exposure_world.social_neighbors.get(target_person_id, ()):
        if neighbor_id != source_person_id:
            exposure_world.persons[neighbor_id].public_behavior = "neutral"
    exposure_world.config.social_network.behavior_update_rate = 0.0
    exposure_placebo = deepcopy(exposure_world)
    key = tuple(sorted((target_person_id, source_person_id)))
    del exposure_placebo.social_edges[key]
    exposure_placebo.social_neighbors[target_person_id].remove(source_person_id)
    exposure_placebo.social_neighbors[source_person_id].remove(target_person_id)
    for world in (exposure_placebo, exposure_world):
        ProcessEngine(world, _ZeroDrawRng()).on_social_influence(
            "SYNTHETIC-EXPOSURE",
            ScheduledEvent(0.0, 0, 0, "social_influence", {"interval": 1.0}),
        )
    placebo_exposure = exposure_placebo.persons[target_person_id].social_exposure.get(
        "insurgent", 0.0)
    recovered_exposure = exposure_world.persons[target_person_id].social_exposure.get(
        "insurgent", 0.0)

    # Recruitment response: condition on the recovered exposure and vary only
    # the recruitment hazard in the matched target representative.
    recruitment_zero = deepcopy(exposure_world)
    recruitment_high = deepcopy(exposure_world)
    for world in (recruitment_zero, recruitment_high):
        person = world.persons[target_person_id]
        person.grievance = 1.0
        person.fear = 0.0
        person.political_access = 0.0
        person.identities["federal"] = world.organizations[organization_id].ideology.get(
            "reform", 0.5)
        world.organizations[organization_id].capital["social"] = 1.0
    recruitment_zero.config.recruitment_rate = 0.0
    recruitment_high.config.recruitment_rate = 1.0
    recruit_and_retain(recruitment_zero, 1.0, _ZeroDrawRng(), interval_days=7.0)
    recruit_and_retain(recruitment_high, 1.0, _ZeroDrawRng(), interval_days=7.0)
    zero_recruit_fraction = recruitment_zero.persons[target_person_id].armed_fraction
    recovered_recruit_fraction = recruitment_high.persons[target_person_id].armed_fraction

    # Fighter conversion: identical exposed/high-recruitment worlds, changing
    # only the conversion fraction.
    conversion_zero = deepcopy(exposure_world)
    conversion_high = deepcopy(exposure_world)
    conversion_zero.config.recruitment_rate = 1.0
    conversion_high.config.recruitment_rate = 1.0
    conversion_zero.config.organization_ecology.fighter_conversion_fraction = 0.0
    conversion_high.config.organization_ecology.fighter_conversion_fraction = 1.0
    before_zero_fighter = _snapshot(conversion_zero)["fighter"][target]
    before_high_fighter = _snapshot(conversion_high)["fighter"][target]
    recruit_and_retain(conversion_zero, 1.0, _ZeroDrawRng(), interval_days=7.0)
    recruit_and_retain(conversion_high, 1.0, _ZeroDrawRng(), interval_days=7.0)
    zero_fighter_gain = _snapshot(conversion_zero)["fighter"][target] - before_zero_fighter
    recovered_fighter_gain = _snapshot(conversion_high)["fighter"][target] - before_high_fighter

    birth_world = deepcopy(base)
    _clean_target(birth_world, target)
    organization = birth_world.organizations[organization_id]
    minimum = birth_world.config.organization_ecology.minimum_formation_personnel
    first_delta, second_delta = minimum * 0.49, minimum * 0.51 + 1e-9
    _, first_created = _apply_local_fighter_change(
        birth_world, organization, target, first_delta)
    pool_after_first = birth_world.organization_manpower_pools.get(
        (organization_id, target), 0.0)
    _, second_created = _apply_local_fighter_change(
        birth_world, organization, target, second_delta)
    local_effective = [f for f in birth_world.formations.values()
                       if f.organization_id == organization_id and f.locality_id == target
                       and f.operational_status == "effective" and f.personnel > 0]

    move_world = deepcopy(base)
    formation = next(f for f in move_world.formations.values()
                     if f.locality_id == source and f.organization_id == organization_id
                     and f.operational_status == "effective" and f.personnel > 0)
    formation.supply_capacity = max(formation.supply_capacity, 1e9)
    formation.supply_stock = formation.supply_capacity
    order = create_movement_order(move_world, formation.formation_id, target, 0.0,
                                  _ZeroDrawRng(), purpose="reallocation")
    advance_movement_orders(move_world, order.execute_at)
    if order.arrives_at is not None:
        advance_movement_orders(move_world, order.arrives_at)
    movement_recovered = order.status == "arrived" and formation.locality_id == target

    surviving_world = deepcopy(birth_world)
    failed_world = deepcopy(birth_world)
    born_ids = [f.formation_id for f in local_effective]
    for formation_id in born_ids:
        failed_world.formations[formation_id].operational_status = "ineffective"
    survival_recovered = _snapshot(surviving_world)["fielded"][target] + EPS >= minimum
    survival_falsified = _snapshot(failed_world)["fielded"][target] + EPS < minimum

    stage_gates = {
        "contact_information_exposure": (
            placebo_exposure <= EPS and recovered_exposure > EPS),
        "recruitment_response": (
            zero_recruit_fraction <= EPS and recovered_recruit_fraction > EPS),
        "local_fighter_conversion": (
            abs(zero_fighter_gain) <= EPS and recovered_fighter_gain > EPS),
        "formation_birth": (
            first_created == 0 and abs(pool_after_first - first_delta) <= 1e-8
            and second_created >= 1 and bool(local_effective)),
        "movement_relocation": movement_recovered,
        "survival_after_birth": survival_recovered and survival_falsified,
    }
    return {
        "passed": all(stage_gates.values()), "historical_outcomes_used": False,
        "empirical_parameter_fitting": False, "seed": seed,
        "target_locality_id": target, "source_locality_id": source,
        "placebo_source_bridge_exposure": placebo_exposure,
        "recovered_source_bridge_exposure": recovered_exposure,
        "zero_rate_target_armed_fraction": zero_recruit_fraction,
        "recovered_target_armed_fraction": recovered_recruit_fraction,
        "zero_conversion_fighter_gain": zero_fighter_gain,
        "recovered_conversion_fighter_gain": recovered_fighter_gain,
        "minimum_formation_personnel": minimum,
        "subthreshold_fighter_delta": first_delta,
        "pool_after_subthreshold_delta": pool_after_first,
        "birth_trigger_delta": second_delta,
        "forced_movement_order_status": order.status,
        "survival_recovered": survival_recovered,
        "survival_falsified_when_newborns_ineffective": survival_falsified,
        "stage_gates": stage_gates,
    }


def run_study(*, seeds: list[int], horizon_days: float = 60.0,
              agent_count: int = 900, locality_count: int = 24,
              survival_window_days: float = 14.0) -> dict[str, Any]:
    if not seeds:
        raise ValueError("at least one synthetic seed is required")
    script_path = Path(__file__)
    script_hash_start = file_sha256(script_path)
    model_hash_start = model_sha256(ROOT)
    hashes_before = _core_source_hashes()
    runs = []
    for seed in seeds:
        if file_sha256(script_path) != script_hash_start:
            raise RuntimeError("study source changed during decomposition; run rejected")
        if model_sha256(ROOT) != model_hash_start or _core_source_hashes() != hashes_before:
            raise RuntimeError("live model source changed during decomposition; run rejected")
        runs.append(run_frontier_cohort(
            seed=seed, horizon_days=horizon_days,
            agent_count=agent_count, locality_count=locality_count,
            survival_window_days=survival_window_days))
    if file_sha256(script_path) != script_hash_start:
        raise RuntimeError("study source changed during decomposition; run rejected")
    recovery = run_matched_recovery_tests(seeds[0])
    hashes_after = _core_source_hashes()
    model_hash_end = model_sha256(ROOT)
    script_hash_end = file_sha256(script_path)
    core_changed = hashes_before != hashes_after or model_hash_start != model_hash_end
    study_changed = script_hash_start != script_hash_end
    if study_changed:
        raise RuntimeError("study source changed during decomposition; run rejected")
    if core_changed:
        raise RuntimeError("live model source changed during decomposition; run rejected")
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_connected_spatial_reproduction_bottleneck_decomposition",
        "historical_outcomes_used": False, "empirical_parameter_fitting": False,
        "core_model_modified": False,
        "negative_results_preserved": True,
        "estimand": "conditional stage realization in the initial road-connected synthetic frontier cohort",
        "seeds": seeds, "horizon_days": horizon_days, "agent_count": agent_count,
        "locality_count": locality_count, "survival_window_days": survival_window_days,
        "core_source_hashes": hashes_before,
        "core_changed_during_study": core_changed,
        "study_changed_during_study": study_changed,
        "provenance_valid": not core_changed and not study_changed,
        "model_sha256_start": model_hash_start,
        "model_sha256_end": model_hash_end,
        "script_sha256_start": script_hash_start,
        "script_sha256_end": script_hash_end,
        "aggregate": aggregate_runs(runs),
        "matched_intervention_recovery": recovery,
        "runs": runs,
        "falsification_rules": {
            "contact_information_exposure": "Deleting only the focal source-target social bridge eliminates focal target exposure; restoring it recovers exposure.",
            "recruitment_response": "With source exposure present, zero recruitment hazard blocks focal recruitment and a high hazard with matched draws recovers it.",
            "local_fighter_conversion": "With exposure and recruitment present, zero conversion yields zero local fighter gain and positive conversion recovers fighter gain.",
            "formation_birth": "Subthreshold fighter inflow pools; crossing the live minimum births a unit.",
            "movement_relocation": "A supplied command-passing connected movement order arrives.",
            "survival_after_birth": "The matched newborn locality is viable with effective newborn force and nonviable when those newborns are made ineffective.",
            "survival_censoring": "Births lacking complete follow-up are censored, not scored as deaths.",
        },
        "interpretive_guardrails": [
            "The contact/information stage is cross-local social exposure, not combat contact.",
            "Movement is a parallel gross-spread pathway and is not algebraically spliced into the sequential social-recruitment chain.",
            "Conditional loss fractions use explicit stage-specific denominators and are diagnostic, not fitted causal effect sizes.",
            "The observation-only genealogy R_I is supplementary and preserves relocation versus non-relocation pathway semantics.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="20260905,20260906,20260907")
    parser.add_argument("--horizon-days", type=float, default=60.0)
    parser.add_argument("--agent-count", type=int, default=900)
    parser.add_argument("--locality-count", type=int, default=24)
    parser.add_argument("--survival-window-days", type=float, default=14.0)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    payload = run_study(seeds=seeds, horizon_days=args.horizon_days,
                        agent_count=args.agent_count, locality_count=args.locality_count,
                        survival_window_days=args.survival_window_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "largest_identified_bottleneck": payload["aggregate"]["largest_identified_bottleneck"],
                      "ranking": payload["aggregate"]["ranking_by_conditional_loss_fraction"],
                      "recovery_passed": payload["matched_intervention_recovery"]["passed"]}, indent=2))


if __name__ == "__main__":
    main()
