from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/build_comparative_control_presence_panels.py"
SPEC = importlib.util.spec_from_file_location("build_comparative_control_presence_panels", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_period_bounds_preserve_missingness():
    assert MODULE.period_bounds("1996-2004") == ("1996-01-01", "2004-12-31")
    assert MODULE.period_bounds("") == ("", "")


def test_colombia_undated_points_are_not_imputed_as_absence(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text(
        "service,layer_id,feature_id,longitude,latitude,period\nA,0,1,1,2,\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.csv"
    MODULE.build_colombia(source, output)
    row = next(csv.DictReader(output.open(encoding="utf-8")))
    assert row["reported_value"] == ""
    assert row["observation_status"] == "not_temporally_located"
    assert row["missingness_reason"] == "source_has_no_reported_period"


def test_iraq_scope_and_nonreporting_are_explicit(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text(
        "case_id,anchor_unit,month,control_responsibility,evidence_status,date_precision\n"
        "iraq_2003_2011,rusafa,2003-03-01,not_reported,not_reported,not_reported\n",
        encoding="utf-8",
    )
    output = tmp_path / "out.csv"
    MODULE.build_iraq(source, output)
    row = next(csv.DictReader(output.open(encoding="utf-8")))
    assert row["reported_value"] == ""
    assert row["spatial_scope"] == "Rusafa_political_district_anchor_only"
    assert row["missingness_reason"] == "outside_reported_operational_window"
