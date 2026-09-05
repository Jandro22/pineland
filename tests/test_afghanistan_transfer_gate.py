from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "afghanistan_2004_2021" / "scripts" / "evaluate_transfer_gate.py"
SPEC = importlib.util.spec_from_file_location("evaluate_transfer_gate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def payload(*, latent: int = 1, attempts: int = 4) -> dict:
    return {
        "horizon_days": 366.0,
        "gate": {"passed": True},
        "contact_funnel_counts": {
            "scheduler_executions": attempts,
            "opposing_armed_organizations": attempts,
            "readiness_available_pairs": attempts,
            "engagement_hazard_draws": attempts,
        },
        "violence_validation": {"latent_contacts": latent},
    }


def test_nondegenerate_year_authorizes_full_run():
    assert MODULE.evaluate(payload())["full_horizon_ensemble_authorized"]


def test_zero_realizations_do_not_block_when_positive_hazard_was_reached():
    report = MODULE.evaluate(payload(latent=0))
    assert report["full_horizon_ensemble_authorized"]
    assert report["observed_latent_contacts"] == 0
    assert not report["latent_contact_realization_required_for_promotion"]
    assert report["outcome_scope"]["structural_and_control_validation"]
    assert not report["outcome_scope"]["realized_violence_validation"]


def test_no_hazard_draws_blocks_expensive_full_run():
    report = MODULE.evaluate(payload(latent=0, attempts=0))
    assert not report["full_horizon_ensemble_authorized"]
    assert report["decision"] == "DIAGNOSE_BEFORE_FULL_ENSEMBLE"


def test_integrity_failure_blocks_escalation_even_with_contacts():
    candidate = payload()
    candidate["gate"]["passed"] = False
    assert not MODULE.evaluate(candidate)["full_horizon_ensemble_authorized"]
