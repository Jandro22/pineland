#!/usr/bin/env python3
"""Exploratory conditional-autonomy classifier for Stage-3 partner-force runs.

This is deliberately post-freeze exploratory analysis. It does not alter the
preregistered Stage-3 estimands or acceptance gates. Its purpose is to separate
four substantively different outcomes among worlds where continued support has
an initially positive capability effect:

* productive_autonomy: capability and indigenous autonomy both improve;
* dependency_gain: capability improves while indigenous autonomy falls;
* contraction_autonomy: autonomy ratio improves while capability falls;
* double_harm: both capability and autonomy fall.

The autonomy coordinate is the Lean-aligned indigenous mission-scale ratio q,
capped at 1 for comparisons because surplus service above mission demand does
not make a force "more than autonomous" for this classification.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


EPS = 1.0e-6
PROFILE_TARGET = {
    "forcegen_heavy": "forcegen",
    "logistics_heavy": "logistics",
    "command_heavy": "command",
}


def _f(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return math.nan


def classify(delta_q: float, delta_capability: float) -> str:
    if delta_q > EPS and delta_capability > EPS:
        return "productive_autonomy"
    if delta_q < -EPS and delta_capability > EPS:
        return "dependency_gain"
    if delta_q > EPS and delta_capability < -EPS:
        return "contraction_autonomy"
    if delta_q < -EPS and delta_capability < -EPS:
        return "double_harm"
    return "mixed_or_flat"


def load_world(primary_path: Path, expected_commit: str | None) -> dict | None:
    trajectory_path = primary_path.with_name(primary_path.stem + ".trajectory.csv")
    if not trajectory_path.exists():
        return None
    with primary_path.open(newline="", encoding="utf-8") as handle:
        primary = list(csv.DictReader(handle))
    with trajectory_path.open(newline="", encoding="utf-8") as handle:
        trajectory = list(csv.DictReader(handle))
    if not primary or not trajectory:
        return None
    commit = primary[0].get("git_commit", "")
    if expected_commit and commit != expected_commit:
        return None

    by_time: dict[float, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in trajectory:
        if row.get("phase") not in {"SUPPORT_ON", "SUPPORT_OFF"}:
            continue
        try:
            time = float(row["days_from_withdrawal"])
        except (KeyError, ValueError):
            continue
        by_time[time][row["phase"]] = row

    if not all(t in by_time and len(by_time[t]) == 2 for t in (30.0, 360.0)):
        return None
    on30, off30 = by_time[30.0]["SUPPORT_ON"], by_time[30.0]["SUPPORT_OFF"]
    on360, off360 = by_time[360.0]["SUPPORT_ON"], by_time[360.0]["SUPPORT_OFF"]
    cap30 = _f(on30, "composite_capability") - _f(off30, "composite_capability")
    cap360 = _f(on360, "composite_capability") - _f(off360, "composite_capability")
    q_on = _f(on360, "interval_formal_q_indigenous")
    q_off = _f(off360, "interval_formal_q_indigenous")
    if not all(math.isfinite(v) for v in (cap30, cap360, q_on, q_off)) or q_on < 0 or q_off < 0:
        return None
    delta_q = min(q_on, 1.0) - min(q_off, 1.0)

    on_primary = next(
        (
            row
            for row in primary
            if row.get("branch") == "SUPPORT_ON" and abs(_f(row, "horizon_days") - 360.0) < 1e-9
        ),
        None,
    )
    if on_primary is None:
        return None

    log_supply_delta = _f(on360, "interval_indigenous_logistics_delivered") - _f(
        off360, "interval_indigenous_logistics_delivered"
    )
    log_demand_delta = _f(on360, "interval_military_logistics_demanded") - _f(
        off360, "interval_military_logistics_demanded"
    )

    return {
        "git_commit": commit,
        "cell_id": on_primary.get("cell_id"),
        "seed": on_primary.get("seed"),
        "support_profile": on_primary.get("support_profile"),
        "formal_bottleneck": on_primary.get("formal_bottleneck"),
        "formal_regime": on_primary.get("formal_regime"),
        "capability_delta_30": cap30,
        "capability_delta_360": cap360,
        "autonomy_delta_360": delta_q,
        "classification": classify(delta_q, cap360),
        "initially_effective": cap30 > EPS,
        "logistics_indigenous_delivery_delta_360": log_supply_delta,
        "logistics_demand_delta_360": log_demand_delta,
        "pre_q_indigenous": _f(on_primary, "formal_q_indigenous"),
        "formal_support_lift": _f(on_primary, "formal_support_lift"),
        "external_share_logistics": _f(on_primary, "external_share_logistics"),
        "external_share_forcegen": _f(on_primary, "external_share_forcegen"),
        "external_share_command": _f(on_primary, "external_share_command"),
        "bottleneck_target_match": (
            PROFILE_TARGET.get(on_primary.get("support_profile", ""))
            == on_primary.get("formal_bottleneck")
            if on_primary.get("support_profile") in PROFILE_TARGET
            else None
        ),
    }


def summarize(worlds: list[dict]) -> dict:
    treated = [w for w in worlds if w["support_profile"] != "none"]
    effective = [w for w in treated if w["initially_effective"]]
    counts = Counter(w["classification"] for w in effective)
    by_profile: dict[str, dict[str, int]] = {}
    for profile in sorted({w["support_profile"] for w in effective}):
        by_profile[profile] = dict(Counter(w["classification"] for w in effective if w["support_profile"] == profile))
    by_bottleneck: dict[str, dict[str, int]] = {}
    for bottleneck in sorted({w["formal_bottleneck"] for w in effective}):
        by_bottleneck[bottleneck] = dict(
            Counter(w["classification"] for w in effective if w["formal_bottleneck"] == bottleneck)
        )

    targeting: dict[str, dict] = {}
    for match_value, label in ((True, "matched"), (False, "mismatched")):
        group = [w for w in treated if w["bottleneck_target_match"] is match_value]
        effective_group = [w for w in group if w["initially_effective"]]
        if group:
            targeting[label] = {
                "n": len(group),
                "initially_effective_fraction": len(effective_group) / len(group),
                "mean_capability_delta_30": mean(w["capability_delta_30"] for w in group),
                "mean_autonomy_delta_360": mean(w["autonomy_delta_360"] for w in group),
                "effective_classification_counts": dict(
                    Counter(w["classification"] for w in effective_group)
                ),
            }

    negative_controls = [w for w in worlds if w["support_profile"] == "none"]
    negative_control_violations = [
        w
        for w in negative_controls
        if abs(w["capability_delta_30"]) > 1e-12
        or abs(w["capability_delta_360"]) > 1e-12
        or abs(w["autonomy_delta_360"]) > 1e-12
    ]

    result = {
        "analysis_status": "EXPLORATORY_POST_FREEZE",
        "worlds_complete": len(worlds),
        "negative_controls_complete": len(negative_controls),
        "negative_control_violations": len(negative_control_violations),
        "treated_worlds_complete": len(treated),
        "initially_effective_treated_worlds": len(effective),
        "classification_counts": dict(counts),
        "classification_fractions": {
            key: value / len(effective) if effective else 0.0 for key, value in counts.items()
        },
        "by_profile": by_profile,
        "by_bottleneck": by_bottleneck,
        "bottleneck_targeting": targeting,
    }
    for label in ("productive_autonomy", "dependency_gain", "contraction_autonomy", "double_harm"):
        group = [w for w in effective if w["classification"] == label]
        if group:
            result[label + "_mechanism"] = {
                "n": len(group),
                "mean_autonomy_delta_360": mean(w["autonomy_delta_360"] for w in group),
                "median_autonomy_delta_360": median(w["autonomy_delta_360"] for w in group),
                "mean_capability_delta_360": mean(w["capability_delta_360"] for w in group),
                "mean_logistics_indigenous_delivery_delta_360": mean(
                    w["logistics_indigenous_delivery_delta_360"] for w in group
                ),
                "mean_logistics_demand_delta_360": mean(w["logistics_demand_delta_360"] for w in group),
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--expected-commit")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    primaries = [
        Path(path)
        for path in glob.glob(str(args.input_dir / "task_*_cell_*_seed_*.csv"))
        if not path.endswith(".trajectory.csv")
    ]
    worlds = [world for path in primaries if (world := load_world(path, args.expected_commit)) is not None]
    result = summarize(worlds)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
