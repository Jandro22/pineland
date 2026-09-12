#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scipy.stats import wasserstein_distance
except Exception:  # deterministic quantile fallback
    wasserstein_distance = None


BASE_CONTINUOUS = [
    "log1p_actions_delta",
    "log1p_recruits_delta",
    "final_M",
    "final_logF",
    "final_E",
    "control_delta",
    "final_C",
    "final_state_control",
]

EXTRA_BY_CANDIDATE = {
    "rootedstock11v3": ["final_Mstar"],
    "rootedstock_hazard12v3": ["final_Mstar", "final_recruitment_hazard"],
    "rootedstock_social12v3": ["final_Mstar", "final_social_exposure"],
    "rootedstock_net12v3": ["final_Mstar", "final_net_transport_pressure"],
    "rootedstock_social_net13v3": ["final_Mstar", "final_social_exposure", "final_net_transport_pressure"],
    "rootedstock_hazard_net13v3": ["final_Mstar", "final_recruitment_hazard", "final_net_transport_pressure"],
    "rootedstock_transport_net13v3": ["final_Mstar", "final_inbound_transport_pressure", "final_net_transport_pressure"],
    "rootedstock_delay16v4": [
        "final_Mstar",
        "final_net_transport_pressure",
        "final_pending_incoming_strength",
        "final_pending_incoming_mean_eta_days",
        "final_pending_outgoing_strength",
        "final_pending_outgoing_mean_eta_days",
    ],
    "rootedstock_execnet12v4": ["final_Mstar", "final_executable_net_transport_pressure"],
    "rootedstock_execnet_ring1_15v5": [
        "final_Mstar",
        "final_executable_net_transport_pressure",
        "final_neighbor_transportable_strength",
        "final_neighbor_rooted_mass",
        "final_neighbor_recruitment_hazard",
    ],
}

DOMAIN_SCALE_FLOOR = {
    "log1p_actions_delta": 0.75,
    "log1p_recruits_delta": 0.75,
    "final_M": 0.20,
    "final_logF": 0.50,
    "final_E": 0.20,
    "control_delta": 0.20,
    "final_C": 0.20,
    "final_state_control": 0.20,
    "final_Mstar": 0.75,
    "final_recruitment_hazard": 0.75,
    "final_social_exposure": 0.20,
    "final_inbound_transport_pressure": 0.75,
    "final_net_transport_pressure": 0.75,
    "final_pending_incoming_strength": 0.75,
    "final_pending_incoming_mean_eta_days": 1.0,
    "final_pending_outgoing_strength": 0.75,
    "final_pending_outgoing_mean_eta_days": 1.0,
    "final_executable_inbound_transport_pressure": 0.75,
    "final_executable_net_transport_pressure": 0.75,
    "final_neighbor_transportable_strength": 0.75,
    "final_neighbor_rooted_mass": 0.75,
    "final_neighbor_recruitment_hazard": 0.75,
}


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paired_signflip_p(diff: np.ndarray, rng: np.random.Generator, draws: int = 20000) -> float:
    diff = np.asarray(diff, float)
    if len(diff) == 0:
        return 1.0
    observed = abs(float(diff.mean()))
    if observed <= 1e-15:
        return 1.0
    signs = rng.choice(np.array([-1.0, 1.0]), size=(draws, len(diff)), replace=True)
    null = np.abs((signs * diff[None, :]).mean(axis=1))
    return float((1 + np.sum(null >= observed)) / (draws + 1))


