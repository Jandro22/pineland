"""Exploratory full Phase-Map measurement audit, with matched contemporaneous controls.

Reproduce the October 26/30/51 table exactly before constructing alternative
scores. Never equate raw readiness with the original deployable-readiness assay.
All cell/seed/time/branch joins are validated and missing controls are fatal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from inventory import BASE, sha256, write_json

FACTORS = ["factor_structure", "factor_capacity_level", "factor_support_intensity"]
MATCH = [*FACTORS[:2], "seed"]
STATE = ["government_control", "military_personnel", "operational_formations", "covered_localities", "readiness"]
FLOWS = ["interval_indigenous_graduates", "interval_indigenous_logistics_delivered", "command_latency_hours"]
METRICS = STATE + FLOWS
EPS = 1e-6


def signs(values: np.ndarray, eps: float = EPS) -> np.ndarray:
    return np.where(np.isfinite(values), np.where(values > eps, "+", np.where(values < -eps, "-", "0")), "?")


def quadrant(s, r):
    s, r = np.asarray(s), np.asarray(r)
    return np.where(np.isfinite(s) & np.isfinite(r), np.char.add(np.char.add(np.char.add("S", signs(s)), "R"), signs(r)), "UNDEFINED")


def bootstrap(values: np.ndarray, key: str, draws: int = 5000) -> tuple[float, float]:
    # Keyed streams make CIs independent of loop order and added metrics.
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "little"))
    boot = values[rng.integers(0, len(values), (draws, len(values)))].mean(axis=1)
    return tuple(float(x) for x in np.percentile(boot, [2.5, 97.5]))


def score(ratios: np.ndarray, cap: bool, aggregation: str) -> np.ndarray:
    values = np.minimum(1.0, ratios) if cap else ratios
    if np.any(values < 0) or np.any(np.isinf(values)):
        raise ValueError("infinite/negative score components")
    return values.mean(axis=1) if aggregation == "arithmetic" else np.prod(values, axis=1) ** (1 / values.shape[1])


def run(raw: Path, contract_path: Path, outdir: Path) -> dict:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    factors = pd.DataFrame(contract["cells"])[["cell_id", *FACTORS]]
    usecols = ["cell_id", "seed", "phase", "days_from_withdrawal", "composite_capability",
               "operational_readiness_retention", *METRICS]
    paths = sorted(raw.glob("*.trajectory.csv"))
    expected = contract["cells_count"] * contract["default_seed_count"]
    if len(paths) != expected:
        raise ValueError(f"expected {expected} worlds, found {len(paths)}")
    frames = []
    for path in paths:
        frame = pd.read_csv(path, usecols=usecols)
        # Keep the entire supported preperiod to distinguish peak from split.
        frame = frame[(frame.phase == "PRE_SUPPORTED") | frame.days_from_withdrawal.isin([30, 360])]
        frames.append(frame)
    t = pd.concat(frames, ignore_index=True).merge(factors, on="cell_id", validate="many_to_one")
    pre = t[t.phase == "PRE_SUPPORTED"]
    split = pre[pre.days_from_withdrawal == 0].set_index(["cell_id", "seed"])
    if len(split) != expected or split.index.has_duplicates:
        raise ValueError("missing/duplicate split states")
    peaks = pre.groupby(["cell_id", "seed"])[STATE].max()
    post = t[t.phase.isin(["SUPPORT_ON", "SUPPORT_OFF"])].copy()
    fullkey = ["cell_id", "seed", "phase", "days_from_withdrawal"]
    if post.duplicated(fullkey).any():
        raise ValueError("duplicate postperiod rows")
    post = post.merge(split[STATE].add_prefix("split_"), on=["cell_id", "seed"], validate="many_to_one")
    post = post.merge(peaks.add_prefix("peak_"), on=["cell_id", "seed"], validate="many_to_one")
    controls = post[post.factor_support_intensity == 0]
    control_key = [*MATCH, "phase", "days_from_withdrawal"]
    ctl = controls[control_key + STATE + ["composite_capability", "operational_readiness_retention"]]
    post = post.merge(ctl.rename(columns={c: "control_" + c for c in ctl if c not in control_key}),
                      on=control_key, how="left", validate="many_to_one", indicator=True)
    if not (post._merge == "both").all():
        raise ValueError("missing matched contemporaneous control")
    post = post.drop(columns="_merge")
    post["original_composite"] = post.composite_capability
    post["original_readiness_component"] = post.operational_readiness_retention
    for metric in METRICS:
        post["absolute_" + metric] = post[metric]
    # A same-time ratio uses a common denominator for treated and control.
    # Zero controls remain undefined, not silently replaced by epsilon.
    denominators = post[["control_" + c for c in STATE]].to_numpy()
    undefined = (denominators <= 0).any(axis=1)
    contemporaneous = np.divide(post[STATE].to_numpy(), denominators,
                                out=np.full_like(denominators, np.nan), where=denominators > 0)
    post["common_time_geometric_uncapped"] = score(contemporaneous, False, "geometric")
    post["common_time_arithmetic_uncapped"] = score(contemporaneous, False, "arithmetic")
    post["common_time_geometric_capped"] = score(contemporaneous, True, "geometric")
    # Controlled 2x2x2 decomposition on one identically defined raw-state vector.
    # Government control is absolute in the original index, so retain it here.
    for baseline, cap, aggregation in product(["split", "control_time", "peak"], [False, True], ["geometric", "arithmetic"]):
        denom = post[[(("control_" + c) if baseline == "control_time" else (baseline + "_" + c)) for c in STATE[1:]]].to_numpy()
        normalized = np.divide(post[STATE[1:]].to_numpy(), denom, out=np.full_like(denom, np.nan), where=denom > 0)
        ratios = np.column_stack([post.government_control.to_numpy(), normalized])
        label = f"raw_{baseline}_{aggregation}_{'capped' if cap else 'uncapped'}"
        post[label] = score(ratios, cap, aggregation)
    scores = [c for c in post if c.startswith(("original_", "absolute_", "common_time_", "raw_"))]
    ctl_scores = post[post.factor_support_intensity == 0][control_key + scores]
    treated = post[post.factor_support_intensity > 0].merge(
        ctl_scores.rename(columns={c: "ctl_score_" + c for c in scores}), on=control_key, validate="many_to_one")
    for metric in scores:
        # Lower command latency is better. All other natural-unit changes keep their actual sign.
        orientation = -1 if metric == "absolute_command_latency_hours" else 1
        treated["delta_" + metric] = orientation * (treated[metric] - treated["ctl_score_" + metric])
    delta_cols = ["delta_" + x for x in scores]
    idcols = ["cell_id", "seed", "days_from_withdrawal", *FACTORS]
    on = treated[treated.phase == "SUPPORT_ON"][idcols + delta_cols].rename(columns={c: "S_" + c[6:] for c in delta_cols})
    off = treated[treated.phase == "SUPPORT_OFF"][idcols + delta_cols].rename(columns={c: "R_" + c[6:] for c in delta_cols})
    worlds = on.merge(off, on=idcols, validate="one_to_one")
    cellrows = []
    for (cell, horizon), group in worlds.groupby(["cell_id", "days_from_withdrawal"], sort=True):
        row = {"cell_id": cell, "horizon": int(horizon), "n": len(group), **group[FACTORS].iloc[0].to_dict()}
        for metric in scores:
            for arm in ["S", "R"]:
                values = group[f"{arm}_{metric}"].to_numpy()
                values = values[np.isfinite(values)]
                row[f"{arm}_{metric}_n_valid"] = len(values)
                lo, hi = bootstrap(values, f"etf-20261024:{cell}:{horizon}:{arm}:{metric}") if len(values) else (np.nan, np.nan)
                row[f"{arm}_{metric}"] = float(values.mean()) if len(values) else np.nan
                row[f"{arm}_{metric}_lo"], row[f"{arm}_{metric}_hi"] = lo, hi
            row["quadrant_" + metric] = str(quadrant([row["S_" + metric]], [row["R_" + metric]])[0])
            if min(row[f"S_{metric}_n_valid"], row[f"R_{metric}_n_valid"]) < len(group):
                row["quadrant_" + metric] = "INCOMPLETE"
        cellrows.append(row)
    cells = pd.DataFrame(cellrows)
    for metric in scores:
        worlds["quadrant_" + metric] = quadrant(worlds["S_" + metric], worlds["R_" + metric])
    negative_cells = set(cells[(cells.horizon == 30) & (cells.quadrant_original_composite == "S-R-")].cell_id)
    worlds["in_original_51_cell_cohort"] = worlds.cell_id.isin(negative_cells)
    matrices, flips = [], []
    for horizon in [30, 360]:
        for unit, frame in [("cell", cells[cells.horizon == horizon]),
                            ("world", worlds[worlds.days_from_withdrawal == horizon])]:
            for metric in scores:
                original = frame["quadrant_original_composite"]
                updated = frame["quadrant_" + metric]
                for (a, b), count in pd.DataFrame({"original": original, "updated": updated}).value_counts().items():
                    matrices.append(dict(unit=unit, horizon=horizon, scale=metric, original=a, updated=b, count=int(count)))
                flips.append(dict(unit=unit, horizon=horizon, scale=metric, n=len(frame),
                                  flipped=int((original != updated).sum()), fraction=float((original != updated).mean()),
                                  original_negative_R_to_positive=int(((frame.R_original_composite < -EPS) & (frame["R_" + metric] > EPS)).sum())))
    # Scalar analytic boundary: matched post-readiness ratio A versus own split denominator ratio B.
    # This is an exact test on the raw readiness measure, not on the unlogged deployable assay.
    boundary = treated[treated.phase == "SUPPORT_OFF"][[*idcols, "readiness", "control_readiness", "split_readiness"]].copy()
    control_split = split.reset_index()
    control_split = control_split[control_split.factor_support_intensity == 0][MATCH + ["readiness"]].rename(columns={"readiness": "control_split_readiness"})
    boundary = boundary.merge(control_split, on=MATCH, validate="many_to_one")
    boundary["post_ratio_A"] = boundary.readiness / boundary.control_readiness
    boundary["denominator_ratio_B"] = boundary.split_readiness / boundary.control_split_readiness
    boundary["self_split_ratio_of_ratios"] = boundary.post_ratio_A / boundary.denominator_ratio_B
    boundary["false_dependency_region"] = (boundary.post_ratio_A > 1) & (boundary.post_ratio_A < boundary.denominator_ratio_B)
    boundary["opposite_region"] = (boundary.post_ratio_A < 1) & (boundary.post_ratio_A > boundary.denominator_ratio_B)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, frame in [("world_reclassification", worlds), ("cell_reclassification", cells),
                        ("reclassification_matrix", pd.DataFrame(matrices)), ("verdict_flips", pd.DataFrame(flips)),
                        ("analytic_boundary_worlds", boundary),
                        ("original_51_cell_cohort_worlds", worlds[(worlds.days_from_withdrawal == 30) & worlds.in_original_51_cell_cohort]),
                        ("original_both_negative_worlds", worlds[(worlds.days_from_withdrawal == 30) & (worlds.quadrant_original_composite == "S-R-")])]:
        frame.to_csv(outdir / (name + ".csv"), index=False, lineterminator="\n")
    point_counts = {str(h): {str(k): int(v) for k, v in cells[cells.horizon == h].quadrant_original_composite.value_counts().items()} for h in [30, 360]}
    result = {"status": "EXPLORATORY_COMPLETE", "contract_sha256": sha256(contract_path),
              "input_worlds": expected, "treated_cells": int((factors.factor_support_intensity > 0).sum()),
              "matched_zero_support_cells": int((factors.factor_support_intensity == 0).sum()),
              "treated_worlds_per_horizon": len(worlds) // 2, "original_cell_quadrants": point_counts,
              "both_negative_worlds_h30": int(((worlds.days_from_withdrawal == 30) & (worlds.quadrant_original_composite == "S-R-")).sum()),
              "worlds_in_original_51_cell_cohort_h30": int(((worlds.days_from_withdrawal == 30) & worlds.in_original_51_cell_cohort).sum()),
              "narrative_checks": {"original_26_30_51_reproduced": all(point_counts["30"].get(k) == v for k, v in {"S+R-": 26, "S+R+": 30, "S-R-": 51}.items()),
                                   "612_both_negative_reproduced": int(((worlds.days_from_withdrawal == 30) & (worlds.quadrant_original_composite == "S-R-")).sum()) == 612},
              "post_rows_with_zero_common_time_denominator": int(undefined.sum()),
              "limits": ["Exploratory; no confirmatory decisions are made by this script.",
                         "Zero control denominators produce UNDEFINED world ratios and INCOMPLETE cell ratios. Those worlds stay in the audit and original classifications. Valid-only means are descriptive and their sample sizes are explicit.",
                         "The exact original composite is observed, but its absolute deployable-readiness numerator and reference denominator were not saved.",
                         "Raw-state construction ablations use logged readiness consistently. Their difference from the exact original also changes the readiness definition and personnel population.",
                         "Absolute results remain a vector in natural units. The readiness quadrant is one component, not an absolute composite.",
                         "Common-time uncapped ratios use the zero-support control at the same simulated time, seed, structure, and capacity.",
                         "Point-sign reclassifications and bootstrap intervals are separate. A point-sign flip is not statistical evidence of a nonzero effect.",
                         "The original denominator is the own split state, not a temporal supported peak. Peak is an explicitly separate exploratory variant.",
                         "The 26/30/51 table is an October post hoc continued-support/withdrawal versus zero-support comparison at +30, not the original Stage-4 capability/autonomy classification."],
              "outputs": {p.name: sha256(p) for p in sorted(outdir.glob("*.csv")) if p.name != "inventory_worlds.csv"}}
    write_json(outdir / "measurement_summary.json", result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir", required=True, type=Path)
    p.add_argument("--contract", type=Path, default=BASE / "contracts/stage4_autonomy_phase_map_v1.json")
    p.add_argument("--output-dir", type=Path, default=Path("experiments/etf_resurrection/results"))
    ns = p.parse_args()
    print(json.dumps(run(ns.input_dir, ns.contract, ns.output_dir), indent=2))
