"""Data-free matched intervention study of local insurgent renewal.

The study exercises the live social-influence, recruitment, local manpower,
formation-presence, and organization-survival code. It never reads historical
case outcomes and does not alter core equations.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.entities import OrganizationKind, SocialEdge  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.organization_ecology import (  # noqa: E402
    _apply_local_fighter_change,
    _set_armed_membership,
    organization_survival_social_base,
    recruit_and_retain,
)
from pineland_sim.physical import recompute_contested_controls  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402

DEFAULT_OUTPUT = ROOT / "studies" / "research_program" / "competitive_local_renewal.json"
GENERATION_COUNT = 4


class MatchedRng:
    """Constant draws keep intervention cells on the same decision threshold."""

    def __init__(self, draw: float = 0.25):
        self.draw = float(draw)

    def random(self) -> float:
        return self.draw

    def choices(self, population, weights, k):
        index = max(range(len(population)), key=lambda item: weights[item])
        return [population[index]]

    def normalvariate(self, mu, sigma):
        return mu

    def uniform(self, low, high):
        return (low + high) / 2


def _armed_organization(world):
    return next(
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT
        and organization.status == "active"
    )


def _add_edge(world, first_id: str, second_id: str, layer: str) -> None:
    key = tuple(sorted((first_id, second_id)))
    world.social_edges[key] = SocialEdge(
        key[0], key[1], (layer,), 1.0, 1.0, 1.0,
        min(world.persons[first_id].weight, world.persons[second_id].weight),
    )
    world.social_neighbors[first_id].append(second_id)
    world.social_neighbors[second_id].append(first_id)


def _select_chain(world) -> dict[str, Any]:
    residents: dict[str, list] = {}
    for person in world.persons.values():
        residents.setdefault(person.residence_locality_id, []).append(person)
    localities = [
        locality_id for locality_id in sorted(world.localities)
        if len(residents.get(locality_id, ())) >= 2
    ][:4]
    if len(localities) < 4:
        raise RuntimeError("need four populated synthetic localities")
    source_locality, *targets = localities
    return {
        "source_locality": source_locality,
        "target_localities": tuple(targets),
        "source": residents[source_locality][0],
        "bridge": {loc: residents[loc][0] for loc in targets},
        "local": {loc: residents[loc][1] for loc in targets},
    }


def build_synthetic_world(seed: int = 20260905):
    config = SimulationConfig(
        agent_count=720, locality_count=24,
        horizon_days=float(GENERATION_COUNT + 1), seed=seed,
    )
    config.recruitment_rate = 1.0
    # The renewal experiment freezes endogenous behavior choice so a social
    # event cannot create a behavior-only same-tick cascade. Armed membership
    # still changes public behavior through the live membership setter and is
    # therefore still a social signal on the next generation.
    config.social_network.behavior_update_rate = 0.0
    config.organization_ecology.recruitment_requires_access = True
    config.organization_ecology.recruitment_subcohorts = 20
    world = generate_pineland(config)
    organization = _armed_organization(world)
    organization.cohesion = 1.0
    organization.capital["social"] = 1.0
    organization.resources = max(organization.resources, 10_000_000.0)

    for other in world.organizations.values():
        if other.kind is OrganizationKind.INSURGENT and other is not organization:
            other.status = "inactive"
    for person in world.persons.values():
        if person.organization_id == organization.organization_id:
            organization.member_ids.discard(person.person_id)
            _set_armed_membership(person, None, 0.0)
        person.public_behavior = "neutral"
        person.social_exposure.clear()
        person.grievance = 0.0
        person.fear = 1.0
        person.efficacy = 0.0
    organization.member_ids.clear()
    for key in [
        key for key in world.organization_manpower_pools
        if key[0] == organization.organization_id
    ]:
        del world.organization_manpower_pools[key]
        world.organization_manpower_supply_reserves.pop(key, None)
    for formation in world.formations.values():
        if formation.organization_id == organization.organization_id:
            formation.personnel = 0.0
            formation.supply_stock = 0.0
            formation.operational_status = "ineffective"
            formation.availability = 0.0
            formation.moving = False

    selected = _select_chain(world)
    source = selected["source"]
    selected_ids = {source.person_id}
    for role in ("bridge", "local"):
        selected_ids.update(p.person_id for p in selected[role].values())
    for person in world.persons.values():
        if person.person_id not in selected_ids:
            person.organization_id = "synthetic_ineligible"

    ideology = organization.ideology.get("reform", 0.5)
    source.organization_id = None
    source.grievance = 1.0
    source.fear = 0.0
    source.efficacy = 0.0
    source.political_access = 0.0
    source.identities["federal"] = ideology
    source.expected_control["insurgent"] = 0.0
    _set_armed_membership(source, organization, 1.0)
    organization.member_ids.add(source.person_id)

    for locality_id in selected["target_localities"]:
        for role in ("bridge", "local"):
            person = selected[role][locality_id]
            person.organization_id = None
            person.armed_fraction = 0.0
            person.public_behavior = "neutral"
            person.grievance = 1.0
            person.fear = 0.0
            person.efficacy = 0.0
            person.political_access = 0.0
            person.identities["federal"] = ideology
            person.expected_control["insurgent"] = 0.0
    world.social_edges.clear()
    world.social_neighbors = {person_id: [] for person_id in world.persons}
    previous = source
    for locality_id in selected["target_localities"]:
        bridge = selected["bridge"][locality_id]
        _add_edge(world, previous.person_id, bridge.person_id, "bridge")
        previous = bridge
    for neighbors in world.social_neighbors.values():
        neighbors.sort()

    metadata = {
        "organization_id": organization.organization_id,
        "source_person_id": source.person_id,
        "source_locality": selected["source_locality"],
        "target_localities": list(selected["target_localities"]),
        "bridge_person_ids": {
            loc: selected["bridge"][loc].person_id
            for loc in selected["target_localities"]
        },
        "local_candidate_ids": {
            loc: selected["local"][loc].person_id
            for loc in selected["target_localities"]
        },
    }
    return world, metadata


def _member_mass(world, organization_id: str, locality_id: str) -> float:
    return sum(
        p.weight * p.armed_fraction for p in world.persons.values()
        if p.residence_locality_id == locality_id
        and p.organization_id == organization_id
    )


def _viable_fielded_personnel(world, organization_id: str, locality_id: str) -> float:
    return sum(
        f.personnel for f in world.formations.values()
        if f.organization_id == organization_id
        and f.locality_id == locality_id and f.personnel > 0
        and f.operational_status == "effective"
        and not f.moving and not f.outside_pineland
    )


def _social_control(world, locality_id: str) -> float:
    control = world.localities[locality_id].control.get("insurgent")
    return 0.0 if control is None else float(control.social)


def _suppress_fielded_presence(world, organization_id: str) -> None:
    for formation in world.formations.values():
        if formation.organization_id == organization_id:
            formation.operational_status = "ineffective"
            formation.availability = 0.0
            formation.moving = False


def _recruit_without_member_access(world, organization, time: float):
    original = {
        person_id: world.persons[person_id].residence_locality_id
        for person_id in organization.member_ids
        if person_id in world.persons
        and world.persons[person_id].organization_id == organization.organization_id
    }
    for person_id in original:
        world.persons[person_id].residence_locality_id = (
            "__blocked_member_access__" + person_id
        )
    try:
        return recruit_and_retain(world, time, MatchedRng(), interval_days=1.0)
    finally:
        for person_id, locality_id in original.items():
            world.persons[person_id].residence_locality_id = locality_id


def _force_exit(world, organization, person_id: str, neutralize: bool) -> float:
    person = world.persons[person_id]
    if person.organization_id != organization.organization_id or person.armed_fraction <= 0:
        return 0.0
    represented = person.weight * person.armed_fraction
    _apply_local_fighter_change(
        world, organization, person.residence_locality_id,
        -represented * world.config.organization_ecology.fighter_conversion_fraction,
    )
    organization.member_ids.discard(person_id)
    _set_armed_membership(person, None, 0.0)
    if neutralize:
        person.public_behavior = "neutral"
        person.social_exposure.clear()
    return represented


def _restore_social_control(world, snapshot: dict[str, float]) -> None:
    for locality_id, value in snapshot.items():
        control = world.localities[locality_id].control.get("insurgent")
        if control is not None:
            control.social = value


def _snapshot(world, metadata: dict[str, Any], generation: int,
              new_member_mass: dict[str, float], recruitment_result: dict[str, float]):
    organization = world.organizations[metadata["organization_id"]]
    target_localities = metadata["target_localities"]
    physical = {
        loc: float(recompute_contested_controls(
            world, loc, float(generation)
        ).get("insurgent", 0.0))
        for loc in target_localities
    }
    return {
        "generation": generation,
        "new_member_mass": {loc: float(new_member_mass[loc]) for loc in target_localities},
        "member_mass": {
            loc: float(_member_mass(world, organization.organization_id, loc))
            for loc in target_localities
        },
        "bridge_armed_fraction": {
            loc: float(world.persons[metadata["bridge_person_ids"][loc]].armed_fraction)
            for loc in target_localities
        },
        "local_candidate_armed_fraction": {
            loc: float(world.persons[metadata["local_candidate_ids"][loc]].armed_fraction)
            for loc in target_localities
        },
        "bridge_insurgent_exposure": {
            loc: float(world.persons[metadata["bridge_person_ids"][loc]]
                       .social_exposure.get("insurgent", 0.0))
            for loc in target_localities
        },
        "social_control": {loc: _social_control(world, loc) for loc in target_localities},
        "physical_control": physical,
        "viable_fielded_personnel": {
            loc: float(_viable_fielded_personnel(
                world, organization.organization_id, loc
            ))
            for loc in target_localities
        },
        "organization_survival_social_base": float(
            organization_survival_social_base(world, organization)
        ),
        "recruitment_result": {
            key: float(value) for key, value in recruitment_result.items()
            if isinstance(value, (int, float))
        },
    }


def run_condition(
    base_world,
    metadata: dict[str, Any],
    *,
    block_social_bridging: bool = False,
    block_local_member_access: bool = False,
    block_fielded_force_presence: bool = False,
    block_persistence: bool = False,
    restore_control_state: bool = False,
    remove_source_after_generation: int | None = None,
) -> dict[str, Any]:
    world = deepcopy(base_world)
    organization = world.organizations[metadata["organization_id"]]
    target_localities = metadata["target_localities"]

    if block_social_bridging:
        keys = [key for key, edge in world.social_edges.items() if "bridge" in edge.layers]
        for first_id, second_id in keys:
            del world.social_edges[(first_id, second_id)]
            world.social_neighbors[first_id].remove(second_id)
            world.social_neighbors[second_id].remove(first_id)
    if block_fielded_force_presence:
        _suppress_fielded_presence(world, organization.organization_id)

    engine = ProcessEngine(world, MatchedRng())
    generations = []
    for generation in range(1, GENERATION_COUNT + 1):
        control_before = {
            loc: _social_control(world, loc) for loc in target_localities
        }
        engine.on_social_influence(
            "SYNTHETIC-SOCIAL-" + str(generation),
            ScheduledEvent(
                float(generation), 0, generation, "social_influence",
                {"interval": 1.0, "elapsed_days": 1.0},
            ),
        )
        if restore_control_state:
            _restore_social_control(world, control_before)

        before = {
            loc: _member_mass(world, organization.organization_id, loc)
            for loc in target_localities
        }
        if block_local_member_access:
            recruitment_result = _recruit_without_member_access(
                world, organization, float(generation)
            )
        else:
            recruitment_result = recruit_and_retain(
                world, float(generation), MatchedRng(), interval_days=1.0
            )
        if block_fielded_force_presence:
            _suppress_fielded_presence(world, organization.organization_id)
        after = {
            loc: _member_mass(world, organization.organization_id, loc)
            for loc in target_localities
        }
        new_member_mass = {
            loc: max(0.0, after[loc] - before[loc]) for loc in target_localities
        }
        generations.append(
            _snapshot(world, metadata, generation, new_member_mass, recruitment_result)
        )

        if remove_source_after_generation == generation:
            _force_exit(
                world, organization, metadata["source_person_id"], neutralize=True
            )
        if block_persistence:
            for loc in target_localities:
                _force_exit(
                    world, organization, metadata["bridge_person_ids"][loc],
                    neutralize=True,
                )
                _force_exit(
                    world, organization, metadata["local_candidate_ids"][loc],
                    neutralize=True,
                )
            if block_fielded_force_presence:
                _suppress_fielded_presence(world, organization.organization_id)

    last = generations[-1]
    return {
        "intervention": {
            "block_social_bridging": block_social_bridging,
            "block_local_member_access": block_local_member_access,
            "block_fielded_force_presence": block_fielded_force_presence,
            "block_persistence": block_persistence,
            "restore_control_state": restore_control_state,
            "remove_source_after_generation": remove_source_after_generation,
        },
        "generations": generations,
        "final_member_mass": dict(last["member_mass"]),
        "final_viable_fielded_personnel": dict(last["viable_fielded_personnel"]),
        "final_survival_social_base": last["organization_survival_social_base"],
    }


def exit_only_residual_signal_diagnostic(base_world, metadata: dict[str, Any]) -> dict[str, Any]:
    world = deepcopy(base_world)
    organization = world.organizations[metadata["organization_id"]]
    first, second, _ = metadata["target_localities"]
    first_bridge = metadata["bridge_person_ids"][first]
    second_bridge = metadata["bridge_person_ids"][second]
    engine = ProcessEngine(world, MatchedRng())
    engine.on_social_influence(
        "EXIT-SEED-SOCIAL",
        ScheduledEvent(
            1.0, 0, 1, "social_influence",
            {"interval": 1.0, "elapsed_days": 1.0},
        ),
    )
    recruit_and_retain(world, 1.0, MatchedRng(), interval_days=1.0)
    before_exit_fraction = world.persons[first_bridge].armed_fraction
    removed_mass = _force_exit(
        world, organization, first_bridge, neutralize=False
    )
    immediate_after_exit_fraction = world.persons[first_bridge].armed_fraction
    post_exit_behavior = world.persons[first_bridge].public_behavior
    engine.on_social_influence(
        "EXIT-NEXT-SOCIAL",
        ScheduledEvent(
            2.0, 0, 2, "social_influence",
            {"interval": 1.0, "elapsed_days": 1.0},
        ),
    )
    downstream_exposure = world.persons[second_bridge].social_exposure.get(
        "insurgent", 0.0
    )
    before_downstream = world.persons[second_bridge].armed_fraction
    # The residual sympathy signal is weaker than full armed membership. Use a
    # slightly lower but still retention-safe matched cutoff to test whether
    # that nonzero signal is causally sufficient for recruitment.
    recruit_and_retain(world, 2.0, MatchedRng(0.20), interval_days=1.0)
    after_downstream = world.persons[second_bridge].armed_fraction
    return {
        "before_exit_armed_fraction": float(before_exit_fraction),
        "removed_represented_member_mass": float(removed_mass),
        "after_exit_armed_fraction": float(immediate_after_exit_fraction),
        "after_exit_public_behavior": post_exit_behavior,
        "downstream_exposure_after_member_exit": float(downstream_exposure),
        "downstream_armed_fraction_before_recruitment": float(before_downstream),
        "downstream_armed_fraction_after_recruitment": float(after_downstream),
    }


def social_control_mediation_diagnostic(
    base_world, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Induce a social-control side effect, then restore only control state."""
    world = deepcopy(base_world)
    organization = world.organizations[metadata["organization_id"]]
    first, second, _ = metadata["target_localities"]
    first_bridge = metadata["bridge_person_ids"][first]
    second_bridge = metadata["bridge_person_ids"][second]
    engine = ProcessEngine(world, MatchedRng())

    # Seed actual armed membership in the first target using the main pathway.
    engine.on_social_influence(
        "CONTROL-DIAGNOSTIC-SEED",
        ScheduledEvent(
            1.0, 0, 1, "social_influence",
            {"interval": 1.0, "elapsed_days": 1.0},
        ),
    )
    recruit_and_retain(world, 1.0, MatchedRng(), interval_days=1.0)
    if world.persons[first_bridge].armed_fraction <= 0:
        raise RuntimeError("control diagnostic failed to seed first bridge member")

    # Add one behavior-only observer. It cannot recruit, but an armed neighbor
    # can move its public behavior and therefore the locality social-control
    # record through the live social influence process.
    excluded = {
        metadata["source_person_id"],
        *metadata["bridge_person_ids"].values(),
        *metadata["local_candidate_ids"].values(),
    }
    observer = next(
        person for person in world.persons.values()
        if person.residence_locality_id == first
        and person.person_id not in excluded
    )
    observer.organization_id = "synthetic_ineligible"
    observer.public_behavior = "neutral"
    observer.grievance = 1.0
    observer.fear = 0.0
    observer.efficacy = 0.0
    observer.expected_control["insurgent"] = 0.0
    _add_edge(world, first_bridge, observer.person_id, "community")
    world.config.social_network.behavior_update_rate = 1.0

    before_control = {
        loc: _social_control(world, loc) for loc in metadata["target_localities"]
    }
    ProcessEngine(world, MatchedRng()).on_social_influence(
        "CONTROL-DIAGNOSTIC-EFFECT",
        ScheduledEvent(
            2.0, 0, 2, "social_influence",
            {"interval": 1.0, "elapsed_days": 1.0},
        ),
    )
    after_control = {
        loc: _social_control(world, loc) for loc in metadata["target_localities"]
    }

    retained = deepcopy(world)
    restored = deepcopy(world)
    _restore_social_control(restored, before_control)
    recruit_and_retain(retained, 2.0, MatchedRng(), interval_days=1.0)
    recruit_and_retain(restored, 2.0, MatchedRng(), interval_days=1.0)
    retained_fraction = retained.persons[second_bridge].armed_fraction
    restored_fraction = restored.persons[second_bridge].armed_fraction
    retained_mass = _member_mass(retained, organization.organization_id, second)
    restored_mass = _member_mass(restored, organization.organization_id, second)
    return {
        "observer_person_id": observer.person_id,
        "observer_behavior_after_exposure": world.persons[observer.person_id].public_behavior,
        "social_control_before": before_control,
        "social_control_after": after_control,
        "first_locality_social_control_delta": float(
            after_control[first] - before_control[first]
        ),
        "downstream_bridge_armed_fraction_with_control_retained": float(
            retained_fraction
        ),
        "downstream_bridge_armed_fraction_with_control_restored": float(
            restored_fraction
        ),
        "downstream_member_mass_with_control_retained": float(retained_mass),
        "downstream_member_mass_with_control_restored": float(restored_mass),
        "membership_trajectory_identical_after_control_restore": bool(
            retained_fraction == restored_fraction
            and abs(retained_mass - restored_mass) <= 1e-12
        ),
    }


