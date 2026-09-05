from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "build_mechanism_evidence.py"
SPEC = importlib.util.spec_from_file_location("build_mechanism_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_mechanism_matrix_is_explicitly_descriptive():
    source = ROOT / "studies/nepal_2001_2006/results/residual_diagnosis/compact_mechanism_diagnostics.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    result = MODULE.build(payload, case_id="nepal_2001_2006", source=source)
    assert result["status"] == "case_evidence_pending_cross_case_replication"
    assert result["ablation_rows"]
    assert all(row["interpretation_status"] == "descriptive_ablation_not_causal_claim" for row in result["ablation_rows"])

