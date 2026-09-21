from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXPERIENCE = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
ATTRITION = (0.002, 0.01, 0.03)
EXPOSURE = (0.2, 0.5, 1.0, 1.35)
SHOCKS = (-1.0, -0.25, 0.0, 0.5, 1.0)
ADVANTAGES = (-1.0, -0.25, 0.0, 0.4, 1.0)


def g(e: float) -> float:
    return 0.75 + 0.50 * e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = 0
    max_own_residual = 0.0
    max_opp_residual = 0.0
    max_exchange_residual = 0.0
    monotonic_failures = []

    for e0 in EXPERIENCE:
        for e1 in EXPERIENCE:
            if e1 <= e0:
                continue
            m = g(e1) / g(e0)
            predicted_own = m ** -0.45
            predicted_opp = m ** 0.45
            predicted_exchange = m ** 0.90

            for attrition in ATTRITION:
                for exposure in EXPOSURE:
                    for shock in SHOCKS:
                        for base_advantage in ADVANTAGES:
                            base_own = attrition * exposure * math.exp(
                                -0.45 * base_advantage + shock
                            )
                            base_opp = attrition * exposure * math.exp(
                                0.45 * base_advantage + shock
                            )
                            new_advantage = base_advantage + math.log(m)
                            new_own = attrition * exposure * math.exp(
                                -0.45 * new_advantage + shock
                            )
                            new_opp = attrition * exposure * math.exp(
                                0.45 * new_advantage + shock
                            )
                            own_ratio = new_own / base_own
                            opp_ratio = new_opp / base_opp
                            exchange_ratio = (new_opp / new_own) / (
                                base_opp / base_own
                            )
                            max_own_residual = max(
                                max_own_residual, abs(own_ratio - predicted_own)
                            )
                            max_opp_residual = max(
                                max_opp_residual, abs(opp_ratio - predicted_opp)
                            )
                            max_exchange_residual = max(
                                max_exchange_residual,
                                abs(exchange_ratio - predicted_exchange),
                            )
                            if not (own_ratio < 1.0 and opp_ratio > 1.0 and exchange_ratio > 1.0):
                                monotonic_failures.append(
                                    [e0, e1, attrition, exposure, shock, base_advantage]
                                )
                            cases += 1

    status = (
        "PURE_MATH_LAYER_VERIFIED"
        if (
            max_own_residual <= 1e-14
            and max_opp_residual <= 1e-14
            and max_exchange_residual <= 1e-14
            and not monotonic_failures
        )
        else "PURE_MATH_LAYER_FAILED"
    )
    payload = {
        "schema_version": "pineland.coin_veterancy_exchange_structural_law_math_verification.v1",
        "status": status,
        "cases": cases,
        "maximum_own_loss_multiplier_residual": max_own_residual,
        "maximum_opponent_loss_multiplier_residual": max_opp_residual,
        "maximum_exchange_multiplier_residual": max_exchange_residual,
        "monotonic_failures": monotonic_failures,
        "example_0_1_to_0_9": {
            "capability_ratio": g(0.9)/g(0.1),
            "own_loss_multiplier": (g(0.9)/g(0.1))**-0.45,
            "opponent_loss_multiplier": (g(0.9)/g(0.1))**0.45,
            "exchange_multiplier": (g(0.9)/g(0.1))**0.90
        },
        "claim_boundary": "Pure uncapped combat algebra only; production-equivalence remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload,indent=2)+"\n",encoding="utf8")
    print(json.dumps({
        "status":status,
        "cases":cases,
        "max_own_residual":max_own_residual,
        "max_opp_residual":max_opp_residual,
        "max_exchange_residual":max_exchange_residual,
        "failures":len(monotonic_failures),
        "example":payload["example_0_1_to_0_9"]
    },indent=2))


if __name__ == "__main__":
    main()
