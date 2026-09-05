import random
import unittest

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import ArmedFormation, OrganizationKind
from pineland_sim.events import ScheduledEvent
from pineland_sim.foreign_affairs import (
    SUPPORT_COMPONENTS, _foreign_belief_update, begin_intervention,
    deliver_support, dependence_metrics, process_cross_border_mobility,
    process_diaspora, process_foreign_affairs, run_intervention_comparison,
)
from pineland_sim.processes import ProcessEngine


class ZeroRng:
    def random(self): return 0.0
    def normalvariate(self, mean, sigma): return mean
    def uniform(self, low, high): return (low + high) / 2
    def choices(self, population, weights=None, k=1): return [population[0]] * k


def make_world(seed=404, insurgency=True):
    return generate_pineland(SimulationConfig(agent_count=500, locality_count=34,
                                              horizon_days=31, seed=seed,
                                              include_insurgency=insurgency))


class ForeignAffairsTests(unittest.TestCase):
    def test_neighbors_and_borders_are_heterogeneous_and_permeabilities_distinct(self):
        world = make_world()
        self.assertEqual(len(world.foreign_states), 5)
        self.assertGreaterEqual(len(world.border_segments), 17)
        self.assertGreater(len({round(s.government_alignment, 3) for s in world.foreign_states.values()}), 1)
        self.assertTrue(any(b.legal_permeability != b.social_permeability
                            for b in world.border_segments.values()))

    def test_cross_border_departure_return_and_social_tie_retention(self):
        world = make_world()
        world.config.foreign_affairs.migration_rate = 1
        person = next(p for p in world.persons.values()
                      if any(b.district_id == world.localities[p.residence_locality_id].district_id
                             for b in world.border_segments.values()))
        neighbors = tuple(world.social_neighbors[person.person_id])
        departures, _ = process_cross_border_mobility(world, 1, ZeroRng())
        self.assertGreater(departures, 0)
        self.assertIsNotNone(person.external_state_id)
        self.assertEqual(tuple(world.social_neighbors[person.person_id]), neighbors)
        world.config.foreign_affairs.return_rate = 1
        _, returns = process_cross_border_mobility(world, 2, ZeroRng())
        self.assertGreater(returns, 0)

    def test_diaspora_remittance_conserves_resources(self):
        world = make_world()
        world.config.foreign_affairs.migration_rate = 1
        process_cross_border_mobility(world, 1, ZeroRng())
        before_foreign = sum(state.resources for state in world.foreign_states.values())
        before_people = sum(person.resources for person in world.persons.values())
        amount, _ = process_diaspora(world, 2, "E-diaspora", ZeroRng())
        self.assertAlmostEqual(before_foreign - sum(s.resources for s in world.foreign_states.values()), amount)
        self.assertAlmostEqual(sum(p.resources for p in world.persons.values()) - before_people, amount)

    def test_support_is_typed_conserved_and_reaches_both_sides(self):
        world = make_world()
        states = list(world.foreign_states.values())
        before_g = world.organizations["government"].resources
        before_i = world.organizations["insurgent"].resources
        first = deliver_support(world, states[0], "government", 1, "E1", random.Random(1), 1000)
        second = deliver_support(world, states[1], "insurgent", 1, "E2", random.Random(2), 1000)
        self.assertEqual(set(first.components), set(SUPPORT_COMPONENTS))
        self.assertAlmostEqual(first.total(), 1000)
        self.assertGreater(world.organizations["government"].resources, before_g)
        self.assertGreater(world.organizations["insurgent"].resources, before_i)
        self.assertAlmostEqual(sum(t.amount for t in world.external_transfers), 2000)

    def test_support_changes_insurgent_ecology_and_sanctuary(self):
        world = make_world()
        organization = world.organizations["insurgent"]
        before = (organization.capital["organizational"],
                  organization.phenotype["resource_dependence"])
        deliver_support(world, next(iter(world.foreign_states.values())), "insurgent",
                        1, "E", random.Random(3), 5000)
        self.assertGreater(organization.external_sanctuary, 0)
        self.assertGreater(organization.capital["organizational"], before[0])
        self.assertGreater(organization.phenotype["resource_dependence"], before[1])

    def test_foreign_formation_uses_existing_formation_logistics_and_patrol_types(self):
        world = make_world()
        state = next(iter(world.foreign_states.values()))
        intervention = begin_intervention(world, state, 0, "substitution", .1, .8)
        formation = world.formations[next(iter(intervention.force_formation_ids))]
        self.assertIsInstance(formation, ArmedFormation)
        self.assertEqual(world.organizations[formation.organization_id].kind, OrganizationKind.FOREIGN)
        self.assertTrue(any(p.formation_id == formation.formation_id for p in world.patrols.values()))
        self.assertGreater(formation.supply_stock, 0)
        world.assert_invariants()

    def test_runtime_foreign_patrol_gets_uncertain_zone_prior_without_truth_read(self):
        world = make_world(seed=405)
        state = next(iter(world.foreign_states.values()))
        intervention = begin_intervention(world, state, 0, "substitution", .1, .8)
        formation = world.formations[next(iter(intervention.force_formation_ids))]
        patrol = next(p for p in world.patrols.values()
                      if p.formation_id == formation.formation_id)
        key = (formation.organization_id, patrol.current_microzone_id)
        self.assertNotIn(key, world.zone_beliefs)
        ProcessEngine(world, random.Random(405)).on_patrol(
            "E-FOR-PATROL",
            ScheduledEvent(0.0, 30, 0, "patrol", {"patrol_id": patrol.patrol_id}),
        )
        belief = world.zone_beliefs[key]
        self.assertEqual(belief.physical_control_estimate, .5)
        self.assertEqual(belief.confidence, .35)

    def test_foreign_beliefs_are_imperfect_and_interpreters_raise_confidence(self):
        low = make_world()
        high = low.clone()
        state_low = next(iter(low.foreign_states.values()))
        state_high = high.foreign_states[state_low.state_id]
        for broker in low.interpreter_brokers.values():
            if broker.foreign_state_id == state_low.state_id:
                broker.foreign_language = broker.local_language = broker.foreign_trust = broker.local_trust = 0
        for broker in high.interpreter_brokers.values():
            if broker.foreign_state_id == state_high.state_id:
                broker.foreign_language = broker.local_language = broker.foreign_trust = broker.local_trust = broker.cultural_knowledge = 1
        _foreign_belief_update(low, state_low, 1, random.Random(5))
        _foreign_belief_update(high, state_high, 1, random.Random(5))
        low_conf = max(b.confidence for (sid, _), b in low.foreign_beliefs.items() if sid == state_low.state_id)
        high_conf = max(b.confidence for (sid, _), b in high.foreign_beliefs.items() if sid == state_high.state_id)
        self.assertGreater(high_conf, low_conf)

    def test_dependence_and_withdrawal_shock_are_explicit(self):
        world = make_world()
        state = next(iter(world.foreign_states.values()))
        intervention = begin_intervention(world, state, 0, "substitution", .1, .8)
        intervention.provided_capacity = 50
        baseline = dependence_metrics(world)
        intervention.status = "withdrawing"
        intervention.withdrawal_rate = .8
        shock = dependence_metrics(world)
        self.assertGreater(baseline["dependence"], 0)
        self.assertGreater(shock["withdrawal_shock"], 0)

    def test_withdrawal_routes_through_movement_order(self):
        world = make_world()
        state = next(iter(world.foreign_states.values()))
        intervention = begin_intervention(world, state, 0, "substitution", .1, .8)
        formation = world.formations[next(iter(intervention.force_formation_ids))]
        border_locality = formation.locality_id
        formation.locality_id = next(lid for lid in world.localities if lid != border_locality)
        intervention.status = "withdrawing"
        process_foreign_affairs(world, 30, "E", random.Random(7))
        self.assertTrue(any(order.formation_id == formation.formation_id
                            for order in world.movement_orders.values()))
        self.assertFalse(formation.outside_pineland)

    def test_foreign_presence_has_heterogeneous_legitimacy_effects(self):
        world = make_world()
        state = next(iter(world.foreign_states.values()))
        intervention = begin_intervention(world, state, 0, "capacity_building", .8, .05)
        formation = world.formations[next(iter(intervention.force_formation_ids))]
        people = [p for p in world.persons.values() if p.residence_locality_id == formation.locality_id]
        before = {p.person_id: p.government_legitimacy for p in people}
        process_foreign_affairs(world, 30, "E", random.Random(8))
        deltas = {round(p.government_legitimacy - before[p.person_id], 8) for p in people}
        self.assertGreater(len(deltas), 1)

    def test_peaceful_null_can_remain_noninternationalized(self):
        world = make_world(insurgency=False)
        cfg = world.config.foreign_affairs
        cfg.intervention_base_hazard = cfg.support_budget_fraction = cfg.migration_rate = 0
        Simulation(world).run(until=31)
        self.assertFalse(world.foreign_interventions)
        self.assertFalse(world.external_support)

    def test_intervention_comparison_distinguishes_substitution_and_capacity_building(self):
        results = run_intervention_comparison(make_world(), years=3, withdrawal_year=2)
        b = results["B_substitution"]["final"]["host_capacity"]
        c = results["C_capacity_building"]["final"]["host_capacity"]
        self.assertGreater(c, b)
        self.assertEqual(results["A_no_intervention"]["final"]["foreign_capacity"], 0)

    def test_foreign_trajectory_is_reproducible(self):
        first = Simulation(make_world(seed=505)).run(until=31).world
        second = Simulation(make_world(seed=505)).run(until=31).world
        self.assertEqual(first.external_support, second.external_support)
        self.assertEqual(first.foreign_interventions, second.foreign_interventions)
        self.assertEqual(first.summary(), second.summary())

    def test_foreign_domestic_opposition_reduces_willingness(self):
        low = make_world(seed=606)
        high = low.clone()
        for world in (low, high):
            world.config.foreign_affairs.support_budget_fraction = 0
            world.config.foreign_affairs.intervention_base_hazard = 0
            world.config.foreign_affairs.migration_rate = 0
        state_id = sorted(low.foreign_states)[0]
        low.foreign_states[state_id].domestic_opposition = 0
        high.foreign_states[state_id].domestic_opposition = 1
        process_foreign_affairs(low, 30, "E", random.Random(14))
        process_foreign_affairs(high, 30, "E", random.Random(14))
        self.assertGreater(low.foreign_states[state_id].willingness,
                           high.foreign_states[state_id].willingness)

    def test_rival_presence_increases_foreign_willingness(self):
        baseline = make_world(seed=707)
        rivalized = baseline.clone()
        for world in (baseline, rivalized):
            world.config.foreign_affairs.support_budget_fraction = 0
            world.config.foreign_affairs.intervention_base_hazard = 0
            world.config.foreign_affairs.migration_rate = 0
        target_id = sorted(baseline.foreign_states)[0]
        rival_id = next(iter(baseline.foreign_states[target_id].rival_ids))
        begin_intervention(rivalized, rivalized.foreign_states[rival_id], 0,
                           "substitution", .1, .8)
        process_foreign_affairs(baseline, 30, "E", random.Random(15))
        process_foreign_affairs(rivalized, 30, "E", random.Random(15))
        self.assertGreater(rivalized.foreign_states[target_id].willingness,
                           baseline.foreign_states[target_id].willingness)


if __name__ == "__main__":
    unittest.main()
