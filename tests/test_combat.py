import random
import unittest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.combat import operational_effectiveness, resolve_engagement
from pineland_sim.physical import recompute_microzone_control


def world_for(seed=71):
    world = generate_pineland(SimulationConfig(agent_count=300, locality_count=24,
                                               horizon_days=2, seed=seed))
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    return world, government, insurgent


class CombatTests(unittest.TestCase):
    def test_engagement_is_spatial_and_does_not_write_control(self):
        world, government, insurgent = world_for()
        before = {a: v.to_dict() for a, v in world.localities[government.locality_id].control.items()}
        engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                           ("government", "insurgent"), 0, random.Random(1))
        self.assertIn(engagement.microzone_id, world.microzones)
        self.assertEqual(before, {a: v.to_dict() for a, v in world.localities[government.locality_id].control.items()})

    def test_different_seeds_produce_different_outcomes(self):
        outcomes = []
        for seed in range(8):
            world, government, insurgent = world_for()
            engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                               ("government", "insurgent"), 0, random.Random(seed))
            outcomes.append(round(engagement.personnel_losses[government.formation_id], 6))
        self.assertGreater(len(set(outcomes)), 4)

    def test_stronger_formation_outperforms_over_ensemble(self):
        margins = []
        for seed in range(60):
            world, government, insurgent = world_for()
            government.personnel = insurgent.personnel * 3
            government.quality = government.cohesion = government.readiness = .95
            engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                               ("government", "insurgent"), 0, random.Random(seed))
            margins.append(engagement.personnel_losses[insurgent.formation_id] / max(1, insurgent.personnel) -
                           engagement.personnel_losses[government.formation_id] / max(1, government.personnel))
        self.assertGreater(sum(margins) / len(margins), 0)

    def test_supply_and_surprise_affect_capability(self):
        supplied, gs, ins = world_for()
        deprived = supplied.clone()
        gd, ind = deprived.formations[gs.formation_id], deprived.formations[ins.formation_id]
        removed = gd.supply_stock
        gd.supply_stock = 0
        deprived.initial_supply_stock -= removed
        aware, _ = resolve_engagement(supplied, "E-aware", gs, ins, (gs.organization_id,), 0, random.Random(4))
        poor, _ = resolve_engagement(deprived, "E-poor", gd, ind, (ind.organization_id,), 0, random.Random(4))
        self.assertGreater(aware.effective_capability[gs.formation_id], poor.effective_capability[gd.formation_id])

    def test_engagement_consumes_supply_and_can_disengage(self):
        world, government, insurgent = world_for()
        before = government.supply_stock
        engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                           ("government", "insurgent"), 0, random.Random(3))
        self.assertLess(government.supply_stock, before)
        self.assertGreater(engagement.supply_consumed[government.formation_id], 0)
        self.assertTrue(engagement.disengaged or government.personnel > 0)

    def test_terrain_changes_mobility_exposure_not_faction_bonus(self):
        open_world, go, io = world_for()
        rough_world, gr, ir = world_for()
        open_zone = open_world.microzones[next(p.current_microzone_id for p in open_world.patrols.values()
                                                if p.formation_id == go.formation_id)]
        rough_zone = rough_world.microzones[next(p.current_microzone_id for p in rough_world.patrols.values()
                                                 if p.formation_id == gr.formation_id)]
        open_zone.terrain_friction = .4
        rough_zone.terrain_friction = 2.0
        open_engagement, _ = resolve_engagement(open_world, "E-open", go, io,
                                                (go.organization_id, io.organization_id), 0, random.Random(8))
        rough_engagement, _ = resolve_engagement(rough_world, "E-rough", gr, ir,
                                                 (gr.organization_id, ir.organization_id), 0, random.Random(8))
        self.assertGreater(open_engagement.effective_capability[go.formation_id],
                           rough_engagement.effective_capability[gr.formation_id])
        self.assertNotEqual(open_engagement.personnel_losses,
                            rough_engagement.personnel_losses)

    def test_cohesion_can_disable_before_manpower_zero(self):
        world, government, insurgent = world_for()
        government.cohesion = world.config.combat.ineffective_cohesion + .001
        world.config.combat.cohesion_loss_multiplier = 20
        engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                           ("government", "insurgent"), 0, random.Random(2))
        self.assertGreater(government.personnel, 0)
        self.assertIn(government.formation_id, engagement.ineffective)

    def test_civilian_harm_reaches_politics_via_observation(self):
        world, government, insurgent = world_for()
        control_before = world.localities[government.locality_id].control["government"].to_dict()
        engagement, observations = resolve_engagement(world, "E-test", government, insurgent,
                                                       ("government", "insurgent"), 0, random.Random(5))
        self.assertGreaterEqual(engagement.civilian_harm, 0)
        self.assertTrue(all(o.observation_type == "engagement_outcome" for o in observations))
        self.assertEqual(control_before, world.localities[government.locality_id].control["government"].to_dict())

    def test_degradation_reduces_generated_presence(self):
        world, government, insurgent = world_for()
        locality_id = government.locality_id
        before = recompute_microzone_control(world, locality_id, "government", 0)
        government.cohesion = .1
        government.availability = .05
        government.operational_status = "ineffective"
        after = recompute_microzone_control(world, locality_id, "government", 1)
        self.assertLess(after, before)

    def test_reinforcement_is_existing_movement_order(self):
        world, government, insurgent = world_for()
        world.config.combat.reinforcement_threshold = 0
        engagement, _ = resolve_engagement(world, "E-test", government, insurgent,
                                           ("government", "insurgent"), 0, random.Random(9))
        self.assertTrue(engagement.reinforcement_order_ids)
        for order_id in engagement.reinforcement_order_ids:
            self.assertIn(order_id, world.movement_orders)
            self.assertEqual(world.movement_orders[order_id].destination_locality_id,
                             government.locality_id)


if __name__ == "__main__":
    unittest.main()
