#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


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
    "final_ring2_transportable_strength": 0.75,
    "final_ring2_rooted_mass": 0.75,
    "final_ring2_recruitment_hazard": 0.75,
}

CANDIDATE_EXTRA = {
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
    "rootedstock_execnet_ring2_18v6": [
        "final_Mstar",
        "final_executable_net_transport_pressure",
        "final_neighbor_transportable_strength",
        "final_neighbor_rooted_mass",
        "final_neighbor_recruitment_hazard",
        "final_ring2_transportable_strength",
        "final_ring2_rooted_mass",
        "final_ring2_recruitment_hazard",
    ],
    "rootedstock_execnet_ring1_localflow17v7": [
        "final_Mstar",
        "final_executable_net_transport_pressure",
        "final_neighbor_transportable_strength",
        "final_neighbor_rooted_mass",
        "final_neighbor_recruitment_hazard",
        "final_net_transport_pressure",
        "final_recruitment_hazard",
    ],
    "rootedstock_execnet_ring1_rawnet16v7": [
        "final_Mstar",
        "final_executable_net_transport_pressure",
        "final_neighbor_transportable_strength",
        "final_neighbor_rooted_mass",
        "final_neighbor_recruitment_hazard",
        "final_net_transport_pressure",
    ],
    "rootedstock_execnet_ring1_hazard16v7": [
        "final_Mstar",
        "final_executable_net_transport_pressure",
        "final_neighbor_transportable_strength",
        "final_neighbor_rooted_mass",
        "final_neighbor_recruitment_hazard",
        "final_recruitment_hazard",
    ],
}

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


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wdist(a: np.ndarray, b: np.ndarray) -> float:
    # Branch counts are equal by design. Sorting gives the empirical 1-Wasserstein
    # distance exactly for equally weighted one-dimensional samples.
    return float(np.mean(np.abs(np.sort(a) - np.sort(b))))


def q(values: np.ndarray, p: float) -> float:
    return float(np.quantile(values, p, method="linear"))


def bootstrap_binary(a: np.ndarray, b: np.ndarray, indices: np.ndarray) -> tuple[float, float, float]:
    observed = abs(float(a.mean() - b.mean()))
    boot = np.abs(a[indices].mean(axis=1) - b[indices].mean(axis=1))
    return observed, q(boot, 0.05), q(boot, 0.95)


def bootstrap_continuous(
    a: np.ndarray,
    b: np.ndarray,
    indices: np.ndarray,
    scale: float,
) -> dict:
    observed_mean = abs(float((a - b).mean())) / scale
    observed_w = wdist(a, b) / scale
    mean_boot = np.abs((a[indices] - b[indices]).mean(axis=1)) / scale
    # Wasserstein requires sorting each resampled empirical distribution.
    a_boot = np.sort(a[indices], axis=1)
    b_boot = np.sort(b[indices], axis=1)
    w_boot = np.mean(np.abs(a_boot - b_boot), axis=1) / scale
    return {
        "observed_standardized_absolute_mean_difference": observed_mean,
        "standardized_absolute_mean_difference_lower95": q(mean_boot, 0.05),
        "standardized_absolute_mean_difference_upper95": q(mean_boot, 0.95),
        "observed_normalized_wasserstein": observed_w,
        "normalized_wasserstein_lower95": q(w_boot, 0.05),
        "normalized_wasserstein_upper95": q(w_boot, 0.95),
    }


