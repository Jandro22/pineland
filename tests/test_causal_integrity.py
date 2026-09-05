import random
import unittest
from unittest.mock import patch

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.information import observe_target
from pineland_sim.processes import ProcessEngine
from pineland_sim.events import ScheduledEvent
from pineland_sim.physical import recompute_microzone_control


def small_world(seed=901):
    return generate_pineland(SimulationConfig(
        seed=seed, agent_count=300, locality_count=24, horizon_days=3,
    ))


class CausalIntegrityTests(unittest.TestCase):
    def test_insurgent_microzone_presence_is_not_patrol_dependent(self):
        world = small_world()
        government = world.formations["FDF-01"]
        insurgent = world.formations["PRF-01"]
        insurgent.locality_id = government.locality_id
        insurgent.current_microzone_id = government.current_microzone_id
        observation = observe_target(
            world, "fdf", government.formation_id, "forensic", "patrol",
            government.locality_id, "insurgent", 0.0, random.Random(4),
            insurgent.formation_id, government.current_microzone_id,
            force_detection=True,
        )
        self.assertIsNotNone(observation)
        self.assertEqual(observation.estimated_value["detected"], True)
        self.assertEqual(observation.target_id, insurgent.formation_id)

    def test_insurgent_physical_reach_is_generated_symmetrically(self):
        world = small_world(902)
        insurgent = world.formations["PRF-01"]
        locality_id = insurgent.locality_id
        insurgent_control = recompute_microzone_control(world, locality_id, "insurgent", 0.0)
        government_control = recompute_microzone_control(world, locality_id, "government", 0.0)
        self.assertGreater(insurgent_control, 0.0)
        self.assertGreater(government_control, 0.0)
        self.assertAlmostEqual(world.localities[locality_id].control["insurgent"].physical,
                               insurgent_control)

    def test_matched_current_formation_occupation_is_side_symmetric_and_departure_is_immediate(self):
        world = small_world(903)
        government = world.formations["FDF-01"]
        insurgent = world.formations["PRF-01"]
        locality_id = government.locality_id
        microzone_id = government.current_microzone_id

        # Remove role-specific infrastructure so the matched comparison isolates
        # the actor-symmetric current-formation presence/response path.
        world.security_posts.clear()
        world.security_post_ids_by_locality.clear()
        world.patrols.clear()
        for formation in world.formations.values():
            formation.moving = formation.formation_id not in {
                government.formation_id, insurgent.formation_id
            }
        for formation in (government, insurgent):
            formation.locality_id = locality_id
            formation.current_microzone_id = microzone_id
            formation.moving = False
            formation.outside_pineland = False
            formation.operational_status = "effective"
            formation.personnel = 500.0
            formation.quality = .6
            formation.cohesion = .7
            formation.readiness = .8
            formation.availability = .75
            formation.command = .9
            formation.information = .5
            formation.fatigue = .1
            formation.supply_capacity = 1_000.0
            formation.supply_stock = 800.0
            formation.sustainment = .8
        for zone in world.microzones.values():
            if zone.locality_id == locality_id:
                zone.presence_memory.pop("government", None)
                zone.presence_memory.pop("insurgent", None)
                zone.presence_updated_at.pop("government", None)
                zone.presence_updated_at.pop("insurgent", None)

        government_control = recompute_microzone_control(
            world, locality_id, "government", 0.0, apply_contestation=False
        )
        insurgent_control = recompute_microzone_control(
            world, locality_id, "insurgent", 0.0, apply_contestation=False
        )
        self.assertAlmostEqual(government_control, insurgent_control, places=12)
        self.assertGreater(insurgent_control, 0.0)

        insurgent.moving = True
        departed_control = recompute_microzone_control(
            world, locality_id, "insurgent", .25, apply_contestation=False
        )
        self.assertEqual(departed_control, 0.0)

    def test_belief_update_does_not_read_realized_control(self):
        world = small_world()
        counterfactual = world.clone()
        person = next(iter(world.persons.values()))
        counter_person = counterfactual.persons[person.person_id]
        locality = counterfactual.localities[counter_person.residence_locality_id]
        locality.control["government"].expected = 0.0
        locality.control["government"].physical = 1.0
        event = ScheduledEvent(0.0, 1, 0, "beliefs", {"interval": 1.0})
        ProcessEngine(world, random.Random(5)).execute(event)
        ProcessEngine(counterfactual, random.Random(5)).execute(event)
        self.assertEqual(person.expected_control, counter_person.expected_control)

    def test_organization_ecology_does_not_recruit_twice(self):
        world = small_world()
        engine = ProcessEngine(world, random.Random(6))
        event = ScheduledEvent(0.0, 1, 0, "organization_ecology", {"interval": 7.0})
        with patch("pineland_sim.processes.recruit_and_retain") as recruit:
            engine.execute(event)
            recruit.assert_not_called()

    def test_identity_dispersion_is_within_group_variance(self):
        world = small_world()
        insurgent = next(org for org in world.organizations.values()
                         if org.kind is OrganizationKind.INSURGENT)
        for pid in insurgent.member_ids:
            world.persons[pid].identities["federal"] = .9
        world.config.organization_ecology.split_base_hazard = 0.0
        ProcessEngine(world, random.Random(7)).execute(
            ScheduledEvent(0.0, 1, 0, "organization_ecology", {"interval": 7.0}))
        row = next(row for row in world.organization_eligibility_log
                   if row["organization_id"] == insurgent.organization_id)
        self.assertAlmostEqual(row["identity_variance"], 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
