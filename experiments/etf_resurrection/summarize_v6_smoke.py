"""Summarize funnel and paired-branch evidence from one traced v6 smoke run."""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path


TRACE_TIME = re.compile(r"\bt=([0-9.]+)")
TRACE_STAGE = re.compile(r"\bstage=([^ ]+)")
TRACE_OUTCOME = re.compile(r"\boutcome=([^ ]+)")


def summarize(trace_path: Path, trajectory_path: Path, withdrawal: float) -> dict:
    trace_lines = trace_path.read_text(encoding="utf-8", errors="replace").splitlines()
    stages: collections.Counter[str] = collections.Counter()
    outcomes: collections.Counter[str] = collections.Counter()
    stages_post: collections.Counter[str] = collections.Counter()
    outcomes_post: collections.Counter[str] = collections.Counter()
    for line in trace_lines:
        if not (line.startswith("FUNNEL ") or line.startswith("MOVEFUNNEL ")):
            continue
        stage_match = TRACE_STAGE.search(line)
        time_match = TRACE_TIME.search(line)
        if not stage_match:
            continue
        stage = stage_match.group(1)
        outcome_match = TRACE_OUTCOME.search(line)
        is_outcome = stage == "strike" and outcome_match is not None
        if is_outcome:
            key = outcome_match.group(1)
            outcomes[key] += 1
        else:
            stages[stage] += 1
        if time_match and float(time_match.group(1)) > withdrawal:
            if is_outcome:
                outcomes_post[key] += 1
            else:
                stages_post[stage] += 1

    with trajectory_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    post_rows = [
        row
        for row in rows
        if row["phase"] in {"SUPPORT_ON", "SUPPORT_OFF"}
        and float(row["time_days"]) > withdrawal
    ]
    branches: dict[str, dict] = {}
    for branch in ("SUPPORT_ON", "SUPPORT_OFF"):
        series = [row for row in post_rows if row["phase"] == branch]
        if not series:
            branches[branch] = {"rows": 0}
            continue
        branches[branch] = {
            "rows": len(series),
            "post_contacts": sum(int(row["interval_contacts"]) for row in series),
            "post_military_losses": sum(float(row["interval_military_losses"]) for row in series),
            "first_post_personnel": float(series[0]["military_personnel"]),
            "last_personnel": float(series[-1]["military_personnel"]),
            "first_post_readiness": float(series[0]["readiness"]),
            "last_readiness": float(series[-1]["readiness"]),
            "last_state_hash": series[-1]["state_hash"],
        }

    total_strikes = sum(outcomes.values())
    both = branches["SUPPORT_ON"], branches["SUPPORT_OFF"]
    return {
        "schema_version": "pineland.etf.v6_smoke_summary.v1",
        "withdrawal_time_days": withdrawal,
        "trace": {
            "stage_counts": dict(sorted(stages.items())),
            "strike_outcome_counts": dict(sorted(outcomes.items())),
            "post_withdrawal_stage_counts": dict(sorted(stages_post.items())),
            "post_withdrawal_strike_outcome_counts": dict(sorted(outcomes_post.items())),
            "strike_attempts": total_strikes,
            "unaffordable_share": outcomes.get("unaffordable", 0) / max(total_strikes, 1),
            "dry_hole_share": outcomes.get("dry_hole", 0) / max(total_strikes, 1),
        },
        "branches": branches,
        "gates": {
            "post_withdrawal_contacts_nonzero": sum(b.get("post_contacts", 0) for b in both) > 0,
            "post_withdrawal_losses_nonzero": sum(b.get("post_military_losses", 0.0) for b in both) > 0,
            "losses_reduce_personnel": any(
                b.get("last_personnel", 0.0) < b.get("first_post_personnel", 0.0) for b in both
            ),
            "support_branches_diverge": both[0].get("last_state_hash")
            != both[1].get("last_state_hash"),
            "combat_outcomes_differ_by_branch": any(
                both[0].get(key) != both[1].get(key)
                for key in ("post_contacts", "post_military_losses")
            ),
        },
        "source_files": {"trace": str(trace_path), "trajectory": str(trajectory_path)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--trajectory", required=True, type=Path)
    parser.add_argument("--withdrawal", type=float, default=120.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = summarize(args.trace, args.trajectory, args.withdrawal)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gates": result["gates"], "trace": result["trace"]}, indent=2))


if __name__ == "__main__":
    main()
