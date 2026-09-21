#!/usr/bin/env python3
"""Generate the main-paper figures from tracked evidence.

The review revision deliberately uses a restrained, print-safe grayscale style.
Legacy Phase-Map, migration-bar, local-divergence, and Stage-5 figures remain in
the replication package but are no longer the main article's visual backbone.
"""

from __future__ import annotations

from pathlib import Path

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
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    def box(x: float, y: float, w: float, h: float, text: str, weight: str = "normal") -> None:
        patch = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.015,rounding_size=0.015",
            linewidth=0.9,
            edgecolor="black",
            facecolor="white",
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontweight=weight)

    box(0.03, 0.69, 0.18, 0.15, "Targeted\nassistance")
    box(0.29, 0.69, 0.18, 0.15, "Constraint\nrelief")
    box(0.55, 0.69, 0.18, 0.15, "Whole-force\nyield")
    box(0.79, 0.69, 0.18, 0.15, "Retained\ncapability")
    for x0, x1 in [(0.21, 0.29), (0.47, 0.55), (0.73, 0.79)]:
        ax.annotate("", xy=(x1, 0.765), xytext=(x0, 0.765), arrowprops={"arrowstyle": "->", "lw": 1.0})

    box(0.29, 0.27, 0.29, 0.17, "Constraint displacement\nAnother service becomes binding")
    box(0.64, 0.27, 0.31, 0.17, "Requirement expansion\nDemand outgrows indigenous service")

    ax.annotate("", xy=(0.50, 0.69), xytext=(0.435, 0.44), arrowprops={"arrowstyle": "->", "lw": 0.9})
    ax.annotate("", xy=(0.84, 0.69), xytext=(0.795, 0.44), arrowprops={"arrowstyle": "->", "lw": 0.9})

    ax.text(0.435, 0.20, "Explains relief without yield", ha="center", va="center", fontstyle="italic")
    ax.text(0.795, 0.20, "Explains yield without retention", ha="center", va="center", fontstyle="italic")
    ax.text(
        0.50,
        0.06,
        "Relief, yield, and retention are separate outcomes and require separate measurements.",
        ha="center",
        va="center",
        fontweight="bold",
    )
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

    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(0, color="black", lw=0.8)

    for structure, marker in STRUCTURE_MARKERS.items():
        g = cells[cells["factor_structure"] == structure]
        sizes = 24 + 26 * g["factor_support_intensity"].astype(float)
        ax.scatter(
            g["supported"],
            g["retained"],
            marker=marker,
            s=sizes,
            facecolors="0.75",
            edgecolors="black",
            linewidths=0.55,
            alpha=0.9,
            label=STRUCTURE_LABELS[structure],
        )

    eps = 1e-6
    n_sr = int(((cells.supported > eps) & (cells.retained < -eps)).sum())
    n_bb = int(((cells.supported > eps) & (cells.retained > eps)).sum())
    n_nn = int(((cells.supported < -eps) & (cells.retained < -eps)).sum())
    n_np = int(((cells.supported < -eps) & (cells.retained > eps)).sum())
    neutral = len(cells) - n_sr - n_bb - n_nn - n_np

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax.text(xlim[1] * 0.68, ylim[1] * 0.82, f"Both positive\nn = {n_bb}", ha="center", va="center")
    ax.text(xlim[1] * 0.68, ylim[0] * 0.72, f"Success without retention\nn = {n_sr}", ha="center", va="center", fontweight="bold")
    ax.text(xlim[0] * 0.68, ylim[0] * 0.72, f"Both negative\nn = {n_nn}", ha="center", va="center")
    ax.text(xlim[0] * 0.68, ylim[1] * 0.82, f"Support negative, retained positive\nn = {n_np}", ha="center", va="center")
    ax.text(0.02, 0.02, f"Neutral on at least one contrast: n = {neutral}", transform=ax.transAxes, ha="left", va="bottom", fontsize=8.2)

    ax.set_xlabel("Supported capability effect vs matched no aid at +30 days")
    ax.set_ylabel("Retained capability effect vs matched no aid at +30 days")
    ax.set_title("Supported performance and post-withdrawal retention are distinct")
    ax.legend(frameon=False, loc="upper left")
    save(fig, "figure2_supported_retained")


