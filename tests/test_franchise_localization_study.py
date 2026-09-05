from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "identify_franchise_localization.py"
SPEC = importlib.util.spec_from_file_location("identify_franchise_localization", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_franchise_localization_study_recovers_all_declared_signatures():
    report = MODULE.run_study(20260905)
    assert report["historical_outcomes_used"] is False
    assert report["historical_parameter_fitting"] is False
    assert report["passed"] is True
    assert all(report["gates"].values())


def test_localization_curve_monotonically_reduces_outsider_disadvantage():
    rows = MODULE.localization_curve(20260906)
    assert rows[0]["indigenous_member_share"] == 0.0
    assert rows[-1]["indigenous_member_share"] == 1.0
    assert rows[-1]["recruitment_intensity"] > rows[0]["recruitment_intensity"]
    assert all(
        right["recruitment_intensity"] >= left["recruitment_intensity"] - 1e-12
        for left, right in zip(rows, rows[1:])
    )
