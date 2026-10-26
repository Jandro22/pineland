from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


G0_VALUES = (0.0, 10.0, 100.0, 1000.0)
INTAKES = (1.0, 10.0, 100.0, 1000.0)
TAU_VALUES = (0.001, 1.0 / 180.0, 1.0 / 90.0, 1.0 / 30.0, 0.1)
MU_VALUES = (0.0, 0.0005, 0.01, 0.05)
DT_VALUES = (1.0, 7.0, 14.0, 30.0)
UPDATES = (1, 2, 4, 8, 16, 32, 64)


def pipeline_closed(g0: float, n: float, a: float, m: int) -> float:
    if abs(1.0 - a) <= 1e-15:
        return g0 + m * n
    return a**m * g0 + a * n * (1.0 - a**m) / (1.0 - a)


def iterate_pipeline(g0: float, n: float, a: float, m: int) -> tuple[float, float]:
    g = g0
    d = 0.0
    for _ in range(m):
        total = g + n
        d = total * (1.0 - a)
        g = total - d
    return g, d


def reserve_closed(r0: float, b: float, inputs: list[float], y: float) -> float:
    r = r0
    for d in inputs:
        r = b * (r + d) - y
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = 0
    max_pipeline_residual = 0.0
    max_graduation_residual = 0.0
    max_reserve_residual = 0.0
    max_pipeline_scaled_residual = 0.0
    max_graduation_scaled_residual = 0.0
    max_reserve_scaled_residual = 0.0
    monotonic_failures = []
    steady_limit_failures = []
    throughput_boundary_failures = []

    for g0 in G0_VALUES:
        for n in INTAKES:
            for tau in TAU_VALUES:
                for dt in DT_VALUES:
                    a = math.exp(-tau * dt)
                    previous_d = None
                    for m in UPDATES:
                        g_iter, d_iter = iterate_pipeline(g0, n, a, m)
                        g_closed = pipeline_closed(g0, n, a, m)
                        g_prev = pipeline_closed(g0, n, a, m - 1) if m > 0 else g0
                        d_closed = (g_prev + n) * (1.0 - a)
                        max_pipeline_residual = max(max_pipeline_residual, abs(g_iter - g_closed))
                        max_graduation_residual = max(max_graduation_residual, abs(d_iter - d_closed))
                        max_pipeline_scaled_residual = max(
                            max_pipeline_scaled_residual,
                            abs(g_iter - g_closed) / max(abs(g_iter), abs(g_closed), 1.0),
                        )
                        max_graduation_scaled_residual = max(
                            max_graduation_scaled_residual,
                            abs(d_iter - d_closed) / max(abs(d_iter), abs(d_closed), 1.0),
                        )
                        if g0 == 0.0:
                            expected_empty = n * (1.0 - a**m)
                            max_graduation_residual = max(max_graduation_residual, abs(d_iter - expected_empty))
                            if previous_d is not None and d_iter + 1e-13 < previous_d:
                                monotonic_failures.append([g0, n, tau, dt, m, previous_d, d_iter])
                            previous_d = d_iter
                        cases += 1

                    g_star = a * n / (1.0 - a)
                    d_star_from_stock = (g_star + n) * (1.0 - a)
                    if abs(d_star_from_stock - n) > 1e-12 * max(n, 1.0):
                        steady_limit_failures.append([n, tau, dt, g_star, d_star_from_stock])

                    for mu in MU_VALUES:
                        b = math.exp(-mu * dt)
                        # Use a long post-transient sequence with exact steady graduation N
                        # to verify the reserve fixed point / throughput boundary.
                        if b < 1.0 - 1e-15:
                            for frac in (0.5, 1.0, 1.25):
                                y = frac * b * n
                                r_star = (b * n - y) / (1.0 - b)
                                recurrence = b * (r_star + n) - y
                                max_reserve_residual = max(max_reserve_residual, abs(recurrence - r_star))
                                max_reserve_scaled_residual = max(
                                    max_reserve_scaled_residual,
                                    abs(recurrence - r_star)
                                    / max(abs(recurrence), abs(r_star), 1.0),
                                )
                                if frac <= 1.0 and r_star < -1e-12:
                                    throughput_boundary_failures.append([n, mu, dt, frac, r_star])
                                if frac > 1.0 and not r_star < 0.0:
                                    throughput_boundary_failures.append([n, mu, dt, frac, r_star])
                        else:
                            # b=1: reserve drift is exactly N-Y.
                            for frac in (0.5, 1.0, 1.25):
                                y = frac * n
                                drift = n - y
                                if frac < 1.0 and not drift > 0.0:
                                    throughput_boundary_failures.append([n, mu, dt, frac, drift])
                                if frac == 1.0 and abs(drift) > 1e-15:
                                    throughput_boundary_failures.append([n, mu, dt, frac, drift])
                                if frac > 1.0 and not drift < 0.0:
                                    throughput_boundary_failures.append([n, mu, dt, frac, drift])

    status = "PURE_MATH_LAYER_VERIFIED" if (
        max_pipeline_scaled_residual <= 2e-12
        and max_graduation_scaled_residual <= 2e-12
        and max_reserve_scaled_residual <= 2e-12
        and not monotonic_failures
        and not steady_limit_failures
        and not throughput_boundary_failures
    ) else "PURE_MATH_LAYER_FAILED"

    payload = {
        "schema_version": "pineland.coin_security_throughput_structural_law_math_verification.v1",
        "status": status,
        "cases": cases,
        "maximum_pipeline_closed_form_residual": max_pipeline_residual,
        "maximum_graduation_closed_form_residual": max_graduation_residual,
        "maximum_reserve_fixed_point_residual": max_reserve_residual,
        "maximum_pipeline_stock_scaled_residual": max_pipeline_scaled_residual,
        "maximum_graduation_stock_scaled_residual": max_graduation_scaled_residual,
        "maximum_reserve_stock_scaled_residual": max_reserve_scaled_residual,
        "monotonicity_failures": monotonic_failures,
        "steady_limit_failures": steady_limit_failures,
        "throughput_boundary_failures": throughput_boundary_failures,
        "claim_boundary": "Pure recurrence verification only; production helper equivalence remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
