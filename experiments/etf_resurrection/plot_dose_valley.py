"""Dose-valley figure: capability effect of continued support vs support dose, with and without learning (production campaign)."""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).parent
e = pd.read_csv(root / "results/arc_prod/out/effects.csv")
e = e[e.h == 360]
core = e[e.factor_support_intensity == 1.0]
variants = {0: {1: "A_lr0", 4: "D_dose4_lr0", 16: "D_dose16_lr0"},
            0.25: {1: "A_lr0.25", 4: "D_dose4_lr0.25", 16: "D_dose16_lr0.25"}}
structs = ["command_constrained", "balanced_capacity", "forcegen_constrained", "logistics_constrained"]
names = {"command_constrained": "Command-constrained", "balanced_capacity": "Balanced",
         "forcegen_constrained": "Force-generation-constrained", "logistics_constrained": "Logistics-constrained"}
INK, MUTED, BG = "#1f2328", "#6b7280", "#fcfcfb"
C_OFF, C_ON = "#2b5d9b", "#b8472f"

fig, axes = plt.subplots(1, 4, figsize=(13.5, 3.9), sharey=True, facecolor=BG)
for ax, st in zip(axes, structs):
    ax.set_facecolor(BG)
    for lr, col, lab in ((0, C_OFF, "Partner does not learn by doing"), (0.25, C_ON, "Partner learns by doing")):
        xs, ms, se = [], [], []
        for dose, v in variants[lr].items():
            g = core[(core.variant == v) & (core.factor_structure == st)].composite_capability.dropna()
            xs.append(dose); ms.append(g.mean()); se.append(g.std(ddof=1) / np.sqrt(len(g)))
        ax.errorbar(xs, ms, yerr=1.96 * np.array(se), color=col, marker="o", lw=2, ms=6, capsize=3, label=lab)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.set_xscale("log", base=2); ax.set_xticks([1, 4, 16], ["1x", "4x", "16x"])
    ax.set_title(names[st], fontsize=10.5, color=INK, fontweight="bold")
    ax.set_xlabel("Support dose (x design)", fontsize=9, color=INK)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5)
axes[0].set_ylabel("Capability effect of continued support\nvs. withdrawal, day +360", fontsize=9, color=INK)
axes[0].legend(fontsize=8, frameon=False, loc="upper left")
fig.suptitle("The dependency valley: with learning by doing, intermediate support is worse than none",
             x=0.01, ha="left", fontsize=12.5, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.93))
out = root / "findings/dose_valley.png"
fig.savefig(out, dpi=170, facecolor=BG)
print(out)
