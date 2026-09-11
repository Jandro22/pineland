from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


MILESTONES = [180.0, 360.0, 720.0, 1080.0, 1440.0]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exp_model(t: np.ndarray, a: float, tau: float) -> np.ndarray:
    return a * (1.0 - np.exp(-t / tau))


def aic_from_sse(sse: float, n: int, k: int) -> float:
    mse = max(float(sse) / max(n, 1), 1e-15)
    return float(n * math.log(mse) + 2.0 * k)


def fit_linear(t: np.ndarray, q: np.ndarray) -> tuple[float, np.ndarray]:
    denom = float(np.dot(t, t))
    a = float(np.dot(t, q) / denom) if denom > 0 else 0.0
    return a, a * t


def fit_exponential(t: np.ndarray, q: np.ndarray) -> tuple[float, float, np.ndarray] | None:
    final = float(q[-1]) if len(q) else 0.1
    a0 = float(np.clip(final if abs(final) > 1e-6 else 0.1, -2.0, 2.0))
    try:
        params, _ = curve_fit(
            exp_model,
            t,
            q,
            p0=[a0, 360.0],
            bounds=([-5.0, 1.0], [5.0, 100000.0]),
            maxfev=30000,
        )
    except Exception:
        return None
    a, tau = map(float, params)
    pred = exp_model(t, a, tau)
    if not (np.isfinite(a) and np.isfinite(tau) and np.all(np.isfinite(pred))):
        return None
    return a, tau, pred


def first_crossing(t: np.ndarray, q: np.ndarray, threshold: float) -> float | None:
    hit = np.flatnonzero(q >= threshold)
    return None if len(hit) == 0 else float(t[hit[0]])


