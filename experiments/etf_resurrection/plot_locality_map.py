"""Pineland war map: SUPPORT_ON vs SUPPORT_OFF from one paired world.

Inputs come from the Stage-4 harness run with ``--locality-output PATH``:
``PATH`` (per-locality snapshots) and its ``.topology.csv`` sibling.

Each locality becomes a Voronoi territory clipped to a smoothed national
outline, coloured by net control (government blue -> contested dark ->
insurgent red). Roads link neighbouring localities; army garrisons are blue
diamonds, insurgent concentrations red triangles (area ~ personnel); police
posts are white dots when staffed and red crosses when overrun; fighting
glows. A shared timeline marks the withdrawal and a strip chart tracks army
strength in both branches. Frames are interpolated between snapshots.

Outputs (next to the input unless --out-dir is given):
  map_<cell>_<seed>.gif / .mp4 (mp4 only if ffmpeg is available)
  map_<cell>_<seed>_panels.png      key moments, both branches
  map_<cell>_<seed>_divergence.png  where the two futures differ at the end
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from scipy.spatial import Voronoi  # noqa: E402
from shapely.geometry import MultiPoint, Polygon  # noqa: E402

BG = "#0b0f17"
PANEL = "#111827"
INK = "#e5e7eb"
MUTED = "#6b7280"
GOV = "#3b82f6"
INS = "#ef4444"
BRANCHES = ("SUPPORT_ON", "SUPPORT_OFF")
TITLES = {"SUPPORT_ON": "SUPPORT CONTINUED", "SUPPORT_OFF": "SUPPORT WITHDRAWN"}
CONTROL = LinearSegmentedColormap.from_list(
    "control", ["#1d4ed8", "#3b82f6", "#1f2937", "#f97316", "#dc2626"]
)
FIELDS = ["net", "military_personnel", "insurgent_personnel", "violence", "police_staffed",
          "gov_control", "ins_control"]


# ---------------------------------------------------------------- geometry
def territories(topo: pd.DataFrame) -> tuple[list[np.ndarray], Polygon]:
    pts = topo[["x_km", "y_km"]].to_numpy()
    span = np.ptp(pts, axis=0).max()
    outline = MultiPoint([tuple(p) for p in pts]).convex_hull.buffer(0.09 * span, join_style=1)
    outline = outline.buffer(-0.03 * span).buffer(0.03 * span)  # soften corners
    far = np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]]) * span * 10 + pts.mean(axis=0)
    vor = Voronoi(np.vstack([pts, far]))
    cells = []
    for i in range(len(pts)):
        region = vor.regions[vor.point_region[i]]
        poly = Polygon(vor.vertices[[v for v in region if v >= 0]]).intersection(outline)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        cells.append(np.asarray(poly.exterior.coords))
    return cells, outline


def roads(topo: pd.DataFrame) -> np.ndarray:
    xy = topo.set_index("locality")[["x_km", "y_km"]]
    segs = []
    for _, r in topo.iterrows():
        for n in str(r["neighbors"]).split(";"):
            if n and n != "nan" and int(n) > int(r["locality"]):
                segs.append([xy.loc[int(r["locality"])].to_numpy(), xy.loc[int(n)].to_numpy()])
    return np.array(segs)


# ---------------------------------------------------------------- data
def load(path: Path):
    rows = pd.read_csv(path)
    topo = pd.read_csv(path.with_suffix(".topology.csv")).sort_values("locality")
    rows["net"] = rows["ins_control"] - rows["gov_control"]
    return rows, topo


def series(rows: pd.DataFrame, branch: str, n: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-locality arrays over time; pre-withdrawal rows are shared."""
    pool = rows[rows["branch"].isin([branch, "PRE_SUPPORTED"])]
    times = np.sort(pool["time_days"].unique())
    out = {f: np.zeros((len(times), n)) for f in FIELDS}
    for k, t in enumerate(times):
        snap = pool[pool["time_days"] == t]
        if snap["branch"].nunique() > 1:
            snap = snap[snap["branch"] == branch]
        snap = snap.set_index("locality").reindex(range(n)).fillna(0)
        for f in FIELDS:
            out[f][k] = snap[f].to_numpy()
    return times, out


def at(times, data, day):
    """Linear interpolation between snapshots (staffing is held, not blended)."""
    k = int(np.clip(np.searchsorted(times, day) - 1, 0, len(times) - 2))
    w = float(np.clip((day - times[k]) / max(times[k + 1] - times[k], 1e-9), 0, 1))
    snap = {f: (1 - w) * data[f][k] + w * data[f][k + 1] for f in FIELDS}
    snap["police_staffed"] = data["police_staffed"][k if w < 0.5 else k + 1]
    return snap


