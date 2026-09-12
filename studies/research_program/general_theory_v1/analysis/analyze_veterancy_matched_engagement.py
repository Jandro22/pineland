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


def paired_ratio(d: pd.DataFrame, fixed_ins: float, low: float = 0.1, high: float = 0.9) -> dict:
    lo = d[(d.government_experience.eq(low)) & d.insurgent_experience.eq(fixed_ins)].set_index(["world_seed", "replicate"])
    hi = d[(d.government_experience.eq(high)) & d.insurgent_experience.eq(fixed_ins)].set_index(["world_seed", "replicate"])
    idx = lo.index.intersection(hi.index)
    lo, hi = lo.loc[idx], hi.loc[idx]
    return {
        "n": int(len(idx)),
        "own_loss_multiplier_high_over_low": float((hi.government_loss_fraction / lo.government_loss_fraction.clip(lower=1e-12)).median()),
        "opponent_loss_multiplier_high_over_low": float((hi.insurgent_loss_fraction / lo.insurgent_loss_fraction.clip(lower=1e-12)).median()),
        "exchange_ratio_multiplier_high_over_low": float((hi.exchange_ratio_insurgent_over_government / lo.exchange_ratio_insurgent_over_government.clip(lower=1e-12)).median()),
        "government_win_probability_low": float(lo.government_wins_loss_exchange.astype(bool).mean()),
        "government_win_probability_high": float(hi.government_wins_loss_exchange.astype(bool).mean()),
    }


def insurgent_paired_ratio(d: pd.DataFrame, fixed_gov: float, low: float = 0.1, high: float = 0.9) -> dict:
    lo = d[(d.insurgent_experience.eq(low)) & d.government_experience.eq(fixed_gov)].set_index(["world_seed", "replicate"])
    hi = d[(d.insurgent_experience.eq(high)) & d.government_experience.eq(fixed_gov)].set_index(["world_seed", "replicate"])
    idx = lo.index.intersection(hi.index)
    lo, hi = lo.loc[idx], hi.loc[idx]
    # From the insurgent perspective own loss is insurgent loss and opponent loss is government loss.
    low_exchange = lo.government_loss_fraction / lo.insurgent_loss_fraction.clip(lower=1e-12)
    high_exchange = hi.government_loss_fraction / hi.insurgent_loss_fraction.clip(lower=1e-12)
    return {
        "n": int(len(idx)),
        "own_loss_multiplier_high_over_low": float((hi.insurgent_loss_fraction / lo.insurgent_loss_fraction.clip(lower=1e-12)).median()),
        "opponent_loss_multiplier_high_over_low": float((hi.government_loss_fraction / lo.government_loss_fraction.clip(lower=1e-12)).median()),
        "exchange_ratio_multiplier_high_over_low": float((high_exchange / low_exchange.clip(lower=1e-12)).median()),
        "insurgent_win_probability_low": float((lo.insurgent_loss_fraction < lo.government_loss_fraction).mean()),
        "insurgent_win_probability_high": float((hi.insurgent_loss_fraction < hi.government_loss_fraction).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = pd.read_csv(a.csv)
    cells = (
        d.groupby(["government_experience", "insurgent_experience"])
        .agg(
            mean_government_loss_fraction=("government_loss_fraction", "mean"),
            mean_insurgent_loss_fraction=("insurgent_loss_fraction", "mean"),
            mean_exchange_ratio=("exchange_ratio_insurgent_over_government", "mean"),
            government_win_probability=("government_wins_loss_exchange", "mean"),
            government_survival_probability=("government_operational_survival", "mean"),
            insurgent_survival_probability=("insurgent_operational_survival", "mean"),
        )
        .reset_index()
    )
    gov = paired_ratio(d, 0.5)
    ins = insurgent_paired_ratio(d, 0.5)
    analytic = {
        "own_loss_multiplier": float(1.5 ** -0.45),
        "opponent_loss_multiplier": float(1.5 ** 0.45),
        "exchange_ratio_multiplier": float(1.5 ** 0.9),
    }
    gates = {
        "government_direction": bool(gov["own_loss_multiplier_high_over_low"] < 1 and gov["opponent_loss_multiplier_high_over_low"] > 1 and gov["exchange_ratio_multiplier_high_over_low"] > 1),
        "insurgent_direction": bool(ins["own_loss_multiplier_high_over_low"] < 1 and ins["opponent_loss_multiplier_high_over_low"] > 1 and ins["exchange_ratio_multiplier_high_over_low"] > 1),
        "government_matches_analytic_within_2pct": bool(
            abs(gov["exchange_ratio_multiplier_high_over_low"] / analytic["exchange_ratio_multiplier"] - 1) <= 0.02
        ),
        "insurgent_matches_analytic_within_2pct": bool(
            abs(ins["exchange_ratio_multiplier_high_over_low"] / analytic["exchange_ratio_multiplier"] - 1) <= 0.02
        ),
    }
    status = "VETERANCY_SURVIVAL_EXCHANGE_CONFIRMED" if all(gates.values()) else "VETERANCY_DIRECTION_CONFIRMED_EFFECT_MODIFIED_BY_CAPS_OR_CONTEXT"
    result = {
        "schema_version": "pineland.veterancy_matched_engagement_results.v1",
        "status": status,
        "historical_outcomes_used": False,
        "input": a.csv,
        "input_sha256": sha256(a.csv),
        "world_count": int(d.world_seed.nunique()),
        "replicates_per_world": int(d.replicate.nunique()),
        "cell_summary": cells.to_dict("records"),
        "government_0.1_to_0.9_at_insurgent_0.5": gov,
        "insurgent_0.1_to_0.9_at_government_0.5": ins,
        "analytic_prediction": analytic,
        "gates": gates,
        "guard": "Synthetic matched-contact result only; no empirical casualty or force-ratio estimate.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "government": gov, "insurgent": ins, "gates": gates}, indent=2))


if __name__ == "__main__":
    main()
