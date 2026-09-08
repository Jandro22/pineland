from pineland_sim.action_model import action_attempt_hazard, local_fighter_equivalents
from pineland_sim.config import SimulationConfig
from pineland_sim.entities import ControlVector
from pineland_sim.generator import generate_pineland
from pineland_sim.organizational_state import (
    advance_local_footholds,
    local_foothold_strength,
    record_local_foothold_arrival,
)


def _world():
    return generate_pineland(
        SimulationConfig(
            seed=20260908,
            agent_count=120,
            locality_count=17,
            horizon_days=5,
        )
    )


def test_foothold_memory_survives_current_presence_loss_and_decays():
    world = _world()
    organization_id = "insurgent"
    formation_localities = {
        formation.locality_id
        for formation in world.formations.values()
        if formation.organization_id == organization_id
    }
    locality_id = next(
        locality_id
        for locality_id in world.localities
        if locality_id not in formation_localities
    )
    organization = world.organizations[organization_id]
    for person_id in list(organization.member_ids):
        person = world.persons[person_id]
        if person.residence_locality_id == locality_id:
            organization.member_ids.discard(person_id)
            person.organization_id = None
            person.armed_fraction = 0.0
    world.localities[locality_id].control[organization_id] = ControlVector()
    world.organization_manpower_pools.pop((organization_id, locality_id), None)
    world.organization_manpower_supply_reserves.pop((organization_id, locality_id), None)
    foothold = world.local_footholds[(organization_id, locality_id)]
    foothold.strength = 0.8
    foothold.raw_signal = 0.0
    foothold.renewal_count = 1
    advance_local_footholds(world, 45.0)
    assert 0.0 < local_foothold_strength(world, organization_id, locality_id) < 0.8


def test_foothold_does_not_create_fighter_capacity_without_stock():
    world = _world()
    organization_id = "insurgent"
    locality_id = sorted(world.localities)[-1]
    foothold = world.local_footholds[(organization_id, locality_id)]
    foothold.strength = 1.0
    foothold.raw_signal = 1.0
    foothold.renewal_count = 1
    assert local_fighter_equivalents(world, organization_id, locality_id) == (0.0, 0.0)
    assert action_attempt_hazard(world, organization_id, locality_id) == 0.0


def test_arrival_records_renewal_without_teleporting_membership():
    world = _world()
    formation = next(
        formation for formation in world.formations.values()
        if formation.organization_id == "insurgent"
    )
    locality_id = formation.locality_id
    before = world.local_footholds[("insurgent", locality_id)].cumulative_arrivals
    record_local_foothold_arrival(world, formation, 0.0)
    foothold = world.local_footholds[("insurgent", locality_id)]
    assert foothold.cumulative_arrivals == before + 1
    assert foothold.renewal_count > 0
    assert foothold.strength >= 0.0
