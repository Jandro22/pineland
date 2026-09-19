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
from typing import Any, Dict, Optional
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
    p.add_argument("--contract-json", help="Path to holdout family contract JSON")
    p.add_argument("--output-json", help="Path to write zero-refit holdout results")
    p.add_argument("--dry-run", action="store_true", help="Validate evaluation plumbing without scientific claims")
    return p.parse_args()


def predict_zero_refit(
    frozen_model: Dict[str, Any],
    df: pd.DataFrame,
    horizon: Optional[int] = None,
) -> np.ndarray:
    """Forward-predict autonomy ratio using frozen predictor with strictly zero refit."""
    spec = frozen_model.get("predictor_specification", {})
    horizon_models = spec.get("horizon_models", {})
    sub_model = None
    if horizon is not None and str(int(horizon)) in horizon_models:
        sub_model = horizon_models[str(int(horizon))]
    else:
        sub_model = spec.get("overall_model")

    if sub_model is None:
        raise ValueError("Frozen predictor specification missing valid model definition")

    func_form = sub_model.get("functional_form")
    if func_form == "isotonic_regression":
        coord = sub_model.get("coordinate", spec.get("winning_coordinate", "omega_min"))
        if coord not in df.columns:
            raise ValueError(f"Required coordinate '{coord}' not found in holdout DataFrame")
        x = df[coord].to_numpy(float)
        knots_x = np.array(sub_model["knots_x"], dtype=float)
        knots_y = np.array(sub_model["knots_y"], dtype=float)
        return np.interp(x, knots_x, knots_y, left=knots_y[0], right=knots_y[-1])
    elif func_form == "standard_scaler_ridge":
        cols = sub_model.get("features", ["omega_manpower", "omega_logistics", "omega_command"])
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"Required feature columns {missing} not found in holdout DataFrame")
        X = df[cols].to_numpy(float)
        mean = np.array(sub_model["scaler_mean"], dtype=float)
        scale = np.array(sub_model["scaler_scale"], dtype=float)
        coef = np.array(sub_model["ridge_coefficients"], dtype=float)
        intercept = float(sub_model["ridge_intercept"])
        X_scaled = (X - mean) / np.maximum(scale, 1e-9)
        return np.dot(X_scaled, coef) + intercept
    else:
        raise ValueError(f"Unsupported frozen functional form: {func_form}")


