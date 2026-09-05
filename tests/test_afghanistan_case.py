import json
from pathlib import Path

import pandas as pd

from pineland_sim import SimulationConfig, generate_pineland


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"


def test_afghanistan_case_instantiates_full_hierarchy_and_population():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(
        agent_count=len(specification["localities"]),
        locality_count=len(specification["localities"]),
        horizon_days=1,
        seed=20040101,
    )
    world = generate_pineland(config, empirical_geography=specification)
    assert len(world.geographic_containers) == 42  # 8 regions + 34 provinces
    assert len(world.districts) == 401
    assert len(world.localities) == 401
    assert len(world.district_hierarchy) == 401
    assert world.weighted_population() == 24_726_689
    assert all(locality.administrative_role == "district_headquarters"
               for locality in world.localities.values())
    assert world.formations["PRF-01"].locality_id == specification["initial_insurgent_locality_ids"][0]
    assert world.organizations["insurgent"].member_ids
    world.assert_invariants()


def test_afghanistan_primary_panel_is_frozen_complete_province_week_surface():
    panel = pd.read_csv(PANEL)
    assert len(panel) == 31_280
    assert panel["province_id"].nunique() == 34
    assert set(panel["split"]) == {
        "training", "geographic_validation", "temporal_validation", "strict_joint_holdout"
    }
    assert panel["taliban_state_active"].isin([0, 1]).all()
    assert int(panel["taliban_state_event_count"].sum()) == 34_641
    assert int(panel["taliban_state_active"].sum()) == 13_307
