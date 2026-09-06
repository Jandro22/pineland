from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_acled_independent_measurement_contract_v1.json"
)
ACQUIRE = (
    ROOT
    / "studies/research_program/scripts/acquire_afghanistan_acled_replication_v1.py"
)


def test_acled_mapping_is_frozen_before_row_acquisition():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["created_before_replication_event_rows_inspected_for_pineland"] is True
    mapping = contract["mapping_frozen_before_rows"]
    assert mapping["actor_fields"] == [
        "ACTOR1", "ALLY_ACTOR1", "ACTOR2", "ALLY_ACTOR_2"
    ]
    assert "taliban|taleban" in mapping["insurgent_regex"].lower()
    assert contract["target_surface"]["primary_year"] == 2008
    assert contract["scientific_firewall"]["primary_year_may_not_be_reselected_after_row_inspection"] is True


def test_acquisition_stage_cannot_parse_event_csv():
    source = ACQUIRE.read_text(encoding="utf-8")
    assert "zipfile" not in source
    assert "csv." not in source
    assert "afpak24may10_3actors.csv" not in source
    assert "event_rows_inspected_by_acquisition" in source
