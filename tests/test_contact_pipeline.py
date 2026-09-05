import unittest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


def prepared_world(seed: int = 8811):
    config = SimulationConfig(seed=seed, agent_count=120, locality_count=17,
                              horizon_days=1, output_mode="ensemble")
    config.organization_ecology.enabled = False
    world = generate_pineland(config)
    government = world.formations["FDF-01"]
    insurgent = world.formations["PRF-01"]
    insurgent.locality_id = government.locality_id
    insurgent.current_microzone_id = government.current_microzone_id
    for formation in (government, insurgent):
        formation.availability = formation.readiness = formation.command = 1.0
        formation.cohesion = 1.0
        formation.fatigue = 0.0
        formation.supply_stock = formation.supply_capacity
        formation.moving = False
        formation.operational_status = "effective"
    world.organizations["insurgent"].status = "active"
    return world, government, insurgent


def one_contact_trial(base, government, insurgent, seed, rate, *, detected=True,
                      same_zone=True, supply_fraction=None, supply_rule=None):
    world = base.clone()
    world.config.seed = seed
    world.config.contact_rate = rate
    world.config.information.contact_true_positive_rate = 1.0
    if supply_rule is not None:
        world.config.combat.contact_supply_rule = supply_rule
    if supply_fraction is not None:
        for formation in (world.formations[government.formation_id],
                          world.formations[insurgent.formation_id]):
            formation.supply_stock = formation.supply_capacity * supply_fraction
    if not same_zone:
        insurgent = world.formations[insurgent.formation_id]
        government = world.formations[government.formation_id]
        insurgent.current_microzone_id = next(
            zone.microzone_id for zone in world.microzones.values()
            if zone.locality_id == government.locality_id and
            zone.microzone_id != government.current_microzone_id
        )
    event = ScheduledEvent(0.0, 20, 0, "contact", {
        "locality_id": government.locality_id,
        "microzone_id": government.current_microzone_id,
        "force_detection": detected,
    })
    ProcessEngine(world).execute(event)
    return world.contact_funnel_records[-1]


