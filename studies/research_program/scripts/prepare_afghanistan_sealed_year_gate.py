"""Create a prospective Afghanistan one-year holdout gate without reading outcomes.

This script is intentionally incapable of opening the province-week outcome
panel. It binds a holdout year to the current model source, runner/scorer
implementations, ensemble design, competitor training window, and acceptance
rules before any forecast outcome is revealed.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.reproducibility import model_sha256, repository_state

EMPTY_DIFF_SHA256 = hashlib.sha256(b"").hexdigest()
INITIALIZATION_DATE = date(2004, 1, 1)
HOLDOUT_LEDGER = (
    ROOT
    / "studies/research_program/afghanistan_empirical_one_year_holdout_ledger.json"
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def day_offset(value: date) -> int:
    return (value - INITIALIZATION_DATE).days


def _load_exposure_certificate(path: Path, year: int) -> tuple[dict, str]:
    certificate = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "case_id": "afghanistan_2004_2021",
        "holdout_year": year,
        "target_labels_previously_inspected": False,
        "created_before_target_label_access": True,
    }
    for key, expected in required.items():
        if certificate.get(key) != expected:
            raise RuntimeError(
                f"exposure certificate fails {key}: "
                f"expected={expected!r} actual={certificate.get(key)!r}"
            )
    basis = certificate.get("certification_basis")
    if not isinstance(basis, list) or not basis:
        raise RuntimeError("exposure certificate requires a non-empty certification_basis")
    if not str(certificate.get("target") or "").strip():
        raise RuntimeError("exposure certificate requires a declared target")
    if not str(certificate.get("source_family") or "").strip():
        raise RuntimeError("exposure certificate requires a declared source_family")
    target_surface = certificate.get("target_surface")
    if not isinstance(target_surface, dict):
        raise RuntimeError("exposure certificate requires target_surface")
    for key in ("panel_path", "target_column", "week_start_column"):
        if not str(target_surface.get(key) or "").strip():
            raise RuntimeError(f"target_surface requires {key}")
    layer = certificate.get("primary_prediction_layer")
    if layer not in {"latent", "recorded"}:
        raise RuntimeError("primary_prediction_layer must be latent or recorded")
    return certificate, file_sha256(path)


def _assert_surface_is_still_eligible(year: int) -> None:
    if not HOLDOUT_LEDGER.exists():
        raise RuntimeError(
            "empirical holdout ledger is required before sealing a holdout"
        )
    ledger = json.loads(HOLDOUT_LEDGER.read_text(encoding="utf-8"))
    for row in ledger.get("holdouts", []):
        if int(row.get("year", -1)) != int(year):
            continue
        status = str(row.get("status") or "")
        if status not in {"sealed_unrevealed", "eligible_unrevealed"}:
            raise RuntimeError(
                f"holdout year {year} is not pristine: ledger status={status!r}"
            )


def build_gate(
    year: int, *, output: Path, exposure_certificate: Path
) -> dict:
    if year <= 2004:
        raise ValueError("prospective holdout year must be later than 2004")
    _assert_surface_is_still_eligible(year)
    certificate, certificate_sha = _load_exposure_certificate(
        exposure_certificate, year
    )
    ledger = json.loads(HOLDOUT_LEDGER.read_text(encoding="utf-8"))
    if (
        ledger.get("next_required_validation_surface", {}).get(
            "same_ucdp_later_year_is_sufficient"
        ) is False
        and str(certificate["source_family"]).casefold().startswith("ucdp")
    ):
        raise RuntimeError(
            "the project ledger requires a new independent source family; "
            "another UCDP year cannot restore pristine confirmation"
        )
    runner = ROOT / "studies/research_program/scripts/run_afghanistan_sealed_year.py"
    scorer = ROOT / "studies/research_program/scripts/score_afghanistan_sealed_year.py"
    repo = repository_state(ROOT)
    if repo["tracked_diff_sha256"] != EMPTY_DIFF_SHA256:
        raise RuntimeError(
            "tracked repository diff must be empty before sealing an empirical holdout"
        )
    start = date(year, 1, 1)
    end_exclusive = date(year + 1, 1, 1)
    training_years = list(range(2004, year))
    seeds = [
        year * 10000 + 113,
        year * 10000 + 220,
        year * 10000 + 327,
        year * 10000 + 403,
    ]
    payload = {
        "schema_version": "pineland.afghanistan.sealed_year_gate.v1",
        "created_without_forecast_outcome_access": True,
        "purpose": (
            "Prospective one-year out-of-sample empirical test of the frozen "
            "Afghanistan latent state-based-violence mechanism after only "
            "independently justified synthetic/general-theory repairs."
        ),
        "holdout_year": year,
        "outcome_exposure_certificate": {
            "path": str(exposure_certificate.resolve()),
            "sha256": certificate_sha,
            "certification_basis": certificate["certification_basis"],
        },
        "frozen_core": {
            "source_commit_at_seal": repo["commit_hash"],
            "model_sha256": model_sha256(ROOT),
            "tracked_diff_sha256": EMPTY_DIFF_SHA256,
        },
        "protocol": {
            "runner": str(runner.relative_to(ROOT)).replace("\\", "/"),
            "runner_sha256": file_sha256(runner),
            "scorer": str(scorer.relative_to(ROOT)).replace("\\", "/"),
            "scorer_sha256": file_sha256(scorer),
        },
        "forecast_window": {
            "initialization_date": INITIALIZATION_DATE.isoformat(),
            "start": start.isoformat(),
            "end_exclusive": end_exclusive.isoformat(),
            "start_day": day_offset(start),
            "end_day": day_offset(end_exclusive),
            "simulation_horizon_days": day_offset(end_exclusive),
            "score_only_forecast_window": True,
            "score_only_full_week_cells": True,
            "first_scored_week_index": (
                day_offset(start) + 6
            ) // 7,
            "end_scored_week_index_exclusive": (
                day_offset(end_exclusive) // 7
            ),
            "forecast_outcomes_may_not_update_predictions": True,
        },
        "training": {
            "outcome_years": training_years,
            "forecast_year_excluded": True,
        },
        "ensemble": {
            "taliban_initial_strengths": [5000, 7500, 10000],
            "stochastic_seeds": seeds,
            "members": 12,
            "cell_probability": (
                "Jeffreys-smoothed member incidence: (hits + 0.5) / (members + 1)"
            ),
        },
        "target_surface": {
            "source_family": certificate["source_family"],
            "panel_path": certificate["target_surface"]["panel_path"],
            "target_column": certificate["target_surface"]["target_column"],
            "week_start_column": certificate["target_surface"]["week_start_column"],
            "province_column": certificate["target_surface"].get(
                "province_column", "province_id"
            ),
            "region_column": certificate["target_surface"].get(
                "region_column", "region_id"
            ),
            "week_index_column": certificate["target_surface"].get(
                "week_index_column", "week_index"
            ),
            "source_silence_semantics": certificate["target_surface"].get(
                "source_silence_semantics"
            ),
        },
        "primary_target": certificate["target"],
        "primary_layer": certificate["primary_prediction_layer"],
        "measurement_claim": {
            "recorded_layer_role": (
                "primary"
                if certificate["primary_prediction_layer"] == "recorded"
                else "diagnostic_only"
            ),
            "reason": certificate.get(
                "measurement_reason",
                "The prediction layer is fixed by the source construct before reveal."
            ),
            "promotion_requires_independent_measurement_license": (
                certificate["primary_prediction_layer"] != "recorded"
            ),
        },
        "competitors": {
            "fit_years": training_years,
            "holdout_refit": False,
            "models": [
                "global_rate",
                "province_empirical_bayes",
                "region_empirical_bayes",
                "training_history_self_exciting",
            ],
            "province_prior_rows": 52,
            "region_prior_rows": 104,
            "self_excitation_alpha": 0.18,
            "self_excitation_decay_per_week": 0.20,
            "self_excitation_history_updates": "training years only",
        },
        "acceptance": {
            "complete_ensemble_required": True,
            "all_member_structural_gates_required": True,
            "all_member_stock_residual_absolute_max": 1e-5,
            "all_member_supply_residual_absolute_max": 1e-5,
            "proper_score_rule": (
                "Pineland primary ensemble must strictly improve on the best "
                "training-only competitor on both mean Brier loss and mean log score "
                "over every holdout province-week cell."
            ),
            "bootstrap_rule": (
                "Paired province-cluster bootstrap, 5000 resamples. Probability "
                "that Pineland improves on the best competitor must be at least "
                "0.95 separately for Brier and log score."
            ),
            "bootstrap_repetitions": 5000,
            "bootstrap_seed": year * 10000 + 606,
            "bootstrap_min_improvement_probability": 0.95,
            "strength_robustness_rule": (
                "Each initial-strength stratum must beat the global-rate baseline "
                "on at least one proper score and may not be worse than global by "
                "more than 0.002 Brier or 0.01 mean log score on the other."
            ),
            "max_brier_worsening_vs_global": 0.002,
            "max_log_worsening_vs_global": 0.01,
            "no_post_reveal_model_changes": True,
        },
        "claim_rule": {
            "pass": (
                "Strong prospective one-year empirical support for the frozen "
                "prediction layer against the declared training-only competitors "
                "on a source family sealed before label access. This does not by "
                "itself license the full 17.6-year benchmark."
            ),
            "fail": (
                "Preserve the failure. Do not tune any model, initialization, "
                "measurement, or scoring choice from this holdout. A later test "
                "requires independently motivated changes and a new untouched year."
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exposure-certificate", type=Path, required=True)
    args = parser.parse_args()
    payload = build_gate(
        args.year,
        output=args.output,
        exposure_certificate=args.exposure_certificate,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
