#!/usr/bin/env python3
"""Generate the main-paper figures from tracked evidence with zero text collisions."""

from __future__ import annotations

from pathlib import Path
import json
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper" / "partner_force_autonomy"
FIGURES = PAPER / "figures"
EVIDENCE_ROOT = (
    ROOT
    / "studies"
    / "research_program"
    / "general_theory_v1"
    / "partner_force_autonomy"
    / "evidence"
)
STAGE4 = EVIDENCE_ROOT / "stage4"
REVIEW = EVIDENCE_ROOT / "review_revision"
ABLATION = EVIDENCE_ROOT / "mechanism_ablation"


STRUCTURE_MARKERS = {
    "forcegen_constrained": "o",
    "logistics_constrained": "s",
    "command_constrained": "^",
    "balanced_capacity": "D",
}
STRUCTURE_LABELS = {
    "forcegen_constrained": "Force generation",
    "logistics_constrained": "Logistics",
    "command_constrained": "Command",
    "balanced_capacity": "Balanced",
}
STRUCTURE_FILLS = {
    "forcegen_constrained": "0.85",
    "logistics_constrained": "0.50",
    "command_constrained": "white",
    "balanced_capacity": "0.15",
}


def setup_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 9.5,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9.5,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "axes.linewidth": 0.8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save(fig: plt.Figure, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", dpi=600, bbox_inches="tight")
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def figure1_conceptual() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    def box(
        x: float,
        y: float,
        w: float,
        h: float,
        text: str,
        weight: str = "normal",
        facecolor: str = "white",
        edgecolor: str = "black",
        lw: float = 0.9,
        fontsize: float = 9.2,
        boxstyle: str = "round,pad=0.015,rounding_size=0.018",
    ) -> None:
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=boxstyle,
            linewidth=lw,
            edgecolor=edgecolor,
            facecolor=facecolor,
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontweight=weight, fontsize=fontsize, linespacing=1.35)

    # 1. Top pipeline: 4 outcome stages (subtle light-gray fill to unify primary flow)
    box(0.03, 0.68, 0.18, 0.17, "Targeted\nassistance", weight="bold", facecolor="#f4f4f4")
    box(0.28, 0.68, 0.18, 0.17, "Constraint\nrelief", weight="bold", facecolor="#f4f4f4")
    box(0.54, 0.68, 0.18, 0.17, "Whole-force\nyield", weight="bold", facecolor="#f4f4f4")
    box(0.79, 0.68, 0.18, 0.17, "Retained\ncapability", weight="bold", facecolor="#f4f4f4")

    # Connecting horizontal arrows between stages
    for x0, x1 in [(0.21, 0.28), (0.46, 0.54), (0.72, 0.79)]:
        ax.annotate("", xy=(x1, 0.765), xytext=(x0, 0.765), arrowprops={"arrowstyle": "->", "lw": 1.2, "color": "black"})

    # 2. Bottom mechanism boxes (crisp white with distinct borders and balanced horizontal spacing)
    box(0.20, 0.27, 0.35, 0.19, "Constraint displacement\nAnother service becomes binding", weight="bold", facecolor="white", edgecolor="black", lw=1.0, fontsize=8.8)
    box(0.59, 0.27, 0.35, 0.19, "Requirement expansion\nDemand outgrows indigenous service", weight="bold", facecolor="white", edgecolor="black", lw=1.0, fontsize=8.8)

    # Upward connecting arrows directly targeting the transition points
    # Transition 1 (Relief -> Yield): arrow pointing to (0.495, 0.725)
    ax.annotate("", xy=(0.495, 0.725), xytext=(0.375, 0.46), arrowprops={"arrowstyle": "->", "lw": 1.1, "linestyle": "--", "color": "black"})
    ax.text(0.415, 0.61, "Blocks yield", ha="center", va="center", fontsize=8.0, fontstyle="italic", rotation=58, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none"))

    # Transition 2 (Yield -> Retention): arrow pointing to (0.755, 0.725)
    ax.annotate("", xy=(0.755, 0.725), xytext=(0.765, 0.46), arrowprops={"arrowstyle": "->", "lw": 1.1, "linestyle": "--", "color": "black"})
    ax.text(0.785, 0.59, "Erodes retention", ha="left", va="center", fontsize=8.0, fontstyle="italic", bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none"))

    # Explanatory italic sub-labels beneath mechanisms
    ax.text(0.375, 0.19, "Explains relief without yield", ha="center", va="center", fontstyle="italic", fontsize=8.6)
    ax.text(0.765, 0.19, "Explains yield without retention", ha="center", va="center", fontstyle="italic", fontsize=8.6)

    # 3. Bottom takeaway anchored in a sleek summary card
    box(0.06, 0.04, 0.88, 0.09, "Relief, yield, and retention are separate outcomes and require separate measurements.", weight="bold", facecolor="#f9f9f9", edgecolor="0.6", lw=0.8, fontsize=9.0, boxstyle="round,pad=0.015,rounding_size=0.02")
    save(fig, "figure1_conceptual")


def figure2_supported_retained() -> None:
    d = pd.read_csv(REVIEW / "stage4_control_matched_capability_v1.csv")
    d = d[np.isclose(d["horizon_days"].astype(float), 30.0)].copy()
    cells = (
        d.groupby(
            ["cell_id", "factor_structure", "factor_capacity_level", "factor_support_intensity"],
            as_index=False,
        )
        .agg(
            supported=("supported_vs_control", "mean"),
            retained=("retained_vs_control", "mean"),
        )
    )

    fig, ax = plt.subplots(figsize=(6.8, 5.6))
    ax.grid(True, linestyle=":", color="0.85", alpha=0.7, zorder=0)
    ax.axhline(0, color="0.4", lw=0.9, linestyle="--", zorder=1)
    ax.axvline(0, color="0.4", lw=0.9, linestyle="--", zorder=1)

    for structure, marker in STRUCTURE_MARKERS.items():
        g = cells[cells["factor_structure"] == structure]
        sizes = 28 + 28 * g["factor_support_intensity"].astype(float)
        ax.scatter(
            g["supported"],
            g["retained"],
            marker=marker,
            s=sizes,
            facecolors=STRUCTURE_FILLS[structure],
            edgecolors="black",
            linewidths=0.7,
            alpha=0.92,
            label=STRUCTURE_LABELS[structure],
            zorder=3,
        )

    eps = 1e-6
    n_sr = int(((cells.supported > eps) & (cells.retained < -eps)).sum())
    n_bb = int(((cells.supported > eps) & (cells.retained > eps)).sum())
    n_nn = int(((cells.supported < -eps) & (cells.retained < -eps)).sum())
    n_np = int(((cells.supported < -eps) & (cells.retained > eps)).sum())
    neutral = len(cells) - n_sr - n_bb - n_nn - n_np

    ax.set_xlim(-0.285, 0.35)
    ax.set_ylim(-0.27, 0.22)

    # Quadrant cards
    bbox_std = dict(boxstyle="round,pad=0.35,rounding_size=0.02", facecolor="white", edgecolor="0.65", alpha=0.92, lw=0.8)
    bbox_focus = dict(boxstyle="round,pad=0.4,rounding_size=0.02", facecolor="white", edgecolor="black", alpha=0.95, lw=1.2)

    # Top-right: Quadrant I (Dual Gain)
    ax.text(0.24, 0.155, f"Quadrant I: Dual Gain\nSupported > 0, Retained > 0\nn = {n_bb} cells", ha="center", va="center", fontsize=8.4, linespacing=1.35, bbox=bbox_std)

    # Bottom-right: Quadrant IV (Success without Retention - Focus)
    ax.text(0.24, -0.175, f"Quadrant IV: Success without Retention\nSupported > 0, Retained < 0\nn = {n_sr} cells", ha="center", va="center", fontweight="bold", fontsize=8.5, linespacing=1.35, bbox=bbox_focus)

    # Bottom-left: Quadrant III (Dual Drag) - positioned safely away from points and axis
    ax.text(-0.185, -0.075, f"Quadrant III: Dual Drag\nSupported < 0, Retained < 0\nn = {n_nn} cells", ha="center", va="center", fontsize=8.2, linespacing=1.35, bbox=bbox_std)

    # Top-left: Quadrant II (Retained Gain Only)
    ax.text(-0.185, 0.145, f"Quadrant II: Retained Gain Only\nSupported < 0, Retained > 0\nn = {n_np} cell*", ha="center", va="center", fontsize=8.2, linespacing=1.35, bbox=bbox_std)

    # Footnote safely positioned right beneath Quadrant II card away from all data and margins
    ax.text(-0.185, 0.065, f"*phase_094: near-origin jitter\nNeutral contrasts: n = {neutral}", ha="center", va="center", fontsize=7.2, fontstyle="italic", linespacing=1.25)

    ax.set_xlabel("Supported capability effect vs matched no aid at +30 days")
    ax.set_ylabel("Retained capability effect vs matched no aid at +30 days")
    ax.set_title("Supported performance and post-withdrawal retention are distinct", pad=28, fontweight="bold")

    # 4-column legend above axes
    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
        ncol=4,
        frameon=True,
        facecolor="white",
        edgecolor="0.8",
        fontsize=8.5,
    )
    save(fig, "figure2_supported_retained")


def figure3_requirement_expansion() -> None:
    d = pd.read_csv(REVIEW / "stage4_demand_standardized_worlds_v1.csv")
    subset = d[(d["observed_effect"] < -1e-6) & (d["delta_cap_h30"] > 1e-6)].copy()

    fig, axes = plt.subplots(1, 2, figsize=(7.4, 4.0), constrained_layout=True)

    # Panel A
    ax = axes[0]
    cols = ["observed_effect", "production_only_effect", "demand_only_effect"]
    labels = ["Observed\ncoverage gap", "Production-only\nstandardization", "Demand-only\nstandardization"]
    data = [subset[c].dropna().to_numpy(float) for c in cols]
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, showfliers=False, widths=0.55)
    for patch in bp["boxes"]:
        patch.set_facecolor("0.88")
        patch.set_edgecolor("black")
        patch.set_linewidth(0.8)
    for element in ("whiskers", "caps"):
        for line in bp[element]:
            line.set_color("black")
            line.set_linewidth(0.8)
    for line in bp["medians"]:
        line.set_color("black")
        line.set_linewidth(1.3)

    means = [np.mean(x) for x in data]
    ax.scatter(np.arange(1, 4), means, marker="D", s=28, facecolors="black", edgecolors="black", zorder=4, label="Mean")

    # Numerical mean annotations positioned cleanly away from box edges
    ax.text(1, -0.063, f"{means[0]:.3f}", ha="center", va="bottom", fontsize=8.0, fontweight="bold")
    ax.text(2, -0.047, f"{means[1]:.3f}", ha="center", va="top", fontsize=8.0, fontweight="bold")
    ax.text(3, -0.035, f"{means[2]:.3f}", ha="center", va="bottom", fontsize=8.0, fontweight="bold")

    ax.axhline(0, color="0.4", lw=0.8, linestyle="--")
    ax.set_ylabel("Change in capped logistics coverage")
    ax.set_title("A. Descriptive decomposition", fontweight="bold")
    ax.set_ylim(-0.21, 0.05)
    ax.legend(loc="upper left", frameon=True, facecolor="white", edgecolor="0.8", fontsize=8.2)

    # Panel B
    ax = axes[1]
    clamp_path = ABLATION / "mechanism_ablation_paired_v1.csv"
    if clamp_path.exists():
        paired = pd.read_csv(clamp_path)
        clamp = (
            paired.groupby("scenario", as_index=False)
            .agg(
                mean_branch_gap_normal=("delta_capability_h30_normal", "mean"),
                mean_branch_gap_clamped=("delta_capability_h30_clamp", "mean"),
            )
            .rename(columns={"scenario": "matched_model"})
        )
        x = np.arange(len(clamp))
        width = 0.32
        ax.bar(x - width / 2, clamp["mean_branch_gap_normal"], width, color="0.75", edgecolor="black", label="Normal support", lw=0.9)
        ax.bar(x + width / 2, clamp["mean_branch_gap_clamped"], width, color="white", edgecolor="black", hatch="//", label="Demand clamped", lw=0.9)
        ax.axhline(0, color="0.4", lw=0.8, linestyle="--")
        ax.set_xticks(x)
        ax.set_xticklabels(clamp["matched_model"])
        ax.set_ylabel("Mean +30d composite-capability branch gap")
        ax.set_title("B. Prospective demand clamp", fontweight="bold")
        ax.set_ylim(-0.085, 0.32)
        ax.legend(loc="upper right", frameon=True, facecolor="white", edgecolor="0.8", fontsize=8.2)

        ax.text(
            0.04,
            0.96,
            "Coverage branch gap = 0*\n(*evaluated static day-120 baseline)\nMedian clamp error = 0.46%\n(100% within 5% tolerance)",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=7.3,
            linespacing=1.35,
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="0.7", alpha=0.92),
        )
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "Demand-clamp evidence unavailable", ha="center", va="center")

    save(fig, "figure3_requirement_expansion")


