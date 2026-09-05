import random

import pytest

from pineland_sim import SimulationConfig, generate_pineland
from pineland_sim.entities import DiasporaLink, ProtoOrganization
from pineland_sim.events import ScheduledEvent
from pineland_sim.foreign_affairs import process_diaspora
from pineland_sim.organization_ecology import mature_proto
from pineland_sim.political_order import process_political_order
from pineland_sim.processes import ProcessEngine


def _config(agent_count: int, seed: int = 707) -> SimulationConfig:
    return SimulationConfig(
        agent_count=agent_count,
        locality_count=24,
        horizon_days=1,
        seed=seed,
        include_insurgency=True,
    )


def _liquid_material_total(world) -> float:
    stocks = world.tracked_stock_totals()
    return sum(
        value for name, value in stocks.items()
        if name not in {
            "formation_personnel", "mobilized_personnel_pool",
            "demobilized_personnel",
        }
    )


def test_generated_civilian_resources_scale_with_represented_population_not_agent_tokens():
    rows = []
    # Keep CI compact while spanning a 4x representative-agent resolution.
    # A separate one-off audit reproduces the reported 5k/10k/20k ladder.
    for count in (500, 1_000, 2_000):
        world = generate_pineland(_config(count))
        civilian = sum(person.resources for person in world.persons.values())
        rows.append((count, world.weighted_population(), civilian))
        assert sum(h.resources for h in world.households.values()) == pytest.approx(civilian)
        assert world.household_resource_residual() < 1e-8

    represented = {row[1] for row in rows}
    assert len(represented) == 1
    per_capita = [civilian / population for _, population, civilian in rows]
    # Endowments are sampled, so finite representative samples need not have
    # identical means.  What must disappear is the old fourfold stock increase
    # when token count rises fourfold.
    assert max(per_capita) / min(per_capita) < 1.05
    totals = [row[2] for row in rows]
    assert max(totals) / min(totals) < 1.05


def test_diaspora_remittance_is_a_conserved_represented_stock_transfer():
    world = generate_pineland(_config(600))
    person = next(iter(world.persons.values()))
    state = next(iter(world.foreign_states.values()))
    person.external_state_id = state.state_id
    link = DiasporaLink(
        "DL-RESOURCE-TEST", person.person_id, state.state_id,
        person.home_locality_id, 1.0, person.resources * .2, 1.0, 0.0,
    )
    world.diaspora_links = {link.link_id: link}
    before_person = person.resources
    before_household = world.households[person.household_id].resources
    before_state = state.resources
    before_total = _liquid_material_total(world)

    amount, _ = process_diaspora(world, 0.0, "E-RESOURCE-REMIT", random.Random(1))

    assert amount > 0
    assert person.resources - before_person == pytest.approx(amount)
    assert world.households[person.household_id].resources - before_household == pytest.approx(amount)
    assert before_state - state.resources == pytest.approx(amount)
    assert _liquid_material_total(world) == pytest.approx(before_total)
    assert world.household_resource_residual() < 1e-8


def test_proto_resource_intensity_and_contribution_use_represented_units_once():
    world = generate_pineland(_config(600))
    cfg = world.config.organization_ecology
    cfg.minimum_formation_personnel = 0.0
    cfg.birth_base_hazard = 1.0
    people = list(world.persons.values())[:4]
    member_ids = {person.person_id for person in people}
    represented = sum(person.weight for person in people)
    civilian_before = sum(person.resources for person in people)
    expected_contribution = civilian_before * cfg.onset_resource_fraction
    per_capita_intensity = civilian_before / represented / 3.0
    proto = ProtoOrganization(
        "PROTO-RESOURCE-TEST", people[0].community_id, people[0].residence_locality_id,
        member_ids,
        {"social": .6, "political": .6, "organizational": .6,
         "material": min(1.0, per_capita_intensity)},
        {"reform": .5, "separatism": .2}, .8, 0.0,
    )
    world.proto_organizations[proto.proto_id] = proto
    before_total = _liquid_material_total(world)

    organization = mature_proto(world, proto, 0.0, random.Random(1))

    assert organization is not None
    civilian_after = sum(world.persons[pid].resources for pid in member_ids)
    assert civilian_before - civilian_after == pytest.approx(expected_contribution)
    formation_supply = sum(
        formation.supply_stock for formation in world.formations.values()
        if formation.organization_id == organization.organization_id
    )
    assert organization.resources + formation_supply == pytest.approx(expected_contribution)
    assert _liquid_material_total(world) == pytest.approx(before_total)
    assert world.household_resource_residual() < 1e-8


