"""Neighbor states, borders, international support, migration, and intervention."""
from __future__ import annotations

from math import exp
import random

from .entities import (ArmedFormation, BorderSegment, DiasporaLink, ExternalSupport,
                       ExternalTransfer, ForeignBelief, ForeignIntervention, ForeignState,
                       InterpreterBroker, Organization, OrganizationKind, Patrol,
                       SecurityPost, SupplySource, clamp, logistic)
from .logistics import _add_command_edge, create_movement_order
from .timebase import reference_probability, reference_scale
from .entities import RelationStatus
from .relations import ensure_relation, set_relation


SUPPORT_COMPONENTS = ("financial", "political", "material", "training",
                      "organizational", "diplomatic", "sanctuary", "direct")


def _record_transfer(world, time, kind, source, destination, amount, border, event_id):
    if amount <= 0:
        return
    world.external_transfers.append(ExternalTransfer(
        f"XT{len(world.external_transfers)+1:09d}", time, kind, source,
        destination, amount, border, event_id))


def initialize_foreign_system(world) -> None:
    rng = __import__("pineland_sim.world", fromlist=["seeded_initialization_rng"]).seeded_initialization_rng(
        world.config, "foreign-system-generation")
    count = world.config.foreign_affairs.neighbor_count
    patterns = ("FS", "AR", "VE", "TA", "FS/AR", "VE/TA")
    districts = sorted(world.districts.values(), key=lambda d: d.district_id)
    for index in range(count):
        sid = f"neighbor-{index+1}"
        primary = patterns[index]
        profile = {language: (.85 if language in primary else .12) for language in ("FS", "AR", "VE", "TA")}
        state = ForeignState(
            sid, f"Neighbor State {index+1}", rng.uniform(600_000, 1_800_000),
            rng.uniform(.3, .9), rng.uniform(-.7, .9), rng.uniform(-.8, .8),
            rng.uniform(.35, .9), rng.uniform(.25, .85), rng.uniform(.2, .8),
            rng.uniform(.2, .85), rng.uniform(.3, .85), rng.uniform(.15, .65),
            rng.uniform(.35, .8), profile, rng.uniform(.4, .9))
        world.foreign_states[sid] = state
    ids = sorted(world.foreign_states)
    for index, sid in enumerate(ids):
        world.foreign_states[sid].rival_ids.add(ids[(index + 1) % len(ids)])
    for index, district in enumerate(districts):
        state = world.foreign_states[ids[index % len(ids)]]
        locality_id = max(district.locality_ids,
                          key=lambda lid: world.localities[lid].terrain_friction)
        locality = world.localities[locality_id]
        overlap = max(state.language_profile.get(lang, 0) for lang in district.language_pattern.split("/"))
        border = BorderSegment(
            f"B-{district.district_id}-{state.state_id}", state.state_id,
            district.district_id, locality_id, locality.terrain_friction,
            locality.infrastructure, rng.uniform(.15, .8), rng.uniform(.25, .95),
            overlap, rng.uniform(.2, .85), rng.uniform(.25, .85))
        world.border_segments[border.border_id] = border
        world.foreign_beliefs[(state.state_id, locality_id)] = ForeignBelief(
            state.state_id, locality_id, .5, .2, .12, 0.0)
    # When sampled, a socially connected resident anchors the interpreter
    # channel for attribution.  The substantive interpretation capability is
    # border/locality-level and is computed below from represented language
    # and social overlap, so absence of a sampled resident does not erase it.
    for border in world.border_segments.values():
        candidates = [p for p in world.persons.values() if p.residence_locality_id == border.locality_id]
        candidates.sort(key=lambda p: (-len(world.social_neighbors.get(p.person_id, ())), p.person_id))
        if not candidates:
            continue
        person = candidates[0]
        state = world.foreign_states[border.foreign_state_id]
        foreign_language = max(sum(person.languages.get(k, 0) * v for k, v in state.language_profile.items()), .05)
        broker = InterpreterBroker(
            f"INT-{border.border_id}", person.person_id, state.state_id, border.locality_id,
            clamp(foreign_language), max(person.languages.values()), .55,
            clamp(.35 + .5 * person.trust.get("government", .5)),
            clamp(.35 + len(world.social_neighbors.get(person.person_id, ())) / 25))
        world.interpreter_brokers[broker.interpreter_id] = broker


