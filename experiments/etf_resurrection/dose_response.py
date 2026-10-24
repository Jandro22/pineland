"""Dose-response of continued support (coupled twins): paired ON-OFF effects by dose, cell and horizon."""
import glob, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results/local_v6/prod2"
METRICS = {
    "composite_capability": "composite",
    "c_government_control": "gov control",
    "c_military_personnel_retention": "army retention",
    "post_military_losses": "army losses",
    "post_indigenous_graduates": "indigenous graduates",
    "c_geographic_coverage_retention": "coverage",
}
runs = {1.0: ROOT / "val"} | {float(p.name.split("_")[1]): p for p in ROOT.glob("dose_*") if p.is_dir()}
rows = []
for dose, d in runs.items():
    for f in d.glob("*_*/w.csv"):
        cell, seed = f.parent.name.split("_")
        if int(seed) >= 16:
            continue
        w = pd.read_csv(f)
        for h in (90, 180, 360):
            on = w[(w.branch == "SUPPORT_ON") & (w.horizon_days == h)]
            off = w[(w.branch == "SUPPORT_OFF") & (w.horizon_days == h)]
            if on.empty:
                continue
            r = dict(dose=dose, cell=cell, seed=int(seed), h=h)
            for k in METRICS:
                r[k] = float(on[k].iloc[0]) - float(off[k].iloc[0])
            rows.append(r)
df = pd.DataFrame(rows)
df.to_csv(ROOT / "dose_response_runs.csv", index=False)
out = []
for (cell, h, dose), g in df.groupby(["cell", "h", "dose"]):
    r = dict(cell=cell, h=h, dose=dose, n=len(g))
    for k, name in METRICS.items():
        x = g[k].to_numpy()
        r[name] = x.mean()
        r[name + " se"] = x.std(ddof=1) / np.sqrt(len(x))
        r[name + " p"] = stats.wilcoxon(x).pvalue if np.any(x != 0) else 1.0
    out.append(r)
t = pd.DataFrame(out)
t.to_csv(ROOT / "dose_response.csv", index=False)
pd.set_option("display.width", 250)
for cell in t.cell.unique():
    print("==", cell)
    print(t[t.cell == cell][["h", "dose", "n", "composite", "gov control", "army retention", "army losses",
                             "indigenous graduates", "coverage"]].round(4).to_string(index=False))
