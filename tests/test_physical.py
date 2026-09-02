import unittest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.physical import (
    decay_presence,
    recompute_microzone_control,
    zones_in_locality,
)
from pineland_sim.processes import ProcessEngine


class PhysicalModelTests(unittest.TestCase):
    def setUp(self):
        self.world = generate_pineland(SimulationConfig(
            agent_count=400, locality_count=24, horizon_days=2, seed=818
        ))

    def test_physical_graphs_are_connected_and_population_shares_sum(self):
        for locality_id in self.world.localities:
            zones = zones_in_locality(self.world, locality_id)
            self.assertGreaterEqual(len(zones), 3)
            self.assertAlmostEqual(sum(zone.population_share for zone in zones), 1.0)
            allowed = {zone.microzone_id for zone in zones}
            reached = {zones[0].microzone_id}
            frontier = list(reached)
            while frontier:
                current = frontier.pop()
                for neighbor in self.world.physical_neighbors[current]:
                    if neighbor in allowed and neighbor not in reached:
                        reached.add(neighbor)
                        frontier.append(neighbor)
            self.assertEqual(reached, allowed)

    def test_locality_control_is_aggregated_upward_from_zones(self):
        locality_id = next(iter(self.world.localities))
        zones = zones_in_locality(self.world, locality_id)
        for index, zone in enumerate(zones):
            zone.physical_control["government"] = index / max(1, len(zones) - 1)
        expected = sum(zone.population_share * zone.physical_control["government"] for zone in zones)
        # Changing locality state cannot push a value down into zones.
        self.world.localities[locality_id].control["government"].physical = .99
        observed = sum(zone.population_share * zone.physical_control["government"] for zone in zones)
        self.assertAlmostEqual(observed, expected)
        self.assertNotAlmostEqual(observed, .99)

    def test_slower_topology_reduces_response_generated_control(self):
        locality_id = next(iter(self.world.localities))
        baseline = recompute_microzone_control(self.world, locality_id, "government", 0)
        for edge in self.world.physical_edges.values():
            if self.world.microzones[edge.microzone_a_id].locality_id == locality_id:
                edge.travel_time_hours *= 8
        slower = recompute_microzone_control(self.world, locality_id, "government", 0)
        self.assertLess(slower, baseline)

    def test_presence_memory_decays(self):
        zone = next(iter(self.world.microzones.values()))
        zone.presence_memory["government"] = 1.0
        zone.presence_updated_at["government"] = 0.0
        remaining = decay_presence(zone, "government", 2.0, 2.0)
        self.assertAlmostEqual(remaining, 0.36787944117)

    def test_patrol_routes_to_perceived_need_not_true_weakness(self):
        patrol = next(iter(self.world.patrols.values()))
        current = patrol.current_microzone_id
        candidates = sorted(self.world.physical_neighbors[current])
        if len(candidates) < 2:
            self.skipTest("generated patrol origin has fewer than two routes")
        believed_weak, believed_strong = candidates[:2]
        actor = patrol.organization_id
        self.world.zone_beliefs[(actor, believed_weak)].physical_control_estimate = 0.0
        self.world.zone_beliefs[(actor, believed_strong)].physical_control_estimate = 1.0
        self.world.microzones[believed_weak].physical_control["government"] = 1.0
        self.world.microzones[believed_strong].physical_control["government"] = 0.0

        class MaxWeightRng:
            def random(self): return 0.5
            def normalvariate(self, mu, sigma): return mu
            def uniform(self, low, high): return low
            def choices(self, population, weights, k):
                return [population[max(range(len(weights)), key=weights.__getitem__)]]

        engine = ProcessEngine(self.world, MaxWeightRng())
        event = ScheduledEvent(0, 0, 0, "patrol", {"patrol_id": patrol.patrol_id})
        engine.execute(event)
        self.assertEqual(patrol.current_microzone_id, believed_weak)
        self.assertNotEqual(patrol.current_microzone_id, believed_strong)


if __name__ == "__main__":
    unittest.main()
