from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from pineland_sim import SimulationConfig, generate_pineland


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "identify_colonization_channels.py"
SPEC = importlib.util.spec_from_file_location("identify_colonization_channels", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_dynamic_cross_local_social_suppression_restores_graph_exactly():
    world = generate_pineland(SimulationConfig(
        agent_count=260, locality_count=24, horizon_days=1, seed=9191,
    ))
    before_keys = set(world.social_edges)
    before_neighbors = {pid: tuple(neighbors) for pid, neighbors in world.social_neighbors.items()}
    initial_cross = MODULE.cross_local_social_edge_count(world)
    assert initial_cross > 0
    with MODULE.suppress_current_cross_local_social_edges(world) as removed:
        assert removed == initial_cross
        assert MODULE.cross_local_social_edge_count(world) == 0
    assert set(world.social_edges) == before_keys
    assert {pid: tuple(neighbors) for pid, neighbors in world.social_neighbors.items()} == before_neighbors


def test_site_reproduction_metrics_separate_new_sites_from_initial_and_relocation():
    episodes = [
        {"activation_id": "A0", "channel": "member_foothold_present", "locality_id": "L0",
         "activation_day": 0.0, "activation_end_day": None, "cause": "initial_condition"},
        {"activation_id": "A1", "channel": "member_foothold_present", "locality_id": "L1",
         "activation_day": 5.0, "activation_end_day": None, "cause": "cross_local_social_recruitment"},
        {"activation_id": "A2", "channel": "fielded_force_viable", "locality_id": "L1",
         "activation_day": 12.0, "activation_end_day": None, "cause": "local_member_to_force_generation"},
        {"activation_id": "A3", "channel": "fielded_force_viable", "locality_id": "L2",
         "activation_day": 8.0, "activation_end_day": 10.0, "cause": "formation_relocation"},
    ]
    edges = [{
        "child_activation_id": "A1", "child_channel": "member_foothold_present",
        "child_locality_id": "L1", "parent_activation_id": "A0",
        "parent_locality_id": "L0", "weight": 1.0,
    }]
    metrics = MODULE.site_reproduction_metrics(episodes, edges, 40.0)
    assert metrics["initial_foothold_sites"] == 1
    assert metrics["distinct_new_foothold_sites"] == 1
    assert metrics["finite_horizon_site_colonization_yield"] == 1.0
    assert metrics["cross_local_parent_edge_mass"] == 1.0
    assert metrics["persistent_new_sites"] == 1
    assert metrics["new_sites_reaching_fielded_force"] == 1


def test_small_condition_run_has_valid_data_free_site_estimand():
    config = SimulationConfig(
        agent_count=260, locality_count=24, horizon_days=12, seed=9292,
        include_insurgency=True, output_mode="ensemble",
    )
    world = generate_pineland(config)
    row = MODULE.run_condition(world, "no_cross_local_social", until=12.0)
    assert row["condition"] == "no_cross_local_social"
    assert row["social_suppression_ticks"] > 0
    assert row["social_edge_instances_suppressed"] > 0
    assert row["initial_foothold_sites"] >= 0
    assert row["distinct_new_foothold_sites"] >= 0
    assert row["gross_formation_relocation_activations"] >= 0


def test_study_contract_is_synthetic_and_preserves_negative_channel_effects():
    report = MODULE.run_study(seeds=(9393,), agents=260, localities=24, days=12.0)
    assert report["historical_outcomes_used"] is False
    assert report["historical_parameter_fitting"] is False
    assert report["core_equations_modified_by_study"] is False
    assert report["matched_channel_interventions_applied"] is True
    assert set(report["design"]["conditions"]) == set(MODULE.CONDITIONS)
    assert len(report["runs"]) == len(MODULE.CONDITIONS)
    for condition, effect in report["paired_channel_effects"].items():
        assert condition != "baseline"
        assert len(effect["paired_runs"]) == 1