class ContactPipelineTests(unittest.TestCase):
    def test_recorded_engagement_requires_latent_engagement(self):
        base, government, insurgent = prepared_world(9901)
        base.config.recording.base_logit = 100.0
        trace = one_contact_trial(base, government, insurgent, 9902, 0.0)
        self.assertEqual(trace["gate_counts"]["recorded_engagements"], 0)
        self.assertEqual(trace["gate_counts"]["recorded_contacts"], 0)

    def test_recorded_active_cell_arithmetic_invariant(self):
        world = generate_pineland(SimulationConfig(seed=9903, agent_count=120,
                                                   locality_count=17, horizon_days=1,
                                                   output_mode="ensemble"))
        result = __import__("pineland_sim").Simulation(world).run(until=1).world
        latent = {entry.event_id for entry in result.event_log
                  if entry.event_type == "contact" and entry.true_state_delta.get("contact", 0) > 0}
        recorded = [record for record in result.synthetic_records
                    if record.event_id in latent and record.recorded]
        active_cells = {(record.locality_id, int(record.time // 7)) for record in recorded}
        self.assertLessEqual(len(active_cells), len(recorded))
        self.assertLessEqual(len(recorded), len(latent))

    def test_interval_is_inside_continuous_time_hazard(self):
        base, government, insurgent = prepared_world(9910)
        hazards = []
        for dt in (.25, .5, 1.0, 2.0, 7.0):
            world = base.clone()
            event = ScheduledEvent(0.0, 20, 0, "contact", {
                "locality_id": government.locality_id,
                "microzone_id": government.current_microzone_id,
                "government_formation_id": government.formation_id,
                "insurgent_formation_id": insurgent.formation_id,
                "force_detection": True,
                "interval_days": dt,
            })
            ProcessEngine(world).execute(event)
            hazards.append((dt, world.contact_funnel_records[-1]["contact_hazard"]))
        rates = [-__import__("math").log(1 - p) / dt for dt, p in hazards]
        self.assertLess(max(rates) - min(rates), 1e-10)

    def test_scheduler_emits_every_spatial_pair(self):
        base, government, insurgent = prepared_world(9920)
        import copy
        base.formations["FDF-X"] = copy.deepcopy(government)
        base.formations["FDF-X"].formation_id = "FDF-X"
        base.formations["PRF-X"] = copy.deepcopy(insurgent)
        base.formations["PRF-X"].formation_id = "PRF-X"
        Simulation = __import__("pineland_sim").Simulation
        simulation = Simulation(base)
        simulation._schedule_contacts(0.0)
        contacts = [e for e in simulation.scheduler._queue if e.event_type == "contact"]
        selected = [e for e in contacts
                    if e.payload["government_formation_id"] in {government.formation_id, "FDF-X"} and
                    e.payload["insurgent_formation_id"] in {insurgent.formation_id, "PRF-X"}]
        self.assertEqual(len(selected), 4)

    def test_scheduler_excludes_explicitly_ineffective_formations(self):
        base, government, insurgent = prepared_world(9921)
        insurgent.operational_status = "ineffective"
        Simulation = __import__("pineland_sim").Simulation
        simulation = Simulation(base)
        simulation._schedule_contacts(0.0)
        contacts = [event for event in simulation.scheduler._queue
                    if event.event_type == "contact"]
        self.assertFalse(any(
            event.payload["insurgent_formation_id"] == insurgent.formation_id
            for event in contacts
        ))
    def test_trace_contains_all_required_gate_fields(self):
        config = SimulationConfig(
            agent_count=100, locality_count=17, horizon_days=1, seed=7711,
            output_mode="ensemble",
        )
        config.combat.organized_action_architecture = "legacy_contact_only"
        world = __import__("pineland_sim").generate_pineland(config)
        Simulation = __import__("pineland_sim").Simulation
        result = Simulation(world).run().world
        self.assertTrue(result.contact_funnel_records)
        trace = result.contact_funnel_records[0]
        required = {
            "opposing_armed_organizations", "opposing_formation_candidate_pairs",
            "same_locality_candidate_pairs", "microzone_eligible_candidate_pairs",
            "proximity_qualified_pairs", "true_target_presence_cases",
            "detected_opponent_sides", "failed_detection_sides", "willingness_decisions",
            "readiness_available_pairs", "supply_eligible_pairs", "command_eligible_pairs",
            "engagement_hazard_draws", "engagement_hazard_passes",
            "realized_latent_contacts", "recorded_contacts",
        }
        self.assertTrue(required.issubset(trace["gate_counts"]))
        self.assertEqual(result.summary()["contact_funnel"]["scheduled_attempts"],
                         len(result.contact_funnel_records))

    def test_controlled_contact_rate_is_monotone_and_matches_hazard(self):
        base, government, insurgent = prepared_world()
        low = [one_contact_trial(base, government, insurgent, 8800 + i, .05)
               for i in range(40)]
        high = [one_contact_trial(base, government, insurgent, 8900 + i, .60)
                for i in range(40)]
        low_rate = sum(t["gate_counts"]["realized_latent_contacts"] for t in low) / len(low)
        high_rate = sum(t["gate_counts"]["realized_latent_contacts"] for t in high) / len(high)
        self.assertGreater(high_rate, low_rate)
        for rows in (low, high):
            expected = sum(t["contact_hazard"] for t in rows) / len(rows)
            observed = sum(t["gate_counts"]["realized_latent_contacts"] for t in rows) / len(rows)
            self.assertLess(abs(expected - observed), .20)

    def test_detection_and_proximity_are_independent_gates(self):
        base, government, insurgent = prepared_world()
        hidden = one_contact_trial(base, government, insurgent, 8921, .60, detected=False)
        distant = one_contact_trial(base, government, insurgent, 8922, .60, same_zone=False)
        self.assertIn(hidden["failure_reason"], {"engagement_hazard_draw", "realized"})
        self.assertGreater(hidden["contact_hazard"], 0.0)
        self.assertEqual(distant["failure_reason"], "no_microzone_proximity")
        self.assertEqual(hidden["gate_counts"]["realized_latent_contacts"], 0)
        self.assertEqual(distant["gate_counts"]["realized_latent_contacts"], 0)

    def test_zero_supply_is_a_contact_theory_branch_not_a_universal_gate(self):
        base, government, insurgent = prepared_world()
        hard = one_contact_trial(base, government, insurgent, 8931, .99,
                                 supply_fraction=0.0, supply_rule="hard_gate")
        open_contact = one_contact_trial(base, government, insurgent, 8931, .99,
                                         supply_fraction=0.0, supply_rule="no_gate")
        self.assertEqual(hard["gate_counts"]["supply_eligible_pairs"], 0)
        self.assertEqual(hard["failure_reason"], "supply_exclusion")
        self.assertEqual(hard["gate_counts"]["engagement_hazard_draws"], 1)
        self.assertEqual(open_contact["gate_counts"]["supply_eligible_pairs"], 1)
        self.assertEqual(open_contact["gate_counts"]["engagement_hazard_draws"], 1)
        self.assertEqual(open_contact["supply_contact_rule"], "no_gate")


if __name__ == "__main__":
    unittest.main()