def bh_qvalues(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    q = np.empty(n, float)
    running = 1.0
    for rank0 in range(n - 1, -1, -1):
        idx = order[rank0]
        rank = rank0 + 1
        running = min(running, p[idx] * n / rank)
        q[idx] = min(1.0, running)
    return q.tolist()


def wdist(a: np.ndarray, b: np.ndarray) -> float:
    if wasserstein_distance is not None:
        return float(wasserstein_distance(a, b))
    qs = np.linspace(0.0, 1.0, 1001)
    return float(np.mean(np.abs(np.quantile(a, qs) - np.quantile(b, qs))))


def analyze(csv_path: str, out_path: str) -> None:
    df = pd.read_csv(csv_path)
    candidates = sorted(df.candidate.astype(str).unique())
    if len(candidates) != 1:
        raise SystemExit(f"expected one candidate, got {candidates}")
    candidate = candidates[0]
    continuous = BASE_CONTINUOUS + EXTRA_BY_CANDIDATE.get(candidate, [])
    required = {"pair_id", "branch", "side", "candidate", "match_distance", "viable"} | set(continuous)
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"missing columns: {missing}")
    if set(df.side.unique()) != {"L", "R"}:
        raise SystemExit("each assay must contain L and R sides")

    rng = np.random.default_rng(20260910)
    tests: list[dict] = []
    pair_meta: dict[int, dict] = {}
    for pair_id, g in df.groupby("pair_id", sort=True):
        left = g[g.side == "L"].sort_values("branch")
        right = g[g.side == "R"].sort_values("branch")
        if left.branch.tolist() != right.branch.tolist():
            raise SystemExit(f"branch mismatch in pair {pair_id}")
        meta = {
            "pair_id": int(pair_id),
            "candidate": str(g.candidate.iloc[0]),
            "match_distance": float(g.match_distance.iloc[0]),
            "left_seed": int(g.left_seed.iloc[0]),
            "right_seed": int(g.right_seed.iloc[0]),
            "locality": int(g.locality.iloc[0]),
            "stratum": str(g.stratum.iloc[0]) if "stratum" in g.columns else "unstratified",
        }
        pair_meta[int(pair_id)] = meta

        lv = left.viable.to_numpy(float)
        rv = right.viable.to_numpy(float)
        diff = lv - rv
        rd = abs(float(lv.mean() - rv.mean()))
        tests.append({
            **meta,
            "outcome": "viable",
            "kind": "binary",
            "mean_left": float(lv.mean()),
            "mean_right": float(rv.mean()),
            "absolute_risk_difference": rd,
            "practically_large": bool(rd > 0.15),
            "p_value": paired_signflip_p(diff, rng),
        })

        for outcome in continuous:
            a = left[outcome].to_numpy(float)
            b = right[outcome].to_numpy(float)
            d = a - b
            pooled = float(np.std(np.concatenate([a, b]), ddof=1)) if len(a) + len(b) > 2 else 0.0
            scale = max(pooled, DOMAIN_SCALE_FLOOR[outcome])
            smd = abs(float(d.mean())) / scale
            nw = wdist(a, b) / scale
            tests.append({
                **meta,
                "outcome": outcome,
                "kind": "continuous",
                "mean_left": float(a.mean()),
                "mean_right": float(b.mean()),
                "paired_mean_difference": float(d.mean()),
                "scale": scale,
                "standardized_mean_difference": smd,
                "normalized_wasserstein": nw,
                "practically_large": bool(smd > 0.25 or nw > 0.25),
                "p_value": paired_signflip_p(d, rng),
            })

    qvals = bh_qvalues([float(x["p_value"]) for x in tests])
    for test, q in zip(tests, qvals):
        test["q_value_bh"] = q
        test["significant_and_large"] = bool(q <= 0.05 and test["practically_large"])

    pairs = []
    for pair_id in sorted(pair_meta):
        subset = [x for x in tests if x["pair_id"] == pair_id]
        pairs.append({
            **pair_meta[pair_id],
            "any_practically_large": any(x["practically_large"] for x in subset),
            "any_significant_and_large": any(x["significant_and_large"] for x in subset),
            "large_outcomes": [x["outcome"] for x in subset if x["practically_large"]],
            "significant_large_outcomes": [x["outcome"] for x in subset if x["significant_and_large"]],
        })

    large_rate = float(np.mean([x["any_practically_large"] for x in pairs]))
    sig_large_rate = float(np.mean([x["any_significant_and_large"] for x in pairs]))
    strata = {}
    for stratum in sorted(set(x["stratum"] for x in pairs)):
        sp = [x for x in pairs if x["stratum"] == stratum]
        strata[stratum] = {
            "pair_count": len(sp),
            "raw_practically_large_pair_rate": float(np.mean([x["any_practically_large"] for x in sp])),
            "multiplicity_significant_and_large_pair_rate": float(np.mean([x["any_significant_and_large"] for x in sp])),
        }
    official_stratified = set(strata) >= {"low", "mid", "high"}
    passed = sig_large_rate <= 0.10 and (
        (not official_stratified)
        or all(v["multiplicity_significant_and_large_pair_rate"] <= 0.20 for v in strata.values())
    )
    out = {
        "schema_version": "pineland.distributional_closure_results.v3",
        "status": "PASS" if passed else "FAIL",
        "historical_outcomes_used": False,
        "input": csv_path,
        "input_sha256": sha256(csv_path),
        "candidate": candidate,
        "anchor_days": float(df.anchor_days.iloc[0]),
        "horizon_days": float(df.horizon_days.iloc[0]),
        "pair_count": len(pairs),
        "branches_per_pair": int(df.branch.nunique()),
        "thresholds": {
            "binary_absolute_risk_difference": 0.15,
            "continuous_standardized_mean_difference": 0.25,
            "continuous_normalized_wasserstein": 0.25,
            "bh_q": 0.05,
            "pair_failure_rate": 0.10,
        },
        "summary": {
            "raw_practically_large_pair_rate": large_rate,
            "multiplicity_significant_and_large_pair_rate": sig_large_rate,
            "median_match_distance": float(df[["pair_id", "match_distance"]].drop_duplicates().match_distance.median()),
            "max_match_distance": float(df[["pair_id", "match_distance"]].drop_duplicates().match_distance.max()),
            "strata": strata,
            "official_stratified_design": official_stratified,
        },
        "pairs": pairs,
        "tests": tests,
        "interpretation_guard": "PASS licenses approximate distributional closure only for the tested synthetic initialization family, candidate state (including candidate-specific future coordinates), anchor, horizons, matching quality, and outcomes. It does not establish exact Markov sufficiency or historical validity.",
    }
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": out["status"], **out["summary"], "pairs": len(pairs)}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out)
