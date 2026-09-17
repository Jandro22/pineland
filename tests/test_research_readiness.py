import random

from pineland_sim import (Simulation, SimulationConfig, generate_pineland,
                          output_mode_benchmark, topology_ablation)
from pineland_sim.networks import degree_preserving_rewire, network_diagnostics
from pineland_sim.peace_process import bargaining_values
from pineland_sim.research_audit import (language_factorial, truth_firewall_battery,
                                          representative_agent_audit,
                                          publication_readiness_report)


def _config(mode="forensic"):
    return SimulationConfig(agent_count=80, locality_count=17, horizon_days=2,
                            seed=20260930, output_mode=mode)


def test_output_modes_preserve_scientific_trajectory():
    worlds = [Simulation(generate_pineland(_config(mode))).run().world
              for mode in ("forensic", "ensemble", "calibration")]
    reference = worlds[0]
    for world in worlds[1:]:
        assert world.summary()["mean_government_effective_control"] == reference.summary()["mean_government_effective_control"]
        assert world.summary()["mean_insurgent_effective_control"] == reference.summary()["mean_insurgent_effective_control"]
        assert world.event_counts == reference.event_counts
        assert world.recruitment_total == reference.recruitment_total
        assert world.contact_event_times == reference.contact_event_times
    assert len(worlds[0].state_deltas) > 0
    assert len(worlds[1].state_deltas) == 0
    assert len(worlds[2].event_log) == 0


def test_output_mode_benchmark_reports_equivalence():
    result = output_mode_benchmark(_config())
    assert result["trajectory_equivalence"]
    assert result["modes"]["calibration"]["peak_bytes"] <= result["modes"]["forensic"]["peak_bytes"]


def test_degree_preserving_rewire_preserves_degree_sequence_and_edges():
    world = generate_pineland(_config())
    before = sorted(len(neighbors) for neighbors in world.social_neighbors.values())
    edges = len(world.social_edges)
    result = degree_preserving_rewire(world, seed=17, swaps=100)
    after = sorted(len(neighbors) for neighbors in world.social_neighbors.values())
    assert result["accepted_swaps"] > 0
    assert before == after
    assert len(world.social_edges) == edges
    assert network_diagnostics(world)["components"] >= 1


def test_language_factorial_has_all_eight_channel_combinations():
    result = language_factorial(_config(), horizon_days=1, repetitions=1, workers=2)
    assert set(result["modes"]) == {
        "none", "topology", "detection", "fusion",
        "topology_detection", "topology_fusion", "detection_fusion", "all",
    }
    sequential = language_factorial(_config(), horizon_days=1, repetitions=1, workers=1)
    assert result["modes"] == sequential["modes"]
    assert result["factor_effects"] == sequential["factor_effects"]


def test_bargaining_default_is_belief_based():
    world = generate_pineland(_config())
    baseline = bargaining_values(world)
    locality = next(iter(world.localities.values()))
    locality.control["government"].physical = 0.0
    locality.violence = 1.0
    assert bargaining_values(world) == baseline
    assert bargaining_values(world, perspective="truth") != baseline


def test_global_accounting_is_explicit_and_reconciled():
    world = Simulation(generate_pineland(_config())).run().world
    accounting = world.global_accounting_diagnostics()
    # Floating-point reduction order differs slightly across platforms. The
    # accounting contract is numerical closure, not bitwise zero.
    assert accounting["max_abs_stock_residual"] <= 1e-6
    assert abs(accounting["population_residual"]) < 1e-6
    assert set(accounting["flow_kinds"]) == {
        "internal_transfer", "production", "consumption", "destruction",
        "external_inflow", "external_outflow",
    }
    assert accounting["reconciliation"]["closed"]


def test_topology_ablation_returns_matched_modes():
    result = topology_ablation(_config(), horizon_days=1, swaps=25)
    assert set(result["modes"]) == {"original", "degree_preserving_rewired", "random_mixing"}
    assert all(row["degree_sequence_preserved"] for row in result["modes"].values())


def test_truth_firewall_battery_and_representative_audit_pass():
    config = _config()
    assert truth_firewall_battery(config, horizon_days=1)["pass"]
    audit = representative_agent_audit(config, horizon_days=1)
    assert audit["all_pass"]
    assert "household archetype" in audit["household_semantics"]


def test_readiness_report_marks_powered_batteries_when_deferred():
    result = publication_readiness_report(_config(), horizon_days=1, language_repetitions=1)
    assert result["substantive_paper_readiness_score"] == 35.0
    assert "resolution_battery" in result["open_or_conditional_questions"]
    assert result["empirical_claim_status"].startswith("not validated")
