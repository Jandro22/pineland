from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_crossing(group: pd.DataFrame, column: str, threshold: float) -> float | None:
    hit = group[group[column] >= threshold]
    return None if hit.empty else float(hit.iloc[0].time)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()

    data = pd.read_csv(ns.csv).sort_values(
        ["seed", "focal", "capital_mult", "shock_fraction", "time"]
    )
    required_shocks = {0.1, 0.3, 0.5, 1.0}
    required_capital = {0.25, 0.5, 1.0, 2.0, 4.0}
    integrity = {
        "rows": int(len(data)),
        "seed_count": int(data.seed.nunique()),
        "focal_count_total": int(data[["seed", "focal"]].drop_duplicates().shape[0]),
        "capital_levels_complete": set(np.round(data.capital_mult.unique(), 10))
        == required_capital,
        "shock_levels_complete": set(np.round(data.shock_fraction.unique(), 10))
        == required_shocks,
    }

    controls = data[data.shock_fraction == 1.0].copy()
    control_cols = [
        "seed",
        "focal",
        "capital_mult",
        "time",
        "institution_capacity",
        "government_effective_control",
    ]
    controls = controls[control_cols].rename(
        columns={
            "institution_capacity": "control_institution_capacity",
            "government_effective_control": "control_government_effective_control",
        }
    )
    shocked = data[data.shock_fraction < 1.0].merge(
        controls, on=["seed", "focal", "capital_mult", "time"], how="left", validate="many_to_one"
    )
    if shocked.control_institution_capacity.isna().any():
        raise RuntimeError("missing matched no-shock control rows")

    # The time-zero gap is the experimentally induced deficit.  Compare every
    # later gap to that moving no-shock trajectory rather than to a fixed
    # baseline that may itself learn or decay.
    base = (
        shocked[shocked.time == 0]
        .set_index(["seed", "focal", "capital_mult", "shock_fraction"])
        .assign(
            gap0=lambda x: x.control_institution_capacity - x.institution_capacity,
            control_gap0=lambda x: x.control_government_effective_control
            - x.government_effective_control,
        )[["gap0", "control_gap0"]]
    )
    shocked = shocked.join(
        base,
        on=["seed", "focal", "capital_mult", "shock_fraction"],
        validate="many_to_one",
    )
    shocked["capacity_gap"] = (
        shocked.control_institution_capacity - shocked.institution_capacity
    )
    shocked["Q_capacity"] = np.where(
        shocked.gap0.abs() > 1e-12,
        1.0 - shocked.capacity_gap / shocked.gap0,
        np.nan,
    )
    shocked["effective_control_gap"] = (
        shocked.control_government_effective_control - shocked.government_effective_control
    )
    shocked["Q_effective_control"] = np.where(
        shocked.control_gap0.abs() > 1e-12,
        1.0 - shocked.effective_control_gap / shocked.control_gap0,
        np.nan,
    )

    keys = ["seed", "focal", "capital_mult", "shock_fraction"]
    trajectories = []
    for key, group in shocked.groupby(keys):
        group = group.sort_values("time")
        last = group.iloc[-1]
        trajectories.append(
            dict(zip(keys, key))
            | {
                "baseline_institution_capacity": float(last.baseline_institution_capacity),
                "baseline_structural_admin": float(last.baseline_structural_admin),
                "Q_capacity_final": float(last.Q_capacity),
                "Q_effective_control_final": (
                    None
                    if not np.isfinite(last.Q_effective_control)
                    else float(last.Q_effective_control)
                ),
                "time_Q50": first_crossing(group, "Q_capacity", 0.5),
                "time_Q80": first_crossing(group, "Q_capacity", 0.8),
                "final_capacity_gap": float(last.capacity_gap),
                "final_government_capital": float(last.government_capital),
                "final_institution_capacity": float(last.institution_capacity),
                "control_final_institution_capacity": float(
                    last.control_institution_capacity
                ),
            }
        )
    traj = pd.DataFrame(trajectories)

    # Capital effect is evaluated as within seed/focal/shock differences.  A
    # higher value is considered rescuing when Q rises as capital increases.
    monotonic = []
    capital_slopes = []
    for _, group in traj.groupby(["seed", "focal", "shock_fraction"]):
        group = group.sort_values("capital_mult")
        q = group.Q_capacity_final.to_numpy(float)
        monotonic.append(bool(np.all(np.diff(q) >= -1e-10)))
        if len(group) > 1:
            capital_slopes.append(
                float(np.polyfit(np.log(group.capital_mult.to_numpy(float)), q, 1)[0])
            )

    # Structural heterogeneity: within each shock/capital level, relate final
    # gap closure to the local pre-shock capacity and structural admin level.
    correlations = {}
    for field in ["baseline_institution_capacity", "baseline_structural_admin"]:
        vals = []
        for _, group in traj.groupby(["capital_mult", "shock_fraction"]):
            if group[field].nunique() > 1 and group.Q_capacity_final.nunique() > 1:
                vals.append(float(group[[field, "Q_capacity_final"]].corr().iloc[0, 1]))
        correlations[field] = {
            "matched_strata": len(vals),
            "mean_correlation": float(np.mean(vals)) if vals else None,
            "median_correlation": float(np.median(vals)) if vals else None,
        }

    shock_summary = (
        traj.groupby("shock_fraction", as_index=False)
        .agg(
            mean_Q_final=("Q_capacity_final", "mean"),
            median_Q_final=("Q_capacity_final", "median"),
            p_Q50=("time_Q50", lambda x: float(x.notna().mean())),
            p_Q80=("time_Q80", lambda x: float(x.notna().mean())),
        )
        .to_dict("records")
    )
    capital_summary = (
        traj.groupby("capital_mult", as_index=False)
        .agg(
            mean_Q_final=("Q_capacity_final", "mean"),
            median_Q_final=("Q_capacity_final", "median"),
            p_Q50=("time_Q50", lambda x: float(x.notna().mean())),
            p_Q80=("time_Q80", lambda x: float(x.notna().mean())),
        )
        .to_dict("records")
    )

    # Time-course summary keeps the moving-counterfactual interpretation visible.
    time_course = (
        shocked.groupby(["time", "capital_mult", "shock_fraction"], as_index=False)
        .agg(
            mean_Q_capacity=("Q_capacity", "mean"),
            median_Q_capacity=("Q_capacity", "median"),
            mean_capacity_gap=("capacity_gap", "mean"),
        )
        .to_dict("records")
    )

    result = {
        "schema_version": "pineland.state_regeneration_analysis.v1",
        "status": "synthetic_state_regeneration_not_state_reproduction_number",
        "historical_outcomes_used": False,
        "input": str(Path(ns.csv)),
        "input_sha256": sha(ns.csv),
        "integrity": integrity,
        "trajectory_count": int(len(traj)),
        "primary": {
            "mean_final_Q_capacity": float(traj.Q_capacity_final.mean()),
            "median_final_Q_capacity": float(traj.Q_capacity_final.median()),
            "fraction_reaching_Q50": float(traj.time_Q50.notna().mean()),
            "fraction_reaching_Q80": float(traj.time_Q80.notna().mean()),
        },
        "capital_effect": {
            "matched_strata": len(monotonic),
            "monotone_rescue_fraction": float(np.mean(monotonic)) if monotonic else None,
            "mean_log_capital_slope_on_final_Q": (
                float(np.mean(capital_slopes)) if capital_slopes else None
            ),
            "median_log_capital_slope_on_final_Q": (
                float(np.median(capital_slopes)) if capital_slopes else None
            ),
        },
        "structural_heterogeneity": correlations,
        "shock_summary": shock_summary,
        "capital_summary": capital_summary,
        "time_course": time_course,
        "trajectory_summaries": traj.to_dict("records"),
        "interpretation_guard": (
            "Q_S is matched closure of an induced capacity gap relative to a moving no-shock "
            "counterfactual. It characterizes the implemented centralized state-regeneration "
            "process; it is not an offspring reproduction number and is not historical evidence."
        ),
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(ns.out)
    print("integrity", integrity)
    print("primary", result["primary"])
    print("capital", result["capital_effect"])
    print("structural", result["structural_heterogeneity"])


if __name__ == "__main__":
    main()
