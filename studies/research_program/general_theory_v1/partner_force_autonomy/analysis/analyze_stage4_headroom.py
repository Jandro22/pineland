#!/usr/bin/env python3
"""Reconstruct pre-withdrawal service headroom from frozen Stage-4 trajectories.

This is a post-completion descriptive analysis. It does not alter the Stage-4
preregistration or primary estimands. The script reconstructs the exact formal
service ratios over the common PRE_SUPPORTED observation window (day 60 to day
120) from trajectory primitives, validates the resulting bottleneck against the
frozen world summary, and emits a compact per-world table for secondary analysis.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


COMMAND_SERVICE_REQUIREMENT_PER_ORDER = 0.5
CHANNEL_ORDER = ("forcegen", "logistics", "command")


def _f(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else 0.0


def _ratio(indigenous: float, demand: float) -> float | None:
    if demand <= 0.0:
        return None
    return indigenous / demand


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--trajectory", required=True, type=Path)
    p.add_argument("--world-summary", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    return p.parse_args()


def main() -> None:
    ns = parse_args()
    sums: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))

    with ns.trajectory.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "cell_id",
            "seed",
            "phase",
            "time_days",
            "interval_military_losses",
            "interval_indigenous_graduates",
            "interval_military_logistics_demanded",
            "interval_indigenous_logistics_delivered",
            "interval_command_opportunities",
            "interval_command_indigenous_service",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"trajectory missing fields: {sorted(missing)}")
        for row in reader:
            if row["phase"] != "PRE_SUPPORTED":
                continue
            # Day 60 is the baseline snapshot with a zero-length interval. It is
            # harmless to include, but requiring [60,120] documents the exact
            # common pre-withdrawal measurement window used by Stage 4.
            t = float(row["time_days"])
            if t < 60.0 - 1e-9 or t > 120.0 + 1e-9:
                continue
            key = (row["cell_id"], int(row["seed"]))
            x = sums[key]
            x["fg_demand"] += _f(row, "interval_military_losses")
            x["fg_indigenous"] += _f(row, "interval_indigenous_graduates")
            x["log_demand"] += _f(row, "interval_military_logistics_demanded")
            x["log_indigenous"] += _f(row, "interval_indigenous_logistics_delivered")
            x["cmd_demand"] += _f(row, "interval_command_opportunities") * COMMAND_SERVICE_REQUIREMENT_PER_ORDER
            x["cmd_indigenous"] += _f(row, "interval_command_indigenous_service")

    worlds: dict[tuple[str, int], dict[str, str]] = {}
    with ns.world_summary.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            worlds[(row["cell_id"], int(row["seed"]))] = row

    if set(sums) != set(worlds):
        missing_trajectory = sorted(set(worlds) - set(sums))[:10]
        missing_world = sorted(set(sums) - set(worlds))[:10]
        raise SystemExit(
            "trajectory/world key mismatch: "
            f"missing_trajectory={missing_trajectory}, missing_world={missing_world}"
        )

    rows: list[dict[str, object]] = []
    mismatches: list[tuple[str, int, str, str]] = []
    for key in sorted(sums):
        cell_id, seed = key
        s = sums[key]
        ratios = {
            "forcegen": _ratio(s["fg_indigenous"], s["fg_demand"]),
            "logistics": _ratio(s["log_indigenous"], s["log_demand"]),
            "command": _ratio(s["cmd_indigenous"], s["cmd_demand"]),
        }
        active = [(name, ratios[name]) for name in CHANNEL_ORDER if ratios[name] is not None]
        if not active:
            reconstructed = "none"
            q1 = q2 = headroom = -1.0
            second = "none"
        else:
            # Match Rust tie behavior: fixed channel order wins exact ties.
            ordered = sorted(active, key=lambda item: (item[1], CHANNEL_ORDER.index(item[0])))
            reconstructed, q1 = ordered[0]
            if len(ordered) >= 2:
                second, q2 = ordered[1]
                headroom = q2 - q1
            else:
                second, q2, headroom = "none", -1.0, -1.0

        w = worlds[key]
        frozen = w["pre_bottleneck"]
        if reconstructed != frozen:
            mismatches.append((cell_id, seed, reconstructed, frozen))

        row: dict[str, object] = {
            "cell_id": cell_id,
            "seed": seed,
            "pre_bottleneck_reconstructed": reconstructed,
            "pre_bottleneck_frozen": frozen,
            "second_constraint": second,
            "pre_q1": q1,
            "pre_q2": q2,
            "pre_headroom": headroom,
            "pre_forcegen_ratio_indigenous": ratios["forcegen"] if ratios["forcegen"] is not None else -1.0,
            "pre_logistics_ratio_indigenous": ratios["logistics"] if ratios["logistics"] is not None else -1.0,
            "pre_command_ratio_indigenous": ratios["command"] if ratios["command"] is not None else -1.0,
        }
        for name in (
            "factor_expected_initial_bottleneck",
            "factor_starting_structure",
            "factor_support_intensity",
            "factor_support_target",
            "delta_composite_capability_h30",
            "delta_q_feasible_h360",
            "first_persistent_migration_days",
            "ever_persistently_migrated",
            "modal_post_bottleneck",
            "initially_effective",
            "autonomy_class_360",
        ):
            row[name] = w[name]
        row["observed_target_match"] = str(w["factor_support_target"] == frozen)
        rows.append(row)

    if mismatches:
        preview = "; ".join(f"{c}/{s}: {a}!={b}" for c, s, a, b in mismatches[:10])
        raise SystemExit(
            f"reconstructed pre-bottleneck disagrees with frozen summary in {len(mismatches)} worlds: {preview}"
        )

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with ns.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"PASS headroom reconstruction: {len(rows)} worlds; 0 bottleneck mismatches")
    print(f"wrote {ns.output}")


if __name__ == "__main__":
    main()
