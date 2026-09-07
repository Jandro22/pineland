"""Operation-count and numerical-equivalence checks for recurring hot paths."""
from collections import deque
from unittest.mock import patch

from pineland_sim import Simulation, SimulationConfig, generate_pineland
from pineland_sim.entities import ArmedFormation
from pineland_sim.information import _corroboration_weight
from pineland_sim.logistics import advance_movement_orders, choose_reallocation_orders, update_logistics
from pineland_sim.physical import response_times
from pineland_sim.world import seeded_rng
from pineland_sim.reproducibility import decision_state_sha256


def test_corroboration_matches_uncapped_history_scan():
    history = deque((index / 12, f"source-{index % 11}") for index in range(120))
    for timestamp in (0, 3, 7.5, 10, 15):
        for source in ("source-0", "other"):
            sources = {identity for stamp, identity in history
                       if identity != source and abs(stamp - timestamp) <= 3}
            for correlation in (0, .15, .35, .55, .65, .99, 1):
                expected = min(3, sum(1.0 - correlation for _ in sources))
                assert _corroboration_weight(history, timestamp, source, correlation) == expected


def test_response_does_not_evaluate_remote_patrol_readiness():
    world = generate_pineland(SimulationConfig(agent_count=50, locality_count=17, seed=818))
    locality = next(iter(world.localities))
    original = ArmedFormation.effective_readiness

    def checked(formation):
        assert formation.locality_id == locality
        return original(formation)

    with patch.object(ArmedFormation, "effective_readiness", checked):
        response_times(world, locality, "government", 0)


class NoArchiveScan(dict):
    def values(self):
        raise AssertionError("Recurring logistics scanned the historical archive")


def test_recurring_logistics_uses_active_indexes_and_conserves_supply():
    config = SimulationConfig(agent_count=50, locality_count=17, horizon_days=3, seed=303)
    world = Simulation(generate_pineland(config)).run().world
    world.movement_orders = NoArchiveScan(world.movement_orders)
    world.supply_shipments = NoArchiveScan(world.supply_shipments)
    advance_movement_orders(world, 4)
    choose_reallocation_orders(world, 4, seeded_rng(config, "scaling-test"))
    update_logistics(world, 4, 1)
    world.movement_orders = dict(world.movement_orders)
    world.supply_shipments = dict(world.supply_shipments)
    assert abs(world.supply_conservation_residual()) < 1e-5
    assert set(world.active_shipment_ids) == {
        key for key, item in world.supply_shipments.items() if item.status == "in_transit"
    }
    assert set(world.active_movement_order_ids) == {
        key for key, item in world.movement_orders.items() if item.status in {"pending", "moving"}
    }


def test_particle_information_compaction_preserves_decision_state():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=1, seed=919
    )
    world = generate_pineland(config)
    world.execution_profile = "particle"
    simulation = Simulation(world)
    simulation.run(until=0.5, validate_invariants=False, checkpoint=False)
    reference = world.clone(share_static=True)
    before = decision_state_sha256(reference)
    reference.compact_particle_information_state()
    assert decision_state_sha256(reference) == before
    pending = {
        reference.information_relays[relay_id].observation_id
        for relay_id in reference.active_information_relays
        if relay_id in reference.information_relays
    }
    assert set(reference.observations) == pending
    assert set(reference.information_relays) <= reference.active_information_relays
    assert reference.observation_index == {}


def test_particle_information_compacts_only_at_delivery_boundary():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=1, seed=927
    )
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    simulation.initialize()
    # Information delivery is the only process that can complete/drop active
    # relays. Patrol/contact events only add new active relay work.
    from unittest.mock import patch
    with patch.object(
        world, "compact_particle_information_state",
        wraps=world.compact_particle_information_state,
    ) as compact:
        simulation.run(until=0.25)
    information_events = world.event_counts.get("information", 0)
    # event_counts is intentionally suppressed in particle mode; use the
    # scheduled information cadence for this short window instead.
    assert compact.call_count >= 1
    assert compact.call_count <= 2


def test_particle_execution_does_not_accumulate_resource_flow_archive():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=2, seed=920
    )
    world = generate_pineland(config)
    world.execution_profile = "particle"
    Simulation(world).run(until=2, validate_invariants=False, checkpoint=False)
    assert world.resource_flows == []


def test_particle_execution_skips_information_diagnostic_archives():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=1, seed=926
    )
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    simulation.run(until=0.5)
    assert world.observation_index == {}
    assert world.information_detection_by_source == {}
    assert not any(world.information_detections.values())


