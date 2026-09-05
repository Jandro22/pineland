"""Create compact diagnostic figures from frozen benchmark outputs.

The figures are descriptive only: no fitting, smoothing, or holdout data are
used to alter model parameters.  PNGs are written under results/figures and
can be regenerated after any audited rerun.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
OUT = STUDY / "results" / "figures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    hist = json.loads((STUDY / "results" / "historical" / "historical_descriptive_statistics.json").read_text())
    unc = pd.read_csv(STUDY / "results" / "benchmark" / "untuned_contact_uncertainty.csv")
    labels = ["Training", "Temporal", "Geographic", "Joint"]
    splits = ["training", "temporal_validation", "geographic_validation", "strict_joint_holdout"]
    target = [hist["splits"][s]["strata"]["two_sided_state_based"]["event_count"] for s in splits]
    model = [float(unc.loc[unc.split == s, "recorded_contact_count_mean"].iloc[0]) for s in splits]
    fig, ax = plt.subplots(figsize=(8.0, 4.6), constrained_layout=True)
    x = range(len(labels))
    ax.bar([i - 0.19 for i in x], target, width=0.38, label="UCDP two-sided state-based events", color="#405a85")
    ax.bar([i + 0.19 for i in x], model, width=0.38, label="Pineland realized recorded contacts", color="#d95f59")
    ax.set_xticks(list(x), labels)
    ax.set_ylabel("Count")
    ax.set_title("Frozen Nepal benchmark: event incidence")
    ax.legend(frameon=False)
    ax.text(0.99, 0.98, "No realized contacts in any Pineland seed", transform=ax.transAxes,
            ha="right", va="top", fontsize=9, color="#8b1e1e")
    fig.savefig(OUT / "event_incidence_comparison.png", dpi=180)
    plt.close(fig)

    cross = pd.read_csv(STUDY / "results" / "historical" / "insec_ucdp_district_crosscheck.csv")
    fig, ax = plt.subplots(figsize=(6.3, 5.1), constrained_layout=True)
    ax.scatter(cross["victim_total_cumulative"], cross["ucdp_recorded_events_2001_2006"], s=22, alpha=0.75, color="#405a85", edgecolor="none")
    ax.set_xlabel("INSEC cumulative victims (1996–2006)")
    ax.set_ylabel("UCDP recorded events (2001–2006)")
    rho = json.loads((STUDY / "results" / "historical" / "insec_ucdp_crosscheck.json").read_text())["spearman_rank_correlation"]
    ax.set_title(f"District spatial cross-check (Spearman ρ = {rho:.3f})")
    ax.text(0.02, 0.98, "Spatial consistency only; periods and units differ", transform=ax.transAxes,
            ha="left", va="top", fontsize=8.5)
    fig.savefig(OUT / "insec_ucdp_spatial_crosscheck.png", dpi=180)
    plt.close(fig)

    scores = pd.read_csv(STUDY / "results" / "competitors" / "competitor_scores.csv")
    hold = scores[scores.split.isin(["temporal_validation", "geographic_validation", "strict_joint_holdout"])]
    rank = hold.groupby("model")["mean_poisson_log_score"].mean().sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(7.5, 4.4), constrained_layout=True)
    ax.barh(rank.index, rank.values, color="#6b8e5e")
    ax.set_xlabel("Mean Poisson log score (higher is better)")
    ax.set_title("Leakage-controlled held-out statistical comparators")
    ax.axvline(0, color="#555", linewidth=0.7)
    fig.savefig(OUT / "competitor_holdout_scores.png", dpi=180)
    plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
