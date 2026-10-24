"""Collect an autonomy-trap campaign: paired effects, summaries and phase maps.

  python collect.py --campaign DIR --scratch DIR [--out DIR] [--allow-incomplete]

Writes to --out (default <campaign>/results):
  effects.csv        one row per (task, horizon): continued minus withdrawn, per metric
  summary.csv        per (variant, cell, horizon): mean, se, share positive, Wilcoxon p
  structure.csv      per (variant, structure, support, horizon), pooled over capacity levels
  phase_A_<metric>.png  phase maps (capacity x support) per learning rate, day +360
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

METRICS = ["composite_capability", "c_government_control", "c_military_personnel_retention",
           "c_operational_formation_survival", "c_geographic_coverage_retention",
           "c_operational_readiness_retention", "post_military_losses", "post_indigenous_graduates",
           "post_indigenous_logistics_produced", "post_donor_cost"]


def wilcoxon_p(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(stats.wilcoxon(x).pvalue) if len(x) > 5 and np.any(x != 0) else 1.0


def summarize(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for k, g in df.groupby(keys):
        r = dict(zip(keys, k if isinstance(k, tuple) else (k,)))
        r["n"] = len(g)
        for m in METRICS:
            x = g[m].to_numpy(dtype=float)
            r[m] = x.mean()
            r[m + "_se"] = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
            r[m + "_pos"] = (x > 0).mean()
            r[m + "_p"] = wilcoxon_p(x)
        rows.append(r)
    return pd.DataFrame(rows)


def phase_maps(summary: pd.DataFrame, out: Path, metric: str, horizon: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

    s = summary[(summary.variant.str.startswith("A_")) & (summary.h == horizon)]
    if s.empty:
        return
    lrs = sorted(s.variant.unique(), key=lambda v: float(v.split("lr")[1]))
    structures = sorted(s.factor_structure.unique())
    lim = max(0.02, float(s[metric].abs().quantile(0.98)))
    cmap = LinearSegmentedColormap.from_list("pm", ["#c4574a", "#e2a79b", "#f4f2ec", "#a9c4e0", "#2b5d9b"])
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)
    fig, axes = plt.subplots(len(lrs), len(structures), figsize=(3.6 * len(structures), 2.9 * len(lrs)),
                             squeeze=False, facecolor="#fcfcfb")
    for i, v in enumerate(lrs):
        for j, st in enumerate(structures):
            ax = axes[i, j]
            g = s[(s.variant == v) & (s.factor_structure == st)]
            caps = sorted(g.factor_capacity_level.unique())
            sups = sorted(g.factor_support_intensity.unique())
            grid = np.full((len(caps), len(sups)), np.nan)
            sig = np.zeros_like(grid, dtype=bool)
            for _, r in g.iterrows():
                a, b = caps.index(r.factor_capacity_level), sups.index(r.factor_support_intensity)
                grid[a, b] = r[metric]
                sig[a, b] = r[metric + "_p"] < 0.05
            ax.imshow(grid, cmap=cmap, norm=norm, origin="lower", aspect="auto")
            for (a, b), flag in np.ndenumerate(sig):
                if flag:
                    ax.text(b, a, "*", ha="center", va="center", fontsize=9, color="#1f2328")
            ax.set_xticks(range(len(sups)), [f"{x:g}" for x in sups], fontsize=7)
            ax.set_yticks(range(len(caps)), [f"{x:g}" for x in caps], fontsize=7)
            if i == 0:
                ax.set_title(st.replace("_", " "), fontsize=10, fontweight="bold")
            if j == 0:
                ax.set_ylabel(f"learning {v.split('lr')[1]}\ncapacity level", fontsize=8)
            if i == len(lrs) - 1:
                ax.set_xlabel("support intensity", fontsize=8)
    fig.suptitle(f"Continued minus withdrawn: {metric}, day +{horizon:g} (* p<0.05)", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")
    cax = fig.add_axes([0.3, 0.005, 0.4, 0.012])
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(out / f"phase_A_{metric}_{horizon:g}.png", dpi=150, facecolor="#fcfcfb")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--scratch", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--allow-incomplete", action="store_true")
    a = ap.parse_args()
    out = a.out or a.campaign / "results"
    out.mkdir(parents=True, exist_ok=True)
    tasks = [json.loads(x) for x in (a.campaign / "tasks.jsonl").read_text().splitlines()]
    meta = {}
    for c in (a.campaign / "contracts").glob("*.json"):
        d = json.loads(c.read_text())
        for i, cell in enumerate(d["cells"]):
            meta[(c.stem, i)] = {k: cell.get(k) for k in ("factor_structure", "factor_capacity_level",
                                                         "factor_support_intensity")}
    rows, missing = [], []
    for t in tasks:
        task_dir = a.scratch / "tasks" / f"{t['id']:06d}"
        if not (task_dir / "_SUCCESS.json").exists():
            missing.append(t["id"])
            continue
        w = pd.read_csv(task_dir / "w.csv")
        for h, g in w.groupby("horizon_days"):
            on, off = g[g.branch == "SUPPORT_ON"], g[g.branch == "SUPPORT_OFF"]
            if on.empty or off.empty:
                continue
            r = dict(id=t["id"], variant=t["variant"], cell_id=t["cell_id"], seed=t["seed"], h=float(h),
                     **meta[(t["variant"], t["cell_index"])])
            for m in METRICS:
                r[m] = float(on[m].iloc[0]) - float(off[m].iloc[0]) if m in g else np.nan
            rows.append(r)
    print(f"collected {len(tasks) - len(missing)}/{len(tasks)} tasks")
    if missing and not a.allow_incomplete:
        raise SystemExit(f"{len(missing)} tasks incomplete (first: {missing[:10]}); use --allow-incomplete")
    df = pd.DataFrame(rows)
    df.to_csv(out / "effects.csv", index=False)
    cell_keys = ["variant", "cell_id", "factor_structure", "factor_capacity_level", "factor_support_intensity", "h"]
    summary = summarize(df, cell_keys)
    summary.to_csv(out / "summary.csv", index=False)
    structure = summarize(df, ["variant", "factor_structure", "factor_support_intensity", "h"])
    structure.to_csv(out / "structure.csv", index=False)
    for metric in ("composite_capability", "c_military_personnel_retention", "c_government_control"):
        phase_maps(summary, out, metric, 360.0)
    print("wrote", out)


if __name__ == "__main__":
    main()