def interpreter_channel_capacity(world, border: BorderSegment) -> float:
    """Resolution-invariant represented interpretation/brokerage capacity."""
    locality = world.localities[border.locality_id]
    if locality.population <= 0:
        return 0.0
    social_access = (
        .45 + .35 * clamp(border.social_permeability) +
        .20 * clamp(border.kinship_overlap)
    )
    return clamp(border.language_overlap * social_access)


def _interpreter_channel_quality(world, border: BorderSegment) -> float:
    """Effective channel quality with optional sampled broker anchoring.

    The demographic baseline exists whenever the represented border population
    has language/social overlap.  A sampled broker can improve that quality,
    but its absence cannot switch the channel off solely because of population
    resolution.
    """
    capacity = interpreter_channel_capacity(world, border)
    if capacity <= 0:
        return 0.0
    demographic_quality = clamp(
        .35 + .35 * border.social_permeability + .30 * border.kinship_overlap
    )
    brokers = [
        broker for broker in world.interpreter_brokers.values()
        if broker.foreign_state_id == border.foreign_state_id
        and broker.locality_id == border.locality_id
    ]
    broker_quality = max(
        (
            broker.foreign_language * broker.local_language *
            broker.foreign_trust * broker.local_trust *
            broker.cultural_knowledge
            for broker in brokers
        ),
        default=0.0,
    )
    return clamp(capacity * max(demographic_quality, broker_quality))


def _best_border(world, state_id):
    return max((b for b in world.border_segments.values() if b.foreign_state_id == state_id),
               key=lambda b: b.social_permeability * b.language_overlap /
               max(.2, b.terrain_friction))


def _return_probability(world, person, state: ForeignState,
                        interval_days: float | None = None) -> float:
    """Actor-facing return hazard based on the migrant's home-security belief."""
    cfg = world.config.foreign_affairs
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    perceived_home_security = world.belief_view().expected_destination_control(
        person.person_id, person.home_locality_id, "government"
    )
    safety_gain = (1 - perceived_home_security) - (1 - state.opportunity) * .2
    reference_hazard = clamp(
        cfg.return_rate * logistic(-2 * safety_gain + person.state_legitimacy)
    )
    return reference_probability(reference_hazard, interval_days, 30.0)


def process_cross_border_mobility(world, time: float, rng: random.Random,
                                  interval_days: float | None = None) -> tuple[float, float]:
    """Move representative cohorts and return represented departure/return mass."""
    cfg = world.config.foreign_affairs
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("foreign-affairs interval_days must be positive")
    departures = returns = 0.0
    for person in world.persons.values():
        if person.external_state_id is not None:
            state = world.foreign_states[person.external_state_id]
            if rng.random() < _return_probability(
                world, person, state, interval_days=interval_days
            ):
                person.external_state_id = None
                person.migration_status = "returned"
                person.origin_tie_strength = clamp(person.origin_tie_strength + .15)
                returns += person.weight
            else:
                person.origin_tie_strength *= exp(-.02 * interval_days / 30)
                link = world.diaspora_links.get(f"DL-{person.person_id}")
                if link:
                    link.social_strength = person.origin_tie_strength
            continue
        borders = [b for b in world.border_segments.values()
                   if b.district_id == world.localities[person.residence_locality_id].district_id]
        if not borders:
            continue
        border = max(borders, key=lambda b: b.social_permeability)
        state = world.foreign_states[border.foreign_state_id]
        locality = world.localities[person.residence_locality_id]
        pressure = locality.violence + person.fear + .4 * (1 - person.government_legitimacy)
        attraction = (state.opportunity + border.kinship_overlap + border.language_overlap -
                      border.terrain_friction * (1 - border.legal_permeability))
        reference_hazard = clamp(
            cfg.migration_rate * logistic(pressure + attraction - 1.6)
        )
        hazard = reference_probability(reference_hazard, interval_days, 30.0)
        if rng.random() < hazard:
            person.external_state_id = state.state_id
            person.migration_status = ("refuge" if locality.violence > .25 else
                                       "temporary_flight" if person.fear > .55 else "economic_migration")
            person.origin_tie_strength = 1.0
            link = DiasporaLink(f"DL-{person.person_id}", person.person_id, state.state_id,
                                person.home_locality_id, 1.0, person.resources * .2,
                                clamp(.35 + .5 * border.language_overlap), time)
            world.diaspora_links[link.link_id] = link
            departures += person.weight
    return departures, returns