def analyze(csv_path: str, out_path: str, draws: int, seed: int, max_match_distance: float) -> None:
    source = Path(csv_path)
    df = pd.read_csv(source)
    required = {
        "pair_id",
        "candidate",
        "branch",
        "side",
        "left_seed",
        "right_seed",
        "locality",
        "stratum",
        "match_distance",
        "viable",
        "pre_org_active",
        "pre_logKo",
        "pre_Mstar",
        "pre_active_owner_logF",
        "final_active_owner_logF",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"missing required columns: {missing}")
    candidates = df.candidate.astype(str).unique().tolist()
    if len(candidates) != 1:
        raise SystemExit(f"expected one candidate, found {candidates}")
    candidate = candidates[0]
    continuous = BASE_CONTINUOUS + CANDIDATE_EXTRA.get(candidate, [])
    for outcome in continuous:
        if outcome not in df.columns:
            raise SystemExit(f"missing outcome {outcome}")

    # Correct the fielded-force future coordinate before any audit.
    work = df.copy()
    work["final_logF"] = work["final_active_owner_logF"].astype(float)
    pair_results = []
    tests = []
    for pair_id, g in work.groupby("pair_id", sort=True):
        left = g[g.side.astype(str).eq("L")].sort_values("branch")
        right = g[g.side.astype(str).eq("R")].sort_values("branch")
        if len(left) != len(right) or len(left) == 0:
            raise SystemExit(f"pair {pair_id}: unbalanced branches")
        if not np.array_equal(left.branch.to_numpy(), right.branch.to_numpy()):
            raise SystemExit(f"pair {pair_id}: branch identities do not align")
        n = len(left)
        # Bootstrap common random numbers must be tied to immutable pair
        # provenance, not candidate-local pair ordinals or iteration order.
        # Otherwise the same state pair selected by two candidates can receive
        # different resamples and therefore different borderline equivalence
        # classifications even though its continuation outcomes are identical.
        first = g.iloc[0]
        provenance = (
            f"{seed}:{int(first.left_seed)}:{int(first.right_seed)}:"
            f"{int(first.locality)}"
        ).encode("utf-8")
        pair_seed = int.from_bytes(hashlib.sha256(provenance).digest()[:8], "little")
        pair_rng = np.random.default_rng(pair_seed)
        indices = pair_rng.integers(0, n, size=(draws, n))
        pair_tests = []

        a = left.viable.to_numpy(float)
        b = right.viable.to_numpy(float)
        observed, lower, upper = bootstrap_binary(a, b, indices)
        binary = {
            "pair_id": int(pair_id),
            "outcome": "viable",
            "kind": "binary",
            "observed_absolute_risk_difference": observed,
            "absolute_risk_difference_lower95": lower,
            "absolute_risk_difference_upper95": upper,
            "margin": 0.15,
            "equivalent": upper <= 0.15,
            "demonstrably_non_equivalent": lower > 0.15,
        }
        pair_tests.append(binary)
        tests.append(binary)

        for outcome in continuous:
            a = left[outcome].to_numpy(float)
            b = right[outcome].to_numpy(float)
            pooled = float(np.std(np.concatenate([a, b]), ddof=1)) if len(a) + len(b) > 2 else 0.0
            scale = max(pooled, DOMAIN_SCALE_FLOOR[outcome])
            metrics = bootstrap_continuous(a, b, indices, scale)
            equivalent = (
                metrics["standardized_absolute_mean_difference_upper95"] <= 0.25
                and metrics["normalized_wasserstein_upper95"] <= 0.25
            )
            non_equivalent = (
                metrics["standardized_absolute_mean_difference_lower95"] > 0.25
                or metrics["normalized_wasserstein_lower95"] > 0.25
            )
            row = {
                "pair_id": int(pair_id),
                "outcome": outcome,
                "kind": "continuous",
                "scale": scale,
                "margin": 0.25,
                **metrics,
                "equivalent": bool(equivalent),
                "demonstrably_non_equivalent": bool(non_equivalent),
            }
            pair_tests.append(row)
            tests.append(row)

        all_equiv = all(t["equivalent"] for t in pair_tests)
        any_non = any(t["demonstrably_non_equivalent"] for t in pair_tests)
        classification = "equivalent" if all_equiv else ("demonstrably_non_equivalent" if any_non else "inconclusive")
        pair_results.append(
            {
                "pair_id": int(pair_id),
                "stratum": str(first.stratum),
                "match_distance": float(first.match_distance),
                "classification": classification,
                "non_equivalent_outcomes": [
                    t["outcome"] for t in pair_tests if t["demonstrably_non_equivalent"]
                ],
                "inconclusive_outcomes": [
                    t["outcome"]
                    for t in pair_tests
                    if not t["equivalent"] and not t["demonstrably_non_equivalent"]
                ],
            }
        )

    pair_df = pd.DataFrame(pair_results)
    eq_fraction = float((pair_df.classification == "equivalent").mean())
    non_fraction = float((pair_df.classification == "demonstrably_non_equivalent").mean())
    strata = {}
    for stratum, g in pair_df.groupby("stratum", sort=True):
        strata[str(stratum)] = {
            "pair_count": int(len(g)),
            "equivalent_pair_fraction": float((g.classification == "equivalent").mean()),
            "demonstrably_non_equivalent_pair_fraction": float((g.classification == "demonstrably_non_equivalent").mean()),
            "inconclusive_pair_fraction": float((g.classification == "inconclusive").mean()),
        }

    anchor_live = (
        (work.pre_org_active.astype(int) == 1)
        & (work.pre_logKo.astype(float) > 1.0e-12)
        & (work.pre_Mstar.astype(float) > 1.0e-12)
        & (work.pre_active_owner_logF.astype(float) > 1.0e-12)
    )
    actual_max_distance = float(work[["pair_id", "match_distance"]].drop_duplicates().match_distance.max())
    old_support = set(strata) >= {"low", "mid", "high"} and all(v["pair_count"] >= 6 for v in strata.values())
    passed = (
        bool(anchor_live.all())
        and old_support
        and actual_max_distance <= max_match_distance
        and eq_fraction >= 0.90
        and non_fraction <= 0.10
        and all(v["equivalent_pair_fraction"] >= 0.80 for v in strata.values())
    )
    escalation_allowed = (
        not passed
        and non_fraction == 0.0
        and float((pair_df.classification == "inconclusive").mean()) > 0.10
    )
    result = {
        "schema_version": "pineland.distributional_closure_equivalence_results.v1",
        "status": "PASS" if passed else "FAIL",
        "historical_outcomes_used": False,
        "input": str(source),
        "input_sha256": sha256(source),
        "candidate": candidate,
        "branches_per_pair": int(work.branch.nunique()),
        "bootstrap_replicates": draws,
        "bootstrap_seed": seed,
        "summary": {
            "pair_count": int(len(pair_df)),
            "equivalent_pair_fraction": eq_fraction,
            "demonstrably_non_equivalent_pair_fraction": non_fraction,
            "inconclusive_pair_fraction": float((pair_df.classification == "inconclusive").mean()),
            "maximum_match_distance": actual_max_distance,
            "all_selected_anchor_rows_live": bool(anchor_live.all()),
            "strata": strata,
        },
        "sequential_precision": {
            "128_branch_expansion_allowed": bool(escalation_allowed),
            "rule": "Allowed only when no pair is demonstrably non-equivalent and failure is driven by inconclusive equivalence classifications.",
        },
        "pairs": pair_results,
        "tests": tests,
        "interpretation_guard": "Direct equivalence audit. A FAIL cannot be converted to closure by citing non-significant legacy difference tests.",
    }
    Path(out_path).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["summary"], "sequential_precision": result["sequential_precision"]}, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--draws", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=2026137991)
    ap.add_argument("--max-match-distance", type=float, default=1.25)
    ns = ap.parse_args()
    analyze(ns.csv, ns.out, ns.draws, ns.seed, ns.max_match_distance)
