from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


KEYS = ["seed", "focal", "capital_mult", "shock_fraction"]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("metadata_csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    d = pd.read_csv(args.csv).sort_values(KEYS + ["time"])
    meta = pd.read_csv(args.metadata_csv)[["seed", "focal", "population"]].drop_duplicates()
    d = d.merge(meta, on=["seed", "focal"], how="left", validate="many_to_one")
    if d.population.isna().any():
        raise SystemExit(f"missing population metadata for {int(d.population.isna().sum())} rows")

    interval = 14.0
    admin_rate = 0.0015
    admin_cost = 0.20
    recruit_rate = 2.0e-6
    training_cost = 8.0
    admin_max_increment = 1.0 - np.exp(-admin_rate * interval)
    d["admin_affordability_ratio"] = d.government_capital / (
        d.population * admin_cost * admin_max_increment
    )
    d["training_affordability_ratio"] = d.government_capital / (
        d.population * recruit_rate * interval * training_cost
    )
    d["admin_binding"] = d.admin_affordability_ratio < 1.0
    d["training_binding"] = d.training_affordability_ratio < 1.0

    rows = []
    for key, g in d.groupby(KEYS, sort=True):
        g = g.sort_values("time")
        initial = g.iloc[0]; final = g.iloc[-1]
        cap_gap = float(initial.baseline_institution_capacity - initial.institution_capacity)
        admin_gap = float(initial.baseline_structural_admin - initial.structural_administrative_capacity)
        qcap = (
            float(final.institution_capacity - initial.institution_capacity) / cap_gap
            if cap_gap > 1e-12 else np.nan
        )
        qadmin = (
            float(final.structural_administrative_capacity - initial.structural_administrative_capacity) / admin_gap
            if admin_gap > 1e-12 else np.nan
        )
        positive_time = g[g.time > 0]
        rows.append({
            "seed": int(key[0]),
            "focal": int(key[1]),
            "capital_mult": float(key[2]),
            "shock_fraction": float(key[3]),
            "Q_capacity_180": qcap,
            "Q_admin_180": qadmin,
            "admin_binding_fraction": float(positive_time.admin_binding.mean()),
            "training_binding_fraction": float(positive_time.training_binding.mean()),
            "min_admin_affordability_ratio": float(g.admin_affordability_ratio.min()),
            "min_training_affordability_ratio": float(g.training_affordability_ratio.min()),
            "final_government_capital": float(final.government_capital),
        })
    t = pd.DataFrame(rows)
    by_cap = (
        t.groupby("capital_mult")
        .agg(
            n=("seed", "size"),
            mean_Q_capacity_180=("Q_capacity_180", "mean"),
            mean_Q_admin_180=("Q_admin_180", "mean"),
            mean_admin_binding_fraction=("admin_binding_fraction", "mean"),
            mean_training_binding_fraction=("training_binding_fraction", "mean"),
            min_admin_affordability_ratio=("min_admin_affordability_ratio", "min"),
            min_training_affordability_ratio=("min_training_affordability_ratio", "min"),
        )
        .reset_index()
        .sort_values("capital_mult")
    )
    caps = by_cap.capital_mult.to_numpy(float)
    binds = by_cap.mean_admin_binding_fraction.to_numpy(float)
    monotone_binding = bool(np.all(np.diff(binds) <= 1e-12))

    def value(cap: float, column: str) -> float:
        row = by_cap[np.isclose(by_cap.capital_mult, cap)]
        if len(row) != 1:
            raise SystemExit(f"missing unique capital cell {cap}")
        return float(row.iloc[0][column])

    low_gain_cap = value(0.25, "mean_Q_capacity_180") - value(0.05, "mean_Q_capacity_180")
    low_gain_admin = value(0.25, "mean_Q_admin_180") - value(0.05, "mean_Q_admin_180")
    low_gain = max(low_gain_cap, low_gain_admin) >= 0.02
    plateau_cap = abs(value(1.0, "mean_Q_capacity_180") - value(0.5, "mean_Q_capacity_180")) <= 0.01
    plateau_admin = abs(value(1.0, "mean_Q_admin_180") - value(0.5, "mean_Q_admin_180")) <= 0.01
    plateau_flat = plateau_cap and plateau_admin
    plateau_unbound = (
        value(0.5, "mean_admin_binding_fraction") <= 0.01
        and value(1.0, "mean_admin_binding_fraction") <= 0.01
    )
    gates = {
        "binding_fraction_nonincreasing": monotone_binding,
        "low_capital_recovery_gain_ge_0_02": bool(low_gain),
        "recovery_plateau_0_5_to_1_abs_diff_le_0_01": bool(plateau_flat),
        "plateau_admin_binding_fraction_le_0_01": bool(plateau_unbound),
    }
    result = {
        "schema_version": "pineland.state_regeneration_capital_transition_results.v1",
        "status": (
            "RESOURCE_TO_ABSORPTIVE_SATURATION_TRANSITION_SUPPORTED"
            if all(gates.values())
            else "CAPITAL_TRANSITION_ARCHITECTURE_NOT_CONFIRMED"
        ),
        "historical_outcomes_used": False,
        "input": str(Path(args.csv)),
        "input_sha256": sha256(args.csv),
        "metadata_input": str(Path(args.metadata_csv)),
        "metadata_sha256": sha256(args.metadata_csv),
        "trajectory_count": int(len(t)),
        "capital_curve": by_cap.to_dict(orient="records"),
        "contrasts": {
            "Q_capacity_0_25_minus_0_05": float(low_gain_cap),
            "Q_admin_0_25_minus_0_05": float(low_gain_admin),
            "Q_capacity_1_minus_0_5": float(value(1.0, "mean_Q_capacity_180") - value(0.5, "mean_Q_capacity_180")),
            "Q_admin_1_minus_0_5": float(value(1.0, "mean_Q_admin_180") - value(0.5, "mean_Q_admin_180")),
        },
        "gates": gates,
        "interpretation_guard": "Synthetic state-regeneration architecture only. Afghanistan and other real cases may motivate the mechanism but do not validate these numerical thresholds or rates.",
    }
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "capital_curve": result["capital_curve"], "contrasts": result["contrasts"], "gates": gates}, indent=2))


if __name__ == "__main__":
    main()
