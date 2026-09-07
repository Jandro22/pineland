import pytest

from pineland_sim.experimental_methods import (
    AdaptiveBranchBudget,
    AdaptiveParticleBudget,
    ExactEarlyStoppingBound,
    ExperimentalMethodGate,
    jeffreys_bernoulli_probability,
)


def test_jeffreys_probability_matches_nested_filter_contract():
    assert jeffreys_bernoulli_probability(0, 3) == 0.125
    assert jeffreys_bernoulli_probability(3, 3) == 0.875


def test_adaptive_branch_budget_uses_only_mc_precision():
    budget = AdaptiveBranchBudget(
        minimum_branches=3,
        maximum_branches=32,
        target_posterior_sd=0.10,
    )
    assert budget.should_continue(1, 2)
    assert budget.posterior_sd(5, 10) > 0
    assert budget.should_continue(16, 32) is False


def test_adaptive_particle_budget_is_ess_mcse_based():
    budget = AdaptiveParticleBudget(
        minimum_particles=32,
        maximum_particles=256,
        target_probability_mcse=0.05,
    )
    assert budget.needs_more_particles(
        particle_count=16, effective_sample_size=16
    )
    assert not budget.needs_more_particles(
        particle_count=256, effective_sample_size=10
    )
    assert budget.conservative_probability_mcse(100) == 0.05


def test_exact_early_stopping_requires_mathematical_bound():
    bound = ExactEarlyStoppingBound(incumbent=10.0)
    assert bound.cannot_improve(
        partial_objective=8.0, best_possible_remaining=2.0
    )
    assert not bound.cannot_improve(
        partial_objective=7.0, best_possible_remaining=2.0
    )


def test_experimental_gate_blocks_unvalidated_empirical_activation():
    gate = ExperimentalMethodGate("rao_blackwellization")
    with pytest.raises(RuntimeError):
        gate.require_synthetic_validation()
    validated = ExperimentalMethodGate(
        "rao_blackwellization",
        status="synthetic_validated",
        preregistration_id="synthetic-v1",
        validation_sha256="a" * 64,
    )
    validated.require_synthetic_validation()
    with pytest.raises(RuntimeError):
        validated.require_empirical_authorization()
