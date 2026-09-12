#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smd(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return 0.0
    va = float(np.var(a, ddof=1))
    vb = float(np.var(b, ddof=1))
    denom = np.sqrt(max((va + vb) / 2.0, 1.0e-18))
    return float(abs(np.mean(a) - np.mean(b)) / denom)


def pair_metric(d: pd.DataFrame, column: str) -> pd.DataFrame:
    rows = []
    for (pair, stratum), g in d.groupby(["pair_id", "stratum"]):
        left = g[g.side.eq("L")][column].to_numpy(float)
        right = g[g.side.eq("R")][column].to_numpy(float)
        rows.append(
            {
                "pair_id": int(pair),
                "stratum": str(stratum),
                "smd": smd(left, right),
                "mean_left": float(left.mean()) if len(left) else None,
                "mean_right": float(right.mean()) if len(right) else None,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = pd.read_csv(a.csv)
    required = {
        "pre_org_active",
        "final_org_active",
        "pre_logF",
        "final_logF",
        "pre_active_owner_logF",
        "final_active_owner_logF",
    }
    missing = required - set(d.columns)
    if missing:
        raise SystemExit(f"missing audit columns: {sorted(missing)}")

    pre_diff = ~np.isclose(d.pre_logF, d.pre_active_owner_logF, rtol=0, atol=1e-12)
    final_diff = ~np.isclose(d.final_logF, d.final_active_owner_logF, rtol=0, atol=1e-12)
    legacy = pair_metric(d, "final_logF")
    corrected = pair_metric(d, "final_active_owner_logF")
    merged = legacy.merge(corrected, on=["pair_id", "stratum"], suffixes=("_legacy", "_corrected"))
    # The original closure work used ~0.5 SMD as a practical large-effect scale.
    merged["large_legacy"] = merged.smd_legacy >= 0.5
    merged["large_corrected"] = merged.smd_corrected >= 0.5
    merged["classification_changed"] = merged.large_legacy != merged.large_corrected

    by_stratum = {}
    for stratum, g in d.assign(pre_diff=pre_diff, final_diff=final_diff).groupby("stratum"):
        pg = merged[merged.stratum.eq(stratum)]
        by_stratum[str(stratum)] = {
            "rows": int(len(g)),
            "pre_definition_disagreement_fraction": float(g.pre_diff.mean()),
            "final_definition_disagreement_fraction": float(g.final_diff.mean()),
            "inactive_owner_final_fraction": float((g.final_org_active == 0).mean()),
            "mean_pair_smd_legacy": float(pg.smd_legacy.mean()),
            "mean_pair_smd_corrected": float(pg.smd_corrected.mean()),
            "pair_large_classification_changes": int(pg.classification_changed.sum()),
        }

    overall_disagreement = float(final_diff.mean())
    classification_changes = int(merged.classification_changed.sum())
    material = bool(overall_disagreement >= 0.01 or classification_changes > 0)
    result = {
        "schema_version": "pineland.fielded_force_definition_audit_results.v1",
        "status": "FIELD_FORCE_DEFINITION_REISSUE_REQUIRED" if material else "FIELD_FORCE_DEFINITION_DOCUMENTATION_ONLY",
        "historical_outcomes_used": False,
        "input": a.csv,
        "input_sha256": sha256(a.csv),
        "seed_count": int(len(set(d.left_seed).union(set(d.right_seed)))),
        "pair_count": int(d.pair_id.nunique()),
        "branch_count": int(d.branch.nunique()),
        "pre_definition_disagreement_fraction": float(pre_diff.mean()),
        "final_definition_disagreement_fraction": overall_disagreement,
        "inactive_owner_final_fraction": float((d.final_org_active == 0).mean()),
        "pair_large_classification_changes": classification_changes,
        "by_stratum": by_stratum,
        "pair_metrics": merged.to_dict("records"),
        "guard": "Measurement audit only. A reissue requirement does not itself falsify the reduced state variables; it requires rerunning closure with active-owner F semantics.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "final_disagreement": overall_disagreement,
                "classification_changes": classification_changes,
                "by_stratum": by_stratum,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
