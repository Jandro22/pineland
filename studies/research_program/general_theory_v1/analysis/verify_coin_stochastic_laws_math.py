from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


ELIGIBLE = (0.05, 0.10, 0.25, 0.50, 0.75, 1.0)
INTENSITIES = (0.01, 0.05, 0.10, 0.25, 0.50, 1.0)
RATE_MULTIPLIERS = (0.03125, 0.0625, 0.125, 0.25)
ELAPSED = (1.0, 7.0, 30.0)
SUBCOHORTS = (5, 20, 50)
DEFAULT_RECRUITMENT_RATE = 0.025

COHESION = (0.2, 0.5, 0.8, 1.0)
LOSSES = (0.0, 0.1, 0.5, 1.0)
SOCIAL = (0.0, 0.25, 0.5, 1.0)
SANCTUARY = (0.0, 0.5, 1.0)
COLLAPSE_BASE_HAZARD = 0.015


def binomial_probability(n: int, k: int, p: float) -> float:
    return math.comb(n, k) * p**k * (1.0 - p) ** (n - k)


def recruitment_moments(
    eligible: float,
    intensity: float,
    rate: float,
    elapsed: float,
    subcohorts: int,
) -> tuple[float, float, float, int]:
    p = 1.0 - math.exp(-max(rate, 0.0) * max(intensity, 0.0) * elapsed)
    available = min(math.ceil(eligible * subcohorts), subcohorts)
    values = []
    probabilities = []
    for recruited in range(available + 1):
        fraction = min(recruited / subcohorts, eligible)
        probability = binomial_probability(available, recruited, p)
        values.append(fraction)
        probabilities.append(probability)
    total_probability = sum(probabilities)
    mean = sum(x * w for x, w in zip(values, probabilities))
    second = sum(x * x * w for x, w in zip(values, probabilities))
    variance = max(second - mean * mean, 0.0)
    return mean, variance, total_probability, available


def collapse_lambda(
    base_hazard: float,
    cohesion: float,
    losses: float,
    social: float,
    sanctuary: float,
) -> float:
    return base_hazard * math.exp(
        2.0 * (1.0 - cohesion)
        + 2.0 * losses
        - 3.0 * social
        - 1.5 * sanctuary
    )


