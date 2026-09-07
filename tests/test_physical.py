import unittest
import random

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.physical import (
    advance_patrol_presence_memory,
    decay_presence,
    recompute_contested_controls,
    recompute_microzone_control,
    zones_in_locality,
)
from pineland_sim.organization_ecology import split_organization
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

    def test_patrol_memory_scales_with_deployed_patrol_fraction_not_full_parent_force(self):
        base = self.world.clone()
        patrol_id = next(iter(base.patrols))
        memories = []

        class StableRng:
            def random(self): return 0.5
            def normalvariate(self, mu, sigma): return mu
            def uniform(self, low, high): return low
            def choices(self, population, weights, k): return [population[0]]

        for fraction in (.1, .6):
            world = base.clone()
            patrol = world.patrols[patrol_id]
            patrol.response_fraction = fraction
            patrol.available_at = 0.0
            patrol.presence_accounted_at = 0.0
            zone = world.microzones[patrol.current_microzone_id]
            zone.presence_memory.pop("government", None)
            zone.presence_updated_at.pop("government", None)
            world.time = .25
            ProcessEngine(world, StableRng()).on_patrol(
                "PATROL-FRACTION",
                ScheduledEvent(.25, 0, 0, "patrol", {"patrol_id": patrol_id}),
            )
            memories.append(zone.presence_memory["government"])
        self.assertGreater(memories[0], 0.0)
        self.assertAlmostEqual(memories[1] / memories[0], 6.0, places=9)

    def test_patrol_memory_is_invariant_to_accounting_slice_length(self):
        base = self.world.clone()
        patrol_id = next(iter(base.patrols))

        def prepare(world):
            patrol = world.patrols[patrol_id]
            patrol.available_at = 0.0
            patrol.presence_accounted_at = 0.0
            zone = world.microzones[patrol.current_microzone_id]
            zone.presence_memory["government"] = .2
            zone.presence_updated_at["government"] = 0.0
            return patrol, zone

        coarse = base.clone()
        _, coarse_zone = prepare(coarse)
        advance_patrol_presence_memory(coarse, 1.0, patrol_id=patrol_id)

        fine = base.clone()
        _, fine_zone = prepare(fine)
        for time in (.25, .5, .75, 1.0):
            advance_patrol_presence_memory(fine, time, patrol_id=patrol_id)

        self.assertAlmostEqual(
            coarse_zone.presence_memory["government"],
            fine_zone.presence_memory["government"],
            places=12,
        )

    def test_current_formation_presence_is_separate_from_patrol_memory(self):
        insurgent = self.world.formations["PRF-01"]
        locality_id = insurgent.locality_id
        zone = self.world.microzones[insurgent.current_microzone_id]
        zone.presence_memory["insurgent"] = 0.0
        zone.presence_updated_at["insurgent"] = 0.0
        control = recompute_microzone_control(
            self.world, locality_id, "insurgent", 1.0, apply_contestation=False
        )
        self.assertGreater(control, 0.0)
        self.assertEqual(zone.presence_memory["insurgent"], 0.0)

    def test_physical_refresh_preserves_franchise_reach_beside_aggregate_insurgent_control(self):
        children = split_organization(
            self.world, "insurgent", 1.0, random.Random(4)
        )
        self.assertEqual(len(children), 2)
        fielded = next(
            formation for formation in self.world.formations.values()
            if formation.organization_id in {child.organization_id for child in children}
            and formation.personnel > 0
        )
        locality_id = fielded.locality_id
        aggregates = recompute_contested_controls(
            self.world, locality_id, 1.0
        )
        self.assertIn(fielded.organization_id, aggregates)
        self.assertGreater(aggregates[fielded.organization_id], 0.0)
        self.assertGreaterEqual(
            aggregates["insurgent"] + 1e-12,
            aggregates[fielded.organization_id],
        )

        self.world.time = 1.0
        ProcessEngine(self.world).on_physical_refresh(
            "FRANCHISE-PHYSICAL",
            ScheduledEvent(1.0, 0, 0, "physical_refresh", {"elapsed_days": 1.0, "interval": 1.0}),
        )
        self.assertAlmostEqual(
            self.world.localities[locality_id].control[fielded.organization_id].physical,
            aggregates[fielded.organization_id],
            places=12,
        )
        self.assertAlmostEqual(
            self.world.localities[locality_id].control["insurgent"].physical,
            aggregates["insurgent"],
            places=12,
        )

    def test_legacy_patrol_presence_gain_migrates_to_separate_gains(self):
        config = SimulationConfig.from_dict({
            "physical": {"patrol_presence_gain": .2},
        })
        self.assertEqual(config.physical.formation_presence_gain, .2)
        self.assertEqual(config.physical.patrol_memory_gain, .2)



if __name__ == "__main__":
    unittest.main()
