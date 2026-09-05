from __future__ import annotations

from dataclasses import dataclass
from .analytics import ensemble_summary
from .config import SimulationConfig
from .generator import generate_pineland
from .simulation import PolicyHook, Simulation


@dataclass(slots=True)
class PairedOutcome:
    seed: int
    baseline: float
    treatment: float
    effect: float


def run_paired_experiment(config: SimulationConfig, treatment: PolicyHook,
                          repetitions: int = 10) -> tuple[list[PairedOutcome], dict[str, float]]:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    outcomes: list[PairedOutcome] = []
    for offset in range(repetitions):
        run_config = SimulationConfig.from_dict(config.to_dict())
        run_config.seed = config.seed + offset
        base_world = generate_pineland(run_config)
        treated_world = base_world.clone()
        baseline = Simulation(base_world).run().world.summary()["mean_government_effective_control"]
        treated = Simulation(treated_world, policy_hook=treatment).run().world.summary()["mean_government_effective_control"]
        outcomes.append(PairedOutcome(run_config.seed, baseline, treated, treated - baseline))
    return outcomes, ensemble_summary([outcome.effect for outcome in outcomes])


def governance_surge(multiplier: float = 1.5, start_day: float = 30, end_day: float = 180) -> PolicyHook:
    applied_at: set[tuple[int, int]] = set()

    def policy(world, time: float) -> None:
        month = int(time // 30)
        key = (id(world), month)
        if start_day <= time <= end_day and key not in applied_at:
            before_stocks = world.tracked_stock_totals()
            world.organizations["government"].resources *= multiplier
            # A surge is an implementation package, not a cash transfer alone:
            # limited technical assistance raises reach and reduces leakage.
            capacity_gain = max(0.0, multiplier - 1.0) * .02
            leakage_reduction = max(0.0, multiplier - 1.0) * .015
            for locality in world.localities.values():
                locality.administrative_capacity = min(1.0, locality.administrative_capacity + capacity_gain)
                locality.governance["leakage"] = max(0.0, locality.governance["leakage"] - leakage_reduction)
            # Policy hooks are explicit exogenous treatments.  Record their
            # stock effect before the next event boundary so global accounting
            # cannot mistake the intervention for unexplained drift.
            world.record_stock_transactions(
                f"POLICY-{month:06d}", "policy_treatment",
                before_stocks, world.tracked_stock_totals(),
            )
            applied_at.add(key)

    return policy
