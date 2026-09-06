import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import ActorBelief, ControlVector, PresenceBelief, SocialCommunity
from pineland_sim.organization_ecology import (
    armed_organizations, collapse_organization, form_proto_organizations,
    genealogy, mature_proto, merge_organizations, process_organization_ecology,
    recruit_and_retain, represented_armed_membership, split_organization,
    _adapt, _apply_local_fighter_change, _interval_hazard_probability,
    _proto_member_fractions, _reference_cycle_probability,
    _reference_cycle_survival_factor,
)


class ZeroRng:
    def random(self): return 0.0
    def uniform(self, low, high): return (low + high) / 2
    def normalvariate(self, mean, sigma): return mean


class ConstantRng(ZeroRng):
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def make_world(include=True, seed=81):
    return generate_pineland(SimulationConfig(agent_count=400, locality_count=24,
                                              horizon_days=8, seed=seed,
                                              include_insurgency=include))


class OrganizationEcologyTests(unittest.TestCase):
    def test_reference_cycle_probability_composes_across_scheduler_partitions(self):
        weekly = _reference_cycle_probability(.2, 7.0)
        daily = _reference_cycle_probability(.2, 1.0)
        fortnight = _reference_cycle_probability(.2, 14.0)
        self.assertAlmostEqual(weekly, .2, places=12)
        self.assertAlmostEqual(weekly, 1 - (1 - daily) ** 7, places=12)
        self.assertAlmostEqual(fortnight, 1 - (1 - weekly) ** 2, places=12)

    def test_reference_cycle_decay_composes_and_preserves_default_week(self):
        weekly = _reference_cycle_survival_factor(.08, 7.0)
        daily = _reference_cycle_survival_factor(.08, 1.0)
        fortnight = _reference_cycle_survival_factor(.08, 14.0)
        self.assertAlmostEqual(weekly, .92, places=12)
        self.assertAlmostEqual(weekly, daily ** 7, places=12)
        self.assertAlmostEqual(fortnight, weekly ** 2, places=12)

    def test_recruitment_hazard_composes_across_numerical_intervals(self):
        daily = _interval_hazard_probability(.03, .6, 1.0)
        weekly = _interval_hazard_probability(.03, .6, 7.0)
        self.assertAlmostEqual(weekly, 1 - (1 - daily) ** 7, places=12)

    def test_recruitment_and_membership_exit_have_independent_hazard_scales(self):
        exit_only = make_world(seed=8811)
        exit_org = exit_only.organizations["insurgent"]
        before_exit = represented_armed_membership(exit_only, exit_org)
        exit_only.config.recruitment_rate = 0.0
        exit_only.config.membership_exit_rate = 10.0
        exit_result = recruit_and_retain(exit_only, 0.0, ZeroRng(), interval_days=1.0)
        self.assertEqual(exit_result["recruits"], 0.0)
        self.assertGreater(exit_result["exits"], 0.0)
        self.assertLess(represented_armed_membership(exit_only, exit_org), before_exit)

        recruit_only = make_world(seed=8811)
        recruit_org = recruit_only.organizations["insurgent"]
        before_recruit = represented_armed_membership(recruit_only, recruit_org)
        recruit_only.config.recruitment_rate = 10.0
        recruit_only.config.membership_exit_rate = 0.0
        recruit_result = recruit_and_retain(recruit_only, 0.0, ZeroRng(), interval_days=1.0)
        self.assertGreater(recruit_result["recruits"], 0.0)
        self.assertEqual(recruit_result["exits"], 0.0)
        self.assertGreater(represented_armed_membership(recruit_only, recruit_org), before_recruit)

    def test_zero_recruitment_and_zero_exit_leave_membership_unchanged(self):
        world = make_world(seed=8812)
        organization = world.organizations["insurgent"]
        before = represented_armed_membership(world, organization)
        world.config.recruitment_rate = 0.0
        world.config.membership_exit_rate = 0.0
        result = recruit_and_retain(world, 0.0, ZeroRng(), interval_days=1.0)
        self.assertEqual(result["recruits"], 0.0)
        self.assertEqual(result["exits"], 0.0)
        self.assertEqual(represented_armed_membership(world, organization), before)

    def test_full_exit_separates_armed_loss_from_residual_sympathy(self):
        retained = make_world(seed=8813)
        retained_org = retained.organizations["insurgent"]
        retained_member_id = next(iter(sorted(retained_org.member_ids)))
        retained.config.recruitment_rate = 0.0
        retained.config.membership_exit_rate = 10.0
        retained.config.organization_ecology.exit_sympathy_retention = 1.0
        recruit_and_retain(retained, 0.0, ZeroRng(), interval_days=1.0)
        retained_person = retained.persons[retained_member_id]
        self.assertEqual(retained_person.armed_fraction, 0.0)
        self.assertEqual(retained_person.public_behavior, "insurgent_sympathy")

        disengaged = make_world(seed=8813)
        disengaged_org = disengaged.organizations["insurgent"]
        disengaged_member_id = next(iter(sorted(disengaged_org.member_ids)))
        self.assertEqual(disengaged_member_id, retained_member_id)
        disengaged.config.recruitment_rate = 0.0
        disengaged.config.membership_exit_rate = 10.0
        disengaged.config.organization_ecology.exit_sympathy_retention = 0.0
        recruit_and_retain(disengaged, 0.0, ZeroRng(), interval_days=1.0)
        disengaged_person = disengaged.persons[disengaged_member_id]
        self.assertEqual(disengaged_person.armed_fraction, 0.0)
        self.assertEqual(disengaged_person.public_behavior, "neutral")
        self.assertNotIn("insurgent", disengaged_person.social_exposure)

    def test_moving_formation_is_not_a_local_recruitment_access_channel(self):
        world = make_world(seed=20260905)
        organization = world.organizations["insurgent"]
        formation = world.formations["PRF-01"]
        locality_id = formation.locality_id
        local_formations = [
            item for item in world.formations.values()
            if item.organization_id == organization.organization_id
            and item.locality_id == locality_id
        ]
        for person in world.persons.values():
            if (person.residence_locality_id == locality_id and
                    person.organization_id == organization.organization_id):
                organization.member_ids.discard(person.person_id)
                person.organization_id = None
                person.armed_fraction = 0.0
        candidate = next(
            person for person in world.persons.values()
            if person.residence_locality_id == locality_id and person.organization_id is None
        )
        candidate.social_exposure.clear()
        candidate.grievance = 1.0
        candidate.fear = 0.0
        candidate.political_access = 0.0
        candidate.identities["federal"] = organization.ideology.get("reform", .5)
        world.config.recruitment_rate = 10.0

        moving = world.clone()
        for item in moving.formations.values():
            if item.organization_id == organization.organization_id and item.locality_id == locality_id:
                item.moving = True
        recruit_and_retain(moving, 0.0, ZeroRng(), interval_days=1.0)
        self.assertIsNone(moving.persons[candidate.person_id].organization_id)

        stationary = world.clone()
        recruit_and_retain(stationary, 0.0, ZeroRng(), interval_days=1.0)
        self.assertEqual(
            stationary.persons[candidate.person_id].organization_id,
            organization.organization_id,
        )

    def test_local_recruits_are_not_absorbed_into_formation_in_transit(self):
        world = make_world(seed=20260905)
        organization = world.organizations["insurgent"]
        formation = world.formations["PRF-01"]
        formation.moving = True
        locality_id = formation.locality_id
        before = formation.personnel
        pool_key = (organization.organization_id, locality_id)
        world.organization_manpower_pools[pool_key] = 0.0
        applied, created = _apply_local_fighter_change(
            world, organization, locality_id, 10.0
        )
        # Political recruitment below the unit threshold does not become an
        # unequipped fighter pool merely because the local formation is moving.
        self.assertEqual(applied, 0.0)
        self.assertEqual(created, 0)
        self.assertEqual(formation.personnel, before)
        self.assertEqual(world.organization_manpower_pools.get(pool_key, 0.0), 0.0)

    def test_observed_active_interval_preserves_identity_not_operations(self):
        world = make_world()
        cfg = world.config.organization_ecology
        cfg.observed_active_intervals = {"insurgent": [[0, 20]]}
        cfg.collapse_base_hazard = cfg.split_base_hazard = 1.0
        organization = world.organizations["insurgent"]
        organization.cohesion = 0.0
        organization.resources = 0.0
        before_readiness = [f.readiness for f in world.formations.values()
                            if f.organization_id == "insurgent"]
        process_organization_ecology(world, 7, ZeroRng())
        self.assertEqual(organization.status, "active")
        self.assertTrue(any(f.organization_id == "insurgent" for f in world.formations.values()))
        self.assertNotEqual([f.readiness for f in world.formations.values()
                             if f.organization_id == "insurgent"], [])
        self.assertEqual(len(before_readiness), sum(f.organization_id == "insurgent"
                                                    for f in world.formations.values()))

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

    def test_recruitment_manpower_is_local_not_prf01_sink(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        prf01 = world.formations["PRF-01"]
        target = next(f for f in world.formations.values()
                      if f.organization_id == "insurgent" and f.formation_id != "PRF-01")
        before_first = prf01.personnel
        before_local = sum(f.personnel for f in world.formations.values()
                           if f.organization_id == organization.organization_id and
                           f.locality_id == target.locality_id)
        before_pool = world.organization_manpower_pools.get(
            (organization.organization_id, target.locality_id), 0.0
        )
        before_resources = organization.resources
        before_supply = sum(
            f.supply_stock for f in world.formations.values()
            if f.organization_id == organization.organization_id
        )
        applied, created = _apply_local_fighter_change(
            world, organization, target.locality_id, 125.0
        )
        self.assertAlmostEqual(applied, 125.0)
        converted = (
            125.0 * world.config.logistics.formation_supply_days
            * world.config.logistics.initial_supply_fraction
        )
        self.assertAlmostEqual(
            before_resources - organization.resources, converted,
        )
        self.assertAlmostEqual(
            sum(f.supply_stock for f in world.formations.values()
                if f.organization_id == organization.organization_id) - before_supply,
            converted,
        )
        self.assertEqual(prf01.personnel, before_first)
        after_local = sum(f.personnel for f in world.formations.values()
                          if f.organization_id == organization.organization_id and
                          f.locality_id == target.locality_id)
        after_pool = world.organization_manpower_pools.get(
            (organization.organization_id, target.locality_id), 0.0
        )
        self.assertAlmostEqual((after_local - before_local) + (after_pool - before_pool), 125.0)
        self.assertTrue(all(
            f.personnel <= world.config.force_structure.insurgent_target_personnel + 1e-9
            for f in world.formations.values()
            if f.organization_id == organization.organization_id and
            f.locality_id == target.locality_id
        ))
        self.assertGreaterEqual(created, 0)

    def test_recruitment_can_materialize_new_local_formation(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        occupied = {f.locality_id for f in world.formations.values()
                    if f.organization_id == organization.organization_id}
        locality_id = next(key for key in world.localities if key not in occupied)
        before = set(world.formations)
        applied, created = _apply_local_fighter_change(
            world, organization, locality_id,
            world.config.organization_ecology.minimum_formation_personnel + 10.0,
        )
        self.assertGreater(applied, 0)
        self.assertEqual(created, 1)
        new_ids = set(world.formations) - before
        self.assertEqual(len(new_ids), 1)
        formation = world.formations[new_ids.pop()]
        self.assertEqual(formation.locality_id, locality_id)
        self.assertNotEqual(formation.formation_id, "PRF-01")

    def test_fractional_recruitment_step_is_bounded(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        world.config.recruitment_rate = 1.0
        world.config.organization_ecology.recruitment_subcohorts = 20
        candidate = next(p for p in world.persons.values() if p.organization_id is None)
        # Make every other civilian ineligible so the result isolates one
        # representative person's transition.
        for person in world.persons.values():
            if person is not candidate and person.organization_id is None:
                person.organization_id = "government"
        before_fraction = candidate.armed_fraction
        recruit_and_retain(world, 0, ZeroRng())
        self.assertLessEqual(
            candidate.armed_fraction - before_fraction,
            1 / world.config.organization_ecology.recruitment_subcohorts + 1e-12,
        )

    def test_fractional_recruitment_can_fill_subcohort_remainder(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        candidate = next(p for p in world.persons.values() if p.organization_id is None)
        candidate.organization_id = organization.organization_id
        candidate.armed_fraction = .98
        organization.member_ids.add(candidate.person_id)
        for person in world.persons.values():
            if person is not candidate and person.organization_id is None:
                person.organization_id = "government"
        world.config.recruitment_rate = 1.0
        world.config.organization_ecology.recruitment_subcohorts = 20
        recruit_and_retain(world, 0, ZeroRng())
        self.assertEqual(candidate.armed_fraction, 1.0)

    def test_existing_organization_recruitment_requires_a_real_access_channel(self):
        config = SimulationConfig(agent_count=400, locality_count=24, horizon_days=2, seed=812)
        config.force_structure.mode = "legacy"
        world = generate_pineland(config)
        organization = world.organizations["insurgent"]
        formation_localities = {f.locality_id for f in world.formations.values()
                                if f.organization_id == organization.organization_id}
        member_localities = {world.persons[pid].residence_locality_id
                             for pid in organization.member_ids}
        candidate = next(
            person for person in world.persons.values()
            if person.organization_id is None and
            person.residence_locality_id not in formation_localities | member_localities
        )
        candidate.social_exposure.clear()
        world.config.recruitment_rate = 1.0
        recruit_and_retain(world, 0, ZeroRng())
        self.assertIsNone(candidate.organization_id)
        self.assertEqual(candidate.armed_fraction, 0.0)

        candidate.social_exposure["insurgent"] = .5
        recruit_and_retain(world, 7, ZeroRng())
        self.assertEqual(candidate.organization_id, organization.organization_id)
        self.assertGreater(candidate.armed_fraction, 0.0)

    def test_collapse_can_leave_nonzero_manpower(self):
        world = make_world()
        formation = world.formations["PRF-01"]
        pool_key = ("insurgent", formation.locality_id)
        before_stocks = world.tracked_stock_totals()
        world.organization_manpower_pools[pool_key] = 42.0
        world.record_stock_transactions(
            "T-POOL-COLLAPSE", "test", before_stocks, world.tracked_stock_totals()
        )
        self.assertGreater(formation.personnel, 0)
        transition = collapse_organization(world, "insurgent", 2, "cohesion_collapse")
        self.assertGreater(transition.causes["nonzero_manpower"], 0)
        self.assertEqual(transition.causes["pooled_demobilized"], 42.0)
        self.assertNotIn(pool_key, world.organization_manpower_pools)
        self.assertGreaterEqual(world.demobilized_personnel, 42.0)
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
        pool_key = (parent.organization_id, world.formations["PRF-01"].locality_id)
        before_stocks = world.tracked_stock_totals()
        world.organization_manpower_pools[pool_key] = 60.0
        world.record_stock_transactions(
            "T-POOL-SPLIT", "test", before_stocks, world.tracked_stock_totals()
        )
        children = split_organization(world, parent.organization_id, 3, random.Random(4))
        self.assertEqual(set().union(*(c.member_ids for c in children)), before_members)
        self.assertAlmostEqual(sum(c.resources for c in children), before_resources)
        self.assertEqual({f.formation_id for f in world.formations.values()
                          if f.organization_id in {c.organization_id for c in children}}, before_formations)
        self.assertNotIn(pool_key, world.organization_manpower_pools)
        self.assertAlmostEqual(sum(
            quantity for (organization_id, _), quantity in world.organization_manpower_pools.items()
            if organization_id in {child.organization_id for child in children}
        ), 60.0)
        self.assertTrue(all(c.parent_ids == (parent.organization_id,) for c in children))
        world.assert_invariants()

    def test_merge_conserves_transition_stocks_and_records_genealogy(self):
        world = make_world()
        first = world.organizations["insurgent"]
        children = split_organization(world, first.organization_id, 2, random.Random(2))
        locality_id = next(iter(world.localities))
        before_stocks = world.tracked_stock_totals()
        world.organization_manpower_pools[(children[0].organization_id, locality_id)] = 25.0
        world.organization_manpower_pools[(children[1].organization_id, locality_id)] = 35.0
        world.record_stock_transactions(
            "T-POOL-MERGE", "test", before_stocks, world.tracked_stock_totals()
        )
        resources = sum(child.resources for child in children)
        members = set().union(*(child.member_ids for child in children))
        merged = merge_organizations(world, children[0].organization_id,
                                     children[1].organization_id, 4, random.Random(3))
        self.assertAlmostEqual(merged.resources, resources)
        self.assertEqual(merged.member_ids, members)
        self.assertEqual(set(genealogy(world, merged.organization_id)["parents"]),
                         {child.organization_id for child in children})
        self.assertEqual(world.organization_manpower_pools[(merged.organization_id, locality_id)], 60.0)
        self.assertFalse(any(key[0] in {children[0].organization_id, children[1].organization_id}
                             for key in world.organization_manpower_pools))
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

    def test_proto_onset_threshold_is_represented_population_not_agent_count(self):
        world = make_world(False, seed=9)
        cfg = world.config.organization_ecology
        cfg.proto_base_hazard = 1.0
        cfg.minimum_proto_members = 100
        cfg.minimum_proto_represented_population = 1_000.0
        community = next(iter(world.social_communities.values()))
        first = world.persons[community.member_ids[0]]
        first.grievance = .95
        first.public_behavior = "protest"
        for pid in community.member_ids[1:]:
            world.persons[pid].grievance = 0.0
            world.persons[pid].public_behavior = "neutral"
        self.assertGreater(first.weight, cfg.minimum_proto_represented_population)
        self.assertTrue(form_proto_organizations(world, 0, ZeroRng()))

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


    def test_fractional_proto_founders_and_birth_are_resolution_invariant(self):
        outcomes = []
        raw_founder_counts = []
        for agents in (120, 240, 480):
            world = generate_pineland(SimulationConfig(
                agent_count=agents, locality_count=17, horizon_days=1,
                seed=20260904, include_insurgency=False,
            ))
            locality_id = next(iter(world.localities))
            world.social_communities = {
                "C-FRACTIONAL": SocialCommunity(
                    "C-FRACTIONAL", locality_id, list(world.persons),
                    {"FS": 1.0}, .8, insurgent_sympathy=.8,
                )
            }
            for person in world.persons.values():
                person.organization_id = None
                person.armed_fraction = 0.0
                person.public_behavior = "protest"
                person.grievance = .8
                person.efficacy = .6
                person.political_access = .2
                person.expected_control["government"] = .5
                person.resources = person.weight * .9
            world.proto_organizations.clear()
            cfg = world.config.organization_ecology
            cfg.proto_base_hazard = 1.0
            cfg.birth_base_hazard = 1.0
            cfg.minimum_proto_members = 10_000
            cfg.minimum_proto_represented_population = 1_000.0
            cfg.minimum_formation_personnel = 75.0
            world.initialize_stock_ledger()

            proto = form_proto_organizations(world, 0, ZeroRng())[0]
            fractions = _proto_member_fractions(world, proto)
            founder_mass = sum(
                world.persons[pid].weight * fraction
                for pid, fraction in fractions.items()
            )
            expected_mass = world.weighted_population() * .5
            self.assertAlmostEqual(founder_mass, expected_mass, places=6)
            self.assertTrue(all(abs(value - .5) <= 1e-12
                                for value in fractions.values()))
            self.assertAlmostEqual(proto.capital["material"], .3, places=12)
            raw_founder_counts.append(len(proto.member_ids))

            blocked = world.clone()
            blocked_proto = blocked.proto_organizations[proto.proto_id]
            represented_personnel = founder_mass * cfg.fighter_conversion_fraction
            blocked.config.organization_ecology.minimum_formation_personnel = (
                represented_personnel + 1.0
            )
            self.assertIsNone(mature_proto(blocked, blocked_proto, 1, ZeroRng()))
            self.assertEqual(
                blocked.organization_transitions[-1].causes["reason"],
                "insufficient_represented_manpower",
            )

            organization = mature_proto(world, proto, 1, ZeroRng())
            self.assertIsNotNone(organization)
            formation = next(
                formation for formation in world.formations.values()
                if formation.organization_id == organization.organization_id
            )
            contributed = world.organization_transitions[-1].resource_assignments[
                organization.organization_id
            ]
            expected_contribution = founder_mass * .9 * cfg.onset_resource_fraction
            self.assertAlmostEqual(
                represented_armed_membership(world, organization),
                founder_mass, places=6,
            )
            self.assertAlmostEqual(
                formation.personnel, represented_personnel, places=6,
            )
            self.assertAlmostEqual(contributed, expected_contribution, places=6)
            outcomes.append((
                founder_mass, proto.capital["material"],
                formation.personnel, contributed,
            ))

        self.assertEqual(raw_founder_counts, [120, 240, 480])
        for outcome in outcomes[1:]:
            for value, reference in zip(outcome, outcomes[0]):
                self.assertAlmostEqual(value, reference, places=6)


    def test_local_access_scales_with_represented_foothold(self):
        decisions = {1.0: [], 1_000.0: []}
        for agents in (120, 240, 480):
            for represented_foothold in decisions:
                world = generate_pineland(SimulationConfig(
                    agent_count=agents, locality_count=17, horizon_days=1,
                    seed=20260904,
                ))
                organization = armed_organizations(world)[0]
                occupied = {
                    formation.locality_id for formation in world.formations.values()
                    if formation.organization_id == organization.organization_id
                    and formation.personnel > 0
                }
                by_locality = {}
                for person in world.persons.values():
                    by_locality.setdefault(person.residence_locality_id, []).append(person)
                locality_id = next(
                    key for key, people in by_locality.items()
                    if key not in occupied and len(people) >= 2
                )
                member, candidate = by_locality[locality_id][:2]

                organization.member_ids = {member.person_id}
                organization.cohesion = 1.0
                for person in world.persons.values():
                    person.organization_id = "government"
                    person.armed_fraction = 0.0
                member.organization_id = organization.organization_id
                member.armed_fraction = represented_foothold / member.weight
                member.grievance = 1.0
                member.fear = 0.0
                candidate.organization_id = None
                candidate.grievance = .95
                candidate.fear = 0.0
                candidate.political_access = 0.0
                candidate.social_exposure.clear()
                candidate.identities["federal"] = organization.ideology.get("reform", .5)

                world.config.recruitment_rate = 1.0
                cfg = world.config.organization_ecology
                cfg.minimum_proto_represented_population = 1_000.0
                cfg.recruitment_subcohorts = 20
                recruit_and_retain(world, 0, ConstantRng(.01))
                decisions[represented_foothold].append(
                    candidate.organization_id == organization.organization_id
                )

        self.assertEqual(decisions[1.0], [False, False, False])
        self.assertEqual(decisions[1_000.0], [True, True, True])


    def test_adaptation_ignores_hidden_peer_truth_but_uses_fused_beliefs(self):
        world = make_world(seed=99)
        observer, peer = split_organization(world, "insurgent", 2, ZeroRng())
        world.config.organization_ecology.mutation_sigma = 0.0
        localities = list(world.localities)[:2]
        for index, locality_id in enumerate(localities):
            world.presence_beliefs[
                (observer.organization_id, peer.organization_id, locality_id, "*")
            ] = PresenceBelief(
                observer.organization_id, peer.organization_id, locality_id,
                .9 if index == 0 else .1, 1.0, 0.0,
                personnel_estimate=900.0 if index == 0 else 100.0,
            )
            level = .8 if index == 0 else .6
            world.control_beliefs[
                (observer.organization_id, peer.organization_id, locality_id)
            ] = ActorBelief(
                observer.organization_id, locality_id,
                ControlVector(*([level] * 7)), 1.0, 0.0,
            )

        baseline = world.clone()
        hidden = world.clone()
        hidden_peer = hidden.organizations[peer.organization_id]
        hidden_peer.resources *= 1_000.0
        hidden_peer.phenotype = {
            key: 1.0 - value for key, value in hidden_peer.phenotype.items()
        }
        for formation in hidden.formations.values():
            if formation.organization_id == hidden_peer.organization_id:
                formation.personnel *= 100.0
                formation.quality = formation.cohesion = formation.readiness = 1.0

        _adapt(baseline, baseline.organizations[observer.organization_id], ZeroRng())
        _adapt(hidden, hidden.organizations[observer.organization_id], ZeroRng())
        self.assertEqual(
            baseline.organizations[observer.organization_id].phenotype,
            hidden.organizations[observer.organization_id].phenotype,
        )

        believed = world.clone()
        for key, belief in believed.control_beliefs.items():
            if key[:2] == (observer.organization_id, peer.organization_id):
                belief.control_estimate = ControlVector(*([.05] * 7))
        for belief in believed.presence_beliefs.values():
            if (belief.observer_id == observer.organization_id and
                    belief.target_actor_id == peer.organization_id):
                belief.presence_estimate = .5
        _adapt(believed, believed.organizations[observer.organization_id], ZeroRng())
        self.assertNotEqual(
            baseline.organizations[observer.organization_id].phenotype,
            believed.organizations[observer.organization_id].phenotype,
        )


    def test_proto_decision_ignores_hidden_repression_truth_but_uses_belief(self):
        world = generate_pineland(SimulationConfig(
            agent_count=120, locality_count=17, horizon_days=1,
            seed=20260904, include_insurgency=False,
        ))
        locality_id = next(iter(world.localities))
        world.social_communities = {
            "C-FIREWALL": SocialCommunity(
                "C-FIREWALL", locality_id, list(world.persons),
                {"FS": 1.0}, .8, insurgent_sympathy=.8,
            )
        }
        for person in world.persons.values():
            person.organization_id = None
            person.public_behavior = "protest"
            person.grievance = .8
            person.political_access = .2
            person.expected_control["government"] = .5
        world.config.organization_ecology.proto_base_hazard = .05
        world.config.organization_ecology.minimum_proto_represented_population = 1_000.0

        baseline = world.clone()
        hidden = world.clone()
        hidden.localities[locality_id].violence = 1.0
        hidden.localities[locality_id].control["government"].physical = 0.0
        form_proto_organizations(baseline, 0, ZeroRng())
        form_proto_organizations(hidden, 0, ZeroRng())
        base_log = baseline.organization_onset_log[-1]
        hidden_log = hidden.organization_onset_log[-1]
        self.assertAlmostEqual(base_log["hazard"], hidden_log["hazard"], places=15)
        self.assertNotEqual(
            base_log["experienced_repression"],
            hidden_log["experienced_repression"],
        )

        believed = world.clone()
        for person in believed.persons.values():
            person.expected_control["government"] = 1.0
        form_proto_organizations(believed, 0, ZeroRng())
        belief_log = believed.organization_onset_log[-1]
        self.assertNotEqual(base_log["hazard"], belief_log["hazard"])


if __name__ == "__main__":
    unittest.main()
