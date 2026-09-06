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
from typing import Any

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


def sample_taliban_spatial_prior(
    inputs: dict[str, Any],
    rng: random.Random,
    *,
    total_strength: float,
    preperiod_counts: dict[str, float] | None = None,
    fielded_share_alpha: float = 2.0,
    fielded_share_beta: float = 2.0,
    presence_scale: float = 4.0,
) -> dict[str, Any]:
    """Sample a pre-period spatial/organizational latent-state prior.

    The 2003 district counts are used as evidence weights, not as a rule that
    every observed district starts with a fielded formation.  A sampled
    presence mask controls which localities can host a fielded formation;
    remaining sourced strength is represented as geographically distributed
    clandestine manpower.  The beta/gamma hyperparameters are explicit prior
    choices and are never fitted to benchmark-period outcomes.
    """
    if total_strength < 0:
        raise ValueError("total_strength must be nonnegative")
    if fielded_share_alpha <= 0 or fielded_share_beta <= 0:
        raise ValueError("fielded-share beta parameters must be positive")
    if presence_scale <= 0:
        raise ValueError("presence_scale must be positive")

    source_counts = preperiod_counts or inputs.get(
        "preperiod_taliban_state_conflict_counts_2003",
        inputs["initialization"]["taliban"]["anchor_weights"],
    )
    evidence: dict[str, float] = {}
    for source_id, count in source_counts.items():
        count = float(count)
        if count <= 0:
            continue
        # Case evidence is district keyed (AF0101), while the generated
        # locality surface is locality keyed (AF0101-HQ).  The archived input
        # anchor table already uses locality IDs, so accept both forms and
        # never manufacture an accidental -HQ-HQ identifier.
        locality_id = str(source_id)
        if not locality_id.endswith("-HQ"):
            locality_id = f"{locality_id}-HQ"
        evidence[locality_id] = evidence.get(locality_id, 0.0) + count
    if not evidence:
        raise ValueError("pre-period Taliban locality evidence is empty")

    fielded_share = rng.betavariate(fielded_share_alpha, fielded_share_beta)
    active = {
        locality_id
        for locality_id, count in evidence.items()
        if rng.random() < 1.0 - exp(-count / presence_scale)
    }
    if not active:
        active = {max(evidence, key=evidence.get)}

    # Gamma draws provide a Dirichlet-like random allocation while preserving
    # the observed evidence ordering in expectation.  The +0.5 term gives
    # low-count districts a real, but modest, chance of carrying state.
    fielded_raw = {
        locality_id: rng.gammavariate(evidence[locality_id] + 0.5, 1.0)
        if locality_id in active else 0.0
        for locality_id in evidence
    }
    clandestine_raw = {
        locality_id: rng.gammavariate(evidence[locality_id] + 0.5, 1.0)
        for locality_id in evidence
    }

    def normalize(values: dict[str, float]) -> dict[str, float]:
        total = sum(max(0.0, value) for value in values.values())
        if total <= 0:
            fallback = max(values, key=values.get)
            return {fallback: 1.0}
        return {
            locality_id: max(0.0, value) / total
            for locality_id, value in sorted(values.items())
            if value > 0
        }

    return {
        "mode": "preperiod_spatial_prior_v1",
        "fielded_share": fielded_share,
        "fielded_locality_weights": normalize(fielded_raw),
        "clandestine_locality_weights": normalize(clandestine_raw),
        "evidence_counts": evidence,
        "hyperparameters": {
            "fielded_share_alpha": fielded_share_alpha,
            "fielded_share_beta": fielded_share_beta,
            "presence_scale": presence_scale,
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
    ana_locality = ana["locality_ids"][0]
    for index in range(ana_count):
        formation_id = f"ANA-{index + 1:02d}"
        world.formations[formation_id] = _formation_from_template(
            fdf_template, formation_id, "fdf", ana_locality, ana_each
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

    residual = max(0.0, float(taliban_strength) - actual_fielded)
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
    world.organizations["insurgent"].sponsor_dependence["pakistan"] = clamp(
        float(inputs["pakistan"]["model_mapping"]["taliban_external_sanctuary"])
    )


def _install_clandestine_state(world, allocations: dict[str, float]) -> None:
    """Install latent local pools and represented member networks.

    Pools are unfielded manpower, not an extra force injection.  They are
    deliberately left unequipped; any future material conversion must pass
    through the existing stock-flow rules.  Represented membership gives the
    existing social/recruitment machinery a local organizational footprint
    without inventing a new safehouse or event-memory variable.
    """
    if not allocations:
        return
    organization = world.organizations["insurgent"]
    conversion = max(
        1e-12,
        float(world.config.organization_ecology.fighter_conversion_fraction),
    )
    for locality_id, quantity in sorted(allocations.items()):
        if locality_id not in world.localities or quantity <= 1e-9:
            continue
        key = (organization.organization_id, locality_id)
        world.organization_manpower_pools[key] = (
            world.organization_manpower_pools.get(key, 0.0) + quantity
        )
        remaining_membership = quantity / conversion
        candidates = sorted(
            (
                person for person in world.persons.values()
                if person.residence_locality_id == locality_id
                and person.organization_id is None
            ),
            key=lambda person: (-person.grievance, person.person_id),
        )
        for person in candidates:
            if remaining_membership <= 1e-9:
                break
            fraction = min(
                1.0,
                remaining_membership / max(1e-12, person.weight),
            )
            _set_armed_membership(person, organization, fraction)
            organization.member_ids.add(person.person_id)
            remaining_membership -= person.weight * fraction
    refresh_community_aggregates(world)


def _set_police_post_stock(world, target: float) -> None:
    """Set the observed aggregate police stock using the declared spatial rule."""
    posts = [
        post for post in world.security_posts.values()
        if post.organization_id == "police" and post.formation_id is None
    ]
    total_population = sum(
        world.localities[post.locality_id].population for post in posts
    )
    for post in posts:
        share = world.localities[post.locality_id].population / total_population
        post.personnel = target * share
        post.fixed_presence = clamp(post.personnel / 250.0)


def _scale_police_posts(world, inputs: dict[str, Any]) -> None:
    _set_police_post_stock(
        world, float(inputs["initialization"]["anp"]["personnel"])
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
    )

    # Rebuild downstream state from the sourced force inventory rather than
    # trying to mutate generated logistics/posts in place.
    generate_logistics_world(world)
    generate_physical_world(world)
    _scale_police_posts(world, inputs)
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
