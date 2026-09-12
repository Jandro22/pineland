#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


META = {
    "pair_id",
    "candidate",
    "side",
    "seed",
    "other_seed",
    "locality",
    "stratum",
    "match_distance",
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(diagnostics_csv: str, closure_json: str, out_path: str) -> None:
    diag = pd.read_csv(diagnostics_csv)
    closure = json.loads(Path(closure_json).read_text(encoding="utf-8"))
    hidden = [c for c in diag.columns if c not in META]
    if set(diag.side.astype(str).unique()) != {"L", "R"}:
        raise SystemExit("diagnostics require exactly L/R sides")

    failing_pairs = {
        int(p["pair_id"])
        for p in closure["pairs"]
        if p.get("any_significant_and_large", False)
    }
    pair_outcomes = {
        int(p["pair_id"]): p.get("significant_large_outcomes", [])
        for p in closure["pairs"]
    }

    rows = []
    pair_rows = []
    for pair_id, g in diag.groupby("pair_id", sort=True):
        if len(g) != 2:
            raise SystemExit(f"pair {pair_id} has {len(g)} diagnostic rows")
        left = g[g.side.astype(str) == "L"].iloc[0]
        right = g[g.side.astype(str) == "R"].iloc[0]
        record = {
            "pair_id": int(pair_id),
            "stratum": str(left.stratum),
            "match_distance": float(left.match_distance),
            "failed": int(pair_id) in failing_pairs,
            "significant_large_outcomes": pair_outcomes.get(int(pair_id), []),
        }
        for feature in hidden:
            record[f"delta::{feature}"] = abs(float(left[feature]) - float(right[feature]))
            record[f"left::{feature}"] = float(left[feature])
            record[f"right::{feature}"] = float(right[feature])
        pair_rows.append(record)

    pairs = pd.DataFrame(pair_rows)
    scales = {}
    for feature in hidden:
        values = diag[feature].astype(float).to_numpy()
        scale = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
        scales[feature] = max(scale, 1.0e-9)
        pairs[f"zdelta::{feature}"] = pairs[f"delta::{feature}"] / scales[feature]

    low = pairs[pairs.stratum == "low"].copy()
    failed_low = low[low.failed]
    passed_low = low[~low.failed]
    for feature in hidden:
        column = f"zdelta::{feature}"
        fail_mean = float(failed_low[column].mean()) if len(failed_low) else 0.0
        pass_mean = float(passed_low[column].mean()) if len(passed_low) else 0.0
        rows.append(
            {
                "feature": feature,
                "scale_across_selected_anchor_sides": scales[feature],
                "failed_low_mean_abs_z_difference": fail_mean,
                "passed_low_mean_abs_z_difference": pass_mean,
                "failed_minus_passed_low": fail_mean - pass_mean,
                "max_failed_low_abs_z_difference": (
                    float(failed_low[column].max()) if len(failed_low) else 0.0
                ),
            }
        )
    ranking = sorted(rows, key=lambda x: x["failed_minus_passed_low"], reverse=True)

    failing_detail = []
    for _, p in failed_low.sort_values("pair_id").iterrows():
        feature_diffs = sorted(
            [
                {
                    "feature": feature,
                    "abs_z_difference": float(p[f"zdelta::{feature}"]),
                    "left": float(p[f"left::{feature}"]),
                    "right": float(p[f"right::{feature}"]),
                }
                for feature in hidden
            ],
            key=lambda x: x["abs_z_difference"],
            reverse=True,
        )
        failing_detail.append(
            {
                "pair_id": int(p.pair_id),
                "match_distance": float(p.match_distance),
                "significant_large_outcomes": p.significant_large_outcomes,
                "largest_hidden_differences": feature_diffs[:8],
            }
        )

    result = {
        "schema_version": "pineland.live_closure_residual_diagnostics.v1",
        "status": "POST_HOC_DIAGNOSTIC_ONLY",
        "historical_outcomes_used": False,
        "diagnostics_input": diagnostics_csv,
        "diagnostics_sha256": sha256(diagnostics_csv),
        "closure_input": closure_json,
        "closure_sha256": sha256(closure_json),
        "failing_pair_ids": sorted(failing_pairs),
        "low_stratum_pair_count": int(len(low)),
        "low_stratum_failing_pair_count": int(len(failed_low)),
        "hidden_difference_ranking": ranking,
        "failing_pair_detail": failing_detail,
        "interpretation_guard": "Exploratory post-hoc diagnosis of the failed closure block. Hidden-coordinate rankings may nominate future preregistered candidates but cannot rescue or certify the failed closure result.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "failing_pair_ids": result["failing_pair_ids"],
        "top_hidden_difference_ranking": ranking[:10],
        "failing_pair_detail": failing_detail,
    }, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("diagnostics_csv")
    ap.add_argument("closure_json")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.diagnostics_csv, ns.closure_json, ns.out)
