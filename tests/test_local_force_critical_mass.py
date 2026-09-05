import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "identify_local_force_critical_mass.py"
SPEC = importlib.util.spec_from_file_location("identify_local_force_critical_mass", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_threshold_sweep_finds_force_birth_before_member_access_saturation():
    report = MODULE.run_threshold_sweep(seed=20260905)
    assert report["minimum_proto_represented_population"] == 1_000.0
    assert report["fighter_conversion_fraction"] == 0.08
    assert report["minimum_formation_personnel"] == 75.0
    assert report["represented_members_for_force_birth_from_empty_pool"] == 937.5
    assert report["proto_implied_fighter_personnel"] == 80.0
    assert report["proto_gate_already_clears_formation_manpower_minimum"] is True

    rows = report["rows"]
    assert rows[0]["represented_members"] < 937.5
    assert rows[0]["formations_created"] == 0
    boundary = next(row for row in rows
                    if abs(row["represented_members"] - 937.5) <= 1e-9)
    assert boundary["formations_created"] == 1
    assert boundary["fielded_force_viable"]
    assert boundary["member_access"] < 1.0
    saturated = next(row for row in rows
                     if abs(row["represented_members"] - 1_000.0) <= 1e-9)
    assert saturated["member_access"] == 1.0
    assert saturated["formations_created"] == 1


def test_concentration_dispersion_holds_total_recruitment_constant_and_changes_births():
    rows = [
        MODULE.run_concentration_condition(n, total_represented=2_000.0,
                                           seed=20261000)
        for n in (1, 2, 3, 4)
    ]
    expected_fighter_total = 2_000.0 * 0.08
    for row in rows:
        assert row["total_represented_recruitment"] == 2_000.0
        assert abs(row["total_fighter_equivalent_applied"] - expected_fighter_total) <= 1e-9
        assert row["formations_created"] == row["fielded_force_viable_localities"]

    by_n = {row["locality_count"]: row for row in rows}
    assert by_n[1]["formations_created"] == 1
    assert by_n[2]["formations_created"] == 2
    assert by_n[3]["formations_created"] == 0
    assert by_n[4]["formations_created"] == 0
    assert by_n[2]["genealogy_edges"]
    assert all(edge["pathway"] == "local_member_to_force_generation"
               for edge in by_n[2]["genealogy_edges"])
    assert all(edge["parent_channel"] == "member_foothold_present"
               for edge in by_n[2]["genealogy_edges"])


def test_pool_alignment_changes_birth_with_matched_total_manpower_budget():
    report = MODULE.run_pool_alignment(seed=20262000)
    aligned = report["aligned"]
    dispersed = report["dispersed"]
    assert aligned["new_represented_recruitment"] == dispersed["new_represented_recruitment"]
    assert aligned["new_fighter_equivalent"] == dispersed["new_fighter_equivalent"]
    assert aligned["preexisting_pool_total"] == dispersed["preexisting_pool_total"]
    assert aligned["total_force_manpower_budget"] == dispersed["total_force_manpower_budget"]
    assert aligned["formations_created"] == 1
    assert dispersed["formations_created"] == 0
    assert aligned["genealogy_edges"]
    assert all(edge["pathway"] == "local_member_to_force_generation"
               for edge in aligned["genealogy_edges"])


def test_hysteresis_same_current_mass_retains_underthreshold_formation_access():
    report = MODULE.run_hysteresis(seed=20263000)
    formed = report["formed_then_attrited"]
    pooled = report["never_formed_pool"]
    assert report["matched_current_represented_members"] == 500.0
    assert report["matched_current_fighter_manpower"] == 55.0
    assert formed["formation_count"] == 1
    assert formed["formation_personnel"] == 55.0
    assert formed["operational_source_count"] == 1
    assert not formed["fielded_force_viable"]
    assert pooled["formation_count"] == 0
    assert pooled["pool_personnel"] == 55.0
    assert not pooled["fielded_force_viable"]
    assert formed["access"]["member_access"] == pooled["access"]["member_access"]
    assert formed["access"]["formation_access"] > pooled["access"]["formation_access"]
    assert report["access_hysteresis"] > 0.0


def test_actual_movement_is_relocation_not_reproduction():
    report = MODULE.run_movement_control(seed=20264000)
    assert report["births_before_move"] == 1
    assert report["formation_count_before_move"] == report["formation_count_after_move"]
    assert report["departure"]["departed"] == 1
    assert report["arrival"]["arrived"] == 1
    assert not report["in_transit"]["origin_viable"]
    assert not report["in_transit"]["target_viable"]
    assert not report["in_transit"]["moving_formation_is_local_recruitment_source"]
    assert report["after_arrival"]["formation_locality"] == report["target"]
    assert report["after_arrival"]["target_viable"]
    assert report["relocation_genealogy_edges"]
    edge = report["relocation_genealogy_edges"][0]
    assert edge["pathway"] == "formation_relocation"
    assert edge["parent_locality_id"] == report["origin"]
    assert edge["child_locality_id"] == report["target"]


def test_study_contract_and_causal_conclusions():
    report = MODULE.run_study(seed=20265000)
    assert report["historical_outcomes_used"] is False
    assert report["empirical_cases_inspected"] is False
    conclusions = report["causal_conclusions"]
    assert conclusions["hard_local_force_birth_threshold_supported"] is True
    assert conclusions["spatial_dispersion_can_block_force_birth_at_fixed_total_manpower"] is True
    assert conclusions["member_access_saturation_is_required_before_force_birth"] is False
    assert conclusions["pool_recruitment_colocation_changes_birth_at_fixed_total_manpower"] is True
    assert conclusions["formed_subthreshold_unit_creates_access_hysteresis"] is True
    assert conclusions["formation_movement_is_relocation_not_reproduction"] is True
    assert conclusions["endogenous_proto_gate_already_clears_formation_manpower_minimum"] is True
    assert conclusions["two_stage_sequential_critical_mass_hypothesis"] == "rejected_as_strict_sequence"
    assert "force birth therefore precedes access saturation" in conclusions["interpretation"]
    assert set(report["rejection_criteria"]) == {
        "hard_force_threshold",
        "dispersion_bottleneck",
        "ordered_two_stage_transition",
        "independent_proto_and_formation_gates",
        "pool_alignment",
        "hysteresis",
        "movement_reproduction",
    }
