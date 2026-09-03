from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any

from .config import SimulationConfig
from .generator import generate_pineland
from .networks import network_diagnostics
from .simulation import Simulation


@dataclass(slots=True)
class ScaleResult:
    agent_count: int
    represented_population: float
    mean_government_effective_control: float
    mean_insurgent_effective_control: float
    mean_social_degree: float
    mean_language_compatibility: float
    behavior_shares: dict[str, float]


def _behavior_shares(world) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    population = world.weighted_population()
    for person in world.persons.values():
        totals[person.public_behavior] += person.weight
    return {behavior: value / population for behavior, value in sorted(totals.items())}


def compare_agent_scales(config: SimulationConfig, agent_counts: list[int],
                         horizon_days: float) -> dict[str, Any]:
    """Run a resolution-sensitivity comparison at fixed represented population."""
    if len(agent_counts) < 2 or any(count <= 0 for count in agent_counts):
        raise ValueError("provide at least two positive agent counts")
    results: list[ScaleResult] = []
    for agent_count in agent_counts:
        run_config = SimulationConfig.from_dict(config.to_dict())
        run_config.agent_count = agent_count
        run_config.horizon_days = horizon_days
        world = Simulation(generate_pineland(run_config)).run().world
        summary = world.summary()
        network = network_diagnostics(world)
        results.append(ScaleResult(
            agent_count, world.weighted_population(),
            summary["mean_government_effective_control"],
            summary["mean_insurgent_effective_control"],
            network["mean_degree"], network["mean_language_compatibility"],
            _behavior_shares(world),
        ))
    reference = results[-1]
    comparisons = []
    for result in results[:-1]:
        behaviors = set(result.behavior_shares) | set(reference.behavior_shares)
        comparisons.append({
            "agent_count": result.agent_count,
            "reference_agent_count": reference.agent_count,
            "government_control_difference": (result.mean_government_effective_control -
                                               reference.mean_government_effective_control),
            "insurgent_control_difference": (result.mean_insurgent_effective_control -
                                              reference.mean_insurgent_effective_control),
            "maximum_behavior_share_difference": max(
                abs(result.behavior_shares.get(key, 0) - reference.behavior_shares.get(key, 0))
                for key in behaviors
            ),
        })
    return {"runs": [asdict(result) for result in results], "comparisons": comparisons,
            "interpretation": "Resolution sensitivity diagnostic; similarity is assessed, not assumed."}


def compare_political_onset_ensembles(config: SimulationConfig, agent_counts: list[int],
                                      horizon_days: float, seeds: list[int]) -> dict[str, Any]:
    """Compare political behavior and endogenous onset as distributions by resolution."""
    if len(agent_counts) < 2 or not seeds:
        raise ValueError("provide at least two resolutions and one seed")
    ensembles = []
    for count in agent_counts:
        samples = []
        for seed in seeds:
            run_config = SimulationConfig.from_dict(config.to_dict())
            run_config.agent_count = count
            run_config.seed = seed
            run_config.horizon_days = horizon_days
            world = Simulation(generate_pineland(run_config)).run().world
            samples.append({
                "seed": seed,
                "onset": any(t.transition_type == "birth" for t in world.organization_transitions),
                "armed_share": _behavior_shares(world).get("armed_participation", 0.0),
                "peaceful_share": sum(_behavior_shares(world).get(key, 0.0)
                                      for key in ("party_participation", "civil_society", "protest")),
            })
        ensembles.append({
            "agent_count": count, "samples": samples,
            "onset_probability": sum(sample["onset"] for sample in samples) / len(samples),
            "mean_armed_share": sum(sample["armed_share"] for sample in samples) / len(samples),
            "mean_peaceful_share": sum(sample["peaceful_share"] for sample in samples) / len(samples),
        })
    reference = ensembles[-1]
    return {"ensembles": ensembles, "comparisons": [{
        "agent_count": item["agent_count"],
        "reference_agent_count": reference["agent_count"],
        "onset_probability_difference": item["onset_probability"] - reference["onset_probability"],
        "armed_share_difference": item["mean_armed_share"] - reference["mean_armed_share"],
        "peaceful_share_difference": item["mean_peaceful_share"] - reference["mean_peaceful_share"],
    } for item in ensembles[:-1]],
            "interpretation": "Ensemble distribution diagnostic; individual onset trajectories are not paired as continuous outcomes."}
