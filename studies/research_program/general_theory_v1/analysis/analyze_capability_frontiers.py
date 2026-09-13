#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


LOWER = [
    "rooted_armed_membership_mass",
    "fielded_force_personnel",
    "foothold_strength_sum",
    "recruitment_hazard_mass",
    "population_weighted_insurgent_control",
    "cumulative_insurgent_actions_since_anchor",
    "government_military_losses_since_anchor",
    "population_loss_since_anchor",
    "displaced_population_fraction",
]
HIGHER = ["population_weighted_government_control", "mean_military_readiness", "mean_military_supply_fraction"]


def lower_metrics(df: pd.DataFrame) -> list[str]:
    metrics = list(LOWER)
    if "cumulative_recruitment_since_anchor" in df.columns:
        # Keep recruitment beside the other insurgent regenerative outcomes
        # without breaking archived force/air CSVs generated before this
        # measurement-only column was added.
        metrics.insert(6, "cumulative_recruitment_since_anchor")
    return metrics


def sha256(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ci(x: pd.Series) -> dict:
    a = x.dropna().to_numpy(float)
    if not len(a):
        return {"n": 0, "mean": None, "ci95": None}
    m = float(a.mean())
    if len(a) == 1:
        return {"n": 1, "mean": m, "ci95": None}
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return {"n": int(len(a)), "mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se]}


def paired(df: pd.DataFrame, baseline: str, tp: str) -> dict:
    d = df[df.timepoint.eq(tp)]
    b = d[d.profile.eq(baseline)].set_index("seed")
    out = {}
    for profile in sorted(d.profile.unique()):
        g = d[d.profile.eq(profile)].set_index("seed")
        idx = b.index.intersection(g.index)
        bb, gg = b.loc[idx], g.loc[idx]
        row = {}
        for m in lower_metrics(df):
            row[m] = ci(bb[m] - gg[m])
        for m in HIGHER:
            row[m] = ci(gg[m] - bb[m])
        row["incremental_total_outflow"] = ci(
            gg.government_capital_outflow_intervention - bb.government_capital_outflow_intervention
        )
        row["incremental_combat_event_outflow"] = ci(
            gg.combat_event_outflow_intervention - bb.combat_event_outflow_intervention
        )
        out[profile] = row
    return out


def profile_means(df: pd.DataFrame, tp: str) -> dict:
    d = df[df.timepoint.eq(tp)]
    cols = lower_metrics(df) + HIGHER + [
        "contacts_since_anchor",
        "government_capital_outflow_intervention",
        "combat_event_outflow_intervention",
        "government_capital",
    ]
    return {
        p: {c: float(d[d.profile.eq(p)][c].mean()) for c in cols}
        for p in sorted(d.profile.unique())
    }


def pareto(means: dict[str, dict], include_cost: bool, lower: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    profiles = sorted(means)
    def vec(p: str) -> np.ndarray:
        vals = [means[p][m] for m in lower]
        vals += [-means[p][m] for m in HIGHER]
        if include_cost:
            vals += [means[p]["combat_event_outflow_intervention"]]
        return np.asarray(vals, float)
    dominated_by = {p: [] for p in profiles}
    for b in profiles:
        vb = vec(b)
        for a in profiles:
            if a == b:
                continue
            va = vec(a)
            scale = np.maximum(np.maximum(abs(va), abs(vb)), 1.0)
            if np.all(va <= vb + 1e-10 * scale) and np.any(va < vb - 1e-10 * scale):
                dominated_by[b].append(a)
    return [p for p in profiles if not dominated_by[p]], dominated_by


def equipment_analysis(df: pd.DataFrame, out_path: str) -> None:
    baseline = "B0C0"
    end = paired(df, baseline, "intervention_end")
    final = paired(df, baseline, "final")
    means = profile_means(df, "final")
    lower = lower_metrics(df)
    front, dominated_by = pareto(means, include_cost=False, lower=lower)
    exposure = {}
    for p, row in means.items():
        contacts = row["contacts_since_anchor"]
        losses = row["government_military_losses_since_anchor"]
        exposure[p] = {
            "mean_contacts_since_anchor": contacts,
            "mean_government_losses_per_contact": (
                losses / contacts if contacts > 1.0e-12 else None
            ),
            "mean_fielded_insurgent_force_per_contact": (
                row["fielded_force_personnel"] / contacts if contacts > 1.0e-12 else None
            ),
            "mean_military_readiness": row["mean_military_readiness"],
            "mean_military_supply_fraction": row["mean_military_supply_fraction"],
        }
    break_even = {}
    for benefit in ["B0", "B1", "B2", "B3"]:
        cells = [f"{benefit}{c}" for c in ["C0", "C1", "C2", "C3"]]
        break_even[benefit] = {}
        for metric in LOWER[:6]:
            passing = [c for c in cells if final[c][metric]["mean"] is not None and final[c][metric]["mean"] > 0]
            break_even[benefit][metric] = passing[-1] if passing else None
    durability = {}
    for p in sorted(df.profile.unique()):
        if p == baseline:
            continue
        durability[p] = {}
        for m in LOWER[:6]:
            e, f = end[p][m]["mean"], final[p][m]["mean"]
            durability[p][m] = {
                "end_improvement": e,
                "final_improvement": f,
                "retained_fraction": float(f / e) if e is not None and e > 0 and f is not None else None,
                "durable": bool(e is not None and e > 0 and f is not None and f >= .5 * e),
            }
    result = {
        "schema_version": "pineland.force_equipment_break_even_results.v1",
        "status": "SYNTHETIC_FORCE_EQUIPMENT_BREAK_EVEN_MEASURED",
        "historical_outcomes_used": False,
        "input_sha256": sha256(df.attrs["input"]),
        "seed_count": int(df.seed.nunique()),
        "baseline": baseline,
        "paired_intervention_end": end,
        "paired_final": final,
        "break_even_highest_burden_with_positive_mean_improvement": break_even,
        "durability": durability,
        "operational_exposure_diagnostics": exposure,
        "pareto_final": {"nondominated_profiles": front, "dominated_by": dominated_by},
        "guard": "Stylized equipment mechanisms only; no profile is an empirical armored/light unit specification.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "pareto": front, "break_even": break_even}, indent=2))


def air_analysis(df: pd.DataFrame, out_path: str) -> None:
    # All intensity-zero cells are behaviorally identical by construction; use H0.
    baseline = "A0.00_H0.00"
    end = paired(df, baseline, "intervention_end")
    final = paired(df, baseline, "final")
    means = profile_means(df, "final")
    lower = lower_metrics(df)
    front, dominated_by = pareto(means, include_cost=True, lower=lower)
    exposure = {}
    for p, row in means.items():
        contacts = row["contacts_since_anchor"]
        exposure[p] = {
            "mean_contacts_since_anchor": contacts,
            "mean_government_losses_per_contact": (
                row["government_military_losses_since_anchor"] / contacts
                if contacts > 1.0e-12 else None
            ),
            "mean_combat_support_cost_per_contact": (
                row["combat_event_outflow_intervention"] / contacts
                if contacts > 1.0e-12 else None
            ),
        }
    efficiency = {}
    for p in sorted(df.profile.unique()):
        if p.startswith("A0.00_"):
            continue
        cost = final[p]["incremental_combat_event_outflow"]["mean"]
        row = {"incremental_combat_event_outflow": cost, "outcomes": {}}
        for m in lower[:7]:
            improvement = final[p][m]["mean"]
            row["outcomes"][m] = {
                "improvement": improvement,
                "improvement_per_100k_combat_outflow": (
                    float(improvement / cost * 100_000.0)
                    if cost is not None and cost > 1e-12 and improvement is not None
                    else None
                ),
                "improvement_per_1200_combat_outflow": (
                    float(improvement / cost * 1_200.0)
                    if cost is not None and cost > 1e-12 and improvement is not None
                    else None
                ),
            }
        efficiency[p] = row
    diminishing = {}
    for harm in [0.0, .5, 1.0]:
        profiles = [f"A{x:.2f}_H{harm:.2f}" for x in [.0, .25, .5, .75, 1.0]]
        diminishing[f"H{harm:.2f}"] = {}
        for m in lower[:7]:
            vals = [final[p][m]["mean"] for p in profiles]
            increments = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
            diminishing[f"H{harm:.2f}"][m] = {
                "improvements": vals,
                "quarter_step_marginal_improvements": increments,
            }
    result = {
        "schema_version": "pineland.air_support_frontier_results.v1",
        "status": "SYNTHETIC_AIR_SUPPORT_FRONTIER_MEASURED",
        "historical_outcomes_used": False,
        "input_sha256": sha256(df.attrs["input"]),
        "seed_count": int(df.seed.nunique()),
        "baseline": baseline,
        "paired_intervention_end": end,
        "paired_final": final,
        "cost_effectiveness_final": efficiency,
        "diminishing_returns": diminishing,
        "operational_exposure_diagnostics": exposure,
        "pareto_final": {"nondominated_profiles": front, "dominated_by": dominated_by},
        "guard": "Stylized synthetic air-support operator only; not an empirical sortie-effect or operational recommendation.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "pareto": front}, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", choices=["equipment", "air"])
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df = pd.read_csv(a.csv)
    df.attrs["input"] = a.csv
    if set(df.experiment) != {a.experiment}:
        raise SystemExit("experiment integrity failed")
    profiles = 16 if a.experiment == "equipment" else 15
    expected = df.seed.nunique() * profiles * 3
    if len(df) != expected:
        raise SystemExit(f"row integrity failed: {len(df)} != {expected}")
    if a.experiment == "equipment":
        equipment_analysis(df, a.out)
    else:
        air_analysis(df, a.out)


if __name__ == "__main__":
    main()
