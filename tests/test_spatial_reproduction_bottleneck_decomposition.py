from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "studies" / "research_program" / "scripts" /
          "decompose_spatial_reproduction_bottlenecks.py")
SPEC = importlib.util.spec_from_file_location("decompose_spatial_reproduction_bottlenecks", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _row(**updates):
    row = {
        "target_locality_id": "L", "source_locality_ids": ["P"],
        "exposure_seen": False, "access_seen": False,
        "recruitment_seen": False, "fighter_conversion_seen": False,
        "local_birth_day": None, "local_birth_ids": [],
        "relocation_seen": False, "relocation_day": None,
        "birth_complete_followup": False, "birth_survived_window": False,
    }
    row.update(updates)
    return row


def test_stage_denominators_are_conditional_and_zero_denominators_unidentified():
    rows = [
        _row(exposure_seen=True, access_seen=True, recruitment_seen=True,
             fighter_conversion_seen=True, local_birth_day=10.0,
             local_birth_ids=["F1"], birth_complete_followup=True,
             birth_survived_window=True),
        _row(exposure_seen=True, access_seen=True),
        _row(),
    ]
    counts = MODULE._stage_counts(rows)
    assert counts["contact_information_exposure"]["opportunity_denominator"] == 3
    assert counts["contact_information_exposure"]["realized_numerator"] == 2
    assert counts["recruitment_response"]["opportunity_denominator"] == 2
    assert counts["recruitment_response"]["realized_numerator"] == 1
    assert counts["local_fighter_conversion"]["opportunity_denominator"] == 1
    assert counts["formation_birth"]["opportunity_denominator"] == 1
    assert counts["survival_after_birth"]["opportunity_denominator"] == 1
    assert (counts["recruitment_response"]["opportunity_denominator"] ==
            counts["contact_information_exposure"]["realized_numerator"])
    assert (counts["local_fighter_conversion"]["opportunity_denominator"] ==
            counts["recruitment_response"]["realized_numerator"])
    assert (counts["formation_birth"]["opportunity_denominator"] ==
            counts["local_fighter_conversion"]["realized_numerator"])
    assert (counts["survival_after_birth"]["opportunity_denominator"] <=
            counts["formation_birth"]["realized_numerator"])
    empty = MODULE._stage_counts([_row()])
    assert not empty["recruitment_response"]["identified"]
    assert empty["recruitment_response"]["loss_fraction"] is None
    off_path = MODULE._stage_counts([
        _row(recruitment_seen=True, fighter_conversion_seen=True,
             local_birth_day=1.0, birth_complete_followup=True,
             birth_survived_window=True)
    ])
    assert off_path["local_fighter_conversion"]["opportunity_denominator"] == 0
    assert off_path["formation_birth"]["opportunity_denominator"] == 0
    assert off_path["survival_after_birth"]["opportunity_denominator"] == 0


def test_ranking_uses_loss_fraction_not_raw_lost_count():
    counts = {stage: {"identified": True, "loss_fraction": 0.1,
                      "lost_opportunities": 1, "opportunity_denominator": 10}
              for stage in MODULE.STAGE_ORDER}
    counts["formation_birth"].update(loss_fraction=0.8, lost_opportunities=8)
    counts["contact_information_exposure"].update(
        loss_fraction=0.6, lost_opportunities=60, opportunity_denominator=100)
    ranking = MODULE.rank_stage_losses(counts)
    assert ranking[0]["stage"] == "formation_birth"
    assert ranking[1]["stage"] == "contact_information_exposure"


def test_matched_live_core_recovery_gates_pass_without_historical_data():
    result = MODULE.run_matched_recovery_tests(seed=20260905)
    assert result["historical_outcomes_used"] is False
    assert result["empirical_parameter_fitting"] is False
    assert result["passed"]
    assert set(result["stage_gates"]) == set(MODULE.STAGE_ORDER)
    assert all(result["stage_gates"].values())


def test_compact_live_frontier_cohort_reports_all_stages():
    result = MODULE.run_frontier_cohort(
        seed=20260905, horizon_days=14.0, agent_count=450,
        locality_count=20, survival_window_days=7.0)
    assert result["frontier_opportunity_count"] > 0
    assert set(result["stage_counts"]) == set(MODULE.STAGE_ORDER)
    assert all(row["opportunity_denominator"] >= row["realized_numerator"]
               for row in result["stage_counts"].values())
    assert "identified" in result["genealogy"]


def test_study_reports_core_provenance_hashes():
    result = MODULE.run_study(
        seeds=[20260905], horizon_days=2.0, agent_count=300,
        locality_count=20, survival_window_days=1.0)
    assert result["historical_outcomes_used"] is False
    assert set(result["core_source_hashes"]) == set(MODULE.CORE_SOURCE_PATHS)
    assert result["core_changed_during_study"] is False
    assert result["study_changed_during_study"] is False
    assert result["provenance_valid"] is True
    assert result["model_sha256_start"] == result["model_sha256_end"]
    assert result["script_sha256_start"] == result["script_sha256_end"]
    assert result["negative_results_preserved"] is True
