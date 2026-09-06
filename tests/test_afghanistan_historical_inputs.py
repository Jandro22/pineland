from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import pytest

from pineland_sim import SimulationConfig, generate_pineland


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
SCRIPTS = STUDY / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from historical_case import (  # noqa: E402
    HistoricalCoalitionSchedule,
    condition_world,
    initialization_diagnostics,
    load_historical_inputs,
)


@pytest.fixture(scope="module")
def generated_world():
    case = json.loads(
        (STUDY / "config" / "case_environment.json").read_text(encoding="utf-8")
    )
    config = SimulationConfig(
        seed=20040101,
        horizon_days=400,
        agent_count=401,
        locality_count=401,
        output_mode="calibration",
    )
    config.foreign_affairs.enabled = False
    config.peace_process.enabled = False
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, 400.0]]
    }
    return generate_pineland(config, empirical_geography=case)


def test_historical_input_package_keeps_uncertainty_and_archived_troop_values():
    inputs = load_historical_inputs()
    assert inputs["benchmark_violence_used"] is False
    assert inputs["initialization"]["taliban"]["personnel_envelope"] == [5000, 7500, 10000]
    schedule = {row["date"]: row for row in inputs["international_forces"]["stock_schedule"]}
    assert schedule["2004-01-01"]["total"] == 24400
    assert schedule["2017-01-01"]["us"] == 14000
    assert schedule["2018-01-01"]["us"] == 14000
    assert schedule["2021-01-15"]["total"] == 9592
    assert schedule["2021-08-15"]["total"] == 6000


def test_sigar_407_to_401_crosswalk_is_complete_except_patoo():
    crosswalk = list(csv.DictReader(
        (STUDY / "data" / "processed" / "sigar_407_to_401_crosswalk.csv").open(
            encoding="utf-8", newline=""
        )
    ))
    control = list(csv.DictReader(
        (STUDY / "data" / "processed" / "sigar_oct2017_control_401.csv").open(
            encoding="utf-8", newline=""
        )
    ))
    assert len(crosswalk) == 407
    assert len({row["target_district_id"] for row in crosswalk}) == 400
    assert len(control) == 401
    missing = [row["district_id"] for row in control if not row["government_control_index"]]
    assert missing == ["AF2409"]
    assert sum(row["relation"] == "split_child_to_parent" for row in crosswalk) == 7
    assert sum(row["relation"] == "same_district_admin_transfer" for row in crosswalk) == 2


@pytest.mark.parametrize("taliban_strength", [5000, 7500, 10000])
def test_conditioned_force_stocks_match_sourced_case(generated_world, taliban_strength):
    world = generated_world.clone()
    inputs = load_historical_inputs()
    condition_world(world, inputs, taliban_strength)
    diagnostic = initialization_diagnostics(world, inputs, taliban_strength)
    assert diagnostic["weighted_population"] == 24_726_689
    assert diagnostic["ana_personnel"] == pytest.approx(6500)
    assert diagnostic["anp_personnel"] == pytest.approx(6000)
    assert diagnostic["taliban_personnel"] == pytest.approx(taliban_strength)
    assert diagnostic["coalition_personnel"] == pytest.approx(24400)
    assert diagnostic["ana_formations"] == 12
    assert diagnostic["taliban_formations"] == 8
    assert diagnostic["coalition_formations"] == 4
    assert diagnostic["foreign_states"] == ["pakistan"]
    assert diagnostic["pakistan_border_segments"] == 45
    assert diagnostic["taliban_external_sanctuary"] == 1.0
    assert abs(diagnostic["stock_ledger_residual"]) < 1e-8
    assert abs(diagnostic["supply_conservation_residual"]) < 1e-8


def test_conditioning_removes_synthetic_insurgent_social_state(generated_world):
    world = generated_world.clone()
    inputs = load_historical_inputs()
    condition_world(world, inputs, 7500)
    anchors = set(inputs["initialization"]["taliban"]["anchor_weights"])
    # Ecology initialization may recreate affiliation at a sourced formation,
    # but no synthetic affinity may survive outside that footprint.
    assert all(person.residence_locality_id in anchors
               for person in world.persons.values()
               if "insurgent" in person.insurgent_affinity)
    assert all("insurgent" not in person.social_exposure for person in world.persons.values())
    assert all(person.residence_locality_id in anchors
               for person in world.persons.values()
               if person.public_behavior in {"armed_participation", "insurgent_sympathy"})


def test_observed_coalition_schedule_replaces_stock_without_breaking_ledgers(generated_world):
    world = generated_world.clone()
    inputs = load_historical_inputs()
    condition_world(world, inputs, 7500)
    schedule = HistoricalCoalitionSchedule(inputs)
    world.time = 366.0  # 2005-01-01; 2004 is leap year.
    schedule(world, world.time)
    personnel = sum(
        formation.personnel for formation in world.formations.values()
        if formation.organization_id == "coalition"
    )
    assert personnel == pytest.approx(26700)
    assert schedule.applied[-1]["date"] == "2005-01-01"
    assert abs(world.stock_ledger_residual()) < 1e-8
    assert abs(world.supply_conservation_residual()) < 1e-8
    world.assert_invariants()
