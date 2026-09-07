"""Research-gated computational methods that can change an estimand/kernel.

Nothing in this module is enabled by a normal Simulation or historical runner.
It exists so potentially valuable inference/scheduling accelerators can be
implemented and validated in synthetic worlds without silently changing the
scientific contract of an empirical confrontation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Protocol, Sequence


_VALID_STATUSES = {"disabled", "synthetic_validated", "empirical_authorized"}


@dataclass(frozen=True, slots=True)
class ExperimentalMethodGate:
    method: str
    status: str = "disabled"
    preregistration_id: str | None = None
    validation_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"unknown experimental method status: {self.status}")

    def require_synthetic_validation(self) -> None:
        if self.status not in {"synthetic_validated", "empirical_authorized"}:
            raise RuntimeError(
                f"{self.method} requires preregistered synthetic validation"
            )
        if not self.preregistration_id or not self.validation_sha256:
            raise RuntimeError(
                f"{self.method} validation must be provenance-bound"
            )

    def require_empirical_authorization(self) -> None:
        self.require_synthetic_validation()
        if self.status != "empirical_authorized":
            raise RuntimeError(
                f"{self.method} is not authorized for empirical confrontation"
            )


def jeffreys_bernoulli_probability(successes: int, trials: int) -> float:
    """Finite-Monte-Carlo Bernoulli estimate used by nested branch filters."""
    if trials < 1 or successes < 0 or successes > trials:
        raise ValueError("successes/trials are inconsistent")
    return (successes + 0.5) / (trials + 1.0)


@dataclass(frozen=True, slots=True)
class AdaptiveBranchBudget:
    """Preregistered Monte-Carlo precision rule; never reads historical score."""

    minimum_branches: int = 3
    maximum_branches: int = 64
    target_posterior_sd: float = 0.05

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_branches <= self.maximum_branches:
            raise ValueError("invalid adaptive branch bounds")
        if self.target_posterior_sd <= 0:
            raise ValueError("target_posterior_sd must be positive")

    def posterior_sd(self, successes: int, trials: int) -> float:
        if trials < 1 or not 0 <= successes <= trials:
            raise ValueError("successes/trials are inconsistent")
        alpha = successes + 0.5
        beta = trials - successes + 0.5
        total = alpha + beta
        variance = alpha * beta / (total * total * (total + 1.0))
        return sqrt(variance)

    def should_continue(self, successes: int, trials: int) -> bool:
        if trials < self.minimum_branches:
            return True
        if trials >= self.maximum_branches:
            return False
        return self.posterior_sd(successes, trials) > self.target_posterior_sd


@dataclass(frozen=True, slots=True)
class AdaptiveParticleBudget:
    """ESS-based probability-estimand MCSE rule, independent of fit quality."""

    minimum_particles: int = 32
    maximum_particles: int = 1024
    target_probability_mcse: float = 0.03

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_particles <= self.maximum_particles:
            raise ValueError("invalid adaptive particle bounds")
        if self.target_probability_mcse <= 0:
            raise ValueError("target_probability_mcse must be positive")

    @staticmethod
    def conservative_probability_mcse(effective_sample_size: float) -> float:
        if effective_sample_size <= 0:
            return float("inf")
        # Worst-case Bernoulli variance is p(1-p)=1/4.
        return 0.5 / sqrt(effective_sample_size)

    def needs_more_particles(
        self, *, particle_count: int, effective_sample_size: float
    ) -> bool:
        if particle_count < self.minimum_particles:
            return True
        if particle_count >= self.maximum_particles:
            return False
        return (
            self.conservative_probability_mcse(effective_sample_size)
            > self.target_probability_mcse
        )


@dataclass(frozen=True, slots=True)
class ExactEarlyStoppingBound:
    """Generic branch-and-bound criterion for an additive objective."""

    incumbent: float

    def cannot_improve(
        self, *, partial_objective: float, best_possible_remaining: float
    ) -> bool:
        return partial_objective + best_possible_remaining >= self.incumbent


class AnalyticalLikelihoodKernel(Protocol):
    """A derivable likelihood replacing simulation only after validation."""

    def log_likelihood(self, state: Any, observation: Any) -> float: ...


class RaoBlackwellizedKernel(Protocol):
    """Integrate a tractable latent component instead of sampling it."""

    def marginalized_log_likelihood(
        self, state: Any, observation: Any
    ) -> float: ...


class DirectHazardScheduler(Protocol):
    """Schedule a mathematically equivalent next-event time from a hazard."""

    def next_event_time(self, state: Any, current_time: float) -> float: ...


class MultiFidelityEstimator(Protocol):
    """Low/high fidelity estimator with an explicit correction term."""

    def estimate(self, low_fidelity: Sequence[float], corrections: Sequence[float]) -> float: ...


class SurrogateScreen(Protocol):
    """Screen candidates only; never substitutes for the final fidelity gate."""

    def screen(self, candidate: Any) -> bool: ...


EXPERIMENTAL_METHOD_REGISTRY = {
    "analytical_likelihood": ExperimentalMethodGate("analytical_likelihood"),
    "rao_blackwellization": ExperimentalMethodGate("rao_blackwellization"),
    "adaptive_branch_count": ExperimentalMethodGate("adaptive_branch_count"),
    "adaptive_particle_count": ExperimentalMethodGate("adaptive_particle_count"),
    "exact_early_stopping": ExperimentalMethodGate("exact_early_stopping"),
    "direct_hazard_scheduling": ExperimentalMethodGate("direct_hazard_scheduling"),
    "multifidelity_monte_carlo": ExperimentalMethodGate("multifidelity_monte_carlo"),
    "surrogate_screening": ExperimentalMethodGate("surrogate_screening"),
}
