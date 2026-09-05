"""Identify the channels that create new insurgent organizational sites.

This is a synthetic, outcome-independent test of a spatial-metapopulation
theory of insurgency.  It distinguishes three processes that are often mixed
together in territorial diagnostics:

1. within-site persistence/deepening of an existing clandestine foothold;
2. between-site colonization of a previously unoccupied locality; and
3. relocation of an already fielded formation.

Matched worlds share the same generated initial state and random seeds.  The
interventions remove cross-local social transmission, domestic person mobility,
or strategic formation reallocation separately and jointly.  No historical
case outcome or target statistic is read by this script.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from trace_locality_activation_genealogy import LocalityActivationTracer  # noqa: E402


OUT = ROOT / "studies" / "research_program" / "colonization_channels.json"
EPS = 1e-12
DEFAULT_SEEDS = (2026090501, 2026090502, 2026090503)

CONDITIONS: dict[str, dict[str, bool]] = {
    "baseline": {},
    "no_cross_local_social": {"cross_local_social": True},
    "no_person_mobility": {"person_mobility": True},
    "no_strategic_force_reallocation": {"force_reallocation": True},
    "no_social_or_person_mobility": {
        "cross_local_social": True,
        "person_mobility": True,
    },
    "no_colonization_transport_channels": {
        "cross_local_social": True,
        "person_mobility": True,
        "force_reallocation": True,
    },
}


def _edge_key(first: str, second: str) -> tuple[str, str]:
    return (first, second) if first < second else (second, first)


def cross_local_social_edge_count(world) -> int:
    return sum(
        world.persons[edge.person_a_id].residence_locality_id
        != world.persons[edge.person_b_id].residence_locality_id
        for edge in world.social_edges.values()
    )


@contextmanager
def suppress_current_cross_local_social_edges(world) -> Iterator[int]:
    """Temporarily remove only ties whose endpoints currently occupy different sites.

    The intervention is applied only while the social-influence process is
    executing.  Other network state, same-locality ties, edge attributes, and
    person attributes remain unchanged.  Re-evaluating residence each social
    tick prevents later civilian mobility from recreating an unmeasured
    cross-local transmission path.
    """
    removed: list[tuple[tuple[str, str], Any]] = []
    for key, edge in list(world.social_edges.items()):
        first = edge.person_a_id
        second = edge.person_b_id
        if (world.persons[first].residence_locality_id
                == world.persons[second].residence_locality_id):
            continue
        removed.append((key, edge))
        del world.social_edges[key]
        if second in world.social_neighbors[first]:
            world.social_neighbors[first].remove(second)
        if first in world.social_neighbors[second]:
            world.social_neighbors[second].remove(first)
    try:
        yield len(removed)
    finally:
        for key, edge in removed:
            world.social_edges[key] = edge
            first = edge.person_a_id
            second = edge.person_b_id
            if second not in world.social_neighbors[first]:
                world.social_neighbors[first].append(second)
            if first not in world.social_neighbors[second]:
                world.social_neighbors[second].append(first)
        for neighbors in world.social_neighbors.values():
            neighbors.sort()


def _episode_duration(row: dict[str, Any], observation_end: float) -> float:
    end = row.get("activation_end_day")
    if end is None:
        end = observation_end
    return max(0.0, float(end) - float(row["activation_day"]))


def site_reproduction_metrics(
    episodes: list[dict[str, Any]],
    parent_edges: list[dict[str, Any]],
    observation_end_day: float,
    *,
    persistence_days: float = 14.0,
    deepening_horizon_days: float = 30.0,
) -> dict[str, Any]:
    """Estimate colonization separately from within-site maturation.

    This is a finite-horizon descriptive estimand, not an asymptotic branching
    ratio.  It intentionally counts every newly occupied locality even when
    parent attribution is unresolved, while reporting attributed cross-local
    parent mass separately.
    """
    footholds = [row for row in episodes if row["channel"] == "member_foothold_present"]
    initial = [row for row in footholds if row["cause"] == "initial_condition"]
    initial_sites = {row["locality_id"] for row in initial}
    colonizations = [
        row for row in footholds
        if row["cause"] != "initial_condition" and row["locality_id"] not in initial_sites
    ]
    first_by_site: dict[str, dict[str, Any]] = {}
    for row in sorted(colonizations, key=lambda item: (item["activation_day"], item["activation_id"])):
        first_by_site.setdefault(row["locality_id"], row)

    access = [row for row in episodes if row["channel"] == "member_access_saturated"]
    fielded = [row for row in episodes if row["channel"] == "fielded_force_viable"]

    def deepened(source: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
        start = float(source["activation_day"])
        return any(
            row["locality_id"] == source["locality_id"]
            and start - EPS <= float(row["activation_day"]) <= start + deepening_horizon_days + EPS
            for row in candidates
        )

    persistence_eligible = [
        row for row in first_by_site.values()
        if observation_end_day + EPS >= float(row["activation_day"]) + persistence_days
    ]
    persistent = [
        row for row in persistence_eligible
        if _episode_duration(row, observation_end_day) + EPS >= persistence_days
    ]
    cross_parent_mass = sum(
        float(edge.get("weight") or 0.0)
        for edge in parent_edges
        if edge.get("child_channel") == "member_foothold_present"
        and edge.get("child_locality_id") not in initial_sites
        and edge.get("parent_locality_id")
        and edge.get("parent_locality_id") != edge.get("child_locality_id")
    )
    colonization_ids = {row["activation_id"] for row in colonizations}
    attributed_colonization_ids = {
        edge["child_activation_id"] for edge in parent_edges
        if edge.get("child_activation_id") in colonization_ids
        and edge.get("parent_activation_id")
    }
    causes = Counter(row["cause"] for row in colonizations)
    roots = len(initial_sites)
    distinct = len(first_by_site)
    return {
        "initial_foothold_sites": roots,
        "initial_foothold_episodes": len(initial),
        "colonization_episodes": len(colonizations),
        "distinct_new_foothold_sites": distinct,
        "finite_horizon_site_colonization_yield": distinct / roots if roots else None,
        "cross_local_parent_edge_mass": cross_parent_mass,
        "parented_colonization_episode_share": (
            len(attributed_colonization_ids) / len(colonization_ids)
            if colonization_ids else None
        ),
        "colonization_causes": dict(sorted(causes.items())),
        "persistence_followup_days": persistence_days,
        "persistence_eligible_new_sites": len(persistence_eligible),
        "persistent_new_sites": len(persistent),
        "new_site_persistence_probability": (
            len(persistent) / len(persistence_eligible) if persistence_eligible else None
        ),
        "deepening_horizon_days": deepening_horizon_days,
        "new_sites_reaching_saturated_access": sum(
            deepened(row, access) for row in first_by_site.values()
        ),
        "new_sites_reaching_fielded_force": sum(
            deepened(row, fielded) for row in first_by_site.values()
        ),
        "new_site_to_access_probability": (
            sum(deepened(row, access) for row in first_by_site.values()) / distinct
            if distinct else None
        ),
        "new_site_to_fielded_force_probability": (
            sum(deepened(row, fielded) for row in first_by_site.values()) / distinct
            if distinct else None
        ),
        "first_colonization_activation_ids": {
            locality: row["activation_id"] for locality, row in sorted(first_by_site.items())
        },
    }


def run_condition(base_world, condition: str, *, until: float) -> dict[str, Any]:
    intervention = CONDITIONS[condition]
    world = deepcopy(base_world)
    if intervention.get("person_mobility"):
        world.config.movement_rate = 0.0
    if intervention.get("force_reallocation"):
        world.config.logistics.reallocation_rate = 0.0

    simulation = Simulation(world)
    simulation.initialize()
    tracer = LocalityActivationTracer(world)
    tracer.initialize(world.time)
    original_execute = simulation.processes.execute
    suppressed_edge_ticks = 0
    suppressed_edge_instances = 0

    def execute(event):
        nonlocal suppressed_edge_ticks, suppressed_edge_instances
        before = tracer.capture()
        if intervention.get("cross_local_social") and event.event_type == "social_influence":
            with suppress_current_cross_local_social_edges(world) as count:
                suppressed_edge_ticks += 1
                suppressed_edge_instances += count
                event_id = original_execute(event)
        else:
            event_id = original_execute(event)
        tracer.observe_transition(before, event.event_type, event_id, world.time)
        return event_id

    simulation.processes.execute = execute
    result = simulation.run(until=until)
    episodes = tracer.finalize(result.stopped_at)
    episode_rows = [
        dict(row) if isinstance(row, dict) else asdict(row)
        for row in episodes
    ]
    parent_edges = tracer.parent_edges()
    metrics = site_reproduction_metrics(
        episode_rows, parent_edges, result.stopped_at,
    )
    metrics.update({
        "condition": condition,
        "seed": world.config.seed,
        "horizon_days": result.stopped_at,
        "events_processed": result.events_processed,
        "intervention": dict(intervention),
        "initial_cross_local_social_edges": cross_local_social_edge_count(base_world),
        "social_suppression_ticks": suppressed_edge_ticks,
        "social_edge_instances_suppressed": suppressed_edge_instances,
        "strategic_reallocation_rate": world.config.logistics.reallocation_rate,
        "person_movement_rate": world.config.movement_rate,
        "gross_formation_relocation_activations": sum(
            row["channel"] == "fielded_force_viable" and row["cause"] == "formation_relocation"
            for row in episode_rows
        ),
    })
    return metrics


def _paired_effects(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_seed: dict[int, dict[str, dict[str, Any]]] = {}
    for row in runs:
        by_seed.setdefault(int(row["seed"]), {})[row["condition"]] = row
    effects: dict[str, Any] = {}
    for condition in CONDITIONS:
        if condition == "baseline":
            continue
        deltas = []
        for seed, rows in sorted(by_seed.items()):
            if "baseline" not in rows or condition not in rows:
                continue
            baseline = rows["baseline"]["distinct_new_foothold_sites"]
            treated = rows[condition]["distinct_new_foothold_sites"]
            deltas.append({
                "seed": seed,
                "baseline_new_sites": baseline,
                "condition_new_sites": treated,
                "lost_new_sites": baseline - treated,
            })
        values = [row["lost_new_sites"] for row in deltas]
        effects[condition] = {
            "paired_runs": deltas,
            "mean_lost_new_sites": statistics.mean(values) if values else None,
            "median_lost_new_sites": statistics.median(values) if values else None,
            "all_pairs_nonnegative": all(value >= 0 for value in values),
        }
    return effects


def run_study(
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    agents: int = 700,
    localities: int = 34,
    days: float = 60.0,
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for seed in seeds:
        config = SimulationConfig(
            agent_count=agents,
            locality_count=localities,
            horizon_days=days,
            seed=seed,
            include_insurgency=True,
            output_mode="ensemble",
        )
        base_world = generate_pineland(config)
        for condition in CONDITIONS:
            runs.append(run_condition(base_world, condition, until=days))

    effects = _paired_effects(runs)
    baseline = [row for row in runs if row["condition"] == "baseline"]
    baseline_yields = [
        row["finite_horizon_site_colonization_yield"] for row in baseline
        if row["finite_horizon_site_colonization_yield"] is not None
    ]
    ranked = sorted(
        (
            (name, values["mean_lost_new_sites"])
            for name, values in effects.items()
            if values["mean_lost_new_sites"] is not None
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_spatial_metapopulation_colonization_identification",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_equations_modified_by_study": False,
        "matched_channel_interventions_applied": True,
        "estimand": {
            "unit": "locality-level armed-member foothold site",
            "colonization": "first noninitial member_foothold_present activation in a locality absent from the initial foothold set",
            "finite_horizon_site_colonization_yield": "distinct new foothold sites / initial foothold sites",
            "relocation": "reported separately and never counted as a new armed-member foothold by itself",
        },
        "design": {
            "seeds": list(seeds),
            "agents": agents,
            "localities": localities,
            "days": days,
            "conditions": CONDITIONS,
            "matched_initial_world_within_seed": True,
        },
        "baseline": {
            "mean_finite_horizon_site_colonization_yield": (
                statistics.mean(baseline_yields) if baseline_yields else None
            ),
            "mean_distinct_new_foothold_sites": statistics.mean(
                row["distinct_new_foothold_sites"] for row in baseline
            ) if baseline else None,
            "mean_new_site_persistence_probability": statistics.mean(
                row["new_site_persistence_probability"] for row in baseline
                if row["new_site_persistence_probability"] is not None
            ) if any(row["new_site_persistence_probability"] is not None for row in baseline) else None,
            "mean_new_site_to_fielded_force_probability": statistics.mean(
                row["new_site_to_fielded_force_probability"] for row in baseline
                if row["new_site_to_fielded_force_probability"] is not None
            ) if any(row["new_site_to_fielded_force_probability"] is not None for row in baseline) else None,
        },
        "paired_channel_effects": effects,
        "channel_ranking_by_mean_lost_new_sites": [
            {"rank": index + 1, "condition": name, "mean_lost_new_sites": value}
            for index, (name, value) in enumerate(ranked)
        ],
        "runs": runs,
        "interpretation_rule": (
            "A positive paired loss under a channel ablation is evidence that the channel contributes "
            "to finite-horizon site colonization. Non-monotone or zero effects are preserved and reject "
            "a simple necessary-channel claim. The study does not tune any rate to produce supercriticality."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--agents", type=int, default=700)
    parser.add_argument("--localities", type=int, default=34)
    parser.add_argument("--days", type=float, default=60.0)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = run_study(
        seeds=tuple(args.seeds), agents=args.agents,
        localities=args.localities, days=args.days,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "baseline": report["baseline"],
        "channel_ranking": report["channel_ranking_by_mean_lost_new_sites"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
