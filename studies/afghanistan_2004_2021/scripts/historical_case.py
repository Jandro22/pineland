"""Afghanistan-specific historical conditioning for the transfer benchmark.

This module maps sourced case inputs into existing Pineland state variables.
It does not alter model equations and never conditions on benchmark-period
violence or the SIGAR control validation outcome.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
from math import exp
from pathlib import Path
import random
from typing import Any, Iterable

from pineland_sim.entities import (
    ActorBelief,
    ArmedFormation,
    BorderSegment,
    ControlVector,
    ForeignBelief,
    ForeignState,
    Organization,
    OrganizationKind,
    clamp,
)
from pineland_sim.action_model import local_fighter_equivalents
from pineland_sim.information import initialize_information_world
from pineland_sim.logistics import generate_logistics_world
from pineland_sim.networks import refresh_community_aggregates
from pineland_sim.organization_ecology import (
    _set_armed_membership,
    initialize_organization_ecology,
)
from pineland_sim.physical import generate_physical_world, recompute_contested_controls


STUDY = Path(__file__).resolve().parents[1]
INPUTS = STUDY / "config" / "historical_case_inputs.json"
START = date(2004, 1, 1)


def load_historical_inputs() -> dict[str, Any]:
    return json.loads(INPUTS.read_text(encoding="utf-8"))


def _neutral_actor_beliefs(world) -> None:
    """Rebuild neutral priors after Afghanistan-specific organizations exist."""
    initialize_information_world(world)
    world.beliefs.clear()
    for organization_id in world.organizations:
        for locality_id in world.localities:
            estimate = ControlVector(*([.5] * 7))
            organization = world.organizations[organization_id]
            target_actor = (
                "insurgent"
                if organization.kind is OrganizationKind.INSURGENT
                else "government"
            )
            world.beliefs[(organization_id, locality_id)] = ActorBelief(
                organization_id,
                locality_id,
                ControlVector(**estimate.to_dict()),
                world.config.information.prior_confidence,
                0.0,
            )
            world.control_beliefs[(organization_id, target_actor, locality_id)] = ActorBelief(
                organization_id,
                locality_id,
                ControlVector(**estimate.to_dict()),
                world.config.information.prior_confidence,
                0.0,
            )
            opposing_actor = "government" if target_actor == "insurgent" else "insurgent"
            if opposing_actor in world.organizations:
                world.control_beliefs[(organization_id, opposing_actor, locality_id)] = ActorBelief(
                    organization_id,
                    locality_id,
                    ControlVector(*([.5] * 7)),
                    world.config.information.prior_confidence,
                    0.0,
                )


def _formation_from_template(template: ArmedFormation, formation_id: str,
                             organization_id: str, locality_id: str,
                             personnel: float) -> ArmedFormation:
    return ArmedFormation(
        formation_id=formation_id,
        organization_id=organization_id,
        locality_id=locality_id,
        personnel=float(personnel),
        quality=template.quality,
        cohesion=template.cohesion,
        readiness=template.readiness,
        sustainment=template.sustainment,
        information=template.information,
        mobility=template.mobility,
        command=template.command,
        embeddedness=template.embeddedness,
        fatigue=0.0,
        availability=.85,
        cumulative_losses=0.0,
    )


TALIBAN_PRIOR_FAMILIES: dict[str, dict[str, float]] = {
    # These are predeclared structural regimes. They are sampled or selected
    # before any 2004+ outcome is read and are not tuned against the holdout.
    "concentrated": {
        "fielded_share_alpha": 2.5,
        "fielded_share_beta": 1.8,
        "presence_scale": 3.0,
        "background_presence_probability": 0.01,
        "manpower_concentration": 0.75,
    },
    "balanced": {
        "fielded_share_alpha": 2.0,
        "fielded_share_beta": 2.0,
        "presence_scale": 4.0,
        "background_presence_probability": 0.02,
        "manpower_concentration": 1.5,
    },
    "dispersed": {
        "fielded_share_alpha": 1.8,
        "fielded_share_beta": 2.5,
        "presence_scale": 6.0,
        "background_presence_probability": 0.04,
        "manpower_concentration": 2.5,
    },
}


def _normalize_weights(values: dict[str, float]) -> dict[str, float]:
    positive = {
        locality_id: max(0.0, float(value))
        for locality_id, value in values.items()
        if float(value) > 0
    }
    total = sum(positive.values())
    if total <= 0:
        raise ValueError("spatial prior has no positive allocation mass")
    return {
        locality_id: value / total
        for locality_id, value in sorted(positive.items())
    }


def sample_taliban_spatial_prior(
    inputs: dict[str, Any],
    rng: random.Random,
    *,
    total_strength: float,
    preperiod_counts: dict[str, float] | None = None,
    preperiod_province_counts: dict[str, float] | None = None,
    locality_ids: Iterable[str] | None = None,
    prior_family: str | None = None,
    fielded_share_alpha: float | None = None,
    fielded_share_beta: float | None = None,
    presence_scale: float | None = None,
    background_presence_probability: float | None = None,
    manpower_concentration: float | None = None,
) -> dict[str, Any]:
    """Sample a hierarchical pre-period spatial/organizational prior.

    Pre-period event counts inform occupancy/foothold evidence only. Conditional
    on a sampled occupancy mask, fielded and equipped-clandestine manpower are
    allocated from an independent exchangeable force prior. This prevents
    observed event frequency from being treated as a direct fighter count and
    permits background occupancy outside recorded districts.
    """
    if total_strength < 0:
        raise ValueError("total_strength must be nonnegative")
    if prior_family is None:
        prior_family = rng.choice(sorted(TALIBAN_PRIOR_FAMILIES))
    if prior_family not in TALIBAN_PRIOR_FAMILIES:
        raise ValueError(
            f"unknown Taliban prior family {prior_family!r}; "
            f"choose from {sorted(TALIBAN_PRIOR_FAMILIES)}"
        )
    family = TALIBAN_PRIOR_FAMILIES[prior_family]
    alpha = (
        float(family["fielded_share_alpha"])
        if fielded_share_alpha is None else float(fielded_share_alpha)
    )
    beta = (
        float(family["fielded_share_beta"])
        if fielded_share_beta is None else float(fielded_share_beta)
    )
    scale = (
        float(family["presence_scale"])
        if presence_scale is None else float(presence_scale)
    )
    background = (
        float(family["background_presence_probability"])
        if background_presence_probability is None
        else float(background_presence_probability)
    )
    concentration = (
        float(family["manpower_concentration"])
        if manpower_concentration is None
        else float(manpower_concentration)
    )
    if alpha <= 0 or beta <= 0:
        raise ValueError("fielded-share beta parameters must be positive")
    if scale <= 0:
        raise ValueError("presence_scale must be positive")
    if not 0 <= background <= 1:
        raise ValueError("background presence probability must be in [0, 1]")
    if concentration <= 0:
        raise ValueError("manpower concentration must be positive")

    source_counts = preperiod_counts or inputs.get(
        "preperiod_taliban_state_conflict_counts_2003"
    ) or inputs["initialization"]["taliban"]["anchor_weights"]
    province_background_counts = preperiod_province_counts or inputs.get(
        "preperiod_taliban_state_conflict_province_background_counts_2003",
        {},
    )
    evidence: dict[str, float] = {}
    for source_id, count in source_counts.items():
        count = float(count)
        if count <= 0:
            continue
        locality_id = str(source_id)
        if not locality_id.endswith("-HQ"):
            locality_id = f"{locality_id}-HQ"
        evidence[locality_id] = evidence.get(locality_id, 0.0) + count
    if not evidence:
        raise ValueError("pre-period Taliban locality evidence is empty")

    candidate_localities = tuple(sorted({
        str(locality_id) for locality_id in (locality_ids or evidence)
    }))
    if not candidate_localities:
        raise ValueError("spatial prior requires at least one candidate locality")
    missing_evidence = set(evidence) - set(candidate_localities)
    if missing_evidence:
        raise ValueError(
            "pre-period evidence references localities outside the supplied "
            f"geography: {sorted(missing_evidence)[:5]}"
        )

    def province_id_for_locality(locality_id: str) -> str | None:
        # Afghanistan case locality IDs are AFdd..-HQ. Returning None for an
        # unfamiliar adapter keeps the generic prior's background floor.
        prefix = locality_id[:4]
        return prefix if prefix.startswith("AF") else None

    occupancy_probability = {}
    for locality_id in candidate_localities:
        if locality_id in evidence:
            occupancy_probability[locality_id] = 1.0 - exp(
                -evidence[locality_id] / scale
            )
            continue
        province_id = province_id_for_locality(locality_id)
        province_count = float(
            province_background_counts.get(province_id, 0.0)
            if province_id is not None else 0.0
        )
        # Low-precision events affect only province/background occupancy. They
        # never enter local manpower allocation.
        occupancy_probability[locality_id] = clamp(
            background + 0.25 * (1.0 - exp(-province_count / scale))
        )
    active = {
        locality_id
        for locality_id in candidate_localities
        if rng.random() < occupancy_probability[locality_id]
    }
    if not active:
        # A nonempty pre-period foothold is a conditioning requirement, while
        # the selected location remains random under the declared evidence.
        active = {rng.choice(sorted(evidence))}

    # Force allocation is independent of event counts once occupancy is known.
    # A common concentration regime is equivalent to a symmetric Dirichlet
    # draw over the sampled occupied localities.
    fielded_raw = {
        locality_id: rng.gammavariate(concentration, 1.0)
        for locality_id in sorted(active)
    }
    clandestine_raw = {
        locality_id: rng.gammavariate(concentration, 1.0)
        for locality_id in sorted(active)
    }
    return {
        "mode": "preperiod_occupancy_force_hierarchy_v2",
        "prior_family": prior_family,
        "fielded_share": rng.betavariate(alpha, beta),
        "fielded_locality_weights": _normalize_weights(fielded_raw),
        "clandestine_locality_weights": _normalize_weights(clandestine_raw),
        "occupied_localities": sorted(active),
        "candidate_localities": list(candidate_localities),
        "evidence_counts": evidence,
        "province_background_counts": {
            str(key): float(value)
            for key, value in sorted(province_background_counts.items())
        },
        "occupancy_probabilities": occupancy_probability,
        "hyperparameters": {
            "fielded_share_alpha": alpha,
            "fielded_share_beta": beta,
            "presence_scale": scale,
            "background_presence_probability": background,
            "manpower_concentration": concentration,
        },
    }


def sample_security_deployment_prior(world, rng: random.Random) -> dict[str, Any]:
    """Sample outcome-free ANA/ANP deployment weights under stock constraints.

    Population, administrative centrality, and a small predeclared gamma
    perturbation determine deployment. The returned ANA draw has exactly the
    sourced formation count; personnel totals are enforced by the installer.
    """
    localities = tuple(sorted(world.localities))
    population_weights = {
        locality_id: max(1.0, float(world.localities[locality_id].population))
        for locality_id in localities
    }
    noisy_anp = {
        locality_id: population_weights[locality_id] * rng.gammavariate(8.0, 1.0 / 8.0)
        for locality_id in localities
    }
    capital_id = "AF0101-HQ" if "AF0101-HQ" in world.localities else localities[0]
    noisy_broad = {
        locality_id: population_weights[locality_id] * rng.gammavariate(4.0, 1.0 / 4.0)
        for locality_id in localities
    }
    ana_weights = _normalize_weights(noisy_broad)
    ana_weights[capital_id] = ana_weights.get(capital_id, 0.0) + 0.75
    ana_weights = _normalize_weights(ana_weights)
    return {
        "mode": "outcome_free_security_deployment_v1",
        "ana_locality_weights": ana_weights,
        "anp_locality_weights": _normalize_weights(noisy_anp),
        "ana_formation_localities": rng.choices(
            list(localities),
            weights=[ana_weights[locality_id] for locality_id in localities],
            k=12,
        ),
        "covariates": {
            "ana": "0.75 capital prior plus population/noisy broad deployment",
            "anp": "population-proportional noisy deployment",
        },
    }


def _clear_synthetic_foreign_system(world) -> None:
    world.foreign_states.clear()
    world.border_segments.clear()
    world.foreign_beliefs.clear()
    world.interpreter_brokers.clear()
    world.diaspora_links.clear()
    world.foreign_interventions.clear()
    world.external_support.clear()
    world.external_transfers.clear()


def _reset_insurgent_membership(world) -> None:
    """Remove generator-created insurgent state before historical conditioning."""
    insurgent = world.organizations["insurgent"]
    for person in world.persons.values():
        if person.organization_id == "insurgent":
            person.organization_id = None
            person.armed_fraction = 0.0
        # Synthetic affinity/sympathy belongs to the generated Pineland case,
        # not the sourced Afghanistan initial condition. Leaving it in place
        # seeds recruitment outside the declared pre-period footprint.
        person.insurgent_affinity.pop("insurgent", None)
        person.social_exposure.pop("insurgent", None)
        if person.public_behavior in {"armed_participation", "insurgent_sympathy"}:
            person.public_behavior = "neutral"
    insurgent.member_ids.clear()
    refresh_community_aggregates(world)
    world.organization_manpower_pools.clear()
    world.organization_manpower_supply_reserves.clear()
    world.proto_organizations.clear()
    world.organization_transitions.clear()
    world.organization_eligibility_log.clear()
    world.organization_onset_log.clear()
    world.leaders.clear()
    insurgent.leader_id = None


def _install_forces(
    world,
    inputs: dict[str, Any],
    taliban_strength: float,
    taliban_prior: dict[str, Any] | None = None,
    security_prior: dict[str, Any] | None = None,
) -> dict[str, float]:
    fdf_template = next(
        formation for formation in world.formations.values()
        if formation.organization_id == "fdf"
    )
    insurgent_template = next(
        formation for formation in world.formations.values()
        if formation.organization_id == "insurgent"
    )
    world.formations.clear()

    ana = inputs["initialization"]["ana"]
    ana_count = int(ana["formation_count"])
    ana_each = float(ana["personnel"]) / ana_count
    ana_localities = (
        list(security_prior.get("ana_formation_localities", ()))
        if security_prior is not None
        else []
    )
    if len(ana_localities) != ana_count:
        ana_localities = [ana["locality_ids"][0]] * ana_count
    for index in range(ana_count):
        formation_id = f"ANA-{index + 1:02d}"
        world.formations[formation_id] = _formation_from_template(
            fdf_template, formation_id, "fdf", ana_localities[index], ana_each
        )

    taliban = inputs["initialization"]["taliban"]
    if taliban_prior is None:
        fielded_weights = {
            str(locality_id): float(weight)
            for locality_id, weight in taliban["anchor_weights"].items()
        }
        fielded_share = 1.0
        clandestine_weights: dict[str, float] = {}
    else:
        fielded_weights = {
            str(locality_id): float(weight)
            for locality_id, weight in taliban_prior["fielded_locality_weights"].items()
        }
        fielded_share = clamp(float(taliban_prior["fielded_share"]))
        clandestine_weights = {
            str(locality_id): float(weight)
            for locality_id, weight in taliban_prior["clandestine_locality_weights"].items()
        }
    total_weight = sum(fielded_weights.values())
    target_fielded = float(taliban_strength) * fielded_share
    minimum_fielded = float(world.config.organization_ecology.minimum_formation_personnel)
    actual_fielded = 0.0
    clandestine_allocations: dict[str, float] = {}
    for index, (locality_id, weight) in enumerate(sorted(fielded_weights.items()), 1):
        personnel = target_fielded * weight / max(1e-12, total_weight)
        if personnel < minimum_fielded:
            clandestine_allocations[locality_id] = (
                clandestine_allocations.get(locality_id, 0.0) + personnel
            )
            continue
        formation_id = f"TAL-{index:02d}"
        world.formations[formation_id] = _formation_from_template(
            insurgent_template, formation_id, "insurgent", locality_id, personnel
        )
        actual_fielded += personnel

    residual = max(
        0.0,
        float(taliban_strength)
        - actual_fielded
        - sum(clandestine_allocations.values()),
    )
    clandestine_total_weight = sum(clandestine_weights.values())
    if clandestine_total_weight <= 0:
        fallback = next(iter(fielded_weights), None)
        if fallback is not None:
            clandestine_weights = {fallback: 1.0}
            clandestine_total_weight = 1.0
    for locality_id, weight in sorted(clandestine_weights.items()):
        clandestine_allocations[locality_id] = (
            clandestine_allocations.get(locality_id, 0.0)
            + residual * weight / max(1e-12, clandestine_total_weight)
        )

    coalition = inputs["international_forces"]
    initial_total = float(coalition["stock_schedule"][0]["total"])
    initial_localities = list(coalition["initial_locality_ids"])
    per_formation = initial_total / len(initial_localities)
    foreign_template = ArmedFormation(
        "TEMPLATE", "coalition", initial_localities[0], per_formation,
        .78, .76, .82, .9, .38, .72, .68, .12,
    )
    for index, locality_id in enumerate(initial_localities, 1):
        formation_id = f"COAL-{index:02d}"
        formation = _formation_from_template(
            foreign_template, formation_id, "coalition", locality_id, per_formation
        )
        world.formations[formation_id] = formation

    # Keep the sourced Taliban envelope exact while allowing the latent prior
    # to split it between fielded formations and clandestine local manpower.
    # Tiny roundoff is assigned to the largest clandestine locality.
    allocated = actual_fielded + sum(clandestine_allocations.values())
    if clandestine_allocations:
        correction = float(taliban_strength) - allocated
        target = max(clandestine_allocations, key=clandestine_allocations.get)
        clandestine_allocations[target] += correction
    elif abs(allocated - float(taliban_strength)) > 1e-8:
        raise AssertionError("Taliban sourced strength was not conserved")
    return {
        locality_id: quantity
        for locality_id, quantity in sorted(clandestine_allocations.items())
        if quantity > 1e-9
    }


def _install_pakistan(world, inputs: dict[str, Any]) -> None:
    """Install explicit Pakistan/border objects and sanctuary semantics.

    Foreign-affairs evolution is disabled for the transfer benchmark, so the
    foreign state's preference fields remain bookkeeping placeholders.  The
    organization-to-sponsor relation is not inert: the existing spatial
    sanctuary operator requires it to turn the binary sourced sanctuary
    availability into a local border gradient.
    """
    state = ForeignState(
        "pakistan", "Pakistan", 0.0,
        .5, .5, .5, .5, .5, .5, .5, .5, .5, .5,
        {"FS": .5, "AR": .5, "VE": .5, "TA": .5}, .5,
    )
    world.foreign_states[state.state_id] = state
    for district_id in inputs["pakistan"]["border_district_ids"]:
        locality_id = f"{district_id}-HQ"
        locality = world.localities[locality_id]
        border_id = f"B-{district_id}-pakistan"
        world.border_segments[border_id] = BorderSegment(
            border_id, "pakistan", district_id, locality_id,
            locality.terrain_friction, locality.infrastructure,
            .5, .5, .5, .5, .5,
        )
        world.foreign_beliefs[("pakistan", locality_id)] = ForeignBelief(
            "pakistan", locality_id, .5, .2, .12, 0.0
        )
    world.organizations["insurgent"].external_sanctuary = float(
        inputs["pakistan"]["model_mapping"]["taliban_external_sanctuary"]
    )
    # The sourced statement supports a sanctuary/access link. It does not
    # identify a maximum political/resource dependence intensity.
    world.organizations["insurgent"].sponsor_links["pakistan"] = 1.0
    world.organizations["insurgent"].sponsor_dependence.pop("pakistan", None)


def _install_clandestine_state(world, allocations: dict[str, float]) -> None:
    """Install latent local pools and represented member networks.

    Pools are equipped clandestine fighter equivalents, not formations. Their
    material reserve is explicit, so action capacity can use the authoritative
    local_fighter_equivalents() operator. Represented membership is allocated
    by a fractional propensity rule rather than a resolution-sensitive
    highest-grievance sort.
    """
    if not allocations:
        return
    organization = world.organizations["insurgent"]
    conversion = max(
        1e-12,
        float(world.config.organization_ecology.fighter_conversion_fraction),
    )
    supply_per_fighter = max(
        1e-12,
        float(world.config.logistics.formation_supply_days)
        * float(world.config.logistics.initial_supply_fraction),
    )
    for locality_id, quantity in sorted(allocations.items()):
        if locality_id not in world.localities or quantity <= 1e-9:
            continue
        key = (organization.organization_id, locality_id)
        world.organization_manpower_pools[key] = (
            world.organization_manpower_pools.get(key, 0.0) + quantity
        )
        world.organization_manpower_supply_reserves[key] = (
            world.organization_manpower_supply_reserves.get(key, 0.0)
            + quantity * supply_per_fighter
        )
        remaining_membership = quantity / conversion
        candidates = sorted(
            (
                person for person in world.persons.values()
                if person.residence_locality_id == locality_id
                and person.organization_id is None
            ),
            key=lambda person: person.person_id,
        )
        # Fractional propensity allocation is invariant to candidate ordering
        # and conserves the represented target population up to available
        # local population caps.
        active = list(candidates)
        assigned_fraction: dict[str, float] = {}
        while remaining_membership > 1e-9 and active:
            propensities = {
                person.person_id: max(
                    1e-9,
                    person.weight * (.5 + .5 * clamp(person.grievance)),
                )
                for person in active
            }
            total_propensity = sum(propensities.values())
            saturated = False
            next_active = []
            allocated_this_round = 0.0
            for person in active:
                share = remaining_membership * propensities[person.person_id] / total_propensity
                capacity = max(
                    0.0,
                    person.weight * (
                        1.0 - assigned_fraction.get(
                            person.person_id,
                            person.armed_fraction,
                        )
                    ),
                )
                represented = min(capacity, share)
                if represented > 0:
                    fraction = represented / max(1e-12, person.weight)
                    cumulative_fraction = assigned_fraction.get(
                        person.person_id,
                        person.armed_fraction,
                    ) + fraction
                    assigned_fraction[person.person_id] = cumulative_fraction
                    _set_armed_membership(
                        world, person, organization, cumulative_fraction
                    )
                    organization.member_ids.add(person.person_id)
                    allocated_this_round += represented
                if represented + 1e-9 < share:
                    saturated = True
                else:
                    next_active.append(person)
            remaining_membership -= allocated_this_round
            if not saturated or allocated_this_round <= 1e-12:
                break
            active = next_active
    refresh_community_aggregates(world)


def _set_police_post_stock(
    world,
    target: float,
    locality_weights: dict[str, float] | None = None,
) -> None:
    """Set aggregate police stock under an explicit spatial deployment prior."""
    posts = [
        post for post in world.security_posts.values()
        if post.organization_id == "police" and post.formation_id is None
    ]
    if locality_weights is None:
        weights = {
            post.locality_id: max(1.0, float(world.localities[post.locality_id].population))
            for post in posts
        }
    else:
        weights = {
            post.locality_id: max(0.0, float(locality_weights.get(post.locality_id, 0.0)))
            for post in posts
        }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("police deployment prior has no mass on generated posts")
    for post in posts:
        share = weights[post.locality_id] / total_weight
        post.personnel = target * share
        post.fixed_presence = clamp(post.personnel / 250.0)


def _scale_police_posts(
    world,
    inputs: dict[str, Any],
    security_prior: dict[str, Any] | None = None,
) -> None:
    _set_police_post_stock(
        world,
        float(inputs["initialization"]["anp"]["personnel"]),
        None if security_prior is None else security_prior.get("anp_locality_weights"),
    )


def _reset_accounting_baselines(world) -> None:
    world.time = 0.0
    world.initial_population = world.weighted_population()
    world.cumulative_deaths = 0.0
    world.cumulative_external_inflow = 0.0
    world.demobilized_personnel = 0.0
    world.demobilized_arms = 0.0
    world.supply_shipments.clear()
    world.initial_supply_stock = (
        sum(source.stock for source in world.supply_sources.values())
        + sum(formation.supply_stock for formation in world.formations.values())
        + sum(world.organization_manpower_supply_reserves.values())
        + world.demobilized_arms
    )
    world.cumulative_supply_produced = 0.0
    world.cumulative_supply_consumed = 0.0
    world.cumulative_supply_lost = 0.0
    world.cumulative_resource_to_supply = 0.0
    world.stock_transactions.clear()
    world.initialize_stock_ledger()


def condition_world(
    world,
    inputs: dict[str, Any] | None = None,
    taliban_strength: float | None = None,
    *,
    taliban_prior: dict[str, Any] | None = None,
    security_prior: dict[str, Any] | None = None,
):
    """Replace generic generated stocks with sourced Afghanistan case inputs."""
    inputs = inputs or load_historical_inputs()
    allowed = {
        float(value)
        for value in inputs["initialization"]["taliban"]["personnel_envelope"]
    }
    if taliban_strength is None:
        taliban_strength = float(
            inputs["initialization"]["taliban"]["default_transfer_scenario"]
        )
    taliban_strength = float(taliban_strength)
    if taliban_strength not in allowed:
        raise ValueError(
            f"Taliban strength must be one of the sourced uncertainty strata: {sorted(allowed)}"
        )

    world.organizations["government"].name = "Islamic Republic of Afghanistan"
    world.organizations["fdf"].name = "Afghan National Army"
    world.organizations["police"].name = "Afghan National Police"
    world.organizations["insurgent"].name = "Taliban"
    world.organizations["coalition"] = Organization(
        "coalition", "International Coalition", OrganizationKind.FOREIGN,
        0.0, .72, .75, .5, .15, .65, .7, .7,
    )

    _clear_synthetic_foreign_system(world)
    _reset_insurgent_membership(world)
    clandestine_allocations = _install_forces(
        world,
        inputs,
        taliban_strength,
        taliban_prior=taliban_prior,
        security_prior=security_prior,
    )

    # Rebuild downstream state from the sourced force inventory rather than
    # trying to mutate generated logistics/posts in place.
    generate_logistics_world(world)
    generate_physical_world(world)
    _scale_police_posts(world, inputs, security_prior=security_prior)
    initialize_organization_ecology(world)
    _install_clandestine_state(world, clandestine_allocations)
    _install_pakistan(world, inputs)

    # Police post scaling changes the initial response field. Recompute true
    # physical control before creating neutral actor priors.
    for locality_id in world.localities:
        aggregates = recompute_contested_controls(world, locality_id, 0.0)
        for actor, aggregate in aggregates.items():
            world.localities[locality_id].control.setdefault(
                actor, ControlVector()
            ).physical = aggregate

    _neutral_actor_beliefs(world)
    _reset_accounting_baselines(world)
    world.assert_invariants()
    return world


def initialization_diagnostics(world, inputs: dict[str, Any],
                               taliban_strength: float) -> dict[str, Any]:
    by_org = {
        organization_id: sum(
            formation.personnel for formation in world.formations.values()
            if formation.organization_id == organization_id
        )
        for organization_id in ("fdf", "insurgent", "coalition")
    }
    police = sum(
        post.personnel for post in world.security_posts.values()
        if post.organization_id == "police" and post.formation_id is None
    )
    clandestine = sum(
        local_fighter_equivalents(world, "insurgent", locality_id)[0]
        for locality_id in world.localities
    )
    raw_clandestine = sum(
        quantity
        for (organization_id, _), quantity
        in world.organization_manpower_pools.items()
        if organization_id == "insurgent"
    )
    total_fighter_equivalents = by_org["insurgent"] + clandestine
    return {
        "weighted_population": world.weighted_population(),
        "ana_personnel": by_org["fdf"],
        "anp_personnel": police,
        "taliban_personnel": total_fighter_equivalents,
        "taliban_fielded_personnel": by_org["insurgent"],
        "taliban_clandestine_personnel": clandestine,
        "taliban_unarmed_manpower_pool": max(0.0, raw_clandestine - clandestine),
        "taliban_total_fighter_equivalents": total_fighter_equivalents,
        "taliban_source_strength_residual": total_fighter_equivalents - float(taliban_strength),
        "coalition_personnel": by_org["coalition"],
        "ana_formations": sum(
            formation.organization_id == "fdf" for formation in world.formations.values()
        ),
        "taliban_formations": sum(
            formation.organization_id == "insurgent" for formation in world.formations.values()
        ),
        "coalition_formations": sum(
            formation.organization_id == "coalition" for formation in world.formations.values()
        ),
        "foreign_states": sorted(world.foreign_states),
        "pakistan_border_segments": len(world.border_segments),
        "taliban_external_sanctuary": world.organizations["insurgent"].external_sanctuary,
        "taliban_pakistan_sponsor_dependence": world.organizations[
            "insurgent"
        ].sponsor_dependence.get("pakistan", 0.0),
        "taliban_pakistan_sanctuary_link": world.organizations[
            "insurgent"
        ].sponsor_links.get("pakistan", 0.0),
        "taliban_clandestine_localities": sorted({
            locality_id
            for (organization_id, locality_id), quantity
            in world.organization_manpower_pools.items()
            if organization_id == "insurgent" and quantity > 0
        }),
        "stock_ledger_residual": world.stock_ledger_residual(),
        "supply_conservation_residual": world.supply_conservation_residual(),
        "expected": {
            "ana_personnel": inputs["initialization"]["ana"]["personnel"],
            "anp_personnel": inputs["initialization"]["anp"]["personnel"],
            "taliban_personnel": taliban_strength,
            "coalition_personnel": inputs["international_forces"]["stock_schedule"][0]["total"],
            "ana_formations": inputs["initialization"]["ana"]["formation_count"],
            "pakistan_border_segments": len(inputs["pakistan"]["border_district_ids"]),
        },
    }


class HistoricalCoalitionSchedule:
    """Condition observed coalition and police stocks at their source dates."""

    def __init__(self, inputs: dict[str, Any]):
        self.schedule = []
        for row in inputs["international_forces"]["stock_schedule"]:
            day = (date.fromisoformat(row["date"]) - START).days
            self.schedule.append((day, dict(row)))
        self.schedule.sort(key=lambda item: item[0])
        # Day zero is already installed in condition_world.
        self.cursor = 1
        self.police_schedule = []
        for row in inputs["initialization"]["anp"].get("stock_schedule", []):
            day = (date.fromisoformat(row["date"]) - START).days
            self.police_schedule.append((day, dict(row)))
        self.police_schedule.sort(key=lambda item: item[0])
        # Day zero is already installed in condition_world.
        self.police_cursor = 1
        self.applied: list[dict[str, Any]] = []
        self.control_validation_day = (
            date.fromisoformat(inputs["control_validation"]["source_date"]) - START
        ).days
        self.control_snapshot: dict[str, dict[str, dict[str, float]]] | None = None
        self.control_snapshot_time: float | None = None

    def clone(self) -> "HistoricalCoalitionSchedule":
        """Clone only mutable schedule progress for particle branching.

        Source-date schedules are immutable case inputs after construction, so
        sibling particles can share them.  Cursor/provenance/snapshot state is
        copied per lineage.
        """
        import copy

        cloned = object.__new__(type(self))
        cloned.schedule = self.schedule
        cloned.cursor = self.cursor
        cloned.police_schedule = self.police_schedule
        cloned.police_cursor = self.police_cursor
        cloned.applied = [dict(item) for item in self.applied]
        cloned.control_validation_day = self.control_validation_day
        cloned.control_snapshot = copy.deepcopy(self.control_snapshot)
        cloned.control_snapshot_time = self.control_snapshot_time
        return cloned

    def _apply_stock(self, world, target: float, row: dict[str, Any]) -> None:
        formations = sorted(
            (
                formation for formation in world.formations.values()
                if formation.organization_id == "coalition"
            ),
            key=lambda formation: formation.formation_id,
        )
        if not formations:
            raise AssertionError("historical coalition schedule has no coalition formations")
        before = world.tracked_stock_totals()
        current = sum(formation.personnel for formation in formations)
        if current > 0:
            scale = target / current
            for formation in formations:
                formation.personnel *= scale
        else:
            for formation in formations:
                formation.personnel = target / len(formations)
        for formation in formations:
            doctrinal_capacity = (
                formation.personnel * world.config.logistics.formation_supply_days
            )
            formation.supply_capacity = max(formation.supply_stock, doctrinal_capacity)
            formation.sustainment = formation.supply_fraction()
            post = world.security_posts.get(f"POST-{formation.formation_id}")
            if post is not None:
                post.personnel = formation.personnel
                post.fixed_presence = clamp(formation.personnel / 2_000.0)

        sources = [
            source for source in world.supply_sources.values()
            if source.organization_id == "coalition"
        ]
        if sources:
            cfg = world.config.logistics
            total_requirement = (
                target * cfg.presence_consumption_per_person_day
                * cfg.organization_sustainment_coverage
            )
            production = total_requirement / len(sources)
            for source in sources:
                desired_capacity = max(
                    5_000.0, production / cfg.source_daily_production_fraction
                )
                source.capacity = max(source.stock, desired_capacity)
                source.production_per_day = production

        after = world.tracked_stock_totals()
        world.record_stock_transactions(
            f"HIST-COALITION-{row['date']}",
            "policy_treatment",
            before,
            after,
        )
        self.applied.append({
            "stock": "coalition_personnel",
            "time": world.time,
            "date": row["date"],
            "target_personnel": target,
            "realized_personnel": sum(f.personnel for f in formations),
            "source_id": row["source_id"],
            "observation_type": row["observation_type"],
        })

    def _apply_police_stock(self, world, target: float, row: dict[str, Any]) -> None:
        before = world.tracked_stock_totals()
        _set_police_post_stock(world, target)
        after = world.tracked_stock_totals()
        world.record_stock_transactions(
            f"HIST-ANP-{row['date']}",
            "policy_treatment",
            before,
            after,
        )
        realized = sum(
            post.personnel for post in world.security_posts.values()
            if post.organization_id == "police" and post.formation_id is None
        )
        self.applied.append({
            "stock": "police_personnel",
            "time": world.time,
            "date": row["date"],
            "target_personnel": target,
            "realized_personnel": realized,
            "source_id": row["source_id"],
            "observation_type": row["observation_type"],
        })

    def __call__(self, world, time: float) -> None:
        while self.cursor < len(self.schedule) and self.schedule[self.cursor][0] <= time:
            _, row = self.schedule[self.cursor]
            self._apply_stock(world, float(row["total"]), row)
            self.cursor += 1
        while (
            self.police_cursor < len(self.police_schedule)
            and self.police_schedule[self.police_cursor][0] <= time
        ):
            _, row = self.police_schedule[self.police_cursor]
            self._apply_police_stock(world, float(row["total"]), row)
            self.police_cursor += 1
        if self.control_snapshot is None and time >= self.control_validation_day:
            self.control_snapshot = {
                locality_id: {
                    "government": locality.control["government"].to_dict(),
                    "insurgent": locality.control["insurgent"].to_dict(),
                }
                for locality_id, locality in world.localities.items()
            }
            self.control_snapshot_time = time


def coalition_schedule_manifest(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in inputs["international_forces"]["stock_schedule"]]
