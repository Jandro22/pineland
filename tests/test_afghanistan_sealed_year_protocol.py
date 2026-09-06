from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "studies/research_program/scripts"


def _source(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def _load(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gate_preparer_and_runner_cannot_open_empirical_panel():
    preparer = _source("prepare_afghanistan_sealed_year_gate.py")
    runner = _source("run_afghanistan_sealed_year.py")
    assert "province_week_panel" not in preparer
    assert "province_week_panel" not in runner
    assert "taliban_state_active" not in preparer
    assert "taliban_state_active" not in runner


def test_2006_calendar_boundary_is_fixed_without_outcome_access():
    preparer = _load("prepare_afghanistan_sealed_year_gate.py")
    from datetime import date

    assert preparer.day_offset(date(2006, 1, 1)) == 731
    assert preparer.day_offset(date(2007, 1, 1)) == 1096


def test_boundary_week_is_neither_training_nor_forecast():
    preparer = _load("prepare_afghanistan_sealed_year_gate.py")
    from datetime import date

    start = preparer.day_offset(date(2007, 1, 1))
    training_end = start // 7
    first_scored = (start + 6) // 7
    assert training_end == 156
    assert first_scored == 157
    assert training_end < first_scored


def test_gate_preparer_requires_year_specific_nonexposure_certificate(tmp_path):
    preparer = _load("prepare_afghanistan_sealed_year_gate.py")
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"case_id":"afghanistan_2004_2021","holdout_year":2006,'
        '"target":"Taliban-government state-based violence incidence by province-week",'
        '"target_labels_previously_inspected":true,'
        '"created_before_target_label_access":false,'
        '"certification_basis":["already exposed"]}',
        encoding="utf-8",
    )
    import pytest

    with pytest.raises(RuntimeError):
        preparer._load_exposure_certificate(bad, 2006)


def test_project_ledger_blocks_consumed_or_exposed_years():
    preparer = _load("prepare_afghanistan_sealed_year_gate.py")
    import pytest

    with pytest.raises(RuntimeError):
        preparer._assert_surface_is_still_eligible(2005)
    with pytest.raises(RuntimeError):
        preparer._assert_surface_is_still_eligible(2006)


def test_scorer_reveal_occurs_after_completeness_and_provenance_checks():
    scorer = _source("score_afghanistan_sealed_year.py")
    reveal = scorer.index("with panel_path.open")
    assert scorer.index("actual_pairs != expected_pairs") < reveal
    assert scorer.index("run belongs to a different sealed gate") < reveal
    assert scorer.index("model hash mismatch in sealed ensemble") < reveal
    assert scorer.index("forecast run is not outcome-blind") < reveal


def test_scorer_uses_gate_declared_surface_and_primary_layer():
    scorer = _source("score_afghanistan_sealed_year.py")
    assert 'surface = gate["target_surface"]' in scorer
    assert 'target_column = surface["target_column"]' in scorer
    assert 'gate["primary_layer"] == "recorded"' in scorer


def test_measurement_license_requires_independent_afghanistan_reference():
    license_source = _source(
        "build_afghanistan_empirical_measurement_license.py"
    )
    assert "recorded_event_promotion_gate" in license_source
    assert "parameters_fit_without_pineland_outcomes" in license_source
    assert "province-week Taliban-government state-based violence" in license_source
