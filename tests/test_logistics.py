import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import CommandEdge
from pineland_sim.logistics import (
    advance_movement_orders,
    command_edge_key,
    command_metrics,
    control_cost,
    create_movement_order,
    choose_reallocation_orders,
    logistics_diagnostics,
    shortest_locality_path,
    update_logistics,
)
from pineland_sim.physical import recompute_microzone_control
from pineland_sim.reproducibility import decision_state_sha256


class AlwaysSuccessRng:
    def random(self):
        return 0.0

    def choices(self, population, weights, k):
        return [population[max(range(len(weights)), key=weights.__getitem__)]]


class LogisticsTests(unittest.TestCase):
    def setUp(self):
        self.world = generate_pineland(SimulationConfig(
            agent_count=400, locality_count=34, horizon_days=10, seed=303
        ))

    def test_topology_changes_travel_time_and_movement_cost(self):
        formation = self.world.formations["FDF-01"]
        origin = formation.locality_id
        destinations = [locality_id for locality_id in self.world.localities if locality_id != origin]
        paths = [(shortest_locality_path(self.world, origin, destination, formation.mobility), destination)
                 for destination in destinations]
        near_path, near = min(paths, key=lambda item: item[0][2])
        far_path, far = max(paths, key=lambda item: item[0][2])
        self.assertGreater(far_path[2], near_path[2])
        near_order = create_movement_order(self.world, formation.formation_id, near, 0, AlwaysSuccessRng())
        self.world.movement_orders.clear()
        far_order = create_movement_order(self.world, formation.formation_id, far, 0, AlwaysSuccessRng())
        self.assertGreater(far_order.travel_time_hours, near_order.travel_time_hours)
        self.assertGreater(far_order.supply_cost, near_order.supply_cost)

    def test_route_cache_is_scientifically_inert(self):
        formation = self.world.formations["FDF-01"]
        destination = next(
            locality_id for locality_id in self.world.localities
            if locality_id != formation.locality_id
        )
        before = decision_state_sha256(self.world)
        first = shortest_locality_path(
            self.world, formation.locality_id, destination, formation.mobility
        )
        self.assertEqual(len(self.world.locality_path_cache), 1)
        second = shortest_locality_path(
            self.world, formation.locality_id, destination, formation.mobility
        )
        self.assertEqual(first, second)
        self.assertIsNot(first[0], second[0])
        self.assertEqual(decision_state_sha256(self.world), before)

    def test_in_transit_stock_cache_matches_shipment_records(self):
        # The cache is an accounting accelerator only; it must agree with the
        # forensic shipment dictionary after a normal short trajectory.
        world = Simulation(generate_pineland(SimulationConfig(
            agent_count=100, locality_count=17, horizon_days=5, seed=304
        ))).run().world
        scanned = sum(
            shipment.quantity_deliverable
            for shipment in world.supply_shipments.values()
            if shipment.status == "in_transit"
        )
        self.assertAlmostEqual(world.in_transit_supply_total, scanned, places=9)

    def test_command_delay_precedes_movement_and_movement_removes_availability(self):
        formation = self.world.formations["FDF-01"]
        destination = next(iter(self.world.adjacency[formation.locality_id]))
        order = create_movement_order(
            self.world, formation.formation_id, destination, 0, AlwaysSuccessRng()
        )
        advance_movement_orders(self.world, max(0, order.execute_at - .001))
        self.assertEqual(order.status, "pending")
        advance_movement_orders(self.world, order.execute_at)
        self.assertEqual(order.status, "moving")
        self.assertEqual(formation.available_personnel(), 0.0)
        advance_movement_orders(self.world, order.arrives_at)
        self.assertEqual(order.status, "arrived")
        self.assertEqual(formation.locality_id, destination)

    def test_reallocation_uses_actor_beliefs(self):
        formation = self.world.formations["FDF-01"]
        for other in self.world.formations.values():
            if other.formation_id != formation.formation_id:
                other.moving = True
        nearest = min(
            (locality_id for locality_id in self.world.localities
             if locality_id != formation.locality_id),
            key=lambda locality_id: shortest_locality_path(
                self.world, formation.locality_id, locality_id, formation.mobility
            )[2],
        )
        for locality_id, locality in self.world.localities.items():
            # Hold population and opponent belief fixed so this test isolates
            # the actor's own-control belief rather than the explicit stay,
            # importance, or threatened-control channels.
            locality.population = 10_000
            belief = self.world.beliefs[(formation.organization_id, locality_id)]
            belief.control_estimate.physical = 1.0
            belief.confidence = 1.0
            opponent = self.world.control_beliefs[
                (formation.organization_id, "insurgent", locality_id)
            ]
            opponent.control_estimate.physical = 0.0
            opponent.confidence = 1.0
        self.world.beliefs[(formation.organization_id, nearest)].control_estimate.physical = 0.0
        original_rate = self.world.config.logistics.reallocation_rate
        self.world.config.logistics.reallocation_rate = 1.0
        orders = choose_reallocation_orders(self.world, 0, AlwaysSuccessRng())
        self.world.config.logistics.reallocation_rate = original_rate
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].destination_locality_id, nearest)

    def test_isolated_formation_loses_effective_readiness_without_negative_supply(self):
        formation = self.world.formations["FDF-01"]
        removed = formation.supply_stock
        formation.supply_stock = 0.0
        formation.sustainment = 0.0
        self.world.initial_supply_stock -= removed
        for source in self.world.supply_sources.values():
            if source.organization_id == formation.organization_id:
                source.operational = False
        before = formation.effective_readiness()
        for day in range(1, 6):
            update_logistics(self.world, day, 1.0)
        self.assertLess(formation.effective_readiness(), before)
        self.assertEqual(formation.supply_stock, 0.0)
        self.world.assert_invariants()

    def test_near_functioning_source_recovers_readiness(self):
        formation = self.world.formations["FDF-01"]
        source = next(source for source in self.world.supply_sources.values()
                      if source.organization_id == formation.organization_id)
        formation.locality_id = source.locality_id
        formation.readiness = .4
        formation.availability = .4
        formation.fatigue = .5
        before = formation.effective_readiness()
        update_logistics(self.world, 1, 1.0)
        self.assertGreater(formation.effective_readiness(), before)

    def test_long_presence_consumes_more_than_temporary_transit(self):
        stationary = self.world.clone()
        for source in stationary.supply_sources.values():
            source.operational = False
        for formation in stationary.formations.values():
            if formation.formation_id != "FDF-01":
                formation.moving = True
        for day in range(1, 6):
            update_logistics(stationary, day, 1.0)
        presence_consumption = stationary.cumulative_supply_consumed

        moving = self.world.clone()
        formation = moving.formations["FDF-01"]
        destination = next(iter(moving.adjacency[formation.locality_id]))
        order = create_movement_order(moving, formation.formation_id, destination, 0, AlwaysSuccessRng())
        advance_movement_orders(moving, order.execute_at)
        self.assertGreater(presence_consumption, moving.cumulative_supply_consumed)

    def test_supply_collapse_reduces_projection_without_changing_manpower(self):
        formation = self.world.formations["FDF-01"]
        locality_id = formation.locality_id
        before_personnel = formation.personnel
        baseline = recompute_microzone_control(self.world, locality_id, "government", 0)
        formation.supply_stock = 0.0
        formation.sustainment = 0.0
        formation.readiness = .1
        formation.availability = .2
        for zone in self.world.microzones.values():
            if zone.locality_id == locality_id:
                zone.presence_memory.clear()
                zone.presence_updated_at.clear()
        degraded = recompute_microzone_control(self.world, locality_id, "government", 10)
        self.assertEqual(formation.personnel, before_personnel)
        self.assertLess(degraded, baseline)

    def test_command_graph_changes_reliability_and_latency(self):
        good_key = command_edge_key("CMD:good", "unit-good")
        poor_key = command_edge_key("CMD:poor", "unit-poor")
        self.world.command_edges[good_key] = CommandEdge(*good_key, "good", .97, 1.0)
        self.world.command_edges[poor_key] = CommandEdge(*poor_key, "poor", .55, 9.0)
        good = command_metrics(self.world, "good", "unit-good")
        poor = command_metrics(self.world, "poor", "unit-poor")
        self.assertGreater(good[0], poor[0])
        self.assertLess(good[1], poor[1])

    def test_supply_transfers_conserve_and_control_cost_accumulates(self):
        world = Simulation(self.world).run(until=10).world
        world.assert_invariants()
        diagnostics = logistics_diagnostics(world)
        self.assertAlmostEqual(diagnostics["supply_conservation"]["residual"], 0.0, places=5)
        self.assertTrue(world.resource_flows)
        locality_id = max(world.control_cost_consumed, key=world.control_cost_consumed.get)
        self.assertGreater(control_cost(world, locality_id)["supply_units_per_day"], 0)

    def test_manpower_shrink_never_discards_existing_supply(self):
        formation = self.world.formations["FDF-01"]
        before_stock = formation.supply_stock
        before_stocks = self.world.tracked_stock_totals()
        formation.personnel *= .1
        self.world.record_stock_transactions(
            "T-MANPOWER-SHRINK", "test", before_stocks, self.world.tracked_stock_totals()
        )
        update_logistics(self.world, 1, 0.0)
        self.assertEqual(formation.supply_stock, before_stock)
        self.assertGreaterEqual(formation.supply_capacity, formation.supply_stock)
        self.world.assert_invariants()

    def test_logistics_trajectory_is_reproducible(self):
        first = Simulation(self.world.clone()).run(until=5).world
        second = Simulation(self.world.clone()).run(until=5).world
        self.assertEqual(logistics_diagnostics(first), logistics_diagnostics(second))


if __name__ == "__main__":
    unittest.main()
