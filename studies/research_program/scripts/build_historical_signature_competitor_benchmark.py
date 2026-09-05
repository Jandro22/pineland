"""Compare simple training-only predictors of next-month event activation.

This is an observation-only benchmark for the candidate's local-renewal and
neighbor-exposure terms. It uses a deterministic temporal split, Laplace
smoothed empirical probabilities, and no simulator parameters. Results are
exploratory for cases without preregistered holdout panels and cannot establish
actor-level reproduction or COIN efficacy.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_harmonized_historical_signatures import (  # noqa: E402
    ROOT,
    _case,
    _months,
    _read_gadm_neighbors,
    _read_json_neighbors,
    _read_panel,
    _stratum_values,
    _ref,
)


PROGRAM = ROOT / "studies" / "research_program"
ALPHA = 1.0
TRAIN_FRACTION = 0.70
ROLLING_TRAIN_FRACTIONS = (0.50, 0.60, 0.70)
ROLLING_TEST_FRACTION = 0.10


def _grid(values: dict[tuple[str, str], int], units: list[str], months: list[str]) -> dict[tuple[str, int], bool]:
    index = {month: i for i, month in enumerate(months)}
    return {
        (unit, index[month]): values.get((unit, month), 0) > 0
        for unit in units
        for month in months
    }


def _rate(success: int, total: int) -> float:
    return (success + ALPHA) / (total + 2.0 * ALPHA)


def _fit(records: list[tuple[bool, bool, bool]]) -> dict[str, Any]:
    # records are (local_state, neighbor_exposure, target_state).
    total = len(records)
    success = sum(int(target) for _, _, target in records)
    local: dict[bool, list[int]] = defaultdict(lambda: [0, 0])
    neighbor: dict[bool, list[int]] = defaultdict(lambda: [0, 0])
    joint: dict[tuple[bool, bool], list[int]] = defaultdict(lambda: [0, 0])
    for local_state, neighbor_state, target in records:
        local[local_state][0] += int(target)
        local[local_state][1] += 1
        neighbor[neighbor_state][0] += int(target)
        neighbor[neighbor_state][1] += 1
        joint[(local_state, neighbor_state)][0] += int(target)
        joint[(local_state, neighbor_state)][1] += 1
    return {
        "n": total,
        "baseline": _rate(success, total),
        "local_state": {str(key): _rate(*value) for key, value in local.items()},
        "neighbor_exposure": {str(key): _rate(*value) for key, value in neighbor.items()},
        "local_plus_neighbor": {f"{key[0]}|{key[1]}": _rate(*value) for key, value in joint.items()},
    }


def _predict(fit: dict[str, Any], local_state: bool, neighbor_state: bool) -> dict[str, float]:
    baseline = float(fit["baseline"])
    return {
        "baseline": baseline,
        "local_state": float(fit["local_state"].get(str(local_state), baseline)),
        "neighbor_exposure": float(fit["neighbor_exposure"].get(str(neighbor_state), baseline)),
        "local_plus_neighbor": float(
            fit["local_plus_neighbor"].get(f"{local_state}|{neighbor_state}", baseline)
        ),
    }


def _score(fit: dict[str, Any], records: list[tuple[bool, bool, bool]]) -> dict[str, Any]:
    scores: dict[str, dict[str, float]] = {
        name: {"brier_sum": 0.0, "log_loss_sum": 0.0} for name in (
            "baseline", "local_state", "neighbor_exposure", "local_plus_neighbor"
        )
    }
    for local_state, neighbor_state, target in records:
        predictions = _predict(fit, local_state, neighbor_state)
        y = float(target)
        for name, probability in predictions.items():
            probability = min(max(probability, 1e-12), 1.0 - 1e-12)
            scores[name]["brier_sum"] += (probability - y) ** 2
            scores[name]["log_loss_sum"] += -(y * math.log(probability) + (1.0 - y) * math.log(1.0 - probability))
    n = len(records)
    return {
        name: {
            "brier": value["brier_sum"] / n if n else None,
            "log_loss": value["log_loss_sum"] / n if n else None,
        }
        for name, value in scores.items()
    }


def _records_for_window(
    activity: dict[tuple[str, int], bool],
    neighbors: dict[str, set[str]],
    units: list[str],
    start_target: int,
    end_target: int,
) -> list[tuple[bool, bool, bool]]:
    """Build records whose target months lie in [start_target, end_target)."""
    records: list[tuple[bool, bool, bool]] = []
    for target_index in range(start_target, end_target):
        source_index = target_index - 1
        for unit in units:
            local_state = activity[(unit, source_index)]
            neighbor_state = any(
                activity.get((neighbor, source_index), False)
                for neighbor in neighbors.get(unit, ())
            )
            records.append((local_state, neighbor_state, activity[(unit, target_index)]))
    return records


def _case_result(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    panel = root / spec["panel"]
    topology_path = root / spec["topology"]
    values, event_units, observed, split_counts = _read_panel(panel, spec["case_id"])
    months = _months(min(observed), max(observed))
    neighbors = _read_json_neighbors(topology_path) if spec["topology_type"] == "json" else _read_gadm_neighbors(topology_path)
    units = sorted(neighbors)
    activity = _grid(values, units, months)
    boundary = max(1, int(len(months) * TRAIN_FRACTION))
    train: list[tuple[bool, bool, bool]] = []
    test: list[tuple[bool, bool, bool]] = []
    for target_index in range(1, len(months)):
        source_index = target_index - 1
        for unit in units:
            local_state = activity[(unit, source_index)]
            neighbor_state = any(
                activity.get((neighbor, source_index), False)
                for neighbor in neighbors.get(unit, ())
            )
            record = (local_state, neighbor_state, activity[(unit, target_index)])
            (train if target_index < boundary else test).append(record)
    fit = _fit(train)
    scores = _score(fit, test)
    baseline_brier = scores["baseline"]["brier"]
    lifts = {
        name: None if baseline_brier is None or result["brier"] is None else baseline_brier - result["brier"]
        for name, result in scores.items()
    }
    rolling_windows: list[dict[str, Any]] = []
    rolling_test_span = max(1, int(round(len(months) * ROLLING_TEST_FRACTION)))
    for train_fraction in ROLLING_TRAIN_FRACTIONS:
        rolling_boundary = max(1, min(len(months) - 1, int(len(months) * train_fraction)))
        rolling_end = min(len(months), rolling_boundary + rolling_test_span)
        rolling_train = _records_for_window(activity, neighbors, units, 1, rolling_boundary)
        rolling_test = _records_for_window(activity, neighbors, units, rolling_boundary, rolling_end)
        rolling_fit = _fit(rolling_train)
        rolling_scores = _score(rolling_fit, rolling_test)
        rolling_baseline = rolling_scores["baseline"]["brier"]
        rolling_lifts = {
            name: None if rolling_baseline is None or result["brier"] is None else rolling_baseline - result["brier"]
            for name, result in rolling_scores.items()
        }
        rolling_windows.append(
            {
                "train_fraction": train_fraction,
                "train_end_month_exclusive": months[rolling_boundary],
                "test_end_month_exclusive": months[rolling_end] if rolling_end < len(months) else None,
                "train_records": len(rolling_train),
                "test_records": len(rolling_test),
                "scores": rolling_scores,
                "brier_lift_over_baseline": rolling_lifts,
            }
        )
    rolling_positive_counts = {
        name: sum(
            (window["brier_lift_over_baseline"].get(name) or 0.0) > 0
            for window in rolling_windows
        )
        for name in ("local_state", "neighbor_exposure", "local_plus_neighbor")
    }
    stratum_benchmarks: list[dict[str, Any]] = []
    for stratum, (stratum_values, source_columns) in _stratum_values(panel, spec["case_id"]).items():
        stratum_activity = _grid(stratum_values, units, months)
        stratum_train: list[tuple[bool, bool, bool]] = []
        stratum_test: list[tuple[bool, bool, bool]] = []
        for target_index in range(1, len(months)):
            source_index = target_index - 1
            for unit in units:
                local_state = stratum_activity[(unit, source_index)]
                neighbor_state = any(
                    stratum_activity.get((neighbor, source_index), False)
                    for neighbor in neighbors.get(unit, ())
                )
                record = (local_state, neighbor_state, stratum_activity[(unit, target_index)])
                (stratum_train if target_index < boundary else stratum_test).append(record)
        stratum_fit = _fit(stratum_train)
        stratum_scores = _score(stratum_fit, stratum_test)
        stratum_baseline = stratum_scores["baseline"]["brier"]
        stratum_lifts = {
            name: None if stratum_baseline is None or result["brier"] is None else stratum_baseline - result["brier"]
            for name, result in stratum_scores.items()
        }
        stratum_benchmarks.append(
            {
                "stratum": stratum,
                "source_columns": source_columns,
                "train_records": len(stratum_train),
                "test_records": len(stratum_test),
                "holdout_scores": stratum_scores,
                "brier_lift_over_baseline": stratum_lifts,
                "interpretation": "Case-native event-class sensitivity only; not a common insurgent outcome or actor-identification result.",
            }
        )
    return {
        "case_id": spec["case_id"],
        "split": {
            "type": "deterministic_temporal_holdout",
            "train_fraction": TRAIN_FRACTION,
            "boundary_month": months[boundary],
            "preregistered": False,
            "note": "Exploratory for Colombia and Iraq; not a replacement for their missing frozen case holdouts.",
        },
        "panel_scope": {
            "months": len(months),
            "topology_units": len(units),
            "event_units": len(event_units),
            "unmatched_event_units": sorted(event_units - set(units)),
            "split_counts": dict(split_counts),
        },
        "training_fit": fit,
        "holdout_scores": scores,
        "brier_lift_over_baseline": lifts,
        "rolling_origin": {
            "train_fractions": list(ROLLING_TRAIN_FRACTIONS),
            "test_fraction": ROLLING_TEST_FRACTION,
            "windows": rolling_windows,
            "positive_brier_lift_counts": rolling_positive_counts,
            "note": "Deterministic blocked-prefix sensitivity analysis; not preregistered and not a causal test.",
        },
        "stratum_sensitivity": stratum_benchmarks,
        "provenance": [_ref(panel), _ref(topology_path)],
        "interpretation": "Predictive association only. Local renewal is an observation feature, not identified insurgent reproduction.",
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    specs = [
        {
            "case_id": "nepal_2001_2006",
            "panel": "studies/nepal_2001_2006/data/processed/district_week_panel.csv",
            "topology": "studies/nepal_2001_2006/data/processed/district_adjacency.json",
            "topology_type": "json",
        },
        {
            "case_id": "afghanistan_2004_2021",
            "panel": "studies/afghanistan_2004_2021/data/processed/district_month_panel.csv",
            "topology": "studies/afghanistan_2004_2021/data/processed/district_adjacency.json",
            "topology_type": "json",
        },
        {
            "case_id": "colombia_1984_2016",
            "panel": "studies/colombia_1984_2016/data/processed/ucdp_colombia_1984_2016_geography_month_panel.csv",
            "topology": "studies/colombia_1984_2016/data/raw/gadm41_COL_2.json.zip",
            "topology_type": "gadm",
        },
        {
            "case_id": "iraq_2003_2011",
            "panel": "studies/iraq_2003_2011/data/processed/ucdp_iraq_2003_2011_geography_month_panel.csv",
            "topology": "studies/iraq_2003_2011/data/raw/gadm41_IRQ_2.json.zip",
            "topology_type": "gadm",
        },
    ]
    cases = [_case_result(root, spec) for spec in specs]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "training_only_simple_competitor_benchmark_not_causal",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "simulator_parameter_fitting": False,
        "core_change_licensed": False,
        "models": ["global_baseline", "local_renewal_state", "neighbor_exposure", "local_plus_neighbor"],
        "smoothing": {"method": "Laplace", "alpha": ALPHA},
        "sensitivity_analysis": "rolling_origin_blocked_temporal_prefixes",
        "stratum_sensitivity_definition": "Nepal and Afghanistan receive the same simple-competitor screen within case-native event columns; these are measurement checks, not pooled outcomes.",
        "negative_constraints": [
            "training-only predictive lift does not identify a causal mechanism",
            "violence-only holdout scores cannot establish control or COIN efficacy",
            "a candidate must beat simpler models in frozen, preregistered holdouts in at least two eligible cases",
        ],
        "measurement_limitations": [
            "event-unit persistence is an observation proxy and does not identify actor-level reproduction",
            "unassigned or low-confidence event locations are represented only through the available panel and require assignment-sensitivity analysis",
            "Nepal monthly aggregation mixes weekly source split labels, so this benchmark is exploratory rather than a frozen holdout",
            "case-native event classes differ across the four panels and are not a common insurgent outcome",
        ],
        "cases": cases,
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "These are observation-only exploratory competitors; current-core provenance and complete case measurement joins are still missing.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "historical_signature_competitor_benchmark.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
