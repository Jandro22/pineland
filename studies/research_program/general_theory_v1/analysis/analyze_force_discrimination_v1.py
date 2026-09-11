from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    d = pd.read_csv(ns.csv)

    police = d[d.assay == "police"].copy().rename(
        columns={
            "seed_or_case": "seed",
            "focal_or_pair": "focal",
            "initial_prof_or_replicate": "initial_professionalism",
            "staffing_or_quality": "staffing_multiplier",
            "parent_standard_or_initial_experience": "parent_standard",
            "start_membership_or_turnover": "start_membership",
            "time_or_post_experience": "time",
            "professionalism_or_capability": "professionalism",
            "intelligence_or_loss_actor": "intelligence",
            "remaining_membership_or_loss_defender": "remaining_membership",
        }
    )
    police["disrupted"] = police.cumulative_disrupted.astype(float)

    low = police[np.isclose(police.initial_professionalism, 0.1)]
    high = police[np.isclose(police.initial_professionalism, 0.9)]
    matched = high.merge(
        low,
        on=["seed", "focal", "staffing_multiplier", "time"],
        suffixes=("_high", "_low"),
        validate="one_to_one",
    )
    contrasts = []
    for (staffing, time), g in matched.groupby(["staffing_multiplier", "time"]):
        contrasts.append(
            {
                "staffing_multiplier": float(staffing),
                "time": float(time),
                "mean_professionalism_gap": float((g.professionalism_high - g.professionalism_low).mean()),
                "mean_intelligence_gap": float((g.intelligence_high - g.intelligence_low).mean()),
                "mean_disruption_gap": float((g.disrupted_high - g.disrupted_low).mean()),
            }
        )
    cdf = pd.DataFrame(contrasts)
    early = float(cdf[np.isclose(cdf.time, cdf.time.min())].mean_professionalism_gap.abs().mean())
    late = float(cdf[np.isclose(cdf.time, cdf.time.max())].mean_professionalism_gap.abs().mean())
    max_intel = float(cdf.mean_intelligence_gap.abs().max())
    max_disruption = float(cdf.mean_disruption_gap.abs().max())
    police_distinct = bool(max_intel > 1e-12 and max_disruption > 1e-9 and early > 1e-12 and late < early)

    half = police[np.isclose(police.staffing_multiplier, 0.5)]
    full = police[np.isclose(police.staffing_multiplier, 1.0)]
    sm = full.merge(
        half,
        on=["seed", "focal", "initial_professionalism", "time"],
        suffixes=("_full", "_half"),
        validate="one_to_one",
    )
    staffing_contrasts = (
        sm.assign(
            intelligence_gap=lambda x: x.intelligence_full - x.intelligence_half,
            disruption_gap=lambda x: x.disrupted_full - x.disrupted_half,
        )
        .groupby(["initial_professionalism", "time"], as_index=False)
        .agg(
            mean_intelligence_gap=("intelligence_gap", "mean"),
            mean_disruption_gap=("disruption_gap", "mean"),
        )
        .to_dict("records")
    )

    veteran = d[d.assay == "veterancy"].copy().rename(
        columns={
            "seed_or_case": "case_seed",
            "focal_or_pair": "pair",
            "initial_prof_or_replicate": "replicate",
            "staffing_or_quality": "quality",
            "parent_standard_or_initial_experience": "initial_experience",
            "start_membership_or_turnover": "turnover",
            "time_or_post_experience": "post_experience",
            "professionalism_or_capability": "capability_factor",
            "intelligence_or_loss_actor": "loss_actor",
            "remaining_membership_or_loss_defender": "loss_defender",
        }
    )
    numeric = [
        "pair", "replicate", "quality", "initial_experience", "turnover",
        "post_experience", "capability_factor", "loss_actor", "loss_defender",
    ]
    for col in numeric:
        veteran[col] = pd.to_numeric(veteran[col])

    summary = veteran.groupby(["turnover", "pair"], as_index=False).agg(
        quality=("quality", "first"),
        initial_experience=("initial_experience", "first"),
        mean_post_experience=("post_experience", "mean"),
        mean_capability_factor=("capability_factor", "mean"),
        mean_loss_actor=("loss_actor", "mean"),
        mean_loss_defender=("loss_defender", "mean"),
    )
    zero = veteran[np.isclose(veteran.turnover, 0.0)]
    za = zero.pivot(index="replicate", columns="pair", values="loss_actor")
    zd = zero.pivot(index="replicate", columns="pair", values="loss_defender")
    baseline_loss_diff = float(max(
        (za.max(axis=1) - za.min(axis=1)).max(),
        (zd.max(axis=1) - zd.min(axis=1)).max(),
    ))
    base_factor = zero.groupby("pair").capability_factor.mean()
    baseline_factor_spread = float(base_factor.max() - base_factor.min())
    turnover_spreads = []
    for turnover, g in summary.groupby("turnover"):
        turnover_spreads.append({
            "turnover": float(turnover),
            "experience_spread": float(g.mean_post_experience.max() - g.mean_post_experience.min()),
            "capability_factor_spread": float(g.mean_capability_factor.max() - g.mean_capability_factor.min()),
            "actor_loss_spread": float(g.mean_loss_actor.max() - g.mean_loss_actor.min()),
            "defender_loss_spread": float(g.mean_loss_defender.max() - g.mean_loss_defender.min()),
        })
    positive = [x for x in turnover_spreads if x["turnover"] > 0]
    veteran_distinct = bool(
        baseline_factor_spread <= 1e-12
        and baseline_loss_diff <= 1e-12
        and any(x["capability_factor_spread"] > 1e-9 for x in positive)
        and any(max(x["actor_loss_spread"], x["defender_loss_spread"]) > 1e-9 for x in positive)
    )

    result = {
        "schema_version": "pineland.professionalism_veterancy_discrimination_analysis.v1",
        "status": "SYNTHETIC_STRUCTURAL_DISCRIMINATION",
        "historical_outcomes_used": False,
        "input": str(Path(ns.csv)),
        "input_sha256": sha(ns.csv),
        "integrity": {
            "police_rows": int(len(police)),
            "police_seed_count": int(police.seed.nunique()),
            "police_professionalism_levels": sorted(police.initial_professionalism.unique().tolist()),
            "police_staffing_levels": sorted(police.staffing_multiplier.unique().tolist()),
            "veterancy_rows": int(len(veteran)),
            "veterancy_replicates": int(veteran.replicate.nunique()),
            "veterancy_pairs": int(veteran.pair.nunique()),
            "turnover_levels": sorted(veteran.turnover.unique().tolist()),
        },
        "police_professionalism": {
            "distinct_dynamic_state_signature_pass": police_distinct,
            "early_high_minus_low_professionalism_gap": early,
            "late_high_minus_low_professionalism_gap": late,
            "late_to_early_gap_ratio": late / early if early > 0 else None,
            "max_abs_mean_intelligence_gap": max_intel,
            "max_abs_mean_cumulative_disruption_gap": max_disruption,
            "professionalism_contrasts": contrasts,
            "half_to_full_staffing_contrasts": staffing_contrasts,
        },
        "formation_veterancy": {
            "distinct_dynamic_state_signature_pass": veteran_distinct,
            "baseline_common_factor_spread": baseline_factor_spread,
            "baseline_common_rng_max_loss_difference": baseline_loss_diff,
            "turnover_spreads": turnover_spreads,
            "cell_summary": summary.to_dict("records"),
        },
        "joint_conclusion": "BOTH_NEW_STATES_STRUCTURALLY_DISTINCT" if police_distinct and veteran_distinct else "ONE_OR_MORE_NEW_STATES_NOT_YET_DISTINGUISHED",
        "interpretation_guard": "Synthetic structural identification only; no historical or empirical magnitude claim is licensed.",
    }
    Path(ns.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(ns.out)
    print("police_distinct", police_distinct, "max_intel_gap", max_intel, "gap_ratio", result["police_professionalism"]["late_to_early_gap_ratio"])
    print("veterancy_distinct", veteran_distinct, "baseline_loss_diff", baseline_loss_diff)
    print("turnover_spreads", turnover_spreads)


if __name__ == "__main__":
    main()
