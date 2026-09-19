from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


PERSONNEL = (1.0, 10.0, 100.0, 1000.0, 10000.0)
REPLACEMENTS = (0.001, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)
EXPERIENCE = (0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
REPLACEMENT_EXPERIENCE = (0.0, 0.1, 0.25, 0.5, 0.9)


def update(p: float, e: float, r: float, er: float) -> float:
    return (p * e + r * er) / (p + r)


def deficit(e: float, e_new: float) -> float:
    return 1.0 - (0.75 + 0.50 * e_new) / (0.75 + 0.50 * e)


def closed_form(p: float, e: float, r: float, er: float) -> tuple[float, float]:
    alpha = r / (p + r)
    e_new = e - alpha * (e - er)
    d = 0.50 * alpha * (e - er) / (0.75 + 0.50 * e)
    return e_new, d


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    cases = 0
    maximum_experience_residual = 0.0
    maximum_deficit_residual = 0.0
    convex_hull_failures = []
    sign_failures = []
    monotonic_replacement_failures = []
    monotonic_quality_failures = []

    for p in PERSONNEL:
        for e in EXPERIENCE:
            for er in REPLACEMENT_EXPERIENCE:
                deficits_by_r = []
                for r in REPLACEMENTS:
                    observed_e = update(p, e, r, er)
                    observed_d = deficit(e, observed_e)
                    predicted_e, predicted_d = closed_form(p, e, r, er)
                    maximum_experience_residual = max(
                        maximum_experience_residual, abs(observed_e - predicted_e)
                    )
                    maximum_deficit_residual = max(
                        maximum_deficit_residual, abs(observed_d - predicted_d)
                    )
                    lo, hi = min(e, er), max(e, er)
                    if not (lo - 1e-15 <= observed_e <= hi + 1e-15):
                        convex_hull_failures.append([p, e, r, er, observed_e])
                    if er < e and r > 0 and not (
                        observed_e < e and observed_d > 0
                    ):
                        sign_failures.append([p, e, r, er, observed_e, observed_d])
                    if er == e and not (
                        abs(observed_e - e) <= 1e-15
                        and abs(observed_d) <= 1e-15
                    ):
                        sign_failures.append([p, e, r, er, observed_e, observed_d])
                    deficits_by_r.append(observed_d)
                    cases += 1

                # When replacements are worse, more replacement must increase
                # fixed-headcount veterancy deficit.
                if er < e and any(
                    deficits_by_r[i + 1] <= deficits_by_r[i]
                    for i in range(len(deficits_by_r) - 1)
                ):
                    monotonic_replacement_failures.append(
                        {"P": p, "E": e, "E_R": er, "deficits": deficits_by_r}
                    )

            # At fixed replacement amount and incumbent state, raising recruit
            # experience must weakly lower the deficit.
            for r in REPLACEMENTS:
                valid = [er for er in REPLACEMENT_EXPERIENCE if er <= e]
                ds = [deficit(e, update(p, e, r, er)) for er in valid]
                if any(ds[i + 1] > ds[i] + 1e-15 for i in range(len(ds) - 1)):
                    monotonic_quality_failures.append(
                        {"P": p, "E": e, "R": r, "E_R": valid, "deficits": ds}
                    )

    status = (
        "PURE_MATH_LAYER_VERIFIED"
        if (
            maximum_experience_residual <= 1e-15
            and maximum_deficit_residual <= 1e-15
            and not convex_hull_failures
            and not sign_failures
            and not monotonic_replacement_failures
            and not monotonic_quality_failures
        )
        else "PURE_MATH_LAYER_FAILED"
    )
    payload = {
        "schema_version": "pineland.coin_human_capital_structural_law_math_verification.v1",
        "status": status,
        "cases": cases,
        "maximum_experience_identity_residual": maximum_experience_residual,
        "maximum_capability_deficit_identity_residual": maximum_deficit_residual,
        "convex_hull_failures": convex_hull_failures,
        "sign_failures": sign_failures,
        "replacement_share_monotonicity_failures": monotonic_replacement_failures,
        "replacement_quality_monotonicity_failures": monotonic_quality_failures,
        "claim_boundary": "Pure algebraic verification only; production-equivalence remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "status": status,
        "cases": cases,
        "max_E_residual": maximum_experience_residual,
        "max_D_residual": maximum_deficit_residual,
        "failure_counts": {
            "convex_hull": len(convex_hull_failures),
            "sign": len(sign_failures),
            "replacement_monotonicity": len(monotonic_replacement_failures),
            "quality_monotonicity": len(monotonic_quality_failures)
        }
    }, indent=2))


if __name__ == "__main__":
    main()
