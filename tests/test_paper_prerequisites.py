from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "studies" / "research_program" / "paper_prerequisites"
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "build_paper_prerequisite_status.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_paper_prerequisite_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PaperPrerequisiteTests(unittest.TestCase):
    def test_contribution_contract_declares_unfinished_research(self):
        contract = json.loads((PAPER / "contribution_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["research_status"], "unfinished")
        self.assertTrue(contract["candidate_theory_is_replaceable"])
        self.assertIn("comparative_transfer", {gate["gate"] for gate in contract["publication_level_gates"]})

    def test_claim_language_cannot_start_at_general_theory(self):
        contract = json.loads((PAPER / "claim_language_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["current_maximum_general_theory_level"], 0)
        self.assertEqual(contract["levels"][-1]["id"], "general_theory_supported")
        self.assertGreaterEqual(len(contract["levels"][-1]["minimum_evidence"]), 4)

    def test_result_outputs_are_explicitly_blocked(self):
        registry = json.loads((PAPER / "figure_table_registry.json").read_text(encoding="utf-8"))
        figure = next(item for item in registry["figures"] if item["id"] == "F6")
        table = next(item for item in registry["tables"] if item["id"] == "T6")
        self.assertEqual(figure["buildability"], "blocked")
        self.assertEqual(table["buildability"], "blocked")

    def test_negative_results_are_required_to_persist(self):
        ledger = json.loads((PAPER / "negative_result_ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["status"], "continuous_negative_result_ledger")
        self.assertGreaterEqual(len(ledger["entries"]), 5)
        self.assertTrue(all(entry["what_it_rules_out"] for entry in ledger["entries"]))
        self.assertTrue(all(entry["what_it_does_not_rule_out"] for entry in ledger["entries"]))

    def test_status_compiler_fails_closed_on_general_claims(self):
        status, claims = _module().compile_status(ROOT)
        self.assertEqual(status["status"], "paper_prerequisites_in_progress_not_manuscript_result")
        self.assertFalse(status["publication_claims_unlocked"])
        self.assertFalse(status["paper_gates"]["stable_general_theory_licensed"])
        self.assertLess(status["eligible_transfer_case_count"], 2)
        self.assertTrue(claims["claims"])
        self.assertTrue(all(not row["general_theory_language_licensed"] for row in claims["claims"]))

    def test_status_compiler_tracks_inputs_by_hash(self):
        status, claims = _module().compile_status(ROOT)
        self.assertGreaterEqual(len(status["input_artifacts"]), 10)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in status["input_artifacts"]))
        self.assertEqual(len(claims["source_artifacts"]), 2)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in claims["source_artifacts"]))


if __name__ == "__main__":
    unittest.main()
