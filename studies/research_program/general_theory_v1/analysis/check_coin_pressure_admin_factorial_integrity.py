from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


CELLS = ("000", "100", "010", "001", "110", "101", "011", "111")
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
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("empty factorial CSV")

    seeds = sorted({int(row["seed"]) for row in rows})
    cells = sorted({row["cell"] for row in rows})
    timepoints = sorted({row["timepoint"] for row in rows})
    expected_rows = len(seeds) * len(CELLS) * len(TIMEPOINTS)

    key_counts: dict[tuple[int, str, str], int] = {}
    factor_flag_errors: list[dict[str, str]] = []
    for row in rows:
        seed = int(row["seed"])
        cell = row["cell"]
        timepoint = row["timepoint"]
        key = (seed, cell, timepoint)
        key_counts[key] = key_counts.get(key, 0) + 1
        if cell in CELLS:
            expected_flags = tuple(int(bit) for bit in cell)
            observed_flags = (
                int(row["security_surge"]),
                int(row["administrative_surge"]),
                int(row["underground_disruption"]),
            )
            if observed_flags != expected_flags:
                factor_flag_errors.append(
                    {
                        "seed": str(seed),
                        "cell": cell,
                        "timepoint": timepoint,
                        "expected": str(expected_flags),
                        "observed": str(observed_flags),
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
        anchor_rows = {
            row["cell"]: row
            for row in rows
            if int(row["seed"]) == seed and row["timepoint"] == "anchor"
        }
        reference = anchor_rows.get("000")
        if reference is None:
            continue
        compare_columns = [
            column
            for column in reference
            if column not in IDENTITY_EXCLUSIONS
        ]
        for cell, row in sorted(anchor_rows.items()):
            differences = [
                column
                for column in compare_columns
                if row[column] != reference[column]
            ]
            if differences:
                anchor_identity_failures.append(
                    {
                        "seed": seed,
                        "cell": cell,
                        "differing_columns": differences,
                    }
                )

    passed = (
        cells == sorted(CELLS)
        and timepoints == sorted(TIMEPOINTS)
        and len(rows) == expected_rows
        and not missing
        and not duplicates
        and not factor_flag_errors
        and not anchor_identity_failures
    )
    payload = {
        "schema_version": "pineland.coin_pressure_admin_factorial_integrity.v1",
        "input": str(Path(args.csv_path).as_posix()),
        "seed_count": len(seeds),
        "row_count": len(rows),
        "expected_row_count": expected_rows,
        "cells": cells,
        "timepoints": timepoints,
        "missing": missing,
        "duplicates": duplicates,
        "factor_flag_errors": factor_flag_errors,
        "anchor_identity_failures": anchor_identity_failures,
        "passed": passed,
        "rule": (
            "Do not interpret factorial outcomes unless the panel is complete, "
            "factor flags are correct, and every within-seed day-60 anchor clone "
            "is byte-identical across all scientific output columns."
        ),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
