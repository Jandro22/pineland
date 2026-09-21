#!/usr/bin/env python3
"""Precommitted analysis for the Stage-5 coordinated-development experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PRIMARY_HORIZON = 360.0
PRIMARY_BRANCH = "SUPPORT_OFF"
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260921
CHANNELS = ("forcegen", "logistics", "command")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--primary-csv", required=True)
    p.add_argument("--trajectory-csv", required=True)
    p.add_argument("--contract", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def paired_bootstrap_ci(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.choice(values, size=(BOOTSTRAP_RESAMPLES, len(values)), replace=True)
    means = draws.mean(axis=1)
    return tuple(np.quantile(means, [0.025, 0.975]))


def arm_metadata(contract: dict) -> pd.DataFrame:
    rows = []
    for c in contract["cells"]:
        rows.append(
            {
                "cell_id": c["cell_id"],
                "factor_starting_structure": c["factor_starting_structure"],
                "factor_channels": c["factor_channels"],
                "factor_channel_count": int(c["factor_channel_count"]),
                "factor_dose_regime": c["factor_dose_regime"],
                "factor_intensity": float(c["factor_intensity"]),
                "factor_normalized_total_effort": float(c["factor_normalized_total_effort"]),
                "factor_nominal_development_cost_per_day": float(
                    c["factor_nominal_development_cost_per_day"]
                ),
            }
        )
    return pd.DataFrame(rows)


def endpoint_table(primary: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    x = primary[
        primary["branch"].eq(PRIMARY_BRANCH)
        & np.isclose(primary["horizon_days"].astype(float), PRIMARY_HORIZON)
    ].copy()
    x = x.merge(meta, on="cell_id", how="left", validate="many_to_one")
    x["q_indigenous_capped"] = np.minimum(x["formal_q_indigenous"].astype(float), 1.0)
    return x


def matched_control_gains(end: pd.DataFrame) -> pd.DataFrame:
    control = end[end["factor_dose_regime"].eq("control")][
        ["factor_starting_structure", "seed", "q_indigenous_capped", "composite_capability"]
    ].rename(
        columns={
            "q_indigenous_capped": "q_control",
            "composite_capability": "capability_control",
        }
    )
    treated = end[~end["factor_dose_regime"].eq("control")].copy()
    out = treated.merge(
        control,
        on=["factor_starting_structure", "seed"],
        how="left",
        validate="many_to_one",
    )
    out["gain_q_vs_control"] = out["q_indigenous_capped"] - out["q_control"]
    out["gain_capability_vs_control"] = (
        out["composite_capability"].astype(float) - out["capability_control"].astype(float)
    )
    return out


def summarize_gains(gains: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "factor_starting_structure",
        "factor_channels",
        "factor_channel_count",
        "factor_dose_regime",
        "factor_intensity",
        "factor_normalized_total_effort",
    ]
    rows = []
    for keys, g in gains.groupby(group_cols, sort=True):
        q = g["gain_q_vs_control"].to_numpy(float)
        cap = g["gain_capability_vs_control"].to_numpy(float)
        qlo, qhi = paired_bootstrap_ci(q)
        clo, chi = paired_bootstrap_ci(cap)
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "n": len(g),
                "mean_gain_q_vs_control": float(np.mean(q)),
                "median_gain_q_vs_control": float(np.median(q)),
                "gain_q_boot95_lo": qlo,
                "gain_q_boot95_hi": qhi,
                "mean_gain_capability_vs_control": float(np.mean(cap)),
                "median_gain_capability_vs_control": float(np.median(cap)),
                "gain_capability_boot95_lo": clo,
                "gain_capability_boot95_hi": chi,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _lookup(
    end: pd.DataFrame,
    structure: str,
    intensity: float,
    channels: str,
    regime: str,
) -> pd.DataFrame:
    return end[
        end["factor_starting_structure"].eq(structure)
        & np.isclose(end["factor_intensity"].astype(float), intensity)
        & end["factor_channels"].eq(channels)
        & end["factor_dose_regime"].eq(regime)
    ][["seed", "q_indigenous_capped"]].rename(columns={"q_indigenous_capped": channels})


def factorial_interactions(end: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for structure in sorted(end["factor_starting_structure"].unique()):
        control = end[
            end["factor_starting_structure"].eq(structure)
            & end["factor_dose_regime"].eq("control")
        ][["seed", "q_indigenous_capped"]].rename(columns={"q_indigenous_capped": "q0"})
        for intensity in sorted(
            end.loc[end["factor_intensity"].astype(float) > 0, "factor_intensity"].astype(float).unique()
        ):
            singles = {
                "forcegen": _lookup(end, structure, intensity, "forcegen", "single_reference"),
                "logistics": _lookup(end, structure, intensity, "logistics", "single_reference"),
                "command": _lookup(end, structure, intensity, "command", "single_reference"),
            }
            for a, b in (("forcegen", "logistics"), ("forcegen", "command"), ("logistics", "command")):
                label = f"{a}+{b}"
                pair = _lookup(end, structure, intensity, label, "equal_channel_dose")
                m = control.merge(singles[a], on="seed").merge(singles[b], on="seed").merge(pair, on="seed")
                vals = m[label] - m[a] - m[b] + m["q0"]
                lo, hi = paired_bootstrap_ci(vals.to_numpy(float))
                rows.append(
                    {
                        "factor_starting_structure": structure,
                        "factor_intensity": intensity,
                        "interaction": label,
                        "order": 2,
                        "n": len(vals),
                        "mean_interaction_q": float(vals.mean()),
                        "median_interaction_q": float(vals.median()),
                        "boot95_lo": lo,
                        "boot95_hi": hi,
                    }
                )
            triple = _lookup(
                end,
                structure,
                intensity,
                "forcegen+logistics+command",
                "equal_channel_dose",
            )
            fl = _lookup(end, structure, intensity, "forcegen+logistics", "equal_channel_dose")
            fc = _lookup(end, structure, intensity, "forcegen+command", "equal_channel_dose")
            lc = _lookup(end, structure, intensity, "logistics+command", "equal_channel_dose")
            m = control
            for frame in [singles["forcegen"], singles["logistics"], singles["command"], fl, fc, lc, triple]:
                m = m.merge(frame, on="seed")
            vals = (
                m["forcegen+logistics+command"]
                - m["forcegen+logistics"]
                - m["forcegen+command"]
                - m["logistics+command"]
                + m["forcegen"]
                + m["logistics"]
                + m["command"]
                - m["q0"]
            )
            lo, hi = paired_bootstrap_ci(vals.to_numpy(float))
            rows.append(
                {
                    "factor_starting_structure": structure,
                    "factor_intensity": intensity,
                    "interaction": "forcegen+logistics+command",
                    "order": 3,
                    "n": len(vals),
                    "mean_interaction_q": float(vals.mean()),
                    "median_interaction_q": float(vals.median()),
                    "boot95_lo": lo,
                    "boot95_hi": hi,
                }
            )
    return pd.DataFrame(rows)


def breadth_premiums(end: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for structure in sorted(end["factor_starting_structure"].unique()):
        for intensity in sorted(
            end.loc[end["factor_intensity"].astype(float) > 0, "factor_intensity"].astype(float).unique()
        ):
            singles = {
                c: _lookup(end, structure, intensity, c, "single_reference") for c in CHANNELS
            }
            for subset in (
                ("forcegen", "logistics"),
                ("forcegen", "command"),
                ("logistics", "command"),
                ("forcegen", "logistics", "command"),
            ):
                label = "+".join(subset)
                multi = _lookup(end, structure, intensity, label, "equal_total_effort")
                m = multi
                for c in subset:
                    m = m.merge(singles[c], on="seed")
                best_single = m[list(subset)].max(axis=1)
                vals = m[label] - best_single
                lo, hi = paired_bootstrap_ci(vals.to_numpy(float))
                rows.append(
                    {
                        "factor_starting_structure": structure,
                        "factor_intensity": intensity,
                        "channels": label,
                        "n": len(vals),
                        "mean_breadth_premium_q": float(vals.mean()),
                        "median_breadth_premium_q": float(vals.median()),
                        "boot95_lo": lo,
                        "boot95_hi": hi,
                    }
                )
    return pd.DataFrame(rows)


def bottleneck_summary(trajectory: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    x = trajectory[
        trajectory["phase"].eq(PRIMARY_BRANCH)
        & (trajectory["days_from_withdrawal"].astype(float) >= 0.0)
        & (trajectory["days_from_withdrawal"].astype(float) <= PRIMARY_HORIZON)
    ].copy()
    x = x.merge(meta, on="cell_id", how="left", validate="many_to_one")
    rows = []
    for (cell_id, seed), g in x.groupby(["cell_id", "seed"], sort=False):
        g = g.sort_values("days_from_withdrawal")
        seq = g["interval_formal_bottleneck"].astype(str).tolist()
        first = seq[0] if seq else "none"
        changed = any(v != first for v in seq[1:])
        m = g.iloc[0]
        rows.append(
            {
                "cell_id": cell_id,
                "seed": seed,
                "factor_starting_structure": m["factor_starting_structure"],
                "factor_channels": m["factor_channels"],
                "factor_dose_regime": m["factor_dose_regime"],
                "factor_intensity": m["factor_intensity"],
                "initial_postsplit_bottleneck": first,
                "bottleneck_changed_by_h360": changed,
                "modal_bottleneck_h360": pd.Series(seq).mode().iloc[0] if seq else "none",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    if contract.get("experiment_id") != "partner_force_stage5_rising_tide_v1":
        raise SystemExit("unexpected Stage-5 contract")
    primary = pd.read_csv(args.primary_csv)
    trajectory = pd.read_csv(args.trajectory_csv)
    meta = arm_metadata(contract)
    endpoint = endpoint_table(primary, meta)
    expected = int(contract["cells_count"]) * int(contract["default_seed_count"])
    if len(endpoint) != expected:
        raise SystemExit(f"expected {expected} primary endpoints, got {len(endpoint)}")

    gains = matched_control_gains(endpoint)
    gain_summary = summarize_gains(gains)
    interactions = factorial_interactions(endpoint)
    breadth = breadth_premiums(endpoint)
    bottlenecks = bottleneck_summary(trajectory, meta)

    gains.to_csv(outdir / "stage5_seed_level_retained_gains_v1.csv", index=False)
    gain_summary.to_csv(outdir / "stage5_retained_gain_summary_v1.csv", index=False)
    interactions.to_csv(outdir / "stage5_factorial_interactions_v1.csv", index=False)
    breadth.to_csv(outdir / "stage5_fixed_effort_breadth_premiums_v1.csv", index=False)
    bottlenecks.to_csv(outdir / "stage5_bottleneck_paths_v1.csv", index=False)

    summary = {
        "schema_version": "pineland.partner_force_stage5_rising_tide_analysis.v1",
        "experiment_id": contract["experiment_id"],
        "primary_branch": PRIMARY_BRANCH,
        "primary_horizon_days": PRIMARY_HORIZON,
        "expected_worlds": expected,
        "observed_primary_endpoints": len(endpoint),
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "output_files": [
            "stage5_seed_level_retained_gains_v1.csv",
            "stage5_retained_gain_summary_v1.csv",
            "stage5_factorial_interactions_v1.csv",
            "stage5_fixed_effort_breadth_premiums_v1.csv",
            "stage5_bottleneck_paths_v1.csv",
        ],
    }
    (outdir / "stage5_analysis_summary_v1.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
