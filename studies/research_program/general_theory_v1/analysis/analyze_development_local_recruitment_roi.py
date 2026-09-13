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


def summary(x: pd.Series) -> dict:
    a = x.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n": int(len(a)),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "p10": float(np.quantile(a, 0.10)),
        "p90": float(np.quantile(a, 0.90)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    d = pd.read_csv(ns.csv)

    # Threat = baseline recruitment hazard; absorptive capacity = actual
    # incremental political-access response to the fixed spending increment.
    threat_q = d.groupby("seed").baseline_recruitment_hazard.transform(
        lambda x: pd.qcut(x.rank(method="first"), 2, labels=["low", "high"])
    )
    absorb_q = d.groupby("seed").incremental_political_access.transform(
        lambda x: pd.qcut(x.rank(method="first"), 2, labels=["low", "high"])
    )
    d = d.assign(threat_band=threat_q.astype(str), absorption_band=absorb_q.astype(str))
    d["quadrant"] = d.threat_band + "_threat__" + d.absorption_band + "_absorption"

    quadrants = {}
    for q, g in d.groupby("quadrant"):
        quadrants[q] = {
            "rows": int(len(g)),
            "baseline_hazard": summary(g.baseline_recruitment_hazard),
            "incremental_political_access": summary(g.incremental_political_access),
            "hazard_reduction_for_fixed_increment": summary(g.first_order_hazard_reduction),
            "fractional_hazard_reduction": summary(g.fractional_hazard_reduction),
            "headroom_to_saturation": summary(g.nominal_public_headroom_to_saturation),
        }

    # Within each seed, identify where the fixed increment buys the most and
    # compare that locality with the locality that merely has the most threat.
    seed_best = []
    for seed, g in d.groupby("seed"):
        roi = g.loc[g.first_order_hazard_reduction.idxmax()]
        threat = g.loc[g.baseline_recruitment_hazard.idxmax()]
        seed_best.append(
            {
                "seed": int(seed),
                "roi_best_locality": int(roi.locality),
                "roi_best_hazard_reduction": float(roi.first_order_hazard_reduction),
                "roi_best_baseline_hazard": float(roi.baseline_recruitment_hazard),
                "roi_best_access_gain": float(roi.incremental_political_access),
                "max_threat_locality": int(threat.locality),
                "max_threat_hazard_reduction": float(threat.first_order_hazard_reduction),
                "max_threat_baseline_hazard": float(threat.baseline_recruitment_hazard),
                "same_locality": bool(int(roi.locality) == int(threat.locality)),
                "roi_gain_over_max_threat_target": (
                    float(roi.first_order_hazard_reduction / threat.first_order_hazard_reduction)
                    if threat.first_order_hazard_reduction > 1e-15
                    else None
                ),
            }
        )

    seed_df = pd.DataFrame(seed_best)
    positive = d[d.baseline_recruitment_hazard > 1e-12]
    result = {
        "schema_version": "pineland.development_local_recruitment_roi_results.v1",
        "status": "SYNTHETIC_LOCAL_DEVELOPMENT_RECRUITMENT_ROI_MAPPED",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(d.seed.nunique()),
        "locality_count": int(d.locality.nunique()),
        "fixed_increment": float(d.incremental_nominal_public.iloc[0]),
        "all_localities": {
            "baseline_hazard": summary(d.baseline_recruitment_hazard),
            "hazard_reduction_for_fixed_increment": summary(d.first_order_hazard_reduction),
            "fractional_hazard_reduction_positive_hazard_only": summary(positive.fractional_hazard_reduction),
            "incremental_political_access": summary(d.incremental_political_access),
            "saturation_headroom": summary(d.nominal_public_headroom_to_saturation),
        },
        "threat_absorption_quadrants": quadrants,
        "seed_best_targets": seed_best,
        "roi_best_equals_max_threat_fraction": float(seed_df.same_locality.mean()),
        "roi_best_over_max_threat_target_ratio": summary(seed_df.roi_gain_over_max_threat_target),
        "correlations": {
            "hazard_reduction_vs_baseline_hazard_spearman": float(
                d.first_order_hazard_reduction.corr(d.baseline_recruitment_hazard, method="spearman")
            ),
            "hazard_reduction_vs_access_gain_spearman": float(
                d.first_order_hazard_reduction.corr(d.incremental_political_access, method="spearman")
            ),
            "hazard_reduction_vs_institution_capacity_spearman": float(
                d.first_order_hazard_reduction.corr(d.institution_capacity, method="spearman")
            ),
        },
        "dollar_conversion": "The fixed +1200 capital increment equals 1% of the default monthly policy-budget ceiling. If that monthly ceiling is externally calibrated to B dollars, each row's effect is the modeled first-order effect per 0.01*B dollars.",
        "guard": "First-order synthetic recruitment mechanism only; does not include long-run feedback or establish real-world aid effectiveness."
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "roi_best_equals_max_threat_fraction": result["roi_best_equals_max_threat_fraction"],
        "roi_best_over_max_threat_target_ratio": result["roi_best_over_max_threat_target_ratio"],
        "quadrants": {k: v["hazard_reduction_for_fixed_increment"] for k, v in quadrants.items()},
        "correlations": result["correlations"],
    }, indent=2))


if __name__ == "__main__":
    main()
