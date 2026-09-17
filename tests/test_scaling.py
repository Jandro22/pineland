import unittest

from pineland_sim import SimulationConfig
from pineland_sim.scaling import compare_agent_scales, compare_political_onset_ensembles


class ScaleSensitivityTests(unittest.TestCase):
    def test_macro_behavior_is_broadly_stable_across_small_resolution_proxy(self):
        config = SimulationConfig(locality_count=24, seed=991, horizon_days=2)
        result = compare_agent_scales(config, [400, 1_200], 2)
        self.assertEqual(len(result["runs"]), 2)
        self.assertLessEqual(
            abs(
                result["runs"][0]["represented_population"]
                - result["runs"][1]["represented_population"]
            ),
            1e-6,
        )
        comparison = result["comparisons"][0]
        self.assertLess(abs(comparison["government_control_difference"]), .05)
        self.assertLess(abs(comparison["insurgent_control_difference"]), .05)
        self.assertLess(comparison["maximum_behavior_share_difference"], .15)

    def test_political_onset_scale_check_uses_ensembles(self):
        config = SimulationConfig(agent_count=200, locality_count=24, horizon_days=1,
                                  include_insurgency=False)
        result = compare_political_onset_ensembles(config, [200, 400], 1, [3, 4])
        self.assertEqual(len(result["ensembles"]), 2)
        self.assertEqual(len(result["ensembles"][0]["samples"]), 2)
        self.assertIn("onset_probability_difference", result["comparisons"][0])


if __name__ == "__main__":
    unittest.main()
