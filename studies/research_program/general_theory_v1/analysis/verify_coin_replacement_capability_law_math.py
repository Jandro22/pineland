from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXPERIENCE = (0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
REPLACEMENT_EXPERIENCE = (0.0, 0.1, 0.25, 0.5, 0.9)
LOSSES = (0.05, 0.1, 0.25, 0.5, 0.75)
REPLACEMENTS = (0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
BETA = 0.72


def g(experience: float) -> float:
    return 0.75 + 0.50 * experience


def closed_ratio(loss: float, replacement: float, experience: float, replacement_experience: float) -> float:
    p = 1.0 - loss
    q = g(replacement_experience) / g(experience)
    return (p + replacement) ** (BETA - 1.0) * (p + replacement * q)


def direct_ratio(loss: float, replacement: float, experience: float, replacement_experience: float) -> float:
    p = 1.0 - loss
    final_personnel = p + replacement
    final_experience = (p * experience + replacement * replacement_experience) / final_personnel
    return final_personnel**BETA * g(final_experience) / g(experience)


def root_for_restoration(loss: float, experience: float, replacement_experience: float) -> float:
    lo = 0.0
    hi = max(1.0, loss)
    while closed_ratio(loss, hi, experience, replacement_experience) < 1.0:
        hi *= 2.0
    for _ in range(160):
        mid = 0.5 * (lo + hi)
        if closed_ratio(loss, mid, experience, replacement_experience) < 1.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cases = 0
    max_identity_residual = 0.0
    max_one_for_one_residual = 0.0
    max_root_residual = 0.0
    monotonic_failures = []
    root_order_failures = []
    roots = []

    for e in EXPERIENCE:
        for er in REPLACEMENT_EXPERIENCE:
            if er > e:
                continue
            q = g(er) / g(e)
            for loss in LOSSES:
                last = None
                for replacement in REPLACEMENTS:
                    observed = direct_ratio(loss, replacement, e, er)
                    predicted = closed_ratio(loss, replacement, e, er)
                    max_identity_residual = max(max_identity_residual, abs(observed - predicted))
                    if last is not None and predicted <= last:
                        monotonic_failures.append([e, er, loss, replacement, last, predicted])
                    last = predicted
                    cases += 1

                one_for_one = closed_ratio(loss, loss, e, er)
                one_for_one_predicted = 1.0 - loss * (1.0 - q)
                max_one_for_one_residual = max(
                    max_one_for_one_residual, abs(one_for_one - one_for_one_predicted)
                )
                root = root_for_restoration(loss, e, er)
                residual = abs(closed_ratio(loss, root, e, er) - 1.0)
                max_root_residual = max(max_root_residual, residual)
                if er < e and not root > loss:
                    root_order_failures.append([e, er, loss, root])
                if er == e and abs(root - loss) > 1e-12:
                    root_order_failures.append([e, er, loss, root])
                roots.append(
                    {
                        "experience": e,
                        "replacement_experience": er,
                        "loss_fraction": loss,
                        "q": q,
                        "one_for_one_capability_ratio": one_for_one,
                        "full_capability_replacement_fraction": root,
                        "replacement_over_losses": root / loss,
                    }
                )

    status = "PURE_MATH_LAYER_VERIFIED" if (
        max_identity_residual <= 1e-14
        and max_one_for_one_residual <= 1e-14
        and max_root_residual <= 1e-12
        and not monotonic_failures
        and not root_order_failures
    ) else "PURE_MATH_LAYER_FAILED"

    default_examples = [
        row for row in roots
        if abs(row["experience"] - 0.9) < 1e-12
        and abs(row["replacement_experience"] - 0.1) < 1e-12
    ]
    payload = {
        "schema_version": "pineland.coin_replacement_capability_structural_law_math_verification.v1",
        "status": status,
        "cases": cases,
        "maximum_closed_form_identity_residual": max_identity_residual,
        "maximum_one_for_one_corollary_residual": max_one_for_one_residual,
        "maximum_full_restoration_root_residual": max_root_residual,
        "monotonicity_failures": monotonic_failures,
        "root_order_failures": root_order_failures,
        "default_E_0_9_replacement_E_0_1": default_examples,
        "claim_boundary": "Pure algebraic verification only; production capability() equivalence remains required for promotion."
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "status": status,
        "cases": cases,
        "max_identity_residual": max_identity_residual,
        "max_one_for_one_residual": max_one_for_one_residual,
        "max_root_residual": max_root_residual,
        "monotonic_failures": len(monotonic_failures),
        "root_order_failures": len(root_order_failures),
        "default_examples": default_examples
    }, indent=2))


if __name__ == "__main__":
    main()
