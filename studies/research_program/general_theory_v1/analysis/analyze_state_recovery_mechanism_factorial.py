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


def safe_gap_closure(final: pd.Series, initial: pd.Series, baseline: pd.Series) -> pd.Series:
    denom = baseline - initial
    out = (final - initial) / denom.where(denom.abs() > 1.0e-12, np.nan)
    return out


def contrast(pivot: pd.DataFrame, left: str, right: str) -> dict:
    d = pivot[left] - pivot[right]
    x = d.dropna().to_numpy(float)
    mean = float(x.mean()) if len(x) else None
    if len(x) > 1:
        se = float(x.std(ddof=1) / np.sqrt(len(x)))
        ci = [mean - 1.96 * se, mean + 1.96 * se]
    else:
        ci = None
    return {"n": int(len(x)), "mean": mean, "ci95": ci}


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    final_time = float(df.time.max())
    end = df[np.isclose(df.time, final_time)].copy()
    end["Q_institution_capacity"] = safe_gap_closure(
        end.institution_capacity,
        end.initial_institution_capacity,
        end.baseline_institution_capacity,
    )
    end["Q_structural_admin"] = safe_gap_closure(
        end.structural_administrative_capacity,
        end.initial_structural_admin,
        end.baseline_structural_admin,
    )
    end["control_delta"] = end.government_effective_control - end.initial_government_effective_control

    cell_summary = []
    for cell, g in end.groupby("cell"):
        cell_summary.append({
            "cell": cell,
            "n": int(len(g)),
            "mean_Q_institution_capacity": float(g.Q_institution_capacity.mean()),
            "mean_Q_structural_admin": float(g.Q_structural_admin.mean()),
            "mean_control_delta": float(g.control_delta.mean()),
            "mean_cumulative_admin_rebuild": float(g.cumulative_admin_rebuild.mean()),
            "mean_security_recruits": float(g.cumulative_security_recruits.mean()),
            "mean_security_deployments": float(g.cumulative_security_deployments.mean()),
            "mean_final_integrity": float(g.institution_integrity.mean()),
        })

    key = ["seed", "focal"]
    pivots = {
        name: end.pivot(index=key, columns="cell", values=name)
        for name in ["Q_institution_capacity", "Q_structural_admin", "control_delta"]
    }
    contrasts = {}
    for metric, p in pivots.items():
        contrasts[metric] = {
            "regeneration_effect_when_political_active_full_minus_political": contrast(p, "full_v2", "political_only"),
            "political_capacity_evolution_effect_when_regeneration_active_full_minus_regeneration_only": contrast(p, "full_v2", "regeneration_only"),
            "regeneration_effect_when_political_frozen_regeneration_minus_neither": contrast(p, "regeneration_only", "neither_capacity_loop"),
        }
        a = (p["full_v2"] - p["political_only"]) - (p["regeneration_only"] - p["neither_capacity_loop"])
        x = a.dropna().to_numpy(float)
        m = float(x.mean()) if len(x) else None
        se = float(x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else None
        contrasts[metric]["interaction"] = {
            "n": int(len(x)),
            "mean": m,
            "ci95": [m - 1.96 * se, m + 1.96 * se] if se is not None else None,
        }

    threshold = 0.02
    q = contrasts["Q_institution_capacity"]
    political_effect = q["political_capacity_evolution_effect_when_regeneration_active_full_minus_regeneration_only"]["mean"]
    regen_frozen_effect = q["regeneration_effect_when_political_frozen_regeneration_minus_neither"]["mean"]
    gates = {
        "political_capacity_evolution_is_material_net_erosion_when_regeneration_active": political_effect is not None and political_effect <= -threshold,
        "explicit_regeneration_is_material_positive_when_political_capacity_frozen": regen_frozen_effect is not None and regen_frozen_effect >= threshold,
    }

    out = {
        "schema_version": "pineland.state_recovery_mechanism_factorial_results.v1",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "final_time_days": final_time,
        "materiality_threshold_abs_Q": threshold,
        "cell_summary": sorted(cell_summary, key=lambda x: x["cell"]),
        "paired_contrasts": contrasts,
        "mechanism_gates": gates,
        "interpretation": (
            "Contrasts isolate the implemented capacity-memory terms while retaining political service spending and control outputs. "
            "They diagnose this synthetic shock support only; interaction means contributions need not add linearly."
        ),
    }
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cells": out["cell_summary"], "institution_Q_contrasts": q, "gates": gates}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
