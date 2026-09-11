#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.stats import wasserstein_distance
except Exception:
    wasserstein_distance = None


CONTINUOUS = [
    "log1p_actions_delta",
    "log1p_recruits_delta",
    "final_M",
    "final_logF",
    "final_E",
    "control_delta",
    "final_C",
    "final_state_control",
]

PRE11 = [
    "pre_M",
    "pre_logF",
    "pre_E",
    "pre_C",
    "pre_logKo",
    "pre_NM",
    "pre_L",
    "pre_Kintel",
    "pre_X",
    "pre_S",
    "pre_U",
]

SECONDARY = [
    "intelligence_delta",
    "underground_disruption_delta",
    "government_formation_losses_delta",
    "insurgent_formation_losses_delta",
    "final_hidden_value",
]

DOMAIN_SCALE_FLOOR = {
    "log1p_actions_delta": 0.75,
    "log1p_recruits_delta": 0.75,
    "final_M": 0.20,
    "final_logF": 0.50,
    "final_E": 0.20,
    "control_delta": 0.20,
    "final_C": 0.20,
    "final_state_control": 0.20,
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paired_signflip_p(diff: np.ndarray, rng: np.random.Generator, draws: int = 20000) -> float:
    diff = np.asarray(diff, float)
    if len(diff) == 0:
        return 1.0
    observed = abs(float(diff.mean()))
    if observed <= 1e-15:
        return 1.0
    signs = rng.choice(np.array([-1.0, 1.0]), size=(draws, len(diff)), replace=True)
    null = np.abs((signs * diff[None, :]).mean(axis=1))
    return float((1 + np.sum(null >= observed)) / (draws + 1))


def bh_qvalues(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    q = np.empty(n, float)
    running = 1.0
    for rank0 in range(n - 1, -1, -1):
        idx = order[rank0]
        rank = rank0 + 1
        running = min(running, p[idx] * n / rank)
        q[idx] = min(1.0, running)
    return q.tolist()


def wdist(a: np.ndarray, b: np.ndarray) -> float:
    if wasserstein_distance is not None:
        return float(wasserstein_distance(a, b))
    qs = np.linspace(0.0, 1.0, 1001)
    return float(np.mean(np.abs(np.quantile(a, qs) - np.quantile(b, qs))))


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    required = {
        "block",
        "seed",
        "locality",
        "stratum",
        "anchor_days",
        "horizon_days",
        "branch",
        "side",
        "assigned_hidden_value",
        "realized_hidden_value",
        "viable",
    } | set(PRE11) | set(CONTINUOUS) | set(SECONDARY)
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"missing columns: {missing}")
    if df.block.nunique() != 1:
        raise SystemExit("one stress block per analysis file is required")
    if df.horizon_days.nunique() != 1:
        raise SystemExit("one horizon per analysis file is required")
    if set(df.side.unique()) != {"low", "high"}:
        raise SystemExit("stress file must contain low and high sides")

    rng = np.random.default_rng(20261003)
    tests: list[dict] = []
    states: dict[tuple[int, int], dict] = {}
    secondary_by_state: dict[tuple[int, int], dict[str, float]] = {}
    max_pre11_abs_difference = 0.0
    hidden_separations = []

    for (seed, locality), g in df.groupby(["seed", "locality"], sort=True):
        low = g[g.side == "low"].sort_values("branch")
        high = g[g.side == "high"].sort_values("branch")
        if low.branch.tolist() != high.branch.tolist():
            raise SystemExit(f"branch mismatch for seed={seed}, locality={locality}")
        if len(low) == 0:
            raise SystemExit(f"empty branch panel for seed={seed}, locality={locality}")
        for col in PRE11:
            delta = np.max(np.abs(low[col].to_numpy(float) - high[col].to_numpy(float)))
            max_pre11_abs_difference = max(max_pre11_abs_difference, float(delta))
        hidden_separations.append(
            float(high.realized_hidden_value.mean() - low.realized_hidden_value.mean())
        )
        meta = {
            "seed": int(seed),
            "locality": int(locality),
            "stratum": str(g.stratum.iloc[0]),
        }
        states[(int(seed), int(locality))] = meta
        secondary_by_state[(int(seed), int(locality))] = {
            column: float(high[column].mean() - low[column].mean())
            for column in SECONDARY
        }

        lv = low.viable.to_numpy(float)
        hv = high.viable.to_numpy(float)
        diff = hv - lv
        rd = abs(float(hv.mean() - lv.mean()))
        tests.append(
            {
                **meta,
                "outcome": "viable",
                "kind": "binary",
                "mean_low": float(lv.mean()),
                "mean_high": float(hv.mean()),
                "high_minus_low": float(hv.mean() - lv.mean()),
                "absolute_risk_difference": rd,
                "practically_large": bool(rd > 0.15),
                "p_value": paired_signflip_p(diff, rng),
            }
        )

        for outcome in CONTINUOUS:
            a = low[outcome].to_numpy(float)
            b = high[outcome].to_numpy(float)
            d = b - a
            pooled = float(np.std(np.concatenate([a, b]), ddof=1)) if len(a) + len(b) > 2 else 0.0
            scale = max(pooled, DOMAIN_SCALE_FLOOR[outcome])
            smd = abs(float(d.mean())) / scale
            nw = wdist(a, b) / scale
            tests.append(
                {
                    **meta,
                    "outcome": outcome,
                    "kind": "continuous",
                    "mean_low": float(a.mean()),
                    "mean_high": float(b.mean()),
                    "high_minus_low": float(d.mean()),
                    "scale": scale,
                    "standardized_mean_difference": smd,
                    "normalized_wasserstein": nw,
                    "practically_large": bool(smd > 0.25 or nw > 0.25),
                    "p_value": paired_signflip_p(d, rng),
                }
            )

    qvals = bh_qvalues([float(x["p_value"]) for x in tests])
    for test, q in zip(tests, qvals):
        test["q_value_bh"] = q
        test["significant_and_large"] = bool(q <= 0.05 and test["practically_large"])

    state_results = []
    for key in sorted(states):
        subset = [x for x in tests if (x["seed"], x["locality"]) == key]
        state_results.append(
            {
                **states[key],
                "secondary_high_minus_low": secondary_by_state[key],
                "any_practically_large": any(x["practically_large"] for x in subset),
                "any_significant_and_large": any(x["significant_and_large"] for x in subset),
                "large_outcomes": [x["outcome"] for x in subset if x["practically_large"]],
                "significant_large_outcomes": [
                    x["outcome"] for x in subset if x["significant_and_large"]
                ],
            }
        )

    raw_rate = float(np.mean([x["any_practically_large"] for x in state_results]))
    sig_rate = float(np.mean([x["any_significant_and_large"] for x in state_results]))
    relevant = any(x["any_significant_and_large"] for x in state_results)
    secondary_summary = {
        column: {
            "max_abs_high_minus_low": float(
                max(abs(secondary_by_state[key][column]) for key in secondary_by_state)
            ),
            "mean_high_minus_low": float(
                np.mean([secondary_by_state[key][column] for key in secondary_by_state])
            ),
            "fraction_nonzero": float(
                np.mean(
                    [
                        abs(secondary_by_state[key][column]) > 1.0e-12
                        for key in secondary_by_state
                    ]
                )
            ),
        }
        for column in SECONDARY
    }
    if str(df.block.iloc[0]) in {"government_veterancy", "insurgent_veterancy"}:
        loss_columns = [
            "government_formation_losses_delta",
            "insurgent_formation_losses_delta",
        ]
        combat_exposure = []
        for (seed, locality), g in df.groupby(["seed", "locality"], sort=True):
            combat_exposure.append(
                any(float(g[column].max()) > 1.0e-12 for column in loss_columns)
            )
        secondary_summary["combat_exposure_fraction"] = float(np.mean(combat_exposure))
    strata = {}
    for stratum in sorted(set(x["stratum"] for x in state_results)):
        sub = [x for x in state_results if x["stratum"] == stratum]
        strata[stratum] = {
            "state_count": len(sub),
            "raw_practically_large_state_rate": float(
                np.mean([x["any_practically_large"] for x in sub])
            ),
            "significant_and_large_state_rate": float(
                np.mean([x["any_significant_and_large"] for x in sub])
            ),
        }

    result = {
        "schema_version": "pineland.v2_omitted_state_stress_analysis.v1",
        "status": "MACROSTATE_RELEVANT" if relevant else "NOT_DETECTED_IN_TESTED_SUPPORT",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "block": str(df.block.iloc[0]),
        "anchor_days": float(df.anchor_days.iloc[0]),
        "horizon_days": float(df.horizon_days.iloc[0]),
        "state_count": len(state_results),
        "branches_per_state": int(df.branch.nunique()),
        "integrity": {
            "competitive11_max_abs_difference_after_hidden_intervention": max_pre11_abs_difference,
            "mean_realized_hidden_high_minus_low": float(np.mean(hidden_separations)),
            "min_realized_hidden_high_minus_low": float(np.min(hidden_separations)),
        },
        "thresholds": {
            "binary_absolute_risk_difference": 0.15,
            "continuous_standardized_mean_difference": 0.25,
            "continuous_normalized_wasserstein": 0.25,
            "bh_q": 0.05,
        },
        "summary": {
            "raw_practically_large_state_rate": raw_rate,
            "significant_and_large_state_rate": sig_rate,
            "strata": strata,
        },
        "secondary_activation_diagnostics": secondary_summary,
        "states": state_results,
        "tests": tests,
        "interpretation_guard": (
            "A positive result establishes synthetic omitted-state sensitivity while the old "
            "competitive11 vector is held exactly fixed. It does not establish empirical effect "
            "size or historical prevalence. A null result screens the block off only over the "
            "tested support and horizons."
        ),
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "block": result["block"],
                "states": result["state_count"],
                "branches": result["branches_per_state"],
                "pre11_max_abs_difference": max_pre11_abs_difference,
                "secondary_activation": secondary_summary,
                **result["summary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    analyze(args.csv, args.out)
