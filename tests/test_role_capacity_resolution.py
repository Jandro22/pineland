import random
import unittest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.foreign_affairs import (
    _foreign_belief_update,
    _interpreter_channel_quality,
    interpreter_channel_capacity,
)
from pineland_sim.information import generate_background_observations
from pineland_sim.networks import community_bridge_capacity
from pineland_sim.organization_ecology import _mobilization_score
from pineland_sim.political_order import local_elite_access_capacity


class ExplicitRoleCapacityResolutionTests(unittest.TestCase):
    """Adversarial checks for roles that must not be raw sampled-person counts."""

    @classmethod
    def setUpClass(cls):
        # Same generated geography/demography and seed; only representative
        # resolution changes.  Three agents deliberately leaves most populated
        # localities without a sampled resident, while 300 fills all of them.
        cls.coarse = generate_pineland(
            SimulationConfig(
                agent_count=3,
                locality_count=17,
                horizon_days=1,
                seed=20260904,
            )
        )
        cls.fine = generate_pineland(
            SimulationConfig(
                agent_count=300,
                locality_count=17,
                horizon_days=1,
                seed=20260904,
            )
        )

    def test_bridge_capacity_is_fractional_represented_mass_not_minimum_one_person(self):
        for world in (self.coarse, self.fine):
            total_capacity = sum(
                community_bridge_capacity(world, community)
                for community in world.social_communities.values()
            )
            self.assertAlmostEqual(
                total_capacity,
                world.weighted_population() * world.config.social_network.bridge_fraction,
                places=6,
            )

        coarse_community = next(iter(self.coarse.social_communities.values()))
        # At this deliberately extreme resolution there is no other sampled
        # community to attach a graph edge to.  The represented brokerage
        # capability nevertheless remains nonzero rather than disappearing.
        self.assertFalse(coarse_community.bridge_member_ids)
        self.assertGreater(
            community_bridge_capacity(self.coarse, coarse_community), 0.0
        )

    def test_bridge_mobilization_effect_is_invariant_to_sampled_anchor_count(self):
        effects = []
        for base in (self.coarse, self.fine):
            world = base.clone()
            community = next(iter(world.social_communities.values()))
            community.cohesion = .3
            community.insurgent_sympathy = .1
            for person_id in community.member_ids:
                person = world.persons[person_id]
                person.grievance = .2
                person.political_access = .5
                person.organization_id = None
                person.public_behavior = "neutral"
            score_with_bridge, _ = _mobilization_score(world, community)
            world.config.social_network.bridge_fraction = 0.0
            score_without_bridge, _ = _mobilization_score(world, community)
            effects.append(score_with_bridge - score_without_bridge)
        self.assertAlmostEqual(effects[0], effects[1], places=12)
        self.assertAlmostEqual(effects[0], .03, places=12)

    def test_elite_access_is_locality_capacity_not_number_of_elite_tokens(self):
        coarse_occupied = {
            person.residence_locality_id for person in self.coarse.persons.values()
        }
        empty_localities = [
            locality_id for locality_id in self.coarse.localities
            if locality_id not in coarse_occupied
        ]
        self.assertTrue(empty_localities)
        for locality_id in self.coarse.localities:
            self.assertAlmostEqual(
                local_elite_access_capacity(self.coarse, locality_id),
                local_elite_access_capacity(self.fine, locality_id),
                places=12,
            )
        # The coarse world has no sampled elite anchor in these populated
        # localities, but substantive elite access remains present.
        locality_id = empty_localities[0]
        self.assertFalse(
            any(elite.locality_id == locality_id
                for elite in self.coarse.local_elites.values())
        )
        self.assertGreater(self.coarse.localities[locality_id].population, 0.0)
        self.assertEqual(local_elite_access_capacity(self.coarse, locality_id), 1.0)

    def test_interpretation_capacity_survives_missing_sampled_resident(self):
        coarse_capacities = {
            border_id: interpreter_channel_capacity(self.coarse, border)
            for border_id, border in self.coarse.border_segments.items()
        }
        fine_capacities = {
            border_id: interpreter_channel_capacity(self.fine, border)
            for border_id, border in self.fine.border_segments.items()
        }
        self.assertEqual(set(coarse_capacities), set(fine_capacities))
        for border_id, coarse_capacity in coarse_capacities.items():
            self.assertAlmostEqual(
                coarse_capacity, fine_capacities[border_id], places=12
            )

        coarse_occupied = {
            person.residence_locality_id for person in self.coarse.persons.values()
        }
        border = next(
            border for border in self.coarse.border_segments.values()
            if border.locality_id not in coarse_occupied
        )
        self.assertFalse(
            any(
                broker.locality_id == border.locality_id
                and broker.foreign_state_id == border.foreign_state_id
                for broker in self.coarse.interpreter_brokers.values()
            )
        )
        self.assertGreater(interpreter_channel_capacity(self.coarse, border), 0.0)
        self.assertGreater(_interpreter_channel_quality(self.coarse, border), 0.0)

        state = self.coarse.foreign_states[border.foreign_state_id]
        baseline_without_interpretation = .2 + .2 * border.language_overlap
        _foreign_belief_update(self.coarse, state, 1.0, random.Random(9))
        belief = self.coarse.foreign_beliefs[(state.state_id, border.locality_id)]
        self.assertGreater(belief.confidence, baseline_without_interpretation)

    def test_empty_populated_locality_keeps_elite_and_interpreter_information_channels(self):
        world = self.coarse.clone()
        occupied = {
            person.residence_locality_id for person in world.persons.values()
        }
        locality_id = next(
            locality_id for locality_id, locality in world.localities.items()
            if locality_id not in occupied
            and "/" in world.districts[locality.district_id].language_pattern
        )
        locality = world.localities[locality_id]
        locality.administrative_capacity = 1.0
        locality.governance["representation"] = 1.0
        world.config.information.administrative_report_rate = 1.0
        world.config.information.elite_report_rate = 1.0
        world.config.information.interpreter_report_rate = 1.0
        observations = generate_background_observations(
            world, 1.0, random.Random(20260904)
        )
        source_types = {
            observation.source_type for observation in observations
            if observation.locality_id == locality_id
        }
        self.assertIn("administrative", source_types)
        self.assertIn("political_elite", source_types)
        self.assertIn("interpreter", source_types)


if __name__ == "__main__":
    unittest.main()
