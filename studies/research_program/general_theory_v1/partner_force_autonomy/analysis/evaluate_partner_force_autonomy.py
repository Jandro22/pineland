"""Stage-3 discovery analysis for the Pineland partner-force autonomy program.

This script never launches Pineland.  It analyzes raw branch output created by
the Rust Stage-3 runner.  Dry-run mode is plumbing-only and writes no artifacts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))

from partner_force_metrics import pair_counterfactual_rows, analyze_paired_panel
from partner_force_regenerative_coordinates import (
    add_candidate_regenerative_coordinates,
    evaluate_bottleneck_competitors,
    evaluate_regeneration_vs_stocks,
    evaluate_supported_performance_vs_indigenous_state,
)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze real Stage-3 paired Pineland output")
    p.add_argument("--input-csv")
    p.add_argument("--output-dir", default=str(BASE / "outputs"))
    p.add_argument("--freeze-predictor-json", help="Path to export frozen predictor JSON")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def load_input(ns: argparse.Namespace) -> tuple[pd.DataFrame, Path]:
    if ns.dry_run:
        path = BASE / "fixtures" / "neutral_pairing_fixture_v2.csv"
    else:
        if not ns.input_csv:
            raise SystemExit("--input-csv is required for real analysis; the evaluator never substitutes fixture data")
        path = Path(ns.input_csv)
        if "fixtures" in path.parts:
            raise SystemExit("refusing scientific analysis of a fixture path; use --dry-run for plumbing validation")
    if not path.exists():
        raise SystemExit(f"input not found: {path}")
    return pd.read_csv(path), path


def get_git_commit() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=BASE)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fit_single_model(
    winner: str,
    df_sub: pd.DataFrame,
) -> Dict[str, Any]:
    original_n = len(df_sub)
    if winner == "formal_q_indigenous":
        df_sub = df_sub[
            np.isfinite(df_sub["formal_q_indigenous"].to_numpy(float))
            & (df_sub["formal_q_indigenous"].to_numpy(float) >= 0.0)
        ].copy()
        if df_sub.empty:
            raise ValueError("formal q estimand has no active-demand observations to fit")
    y = df_sub["autonomy_ratio"].to_numpy(float)
    if winner in ("formal_q_indigenous", "omega_min", "omega_mean", "omega_geo"):
        x = df_sub[winner].to_numpy(float)
        if len(np.unique(x)) >= 2:
            iso = IsotonicRegression(out_of_bounds="clip", increasing=True).fit(x, y)
            knots_x = [float(v) for v in iso.X_thresholds_]
            knots_y = [float(v) for v in iso.y_thresholds_]
            y_pred = np.interp(x, knots_x, knots_y, left=knots_y[0], right=knots_y[-1])
        else:
            val = float(np.mean(y)) if len(y) > 0 else 0.0
            knots_x = [0.0, 1.0]
            knots_y = [val, val]
            y_pred = np.full_like(y, val)
        rho = (
            float(pd.Series(x).corr(pd.Series(y), method="spearman"))
            if (len(np.unique(x)) > 1 and len(np.unique(y)) > 1)
            else 0.0
        )
        mae = float(np.mean(np.abs(y_pred - y))) if len(y) > 0 else 0.0
        return {
            "functional_form": "isotonic_regression",
            "coordinate": winner,
            "n_obs": int(len(x)),
            "n_no_active_demand_excluded": int(original_n - len(df_sub)),
            "knots_x": knots_x,
            "knots_y": knots_y,
            "in_sample_spearman_rho": 0.0 if np.isnan(rho) else rho,
            "in_sample_mae": mae,
        }
    elif winner == "regularized_additive":
        cols = ["omega_manpower", "omega_logistics", "omega_command"]
        X = df_sub[cols].to_numpy(float)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = Ridge(alpha=1.0)
        model.fit(X_scaled, y)
        y_pred = model.predict(X_scaled)
        rho = (
            float(pd.Series(y_pred).corr(pd.Series(y), method="spearman"))
            if (len(np.unique(y_pred)) > 1 and len(np.unique(y)) > 1)
            else 0.0
        )
        mae = float(np.mean(np.abs(y_pred - y))) if len(y) > 0 else 0.0
        return {
            "functional_form": "standard_scaler_ridge",
            "features": cols,
            "n_obs": int(len(X)),
            "scaler_mean": [float(v) for v in scaler.mean_],
            "scaler_scale": [float(v) for v in scaler.scale_],
            "ridge_coefficients": [float(v) for v in model.coef_],
            "ridge_intercept": float(model.intercept_),
            "in_sample_spearman_rho": 0.0 if np.isnan(rho) else rho,
            "in_sample_mae": mae,
        }
    else:
        raise ValueError(f"Unknown winning coordinate {winner}")


def fit_and_export_frozen_predictor(
    paired: pd.DataFrame,
    source_path: Path,
    output_json_path: Optional[Path] = None,
) -> Dict[str, Any]:
    # Preregistered target horizons: long-horizon resilience (90d and 180d)
    long_horizons = [90, 180]
    target_df = paired[paired["horizon_days"].isin(long_horizons)]
    selection_target_horizons = long_horizons if not target_df.empty else sorted([int(h) for h in paired["horizon_days"].unique()])
    selection_df = target_df if not target_df.empty else paired

    bottleneck_res = evaluate_bottleneck_competitors(selection_df)
    target_metrics = bottleneck_res["metrics"]
    ranking = bottleneck_res["competitor_ranking_by_grouped_cv_rmse"]

    # Also compute pooled metrics across all horizons for complete reporting
    pooled_res = evaluate_bottleneck_competitors(paired)
    pooled_metrics = pooled_res["metrics"]

    # Stage 3 v3 preregisters the Lean-derived q- coordinate as the primary
    # theory. Legacy Omega coordinates remain explicit discovery comparators and
    # can outperform q without replacing the confirmatory specification.
    if "formal_q_indigenous" in selection_df.columns:
        priority = ["formal_q_indigenous", "omega_min", "omega_geo", "omega_mean", "regularized_additive"]
        winner = "formal_q_indigenous"
        selection_mode = "PREREGISTERED_FORMAL_PRIMARY_NO_POSTHOC_SELECTION"
    else:
        # Historical v1/v2 compatibility: retain the original discovery tie rule.
        priority = ["omega_min", "omega_geo", "omega_mean", "regularized_additive"]
        best_rmse = float("inf")
        for cand in ranking:
            m = target_metrics.get(cand, {})
            rmse = m.get("grouped_cv_isotonic_rmse", m.get("rmse", float("inf")))
            if not np.isnan(rmse) and rmse < best_rmse:
                best_rmse = rmse
        close_candidates = []
        for cand in ranking:
            m = target_metrics.get(cand, {})
            rmse = m.get("grouped_cv_isotonic_rmse", m.get("rmse", float("inf")))
            if not np.isnan(rmse) and (rmse - best_rmse) <= 1e-4:
                close_candidates.append(cand)
        winner = min(close_candidates, key=lambda c: priority.index(c)) if close_candidates else ranking[0]
        selection_mode = "HISTORICAL_DISCOVERY_SELECTION"

    # Fit horizon-specific models for all horizons present in paired
    horizons = sorted(paired["horizon_days"].unique())
    horizon_models = {}
    for h in horizons:
        hdf = paired[paired["horizon_days"] == h]
        horizon_models[str(int(h))] = _fit_single_model(winner, hdf)

    # Fit overall model
    overall_model = _fit_single_model(winner, paired)

    freeze_manifest_path = BASE / "contracts" / "partner_force_autonomy_preregistration_freeze_v3.json"
    bundle = {
        "schema_version": "pineland.partner_force_autonomy_frozen_predictor.v1",
        "status": "FROZEN_PREDICTOR_READY_FOR_ZERO_REFIT_HOLDOUTS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "discovery_provenance": {
            "source_csv": str(source_path),
            "source_csv_sha256": get_file_sha256(source_path),
            "git_commit": get_git_commit(),
            "preregistration_freeze_sha256": get_file_sha256(freeze_manifest_path),
        },
        "selection_protocol": {
            "criterion": "preregistered_formal_q_primary; grouped_cv_metrics_are_comparative_diagnostics",
            "selection_mode": selection_mode,
            "target_horizons_days": selection_target_horizons,
            "target_metrics_summary": target_metrics,
            "pooled_all_horizons_metrics_summary": pooled_metrics,
            "candidate_ranking": ranking,
            "tie_break_priority": priority,
            "tie_break_tolerance": 1e-4,
            "winning_coordinate": winner,
        },
        "predictor_specification": {
            "winning_coordinate": winner,
            "functional_form": "isotonic_regression" if winner != "regularized_additive" else "standard_scaler_ridge",
            "formal_primary_coordinate": "formal_q_indigenous" if "formal_q_indigenous" in paired.columns else None,
            "legacy_comparator_coordinates": ["omega_min", "omega_geo", "omega_mean", "regularized_additive"],
            "subsystem_coordinates": ["omega_manpower", "omega_logistics", "omega_command"],
            "horizons_days": [int(h) for h in horizons],
            "horizon_models": horizon_models,
            "overall_model": overall_model,
        },
        "zero_refit_rule": "Holdout mechanism families MUST apply this predictor forward without adjusting parameters, weights, or knots.",
        "formal_estimand_scope": {
            "rule": "formal_q_indigenous predictive fitting/evaluation includes only observations with q >= 0 (at least one positive service demand)",
            "no_active_demand": "Rows encoded NO_ACTIVE_DEMAND/q=-1 are reported separately and never treated as numeric low-q observations.",
            "discovery_excluded_rows": int((paired["formal_q_indigenous"] < 0).sum()) if "formal_q_indigenous" in paired.columns else 0,
        },
    }

    if output_json_path is not None:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        output_json_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    return bundle


def main() -> None:
    ns = args()
    raw, source = load_input(ns)
    paired = pair_counterfactual_rows(raw)
    paired = add_candidate_regenerative_coordinates(paired)

    if ns.dry_run:
        assert len(paired) >= 2
        assert paired["autonomy_ratio"].notna().all()
        assert paired[["omega_manpower", "omega_logistics", "omega_command"]].notna().all().all()
        # Verify export plumbing without writing to disk
        bundle = fit_and_export_frozen_predictor(paired, source, output_json_path=None)
        assert bundle["status"] == "FROZEN_PREDICTOR_READY_FOR_ZERO_REFIT_HOLDOUTS"
        assert bundle["predictor_specification"]["winning_coordinate"] in ["formal_q_indigenous", "omega_min", "omega_geo", "omega_mean", "regularized_additive"]
        print("PLUMBING_ONLY_PASS: neutral fixture paired correctly; R_h/Delta_h, candidate coordinates, and frozen predictor export derive from raw branches.")
        print("NO_SCIENTIFIC_EVALUATION: dry-run generated no findings and wrote no output files.")
        return

    bundle = {
        "schema_version": "pineland.partner_force_autonomy_stage3_discovery_analysis.v1",
        "status": "DISCOVERY_ANALYSIS_NO_HOLDOUT_CLAIMS",
        "source_csv": str(source),
        "paired_summary": analyze_paired_panel(paired),
        "PF-H1_performance_masking_discovery": evaluate_supported_performance_vs_indigenous_state(paired),
        "PF-H2_bottleneck_discovery": evaluate_bottleneck_competitors(paired),
        "PF-H3_regeneration_discovery": evaluate_regeneration_vs_stocks(paired),
        "PF-H4_complexity_capacity": {
            "status": "NOT_TESTED_IN_STAGE3_DISCOVERY",
            "reason": "Complexity is intentionally reserved for a preregistered held-out mechanism family after discovery predictors are frozen.",
        },
        "claim_boundary": "These are in-model discovery results. No transport or real-world claim is licensed until zero-refit held-out tests are completed.",
    }
    outdir = Path(ns.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "partner_force_autonomy_stage3_discovery_metrics_v1.json"
    paired_path = outdir / "partner_force_autonomy_stage3_paired_v1.csv"
    json_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    paired.to_csv(paired_path, index=False)
    print(f"Wrote discovery metrics: {json_path}")
    print(f"Wrote derived paired panel: {paired_path}")

    # Export frozen predictor
    freeze_path = Path(ns.freeze_predictor_json) if ns.freeze_predictor_json else outdir / "partner_force_autonomy_frozen_predictor_v1.json"
    fit_and_export_frozen_predictor(paired, source, freeze_path)
    print(f"Wrote frozen predictor: {freeze_path}")
    print("STATUS: DISCOVERY ONLY — freeze candidate predictors before running any held-out mechanism family.")


if __name__ == "__main__":
    main()
