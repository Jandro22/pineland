from collections import deque
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.analytics import district_control_distribution
from pineland_sim.config import SocialNetworkConfig
from pineland_sim.networks import (
    bridge_target_community_weights,
    language_compatibility,
    locality_social_aggregation,
    network_diagnostics,
    network_snapshot,
)


class SocialNetworkTests(unittest.TestCase):
    def config(self, **network_overrides):
        network = SocialNetworkConfig(**network_overrides)
        return SimulationConfig(agent_count=800, locality_count=24, horizon_days=2,
                                seed=741, social_network=network)

    def test_language_compatibility_uses_best_shared_language(self):
        first = {"FS": .8, "AR": .2, "VE": .1, "TA": 0}
        second = {"FS": .4, "AR": .9, "VE": .1, "TA": 0}
        self.assertEqual(language_compatibility(first, second), .4)

    def test_membership_households_edges_and_community_connectivity(self):
        world = generate_pineland(self.config())
        self.assertTrue(world.social_communities)
        self.assertTrue(world.social_edges)
        self.assertTrue(all(person.community_id for person in world.persons.values()))
        for household in world.households.values():
            self.assertEqual(len({world.persons[x].community_id for x in household.member_ids}), 1)
        for community in world.social_communities.values():
            self.assertTrue(all(world.persons[x].home_locality_id == community.locality_id
                                for x in community.member_ids))
            if len(community.member_ids) < 2:
                continue
            allowed = set(community.member_ids)
            reached = {community.member_ids[0]}
            queue = deque(reached)
            while queue:
                current = queue.popleft()
                for neighbor in world.social_neighbors[current]:
                    if neighbor in allowed and neighbor not in reached:
                        reached.add(neighbor)
                        queue.append(neighbor)
            self.assertEqual(reached, allowed)
        world.assert_invariants()

    def test_network_generation_is_deterministic_and_has_bridges(self):
        first = generate_pineland(self.config())
        second = generate_pineland(self.config())
        self.assertEqual(first.social_edges, second.social_edges)
        diagnostics = network_diagnostics(first)
        self.assertGreater(diagnostics["bridge_edges"], 0)
        self.assertGreater(diagnostics["cross_local_bridge_edges"], 0)
        self.assertGreater(diagnostics["represented_cross_local_bridge_relationship_mass"], 0)
        self.assertGreater(diagnostics["mean_degree"], 2)
        self.assertGreater(diagnostics["mean_language_compatibility"], 0)
        first_edge = next(iter(first.social_edges.values()))
        self.assertAlmostEqual(first_edge.represented_relationships,
                               next(iter(first.persons.values())).weight)

    def test_bridge_target_opportunity_uses_represented_mass_not_community_count(self):
        world = generate_pineland(self.config())
        community = next(
            item for item in world.social_communities.values()
            if world.adjacency[item.locality_id]
        )
        weights = bridge_target_community_weights(world, community)
        self.assertTrue(weights)
        cross_mass = sum(
            weight for community_id, weight in weights.items()
            if world.social_communities[community_id].locality_id != community.locality_id
        )
        self.assertGreater(cross_mass, 0.0)

    def test_interlocality_bridge_share_does_not_collapse_at_finer_resolution(self):
        shares = []
        for agents in (1_000, 5_000):
            world = generate_pineland(SimulationConfig(
                agent_count=agents, locality_count=72, horizon_days=1,
                seed=20260905,
            ))
            bridge_edges = [edge for edge in world.social_edges.values()
                            if "bridge" in edge.layers]
            cross = [
                edge for edge in bridge_edges
                if world.persons[edge.person_a_id].residence_locality_id !=
                world.persons[edge.person_b_id].residence_locality_id
            ]
            shares.append(len(cross) / max(1, len(bridge_edges)))
        self.assertGreater(min(shares), 0.10)
        self.assertLess(abs(shares[0] - shares[1]), 0.10)

    def test_debug_snapshot_exposes_edge_semantics_and_context(self):
        world = generate_pineland(self.config())
        person_id = next(iter(world.persons))
        community_id = world.persons[person_id].community_id
        snapshot = network_snapshot(world, [person_id], [community_id])
        agent = snapshot["agents"][person_id]
        self.assertIn("aggregate channel", snapshot["edge_semantics"])
        self.assertEqual(agent["community_id"], community_id)
        self.assertIn("effective_edge_weight", agent["neighbors"][0])

    def test_social_influence_changes_behavior_and_writes_provenance(self):
        world = generate_pineland(self.config(behavior_update_rate=1.0))
        result = Simulation(world).run(until=1)
        social_events = [entry for entry in result.world.event_log
                         if entry.event_type == "social_influence"]
        self.assertTrue(social_events)
        self.assertGreater(social_events[-1].true_state_delta["behavior_changes"], 0)
        self.assertTrue(any(item.mechanism == "social_network_influence"
                            for item in result.world.causal_ledger))
        self.assertTrue(any(person.social_exposure for person in result.world.persons.values()))

    def test_locality_and_district_diagnostics_preserve_dispersion(self):
        world = generate_pineland(self.config())
        Simulation(world).run(until=1)
        locality_id = next(iter(world.localities))
        local = locality_social_aggregation(world, locality_id)
        district = district_control_distribution(world, world.localities[locality_id].district_id)
        self.assertEqual(set(local), {"government_cooperation", "insurgent_sympathy", "community_variance"})
        self.assertGreaterEqual(district["variance"], 0)
        self.assertLessEqual(district["minimum"], district["maximum"])


if __name__ == "__main__":
    unittest.main()
