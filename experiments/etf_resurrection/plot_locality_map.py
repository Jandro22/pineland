"""Pineland situation map: SUPPORT_CONTINUED vs SUPPORT_WITHDRAWN from one paired world.

Inputs come from the Stage-4 harness run with ``--locality-output PATH``:
``PATH`` (per-locality snapshots) and its ``.topology.csv`` sibling.

Reads like a staff situation map (APP-6 / MIL-STD-2525 style symbology):
  * localities are fractal-bordered territories (districts outlined, named),
    tinted by net control: blue = government, red = insurgent, pale = contested
  * blue rectangle with X = army infantry; red diamond with X = insurgent force;
    echelon marks above the frame (I company, II battalion, III regiment, X brigade)
  * each locality has ONE symbol slot; slots are spread apart so none overlap,
    with a thin leader line to the true locality position
  * small blue square = police post held, red cross = post overrun
  * dark ring = heavy fighting in the last interval
  * every panel carries counts; the legend and a strip chart (army strength in
    both branches, withdrawal marked) explain the rest

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
import matplotlib.patches
import matplotlib.patheffects as pe

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.collections import LineCollection, PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from scipy.spatial import Voronoi  # noqa: E402
from shapely.geometry import MultiPoint, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

PAPER = "#f4f1ea"
SEA = "#EBEAE6"
INK = "#1f2933"
MUTED = "#5b6670"
GOV = "#2b5d9b"
INS = "#b5332a"
BRANCHES = ("SUPPORT_ON", "SUPPORT_OFF")
TITLES = {"SUPPORT_ON": "SUPPORT CONTINUED", "SUPPORT_OFF": "SUPPORT WITHDRAWN"}
CONTROL = LinearSegmentedColormap.from_list("control", ["#4f83bd", "#a9c4e0", "#efeadf", "#e2a79b", "#c4574a"])
FIELDS = ["net", "gov_control", "ins_control", "military_personnel", "insurgent_personnel", "violence", "police_staffed"]
FRIEND_FILL, FRIEND_EDGE = "#80e0ff", "#0b3a5c"
HOSTILE_FILL, HOSTILE_EDGE = "#ff8080", "#5c0b0b"
ECHELON = [(15, ""), (60, "•"), (200, "I"), (800, "II"), (3000, "III"), (8000, "X")]


# ---------------------------------------------------------------- geometry
def _jag(a, b, rng, depth=6, rough=0.22, decay=0.62):
    """Fractal (midpoint-displacement) polyline from a to b: natural, jagged borders."""
    pts = [np.asarray(a, float), np.asarray(b, float)]
    amp = rough
    for _ in range(depth):
        out = [pts[0]]
        for p, q in zip(pts[:-1], pts[1:]):
            d = q - p
            out.append((p + q) / 2 + np.array([-d[1], d[0]]) * rng.normal(0, amp))
            out.append(q)
        pts, amp = out, amp * decay
    return pts


def jagged_ring(ring):
    """Identical displacement for both neighbours of a shared edge, so borders stay shared."""
    out = []
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        ka, kb = tuple(np.round(a, 5)), tuple(np.round(b, 5))
        rng = np.random.default_rng(abs(hash(tuple(sorted((ka, kb))))) % (2**32))
        pts = _jag(a, b, rng) if ka <= kb else _jag(b, a, rng)[::-1]
        out.extend(pts[:-1])
    return np.array(out)


def territories(topo: pd.DataFrame):
    pts = topo[["x_km", "y_km"]].to_numpy()
    span = np.ptp(pts, axis=0).max()
    hull = MultiPoint([tuple(p) for p in pts]).convex_hull.buffer(0.10 * span, join_style=1).simplify(0.04 * span)
    rng = np.random.default_rng(7)
    ring = np.asarray(hull.exterior.coords)[:-1]
    border = []
    for i in range(len(ring)):
        border.extend(_jag(ring[i], ring[(i + 1) % len(ring)], rng, depth=7, rough=0.14, decay=0.66)[:-1])
    outline = Polygon(border).buffer(0)
    if outline.geom_type == "MultiPolygon":
        outline = max(outline.geoms, key=lambda g: g.area)
    far = np.array([[-1, -1], [-1, 1], [1, -1], [1, 1]]) * span * 10 + pts.mean(axis=0)
    vor = Voronoi(np.vstack([pts, far]))
    polys = []
    for i in range(len(pts)):
        region = vor.regions[vor.point_region[i]]
        poly = Polygon(jagged_ring(vor.vertices[[v for v in region if v >= 0]])).buffer(0).intersection(outline)
        if poly.geom_type != "Polygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        polys.append(poly)
    cells = [np.asarray(p.exterior.coords) for p in polys]
    districts, dgeoms = [], []
    for d in sorted(topo["district"].unique()):
        u = unary_union([polys[i] for i in np.flatnonzero(topo["district"].to_numpy() == d)])
        for g in (u.geoms if u.geom_type == "MultiPolygon" else [u]):
            districts.append(np.asarray(g.exterior.coords))
        dgeoms.append((d, max(u.geoms, key=lambda g: g.area) if u.geom_type == "MultiPolygon" else u))
    return cells, outline, districts, dgeoms, polys


def badge_positions(dgeoms, anchors):
    """District badge at the open spot farthest from borders and from every unit symbol."""
    out = []
    for d, g in dgeoms:
        minx, miny, maxx, maxy = g.bounds
        best, score = g.representative_point().coords[0], -1.0
        for x in np.linspace(minx, maxx, 28):
            for y in np.linspace(miny, maxy, 28):
                pt = Point(x, y)
                if not g.contains(pt):
                    continue
                sc = min(g.exterior.distance(pt), float(np.min(np.hypot(anchors[:, 0] - x, anchors[:, 1] - y))))
                if sc > score:
                    best, score = (x, y), sc
        out.append((d, best))
    return out


def spread_anchors(xy: np.ndarray, outline: Polygon, min_sep: float) -> np.ndarray:
    """Relax symbol anchors so no two localities' symbol pairs overlap (kept inside the outline)."""
    inner = outline.buffer(-min_sep * 0.3)
    a = xy.copy()
    rng = np.random.default_rng(3)
    a += rng.normal(0, min_sep * 0.02, a.shape)
    for _ in range(600):
        moved = False
        for i in range(len(a)):
            d = a[i] - a
            dist = np.hypot(d[:, 0], d[:, 1])
            dist[i] = np.inf
            j = int(np.argmin(dist))
            if dist[j] < min_sep:
                push = (d[j] / max(dist[j], 1e-9)) * (min_sep - dist[j]) * 0.5
                a[i] += push
                a[j] -= push
                moved = True
        for i in range(len(a)):
            if not inner.contains(Point(a[i])):
                nearest = inner.exterior.interpolate(inner.exterior.project(Point(a[i])))
                a[i] = [nearest.x, nearest.y]
        if not moved:
            break
    return a


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


