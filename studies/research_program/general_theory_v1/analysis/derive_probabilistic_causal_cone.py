#!/usr/bin/env python3
"""Derive an analytic upper envelope for movement-mediated graph influence.

Pineland's default command process gives each eligible formation a daily
reallocation probability and evaluates that probability on a fixed command
interval.  With adjacent-only destinations, each successful reallocation can
advance a formation by at most one locality-graph edge.  Therefore the number
of command decisions over a horizon provides a conservative upper bound on
how many graph shells a formation can traverse.

This is deliberately an *upper envelope*, not an empirical propagation
probability: in the real model, ineligibility, command latency, travel time,
supply constraints, destination choice, route interdiction, and moves not
toward the focal locality all reduce realized propagation.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def interval_probability(daily_probability: float, interval_days: float) -> float:
    if daily_probability <= 0.0:
        return 0.0
    if daily_probability >= 1.0:
        return 1.0
    return 1.0 - (1.0 - daily_probability) ** interval_days


def binomial_tail(n: int, p: float, threshold: int) -> float:
    """P[X >= threshold] for X~Binomial(n,p), stable enough for small n."""
    if threshold <= 0:
        return 1.0
    if threshold > n:
        return 0.0
    cdf = sum(
        math.comb(n, k) * (p**k) * ((1.0 - p) ** (n - k))
        for k in range(threshold)
    )
    return max(0.0, min(1.0, 1.0 - cdf))


def minimum_included_radius(n: int, p: float, epsilon: float) -> dict[str, float | int]:
    """Smallest R with P[X >= R+1] <= epsilon.

    If state includes graph shells through R, a source outside that radius
    needs at least R+1 one-edge reallocations to reach the focal locality.
    """
    for radius in range(n + 1):
        tail = binomial_tail(n, p, radius + 1)
        if tail <= epsilon:
            return {"radius": radius, "omitted_influence_upper_bound": tail}
    return {"radius": n, "omitted_influence_upper_bound": 0.0}


def derive(
    daily_probability: float,
    interval_days: float,
    horizons: list[float],
    epsilons: list[float],
    max_shell: int,
) -> dict:
    q = interval_probability(daily_probability, interval_days)
    records = []
    for horizon in horizons:
        opportunities = int(math.floor(horizon / interval_days + 1e-12))
        tails = {
            str(shell): binomial_tail(opportunities, q, shell)
            for shell in range(1, max_shell + 1)
        }
        radii = {
            f"epsilon_{epsilon:g}": minimum_included_radius(opportunities, q, epsilon)
            for epsilon in epsilons
        }
        records.append(
            {
                "horizon_days": horizon,
                "command_opportunities": opportunities,
                "interval_decision_probability": q,
                "expected_decisions_upper_envelope": opportunities * q,
                "probability_at_least_k_decisions": tails,
                "minimum_included_radius_by_tolerance": radii,
            }
        )

    return {
        "schema_version": "pineland.probabilistic_causal_cone.v1",
        "daily_reallocation_probability": daily_probability,
        "command_interval_days": interval_days,
        "destination_scope_assumption": "adjacent",
        "interpretation": (
            "Conservative upper envelope on movement-mediated graph reach. "
            "Actual propagation is weakly slower because the bound treats every "
            "eligible command decision as a successful one-edge move toward the focal locality."
        ),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily-probability", type=float, default=0.04)
    parser.add_argument("--interval-days", type=float, default=0.25)
    parser.add_argument("--horizons", type=float, nargs="+", default=[5, 10, 15, 20, 30, 45, 60])
    parser.add_argument("--epsilons", type=float, nargs="+", default=[0.10, 0.05, 0.01])
    parser.add_argument("--max-shell", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = derive(
        args.daily_probability,
        args.interval_days,
        args.horizons,
        args.epsilons,
        args.max_shell,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
