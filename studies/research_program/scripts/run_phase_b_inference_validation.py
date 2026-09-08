"""Validate the statistical accelerators in preregistered synthetic worlds."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import exp, isfinite, log, pi, sqrt
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import canonical_sha256, file_sha256, model_sha256  # noqa: E402
from pineland_sim.state_estimation import (  # noqa: E402
    RaoBlackwellizedActivityLikelihood,
    binary_mcse_upper_bound,
)


PROTOCOL_PATH = ROOT / "studies/research_program/phase_b_inference_validation_protocol_v2.json"
PHASE_A_PATH = ROOT / "studies/research_program/phase_a_exactness_battery_v1.json"


def _normal_logpdf(x: float, mean: float, variance: float) -> float:
    return -0.5 * (log(2.0 * pi * variance) + (x - mean) ** 2 / variance)


def _weighted_mean_variance(values: list[float], weights: list[float]) -> tuple[float, float]:
    total = sum(weights)
    normalized = [weight / total for weight in weights]
    mean = sum(weight * value for weight, value in zip(normalized, values))
    variance = sum(weight * (value - mean) ** 2 for weight, value in zip(normalized, values))
    return mean, variance


def _weighted_quantile(values: list[float], weights: list[float], probability: float) -> float:
    pairs = sorted(zip(values, weights))
    total = sum(weight for _, weight in pairs)
    target = max(0.0, min(1.0, probability)) * total
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return value
    return pairs[-1][0]


def _effective_sample_size(weights: list[float]) -> float:
    total = sum(weights)
    normalized = [weight / total for weight in weights]
    return 1.0 / sum(weight * weight for weight in normalized)


def _wilson_interval(successes: int, count: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / count
    z2 = z * z
    denominator = 1.0 + z2 / count
    center = (p + z2 / (2.0 * count)) / denominator
    half = z * sqrt(p * (1.0 - p) / count + z2 / (4.0 * count * count)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def validate_rb(protocol: dict[str, Any]) -> dict[str, Any]:
    likelihood = RaoBlackwellizedActivityLikelihood()
    analytic = []
    for hazard in (0.0, log(2.0), 1.0e-12, 50.0):
        expected = 1.0 - exp(-hazard)
        observed = likelihood.probability_from_hazards((hazard,))
        analytic.append({
            "hazard": hazard,
            "expected": expected,
            "observed": observed,
            "absolute_error": abs(expected - observed),
        })

    rng = random.Random(protocol["seeds"]["rb"])
    errors: list[float] = []
    signed: list[float] = []
    for cell in range(protocol["rb"]["monte_carlo_cells"]):
        hazard = exp(-8.0 + 16.0 * cell / max(1, protocol["rb"]["monte_carlo_cells"] - 1))
        truth = likelihood.probability_from_hazards((hazard,))
        draws = [float(rng.random() < truth) for _ in range(protocol["rb"]["branches_per_cell"])]
        oracle = sum(draws) / len(draws)
        error = truth - oracle
        errors.append(abs(error))
        signed.append(error)
    mae = statistics.fmean(errors)
    p95 = sorted(errors)[int(0.95 * (len(errors) - 1))]
    bias = statistics.fmean(signed)
    rmse = sqrt(statistics.fmean(error * error for error in signed))
    report = {
        "analytic": analytic,
        "monte_carlo": {
            "cells": len(errors),
            "branches_per_cell": protocol["rb"]["branches_per_cell"],
            "mae": mae,
            "absolute_error_p95": p95,
            "mean_signed_bias": bias,
            "rmse": rmse,
            "maximum_absolute_error": max(errors),
        },
    }
    report["passed"] = (
        max(item["absolute_error"] for item in analytic)
        <= protocol["rb"]["analytic_absolute_error"]
        and mae <= protocol["rb"]["mean_absolute_error"]
        and p95 <= protocol["rb"]["absolute_error_p95"]
        and abs(bias) <= protocol["rb"]["absolute_mean_signed_bias"]
    )
    return report


def _gaussian_replicate(
    rng: random.Random,
    particles: int,
    *,
    guided: bool,
    observation: float,
    proposal_variance: float,
) -> dict[str, float | bool]:
    prior_mean, prior_variance = 0.0, 1.0
    observation_variance = 1.0
    posterior_variance = 1.0 / (1.0 / prior_variance + 1.0 / observation_variance)
    posterior_mean = posterior_variance * (prior_mean / prior_variance + observation / observation_variance)
    proposal_mean = posterior_mean if guided else prior_mean
    proposal_variance = proposal_variance if guided else prior_variance
    values: list[float] = []
    log_weights: list[float] = []
    for _ in range(particles):
        value = rng.gauss(proposal_mean, sqrt(proposal_variance))
        values.append(value)
        log_weights.append(
            _normal_logpdf(value, prior_mean, prior_variance)
            + _normal_logpdf(observation, value, observation_variance)
            - _normal_logpdf(value, proposal_mean, proposal_variance)
        )
    maximum = max(log_weights)
    weights = [exp(value - maximum) for value in log_weights]
    mean, variance = _weighted_mean_variance(values, weights)
    interval = (
        _weighted_quantile(values, weights, 0.025),
        _weighted_quantile(values, weights, 0.975),
    )
    truth = rng.gauss(posterior_mean, sqrt(posterior_variance))
    return {
        "mean_error": mean - posterior_mean,
        "variance_relative_error": (variance - posterior_variance) / posterior_variance,
        "ess": _effective_sample_size(weights),
        "covers_truth": interval[0] <= truth <= interval[1],
    }


def validate_guided(protocol: dict[str, Any]) -> dict[str, Any]:
    replicates = protocol["guided"]["replicates"]
    particles = protocol["guided"]["particles"]
    bootstrap = []
    guided = []
    rng = random.Random(protocol["seeds"]["guided"])
    for _ in range(replicates):
        bootstrap.append(_gaussian_replicate(
            rng,
            particles,
            guided=False,
            observation=float(protocol["guided"]["observation"]),
            proposal_variance=float(protocol["guided"]["proposal_variance"]),
        ))
        guided.append(_gaussian_replicate(
            rng,
            particles,
            guided=True,
            observation=float(protocol["guided"]["observation"]),
            proposal_variance=float(protocol["guided"]["proposal_variance"]),
        ))
    posterior_sd = sqrt(0.5)
    bootstrap_ess = [float(item["ess"]) for item in bootstrap]
    guided_ess = [float(item["ess"]) for item in guided]
    ratios = [g / b for g, b in zip(guided_ess, bootstrap_ess)]
    report = {
        "replicates": replicates,
        "particles": particles,
        "bootstrap": {
            "mean_rmse_in_posterior_sd": sqrt(statistics.fmean(float(item["mean_error"]) ** 2 for item in bootstrap)) / posterior_sd,
            "variance_relative_error_median_abs": statistics.median(abs(float(item["variance_relative_error"])) for item in bootstrap),
            "coverage": statistics.fmean(bool(item["covers_truth"]) for item in bootstrap),
            "median_ess": statistics.median(bootstrap_ess),
        },
        "guided": {
            "mean_rmse_in_posterior_sd": sqrt(statistics.fmean(float(item["mean_error"]) ** 2 for item in guided)) / posterior_sd,
            "variance_relative_error_median_abs": statistics.median(abs(float(item["variance_relative_error"])) for item in guided),
            "coverage": statistics.fmean(bool(item["covers_truth"]) for item in guided),
            "median_ess": statistics.median(guided_ess),
        },
        "median_ess_ratio": statistics.median(ratios),
    }
    report["passed"] = (
        report["guided"]["mean_rmse_in_posterior_sd"] <= protocol["guided"]["posterior_mean_rmse_in_posterior_sd"]
        and report["guided"]["variance_relative_error_median_abs"] <= protocol["guided"]["posterior_variance_relative_error"]
        and report["guided"]["coverage"] >= protocol["guided"]["coverage_minimum"]
        and report["median_ess_ratio"] >= protocol["guided"]["ess_ratio_median_minimum"]
    )
    return report


def validate_mcse(protocol: dict[str, Any]) -> dict[str, Any]:
    tolerance = protocol["mcse"]["tolerance"]
    rng = random.Random(protocol["seeds"]["mcse"])
    by_probability: dict[str, dict[str, Any]] = {}
    all_errors: list[float] = []
    all_coverage: list[bool] = []
    for probability in protocol["mcse"]["probabilities"]:
        errors: list[float] = []
        coverage: list[bool] = []
        counts: list[int] = []
        for _ in range(protocol["mcse"]["replicates_per_probability"]):
            values: list[float] = []
            while len(values) < 4096:
                values.append(float(rng.random() < probability))
                if len(values) >= 32 and binary_mcse_upper_bound(values) <= tolerance:
                    break
            estimate = statistics.fmean(values)
            errors.append(abs(estimate - probability))
            low, high = _wilson_interval(int(sum(values)), len(values))
            coverage.append(low <= probability <= high)
            counts.append(len(values))
        all_errors.extend(errors)
        all_coverage.extend(coverage)
        p95 = sorted(errors)[int(0.95 * (len(errors) - 1))]
        by_probability[str(probability)] = {
            "replicates": len(errors),
            "mean_sample_count": statistics.fmean(counts),
            "p95_sample_count": sorted(counts)[int(0.95 * (len(counts) - 1))],
            "rmse": sqrt(statistics.fmean(error * error for error in errors)),
            "absolute_error_p95": p95,
            "coverage": statistics.fmean(coverage),
            "passed": p95 <= protocol["mcse"]["maximum_absolute_error_p95"] and statistics.fmean(coverage) >= protocol["mcse"]["per_regime_coverage_minimum"],
        }
    pooled_rmse = sqrt(statistics.fmean(error * error for error in all_errors))
    pooled_p95 = sorted(all_errors)[int(0.95 * (len(all_errors) - 1))]
    pooled_coverage = statistics.fmean(all_coverage)
    report = {
        "by_probability": by_probability,
        "pooled": {
            "experiments": len(all_errors),
            "rmse": pooled_rmse,
            "absolute_error_p95": pooled_p95,
            "coverage": pooled_coverage,
        },
    }
    report["passed"] = (
        all(item["passed"] for item in by_probability.values())
        and pooled_rmse <= protocol["mcse"]["rmse"]
        and pooled_p95 <= protocol["mcse"]["maximum_absolute_error_p95"]
        and pooled_coverage >= protocol["mcse"]["pooled_coverage_minimum"]
    )
    return report


def validate_combined(protocol: dict[str, Any], rb: dict[str, Any], guided: dict[str, Any], mcse: dict[str, Any]) -> dict[str, Any]:
    """Combine exact RB likelihoods with an importance-corrected proposal.

    The high-cost reference is a prior Monte Carlo integral for the same
    synthetic latent model.  The packed propagation gate is imported from the
    completed Phase-A artifact; this test does not silently substitute the
    scalar synthetic filter for execution equivalence.
    """
    likelihood = RaoBlackwellizedActivityLikelihood()
    rng = random.Random(protocol["seeds"]["combined"])
    errors: list[float] = []
    coverages: list[bool] = []
    for _ in range(protocol["combined"]["worlds"]):
        latent = rng.gauss(0.0, 1.0)
        probability = likelihood.probability_from_hazards((exp(latent),))
        observed = float(rng.random() < probability)
        reference_values: list[float] = []
        reference_weights: list[float] = []
        for _ in range(protocol["combined"]["reference_prior_draws"]):
            value = rng.gauss(0.0, 1.0)
            p = likelihood.probability_from_hazards((exp(value),))
            reference_values.append(value)
            reference_weights.append(p if observed else 1.0 - p)
        reference_mean, _ = _weighted_mean_variance(reference_values, reference_weights)

        proposal_mean = 0.65 if observed else -0.25
        values: list[float] = []
        log_weights: list[float] = []
        for _ in range(protocol["combined"]["particles"]):
            value = rng.gauss(proposal_mean, 1.0)
            p = likelihood.probability_from_hazards((exp(value),))
            log_likelihood = log(max(1.0e-15, p if observed else 1.0 - p))
            log_weights.append(_normal_logpdf(value, 0.0, 1.0) + log_likelihood - _normal_logpdf(value, proposal_mean, 1.0))
            values.append(value)
        maximum = max(log_weights)
        weights = [exp(value - maximum) for value in log_weights]
        estimate, _ = _weighted_mean_variance(values, weights)
        interval = (_weighted_quantile(values, weights, 0.025), _weighted_quantile(values, weights, 0.975))
        errors.append(abs(estimate - reference_mean))
        coverages.append(interval[0] <= latent <= interval[1])
    phase_a = json.loads(PHASE_A_PATH.read_text(encoding="utf-8")) if PHASE_A_PATH.exists() else {"passed": False}
    report = {
        "worlds": len(errors),
        "reference_prior_draws": protocol["combined"]["reference_prior_draws"],
        "posterior_mean_absolute_error_p95": sorted(errors)[int(0.95 * (len(errors) - 1))],
        "posterior_mean_absolute_error_mean": statistics.fmean(errors),
        "latent_interval_coverage": statistics.fmean(coverages),
        "rb_component_passed": rb["passed"],
        "guided_component_passed": guided["passed"],
        "mcse_component_passed": mcse["passed"],
        "packed_propagation_passed": phase_a.get("passed", False),
    }
    report["passed"] = (
        report["posterior_mean_absolute_error_p95"] <= protocol["combined"]["posterior_mean_absolute_error_p95"]
        and report["latent_interval_coverage"] >= protocol["combined"]["latent_interval_coverage_minimum"]
        and all(report[key] for key in ("rb_component_passed", "guided_component_passed", "mcse_component_passed", "packed_propagation_passed"))
    )
    return report


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing validation evidence: {output}")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    rb = validate_rb(protocol)
    guided = validate_guided(protocol)
    mcse = validate_mcse(protocol)
    combined = validate_combined(protocol, rb, guided, mcse)
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_b_inference_validation_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "synthetic_only",
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "protocol_sha256": file_sha256(PROTOCOL_PATH),
            "phase_a_artifact_sha256": file_sha256(PHASE_A_PATH) if PHASE_A_PATH.exists() else None,
            "command": "python studies/research_program/scripts/run_phase_b_inference_validation.py",
        },
        "protocol": protocol,
        "rb": rb,
        "guided": guided,
        "mcse": mcse,
        "combined": combined,
        "passed": bool(rb["passed"] and guided["passed"] and mcse["passed"] and combined["passed"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    result["artifact_sha256"] = canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_b_inference_validation_v2.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({
        "output": str(args.output.resolve()),
        "passed": result["passed"],
        "rb_passed": result["rb"]["passed"],
        "guided_passed": result["guided"]["passed"],
        "mcse_passed": result["mcse"]["passed"],
        "combined_passed": result["combined"]["passed"],
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
