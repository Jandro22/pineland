from __future__ import annotations

import importlib.util
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "studies/research_program/scripts/build_afghanistan_acled_province_week_v1.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("acled_mapping", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_actor_mapping_requires_both_frozen_sides():
    module = _module()
    insurgent = re.compile(r"(?i)\b(taliban|taleban)\b")
    state = re.compile(r"(?i)(forces of afghanistan|police|isaf)")
    fields = ["ACTOR1", "ALLY_ACTOR1", "ACTOR2", "ALLY_ACTOR_2"]
    positive = {
        "ACTOR1": "Taliban (Afghanistan)",
        "ALLY_ACTOR1": "",
        "ACTOR2": "Police Forces of Afghanistan",
        "ALLY_ACTOR_2": "",
    }
    civilian = {**positive, "ACTOR2": "Civilians (Afghanistan)"}
    assert module.actor_mapping(positive, insurgent, state, fields) == (True, True)
    assert module.actor_mapping(civilian, insurgent, state, fields) == (True, False)


def test_calendar_week_index_is_absolute_from_2004_boundary():
    module = _module()
    from datetime import date
    assert module.week_index(date(2004, 1, 1)) == 0
    assert module.week_index(date(2008, 1, 1)) == 208
    rows = module._calendar_rows(2008)
    assert min(int(row["week_index"]) for row in rows) == 208
    assert max(int(row["week_index"]) for row in rows) == module.week_index(
        date(2008, 12, 31)
    )
    assert any(
        row["week_index"] == "208" and row["week_start"] == "2007-12-27"
        for row in rows
    )