# ---------------------------------------------------------------- drawing
class MapPanel:
    def __init__(self, ax, topo, cells, outline, segs, norm, title):
        self.ax, self.topo, self.title = ax, topo, title
        xy = topo[["x_km", "y_km"]].to_numpy()
        self.xy = xy
        ax.set_facecolor(BG)
        ox, oy = outline.exterior.xy
        ax.fill(ox, oy, color="#0f172a", zorder=0)
        self.terr = PolyCollection(cells, cmap=CONTROL, norm=norm, edgecolors="#0b0f17",
                                   linewidths=0.6, zorder=1)
        self.terr.set_array(np.zeros(len(cells)))
        ax.add_collection(self.terr)
        ax.plot(ox, oy, color="#334155", lw=1.4, zorder=2)
        ax.add_collection(LineCollection(segs, colors="#94a3b8", linewidths=0.5, alpha=0.35, zorder=3))
        self.glow = ax.scatter(xy[:, 0], xy[:, 1], s=0, c="#f59e0b", alpha=0.22, zorder=4, linewidths=0)
        self.core = ax.scatter(xy[:, 0], xy[:, 1], s=0, c="#fde68a", alpha=0.85, zorder=5, linewidths=0)
        self.army = ax.scatter(xy[:, 0], xy[:, 1], s=0, marker="D", c=GOV, edgecolors="white",
                               linewidths=0.6, zorder=6)
        self.ins = ax.scatter(xy[:, 0] + 0.012 * np.ptp(xy[:, 0]), xy[:, 1], s=0, marker="^", c=INS,
                              edgecolors="white", linewidths=0.6, zorder=6)
        self.post = ax.scatter(xy[:, 0], xy[:, 1] - 0.018 * np.ptp(xy[:, 1]), s=10, c="white", zorder=7,
                               linewidths=0)
        self.lost = ax.scatter([], [], s=28, marker="x", c=INS, linewidths=1.6, zorder=7)
        self.head = ax.text(0.02, 0.97, title, transform=ax.transAxes, color=INK, fontsize=12,
                            fontweight="bold", va="top")
        self.stats = ax.text(0.02, 0.91, "", transform=ax.transAxes, color=MUTED, fontsize=9,
                             va="top", family="monospace")
        pad = 0.06 * np.ptp(xy, axis=0).max()
        ax.set_xlim(xy[:, 0].min() - 2 * pad, xy[:, 0].max() + 2 * pad)
        # Extra headroom at the top for the title and stats block.
        ax.set_ylim(xy[:, 1].min() - 2 * pad, xy[:, 1].max() + 6 * pad)
        ax.set_aspect("equal")
        ax.axis("off")

    def update(self, s, scale):
        self.terr.set_array(s["net"])
        self.army.set_sizes(260 * np.sqrt(s["military_personnel"] / scale))
        self.ins.set_sizes(260 * np.sqrt(s["insurgent_personnel"] / scale))
        # Fighting: only localities with real recent violence glow.
        heat = np.clip((s["violence"] - 0.5) / 0.5, 0, 1)
        self.glow.set_sizes(520 * heat ** 1.5)
        self.core.set_sizes(40 * heat ** 1.5)
        staffed = s["police_staffed"] > 0
        self.post.set_offsets(np.c_[self.xy[staffed, 0], self.xy[staffed, 1] - 0.018 * np.ptp(self.xy[:, 1])])
        self.lost.set_offsets(np.c_[self.xy[~staffed, 0], self.xy[~staffed, 1] - 0.018 * np.ptp(self.xy[:, 1])]
                              if (~staffed).any() else np.empty((0, 2)))
        held = int((s["net"] < -0.05).sum())
        lost = int((s["net"] > 0.05).sum())
        self.stats.set_text(
            f"army {s['military_personnel'].sum():>7,.0f}   insurgents {s['insurgent_personnel'].sum():>7,.0f}\n"
            f"gov-held {held:>3}   insurgent-held {lost:>3}   posts lost {int((~staffed).sum()):>3}"
        )


