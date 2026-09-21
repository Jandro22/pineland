#!/usr/bin/env python3
"""Generate manuscript figures from tracked Stage-4 compact evidence."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper" / "partner_force_autonomy"
FIGURES = PAPER / "figures"
EVIDENCE = (
    ROOT
    / "studies"
    / "research_program"
    / "general_theory_v1"
    / "partner_force_autonomy"
    / "evidence"
    / "stage4"
)

STRUCTURE_LABELS = {
    "balanced_capacity": "Balanced",
    "command_constrained": "Command constrained",
    "forcegen_constrained": "Force generation constrained",
    "logistics_constrained": "Logistics constrained",
}


def save(fig: plt.Figure, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURES / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def figure1_conceptual() -> None:
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.axis("off")
    boxes = [
        (0.04, "External service\nor development"),
        (0.23, "Relief of current\nbinding constraint"),
        (0.42, "Supported operating\nenvelope changes"),
        (0.61, "Indigenous supply and\nservice demand co-evolve"),
        (0.80, "Binding constraint\nmay migrate"),
    ]
    for x, label in boxes:
        ax.text(
            x,
            0.58,
            label,
            ha="center",
            va="center",
            fontsize=10,
            bbox={"boxstyle": "round,pad=0.45", "fc": "white", "ec": "black"},
            transform=ax.transAxes,
        )
    for i in range(len(boxes) - 1):
        ax.annotate(
            "",
            xy=(boxes[i + 1][0] - 0.075, 0.58),
            xytext=(boxes[i][0] + 0.075, 0.58),
            xycoords=ax.transAxes,
            arrowprops={"arrowstyle": "->", "lw": 1.2},
        )
    ax.text(
        0.5,
        0.17,
        "Long-run autonomy depends on indigenous coverage at the constraint that binds the adapted system",
        ha="center",
        va="center",
        fontsize=11,
        fontweight="bold",
        transform=ax.transAxes,
    )
    ax.annotate(
        "",
        xy=(0.5, 0.29),
        xytext=(0.80, 0.45),
        xycoords=ax.transAxes,
        arrowprops={"arrowstyle": "->", "lw": 1.0},
    )
    ax.set_title("Moving-bottleneck mechanism", fontsize=14, pad=10)
    save(fig, "figure1_conceptual")


def figure2_phase_map(phase: pd.DataFrame) -> None:
    treated = phase[phase["factor_support_intensity"] > 0].copy()
    structures = list(STRUCTURE_LABELS)
    intensities = sorted(treated["factor_support_intensity"].unique())

    v = np.nanmax(np.abs(treated["mean_delta_q_feasible_h360"]))
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5), constrained_layout=True)
    for ax, structure in zip(axes.flat, structures, strict=True):
        d = treated[treated["factor_structure"] == structure]
        capacities = sorted(d["factor_capacity_level"].unique())
        grid = (
            d.pivot(
                index="factor_capacity_level",
                columns="factor_support_intensity",
                values="mean_delta_q_feasible_h360",
            )
            .reindex(index=capacities, columns=intensities)
            .to_numpy()
        )
        image = ax.imshow(
            grid,
            origin="lower",
            aspect="auto",
            cmap="RdBu_r",
            vmin=-v,
            vmax=v,
        )
        ax.set_title(STRUCTURE_LABELS[structure])
        ax.set_xticks(range(len(intensities)), [f"{x:g}" for x in intensities])
        ax.set_yticks(range(len(capacities)), [f"{x:g}" for x in capacities])
        ax.set_xlabel("Direct support intensity")
        ax.set_ylabel("Indigenous capacity level")

        for y, capacity in enumerate(capacities):
            for x, intensity in enumerate(intensities):
                row = d[
                    d["factor_capacity_level"].eq(capacity)
                    & d["factor_support_intensity"].eq(intensity)
                ].iloc[0]
                marker = ""
                if row["robust_phase_regime"] == "robust_effective_autonomy_trap":
                    marker = "T"
                elif row["phase_regime"] == "effective_autonomy_building":
                    marker = "+"
                elif row["phase_regime"] == "not_initially_effective":
                    marker = "x"
                if marker:
                    ax.text(x, y, marker, ha="center", va="center", fontsize=9)

    cbar = fig.colorbar(image, ax=axes, shrink=0.86)
    cbar.set_label("Mean change in capped indigenous autonomy at +360d")
    fig.suptitle("Autonomy effects of continued direct support", fontsize=14)
    fig.text(
        0.5,
        0.01,
        "T = robust autonomy trap; + = descriptive autonomy-building cell; x = not initially effective",
        ha="center",
        fontsize=9,
    )
    save(fig, "figure2_phase_map")


def figure3_intensity_tradeoff(phase: pd.DataFrame) -> None:
    d = (
        phase[phase["factor_support_intensity"] > 0]
        .groupby("factor_support_intensity", as_index=False)
        .agg(
            capability=("mean_delta_capability_h30", "mean"),
            autonomy=("mean_delta_q_feasible_h360", "mean"),
        )
    )

    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.axhline(0, linewidth=0.8, color="black")
    ax.plot(
        d["factor_support_intensity"],
        d["capability"],
        marker="o",
        label="Capability at +30d",
    )
    ax.plot(
        d["factor_support_intensity"],
        d["autonomy"],
        marker="s",
        label="Indigenous autonomy at +360d",
    )
    ax.set_xlabel("Direct support intensity")
    ax.set_ylabel("Mean continued-support minus withdrawal effect")
    ax.set_title("Short-run capability and long-run autonomy diverge")
    ax.legend(frameon=False)
    save(fig, "figure3_intensity_tradeoff")


def figure4_migration(migration: pd.DataFrame) -> None:
    d = migration[
        migration["observed_target_match"].eq(True)
        & migration["factor_support_target"].isin(["command", "forcegen", "logistics"])
    ].copy()
    agg = (
        d.groupby("factor_support_target")
        .apply(
            lambda x: pd.Series(
                {
                    "n": x["n"].sum(),
                    "events": x["persistent_migration_count"].sum(),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    agg["rate"] = agg["events"] / agg["n"]
    order = ["command", "forcegen", "logistics"]
    agg = agg.set_index("factor_support_target").loc[order].reset_index()
    labels = ["Command", "Force generation", "Logistics"]

    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    bars = ax.bar(labels, agg["rate"])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Persistent migration fraction")
    ax.set_title("Bottleneck migration when treatment matches the observed constraint")
    for bar, row in zip(bars, agg.itertuples(), strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(row.rate + 0.035, 1.035),
            f"{int(row.events)}/{int(row.n)}",
            ha="center",
            va="bottom",
        )
    save(fig, "figure4_matched_migration")


def figure5_mode_contrasts(contrasts: pd.DataFrame) -> None:
    d = contrasts[
        contrasts["contrast"].isin(
            ["development_minus_substitution", "hybrid_minus_substitution"]
        )
    ].copy()
    d["label"] = (
        d["factor_target"].str.replace("forcegen", "force generation", regex=False)
        + ", "
        + d["factor_severity"]
        + ", "
        + d["factor_intensity"].map(lambda x: f"{x:g}x")
        + ", "
        + d["contrast"].map(
            {
                "development_minus_substitution": "development",
                "hybrid_minus_substitution": "hybrid",
            }
        )
    )
    target_order = {"logistics": 0, "command": 1, "forcegen": 2}
    contrast_order = {"development_minus_substitution": 0, "hybrid_minus_substitution": 1}
    d["target_order"] = d["factor_target"].map(target_order)
    d["contrast_order"] = d["contrast"].map(contrast_order)
    d = d.sort_values(
        ["target_order", "factor_severity", "factor_intensity", "contrast_order"]
    ).reset_index(drop=True)

    y = np.arange(len(d))
    mean = d["mean_delta_q_feasible_h360"].to_numpy()
    lo = d["delta_q_feasible_h360_boot95_lo"].to_numpy()
    hi = d["delta_q_feasible_h360_boot95_hi"].to_numpy()
    xerr = np.vstack([mean - lo, hi - mean])

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.axvline(0, linewidth=0.8, color="black")
    ax.errorbar(mean, y, xerr=xerr, fmt="o", capsize=2.5)
    ax.set_yticks(y, d["label"])
    ax.invert_yaxis()
    ax.set_xlabel("Change in terminal autonomy relative to substitution")
    ax.set_title("Development and hybrid assistance versus direct substitution")
    save(fig, "figure5_mode_contrasts")


def figure6_local_system_divergence(contrasts: pd.DataFrame) -> None:
    d = contrasts[
        contrasts["contrast"].eq("development_minus_substitution")
        & contrasts["factor_target"].isin(["command", "forcegen", "logistics"])
    ].copy()
    labels = {
        "command": "Command",
        "forcegen": "Force generation",
        "logistics": "Logistics",
    }

    fig, ax = plt.subplots(figsize=(7.6, 5.4))
    ax.axhline(0, linewidth=0.8, color="black")
    for target, group in d.groupby("factor_target"):
        ax.scatter(
            group["mean_relevant_delta_coverage_capped_h360"],
            group["mean_delta_q_feasible_h360"],
            label=labels[target],
            s=55,
        )
    ax.set_xlabel("Indigenous coverage gain in targeted subsystem at +360d")
    ax.set_ylabel("Whole-system terminal autonomy gain at +360d")
    ax.set_title("Local indigenous development is not equivalent to system autonomy")
    ax.legend(frameon=False)
    save(fig, "figure6_local_system_divergence")


def main() -> None:
    phase = pd.read_csv(EVIDENCE / "phase_cell_summary_v1.csv")
    migration = pd.read_csv(EVIDENCE / "migration_target_match_summary_v1.csv")
    contrasts = pd.read_csv(EVIDENCE / "mechanism_mode_contrasts_v1.csv")

    figure1_conceptual()
    figure2_phase_map(phase)
    figure3_intensity_tradeoff(phase)
    figure4_migration(migration)
    figure5_mode_contrasts(contrasts)
    figure6_local_system_divergence(contrasts)
    print(f"wrote figures to {FIGURES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
