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
import hashlib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))

from partner_force_metrics import pair_counterfactual_rows
from partner_force_regenerative_coordinates import add_candidate_regenerative_coordinates


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_contract_is_frozen(contract_path: Path) -> None:
    freeze_path = BASE / "contracts" / "partner_force_autonomy_preregistration_freeze_v1.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    target = contract_path.resolve()
    for entry in freeze.get("frozen_artifacts", {}).values():
        candidate = Path(entry.get("path", ""))
        if not candidate.is_absolute():
            candidate = (BASE.parents[3] / candidate).resolve()
        if candidate == target:
            actual = _sha256_file(contract_path)
            if actual != entry.get("sha256"):
                raise ValueError(
                    f"holdout contract hash mismatch for frozen artifact {contract_path}: "
                    f"expected {entry.get('sha256')}, got {actual}"
                )
            return
    raise ValueError(f"holdout contract is not registered in preregistration freeze: {contract_path}")


def validate_holdout_panel_against_contract(
    paired: pd.DataFrame,
    contract: Dict[str, Any],
) -> None:
    family = str(contract["holdout_family_id"])
    expected_experiment = f"partner_force_autonomy_holdout_{family}_v1"
    expected_cells = {str(c["cell_id"]): c for c in contract["cells"]}
    expected_seeds = set(
        range(
            int(contract["seed_base"]),
            int(contract["seed_base"]) + int(contract["default_seed_count"]),
        )
    )
    expected_horizons = {int(h) for h in contract["horizons_days"]}

    actual_experiments = set(paired["experiment_id"].astype(str))
    if actual_experiments != {expected_experiment}:
        raise ValueError(
            f"holdout experiment_id mismatch: expected {expected_experiment}, got {sorted(actual_experiments)}"
        )
    actual_versions = set(paired["design_version"].astype(str))
    if actual_versions != {"pineland.partner_force_holdout_contract.v1"}:
        raise ValueError(f"holdout design_version mismatch: {sorted(actual_versions)}")
    actual_cells = set(paired["cell_id"].astype(str))
    if actual_cells != set(expected_cells):
        raise ValueError(
            f"holdout cell coverage mismatch; missing={sorted(set(expected_cells)-actual_cells)}, "
            f"extra={sorted(actual_cells-set(expected_cells))}"
        )
    actual_seeds = {int(x) for x in paired["seed"].unique()}
    if actual_seeds != expected_seeds:
        raise ValueError(
            f"holdout seed coverage mismatch; missing={sorted(expected_seeds-actual_seeds)}, "
            f"extra={sorted(actual_seeds-expected_seeds)}"
        )
    actual_horizons = {int(x) for x in paired["horizon_days"].unique()}
    if actual_horizons != expected_horizons:
        raise ValueError(
            f"holdout horizon coverage mismatch; expected={sorted(expected_horizons)}, got={sorted(actual_horizons)}"
        )

    field_map = {
        "forcegen_mult": "indigenous_forcegen_multiplier",
        "logistics_mult": "indigenous_logistics_multiplier",
        "command_mult": "indigenous_command_multiplier",
        "air_intensity": "support_air_intensity",
        "air_bonus": "support_air_bonus",
        "logistics_rate": "support_logistics_rate",
        "command_reliability_boost": "support_command_reliability_boost",
        "command_latency_reduction_fraction": "support_command_latency_reduction_fraction",
        "forcegen_training_rate_boost": "support_forcegen_training_rate_boost",
    }
    for cell_id, spec in expected_cells.items():
        rows = paired[paired["cell_id"].astype(str) == cell_id]
        if set(rows["support_profile"].astype(str)) != {str(spec["support_profile"])}:
            raise ValueError(f"holdout support_profile mismatch for {cell_id}")
        for contract_key, column in field_map.items():
            expected = float(spec[contract_key])
            values = rows[column].to_numpy(float)
            if not np.allclose(values, expected, rtol=1e-12, atol=1e-12):
                raise ValueError(
                    f"holdout treatment mismatch for {cell_id}.{contract_key}: "
                    f"expected {expected}, observed range [{values.min()}, {values.max()}]"
                )


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


def predict_zero_refit_by_horizon(
    frozen_model: Dict[str, Any],
    df: pd.DataFrame,
) -> np.ndarray:
    """Predict each row with its preregistered horizon-specific frozen mapping."""
    if "horizon_days" not in df.columns:
        raise ValueError("holdout DataFrame is missing horizon_days")
    prediction = pd.Series(index=df.index, dtype=float)
    for h, hdf in df.groupby("horizon_days", sort=False):
        prediction.loc[hdf.index] = predict_zero_refit(frozen_model, hdf, horizon=int(h))
    if prediction.isna().any():
        raise ValueError("failed to generate horizon-specific predictions for every holdout row")
    return prediction.loc[df.index].to_numpy(float)


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
            # The pooled gate pools errors/ranks across the preregistered target
            # horizons, but every row is predicted with its frozen horizon-specific
            # calibration.  Using the overall model here would silently evaluate a
            # different predictor from the one used by the per-horizon gates.
            eval_y_pred = predict_zero_refit_by_horizon(frozen_model, eval_df)
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

    if not ns.discovery_model_json or not ns.holdout_raw_csv or not ns.contract_json:
        raise SystemExit(
            "--discovery-model-json, --holdout-raw-csv, and --contract-json are all required for scientific zero-refit evaluation"
        )

    model_path = Path(ns.discovery_model_json)
    if not model_path.exists():
        raise SystemExit(f"discovery model file not found: {model_path}")

    raw_path = Path(ns.holdout_raw_csv)
    if not raw_path.exists():
        raise SystemExit(f"holdout raw CSV not found: {raw_path}")

    frozen_model = json.loads(model_path.read_text(encoding="utf-8"))
    if frozen_model.get("schema_version") != "pineland.partner_force_autonomy_frozen_predictor.v1":
        raise SystemExit("discovery model is not a partner-force frozen predictor v1 artifact")
    if frozen_model.get("status") != "FROZEN_PREDICTOR_READY_FOR_ZERO_REFIT_HOLDOUTS":
        raise SystemExit("discovery model is not marked ready for zero-refit holdouts")
    freeze_path = BASE / "contracts" / "partner_force_autonomy_preregistration_freeze_v1.json"
    current_freeze_sha = _sha256_file(freeze_path)
    recorded_freeze_sha = frozen_model.get("discovery_provenance", {}).get("preregistration_freeze_sha256")
    if recorded_freeze_sha != current_freeze_sha:
        raise SystemExit(
            "frozen predictor was created under a different preregistration freeze; refusing holdout evaluation"
        )
    holdout_raw = pd.read_csv(raw_path)
    holdout_paired = pair_counterfactual_rows(holdout_raw)

    c_path = Path(ns.contract_json)
    if not c_path.exists():
        raise SystemExit(f"contract JSON not found: {c_path}")
    try:
        verify_contract_is_frozen(c_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    contract = json.loads(c_path.read_text(encoding="utf-8"))
    try:
        validate_holdout_panel_against_contract(holdout_paired, contract)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

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
