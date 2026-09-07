"""Outcome-blind Afghanistan representative-resolution convergence study.

The ladder keeps the 401-district geography and sourced pre-period inputs
fixed while varying only the number of weighted civilian representatives.  It
does not open an outcome panel.  The default horizon is intentionally short;
the same runner can be used for a full pre-registered horizon after runtime
has been profiled.
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(STUDY / "scripts"))

from historical_case import (  # noqa: E402
    HistoricalCoalitionSchedule,
    condition_world,
    load_historical_inputs,
    sample_taliban_spatial_prior,
    sample_security_deployment_prior,
)
from pineland_sim import Simulation, SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.organizational_state import local_organizational_embeddedness  # noqa: E402
from pineland_sim.relations import STATE_SECURITY_KINDS  # noqa: E402


DEFAULT_RESOLUTIONS = (401, 802, 1604, 3208)
DEFAULT_SEEDS = (2026090612, 2026090613)


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average = (index + 1 + end) / 2.0
        for position in range(index, end):
            ranks[ordered[position][0]] = average
        index = end
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    numerator = sum((x - mx) * (y - my) for x, y in zip(rx, ry))
    denominator = math.sqrt(
        sum((x - mx) ** 2 for x in rx) * sum((y - my) ** 2 for y in ry)
    )
    return numerator / denominator if denominator else None


def morans_i(values: dict[str, float], adjacency: dict[str, dict[str, float]]) -> float | None:
    nodes = sorted(values)
    if len(nodes) < 2:
        return None
    mean = sum(values[node] for node in nodes) / len(nodes)
    centered = {node: values[node] - mean for node in nodes}
    denominator = sum(value * value for value in centered.values())
    if denominator <= 0:
        return None
    edges: list[tuple[str, str, float]] = []
    for first in nodes:
        for second, weight in adjacency.get(first, {}).items():
            if first < second and second in values and weight > 0:
                edges.append((first, second, float(weight)))
    total_weight = sum(2.0 * weight for _, _, weight in edges)
    # ``edges`` stores each undirected adjacency once.  Moran's numerator is
    # the ordered sum over i,j, so each stored edge contributes twice, just as
    # the denominator's total weight does.
    numerator = 2.0 * sum(
        weight * centered[first] * centered[second]
        for first, second, weight in edges
    )
    return len(nodes) * numerator / (total_weight * denominator) if total_weight else None


def hhi(counts: dict[str, float]) -> float:
    total = sum(max(0.0, value) for value in counts.values())
    if total <= 0:
        return 0.0
    return sum((max(0.0, value) / total) ** 2 for value in counts.values())


def _province(world, locality_id: str) -> str:
    district_id = world.localities[locality_id].district_id
    return world.district_hierarchy[district_id]["province"]


def _configuration(seed: int, agent_count: int, horizon: float) -> SimulationConfig:
    config = SimulationConfig(
        seed=seed,
        initialization_seed=20040101,
        horizon_days=horizon,
        agent_count=agent_count,
        locality_count=401,
        output_mode="ensemble",
    )
    config.information.observation_retention_days = 90.0
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, horizon]]
    }
    config.foreign_affairs.enabled = False
    config.peace_process.enabled = False
    config.validate()
    return config


def run_one(
    *,
    agent_count: int,
    seed: int,
    horizon: float,
    case: dict,
    inputs: dict,
    prior: dict,
    security_prior: dict | None = None,
) -> dict:
    config = _configuration(seed, agent_count, horizon)
    world = generate_pineland(config, empirical_geography=case)
    condition_world(
        world,
        inputs,
        7500.0,
        taliban_prior=prior,
        security_prior=security_prior,
    )
    initial_formations = set(world.formations)
    schedule = HistoricalCoalitionSchedule(inputs)
    result = Simulation(world, policy_hook=schedule).run()

    locality_event_counts: Counter[str] = Counter()
    province_week_counts: Counter[tuple[str, int]] = Counter()
    for event in world.state_based_events:
        if event.locality_id not in world.localities or not 0 <= event.time < horizon:
            continue
        if (
            "insurgent" not in event.actor_organization_ids
            or not any(
                world.organizations.get(actor) is not None
                and world.organizations[actor].kind in STATE_SECURITY_KINDS
                for actor in event.actor_organization_ids
                if actor != "insurgent"
            )
        ):
            continue
        locality_event_counts[event.locality_id] += 1
        province_week_counts[(_province(world, event.locality_id), int(event.time // 7))] += 1

    recruitment_mass = Counter()
    for person in world.persons.values():
        if (
            person.organization_id == "insurgent"
            and person.armed_fraction > 0
        ):
            recruitment_mass[person.residence_locality_id] += (
                person.weight * person.armed_fraction
            )
    movement_destinations = Counter(
        order.destination_locality_id
        for order in world.movement_orders.values()
        if order.organization_id == "insurgent"
    )
    embeddedness = {
        locality_id: local_organizational_embeddedness(
            world, "insurgent", locality_id
        )
        for locality_id in world.localities
    }
    new_formations = [
        formation for formation_id, formation in world.formations.items()
        if formation_id not in initial_formations
        and formation.organization_id == "insurgent"
    ]
    return {
        "agent_count": agent_count,
        "seed": seed,
        "horizon_days": horizon,
        "events_processed": result.events_processed,
        "state_based_event_rate": sum(locality_event_counts.values()) / max(1.0, horizon),
        "province_week_counts": {
            f"{province}|{week}": count
            for (province, week), count in sorted(province_week_counts.items())
        },
        "locality_event_counts": dict(sorted(locality_event_counts.items())),
        "spatial_concentration_hhi": hhi(locality_event_counts),
        "morans_i_event_intensity": morans_i(
            {locality_id: float(locality_event_counts.get(locality_id, 0))
             for locality_id in world.localities},
            world.adjacency,
        ),
        "locality_reproduction": {
            "new_insurgent_formations": len(new_formations),
            "new_formation_localities": len({item.locality_id for item in new_formations}),
            "local_manpower_pool_localities": len({
                locality_id for (organization_id, locality_id), quantity
                in world.organization_manpower_pools.items()
                if organization_id == "insurgent" and quantity > 0
            }),
        },
        "recruitment_geography": {
            "total_represented_armed_membership": sum(recruitment_mass.values()),
            "locality_hhi": hhi(recruitment_mass),
            "active_localities": sum(value > 0 for value in recruitment_mass.values()),
        },
        "movement_destinations": {
            "orders": sum(movement_destinations.values()),
            "unique_localities": len(movement_destinations),
            "locality_hhi": hhi(movement_destinations),
        },
        "organization_local_embeddedness": {
            "mean": sum(embeddedness.values()) / max(1, len(embeddedness)),
            "maximum": max(embeddedness.values(), default=0.0),
            "active_localities": sum(value > 0 for value in embeddedness.values()),
        },
        "summary": world.summary(),
    }


def _aggregate_probability_field(
    runs: list[dict],
    surface_keys: list[str],
) -> dict[str, float]:
    return {
        key: sum(key in run["province_week_counts"] for run in runs) / len(runs)
        for key in surface_keys
    }


def compare_probability_fields(first: dict[str, float], second: dict[str, float]) -> dict[str, float | None]:
    keys = sorted(set(first) | set(second))
    xs = [first.get(key, 0.0) for key in keys]
    ys = [second.get(key, 0.0) for key in keys]
    return {
        "cells": len(keys),
        "spearman": spearman(xs, ys),
        "mean_absolute_difference": sum(abs(x - y) for x, y in zip(xs, ys)) / max(1, len(xs)),
        "max_absolute_difference": max((abs(x - y) for x, y in zip(xs, ys)), default=0.0),
    }


MECHANISM_METRIC_PATHS = (
    ("state_based_event_rate", 0.10),
    ("recruitment_geography", "total_represented_armed_membership", 0.10),
    ("movement_destinations", "locality_hhi", 0.05),
    ("organization_local_embeddedness", "mean", 0.05),
    ("organization_local_embeddedness", "maximum", 0.05),
)


def _metric_value(run: dict, path: tuple[str, ...] | tuple[str, float]) -> float:
    value: object = run
    for key in path:
        if isinstance(key, float):
            break
        value = value[key]
    return float(value)


def compare_mechanism_metrics(
    first_runs: list[dict],
    second_runs: list[dict],
) -> dict[str, dict[str, float | bool]]:
    """Compare outcome-free hazard/recruitment/movement/embeddedness channels."""
    comparisons: dict[str, dict[str, float | bool]] = {}
    for path in MECHANISM_METRIC_PATHS:
        threshold = float(path[-1]) if isinstance(path[-1], float) else 0.05
        keys = path[:-1] if isinstance(path[-1], float) else path
        first_value = sum(_metric_value(item, keys) for item in first_runs) / max(1, len(first_runs))
        second_value = sum(_metric_value(item, keys) for item in second_runs) / max(1, len(second_runs))
        difference = abs(first_value - second_value)
        scale = max(1.0, abs(first_value), abs(second_value))
        relative_difference = difference / scale
        comparisons[".".join(keys)] = {
            "first": first_value,
            "second": second_value,
            "absolute_difference": difference,
            "relative_difference": relative_difference,
            "converged": relative_difference <= threshold,
        }
    return comparisons


def run_ladder(
    *,
    resolutions: tuple[int, ...] = DEFAULT_RESOLUTIONS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    horizon: float = 30.0,
    output: Path | None = None,
    assessment_horizons: tuple[float, ...] | None = None,
) -> dict:
    if not resolutions or any(count < 401 for count in resolutions):
        raise ValueError("every resolution must be at least the 401-locality geography")
    if not seeds:
        raise ValueError("at least one stochastic seed is required")
    if assessment_horizons is not None:
        horizons = tuple(sorted({float(value) for value in assessment_horizons}))
        if not horizons or any(value <= 0 for value in horizons):
            raise ValueError("assessment horizons must be positive")
        if len(horizons) > 1:
            horizon_results = {
                str(check_horizon): run_ladder(
                    resolutions=resolutions,
                    seeds=seeds,
                    horizon=check_horizon,
                    output=None,
                    assessment_horizons=None,
                )
                for check_horizon in horizons
            }
            primary_key = (
                str(float(horizon))
                if str(float(horizon)) in horizon_results
                else str(horizons[0])
            )
            primary = dict(horizon_results[primary_key])
            primary["assessment_horizons"] = list(horizons)
            primary["multi_horizon_convergence"] = {
                key: {
                    "lowest_converged_resolution": value[
                        "lowest_converged_resolution"
                    ],
                    "resolution_convergence_by_candidate": value[
                        "resolution_convergence_by_candidate"
                    ],
                }
                for key, value in horizon_results.items()
            }
            if output is not None:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(primary, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return primary
    case = json.loads(CASE.read_text(encoding="utf-8"))
    inputs = load_historical_inputs()
    deployment_world = generate_pineland(
        _configuration(2026090614, 401, horizon),
        empirical_geography=case,
    )
    security_prior = sample_security_deployment_prior(
        deployment_world,
        random.Random(2026090615),
    )
    prior = sample_taliban_spatial_prior(
        inputs,
        random.Random(2026090614),
        total_strength=7500.0,
        preperiod_counts=case["preperiod_taliban_state_conflict_counts_2003"],
        preperiod_province_counts=case.get(
            "preperiod_taliban_state_conflict_province_background_counts_2003",
            {},
        ),
        locality_ids=deployment_world.localities,
    )
    provinces = sorted({row["container_ids"]["province"] for row in case["districts"]})
    surface_keys = [
        f"{province}|{week}"
        for week in range(max(1, math.ceil(horizon / 7.0)))
        for province in provinces
    ]
    runs = {
        str(agent_count): [
            run_one(
                agent_count=agent_count,
                seed=seed,
                horizon=horizon,
                case=case,
                inputs=inputs,
                prior=prior,
                security_prior=security_prior,
            )
            for seed in seeds
        ]
        for agent_count in resolutions
    }
    fields = {
        agent_count: _aggregate_probability_field(items, surface_keys)
        for agent_count, items in runs.items()
    }
    sorted_resolutions = sorted(int(value) for value in runs)
    comparisons = []
    mechanism_comparisons = []
    for index, previous in enumerate(sorted_resolutions):
        for current in sorted_resolutions[index + 1:]:
            comparison = compare_probability_fields(
                fields[str(previous)],
                fields[str(current)],
            )
            comparison.update({"from_agent_count": previous, "to_agent_count": current})
            comparison["converged"] = bool(
                comparison["mean_absolute_difference"] <= 0.05
                and (
                    (
                        comparison["spearman"] is not None
                        and comparison["spearman"] >= 0.95
                    )
                    or (
                        comparison["spearman"] is None
                        and comparison["max_absolute_difference"] == 0.0
                    )
                )
            )
            comparisons.append(comparison)
            mechanism = compare_mechanism_metrics(
                runs[str(previous)],
                runs[str(current)],
            )
            mechanism_comparisons.append({
                "from_agent_count": previous,
                "to_agent_count": current,
                "metrics": mechanism,
                "converged": all(
                    bool(item["converged"]) for item in mechanism.values()
                ),
            })
    convergence_by_candidate = []
    lowest_converged = None
    for candidate in sorted_resolutions[:-1]:
        higher = [
            comparison for comparison in comparisons
            if comparison["from_agent_count"] == candidate
        ]
        higher_mechanisms = [
            comparison for comparison in mechanism_comparisons
            if comparison["from_agent_count"] == candidate
        ]
        stable = bool(higher) and bool(higher_mechanisms) and all(
            item["converged"] for item in higher
        ) and all(
            item["converged"] for item in higher_mechanisms
        )
        convergence_by_candidate.append({
            "candidate_agent_count": candidate,
            "stable_vs_all_higher": stable,
            "comparisons": higher,
            "mechanism_comparisons": higher_mechanisms,
        })
        if stable and lowest_converged is None:
            lowest_converged = candidate
    payload = {
        "schema_version": "pineland.afghanistan.resolution_convergence.v2",
        "outcome_blind": True,
        "outcome_panel_read": False,
        "fixed_geography_localities": 401,
        "horizon_days": horizon,
        "assessment_horizons": [horizon],
        "resolutions": sorted_resolutions,
        "seeds": list(seeds),
        "prior_mode": prior["mode"],
        "prior_hyperparameters": prior["hyperparameters"],
        "runs": runs,
        "probability_field_stability": comparisons,
        "mechanism_stability": mechanism_comparisons,
        "resolution_convergence_by_candidate": convergence_by_candidate,
        "convergence_rule": (
            "candidate must meet Spearman >= .95 and mean absolute difference <= .05 "
            "against every sufficiently higher resolution in the ladder"
        ),
        "lowest_converged_resolution": lowest_converged,
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-counts", type=int, nargs="+", default=list(DEFAULT_RESOLUTIONS))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--horizon-days", type=float, default=30.0)
    parser.add_argument(
        "--assessment-horizons",
        type=float,
        nargs="+",
        help="optional outcome-blind horizons to assess jointly",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run_ladder(
        resolutions=tuple(args.agent_counts),
        seeds=tuple(args.seeds),
        horizon=args.horizon_days,
        output=args.output,
        assessment_horizons=(
            tuple(args.assessment_horizons)
            if args.assessment_horizons is not None else None
        ),
    )
    print(json.dumps({
        "output": str(args.output),
        "resolutions": payload["resolutions"],
        "lowest_converged_resolution": payload["lowest_converged_resolution"],
    }))


if __name__ == "__main__":
    main()