def collapse_probability(rate: float, elapsed: float) -> float:
    return 1.0 - math.exp(-rate * elapsed / 7.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    recruitment_cases = 0
    max_probability_residual = 0.0
    minimum_variance = math.inf
    maximum_mean_minus_eligible = -math.inf
    monotonic_failures: list[dict[str, object]] = []

    for e in ELIGIBLE:
        for n in SUBCOHORTS:
            for dt in ELAPSED:
                for intensity in INTENSITIES:
                    means_by_rate = []
                    for mult in RATE_MULTIPLIERS:
                        rate = DEFAULT_RECRUITMENT_RATE * mult
                        mean, variance, total_probability, _ = recruitment_moments(
                            e, intensity, rate, dt, n
                        )
                        recruitment_cases += 1
                        max_probability_residual = max(
                            max_probability_residual, abs(total_probability - 1.0)
                        )
                        minimum_variance = min(minimum_variance, variance)
                        maximum_mean_minus_eligible = max(
                            maximum_mean_minus_eligible, mean - e
                        )
                        means_by_rate.append(mean)
                    if any(
                        means_by_rate[i + 1] + 1e-15 < means_by_rate[i]
                        for i in range(len(means_by_rate) - 1)
                    ):
                        monotonic_failures.append(
                            {
                                "dimension": "rate",
                                "eligible": e,
                                "subcohorts": n,
                                "elapsed": dt,
                                "intensity": intensity,
                                "means": means_by_rate,
                            }
                        )

    # Intensity and elapsed monotonicity on the same frozen finite-support law.
    for e in ELIGIBLE:
        for n in SUBCOHORTS:
            for mult in RATE_MULTIPLIERS:
                rate = DEFAULT_RECRUITMENT_RATE * mult
                for dt in ELAPSED:
                    means = [
                        recruitment_moments(e, x, rate, dt, n)[0]
                        for x in INTENSITIES
                    ]
                    if any(means[i + 1] + 1e-15 < means[i] for i in range(len(means) - 1)):
                        monotonic_failures.append(
                            {
                                "dimension": "intensity",
                                "eligible": e,
                                "subcohorts": n,
                                "rate_multiplier": mult,
                                "elapsed": dt,
                                "means": means,
                            }
                        )
                for intensity in INTENSITIES:
                    means = [
                        recruitment_moments(e, intensity, rate, dt, n)[0]
                        for dt in ELAPSED
                    ]
                    if any(means[i + 1] + 1e-15 < means[i] for i in range(len(means) - 1)):
                        monotonic_failures.append(
                            {
                                "dimension": "elapsed",
                                "eligible": e,
                                "subcohorts": n,
                                "rate_multiplier": mult,
                                "intensity": intensity,
                                "means": means,
                            }
                        )

    recruitment_mc_cases = [
        (0.05, 0.10, 0.025 * 0.03125, 7.0, 20),
        (0.25, 0.50, 0.025 * 0.125, 7.0, 20),
        (0.75, 1.00, 0.025 * 0.25, 30.0, 20),
        (0.10, 0.25, 0.025 * 0.25, 30.0, 5),
        (0.75, 0.50, 0.025 * 0.125, 30.0, 50),
    ]
    mc_draws = 100_000
    rng = random.Random(2026192200)
    recruitment_mc = []
    for e, intensity, rate, dt, n in recruitment_mc_cases:
        expected_mean, expected_variance, _, available = recruitment_moments(
            e, intensity, rate, dt, n
        )
        p = 1.0 - math.exp(-rate * intensity * dt)
        draws = []
        for _ in range(mc_draws):
            recruited = sum(rng.random() < p for _ in range(available))
            draws.append(min(recruited / n, e))
        observed_mean = sum(draws) / mc_draws
        mean_se = math.sqrt(expected_variance / mc_draws)
        z = (
            0.0
            if mean_se <= 1e-18
            else (observed_mean - expected_mean) / mean_se
        )
        recruitment_mc.append(
            {
                "eligible": e,
                "intensity": intensity,
                "rate": rate,
                "elapsed": dt,
                "subcohorts": n,
                "expected_mean": expected_mean,
                "expected_variance": expected_variance,
                "observed_mean": observed_mean,
                "mean_z": z,
                "passed_6sigma": abs(z) <= 6.0,
            }
        )

    collapse_cases = 0
    semigroup_max_residual = 0.0
    monotonic_collapse_failures: list[dict[str, object]] = []
    for cohesion in COHESION:
        for losses in LOSSES:
            for social in SOCIAL:
                for sanctuary in SANCTUARY:
                    lam = collapse_lambda(
                        COLLAPSE_BASE_HAZARD,
                        cohesion,
                        losses,
                        social,
                        sanctuary,
                    )
                    for dt1 in ELAPSED:
                        for dt2 in ELAPSED:
                            q_total = collapse_probability(lam, dt1 + dt2)
                            q1 = collapse_probability(lam, dt1)
                            q2 = collapse_probability(lam, dt2)
                            residual = abs((1.0 - q_total) - (1.0 - q1) * (1.0 - q2))
                            semigroup_max_residual = max(semigroup_max_residual, residual)
                            collapse_cases += 1

    # Directional monotonicity on frozen state.
    for losses in LOSSES:
        for social in SOCIAL:
            for sanctuary in SANCTUARY:
                qs = [
                    collapse_probability(
                        collapse_lambda(COLLAPSE_BASE_HAZARD, c, losses, social, sanctuary),
                        7.0,
                    )
                    for c in COHESION
                ]
                if any(qs[i + 1] > qs[i] + 1e-15 for i in range(len(qs) - 1)):
                    monotonic_collapse_failures.append({"dimension": "cohesion", "q": qs})
    for cohesion in COHESION:
        for social in SOCIAL:
            for sanctuary in SANCTUARY:
                qs = [
                    collapse_probability(
                        collapse_lambda(COLLAPSE_BASE_HAZARD, cohesion, x, social, sanctuary),
                        7.0,
                    )
                    for x in LOSSES
                ]
                if any(qs[i + 1] + 1e-15 < qs[i] for i in range(len(qs) - 1)):
                    monotonic_collapse_failures.append({"dimension": "losses", "q": qs})
    for cohesion in COHESION:
        for losses in LOSSES:
            for sanctuary in SANCTUARY:
                qs = [
                    collapse_probability(
                        collapse_lambda(COLLAPSE_BASE_HAZARD, cohesion, losses, x, sanctuary),
                        7.0,
                    )
                    for x in SOCIAL
                ]
                if any(qs[i + 1] > qs[i] + 1e-15 for i in range(len(qs) - 1)):
                    monotonic_collapse_failures.append({"dimension": "social", "q": qs})
    for cohesion in COHESION:
        for losses in LOSSES:
            for social in SOCIAL:
                qs = [
                    collapse_probability(
                        collapse_lambda(COLLAPSE_BASE_HAZARD, cohesion, losses, social, x),
                        7.0,
                    )
                    for x in SANCTUARY
                ]
                if any(qs[i + 1] > qs[i] + 1e-15 for i in range(len(qs) - 1)):
                    monotonic_collapse_failures.append({"dimension": "sanctuary", "q": qs})

    collapse_mc_states = [
        (0.2, 1.0, 0.0, 0.0),
        (0.5, 0.5, 0.25, 0.0),
        (0.8, 0.1, 0.5, 0.5),
        (1.0, 0.0, 1.0, 1.0),
    ]
    collapse_mc = []
    rng = random.Random(2026192201)
    for cohesion, losses, social, sanctuary in collapse_mc_states:
        lam = collapse_lambda(
            COLLAPSE_BASE_HAZARD, cohesion, losses, social, sanctuary
        )
        q = collapse_probability(lam, 7.0)
        observed = sum(rng.random() < q for _ in range(mc_draws)) / mc_draws
        se = math.sqrt(max(q * (1.0 - q), 1e-18) / mc_draws)
        z = (observed - q) / se
        collapse_mc.append(
            {
                "cohesion": cohesion,
                "losses": losses,
                "social": social,
                "sanctuary": sanctuary,
                "q": q,
                "observed": observed,
                "z": z,
                "passed_6sigma": abs(z) <= 6.0,
            }
        )

    payload = {
        "schema_version": "pineland.coin_stochastic_laws_math_verification.v1",
        "status": "PURE_MATH_LAYER_VERIFIED"
        if (
            max_probability_residual <= 1e-12
            and minimum_variance >= -1e-15
            and maximum_mean_minus_eligible <= 1e-15
            and not monotonic_failures
            and all(x["passed_6sigma"] for x in recruitment_mc)
            and semigroup_max_residual <= 1e-12
            and not monotonic_collapse_failures
            and all(x["passed_6sigma"] for x in collapse_mc)
        )
        else "PURE_MATH_LAYER_FAILED",
        "recruitment": {
            "grid_cases": recruitment_cases,
            "maximum_probability_sum_residual": max_probability_residual,
            "minimum_variance": minimum_variance,
            "maximum_mean_minus_eligible": maximum_mean_minus_eligible,
            "monotonic_failures": monotonic_failures,
            "monte_carlo_draws_per_case": mc_draws,
            "monte_carlo": recruitment_mc,
        },
        "collapse": {
            "semigroup_cases": collapse_cases,
            "semigroup_maximum_absolute_residual": semigroup_max_residual,
            "monotonic_failures": monotonic_collapse_failures,
            "monte_carlo_draws_per_case": mc_draws,
            "monte_carlo": collapse_mc,
        },
        "claim_boundary": (
            "This verifies the mathematical probability laws stated in the "
            "contract. Production-code promotion still requires helper "
            "refactoring/equivalence tests after the risk-frontier run."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "recruitment_grid_cases": recruitment_cases,
                "recruitment_max_probability_residual": max_probability_residual,
                "recruitment_mc_max_abs_z": max(abs(x["mean_z"]) for x in recruitment_mc),
                "collapse_semigroup_cases": collapse_cases,
                "collapse_semigroup_max_residual": semigroup_max_residual,
                "collapse_mc_max_abs_z": max(abs(x["z"]) for x in collapse_mc),
                "recruitment_monotonic_failures": len(monotonic_failures),
                "collapse_monotonic_failures": len(monotonic_collapse_failures),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
