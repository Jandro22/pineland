from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "studies" / "research_program" / "scripts"
    / "identify_competitive_local_renewal.py"
)
ARTIFACT = ROOT / "studies" / "research_program" / "competitive_local_renewal.json"
SPEC = importlib.util.spec_from_file_location("competitive_local_renewal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


@pytest.fixture(scope="module")
def result():
    return MODULE.run_study(seed=20260905)


def test_study_is_data_free_and_all_recovery_gates_pass(result):
    assert result["status"] == "synthetic_general_theory_intervention_study"
    assert result["historical_outcomes_used"] is False
    assert result["historical_parameter_fitting"] is False
    assert result["passed"] is True
    assert all(result["gates"].values())


def test_cross_local_bridge_is_a_true_next_generation_reproduction_path(result):
    first, second, third = result["design"]["localities"]["target_localities"]
    baseline = result["conditions"]["baseline"]["generations"]
    no_bridge = result["conditions"]["no_social_bridging"]["generations"]

    assert baseline[0]["bridge_armed_fraction"][first] > 0
    assert baseline[0]["bridge_armed_fraction"][second] == 0
    assert baseline[1]["bridge_armed_fraction"][second] > 0
    assert baseline[1]["bridge_armed_fraction"][third] == 0
    assert baseline[2]["bridge_armed_fraction"][third] > 0
    assert all(
        row["bridge_armed_fraction"][locality_id] == 0
        for row in no_bridge
        for locality_id in (first, second, third)
    )


def test_member_access_and_field_presence_are_redundant_local_amplifiers(result):
    first = result["design"]["localities"]["target_localities"][0]
    no_member = result["conditions"]["no_local_member_access"]["generations"]
    no_field = result["conditions"]["no_fielded_force_presence"]["generations"]
    combined = result["conditions"]["no_local_or_field_access"]["generations"]

    # The first recruited bridge member is established in generation 1.
    # In generation 2 either remaining local channel can recruit the isolated
    # local candidate, but removing both leaves that candidate unrecruited.
    assert no_member[1]["local_candidate_armed_fraction"][first] > 0
    assert no_field[1]["local_candidate_armed_fraction"][first] > 0
    assert all(
        row["local_candidate_armed_fraction"][first] == 0 for row in combined
    )


def test_cross_local_chain_does_not_require_either_local_access_amplifier(result):
    third = result["design"]["localities"]["target_localities"][2]
    combined = result["conditions"]["no_local_or_field_access"]["generations"]
    assert combined[2]["bridge_armed_fraction"][third] > 0
    assert combined[-1]["bridge_armed_fraction"][third] == 1.0


def test_clandestine_membership_self_sustains_after_source_cut_without_field_force(result):
    first, _, third = result["design"]["localities"]["target_localities"]
    rows = result["conditions"]["clandestine_after_source_cut"]["generations"]

    assert rows[0]["bridge_armed_fraction"][first] > 0
    assert rows[1]["local_candidate_armed_fraction"][first] > 0
    assert rows[2]["bridge_armed_fraction"][third] > 0
    assert all(
        value == 0
        for row in rows
        for value in row["viable_fielded_personnel"].values()
    )
    assert rows[-1]["organization_survival_social_base"] > 0


def test_full_persistence_break_stops_the_renewal_chain(result):
    first, second, third = result["design"]["localities"]["target_localities"]
    rows = result["conditions"]["no_persistence"]["generations"]
    assert rows[0]["bridge_armed_fraction"][first] > 0
    assert rows[1]["bridge_armed_fraction"][second] == 0
    assert rows[2]["bridge_armed_fraction"][third] == 0


def test_live_membership_exit_leaves_a_weaker_but_causal_social_signal(result):
    diagnostic = result["exit_only_residual_signal"]
    assert diagnostic["before_exit_armed_fraction"] > 0
    assert diagnostic["after_exit_armed_fraction"] == 0
    assert diagnostic["after_exit_public_behavior"] == "insurgent_sympathy"
    assert diagnostic["downstream_exposure_after_member_exit"] > 0
    assert (
        diagnostic["downstream_armed_fraction_after_recruitment"]
        > diagnostic["downstream_armed_fraction_before_recruitment"]
    )


def test_social_control_is_downstream_not_a_recruitment_mediator(result):
    diagnostic = result["social_control_mediation"]
    assert diagnostic["first_locality_social_control_delta"] > 0
    assert diagnostic["observer_behavior_after_exposure"] == "insurgent_sympathy"
    assert diagnostic["membership_trajectory_identical_after_control_restore"] is True
    assert (
        diagnostic["downstream_member_mass_with_control_retained"]
        == diagnostic["downstream_member_mass_with_control_restored"]
    )


def test_generated_artifact_records_the_same_data_free_conclusion():
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert payload["historical_outcomes_used"] is False
    assert payload["historical_parameter_fitting"] is False
    assert payload["passed"] is True
    assert payload["live_mechanism_audit"]["renewing_positive_feedback_loop_present"] is True
    assert (
        payload["live_mechanism_audit"][
            "clandestine_self_sustain_without_fielded_presence"
        ]
        is True
    )
