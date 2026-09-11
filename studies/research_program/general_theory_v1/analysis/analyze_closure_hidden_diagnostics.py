from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


ID_COLS = {
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


def auc_or_none(y: np.ndarray, score: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2 or np.nanstd(score) < 1e-12:
        return None
    return float(roc_auc_score(y, score))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("diagnostics_csv")
    ap.add_argument("closure_results_json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    d = pd.read_csv(args.diagnostics_csv)
    closure = json.loads(Path(args.closure_results_json).read_text(encoding="utf-8"))
    features = [c for c in d.columns if c not in ID_COLS]
    if set(d.side.unique()) != {"L", "R"}:
        raise SystemExit("diagnostics must contain L/R rows")

    left = d[d.side == "L"].set_index("pair_id")
    right = d[d.side == "R"].set_index("pair_id")
    pair_ids = sorted(set(left.index) & set(right.index))
    if len(pair_ids) != int(closure["pair_count"]):
        raise SystemExit(f"pair mismatch diagnostics={len(pair_ids)} closure={closure['pair_count']}")

    pair_records = {int(p["pair_id"]): p for p in closure["pairs"]}
    labels = pd.DataFrame(
        [
            {
                "pair_id": pair_id,
                "fail_any": bool(pair_records[pair_id]["any_significant_and_large"]),
                "fail_M": "final_M" in pair_records[pair_id]["significant_large_outcomes"],
                "fail_F": "final_logF" in pair_records[pair_id]["significant_large_outcomes"],
                "fail_E": "final_E" in pair_records[pair_id]["significant_large_outcomes"],
                "stratum": pair_records[pair_id]["stratum"],
                "match_distance": float(pair_records[pair_id]["match_distance"]),
            }
            for pair_id in pair_ids
        ]
    ).set_index("pair_id")

    rows = []
    per_pair = []
    for feature in features:
        lv = left.loc[pair_ids, feature].to_numpy(float)
        rv = right.loc[pair_ids, feature].to_numpy(float)
        pooled = np.concatenate([lv, rv])
        finite = pooled[np.isfinite(pooled)]
        scale = float(np.std(finite, ddof=0)) if len(finite) else 0.0
        if not np.isfinite(scale) or scale < 1e-9:
            scale = 1.0
        diff = np.abs(lv - rv)
        z = diff / scale
        record = {
            "feature": feature,
            "pooled_scale": scale,
            "median_abs_difference": float(np.nanmedian(diff)),
            "median_standardized_difference": float(np.nanmedian(z)),
        }
        for label in ["fail_any", "fail_M", "fail_F", "fail_E"]:
            y = labels.loc[pair_ids, label].to_numpy(int)
            failing = z[y == 1]
            passing = z[y == 0]
            record[f"{label}_auc"] = auc_or_none(y, z)
            record[f"{label}_median_z_failing"] = (
                float(np.nanmedian(failing)) if len(failing) else None
            )
            record[f"{label}_median_z_passing"] = (
                float(np.nanmedian(passing)) if len(passing) else None
            )
            record[f"{label}_median_gap"] = (
                float(np.nanmedian(failing) - np.nanmedian(passing))
                if len(failing) and len(passing)
                else None
            )
        rows.append(record)
        for i, pair_id in enumerate(pair_ids):
            per_pair.append(
                {
                    "pair_id": pair_id,
                    "feature": feature,
                    "abs_difference": float(diff[i]),
                    "standardized_difference": float(z[i]),
                }
            )

    ranked = sorted(
        rows,
        key=lambda x: (
            -1.0 if x["fail_any_auc"] is None else -x["fail_any_auc"],
            -(x["fail_any_median_gap"] or -1e9),
            x["feature"],
        ),
    )
    result = {
        "schema_version": "pineland.closure_hidden_diagnostics.v1",
        "status": "EXPLORATORY_HIDDEN_STATE_DIAGNOSTIC",
        "historical_outcomes_used": False,
        "diagnostics_csv": str(Path(args.diagnostics_csv)),
        "diagnostics_sha256": sha256(args.diagnostics_csv),
        "closure_results": str(Path(args.closure_results_json)),
        "closure_results_sha256": sha256(args.closure_results_json),
        "pair_count": len(pair_ids),
        "failure_counts": {
            label: int(labels[label].sum()) for label in ["fail_any", "fail_M", "fail_F", "fail_E"]
        },
        "feature_rankings": ranked,
        "pair_labels": labels.reset_index().to_dict(orient="records"),
        "pair_feature_differences": per_pair,
        "interpretation_guard": (
            "These omitted features are examined after the closure outcomes are known. Rankings are "
            "mechanism-development evidence only. Any feature promoted into the macrostate must be "
            "frozen and tested on a new seed block before it can support a closure claim."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("failure counts", result["failure_counts"])
    print("top hidden features")
    for row in ranked[:12]:
        print(
            row["feature"],
            "AUC(any)=", row["fail_any_auc"],
            "gap(any)=", row["fail_any_median_gap"],
            "AUC(M/F/E)=", row["fail_M_auc"], row["fail_F_auc"], row["fail_E_auc"],
        )


if __name__ == "__main__":
    main()
