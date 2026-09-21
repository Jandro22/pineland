from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


LOSSES = (0.05, 0.1, 0.25, 0.5)
EXPERIENCE = (0.5, 0.9, 1.0)
REPLACEMENT_EXPERIENCE = (0.0, 0.1, 0.5)
INTAKE = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
TRAINING = (1.0 / 180.0, 1.0 / 90.0, 1.0 / 30.0)
ATTRITION = (0.0, 0.0005, 0.01)
INTERVAL = (7.0, 14.0, 30.0)
UPDATES = (1, 2, 4, 8, 16, 32)
BETA = 0.72


def g(e: float) -> float:
    return 0.75 + 0.50 * e


def capability_ratio(loss: float, replacement: float, e: float, er: float) -> float:
    p = 1.0 - loss
    q = g(er) / g(e)
    return (p + replacement) ** (BETA - 1.0) * (p + replacement * q)


def closed_absorbed(intake: float, tau: float, mu: float, dt: float, updates: int, loss: float) -> float:
    a = math.exp(-tau * dt)
    b = math.exp(-mu * dt)
    return min(intake * b * (1.0 - a**updates), loss)


def iterative_absorbed(intake: float, tau: float, mu: float, dt: float, updates: int, loss: float) -> float:
    a = math.exp(-tau * dt)
    b = math.exp(-mu * dt)
    pipeline = intake
    deployed = 0.0
    reserve = 0.0
    for _ in range(updates):
        graduated = pipeline * (1.0 - a)
        pipeline -= graduated
        reserve = (reserve + graduated) * b
        remaining_deficit = max(loss - deployed, 0.0)
        sent = min(reserve, remaining_deficit)
        reserve -= sent
        deployed += sent
    return deployed


def first_refill_interval(intake: float, tau: float, mu: float, dt: float, loss: float):
    a = math.exp(-tau * dt)
    b = math.exp(-mu * dt)
    if loss <= 0.0:
        return 0
    if intake * b <= loss or not (0.0 < a < 1.0):
        return None
    raw = math.log(1.0 - loss / (intake * b)) / math.log(a)
    return math.ceil(raw - 1e-12)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = 0
    max_absorption_residual = 0.0
    max_capability_residual = 0.0
    monotonic_failures = []
    ceiling_failures = []
    refill_formula_failures = []

    for loss in LOSSES:
        for e in EXPERIENCE:
            for er in REPLACEMENT_EXPERIENCE:
                if er > e:
                    continue
                q = g(er) / g(e)
                ceiling = 1.0 - loss * (1.0 - q)
                if er < e and not ceiling < 1.0:
                    ceiling_failures.append([loss, e, er, ceiling])
                for intake in INTAKE:
                    for tau in TRAINING:
                        for mu in ATTRITION:
                            for dt in INTERVAL:
                                previous = None
                                for updates in UPDATES:
                                    closed = closed_absorbed(
                                        intake, tau, mu, dt, updates, loss
                                    )
                                    iterative = iterative_absorbed(
                                        intake, tau, mu, dt, updates, loss
                                    )
                                    max_absorption_residual = max(
                                        max_absorption_residual,
                                        abs(closed - iterative),
                                    )
                                    observed_capability = capability_ratio(
                                        loss, iterative, e, er
                                    )
                                    closed_capability = capability_ratio(
                                        loss, closed, e, er
                                    )
                                    max_capability_residual = max(
                                        max_capability_residual,
                                        abs(observed_capability - closed_capability),
                                    )
                                    if previous is not None and closed + 1e-14 < previous:
                                        monotonic_failures.append(
                                            [loss, e, er, intake, tau, mu, dt, updates]
                                        )
                                    previous = closed
                                    cases += 1

                                predicted_interval = first_refill_interval(
                                    intake, tau, mu, dt, loss
                                )
                                if predicted_interval is not None:
                                    before = (
                                        0.0
                                        if predicted_interval <= 1
                                        else closed_absorbed(
                                            intake,
                                            tau,
                                            mu,
                                            dt,
                                            predicted_interval - 1,
                                            loss,
                                        )
                                    )
                                    at = closed_absorbed(
                                        intake,
                                        tau,
                                        mu,
                                        dt,
                                        predicted_interval,
                                        loss,
                                    )
                                    if not (before < loss - 1e-12 and abs(at - loss) <= 1e-12):
                                        refill_formula_failures.append(
                                            [
                                                loss,
                                                intake,
                                                tau,
                                                mu,
                                                dt,
                                                predicted_interval,
                                                before,
                                                at,
                                            ]
                                        )

    default_tau = 1.0 / 90.0
    default_mu = 0.0005
    default_dt = 14.0
    examples = []
    for loss in (0.1, 0.25):
        for intake in (loss, 2.0 * loss, 0.5):
            refill = first_refill_interval(
                intake, default_tau, default_mu, default_dt, loss
            )
            examples.append(
                {
                    "loss_fraction": loss,
                    "intake_fraction": intake,
                    "headcount_refill_interval": refill,
                    "headcount_refill_days": None if refill is None else refill * default_dt,
                    "authorized_strength_capability_ceiling_E_0_9_E_R_0_1": (
                        1.0 - loss * (1.0 - g(0.1) / g(0.9))
                    ),
                }
            )

    status = (
        "PURE_MATH_LAYER_VERIFIED"
        if (
            max_absorption_residual <= 2e-14
            and max_capability_residual <= 2e-14
            and not monotonic_failures
            and not ceiling_failures
            and not refill_formula_failures
        )
        else "PURE_MATH_LAYER_FAILED"
    )
    payload = {
        "schema_version": "pineland.coin_absorption_capability_ceiling_math_verification.v1",
        "status": status,
        "cases": cases,
        "maximum_absorption_closed_form_residual": max_absorption_residual,
        "maximum_capability_composition_residual": max_capability_residual,
        "monotonicity_failures": monotonic_failures,
        "ceiling_failures": ceiling_failures,
        "refill_formula_failures": refill_formula_failures,
        "default_examples": examples,
        "claim_boundary": "Pure composite-law verification only; production target-cap verification remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
