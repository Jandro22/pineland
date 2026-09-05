from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "studies" / "research_program" / "scripts" / "audit_program.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_program", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ResearchProgramTests(unittest.TestCase):
    def test_topology_null_relabels_both_endpoints_without_loops(self):
        scripts = [
            (ROOT / "studies/research_program/scripts/build_event_only_spatial_signatures.py", "_shuffle_neighbors"),
            (ROOT / "studies/research_program/scripts/build_harmonized_historical_signatures.py", "_shuffle"),
            (ROOT / "studies/research_program/scripts/build_actor_continuity_diagnostic.py", "_shuffle"),
        ]
        graph = {
            "a": {"b", "c"},
            "b": {"a", "c"},
            "c": {"a", "b", "d"},
            "d": {"c"},
        }
        original_degrees = sorted(len(values) for values in graph.values())
        for script, function_name in scripts:
            spec = importlib.util.spec_from_file_location(f"shuffle_{script.stem}", script)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            shuffled = getattr(module, function_name)(graph, 20260905)
            self.assertEqual(set(shuffled), set(graph))
            self.assertEqual(sorted(len(values) for values in shuffled.values()), original_degrees)
            self.assertTrue(all(unit not in values for unit, values in shuffled.items()))
            self.assertTrue(
                all(other in shuffled[unit] for unit, values in shuffled.items() for other in values)
            )

    def test_assignment_sensitivity_keeps_unassigned_events_missing(self):
        path = ROOT / "studies/research_program/historical_assignment_sensitivity.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        afghanistan = next(item for item in report["cases"] if item["case_id"] == "afghanistan_2004_2021")
        self.assertEqual(
            afghanistan["unassigned_rows"],
            afghanistan["raw_event_rows"] - afghanistan["assigned_rows"],
        )
        self.assertLess(afghanistan["assignment_coverage"], 0.5)
        self.assertEqual(report["status"], "descriptive_assignment_coverage_not_imputation")

    def test_eight_seed_contact_challenge_is_synthetic_and_provenanced(self):
        artifact = json.loads(
            (ROOT / "studies/research_program/contact_challenge_eight_seed_replication.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = json.loads(
            (ROOT / "studies/research_program/contact_challenge_eight_seed_replication_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(artifact["seed_count"], 8)
        self.assertEqual(artifact["cell_count"], 32)
        self.assertTrue(artifact["all_seeds_have_latent_contacts"])
        self.assertTrue(artifact["presence_memory_contrast_positive_every_seed"])
        self.assertFalse(artifact["core_certificate"]["passed"])
        self.assertEqual(manifest["status"], "synthetic_replication_provenance_manifest")
        self.assertFalse(manifest["core_change_licensed"])

    def test_authoritative_certificate_is_valid_and_drift_fails_closed(self):
        report = _module().audit_program(ROOT)
        self.assertTrue(report["certificate_valid"], report)
        self.assertEqual(
            report["passed"],
            all(all(section.values()) for section in report["sections"].values()),
            report,
        )
        self.assertFalse(report["calibration_licensed"])
        self.assertFalse(report["coin_inference_licensed"])

    def test_case_ladder_preserves_falsification_and_future_uncertainty(self):
        path = ROOT / "studies" / "research_program" / "case_ladder.json"
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(cases[0]["status"], "completed_falsification")
        self.assertEqual(cases[1]["role"], "first_transfer")
        self.assertTrue(all(case["status"] in {"not_started", "data_construction", "preregistered"} for case in cases[2:]))
        self.assertTrue(all(case["status"] == "data_construction" for case in cases[2:]))

    def test_core_change_rule_rejects_case_fit_as_justification(self):
        path = ROOT / "studies" / "research_program" / "core_freeze.json"
        freeze = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(freeze["change_rule"]["case_fit_is_sufficient"])
        self.assertEqual(
            freeze["change_rule"]["required_classification"],
            "general_defect_or_preregistered_structural_change",
        )
        self.assertTrue(freeze["change_rule"]["historical_revalidation_required"])

    def test_theory_protocol_keeps_mechanisms_unresolved_until_transfer(self):
        path = ROOT / "studies" / "research_program" / "theory_extraction_protocol.json"
        protocol = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(all(status == "unresolved" for status in protocol["mechanism_statuses"].values()))
        self.assertIn("two cases", " ".join(protocol["survival_criteria"]))

    def test_outcome_contract_keeps_control_separate_from_violence(self):
        path = ROOT / "studies" / "research_program" / "outcome_measurement_contract.json"
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("control", contract["outcomes"]["violence"]["proxy_forbidden"])
        self.assertIn("violence", contract["outcomes"]["control"]["proxy_forbidden"])

    def test_moonshot_checklist_is_explicit_and_not_falsely_complete(self):
        path = ROOT / "studies/research_program/moonshot_checklist.json"
        checklist = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(checklist["stages"]), 8)
        afghanistan = next(stage for stage in checklist["stages"] if stage["name"] == "afghanistan_first_transfer")
        self.assertIn(afghanistan["status"], {
            "complete_falsification", "legacy_falsification_revalidation_required"
        })
        self.assertTrue(afghanistan["remaining"])

    def test_legacy_nepal_path_cannot_certify_final_rescore(self):
        freeze = json.loads(
            (ROOT / "studies" / "research_program" / "core_freeze.json").read_text(
                encoding="utf-8"
            )
        )
        detail = _module().verify_evidence(
            ROOT,
            freeze["freeze_basis"]["nepal_final_rescore"],
            freeze["model_sha256"],
        )
        self.assertFalse(detail["valid"])
        self.assertEqual(detail["reason"], "legacy_path_only_unverified")

        # A later verified rescore may legitimately supersede the legacy path,
        # but only through an explicit content-addressed evidence record.
        current = freeze.get("evidence_records", {}).get("nepal_final_rescore")
        if current is not None:
            self.assertIsInstance(current, dict)
            self.assertNotEqual(current.get("status"), "legacy_path_only_unverified")


if __name__ == "__main__":
    unittest.main()