def trajectory_fit(t: np.ndarray, q: np.ndarray) -> dict:
    lin_a, lin_pred = fit_linear(t, q)
    lin_sse = float(np.sum((q - lin_pred) ** 2))
    lin_aic = aic_from_sse(lin_sse, len(t), 1)
    exp = fit_exponential(t, q)
    if exp is None:
        exp_a = exp_tau = None
        exp_aic = float("inf")
    else:
        exp_a, exp_tau, exp_pred = exp
        exp_sse = float(np.sum((q - exp_pred) ** 2))
        exp_aic = aic_from_sse(exp_sse, len(t), 2)

    split = int(math.ceil(0.70 * len(t)))
    split = max(2, min(split, len(t) - 1))
    t_train, q_train = t[:split], q[:split]
    t_test, q_test = t[split:], q[split:]
    early_lin_a, _ = fit_linear(t_train, q_train)
    lin_rmse = float(np.sqrt(np.mean((q_test - early_lin_a * t_test) ** 2)))
    early_exp = fit_exponential(t_train, q_train)
    if early_exp is None:
        exp_rmse = float("inf")
    else:
        ea, etau, _ = early_exp
        exp_rmse = float(np.sqrt(np.mean((q_test - exp_model(t_test, ea, etau)) ** 2)))

    return {
        "linear_slope": lin_a,
        "linear_aic": lin_aic,
        "exponential_A": exp_a,
        "exponential_tau_days": exp_tau,
        "exponential_aic": exp_aic if np.isfinite(exp_aic) else None,
        "exponential_aic_wins": bool(exp_aic < lin_aic),
        "heldout_linear_rmse": lin_rmse,
        "heldout_exponential_rmse": exp_rmse if np.isfinite(exp_rmse) else None,
        "exponential_heldout_rmse_wins": bool(exp_rmse < lin_rmse),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    data = pd.read_csv(ns.csv).sort_values(
        ["seed", "focal", "capital_mult", "shock_fraction", "time"]
    )
    required = {
        "seed", "focal", "capital_mult", "shock_fraction", "time",
        "institution_capacity", "government_effective_control",
    }
    missing = sorted(required - set(data.columns))
    if missing:
        raise SystemExit(f"missing columns: {missing}")

    controls = data[data.shock_fraction == 1.0][
        ["seed", "focal", "capital_mult", "time", "institution_capacity", "government_effective_control"]
    ].rename(columns={
        "institution_capacity": "control_institution_capacity",
        "government_effective_control": "control_government_effective_control",
    })
    shocked = data[data.shock_fraction < 1.0].merge(
        controls,
        on=["seed", "focal", "capital_mult", "time"],
        how="left",
        validate="many_to_one",
    )
    if shocked.control_institution_capacity.isna().any():
        raise SystemExit("missing matched control observations")
    keys = ["seed", "focal", "capital_mult", "shock_fraction"]
    gap0 = shocked[shocked.time == 0].copy()
    gap0["capacity_gap0"] = gap0.control_institution_capacity - gap0.institution_capacity
    base = gap0.set_index(keys)["capacity_gap0"]
    shocked = shocked.join(base, on=keys, validate="many_to_one")
    shocked["capacity_gap"] = shocked.control_institution_capacity - shocked.institution_capacity
    shocked["Q_capacity"] = np.where(
        shocked.capacity_gap0.abs() > 1e-12,
        1.0 - shocked.capacity_gap / shocked.capacity_gap0,
        np.nan,
    )

    trajectories = []
    milestone_rows = []
    for key, group in shocked.groupby(keys):
        group = group.sort_values("time")
        t = group.time.to_numpy(float)
        q = group.Q_capacity.to_numpy(float)
        eligible = len(t) >= 8 and np.all(np.isfinite(q))
        record = dict(zip(keys, key)) | {
            "observations": int(len(t)),
            "eligible": bool(eligible),
            "time_Q50": first_crossing(t, q, 0.50) if eligible else None,
            "time_Q80": first_crossing(t, q, 0.80) if eligible else None,
            "final_Q_capacity": float(q[-1]) if len(q) and np.isfinite(q[-1]) else None,
        }
        if eligible:
            record |= trajectory_fit(t, q)
        trajectories.append(record)
        if eligible:
            for milestone in MILESTONES:
                row = group[np.isclose(group.time, milestone)]
                if not row.empty:
                    milestone_rows.append(dict(zip(keys, key)) | {
                        "time": milestone,
                        "Q_capacity": float(row.iloc[0].Q_capacity),
                    })

    traj = pd.DataFrame(trajectories)
    eligible = traj[traj.eligible].copy()
    if eligible.empty:
        raise SystemExit("no eligible long-horizon trajectories")

    aic_win = float(eligible.exponential_aic_wins.mean())
    rmse_win = float(eligible.exponential_heldout_rmse_wins.mean())
    q50_fraction = float(eligible.time_Q50.notna().mean())

    tau_by_shock = []
    tau_gate = True
    for shock, group in eligible.groupby("shock_fraction"):
        tau = group.loc[
            group.exponential_tau_days.notna() & (group.exponential_A > 0),
            "exponential_tau_days",
        ].to_numpy(float)
        mean_tau = float(np.mean(tau)) if len(tau) else None
        cv = float(np.std(tau, ddof=1) / mean_tau) if len(tau) >= 2 and mean_tau and mean_tau > 0 else None
        passes = bool(len(tau) >= 4 and cv is not None and cv <= 0.50)
        tau_gate &= passes
        tau_by_shock.append({
            "shock_fraction": float(shock),
            "eligible_tau_count": int(len(tau)),
            "mean_tau_days": mean_tau,
            "median_tau_days": float(np.median(tau)) if len(tau) else None,
            "tau_cv": cv,
            "passes_cv_gate": passes,
        })

    milestones = pd.DataFrame(milestone_rows)
    milestone_summary = []
    if not milestones.empty:
        for time, group in milestones.groupby("time"):
            milestone_summary.append({
                "time_days": float(time),
                "mean_Q_capacity": float(group.Q_capacity.mean()),
                "median_Q_capacity": float(group.Q_capacity.median()),
                "fraction_Q50": float((group.Q_capacity >= 0.50).mean()),
                "fraction_Q80": float((group.Q_capacity >= 0.80).mean()),
            })

    capital_summary = []
    if not milestones.empty:
        final_milestone = milestones[np.isclose(milestones.time, max(MILESTONES))]
        for capital, group in final_milestone.groupby("capital_mult"):
            capital_summary.append({
                "capital_mult": float(capital),
                "mean_Q_capacity_1440": float(group.Q_capacity.mean()),
                "median_Q_capacity_1440": float(group.Q_capacity.median()),
            })

    gates = {
        "exponential_aic_win_fraction_ge_0_70": bool(aic_win >= 0.70),
        "exponential_heldout_rmse_win_fraction_ge_0_70": bool(rmse_win >= 0.70),
        "fraction_reaching_Q50_ge_0_50": bool(q50_fraction >= 0.50),
        "tau_cv_each_shock_le_0_50": bool(tau_gate),
    }
    gates["single_timescale_promoted"] = bool(all(gates.values()))
    status = (
        "SINGLE_STATE_RECOVERY_TIMESCALE_SUPPORTED_ON_SYNTHETIC_ASSAY"
        if gates["single_timescale_promoted"]
        else "STATE_RECOVERY_MULTI_TIMESCALE_OR_CONTEXT_DEPENDENT"
    )

    result = {
        "schema_version": "pineland.state_regeneration_long_horizon_results.v1",
        "status": status,
        "historical_outcomes_used": False,
        "input": str(Path(ns.csv)),
        "input_sha256": sha256(ns.csv),
        "integrity": {
            "rows": int(len(data)),
            "seed_count": int(data.seed.nunique()),
            "focal_seed_pairs": int(data[["seed", "focal"]].drop_duplicates().shape[0]),
            "eligible_trajectories": int(len(eligible)),
            "total_shocked_trajectories": int(len(traj)),
        },
        "functional_form": {
            "exponential_aic_win_fraction": aic_win,
            "exponential_heldout_rmse_win_fraction": rmse_win,
            "fraction_reaching_Q50": q50_fraction,
            "fraction_reaching_Q80": float(eligible.time_Q80.notna().mean()),
            "tau_by_shock": tau_by_shock,
        },
        "milestones": milestone_summary,
        "capital_response_1440": capital_summary,
        "gates": gates,
        "interpretation_guard": "This identifies or rejects a scalar recovery timescale only for the implemented pure-recovery synthetic system. It is not a historical empirical estimate.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "gates": gates, "functional_form": result["functional_form"]}, indent=2))


if __name__ == "__main__":
    main()
