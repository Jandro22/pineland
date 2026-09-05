"""Exercise spatial-reproduction channels without reading historical outcomes.

This diagnostic deliberately does not modify model equations or inspect Nepal /
Afghanistan target outcomes.  It exposes two live implementation semantics that
matter for local persistence and geographic propagation:

* formation reallocation as a function of the actor's own-side control belief;
* which armed-presence processes actually write decaying microzone memory.

The output is evidence for theory review, not a license to tune either case.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "studies" / "research_program" / "spatial_mechanism_channels.json"

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.logistics import (  # noqa: E402
    choose_reallocation_orders,
    reallocation_destination_score,
    shortest_locality_path,
)
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import (  # noqa: E402
    audit_run_manifest,
    build_run_manifest,
    file_sha256,
)


class MaxWeightRng:
    """Deterministically choose the maximum-weight option and pass command draws."""

    def random(self) -> float:
        return 0.0

    def choices(self, population, weights, k):
        index = max(range(len(weights)), key=weights.__getitem__)
        return [population[index]]


def _world(seed: int):
    config = SimulationConfig(
        agent_count=300,
        locality_count=34,
        horizon_days=1,
        seed=seed,
    )
    config.logistics.reallocation_rate = 1.0
    return generate_pineland(config)


def _formation(world, *, insurgent: bool):
    return next(
        formation for formation in sorted(world.formations.values(), key=lambda item: item.formation_id)
        if (world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT) == insurgent
    )


def _baseline_best_destination(world, formation) -> str:
    maximum_population = max(locality.population for locality in world.localities.values())
    candidates = [locality_id for locality_id in sorted(world.localities)
                  if locality_id != formation.locality_id]

    def noncontrol_utility(locality_id: str) -> float:
        travel_hours = shortest_locality_path(
            world, formation.locality_id, locality_id, formation.mobility
        )[2]
        importance = world.localities[locality_id].population / maximum_population
        return 0.5 * importance - 0.03 * travel_hours

    return max(candidates, key=lambda locality_id: (noncontrol_utility(locality_id), locality_id))


def _choice_with_target_level(base_world, *, insurgent: bool,
                              target: str, target_level: float) -> str | None:
    world = base_world.clone()
    formation = _formation(world, insurgent=insurgent)
    world.movement_orders.clear()
    for other in world.formations.values():
        other.moving = other.formation_id != formation.formation_id
    other_level = 1.0 - target_level
    for locality_id in world.localities:
        if locality_id == formation.locality_id:
            continue
        belief = world.beliefs[(formation.organization_id, locality_id)]
        belief.control_estimate.physical = target_level if locality_id == target else other_level
        belief.confidence = 1.0
    orders = choose_reallocation_orders(world, 0.0, MaxWeightRng())
    if len(orders) != 1:
        return None
    return orders[0].destination_locality_id


def movement_policy_diagnostic(seed: int = 20260904) -> dict:
    world = _world(seed)
    result = {}
    for label, insurgent in (("government", False),):
        formation = _formation(world, insurgent=insurgent)
        target = _baseline_best_destination(world, formation)
        favorable_level, unfavorable_level = 0.0, 1.0
        live_direction = "lower_own_control_increases_reallocation_utility"
        favorable_choice = _choice_with_target_level(
            world, insurgent=insurgent, target=target, target_level=favorable_level
        )
        unfavorable_choice = _choice_with_target_level(
            world, insurgent=insurgent, target=target, target_level=unfavorable_level
        )
        result[label] = {
            "formation_id": formation.formation_id,
            "origin_locality_id": formation.locality_id,
            "controlled_target_locality_id": target,
            "favorable_target_own_control": favorable_level,
            "favorable_choice": favorable_choice,
            "unfavorable_target_own_control": unfavorable_level,
            "unfavorable_choice": unfavorable_choice,
            "target_selected_when_favored": (
                favorable_choice is not None and favorable_choice == target
            ),
            "target_rejected_when_disfavored": (
                unfavorable_choice is not None and unfavorable_choice != target
            ),
            "favorable_choice_available": favorable_choice is not None,
            "unfavorable_choice_available": unfavorable_choice is not None,
            "live_policy_direction": live_direction,
        }

    insurgent = _formation(world, insurgent=True)
    target = _baseline_best_destination(world, insurgent)
    own_belief = world.beliefs[(insurgent.organization_id, target)]
    government_belief = world.control_beliefs[
        (insurgent.organization_id, "government", target)
    ]
    own_belief.control_estimate.physical = 0.0
    own_belief.confidence = 1.0
    government_belief.control_estimate.physical = 0.0
    government_belief.confidence = 1.0
    frontier = reallocation_destination_score(
        world, insurgent, target, footholds={target: 0.0}
    )
    own_belief.control_estimate.physical = 1.0
    stronghold = reallocation_destination_score(
        world, insurgent, target, footholds={target: 0.0}
    )
    own_belief.control_estimate.physical = 0.5
    government_belief.control_estimate.physical = 0.5
    foothold = reallocation_destination_score(
        world, insurgent, target, footholds={target: 1.0}
    )
    cfg = world.config.logistics
    weights = {
        "frontier": cfg.insurgent_frontier_weight,
        "foothold": cfg.insurgent_foothold_weight,
        "stronghold": cfg.insurgent_stronghold_weight,
        "exploration": cfg.reallocation_exploration_weight,
    }
    result["insurgent"] = {
        "formation_id": insurgent.formation_id,
        "controlled_target_locality_id": target,
        "live_policy_direction": "mixed_frontier_foothold_stronghold_exploration",
        "weights": weights,
        "frontier_scenario": frontier,
        "stronghold_scenario": stronghold,
        "foothold_scenario": foothold,
    }
    result["insurgent_mixed_policy_confirmed"] = bool(
        all(value > 0 for value in weights.values())
        and abs(sum(weights.values()) - 1.0) <= 1e-12
        and frontier["frontier"] > 0
        and stronghold["stronghold"] > 0
        and foothold["foothold"] > 0
    )
    result["government_gap_filling_confirmed"] = bool(
        result["government"]["target_selected_when_favored"] and
        result["government"]["target_rejected_when_disfavored"]
    )
    return result


def presence_memory_diagnostic(seed: int = 20260904) -> dict:
    world = _world(seed)
    government_patrol = next(iter(sorted(world.patrols.values(), key=lambda item: item.patrol_id)))
    government_zone_id = government_patrol.current_microzone_id
    government_zone = world.microzones[government_zone_id]
    government_zone.presence_memory.pop("government", None)
    government_zone.presence_updated_at.pop("government", None)
    government_patrol.available_at = 0.0
    government_patrol.presence_accounted_at = 0.0

    engine = ProcessEngine(world, random.Random(seed))
    # Give the patrol a fixed quarter-day of completed dwell. Presence memory
    # is now duration-integrated rather than an event-count impulse.
    world.time = 0.25
    engine.on_patrol(
        "DIAG-GOV-PATROL",
        ScheduledEvent(0.25, 0, 0, "patrol", {"patrol_id": government_patrol.patrol_id}),
    )
    government_memory = government_zone.presence_memory.get("government", 0.0)

    insurgent = _formation(world, insurgent=True)
    insurgent_zone_id = insurgent.current_microzone_id
    insurgent_zone = world.microzones[insurgent_zone_id]
    insurgent_zone.presence_memory.pop("insurgent", None)
    insurgent_zone.presence_updated_at.pop("insurgent", None)
    engine.on_physical_refresh(
        "DIAG-PHYSICAL-REFRESH",
        ScheduledEvent(
            0.25, 0, 1, "physical_refresh",
            {"interval": world.config.intervals.physical_refresh},
        ),
    )
    insurgent_memory = insurgent_zone.presence_memory.get("insurgent", 0.0)
    insurgent_direct_control = insurgent_zone.physical_control.get("insurgent", 0.0)
    insurgent_patrols = [
        patrol.patrol_id for patrol in world.patrols.values()
        if world.organizations[patrol.organization_id].kind is OrganizationKind.INSURGENT
    ]
    asymmetry = bool(
        government_memory > 0 and insurgent_direct_control > 0 and
        insurgent_memory == 0 and not insurgent_patrols
    )
    interpretation = (
        "The diagnostic observed government patrol-written decaying memory without "
        "an equivalent stationary insurgent formation-memory update."
        if asymmetry else
        "The diagnostic did not confirm patrol-memory asymmetry under the current "
        "live implementation; the proposed memory channel requires a matched "
        "synthetic persistence test before interpretation."
    )
    return {
        "government_patrol_id": government_patrol.patrol_id,
        "government_memory_after_patrol": government_memory,
        "insurgent_formation_id": insurgent.formation_id,
        "insurgent_current_microzone_id": insurgent_zone_id,
        "insurgent_direct_physical_control_after_refresh": insurgent_direct_control,
        "insurgent_memory_after_stationary_physical_refresh": insurgent_memory,
        "insurgent_patrol_object_count": len(insurgent_patrols),
        "insurgent_patrol_ids": insurgent_patrols,
        "patrol_memory_channel_asymmetry_confirmed": asymmetry,
        "interpretation": interpretation,
    }


def diagnose(seed: int = 20260904) -> dict:
    movement = movement_policy_diagnostic(seed)
    memory = presence_memory_diagnostic(seed)
    asymmetry = memory["patrol_memory_channel_asymmetry_confirmed"]
    if asymmetry:
        memory_interpretation = (
            "The diagnostic observed government patrol-written decaying memory without "
            "an equivalent stationary insurgent formation-memory update."
        )
        memory_explanation = "government patrols write decaying presence memory while ordinary insurgent formation occupancy does not"
    else:
        memory_interpretation = (
            "The diagnostic did not confirm patrol-memory asymmetry under the current "
            "live implementation; the proposed memory channel requires a matched "
            "synthetic persistence test before interpretation."
        )
        memory_explanation = "patrol-memory asymmetry was not confirmed by the current synthetic diagnostic"
    memory["interpretation"] = memory_interpretation
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_mechanism_diagnostic_not_model_repair",
        "historical_outcomes_used": False,
        "empirical_parameter_fitting": False,
        "core_change_licensed": False,
        "seed": seed,
        "movement_policy": movement,
        "presence_memory": memory,
        "candidate_structural_explanations": [
            "insurgent reallocation mixes frontier opportunity, local footholds, limited stronghold consolidation, and exploration",
            memory_explanation,
        ],
        "scientific_use": (
            "Use these channels in matched synthetic persistence/propagation experiments before any "
            "core change. They do not authorize tuning Nepal or Afghanistan."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    result = diagnose(args.seed)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = build_run_manifest(
        {
            "diagnostic": "spatial_mechanism_channels",
            "schema_version": result["schema_version"],
            "seed": args.seed,
            "historical_outcomes_used": False,
        },
        seeds=[args.seed],
        execution_mode="deterministic_synthetic_mechanism_diagnostic",
        output_schema={"name": "spatial_mechanism_channels", "version": "1.0.0"},
        repo_root=ROOT,
        extra={
            "stage": "synthetic_spatial_mechanism_diagnosis",
            "historical_outcomes_used": False,
            "artifacts": {
                output.relative_to(ROOT).as_posix(): file_sha256(output),
            },
        },
    )
    audit = audit_run_manifest(manifest)
    if not audit["valid"]:
        raise RuntimeError(f"diagnostic manifest failed reproducibility contract: {audit}")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