def _support_recipient(world, state: ForeignState,
                       active_insurgents: list[Organization]) -> str:
    """Choose support from foreign-state alignment and its own transfer record."""
    if state.government_alignment >= state.ideological_alignment or not active_insurgents:
        return "government"
    prior_support: dict[str, float] = {o.organization_id: 0.0 for o in active_insurgents}
    for support in world.external_support:
        if (support.foreign_state_id == state.state_id and
                support.recipient_id in prior_support):
            prior_support[support.recipient_id] += support.total()
    return min(
        active_insurgents,
        key=lambda o: (-prior_support[o.organization_id], o.organization_id),
    ).organization_id


def process_diaspora(world, time: float, event_id: str, rng: random.Random,
                     interval_days: float | None = None) -> tuple[float, int]:
    cfg = world.config.foreign_affairs
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days <= 0:
        raise ValueError("foreign-affairs interval_days must be positive")
    cycle_scale = reference_scale(interval_days, 30.0)
    remittances = 0.0
    messages = 0
    for link in world.diaspora_links.values():
        person = world.persons[link.person_id]
        if person.external_state_id is None:
            continue
        state = world.foreign_states[link.foreign_state_id]
        amount = min(
            state.resources,
            link.financial_capacity * cfg.diaspora_remittance_rate *
            link.social_strength * cycle_scale,
        )
        state.resources -= amount
        world.adjust_person_resources(person.person_id, amount)
        remittances += amount
        world.cumulative_external_remittances += amount
        _record_transfer(world, time, "diaspora_remittance", state.state_id,
                         person.person_id, amount, _best_border(world, state.state_id).border_id, event_id)
        message_probability = reference_probability(
            clamp(cfg.diaspora_information_rate * link.information_reliability),
            interval_days,
            30.0,
        )
        if rng.random() < message_probability:
            person.social_exposure["government"] = clamp(
                person.social_exposure.get("government", 0) + .05 * link.social_strength)
            messages += 1
    return remittances, messages


def _foreign_belief_update(world, state: ForeignState, time: float, rng: random.Random) -> None:
    cfg = world.config.foreign_affairs
    for border in (b for b in world.border_segments.values() if b.foreign_state_id == state.state_id):
        interpreter_quality = _interpreter_channel_quality(world, border)
        # Foreign actors consume the host's imperfect belief, never true control.
        host_estimate = world.belief_view("government").locality_control(
            border.locality_id, "government", "government").physical
        noise = cfg.belief_noise * (1 - cfg.interpreter_effect * interpreter_quality)
        belief = world.foreign_beliefs.setdefault((state.state_id, border.locality_id),
                                                   ForeignBelief(state.state_id, border.locality_id, .5, .2, 0, time))
        belief.government_control_estimate = clamp(host_estimate + rng.normalvariate(0, noise))
        belief.insurgent_presence_estimate = clamp(1 - belief.government_control_estimate +
                                                   rng.normalvariate(0, noise))
        belief.confidence = clamp(.2 + .45 * interpreter_quality + .2 * border.language_overlap)
        belief.updated_at = time


