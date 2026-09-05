"""Calendar-time conversion helpers for recurring stochastic processes."""
from __future__ import annotations

from math import exp


def _exposure(elapsed_days: float, reference_days: float) -> float:
    if elapsed_days < 0:
        raise ValueError("elapsed_days cannot be negative")
    if reference_days <= 0:
        raise ValueError("reference_days must be positive")
    return elapsed_days / reference_days


def reference_probability(
    probability: float,
    elapsed_days: float,
    reference_days: float = 1.0,
    *,
    intensity: float = 1.0,
) -> float:
    """Convert a reference-period Bernoulli probability to an interval."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    if intensity < 0:
        raise ValueError("intensity cannot be negative")
    exposure = _exposure(elapsed_days, reference_days) * intensity
    if probability == 0.0 or exposure == 0.0:
        return 0.0
    if probability == 1.0:
        return 1.0
    return 1.0 - (1.0 - probability) ** exposure


def poisson_probability(
    rate: float,
    elapsed_days: float,
    reference_days: float = 1.0,
    *,
    intensity: float = 1.0,
) -> float:
    """Convert a nonnegative Poisson hazard per reference period."""
    if rate < 0:
        raise ValueError("rate cannot be negative")
    if intensity < 0:
        raise ValueError("intensity cannot be negative")
    exposure = _exposure(elapsed_days, reference_days)
    return 1.0 - exp(-rate * intensity * exposure)


def reference_fraction(
    fraction: float,
    elapsed_days: float,
    reference_days: float = 1.0,
) -> float:
    """Convert a remaining-stock fraction per reference period to elapsed time."""
    return reference_probability(fraction, elapsed_days, reference_days)


def reference_scale(elapsed_days: float, reference_days: float = 1.0) -> float:
    """Linear scale for additive flows defined per reference period."""
    return _exposure(elapsed_days, reference_days)
