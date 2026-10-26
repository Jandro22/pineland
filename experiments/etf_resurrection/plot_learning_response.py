"""Learning dose-response figure: capability effect of continued support vs learning rate (production campaign, 2,240 worlds per point)."""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).parent
e = pd.read_csv(root / "results/arc_prod/out/effects.csv")
e = e[(e.h == 360) & e.variant.str.startswith("A_lr")]
e["lr"] = e.variant.str.split("lr").str[1].astype(float)
structs = [("command_constrained", "Command-constrained", "#b8472f"), ("balanced_capacity", "Balanced", "#2b5d9b"),
           ("logistics_constrained", "Logistics-constrained", "#8a6d1d"), ("forcegen_constrained", "Force-generation-constrained", "#4c7a5a")]
INK, MUTED, BG = "#1f2328", "#6b7280", "#fcfcfb"
fig, ax = plt.subplots(figsize=(9.2, 5.1), facecolor=BG)
ax.set_facecolor(BG)
lrs = sorted(e.lr.unique())
for st, name, col in structs:
    g = e[e.factor_structure == st].groupby("lr").composite_capability
    m, s, n = g.mean(), g.std(ddof=1), g.count()
    ci = 1.96 * s / np.sqrt(n)
    ax.errorbar(range(len(lrs)), m.loc[lrs], yerr=ci.loc[lrs], color=col, marker="o", lw=2.2, ms=6, capsize=3, label=name)
ax.axhline(0, color=MUTED, lw=0.9)
ax.set_xticks(range(len(lrs)), [f"{x:g}" for x in lrs])
ax.set_xlabel("How fast the partner force gains or loses capacity with use (learning rate per 30 days)", fontsize=10, color=INK)
ax.set_ylabel("Capability effect of continued support\nvs. withdrawal, day +360", fontsize=10, color=INK)
for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
ax.tick_params(colors=MUTED, labelsize=10)
ax.legend(frameon=False, fontsize=9.5, loc="lower left")
ax.annotate("Support helps slightly\nif partners don't learn by doing", (0, 0.019), (0.2, 0.027), fontsize=9.5, color=INK,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
fig.tight_layout()
out = root / "findings/learning_response.png"
fig.savefig(out, dpi=170, facecolor=BG)
print(out)
