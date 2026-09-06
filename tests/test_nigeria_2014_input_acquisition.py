from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/acquire_nigeria_2014_case_inputs.py"


def test_nigeria_acquisition_cannot_parse_ged_rows():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "import csv" not in source
    assert "csv.DictReader" not in source
    assert "import zipfile" not in source
    assert "zipfile.ZipFile" not in source
    assert "type_of_violence" not in source
    assert "date_start" not in source
    assert '"ged_rows_read": False' in source
    assert '"target_rows_read": False' in source