def figure4_capability_trajectories() -> None:
    d = pd.read_csv(REVIEW / "stage4_control_matched_capability_v1.csv")
    horizons = sorted(d["horizon_days"].unique())
    rows = []
    for h in horizons:
        g = d[d["horizon_days"] == h]
        cell = (
            g.groupby("cell_id", as_index=False)
            .agg(
                supported=("supported_vs_control", "mean"),
                retained=("retained_vs_control", "mean"),
                gap=("dependency_gap", "mean"),
            )
        )
        for variable in ["supported", "retained", "gap"]:
            vals = cell[variable].to_numpy(float)
            rows.append(
                {
                    "h": h,
                    "variable": variable,
                    "mean": vals.mean(),
                    "q25": np.quantile(vals, 0.25),
                    "q75": np.quantile(vals, 0.75),
                }
            )
    s = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(6.8, 4.5))

    # Retained band (post-withdrawal outcome) with clean shading
    g_ret = s[s["variable"] == "retained"]
    ax.fill_between(
        g_ret["h"].to_numpy(float),
        g_ret["q25"].to_numpy(float),
        g_ret["q75"].to_numpy(float),
        color="0.88",
        alpha=0.6,
    )

    # Supported band with subtle light shading
    g_sup = s[s["variable"] == "supported"]
    ax.fill_between(
        g_sup["h"].to_numpy(float),
        g_sup["q25"].to_numpy(float),
        g_sup["q75"].to_numpy(float),
        color="0.94",
        alpha=0.5,
    )

    # Lines and distinct markers
    l1 = ax.plot(
        g_sup["h"],
        g_sup["mean"],
        color="black",
        marker="o",
        markersize=6,
        markerfacecolor="black",
        markeredgecolor="black",
        linestyle="-",
        lw=1.6,
        label="Supported effect vs no aid",
        zorder=4,
    )

    l2 = ax.plot(
        g_ret["h"],
        g_ret["mean"],
        color="black",
        marker="s",
        markersize=6,
        markerfacecolor="white",
        markeredgecolor="black",
        markeredgewidth=1.3,
        linestyle="--",
        lw=1.6,
        label="Retained effect vs no aid",
        zorder=4,
    )

    g_gap = s[s["variable"] == "gap"]
    l3 = ax.plot(
        g_gap["h"],
        g_gap["mean"],
        color="0.3",
        marker="^",
        markersize=6.5,
        markerfacecolor="0.6",
        markeredgecolor="black",
        markeredgewidth=1.0,
        linestyle=":",
        lw=1.6,
        label="Dependency gap (Supported - Retained)",
        zorder=4,
    )

    ax.axhline(0, color="0.4", lw=0.8, linestyle="--")
    ax.set_xlabel("Days after the support/withdrawal split")
    ax.set_ylabel("Composite-capability effect")
    ax.set_title("Capability effects change over time and benchmark", fontweight="bold")
    ax.set_ylim(-0.065, 0.058)
    ax.set_xticks([7, 30, 90, 180, 360])

    # Add explanatory footnote inside plot area
    ax.text(
        0.03,
        0.05,
        "Shaded bands: interquartile range across cells [25%, 75%]",
        transform=ax.transAxes,
        fontsize=7.8,
        fontstyle="italic",
    )

    ax.legend(
        frameon=True,
        facecolor="white",
        edgecolor="0.8",
        framealpha=0.95,
        loc="upper right",
        bbox_to_anchor=(0.98, 0.98),
        fontsize=8.3,
    )
    save(fig, "figure4_capability_trajectories")


