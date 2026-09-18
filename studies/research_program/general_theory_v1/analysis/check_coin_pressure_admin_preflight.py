from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


TIMEPOINTS = ("anchor", "intervention_end", "final")
THRESHOLDS = {"anchor": 6, "intervention_end": 6, "final": 5}


def value(row: dict[str, str], key: str) -> float:
    return float(row[key])


def viable(row: dict[str, str]) -> bool:
    return (
        int(float(row["canonical_insurgent_active"])) == 1
        and value(row, "canonical_insurgent_capital") > 0.0
        and value(row, "rooted_armed_membership_mass") > 0.0
        and value(row, "fielded_force_personnel") > 0.0
        and value(row, "recruitment_hazard_mass") > 0.0
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.csv_path, newline="", encoding="utf8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("empty preflight CSV")

    cells = sorted({row["cell"] for row in rows})
    if cells != ["000"]:
        raise SystemExit(f"preflight may inspect only cell 000, got {cells}")

    seeds = sorted({int(row["seed"]) for row in rows})
    counts: dict[str, int] = {}
    seed_status: dict[str, dict[int, bool]] = {}
    for timepoint in TIMEPOINTS:
        relevant = [row for row in rows if row["timepoint"] == timepoint]
        by_seed = {int(row["seed"]): viable(row) for row in relevant}
        if sorted(by_seed) != seeds:
            raise SystemExit(
                f"preflight missing seeds at {timepoint}: "
                f"expected={seeds}, observed={sorted(by_seed)}"
            )
        counts[timepoint] = sum(by_seed.values())
        seed_status[timepoint] = by_seed

    gates = {
        timepoint: counts[timepoint] >= THRESHOLDS[timepoint]
        for timepoint in TIMEPOINTS
    }
    payload = {
        "schema_version": "pineland.coin_pressure_admin_preflight.v1",
        "historical_outcomes_used": False,
        "input": str(Path(args.csv_path).as_posix()),
        "seeds": seeds,
        "live_counts": counts,
        "minimum_live_worlds": THRESHOLDS,
        "gates": gates,
        "passed": all(gates.values()),
        "seed_viability": seed_status,
        "rule": "Do not run or inspect full factorial outcomes unless passed=true.",
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if payload["passed"] else 2)


if __name__ == "__main__":
    main()
