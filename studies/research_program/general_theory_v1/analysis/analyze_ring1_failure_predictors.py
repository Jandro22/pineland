#!/usr/bin/env python3
"""Post-hoc diagnostic of omitted anchor-state mismatch in the ring-1 screen.

This script is intentionally descriptive.  It must not be used to relabel the
already-completed preregistered ring-1 screen.  Its purpose is to nominate
coordinates for an independent fresh development screen.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


RING1_MATCHED = {
    "pre_Mstar",
    "pre_executable_net_transport_pressure",
    "pre_logF",
    "pre_E",
    "pre_C",
    "pre_logKo",
    "pre_NM",
    "pre_L",
    "pre_Kintel",
    "pre_X",
    "pre_S",
    "pre_U",
    "pre_neighbor_transportable_strength",
    "pre_neighbor_rooted_mass",
    "pre_neighbor_recruitment_hazard",
}


def auc_for_failure(values: list[tuple[int, float]]) -> float:
    positive = [v for y, v in values if y == 1]
    negative = [v for y, v in values if y == 0]
    if not positive or not negative:
        return float("nan")
    wins = sum(a > b for a in positive for b in negative)
    ties = sum(a == b for a in positive for b in negative)
    return (wins + 0.5 * ties) / (len(positive) * len(negative))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("equivalence_json", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.csv.open(newline="", encoding="utf-8")))
    result = json.loads(args.equivalence_json.read_text(encoding="utf-8"))
    classification = {
        int(pair["pair_id"]): pair["classification"] for pair in result["pairs"]
    }

    anchors: dict[tuple[int, str], dict[str, str]] = {}
    for row in rows:
        if row["branch"] == "0":
            anchors[(int(row["pair_id"]), row["side"])] = row

    pre_columns = [
        c
        for c in rows[0]
        if c.startswith("pre_") and c not in {"pre_org_active", "pre_active_owner_logF"}
    ]
    scales = {}
    for column in pre_columns:
        values = [float(row[column]) for row in anchors.values()]
        scales[column] = max(statistics.pstdev(values), 1e-12)

    pair_records = []
    for pair_id in sorted(classification):
        left = anchors[(pair_id, "L")]
        right = anchors[(pair_id, "R")]
        normalized_mismatch = {
            column: abs(float(left[column]) - float(right[column])) / scales[column]
            for column in pre_columns
        }
        pair_records.append(
            {
                "pair_id": pair_id,
                "classification": classification[pair_id],
                "failure": classification[pair_id] == "demonstrably_non_equivalent",
                "match_distance": float(left["match_distance"]),
                "normalized_mismatch": normalized_mismatch,
            }
        )

    diagnostics = []
    for column in pre_columns:
        if column in RING1_MATCHED:
            continue
        failed = [
            p["normalized_mismatch"][column]
            for p in pair_records
            if p["failure"]
        ]
        others = [
            p["normalized_mismatch"][column]
            for p in pair_records
            if not p["failure"]
        ]
        auc = auc_for_failure(
            [(int(p["failure"]), p["normalized_mismatch"][column]) for p in pair_records]
        )
        diagnostics.append(
            {
                "coordinate": column,
                "mean_mismatch_failed": statistics.mean(failed),
                "mean_mismatch_other": statistics.mean(others),
                "mean_difference": statistics.mean(failed) - statistics.mean(others),
                "auc_for_failure": auc,
            }
        )
    diagnostics.sort(key=lambda item: item["auc_for_failure"], reverse=True)

    net_hazard_values = []
    for pair in pair_records:
        composite = (
            pair["normalized_mismatch"]["pre_net_transport_pressure"]
            + pair["normalized_mismatch"]["pre_recruitment_hazard"]
        )
        net_hazard_values.append((int(pair["failure"]), composite))

    output = {
        "schema_version": "pineland.ring1_failure_predictors.v1",
        "status": "POST_HOC_DIAGNOSTIC_ONLY",
        "pair_count": len(pair_records),
        "demonstrably_non_equivalent_pairs": sum(p["failure"] for p in pair_records),
        "omitted_coordinate_diagnostics": diagnostics,
        "net_transport_plus_recruitment_hazard_auc_for_failure": auc_for_failure(net_hazard_values),
        "interpretation_guard": (
            "These associations were discovered after inspecting ring-1 outcomes. "
            "They nominate independent fresh tests and are not confirmatory evidence."
        ),
    }
    text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
