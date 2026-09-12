#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


MODES = ["equal_locality", "per_capita", "threat_weighted", "need_weighted", "marginal_return"]
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
HIGHER = [
    "population_weighted_government_control",
    "mean_government_legitimacy",
    "mean_local_institution_capacity",
]


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ci(x: pd.Series) -> dict:
    a = x.dropna().to_numpy(float)
    if len(a) == 0:
        return {"n": 0, "mean": None, "ci95": None}
    mean = float(a.mean())
    if len(a) == 1:
        return {"n": 1, "mean": mean, "ci95": None}
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return {"n": int(len(a)), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def means(df: pd.DataFrame, tp: str) -> dict:
    d = df[df.timepoint.eq(tp)]
    cols = LOWER + HIGHER + [
        "government_capital_outflow_intervention",
        "political_order_outflow_intervention",
        "public_development_outflow_intervention",
    ]
    return {m: {c: float(d[d["mode"].eq(m)][c].mean()) for c in cols} for m in MODES}


def contrasts(df: pd.DataFrame, tp: str) -> dict:
    d = df[df.timepoint.eq(tp)]
    base = d[d["mode"].eq("equal_locality")].set_index("seed")
    out = {}
    for mode in MODES:
        g = d[d["mode"].eq(mode)].set_index("seed")
        idx = base.index.intersection(g.index)
        b, x = base.loc[idx], g.loc[idx]
        row = {}
        for metric in LOWER:
            row[metric] = ci(b[metric] - x[metric])
        for metric in HIGHER:
            row[metric] = ci(x[metric] - b[metric])
        out[mode] = row
    return out


def pareto(m: dict) -> tuple[list[str], dict[str, list[str]]]:
    def v(mode: str) -> np.ndarray:
        return np.asarray([m[mode][x] for x in LOWER] + [-m[mode][x] for x in HIGHER], float)

    dominated_by = {mode: [] for mode in MODES}
    for b in MODES:
        vb = v(b)
        for a in MODES:
            if a == b:
                continue
            va = v(a)
            scale = np.maximum(np.maximum(abs(va), abs(vb)), 1.0)
            if np.all(va <= vb + 1e-10 * scale) and np.any(va < vb - 1e-10 * scale):
                dominated_by[b].append(a)
    return [m for m in MODES if not dominated_by[m]], dominated_by


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    df = pd.read_csv(a.csv)
    expected = df.seed.nunique() * len(MODES) * 3
    if len(df) != expected:
        raise SystemExit(f"row integrity failed: {len(df)} != {expected}")
    if set(df["mode"]) != set(MODES) or set(df.timepoint) != {"anchor", "intervention_end", "final"}:
        raise SystemExit("mode/timepoint integrity failed")
    end_m, final_m = means(df, "intervention_end"), means(df, "final")
    end_c, final_c = contrasts(df, "intervention_end"), contrasts(df, "final")
    front, dominated_by = pareto(final_m)
    durability = {}
    for mode in MODES[1:]:
        durability[mode] = {}
        for metric in LOWER[:6]:
            e = end_c[mode][metric]["mean"]
            f = final_c[mode][metric]["mean"]
            durability[mode][metric] = {
                "intervention_end_improvement": e,
                "final_improvement": f,
                "retained_fraction": float(f / e) if e is not None and e > 0 and f is not None else None,
                "durable": bool(e is not None and e > 0 and f is not None and f >= 0.5 * e),
            }
    spend = {m: final_m[m]["public_development_outflow_intervention"] for m in MODES}
    result = {
        "schema_version": "pineland.development_allocation_frontier_results.v1",
        "status": "SYNTHETIC_DEVELOPMENT_ALLOCATION_FRONTIER_MEASURED",
        "historical_outcomes_used": False,
        "scope_guard": "Budget-neutral synthetic Pineland allocation comparison; not a real-world aid targeting recommendation.",
        "input": a.csv,
        "input_sha256": sha256(a.csv),
        "seed_count": int(df.seed.nunique()),
        "means_intervention_end": end_m,
        "means_final": final_m,
        "paired_improvement_vs_equal_intervention_end": end_c,
        "paired_improvement_vs_equal_final": final_c,
        "durability": durability,
        "public_development_outflow_by_mode": spend,
        "realized_spend_range_fraction": (
            float((max(spend.values()) - min(spend.values())) / max(np.mean(list(spend.values())), 1e-12))
        ),
        "pareto_final": {
            "nondominated_modes": front,
            "dominated_by": dominated_by,
        },
        "interpretation_guard": "The marginal-return rule is derived from Pineland's own service production law. External validity requires separate historical tests.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "nondominated": front,
        "spend": spend,
        "final_rooted_improvement": {m: final_c[m]["rooted_armed_membership_mass"]["mean"] for m in MODES},
        "final_hazard_improvement": {m: final_c[m]["recruitment_hazard_mass"]["mean"] for m in MODES},
        "final_gov_control_improvement": {m: final_c[m]["population_weighted_government_control"]["mean"] for m in MODES},
    }, indent=2))


if __name__ == "__main__":
    main()
