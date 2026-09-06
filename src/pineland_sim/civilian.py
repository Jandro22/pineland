"""Typed civilian harm and population-conserving civilian consequences."""
from __future__ import annotations

from .entities import CivilianHarmEvent


def _resident_people(world, locality_id: str):
    return [
        person
        for person in world.persons.values()
        if person.external_state_id is None
        and person.residence_locality_id == locality_id
        and person.weight > 0
    ]


def apply_direct_civilian_harm(
    world,
    event_id: str,
    locality_id: str,
    direct_harm: float,
    *,
    cause: str,
    responsible_organization_id: str | None = None,
) -> CivilianHarmEvent:
    """Apply casualty-equivalent direct harm without resolution dependence.

    The direct-harm quantity is expected affected population. Fatalities reduce
    representative weights proportionally across the exposed locality;
    injuries are a cumulative flow and do not remove population.
    """
    direct_harm = max(0.0, float(direct_harm))
    cfg = world.config.civilian_dynamics
    residents = _resident_people(world, locality_id)
    represented = sum(person.weight for person in residents)
    deaths = min(
        represented,
        direct_harm * cfg.fatality_fraction_of_direct_harm,
    )
    injuries = min(
        max(0.0, represented - deaths),
        direct_harm * cfg.injury_fraction_of_direct_harm,
    )
    if deaths > 0 and represented > 0:
        for person in residents:
            share = person.weight / represented
            person.weight = max(0.0, person.weight - deaths * share)
        locality = world.localities[locality_id]
        locality.population = max(0.0, float(locality.population) - deaths)
        district = world.districts[locality.district_id]
        district.population = max(0.0, float(district.population) - deaths)
        world.cumulative_deaths += deaths
    world.cumulative_civilian_harm += direct_harm
    world.cumulative_civilian_injuries += injuries
    harm = CivilianHarmEvent(
        f"CH{len(world.civilian_harm_events) + 1:010d}",
        world.time,
        event_id,
        locality_id,
        cause,
        responsible_organization_id,
        direct_harm,
        deaths,
        injuries,
    )
    world.civilian_harm_events.append(harm)
    return harm


def apply_civilian_resource_loss(
    world,
    event_id: str,
    locality_id: str,
    amount: float,
    *,
    cause: str,
    responsible_organization_id: str | None = None,
) -> CivilianHarmEvent | None:
    """Destroy a declared quantity of civilian-owned resources proportionally."""
    residents = _resident_people(world, locality_id)
    available = sum(max(0.0, person.resources) for person in residents)
    loss = min(max(0.0, float(amount)), available)
    if loss <= 0:
        return None
    for person in residents:
        share = max(0.0, person.resources) / max(1e-12, available)
        world.adjust_person_resources(person.person_id, -loss * share)
    world.cumulative_civilian_resource_loss += loss
    harm = CivilianHarmEvent(
        f"CH{len(world.civilian_harm_events) + 1:010d}",
        world.time,
        event_id,
        locality_id,
        cause,
        responsible_organization_id,
        0.0,
        0.0,
        0.0,
        resource_loss=loss,
    )
    world.civilian_harm_events.append(harm)
    return harm


def record_displacement_harm(
    world,
    event_id: str,
    locality_id: str,
    displaced_population: float,
    *,
    cause: str = "forced_displacement",
) -> None:
    displaced_population = max(0.0, float(displaced_population))
    if displaced_population <= 0:
        return
    world.cumulative_civilian_displacement += displaced_population
    world.civilian_harm_events.append(
        CivilianHarmEvent(
            f"CH{len(world.civilian_harm_events) + 1:010d}",
            world.time,
            event_id,
            locality_id,
            cause,
            None,
            0.0,
            0.0,
            0.0,
            displaced_population=displaced_population,
        )
    )


def civilian_harm_diagnostics(world) -> dict:
    return {
        "direct_harm": world.cumulative_civilian_harm,
        "deaths": world.cumulative_deaths,
        "injuries": world.cumulative_civilian_injuries,
        "resource_loss": world.cumulative_civilian_resource_loss,
        "displacement_flow": world.cumulative_civilian_displacement,
        "events": len(world.civilian_harm_events),
    }
