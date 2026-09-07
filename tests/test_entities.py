import math
import unittest

from pineland_sim.entities import ControlVector, clamp, logistic


class EntityTests(unittest.TestCase):
    def test_clamp_preserves_boundary_and_nan_semantics(self):
        self.assertEqual(clamp(-1.0), 0.0)
        self.assertEqual(clamp(0.25), 0.25)
        self.assertEqual(clamp(2.0), 1.0)
        self.assertEqual(clamp(float("nan")), 0.0)
        self.assertEqual(clamp(5.0, 2.0, 1.0), 1.0)

    def test_control_is_bounded_and_geometric(self):
        control = ControlVector(*([0.5] * 7))
        control.update({"physical": 2, "social": -2})
        self.assertEqual(control.physical, 1)
        self.assertEqual(control.social, 0)
        self.assertGreaterEqual(control.effective(), 0)
        self.assertLessEqual(control.effective(), 1)

    def test_effective_control_respects_exact_geometric_boundaries(self):
        self.assertEqual(ControlVector().effective(), 0.0)
        self.assertEqual(ControlVector(*([1.0] * 7)).effective(), 1.0)
        self.assertEqual(ControlVector(1, 1, 1, 1, 1, 1, 0).effective(), 0.0)

    def test_zero_weight_dimension_does_not_collapse_effective_control(self):
        dimensions = (
            "formal", "physical", "administrative", "legal",
            "fiscal", "social", "expected",
        )
        weights = {dimension: 1.0 for dimension in dimensions}
        weights["formal"] = 0.0
        control = ControlVector(0.0, *([0.5] * 6))
        self.assertAlmostEqual(control.effective(weights), 0.5)

    def test_invalid_effective_control_weights_fail_closed(self):
        with self.assertRaises(ValueError):
            ControlVector(*([0.5] * 7)).effective({"physical": 1.0})
        with self.assertRaises(ValueError):
            ControlVector(*([0.5] * 7)).effective({})
        with self.assertRaises(ValueError):
            ControlVector(*([0.5] * 7)).effective({
                "formal": -1.0, "physical": 1.0, "administrative": 1.0,
                "legal": 1.0, "fiscal": 1.0, "social": 1.0, "expected": 1.0,
            })
        with self.assertRaises(ValueError):
            ControlVector(*([0.5] * 7)).effective({
                "formal": float("nan"), "physical": 1.0, "administrative": 1.0,
                "legal": 1.0, "fiscal": 1.0, "social": 1.0, "expected": 1.0,
            })

    def test_logistic_is_stable_at_extremes(self):
        self.assertAlmostEqual(logistic(1000), 1.0)
        self.assertAlmostEqual(logistic(-1000), 0.0)
        self.assertAlmostEqual(logistic(0), 0.5)


if __name__ == "__main__":
    unittest.main()

