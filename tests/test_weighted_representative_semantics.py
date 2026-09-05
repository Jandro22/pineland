import random
import unittest
from types import SimpleNamespace

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.combat import resolve_engagement
from pineland_sim.entities import SocialCommunity
from pineland_sim.foreign_affairs import process_cross_border_mobility
from pineland_sim.networks import (_balanced_household_groups, _language_profile,
                                   locality_social_aggregation, network_diagnostics)
from pineland_sim.organization_ecology import recruit_and_retain
from pineland_sim.peace_process import (_implement, initiate_negotiation,
                                        sign_agreement)
from pineland_sim.political_order import political_diagnostics, run_election


class ZeroRng:
    def random(self):
        return 0.0

    def normalvariate(self, mean, sigma):
        return mean


class WeightedRepresentativeSemanticsTests(unittest.TestCase):
    RESOLUTIONS = (120, 240, 480)

    @classmethod
    def setUpClass(cls):
        cls.worlds = {}
        for agents in cls.RESOLUTIONS:
            config = SimulationConfig(
                agent_count=agents,
                locality_count=17,
                horizon_days=1,
                seed=20260904,
            )
            cls.worlds[agents] = generate_pineland(config)

    def test_matched_worlds_conserve_the_same_represented_population(self):
        represented = [self.worlds[count].weighted_population()
                       for count in self.RESOLUTIONS]
        for value in represented[1:]:
            self.assertAlmostEqual(value, represented[0], places=6)

    def test_force_decomposition_and_origin_are_resolution_invariant(self):
        fingerprints = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count]
            fingerprints.append([
                (formation.formation_id, formation.organization_id,
                 formation.locality_id, formation.personnel)
                for formation in sorted(world.formations.values(),
                                        key=lambda item: item.formation_id)
                if formation.organization_id in {"fdf", "insurgent"}
            ])
        self.assertTrue(all(row == fingerprints[0] for row in fingerprints[1:]))

    def test_election_allocates_fractional_represented_voting_mass_invariantly(self):
        outcomes = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            parties = sorted((organization for organization in world.organizations.values()
                              if organization.kind.value == "party"),
                             key=lambda organization: organization.organization_id)
            for branch in world.party_branches.values():
                branch.electoral_support = 0.0
                branch.patronage_stock = 0.0
            preferences = {party.organization_id: value
                           for party, value in zip(parties, (.8, .4, .2))}
            for person in world.persons.values():
                person.political_access = .8
                person.state_legitimacy = .7
                person.party_legitimacy = dict(preferences)
                person.private_preference = dict(preferences)
            election = run_election(world, 10, random.Random(999))
            represented = world.weighted_population()
            self.assertAlmostEqual(sum(election.votes.values()) + election.abstention,
                                   represented, places=6)
            outcomes.append((
                tuple(election.votes[party.organization_id] / represented
                      for party in parties),
                election.abstention / represented,
                election.winner_party_id,
            ))
        for outcome in outcomes[1:]:
            for left, right in zip(outcome[0], outcomes[0][0]):
                self.assertAlmostEqual(left, right, places=12)
            self.assertAlmostEqual(outcome[1], outcomes[0][1], places=12)
            self.assertEqual(outcome[2], outcomes[0][2])

    def test_cross_border_mobility_returns_represented_population_not_agent_count(self):
        totals = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            represented = world.weighted_population()
            departures, _ = process_cross_border_mobility(world, 1, ZeroRng())
            self.assertAlmostEqual(departures, represented, places=6)
            self.assertAlmostEqual(world.summary()["external_migrants"],
                                   represented, places=6)
            self.assertEqual(world.summary()["external_migrant_agents"],
                             len(world.persons))
            _, returns = process_cross_border_mobility(world, 2, ZeroRng())
            self.assertAlmostEqual(returns, represented, places=6)
            totals.append((departures, returns))
        for row in totals[1:]:
            self.assertAlmostEqual(row[0], totals[0][0], places=6)
            self.assertAlmostEqual(row[1], totals[0][1], places=6)

    def test_recruitment_mass_is_resolution_invariant_under_matched_conditions(self):
        recruited = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            organization = world.organizations["insurgent"]
            organization.member_ids.clear()
            world.config.recruitment_rate = 1.0
            world.config.organization_ecology.recruitment_requires_access = False
            world.config.organization_ecology.recruitment_subcohorts = 20
            for person in world.persons.values():
                person.organization_id = None
                person.armed_fraction = 0.0
                person.grievance = .8
                person.fear = .1
                person.political_access = .2
            result = recruit_and_retain(world, 0, ZeroRng())
            # ZeroRng makes every Bernoulli microcohort hazard draw succeed.
            # Under continuous-time interval hazards all eligible subcohorts
            # therefore recruit; the invariant quantity is represented
            # population, not the former arbitrary one-cohort-per-update cap.
            expected = world.weighted_population()
            self.assertAlmostEqual(result["recruits"], expected, places=6)
            recruited.append(result["recruits"])
        for value in recruited[1:]:
            self.assertAlmostEqual(value, recruited[0], places=6)

    def test_fractional_recruitment_has_no_unreachable_remainder_at_any_resolution(self):
        remainder = .013
        recruited = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            organization = world.organizations["insurgent"]
            organization.member_ids = set(world.persons)
            world.config.recruitment_rate = 1.0
            world.config.organization_ecology.recruitment_requires_access = False
            world.config.organization_ecology.recruitment_subcohorts = 20
            for person in world.persons.values():
                person.organization_id = organization.organization_id
                person.armed_fraction = 1.0 - remainder
                person.grievance = .8
                person.fear = .1
                person.political_access = .2
            result = recruit_and_retain(world, 0, ZeroRng())
            expected = world.weighted_population() * remainder
            self.assertAlmostEqual(result["recruits"], expected, places=6)
            self.assertTrue(all(abs(person.armed_fraction - 1.0) <= 1e-12
                                for person in world.persons.values()))
            recruited.append(result["recruits"])
        for value in recruited[1:]:
            self.assertAlmostEqual(value, recruited[0], places=6)

    def test_combat_losses_and_civilian_harm_ignore_civilian_agent_resolution(self):
        outcomes = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            government = world.formations["FDF-01"]
            insurgent = world.formations["PRF-01"]
            insurgent.locality_id = government.locality_id
            insurgent.current_microzone_id = government.current_microzone_id
            engagement, _ = resolve_engagement(
                world, "E-weighted", government, insurgent,
                (government.organization_id, insurgent.organization_id),
                0, random.Random(4815),
            )
            outcomes.append((
                engagement.personnel_losses[government.formation_id],
                engagement.personnel_losses[insurgent.formation_id],
                engagement.civilian_harm,
            ))
        for outcome in outcomes[1:]:
            for value, reference in zip(outcome, outcomes[0]):
                self.assertAlmostEqual(value, reference, places=9)

    def test_ddr_demobilizes_continuous_formation_manpower_invariantly(self):
        outcomes = []
        for count in self.RESOLUTIONS:
            world = self.worlds[count].clone()
            negotiation = initiate_negotiation(world, 0)
            agreement = sign_agreement(world, negotiation, 0, ZeroRng())
            for provision_id in agreement.provision_ids:
                provision = world.agreement_provisions[provision_id]
                provision.progress = 0.0
                provision.government_will = .8
                provision.insurgent_will = .8
                provision.institutional_resistance = .2
                provision.monitoring = .8
                provision.status = "pending"
            demobilization = world.agreement_provisions[
                f"{agreement.agreement_id}-demobilization"
            ]
            demobilization.progress = .8
            before = world.demobilized_personnel
            _implement(world, agreement, 30, "E-ddr", ZeroRng())
            outcomes.append(world.demobilized_personnel - before)
        for value in outcomes[1:]:
            self.assertAlmostEqual(value, outcomes[0], places=9)

    def test_language_profiles_and_population_diagnostics_use_weights(self):
        world = self.worlds[self.RESOLUTIONS[0]].clone()
        first_id, second_id = list(world.persons)[:2]
        first, second = world.persons[first_id], world.persons[second_id]
        first.weight, second.weight = 9.0, 1.0
        for language in first.languages:
            first.languages[language] = 0.0
            second.languages[language] = 0.0
        first.languages["FS"] = 1.0
        second.languages["AR"] = 1.0
        profile = _language_profile(world, [first_id, second_id])
        self.assertAlmostEqual(profile["FS"], .9)
        self.assertAlmostEqual(profile["AR"], .1)

        for index, person in enumerate(world.persons.values(), 1):
            person.weight = float(index)
            person.state_legitimacy = index / len(world.persons)
            person.government_legitimacy = 1 - person.state_legitimacy
            person.political_access = .25 + .5 * person.state_legitimacy
        diagnostics = political_diagnostics(world)
        total = sum(person.weight for person in world.persons.values())
        self.assertAlmostEqual(
            diagnostics["mean_state_legitimacy"],
            sum(person.weight * person.state_legitimacy
                for person in world.persons.values()) / total,
        )

    def test_community_aggregation_and_network_statistics_expose_represented_weight(self):
        world = self.worlds[self.RESOLUTIONS[0]].clone()
        first_id, second_id = list(world.persons)[:2]
        locality_id = world.persons[first_id].residence_locality_id
        world.persons[first_id].weight = 9.0
        world.persons[second_id].weight = 1.0
        world.social_communities = {
            "weighted-a": SocialCommunity(
                "weighted-a", locality_id, [first_id],
                dict(world.persons[first_id].languages), .5,
                government_cooperation=1.0, insurgent_sympathy=0.0,
            ),
            "weighted-b": SocialCommunity(
                "weighted-b", locality_id, [second_id],
                dict(world.persons[second_id].languages), .5,
                government_cooperation=0.0, insurgent_sympathy=1.0,
            ),
        }
        aggregate = locality_social_aggregation(world, locality_id)
        self.assertAlmostEqual(aggregate["government_cooperation"], .9)
        self.assertAlmostEqual(aggregate["insurgent_sympathy"], .1)

        diagnostics = network_diagnostics(self.worlds[self.RESOLUTIONS[0]])
        expected_degree = sum(
            person.weight * len(self.worlds[self.RESOLUTIONS[0]].social_neighbors[person.person_id])
            for person in self.worlds[self.RESOLUTIONS[0]].persons.values()
        ) / self.worlds[self.RESOLUTIONS[0]].weighted_population()
        self.assertAlmostEqual(diagnostics["represented_mean_degree"], expected_degree)

    def test_community_partition_targets_represented_population_across_resolutions(self):
        represented_total = 120_000.0
        group_counts = []
        for agents in (100, 200, 400):
            weight = represented_total / agents
            persons = {
                f"P{index}": SimpleNamespace(weight=weight)
                for index in range(agents)
            }
            households = {
                f"H{index}": SimpleNamespace(member_ids=[f"P{index}"])
                for index in range(agents)
            }
            world = SimpleNamespace(persons=persons, households=households)
            groups = _balanced_household_groups(
                world, list(households), 6_000.0, 12_000.0, 18_000.0,
                random.Random(7),
            )
            represented_groups = [
                sum(persons[households[household_id].member_ids[0]].weight
                    for household_id in group)
                for group in groups
            ]
            self.assertEqual(len(groups), 10)
            self.assertTrue(all(abs(value - 12_000.0) <= 1e-8
                                for value in represented_groups))
            group_counts.append(len(groups))
        self.assertEqual(group_counts, [10, 10, 10])


if __name__ == "__main__":
    unittest.main()
