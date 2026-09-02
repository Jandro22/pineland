import unittest

from pineland_sim import SimulationConfig, generate_pineland


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = SimulationConfig(agent_count=300, locality_count=34, horizon_days=5)

    def test_expected_world_shape_and_conservation(self):
        world = generate_pineland(self.config)
        self.assertEqual(len(world.districts), 17)
        self.assertEqual(len(world.localities), 34)
        self.assertEqual(len(world.persons), 300)
        self.assertTrue(all(d.locality_ids for d in world.districts.values()))
        self.assertAlmostEqual(world.weighted_population(), world.initial_population)
        world.assert_invariants()

    def test_generation_is_reproducible(self):
        first = generate_pineland(self.config)
        second = generate_pineland(self.config)
        self.assertEqual(first.summary(), second.summary())
        keys = sorted(first.localities)
        self.assertEqual(
            [first.localities[k].economic_output for k in keys],
            [second.localities[k].economic_output for k in keys],
        )


if __name__ == "__main__":
    unittest.main()

