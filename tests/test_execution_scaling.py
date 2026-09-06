"""Operation-count and numerical-equivalence checks for recurring hot paths."""
from collections import deque
from unittest.mock import patch

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import ArmedFormation
from pineland_sim.information import _corroboration_weight
from pineland_sim.logistics import advance_movement_orders, choose_reallocation_orders, update_logistics
from pineland_sim.physical import response_times
from pineland_sim.world import seeded_rng


def test_corroboration_matches_uncapped_history_scan():
    history = deque((index / 12, f"source-{index % 11}") for index in range(120))
    for timestamp in (0, 3, 7.5, 10, 15):
        for source in ("source-0", "other"):
            sources = {identity for stamp, identity in history
                       if identity != source and abs(stamp - timestamp) <= 3}
            for correlation in (0, .15, .35, .55, .65, .99, 1):
                expected = min(3, sum(1.0 - correlation for _ in sources))
                assert _corroboration_weight(history, timestamp, source, correlation) == expected


def test_response_does_not_evaluate_remote_patrol_readiness():
    world = generate_pineland(SimulationConfig(agent_count=50, locality_count=17, seed=818))
    locality = next(iter(world.localities))
    original = ArmedFormation.effective_readiness

    def checked(formation):
        assert formation.locality_id == locality
        return original(formation)

    with patch.object(ArmedFormation, "effective_readiness", checked):
        response_times(world, locality, "government", 0)


class NoArchiveScan(dict):
    def values(self):
        raise AssertionError("Recurring logistics scanned the historical archive")


def test_recurring_logistics_uses_active_indexes_and_conserves_supply():
    config = SimulationConfig(agent_count=50, locality_count=17, horizon_days=3, seed=303)
    world = Simulation(generate_pineland(config)).run().world
    world.movement_orders = NoArchiveScan(world.movement_orders)
    world.supply_shipments = NoArchiveScan(world.supply_shipments)
    advance_movement_orders(world, 4)
    choose_reallocation_orders(world, 4, seeded_rng(config, "scaling-test"))
    update_logistics(world, 4, 1)
    world.movement_orders = dict(world.movement_orders)
    world.supply_shipments = dict(world.supply_shipments)
    assert abs(world.supply_conservation_residual()) < 1e-5
    assert set(world.active_shipment_ids) == {
        key for key, item in world.supply_shipments.items() if item.status == "in_transit"
    }
    assert set(world.active_movement_order_ids) == {
        key for key, item in world.movement_orders.items() if item.status in {"pending", "moving"}
    }
