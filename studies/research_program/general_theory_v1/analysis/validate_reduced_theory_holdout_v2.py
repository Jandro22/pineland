#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from sklearn.metrics import balanced_accuracy_score, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_macrostate_closure_v1 import compute_spatial_weights
from simulate_reduced_theory import ReducedInsurgencyCOINSystem


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    err = pred - y
    rmse = float(np.sqrt(np.mean(err * err)))
    sd = float(np.std(y))
    return {
        "n": int(len(y)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": rmse,
        "truth_sd": sd,
        "nrmse": float(rmse / sd) if sd > 1e-12 else None,
        "r2": float(r2_score(y, pred)) if sd > 1e-12 else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("panel")
    ap.add_argument("--freeze", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    freeze = json.loads(Path(ns.freeze).read_text(encoding="utf-8"))
    params = freeze["parameters"]
    df = pd.read_csv(ns.panel)
    expected_seeds = set(range(2026101000, 2026101008))
    actual_seeds = set(int(x) for x in df.seed.unique())
    if actual_seeds != expected_seeds:
        raise SystemExit(f"holdout seed contract mismatch: expected {sorted(expected_seeds)}, got {sorted(actual_seeds)}")

    results = {}
    strict_pass = True
    for horizon in (30.0, 90.0):
        truth = {"M": [], "F": [], "E": [], "C": []}
        preds = {"M": [], "F": [], "E": [], "C": []}
        viability_true = []
        viability_pred = []
        seed_rows = []
        for seed, g in df.groupby("seed"):
            g0 = g[g.time == 0.0].sort_values("locality")
            gh = g[g.time == horizon].sort_values("locality")
            if len(g0) != 34 or len(gh) != 34:
                raise SystemExit(f"seed {seed} lacks 34 rows at t0/t{horizon:g}")
            W = compute_spatial_weights(34, seed=int(seed))
            system = ReducedInsurgencyCOINSystem(params, W)
            M0 = g0.m_member_depth.to_numpy(float)
            F0 = np.log1p(g0.f_effective_strength.clip(lower=0).to_numpy(float))
            E0 = g0.e_foothold_strength.to_numpy(float)
            C0 = g0.c_margin.to_numpy(float)
            Ko0 = float(g0.org_liquid_capital.mean())
            S = g0[["c_gov_effective", "s_admin_capacity", "s_institution_capacity", "s_government_governance"]].mean(axis=1).to_numpy(float)
            Y = g0.economic_output.to_numpy(float)
            y0 = np.concatenate([M0, F0, E0, C0, [Ko0]])
            sol = solve_ivp(system.derivatives, [0.0, horizon], y0, args=(S, Y, 1.0, 1.0), t_eval=[horizon], method="RK23")
            if not sol.success:
                raise SystemExit(f"ODE integration failed for seed {seed}: {sol.message}")
            n = 34
            mp = np.clip(sol.y[0:n, -1], 0.0, 1.0)
            fp = np.maximum(sol.y[n:2*n, -1], 0.0)
            ep = np.clip(sol.y[2*n:3*n, -1], 0.0, 1.0)
            cp = np.clip(sol.y[3*n:4*n, -1], -1.0, 1.0)
            mt = gh.m_member_depth.to_numpy(float)
            ft = np.log1p(gh.f_effective_strength.clip(lower=0).to_numpy(float))
            et = gh.e_foothold_strength.to_numpy(float)
            ct = gh.c_margin.to_numpy(float)
            for key, t, p in [("M", mt, mp), ("F", ft, fp), ("E", et, ep), ("C", ct, cp)]:
                truth[key].extend(t.tolist())
                preds[key].extend(p.tolist())
            viability_true.extend((et >= 0.20).astype(int).tolist())
            viability_pred.extend((ep >= 0.20).astype(int).tolist())
            seed_rows.append({
                "seed": int(seed),
                "true_viable_count": int(np.sum(et >= 0.20)),
                "pred_viable_count": int(np.sum(ep >= 0.20)),
                "mean_abs_E_error": float(np.mean(np.abs(ep - et))),
                "mean_abs_C_error": float(np.mean(np.abs(cp - ct))),
            })

        state_metrics = {k: metrics(np.asarray(truth[k]), np.asarray(preds[k])) for k in truth}
        bal = float(balanced_accuracy_score(viability_true, viability_pred))
        horizon_pass = all(
            m["nrmse"] is not None and m["nrmse"] <= 0.50 for m in state_metrics.values()
        ) and bal >= 0.80
        strict_pass = strict_pass and horizon_pass
        results[str(int(horizon))] = {
            "state_metrics": state_metrics,
            "viability_balanced_accuracy": bal,
            "strict_gate_pass": bool(horizon_pass),
            "seed_diagnostics": seed_rows,
        }

    out = {
        "schema_version": "pineland.reduced_theory_holdout_results.v2",
        "status": "PASS" if strict_pass else "FAIL",
        "historical_outcomes_used": False,
        "panel": ns.panel,
        "panel_sha256": sha256(ns.panel),
        "candidate_freeze": ns.freeze,
        "candidate_freeze_sha256": sha256(ns.freeze),
        "holdout_seeds": sorted(actual_seeds),
        "results_by_horizon": results,
        "strict_stage1_gate_pass": bool(strict_pass),
        "interpretation_guard": "This is a frozen-candidate untouched-seed same-family holdout. It neither validates historical transfer nor substitutes for topology/intervention/regime holdouts."
    }
    Path(ns.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], "strict_stage1_gate_pass": strict_pass, "results": results}, indent=2))


if __name__ == "__main__":
    main()