def run_study(seed: int = 20260905) -> dict[str, Any]:
    base_world, metadata = build_synthetic_world(seed)
    conditions = {
        "baseline": run_condition(base_world, metadata),
        "no_social_bridging": run_condition(
            base_world, metadata, block_social_bridging=True
        ),
        "no_local_member_access": run_condition(
            base_world, metadata, block_local_member_access=True
        ),
        "no_fielded_force_presence": run_condition(
            base_world, metadata, block_fielded_force_presence=True
        ),
        "no_local_or_field_access": run_condition(
            base_world, metadata,
            block_local_member_access=True,
            block_fielded_force_presence=True,
        ),
        "no_persistence": run_condition(
            base_world, metadata, block_persistence=True
        ),
        "clandestine_after_source_cut": run_condition(
            base_world, metadata,
            block_fielded_force_presence=True,
            remove_source_after_generation=1,
        ),
    }
    exit_diagnostic = exit_only_residual_signal_diagnostic(base_world, metadata)
    control_diagnostic = social_control_mediation_diagnostic(base_world, metadata)
    first, second, third = metadata["target_localities"]
    baseline = conditions["baseline"]
    no_bridge = conditions["no_social_bridging"]
    no_member = conditions["no_local_member_access"]
    no_field = conditions["no_fielded_force_presence"]
    combined = conditions["no_local_or_field_access"]
    no_persistence = conditions["no_persistence"]
    clandestine = conditions["clandestine_after_source_cut"]
    baseline_last = baseline["generations"][-1]
    no_bridge_last = no_bridge["generations"][-1]
    combined_last = combined["generations"][-1]
    clandestine_last = clandestine["generations"][-1]

    gates = {
        "renewal_reaches_successive_cross_local_generations": (
            baseline["generations"][0]["bridge_armed_fraction"][first] > 0
            and baseline["generations"][1]["bridge_armed_fraction"][second] > 0
            and baseline["generations"][2]["bridge_armed_fraction"][third] > 0
        ),
        "bridge_ablation_blocks_cross_local_reproduction": all(
            no_bridge_last["bridge_armed_fraction"][loc] == 0
            for loc in metadata["target_localities"]
        ),
        "local_member_and_field_access_are_redundant_amplifiers": (
            no_member["generations"][1]["local_candidate_armed_fraction"][first] > 0
            and no_field["generations"][1]["local_candidate_armed_fraction"][first] > 0
            and combined_last["local_candidate_armed_fraction"][first] == 0
        ),
        "cross_local_social_chain_survives_both_local_access_ablations": (
            combined_last["bridge_armed_fraction"][third] > 0
        ),
        "full_persistence_break_stops_next_generation": (
            no_persistence["generations"][1]["bridge_armed_fraction"][second] == 0
            and no_persistence["generations"][2]["bridge_armed_fraction"][third] == 0
        ),
        "clandestine_membership_renews_without_viable_field_presence_after_source_cut": (
            clandestine_last["bridge_armed_fraction"][third] > 0
            and clandestine_last["local_candidate_armed_fraction"][first] > 0
            and all(
                clandestine_last["viable_fielded_personnel"][loc] == 0
                for loc in metadata["target_localities"]
            )
        ),
        "social_control_state_is_not_a_recruitment_mediator": (
            control_diagnostic[
                "membership_trajectory_identical_after_control_restore"
            ]
        ),
        "membership_exit_leaves_residual_social_signal": (
            exit_diagnostic["before_exit_armed_fraction"] > 0
            and exit_diagnostic["after_exit_armed_fraction"] == 0
            and exit_diagnostic["after_exit_public_behavior"] == "insurgent_sympathy"
            and exit_diagnostic["downstream_exposure_after_member_exit"] > 0
            and exit_diagnostic["downstream_armed_fraction_after_recruitment"]
            > exit_diagnostic["downstream_armed_fraction_before_recruitment"]
        ),
        "field_presence_ablation_removes_viable_force_but_not_renewal": (
            all(
                no_field["generations"][-1]["viable_fielded_personnel"][loc] == 0
                for loc in metadata["target_localities"]
            )
            and no_field["generations"][-1]["bridge_armed_fraction"][third] > 0
            and no_field["generations"][-1]["local_candidate_armed_fraction"][first] > 0
        ),
        "armed_membership_generates_social_and_physical_side_effects": (
            control_diagnostic["first_locality_social_control_delta"] > 0
            and baseline_last["physical_control"][first] > 0
        ),
    }

    contrasts = {
        "baseline_minus_no_bridge_final_member_mass": {
            loc: baseline_last["member_mass"][loc] - no_bridge_last["member_mass"][loc]
            for loc in metadata["target_localities"]
        },
        "baseline_minus_no_member_access_local_fraction": {
            loc: baseline_last["local_candidate_armed_fraction"][loc]
            - no_member["generations"][-1]["local_candidate_armed_fraction"][loc]
            for loc in metadata["target_localities"]
        },
        "baseline_minus_no_field_presence_local_fraction": {
            loc: baseline_last["local_candidate_armed_fraction"][loc]
            - no_field["generations"][-1]["local_candidate_armed_fraction"][loc]
            for loc in metadata["target_localities"]
        },
        "combined_local_access_ablation_local_fraction": {
            loc: combined_last["local_candidate_armed_fraction"][loc]
            for loc in metadata["target_localities"]
        },
    }

    return {
        "schema_version": "1.0.0",
        "status": "synthetic_general_theory_intervention_study",
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "seed": seed,
        "live_mechanism_audit": {
            "renewing_positive_feedback_loop_present": bool(
                gates["renewal_reaches_successive_cross_local_generations"]
            ),
            "identified_loop": [
                "cross-local public behavior writes social exposure",
                "social exposure supplies recruitment access and enters recruitment intensity",
                "recruitment writes fractional armed membership",
                "armed membership supplies future local member access",
                "armed membership converts into local fighter manpower",
                "fighter manpower can materialize an effective local formation",
                "armed members broadcast future insurgent social signal",
                "member mass raises organization survival social base",
            ],
            "control_mediation": {
                "social_control_level_enters_recruitment_hazard": False,
                "physical_control_level_enters_recruitment_hazard": False,
                "fielded_formation_presence_enters_recruitment_access": True,
                "interpretation": (
                    "Control is downstream in this loop. The causal inputs back into "
                    "recruitment are social exposure, local armed-member access, and "
                    "effective local formation access. Restoring social-control state "
                    "does not change the matched membership trajectory."
                ),
            },
            "persistence_layers": {
                "armed_membership": (
                    "supports local recruitment access and fighter-manpower generation"
                ),
                "public_sympathy_after_exit": (
                    "live member exit removes armed membership but leaves insurgent "
                    "sympathy, which can continue cross-local exposure"
                ),
            },
            "clandestine_self_sustain_without_fielded_presence": bool(
                gates[
                    "clandestine_membership_renews_without_viable_field_presence_after_source_cut"
                ]
            ),
        },
        "design": {
            "generations": GENERATION_COUNT,
            "localities": metadata,
            "common_draw": 0.25,
            "same_tick_cascades": "excluded by the live frozen access snapshot",
            "interventions": {
                "social_bridging": "remove only cross-local bridge edges",
                "local_armed_membership_access": (
                    "hide incumbent residence only while live recruitment snapshots "
                    "local armed-member access"
                ),
                "fielded_force_presence": (
                    "make insurgent formations ineffective and unavailable while "
                    "preserving armed member state"
                ),
                "persistence_exit": (
                    "force recruited members to exit and neutralize the remaining "
                    "public social signal at each generation boundary"
                ),
                "social_control_placebo": (
                    "restore social-control state after influence while preserving "
                    "social exposure and behavior"
                ),
            },
        },
        "conditions": conditions,
        "exit_only_residual_signal": exit_diagnostic,
        "social_control_mediation": control_diagnostic,
        "contrasts": contrasts,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_study(args.seed)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