def deliver_support(world, state: ForeignState, recipient_id: str, time: float,
                    event_id: str, rng: random.Random, total: float | None = None) -> ExternalSupport:
    cfg = world.config.foreign_affairs
    total = min(state.resources, total if total is not None else state.resources * cfg.support_budget_fraction * state.willingness)
    if total <= 0:
        return ExternalSupport("", time, state.state_id, recipient_id,
                               {key: 0.0 for key in SUPPORT_COMPONENTS}, 0.0, False)
    state.resources -= total
    weights = {
        "financial": .22, "political": .08, "material": .19, "training": .14,
        "organizational": .10, "diplomatic": .07, "sanctuary": .12, "direct": .08,
    }
    components = {key: total * value for key, value in weights.items()}
    support = ExternalSupport(f"ES{len(world.external_support)+1:08d}", time, state.state_id,
                              recipient_id, components,
                              state.government_alignment if recipient_id == "government" else state.ideological_alignment)
    world.external_support.append(support)
    recipient = world.organizations[recipient_id]
    recipient.resources += components["financial"]
    if recipient_id == "government":
        institutions = list(world.political_institutions.values())
        learning = components["training"] + components["organizational"]
        for institution in institutions:
            institution.capacity = clamp(institution.capacity +
                                         learning / max(1, total) * .02 / max(1, len(institutions)))
        for person in world.persons.values():
            person.government_legitimacy = clamp(
                person.government_legitimacy + components["political"] /
                max(1, total) * .002 * (person.trust.get("government", .5) - .35))
    if recipient.kind is OrganizationKind.INSURGENT:
        recipient.external_sanctuary = clamp(recipient.external_sanctuary + components["sanctuary"] / max(1, total))
        if components["sanctuary"] > 0:
            recipient.sponsor_links[state.state_id] = 1.0
        recipient.capital["organizational"] = clamp(recipient.capital["organizational"] + components["organizational"] / max(1, total) * .08)
        recipient.phenotype["resource_dependence"] = clamp(recipient.phenotype["resource_dependence"] + .04)
        recipient.sponsor_dependence[state.state_id] = clamp(
            recipient.sponsor_dependence.get(state.state_id, 0) + total / max(1, recipient.resources + total))
    formations = [f for f in world.formations.values() if f.organization_id == recipient_id]
    for formation in formations:
        formation.quality = clamp(formation.quality + components["training"] / max(1, total) * .025)
        formation.cohesion = clamp(formation.cohesion + components["training"] / max(1, total) * .015)
        material = components["material"] / max(1, len(formations))
        accepted = min(material, formation.supply_capacity - formation.supply_stock)
        formation.supply_stock += accepted
        world.cumulative_supply_produced += accepted
    for component, amount in components.items():
        _record_transfer(world, time, f"external_{component}", state.state_id,
                         recipient_id, amount, _best_border(world, state.state_id).border_id, event_id)
    state.cumulative_cost += total
    return support


def begin_intervention(world, state: ForeignState, time: float, mode: str,
                       transfer_efficiency: float, crowding_out: float) -> ForeignIntervention:
    before_stocks = world.tracked_stock_totals()
    iid = f"FI{len(world.foreign_interventions)+1:05d}"
    intervention = ForeignIntervention(iid, state.state_id, "government", time, mode,
                                       0.0, transfer_efficiency, crowding_out)
    world.foreign_interventions[iid] = intervention
    oid = f"foreign-{state.state_id}"
    if oid not in world.organizations:
        world.organizations[oid] = Organization(
            oid, f"{state.name} Expeditionary Command", OrganizationKind.FOREIGN,
            state.resources * .02, .72, .75, .5, .15, .65, .7, .7)
        # A deployed expeditionary command is explicitly aligned with its
        # intervention recipient; FOREIGN as a taxonomic kind is not itself a
        # synonym for government-side allegiance.
        for ally_id in ("government", "fdf", "police"):
            if ally_id in world.organizations:
                set_relation(
                    world, oid, ally_id, RelationStatus.ALLIED, time,
                    cooperation_memory=1.0,
                )
        for organization in world.organizations.values():
            if (
                organization.kind is OrganizationKind.INSURGENT
                and organization.status == "active"
            ):
                set_relation(
                    world, oid, organization.organization_id,
                    RelationStatus.HOSTILE, time, hostility_memory=1.0,
                )
        for other_id in world.organizations:
            if other_id != oid:
                ensure_relation(world, oid, other_id, time)
    border = _best_border(world, state.state_id)
    fid = f"{oid.upper()}-01"
    if fid not in world.formations:
        personnel = 900.0
        formation = ArmedFormation(fid, oid, border.locality_id, personnel, .78, .76, .82,
                                   .9, .38, .72, .68, .12, external_state_id=state.state_id)
        formation.supply_capacity = personnel * world.config.logistics.formation_supply_days
        formation.supply_stock = formation.supply_capacity * .75
        # Runtime intervention materiel is an external inflow, not a rewrite
        # of the generated baseline stock.
        world.cumulative_supply_produced += formation.supply_stock
        world.formations[fid] = formation
        _add_command_edge(world, f"CMD:{oid}", fid, oid, .7, 7.0)
        sid = f"SUP-{oid}"
        world.supply_sources[sid] = SupplySource(sid, oid, border.locality_id,
                                                 12000, 18000, 350)
        world.cumulative_supply_produced += 12000
        zone = max((z for z in world.microzones.values() if z.locality_id == border.locality_id),
                   key=lambda z: z.population_share)
        pid = f"PATROL-{fid}"
        world.patrols[pid] = Patrol(pid, fid, oid, border.locality_id,
                                   zone.microzone_id, [zone.microzone_id], time, .35)
        postid = f"POST-{fid}"
        world.security_posts[postid] = SecurityPost(postid, oid, border.locality_id,
                                                    zone.microzone_id, personnel*.15, .2, .7, fid)
        world.security_post_ids_by_locality.setdefault(border.locality_id, []).append(postid)
        intervention.force_formation_ids.add(fid)
    # Intervention creation is an explicit external inflow even when invoked
    # directly by an experiment rather than through the scheduler.
    if world.active_event_id is None:
        world.record_stock_transactions(
            f"FOREIGN-{iid}", "foreign_affairs", before_stocks,
            world.tracked_stock_totals(),
        )
    return intervention


