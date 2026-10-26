from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

LOW = 0.03125
HIGH = 0.125
ROOT_WEIGHT = 0.75

def summary(values):
    values = list(values)
    m = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"n": len(values), "mean": m, "median": statistics.median(values),
            "se": se, "normal_95": [m - 1.96 * se, m + 1.96 * se],
            "minimum": min(values), "maximum": max(values)}

def pearson(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = sum((x-mx)**2 for x in xs); sy = sum((y-my)**2 for y in ys)
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys)) / math.sqrt(sx*sy) if sx > 0 and sy > 0 else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.csv_path, encoding="utf-8-sig", newline="")))
    seeds = sorted({int(r["seed"]) for r in rows})
    rates = sorted({float(r["recruitment_multiplier"]) for r in rows})
    if len(seeds) != 24 or rates != [LOW, HIGH]:
        raise SystemExit(f"unexpected support seeds={len(seeds)} rates={rates}")
    index = {(int(r["seed"]), float(r["recruitment_multiplier"]), int(r["underground_disruption"]), r["timepoint"]): r for r in rows}
    if len(index) != 24 * 2 * 2 * 3:
        raise SystemExit(f"unexpected row support {len(index)}")

    state_cols = ["rooted_armed_membership_mass","fielded_force_personnel","canonical_insurgent_capital",
                  "canonical_insurgent_active","cumulative_recruitment_mass_since_anchor",
                  "cumulative_underground_disruption_since_anchor"]
    anchor_failures = []
    for seed in seeds:
        ref = index[(seed, LOW, 0, "anchor")]
        for rate in (LOW, HIGH):
            for u in (0,1):
                row = index[(seed, rate, u, "anchor")]
                for col in state_cols:
                    if row[col] != ref[col]:
                        anchor_failures.append([seed,rate,u,col,row[col],ref[col]])
    if anchor_failures:
        raise SystemExit(f"anchor identity failures: {anchor_failures[:3]}")

    def v(seed, rate, u, tp, col):
        return float(index[(seed, rate, u, tp)][col])
    def effect(seed, rate, tp, col):
        return v(seed,rate,1,tp,col) - v(seed,rate,0,tp,col)

    metrics = {}
    for tp in ("intervention_end","final"):
        metrics[tp] = {}
        for col in ("rooted_armed_membership_mass","eligible_recruitment_mass",
                    "cumulative_recruitment_mass_since_anchor","canonical_insurgent_capital",
                    "recruitment_hazard_mass"):
            low = [effect(s,LOW,tp,col) for s in seeds]
            high = [effect(s,HIGH,tp,col) for s in seeds]
            metrics[tp][col] = {"low":summary(low),"high":summary(high),
                                "high_minus_low":summary([h-l for h,l in zip(high,low)])}

    root_logit = {}
    root_hazard = {}
    compatibility = {}
    for rate in (LOW,HIGH):
        root_vals=[]; hazard_vals=[]; comp_vals=[]
        for s in seeds:
            root_vals.append(ROOT_WEIGHT * effect(s,rate,"intervention_end","mean_local_congruence"))
            comp_vals.append(effect(s,rate,"intervention_end","mean_compatibility"))
            h1=v(s,rate,1,"intervention_end","recruitment_hazard_mass")
            h0=v(s,rate,0,"intervention_end","recruitment_hazard_mass")
            n1=v(s,rate,1,"intervention_end","recruitment_hazard_no_rootedness")
            n0=v(s,rate,0,"intervention_end","recruitment_hazard_no_rootedness")
            hazard_vals.append(math.log(h1/h0)-math.log(n1/n0))
        root_logit[rate]=root_vals; root_hazard[rate]=hazard_vals; compatibility[rate]=comp_vals

    root_mechanism = {
        "rootedness_logit_low": summary(root_logit[LOW]),
        "rootedness_logit_high": summary(root_logit[HIGH]),
        "rootedness_logit_high_minus_low": summary([h-l for h,l in zip(root_logit[HIGH],root_logit[LOW])]),
        "rootedness_log_hazard_low": summary(root_hazard[LOW]),
        "rootedness_log_hazard_high": summary(root_hazard[HIGH]),
        "rootedness_log_hazard_high_minus_low": summary([h-l for h,l in zip(root_hazard[HIGH],root_hazard[LOW])]),
        "compatibility_high": summary(compatibility[HIGH]),
    }

    day360_recruit = []
    day360_capital = []
    for rate in (LOW,HIGH):
        for s in seeds:
            day360_recruit.append(effect(s,rate,"final","cumulative_recruitment_mass_since_anchor"))
            day360_capital.append(effect(s,rate,"final","canonical_insurgent_capital"))
    capital_r = pearson(day360_recruit, day360_capital)

    p = {}
    p["R1"] = all(metrics["intervention_end"]["rooted_armed_membership_mass"][k]["normal_95"][1] < 0 for k in ("low","high"))
    p["R2"] = all(metrics["intervention_end"]["eligible_recruitment_mass"][k]["normal_95"][0] > 0 for k in ("low","high"))
    p["R3"] = metrics["intervention_end"]["cumulative_recruitment_mass_since_anchor"]["high_minus_low"]["normal_95"][1] < 0
    p["R4"] = metrics["final"]["cumulative_recruitment_mass_since_anchor"]["high_minus_low"]["normal_95"][1] < 0
    p["R5"] = metrics["final"]["rooted_armed_membership_mass"]["high_minus_low"]["normal_95"][1] < 0
    p["R6"] = metrics["final"]["canonical_insurgent_capital"]["high_minus_low"]["normal_95"][0] > 0
    p["M1"] = root_mechanism["rootedness_logit_high"]["normal_95"][1] < 0
    p["M2"] = root_mechanism["rootedness_log_hazard_high"]["normal_95"][1] < 0
    p["M3"] = root_mechanism["rootedness_log_hazard_high_minus_low"]["normal_95"][1] < 0
    p["M4"] = abs(root_mechanism["rootedness_logit_high"]["mean"]) > 5 * abs(root_mechanism["compatibility_high"]["mean"])
    p["K1"] = capital_r is not None and capital_r <= -0.95
    payload = {
        "schema_version":"pineland.coin_rootedness_feedback_fresh_confirmation_results.v1",
        "status":"fresh_seed_confirmation_complete",
        "historical_outcomes_used":False,
        "integrity":{"passed":True,"seed_count":len(seeds),"anchor_identity_failures":0},
        "prediction_results":p,
        "rate_conditioned_throttling_all_passed":all(p[x] for x in ("R1","R2","R3","R4","R5","R6")),
        "rootedness_feedback_all_passed":all(p[x] for x in ("R1","R2","R3","R4","M1","M2","M3","M4")),
        "capital_replication_passed":p["K1"],
        "metrics":metrics,
        "rootedness_mechanism":root_mechanism,
        "day360_recruitment_vs_capital_pearson":capital_r,
        "guard":"Synthetic Pineland mechanism confirmation only."
    }
    Path(args.out).write_text(json.dumps(payload,indent=2)+"\n",encoding="utf8")
    print(json.dumps({
        "prediction_results":p,
        "rate_conditioned_throttling_all_passed":payload["rate_conditioned_throttling_all_passed"],
        "rootedness_feedback_all_passed":payload["rootedness_feedback_all_passed"],
        "capital_r":capital_r,
        "day240_recruitment_contrast":metrics["intervention_end"]["cumulative_recruitment_mass_since_anchor"]["high_minus_low"],
        "day360_recruitment_contrast":metrics["final"]["cumulative_recruitment_mass_since_anchor"]["high_minus_low"],
        "day360_rooted_contrast":metrics["final"]["rooted_armed_membership_mass"]["high_minus_low"],
        "day360_capital_contrast":metrics["final"]["canonical_insurgent_capital"]["high_minus_low"],
        "rootedness_mechanism":root_mechanism
    },indent=2))

if __name__ == "__main__":
    main()
