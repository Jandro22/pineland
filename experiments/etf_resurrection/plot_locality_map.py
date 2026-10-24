"""Side-by-side Pineland maps: SUPPORT_ON vs SUPPORT_OFF from one paired world.

Inputs come from the Stage-4 harness run with ``--locality-output PATH``:
``PATH`` (per-locality snapshots) and ``PATH``'s ``.topology.csv`` sibling.

Outputs (next to the input unless --out-dir is given):
  map_<cell>_<seed>.gif           animation over time, both branches
  map_<cell>_<seed>_panels.png    small multiples at selected days
  map_<cell>_<seed>_divergence.png  where the branches end up different

Colour = net control (insurgent effective control minus government effective
control, red = insurgent, blue = government). Marker size = troops present;
a black ring marks a staffed police post, an "x" an overrun/unstaffed one.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

BRANCHES = ("SUPPORT_ON", "SUPPORT_OFF")
TITLES = {"SUPPORT_ON": "Support continued", "SUPPORT_OFF": "Support withdrawn"}


def load(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = pd.read_csv(path)
    topo = pd.read_csv(path.with_suffix(".topology.csv"))
    rows["net"] = rows["ins_control"] - rows["gov_control"]
    return rows, topo


def edges(topo: pd.DataFrame) -> list[tuple[int, int]]:
    out = []
    for _, r in topo.iterrows():
        for n in str(r["neighbors"]).split(";"):
            if n and n != "nan" and int(n) > int(r["locality"]):
                out.append((int(r["locality"]), int(n)))
    return out


def frame(rows: pd.DataFrame, branch: str, day: float) -> pd.DataFrame:
    """Snapshot of a branch at ``day``; before withdrawal both share PRE_SUPPORTED."""
    pool = rows[rows["branch"].isin([branch, "PRE_SUPPORTED"])]
    times = np.sort(pool["time_days"].unique())
    t = times[np.searchsorted(times, day, side="right") - 1]
    snap = pool[pool["time_days"] == t]
    if snap["branch"].nunique() > 1:
        snap = snap[snap["branch"] == branch]
    return snap.sort_values("locality")


def draw(ax, topo, links, snap, norm, title):
    ax.clear()
    xy = topo.set_index("locality")[["x_km", "y_km"]]
    for a, b in links:
        ax.plot(*zip(xy.loc[a], xy.loc[b]), color="#bbbbbb", lw=0.6, zorder=1)
    s = snap.set_index("locality").reindex(xy.index)
    troops = s["military_personnel"].fillna(0) + s["insurgent_personnel"].fillna(0)
    size = 40 + 260 * np.sqrt(troops / max(troops.max(), 1.0))
    ax.scatter(xy["x_km"], xy["y_km"], c=s["net"], cmap="RdBu_r", norm=norm, s=size,
               edgecolors="none", zorder=2)
    staffed = s["police_staffed"] > 0
    ax.scatter(xy["x_km"][staffed], xy["y_km"][staffed], s=size[staffed] + 30,
               facecolors="none", edgecolors="black", linewidths=0.8, zorder=3)
    ax.scatter(xy["x_km"][~staffed], xy["y_km"][~staffed], marker="x", s=30,
               color="black", zorder=4)
    gov = snap["gov_control"].mean()
    ins = snap["ins_control"].mean()
    mil = snap["military_personnel"].sum()
    ax.set_title(f"{title}\ngov {gov:.2f} | ins {ins:.2f} | army {mil:,.0f}", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("localities", type=Path)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--fps", type=int, default=6)
    args = ap.parse_args()
    rows, topo = load(args.localities)
    out_dir = args.out_dir or args.localities.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    cell = rows["cell_id"].iloc[0]
    seed = rows["seed"].iloc[0]
    stem = f"map_{cell}_{seed}"
    links = edges(topo)
    lim = max(0.05, rows["net"].abs().quantile(0.98))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    pre = rows[rows["branch"] == "PRE_SUPPORTED"]["time_days"]
    withdrawal = pre.max() if len(pre) else rows["time_days"].min()
    days = np.sort(rows["time_days"].unique())

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.6))
    sup = fig.suptitle("")

    def update(i):
        day = days[i]
        for ax, branch in zip(axes, BRANCHES):
            draw(ax, topo, links, frame(rows, branch, day), norm, TITLES[branch])
        phase = "before withdrawal" if day <= withdrawal else f"+{day - withdrawal:.0f} days after withdrawal"
        sup.set_text(f"Pineland {cell}, seed {seed}: day {day:.0f} ({phase})")
        return []

    anim = FuncAnimation(fig, update, frames=len(days), blit=False)
    anim.save(out_dir / f"{stem}.gif", writer=PillowWriter(fps=args.fps))
    plt.close(fig)

    picks = [withdrawal] + [withdrawal + d for d in (30, 90, 180, 360) if withdrawal + d <= days.max()]
    fig, axes = plt.subplots(2, len(picks), figsize=(3.4 * len(picks), 7))
    axes = np.atleast_2d(axes)
    for j, day in enumerate(picks):
        for i, branch in enumerate(BRANCHES):
            draw(axes[i, j], topo, links, frame(rows, branch, day), norm,
                 f"{TITLES[branch]}, +{day - withdrawal:.0f}d")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="RdBu_r"), ax=axes, shrink=0.6,
                 label="insurgent minus government control")
    fig.savefig(out_dir / f"{stem}_panels.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    end = days.max()
    on, off = frame(rows, "SUPPORT_ON", end), frame(rows, "SUPPORT_OFF", end)
    diff = off.set_index("locality")["net"] - on.set_index("locality")["net"]
    fig, ax = plt.subplots(figsize=(6, 5.6))
    snap = off.copy()
    snap["net"] = diff.reindex(snap["locality"]).values
    dl = max(0.02, diff.abs().max())
    draw(ax, topo, links, snap, TwoSlopeNorm(vmin=-dl, vcenter=0, vmax=dl),
         f"Day {end:.0f}: withdrawn minus continued (red = lost to insurgents)")
    fig.savefig(out_dir / f"{stem}_divergence.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {stem}.gif, {stem}_panels.png, {stem}_divergence.png to {out_dir}")


if __name__ == "__main__":
    main()
