from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "estimate_insurgent_reproduction.py"
SPEC = importlib.util.spec_from_file_location("estimate_insurgent_reproduction", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def row(locality, day, end, parent=None, weight=1.0, viable=True,
        activation_id=None, parent_activation_id=None, activation_end_day=None):
    result = {
        "locality_id": locality,
        "activation_day": day,
        "observation_end_day": end,
        "parent_locality_id": parent,
        "parent_weight": weight,
        "viable": viable,
    }
    if activation_id is not None:
        result["activation_id"] = activation_id
    if parent_activation_id is not None:
        result["parent_activation_id"] = parent_activation_id
    if activation_end_day is not None:
        result["activation_end_day"] = activation_end_day
    return result


def test_known_reproduction_tree_is_recovered():
    rows = [
        row("A", 0, 100), row("B", 0, 100),
        row("C", 10, 100, "A"), row("D", 20, 100, "A"),
        row("E", 15, 100, "B"),
    ]
    result = MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    assert result["eligible_parent_localities"] == 5
    assert result["attributed_viable_child_weight"] == 3
    assert result["estimate"] == 0.6


def test_right_censored_parent_is_excluded():
    rows = [row("A", 0, 100), row("B", 80, 100, "A")]
    result = MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    assert result["eligible_parent_localities"] == 1
    # The only attributed child arrives after the declared reproduction
    # window, so it must not inflate the one eligible parent's estimate.
    assert result["estimate"] == 0.0


def test_fractional_parent_attribution_is_preserved():
    rows = [row("A", 0, 100), row("B", 0, 100), row("C", 10, 100, "A", 0.5)]
    result = MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    assert result["attributed_viable_child_weight"] == 0.5


def test_nonpositive_horizon_is_rejected():
    try:
        MODULE.estimate([], horizon_days=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_repeated_locality_activations_require_episode_identifiers():
    rows = [row("A", 0, 100), row("A", 20, 100)]
    try:
        MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    except ValueError as exc:
        assert "activation_id" in str(exc)
    else:
        raise AssertionError("expected ambiguous repeated activations to fail closed")


def test_repeated_activation_parentage_is_episode_specific():
    rows = [
        row("A", 0, 100, activation_id="A-1"),
        row("A", 40, 100, activation_id="A-2"),
        row("B", 10, 100, parent="A", activation_id="B-1", parent_activation_id="A-1"),
        row("C", 50, 100, parent="A", activation_id="C-1", parent_activation_id="A-2"),
    ]
    result = MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    assert result["eligible_parent_activations"] == 4
    assert result["eligible_parent_localities"] == 3
    assert result["attributed_viable_child_weight"] == 2.0
    assert result["estimate"] == 0.5


def test_parentage_losses_are_reported_instead_of_silently_dropped():
    rows = [
        row("A", 80, 100),
        row("B", 90, 100, "A", weight=0.25),
        row("C", 10, 100, "MISSING", weight=0.5),
    ]
    result = MODULE.estimate(rows, horizon_days=30, bootstrap=0)
    assert result["ineligible_parent_child_weight"] == 0.25
    assert result["unknown_parent_child_weight"] == 0.5


def test_parent_relocation_is_not_mistaken_for_locality_reproduction():
    rows = [
        row("A", 0, 100, activation_id="A-1", activation_end_day=12),
        row("B", 10, 100, parent="A", activation_id="B-1",
            parent_activation_id="A-1", activation_end_day=100),
    ]
    result = MODULE.estimate(
        rows, horizon_days=30, bootstrap=0, minimum_parent_overlap_days=7
    )
    assert result["gross_estimate"] == 0.5
    assert result["estimate"] == 0.0
    assert result["gross_attributed_viable_child_weight"] == 1.0
    assert result["relocation_or_parent_extinction_child_weight"] == 1.0


def test_persistent_parent_child_overlap_counts_as_net_reproduction():
    rows = [
        row("A", 0, 100, activation_id="A-1", activation_end_day=40),
        row("B", 10, 100, parent="A", activation_id="B-1",
            parent_activation_id="A-1", activation_end_day=100),
    ]
    result = MODULE.estimate(
        rows, horizon_days=30, bootstrap=0, minimum_parent_overlap_days=7
    )
    assert result["gross_estimate"] == 0.5
    assert result["estimate"] == 0.5
    assert result["relocation_or_parent_extinction_child_weight"] == 0.0


def test_net_reproduction_gate_fails_closed_without_parent_episode_end():
    rows = [
        row("A", 0, 100, activation_id="A-1"),
        row("B", 10, 100, parent="A", activation_id="B-1",
            parent_activation_id="A-1"),
    ]
    try:
        MODULE.estimate(rows, horizon_days=30, bootstrap=0,
                        minimum_parent_overlap_days=7)
    except ValueError as exc:
        assert "activation_end_day" in str(exc)
    else:
        raise AssertionError("expected net reproduction to require parent episode end times")


def test_multi_parent_edge_table_conserves_one_child_without_duplication():
    rows = [
        row("A", 0, 100, activation_id="A-1", activation_end_day=100),
        row("B", 0, 100, activation_id="B-1", activation_end_day=100),
        row("C", 10, 100, activation_id="C-1", activation_end_day=100),
    ]
    edges = [
        {"child_activation_id": "C-1", "parent_activation_id": "A-1", "weight": 0.4},
        {"child_activation_id": "C-1", "parent_activation_id": "B-1", "weight": 0.6},
    ]
    result = MODULE.estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0
    )
    assert result["parentage_representation"] == "multi_parent_edge_table"
    assert result["gross_attributed_viable_child_weight"] == 1.0
    assert result["attributed_viable_child_weight"] == 1.0
    assert result["estimate"] == 1 / 3


def test_multi_parent_edge_mass_over_one_fails_closed():
    rows = [
        row("A", 0, 100, activation_id="A-1"),
        row("B", 10, 100, activation_id="B-1"),
    ]
    edges = [
        {"child_activation_id": "B-1", "parent_activation_id": "A-1", "weight": 0.7},
        {"child_activation_id": "B-1", "parent_activation_id": "A-1", "weight": 0.5},
    ]
    try:
        MODULE.estimate(rows, parent_edges=edges, horizon_days=30, bootstrap=0)
    except ValueError as exc:
        assert "exceeds one" in str(exc)
    else:
        raise AssertionError("expected parent attribution mass >1 to fail closed")


def test_multitype_reproduction_separates_member_and_fielded_force_channels():
    rows = [
        {"activation_id": "M-parent", "locality_id": "A", "channel": "member_access_saturated",
         "activation_day": 0, "activation_end_day": 100, "observation_end_day": 100, "viable": True},
        {"activation_id": "F-parent", "locality_id": "A", "channel": "fielded_force_viable",
         "activation_day": 0, "activation_end_day": 100, "observation_end_day": 100, "viable": True},
        {"activation_id": "M-child", "locality_id": "B", "channel": "member_access_saturated",
         "activation_day": 10, "activation_end_day": 20, "observation_end_day": 20, "viable": True},
        {"activation_id": "F-child", "locality_id": "B", "channel": "fielded_force_viable",
         "activation_day": 20, "activation_end_day": 20, "observation_end_day": 20, "viable": True},
    ]
    edges = [
        {"child_activation_id": "M-child", "parent_activation_id": "M-parent", "weight": 1.0},
        {"child_activation_id": "F-child", "parent_activation_id": "M-parent", "weight": 1.0},
    ]
    result = MODULE.estimate_multitype_reproduction(
        rows, edges, horizon_days=30
    )
    assert result["eligible_parent_activations_by_channel"] == {
        "fielded_force_viable": 1,
        "member_access_saturated": 1,
    }
    assert result["matrix"]["member_access_saturated"]["member_access_saturated"] == 1.0
    assert result["matrix"]["member_access_saturated"]["fielded_force_viable"] == 1.0
    assert result["matrix"]["fielded_force_viable"]["member_access_saturated"] == 0.0
    assert abs(result["spectral_radius"] - 1.0) < 1e-9


def test_initial_condition_roots_are_not_reported_as_unattributed_children():
    rows = [
        {"activation_id": "ROOT", "locality_id": "A", "activation_day": 0,
         "activation_end_day": 100, "observation_end_day": 100,
         "viable": True, "cause": "initial_condition", "channel": "member_foothold_present"},
        {"activation_id": "CHILD", "locality_id": "B", "activation_day": 10,
         "activation_end_day": 100, "observation_end_day": 100,
         "viable": True, "cause": "cross_local_social_recruitment",
         "channel": "member_foothold_present"},
    ]
    edges = [{
        "child_activation_id": "CHILD", "parent_activation_id": "ROOT",
        "parent_channel": "member_foothold_present", "weight": 1.0,
        "pathway": "cross_local_social_recruitment",
    }]
    result = MODULE.estimate(rows, parent_edges=edges, horizon_days=30, bootstrap=0)
    assert result["root_viable_activation_weight"] == 1.0
    assert result["unattributed_viable_child_weight"] == 0.0
    assert result["attributed_viable_child_weight"] == 1.0


def test_same_event_cross_type_progression_enters_multitype_not_scalar_RI():
    rows = [
        {"activation_id": "M", "locality_id": "A", "channel": "member_foothold_present",
         "activation_day": 10, "activation_end_day": 100,
         "observation_end_day": 100, "viable": True, "cause": "local_recruitment"},
        {"activation_id": "F", "locality_id": "A", "channel": "fielded_force_viable",
         "activation_day": 10, "activation_end_day": 100,
         "observation_end_day": 100, "viable": True,
         "cause": "local_member_to_force_generation"},
    ]
    edges = [{
        "child_activation_id": "F", "parent_activation_id": "M",
        "parent_channel": "member_foothold_present", "weight": 1.0,
        "pathway": "local_member_to_force_generation",
    }]
    scalar = MODULE.estimate(rows, parent_edges=edges, horizon_days=30, bootstrap=0)
    assert scalar["attributed_viable_child_weight"] == 0.0
    assert scalar["same_time_cross_type_transition_weight_excluded_from_scalar_R_I"] == 1.0
    typed = MODULE.estimate_multitype_reproduction(rows, edges, horizon_days=30)
    assert typed["matrix"]["member_foothold_present"]["fielded_force_viable"] == 1.0


def test_multitype_partial_identification_upper_bound_dominates_unresolved_parentage():
    rows = [
        {"activation_id": "M0", "locality_id": "A", "channel": "member_foothold_present",
         "activation_day": 0, "activation_end_day": 100,
         "observation_end_day": 100, "viable": True, "cause": "initial_condition"},
        {"activation_id": "F0", "locality_id": "A", "channel": "fielded_force_viable",
         "activation_day": 0, "activation_end_day": 100,
         "observation_end_day": 100, "viable": True, "cause": "initial_condition"},
        {"activation_id": "M1", "locality_id": "B", "channel": "member_foothold_present",
         "activation_day": 10, "activation_end_day": 100,
         "observation_end_day": 100, "viable": True, "cause": "local_recruitment"},
    ]
    result = MODULE.estimate_multitype_reproduction(
        rows, [], horizon_days=30, minimum_parent_overlap_days=7
    )
    assert result["spectral_radius_lower_bound"] == 0.0
    assert result["unresolved_nonroot_viable_activation_count"] == 1
    assert result["unresolved_temporally_parentable_activation_count"] == 1
    assert set(result["feasible_parent_channels_by_unresolved_child"]["M1"]) == {
        "fielded_force_viable", "member_foothold_present"
    }
    upper = result["conservative_upper_bound_matrix"]
    assert upper["fielded_force_viable"]["member_foothold_present"] == 1.0
    # M1 itself has complete follow-up and is therefore also an eligible future
    # parent, so the member-channel denominator is two episodes (M0 and M1).
    assert upper["member_foothold_present"]["member_foothold_present"] == 0.5
    assert result["conservative_upper_bound_spectral_radius"] >= result["spectral_radius"]
    assert result["criticality_identification"] == "identified_subcritical"


def test_multitype_upper_bound_can_identify_subcriticality_despite_missing_parents():
    rows = [
        {"activation_id": f"M{i}", "locality_id": f"A{i}",
         "channel": "member_foothold_present", "activation_day": 0,
         "activation_end_day": 100, "observation_end_day": 100,
         "viable": True, "cause": "initial_condition"}
        for i in range(10)
    ] + [{
        "activation_id": "M-child", "locality_id": "B",
        "channel": "member_foothold_present", "activation_day": 10,
        "activation_end_day": 100, "observation_end_day": 100,
        "viable": True, "cause": "local_recruitment",
    }]
    result = MODULE.estimate_multitype_reproduction(
        rows, [], horizon_days=30, minimum_parent_overlap_days=7
    )
    # Ten founder episodes plus the child itself are eligible parents.
    expected = 1 / 11
    assert result["conservative_upper_bound_matrix"]["member_foothold_present"][
        "member_foothold_present"
    ] == expected
    assert result["conservative_upper_bound_spectral_radius"] == expected
    assert result["criticality_identification"] == "identified_subcritical"


def test_component_decomposition_keeps_ignition_colonization_deepening_and_survival_separate():
    rows = [
        {"activation_id": "ROOT-M", "locality_id": "A",
         "channel": "member_foothold_present", "activation_day": 0,
         "activation_end_day": 100, "observation_end_day": 100,
         "viable": True, "cause": "initial_condition"},
        {"activation_id": "LOCAL", "locality_id": "B",
         "channel": "member_foothold_present", "activation_day": 5,
         "activation_end_day": 50, "observation_end_day": 100,
         "viable": True, "cause": "local_recruitment"},
        {"activation_id": "COLONY", "locality_id": "C",
         "channel": "member_foothold_present", "activation_day": 10,
         "activation_end_day": 60, "observation_end_day": 100,
         "viable": True, "cause": "stored_social_exposure_recruitment"},
        {"activation_id": "FORCE", "locality_id": "C",
         "channel": "fielded_force_viable", "activation_day": 12,
         "activation_end_day": 60, "observation_end_day": 100,
         "viable": True, "cause": "local_member_to_force_generation"},
        {"activation_id": "MOVE", "locality_id": "D",
         "channel": "fielded_force_viable", "activation_day": 15,
         "activation_end_day": 20, "observation_end_day": 100,
         "viable": True, "cause": "formation_relocation"},
    ]
    edges = [
        {"child_activation_id": "COLONY", "parent_activation_id": "ROOT-M",
         "weight": 1.0, "pathway": "stored_social_exposure_recruitment"},
        {"child_activation_id": "FORCE", "parent_activation_id": "COLONY",
         "weight": 1.0, "pathway": "local_member_to_force_generation"},
        {"child_activation_id": "MOVE", "parent_activation_id": "FORCE",
         "weight": 1.0, "pathway": "formation_relocation"},
    ]
    result = MODULE.estimate_reproduction_decomposition(
        rows, edges, horizon_days=30, survival_window_days=30
    )
    components = result["components"]
    assert components["local_endogenous_ignition"]["numerator"] == 1.0
    assert components["parent_attributed_cross_local_colonization"]["numerator"] == 1.0
    assert components["foothold_deepening_force_formation"]["numerator"] == 1.0
    assert components["post_establishment_survival"]["numerator"] == 4
    assert result["parentage_mass_by_class"]["formation_relocation"] == 1.0
    assert result["legacy_scalar_R_I"]["status"] == "deprecated_compatibility_only"


def test_parentage_ontology_fails_unknown_provenance_closed_to_unresolved():
    row = {"cause": "local_recruitment_unattributed_provenance"}
    assert MODULE.parentage_class(row) == "unresolved"
    assert set(MODULE.PARENTAGE_CLASSES) == {
        "local_spontaneous_ignition", "social_network_seeded",
        "migrating_member_seeded", "formation_recruitment_seeded",
        "formation_relocation", "organizational_split_offspring",
        "sanctuary_external_seeded", "unresolved",
    }
