"""Mechanism figure: what continued support does to the partner's own output and to losses, by support dose (production campaign, pooled over structures)."""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).parent
e = pd.read_csv(root / "results/arc_prod/out/effects.csv")
e = e[(e.h == 360) & (e.factor_support_intensity == 1.0)]
variants = {0: {1: "A_lr0", 4: "D_dose4_lr0", 16: "D_dose16_lr0"},
            0.25: {1: "A_lr0.25", 4: "D_dose4_lr0.25", 16: "D_dose16_lr0.25"}}
INK, MUTED, BG = "#1f2328", "#6b7280", "#fcfcfb"
C_OFF, C_ON = "#2b5d9b", "#b8472f"
panels = [("post_indigenous_logistics_produced", 1e-3, "The partner's own supply output,\ncontinued minus withdrawn (thousand supply units)", "Partner's own output falls when it learns by doing"),
          ("post_military_losses", -1.0, "Military personnel losses avoided\nby continuing support (people)", "Continued support saves lives either way")]
fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.9), facecolor=BG)
pooled = {}
for ax, (col, scale, ylab, title) in zip(axes, panels):
    ax.set_facecolor(BG)
    for lr, color, lab in ((0, C_OFF, "Partner does not learn by doing"), (0.25, C_ON, "Partner learns by doing")):
        xs, ms, ci = [], [], []
        for dose, v in variants[lr].items():
            g = e[e.variant == v][col].dropna() * scale
            xs.append(dose); ms.append(g.mean()); ci.append(1.96 * g.std(ddof=1) / np.sqrt(len(g)))
            pooled[(col, lr, dose)] = round(g.mean(), 1)
        ax.errorbar(xs, ms, yerr=ci, color=color, marker="o", lw=2.4, ms=7, capsize=3, label=lab)
    ax.axhline(0, color=MUTED, lw=0.9)
    ax.set_xscale("log", base=2); ax.set_xticks([1, 4, 16], ["1x", "4x", "16x"])
    ax.set_xlabel("Support dose (x design)", fontsize=10.5, color=INK)
    ax.set_ylabel(ylab, fontsize=10, color=INK)
    ax.set_title(title, fontsize=11.5, color=INK, fontweight="bold", loc="left")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=10)
axes[0].legend(frameon=False, fontsize=9.5, loc="lower left")
fig.tight_layout()
out = root / "findings/mechanism_displacement.png"
fig.savefig(out, dpi=170, facecolor=BG)
print(out)
for k, v in sorted(pooled.items()): print(k, v)
# pooled capability effect at the same cells for slide numbers
for lr in (0, 0.25):
    print("capability", lr, {d: round(e[e.variant == v].composite_capability.mean(), 3) for d, v in variants[lr].items()})