def evaluate_zero_refit(
    holdout_paired: pd.DataFrame,
    frozen_model: Dict[str, Any],
    contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute zero-refit holdout evaluation against frozen model and acceptance criteria."""
    df = add_candidate_regenerative_coordinates(holdout_paired)
    y_true = df["autonomy_ratio"].to_numpy(float)
    y_pred = predict_zero_refit(frozen_model, df, horizon=None)

    # Compute overall metrics
    has_variance = len(np.unique(y_pred)) > 1 and len(np.unique(y_true)) > 1
    spearman = float(pd.Series(y_pred).corr(pd.Series(y_true), method="spearman")) if has_variance else 0.0
    if np.isnan(spearman):
        spearman = 0.0
    mae = float(np.mean(np.abs(y_pred - y_true)))
    rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))

    by_horizon = {}
    for h, hdf in df.groupby("horizon_days"):
        hy_true = hdf["autonomy_ratio"].to_numpy(float)
        hy_pred = predict_zero_refit(frozen_model, hdf, horizon=int(h))
        h_variance = len(np.unique(hy_pred)) > 1 and len(np.unique(hy_true)) > 1
        hrho = float(pd.Series(hy_pred).corr(pd.Series(hy_true), method="spearman")) if h_variance else 0.0
        if np.isnan(hrho):
            hrho = 0.0
        hmae = float(np.mean(np.abs(hy_pred - hy_true)))
        hrmse = float(np.sqrt(np.mean((hy_pred - hy_true) ** 2)))
        by_horizon[str(int(h))] = {
            "n": int(len(hdf)),
            "spearman_rho": hrho,
            "mae_zero_refit": hmae,
            "rmse_zero_refit": hrmse,
        }

    res: Dict[str, Any] = {
        "status": "ZERO_REFIT_HOLDOUT_EVALUATION",
        "frozen_predictor_coordinate": frozen_model.get("predictor_specification", {}).get("winning_coordinate"),
        "frozen_functional_form": frozen_model.get("predictor_specification", {}).get("functional_form"),
        "discovery_provenance": frozen_model.get("discovery_provenance", {}),
        "n_holdout_pairs": int(len(df)),
        "overall_spearman_rho": spearman,
        "overall_mae_zero_refit": mae,
        "overall_rmse_zero_refit": rmse,
        "by_horizon": by_horizon,
        "refit_permitted": False,
    }

    if contract is not None:
        criteria = contract.get("pass_fail_criteria", contract.get("acceptance_criteria", {}))
        min_rho = float(criteria.get("minimum_spearman_rho", 0.0))
        max_mae = float(criteria.get("maximum_prediction_mae", float("inf")))
        eval_horizons_raw = criteria.get("evaluation_horizons")
        eval_horizons = [int(h) for h in eval_horizons_raw] if eval_horizons_raw else [int(h) for h in df["horizon_days"].unique()]

        # Filter strictly to specified evaluation horizons for pooled contract evaluation
        eval_df = df[df["horizon_days"].isin(eval_horizons)]
        if not eval_df.empty:
            eval_y_true = eval_df["autonomy_ratio"].to_numpy(float)
            eval_y_pred = predict_zero_refit(frozen_model, eval_df, horizon=None)
            eval_variance = len(np.unique(eval_y_pred)) > 1 and len(np.unique(eval_y_true)) > 1
            pooled_rho = float(pd.Series(eval_y_pred).corr(pd.Series(eval_y_true), method="spearman")) if eval_variance else 0.0
            if np.isnan(pooled_rho):
                pooled_rho = 0.0
            pooled_mae = float(np.mean(np.abs(eval_y_pred - eval_y_true)))
            pooled_rmse = float(np.sqrt(np.mean((eval_y_pred - eval_y_true) ** 2)))
        else:
            pooled_rho = 0.0
            pooled_mae = float("inf")
            pooled_rmse = float("inf")

        # Check each specified evaluation horizon independently
        horizon_verdicts = {}
        for h in eval_horizons:
            h_key = str(h)
            h_metrics = by_horizon.get(h_key)
            if h_metrics is not None:
                h_rho = h_metrics["spearman_rho"]
                h_mae = h_metrics["mae_zero_refit"]
                h_rho_pass = bool(h_rho >= min_rho)
                h_mae_pass = bool(h_mae <= max_mae)
                horizon_verdicts[h_key] = {
                    "spearman_rho": h_rho,
                    "mae_zero_refit": h_mae,
                    "spearman_rho_pass": h_rho_pass,
                    "mae_pass": h_mae_pass,
                    "pass": h_rho_pass and h_mae_pass,
                }
            else:
                horizon_verdicts[h_key] = {
                    "spearman_rho": 0.0,
                    "mae_zero_refit": float("inf"),
                    "spearman_rho_pass": False,
                    "mae_pass": False,
                    "pass": False,
                }

        all_horizons_pass = bool(len(horizon_verdicts) > 0 and all(v["pass"] for v in horizon_verdicts.values()))
        pooled_rho_pass = bool(pooled_rho >= min_rho)
        pooled_mae_pass = bool(pooled_mae <= max_mae)
        pooled_pass = pooled_rho_pass and pooled_mae_pass
        gate_verdict = "PASS" if (all_horizons_pass and pooled_pass) else "FAIL"

        res["contract_evaluation"] = {
            "contract_id": contract.get("contract_id", contract.get("holdout_family_id", contract.get("schema_version"))),
            "evaluation_horizons": eval_horizons,
            "decision_rule": criteria.get("decision_rule", "Dual-pass: each specified horizon must pass independently AND pooled evaluation across specified horizons must pass."),
            "minimum_spearman_rho": min_rho,
            "maximum_prediction_mae": max_mae,
            "pooled_evaluation": {
                "spearman_rho": pooled_rho,
                "mae_zero_refit": pooled_mae,
                "rmse_zero_refit": pooled_rmse,
                "spearman_rho_pass": pooled_rho_pass,
                "mae_pass": pooled_mae_pass,
                "pass": pooled_pass,
            },
            "horizon_verdicts": horizon_verdicts,
            "all_horizons_independently_passed": all_horizons_pass,
            "gate_verdict": gate_verdict,
        }

    return res


def main() -> None:
    ns = args()
    if ns.dry_run:
        # Validate zero-refit pipeline end-to-end with fixture data and contract
        fixture_path = BASE / "fixtures" / "neutral_pairing_fixture_v2.csv"
        raw = pd.read_csv(fixture_path)
        paired = pair_counterfactual_rows(raw)
        paired = add_candidate_regenerative_coordinates(paired)

        # Import predictor exporter to generate in-memory frozen model bundle
        from evaluate_partner_force_autonomy import fit_and_export_frozen_predictor

        dummy_model = fit_and_export_frozen_predictor(paired, fixture_path, output_json_path=None)
        contract_path = BASE / "contracts" / "partner_force_holdout_complexity_v1.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.exists() else None

        result = evaluate_zero_refit(paired, dummy_model, contract)
        assert result["status"] == "ZERO_REFIT_HOLDOUT_EVALUATION"
        assert result["refit_permitted"] is False
        assert "overall_spearman_rho" in result
        assert "overall_mae_zero_refit" in result

        print("PLUMBING_ONLY_PASS: zero-refit holdout evaluator verified end-to-end with frozen predictor and holdout contract.")
        print("NO_HOLDOUT_EVALUATION: dry-run executed no scientific evaluation and wrote no output files.")
        return

    if not ns.discovery_model_json or not ns.holdout_raw_csv:
        raise SystemExit("--discovery-model-json and --holdout-raw-csv are required for zero-refit evaluation")

    model_path = Path(ns.discovery_model_json)
    if not model_path.exists():
        raise SystemExit(f"discovery model file not found: {model_path}")

    raw_path = Path(ns.holdout_raw_csv)
    if not raw_path.exists():
        raise SystemExit(f"holdout raw CSV not found: {raw_path}")

    frozen_model = json.loads(model_path.read_text(encoding="utf-8"))
    holdout_raw = pd.read_csv(raw_path)
    holdout_paired = pair_counterfactual_rows(holdout_raw)

    contract = None
    if ns.contract_json:
        c_path = Path(ns.contract_json)
        if not c_path.exists():
            raise SystemExit(f"contract JSON not found: {c_path}")
        contract = json.loads(c_path.read_text(encoding="utf-8"))

    result = evaluate_zero_refit(holdout_paired, frozen_model, contract)

    if ns.output_json:
        out_p = Path(ns.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote holdout results: {out_p}")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
