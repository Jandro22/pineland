"""Dose-response small multiples from dose_response.csv (coupled-twin paired effects, 360 days).

Each panel is one outcome on its own axis; x is the support dose (multiple of the
design intensity, log scale); one line per constraint cell, with +/-1 SE whiskers
and direct labels.  Effect = continued support minus withdrawn.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results/local_v6/prod2"
H = float(sys.argv[2]) if len(sys.argv) > 2 else 360
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#1f2328", "#5b6168", "#e6e5e1"
CELLS = {  # fixed categorical order (validated: blue, orange, aqua)
    "logistics": ("#2a78d6", "o", "Logistics-constrained"),
    "command": ("#eb6834", "s", "Command-constrained"),
    "forcegen": ("#1baf7a", "D", "Force-generation-constrained"),
}
SHORT = {"logistics": "Logistics", "command": "Command", "forcegen": "Force gen."}
PANELS = [
    ("composite", "Force capability (composite index)", 1.0),
    ("army losses", "Army casualties averted", -1.0),
    ("indigenous graduates", "Change in indigenous recruits trained", 1.0),
]

t = pd.read_csv(ROOT / "dose_response.csv")
t = t[t.h == H].sort_values("dose")
fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), facecolor=SURFACE)
for ax, (col, title, sign) in zip(axes, PANELS):
    ax.set_facecolor(SURFACE)
    ax.axhline(0, color=MUTED, lw=1)
    ends = []
    for cell, (color, marker, label) in CELLS.items():
        g = t[t.cell == cell]
        if g.empty:
            continue
        y, e = sign * g[col], g[col + " se"]
        ax.errorbar(g.dose, y, yerr=e, color=color, marker=marker, ms=7, lw=2, capsize=3, elinewidth=1,
                    markeredgecolor=SURFACE, markeredgewidth=1.5)
        ends.append([y.iloc[-1], g.dose.iloc[-1], SHORT[cell]])
    # direct labels, dodged vertically so they never collide
    lo, hi = ax.get_ylim()
    gap = 0.07 * (hi - lo)
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + gap)
    for yv, xv, name in ends:
        ax.annotate(name, (xv, yv), xytext=(8, 0), textcoords="offset points", va="center", fontsize=8.5,
                    color=INK)
    ax.set_xscale("log", base=2)
    ax.set_xticks(sorted(t.dose.unique()))
    ax.set_xticklabels([f"{d:g}x" for d in sorted(t.dose.unique())])
    ax.set_title(title, fontsize=11, color=INK, loc="left", fontweight="bold")
    ax.set_xlabel("support dose (x design intensity)", fontsize=8.5, color=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.margins(x=0.25)
axes[0].set_ylabel(f"continued minus withdrawn, day +{H:.0f}", fontsize=8.5, color=MUTED)
handles = [plt.Line2D([], [], color=c, marker=m, lw=2, label=l) for c, m, l in CELLS.values()]
fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=9, bbox_to_anchor=(0.5, -0.04))
fig.suptitle("The same support builds capability or only saves lives, depending on which constraint binds",
             x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0.04, 1, 0.95))
out = ROOT / f"dose_response_{H:.0f}.png"
fig.savefig(out, dpi=170, facecolor=SURFACE, bbox_inches="tight")
print("wrote", out)