def dependence_metrics(world) -> dict[str, float]:
    foreign_capacity = sum(i.provided_capacity for i in world.foreign_interventions.values()
                           if i.status in {"active", "withdrawing"})
    host_capacity = sum(i.capacity for i in world.political_institutions.values()
                        if i.level in {"district", "municipal"})
    dependence = foreign_capacity / max(1e-9, foreign_capacity + host_capacity)
    active = [i for i in world.foreign_interventions.values() if i.status == "withdrawing"]
    withdrawal_speed = sum(i.withdrawal_rate for i in active) / max(1, len(active))
    absorption = host_capacity / max(1.0, len(world.localities))
    return {"foreign_capacity": foreign_capacity, "host_capacity": host_capacity,
            "dependence": dependence, "withdrawal_speed": withdrawal_speed,
            "absorption_capacity": clamp(absorption),
            "withdrawal_shock": dependence * withdrawal_speed * (1 - clamp(absorption))}


def process_foreign_affairs(world, time: float, event_id: str, rng: random.Random,
                            interval_days: float | None = None) -> dict:
    cfg = world.config.foreign_affairs
    if not cfg.enabled:
        return {"support": 0, "departures": 0, "returns": 0}
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days < 0:
        raise ValueError("foreign-affairs interval_days cannot be negative")
    if interval_days == 0:
        return {
            "support": 0, "departures": 0.0, "returns": 0.0,
            "remittances": 0.0, "messages": 0, "interventions": 0,
            "withdrawals": 0,
        }
    cycle_scale = reference_scale(interval_days, 30.0)
    departures, returns = process_cross_border_mobility(
        world, time, rng, interval_days=interval_days
    )
    remittances, messages = process_diaspora(
        world, time, event_id, rng, interval_days=interval_days
    )
    active_insurgents = [o for o in world.organizations.values()
                         if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
    support_count = interventions = withdrawals = 0
    active_foreign = {i.foreign_state_id for i in world.foreign_interventions.values() if i.status == "active"}
    for state in world.foreign_states.values():
        _foreign_belief_update(world, state, time, rng)
        rival_presence = sum(rival in active_foreign for rival in state.rival_ids)
        perceived_progress = sum(b.government_control_estimate for (sid, _), b in world.foreign_beliefs.items()
                                 if sid == state.state_id) / max(1, sum(sid == state.state_id for sid, _ in world.foreign_beliefs))
        cost_pressure = state.cumulative_cost / max(1, state.resources + state.cumulative_cost)
        state.willingness = clamp(logistic(1.2 * state.stability_preference + state.regional_influence +
                                           cfg.rival_reaction * rival_presence + perceived_progress -
                                           cfg.willingness_cost_weight * cost_pressure -
                                           cfg.willingness_casualty_weight * state.cumulative_casualties / 100 -
                                           state.domestic_opposition - 1.0))
        recipient = _support_recipient(world, state, active_insurgents)
        support_probability = reference_probability(
            clamp(state.willingness * .3), interval_days, 30.0
        )
        if cfg.support_budget_fraction > 0 and rng.random() < support_probability:
            support = deliver_support(world, state, recipient, time, event_id, rng)
            support_count += int(support.delivered)
        intervention_probability = reference_probability(
            clamp(
                cfg.intervention_base_hazard * state.willingness *
                (1 + cfg.rival_reaction * rival_presence)
            ),
            interval_days,
            30.0,
        )
        if (state.state_id not in active_foreign and
                rng.random() < intervention_probability):
            begin_intervention(world, state, time, "capacity_building" if state.humanitarian_preference > .5 else "substitution",
                               cfg.host_transfer_efficiency, cfg.host_crowding_out)
            interventions += 1
    for intervention in world.foreign_interventions.values():
        if intervention.status == "active":
            contribution = sum(world.formations[fid].effective_strength() for fid in intervention.force_formation_ids
                               if fid in world.formations) / 25
            intervention.provided_capacity = contribution
            intervention.peak_provided_capacity = max(intervention.peak_provided_capacity, contribution)
            local = [i for i in world.political_institutions.values() if i.level in {"district", "municipal"}]
            for institution in local:
                transfer_gain = (.002 * intervention.transfer_efficiency * contribution /
                                 max(1, len(local)) * cycle_scale)
                crowding_loss = (.002 * intervention.crowding_out * contribution /
                                  max(1, len(local)) * cycle_scale)
                institution.capacity = clamp(institution.capacity + transfer_gain - crowding_loss)
                intervention.cumulative_retained_host_capacity += transfer_gain
                intervention.cumulative_crowding_out += crowding_loss
            intervention.cumulative_transferred_capacity += (
                contribution * intervention.transfer_efficiency * cycle_scale
            )
            formations = [world.formations[fid] for fid in intervention.force_formation_ids
                          if fid in world.formations]
            for formation in formations:
                locality = world.localities[formation.locality_id]
                for person in world.persons.values():
                    if person.residence_locality_id != locality.locality_id:
                        continue
                    language_affinity = max(person.languages.values())
                    foreignness = (1 - person.identities.get("federal", .5)) * (1 - language_affinity)
                    benefit = contribution / max(1.0, locality.population * .001)
                    harm = formation.cumulative_losses / max(1.0, formation.personnel)
                    person.government_legitimacy = clamp(
                        person.government_legitimacy + cycle_scale * (
                            .006 * benefit * person.trust.get("government", .5) -
                            .004 * foreignness - .008 * harm
                        ))
            state = world.foreign_states[intervention.foreign_state_id]
            state.cumulative_casualties = sum(world.formations[fid].cumulative_losses
                                              for fid in intervention.force_formation_ids if fid in world.formations)
            if state.willingness < cfg.withdrawal_threshold:
                intervention.status = "withdrawing"
                intervention.withdrawal_rate = cfg.withdrawal_rate
        if intervention.status == "withdrawing":
            border = _best_border(world, intervention.foreign_state_id)
            for fid in intervention.force_formation_ids:
                formation = world.formations[fid]
                active_order = any(o.formation_id == fid and o.status in {"pending", "moving"}
                                   for o in world.movement_orders.values())
                if formation.locality_id != border.locality_id and not active_order:
                    create_movement_order(world, fid, border.locality_id, time, rng)
                elif formation.locality_id == border.locality_id and not formation.moving:
                    formation.outside_pineland = True
                    formation.availability = 0
            if all(world.formations[fid].outside_pineland for fid in intervention.force_formation_ids):
                intervention.withdrawn_capacity = intervention.provided_capacity
                intervention.status = "withdrawn"
                intervention.provided_capacity = 0
                withdrawals += 1
    return {"support": support_count, "interventions": interventions,
            "withdrawals": withdrawals, "departures": departures, "returns": returns,
            "remittances": remittances, "diaspora_messages": messages,
            **dependence_metrics(world)}


def foreign_diagnostics(world) -> dict:
    metrics = dependence_metrics(world)
    active = sum(i.status == "active" for i in world.foreign_interventions.values())
    rival_induced = sum(bool(world.foreign_states[i.foreign_state_id].rival_ids &
                             {j.foreign_state_id for j in world.foreign_interventions.values()
                              if j.started_at <= i.started_at and j.intervention_id != i.intervention_id})
                        for i in world.foreign_interventions.values())
    interventions = list(world.foreign_interventions.values())
    gross_transfer = sum(i.cumulative_transferred_capacity for i in interventions)
    retained = sum(i.cumulative_retained_host_capacity for i in interventions)
    crowding = sum(i.cumulative_crowding_out for i in interventions)
    withdrawn = sum(i.withdrawn_capacity for i in interventions)
    return {**metrics, "foreign_states": len(world.foreign_states),
            "border_segments": len(world.border_segments), "active_interventions": active,
            "external_support_events": sum(
                support.time >= 0 for support in world.external_support
            ),
            "external_transfers": len(world.external_transfers),
            "diaspora_links": len(world.diaspora_links),
            "externalization_reproduction": rival_induced / max(1, len(world.foreign_interventions)),
            "capacity_decomposition": {
                "gross_transferred_capacity": gross_transfer,
                "retained_host_capacity": retained,
                "crowding_out_capacity": crowding,
                "net_host_capacity_change": retained - crowding,
                "withdrawn_capacity": withdrawn,
                "active_peak_capacity": sum(i.peak_provided_capacity for i in interventions),
                "retention_ratio": retained / max(1e-9, gross_transfer),
                "substitution_ratio": crowding / max(1e-9, gross_transfer),
                "withdrawal_ratio": withdrawn / max(1e-9, sum(i.peak_provided_capacity for i in interventions)),
            },
            "beliefs": {f"{sid}:{lid}": {"government_control": b.government_control_estimate,
                                           "insurgent_presence": b.insurgent_presence_estimate,
                                           "confidence": b.confidence}
                        for (sid, lid), b in world.foreign_beliefs.items()}}


def run_intervention_comparison(world, years: int = 10, withdrawal_year: int = 8) -> dict:
    """Controlled A/B/C comparison with equal initial foreign force resources."""
    import copy
    results = {}
    for label, mode, transfer, crowding in (
            ("A_no_intervention", None, 0.0, 0.0),
            ("B_substitution", "substitution", .05, .80),
            ("C_capacity_building", "capacity_building", .80, .05)):
        trial = copy.deepcopy(world)
        trial.config.foreign_affairs.intervention_base_hazard = 0
        trial.config.foreign_affairs.support_budget_fraction = 0
        trial.config.foreign_affairs.migration_rate = 0
        state = trial.foreign_states[sorted(trial.foreign_states)[0]]
        intervention = (begin_intervention(trial, state, 0, mode, transfer, crowding)
                        if mode else None)
        rng = random.Random(8675309)
        trajectory = []
        withdrawal_shock_peak = 0.0
        for month in range(years * 12 + 1):
            if intervention and month == withdrawal_year * 12:
                intervention.status = "withdrawing"
                intervention.withdrawal_rate = trial.config.foreign_affairs.withdrawal_rate
                withdrawal_shock_peak = dependence_metrics(trial)["withdrawal_shock"]
            process_foreign_affairs(trial, month * 30.0, f"X-{label}-{month}", rng)
            if month % 12 == 0:
                metrics = dependence_metrics(trial)
                intervention_metrics = {
                    "gross_transferred_capacity": intervention.cumulative_transferred_capacity if intervention else 0.0,
                    "retained_host_capacity": intervention.cumulative_retained_host_capacity if intervention else 0.0,
                    "crowding_out_capacity": intervention.cumulative_crowding_out if intervention else 0.0,
                    "withdrawn_capacity": intervention.withdrawn_capacity if intervention else 0.0,
                }
                trajectory.append({"year": month // 12,
                                   "host_capacity": metrics["host_capacity"],
                                   "foreign_capacity": metrics["foreign_capacity"],
                                   "dependence": metrics["dependence"],
                                   "withdrawal_shock": metrics["withdrawal_shock"],
                                   **intervention_metrics})
        results[label] = {"trajectory": trajectory, "final": trajectory[-1],
                          "withdrawal_shock_peak": withdrawal_shock_peak,
                          "pre_withdrawal": trajectory[min(max(0, withdrawal_year-1), len(trajectory)-1)]}
    return results
