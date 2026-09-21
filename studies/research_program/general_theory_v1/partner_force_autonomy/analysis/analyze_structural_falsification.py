#!/usr/bin/env python3
"""Analyze the frozen 32-world structural-falsification sidecar."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


COMMAND_REQ = 0.5
CHANNELS = ("forcegen", "logistics", "command")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def f(row: dict[str, str], key: str) -> float:
    v = row.get(key, "")
    return float(v) if v not in ("", None) else 0.0


def ratio(i: float, d: float) -> float | None:
    return None if d <= 0.0 else i / d


def pre_bottleneck(trajectory: Path) -> tuple[str, dict[str, float | None]]:
    sums = defaultdict(float)
    with trajectory.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["phase"] != "PRE_SUPPORTED":
                continue
            t = float(row["time_days"])
            if not (60.0 - 1e-9 <= t <= 120.0 + 1e-9):
                continue
            sums["fg_d"] += f(row, "interval_military_losses")
            sums["fg_i"] += f(row, "interval_indigenous_graduates")
            sums["log_d"] += f(row, "interval_military_logistics_demanded")
            sums["log_i"] += f(row, "interval_indigenous_logistics_delivered")
            sums["cmd_d"] += f(row, "interval_command_opportunities") * COMMAND_REQ
            sums["cmd_i"] += f(row, "interval_command_indigenous_service")
    ratios = {
        "forcegen": ratio(sums["fg_i"], sums["fg_d"]),
        "logistics": ratio(sums["log_i"], sums["log_d"]),
        "command": ratio(sums["cmd_i"], sums["cmd_d"]),
    }
    active = [(c, ratios[c]) for c in CHANNELS if ratios[c] is not None]
    if not active:
        return "none", ratios
    return min(active, key=lambda x: (x[1], CHANNELS.index(x[0])))[0], ratios


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--contract", required=True, type=Path)
    p.add_argument("--world-output", required=True, type=Path)
    p.add_argument("--summary-output", required=True, type=Path)
    p.add_argument("--result-json", required=True, type=Path)
    return p.parse_args()


def main() -> None:
    ns = parse_args()
    contract = json.loads(ns.contract.read_text(encoding="utf-8"))
    cells = {c["cell_id"]: c for c in contract["cells"]}
    expected = int(contract["cells_count"]) * int(contract["default_seed_count"])
    primaries = sorted(
        p for p in ns.input_dir.glob("task_*_cell_*_seed_*.csv") if ".trajectory.csv" not in p.name
    )
    if len(primaries) != expected:
        raise SystemExit(f"expected {expected} primary shards, found {len(primaries)}")

    rows: list[dict[str, object]] = []
    for primary in primaries:
        trajectory = primary.with_name(primary.stem + ".trajectory.csv")
        metadata = primary.with_suffix(".json")
        if not trajectory.exists() or not metadata.exists():
            raise SystemExit(f"missing trajectory/metadata for {primary}")
        meta = json.loads(metadata.read_text(encoding="utf-8"))
        if meta.get("output_sha256") != sha256(primary):
            raise SystemExit(f"primary hash mismatch: {primary}")
        if meta.get("trajectory_sha256") != sha256(trajectory):
            raise SystemExit(f"trajectory hash mismatch: {trajectory}")

        with primary.open(newline="", encoding="utf-8") as fh:
            primary_rows = list(csv.DictReader(fh))
        on30 = [
            r for r in primary_rows
            if r["branch"] == "SUPPORT_ON" and abs(float(r["horizon_days"]) - 30.0) < 1e-9
        ]
        if len(on30) != 1:
            raise SystemExit(f"expected exactly one SUPPORT_ON +30 row in {primary}")
        r30 = on30[0]
        cell_id = r30["cell_id"]
        cell = cells[cell_id]
        pre, ratios = pre_bottleneck(trajectory)
        expected_initial = cell["factor_expected_initial_bottleneck"]
        expected_post = cell["factor_expected_post_bottleneck"]
        post = r30["formal_bottleneck"]
        rows.append(
            {
                "cell_id": cell_id,
                "factor_path": cell["factor_path"],
                "factor_treatment_mode": cell["factor_treatment_mode"],
                "seed": int(r30["seed"]),
                "pre_bottleneck": pre,
                "expected_initial_bottleneck": expected_initial,
                "target_match": pre == expected_initial,
                "post_bottleneck_h30": post,
                "expected_post_bottleneck": expected_post,
                "designated_path_realized": pre == expected_initial and post == expected_post,
                "pre_forcegen_ratio": ratios["forcegen"] if ratios["forcegen"] is not None else -1.0,
                "pre_logistics_ratio": ratios["logistics"] if ratios["logistics"] is not None else -1.0,
                "pre_command_ratio": ratios["command"] if ratios["command"] is not None else -1.0,
                "composite_capability_h30": float(r30["composite_capability"]),
                "formal_q_indigenous_h30": float(r30["formal_q_indigenous"]),
                "formal_q_supported_h30": float(r30["formal_q_supported"]),
            }
        )

    fieldnames = list(rows[0])
    ns.world_output.parent.mkdir(parents=True, exist_ok=True)
    with ns.world_output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    summaries: list[dict[str, object]] = []
    for cell_id in sorted(cells):
        g = [r for r in rows if r["cell_id"] == cell_id]
        matched = [r for r in g if r["target_match"]]
        counts = Counter(str(r["post_bottleneck_h30"]) for r in matched)
        expected_post = cells[cell_id]["factor_expected_post_bottleneck"]
        summaries.append(
            {
                "cell_id": cell_id,
                "factor_path": cells[cell_id]["factor_path"],
                "n": len(g),
                "target_match_n": len(matched),
                "designated_post_n": counts.get(expected_post, 0),
                "designated_post_fraction_among_matched": (
                    counts.get(expected_post, 0) / len(matched) if matched else 0.0
                ),
                "post_forcegen_n": counts.get("forcegen", 0),
                "post_logistics_n": counts.get("logistics", 0),
                "post_command_n": counts.get("command", 0),
                "post_none_n": counts.get("none", 0),
            }
        )
    with ns.summary_output.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summaries[0]))
        w.writeheader()
        w.writerows(summaries)

    matched = [r for r in rows if r["target_match"]]
    command_terminal = sum(r["post_bottleneck_h30"] == "command" for r in matched)
    forcegen_terminal = sum(r["post_bottleneck_h30"] == "forcegen" for r in matched)
    result = {
        "schema_version": "pineland.partner_force_structural_falsification_result.v1",
        "worlds": len(rows),
        "target_matched_worlds": len(matched),
        "matched_command_terminal_worlds": command_terminal,
        "matched_forcegen_terminal_worlds": forcegen_terminal,
        "matched_logistics_terminal_worlds": sum(r["post_bottleneck_h30"] == "logistics" for r in matched),
        "unique_logistics_hard_code_rejected": command_terminal > 0 and forcegen_terminal > 0,
        "interpretation_rule": contract["analysis_rules"]["artifact_rejection_rule"],
    }
    ns.result_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