def series(rows: pd.DataFrame, branch: str, n: int):
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
    k = int(np.clip(np.searchsorted(times, day) - 1, 0, len(times) - 2))
    w = float(np.clip((day - times[k]) / max(times[k + 1] - times[k], 1e-9), 0, 1))
    snap = {f: (1 - w) * data[f][k] + w * data[f][k + 1] for f in FIELDS}
    snap["police_staffed"] = data["police_staffed"][k if w < 0.5 else k + 1]
    return snap


# ---------------------------------------------------------------- symbols
def echelon(n: float) -> str:
    label = ""
    for floor, mark in ECHELON:
        if n >= floor:
            label = mark
    return label


class Unit:
    """APP-6 style symbol: friendly rectangle / hostile diamond, infantry X, echelon mark."""

    def __init__(self, ax, hostile: bool, z=8):
        self.hostile = hostile
        fill, edge = (HOSTILE_FILL, HOSTILE_EDGE) if hostile else (FRIEND_FILL, FRIEND_EDGE)
        self.frame = matplotlib.patches.Polygon(np.zeros((4, 2)), closed=True, fc=fill, ec=edge, lw=1.1, zorder=z, path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])
        ax.add_patch(self.frame)
        self.x1, = ax.plot([], [], color=edge, lw=0.9, zorder=z + 1)
        self.x2, = ax.plot([], [], color=edge, lw=0.9, zorder=z + 1)
        self.mark = ax.text(0, 0, "", color=INK, fontsize=6.5, ha="center", va="bottom", fontweight="bold",
                            zorder=z + 2, path_effects=[pe.withStroke(linewidth=2, foreground="white")])
        self.artists = [self.frame, self.x1, self.x2, self.mark]

    def set(self, cx, cy, size, personnel):
        show = personnel >= 15
        for a in self.artists:
            a.set_visible(bool(show))
        if not show:
            return
        w, h = size * 1.5, size
        if self.hostile:
            pts = np.array([[cx, cy + h * 0.75], [cx + w * 0.62, cy], [cx, cy - h * 0.75], [cx - w * 0.62, cy]])
            hw, hh, top = w * 0.31, h * 0.37, cy + h * 0.75
        else:
            pts = np.array([[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2],
                            [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]])
            hw, hh, top = w / 2, h / 2, cy + h / 2
        self.frame.set_xy(pts)
        self.x1.set_data([cx - hw, cx + hw], [cy - hh, cy + hh])
        self.x2.set_data([cx - hw, cx + hw], [cy + hh, cy - hh])
        self.mark.set_position((cx, top))
        self.mark.set_text(echelon(personnel))


