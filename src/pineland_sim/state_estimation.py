"""Generic sequential state-estimation utilities for partially observed worlds.

This module deliberately contains no empirical case data and no model-fitting
logic.  Structural parameters belong to the transition model; particle weights
represent uncertainty about latent *state*.  A study layer must supply its own
predeclared observation likelihood before historical assimilation is allowed.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import exp, isfinite, log
import random
from typing import Callable, Generic, Sequence, TypeVar


StateT = TypeVar("StateT")
ObservationT = TypeVar("ObservationT")


@dataclass(slots=True)
class Particle(Generic[StateT]):
    state: StateT
    log_weight: float = 0.0


def normalize_log_weights(log_weights: Sequence[float]) -> list[float]:
    """Normalize arbitrary log weights without numerical underflow."""
    if not log_weights:
        raise ValueError("cannot normalize an empty particle set")
    finite = [value for value in log_weights if isfinite(value)]
    if not finite:
        return [1.0 / len(log_weights)] * len(log_weights)
    maximum = max(finite)
    scaled = [exp(value - maximum) if isfinite(value) else 0.0
              for value in log_weights]
    total = sum(scaled)
    if total <= 0:
        return [1.0 / len(log_weights)] * len(log_weights)
    return [value / total for value in scaled]


def particle_weights(particles: Sequence[Particle[StateT]]) -> list[float]:
    return normalize_log_weights([particle.log_weight for particle in particles])


def effective_sample_size(weights: Sequence[float]) -> float:
    """Return 1/sum(w^2) after defensively normalizing the supplied weights."""
    if not weights:
        raise ValueError("effective sample size needs at least one weight")
    total = sum(max(0.0, float(weight)) for weight in weights)
    if total <= 0:
        return float(len(weights))
    normalized = [max(0.0, float(weight)) / total for weight in weights]
    return 1.0 / sum(weight * weight for weight in normalized)


def measurement_update(
    particles: Sequence[Particle[StateT]],
    observation: ObservationT,
    log_likelihood: Callable[[StateT, ObservationT], float],
) -> dict[str, float]:
    """Condition particle state weights on one observation.

    The supplied likelihood may inspect latent state but must not mutate it.
    Parameters are never changed by this function.
    """
    if not particles:
        raise ValueError("measurement update needs at least one particle")
    prior = particle_weights(particles)
    for particle, prior_weight in zip(particles, prior):
        likelihood = float(log_likelihood(particle.state, observation))
        particle.log_weight = (
            -float("inf") if prior_weight <= 0 or not isfinite(likelihood)
            else log(prior_weight) + likelihood
        )
    posterior = particle_weights(particles)
    for particle, weight in zip(particles, posterior):
        particle.log_weight = log(weight) if weight > 0 else -float("inf")
    return {
        "prior_ess": effective_sample_size(prior),
        "posterior_ess": effective_sample_size(posterior),
        "maximum_posterior_weight": max(posterior),
    }


def systematic_resample_indices(weights: Sequence[float], rng: random.Random) -> list[int]:
    """Systematic resampling with one random draw and deterministic traversal."""
    if not weights:
        raise ValueError("resampling needs at least one particle")
    total = sum(max(0.0, float(weight)) for weight in weights)
    normalized = (
        [max(0.0, float(weight)) / total for weight in weights]
        if total > 0 else
        [1.0 / len(weights)] * len(weights)
    )
    count = len(normalized)
    start = rng.random() / count
    positions = [start + index / count for index in range(count)]
    indices: list[int] = []
    cumulative = normalized[0]
    source_index = 0
    for position in positions:
        while position > cumulative and source_index < count - 1:
            source_index += 1
            cumulative += normalized[source_index]
        indices.append(source_index)
    return indices


def resample_particles(
    particles: Sequence[Particle[StateT]],
    rng: random.Random,
    *,
    clone_state: Callable[[StateT], StateT] = deepcopy,
) -> tuple[list[Particle[StateT]], dict[str, float | list[int]]]:
    """Resample latent states and reset to an equal-weight posterior ensemble."""
    weights = particle_weights(particles)
    indices = systematic_resample_indices(weights, rng)
    resampled = [
        Particle(clone_state(particles[index].state), 0.0)
        for index in indices
    ]
    return resampled, {
        "ess_before": effective_sample_size(weights),
        "unique_parent_particles": len(set(indices)),
        "parent_indices": indices,
    }


def resample_if_degenerate(
    particles: Sequence[Particle[StateT]],
    rng: random.Random,
    *,
    ess_fraction: float = 0.5,
    clone_state: Callable[[StateT], StateT] = deepcopy,
) -> tuple[list[Particle[StateT]], dict[str, float | bool | list[int]]]:
    """Resample only when ESS falls below a predeclared particle fraction."""
    if not 0 < ess_fraction <= 1:
        raise ValueError("ess_fraction must be in (0, 1]")
    weights = particle_weights(particles)
    ess = effective_sample_size(weights)
    threshold = ess_fraction * len(particles)
    if ess >= threshold:
        return list(particles), {
            "resampled": False,
            "ess_before": ess,
            "threshold": threshold,
            "parent_indices": list(range(len(particles))),
        }
    resampled, diagnostics = resample_particles(
        particles, rng, clone_state=clone_state
    )
    return resampled, {
        "resampled": True,
        "threshold": threshold,
        **diagnostics,
    }
