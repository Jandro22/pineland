from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
CERT = ROOT / "studies/research_program/nigeria_2014_external_holdout_certificate.json"
DESIGN = ROOT / "studies/research_program/nigeria_2014_external_holdout_design.json"


def test_nigeria_holdout_is_sealed_as_unexposed_before_target_extraction():
    cert = json.loads(CERT.read_text(encoding="utf-8"))
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    assert cert["case_id"] == design["case_id"] == "nigeria_boko_haram_2014"
    assert cert["target_labels_previously_inspected"] is False
    assert cert["created_before_target_label_access"] is True
    assert design["target_year"] == 2014
    assert design["initialization"]["preperiod_year"] == 2013
    assert design["acceptance"]["no_post_reveal_changes"] is True


def test_target_mapping_and_competitors_are_declared_before_reveal():
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    source = design["outcome_source"]
    assert source["event_type_rule"] == "type_of_violence == 1"
    assert "boko" in source["insurgent_regex"].lower()
    assert source["government_regex"] == "(?i)^government of nigeria$"
    assert design["competitors"]["fit_scope"].startswith("2013")
    assert design["prediction"]["primary_layer"] == "latent state-based violence"