def test_particle_clone_shares_only_read_only_observation_payloads():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=1, seed=921
    )
    world = generate_pineland(config)
    world.execution_profile = "particle"
    Simulation(world).run(until=0.5, validate_invariants=False, checkpoint=False)
    cloned = world.clone(share_static=True)
    if world.observations:
        observation_id = next(iter(world.observations))
        parent = world.observations[observation_id]
        child = cloned.observations[observation_id]
        assert child is not parent
        assert child.estimated_value is parent.estimated_value
        assert child.provenance is parent.provenance
        old_received = parent.received_at
        child.received_at = 123.0
        assert parent.received_at == old_received
    assert cloned.physical_neighbors is world.physical_neighbors
    assert cloned.microzone_ids_by_locality is world.microzone_ids_by_locality


def test_command_path_cache_is_invalidated_by_new_edge():
    from pineland_sim.logistics import _add_command_edge, command_path

    world = generate_pineland(
        SimulationConfig(agent_count=50, locality_count=17, seed=922)
    )
    edge = next(iter(world.command_edges.values()))
    organization_id = edge.organization_id
    command_path(
        world, organization_id, edge.node_a_id, edge.node_b_id
    )
    assert world.command_path_cache
    _add_command_edge(
        world,
        f"CMD:{organization_id}",
        "TEST-NODE",
        organization_id,
        0.9,
        1.0,
    )
    assert world.command_path_cache == {}


def test_particle_residence_index_tracks_relocation_exactly():
    world = generate_pineland(
        SimulationConfig(agent_count=50, locality_count=17, seed=923)
    )
    world.execution_profile = "particle"
    person = next(iter(world.persons.values()))
    origin = person.residence_locality_id
    destination = next(
        locality_id for locality_id in world.localities
        if locality_id != origin
    )
    assert person.person_id in world.person_ids_by_residence_locality[origin]
    world.relocate_person(person, destination)
    assert person.person_id not in world.person_ids_by_residence_locality[origin]
    assert person.person_id in world.person_ids_by_residence_locality[destination]
    assert [item.person_id for item in world.persons_in_locality(destination)] == (
        world.person_ids_by_residence_locality[destination]
    )


def test_particle_membership_indexes_track_assignment_exactly():
    world = generate_pineland(
        SimulationConfig(agent_count=50, locality_count=17, seed=924)
    )
    world.execution_profile = "particle"
    person = next(iter(world.unassigned_people()))
    organization_id = next(iter(world.organizations))
    world.set_person_organization(person, organization_id)
    assert person.person_id not in world.unassigned_person_ids
    assert person.person_id in world.person_ids_by_organization[organization_id]
    world.set_person_organization(person, None)
    assert person.person_id in world.unassigned_person_ids
    assert person.person_id not in world.person_ids_by_organization[
        organization_id
    ]


def test_entering_particle_mode_rebuilds_preconditioning_indexes():
    world = generate_pineland(
        SimulationConfig(agent_count=50, locality_count=17, seed=925)
    )
    person = next(iter(world.persons.values()))
    origin = person.residence_locality_id
    destination = next(
        locality_id for locality_id in world.localities
        if locality_id != origin
    )
    # Emulate an empirical conditioning layer that mutates standard state
    # directly before handing the world to the particle runner.
    person.residence_locality_id = destination
    person.organization_id = next(iter(world.organizations))
    simulation = Simulation(world)
    simulation.configure_execution(retain_output_archives=False)
    assert person.person_id in world.person_ids_by_residence_locality[destination]
    assert person.person_id not in world.person_ids_by_residence_locality.get(
        origin, ()
    )
    assert person.person_id in world.person_ids_by_organization[
        person.organization_id
    ]


def test_particle_physical_refresh_trusts_maintained_runtime_indexes():
    config = SimulationConfig(
        agent_count=80, locality_count=17, horizon_days=1, seed=930
    )
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.configure_execution(
        validate_invariants=False,
        checkpointing=False,
        retain_output_archives=False,
    )
    from unittest.mock import patch
    with patch.object(
        type(world),
        "rebuild_runtime_entity_indexes",
        wraps=type(world).rebuild_runtime_entity_indexes,
    ) as rebuild:
        simulation.run(until=0.25)
    assert rebuild.call_count == 0


def test_language_metadata_indexes_match_district_patterns():
    world = generate_pineland(
        SimulationConfig(agent_count=50, locality_count=17, seed=929)
    )
    for locality_id, locality in world.localities.items():
        pattern = world.districts[locality.district_id].language_pattern
        assert world.primary_language_by_locality[locality_id] == (
            pattern.split("/", 1)[0]
        )
        assert (
            locality_id in world.multilingual_locality_ids
        ) == ("/" in pattern)
