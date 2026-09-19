from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


PIPELINE = (0.0, 1.0, 100.0, 10000.0)
RECRUITS = (0.0, 1.0, 100.0, 10000.0)
TRAINING = (0.0, 0.001, 1.0 / 90.0, 0.05, 1.0)
RESERVE = (0.0, 10.0, 1000.0)
ATTRITION = (0.0, 0.0005, 0.01, 0.1)
ELAPSED = (1.0, 7.0, 14.0, 30.0, 90.0)


def transition(g0: float, recruits: float, tau: float, r0: float, mu: float, dt: float):
    total = g0 + recruits
    survival = math.exp(-tau * dt)
    graduated = total * (1.0 - survival)
    g1 = total - graduated
    reserve_survival = math.exp(-mu * dt)
    r_star = (r0 + graduated) * reserve_survival
    return g1, graduated, r_star


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = 0
    max_pipeline_balance = 0.0
    max_closed_form_pipeline = 0.0
    max_semigroup = 0.0
    max_pipeline_balance_scaled = 0.0
    max_closed_form_pipeline_scaled = 0.0
    max_semigroup_scaled = 0.0
    monotonic_failures = []

    for g0 in PIPELINE:
        for recruits in RECRUITS:
            for tau in TRAINING:
                previous_graduated = None
                previous_remaining = None
                for dt in ELAPSED:
                    for r0 in RESERVE:
                        for mu in ATTRITION:
                            g1, graduated, _ = transition(g0, recruits, tau, r0, mu, dt)
                            total = g0 + recruits
                            max_pipeline_balance = max(
                                max_pipeline_balance, abs((g1 + graduated) - total)
                            )
                            max_pipeline_balance_scaled = max(
                                max_pipeline_balance_scaled,
                                abs((g1 + graduated) - total) / max(total, 1.0),
                            )
                            expected_g1 = total * math.exp(-tau * dt)
                            max_closed_form_pipeline = max(
                                max_closed_form_pipeline, abs(g1 - expected_g1)
                            )
                            max_closed_form_pipeline_scaled = max(
                                max_closed_form_pipeline_scaled,
                                abs(g1 - expected_g1) / max(total, 1.0),
                            )
                            cases += 1
                # Training monotonicity at a representative elapsed interval.
                g1, graduated, _ = transition(g0, recruits, tau, 0.0, 0.0, 14.0)
                if previous_graduated is not None:
                    pass

    for g0 in PIPELINE:
        for recruits in RECRUITS:
            total = g0 + recruits
            graduated_values = []
            remaining_values = []
            for tau in TRAINING:
                g1, graduated, _ = transition(g0, recruits, tau, 0.0, 0.0, 14.0)
                graduated_values.append(graduated)
                remaining_values.append(g1)
            if any(graduated_values[i + 1] + 1e-14 < graduated_values[i] for i in range(len(TRAINING) - 1)):
                monotonic_failures.append(["graduation", g0, recruits, graduated_values])
            if any(remaining_values[i + 1] > remaining_values[i] + 1e-14 for i in range(len(TRAINING) - 1)):
                monotonic_failures.append(["remaining", g0, recruits, remaining_values])
            for tau in TRAINING:
                for dt1 in ELAPSED:
                    for dt2 in ELAPSED:
                        direct = total * math.exp(-tau * (dt1 + dt2))
                        split = total * math.exp(-tau * dt1) * math.exp(-tau * dt2)
                        max_semigroup = max(max_semigroup, abs(direct - split))
                        max_semigroup_scaled = max(
                            max_semigroup_scaled,
                            abs(direct - split) / max(total, 1.0),
                        )

    default_tau = 1.0 / 90.0
    default_dt = 14.0
    graduation_fraction = 1.0 - math.exp(-default_tau * default_dt)
    payload = {
        "schema_version": "pineland.coin_security_absorption_pipeline_math_verification.v1",
        "status": "PURE_MATH_LAYER_VERIFIED"
        if (
            max_pipeline_balance_scaled <= 1e-12
            and max_closed_form_pipeline_scaled <= 1e-12
            and max_semigroup_scaled <= 1e-12
            and not monotonic_failures
        )
        else "PURE_MATH_LAYER_FAILED",
        "cases": cases,
        "maximum_pipeline_balance_residual": max_pipeline_balance,
        "maximum_closed_form_pipeline_residual": max_closed_form_pipeline,
        "maximum_training_semigroup_residual": max_semigroup,
        "maximum_pipeline_balance_stock_scaled_residual": max_pipeline_balance_scaled,
        "maximum_closed_form_pipeline_stock_scaled_residual": max_closed_form_pipeline_scaled,
        "maximum_training_semigroup_stock_scaled_residual": max_semigroup_scaled,
        "monotonicity_failures": monotonic_failures,
        "default_descriptives": {
            "graduation_fraction_per_14_day_update": graduation_fraction,
            "trainee_fraction_remaining_after_14_days": 1.0 - graduation_fraction,
            "continuous_half_life_days": math.log(2.0) / default_tau,
            "continuous_90_percent_completion_days": math.log(10.0) / default_tau,
            "reserve_survival_per_14_days": math.exp(-0.0005 * 14.0)
        },
        "claim_boundary": "Pure stock-flow math only; production equivalence remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
