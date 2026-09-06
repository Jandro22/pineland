import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies/research_program/scripts/validate_final_theory_hardening_v1.py"


def test_planted_base_signature_follows_organization_not_geography():
    spec = importlib.util.spec_from_file_location("hardening", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    row = module.run_seed(2026090699)
    assert row["passed"], row
