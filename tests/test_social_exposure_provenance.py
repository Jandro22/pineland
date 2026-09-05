from __future__ import annotations

import importlib.util
from pathlib import Path
import random
import sys

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import Organization, OrganizationKind, SocialEdge
from pineland_sim.events import ScheduledEvent
from pineland_sim.processes import ProcessEngine


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "studies" / "research_program" / "scripts" /
    "identify_social_exposure_provenance.py"
)
SPEC = importlib.util.spec_from_file_location("identify_social_exposure_provenance", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _organization(organization_id: str) -> Organization:
    return Organization(
        organization_id=organization_id,
        name=organization_id,
        kind=OrganizationKind.INSURGENT,
        resources=100.0,
        cohesion=.6,
        discipline=.6,
        accountability=.5,
        local_knowledge=.5,
        persistence=.6,
        mobility=.5,
        institutional_quality=.5,
        capital={"social": .5, "political": .5, "organizational": .5, "material": .5},
        ideology={"reform": .5, "separatism": 0.0},
    )


def _world(seed: int = 8801):
    world = generate_pineland(SimulationConfig(
        agent_count=120,
        locality_count=18,
        horizon_days=3,
        seed=seed,
        include_insurgency=False,
    ))
    organization = _organization("franchise-a")
    competitor = _organization("franchise-b")
    world.organizations[organization.organization_id] = organization
    world.organizations[competitor.organization_id] = competitor
    world.config.social_network.behavior_update_rate = 0.0
    return world, organization, competitor


def _isolate_chain(world):
    ordered = [world.persons[person_id] for person_id in sorted(world.persons)]
    target = ordered[0]
    middle = ordered[1]
    source = next(
        person for person in reversed(ordered[2:])
        if person.residence_locality_id != target.residence_locality_id
    )
    selected = {target.person_id, middle.person_id, source.person_id}
    for key, edge in list(world.social_edges.items()):
        if edge.person_a_id in selected or edge.person_b_id in selected:
            del world.social_edges[key]
    for person_id, neighbors in world.social_neighbors.items():
        if person_id in selected:
            world.social_neighbors[person_id] = []
        else:
            world.social_neighbors[person_id] = [
                neighbor_id for neighbor_id in neighbors if neighbor_id not in selected
            ]
    for first, second in ((target, middle), (middle, source)):
        key = tuple(sorted((first.person_id, second.person_id)))
        world.social_edges[key] = SocialEdge(
            key[0], key[1], ("bridge",), 1.0, 1.0, 1.0, 1.0
        )
        world.social_neighbors[first.person_id].append(second.person_id)
        world.social_neighbors[second.person_id].append(first.person_id)
    for person_id in selected:
        world.social_neighbors[person_id].sort()
    return source, middle, target


def _social_tick(world, engine, tracer, event_id: str, time: float):
    before = tracer.capture()
    engine.on_social_influence(
        event_id,
        ScheduledEvent(
            time, 0, int(time), "social_influence",
            {"elapsed_days": 1.0, "interval": 1.0},
        ),
    )
    return tracer.observe_social_influence(before, event_id=event_id, time=time)


def _actor_snapshot(world):
    return {
        person.person_id: (
            person.public_behavior,
            person.organization_id,
            float(person.armed_fraction),
            dict(person.insurgent_affinity),
            dict(person.social_exposure),
        )
        for person in world.persons.values()
    }


class _InactiveChoiceRng:
    def random(self):
        return 0.0

    def choices(self, population, weights=None, k=1):
        assert "inactive" in population
        return ["inactive"]


def test_behavior_change_that_clears_affinity_does_not_carry_stale_origin():
    world, organization, _competitor = _world(seed=8800)
    source, middle, target = _isolate_chain(world)
    for person in (source, middle, target):
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
        person.social_exposure.clear()
    source.organization_id = organization.organization_id
    source.armed_fraction = 1.0
    source.public_behavior = "armed_participation"
    organization.member_ids.add(source.person_id)
    middle.public_behavior = "insurgent_sympathy"
    middle.insurgent_affinity = {organization.organization_id: 1.0}

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    world.config.social_network.behavior_update_rate = 1.0
    before = tracer.capture()
    ProcessEngine(world, _InactiveChoiceRng()).on_social_influence(
        "SOCIAL-BEHAVIOR-ORDER",
        ScheduledEvent(
            1.0, 0, 1, "social_influence",
            {"elapsed_days": 1.0, "interval": 1.0},
        ),
    )
    assert middle.public_behavior == "inactive"
    tracer.observe_social_influence(
        before, event_id="SOCIAL-BEHAVIOR-ORDER", time=1.0
    )
    assert middle.insurgent_affinity == {}

    # The live handler clears affinity when the behavior draw moves an unarmed
    # person out of insurgent sympathy/participation.  A later manual return to
    # sympathy therefore has no identified franchise origin until another
    # observed social tick rebuilds it; the observer must not resurrect the
    # pre-clear source as temporal provenance.
    middle.public_behavior = "insurgent_sympathy"
    world.config.social_network.behavior_update_rate = 0.0
    _social_tick(
        world,
        ProcessEngine(world, random.Random(8800)),
        tracer,
        "SOCIAL-AFTER-BEHAVIOR-ORDER",
        2.0,
    )
    target_record = tracer.sources_for(
        target.person_id, organization.organization_id
    )
    assert target_record is None


def test_delayed_two_tick_propagation_recovers_ultimate_source_locality():
    world, organization, _competitor = _world()
    source, middle, target = _isolate_chain(world)
    for person in (source, middle, target):
        person.organization_id = None
        person.armed_fraction = 0.0
        person.public_behavior = "neutral"
        person.insurgent_affinity.clear()
        person.social_exposure.clear()
    source.organization_id = organization.organization_id
    source.armed_fraction = 1.0
    source.public_behavior = "armed_participation"
    organization.member_ids.add(source.person_id)
    middle.public_behavior = "insurgent_sympathy"

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    engine = ProcessEngine(world, random.Random(8801))

    _social_tick(world, engine, tracer, "SOCIAL-1", 1.0)
    assert target.social_exposure[organization.organization_id] == 0.0
    middle_record = tracer.sources_for(middle.person_id, organization.organization_id)
    assert middle_record is not None
    assert middle_record.source_localities == {
        source.residence_locality_id: middle_record.exposure
    }
    assert middle_record.unattributed == 0.0

    _social_tick(world, engine, tracer, "SOCIAL-2", 2.0)
    target_record = tracer.sources_for(target.person_id, organization.organization_id)
    assert target_record is not None
    assert target_record.exposure > 0.0
    assert target_record.source_localities == {
        source.residence_locality_id: target_record.exposure
    }
    assert target_record.unattributed == 0.0
    assert target_record.coverage == 1.0
    assert abs(tracer.mass_balance()["error"]) <= 1e-12


def test_decay_and_overwrite_replace_stale_provenance_instead_of_accumulating_it():
    world, organization, _competitor = _world(seed=8802)
    source, middle, target = _isolate_chain(world)
    source.organization_id = organization.organization_id
    source.armed_fraction = 1.0
    source.public_behavior = "armed_participation"
    organization.member_ids.add(source.person_id)
    middle.organization_id = None
    middle.armed_fraction = 0.0
    middle.public_behavior = "insurgent_sympathy"
    middle.insurgent_affinity.clear()
    target.organization_id = None
    target.armed_fraction = 0.0
    target.public_behavior = "neutral"
    target.insurgent_affinity.clear()

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    engine = ProcessEngine(world, random.Random(8802))
    _social_tick(world, engine, tracer, "SOCIAL-1", 1.0)
    _social_tick(world, engine, tracer, "SOCIAL-2", 2.0)
    full = tracer.sources_for(target.person_id, organization.organization_id)
    assert full is not None and full.exposure > 0.0

    # A weaker observable signal preserves the same causal origin but scales
    # the provenance mass down with the newly overwritten exposure value.
    middle.public_behavior = "protest"
    _social_tick(world, engine, tracer, "SOCIAL-3", 3.0)
    decayed = tracer.sources_for(target.person_id, organization.organization_id)
    assert decayed is not None
    assert 0.0 < decayed.exposure < full.exposure
    assert decayed.source_localities == {
        source.residence_locality_id: decayed.exposure
    }
    assert decayed.unattributed == 0.0

    # Once the stored exposure is overwritten with zero, no stale provenance
    # remains available for a later recruitment event.
    middle.public_behavior = "neutral"
    middle.insurgent_affinity.clear()
    _social_tick(world, engine, tracer, "SOCIAL-4", 4.0)
    assert target.social_exposure[organization.organization_id] == 0.0
    assert tracer.sources_for(target.person_id, organization.organization_id) is None
    assert abs(tracer.mass_balance()["error"]) <= 1e-12


def test_missing_affinity_provenance_stays_unattributed_and_mass_conserving():
    world, organization, _competitor = _world(seed=8803)
    _source, middle, target = _isolate_chain(world)
    middle.organization_id = None
    middle.armed_fraction = 0.0
    middle.public_behavior = "insurgent_sympathy"
    middle.insurgent_affinity = {organization.organization_id: 1.0}
    target.organization_id = None
    target.armed_fraction = 0.0
    target.public_behavior = "neutral"

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    engine = ProcessEngine(world, random.Random(8803))
    _social_tick(world, engine, tracer, "SOCIAL-UNKNOWN", 1.0)

    record = tracer.sources_for(target.person_id, organization.organization_id)
    assert record is not None and record.exposure > 0.0
    assert record.source_localities == {}
    assert abs(record.unattributed - record.exposure) <= 1e-12
    assert record.coverage == 0.0
    balance = tracer.mass_balance()
    assert abs(balance["error"]) <= 1e-12


def test_external_affinity_overwrite_invalidates_old_origin_instead_of_reusing_it():
    world, organization, competitor = _world(seed=88031)
    source, middle, target = _isolate_chain(world)
    source.organization_id = organization.organization_id
    source.armed_fraction = 1.0
    source.public_behavior = "armed_participation"
    organization.member_ids.add(source.person_id)
    middle.organization_id = None
    middle.armed_fraction = 0.0
    middle.public_behavior = "insurgent_sympathy"
    middle.insurgent_affinity.clear()
    target.organization_id = None
    target.armed_fraction = 0.0
    target.public_behavior = "neutral"

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    engine = ProcessEngine(world, random.Random(88031))
    _social_tick(world, engine, tracer, "SOCIAL-1", 1.0)
    known = tracer.sources_for(middle.person_id, organization.organization_id)
    assert known is not None and known.coverage == 1.0

    # This change occurred outside the observed social process. Even though the
    # old source remains a plausible story, carrying it forward would be a
    # provenance guess rather than an identified causal attribution.
    middle.insurgent_affinity = {
        organization.organization_id: 0.5,
        competitor.organization_id: 0.5,
    }
    _social_tick(world, engine, tracer, "SOCIAL-2", 2.0)
    target_record = tracer.sources_for(target.person_id, organization.organization_id)
    assert target_record is not None and target_record.exposure > 0.0
    assert target_record.source_localities == {}
    assert abs(target_record.unattributed - target_record.exposure) <= 1e-12
    assert target_record.coverage == 0.0


def test_observer_does_not_mutate_actor_state_or_draw_from_transition_rng():
    world, organization, _competitor = _world(seed=8804)
    source, middle, _target = _isolate_chain(world)
    source.organization_id = organization.organization_id
    source.armed_fraction = 1.0
    source.public_behavior = "armed_participation"
    organization.member_ids.add(source.person_id)
    middle.public_behavior = "insurgent_sympathy"

    tracer = MODULE.SocialExposureProvenanceTracer(world)
    engine = ProcessEngine(world, random.Random(8804))
    before = tracer.capture()
    engine.on_social_influence(
        "SOCIAL-OBS",
        ScheduledEvent(1.0, 0, 1, "social_influence", {"elapsed_days": 1.0}),
    )
    actor_state = _actor_snapshot(world)
    rng_state = engine.rng.getstate()
    tracer.observe_social_influence(before, event_id="SOCIAL-OBS", time=1.0)
    assert _actor_snapshot(world) == actor_state
    assert engine.rng.getstate() == rng_state


def test_standalone_provenance_study_reports_exact_mass_balance():
    report = MODULE.trace_social_exposure_provenance(
        SimulationConfig(
            agent_count=180,
            locality_count=18,
            horizon_days=3,
            seed=8805,
            output_mode="ensemble",
        ),
        until=3.0,
    )
    assert report["historical_outcomes_used"] is False
    assert report["dynamics_modified"] is False
    assert abs(report["history_mass_balance"]["error"]) <= 1e-12
    assert abs(report["current_mass_balance"]["error"]) <= 1e-12

