from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "studies" / "research_program" / "reproduction_competitors.py"
SPEC = importlib.util.spec_from_file_location("reproduction_competitors", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def genealogy() -> dict:
    return {
        "seed": 1,
        "horizon_days": 28.0,
        "episodes": [
            {"activation_id":"F0","channel":"member_foothold_present","locality_id":"A",
             "activation_day":0.0,"activation_end_day":28.0,"observation_end_day":28.0,
             "cause":"initial_condition","parentage_class":"initial_condition"},
            {"activation_id":"F1","channel":"member_foothold_present","locality_id":"B",
             "activation_day":7.0,"activation_end_day":28.0,"observation_end_day":28.0,
             "cause":"cross_local_social_recruitment","parentage_class":"social_network_seeded"},
            {"activation_id":"A1","channel":"member_access_saturated","locality_id":"B",
             "activation_day":10.0,"activation_end_day":28.0,"observation_end_day":28.0,
             "cause":"local_recruitment","parentage_class":"unresolved"},
            {"activation_id":"X1","channel":"fielded_force_viable","locality_id":"B",
             "activation_day":12.0,"activation_end_day":28.0,"observation_end_day":28.0,
             "cause":"local_member_to_force_generation","parentage_class":"unresolved"},
            {"activation_id":"F2","channel":"member_foothold_present","locality_id":"C",
             "activation_day":14.0,"activation_end_day":18.0,"observation_end_day":28.0,
             "cause":"local_recruitment","parentage_class":"local_spontaneous_ignition"},
            {"activation_id":"F3","channel":"member_foothold_present","locality_id":"D",
             "activation_day":21.0,"activation_end_day":28.0,"observation_end_day":28.0,
             "cause":"local_recruitment_unattributed_provenance","parentage_class":"unresolved"},
        ],
    }


def test_full_locality_universe_is_required_and_validated():
    with pytest.raises(ValueError, match="full locality universe"):
        MODULE.GenealogyRun("1", "training", genealogy(), ())
    run = MODULE.GenealogyRun("1", "training", genealogy(), ("A","B","C"))
    with pytest.raises(ValueError, match="outside declared universe"):
        MODULE.build_site_period_panel(run)


def test_site_period_panel_separates_local_ignition_colonization_and_unresolved():
    run = MODULE.GenealogyRun("1", "training", genealogy(), ("A","B","C","D","E"))
    panel = MODULE.build_site_period_panel(
        run, bin_days=7.0,
        adjacency={"A":["B"],"B":["A","C"],"C":["B","D"],"D":["C"],"E":[]},
    )
    b = panel[(panel.locality_id == "B") & (panel.period_index == 1)].iloc[0]
    assert b.new_foothold_site == 1
    assert b.parent_attributed_colonization == 1
    assert b.local_spontaneous_ignition == 0
    c = panel[(panel.locality_id == "C") & (panel.period_index == 2)].iloc[0]
    assert c.local_spontaneous_ignition == 1
    d = panel[(panel.locality_id == "D") & (panel.period_index == 3)].iloc[0]
    assert d.unresolved_new_foothold == 1
    e = panel[panel.locality_id == "E"]
    assert e.at_risk_for_new_foothold.eq(1).all()
    assert e.new_foothold_site.eq(0).all()


def test_relocation_is_never_counted_as_parent_attributed_colonization():
    data = genealogy()
    data["episodes"].append({
        "activation_id":"R1","channel":"member_foothold_present","locality_id":"E",
        "activation_day":7.0,"activation_end_day":28.0,"observation_end_day":28.0,
        "cause":"formation_relocation","parentage_class":"formation_relocation",
    })
    run = MODULE.GenealogyRun("1", "training", data, ("A","B","C","D","E"))
    panel = MODULE.build_site_period_panel(run)
    row = panel[(panel.locality_id == "E") & (panel.period_index == 1)].iloc[0]
    assert row.relocation_classified_new_foothold == 1
    assert row.parent_attributed_colonization == 0


def test_deepening_and_survival_use_followup_censoring():
    run = MODULE.GenealogyRun("1", "training", genealogy(), ("A","B","C","D","E"))
    panel = MODULE.build_foothold_episode_panel(
        run, deepening_horizon_days=14.0, survival_horizon_days=7.0
    )
    b = panel[panel.activation_id == "F1"].iloc[0]
    assert b.deepened_to_saturated_access == 1
    assert b.deepened_to_fielded_force == 1
    assert b.survived_horizon == 1
    c = panel[panel.activation_id == "F2"].iloc[0]
    assert c.deepening_followup_eligible == 1
    assert c.deepened_to_fielded_force == 0
    assert c.survived_horizon == 0
    d = panel[panel.activation_id == "F3"].iloc[0]
    assert d.deepening_followup_eligible == 0
    assert np.isnan(d.deepened_to_fielded_force)
    assert d.survival_followup_eligible == 1


def test_aggregate_panel_preserves_decomposition_counts():
    run = MODULE.GenealogyRun("1", "training", genealogy(), ("A","B","C","D","E"))
    tables = MODULE.build_reproduction_tables(
        [run], bin_days=7.0, deepening_horizon_days=14.0, survival_horizon_days=7.0
    )
    aggregate = tables["aggregate_period"]
    assert aggregate.new_foothold_sites.sum() == 3
    assert aggregate.parent_attributed_colonizations.sum() == 1
    assert aggregate.local_spontaneous_ignitions.sum() == 1
    assert aggregate.unresolved_new_footholds.sum() == 1
    summary = MODULE.decomposition_summary(tables)
    assert summary["parent_attributed_colonizations"] == 1
    assert summary["unresolved_new_footholds"] == 1


def test_episode_baselines_fit_training_only_and_preserve_holdout_outcomes():
    first = MODULE.GenealogyRun("train", "training", genealogy(), ("A","B","C","D","E"))
    holdout_data = genealogy(); holdout_data["seed"] = 2
    second = MODULE.GenealogyRun("holdout", "temporal_validation", holdout_data, ("A","B","C","D","E"))
    episode = MODULE.build_reproduction_tables(
        [first, second], deepening_horizon_days=14.0, survival_horizon_days=7.0
    )["foothold_episode"]
    predictions = MODULE.episode_binary_competitors(episode, "deepened_to_fielded_force")
    mutated = episode.copy()
    mask = mutated.split != "training"
    mutated.loc[mask & mutated.deepened_to_fielded_force.notna(), "deepened_to_fielded_force"] = (
        1 - mutated.loc[mask & mutated.deepened_to_fielded_force.notna(), "deepened_to_fielded_force"]
    )
    second_predictions = MODULE.episode_binary_competitors(mutated, "deepened_to_fielded_force")
    holdout = predictions.split != "training"
    for model in ("constant_probability", "locality_empirical_bayes", "parentage_class_empirical_bayes"):
        np.testing.assert_allclose(predictions.loc[holdout, model], second_predictions.loc[holdout, model])
