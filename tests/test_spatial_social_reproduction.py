import random

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind
from pineland_sim.events import ScheduledEvent
from pineland_sim.organization_ecology import _set_armed_membership, recruit_and_retain
from pineland_sim.processes import ProcessEngine


class ZeroRng:
    def random(self):
        return 0.0

    def choices(self, population, weights, k):
        return [population[0]]

    def normalvariate(self, mu, sigma):
        return mu

    def uniform(self, low, high):
        return low


def _isolated_cross_local_bridge_world():
    world = generate_pineland(SimulationConfig(
        agent_count=800, locality_count=24, horizon_days=1,
        seed=741,
    ))
    insurgent = next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )
    formation_localities = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == insurgent.organization_id and formation.personnel > 0
    }
    edge = next(
        edge for edge in world.social_edges.values()
        if "bridge" in edge.layers
        and world.persons[edge.person_a_id].residence_locality_id !=
            world.persons[edge.person_b_id].residence_locality_id
        and world.persons[edge.person_b_id].residence_locality_id not in formation_localities
    )
    source = world.persons[edge.person_a_id]
    target = world.persons[edge.person_b_id]
    source_locality = source.residence_locality_id
    target_locality = target.residence_locality_id
    assert target_locality in world.adjacency[source_locality]

    # Remove pre-existing armed social access in the target locality so the
    # bridge is the only recruitment-access channel under test.
    for person in world.persons.values():
        if person.residence_locality_id != target_locality:
            continue
        if person.organization_id == insurgent.organization_id:
            insurgent.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
        person.public_behavior = "neutral"
        person.social_exposure.clear()

    # Make exactly one remote source visibly armed. Other target neighbors are
    # neutral so a positive target signal has a transparent causal source.
    _set_armed_membership(source, insurgent, 1.0)
    insurgent.member_ids.add(source.person_id)
    source.public_behavior = "armed_participation"
    for neighbor_id in world.social_neighbors[target.person_id]:
        if neighbor_id == source.person_id:
            continue
        neighbor = world.persons[neighbor_id]
        neighbor.public_behavior = "neutral"
        if neighbor.residence_locality_id == target_locality and \
                neighbor.organization_id == insurgent.organization_id:
            insurgent.member_ids.discard(neighbor.person_id)
            _set_armed_membership(neighbor, None, 0.0)

    target.organization_id = None
    target.armed_fraction = 0.0
    target.public_behavior = "neutral"
    target.grievance = 1.0
    target.fear = 0.0
    target.political_access = 0.0
    target.identities["federal"] = insurgent.ideology.get("reform", 0.5)
    insurgent.capital["social"] = 1.0
    world.config.recruitment_rate = 1.0
    world.config.social_network.behavior_update_rate = 0.0
    world.config.organization_ecology.recruitment_requires_access = True
    return world, insurgent, source, target, edge


def _remove_edge(world, first_id: str, second_id: str) -> None:
    key = tuple(sorted((first_id, second_id)))
    del world.social_edges[key]
    world.social_neighbors[first_id].remove(second_id)
    world.social_neighbors[second_id].remove(first_id)


def test_adjacent_social_bridge_can_seed_recruitment_without_prior_local_force_or_members():
    world, insurgent, source, target, edge = _isolated_cross_local_bridge_world()
    target_locality = target.residence_locality_id
    assert not any(
        formation.organization_id == insurgent.organization_id
        and formation.locality_id == target_locality
        and formation.personnel > 0
        for formation in world.formations.values()
    )
    assert sum(
        person.weight * person.armed_fraction
        for person in world.persons.values()
        if person.residence_locality_id == target_locality
        and person.organization_id == insurgent.organization_id
    ) == 0.0

    engine = ProcessEngine(world, random.Random(19))
    engine.on_social_influence(
        "SOCIAL-SEED",
        ScheduledEvent(0.0, 0, 0, "social_influence", {"interval": 1.0}),
    )
    assert target.social_exposure["insurgent"] > 0.0
    before = target.armed_fraction
    recruit_and_retain(world, 0.0, ZeroRng())
    assert before == 0.0
    assert target.organization_id == insurgent.organization_id
    assert target.armed_fraction > 0.0


def test_removing_only_the_cross_local_bridge_blocks_that_recruitment_seed():
    world, insurgent, source, target, edge = _isolated_cross_local_bridge_world()
    _remove_edge(world, source.person_id, target.person_id)
    engine = ProcessEngine(world, random.Random(19))
    engine.on_social_influence(
        "SOCIAL-PLACEBO",
        ScheduledEvent(0.0, 0, 0, "social_influence", {"interval": 1.0}),
    )
    assert target.social_exposure.get("insurgent", 0.0) == 0.0
    recruit_and_retain(world, 0.0, ZeroRng())
    assert target.organization_id is None
    assert target.armed_fraction == 0.0