# ---------------------------------------------------------------- panel
class MapPanel:
    def __init__(self, ax, topo, geo, norm, title, compact=False):
        cells, outline, districts, labels, segs, anchors, sym = geo
        self.ax, self.topo, self.title, self.anchors, self.sym = ax, topo, title, anchors, sym
        xy = topo[["x_km", "y_km"]].to_numpy()
        self.xy = xy
        span = float(np.ptp(xy, axis=0).max())
        ax.set_facecolor(SEA)
        ox, oy = outline.exterior.xy
        self.terr = PolyCollection(cells, cmap=CONTROL, norm=norm, edgecolors=(0, 0, 0, 0.28), linewidths=0.5,
                                   zorder=1)
        self.terr.set_array(np.zeros(len(cells)))
        ax.add_collection(self.terr)
        ax.add_collection(LineCollection(segs, colors="#444444", linewidths=0.6, alpha=0.25, zorder=1.5))
        ax.add_collection(PolyCollection(districts, facecolors="none", edgecolors="white", linewidths=2.8,
                                         zorder=2))
        ax.add_collection(PolyCollection(districts, facecolors="none", edgecolors="#333333", linewidths=1.1,
                                         zorder=2.2))
        ax.plot(ox, oy, color="#1a1a1a", lw=2.4, zorder=2.5)
        for name, (lx, ly) in labels:
            ax.text(lx, ly, f"D{name}", color="#222222", fontsize=7 if compact else 9, ha="center", va="center",
                    fontweight="bold", zorder=7,
                    path_effects=[pe.withStroke(linewidth=2.5, foreground=(1, 1, 1, 0.75))])
        lead = [[xy[i], anchors[i]] for i in range(len(xy)) if np.hypot(*(xy[i] - anchors[i])) > 0.2 * sym]
        ax.add_collection(LineCollection(lead, colors="#333333", linewidths=0.7, alpha=0.7, zorder=4))
        ax.scatter(xy[:, 0], xy[:, 1], s=4, c="#444444", zorder=4.5, linewidths=0)
        self.ring = ax.scatter(anchors[:, 0], anchors[:, 1], s=0, facecolors="none", edgecolors="#9b1c1c",
                               linewidths=1.3, linestyles=(0, (3, 2)), zorder=6)
        self.army_units = [Unit(ax, False) for _ in range(len(xy))]
        self.ins_units = [Unit(ax, True) for _ in range(len(xy))]
        self.lost = ax.scatter([], [], s=36, marker="X", c="#d62828", edgecolors="white", linewidths=0.6, zorder=7)
        self.head = ax.text(0.02, 0.985, title, transform=ax.transAxes, color=INK, fontsize=11 if compact else 13,
                            fontweight="bold", va="top")
        self.stats = ax.text(0.02, 0.94, "", transform=ax.transAxes, color=MUTED,
                             fontsize=6.5 if compact else 8, va="top", linespacing=1.5)
        pad = 0.06 * span
        x0, x1 = xy[:, 0].min() - 2.4 * pad, xy[:, 0].max() + 2.4 * pad
        y0, y1 = xy[:, 1].min() - 2.4 * pad, xy[:, 1].max() + 5 * pad
        bar = 10 ** np.floor(np.log10(span / 3))
        bx, by = x0 + pad, y0 + 0.9 * pad
        ax.plot([bx, bx + bar], [by, by], color=INK, lw=2.2, zorder=11)
        ax.text(bx + bar / 2, by + 0.3 * pad, f"{bar:g} km", color=INK, fontsize=7, ha="center", zorder=11)
        ax.annotate("", xy=(x1 - pad, y0 + 2.4 * pad), xytext=(x1 - pad, y0 + 0.6 * pad),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2), zorder=11)
        ax.text(x1 - pad, y0 + 2.6 * pad, "N", color=INK, fontsize=8, ha="center", fontweight="bold")
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color("#8b8f94")

    def update(self, s, scale):
        self.terr.set_array(s["net"])
        a, sym = self.anchors, self.sym
        for i in range(len(a)):
            m, e = s["military_personnel"][i], s["insurgent_personnel"][i]
            dx = 0.55 * sym if (m >= 15 and e >= 15) else 0.0
            size = sym * (0.6 + 0.4 * np.sqrt(max(m, e) / scale))
            self.army_units[i].set(a[i, 0] - dx, a[i, 1], size, m)
            self.ins_units[i].set(a[i, 0] + dx, a[i, 1], size, e)
        heat = np.clip((s["violence"] - 0.5) / 0.5, 0, 1)
        self.ring.set_sizes(380 * heat)
        staffed = s["police_staffed"] > 0
        off = np.array([0.0, -0.95 * sym])
        self.lost.set_offsets(a[~staffed] + off if (~staffed).any() else np.empty((0, 2)))
        gov, ins = s["gov_control"].mean(), s["ins_control"].mean()
        self.stats.set_text(
            f"Army {s['military_personnel'].sum():,.0f}   Insurgents {s['insurgent_personnel'].sum():,.0f}\n"
            f"Mean control: government {gov:.1%}, insurgent {ins:.1%}\n"
            f"Police posts overrun: {int((~staffed).sum())} of {len(a)}"
        )


