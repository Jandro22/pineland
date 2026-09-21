#!/usr/bin/env python3
"""Analyze the prospectively frozen demand-clamp mechanism ablation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


HORIZONS = (7, 30, 90, 180, 360)
EPS = 1.0e-6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--contract", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    return p.parse_args()


def bootstrap_mean_ci(values: np.ndarray, seed: int, reps: int) -> tuple[float, float]:
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), size=(reps, len(values)))
    means = values[draws].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def main() -> None:
    ns = args()
    ns.output_dir.mkdir(parents=True, exist_ok=True)
    contract = json.loads(ns.contract.read_text(encoding="utf-8"))
    cells = {c["cell_id"]: c for c in contract["cells"]}
    expected = int(contract["cells_count"]) * int(contract["default_seed_count"])

    primaries = sorted(
        p for p in ns.input_dir.glob("task_*_cell_*_seed_*.csv") if ".trajectory.csv" not in p.name
    )
    if len(primaries) != expected:
        raise SystemExit(f"expected {expected} primary shards, found {len(primaries)}")

    world_rows: list[dict[str, object]] = []
    interval_rows: list[dict[str, object]] = []
    commits: set[str] = set()
    contract_hashes: set[str] = set()
    freeze_hashes: set[str] = set()

    for primary in primaries:
        trajectory = primary.with_name(primary.stem + ".trajectory.csv")
        metadata = primary.with_suffix(".json")
        if not trajectory.exists() or not metadata.exists():
            raise SystemExit(f"missing paired files for {primary}")
        meta = json.loads(metadata.read_text(encoding="utf-8"))
        if meta["output_sha256"] != sha256(primary):
            raise SystemExit(f"primary hash mismatch: {primary}")
        if meta["trajectory_sha256"] != sha256(trajectory):
            raise SystemExit(f"trajectory hash mismatch: {trajectory}")
        commits.add(str(meta["git_commit"]))
        contract_hashes.add(str(meta["contract_sha256"]))
        freeze_hashes.add(str(meta["freeze_sha256"]))

        p = pd.read_csv(primary)
        t = pd.read_csv(trajectory)
        cell_id = str(p["cell_id"].iloc[0])
        seed = int(p["seed"].iloc[0])
        cell = cells[cell_id]
        row: dict[str, object] = {
            "cell_id": cell_id,
            "scenario": cell["factor_scenario"],
            "mode": cell["factor_ablation_mode"],
            "seed": seed,
            "source_cell_id": cell["factor_source_cell_id"],
            "source_structure": cell["factor_structure"],
            "source_capacity": cell["factor_capacity_level"],
            "source_intensity": cell["factor_support_intensity"],
        }
        for horizon in HORIZONS:
            z = p[np.isclose(p["horizon_days"].astype(float), float(horizon))]
            on = z[z["branch"] == "SUPPORT_ON"]
            off = z[z["branch"] == "SUPPORT_OFF"]
            if len(on) != 1 or len(off) != 1:
                raise SystemExit(f"bad branch pair {cell_id}/{seed}/h{horizon}")
            row[f"delta_capability_h{horizon}"] = float(
                on["composite_capability"].iloc[0] - off["composite_capability"].iloc[0]
            )
            row[f"delta_q_h{horizon}"] = float(
                min(float(on["formal_q_indigenous"].iloc[0]), 1.0)
                - min(float(off["formal_q_indigenous"].iloc[0]), 1.0)
            )
            row[f"bottleneck_on_h{horizon}"] = str(on["formal_bottleneck"].iloc[0])
            row[f"bottleneck_off_h{horizon}"] = str(off["formal_bottleneck"].iloc[0])
            row[f"logistics_demand_on_h{horizon}"] = float(on["formal_logistics_demand"].iloc[0])
            row[f"logistics_demand_off_h{horizon}"] = float(off["formal_logistics_demand"].iloc[0])
            row[f"logistics_indigenous_on_h{horizon}"] = float(
                on["formal_logistics_indigenous_service"].iloc[0]
            )
            row[f"logistics_indigenous_off_h{horizon}"] = float(
                off["formal_logistics_indigenous_service"].iloc[0]
            )
        world_rows.append(row)

        if cell["factor_ablation_mode"] == "demand_clamped":
            post = t[t["phase"].isin(["SUPPORT_ON", "SUPPORT_OFF"])]
            wide = post.pivot(
                index="days_from_withdrawal",
                columns="phase",
                values="interval_military_logistics_demanded",
            ).dropna()
            wide = wide[wide.index.astype(float) > 0.0]
            for day, r in wide.iterrows():
                d_on = float(r["SUPPORT_ON"])
                d_off = float(r["SUPPORT_OFF"])
                err = abs(d_on - d_off) / max(abs(d_off), 1.0)
                interval_rows.append(
                    {
                        "scenario": cell["factor_scenario"],
                        "seed": seed,
                        "days_from_withdrawal": float(day),
                        "demand_on": d_on,
                        "demand_off": d_off,
                        "relative_error": err,
                    }
                )

    if len(commits) != 1 or len(contract_hashes) != 1 or len(freeze_hashes) != 1:
        raise SystemExit(
            f"production provenance not unique: commits={commits} contract={contract_hashes} freeze={freeze_hashes}"
        )

    worlds = pd.DataFrame(world_rows)
    intervals = pd.DataFrame(interval_rows)
    worlds.to_csv(ns.output_dir / "mechanism_ablation_worlds_v1.csv", index=False)
    intervals.to_csv(ns.output_dir / "mechanism_ablation_clamp_intervals_v1.csv", index=False)

    normal = worlds[worlds["mode"] == "normal"].copy()
    clamp = worlds[worlds["mode"] == "demand_clamped"].copy()
    keys = ["scenario", "seed"]
    paired = normal.merge(clamp, on=keys, suffixes=("_normal", "_clamp"), validate="one_to_one")
    for horizon in HORIZONS:
        paired[f"attenuation_q_h{horizon}"] = (
            paired[f"delta_q_h{horizon}_clamp"] - paired[f"delta_q_h{horizon}_normal"]
        )
        paired[f"change_capability_effect_h{horizon}"] = (
            paired[f"delta_capability_h{horizon}_clamp"]
            - paired[f"delta_capability_h{horizon}_normal"]
        )
    paired.to_csv(ns.output_dir / "mechanism_ablation_paired_v1.csv", index=False)

    reps = int(contract["analysis_rules"]["bootstrap_replicates"])
    boot_seed = int(contract["analysis_rules"]["bootstrap_seed"])
    summary_rows: list[dict[str, object]] = []
    groups = [("pooled", paired)] + [(str(k), g) for k, g in paired.groupby("scenario", sort=True)]
    for i, (label, g) in enumerate(groups):
        aq = g["attenuation_q_h360"].to_numpy(float)
        lo, hi = bootstrap_mean_ci(aq, boot_seed + i, reps)
        normal_mean = float(g["delta_q_h360_normal"].mean())
        summary_rows.append(
            {
                "group": label,
                "n": len(g),
                "mean_delta_q_h360_normal": normal_mean,
                "mean_delta_q_h360_clamp": float(g["delta_q_h360_clamp"].mean()),
                "mean_attenuation_q_h360": float(aq.mean()),
                "median_attenuation_q_h360": float(np.median(aq)),
                "attenuation_boot95_lo": lo,
                "attenuation_boot95_hi": hi,
                "attenuation_fraction_of_abs_normal_mean": (
                    float(aq.mean() / abs(normal_mean)) if abs(normal_mean) > EPS else float("nan")
                ),
                "negative_normal_reversed_fraction": float(
                    (
                        (g["delta_q_h360_normal"] < -EPS)
                        & (g["delta_q_h360_clamp"] >= -EPS)
                    ).mean()
                ),
                "mean_change_capability_effect_h30": float(
                    g["change_capability_effect_h30"].mean()
                ),
                "mean_change_capability_effect_h90": float(
                    g["change_capability_effect_h90"].mean()
                ),
                "mean_change_capability_effect_h180": float(
                    g["change_capability_effect_h180"].mean()
                ),
                "mean_change_capability_effect_h360": float(
                    g["change_capability_effect_h360"].mean()
                ),
            }
        )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(ns.output_dir / "mechanism_ablation_summary_v1.csv", index=False)

    errors = intervals["relative_error"].to_numpy(float)
    median_err = float(np.median(errors))
    mean_err = float(np.mean(errors))
    p95_err = float(np.quantile(errors, 0.95))
    max_err = float(np.max(errors))
    within5 = float(np.mean(errors <= 0.05))
    manipulation_pass = (
        median_err <= float(contract["analysis_rules"]["manipulation_median_relative_error_max"])
        and within5 >= float(contract["analysis_rules"]["manipulation_fraction_within_5pct_min"])
    )
    pooled = summary[summary["group"] == "pooled"].iloc[0]
    result = {
        "schema_version": "pineland.partner_force_mechanism_ablation_result.v1",
        "status": "ANALYSIS_COMPLETE",
        "worlds": len(worlds),
        "paired_worlds": len(paired),
        "production_git_commit": next(iter(commits)),
        "contract_sha256": next(iter(contract_hashes)),
        "freeze_sha256": next(iter(freeze_hashes)),
        "clamp_interval_count": len(intervals),
        "clamp_error_mean": mean_err,
        "clamp_error_median": median_err,
        "clamp_error_p95": p95_err,
        "clamp_error_max": max_err,
        "clamp_fraction_within_5pct": within5,
        "manipulation_check_pass": bool(manipulation_pass),
        "pooled_mean_delta_q_h360_normal": float(pooled["mean_delta_q_h360_normal"]),
        "pooled_mean_delta_q_h360_clamp": float(pooled["mean_delta_q_h360_clamp"]),
        "pooled_mean_attenuation_q_h360": float(pooled["mean_attenuation_q_h360"]),
        "pooled_attenuation_fraction_of_abs_normal_mean": float(
            pooled["attenuation_fraction_of_abs_normal_mean"]
        ),
        "interpretation_rule": (
            "Positive paired attenuation after a passing manipulation check supports endogenous "
            "logistics requirement expansion as one causal component of the terminal coverage gap."
        ),
    }
    (ns.output_dir / "mechanism_ablation_result_v1.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

