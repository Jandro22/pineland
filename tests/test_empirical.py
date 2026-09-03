import json
from pathlib import Path
import tempfile
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.empirical import (RawObservation, aggregate_observations,
    build_case_package, case_catalog, load_case_package, load_raw_observations,
    recorded_vs_true_metrics, save_case_package)
from pineland_sim.validation import (fragmentation_forensic, parameter_recovery_experiment,
    question_parameter_subset, question_specific_registry)


class EmpiricalTests(unittest.TestCase):
    def test_raw_data_transform_retains_formula_ids_uncertainty_and_hash(self):
        rows = [RawObservation("a", "case", "t1", "g1", "events", 2, "source", recorded_uncertainty=.5),
                RawObservation("b", "case", "t2", "g1", "events", 4, "source", recorded_uncertainty=.5)]
        target, transform = aggregate_observations(rows, "event_frequency", "mean", uncertainty=.75,
                                                    assumptions=("equal observation windows",))
        self.assertEqual(target.value, 3)
        self.assertEqual(target.uncertainty, .75)
        self.assertEqual(transform.input_observation_ids, ("a", "b"))
        self.assertIn("equal observation windows", transform.assumptions)
        self.assertEqual(len(transform.source_hash), 64)

    def test_case_package_round_trip_and_missingness_are_explicit(self):
        rows = [RawObservation("a", "case", "t1", "g1", "events", 2, "source")]
        package = build_case_package("case", "Example", rows,
            [{"measure": "events", "metric": "event_frequency", "uncertainty": .2}],
            missing_metrics=("recurrence",), metadata={"family": "conflict_events", "source": "test"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            save_case_package(package, path)
            loaded = load_case_package(path)
        self.assertEqual(loaded.target_contract()["missing_metrics"], ["recurrence"])
        self.assertEqual(loaded.transformations[0].output_metric, "event_frequency")

    def test_csv_loader_preserves_recorded_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.csv"
            path.write_text("observation_id,case_id,timestamp,measure,value,source,recorded_uncertainty\na,c,t,events,3,src,0.4\n", encoding="utf-8")
            rows = load_raw_observations(path)
        self.assertEqual(rows[0].value, 3)
        self.assertEqual(rows[0].source, "src")
        self.assertEqual(rows[0].recorded_uncertainty, .4)

    def test_recorded_metrics_are_distinct_observation_layer(self):
        config = SimulationConfig(agent_count=120, locality_count=17, horizon_days=2, seed=1111)
        world = Simulation(generate_pineland(config)).run(until=2).world
        metrics = recorded_vs_true_metrics(world)
        self.assertIn("true", metrics["event_count"])
        self.assertIn("recorded", metrics["event_count"])
        self.assertGreaterEqual(metrics["event_count"]["recorded"], 0)

    def test_catalog_reports_case_metadata(self):
        result = case_catalog(["scenarios/cases/illustrative-pineland-case.json"])
        self.assertEqual(result["cases"][0]["case_id"], "illustrative-pineland")
        self.assertIn("organization_fragmentation", result["cases"][0]["missing_metrics"])

    def test_question_specific_registry_is_strict_subset(self):
        config = SimulationConfig(agent_count=100, locality_count=17, horizon_days=1)
        result = question_specific_registry("fragmentation", config)
        self.assertEqual(len(result["parameters"]), 4)
        self.assertIn("organization_ecology.split_base_hazard",
                      [item["code_name"] for item in result["parameters"]])
        with self.assertRaises(ValueError):
            question_parameter_subset("unknown question")

    def test_fragmentation_forensic_returns_structural_diagnosis_fields(self):
        config = SimulationConfig(agent_count=100, locality_count=17, horizon_days=1, seed=1212)
        result = fragmentation_forensic(config, empirical_target=1, samples=3, repetitions=1)
        self.assertIn(result["diagnosis"], {
            "parameter problem: at least one focused lever can reproduce the target",
            "parameter problem with weak identifiability",
            "structural model problem or measurement mismatch"})
        self.assertIn("identifiability", result)

    def test_synthetic_parameter_recovery_exposes_truth_and_error(self):
        config = SimulationConfig(agent_count=100, locality_count=17, horizon_days=1, seed=1313)
        result = parameter_recovery_experiment(config,
            ["recruitment_rate", "contact_rate"], samples=3, repetitions=1)
        self.assertEqual(set(result["truth"]), set(result["recovered"]))
        self.assertIn(result["status"], {"recovered", "partially recovered", "not recovered"})
        self.assertIn("normalized_error", result["comparison"]["contact_rate"])


if __name__ == "__main__":
    unittest.main()