def legend(ax, note=None):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.scatter([0.015], [0.62], s=110, marker="s", c=FRIEND_FILL, edgecolors=FRIEND_EDGE, linewidths=1.1)
    ax.text(0.03, 0.62, "Army (friendly)", va="center", fontsize=8, color=INK)
    ax.scatter([0.165], [0.62], s=110, marker="D", c=HOSTILE_FILL, edgecolors=HOSTILE_EDGE, linewidths=1.1)
    ax.text(0.18, 0.62, "Insurgent force (hostile)", va="center", fontsize=8, color=INK)
    ax.scatter([0.40], [0.62], s=36, marker="X", c="#d62828", edgecolors="white", linewidths=0.6)
    ax.text(0.413, 0.62, "Police post overrun", va="center", fontsize=8, color=INK)
    ax.scatter([0.575], [0.62], s=150, facecolors="none", edgecolors="#9b1c1c", linewidths=1.3,
               linestyles=(0, (3, 2)))
    ax.text(0.595, 0.62, "Heavy fighting", va="center", fontsize=8, color=INK)
    ax.plot([0.70, 0.735], [0.62, 0.62], color="#444444", lw=0.8, alpha=0.5)
    ax.text(0.745, 0.62, "Road link", va="center", fontsize=8, color=INK)
    ax.text(0.012, 0.28, "Echelon: \u2022 squad   I company   II battalion   III regiment   X brigade;"
            " symbol size also grows with strength.", va="center", fontsize=8, color=MUTED)
    if note:
        ax.text(0.012, -0.08, note, va="center", fontsize=8, color=MUTED)