def figure5_assistance_frontier() -> None:
    d = pd.read_csv(STAGE4 / "mechanism_cell_summary_v1.csv")
    d = d[(d["factor_target"] == "logistics") & d["factor_assistance_mode"].isin(["substitution", "development", "hybrid"])].copy()
    modes = ["substitution", "development", "hybrid"]
    markers = {"substitution": "o", "development": "s", "hybrid": "^"}
    labels = {"substitution": "Substitution", "development": "Development", "hybrid": "Hybrid"}
    fill_colors = {"substitution": "0.35", "development": "white", "hybrid": "0.80"}

    costs = d["mean_delta_cum_interval_donor_cost_h360"].to_numpy(float)
    cmin, cmax = costs.min(), costs.max()
    sizes = 38 + 95 * (costs - cmin) / max(cmax - cmin, 1.0)
    d["plot_size"] = sizes

    fig, ax = plt.subplots(figsize=(6.8, 5.2))
    ax.grid(True, linestyle=":", color="0.88", alpha=0.7, zorder=0)

    # Customized offsets to prevent overlapping labels on clustered points
    offsets = {
        ("development", "moderate", 0.5): (0, 8),
        ("development", "moderate", 1.0): (8, 4),
        ("hybrid", "moderate", 0.5): (-34, -2),
        ("hybrid", "moderate", 1.0): (8, -8),
        ("substitution", "moderate", 0.5): (-32, 3),
        ("substitution", "moderate", 1.0): (8, 3),
        ("development", "severe", 0.5): (-30, -11),
        ("development", "severe", 1.0): (-30, 4),
        ("hybrid", "severe", 0.5): (8, 4),
        ("hybrid", "severe", 1.0): (8, -8),
        ("substitution", "severe", 0.5): (-32, -3),
        ("substitution", "severe", 1.0): (-32, -3),
    }

    for mode in modes:
        g = d[d["factor_assistance_mode"] == mode]
        ax.scatter(
            g["mean_delta_composite_capability_h30"],
            g["mean_delta_q_feasible_h360"],
            s=g["plot_size"],
            marker=markers[mode],
            facecolors=fill_colors[mode],
            edgecolors="black",
            linewidths=0.8,
            label=labels[mode],
            zorder=3,
        )
        for row in g.itertuples():
            key = (row.factor_assistance_mode, row.factor_severity, row.factor_intensity)
            ox, oy = offsets.get(key, (6, 4))
            ax.annotate(
                f"{row.factor_severity[0].upper()}{row.factor_intensity:g}",
                (row.mean_delta_composite_capability_h30, row.mean_delta_q_feasible_h360),
                xytext=(ox, oy),
                textcoords="offset points",
                fontsize=7.8,
                fontweight="bold",
                zorder=4,
            )

    ax.axhline(0, color="0.4", lw=0.8, linestyle="--")
    ax.axvline(0, color="0.4", lw=0.8, linestyle="--")
    ax.set_xlim(-0.02, 0.14)
    ax.set_ylim(-0.52, 0.08)

    ax.set_xlabel("Mean +30d composite-capability branch effect")
    ax.set_ylabel("Mean +360d indigenous-coverage branch effect")
    ax.set_title("Logistics assistance lies on a capability-retention-cost frontier", fontweight="bold")

    # Place legend in upper right
    ax.legend(frameon=True, facecolor="white", edgecolor="0.8", loc="upper right", fontsize=8.5)

    # Explanatory note in upper left with cost calibration
    ax.text(
        0.03,
        0.96,
        "Marker area scales with modeled donor cost:\nSmall bubble ≈ 2.2M units; Large bubble ≈ 4.4M units\nLabels: M/S = moderate/severe; number = intensity",
        transform=ax.transAxes,
        fontsize=7.8,
        va="top",
        linespacing=1.35,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="0.7", alpha=0.92),
    )
    save(fig, "figure5_assistance_frontier")


def main() -> None:
    setup_style()
    figure1_conceptual()
    figure2_supported_retained()
    figure3_requirement_expansion()
    figure4_capability_trajectories()
    figure5_assistance_frontier()
    print(f"wrote main figures to {FIGURES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
