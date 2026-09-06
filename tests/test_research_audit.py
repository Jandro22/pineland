import json
import random
import tempfile
import unittest
from pathlib import Path

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import ProtoOrganization
from pineland_sim.empirical import build_construct_correspondence
from pineland_sim.organization_ecology import mature_proto
from pineland_sim.research_audit import (causal_ledger_audit, null_and_extreme_checks,
                                          recording_calibration, scheduler_audit,
                                          truth_firewall_check)


class ResearchAuditTests(unittest.TestCase):
    def config(self, **overrides):
        values = dict(agent_count=120, locality_count=17, horizon_days=2, seed=7331,
                      burn_in_days=0.0)
        values.update(overrides)
        return SimulationConfig(**values)

    def test_burn_in_is_unrecorded_and_rebaselined(self):
        config = self.config(burn_in_days=2.0, horizon_days=1.0)
        world = Simulation(generate_pineland(config)).run().world
        self.assertTrue(world.event_log)
        self.assertTrue(all(event.time >= 0 for event in world.event_log))
        self.assertTrue(all(record.time >= 0 for record in world.synthetic_records))
        self.assertEqual(world.time, 1.0)
        self.assertFalse(world.in_burn_in)
        self.assertGreater(world.initial_population, 0.0)

    def test_burn_in_rebases_flow_ledgers_and_counters_without_deleting_state(self):
        config = self.config(burn_in_days=7.0, horizon_days=1.0)
        simulation = Simulation(generate_pineland(config))
        simulation.initialize()
        world = simulation.world
        self.assertEqual(world.time, 0.0)
        self.assertFalse(world.resource_flows)
        self.assertFalse(world.engagements)
        self.assertFalse(world.political_transfers)
        self.assertFalse(world.policy_implementations)
        self.assertFalse(world.external_transfers)
        self.assertFalse(world.peace_transitions)
        self.assertEqual(world.cumulative_civilian_harm, 0.0)
        self.assertEqual(world.cumulative_public_spending, 0.0)
        self.assertEqual(world.cumulative_external_remittances, 0.0)
        self.assertTrue(all(value == 0.0 for value in world.control_cost_consumed.values()))
        self.assertTrue(all(formation.cumulative_losses == 0.0
                            for formation in world.formations.values()))
        self.assertTrue(all(value == 0 for value in world.information_detections.values()))
        # Burn-in establishes a real initial state; it must not erase the
        # organizations/formations/resources that embody that state.
        self.assertTrue(world.organizations)
        self.assertTrue(world.formations)
        self.assertGreater(world.initial_supply_stock, 0.0)

    def test_burn_in_does_not_execute_observed_recurring_clocks_at_zero_twice(self):
        config = self.config(burn_in_days=1.0, horizon_days=1.0)
        simulation = Simulation(generate_pineland(config))
        seen = []
        original_execute = simulation.processes.execute

        def recording_execute(event):
            seen.append((event.time, event.event_type))
            return original_execute(event)

        simulation.processes.execute = recording_execute
        simulation.initialize()
        zero_events = [event_type for time, event_type in seen if time == 0.0]
        self.assertTrue(zero_events)
        self.assertTrue(all(
            event_type in {"contact", "organized_action"}
            for event_type in zero_events
        ))

    def test_audit_batteries_pass_on_small_world(self):
        config = self.config()
        self.assertTrue(truth_firewall_check(config, 1.0)["pass"])
        self.assertTrue(scheduler_audit(config, 2.0)["pass"])
        self.assertTrue(causal_ledger_audit(config, 2.0)["pass"])
        self.assertTrue(null_and_extreme_checks(config)["all_pass"])
        channels = recording_calibration(config, 12)["channels"]
        self.assertEqual(set(channels), {"patrol", "fixed_post", "civilian", "administrative", "contact"})

    def test_stock_and_state_delta_outputs_are_serializable(self):
        with tempfile.TemporaryDirectory() as directory:
            world = Simulation(generate_pineland(self.config(horizon_days=1))).run().world
            world.write_results(directory)
            stock_lines = Path(directory, "stock_transactions.jsonl").read_text().splitlines()
            state_lines = Path(directory, "state_deltas.jsonl").read_text().splitlines()
            self.assertEqual(len(stock_lines), len(world.stock_transactions))
            self.assertEqual(len(state_lines), len(world.state_deltas))
            if stock_lines:
                self.assertIn("stock_class", json.loads(stock_lines[0]))

    def test_construct_correspondence_requires_explicit_fields(self):
        result = build_construct_correspondence(
            "government_control",
            theoretical_construct="state territorial reach",
            simulation_latent_variable="locality.control.government.physical",
            simulation_observable="recorded physical-control reports",
            empirical_observable="geocoded territorial evidence",
            transformation="locality-month aggregation",
            observation_model="source-specific reporting and geocoding",
            known_mismatch="event occurrence is not persistent control",
            calibration_status="holdout",
        )
        self.assertEqual(result.metric, "government_control")

    def test_false_event_recording_is_separate_from_latent_truth(self):
        config = self.config(horizon_days=1)
        config.recording.false_event_rate = 1.0
        world = Simulation(generate_pineland(config)).run().world
        self.assertTrue(any(record.event_type == "false_event" for record in world.synthetic_records))
        self.assertFalse(any(event.event_type == "false_event" for event in world.event_log))

    def test_false_event_process_is_independent_of_latent_scheduler_density(self):
        rows = []
        for contact_interval in (1.0, 0.05):
            config = self.config(horizon_days=1, output_mode="calibration")
            config.intervals.contact = contact_interval
            config.recording.false_event_rate = 0.35
            world = Simulation(generate_pineland(config)).run().world
            rows.append([
                (
                    record.time,
                    record.locality_id,
                    record.reported_severity,
                    record.geocoding_error,
                    record.geocoding_error_distance_km,
                )
                for record in world.synthetic_records
                if record.event_type == "false_event"
            ])
        self.assertEqual(rows[0], rows[1])

    def test_insufficient_proto_manpower_collapses_atomically(self):
        config = self.config(agent_count=120)
        world = generate_pineland(config)
        community = next(iter(world.social_communities.values()))
        member_ids = set(community.member_ids) & {
            person_id for person_id, person in world.persons.items()
            if person.organization_id is None
        }
        member_ids = set(sorted(member_ids)[:2])
        before_resources = {person_id: world.persons[person_id].resources for person_id in member_ids}
        proto = ProtoOrganization("PROTO-ATOMIC", community.community_id, community.locality_id,
                                 member_ids, {"social": .9, "political": .9,
                                               "organizational": .9, "material": .9},
                                 {"reform": .6, "separatism": .2}, .9, 0.0)
        world.proto_organizations[proto.proto_id] = proto
        world.config.organization_ecology.birth_base_hazard = 1e6
        world.config.organization_ecology.minimum_formation_personnel = 1e12
        result = mature_proto(world, proto, 0.0, random.Random(4))
        self.assertIsNone(result)
        self.assertEqual(proto.status, "collapsed")
        self.assertTrue(all(world.persons[person_id].organization_id is None for person_id in member_ids))
        self.assertEqual(before_resources,
                         {person_id: world.persons[person_id].resources for person_id in member_ids})


if __name__ == "__main__":
    unittest.main()
