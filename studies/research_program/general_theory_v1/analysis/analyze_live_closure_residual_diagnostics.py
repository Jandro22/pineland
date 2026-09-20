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

    # Support both the legacy significance/effect-size closure JSON and the
    # stricter paired-bootstrap equivalence JSON.  The latter is now the
    # authoritative closure criterion: a pair fails only when it is explicitly
    # classified as demonstrably non-equivalent.
    def is_failing_pair(p: dict) -> bool:
        if "classification" in p:
            return p["classification"] == "demonstrably_non_equivalent"
        return bool(p.get("any_significant_and_large", False))

    def failing_outcomes(p: dict) -> list[str]:
        if "non_equivalent_outcomes" in p:
            return list(p.get("non_equivalent_outcomes", []))
        return list(p.get("significant_large_outcomes", []))

    failing_pairs = {int(p["pair_id"]) for p in closure["pairs"] if is_failing_pair(p)}
    pair_outcomes = {int(p["pair_id"]): failing_outcomes(p) for p in closure["pairs"]}
    closure_pair_ids = {int(p["pair_id"]) for p in closure["pairs"]}
    diagnostic_pair_ids = set(int(x) for x in diag.pair_id.unique())
    if diagnostic_pair_ids != closure_pair_ids:
        missing = sorted(closure_pair_ids - diagnostic_pair_ids)
        extra = sorted(diagnostic_pair_ids - closure_pair_ids)
        raise SystemExit(f"pair identity mismatch missing={missing} extra={extra}")

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
            "non_equivalent_outcomes": pair_outcomes.get(int(pair_id), []),
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

    def rank_subset(frame: pd.DataFrame, failed_mask: pd.Series) -> list[dict]:
        failed = frame[failed_mask].copy()
        nonfailed = frame[~failed_mask].copy()
        ranked = []
        for feature in hidden:
            column = f"zdelta::{feature}"
            fail_mean = float(failed[column].mean()) if len(failed) else 0.0
            nonfail_mean = float(nonfailed[column].mean()) if len(nonfailed) else 0.0
            ranked.append(
                {
                    "feature": feature,
                    "scale_across_selected_anchor_sides": scales[feature],
                    "failed_mean_abs_z_difference": fail_mean,
                    "nonfailed_mean_abs_z_difference": nonfail_mean,
                    "failed_minus_nonfailed": fail_mean - nonfail_mean,
                    "failed_to_nonfailed_ratio": (
                        fail_mean / nonfail_mean if nonfail_mean > 1.0e-12 else None
                    ),
                    "max_failed_abs_z_difference": (
                        float(failed[column].max()) if len(failed) else 0.0
                    ),
                }
            )
        return sorted(ranked, key=lambda x: x["failed_minus_nonfailed"], reverse=True)

    all_ranking = rank_subset(pairs, pairs.failed.astype(bool))
    stratum_rankings = {}
    for stratum in sorted(pairs.stratum.unique()):
        frame = pairs[pairs.stratum == stratum].copy()
        stratum_rankings[str(stratum)] = rank_subset(frame, frame.failed.astype(bool))

    all_outcomes = sorted({o for values in pair_outcomes.values() for o in values})
    outcome_rankings = {}
    for outcome in all_outcomes:
        mask = pairs.non_equivalent_outcomes.apply(
            lambda xs, outcome=outcome: outcome in xs
        )
        outcome_rankings[outcome] = rank_subset(pairs, mask)

    # Retain the previous low-stratum summary for continuity with the first
    # residual diagnosis, but no longer privilege it in the primary ranking.
    low = pairs[pairs.stratum == "low"].copy()
    failed_low = low[low.failed]
    legacy_low_ranking = stratum_rankings.get("low", [])

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
                "non_equivalent_outcomes": p.non_equivalent_outcomes,
                "largest_hidden_differences": feature_diffs[:8],
            }
        )

    result = {
        "schema_version": "pineland.live_closure_residual_diagnostics.v2",
        "status": "POST_HOC_DIAGNOSTIC_ONLY",
        "historical_outcomes_used": False,
        "diagnostics_input": diagnostics_csv,
        "diagnostics_sha256": sha256(diagnostics_csv),
        "closure_input": closure_json,
        "closure_sha256": sha256(closure_json),
        "failing_pair_ids": sorted(failing_pairs),
        "pair_count": int(len(pairs)),
        "failing_pair_count": int(pairs.failed.sum()),
        "low_stratum_pair_count": int(len(low)),
        "low_stratum_failing_pair_count": int(len(failed_low)),
        "hidden_difference_ranking": all_ranking,
        "hidden_difference_ranking_by_stratum": stratum_rankings,
        "hidden_difference_ranking_by_failed_outcome": outcome_rankings,
        "legacy_low_stratum_hidden_difference_ranking": legacy_low_ranking,
        "failing_pair_detail": failing_detail,
        "interpretation_guard": "Exploratory post-hoc diagnosis of the failed closure block. Hidden-coordinate rankings may nominate future preregistered candidates but cannot rescue or certify the failed closure result.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "failing_pair_ids": result["failing_pair_ids"],
        "top_hidden_difference_ranking": all_ranking[:10],
        "top_hidden_difference_ranking_by_failed_outcome": {
            outcome: ranking[:6] for outcome, ranking in outcome_rankings.items()
        },
        "failing_pair_detail": failing_detail,
    }, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("diagnostics_csv")
    ap.add_argument("closure_json")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.diagnostics_csv, ns.closure_json, ns.out)
