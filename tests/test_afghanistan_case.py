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


def test_afghanistan_connectivity_is_derived_from_frozen_topology_not_constant():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    values = [float(row["connectivity"]) for row in specification["districts"]]
    assert len(set(round(value, 12) for value in values)) > 100
    assert min(values) >= 0.0
    assert max(values) <= 1.0
    assert min(values) == 0.0
    assert max(values) == 1.0
    metadata = specification["derived_non_outcome_inputs"]["district_connectivity"]
    assert metadata["historical_outcomes_used"] is False
    assert metadata["fitted_coefficients"] is False


def test_afghanistan_retains_worldpop_settlement_covariates_without_using_outcomes():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    rows = specification["districts"]
    assert all("empirical_covariates" in row for row in rows)
    density = [
        row["empirical_covariates"]["population_density_per_sqkm"]
        for row in rows
    ]
    concentration = [
        row["empirical_covariates"]["settlement_concentration_hhi"]
        for row in rows
    ]
    assert min(density) > 0
    assert max(density) > min(density) * 10
    assert max(concentration) > min(concentration)
    metadata = specification["derived_non_outcome_inputs"][
        "worldpop_settlement_structure"
    ]
    assert metadata["historical_outcomes_used"] is False
    assert metadata["fitted_coefficients"] is False
    assert metadata["model_equations_currently_changed_by_covariates"] is True


def test_afghanistan_preoutcome_settlement_structure_drives_spatial_fields():
    specification = json.loads(CASE.read_text(encoding="utf-8"))
    localities = specification["localities"]
    districts = {row["district_id"]: row for row in specification["districts"]}
    for field in ("infrastructure", "observability"):
        values = [float(row[field]) for row in localities]
        assert min(values) >= 0.0
        assert max(values) <= 1.0
        assert len(set(round(value, 10) for value in values)) > 100
    urbanization = [float(row["urbanization"]) for row in districts.values()]
    assert min(urbanization) >= 0.0
    assert max(urbanization) <= 1.0
    assert len(set(round(value, 10) for value in urbanization)) > 100
    # No unsupported terrain or state-capacity signal is inferred from
    # settlement density alone.
    assert {float(row["terrain_friction"]) for row in localities} == {1.0}
    assert {float(row["administrative_capacity"]) for row in localities} == {0.5}
    assert specification["outcome_data_used_for_geography"] is False
    assert specification["benchmark_period_outcomes_used_for_initialization"] is False


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
