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


def finite_summary(x: pd.Series) -> dict:
    a = x.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    if not len(a):
        return {"n": 0}
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "p10": float(np.quantile(a, 0.1)),
        "p90": float(np.quantile(a, 0.9)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    d = pd.read_csv(ns.csv)
    thresholds = {
        "government_legitimacy": (
            "production_threshold_government_legitimacy",
            "nominal_public_required_government_legitimacy",
        ),
        "state_legitimacy": (
            "production_threshold_state_legitimacy",
            "nominal_public_required_state_legitimacy",
        ),
        "political_access": (
            "production_threshold_political_access",
            "nominal_public_required_political_access",
        ),
    }
    out_thresholds = {}
    for name, (pcol, spendcol) in thresholds.items():
        possible = d[pcol] <= 1.0
        affordable_baseline = possible & (d.baseline_equal_locality_nominal_public >= d[spendcol])
        out_thresholds[name] = {
            "structurally_possible_fraction": float(possible.mean()),
            "baseline_equal_allocation_clears_threshold_fraction": float(affordable_baseline.mean()),
            "required_nominal_public_when_possible": finite_summary(d.loc[possible, spendcol]),
        }
    saturation = d.baseline_equal_locality_nominal_public >= d.nominal_public_saturation
    result = {
        "schema_version": "pineland.development_absorptive_thresholds_results.v1",
        "status": "ANALYTIC_ABSORPTIVE_THRESHOLDS_MAPPED",
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "rows": int(len(d)),
        "seeds": int(d.seed.nunique()),
        "thresholds": out_thresholds,
        "baseline_equal_allocation_saturates_production_fraction": float(saturation.mean()),
        "marginal_production_per_nominal_public": finite_summary(d.marginal_production_per_nominal_public),
        "interpretation": "Under the implemented political-order equations, public spending can fail to improve legitimacy/access when local institutions cannot convert spending into sufficiently high-quality services. Production thresholds above 1 are impossible to clear by spending alone in that cycle.",
        "guard": "Exact/approximate synthetic equation audit. Nominal-public thresholds use stored compliance as the mean sampled-compliance approximation and are not empirical monetary estimates.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
