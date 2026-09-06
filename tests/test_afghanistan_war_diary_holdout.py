from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_awd_2007_independent_holdout_contract_v1.json"
)
ACQUIRE = (
    ROOT
    / "studies/research_program/scripts/acquire_afghanistan_war_diary_v1.py"
)
BUILD = (
    ROOT
    / "studies/research_program/scripts/build_afghanistan_war_diary_province_week_v1.py"
)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_contract_is_frozen_before_war_diary_rows():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert (
        contract["created_before_war_diary_event_rows_acquired_for_pineland"]
        is True
    )
    assert contract["target_surface"]["holdout_year"] == 2007
    assert contract["target_surface"]["primary_prediction_layer"] == "recorded"
    assert contract["scientific_firewall"][
        "mapping_code_must_be_committed_before_acquisition"
    ] is True


def test_acquisition_stage_cannot_parse_event_rows():
    source = ACQUIRE.read_text(encoding="utf-8")
    assert "csv.reader" not in source
    assert "csv.DictReader" not in source
    assert "event_rows_inspected_by_acquisition" in source


def test_frozen_mapping_requires_violence_and_hostile_insurgent_evidence():
    module = _load(BUILD)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    mapping = contract["mapping_frozen_before_rows"]
    combat = re.compile(mapping["combat_regex"])
    taliban = re.compile(mapping["taliban_regex"])
    enemy_affiliation = re.compile(mapping["enemy_affiliation_regex"])
    enemy_display = re.compile(mapping["enemy_display_regex"])
    base = {name: "" for name in contract["frozen_fields"]}
    positive = {
        **base,
        "Category": "IED AMBUSH",
        "Affiliation": "ENEMY",
    }
    nonviolent = {**base, "Affiliation": "ENEMY", "Category": "MEETING"}
    nonhostile = {**base, "Category": "IED AMBUSH", "Affiliation": "FRIEND"}
    assert module.row_qualifies(
        positive, combat, taliban, enemy_affiliation, enemy_display
    ) == (True, True)
    assert module.row_qualifies(
        nonviolent, combat, taliban, enemy_affiliation, enemy_display
    ) == (False, True)
    assert module.row_qualifies(
        nonhostile, combat, taliban, enemy_affiliation, enemy_display
    ) == (True, False)


def test_2007_full_week_scoring_excludes_boundary_cells():
    preparer = _load(
        ROOT
        / "studies/research_program/scripts/prepare_afghanistan_sealed_year_gate.py"
    )
    from datetime import date

    start = preparer.day_offset(date(2007, 1, 1))
    end = preparer.day_offset(date(2008, 1, 1))
    first = (start + 6) // 7
    training_end = start // 7
    end_exclusive = end // 7
    assert training_end == 156
    assert first == 157
    assert end_exclusive == 208
    assert end_exclusive - first == 51
    assert first - training_end == 1
