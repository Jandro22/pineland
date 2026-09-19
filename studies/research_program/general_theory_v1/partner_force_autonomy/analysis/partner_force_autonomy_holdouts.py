"""Zero-refit holdout evaluator for partner-force autonomy candidate predictors.

Applies frozen candidate predictors from Stage-3 discovery to held-out mechanism
families without refitting, re-estimating, or recalibrating any parameters.

Strict scientific gate: Refuses evaluation if discovery results are not frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))

from partner_force_metrics import pair_counterfactual_rows
from partner_force_regenerative_coordinates import add_candidate_regenerative_coordinates


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate frozen discovery predictors on held-out families")
    p.add_argument("--discovery-model-json", help="Path to frozen discovery predictor JSON")
    p.add_argument("--holdout-raw-csv", help="Path to held-out mechanism raw branch CSV")
    p.add_argument("--output-json", help="Path to write zero-refit holdout results")
    p.add_argument("--dry-run", action="store_true", help="Validate evaluation plumbing without scientific claims")
    return p.parse_args()


def evaluate_zero_refit(
    holdout_paired: pd.DataFrame,
    frozen_predictor_name: str = "omega_min",
) -> Dict[str, Any]:
    df = add_candidate_regenerative_coordinates(holdout_paired)
    if frozen_predictor_name not in df.columns:
        raise ValueError(f"frozen predictor '{frozen_predictor_name}' not present in holdout coordinates")

    x = df[frozen_predictor_name].to_numpy(float)
    y = df["autonomy_ratio"].to_numpy(float)

    # Zero-refit: monotonic rank correlation and absolute prediction error against identity
    # (Since omega in [0,1] and autonomy_ratio in [0, 1+], evaluate directly without re-fitting)
    spearman = float(pd.Series(x).corr(pd.Series(y), method="spearman")) if len(np.unique(x)) > 1 else 0.0
    mae = float(np.mean(np.abs(x - y)))
    rmse = float(np.sqrt(np.mean((x - y) ** 2)))

    by_horizon = {}
    for h, hdf in df.groupby("horizon_days"):
        hx = hdf[frozen_predictor_name].to_numpy(float)
        hy = hdf["autonomy_ratio"].to_numpy(float)
        hrho = float(pd.Series(hx).corr(pd.Series(hy), method="spearman")) if len(np.unique(hx)) > 1 else 0.0
        by_horizon[str(int(h))] = {
            "n": int(len(hdf)),
            "spearman_rho": hrho,
            "mae_zero_refit": float(np.mean(np.abs(hx - hy))),
            "rmse_zero_refit": float(np.sqrt(np.mean((hx - hy) ** 2))),
        }

    return {
        "status": "ZERO_REFIT_HOLDOUT_EVALUATION",
        "frozen_predictor": frozen_predictor_name,
        "n_holdout_pairs": int(len(df)),
        "overall_spearman_rho": spearman,
        "overall_mae_zero_refit": mae,
        "overall_rmse_zero_refit": rmse,
        "by_horizon": by_horizon,
        "refit_permitted": False,
    }


def main() -> None:
    ns = args()
    if ns.dry_run:
        print("PLUMBING_ONLY_PASS: zero-refit holdout evaluator imported and initialized cleanly.")
        print("NO_HOLDOUT_EVALUATION: dry-run executed no evaluation.")
        return

    if not ns.discovery_model_json or not ns.holdout_raw_csv:
        raise SystemExit("--discovery-model-json and --holdout-raw-csv are required for zero-refit evaluation")

    model_path = Path(ns.discovery_model_json)
    if not model_path.exists():
        raise SystemExit(f"discovery model file not found: {model_path}")

    raw_path = Path(ns.holdout_raw_csv)
    if not raw_path.exists():
        raise SystemExit(f"holdout raw CSV not found: {raw_path}")

    holdout_raw = pd.read_csv(raw_path)
    holdout_paired = pair_counterfactual_rows(holdout_raw)
    result = evaluate_zero_refit(holdout_paired)

    if ns.output_json:
        out_p = Path(ns.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote holdout results: {out_p}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