def build_figure(rows, topo, cells, outline, segs, norm):
    fig = plt.figure(figsize=(14, 8.4), facecolor=BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[5, 1.15], hspace=0.08, wspace=0.03,
                          left=0.02, right=0.98, top=0.9, bottom=0.07)
    panels = {b: MapPanel(fig.add_subplot(gs[0, i]), topo, cells, outline, segs, norm, TITLES[b])
              for i, b in enumerate(BRANCHES)}
    strip = fig.add_subplot(gs[1, :], facecolor=PANEL)
    for side in strip.spines.values():
        side.set_color("#1f2937")
    strip.tick_params(colors=MUTED, labelsize=8)
    title = fig.text(0.02, 0.955, "", color=INK, fontsize=15, fontweight="bold")
    sub = fig.text(0.02, 0.925, "", color=MUTED, fontsize=10)
    cax = fig.add_axes([0.80, 0.935, 0.17, 0.014])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=CONTROL), cax=cax, orientation="horizontal")
    cb.set_ticks([norm.vmin, 0, norm.vmax])
    cb.set_ticklabels(["government", "contested", "insurgent"])
    cb.ax.tick_params(colors=MUTED, labelsize=8, length=0)
    cb.outline.set_visible(False)
    return fig, panels, strip, title, sub


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("localities", type=Path)
    ap.add_argument("--out-dir", type=Path)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--days-per-frame", type=float, default=2.0)
    args = ap.parse_args()
    rows, topo = load(args.localities)
    out_dir = args.out_dir or args.localities.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(topo)
    cell, seed = rows["cell_id"].iloc[0], rows["seed"].iloc[0]
    stem = f"map_{cell}_{seed}"
    cells, outline = territories(topo)
    segs = roads(topo)
    lim = max(0.05, rows["net"].abs().quantile(0.98))
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    data = {b: series(rows, b, n) for b in BRANCHES}
    pre = rows.loc[rows["branch"] == "PRE_SUPPORTED", "time_days"]
    withdrawal = float(pre.max()) if len(pre) else float(rows["time_days"].min())
    t0, t1 = float(rows["time_days"].min()), float(rows["time_days"].max())
    days = np.arange(t0, t1 + 1e-9, args.days_per_frame)
    scale = max(rows.groupby(["branch", "time_days", "locality"])[["military_personnel", "insurgent_personnel"]]
                .sum().max().max(), 1.0)
    army = {b: [at(*data[b], d)["military_personnel"].sum() for d in days] for b in BRANCHES}

    fig, panels, strip, title, sub = build_figure(rows, topo, cells, outline, segs, norm)
    strip.axvline(withdrawal, color="#fbbf24", lw=1, ls="--")
    strip.text(withdrawal, 1.02, " withdrawal", color="#fbbf24", fontsize=8, transform=strip.get_xaxis_transform())
    lines = {b: strip.plot([], [], color=(GOV if b == "SUPPORT_ON" else INS), lw=2,
                           label=TITLES[b].title())[0] for b in BRANCHES}
    cursor = strip.axvline(t0, color=INK, lw=0.8, alpha=0.6)
    strip.set_xlim(t0, t1)
    strip.set_ylim(0, max(max(v) for v in army.values()) * 1.08)
    strip.set_ylabel("army strength", color=MUTED, fontsize=8)
    strip.set_xlabel("day", color=MUTED, fontsize=8)
    strip.legend(loc="lower left", frameon=False, labelcolor=INK, fontsize=8)

    def update(i):
        day = days[i]
        for b in BRANCHES:
            panels[b].update(at(*data[b], day), scale)
            lines[b].set_data(days[: i + 1], army[b][: i + 1])
        cursor.set_xdata([day, day])
        title.set_text(f"PINELAND  |  day {day:5.0f}")
        sub.set_text("same world, same history until withdrawal; then two futures"
                     if day <= withdrawal else f"{day - withdrawal:.0f} days after the support decision")
        return []

    anim = FuncAnimation(fig, update, frames=len(days), blit=False)
    anim.save(out_dir / f"{stem}.gif", writer=PillowWriter(fps=args.fps), savefig_kwargs={"facecolor": BG})
    if shutil.which("ffmpeg"):
        anim.save(out_dir / f"{stem}.mp4", writer=FFMpegWriter(fps=args.fps, bitrate=4000),
                  savefig_kwargs={"facecolor": BG})
    plt.close(fig)

    # Key-moment panels.
    picks = [withdrawal] + [withdrawal + d for d in (90, 180, 360) if withdrawal + d <= t1]
    fig, axes = plt.subplots(2, len(picks), figsize=(4.2 * len(picks), 8.2), facecolor=BG)
    axes = np.atleast_2d(axes).reshape(2, len(picks))
    for j, day in enumerate(picks):
        for i, b in enumerate(BRANCHES):
            p = MapPanel(axes[i, j], topo, cells, outline, segs, norm,
                         f"{TITLES[b]}  +{day - withdrawal:.0f}d")
            p.update(at(*data[b], day), scale)
            p.head.set_fontsize(9)
            p.stats.set_fontsize(7)
    fig.savefig(out_dir / f"{stem}_panels.png", dpi=170, facecolor=BG, bbox_inches="tight")
    plt.close(fig)

    # Divergence at the end: where withdrawal lost ground relative to support.
    on, off = at(*data["SUPPORT_ON"], t1), at(*data["SUPPORT_OFF"], t1)
    diff = off["net"] - on["net"]
    dl = max(0.02, np.abs(diff).max())
    fig, ax = plt.subplots(figsize=(7.5, 7.5), facecolor=BG)
    p = MapPanel(ax, topo, cells, outline, segs, TwoSlopeNorm(vmin=-dl, vcenter=0, vmax=dl),
                 f"DAY {t1:.0f}: COST OF WITHDRAWAL")
    p.update({**off, "net": diff}, scale)
    p.stats.set_text("red = ground lost to insurgents because support was withdrawn")
    fig.savefig(out_dir / f"{stem}_divergence.png", dpi=170, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {stem}.gif, {stem}_panels.png, {stem}_divergence.png to {out_dir}")


if __name__ == "__main__":
    main()
