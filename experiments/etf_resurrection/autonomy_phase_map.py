"""Autonomy-trap phase map: sign and size of the continued-support effect on force
capability at day +360, over support dose x institutional learning rate, per cell.

Learning rate 0 reuses the dose-response runs (results/local_v6/prod2); positive
rates come from results/local_v6/learn.  Cells show the mean paired effect
(continued minus withdrawn) and the share of seeds where it is positive.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).parent / "results/local_v6"
CELLS = {"forcegen": "Force-generation-constrained", "command": "Command-constrained",
         "logistics": "Logistics-constrained"}
METRIC = "composite_capability"
H = 360.0


def source(dose, lr):
    if lr == 0:
        return HERE / "prod2" / ("val" if dose == 1 else f"dose_{dose:g}")
    if dose == 1:
        return HERE / "learn" / f"lr_{lr:g}" if (HERE / "learn" / f"lr_{lr:g}").exists() else HERE / "learn" / f"lr_{lr}"
    return HERE / "learn" / f"g_d{dose:g}_lr{lr}"


rows = []
for dose in (1, 4, 16):
    for lr in (0, 0.25, 1.0):
        root = source(dose, lr)
        if not root.exists():
            continue
        for f in root.glob("*_*/w.csv"):
            cell, seed = f.parent.name.split("_")
            if int(seed) >= 16:
                continue
            try:
                w = pd.read_csv(f)
            except pd.errors.EmptyDataError:
                continue  # run still in progress
            on = w[(w.branch == "SUPPORT_ON") & (w.horizon_days == H)]
            off = w[(w.branch == "SUPPORT_OFF") & (w.horizon_days == H)]
            if on.empty:
                continue
            rows.append(dict(cell=cell, dose=dose, lr=lr, seed=int(seed),
                             d=float(on[METRIC].iloc[0]) - float(off[METRIC].iloc[0])))
df = pd.DataFrame(rows)
summary = (df.groupby(["cell", "lr", "dose"])["d"]
           .agg(mean="mean", n="size", pos=lambda x: (x > 0).mean(),
                p=lambda x: stats.wilcoxon(x).pvalue if np.any(x != 0) else 1.0)
           .reset_index())
summary.to_csv(HERE / "autonomy_phase_map.csv", index=False)
print(summary.round(4).to_string(index=False))

lim = max(0.05, float(summary["mean"].abs().max()))
cmap = LinearSegmentedColormap.from_list("pm", ["#c4574a", "#e2a79b", "#f4f2ec", "#a9c4e0", "#2b5d9b"])
norm = TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)
doses, lrs = [1, 4, 16], [0, 0.25, 1.0]
fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), facecolor="#fcfcfb")
for ax, (cell, name) in zip(axes, CELLS.items()):
    grid = np.full((len(lrs), len(doses)), np.nan)
    for i, lr in enumerate(lrs):
        for j, dose in enumerate(doses):
            s = summary[(summary.cell == cell) & (summary.lr == lr) & (summary.dose == dose)]
            if s.empty:
                continue
            grid[i, j] = s["mean"].iloc[0]
            star = "*" if s["p"].iloc[0] < 0.05 else ""
            ax.text(j, i, f"{s['mean'].iloc[0]:+.3f}{star}\n{s['pos'].iloc[0]:.0%} seeds +", ha="center",
                    va="center", fontsize=8.5, color="#1f2328")
    ax.imshow(grid, cmap=cmap, norm=norm, origin="lower", aspect="auto")
    ax.set_xticks(range(len(doses)), [f"{d}x" for d in doses])
    ax.set_yticks(range(len(lrs)), [f"{lr:g}" for lr in lrs])
    ax.set_xlabel("support dose (x design intensity)", fontsize=9, color="#5b6168")
    ax.set_title(name, fontsize=11, fontweight="bold", loc="left", color="#1f2328")
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0, colors="#5b6168")
axes[0].set_ylabel("institutional learning rate (per 30 days)", fontsize=9, color="#5b6168")
cax = fig.add_axes([0.35, 0.07, 0.3, 0.025])
cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal")
cb.set_ticks([-lim, 0, lim])
cb.set_ticklabels(["support erodes capability", "no effect", "support builds capability"])
cb.ax.tick_params(labelsize=8, length=0)
cb.outline.set_visible(False)
fig.suptitle("Autonomy-trap phase map: effect of continued support on force capability at day +360 "
             "(* p<0.05, 16 seeds)", x=0.01, ha="left", fontsize=12, fontweight="bold", color="#1f2328")
fig.subplots_adjust(left=0.07, right=0.99, top=0.84, bottom=0.25, wspace=0.18)
fig.savefig(HERE / "autonomy_phase_map.png", dpi=170, facecolor="#fcfcfb")
print("wrote", HERE / "autonomy_phase_map.png")
