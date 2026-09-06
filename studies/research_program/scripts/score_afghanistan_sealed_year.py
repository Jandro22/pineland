"""Reveal and score one preregistered Afghanistan sealed-year holdout.

The empirical panel is opened only after the exact ensemble, gate identity,
protocol source, model source, tracked diff, and structural initialization
checks have all passed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.reproducibility import model_sha256, repository_state


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clip(p: float) -> float:
    return min(1.0 - 1e-9, max(1e-9, p))


def _losses(
    rows: list[dict],
    probabilities: dict[tuple[str, int], float],
    target_column: str,
) -> dict[str, float]:
    brier = 0.0
    log_score = 0.0
    for row in rows:
        key = (row["province_id"], int(row["week_index"]))
        y = int(row[target_column])
        p = _clip(probabilities[key])
        brier += (y - p) ** 2
        log_score += y * math.log(p) + (1 - y) * math.log(1 - p)
    n = max(1, len(rows))
    return {"brier": brier / n, "log_score": log_score / n}


def _fit_competitors(
    training: list[dict],
    forecast: list[dict],
    gate: dict,
    target_column: str,
    province_column: str,
    region_column: str,
    week_index_column: str,
) -> dict[str, dict[tuple[str, int], float]]:
    positives = sum(int(row[target_column]) for row in training)
    global_p = (positives + 1) / (len(training) + 2)
    cfg = gate["competitors"]

    def grouped(field: str, prior_rows: float) -> dict[str, float]:
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in training:
            counts[row[field]][0] += int(row[target_column])
            counts[row[field]][1] += 1
        return {
            key: (positive + prior_rows * global_p) / (total + prior_rows)
            for key, (positive, total) in counts.items()
        }

    province_p = grouped(province_column, float(cfg["province_prior_rows"]))
    region_p = grouped(region_column, float(cfg["region_prior_rows"]))
    active_history: dict[str, list[int]] = defaultdict(list)
    for row in training:
        if int(row[target_column]):
            active_history[row[province_column]].append(
                int(row[week_index_column])
            )

    result = {
        name: {}
        for name in (
            "global_rate",
            "province_empirical_bayes",
            "region_empirical_bayes",
            "training_history_self_exciting",
        )
    }
    alpha = float(cfg["self_excitation_alpha"])
    decay = float(cfg["self_excitation_decay_per_week"])
    for row in forecast:
        key = (row[province_column], int(row[week_index_column]))
        base = province_p.get(row[province_column], global_p)
        excitation = sum(
            math.exp(-decay * (key[1] - prior_week))
            for prior_week in active_history[row[province_column]]
            if prior_week < key[1]
        )
        result["global_rate"][key] = global_p
        result["province_empirical_bayes"][key] = base
        result["region_empirical_bayes"][key] = region_p.get(
            row[region_column], global_p
        )
        result["training_history_self_exciting"][key] = 1.0 - math.exp(
            -(-math.log(1.0 - base) + alpha * excitation)
        )
    return result


def _ensemble_probability(
    runs: list[dict],
    keys: set[tuple[str, int]],
    field: str,
) -> dict[tuple[str, int], float]:
    member_sets = [
        {
            (row["province_id"], int(row["week_index"]))
            for row in run[field]
        }
        for run in runs
    ]
    n = len(member_sets)
    return {
        key: (sum(key in cells for cells in member_sets) + 0.5) / (n + 1.0)
        for key in keys
    }


def _province_losses(
    rows: list[dict],
    probabilities: dict[tuple[str, int], float],
    target_column: str,
    province_column: str,
    week_index_column: str,
) -> dict[str, tuple[float, float, int]]:
    buckets: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        key = (row[province_column], int(row[week_index_column]))
        buckets[row[province_column]].append(
            (int(row[target_column]), _clip(probabilities[key]))
        )
    result = {}
    for province, values in buckets.items():
        brier = sum((y - p) ** 2 for y, p in values) / len(values)
        log_score = sum(
            y * math.log(p) + (1 - y) * math.log(1 - p)
            for y, p in values
        ) / len(values)
        result[province] = (brier, log_score, len(values))
    return result


def _bootstrap_improvement(
    rows: list[dict],
    pineland: dict[tuple[str, int], float],
    competitor: dict[tuple[str, int], float],
    *,
    reps: int,
    seed: int,
    target_column: str,
    province_column: str,
    week_index_column: str,
) -> dict[str, float]:
    p = _province_losses(
        rows, pineland, target_column, province_column, week_index_column
    )
    c = _province_losses(
        rows, competitor, target_column, province_column, week_index_column
    )
    provinces = sorted(p)
    rng = random.Random(seed)
    brier_wins = 0
    log_wins = 0
    brier_deltas = []
    log_deltas = []
    for _ in range(reps):
        sampled = [rng.choice(provinces) for _ in provinces]
        pin_brier = sum(p[x][0] for x in sampled) / len(sampled)
        cmp_brier = sum(c[x][0] for x in sampled) / len(sampled)
        pin_log = sum(p[x][1] for x in sampled) / len(sampled)
        cmp_log = sum(c[x][1] for x in sampled) / len(sampled)
        brier_delta = cmp_brier - pin_brier
        log_delta = pin_log - cmp_log
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


def _auc(
    rows: list[dict],
    probabilities: dict[tuple[str, int], float],
    target_column: str,
    province_column: str,
    week_index_column: str,
) -> float | None:
    positives = []
    negatives = []
    for row in rows:
        key = (row[province_column], int(row[week_index_column]))
        if int(row[target_column]):
            positives.append(probabilities[key])
        else:
            negatives.append(probabilities[key])
    if not positives or not negatives:
        return None
    wins = 0.0
    total = len(positives) * len(negatives)
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / total


def _diagnostics(
    rows: list[dict],
    latent: dict[tuple[str, int], float],
    recorded: dict[tuple[str, int], float],
    target_column: str,
    province_column: str,
    week_index_column: str,
) -> dict:
    observed_rate = sum(
        int(row[target_column]) for row in rows
    ) / max(1, len(rows))
    latent_rate = sum(latent.values()) / max(1, len(latent))
    recorded_rate = sum(recorded.values()) / max(1, len(recorded))
    return {
        "observed_active_rate": observed_rate,
        "latent_predicted_active_rate": latent_rate,
        "latent_rate_error": latent_rate - observed_rate,
        "latent_auc": _auc(
            rows, latent, target_column, province_column, week_index_column
        ),
        "recorded_predicted_active_rate": recorded_rate,
        "recording_attenuation_ratio": (
            recorded_rate / latent_rate if latent_rate > 0 else None
        ),
        "recorded_auc": _auc(
            rows, recorded, target_column, province_column, week_index_column
        ),
        "interpretation_guard": (
            "Rate, discrimination, and latent-to-recorded attenuation are "
            "diagnostics only. They do not alter the preregistered pass/fail rule."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    protocol = gate["protocol"]
    if file_sha256(Path(__file__).resolve()) != protocol["scorer_sha256"]:
        raise SystemExit("scorer source differs from sealed protocol")
    expected_gate_sha = file_sha256(args.gate)
    frozen = gate["frozen_core"]
    if model_sha256(ROOT) != frozen["model_sha256"]:
        raise SystemExit("live model differs from sealed core before outcome reveal")
    repo = repository_state(ROOT)
    if repo["tracked_diff_sha256"] != frozen["tracked_diff_sha256"]:
        raise SystemExit("tracked diff differs from sealed core before outcome reveal")

    expected_strengths = {
        float(x) for x in gate["ensemble"]["taliban_initial_strengths"]
    }
    expected_seeds = {
        int(x) for x in gate["ensemble"]["stochastic_seeds"]
    }
    files = sorted(args.runs_dir.glob("*.json"))
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    expected_pairs = {
        (strength, seed)
        for strength in expected_strengths
        for seed in expected_seeds
    }
    actual_pairs = {
        (float(run["taliban_initial_strength"]), int(run["seed"]))
        for run in runs
    }
    if actual_pairs != expected_pairs or len(runs) != len(expected_pairs):
        raise SystemExit(
            f"incomplete or duplicate ensemble: "
            f"expected={len(expected_pairs)} actual={len(runs)}"
        )
    for run in runs:
        if run["gate_sha256"] != expected_gate_sha:
            raise SystemExit("run belongs to a different sealed gate")
        if int(run["holdout_year"]) != int(gate["holdout_year"]):
            raise SystemExit("holdout year mismatch")
        if run["model_sha256"] != frozen["model_sha256"]:
            raise SystemExit("model hash mismatch in sealed ensemble")
        if run["tracked_diff_sha256"] != frozen["tracked_diff_sha256"]:
            raise SystemExit("tracked diff mismatch in sealed ensemble")
        if not run["initialization_gate"]["passed"]:
            raise SystemExit("structural initialization failure in sealed ensemble")
        if run.get("empirical_forecast_outcomes_read") is not False:
            raise SystemExit("forecast run is not outcome-blind")

    # EMPIRICAL OUTCOME REVEAL BEGINS HERE, and only here.
    surface = gate["target_surface"]
    panel_path = ROOT / surface["panel_path"]
    target_column = surface["target_column"]
    week_start_column = surface["week_start_column"]
    province_column = surface.get("province_column", "province_id")
    region_column = surface.get("region_column", "region_id")
    week_index_column = surface.get("week_index_column", "week_index")
    with panel_path.open(encoding="utf-8", newline="") as handle:
        all_rows = list(csv.DictReader(handle))

    forecast_year = str(gate["holdout_year"])
    training_years = {str(year) for year in gate["training"]["outcome_years"]}
    score_start_week = int(
        gate["forecast_window"]["first_scored_week_index"]
    )
    score_end_week = int(
        gate["forecast_window"]["end_scored_week_index_exclusive"]
    )
    training = [
        row
        for row in all_rows
        if 0 <= int(row[week_index_column]) < score_start_week
    ]
    forecast = [
        row
        for row in all_rows
        if score_start_week
        <= int(row[week_index_column])
        < score_end_week
    ]
    if not training or not forecast:
        raise SystemExit("training or forecast panel rows are missing")
    forecast.sort(
        key=lambda row: (
            int(row[week_index_column]),
            row[province_column],
        )
    )
    keys = {
        (row[province_column], int(row[week_index_column]))
        for row in forecast
    }

    competitors = _fit_competitors(
        training,
        forecast,
        gate,
        target_column,
        province_column,
        region_column,
        week_index_column,
    )
    pineland = _ensemble_probability(runs, keys, "latent_active_cells")
    recorded = _ensemble_probability(runs, keys, "recorded_active_cells")
    scores = {
        "pineland_latent_ensemble": _losses(
            forecast, pineland, target_column
        ),
        "pineland_recorded_ensemble": _losses(
            forecast, recorded, target_column
        ),
    }
    for name, probabilities in competitors.items():
        scores[name] = _losses(forecast, probabilities, target_column)

    competitor_names = list(competitors)
    primary_prediction_field = (
        "recorded_active_cells"
        if gate["primary_layer"] == "recorded"
        else "latent_active_cells"
    )
    primary_score_name = (
        "pineland_recorded_ensemble"
        if gate["primary_layer"] == "recorded"
        else "pineland_latent_ensemble"
    )
    primary_probabilities = (
        recorded if gate["primary_layer"] == "recorded" else pineland
    )
    best_brier = min(
        competitor_names, key=lambda name: scores[name]["brier"]
    )
    best_log = max(
        competitor_names, key=lambda name: scores[name]["log_score"]
    )
    proper_score_pass = (
        scores[primary_score_name]["brier"]
        < scores[best_brier]["brier"]
        and scores[primary_score_name]["log_score"]
        > scores[best_log]["log_score"]
    )

    acceptance = gate["acceptance"]
    reps = int(acceptance["bootstrap_repetitions"])
    bootstrap_seed = int(acceptance["bootstrap_seed"])
    threshold = float(acceptance["bootstrap_min_improvement_probability"])
    bootstrap_brier = _bootstrap_improvement(
        forecast,
        primary_probabilities,
        competitors[best_brier],
        reps=reps,
        seed=bootstrap_seed,
        target_column=target_column,
        province_column=province_column,
        week_index_column=week_index_column,
    )
    bootstrap_log = (
        bootstrap_brier
        if best_log == best_brier
        else _bootstrap_improvement(
            forecast,
            primary_probabilities,
            competitors[best_log],
            reps=reps,
            seed=bootstrap_seed,
            target_column=target_column,
            province_column=province_column,
            week_index_column=week_index_column,
        )
    )
    bootstrap_pass = (
        bootstrap_brier["brier_improvement_probability"] >= threshold
        and bootstrap_log["log_score_improvement_probability"] >= threshold
    )

    global_scores = scores["global_rate"]
    strength_rows = {}
    strength_passes = []
    for strength in sorted(expected_strengths):
        stratum = [
            run
            for run in runs
            if float(run["taliban_initial_strength"]) == strength
        ]
        probs = _ensemble_probability(
            stratum, keys, primary_prediction_field
        )
        result = _losses(forecast, probs, target_column)
        brier_delta = result["brier"] - global_scores["brier"]
        log_delta = result["log_score"] - global_scores["log_score"]
        passes = (
            (
                result["brier"] < global_scores["brier"]
                or result["log_score"] > global_scores["log_score"]
            )
            and brier_delta
            <= float(acceptance["max_brier_worsening_vs_global"])
            and log_delta
            >= -float(acceptance["max_log_worsening_vs_global"])
        )
        strength_rows[str(int(strength))] = {
            **result,
            "brier_minus_global": brier_delta,
            "log_score_minus_global": log_delta,
            "passed": passes,
        }
        strength_passes.append(passes)

    stock_limit = float(
        acceptance["all_member_stock_residual_absolute_max"]
    )
    supply_limit = float(
        acceptance["all_member_supply_residual_absolute_max"]
    )
    residual_pass = all(
        abs(float(run["stock_ledger_residual"])) <= stock_limit
        and abs(float(run["supply_conservation_residual"])) <= supply_limit
        and abs(float(run.get("population_residual", 0.0))) <= 1e-5
        for run in runs
    )
    current_model_unchanged = model_sha256(ROOT) == frozen["model_sha256"]
    current_diff_unchanged = (
        repository_state(ROOT)["tracked_diff_sha256"]
        == frozen["tracked_diff_sha256"]
    )
    checks = {
        "complete_ensemble": True,
        "sealed_gate_identity": True,
        "frozen_core_identity": current_model_unchanged and current_diff_unchanged,
        "structural_gates": True,
        "ledger_residuals": residual_pass,
        "proper_scores_beat_best_competitors": proper_score_pass,
        "province_cluster_bootstrap": bootstrap_pass,
        "all_strength_strata_robust": all(strength_passes),
        "no_post_reveal_model_changes": (
            current_model_unchanged and current_diff_unchanged
        ),
    }
    passed = all(checks.values())
    report = {
        "schema_version": "pineland.afghanistan.sealed_year_score.v1",
        "passed": passed,
        "prospective_holdout": forecast_year,
        "source_family": surface["source_family"],
        "target_column": target_column,
        "primary_layer": gate["primary_layer"],
        "training_years": sorted(int(year) for year in training_years),
        "scored_week_index_range": [
            score_start_week,
            score_end_week,
        ],
        "rows": len(forecast),
        "checks": checks,
        "scores": scores,
        "best_competitor_by_brier": best_brier,
        "best_competitor_by_log_score": best_log,
        "bootstrap_vs_best_brier": bootstrap_brier,
        "bootstrap_vs_best_log": bootstrap_log,
        "strength_robustness": strength_rows,
        "diagnostics": _diagnostics(
            forecast,
            pineland,
            recorded,
            target_column,
            province_column,
            week_index_column,
        ),
        "run_runtime_seconds": {
            f"{int(run['taliban_initial_strength'])}:{run['seed']}":
                run["runtime_seconds"]
            for run in runs
        },
        "gate_sha256": expected_gate_sha,
        "model_sha256": frozen["model_sha256"],
        "interpretation": (
            gate["claim_rule"]["pass"]
            if passed
            else gate["claim_rule"]["fail"]
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
