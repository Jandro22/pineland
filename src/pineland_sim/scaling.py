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
