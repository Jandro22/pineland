#!/usr/bin/env python3
"""Precommitted paper-level secondary analysis for Stage 4.

Consumes only complete outputs produced by the frozen/repaired module analysis.
No production simulator state is modified by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1.0e-6
DEFAULT_BOOTSTRAP_SEED = 20260920
DEFAULT_BOOTSTRAP_RESAMPLES = 10_000
Z95 = 1.959963984540054


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--phase-world", required=True)
    p.add_argument("--phase-paired", required=True)
    p.add_argument("--migration-world", required=True)
    p.add_argument("--migration-paired", required=True)
    p.add_argument("--mechanism-world", required=True)
    p.add_argument("--mechanism-paired", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES)
    p.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    return p.parse_args()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stable_rng(base_seed: int, key: object) -> np.random.Generator:
    digest = hashlib.sha256(f"{base_seed}|{key!r}".encode()).digest()
    seed = int.from_bytes(digest[:8], "little", signed=False)
    return np.random.default_rng(seed)


def finite(values: Iterable[float]) -> np.ndarray:
    x = np.asarray(list(values), dtype=float)
    return x[np.isfinite(x)]


def bootstrap_mean_ci(
    values: Iterable[float], *, base_seed: int, key: object, resamples: int
) -> tuple[float, float]:
    x = finite(values)
    if len(x) == 0:
        return math.nan, math.nan
    if len(x) == 1:
        return float(x[0]), float(x[0])
    rng = stable_rng(base_seed, key)
    idx = rng.integers(0, len(x), size=(resamples, len(x)))
    means = x[idx].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def wilson_interval(successes: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return math.nan, math.nan
    p = successes / n
    z2 = Z95 * Z95
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = Z95 * math.sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n)) / denom
    return center - half, center + half


def q10_q90(values: Iterable[float]) -> tuple[float, float]:
    x = finite(values)
    if len(x) == 0:
        return math.nan, math.nan
    q = np.quantile(x, [0.1, 0.9])
    return float(q[0]), float(q[1])


def sign_eps(value: float) -> int:
    if not math.isfinite(value) or abs(value) <= EPS:
        return 0
    return 1 if value > 0.0 else -1


def phase_cell_summary(
    worlds: pd.DataFrame, *, base_seed: int, resamples: int
) -> pd.DataFrame:
    keys = [
        "factor_structure",
        "factor_capacity_level",
        "factor_capacity_level_index",
        "factor_support_intensity",
    ]
    rows: list[dict] = []
    for group_key, g in worlds.groupby(keys, dropna=False, sort=True):
        dc = g["delta_composite_capability_h30"].to_numpy(float)
        dq = g["delta_q_feasible_h360"].to_numpy(float)
        mean_dc = float(np.mean(dc))
        mean_dq = float(np.mean(dq))
        med_dc = float(np.median(dc))
        med_dq = float(np.median(dq))
        dc_lo, dc_hi = bootstrap_mean_ci(
            dc, base_seed=base_seed, key=("phase", group_key, "dc30"), resamples=resamples
        )
        dq_lo, dq_hi = bootstrap_mean_ci(
            dq, base_seed=base_seed, key=("phase", group_key, "dq360"), resamples=resamples
        )
        dc_q10, dc_q90 = q10_q90(dc)
        dq_q10, dq_q90 = q10_q90(dq)
        effective = dc > EPS
        traps = effective & (dq < -EPS)
        builds = effective & (dq > EPS)
        n = len(g)
        neff = int(effective.sum())
        trap_n = int(traps.sum())
        build_n = int(builds.sum())
        eff_ci = wilson_interval(neff, n)
        trap_ci = wilson_interval(trap_n, n)
        build_ci = wilson_interval(build_n, n)
        trap_eff_ci = wilson_interval(trap_n, neff)
        build_eff_ci = wilson_interval(build_n, neff)

        if mean_dc <= EPS:
            regime = "not_initially_effective"
        elif mean_dq > EPS:
            regime = "effective_autonomy_building"
        elif mean_dq < -EPS:
            regime = "effective_autonomy_trap"
        else:
            regime = "effective_autonomy_neutral"

        robust = "uncertain_or_mixed"
        if dc_lo > EPS and med_dc > EPS:
            if dq_lo > EPS and med_dq > EPS:
                robust = "robust_effective_autonomy_building"
            elif dq_hi < -EPS and med_dq < -EPS:
                robust = "robust_effective_autonomy_trap"
            elif dq_lo >= -EPS and dq_hi <= EPS:
                robust = "robust_effective_autonomy_neutral"
            else:
                robust = "effective_autonomy_direction_uncertain"
        elif dc_hi <= EPS:
            robust = "robust_not_initially_effective"

        row = dict(zip(keys, group_key))
        row.update(
            {
                "n": n,
                "mean_delta_capability_h30": mean_dc,
                "median_delta_capability_h30": med_dc,
                "delta_capability_h30_boot95_lo": dc_lo,
                "delta_capability_h30_boot95_hi": dc_hi,
                "delta_capability_h30_q10": dc_q10,
                "delta_capability_h30_q90": dc_q90,
                "mean_delta_q_feasible_h360": mean_dq,
                "median_delta_q_feasible_h360": med_dq,
                "delta_q_feasible_h360_boot95_lo": dq_lo,
                "delta_q_feasible_h360_boot95_hi": dq_hi,
                "delta_q_feasible_h360_q10": dq_q10,
                "delta_q_feasible_h360_q90": dq_q90,
                "effective_seed_count": neff,
                "effective_seed_fraction": neff / n,
                "effective_seed_fraction_wilson95_lo": eff_ci[0],
                "effective_seed_fraction_wilson95_hi": eff_ci[1],
                "trap_seed_count": trap_n,
                "trap_seed_fraction": trap_n / n,
                "trap_seed_fraction_wilson95_lo": trap_ci[0],
                "trap_seed_fraction_wilson95_hi": trap_ci[1],
                "build_seed_count": build_n,
                "build_seed_fraction": build_n / n,
                "build_seed_fraction_wilson95_lo": build_ci[0],
                "build_seed_fraction_wilson95_hi": build_ci[1],
                "trap_fraction_among_effective": trap_n / neff if neff else math.nan,
                "trap_among_effective_wilson95_lo": trap_eff_ci[0],
                "trap_among_effective_wilson95_hi": trap_eff_ci[1],
                "build_fraction_among_effective": build_n / neff if neff else math.nan,
                "build_among_effective_wilson95_lo": build_eff_ci[0],
                "build_among_effective_wilson95_hi": build_eff_ci[1],
                "phase_regime": regime,
                "robust_phase_regime": robust,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def transition_rows(
    cells: pd.DataFrame,
    *, group_cols: list[str],
    x_col: str,
    x_index_col: str | None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for group_key, g in cells.groupby(group_cols, dropna=False, sort=True):
        order = x_index_col or x_col
        g = g.sort_values(order, kind="mergesort")
        records = list(g.to_dict("records"))
        for left, right in pairwise(records):
            q0 = float(left["mean_delta_q_feasible_h360"])
            q1 = float(right["mean_delta_q_feasible_h360"])
            s0, s1 = sign_eps(q0), sign_eps(q1)
            if s0 == 0 or s1 == 0 or s0 == s1:
                continue
            x0, x1 = float(left[x_col]), float(right[x_col])
            interp = x0 + (0.0 - q0) * (x1 - x0) / (q1 - q0)
            row = dict(zip(group_cols, group_key if isinstance(group_key, tuple) else (group_key,)))
            row.update(
                {
                    "lower_grid_value": x0,
                    "upper_grid_value": x1,
                    "left_mean_delta_q_h360": q0,
                    "right_mean_delta_q_h360": q1,
                    "direction": "building_to_eroding" if s0 > 0 else "eroding_to_building",
                    "descriptive_linear_zero_interpolation": interp,
                    "both_cells_initially_effective": bool(
                        left["mean_delta_capability_h30"] > EPS
                        and right["mean_delta_capability_h30"] > EPS
                    ),
                    "both_cells_robustly_effective": bool(
                        left["delta_capability_h30_boot95_lo"] > EPS
                        and right["delta_capability_h30_boot95_lo"] > EPS
                    ),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def add_cumulative_coverage(paired: pd.DataFrame) -> pd.DataFrame:
    x = paired.copy()
    for ch in ("fg", "log", "cmd"):
        for branch in ("on", "off"):
            indigenous = x[f"cum_{ch}_indigenous_{branch}"].to_numpy(float)
            demand = x[f"cum_{ch}_demand_{branch}"].to_numpy(float)
            raw = np.divide(
                indigenous,
                demand,
                out=np.full(len(x), np.nan),
                where=demand > 0.0,
            )
            x[f"cum_{ch}_coverage_{branch}"] = raw
            x[f"cum_{ch}_coverage_capped_{branch}"] = np.minimum(raw, 1.0)
        x[f"delta_cum_{ch}_coverage"] = (
            x[f"cum_{ch}_coverage_on"] - x[f"cum_{ch}_coverage_off"]
        )
        x[f"delta_cum_{ch}_coverage_capped"] = (
            x[f"cum_{ch}_coverage_capped_on"] - x[f"cum_{ch}_coverage_capped_off"]
        )
    return x


def mechanism_cell_summary(
    worlds: pd.DataFrame, paired: pd.DataFrame, *, base_seed: int, resamples: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    h360 = add_cumulative_coverage(paired[paired["horizon_days"] == 360.0].copy())
    coverage_cols = [
        "cell_id",
        "seed",
        "delta_cum_fg_coverage_capped",
        "delta_cum_log_coverage_capped",
        "delta_cum_cmd_coverage_capped",
    ]
    w = worlds.merge(h360[coverage_cols], on=["cell_id", "seed"], validate="one_to_one")
    target_to_channel = {"forcegen": "fg", "logistics": "log", "command": "cmd"}
    w["relevant_delta_indigenous_h360"] = np.nan
    w["relevant_delta_demand_h360"] = np.nan
    w["relevant_delta_coverage_capped_h360"] = np.nan
    for target, ch in target_to_channel.items():
        mask = w["factor_target"] == target
        w.loc[mask, "relevant_delta_indigenous_h360"] = w.loc[
            mask, f"delta_cum_{ch}_indigenous_h360"
        ]
        w.loc[mask, "relevant_delta_demand_h360"] = w.loc[
            mask, f"delta_cum_{ch}_demand_h360"
        ]
        w.loc[mask, "relevant_delta_coverage_capped_h360"] = w.loc[
            mask, f"delta_cum_{ch}_coverage_capped"
        ]

    keys = ["factor_target", "factor_severity", "factor_assistance_mode", "factor_intensity"]
    metrics = [
        "delta_composite_capability_h30",
        "delta_q_feasible_h360",
        "relevant_delta_indigenous_h360",
        "relevant_delta_demand_h360",
        "relevant_delta_coverage_capped_h360",
        "delta_cum_interval_donor_cost_h360",
    ]
    rows: list[dict] = []
    for group_key, g in w.groupby(keys, dropna=False, sort=True):
        row = dict(zip(keys, group_key))
        row["n"] = len(g)
        for metric in metrics:
            vals = g[metric].to_numpy(float)
            lo, hi = bootstrap_mean_ci(
                vals,
                base_seed=base_seed,
                key=("mechanism-cell", group_key, metric),
                resamples=resamples,
            )
            row[f"mean_{metric}"] = float(np.nanmean(vals))
            row[f"median_{metric}"] = float(np.nanmedian(vals))
            row[f"{metric}_boot95_lo"] = lo
            row[f"{metric}_boot95_hi"] = hi
        rows.append(row)
    cells = pd.DataFrame(rows)

    treated = w[w["factor_assistance_mode"].isin(["substitution", "development", "hybrid"])].copy()
    index = ["factor_target", "factor_severity", "factor_intensity", "seed"]
    contrast_metrics = metrics
    wide = treated.pivot(index=index, columns="factor_assistance_mode", values=contrast_metrics)
    contrasts: list[dict] = []
    for group_key, gidx in treated[index[:-1]].drop_duplicates().groupby(index[:-1], sort=True):
        target, severity, intensity = group_key
        try:
            block = wide.loc[(target, severity, intensity)]
        except KeyError:
            continue
        for lhs, rhs, label in (
            ("development", "substitution", "development_minus_substitution"),
            ("hybrid", "substitution", "hybrid_minus_substitution"),
        ):
            row = {
                "factor_target": target,
                "factor_severity": severity,
                "factor_intensity": intensity,
                "contrast": label,
                "n_matched_seeds": len(block),
            }
            for metric in contrast_metrics:
                if lhs not in block[metric].columns or rhs not in block[metric].columns:
                    diff = np.array([], dtype=float)
                else:
                    diff = (block[metric][lhs] - block[metric][rhs]).to_numpy(float)
                diff = finite(diff)
                lo, hi = bootstrap_mean_ci(
                    diff,
                    base_seed=base_seed,
                    key=("mechanism-contrast", group_key, label, metric),
                    resamples=resamples,
                )
                row[f"mean_{metric}"] = float(np.mean(diff)) if len(diff) else math.nan
                row[f"median_{metric}"] = float(np.median(diff)) if len(diff) else math.nan
                row[f"{metric}_boot95_lo"] = lo
                row[f"{metric}_boot95_hi"] = hi
            contrasts.append(row)
    return cells, pd.DataFrame(contrasts)


def migration_summary(worlds: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    h360 = paired[paired["horizon_days"] == 360.0][
        [
            "cell_id",
            "seed",
            "delta_smooth_q_arithmetic",
            "delta_smooth_q_geometric",
            "delta_smooth_q_harmonic",
        ]
    ].copy()
    w = worlds.merge(h360, on=["cell_id", "seed"], validate="one_to_one")
    w["observed_target_match"] = (
        (w["factor_support_target"] != "none")
        & (w["factor_support_target"].astype(str) == w["pre_bottleneck"].astype(str))
    )
    for name in (
        "delta_q_feasible_h360",
        "delta_smooth_q_arithmetic",
        "delta_smooth_q_geometric",
        "delta_smooth_q_harmonic",
    ):
        w[f"sign_{name}"] = w[name].map(sign_eps)
    for smooth in ("arithmetic", "geometric", "harmonic"):
        w[f"sign_concordance_{smooth}"] = (
            w["sign_delta_q_feasible_h360"] == w[f"sign_delta_smooth_q_{smooth}"]
        )

    keys = [
        "factor_starting_structure",
        "factor_support_target",
        "factor_support_intensity",
        "observed_target_match",
    ]
    rows: list[dict] = []
    for group_key, g in w.groupby(keys, dropna=False, sort=True):
        migrated = g["ever_persistently_migrated"].fillna(False).astype(bool)
        nmig = int(migrated.sum())
        n = len(g)
        ci = wilson_interval(nmig, n)
        times = g.loc[migrated, "first_persistent_migration_days"].to_numpy(float)
        row = dict(zip(keys, group_key))
        row.update(
            {
                "n": n,
                "persistent_migration_count": nmig,
                "persistent_migration_fraction": nmig / n,
                "persistent_migration_wilson95_lo": ci[0],
                "persistent_migration_wilson95_hi": ci[1],
                "median_migration_time_days_among_migrated": (
                    float(np.nanmedian(times)) if len(times) else math.nan
                ),
                "mean_bottleneck_path_entropy": float(g["bottleneck_path_entropy"].mean()),
                "mean_delta_capability_h30": float(g["delta_composite_capability_h30"].mean()),
                "mean_delta_q_feasible_h360": float(g["delta_q_feasible_h360"].mean()),
                "mean_delta_smooth_q_arithmetic_h360": float(
                    g["delta_smooth_q_arithmetic"].mean()
                ),
                "mean_delta_smooth_q_geometric_h360": float(
                    g["delta_smooth_q_geometric"].mean()
                ),
                "mean_delta_smooth_q_harmonic_h360": float(
                    g["delta_smooth_q_harmonic"].mean()
                ),
                "sign_concordance_arithmetic": float(g["sign_concordance_arithmetic"].mean()),
                "sign_concordance_geometric": float(g["sign_concordance_geometric"].mean()),
                "sign_concordance_harmonic": float(g["sign_concordance_harmonic"].mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ns = parse_args()
    if ns.bootstrap_resamples <= 0:
        raise SystemExit("--bootstrap-resamples must be positive")
    paths = {
        "phase_world": Path(ns.phase_world),
        "phase_paired": Path(ns.phase_paired),
        "migration_world": Path(ns.migration_world),
        "migration_paired": Path(ns.migration_paired),
        "mechanism_world": Path(ns.mechanism_world),
        "mechanism_paired": Path(ns.mechanism_paired),
    }
    outdir = Path(ns.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    data = {name: pd.read_csv(path) for name, path in paths.items()}
    phase_cells = phase_cell_summary(
        data["phase_world"], base_seed=ns.bootstrap_seed, resamples=ns.bootstrap_resamples
    )
    phase_cells.to_csv(outdir / "phase_cell_summary_v1.csv", index=False)

    support_transitions = transition_rows(
        phase_cells,
        group_cols=["factor_structure", "factor_capacity_level", "factor_capacity_level_index"],
        x_col="factor_support_intensity",
        x_index_col=None,
    )
    support_transitions.to_csv(outdir / "phase_support_transition_intervals_v1.csv", index=False)

    capacity_transitions = transition_rows(
        phase_cells,
        group_cols=["factor_structure", "factor_support_intensity"],
        x_col="factor_capacity_level",
        x_index_col="factor_capacity_level_index",
    )
    capacity_transitions.to_csv(outdir / "phase_capacity_transition_intervals_v1.csv", index=False)

    mechanism_cells, mechanism_contrasts = mechanism_cell_summary(
        data["mechanism_world"],
        data["mechanism_paired"],
        base_seed=ns.bootstrap_seed,
        resamples=ns.bootstrap_resamples,
    )
    mechanism_cells.to_csv(outdir / "mechanism_cell_summary_v1.csv", index=False)
    mechanism_contrasts.to_csv(outdir / "mechanism_mode_contrasts_v1.csv", index=False)

    migration = migration_summary(data["migration_world"], data["migration_paired"])
    migration.to_csv(outdir / "migration_target_match_summary_v1.csv", index=False)

    summary = {
        "schema_version": "pineland.partner_force_stage4_paper_secondary.v1",
        "status": "PRECOMMITTED_PAPER_SECONDARY_ANALYSIS",
        "bootstrap_seed": ns.bootstrap_seed,
        "bootstrap_resamples": ns.bootstrap_resamples,
        "epsilon": EPS,
        "primary_estimands": {
            "early_operational_effect": "delta composite_capability at +30d",
            "terminal_autonomy_effect": "delta min(q_indigenous, 1.0) at +360d",
            "effective_autonomy_trap": "early effect > epsilon and terminal autonomy < -epsilon",
            "effective_autonomy_building": "early effect > epsilon and terminal autonomy > epsilon",
        },
        "input_sha256": {name: file_sha256(path) for name, path in paths.items()},
        "outputs": {},
    }
    for path in sorted(outdir.glob("*.csv")):
        summary["outputs"][path.name] = file_sha256(path)
    (outdir / "stage4_paper_secondary_summary_v1.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
