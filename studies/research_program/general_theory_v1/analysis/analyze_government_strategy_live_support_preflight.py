#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


GATES = {
    "anchor": 12,
    "intervention_end": 10,
    "final": 8,
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def live_mask(frame: pd.DataFrame) -> pd.Series:
    return (
        (frame["canonical_insurgent_active"].astype(int) == 1)
        & (frame["canonical_insurgent_capital"].astype(float) > 1.0e-12)
        & (frame["rooted_armed_membership_mass"].astype(float) > 1.0e-12)
        & (frame["fielded_force_personnel"].astype(float) > 1.0e-12)
        & (frame["recruitment_hazard_mass"].astype(float) > 1.0e-12)
    )


def analyze(csv_path: str, out_path: str) -> None:
    source = Path(csv_path)
    df = pd.read_csv(source)
    required = {
        "seed",
        "strategy",
        "timepoint",
        "canonical_insurgent_active",
        "canonical_insurgent_capital",
        "rooted_armed_membership_mass",
        "fielded_force_personnel",
        "recruitment_hazard_mass",
        "ecosystem_rooted_membership",
        "ecosystem_operational_force",
        "ecosystem_recruitment_hazard",
        "active_insurgent_organizations",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"missing required preflight columns: {missing}")
    strategies = sorted(df.strategy.astype(str).unique().tolist())
    if strategies != ["baseline"]:
        raise SystemExit(f"preflight must contain baseline only; found {strategies}")

    expected = set(GATES)
    observed = set(df.timepoint.astype(str).unique())
    if observed != expected:
        raise SystemExit(f"expected timepoints {sorted(expected)}; found {sorted(observed)}")

    seed_count = int(df.seed.nunique())
    if len(df) != seed_count * 3:
        raise SystemExit(
            f"expected exactly 3 rows per seed; rows={len(df)} seeds={seed_count}"
        )

    summaries = {}
    gate_status = {}
    for tp, minimum in GATES.items():
        g = df[df.timepoint.astype(str) == tp].copy()
        live = live_mask(g)
        live_n = int(live.sum())
        summaries[tp] = {
            "n": int(len(g)),
            "live_reproductive_n": live_n,
            "live_reproductive_fraction": float(live.mean()),
            "median_canonical_capital": float(g.canonical_insurgent_capital.median()),
            "median_rooted_membership": float(g.rooted_armed_membership_mass.median()),
            "median_active_owner_fielded_force": float(g.fielded_force_personnel.median()),
            "median_recruitment_hazard": float(g.recruitment_hazard_mass.median()),
            "median_ecosystem_rooted_membership": float(g.ecosystem_rooted_membership.median()),
            "median_ecosystem_operational_force": float(g.ecosystem_operational_force.median()),
            "median_ecosystem_recruitment_hazard": float(g.ecosystem_recruitment_hazard.median()),
            "median_active_insurgent_organizations": float(g.active_insurgent_organizations.median()),
            "minimum_live_worlds": minimum,
        }
        gate_status[tp] = live_n >= minimum

    passed = seed_count == 16 and all(gate_status.values())
    result = {
        "schema_version": "pineland.government_strategy_live_support_preflight_results.v2",
        "status": "PASS" if passed else "FAIL",
        "historical_outcomes_used": False,
        "policy_contrasts_used": False,
        "input": str(source),
        "input_sha256": sha256(source),
        "seed_count": seed_count,
        "challenge_recruitment_multiplier": 0.0625,
        "challenge_underground_disruption_multiplier": 1.0,
        "live_reproductive_definition": [
            "canonical insurgent organization active=1",
            "canonical insurgent liquid capital > 0",
            "canonical rooted armed membership > 0",
            "canonical active-owner effective fielded force > 0",
            "canonical recruitment hazard mass > 0",
        ],
        "timepoint_summary": summaries,
        "gates": {
            "exactly_16_preregistered_worlds": seed_count == 16,
            "day60_at_least_12_live": gate_status["anchor"],
            "day240_at_least_10_live": gate_status["intervention_end"],
            "day360_at_least_8_live": gate_status["final"],
        },
        "next_action": (
            "AUTHORIZED_TO_RUN_FIXED_POLICY_MENU_ON_THIS_UNTOUCHED_SEED_BLOCK"
            if passed
            else "BLOCK_POLICY_MENU_AND_PREREGISTER_BASELINE_ONLY_CHALLENGE_EXPANSION"
        ),
        "guard": "Baseline persistence support only. No policy contrast or historical outcome is used in this gate.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "gates": result["gates"], "timepoint_summary": summaries}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