def figure3_requirement_expansion() -> None:
    d = pd.read_csv(REVIEW / "stage4_demand_standardized_worlds_v1.csv")
    subset = d[(d["observed_effect"] < -1e-6) & (d["delta_cap_h30"] > 1e-6)].copy()

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.8), constrained_layout=True)
    ax = axes[0]
    cols = ["observed_effect", "production_only_effect", "demand_only_effect"]
    labels = ["Observed\ncoverage gap", "Production-only\nstandardization", "Demand-only\nstandardization"]
    data = [subset[c].dropna().to_numpy(float) for c in cols]
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, showfliers=False, widths=0.62)
    for patch in bp["boxes"]:
        patch.set_facecolor("0.85")
        patch.set_edgecolor("black")
    for element in ("whiskers", "caps", "medians"):
        for line in bp[element]:
            line.set_color("black")
    means = [np.mean(x) for x in data]
    ax.scatter(np.arange(1, 4), means, marker="D", s=25, facecolors="black", edgecolors="black", zorder=3, label="Mean")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel("Change in capped logistics coverage")
    ax.set_title("A. Descriptive decomposition")
    ax.legend(frameon=False, loc="lower left")

    ax = axes[1]
    world_file = ABLATION / "mechanism_ablation_worlds_v1.csv"
    result_file = ABLATION / "mechanism_ablation_result_v1.json"
    if world_file.exists() and result_file.exists():
        import json

        w = pd.read_csv(world_file)
        means = (
            w.groupby(["scenario", "mode"], as_index=False)["delta_capability_h30"]
            .mean()
            .pivot(index="scenario", columns="mode", values="delta_capability_h30")
        )
        scenario_order = list(means.index.astype(str))
        x = np.arange(len(scenario_order))
        normal = means.loc[scenario_order, "normal"].to_numpy(float)
        clamp = means.loc[scenario_order, "demand_clamped"].to_numpy(float)
        width = 0.34
        ax.bar(x - width / 2, normal, width, facecolor="0.75", edgecolor="black", label="Normal support")
        ax.bar(x + width / 2, clamp, width, facecolor="white", edgecolor="black", hatch="///", label="Demand clamped")
        ax.set_xticks(x, scenario_order)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_ylabel("Mean +30d composite-capability branch gap")
        ax.set_title("B. Clamp changes capability; coverage gap fails to reproduce")
        ax.legend(frameon=False, loc="best")

        result = json.loads(result_file.read_text(encoding="utf-8"))
        ax.text(
            0.02,
            0.03,
            "Coverage branch gap = 0 in all 48 normal and 48 clamped pairs\n"
            f"at every registered horizon; demand match median error = {100*result['clamp_error_median']:.2f}%\n"
            f"and {100*result['clamp_fraction_within_5pct']:.0f}% of intervals are within 5%.",
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=7.1,
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

    fig, ax = plt.subplots(figsize=(6.8, 4.4))
    styles = {
        "supported": {"label": "Supported effect vs no aid", "marker": "o", "ls": "-"},
        "retained": {"label": "Retained effect vs no aid", "marker": "s", "ls": "--"},
        "gap": {"label": "Dependency gap", "marker": "^", "ls": ":"},
    }
    for variable, style in styles.items():
        g = s[s["variable"] == variable]
        ax.plot(g["h"], g["mean"], color="black", marker=style["marker"], linestyle=style["ls"], label=style["label"])
        ax.fill_between(g["h"].to_numpy(float), g["q25"].to_numpy(float), g["q75"].to_numpy(float), color="0.85", alpha=0.45)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xlabel("Days after the support/withdrawal split")
    ax.set_ylabel("Composite-capability effect")
    ax.set_title("Capability effects change over time and benchmark")
    ax.legend(frameon=False, ncol=1)
    save(fig, "figure4_capability_trajectories")


def figure5_assistance_frontier() -> None:
    d = pd.read_csv(STAGE4 / "mechanism_cell_summary_v1.csv")
    d = d[(d["factor_target"] == "logistics") & d["factor_assistance_mode"].isin(["substitution", "development", "hybrid"])].copy()
    modes = ["substitution", "development", "hybrid"]
    markers = {"substitution": "o", "development": "s", "hybrid": "^"}
    labels = {"substitution": "Substitution", "development": "Development", "hybrid": "Hybrid"}

    costs = d["mean_delta_cum_interval_donor_cost_h360"].to_numpy(float)
    cmin, cmax = costs.min(), costs.max()
    sizes = 38 + 95 * (costs - cmin) / max(cmax - cmin, 1.0)
    d["plot_size"] = sizes

    fig, ax = plt.subplots(figsize=(6.7, 5.0))
    for mode in modes:
        g = d[d["factor_assistance_mode"] == mode]
        ax.scatter(
            g["mean_delta_composite_capability_h30"],
            g["mean_delta_q_feasible_h360"],
            s=g["plot_size"],
            marker=markers[mode],
            facecolors="0.78" if mode != "development" else "white",
            edgecolors="black",
            linewidths=0.7,
            label=labels[mode],
        )
        for row in g.itertuples():
            ax.annotate(
                f"{row.factor_severity[0].upper()}{row.factor_intensity:g}",
                (row.mean_delta_composite_capability_h30, row.mean_delta_q_feasible_h360),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=7.2,
            )
    ax.axhline(0, color="black", lw=0.8)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Mean +30d composite-capability branch effect")
    ax.set_ylabel("Mean +360d indigenous-coverage branch effect")
    ax.set_title("Logistics assistance lies on a capability-retention-cost frontier")
    ax.legend(frameon=False, loc="lower right")
    ax.text(0.02, 0.02, "Marker area scales with modeled cumulative donor cost\nLabels: M/S = moderate/severe weakness; number = intensity", transform=ax.transAxes, fontsize=7.8, va="bottom")
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
