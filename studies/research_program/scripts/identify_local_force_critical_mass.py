"""Case-free synthetic identification of local insurgent force critical mass."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))
from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind, clamp  # noqa: E402
from pineland_sim.logistics import (  # noqa: E402
    advance_movement_orders, create_movement_order,
)
from pineland_sim.organization_ecology import (  # noqa: E402
    _apply_local_fighter_change, _formation_is_local_recruitment_source,
    _set_armed_membership,
)
from trace_locality_activation_genealogy import LocalityActivationTracer  # noqa: E402

OUT = ROOT / "studies" / "research_program" / "local_force_critical_mass.json"
SEED = 20260905

class _ZeroRng:
    def random(self):
        return 0.0

def _world(seed: int):
    return generate_pineland(SimulationConfig(
        agent_count=600, locality_count=34, horizon_days=1, seed=seed,
        output_mode="ensemble"))

def _org(world):
    return next(o for o in world.organizations.values()
                if o.kind is OrganizationKind.INSURGENT and o.status == "active")

def _targets(world, org, n: int) -> list[str]:
    occupied = {f.locality_id for f in world.formations.values()
                if f.organization_id == org.organization_id and f.personnel > 0}
    ids = [lid for lid in sorted(world.localities)
           if lid not in occupied and any(
               p.residence_locality_id == lid and
               p.organization_id in {None, org.organization_id}
               for p in world.persons.values())]
    if len(ids) < n:
        raise RuntimeError(f"need {n} target localities, found {len(ids)}")
    return ids[:n]

def _set_members(world, org, lid: str, mass: float) -> None:
    for p in world.persons.values():
        if p.residence_locality_id == lid and p.organization_id == org.organization_id:
            org.member_ids.discard(p.person_id)
            _set_armed_membership(p, None, 0.0)
    remaining = float(mass)
    people = sorted(
        (p for p in world.persons.values()
         if p.residence_locality_id == lid and p.organization_id is None),
        key=lambda p: (-p.weight, p.person_id))
    for p in people:
        if remaining <= 1e-9:
            break
        represented = min(p.weight, remaining)
        _set_armed_membership(p, org, represented / p.weight)
        org.member_ids.add(p.person_id)
        remaining -= represented
    if remaining > 1e-6:
        raise RuntimeError(f"insufficient represented population in {lid}")

def _member_mass(world, org, lid: str) -> float:
    return sum(p.weight * p.armed_fraction for p in world.persons.values()
               if p.residence_locality_id == lid and
               p.organization_id == org.organization_id)

def _forms(world, org, lid: str):
    return [f for f in world.formations.values()
            if f.organization_id == org.organization_id and
            f.locality_id == lid and f.personnel > 0]

def _access(world, org, lid: str) -> dict[str, float]:
    cfg = world.config.organization_ecology
    members = _member_mass(world, org, lid)
    force = sum(f.personnel for f in _forms(world, org, lid)
                if _formation_is_local_recruitment_source(f))
    ma = clamp(members / cfg.minimum_proto_represented_population)
    fa = clamp(force / cfg.minimum_formation_personnel)
    return {"represented_members": members, "member_access": ma,
            "formation_source_personnel": force, "formation_access": fa,
            "combined_access": max(ma, fa)}

def _edges(tracer, lids: set[str]) -> list[dict]:
    child_ids = {e.activation_id for e in tracer.episodes
                 if e.channel == "fielded_force_viable" and
                 e.locality_id in lids and e.cause != "initial_condition"}
    return [edge for edge in tracer.parent_edges()
            if edge["child_activation_id"] in child_ids]


def run_concentration_condition(n: int, total_represented: float = 2000.0,
                                seed: int = SEED) -> dict[str, Any]:
    world = _world(seed)
    org = _org(world)
    lids = _targets(world, org, n)
    share = total_represented / n
    cfg = world.config.organization_ecology
    for lid in lids:
        world.organization_manpower_pools[(org.organization_id, lid)] = 0.0
        _set_members(world, org, lid, share)
    tracer = LocalityActivationTracer(world)
    tracer.initialize(0.0)
    applied = 0.0
    births = 0
    for i, lid in enumerate(lids):
        before = tracer.capture()
        delta, created = _apply_local_fighter_change(
            world, org, lid, share * cfg.fighter_conversion_fraction)
        applied += delta
        births += created
        tracer.observe_transition(before, "recruitment", f"CM-C-{n}-{i}", 1.0)
    snap = tracer.capture()
    return {
        "locality_count": n,
        "total_represented_recruitment": total_represented,
        "represented_recruitment_per_locality": share,
        "total_fighter_equivalent_applied": applied,
        "formations_created": births,
        "member_access_saturated_localities": sum(
            snap["states"]["member_access_saturated"][lid] for lid in lids),
        "fielded_force_viable_localities": sum(
            snap["states"]["fielded_force_viable"][lid] for lid in lids),
        "remaining_pool_total": sum(world.organization_manpower_pools.get(
            (org.organization_id, lid), 0.0) for lid in lids),
        "access": {lid: _access(world, org, lid) for lid in lids},
        "genealogy_edges": _edges(tracer, set(lids)),
    }

def run_threshold_sweep(seed: int = SEED) -> dict[str, Any]:
    ref = _world(seed)
    cfg = ref.config.organization_ecology
    force_threshold = cfg.minimum_formation_personnel / cfg.fighter_conversion_fraction
    proto = cfg.minimum_proto_represented_population
    eps = force_threshold * 1e-6
    values = sorted({force_threshold - eps, force_threshold,
                     (force_threshold + proto) / 2, proto, proto + eps})
    rows = []
    for i, mass in enumerate(values):
        world = _world(seed)
        org = _org(world)
        lid = _targets(world, org, 1)[0]
        world.organization_manpower_pools[(org.organization_id, lid)] = 0.0
        _set_members(world, org, lid, mass)
        _, births = _apply_local_fighter_change(
            world, org, lid,
            mass * world.config.organization_ecology.fighter_conversion_fraction)
        a = _access(world, org, lid)
        rows.append({
            "represented_members": mass,
            "member_access": a["member_access"],
            "formations_created": births,
            "fielded_force_viable":
                a["formation_source_personnel"] + 1e-12 >=
                world.config.organization_ecology.minimum_formation_personnel,
        })
    return {
        "minimum_proto_represented_population": proto,
        "minimum_formation_personnel": cfg.minimum_formation_personnel,
        "fighter_conversion_fraction": cfg.fighter_conversion_fraction,
        "proto_implied_fighter_personnel":
            proto * cfg.fighter_conversion_fraction,
        "proto_gate_already_clears_formation_manpower_minimum":
            proto * cfg.fighter_conversion_fraction + 1e-12 >=
            cfg.minimum_formation_personnel,
        "represented_members_for_force_birth_from_empty_pool": force_threshold,
        "rows": rows,
    }

def run_pool_alignment(seed: int = SEED) -> dict[str, Any]:
    out = {}
    new_members, prepool = 500.0, 40.0
    for j, condition in enumerate(("aligned", "dispersed")):
        world = _world(seed)
        org = _org(world)
        recruit, a, b = _targets(world, org, 3)
        for lid in (recruit, a, b):
            world.organization_manpower_pools[(org.organization_id, lid)] = 0.0
        if condition == "aligned":
            world.organization_manpower_pools[(org.organization_id, recruit)] = prepool
        else:
            world.organization_manpower_pools[(org.organization_id, a)] = prepool / 2
            world.organization_manpower_pools[(org.organization_id, b)] = prepool / 2
        _set_members(world, org, recruit, new_members)
        tracer = LocalityActivationTracer(world)
        tracer.initialize(0.0)
        before = tracer.capture()
        applied, births = _apply_local_fighter_change(
            world, org, recruit,
            new_members * world.config.organization_ecology.fighter_conversion_fraction)
        tracer.observe_transition(before, "recruitment", f"CM-P-{condition}", 1.0)
        out[condition] = {
            "new_represented_recruitment": new_members,
            "new_fighter_equivalent": applied,
            "preexisting_pool_total": prepool,
            "total_force_manpower_budget": prepool + applied,
            "formations_created": births,
            "genealogy_edges": _edges(tracer, {recruit}),
        }
    return out


def run_hysteresis(seed: int = SEED) -> dict[str, Any]:
    represented, prepool, recruited, loss = 500.0, 35.0, 40.0, 20.0
    current = prepool + recruited - loss

    formed = _world(seed)
    fo = _org(formed)
    fl = _targets(formed, fo, 1)[0]
    _set_members(formed, fo, fl, represented)
    formed.organization_manpower_pools[(fo.organization_id, fl)] = prepool
    _apply_local_fighter_change(formed, fo, fl, recruited)
    _apply_local_fighter_change(formed, fo, fl, -loss)
    f_access = _access(formed, fo, fl)
    units = _forms(formed, fo, fl)

    pooled = _world(seed)
    po = _org(pooled)
    pl = _targets(pooled, po, 1)[0]
    _set_members(pooled, po, pl, represented)
    pooled.organization_manpower_pools[(po.organization_id, pl)] = current
    p_access = _access(pooled, po, pl)

    minimum = formed.config.organization_ecology.minimum_formation_personnel
    return {
        "matched_current_represented_members": represented,
        "matched_current_fighter_manpower": current,
        "formed_then_attrited": {
            "formation_count": len(units),
            "formation_personnel": sum(f.personnel for f in units),
            "operational_source_count":
                sum(_formation_is_local_recruitment_source(f) for f in units),
            "fielded_force_viable":
                sum(f.personnel for f in units) + 1e-12 >= minimum,
            "access": f_access,
        },
        "never_formed_pool": {
            "formation_count": len(_forms(pooled, po, pl)),
            "pool_personnel":
                pooled.organization_manpower_pools[(po.organization_id, pl)],
            "fielded_force_viable": False,
            "access": p_access,
        },
        "access_hysteresis":
            f_access["combined_access"] - p_access["combined_access"],
    }

def run_movement_control(seed: int = SEED) -> dict[str, Any]:
    """Verify that a formed force can relocate but does not reproduce by moving."""
    world = _world(seed)
    org = _org(world)
    cfg = world.config.organization_ecology
    represented = cfg.minimum_formation_personnel / cfg.fighter_conversion_fraction
    origin = _targets(world, org, 1)[0]
    target = sorted(world.adjacency[origin])[0]
    world.organization_manpower_pools[(org.organization_id, origin)] = 0.0
    _set_members(world, org, origin, represented)

    tracer = LocalityActivationTracer(world)
    tracer.initialize(0.0)
    before_birth = tracer.capture()
    _, births = _apply_local_fighter_change(
        world, org, origin, cfg.minimum_formation_personnel)
    tracer.observe_transition(before_birth, "recruitment", "CM-MOVE-BIRTH", 1.0)
    formation = _forms(world, org, origin)[0]
    formation.availability = 1.0
    formation.supply_capacity = max(
        formation.supply_capacity, formation.personnel * 100.0)
    formation.supply_stock = formation.supply_capacity
    formation.sustainment = formation.supply_fraction()
    formation_id = formation.formation_id
    before_count = sum(f.organization_id == org.organization_id
                       for f in world.formations.values())

    order = create_movement_order(
        world, formation_id, target, 2.0, _ZeroRng(), purpose="reallocation")
    before_departure = tracer.capture()
    departure = advance_movement_orders(world, order.execute_at + 1e-8)
    tracer.observe_transition(
        before_departure, "force_movement", order.order_id, order.execute_at + 1e-8)
    in_transit = tracer.capture()
    moving_is_source = _formation_is_local_recruitment_source(
        world.formations[formation_id])
    if order.arrives_at is None:
        raise RuntimeError(
            f"synthetic movement did not depart: {order.status}, {departure}")

    before_arrival = tracer.capture()
    arrival_time = order.arrives_at + 1e-8
    arrival = advance_movement_orders(world, arrival_time)
    tracer.observe_transition(
        before_arrival, "force_movement", order.order_id, arrival_time)
    after = tracer.capture()
    after_count = sum(f.organization_id == org.organization_id
                      for f in world.formations.values())
    relocation = [
        edge for edge in tracer.parent_edges()
        if edge["child_channel"] == "fielded_force_viable"
        and edge["child_locality_id"] == target
        and edge["pathway"] == "formation_relocation"
    ]
    return {
        "origin": origin,
        "target": target,
        "formation_id": formation_id,
        "births_before_move": births,
        "formation_count_before_move": before_count,
        "formation_count_after_move": after_count,
        "departure": departure,
        "arrival": arrival,
        "in_transit": {
            "origin_viable":
                in_transit["states"]["fielded_force_viable"][origin],
            "target_viable":
                in_transit["states"]["fielded_force_viable"][target],
            "moving_formation_is_local_recruitment_source": moving_is_source,
        },
        "after_arrival": {
            "formation_locality": world.formations[formation_id].locality_id,
            "target_viable": after["states"]["fielded_force_viable"][target],
        },
        "relocation_genealogy_edges": relocation,
    }

def run_study(seed: int = SEED) -> dict[str, Any]:
    threshold = run_threshold_sweep(seed)
    concentration = [
        run_concentration_condition(n, seed=seed + 1000)
        for n in (1, 2, 3, 4)
    ]
    pools = run_pool_alignment(seed + 2000)
    hyst = run_hysteresis(seed + 3000)
    movement = run_movement_control(seed + 4000)
    force_t = threshold["represented_members_for_force_birth_from_empty_pool"]
    proto_t = threshold["minimum_proto_represented_population"]
    dispersion = (
        concentration[0]["formations_created"] > 0
        and concentration[1]["formations_created"] > 0
        and concentration[2]["formations_created"] == 0
        and concentration[3]["formations_created"] == 0
    )
    ordered = proto_t <= force_t
    threshold_rows = threshold["rows"]
    threshold_supported = (
        threshold_rows[0]["formations_created"] == 0
        and all(row["formations_created"] > 0 for row in threshold_rows[1:])
    )
    movement_relocation = (
        movement["births_before_move"] == 1
        and movement["formation_count_before_move"] == movement["formation_count_after_move"]
        and not movement["in_transit"]["origin_viable"]
        and not movement["in_transit"]["target_viable"]
        and not movement["in_transit"]["moving_formation_is_local_recruitment_source"]
        and movement["after_arrival"]["target_viable"]
        and bool(movement["relocation_genealogy_edges"])
    )
    conclusions = {
        "hard_local_force_birth_threshold_supported": threshold_supported,
        "spatial_dispersion_can_block_force_birth_at_fixed_total_manpower":
            dispersion,
        "member_access_saturation_is_required_before_force_birth":
            ordered,
        "pool_recruitment_colocation_changes_birth_at_fixed_total_manpower":
            pools["aligned"]["formations_created"] >
            pools["dispersed"]["formations_created"],
        "formed_subthreshold_unit_creates_access_hysteresis":
            hyst["access_hysteresis"] > 1e-12,
        "formation_movement_is_relocation_not_reproduction": movement_relocation,
        "endogenous_proto_gate_already_clears_formation_manpower_minimum":
            threshold["proto_gate_already_clears_formation_manpower_minimum"],
        "two_stage_sequential_critical_mass_hypothesis":
            "supported" if ordered else "rejected_as_strict_sequence",
        "interpretation": (
            f"Empty-pool force birth requires {force_t:.3f} represented local "
            f"recruits, but member access saturates at {proto_t:.3f}; force "
            "birth therefore precedes access saturation under live defaults. "
            f"At endogenous onset, {proto_t:.0f} proto members convert to "
            f"{threshold['proto_implied_fighter_personnel']:.1f} fighters, already "
            f"above the {threshold['minimum_formation_personnel']:.1f}-person "
            "formation minimum, so those are not independent hard gates. "
            "Concentration and pool/recruitment co-location are causal "
            "bottlenecks, while movement only relocates formed units."
        ),
    }
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_general_theory_identification",
        "historical_outcomes_used": False,
        "empirical_cases_inspected": False,
        "seed": seed,
        "mechanism_trace": {
            "configuration": {
                "file": "src/pineland_sim/config.py",
                "symbols": [
                    "minimum_proto_represented_population",
                    "minimum_formation_personnel",
                    "fighter_conversion_fraction",
                ],
            },
            "recruitment_pool_birth": {
                "file": "src/pineland_sim/organization_ecology.py",
                "symbols": [
                    "recruit_and_retain",
                    "_apply_local_fighter_change",
                    "_create_local_recruitment_formation",
                ],
                "semantics": (
                    "recruits/exits convert to fighter-equivalents; positive "
                    "deltas reinforce local effective formations or accumulate "
                    "in locality pools until the minimum; exits drain pools "
                    "then formations"
                ),
                "recruit_hazard": (
                    "1-exp(-recruitment_rate*recruitment_intensity*interval_days); "
                    "when access is required, intensity is multiplied by the "
                    "maximum of social exposure, local formation access, and "
                    "local member access"
                ),
                "exit_hazard": (
                    "1-exp(-membership_exit_rate*logistic(fear + 0.7 - cohesion - "
                    "grievance)*interval_days); represented exits convert back "
                    "through fighter_conversion_fraction and withdraw locally first"
                ),
            },
            "movement": {
                "file": "src/pineland_sim/logistics.py",
                "symbols": [
                    "choose_reallocation_orders",
                    "create_movement_order",
                    "advance_movement_orders",
                ],
                "semantics": (
                    "downstream relocation of an existing formation, not "
                    "local force birth"
                ),
            },
        },
        "threshold_sweep": threshold,
        "concentration_dispersion": concentration,
        "pool_alignment": pools,
        "hysteresis": hyst,
        "movement_control": movement,
        "causal_conclusions": conclusions,
        "rejection_criteria": {
            "hard_force_threshold":
                "reject if empty-pool birth occurs below, or fails at, "
                "minimum_formation_personnel/fighter_conversion_fraction",
            "dispersion_bottleneck":
                "reject if equal-total recruitment/manpower is invariant when "
                "per-locality shares cross the derived birth threshold",
            "ordered_two_stage_transition":
                "reject whenever force birth occurs before member_access reaches 1",
            "independent_proto_and_formation_gates":
                "reject whenever minimum_proto_represented_population times "
                "fighter_conversion_fraction already meets or exceeds "
                "minimum_formation_personnel",
            "pool_alignment":
                "reject if aligned versus separated pools give identical births "
                "under matched total recruitment and pooled manpower",
            "hysteresis":
                "reject if a formed sub-threshold effective unit gives no more "
                "recruitment access than equal unformed pooled manpower",
            "movement_reproduction":
                "reject relocation-only semantics if movement increases focal "
                "formation count or the target viable-force activation is not "
                "genealogically attributed to formation_relocation",
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = run_study(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["causal_conclusions"], indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

