from __future__ import annotations

import copy

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import OrganizationKind

from studies.research_program.experimental_action_support import (
    local_action_support,
    national_fighter_equivalents,
)


def _world(seed: int = 77):
    return generate_pineland(SimulationConfig(
        seed=seed, agent_count=300, locality_count=24, horizon_days=1,
    ))


def _pair(world):
    insurgent = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT
    )
    government = next(
        formation for formation in world.formations.values()
        if world.organizations[formation.organization_id].kind in {
            OrganizationKind.MILITARY, OrganizationKind.POLICE, OrganizationKind.FOREIGN
        }
    )
    for formation in (insurgent, government):
        formation.moving = False
        formation.outside_pineland = False
        formation.operational_status = "effective"
        formation.personnel = max(100.0, formation.personnel)
    government.locality_id = insurgent.locality_id
    government.current_microzone_id = insurgent.current_microzone_id
    return insurgent, government


def _reserve_for(world, quantity: float) -> float:
    return quantity * (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )


def test_formation_to_pool_transfer_preserves_capacity_but_not_battle_support():
    world = _world()
    insurgent, _ = _pair(world)
    locality = insurgent.locality_id
    before = local_action_support(world, insurgent.organization_id, locality)
    assert before.armed_confrontation
    national_before = national_fighter_equivalents(world, insurgent.organization_id)

    moved = insurgent.personnel
    reserve = _reserve_for(world, moved)
    assert insurgent.supply_stock >= reserve
    world.organization_manpower_pools[(insurgent.organization_id, locality)] = (
        world.organization_manpower_pools.get((insurgent.organization_id, locality), 0.0) + moved
    )
    world.organization_manpower_supply_reserves[(insurgent.organization_id, locality)] = reserve
    insurgent.supply_stock -= reserve
    insurgent.personnel = 0.0
    insurgent.operational_status = "ineffective"
    after = local_action_support(world, insurgent.organization_id, locality)

    assert after.total_fighter_equivalents == before.total_fighter_equivalents
    assert national_fighter_equivalents(world, insurgent.organization_id) == national_before
    assert not after.armed_confrontation
    assert after.government_asset_target
    assert after.civilian_coercion_or_extraction


def test_pool_to_formation_transfer_does_not_create_fighter_equivalents():
    world = _world(seed=78)
    insurgent, _ = _pair(world)
    locality = insurgent.locality_id
    quantity = 60.0
    world.organization_manpower_pools[(insurgent.organization_id, locality)] = quantity
    reserve = _reserve_for(world, quantity)
    assert insurgent.supply_stock >= reserve
    insurgent.supply_stock -= reserve
    world.organization_manpower_supply_reserves[(insurgent.organization_id, locality)] = reserve
    before = national_fighter_equivalents(world, insurgent.organization_id)
    insurgent.personnel += quantity
    insurgent.supply_stock += reserve
    world.organization_manpower_pools[(insurgent.organization_id, locality)] = 0.0
    world.organization_manpower_supply_reserves.pop((insurgent.organization_id, locality))
    after = national_fighter_equivalents(world, insurgent.organization_id)
    assert after == before


def test_relocation_moves_local_support_without_reproduction():
    world = _world(seed=79)
    insurgent, _ = _pair(world)
    origin = insurgent.locality_id
    destination = next(locality for locality in world.localities if locality != origin)
    world.organization_manpower_pools[(insurgent.organization_id, origin)] = 50.0
    reserve = _reserve_for(world, 50.0)
    assert insurgent.supply_stock >= reserve
    insurgent.supply_stock -= reserve
    world.organization_manpower_supply_reserves[(insurgent.organization_id, origin)] = reserve
    before_total = national_fighter_equivalents(world, insurgent.organization_id)
    origin_before = local_action_support(world, insurgent.organization_id, origin).total_fighter_equivalents

    world.organization_manpower_pools[(insurgent.organization_id, origin)] = 0.0
    reserve = world.organization_manpower_supply_reserves.pop((insurgent.organization_id, origin))
    world.organization_manpower_pools[(insurgent.organization_id, destination)] = 50.0
    world.organization_manpower_supply_reserves[(insurgent.organization_id, destination)] = reserve
    origin_after = local_action_support(world, insurgent.organization_id, origin).total_fighter_equivalents
    destination_after = local_action_support(world, insurgent.organization_id, destination).total_fighter_equivalents

    assert national_fighter_equivalents(world, insurgent.organization_id) == before_total
    assert origin_after == origin_before - 50.0
    assert destination_after >= 50.0
