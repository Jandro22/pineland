import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.political_order import process_political_order, run_election
from pineland_sim.organization_ecology import recruit_and_retain


def make_world(seed=311, insurgency=True):
    return generate_pineland(SimulationConfig(agent_count=500, locality_count=24,
                                              horizon_days=35, seed=seed,
                                              include_insurgency=insurgency))


class PoliticalOrderTests(unittest.TestCase):
    def test_institutional_ecosystem_parties_branches_and_elites_exist(self):
        world = make_world()
        kinds = {institution.institution_type for institution in world.political_institutions.values()}
        self.assertTrue({"executive", "legislature", "civil_administration", "judiciary",
                         "military", "police", "district_government",
                         "municipal_government"}.issubset(kinds))
        self.assertEqual(len(world.party_branches), 3 * len(world.localities))
        self.assertTrue(world.local_elites)

    def test_state_government_and_party_legitimacy_are_distinct(self):
        person = next(iter(make_world().persons.values()))
        self.assertNotEqual(person.state_legitimacy, person.government_legitimacy)
        self.assertTrue(person.party_legitimacy)
        self.assertNotEqual(person.government_legitimacy,
                            next(iter(person.party_legitimacy.values())))

    def test_election_changes_party_power_without_rewriting_control(self):
        world = make_world()
        before = {lid: loc.control["government"].to_dict() for lid, loc in world.localities.items()}
        for person in world.persons.values():
            person.political_access = person.state_legitimacy = 1
            for party_id in person.party_legitimacy:
                person.party_legitimacy[party_id] = 1 if party_id == "party-2" else .001
                person.private_preference[party_id] = 1 if party_id == "party-2" else .001
        election = run_election(world, 180, random.Random(4))
        self.assertEqual(election.winner_party_id, "party-2")
        self.assertEqual(before, {lid: loc.control["government"].to_dict()
                                  for lid, loc in world.localities.items()})

    def test_policy_budget_is_conserved_across_destinations(self):
        world = make_world()
        government_before = world.organizations["government"].resources
        branch_before = sum(b.patronage_stock for b in world.party_branches.values())
        elite_before = sum(e.resources for e in world.local_elites.values())
        private_before = world.private_diversion_stock
        spent_before = world.cumulative_public_spending
        result = process_political_order(world, 30, "E-policy", random.Random(2))
        allocated = ((sum(b.patronage_stock for b in world.party_branches.values()) - branch_before) +
                     (sum(e.resources for e in world.local_elites.values()) - elite_before) +
                     world.private_diversion_stock - private_before +
                     world.cumulative_public_spending - spent_before)
        self.assertAlmostEqual(government_before - world.organizations["government"].resources,
                               result["budget"])
        self.assertAlmostEqual(allocated, result["budget"], places=6)

    def test_corruption_redistributes_and_can_raise_loyalty_while_hurting_capacity(self):
        world = make_world()
        cfg = world.config.political_order
        cfg.public_budget_share, cfg.patronage_share, cfg.private_diversion_share = .2, .7, .1
        institution = next(i for i in world.political_institutions.values() if i.level == "municipal")
        locality_people = [p for p in world.persons.values()
                           if p.residence_locality_id == institution.locality_id]
        before_capacity = institution.capacity
        before_party = sum(p.party_legitimacy[world.ruling_party_id] for p in locality_people)
        process_political_order(world, 30, "E-policy", random.Random(3))
        after_party = sum(p.party_legitimacy[world.ruling_party_id] for p in locality_people)
        self.assertGreater(world.private_diversion_stock, 0)
        self.assertTrue(any(branch.patronage_stock > 0 for branch in world.party_branches.values()))
        self.assertLess(institution.capacity, before_capacity)
        self.assertGreaterEqual(after_party, before_party)

    def test_identical_federal_policy_is_locally_distorted(self):
        world = make_world()
        process_political_order(world, 30, "E-policy", random.Random(5))
        qualities = {round(item.implementation_quality, 6) for item in world.policy_implementations}
        outputs = {round(item.service_output["services"], 6) for item in world.policy_implementations}
        self.assertGreater(len(qualities), 1)
        self.assertGreater(len(outputs), 1)

    def test_capacity_moves_slowly_relative_to_policy_spending(self):
        world = make_world()
        before = {key: item.capacity for key, item in world.political_institutions.items()}
        process_political_order(world, 30, "E-policy", random.Random(6))
        largest = max(abs(world.political_institutions[key].capacity - value)
                      for key, value in before.items())
        self.assertLess(largest, .05)
        self.assertGreater(world.cumulative_public_spending, 0)

    def test_peaceful_channels_reduce_recruitment(self):
        low = make_world(seed=55)
        high = low.clone()
        low.config.recruitment_rate = high.config.recruitment_rate = .12
        low.config.political_order.peaceful_channel_strength = 0
        high.config.political_order.peaceful_channel_strength = 1
        for person in low.persons.values():
            person.political_access = 1
        for person in high.persons.values():
            person.political_access = 1
        low_result = recruit_and_retain(low, 0, random.Random(10))
        high_result = recruit_and_retain(high, 0, random.Random(10))
        self.assertGreaterEqual(low_result["recruits"], high_result["recruits"])

    def test_governance_improvement_reduces_recruitment_without_deleting_org(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        for person in world.persons.values():
            person.political_access = 1
            person.grievance *= .2
        world.config.political_order.peaceful_channel_strength = 1
        world.config.recruitment_rate = .1
        before = organization.organization_id in world.organizations
        result = recruit_and_retain(world, 30, random.Random(12))
        self.assertTrue(before and organization.organization_id in world.organizations)
        self.assertLess(result["recruits"], world.weighted_population() * .1)

    def test_no_insurgency_world_retains_contentious_peaceful_politics(self):
        world = Simulation(make_world(insurgency=False)).run(until=35).world
        self.assertTrue(world.elections)
        self.assertFalse(world.engagements)
        self.assertTrue(any(p.public_behavior in {"protest", "party_participation", "civil_society"}
                            for p in world.persons.values()))

    def test_political_trajectory_is_reproducible(self):
        first = Simulation(make_world(seed=818)).run(until=35).world
        second = Simulation(make_world(seed=818)).run(until=35).world
        self.assertEqual(first.elections, second.elections)
        self.assertEqual(first.policy_implementations, second.policy_implementations)
        self.assertEqual(first.summary(), second.summary())


if __name__ == "__main__":
    unittest.main()
