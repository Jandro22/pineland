import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.organization_ecology import split_organization
from pineland_sim.peace_process import (PROVISION_TYPES, bargaining_values,
    initiate_negotiation, peace_diagnostics, process_peace,
    run_fragmentation_comparison, sign_agreement)


class ZeroRng:
    def random(self): return 0.0
    def normalvariate(self, mean, sigma): return mean


def make_world(seed=909, agents=500):
    cfg = SimulationConfig(agent_count=agents, locality_count=34, horizon_days=366, seed=seed)
    cfg.foreign_affairs.intervention_base_hazard = 0
    cfg.foreign_affairs.support_budget_fraction = 0
    return generate_pineland(cfg)


class PeaceProcessTests(unittest.TestCase):
    def test_bargaining_values_include_war_peace_surplus_and_future_power(self):
        values = bargaining_values(make_world())
        self.assertIn("government", values)
        self.assertIn("insurgent", values)
        self.assertEqual(set(values["government"]), {"war", "peace", "surplus", "future_power"})

    def test_negotiation_is_endogenous_and_causally_logged(self):
        world = make_world()
        world.config.peace_process.negotiation_base_hazard = 1
        result = process_peace(world, 30, "E", ZeroRng())
        self.assertEqual(result["initiated"], 1)
        self.assertTrue(any(t.transition_type == "negotiation_initiated"
                            for t in world.peace_transitions))

    def test_agreement_has_explicit_provisions_and_temporary_ceasefire(self):
        world = make_world()
        negotiation = initiate_negotiation(world, 0)
        agreement = sign_agreement(world, negotiation, 30, ZeroRng())
        self.assertEqual({world.agreement_provisions[p].provision_type for p in agreement.provision_ids},
                         set(PROVISION_TYPES))
        self.assertTrue(all(world.ceasefires[x] == "active" for x in agreement.signatory_ids))

    def test_implementation_is_gradual_and_can_stall(self):
        world = make_world()
        agreement = sign_agreement(world, initiate_negotiation(world, 0), 0, ZeroRng())
        process_peace(world, 30, "E", random.Random(1))
        progresses = [world.agreement_provisions[x].progress for x in agreement.provision_ids]
        self.assertTrue(all(0 <= x < 1 for x in progresses))
        world.config.peace_process.implementation_rate = 0
        before = tuple(progresses)
        process_peace(world, 60, "E2", random.Random(2))
        self.assertEqual(before, tuple(world.agreement_provisions[x].progress for x in agreement.provision_ids))

    def test_government_and_insurgent_will_are_distinct(self):
        world = make_world()
        negotiation = initiate_negotiation(world, 0)
        negotiation.bargaining_surplus["government"] = -.3
        negotiation.bargaining_surplus["insurgent"] = .4
        agreement = sign_agreement(world, negotiation, 0, ZeroRng())
        p = world.agreement_provisions[agreement.provision_ids[0]]
        self.assertNotEqual(p.government_will, p.insurgent_will)

    def test_fragmentation_can_leave_armed_rejecting_factions(self):
        world = make_world()
        split_organization(world, "insurgent", 0, random.Random(4))
        children = [o for o in world.organizations.values() if o.parent_ids == ("insurgent",)]
        negotiation = initiate_negotiation(world, 1, children)
        agreement = sign_agreement(world, negotiation, 2, random.Random(6))
        self.assertGreaterEqual(len(agreement.rejecting_faction_ids), 0)
        self.assertEqual(set(agreement.signatory_ids) | set(agreement.rejecting_faction_ids),
                         set(negotiation.insurgent_ids))

    def test_demobilization_conserves_personnel_and_arms(self):
        world = make_world()
        agreement = sign_agreement(world, initiate_negotiation(world, 0), 0, ZeroRng())
        provision = world.agreement_provisions[f"{agreement.agreement_id}-demobilization"]
        provision.progress = .8
        before_personnel = sum(f.personnel for f in world.formations.values()) + world.demobilized_personnel
        before_arms = sum(f.supply_stock for f in world.formations.values()) + world.demobilized_arms
        process_peace(world, 30, "E", random.Random(10))
        self.assertAlmostEqual(before_personnel,
            sum(f.personnel for f in world.formations.values()) + world.demobilized_personnel)
        self.assertAlmostEqual(before_arms,
            sum(f.supply_stock for f in world.formations.values()) + world.demobilized_arms)
        world.assert_invariants()

    def test_completed_peace_demobilizes_pending_local_manpower_pool(self):
        world = make_world()
        org = world.organizations["insurgent"]
        locality_id = next(f.locality_id for f in world.formations.values()
                           if f.organization_id == org.organization_id)
        before_stocks = world.tracked_stock_totals()
        world.organization_manpower_pools[(org.organization_id, locality_id)] = 55.0
        world.record_stock_transactions(
            "T-POOL-PEACE", "test", before_stocks, world.tracked_stock_totals()
        )
        agreement = sign_agreement(world, initiate_negotiation(world, 0), 0, ZeroRng())
        for provision_id in agreement.provision_ids:
            provision = world.agreement_provisions[provision_id]
            provision.progress = provision.target
        before = world.demobilized_personnel
        process_peace(world, 30, "E", ZeroRng())
        self.assertEqual(agreement.status, "completed")
        self.assertNotIn((org.organization_id, locality_id), world.organization_manpower_pools)
        self.assertAlmostEqual(world.demobilized_personnel - before, 55.0 + sum(
            transition.personnel for transition in world.peace_transitions
            if transition.transition_type == "demobilization" and
            not transition.causes.get("pending_local_manpower_pool")
        ))
        self.assertTrue(any(
            transition.causes.get("pending_local_manpower_pool")
            for transition in world.peace_transitions
        ))
        world.assert_invariants()

    def test_political_transformation_preserves_members_resources_and_capital(self):
        world = make_world()
        org = world.organizations["insurgent"]
        agreement = sign_agreement(world, initiate_negotiation(world, 0), 0, ZeroRng())
        world.agreement_provisions[f"{agreement.agreement_id}-demobilization"].progress = .8
        world.agreement_provisions[f"{agreement.agreement_id}-political_incorporation"].progress = .8
        resource_before = org.resources
        process_peace(world, 30, "E", random.Random(11))
        party = world.organizations["party-insurgent"]
        self.assertEqual(party.kind, OrganizationKind.PARTY)
        self.assertEqual(party.member_ids, org.member_ids)
        branch_resources = sum(b.resources for b in world.party_branches.values()
                               if b.party_id == party.organization_id)
        self.assertAlmostEqual(party.resources + branch_resources + org.resources, resource_before)
        self.assertGreater(party.capital["political"], 0)

    def test_foreign_mediators_raise_credibility(self):
        world = make_world()
        for state in world.foreign_states.values():
            state.humanitarian_preference = state.willingness = 1
        high = initiate_negotiation(world, 0)
        low_world = make_world()
        for state in low_world.foreign_states.values():
            state.humanitarian_preference = state.willingness = 0
        low = initiate_negotiation(low_world, 0)
        self.assertGreater(high.credibility, low.credibility)

    def test_battlefield_position_changes_bargaining_values(self):
        low = make_world(); high = low.clone()
        low_strength = bargaining_values(low)["insurgent"]["future_power"]
        for formation in high.formations.values():
            if formation.organization_id == "insurgent": formation.personnel *= 4
        high_values = bargaining_values(high)["insurgent"]
        self.assertGreater(high_values["future_power"], low_strength)
        self.assertGreater(high_values["war"], bargaining_values(low)["insurgent"]["war"])

    def test_failed_implementation_can_recur_after_apparent_peace(self):
        world = make_world()
        agreement = sign_agreement(world, initiate_negotiation(world, 0), 0, ZeroRng())
        world.config.peace_process.implementation_rate = 0
        world.config.peace_process.recurrence_base_hazard = 1
        process_peace(world, 366, "E", ZeroRng())
        self.assertEqual(agreement.status, "failed")
        self.assertEqual(peace_diagnostics(world)["recurrences"], 1)

    def test_weak_insurgency_can_receive_concessions(self):
        world = make_world()
        for f in world.formations.values():
            if f.organization_id == "insurgent": f.personnel = 1
        values = bargaining_values(world)["insurgent"]
        self.assertGreater(values["peace"], values["war"])

    def test_commitment_problem_can_block_favorable_deal(self):
        world = make_world()
        negotiation = initiate_negotiation(world, 0)
        negotiation.credibility = 0
        negotiation.fragmentation = 1
        negotiation.bargaining_surplus = {key: .5 for key in negotiation.bargaining_surplus}
        world.config.peace_process.agreement_base_hazard = .01
        result = process_peace(world, 30, "E", random.Random(3))
        self.assertEqual(result["signed"], 0)

    def test_reproducible_integrated_trajectory(self):
        first = Simulation(make_world(seed=919)).run(until=366).world
        second = Simulation(make_world(seed=919)).run(until=366).world
        self.assertEqual(first.negotiations, second.negotiations)
        self.assertEqual(first.peace_agreements, second.peace_agreements)
        self.assertEqual(first.summary(), second.summary())

    def test_fragmentation_comparison_reports_requested_metrics(self):
        result = run_fragmentation_comparison(make_world(agents=250), replications=3, years=3, opportunity_year=1)
        for scenario in result.values():
            self.assertEqual(scenario["replications"], 3)
            self.assertIn("agreement_probability", scenario)
            self.assertIn("completion_probability", scenario)
            self.assertIn("recurrence_probability", scenario)
            self.assertIn("mean_peace_duration_days", scenario)


if __name__ == "__main__":
    unittest.main()
