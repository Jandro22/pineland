"""Answer the autonomy-trap questions from a (local or ARC) campaign's raw task outputs.

  python analyze_local.py --campaign DIR [--scratch DIR] [--h 360]

Tables (day +h, paired by seed, Wilcoxon p, share of seeds positive):
  1 trap        continued-minus-withdrawn effect by learning rate (A blocks)
  2 duration    same effect by withdrawal day (B blocks; T=120 is A)
  3 exit        withdrawn-branch outcome when one channel stays 180 days longer,
                minus immediate full withdrawal (S vs A_lr0.25, same seeds)
  4 remedy      continued-minus-withdrawn effect with developmental assistance (G vs A)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

METRICS = {"composite_capability": "capability", "c_military_personnel_retention": "army",
           "c_geographic_coverage_retention": "coverage", "c_government_control": "gov ctrl"}


def load(campaign: Path, scratch: Path) -> pd.DataFrame:
    rows = []
    for line in (campaign / "tasks.jsonl").read_text().splitlines():
        t = json.loads(line)
        d = scratch / "tasks" / f"{t['id']:06d}"
        if not (d / "_SUCCESS.json").exists():
            continue
        w = pd.read_csv(d / "w.csv")
        structure = json.loads((campaign / t["contract"]).read_text())["cells"][t["cell_index"]]["factor_structure"]
        for _, r in w.iterrows():
            rows.append(dict(variant=t["variant"], structure=structure, seed=t["seed"], h=float(r.horizon_days),
                             branch=r.branch, **{m: float(r[m]) for m in METRICS}))
    return pd.DataFrame(rows)


def stat(x: np.ndarray) -> str:
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return "      n<3"
    p = stats.wilcoxon(x).pvalue if np.any(x != 0) else 1.0
    star = "*" if p < 0.05 else " "
    return f"{x.mean():+.3f}{star} {int((x > 0).sum()):>2}/{len(x):<2}"


def effect(df: pd.DataFrame, variant: str, h: float) -> pd.DataFrame:
    g = df[(df.variant == variant) & (df.h == h)]
    on = g[g.branch == "SUPPORT_ON"].set_index(["structure", "seed"])
    off = g[g.branch == "SUPPORT_OFF"].set_index(["structure", "seed"])
    return (on[list(METRICS)] - off[list(METRICS)]).dropna()


def branch(df: pd.DataFrame, variant: str, h: float, name: str) -> pd.DataFrame:
    g = df[(df.variant == variant) & (df.h == h) & (df.branch == name)]
    return g.set_index(["structure", "seed"])[list(METRICS)]


def table(title: str, blocks: dict[str, pd.DataFrame]) -> None:
    print(f"\n== {title}")
    structures = sorted({s for b in blocks.values() for s in b.index.get_level_values(0)})
    for metric, label in METRICS.items():
        print(f"  [{label}]  " + "  ".join(f"{s.split('_')[0]:>18s}" for s in structures))
        for name, b in blocks.items():
            cells = []
            for s in structures:
                x = b.loc[s][metric].to_numpy() if s in b.index.get_level_values(0) else np.array([])
                cells.append(f"{stat(x):>18s}")
            print(f"    {name:24s}" + "  ".join(cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=Path, required=True)
    ap.add_argument("--scratch", type=Path)
    ap.add_argument("--h", type=float, default=360.0)
    a = ap.parse_args()
    df = load(a.campaign, a.scratch or a.campaign / "scratch")
    df.to_csv(a.campaign / "branch_outcomes.csv", index=False)
    variants = set(df.variant)
    h = a.h
    print(f"tasks loaded: {df[['variant', 'structure', 'seed']].drop_duplicates().shape[0]}; horizon +{h:g} days")
    print("cells: mean effect (* p<0.05), seeds positive / n")
    table("1 trap: continued minus withdrawn, by learning rate",
          {v: effect(df, v, h) for v in sorted(v for v in variants if v.startswith("A_"))})
    dur = {}
    for t in (90, 120, 240, 360):
        for lr in ("0", "0.25"):
            v = f"A_lr{lr}" if t == 120 else f"B_T{t}_lr{lr}"
            if v in variants:
                dur[f"T{t} lr{lr}"] = effect(df, v, h)
    table("2 duration: continued minus withdrawn, by withdrawal day", dur)
    if "A_lr0.25" in variants:
        base = branch(df, "A_lr0.25", h, "SUPPORT_OFF")
        table("3 exit: withdrawn branch with one channel kept 180 d, minus immediate exit (learning .25)",
              {v: (branch(df, v, h, "SUPPORT_OFF") - base).dropna()
               for v in sorted(v for v in variants if v.startswith("S_"))})
    table("4 remedy: continued minus withdrawn with developmental assistance",
          {v: effect(df, v, h) for v in sorted(v for v in variants if v.startswith("G_"))})


if __name__ == "__main__":
    main()
