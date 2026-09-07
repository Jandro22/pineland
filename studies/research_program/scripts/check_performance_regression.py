"""Compare two Pineland performance artifacts with explicit tolerances."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _lookup(payload, dotted: str):
    value = payload
    for part in dotted.split("."):
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value[part]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--metric", action="append", required=True)
    parser.add_argument("--max-slowdown", type=float, default=0.10)
    parser.add_argument(
        "--require-true",
        action="append",
        default=[],
        help="candidate dotted path that must evaluate to true",
    )
    args = parser.parse_args()
    if args.max_slowdown < 0:
        raise ValueError("max-slowdown must be nonnegative")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    rows = []
    failed = False
    for dotted in args.metric:
        old = float(_lookup(baseline, dotted))
        new = float(_lookup(candidate, dotted))
        limit = old * (1.0 + args.max_slowdown)
        passed = new <= limit
        failed |= not passed
        rows.append({
            "metric": dotted,
            "baseline": old,
            "candidate": new,
            "maximum_allowed": limit,
            "passed": passed,
        })
    exact_checks = []
    for dotted in args.require_true:
        value = bool(_lookup(candidate, dotted))
        failed |= not value
        exact_checks.append({
            "path": dotted,
            "value": value,
            "passed": value,
        })
    result = {
        "schema_version": "pineland.performance.regression_check.v1",
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "max_slowdown_fraction": args.max_slowdown,
        "metrics": rows,
        "exact_checks": exact_checks,
        "passed": not failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
