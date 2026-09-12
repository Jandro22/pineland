#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_time(g: pd.DataFrame, mask: pd.Series) -> float | None:
    x = g.loc[mask, "time"]
    return float(x.iloc[0]) if len(x) else None


def summarize_case(g: pd.DataFrame) -> dict:
    g = g.sort_values("time").copy()
    rooted_zero = g.rooted_armed_membership_mass <= 1.0e-9
    inactive = g.organization_active <= 0
    first_zero = first_time(g, rooted_zero)
    first_inactive = first_time(g, inactive)
    regenerated = False
    max_force_after_zero = None
    if first_zero is not None:
        after = g[g.time > first_zero]
        regenerated = bool((after.rooted_armed_membership_mass > 1.0e-9).any())
        max_force_after_zero = float(after.operational_fielded_force.max()) if len(after) else 0.0
    final = g.iloc[-1]
    return {
        "first_rooted_zero_day": first_zero,
        "first_inactive_day": first_inactive,
        "zero_to_inactive_days": (
            first_inactive - first_zero
            if first_zero is not None and first_inactive is not None and first_inactive >= first_zero
            else None
        ),
        "regenerated_after_zero": regenerated,
        "max_operational_force_after_zero": max_force_after_zero,
        "final_rooted": float(final.rooted_armed_membership_mass),
        "final_force": float(final.operational_fielded_force),
        "final_hazard": float(final.recruitment_hazard_mass),
        "final_active": int(final.organization_active),
        "final_insurgent_control": float(final.population_weighted_insurgent_control),
        "final_ecosystem_rooted": float(final.ecosystem_rooted_membership),
        "final_ecosystem_force": float(final.ecosystem_operational_force),
        "final_ecosystem_hazard": float(final.ecosystem_recruitment_hazard),
        "final_active_insurgent_organizations": int(final.active_insurgent_organizations),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    df = pd.read_csv(ns.csv)
    expected = df.seed.nunique() * 2 * 25
    if len(df) != expected:
        raise SystemExit(f"row integrity failed {len(df)} != {expected}")
    cases = []
    for (seed, variant), g in df.groupby(["seed", "variant"]):
        row = {"seed": int(seed), "variant": variant}
        row.update(summarize_case(g))
        cases.append(row)
    c = pd.DataFrame(cases)
    summaries = {}
    for variant, g in c.groupby("variant"):
        summaries[variant] = {
            "n": int(len(g)),
            "final_active_fraction": float(g.final_active.mean()),
            "final_reproductive_fraction": float(((g.final_rooted > 0) & (g.final_hazard > 0) & (g.final_force > 0)).mean()),
            "median_final_rooted": float(g.final_rooted.median()),
            "median_final_force": float(g.final_force.median()),
            "median_final_hazard": float(g.final_hazard.median()),
            "median_final_insurgent_control": float(g.final_insurgent_control.median()),
            "median_final_ecosystem_rooted": float(g.final_ecosystem_rooted.median()),
            "median_final_ecosystem_force": float(g.final_ecosystem_force.median()),
            "median_final_ecosystem_hazard": float(g.final_ecosystem_hazard.median()),
            "median_final_active_insurgent_organizations": float(g.final_active_insurgent_organizations.median()),
            "rooted_zero_fraction": float(g.first_rooted_zero_day.notna().mean()),
            "regeneration_after_zero_fraction_among_zero": (
                float(g.loc[g.first_rooted_zero_day.notna(), "regenerated_after_zero"].mean())
                if g.first_rooted_zero_day.notna().any() else None
            ),
            "median_zero_to_inactive_days": (
                float(g.zero_to_inactive_days.dropna().median())
                if g.zero_to_inactive_days.notna().any() else None
            ),
            "median_max_operational_force_after_zero": (
                float(g.max_operational_force_after_zero.dropna().median())
                if g.max_operational_force_after_zero.notna().any() else None
            ),
        }

    # Within-seed final contrasts, continuity - legacy.
    wide = c.pivot(index="seed", columns="variant")
    contrasts = {}
    for metric in [
        "final_rooted",
        "final_force",
        "final_hazard",
        "final_active",
        "final_insurgent_control",
        "final_ecosystem_rooted",
        "final_ecosystem_force",
        "final_ecosystem_hazard",
        "final_active_insurgent_organizations",
    ]:
        d = wide[metric]["fielded_continuity"] - wide[metric]["legacy"]
        contrasts[metric] = {
            "mean": float(d.mean()),
            "median": float(d.median()),
            "positive_fraction": float((d > 0).mean()),
        }

    material = (
        abs(contrasts["final_active"]["mean"]) >= 0.25
        or abs(contrasts["final_force"]["mean"]) >= 100.0
        or abs(contrasts["final_rooted"]["mean"]) >= 1000.0
        or abs(contrasts["final_ecosystem_force"]["mean"]) >= 100.0
        or abs(contrasts["final_ecosystem_rooted"]["mean"]) >= 1000.0
    )
    result = {
        "schema_version": "pineland.fielded_continuity_architecture_results.v1",
        "status": (
            "POLICY_SUPPORT_MATERIALLY_SENSITIVE_TO_COLLAPSE_ARCHITECTURE"
            if material else "NO_MATERIAL_SENSITIVITY_DETECTED_ON_TESTED_SUPPORT"
        ),
        "historical_outcomes_used": False,
        "input": ns.csv,
        "input_sha256": sha256(ns.csv),
        "seed_count": int(df.seed.nunique()),
        "variant_summary": summaries,
        "within_seed_final_continuity_minus_legacy": contrasts,
        "case_diagnostics": cases,
        "policy_guard": "If material sensitivity is detected, no single policy frontier is licensed without freezing/reporting the collapse architecture assumption.",
        "interpretation_guard": "Architecture sensitivity only. Persistence under the continuity rule is not evidence that the rule is empirically correct.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "variant_summary": summaries, "contrasts": contrasts}, indent=2))


if __name__ == "__main__":
    main()
