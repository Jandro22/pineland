#!/usr/bin/env python3
"""Reviewer-driven post-completion diagnostics for the Stage-4 Phase Map.

This script was written after Stage-4 and Stage-5 production completed. It is
therefore descriptive / diagnostic, not part of the frozen confirmatory
analysis. Its purpose is to answer review questions that the original paper did
not report explicitly:

1. Does persistent bottleneck migration covary with the terminal indigenous
   coverage penalty?
2. How does the supported-capability contrast evolve across all frozen
   horizons?
3. In worlds with lower terminal coverage, how much comes from indigenous
   service differences versus changes in service demand?
4. What is the unconditional capability-sign x coverage-sign table, without
   conditioning first on +30d effectiveness?

The input directory is the original immutable Stage-4 Phase-Map shard folder.
No simulation is rerun.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


HORIZONS = (7, 30, 90, 180, 360)
EPS = 1.0e-6


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--contract", required=True, type=Path)
    p.add_argument("--phase-cell-summary", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    return p.parse_args()


def world_diagnostics(input_dir: Path, contract_path: Path) -> pd.DataFrame:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    factors = {str(x["cell_id"]): x for x in contract["cells"]}
    rows: list[dict[str, object]] = []

    trajectory_files = sorted(input_dir.glob("*.trajectory.csv"))
    expected = int(contract["cells_count"]) * int(contract["default_seed_count"])
    if len(trajectory_files) != expected:
        raise SystemExit(f"expected {expected} trajectory shards, found {len(trajectory_files)}")

    for trajectory_file in trajectory_files:
        primary_file = trajectory_file.with_name(trajectory_file.name.replace(".trajectory.csv", ".csv"))
        if not primary_file.exists():
            raise SystemExit(f"missing primary shard for {trajectory_file}")
        t = pd.read_csv(trajectory_file)
        p = pd.read_csv(primary_file)
        cell_id = str(t["cell_id"].iloc[0])
        seed = int(t["seed"].iloc[0])
        fac = factors[cell_id]

        pre = t[(t["phase"] == "PRE_SUPPORTED") & (t["interval_formal_bottleneck"] != "none")]
        pre = pre.sort_values("days_from_withdrawal", kind="mergesort")
        pre_bottleneck = str(pre.iloc[-1]["interval_formal_bottleneck"]) if len(pre) else "none"

        on = t[(t["phase"] == "SUPPORT_ON") & (t["days_from_withdrawal"].astype(float) > 0.0)]
        on = on.sort_values("days_from_withdrawal", kind="mergesort")
        seq = list(on["interval_formal_bottleneck"].astype(str))
        times = list(on["days_from_withdrawal"].astype(float))
        first_migration = math.nan
        for i in range(max(0, len(seq) - 1)):
            if seq[i] != pre_bottleneck and seq[i + 1] != pre_bottleneck:
                first_migration = times[i]
                break

        capability: dict[int, float] = {}
        for horizon in HORIZONS:
            z = p[p["horizon_days"].astype(float) == float(horizon)]
            on_p = z[z["branch"] == "SUPPORT_ON"]
            off_p = z[z["branch"] == "SUPPORT_OFF"]
            if len(on_p) != 1 or len(off_p) != 1:
                raise SystemExit(f"bad primary pair {cell_id}/{seed}/h{horizon}")
            capability[horizon] = float(
                on_p["composite_capability"].iloc[0] - off_p["composite_capability"].iloc[0]
            )

        on360 = on[np.isclose(on["days_from_withdrawal"].astype(float), 360.0)]
        off360 = t[
            (t["phase"] == "SUPPORT_OFF")
            & np.isclose(t["days_from_withdrawal"].astype(float), 360.0)
        ]
        if len(on360) != 1 or len(off360) != 1:
            raise SystemExit(f"missing terminal trajectory pair {cell_id}/{seed}")
        a, b = on360.iloc[0], off360.iloc[0]
        q_on = min(float(a["interval_formal_q_indigenous"]), 1.0)
        q_off = min(float(b["interval_formal_q_indigenous"]), 1.0)
        bott_on = str(a["interval_formal_bottleneck"])
        bott_off = str(b["interval_formal_bottleneck"])

        channel_fields = {
            "forcegen": ("interval_indigenous_graduates", "interval_military_losses"),
            "logistics": (
                "interval_indigenous_logistics_delivered",
                "interval_military_logistics_demanded",
            ),
            "command": ("interval_command_indigenous_service", "interval_command_opportunities"),
        }
        common = bott_on if bott_on == bott_off and bott_on in channel_fields else None
        i_on = i_off = d_on = d_off = math.nan
        d_i = d_d = d_log_i = d_log_d = d_log_q = math.nan
        if common:
            i_field, d_field = channel_fields[common]
            i_on, i_off = float(a[i_field]), float(b[i_field])
            d_on, d_off = float(a[d_field]), float(b[d_field])
            if common == "command":
                d_on *= 0.5
                d_off *= 0.5
            d_i, d_d = i_on - i_off, d_on - d_off
            if min(i_on, i_off, d_on, d_off) > 0.0:
                d_log_i = math.log(i_on / i_off)
                d_log_d = math.log(d_on / d_off)
                d_log_q = d_log_i - d_log_d

        rows.append(
            {
                "cell_id": cell_id,
                "seed": seed,
                "structure": fac["factor_structure"],
                "capacity": fac["factor_capacity_level"],
                "support_intensity": fac["factor_support_intensity"],
                "pre_bottleneck": pre_bottleneck,
                "migrated": math.isfinite(first_migration),
                "first_migration": first_migration,
                **{f"delta_cap_h{h}": capability[h] for h in HORIZONS},
                "q_on_h360": q_on,
                "q_off_h360": q_off,
                "delta_q_h360": q_on - q_off,
                "bott_on_h360": bott_on,
                "bott_off_h360": bott_off,
                "same_terminal_bottleneck": common is not None,
                "common_bottleneck": common or "",
                "I_on": i_on,
                "I_off": i_off,
                "D_on": d_on,
                "D_off": d_off,
                "delta_I": d_i,
                "delta_D": d_d,
                "delta_log_I": d_log_i,
                "delta_log_D": d_log_d,
                "delta_log_q_decomp": d_log_q,
            }
        )
    return pd.DataFrame(rows)


def control_matched_capability(input_dir: Path, contract_path: Path) -> pd.DataFrame:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    factors = pd.DataFrame(contract["cells"])[
        ["cell_id", "factor_structure", "factor_capacity_level", "factor_support_intensity"]
    ]
    primary_files = sorted(
        p for p in input_dir.glob("*.csv") if not p.name.endswith(".trajectory.csv")
    )
    expected = int(contract["cells_count"]) * int(contract["default_seed_count"])
    # Each world contributes both SUPPORT_ON and SUPPORT_OFF rows at each
    # registered horizon; therefore count distinct cell/seed worlds after load.
    primary = pd.concat((pd.read_csv(p) for p in primary_files), ignore_index=True)
    worlds = primary[["cell_id", "seed"]].drop_duplicates()
    if len(worlds) != expected:
        raise SystemExit(f"expected {expected} primary worlds, found {len(worlds)}")
    primary = primary.merge(factors, on="cell_id", validate="many_to_one")

    controls = primary[
        (primary["factor_support_intensity"].astype(float) == 0.0)
        & (primary["branch"] == "SUPPORT_OFF")
    ][
        [
            "factor_structure",
            "factor_capacity_level",
            "seed",
            "horizon_days",
            "composite_capability",
        ]
    ].rename(columns={"composite_capability": "control_capability"})

    treated = primary[primary["factor_support_intensity"].astype(float) > 0.0].merge(
        controls,
        on=["factor_structure", "factor_capacity_level", "seed", "horizon_days"],
        validate="many_to_one",
    )
    wide = treated.pivot(
        index=[
            "cell_id",
            "factor_structure",
            "factor_capacity_level",
            "factor_support_intensity",
            "seed",
            "horizon_days",
            "control_capability",
        ],
        columns="branch",
        values="composite_capability",
    ).reset_index()
    wide.columns.name = None
    wide["supported_vs_control"] = wide["SUPPORT_ON"] - wide["control_capability"]
    wide["retained_vs_control"] = wide["SUPPORT_OFF"] - wide["control_capability"]
    wide["dependency_gap"] = wide["SUPPORT_ON"] - wide["SUPPORT_OFF"]
    return wide.rename(
        columns={
            "SUPPORT_ON": "supported_capability",
            "SUPPORT_OFF": "withdrawn_capability",
        }
    )


def main() -> None:
    ns = args()
    ns.output_dir.mkdir(parents=True, exist_ok=True)
    d = world_diagnostics(ns.input_dir, ns.contract)
    d.to_csv(ns.output_dir / "stage4_phase_world_diagnostics_v1.csv", index=False)

    treated = d[d["support_intensity"].astype(float) > 0.0].copy()
    effective = treated[treated["delta_cap_h30"] > EPS].copy()
    penalty = treated[treated["delta_q_h360"] < -EPS].copy()
    same_penalty = penalty[penalty["same_terminal_bottleneck"].astype(bool)].copy()

    migration_rows = []
    for label, g in [
        ("treated_migrated", treated[treated["migrated"]]),
        ("treated_not_migrated", treated[~treated["migrated"]]),
        ("effective_migrated", effective[effective["migrated"]]),
        ("effective_not_migrated", effective[~effective["migrated"]]),
    ]:
        migration_rows.append(
            {
                "group": label,
                "n": len(g),
                "mean_delta_cap_h30": g["delta_cap_h30"].mean(),
                "mean_delta_q_h360": g["delta_q_h360"].mean(),
                "q_penalty_fraction": (g["delta_q_h360"] < -EPS).mean(),
                "effective_h30_fraction": (g["delta_cap_h30"] > EPS).mean(),
            }
        )
    pd.DataFrame(migration_rows).to_csv(
        ns.output_dir / "stage4_migration_penalty_summary_v1.csv", index=False
    )

    trajectory_rows = []
    for subset, g in [("all_treated", treated), ("h30_effective", effective)]:
        for horizon in HORIZONS:
            x = g[f"delta_cap_h{horizon}"]
            trajectory_rows.append(
                {
                    "subset": subset,
                    "horizon_days": horizon,
                    "n": len(g),
                    "mean_delta_capability": x.mean(),
                    "median_delta_capability": x.median(),
                    "positive_fraction": (x > EPS).mean(),
                }
            )
    pd.DataFrame(trajectory_rows).to_csv(
        ns.output_dir / "stage4_capability_trajectory_summary_v1.csv", index=False
    )

    sign_rows = []
    for cap_label, cap_mask in [
        ("positive", treated["delta_cap_h30"] > EPS),
        ("nonpositive", treated["delta_cap_h30"] <= EPS),
    ]:
        for q_label, q_mask in [
            ("positive", treated["delta_q_h360"] > EPS),
            ("negative", treated["delta_q_h360"] < -EPS),
            ("neutral", treated["delta_q_h360"].abs() <= EPS),
        ]:
            sign_rows.append(
                {
                    "unit": "world",
                    "capability_h30_sign": cap_label,
                    "coverage_h360_sign": q_label,
                    "count": int((cap_mask & q_mask).sum()),
                }
            )
    cells = pd.read_csv(ns.phase_cell_summary)
    cells = cells[cells["factor_support_intensity"].astype(float) > 0.0]
    for cap_label, cap_mask in [
        ("positive", cells["mean_delta_capability_h30"] > EPS),
        ("nonpositive", cells["mean_delta_capability_h30"] <= EPS),
    ]:
        for q_label, q_mask in [
            ("positive", cells["mean_delta_q_feasible_h360"] > EPS),
            ("negative", cells["mean_delta_q_feasible_h360"] < -EPS),
            ("neutral", cells["mean_delta_q_feasible_h360"].abs() <= EPS),
        ]:
            sign_rows.append(
                {
                    "unit": "cell",
                    "capability_h30_sign": cap_label,
                    "coverage_h360_sign": q_label,
                    "count": int((cap_mask & q_mask).sum()),
                }
            )
    pd.DataFrame(sign_rows).to_csv(
        ns.output_dir / "stage4_unconditional_sign_table_v1.csv", index=False
    )

    decomposition = {
        "status": "POST_COMPLETION_REVIEW_DRIVEN_DESCRIPTIVE_ANALYSIS",
        "treated_worlds": len(treated),
        "h30_effective_worlds": len(effective),
        "negative_coverage_worlds": len(penalty),
        "negative_coverage_same_terminal_bottleneck_worlds": len(same_penalty),
        "same_terminal_bottleneck": same_penalty["common_bottleneck"].value_counts().to_dict(),
        "lower_indigenous_service_fraction": float((same_penalty["delta_I"] < 0.0).mean()),
        "higher_demand_fraction": float((same_penalty["delta_D"] > 0.0).mean()),
        "both_lower_I_and_higher_D_fraction": float(
            ((same_penalty["delta_I"] < 0.0) & (same_penalty["delta_D"] > 0.0)).mean()
        ),
        "mean_delta_I": float(same_penalty["delta_I"].mean()),
        "mean_delta_D": float(same_penalty["delta_D"].mean()),
        "mean_delta_log_I": float(same_penalty["delta_log_I"].mean()),
        "mean_delta_log_D": float(same_penalty["delta_log_D"].mean()),
        "mean_delta_log_coverage_decomposition": float(same_penalty["delta_log_q_decomp"].mean()),
    }
    (ns.output_dir / "stage4_supply_demand_decomposition_v1.json").write_text(
        json.dumps(decomposition, indent=2) + "\n", encoding="utf-8"
    )

    common_logistics = treated[
        treated["same_terminal_bottleneck"].astype(bool)
        & (treated["common_bottleneck"] == "logistics")
        & (treated["D_on"] > 0.0)
        & (treated["D_off"] > 0.0)
    ].copy()
    x = common_logistics
    x["q_off"] = np.minimum(x["I_off"] / x["D_off"], 1.0)
    x["q_on_observed"] = np.minimum(x["I_on"] / x["D_on"], 1.0)
    x["q_on_control_demand"] = np.minimum(x["I_on"] / x["D_off"], 1.0)
    x["q_off_supported_demand"] = np.minimum(x["I_off"] / x["D_on"], 1.0)
    x["observed_effect"] = x["q_on_observed"] - x["q_off"]
    x["production_only_effect"] = x["q_on_control_demand"] - x["q_off"]
    x["demand_only_effect"] = x["q_off_supported_demand"] - x["q_off"]
    x["residual_nonadditivity"] = (
        x["observed_effect"] - x["production_only_effect"] - x["demand_only_effect"]
    )
    x.to_csv(ns.output_dir / "stage4_demand_standardized_worlds_v1.csv", index=False)

    standard_rows = []
    for label, g in [
        ("all_common_logistics", x),
        ("observed_penalty", x[x["observed_effect"] < -EPS]),
        (
            "h30_effective_penalty",
            x[(x["observed_effect"] < -EPS) & (x["delta_cap_h30"] > EPS)],
        ),
    ]:
        row: dict[str, object] = {"subset": label, "n": len(g)}
        for field in (
            "observed_effect",
            "production_only_effect",
            "demand_only_effect",
            "residual_nonadditivity",
        ):
            row[f"mean_{field}"] = float(g[field].mean())
            row[f"median_{field}"] = float(g[field].median())
        row["production_only_negative_fraction"] = float(
            (g["production_only_effect"] < -EPS).mean()
        )
        row["demand_only_negative_fraction"] = float((g["demand_only_effect"] < -EPS).mean())
        standard_rows.append(row)
    pd.DataFrame(standard_rows).to_csv(
        ns.output_dir / "stage4_demand_standardization_summary_v1.csv", index=False
    )

    control = control_matched_capability(ns.input_dir, ns.contract)
    control.to_csv(ns.output_dir / "stage4_control_matched_capability_v1.csv", index=False)
    control_rows = []
    for horizon, g in control.groupby("horizon_days", sort=True):
        cell = (
            g.groupby(
                [
                    "cell_id",
                    "factor_structure",
                    "factor_capacity_level",
                    "factor_support_intensity",
                ],
                as_index=False,
            )
            .agg(
                supported_vs_control=("supported_vs_control", "mean"),
                retained_vs_control=("retained_vs_control", "mean"),
                dependency_gap=("dependency_gap", "mean"),
            )
        )
        for unit, frame in [("world", g), ("cell", cell)]:
            supported = frame["supported_vs_control"]
            retained = frame["retained_vs_control"]
            control_rows.append(
                {
                    "horizon_days": horizon,
                    "unit": unit,
                    "n": len(frame),
                    "mean_supported_vs_control": supported.mean(),
                    "mean_retained_vs_control": retained.mean(),
                    "mean_dependency_gap": frame["dependency_gap"].mean(),
                    "supported_positive_fraction": (supported > EPS).mean(),
                    "retained_positive_fraction": (retained > EPS).mean(),
                    "strong_trap_fraction": (
                        (supported > EPS) & (retained < -EPS)
                    ).mean(),
                    "both_positive_fraction": (
                        (supported > EPS) & (retained > EPS)
                    ).mean(),
                    "both_negative_fraction": (
                        (supported < -EPS) & (retained < -EPS)
                    ).mean(),
                }
            )
    pd.DataFrame(control_rows).to_csv(
        ns.output_dir / "stage4_control_matched_summary_v1.csv", index=False
    )

    print(f"PASS review diagnostics: {len(d)} worlds; {len(treated)} treated")


if __name__ == "__main__":
    main()
