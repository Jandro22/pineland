"""Reveal and score the preregistered Afghanistan 2005 prospective holdout.

Do not run until all 12 frozen-core trajectory files exist.  The scorer fits all
competitors on 2004 only, never updates from a 2005 outcome, and evaluates the
gate exactly as declared in prospective_2005_one_year_gate.json.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

PANEL = ROOT / "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv"
GATE = ROOT / "studies/research_program/afghanistan_performance/prospective_2005_one_year_gate.json"


def _clip(p: float) -> float:
    return min(1.0 - 1e-9, max(1e-9, p))


def _losses(rows: list[dict], probabilities: dict[tuple[str, int], float]) -> dict[str, float]:
    brier = 0.0
    log_score = 0.0
    for row in rows:
        key = (row["province_id"], int(row["week_index"]))
        y = int(row["taliban_state_active"])
        p = _clip(probabilities[key])
        brier += (y - p) ** 2
        log_score += y * math.log(p) + (1 - y) * math.log(1 - p)
    n = max(1, len(rows))
    return {"brier": brier / n, "log_score": log_score / n}


def _fit_competitors(training: list[dict], forecast: list[dict]) -> dict[str, dict[tuple[str, int], float]]:
    positives = sum(int(row["taliban_state_active"]) for row in training)
    global_p = (positives + 1) / (len(training) + 2)

    def grouped(field: str, prior_rows: float) -> dict[str, float]:
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in training:
            counts[row[field]][0] += int(row["taliban_state_active"])
            counts[row[field]][1] += 1
        return {
            key: (positive + prior_rows * global_p) / (total + prior_rows)
            for key, (positive, total) in counts.items()
        }

    province_p = grouped("province_id", 52.0)
    region_p = grouped("region_id", 104.0)
    active_history: dict[str, list[int]] = defaultdict(list)
    for row in training:
        if int(row["taliban_state_active"]):
            active_history[row["province_id"]].append(int(row["week_index"]))

    result = {name: {} for name in (
        "global_rate", "province_empirical_bayes", "region_empirical_bayes",
        "training_history_self_exciting",
    )}
    alpha, decay = 0.18, 0.20
    for row in forecast:
        key = (row["province_id"], int(row["week_index"]))
        base = province_p.get(row["province_id"], global_p)
        excitation = sum(
            math.exp(-decay * (key[1] - prior_week))
            for prior_week in active_history[row["province_id"]]
            if prior_week < key[1]
        )
        result["global_rate"][key] = global_p
        result["province_empirical_bayes"][key] = base
        result["region_empirical_bayes"][key] = region_p.get(row["region_id"], global_p)
        result["training_history_self_exciting"][key] = 1.0 - math.exp(
            -(-math.log(1.0 - base) + alpha * excitation)
        )
    return result


def _ensemble_probability(runs: list[dict], keys: set[tuple[str, int]], field: str) -> dict[tuple[str, int], float]:
    member_sets = [
        {(row["province_id"], int(row["week_index"])) for row in run[field]}
        for run in runs
    ]
    n = len(member_sets)
    return {
        key: (sum(key in cells for cells in member_sets) + 0.5) / (n + 1.0)
        for key in keys
    }


def _province_losses(rows: list[dict], probabilities: dict[tuple[str, int], float]) -> dict[str, tuple[float, float, int]]:
    buckets: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        key = (row["province_id"], int(row["week_index"]))
        buckets[row["province_id"]].append((int(row["taliban_state_active"]), _clip(probabilities[key])))
    result = {}
    for province, values in buckets.items():
        brier = sum((y - p) ** 2 for y, p in values) / len(values)
        log_score = sum(y * math.log(p) + (1 - y) * math.log(1 - p) for y, p in values) / len(values)
        result[province] = (brier, log_score, len(values))
    return result


def _bootstrap_improvement(
    rows: list[dict], pineland: dict[tuple[str, int], float], competitor: dict[tuple[str, int], float],
    *, reps: int = 5000, seed: int = 20050505,
) -> dict[str, float]:
    p = _province_losses(rows, pineland)
    c = _province_losses(rows, competitor)
    provinces = sorted(p)
    rng = random.Random(seed)
    brier_wins = 0
    log_wins = 0
    brier_deltas = []
    log_deltas = []
    for _ in range(reps):
        sampled = [rng.choice(provinces) for _ in provinces]
        # Equal province-cluster weighting is deliberate: each province is the
        # resampling unit and every province has the same 52 forecast weeks.
        pin_brier = sum(p[x][0] for x in sampled) / len(sampled)
        cmp_brier = sum(c[x][0] for x in sampled) / len(sampled)
        pin_log = sum(p[x][1] for x in sampled) / len(sampled)
        cmp_log = sum(c[x][1] for x in sampled) / len(sampled)
        brier_delta = cmp_brier - pin_brier  # positive = Pineland improves
        log_delta = pin_log - cmp_log        # positive = Pineland improves
        brier_deltas.append(brier_delta)
        log_deltas.append(log_delta)
        brier_wins += brier_delta > 0
        log_wins += log_delta > 0
    brier_deltas.sort()
    log_deltas.sort()
    lo = int(0.025 * reps)
    hi = min(reps - 1, int(0.975 * reps))
    return {
        "brier_improvement_probability": brier_wins / reps,
        "log_score_improvement_probability": log_wins / reps,
        "brier_improvement_ci95_low": brier_deltas[lo],
        "brier_improvement_ci95_high": brier_deltas[hi],
        "log_score_improvement_ci95_low": log_deltas[lo],
        "log_score_improvement_ci95_high": log_deltas[hi],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    expected_strengths = {float(x) for x in gate["ensemble"]["taliban_initial_strengths"]}
    expected_seeds = {int(x) for x in gate["ensemble"]["stochastic_seeds"]}
    files = sorted(args.runs_dir.glob("*.json"))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    expected_pairs = {(strength, seed) for strength in expected_strengths for seed in expected_seeds}
    actual_pairs = {(float(run["taliban_initial_strength"]), int(run["seed"])) for run in runs}
    if actual_pairs != expected_pairs or len(runs) != len(expected_pairs):
        raise SystemExit(f"incomplete or duplicate ensemble: expected={len(expected_pairs)} actual={len(runs)}")
    frozen = gate["frozen_core"]
    for run in runs:
        if run["model_sha256"] != frozen["model_sha256"]:
            raise SystemExit("model hash mismatch in prospective ensemble")
        if run["tracked_diff_sha256"] != frozen["tracked_diff_sha256"]:
            raise SystemExit("tracked diff mismatch in prospective ensemble")
        if not run["initialization_gate"]["passed"]:
            raise SystemExit("structural initialization failure in prospective ensemble")

    # Outcome reveal begins here, only after completeness/provenance checks.
    with PANEL.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    training = [row for row in all_rows if row["week_start"].startswith("2004-")]
    forecast = [row for row in all_rows if row["week_start"].startswith("2005-")]
    forecast.sort(key=lambda row: (int(row["week_index"]), row["province_id"]))
    keys = {(row["province_id"], int(row["week_index"])) for row in forecast}
    competitors = _fit_competitors(training, forecast)
    pineland = _ensemble_probability(runs, keys, "latent_active_cells_2005")
    recorded = _ensemble_probability(runs, keys, "recorded_active_cells_2005")

    scores = {"pineland_latent_ensemble": _losses(forecast, pineland)}
    scores["pineland_recorded_diagnostic"] = _losses(forecast, recorded)
    for name, probabilities in competitors.items():
        scores[name] = _losses(forecast, probabilities)

    competitor_names = list(competitors)
    best_brier = min(competitor_names, key=lambda name: scores[name]["brier"])
    best_log = max(competitor_names, key=lambda name: scores[name]["log_score"])
    proper_score_pass = (
        scores["pineland_latent_ensemble"]["brier"] < scores[best_brier]["brier"]
        and scores["pineland_latent_ensemble"]["log_score"] > scores[best_log]["log_score"]
    )
    bootstrap_brier = _bootstrap_improvement(forecast, pineland, competitors[best_brier])
    bootstrap_log = (
        bootstrap_brier if best_log == best_brier
        else _bootstrap_improvement(forecast, pineland, competitors[best_log])
    )
    bootstrap_pass = (
        bootstrap_brier["brier_improvement_probability"] >= 0.95
        and bootstrap_log["log_score_improvement_probability"] >= 0.95
    )

    global_scores = scores["global_rate"]
    strength_rows = {}
    strength_passes = []
    for strength in sorted(expected_strengths):
        stratum = [run for run in runs if float(run["taliban_initial_strength"]) == strength]
        probs = _ensemble_probability(stratum, keys, "latent_active_cells_2005")
        result = _losses(forecast, probs)
        brier_delta = result["brier"] - global_scores["brier"]
        log_delta = result["log_score"] - global_scores["log_score"]
        passes = (
            (result["brier"] < global_scores["brier"] or result["log_score"] > global_scores["log_score"])
            and brier_delta <= 0.002
            and log_delta >= -0.01
        )
        strength_rows[str(int(strength))] = {
            **result,
            "brier_minus_global": brier_delta,
            "log_score_minus_global": log_delta,
            "passed": passes,
        }
        strength_passes.append(passes)

    residual_pass = all(
        abs(float(run["stock_ledger_residual"])) <= 1e-5
        and abs(float(run["supply_conservation_residual"])) <= 1e-5
        for run in runs
    )
    checks = {
        "complete_ensemble": True,
        "frozen_core_identity": True,
        "structural_gates": True,
        "ledger_residuals": residual_pass,
        "proper_scores_beat_best_competitors": proper_score_pass,
        "province_cluster_bootstrap": bootstrap_pass,
        "all_strength_strata_robust": all(strength_passes),
        "no_post_reveal_model_changes": True,
    }
    passed = all(checks.values())
    observed_rate = sum(int(row["taliban_state_active"]) for row in forecast) / len(forecast)
    report = {
        "schema_version": "1.0",
        "passed": passed,
        "prospective_holdout": "2005",
        "rows": len(forecast),
        "observed_active_rate": observed_rate,
        "checks": checks,
        "scores": scores,
        "best_competitor_by_brier": best_brier,
        "best_competitor_by_log_score": best_log,
        "bootstrap_vs_best_brier": bootstrap_brier,
        "bootstrap_vs_best_log": bootstrap_log,
        "strength_robustness": strength_rows,
        "run_runtime_seconds": {
            f"{int(run['taliban_initial_strength'])}:{run['seed']}": run["runtime_seconds"]
            for run in runs
        },
        "interpretation": (
            "Prospective one-year gate passed under frozen mechanisms and predeclared scoring."
            if passed else
            "Prospective one-year gate failed; preserve this result and do not tune on 2005."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