def test_tax_extraction_and_patronage_magnitudes_do_not_depend_on_agent_resolution():
    economy_rows = []
    political_rows = []
    for count in (500, 1_000, 2_000):
        world = generate_pineland(_config(count, seed=909))
        government_before_economy = world.organizations["government"].resources
        insurgents_before_economy = sum(
            organization.resources for organization in world.organizations.values()
            if organization.kind.value == "insurgent"
        )
        economy = ProcessEngine(world, random.Random(11)).on_economy(
            "E-RESOURCE-ECON",
            ScheduledEvent(30.0, 0, 0, "economy", {"interval": 30.0}),
        )
        insurgents_after_economy = sum(
            organization.resources for organization in world.organizations.values()
            if organization.kind.value == "insurgent"
        )
        economy_rows.append((
            economy["net_output"],
            economy["government_revenue"],
            world.organizations["government"].resources - government_before_economy,
            insurgents_after_economy - insurgents_before_economy,
        ))
        government_before = world.organizations["government"].resources
        result = process_political_order(world, 30.0, "E-RESOURCE-POL", random.Random(4))
        political_rows.append((
            result["budget"], result["patronage"],
            government_before - world.organizations["government"].resources,
        ))
        assert world.household_resource_residual() < 1e-8

    assert economy_rows[0] == pytest.approx(economy_rows[1])
    assert economy_rows[0] == pytest.approx(economy_rows[2])
    assert political_rows[0] == pytest.approx(political_rows[1])
    assert political_rows[0] == pytest.approx(political_rows[2])


def test_global_resource_ledger_stress_preserves_transfer_accounting():
    world = generate_pineland(_config(800, seed=1201))
    initial = world.tracked_stock_totals()

    person = next(iter(world.persons.values()))
    state = next(iter(world.foreign_states.values()))
    person.external_state_id = state.state_id
    world.diaspora_links = {
        "DL-STRESS": DiasporaLink(
            "DL-STRESS", person.person_id, state.state_id, person.home_locality_id,
            1.0, person.resources * .4, 1.0, 0.0,
        )
    }
    for step in range(25):
        before = world.tracked_stock_totals()
        total_before = _liquid_material_total(world)
        process_diaspora(world, float(step), f"E-STRESS-REM-{step}", random.Random(step))
        after = world.tracked_stock_totals()
        world.record_stock_transactions(f"E-STRESS-REM-{step}", "foreign_affairs", before, after)
        assert _liquid_material_total(world) == pytest.approx(total_before)

    for step in range(8):
        before = world.tracked_stock_totals()
        process_political_order(world, 30.0 * (step + 1), f"E-STRESS-POL-{step}",
                                random.Random(100 + step))
        after = world.tracked_stock_totals()
        world.record_stock_transactions(f"E-STRESS-POL-{step}", "political_order", before, after)

    diagnostics = world.global_accounting_diagnostics()
    assert diagnostics["max_abs_stock_residual"] < 1e-6
    assert diagnostics["reconciliation"]["closed"]
    assert world.stock_ledger_residual() == pytest.approx(0.0, abs=1e-6)
    assert world.household_resource_residual() < 1e-8
    assert all(value >= -1e-9 for value in world.tracked_stock_totals().values())
    assert initial["person_resources"] > 0
