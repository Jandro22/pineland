from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "studies/research_program/scripts/compare_afghanistan_acled_ucdp_v1.py"
)


def test_concordance_script_cannot_fit_or_modify_model():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "parameters_fitted" in source
    assert '"parameters_fitted": False' in source
    assert "generate_pineland" not in source
    assert "Simulation(" not in source
    assert "set_parameter" not in source
