import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.analytics import locality_control_change
from pineland_sim.events import ScheduledEvent
from pineland_sim.experiments import governance_surge, run_paired_experiment
from pineland_sim.processes import ProcessEngine


def small_config(**overrides):
    values = dict(agent_count=250, locality_count=24, horizon_days=8, seed=44)
    values.update(overrides)
    return SimulationConfig(**values)


class SimulationTests(unittest.TestCase):
    def test_end_to_end_run_logs_provenance_and_records(self):
        result = Simulation(generate_pineland(small_config())).run()
        self.assertGreater(result.events_processed, 0)
        self.assertTrue(result.world.event_log)
        self.assertTrue(result.world.synthetic_records)
        self.assertTrue(result.world.checkpoints)
        result.world.assert_invariants()
        locality_id = result.world.causal_ledger[0].locality_id
        self.assertTrue(locality_control_change(result.world, locality_id))

    def test_same_seed_reproduces_trajectory(self):
        first = Simulation(generate_pineland(small_config())).run().world
        second = Simulation(generate_pineland(small_config())).run().world
        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.checkpoints, second.checkpoints)

    def test_non_aligned_horizon_reports_requested_calendar_time(self):
        config = small_config(
            horizon_days=2.3,
            include_insurgency=False,
            agent_count=100,
            locality_count=17,
        )
        result = Simulation(generate_pineland(config)).run()
        self.assertAlmostEqual(result.stopped_at, 2.3, places=12)
        self.assertAlmostEqual(result.world.time, 2.3, places=12)
        self.assertAlmostEqual(result.world.checkpoints[-1]["time"], 2.3, places=12)

    def test_run_rejects_backward_horizon(self):
        simulation = Simulation(generate_pineland(small_config(horizon_days=3)))
        simulation.run(until=2.0)
        with self.assertRaisesRegex(ValueError, "cannot run backward"):
            simulation.run(until=1.0)
        self.assertEqual(simulation.world.time, 2.0)

    def test_max_events_stop_is_not_relabelled_as_completed_horizon(self):
        simulation = Simulation(generate_pineland(small_config(horizon_days=8)))
        result = simulation.run(until=8.0, max_events=1)
        self.assertLess(result.stopped_at, 8.0)

    def test_no_insurgency_null_model(self):
        world = Simulation(generate_pineland(small_config(include_insurgency=False))).run().world
        self.assertNotIn("insurgent", world.organizations)
        self.assertTrue(all("insurgent" not in locality.control for locality in world.localities.values()))
        self.assertFalse(any(person.public_behavior in {"insurgent_sympathy", "armed_participation"}
                             for person in world.persons.values()))
        self.assertFalse(any(key[0] == "insurgent" for key in world.beliefs))
        self.assertFalse(any(key[0] == "insurgent" for key in world.zone_beliefs))
        self.assertFalse(any(formation.organization_id == "insurgent" for formation in world.formations.values()))
        self.assertFalse(any("insurgent" in entry.actor_ids or entry.event_type == "recruitment"
                             for entry in world.event_log))
        self.assertFalse(any(record.reported_actor == "insurgent" for record in world.synthetic_records))
        self.assertFalse(any("insurgent" in item.mechanism for item in world.causal_ledger))
        self.assertTrue(all(person.social_exposure.get("insurgent", 0.0) == 0
                            for person in world.persons.values()))
        self.assertEqual(sum(1 for entry in world.event_log if entry.event_type == "contact"), 0)
        self.assertFalse(world.engagements)
        world.assert_invariants()

    def test_paired_worlds_start_identically(self):
        base = generate_pineland(small_config())
        fork = base.clone()
        self.assertEqual(base.summary(), fork.summary())
        fork.organizations["government"].resources += 1
        self.assertNotEqual(base.organizations["government"].resources,
                            fork.organizations["government"].resources)

    def test_world_invariants_reject_armed_member_with_rival_franchise_affinity(self):
        world = generate_pineland(small_config())
        insurgent = world.organizations["insurgent"]
        member_id = next(iter(insurgent.member_ids))
        member = world.persons[member_id]
        world.assert_invariants()
        member.insurgent_affinity["insurgent"] = 0.5
        # Add a second live insurgent identity only to make the corruption
        # explicit; active armed membership itself remains assigned to PRF.
        rival = __import__("copy").deepcopy(insurgent)
        rival.organization_id = "rival-franchise"
        rival.name = "Rival Franchise"
        rival.member_ids = set()
        world.organizations[rival.organization_id] = rival
        member.insurgent_affinity[rival.organization_id] = 0.5
        with self.assertRaisesRegex(
            AssertionError, "competing franchise affinity"
        ):
            world.assert_invariants()

    def test_matched_seed_counterfactual(self):
        config = small_config(horizon_days=3)
        outcomes, summary = run_paired_experiment(
            config, governance_surge(1.2, start_day=0, end_day=3), repetitions=2
        )
        self.assertEqual(len(outcomes), 2)
        self.assertIn("median", summary)
        self.assertTrue(any(outcome.effect != 0 for outcome in outcomes))

    def test_contact_changes_stocks_and_records_cause(self):
        world = generate_pineland(small_config(contact_rate=1.0))
        government = world.formations["FDF-01"]
        insurgent = world.formations["PRF-01"]
        insurgent.locality_id = government.locality_id

        class PredictableRng:
            def random(self): return 0.0
            def normalvariate(self, mu, sigma): return mu
            def expovariate(self, rate): return 0.01
            def uniform(self, low, high): return (low + high) / 2

        before = (government.personnel, insurgent.personnel)
        engine = ProcessEngine(world, PredictableRng())
        event = ScheduledEvent(0, 0, 0, "contact", {"locality_id": government.locality_id})
        engine.execute(event)
        self.assertLess(government.personnel, before[0])
        self.assertLess(insurgent.personnel, before[1])
        self.assertTrue(any(item.mechanism == "combat" for item in world.causal_ledger))


if __name__ == "__main__":
    unittest.main()