def build_figure(topo, geo, norm):
    fig = plt.figure(figsize=(14, 9.6), facecolor=PAPER)
    gs = fig.add_gridspec(3, 2, height_ratios=[5.2, 1.1, 0.55], hspace=0.12, wspace=0.03,
                          left=0.02, right=0.98, top=0.9, bottom=0.02)
    panels = {b: MapPanel(fig.add_subplot(gs[0, i]), topo, geo, norm, TITLES[b]) for i, b in enumerate(BRANCHES)}
    strip = fig.add_subplot(gs[1, :], facecolor="#fbfaf6")
    for side in strip.spines.values():
        side.set_color("#c9c5ba")
    strip.tick_params(colors=MUTED, labelsize=8)
    legend(fig.add_subplot(gs[2, :]))
    title = fig.text(0.02, 0.955, "", color=INK, fontsize=16, fontweight="bold")
    sub = fig.text(0.02, 0.925, "", color=MUTED, fontsize=10)
    cax = fig.add_axes([0.74, 0.935, 0.23, 0.014])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=CONTROL), cax=cax, orientation="horizontal")
    cb.set_ticks([norm.vmin, 0, norm.vmax])
    cb.set_ticklabels(["government control", "contested", "insurgent control"])
    cb.ax.tick_params(colors=INK, labelsize=8, length=0)
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
    xy = topo[["x_km", "y_km"]].to_numpy()
    span = float(np.ptp(xy, axis=0).max())
    sym = 0.036 * span
    cells, outline, districts, dgeoms, polys = territories(topo)
    anchors = spread_anchors(xy, outline, 2.6 * sym)
    labels = badge_positions(dgeoms, anchors)
    geo = (cells, outline, districts, labels, roads(topo), anchors, sym)
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

    fig, panels, strip, title, sub = build_figure(topo, geo, norm)
    strip.axvspan(withdrawal, t1, color="#e8e3d6", alpha=0.6, lw=0)
    strip.axvline(withdrawal, color="#b45309", lw=1.2, ls="--")
    strip.text(withdrawal, 1.04, " external support withdrawn", color="#b45309", fontsize=8,
               transform=strip.get_xaxis_transform())
    lines = {b: strip.plot([], [], color=(GOV if b == "SUPPORT_ON" else INS), lw=2.2,
                           label=TITLES[b].title())[0] for b in BRANCHES}
    cursor = strip.axvline(t0, color=INK, lw=0.8, alpha=0.6)
    strip.set_xlim(t0, t1)
    strip.set_ylim(0, max(max(v) for v in army.values()) * 1.1)
    strip.set_ylabel("army personnel", color=MUTED, fontsize=8)
    strip.set_xlabel("simulation day", color=MUTED, fontsize=8)
    strip.legend(loc="lower left", frameon=False, labelcolor=INK, fontsize=8)

    def update(i):
        day = days[i]
        for b in BRANCHES:
            panels[b].update(at(*data[b], day), scale)
            lines[b].set_data(days[: i + 1], army[b][: i + 1])
        cursor.set_xdata([day, day])
        title.set_text(f"PINELAND  |  day {day:.0f}")
        sub.set_text("Same world and history up to the withdrawal decision; the two panels then diverge."
                     if day <= withdrawal else
                     f"{day - withdrawal:.0f} days after the decision (left: support continued, right: withdrawn)")
        return []

    anim = FuncAnimation(fig, update, frames=len(days), blit=False)
    anim.save(out_dir / f"{stem}.gif", writer=PillowWriter(fps=args.fps), savefig_kwargs={"facecolor": PAPER})
    if shutil.which("ffmpeg"):
        anim.save(out_dir / f"{stem}.mp4", writer=FFMpegWriter(fps=args.fps, bitrate=4000),
                  savefig_kwargs={"facecolor": PAPER})
    plt.close(fig)

    picks = [withdrawal] + [withdrawal + d for d in (90, 180, 360) if withdrawal + d <= t1]
    fig, axes = plt.subplots(2, len(picks), figsize=(4.6 * len(picks), 9.4), facecolor=PAPER)
    axes = np.atleast_2d(axes).reshape(2, len(picks))
    for j, day in enumerate(picks):
        for i, b in enumerate(BRANCHES):
            p = MapPanel(axes[i, j], topo, geo, norm, f"{TITLES[b].title()}, day +{day - withdrawal:.0f}",
                         compact=True)
            p.update(at(*data[b], day), scale)
    fig.savefig(out_dir / f"{stem}_panels.png", dpi=170, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)

    on, off = at(*data["SUPPORT_ON"], t1), at(*data["SUPPORT_OFF"], t1)
    diff = off["net"] - on["net"]
    dl = max(0.02, float(np.quantile(np.abs(diff), 0.92)))
    dnorm = TwoSlopeNorm(vmin=-dl, vcenter=0, vmax=dl)
    fig = plt.figure(figsize=(8.4, 10.4), facecolor=PAPER)
    ax = fig.add_axes([0.02, 0.17, 0.96, 0.78])
    p = MapPanel(ax, topo, geo, dnorm, f"Day {t1:.0f}: what withdrawing support changed")
    p.update({**off, "net": diff}, scale)
    p.stats.set_text("Colour = change in net control caused by the withdrawal\n(withdrawn branch minus continued branch)")
    # absolute state: hatch where insurgents out-control the government at the end (withdrawn branch)
    majority = [cells[i] for i in range(n) if off["ins_control"][i] > off["gov_control"][i]]
    if majority:
        ax.add_collection(PolyCollection(majority, facecolors="none", edgecolors=(0.15, 0.15, 0.15, 0.6),
                                         hatch="////", linewidths=0, zorder=1.2))
    # primary shock sites: localities garrisoned by the army at the withdrawal decision
    garrison = at(*data["SUPPORT_OFF"], withdrawal)["military_personnel"]
    shock = [cells[i] for i in range(n) if garrison[i] >= 15]
    if shock:
        ax.add_collection(PolyCollection(shock, facecolors="none", edgecolors="#111111", linewidths=1.8,
                                         linestyles=(0, (1, 1.6)), zorder=2.6))
    # timeline inset: national control shift caused by the withdrawal
    grid = np.arange(t0, t1 + 1e-9, 2.0)
    mean_net = {b: np.array([at(*data[b], d)["net"].mean() for d in grid]) for b in BRANCHES}
    inset = ax.inset_axes([0.60, 0.80, 0.37, 0.14], facecolor="white")
    inset.plot(grid, 100 * (mean_net["SUPPORT_OFF"] - mean_net["SUPPORT_ON"]), color=INS, lw=1.6)
    inset.axhline(0, color="#999999", lw=0.6)
    inset.axvline(withdrawal, color="#b45309", lw=1, ls="--")
    inset.set_title("national shift (pp)", fontsize=7, color=INK, pad=2)
    inset.tick_params(labelsize=6, colors=MUTED, length=2)
    for side in inset.spines.values():
        side.set_color("#bbbbbb")
    # footer: diverging colour bar, symbol key
    cax = fig.add_axes([0.10, 0.125, 0.30, 0.014])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=dnorm, cmap=CONTROL), cax=cax, orientation="horizontal")
    cb.set_ticks([-dl, 0, dl])
    cb.set_ticklabels([f"-{dl * 100:.0f} pp gov", "0", f"+{dl * 100:.0f} pp insurgent"])
    cb.ax.tick_params(colors=INK, labelsize=7.5, length=0)
    cb.outline.set_visible(False)
    foot = fig.add_axes([0.02, 0.01, 0.96, 0.09])
    legend(foot, "Hatch = insurgent-majority at the end; dotted outline = army garrison at withdrawal. "
                 "Symbols show forces in the withdrawn branch.")
    fig.savefig(out_dir / f"{stem}_divergence.png", dpi=170, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {stem}.gif, {stem}_panels.png, {stem}_divergence.png to {out_dir}")


if __name__ == "__main__":
    main()
