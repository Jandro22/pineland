import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import Observation
from pineland_sim.information import (
    belief_error,
    decay_information,
    detection_probability,
    fuse_observation,
    generate_background_observations,
    information_age,
    information_diagnostics,
    observe_target,
    process_information,
)
from pineland_sim.world import seeded_rng


class InformationTests(unittest.TestCase):
    def setUp(self):
        self.world = generate_pineland(SimulationConfig(
            agent_count=500, locality_count=24, horizon_days=5, seed=1404,
        ))
        self.world.config.information.attribution_error_rate = 0.0
        self.government = self.world.formations["FDF-01"]
        self.insurgent = self.world.formations["PRF-01"]
        self.insurgent.locality_id = self.government.locality_id

    def test_observation_is_first_class_and_has_provenance_and_age_decay(self):
        observation = observe_target(
            self.world, "fdf", self.government.formation_id, "PATROL:test", "patrol",
            self.government.locality_id, "insurgent", 0.0, random.Random(1),
            self.insurgent.formation_id, force_detection=True,
        )
        self.assertIsNotNone(observation)
        self.assertEqual(observation.timestamp, 0.0)
        self.assertIn("source_type", observation.provenance)
        self.assertGreater(observation.effective_confidence(0),
                           observation.effective_confidence(10))
        self.assertTrue(self.world.information_relays)

    def test_contradictory_reports_reduce_confidence_without_last_write_wins(self):
        for index, detected in enumerate((True, False)):
            observe_target(
                self.world, "fdf", self.government.formation_id, f"source:{index}",
                "contact", self.government.locality_id, "insurgent", 0.0,
                random.Random(index), self.insurgent.formation_id,
                force_detection=detected,
            )
        belief = next(item for key, item in self.world.node_presence_beliefs.items()
                      if key[-1] == self.insurgent.formation_id)
        self.assertGreater(belief.contradiction_index, 0)
        self.assertGreater(belief.presence_estimate, 0)
        self.assertLess(belief.presence_estimate, 1)
        self.assertLess(belief.confidence, .35)

    def test_command_relay_delays_headquarters_knowledge_but_keeps_local_knowledge(self):
        observation = observe_target(
            self.world, "fdf", self.government.formation_id, "PATROL:relay", "patrol",
            self.government.locality_id, "insurgent", 0.0, random.Random(2),
            self.insurgent.formation_id, force_detection=True,
        )
        relay = next(iter(self.world.information_relays.values()))
        local = [item for key, item in self.world.node_presence_beliefs.items()
                 if key[0] == self.government.formation_id and
                 key[2].startswith(self.government.locality_id)]
        self.assertTrue(local)
        self.assertEqual(relay.status, "in_transit")
        process_information(self.world, relay.arrives_at + .01, random.Random(3))
        self.assertEqual(relay.status, "delivered")
        headquarters = [item for key, item in self.world.presence_beliefs.items()
                        if key[0] == "fdf" and key[-1] == self.insurgent.formation_id]
        self.assertTrue(headquarters)
        self.assertGreaterEqual(max(item.evidence_count for item in headquarters), 1)

    def test_social_cooperation_adds_reports_without_changing_physical_presence(self):
        low = self.world.clone()
        high = self.world.clone()
        for community in low.social_communities.values():
            community.government_cooperation = 0.0
        for community in high.social_communities.values():
            community.government_cooperation = 1.0
        low_obs = generate_background_observations(low, 0.0, seeded_rng(low.config, "social-test"))
        high_obs = generate_background_observations(high, 0.0, seeded_rng(high.config, "social-test"))
        low_social = sum(item.source_type in {"civilian", "social_network"} for item in low_obs)
        high_social = sum(item.source_type in {"civilian", "social_network"} for item in high_obs)
        self.assertGreater(high_social, low_social)
        self.assertEqual(low.formations["FDF-01"].personnel,
                         high.formations["FDF-01"].personnel)

    def test_language_reduces_but_does_not_delete_information(self):
        localities = sorted(self.world.localities)
        fs = next(item for item in localities
                  if self.world.districts[self.world.localities[item].district_id].language_pattern == "FS")
        non_fs = next(item for item in localities
                      if self.world.districts[self.world.localities[item].district_id].language_pattern != "FS")
        from pineland_sim.information import language_comprehension
        fs_value = language_comprehension(self.world, "government", fs, "civilian")
        non_fs_value = language_comprehension(self.world, "government", non_fs, "civilian")
        self.assertGreater(fs_value, non_fs_value)
        self.assertGreater(non_fs_value, 0)

    def test_belief_error_and_information_age_are_analyst_diagnostics(self):
        process_information(self.world, 0.0, random.Random(4))
        age_before = information_age(self.world, "fdf", self.government.locality_id,
                                     target_actor_id="insurgent", time=0.0)
        decay_information(self.world, 5.0)
        age_after = information_age(self.world, "fdf", self.government.locality_id,
                                    target_actor_id="insurgent", time=5.0)
        self.assertGreaterEqual(age_after, age_before)
        diagnostics = information_diagnostics(self.world)
        self.assertIn("belief_error", diagnostics)
        self.assertIn("information_age", diagnostics)
        self.assertGreaterEqual(belief_error(self.world, "fdf", self.government.locality_id), 0)

    def test_null_world_has_no_insurgent_observation_artifact(self):
        world = generate_pineland(SimulationConfig(
            agent_count=500, locality_count=24, horizon_days=2,
            seed=1404, include_insurgency=False,
        ))
        Simulation(world).run(until=1)
        self.assertFalse(any(item.target_actor_id == "insurgent" for item in world.observations.values()))
        self.assertFalse(any(formation.organization_id == "insurgent"
                             for formation in world.formations.values()))
        world.assert_invariants()

    def test_detection_probability_is_conditioned_and_bounded(self):
        value = detection_probability(
            self.world, self.government.formation_id, self.insurgent.formation_id,
            self.government.locality_id, "patrol",
        )
        self.assertGreater(value, 0)
        self.assertLess(value, 1)

    def test_information_trajectory_is_reproducible(self):
        first = Simulation(self.world.clone()).run(until=2).world
        second = Simulation(self.world.clone()).run(until=2).world
        self.assertEqual(first.observations, second.observations)
        self.assertEqual(first.information_relays, second.information_relays)
        self.assertEqual(first.information_detections, second.information_detections)


if __name__ == "__main__":
    unittest.main()
