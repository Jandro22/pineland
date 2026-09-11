from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score


KEYS = ["seed", "recruitment_mult", "fielding_mult", "capital_mult"]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite_auc(y: np.ndarray, score: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    finite = np.isfinite(score)
    if not finite.all():
        finite_values = score[finite]
        if len(finite_values):
            lo = float(finite_values.min())
            hi = float(finite_values.max())
        else:
            lo, hi = -1.0, 1.0
        score = score.copy()
        score[np.isneginf(score)] = lo - max(1.0, abs(lo))
        score[np.isposinf(score)] = hi + max(1.0, abs(hi))
        score[np.isnan(score)] = lo - 2.0 * max(1.0, abs(lo))
    return float(roc_auc_score(y, score))


def loso_knob_predictions(summary: pd.DataFrame, y: np.ndarray) -> np.ndarray:
    x = np.column_stack(
        [
            np.log(summary.recruitment_mult.to_numpy(float)),
            np.log(summary.fielding_mult.to_numpy(float)),
            np.log(summary.capital_mult.to_numpy(float)),
        ]
    )
    seeds = summary.seed.to_numpy(int)
    pred = np.zeros(len(summary), dtype=float)
    for seed in np.unique(seeds):
        test = seeds == seed
        train = ~test
        y_train = y[train]
        prevalence = float(np.clip(y_train.mean(), 1e-9, 1 - 1e-9))
        if len(np.unique(y_train)) < 2:
            pred[test] = prevalence
            continue
        model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000)
        model.fit(x[train], y_train)
        pred[test] = model.predict_proba(x[test])[:, 1]
    return np.clip(pred, 1e-9, 1 - 1e-9)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    raw = pd.read_csv(args.csv)
    required = {
        *KEYS,
        "time",
        "org_active",
        "capital",
        "initial_capital",
        "capital_inflow",
        "capital_outflow",
        "economy_positive",
        "recruitment_negative",
        "other_abs_flow",
        "accounting_residual",
        "lambda_k",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise SystemExit(f"missing required columns: {missing}")

    raw = raw.sort_values(KEYS + ["time"]).reset_index(drop=True)
    trajectory_rows = []
    for key, group in raw.groupby(KEYS, sort=True):
        group = group.sort_values("time")
        final = group.iloc[-1]
        row30 = group.iloc[(group.time.to_numpy(float) - 30.0).__abs__().argmin()]
        initial = float(group.iloc[0].initial_capital)
        scale = np.maximum.reduce(
            [
                np.ones(len(group)),
                np.full(len(group), abs(initial)),
                np.abs(group.capital_inflow.to_numpy(float)),
                np.abs(group.capital_outflow.to_numpy(float)),
            ]
        )
        normalized_residual = np.abs(group.accounting_residual.to_numpy(float)) / scale
        inactive = group[group.org_active.to_numpy(float) < 0.5]
        collapse_time = float(inactive.iloc[0].time) if len(inactive) else None
        capital_at_collapse = float(inactive.iloc[0].capital) if len(inactive) else None
        lambda_at_collapse = float(inactive.iloc[0].lambda_k) if len(inactive) else None
        exhausted_collapse = bool(
            len(inactive)
            and capital_at_collapse is not None
            and capital_at_collapse <= 1e-9 * max(1.0, initial)
        )

        net_burn_30 = (float(row30.capital_outflow) - float(row30.capital_inflow)) / max(
            float(row30.time), 1e-12
        )
        if net_burn_30 > 1e-12:
            runway = float(row30.capital) / net_burn_30
        else:
            runway = float("inf")
        trajectory_rows.append(
            {
                "seed": int(key[0]),
                "recruitment_mult": float(key[1]),
                "fielding_mult": float(key[2]),
                "capital_mult": float(key[3]),
                "collapsed_180": bool(float(final.org_active) < 0.5),
                "collapse_time": collapse_time,
                "capital_at_collapse": capital_at_collapse,
                "lambda_at_collapse": lambda_at_collapse,
                "exhausted_collapse": exhausted_collapse,
                "max_normalized_accounting_residual": float(normalized_residual.max()),
                "max_other_abs_flow": float(group.other_abs_flow.max()),
                "final_lambda_k": float(final.lambda_k),
                "capital_30": float(row30.capital),
                "inflow_30": float(row30.capital_inflow),
                "outflow_30": float(row30.capital_outflow),
                "net_burn_rate_30": float(net_burn_30),
                "early_runway_days": runway,
                "parameter_free_prediction": bool(runway < 150.0),
            }
        )

    summary = pd.DataFrame(trajectory_rows)
    y = summary.collapsed_180.to_numpy(int)
    runway_score = -summary.early_runway_days.to_numpy(float)
    runway_auc = _finite_auc(y, runway_score)
    knob_pred = loso_knob_predictions(summary, y)
    knob_auc = float(roc_auc_score(y, knob_pred)) if len(np.unique(y)) == 2 else None
    knob_ll = float(log_loss(y, knob_pred, labels=[0, 1]))
    parameter_free_accuracy = float(
        (summary.parameter_free_prediction.to_numpy(bool) == summary.collapsed_180.to_numpy(bool)).mean()
    )

    collapsed = summary[summary.collapsed_180]
    exhausted = collapsed[collapsed.exhausted_collapse]
    lambda_consistent = bool(
        len(exhausted) == 0
        or np.max(np.abs(exhausted.lambda_at_collapse.to_numpy(float) - 1.0)) <= 1e-8
    )
    max_residual = float(summary.max_normalized_accounting_residual.max())
    conservation = max_residual <= 1e-8
    discrimination = runway_auc is not None and runway_auc >= 0.95
    auc_regret = None if runway_auc is None or knob_auc is None else float(knob_auc - runway_auc)
    compression = auc_regret is not None and auc_regret <= 0.03

    result = {
        "schema_version": "pineland.mobilization_resource_flow_results.v1",
        "status": (
            "MECHANISTIC_RESOURCE_RUNWAY_SUPPORTED"
            if all([conservation, lambda_consistent, discrimination, compression])
            else "RESOURCE_LEDGER_CONFIRMED_RUNWAY_NOT_YET_SUPPORTED"
        ),
        "historical_outcomes_used": False,
        "input": str(Path(args.csv)),
        "input_sha256": sha256(args.csv),
        "trajectories": int(len(summary)),
        "seeds": [int(x) for x in sorted(summary.seed.unique())],
        "collapse": {
            "count": int(summary.collapsed_180.sum()),
            "rate": float(summary.collapsed_180.mean()),
            "capital_exhausted_count": int(summary.exhausted_collapse.sum()),
            "capital_exhausted_fraction_of_collapses": (
                float(summary.exhausted_collapse.sum() / summary.collapsed_180.sum())
                if summary.collapsed_180.sum()
                else None
            ),
        },
        "accounting": {
            "max_normalized_residual": max_residual,
            "max_other_abs_flow": float(summary.max_other_abs_flow.max()),
        },
        "early_runway": {
            "auc": runway_auc,
            "parameter_free_accuracy_runway_lt_150": parameter_free_accuracy,
            "knob_model_loso_auc": knob_auc,
            "knob_model_loso_logloss": knob_ll,
            "auc_regret_vs_knob_model": auc_regret,
        },
        "gates": {
            "capital_conservation": bool(conservation),
            "capital_exhaustion_lambda_consistency": bool(lambda_consistent),
            "early_runway_auc_ge_0_95": bool(discrimination),
            "auc_regret_vs_knobs_le_0_03": bool(compression),
            "all_pass": bool(all([conservation, lambda_consistent, discrimination, compression])),
        },
        "trajectory_summaries": trajectory_rows,
        "interpretation_guard": (
            "The capital stock-flow identity is a closed synthetic-assay accounting result. "
            "Any early-runway predictive law requires separate transport across topology, scale, "
            "organization phenotype, and historical cases."
        ),
    }
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "collapse": result["collapse"],
                "accounting": result["accounting"],
                "early_runway": result["early_runway"],
                "gates": result["gates"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
