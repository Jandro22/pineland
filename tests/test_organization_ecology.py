import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.organization_ecology import (
    armed_organizations, collapse_organization, form_proto_organizations,
    genealogy, mature_proto, merge_organizations, process_organization_ecology,
    recruit_and_retain, split_organization,
)


class ZeroRng:
    def random(self): return 0.0
    def uniform(self, low, high): return (low + high) / 2
    def normalvariate(self, mean, sigma): return mean


def make_world(include=True, seed=81):
    return generate_pineland(SimulationConfig(agent_count=400, locality_count=24,
                                              horizon_days=8, seed=seed,
                                              include_insurgency=include))


class OrganizationEcologyTests(unittest.TestCase):
    def test_existing_organization_has_capital_phenotype_and_leader(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        self.assertEqual(set(organization.capital), {"social", "political", "organizational", "material"})
        self.assertEqual(len(organization.phenotype), 8)
        self.assertIn(organization.leader_id, world.leaders)

    def test_peaceful_null_can_remain_without_armed_organization(self):
        world = make_world(False)
        cfg = world.config.organization_ecology
        cfg.proto_base_hazard = cfg.birth_base_hazard = 0
        Simulation(world).run(until=8)
        self.assertFalse(armed_organizations(world))
        self.assertFalse(world.organization_transitions)
        self.assertFalse(world.engagements)

    def test_endogenous_birth_from_mobilized_social_cluster(self):
        world = make_world(False)
        cfg = world.config.organization_ecology
        cfg.proto_base_hazard = cfg.birth_base_hazard = 1
        cfg.minimum_proto_members = 2
        community = next(iter(world.social_communities.values()))
        for person_id in community.member_ids:
            person = world.persons[person_id]
            person.grievance = .95
            person.public_behavior = "protest"
        protos = form_proto_organizations(world, 0, ZeroRng())
        self.assertTrue(protos)
        organization = mature_proto(world, protos[0], 1, ZeroRng())
        self.assertIsNotNone(organization)
        self.assertTrue(any(t.transition_type == "birth" for t in world.organization_transitions))
        self.assertTrue(any(f.organization_id == organization.organization_id for f in world.formations.values()))
        world.assert_invariants()

    def test_recruitment_can_add_members_while_reducing_cohesion(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        world.config.recruitment_rate = 1
        before_members = len(organization.member_ids)
        before_cohesion = organization.cohesion
        recruit_and_retain(world, 0, ZeroRng())
        self.assertGreater(len(organization.member_ids), before_members)
        self.assertLess(organization.cohesion, before_cohesion)

    def test_collapse_can_leave_nonzero_manpower(self):
        world = make_world()
        formation = world.formations["PRF-01"]
        self.assertGreater(formation.personnel, 0)
        transition = collapse_organization(world, "insurgent", 2, "cohesion_collapse")
        self.assertGreater(transition.causes["nonzero_manpower"], 0)
        self.assertEqual(formation.operational_status, "ineffective")
        self.assertEqual(world.organizations["insurgent"].status, "collapsed")

    def test_split_conserves_members_resources_and_formations(self):
        world = make_world()
        parent = world.organizations["insurgent"]
        # Supply enough members across real community structure for a meaningful split.
        additions = sorted(world.persons.values(), key=lambda p: p.person_id)[:20]
        for person in additions:
            if person.organization_id and person.organization_id != parent.organization_id:
                world.organizations[person.organization_id].member_ids.discard(person.person_id)
            person.organization_id = parent.organization_id
            parent.member_ids.add(person.person_id)
        before_members = set(parent.member_ids)
        before_resources = parent.resources
        before_formations = {f.formation_id for f in world.formations.values()
                             if f.organization_id == parent.organization_id}
        children = split_organization(world, parent.organization_id, 3, random.Random(4))
        self.assertEqual(set().union(*(c.member_ids for c in children)), before_members)
        self.assertAlmostEqual(sum(c.resources for c in children), before_resources)
        self.assertEqual({f.formation_id for f in world.formations.values()
                          if f.organization_id in {c.organization_id for c in children}}, before_formations)
        self.assertTrue(all(c.parent_ids == (parent.organization_id,) for c in children))
        world.assert_invariants()

    def test_merge_conserves_transition_stocks_and_records_genealogy(self):
        world = make_world()
        first = world.organizations["insurgent"]
        children = split_organization(world, first.organization_id, 2, random.Random(2))
        resources = sum(child.resources for child in children)
        members = set().union(*(child.member_ids for child in children))
        merged = merge_organizations(world, children[0].organization_id,
                                     children[1].organization_id, 4, random.Random(3))
        self.assertAlmostEqual(merged.resources, resources)
        self.assertEqual(merged.member_ids, members)
        self.assertEqual(set(genealogy(world, merged.organization_id)["parents"]),
                         {child.organization_id for child in children})
        self.assertLess(merged.cohesion, max(child.cohesion for child in children))
        world.assert_invariants()

    def test_military_losses_reduce_organizational_cohesion(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        formation = world.formations["PRF-01"]
        formation.cumulative_losses = formation.personnel
        before = organization.cohesion
        world.config.organization_ecology.split_base_hazard = 0
        world.config.organization_ecology.collapse_base_hazard = 0
        process_organization_ecology(world, 7, random.Random(7))
        self.assertLess(organization.cohesion, before)

    def test_adaptation_preserves_distinct_bounded_phenotypes(self):
        world = make_world()
        children = split_organization(world, "insurgent", 2, random.Random(12))
        before = [dict(child.phenotype) for child in children]
        world.config.organization_ecology.split_base_hazard = 0
        world.config.organization_ecology.merger_base_hazard = 0
        world.config.organization_ecology.collapse_base_hazard = 0
        process_organization_ecology(world, 7, random.Random(13))
        self.assertNotEqual(before, [child.phenotype for child in children])
        self.assertNotEqual(children[0].phenotype, children[1].phenotype)
        self.assertTrue(all(0 <= value <= 1 for child in children
                            for value in child.phenotype.values()))

    def test_matched_seed_ecology_is_reproducible(self):
        first = Simulation(make_world(seed=99)).run(until=8).world
        second = Simulation(make_world(seed=99)).run(until=8).world
        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.organization_transitions, second.organization_transitions)

    def test_onset_is_a_probabilistic_regime(self):
        outcomes = []
        for seed in range(30):
            world = make_world(False, seed=9)
            world.config.organization_ecology.proto_base_hazard = .08
            world.config.organization_ecology.minimum_proto_members = 2
            community = next(iter(world.social_communities.values()))
            community.cohesion = .9
            for pid in community.member_ids:
                world.persons[pid].grievance = .9
                world.persons[pid].public_behavior = "protest"
            outcomes.append(bool(form_proto_organizations(world, 0, random.Random(seed))))
        self.assertTrue(any(outcomes))
        self.assertTrue(any(not outcome for outcome in outcomes))

    def test_network_cohesion_changes_onset_under_identical_macro_state(self):
        outcomes = []
        for cohesion in (.05, .95):
            world = make_world(False, seed=9)
            world.config.organization_ecology.proto_base_hazard = .08
            world.config.organization_ecology.minimum_proto_members = 2
            community = next(iter(world.social_communities.values()))
            community.cohesion = cohesion
            for pid in community.member_ids:
                world.persons[pid].grievance = .9
                world.persons[pid].public_behavior = "protest"
            outcomes.append(bool(form_proto_organizations(world, 0, random.Random(1))))
        self.assertEqual(outcomes, [False, True])

    def test_leadership_succession_is_explicit_and_causal(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        previous = organization.leader_id
        cfg = world.config.organization_ecology
        cfg.succession_base_hazard = 1
        cfg.split_base_hazard = cfg.merger_base_hazard = cfg.collapse_base_hazard = 0
        process_organization_ecology(world, 7, ZeroRng())
        self.assertNotEqual(organization.leader_id, previous)
        self.assertFalse(world.leaders[previous].active)
        self.assertTrue(any(t.transition_type == "succession" for t in world.organization_transitions))


if __name__ == "__main__":
    unittest.main()
