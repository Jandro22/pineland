from copy import deepcopy
from math import log
import random
import unittest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.combat import _perceived_disadvantage, formation_microzone
from pineland_sim.entities import ActorBelief, ControlVector, PresenceBelief
from pineland_sim.events import ScheduledEvent
from pineland_sim.foreign_affairs import (
    _return_probability,
    _support_recipient,
    deliver_support,
)
from pineland_sim.logistics import choose_reallocation_orders, shortest_locality_path, update_logistics
from pineland_sim.peace_process import bargaining_values
from pineland_sim.political_order import run_election
from pineland_sim.processes import ProcessEngine


class PickMaxRng:
    def random(self):
        return 0.0

    def uniform(self, low, high):
        return low

    def normalvariate(self, mean, sigma):
        return mean

    def choices(self, population, weights=None, k=1):
        if weights is None:
            return [population[0]] * k
        index = max(range(len(population)), key=lambda i: weights[i])
        return [population[index]] * k


class HighRng(PickMaxRng):
    def random(self):
        return 0.99


def event(event_type, payload=None):
    return ScheduledEvent(0.0, 100, 0, event_type, payload or {})


class TruthBeliefRecordFirewallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = generate_pineland(SimulationConfig(
            agent_count=180, locality_count=24, horizon_days=2, seed=2404
        ))

    def test_civilian_mobility_ignores_destination_truth_but_uses_destination_belief(self):
        world = self.template.clone()
        person = next(
            p for p in world.persons.values()
            if len(world.adjacency[p.residence_locality_id]) >= 2
        )
        foreign_state_id = next(iter(world.foreign_states))
        for other in world.persons.values():
            if other.person_id != person.person_id:
                other.external_state_id = foreign_state_id
        world.config.movement_rate = 1.0
        world.localities[person.residence_locality_id].violence = 0.0
        candidates = list(world.adjacency[person.residence_locality_id])
        structural = {}
        for locality_id in candidates:
            locality = world.localities[locality_id]
            livelihood = log(max(2, locality.economic_output / max(1, locality.population)))
            structural[locality_id] = .1 * livelihood - world.adjacency[person.residence_locality_id][locality_id]
        ranked = sorted(candidates, key=structural.get, reverse=True)
        first = ranked[0]
        second = next(
            (candidate for candidate in ranked[1:]
             if structural[first] - structural[candidate] < 1.2),
            ranked[1],
        )
        self.assertLess(structural[first] - structural[second], 1.2)
        person.expected_control_by_locality = {
            candidate: {"government": 1.0 if candidate == first else 0.0}
            for candidate in candidates
        }

        hidden = world.clone()
        for index, candidate in enumerate(candidates):
            hidden.localities[candidate].control["government"].physical = float(index % 2)
        ProcessEngine(world, PickMaxRng()).on_mobility("E-base", event("mobility"))
        ProcessEngine(hidden, PickMaxRng()).on_mobility("E-hidden", event("mobility"))
        self.assertEqual(
            world.persons[person.person_id].residence_locality_id,
            hidden.persons[person.person_id].residence_locality_id,
        )

        believed = self.template.clone()
        bp = believed.persons[person.person_id]
        foreign_state_id = next(iter(believed.foreign_states))
        for other in believed.persons.values():
            if other.person_id != bp.person_id:
                other.external_state_id = foreign_state_id
        believed.config.movement_rate = 1.0
        believed.localities[bp.residence_locality_id].violence = 0.0
        bp.expected_control_by_locality = {
            candidate: {"government": 1.0 if candidate == second else 0.0}
            for candidate in candidates
        }
        ProcessEngine(believed, PickMaxRng()).on_mobility("E-belief", event("mobility"))
        self.assertEqual(believed.persons[bp.person_id].residence_locality_id, second)
        self.assertNotEqual(world.persons[person.person_id].residence_locality_id, second)

    def test_patrol_route_ignores_zone_truth_but_uses_zone_belief(self):
        world = self.template.clone()
        patrol = next(
            p for p in world.patrols.values()
            if len(world.physical_neighbors[p.current_microzone_id]) >= 2
        )
        formation = world.formations[patrol.formation_id]
        candidates = sorted(world.physical_neighbors[patrol.current_microzone_id])
        first, second = candidates[:2]
        world.config.information.patrol_report_rate = 0.0
        world.config.physical.patrol_route_randomness = 0.0
        for candidate in candidates:
            edge_id = world.physical_neighbors[patrol.current_microzone_id][candidate]
            world.physical_edges[edge_id].travel_time_hours = 1.0
            belief = world.zone_beliefs[(formation.organization_id, candidate)]
            belief.confidence = 1.0
            belief.physical_control_estimate = 0.0 if candidate == first else 1.0

        hidden = world.clone()
        for index, candidate in enumerate(candidates):
            hidden.microzones[candidate].physical_control["government"] = float(index % 2)
        ProcessEngine(world, PickMaxRng()).on_patrol(
            "E-base", event("patrol", {"patrol_id": patrol.patrol_id})
        )
        ProcessEngine(hidden, PickMaxRng()).on_patrol(
            "E-hidden", event("patrol", {"patrol_id": patrol.patrol_id})
        )
        self.assertEqual(
            world.patrols[patrol.patrol_id].current_microzone_id,
            hidden.patrols[patrol.patrol_id].current_microzone_id,
        )
        self.assertEqual(world.patrols[patrol.patrol_id].current_microzone_id, first)

        believed = self.template.clone()
        bp = believed.patrols[patrol.patrol_id]
        bf = believed.formations[bp.formation_id]
        believed.config.information.patrol_report_rate = 0.0
        believed.config.physical.patrol_route_randomness = 0.0
        for candidate in candidates:
            edge_id = believed.physical_neighbors[bp.current_microzone_id][candidate]
            believed.physical_edges[edge_id].travel_time_hours = 1.0
            belief = believed.zone_beliefs[(bf.organization_id, candidate)]
            belief.confidence = 1.0
            belief.physical_control_estimate = 0.0 if candidate == second else 1.0
        ProcessEngine(believed, PickMaxRng()).on_patrol(
            "E-belief", event("patrol", {"patrol_id": bp.patrol_id})
        )
        self.assertEqual(believed.patrols[bp.patrol_id].current_microzone_id, second)

    def test_reallocation_ignores_control_truth_but_uses_command_belief(self):
        world = self.template.clone()
        formation = world.formations["FDF-01"]
        for other in world.formations.values():
            if other.formation_id != formation.formation_id:
                other.moving = True
        world.config.logistics.reallocation_rate = 1.0
        for locality_id in world.localities:
            belief = world.beliefs[(formation.organization_id, locality_id)]
            belief.control_estimate.physical = .5
            belief.confidence = 1.0
            opponent = world.control_beliefs[
                (formation.organization_id, "insurgent", locality_id)
            ]
            opponent.control_estimate.physical = .5
            opponent.confidence = 1.0
        hidden = world.clone()
        for index, locality in enumerate(hidden.localities.values()):
            locality.control["government"].physical = float(index % 2)
        base_orders = choose_reallocation_orders(world, 0, PickMaxRng())
        hidden_orders = choose_reallocation_orders(hidden, 0, PickMaxRng())
        base_choice = (base_orders[0].destination_locality_id
                       if base_orders else formation.locality_id)
        hidden_choice = (hidden_orders[0].destination_locality_id
                         if hidden_orders else hidden.formations["FDF-01"].locality_id)
        self.assertEqual(base_choice, hidden_choice)

        believed = self.template.clone()
        bf = believed.formations["FDF-01"]
        for other in believed.formations.values():
            if other.formation_id != bf.formation_id:
                other.moving = True
        believed.config.logistics.reallocation_rate = 1.0
        nearest = min(
            (lid for lid in believed.localities if lid != bf.locality_id),
            key=lambda lid: shortest_locality_path(
                believed, bf.locality_id, lid, bf.mobility
            )[2],
        )
        for locality_id in believed.localities:
            belief = believed.beliefs[(bf.organization_id, locality_id)]
            belief.control_estimate.physical = 1.0
            belief.confidence = 1.0
            opponent = believed.control_beliefs[
                (bf.organization_id, "insurgent", locality_id)
            ]
            opponent.control_estimate.physical = 0.0
            opponent.confidence = 1.0
        believed.beliefs[(bf.organization_id, nearest)].control_estimate.physical = 0.0
        belief_order = choose_reallocation_orders(believed, 0, PickMaxRng())[0]
        self.assertEqual(belief_order.destination_locality_id, nearest)

    def test_legacy_contact_initiation_does_not_consume_conditioned_detection_truth(self):
        def run(world, confidence):
            g = world.formations["FDF-01"]
            i = world.formations["PRF-01"]
            i.locality_id = g.locality_id
            i.current_microzone_id = formation_microzone(world, g)
            world.config.contact_rate = .001
            world.config.combat.contact_opportunity_model = "legacy_symmetric"
            world.config.information.positive_report_confidence = confidence
            payload = {
                "locality_id": g.locality_id,
                "microzone_id": i.current_microzone_id,
                "government_formation_id": g.formation_id,
                "insurgent_formation_id": i.formation_id,
                "interval_days": 1.0,
                "force_detection": True,
            }
            result = ProcessEngine(world, HighRng()).on_contact(
                "E-contact", event("contact", payload)
            )
            g_obs = world.observations[result["observations_by_actor"][g.organization_id][0]]
            return result["contact_hazard"], g_obs.estimated_value["detection_probability"]

        low_hidden = self.template.clone()
        high_hidden = self.template.clone()
        low_hidden.formations["PRF-01"].embeddedness = 0.0
        high_hidden.formations["PRF-01"].embeddedness = 1.0
        low_hazard, low_truth_probability = run(low_hidden, .7)
        high_hazard, high_truth_probability = run(high_hidden, .7)
        self.assertNotEqual(low_truth_probability, high_truth_probability)
        self.assertAlmostEqual(low_hazard, high_hazard)

    def test_disengagement_ignores_opponent_truth_but_uses_contact_belief(self):
        world = self.template.clone()
        g = world.formations["FDF-01"]
        i = world.formations["PRF-01"]
        i.locality_id = g.locality_id
        zone_id = formation_microzone(world, g)
        i.current_microzone_id = zone_id
        key = (g.formation_id, i.organization_id, f"{g.locality_id}:{zone_id}", i.formation_id)
        world.node_presence_beliefs[key] = PresenceBelief(
            g.formation_id, i.organization_id, g.locality_id,
            presence_estimate=1.0, confidence=.8, updated_at=0.0,
            evidence_count=1, target_id=i.formation_id, microzone_id=zone_id,
            personnel_estimate=500.0,
        )
        own_reference = max(1.0, g.deployable_personnel())
        base = _perceived_disadvantage(world, g, i, zone_id, own_reference)
        hidden = world.clone()
        hi = hidden.formations[i.formation_id]
        hi.personnel *= 12
        hi.quality = hi.cohesion = hi.readiness = 1.0
        same = _perceived_disadvantage(
            hidden, hidden.formations[g.formation_id], hi, zone_id, own_reference
        )
        self.assertAlmostEqual(base, same)
        believed = world.clone()
        believed.node_presence_beliefs[key].personnel_estimate = 5_000.0
        changed = _perceived_disadvantage(
            believed, believed.formations[g.formation_id],
            believed.formations[i.formation_id], zone_id, own_reference,
        )
        self.assertGreater(changed, base)

    def test_logistics_dispatch_ignores_true_interdiction_but_uses_route_belief(self):
        def prepare(world, believed_risk):
            formation = world.formations["FDF-01"]
            cfg = world.config.logistics
            cfg.route_interdiction_enabled = True
            cfg.route_interdiction_rate = .6
            cfg.shipment_loss_per_travel_hour = 0.0
            for other in world.formations.values():
                other.supply_stock = other.supply_capacity
            formation.supply_stock = 0.0
            for source in world.supply_sources.values():
                if source.organization_id == formation.organization_id:
                    source.capacity = source.stock = 1e8
            for locality_id in world.localities:
                key = (formation.organization_id, "insurgent", locality_id)
                belief = world.control_beliefs.get(key)
                if belief is None:
                    belief = ActorBelief(
                        formation.organization_id, locality_id,
                        ControlVector(*([.5] * 7)), 1.0, 0.0,
                    )
                    world.control_beliefs[key] = belief
                belief.control_estimate.physical = believed_risk
                belief.confidence = 1.0
            return formation

        low_truth = self.template.clone()
        high_truth = self.template.clone()
        lf = prepare(low_truth, .2)
        hf = prepare(high_truth, .2)
        for locality in low_truth.localities.values():
            locality.control["insurgent"].physical = 0.0
        for locality in high_truth.localities.values():
            locality.control["insurgent"].physical = 1.0
        update_logistics(low_truth, 1, 0.0)
        update_logistics(high_truth, 1, 0.0)
        low_shipment = next(s for s in low_truth.supply_shipments.values()
                            if s.formation_id == lf.formation_id)
        high_shipment = next(s for s in high_truth.supply_shipments.values()
                             if s.formation_id == hf.formation_id)
        self.assertAlmostEqual(low_shipment.quantity_sent, high_shipment.quantity_sent)
        self.assertGreater(low_shipment.quantity_deliverable, high_shipment.quantity_deliverable)

        high_belief = self.template.clone()
        bf = prepare(high_belief, .9)
        for locality in high_belief.localities.values():
            locality.control["insurgent"].physical = 0.0
        update_logistics(high_belief, 1, 0.0)
        belief_shipment = next(s for s in high_belief.supply_shipments.values()
                               if s.formation_id == bf.formation_id)
        self.assertGreater(belief_shipment.quantity_sent, low_shipment.quantity_sent)

    def test_election_ignores_hidden_patronage_stock_but_uses_voter_belief(self):
        baseline = self.template.clone()
        hidden = baseline.clone()
        for branch in hidden.party_branches.values():
            branch.patronage_stock += 1e9
        base_election = run_election(baseline, 180, random.Random(4))
        hidden_election = run_election(hidden, 180, random.Random(4))
        self.assertEqual(base_election.votes, hidden_election.votes)
        self.assertEqual(base_election.winner_party_id, hidden_election.winner_party_id)

        believed = self.template.clone()
        for person in believed.persons.values():
            for party_id in person.party_legitimacy:
                person.party_legitimacy[party_id] = 1.0 if party_id == "party-2" else .001
                person.private_preference[party_id] = 1.0 if party_id == "party-2" else .001
        belief_election = run_election(believed, 180, random.Random(4))
        self.assertEqual(belief_election.winner_party_id, "party-2")

    def test_return_migration_ignores_unseen_home_violence_but_uses_home_belief(self):
        world = self.template.clone()
        person = next(iter(world.persons.values()))
        state = next(iter(world.foreign_states.values()))
        world.config.foreign_affairs.return_rate = 1.0
        person.expected_control_by_locality[person.home_locality_id] = {"government": .2}
        base = _return_probability(world, person, state)
        hidden = world.clone()
        hidden.localities[person.home_locality_id].violence = 1.0
        same = _return_probability(
            hidden, hidden.persons[person.person_id], hidden.foreign_states[state.state_id]
        )
        self.assertAlmostEqual(base, same)
        believed = world.clone()
        believed.persons[person.person_id].expected_control_by_locality[
            person.home_locality_id
        ]["government"] = .95
        changed = _return_probability(
            believed, believed.persons[person.person_id],
            believed.foreign_states[state.state_id],
        )
        self.assertGreater(changed, base)

    def test_foreign_support_target_ignores_hidden_insurgent_phenotype_and_uses_own_record(self):
        world = self.template.clone()
        state = next(iter(world.foreign_states.values()))
        state.government_alignment = -1.0
        state.ideological_alignment = 1.0
        original = world.organizations["insurgent"]
        alternate = deepcopy(original)
        alternate.organization_id = "zz-insurgent"
        alternate.name = "Alternate insurgent"
        world.organizations[alternate.organization_id] = alternate
        active = [original, alternate]
        original.phenotype["resource_dependence"] = 0.0
        alternate.phenotype["resource_dependence"] = 1.0
        baseline_recipient = _support_recipient(world, state, active)

        hidden = world.clone()
        hidden.organizations["insurgent"].phenotype["resource_dependence"] = 1.0
        hidden.organizations["zz-insurgent"].phenotype["resource_dependence"] = 0.0
        hidden_recipient = _support_recipient(
            hidden, hidden.foreign_states[state.state_id],
            [hidden.organizations["insurgent"], hidden.organizations["zz-insurgent"]],
        )
        self.assertEqual(baseline_recipient, hidden_recipient)

        recorded = world.clone()
        recorded_state = recorded.foreign_states[state.state_id]
        deliver_support(
            recorded, recorded_state, "zz-insurgent", 1, "E-support",
            random.Random(3), total=100.0,
        )
        record_recipient = _support_recipient(
            recorded, recorded_state,
            [recorded.organizations["insurgent"], recorded.organizations["zz-insurgent"]],
        )
        self.assertEqual(record_recipient, "zz-insurgent")

    def test_bargaining_ignores_opponent_truth_but_uses_presence_belief(self):
        world = self.template.clone()
        world.presence_beliefs.clear()
        locality_id = next(iter(world.localities))
        key = ("government", "insurgent", f"{locality_id}:*", "*")
        world.presence_beliefs[key] = PresenceBelief(
            "government", "insurgent", locality_id,
            presence_estimate=1.0, confidence=.8, updated_at=0.0,
            evidence_count=1, personnel_estimate=1_000.0,
        )
        baseline = bargaining_values(world)["government"]
        hidden = world.clone()
        for formation in hidden.formations.values():
            if hidden.organizations[formation.organization_id].kind.value == "insurgent":
                formation.personnel *= 10
                formation.quality = formation.cohesion = formation.readiness = 1.0
        hidden_value = bargaining_values(hidden)["government"]
        self.assertAlmostEqual(baseline["future_power"], hidden_value["future_power"])
        self.assertAlmostEqual(baseline["war"], hidden_value["war"])

        believed = world.clone()
        believed.presence_beliefs[key].personnel_estimate = 10_000.0
        changed = bargaining_values(believed)["government"]
        self.assertLess(changed["future_power"], baseline["future_power"])
        self.assertLess(changed["war"], baseline["war"])


if __name__ == "__main__":
    unittest.main()
