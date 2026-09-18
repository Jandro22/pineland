from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


CELLS = ("000", "001")
TIMEPOINTS = ("anchor", "intervention_end", "final")
IDENTITY_EXCLUSIONS = {
    "cell",
    "security_surge",
    "administrative_surge",
    "underground_disruption",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--expected-seeds", type=int, default=16)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("empty replication CSV")

    seeds = sorted({int(row["seed"]) for row in rows})
    observed_cells = sorted({row["cell"] for row in rows})
    observed_timepoints = sorted({row["timepoint"] for row in rows})
    expected_rows = len(seeds) * len(CELLS) * len(TIMEPOINTS)
    key_counts: dict[tuple[int, str, str], int] = {}
    flag_errors: list[dict[str, object]] = []

    for row in rows:
        key = (int(row["seed"]), row["cell"], row["timepoint"])
        key_counts[key] = key_counts.get(key, 0) + 1
        if row["cell"] in CELLS:
            expected = tuple(int(bit) for bit in row["cell"])
            observed = (
                int(row["security_surge"]),
                int(row["administrative_surge"]),
                int(row["underground_disruption"]),
            )
            if expected != observed:
                flag_errors.append(
                    {
                        "seed": int(row["seed"]),
                        "cell": row["cell"],
                        "timepoint": row["timepoint"],
                        "expected": expected,
                        "observed": observed,
                    }
                )

    missing = [
        [seed, cell, timepoint]
        for seed in seeds
        for cell in CELLS
        for timepoint in TIMEPOINTS
        if key_counts.get((seed, cell, timepoint), 0) == 0
    ]
    duplicates = [
        [seed, cell, timepoint, count]
        for (seed, cell, timepoint), count in sorted(key_counts.items())
        if count != 1
    ]

    anchor_identity_failures: list[dict[str, object]] = []
    for seed in seeds:
        baseline = next(
            (
                row
                for row in rows
                if int(row["seed"]) == seed
                and row["cell"] == "000"
                and row["timepoint"] == "anchor"
            ),
            None,
        )
        treatment = next(
            (
                row
                for row in rows
                if int(row["seed"]) == seed
                and row["cell"] == "001"
                and row["timepoint"] == "anchor"
            ),
            None,
        )
        if baseline is None or treatment is None:
            continue
        differences = [
            column
            for column in baseline
            if column not in IDENTITY_EXCLUSIONS
            and baseline[column] != treatment[column]
        ]
        if differences:
            anchor_identity_failures.append(
                {"seed": seed, "differing_columns": differences}
            )

    passed = (
        len(seeds) == args.expected_seeds
        and observed_cells == sorted(CELLS)
        and observed_timepoints == sorted(TIMEPOINTS)
        and len(rows) == expected_rows
        and not missing
        and not duplicates
        and not flag_errors
        and not anchor_identity_failures
    )
    payload = {
        "schema_version": "pineland.coin_underground_durability_integrity.v1",
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "expected_seed_count": args.expected_seeds,
        "row_count": len(rows),
        "expected_row_count": expected_rows,
        "cells": observed_cells,
        "timepoints": observed_timepoints,
        "missing": missing,
        "duplicates": duplicates,
        "factor_flag_errors": flag_errors,
        "anchor_identity_failures": anchor_identity_failures,
        "passed": passed,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
