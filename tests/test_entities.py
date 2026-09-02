import math
import unittest

from pineland_sim.entities import ControlVector, logistic


class EntityTests(unittest.TestCase):
    def test_control_is_bounded_and_geometric(self):
        control = ControlVector(*([0.5] * 7))
        control.update({"physical": 2, "social": -2})
        self.assertEqual(control.physical, 1)
        self.assertEqual(control.social, 0)
        self.assertGreaterEqual(control.effective(), 0)
        self.assertLessEqual(control.effective(), 1)

    def test_logistic_is_stable_at_extremes(self):
        self.assertAlmostEqual(logistic(1000), 1.0)
        self.assertAlmostEqual(logistic(-1000), 0.0)
        self.assertAlmostEqual(logistic(0), 0.5)


if __name__ == "__main__":
    unittest.main()

