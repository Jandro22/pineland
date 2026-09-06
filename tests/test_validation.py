import json
from pathlib import Path
import tempfile
import unittest

from pineland_sim import SimulationConfig, empirical_target_contract, parameter_registry
from pineland_sim.validation import (SAMPLE_BOUNDS, calibrate_and_validate,
    bargaining_stress_test, global_sensitivity, model_ladder, practical_identifiability, registry_document,
    score_targets, set_parameter)


def tiny_config():
    return SimulationConfig(agent_count=100, locality_count=17, horizon_days=1, seed=1010)


class ValidationTests(unittest.TestCase):
    def test_registry_covers_all_scalar_configuration_fields_and_marks_priors(self):
        registry = parameter_registry(tiny_config())
        names = {item.code_name for item in registry}
        self.assertIn("peace_process.implementation_rate", names)
        self.assertIn("combat.base_attrition_rate", names)
        recruitment = next(x for x in registry if x.code_name == "recruitment_rate")
        self.assertEqual(recruitment.calibration_status, "uncalibrated")
        membership_exit = next(x for x in registry if x.code_name == "membership_exit_rate")
        self.assertEqual(membership_exit.units, "rate/day")
        self.assertEqual(membership_exit.calibration_status, "uncalibrated")
        legacy_members = next(
            x for x in registry
            if x.code_name == "organization_ecology.minimum_proto_members"
        )
        self.assertEqual(
            legacy_members.assumption_type,
            "compatibility-only deprecated field",
        )
        self.assertEqual(legacy_members.calibration_status, "non-inferential")
        self.assertIn("parameters", registry_document(tiny_config()))

    def test_legacy_config_maps_common_recruitment_exit_rate(self):
        values = tiny_config().to_dict()
        values["recruitment_rate"] = 0.0023
        values.pop("membership_exit_rate")
        loaded = SimulationConfig.from_dict(values)
        self.assertEqual(loaded.recruitment_rate, 0.0023)
        self.assertEqual(loaded.membership_exit_rate, 0.0023)

    def test_target_contract_requires_declared_metrics_and_scores_errors(self):
        contract = empirical_target_contract({"government_control": .5}, "control", "source", "case-A", "training")
        score = score_targets({"government_control": .5}, contract)
        self.assertEqual(score["mean_normalized_error"], 0)
        with self.assertRaises(ValueError):
            empirical_target_contract({"not_a_metric": 1})

    def test_parameter_setter_updates_nested_configuration(self):
        config = tiny_config()
        set_parameter(config, "peace_process.implementation_rate", .11)
        self.assertEqual(config.peace_process.implementation_rate, .11)

    def test_latin_hypercube_sensitivity_is_reproducible_and_contains_interactions(self):
        config = tiny_config()
        parameters = ["recruitment_rate", "peace_process.implementation_rate"]
        first = global_sensitivity(config, ["government_control"], samples=3, parameters=parameters)
        second = global_sensitivity(config, ["government_control"], samples=3, parameters=parameters)
        self.assertEqual(first, second)
        result = first["analysis"]["government_control"]
        self.assertEqual(set(result["main_effect_screen"]), set(parameters))
        self.assertIn("recruitment_rate × peace_process.implementation_rate", result["interaction_screen"])

    def test_identifiability_reports_all_supported_categories(self):
        sensitivity = {
            "parameters": ["recruitment_rate", "contact_rate"],
            "records": [
                {"parameters": {"recruitment_rate": SAMPLE_BOUNDS["recruitment_rate"][0],
                                "contact_rate": SAMPLE_BOUNDS["contact_rate"][0]},
                 "outcomes": {"government_control": .5}},
                {"parameters": {"recruitment_rate": SAMPLE_BOUNDS["recruitment_rate"][0] + .0001,
                                "contact_rate": SAMPLE_BOUNDS["contact_rate"][1]},
                 "outcomes": {"government_control": .5}},
            ],
        }
        target = empirical_target_contract({"government_control": .5}, "control")
        report = practical_identifiability(sensitivity, target)
        self.assertEqual(report["parameters"]["recruitment_rate"]["status"], "well constrained")
        self.assertEqual(report["parameters"]["contact_rate"]["status"], "non-identifiable")

    def test_calibration_scores_holdout_without_retuning(self):
        config = tiny_config()
        training = empirical_target_contract({"government_control": .55}, "control", split="training")
        holdout = empirical_target_contract({"insurgent_control": .001}, "control", split="holdout")
        result = calibrate_and_validate(config, training, holdout, samples=3,
                                        parameters=["recruitment_rate", "contact_rate"])
        self.assertIn("best_training_error", result["calibration"])
        self.assertIn("holdout_score", result["out_of_sample"])
        self.assertEqual(set(result["calibration"]["parameters"]), {"recruitment_rate", "contact_rate"})

    def test_model_ladder_includes_required_models_and_scores_same_contract(self):
        target = empirical_target_contract({"event_frequency": .01, "government_control": .5})
        result = model_ladder(tiny_config(), target)
        self.assertEqual(set(result["models"]), {"M0_random_null", "M1_self_exciting_proxy",
                                                   "M2_reduced_pineland", "M3_full_pineland"})
        self.assertIsNotNone(result["models"]["M3_full_pineland"]["score"])
        self.assertIn("mean_normalized_error", result["models"]["M3_full_pineland"]["score"])
        self.assertEqual(result["models"]["M0_random_null"]["capabilities"],
                         ["event_frequency", "event_spatial_concentration", "event_temporal_burstiness"])

    def test_bargaining_stress_test_breaks_agreement_ceiling(self):
        result = bargaining_stress_test(tiny_config(), replications=8, months=12)
        probabilities = [item["agreement_probability"] for item in result["regimes"]]
        self.assertEqual(len(probabilities), 5)
        self.assertLess(probabilities[0], probabilities[-1])


if __name__ == "__main__":
    unittest.main()
