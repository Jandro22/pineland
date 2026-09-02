import unittest

from pineland_sim import SimulationConfig
from pineland_sim.scaling import compare_agent_scales


class ScaleSensitivityTests(unittest.TestCase):
    def test_macro_behavior_is_broadly_stable_across_small_resolution_proxy(self):
        config = SimulationConfig(locality_count=24, seed=991, horizon_days=2)
        result = compare_agent_scales(config, [400, 1_200], 2)
        self.assertEqual(len(result["runs"]), 2)
        self.assertAlmostEqual(result["runs"][0]["represented_population"],
                               result["runs"][1]["represented_population"])
        comparison = result["comparisons"][0]
        self.assertLess(abs(comparison["government_control_difference"]), .05)
        self.assertLess(abs(comparison["insurgent_control_difference"]), .05)
        self.assertLess(comparison["maximum_behavior_share_difference"], .15)


if __name__ == "__main__":
    unittest.main()
