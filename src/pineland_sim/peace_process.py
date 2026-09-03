"""Endogenous bargaining, settlement implementation, DDR, and recurrence."""
from __future__ import annotations

from math import exp
import random

from .entities import (AgreementProvision, Organization, OrganizationKind, PartyBranch,
                       PeaceAgreement, PeaceTransition, Negotiation, clamp, logistic)


PROVISION_TYPES = ("ceasefire", "security_reform", "political_incorporation",
                   "power_sharing", "demobilization", "grievance_redress")


def _armed_strength(world, organization_id: str) -> float:
    return sum(f.effective_strength() for f in world.formations.values()
               if f.organization_id == organization_id and not f.outside_pineland)


def _fragmentation(world, insurgents) -> float:
    if not insurgents:
        return 0.0
    total = sum(max(1.0, _armed_strength(world, o.organization_id)) for o in insurgents)
    largest = max(max(1.0, _armed_strength(world, o.organization_id)) for o in insurgents)
    structural = 1 - largest / total
    internal = sum((1 - o.cohesion) + .5 * (1 - o.phenotype["centralization"])
                   for o in insurgents) / (1.5 * len(insurgents))
    return clamp(.65 * structural + .35 * internal)


def bargaining_values(world, insurgents=None) -> dict[str, dict[str, float]]:
    insurgents = insurgents or [o for o in world.organizations.values()
                                if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
    government = world.organizations["government"]
    g_strength = _armed_strength(world, "fdf") + _armed_strength(world, "police")
    i_strength = sum(_armed_strength(world, o.organization_id) for o in insurgents)
    total = max(1.0, g_strength + i_strength)
    violence = sum(l.violence for l in world.localities.values()) / max(1, len(world.localities))
    control = sum(l.control["government"].effective() for l in world.localities.values()) / max(1, len(world.localities))
    foreign_pressure = sum(s.willingness * s.humanitarian_preference for s in world.foreign_states.values()) / max(1, len(world.foreign_states))
    result = {}
    g_future = g_strength / total
    g_war = clamp(.35 + .45 * g_future + .2 * control - .3 * violence)
    g_peace = clamp(.56 + .14 * control + .08 * foreign_pressure)
    result[government.organization_id] = {"war": g_war, "peace": g_peace,
                                          "surplus": g_peace - g_war,
                                          "future_power": g_future}
    for org in insurgents:
        strength = _armed_strength(world, org.organization_id)
        future = strength / total
        grievance = sum(world.persons[p].grievance * world.persons[p].weight for p in org.member_ids
                        if p in world.persons) / max(1.0, sum(world.persons[p].weight for p in org.member_ids
                                                            if p in world.persons))
        concessions = .42 + .24 * org.capital["political"] + .15 * grievance
        war = clamp(.18 + .62 * future + .14 * org.external_sanctuary - .18 * violence)
        risk = .20 * (1 - government.accountability) + .15 * (1 - org.cohesion)
        peace = clamp(concessions - risk + .08 * foreign_pressure)
        result[org.organization_id] = {"war": war, "peace": peace,
                                       "surplus": peace - war, "future_power": future}
    return result


def initiate_negotiation(world, time: float, insurgents=None) -> Negotiation:
    insurgents = insurgents or [o for o in world.organizations.values()
                                if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
    values = bargaining_values(world, insurgents)
    fragmentation = _fragmentation(world, insurgents)
    mediators = tuple(sorted(s.state_id for s in world.foreign_states.values()
                             if s.humanitarian_preference > .58 and s.willingness > .35))
    monitoring = min(1.0, .12 * len(mediators))
    credibility = clamp(.35 + .28 * world.organizations["government"].accountability +
                        .18 * sum(o.discipline for o in insurgents) / max(1, len(insurgents)) + monitoring -
                        .22 * fragmentation)
    nid = f"NEG{len(world.negotiations)+1:06d}"
    actors = ("government", *(o.organization_id for o in insurgents))
    item = Negotiation(nid, "government", tuple(o.organization_id for o in insurgents), time,
                       {a: values[a]["war"] for a in actors},
                       {a: values[a]["peace"] for a in actors},
                       {a: values[a]["surplus"] for a in actors}, credibility,
                       fragmentation, mediators)
    world.negotiations[nid] = item
    world.peace_transitions.append(PeaceTransition(
        f"PX{len(world.peace_transitions)+1:07d}", time, "negotiation_initiated", None,
        actors, causes={"credibility": credibility, "fragmentation": fragmentation}))
    return item


def sign_agreement(world, negotiation: Negotiation, time: float, rng: random.Random) -> PeaceAgreement:
    cfg = world.config.peace_process
    accepted, rejected = [], []
    for oid in negotiation.insurgent_ids:
        org = world.organizations[oid]
        sponsor_pressure = sum(org.sponsor_dependence.get(sid, 0) *
                               (world.foreign_states[sid].humanitarian_preference - .5)
                               for sid in org.sponsor_dependence if sid in world.foreign_states)
        consent = logistic(4 * negotiation.bargaining_surplus.get(oid, 0) +
                           1.3 * negotiation.credibility + sponsor_pressure -
                           1.4 * (1 - org.cohesion) - org.phenotype["risk_tolerance"])
        (accepted if rng.random() < consent else rejected).append(oid)
    if not accepted:
        accepted.append(max(negotiation.insurgent_ids,
                            key=lambda x: negotiation.bargaining_surplus.get(x, -1)))
        rejected = [x for x in negotiation.insurgent_ids if x not in accepted]
    aid = f"AGR{len(world.peace_agreements)+1:06d}"
    provision_ids = []
    monitor = clamp(.2 + .14 * len(negotiation.foreign_mediator_ids))
    for kind in PROVISION_TYPES:
        pid = f"{aid}-{kind}"
        provision = AgreementProvision(pid, aid, kind, 1.0, 0.0,
            clamp(.48 + .35 * negotiation.bargaining_surplus["government"]),
            clamp(.48 + .35 * sum(negotiation.bargaining_surplus[x] for x in accepted) / len(accepted)),
            .18 if kind in {"ceasefire", "demobilization"} else .34,
            monitor)
        world.agreement_provisions[pid] = provision
        provision_ids.append(pid)
    agreement = PeaceAgreement(aid, negotiation.negotiation_id, time, "government",
                               tuple(accepted), tuple(rejected), tuple(provision_ids),
                               negotiation.credibility, negotiation.foreign_mediator_ids)
    world.peace_agreements[aid] = agreement
    negotiation.status, negotiation.concluded_at = "agreement", time
    for oid in accepted:
        world.ceasefires[oid] = "active"
    world.peace_transitions.append(PeaceTransition(
        f"PX{len(world.peace_transitions)+1:07d}", time, "agreement_signed", aid,
        ("government", *accepted), causes={"rejecting_factions": len(rejected),
                                           "credibility": agreement.credibility}))
    return agreement


def _ensure_party(world, org: Organization, agreement: PeaceAgreement, time: float) -> Organization:
    party_id = f"party-{org.organization_id}"
    if party_id in world.organizations:
        return world.organizations[party_id]
    cfg = world.config.peace_process
    retained = cfg.political_capital_retention
    resources = org.resources * cfg.resource_conversion_rate
    org.resources -= resources
    party = Organization(party_id, f"{org.name} Political Movement", OrganizationKind.PARTY,
                         resources, org.cohesion, org.discipline, org.accountability,
                         org.local_knowledge, org.persistence, .2, org.institutional_quality,
                         capital={k: clamp(v * retained) for k, v in org.capital.items()},
                         ideology=dict(org.ideology), founded_at=time, parent_ids=(org.organization_id,))
    world.organizations[party_id] = party
    branch_allocation = resources / max(1, len(world.localities))
    for locality_id in world.localities:
        members = {pid for pid in org.member_ids if world.persons[pid].residence_locality_id == locality_id}
        party.member_ids.update(members)
        for pid in members:
            world.persons[pid].private_preference[party_id] = clamp(.55 + .35 * org.capital["political"])
            world.persons[pid].party_legitimacy[party_id] = clamp(.5 + .35 * org.capital["social"])
        bid = f"BR-{party_id}-{locality_id}"
        world.party_branches[bid] = PartyBranch(bid, party_id, locality_id, members,
                                               branch_allocation, 0,
                                               clamp(.15 + org.capital["political"] * retained),
                                               clamp(.08 + org.capital["organizational"] * retained))
        party.resources -= branch_allocation
    party.resources = max(0.0, party.resources)
    world.peace_transitions.append(PeaceTransition(
        f"PX{len(world.peace_transitions)+1:07d}", time, "political_transformation",
        agreement.agreement_id, (org.organization_id, party_id), resources=resources,
        causes={"capital_retention": retained}))
    return party


def _implement(world, agreement: PeaceAgreement, time: float, event_id: str,
               rng: random.Random) -> tuple[int, float]:
    cfg = world.config.peace_process
    signatories = [world.organizations[x] for x in agreement.signatory_ids]
    spoilers = len(agreement.rejecting_faction_ids) + sum(world.ceasefires.get(x) == "violated"
                                                          for x in agreement.signatory_ids)
    capacity = sum(i.capacity for i in world.political_institutions.values()) / max(1, len(world.political_institutions))
    completed = 0
    total_increment = 0.0
    for pid in agreement.provision_ids:
        p = world.agreement_provisions[pid]
        if p.status == "completed":
            completed += 1
            continue
        increment = cfg.implementation_rate * clamp(.35 * capacity + .25 * p.government_will +
                    .25 * p.insurgent_will + .3 * p.monitoring - .12 * spoilers -
                    .2 * p.institutional_resistance + rng.normalvariate(0, .025))
        p.progress = min(p.target, p.progress + increment)
        total_increment += increment
        p.status = "completed" if p.progress >= p.target - 1e-9 else ("implementing" if increment else "stalled")
        completed += p.status == "completed"
        if p.provision_type == "grievance_redress":
            for org in signatories:
                for person_id in org.member_ids:
                    world.persons[person_id].grievance = clamp(world.persons[person_id].grievance - .01 * increment)
    demob = world.agreement_provisions[f"{agreement.agreement_id}-demobilization"]
    political = world.agreement_provisions[f"{agreement.agreement_id}-political_incorporation"]
    if demob.progress > .15:
        for org in signatories:
            for formation in [f for f in world.formations.values() if f.organization_id == org.organization_id]:
                amount = min(formation.personnel, formation.personnel * cfg.demobilization_rate * demob.progress)
                arms = min(formation.supply_stock, amount * formation.supply_fraction())
                formation.personnel -= amount
                formation.supply_stock -= arms
                world.demobilized_personnel += amount
                world.demobilized_arms += arms
                if amount:
                    world.peace_transitions.append(PeaceTransition(
                        f"PX{len(world.peace_transitions)+1:07d}", time, "demobilization",
                        agreement.agreement_id, (org.organization_id,), amount, arms, 0,
                        {"provision_progress": demob.progress}))
            if political.progress > .2:
                _ensure_party(world, org, agreement, time)
    if completed == len(agreement.provision_ids):
        agreement.status, agreement.completed_at = "completed", time
        for org in signatories:
            org.status = "political"
            world.ceasefires[org.organization_id] = "settled"
    return completed, total_increment


def process_peace(world, time: float, event_id: str, rng: random.Random) -> dict:
    cfg = world.config.peace_process
    if not cfg.enabled:
        return {"initiated": 0, "signed": 0, "recurrences": 0}
    active = [o for o in world.organizations.values()
              if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
    initiated = signed = violations = recurrences = provisions_completed = 0
    implementation = 0.0
    if active and not any(n.status == "active" for n in world.negotiations.values()):
        values = bargaining_values(world, active)
        joint = min(values["government"]["surplus"],
                    max(values[o.organization_id]["surplus"] for o in active))
        hazard = cfg.negotiation_base_hazard * logistic(3.5 * joint + .8)
        if rng.random() < hazard:
            initiate_negotiation(world, time, active)
            initiated = 1
    for negotiation in [n for n in world.negotiations.values() if n.status == "active"]:
        joint = min(negotiation.bargaining_surplus.values())
        spoiler = negotiation.fragmentation
        foreign = .1 * len(negotiation.foreign_mediator_ids)
        hazard = cfg.agreement_base_hazard * logistic(2.8 * joint +
                 cfg.credibility_weight * negotiation.credibility -
                 cfg.fragmentation_penalty * negotiation.fragmentation -
                 cfg.spoiler_penalty * spoiler + cfg.foreign_influence_weight * foreign)
        if rng.random() < hazard:
            sign_agreement(world, negotiation, time, rng)
            signed += 1
    for agreement in [a for a in world.peace_agreements.values() if a.status in {"signed", "implementing"}]:
        agreement.status = "implementing"
        for oid in agreement.signatory_ids:
            org = world.organizations[oid]
            violation_hazard = cfg.ceasefire_violation_rate * (1 + agreement.rejecting_faction_ids.__len__()) * \
                               (1 - agreement.credibility) * (1 + org.phenotype["risk_tolerance"])
            if world.ceasefires.get(oid) == "active" and rng.random() < violation_hazard:
                world.ceasefires[oid] = "violated"
                violations += 1
                world.peace_transitions.append(PeaceTransition(
                    f"PX{len(world.peace_transitions)+1:07d}", time, "ceasefire_violation",
                    agreement.agreement_id, (oid,), causes={"hazard": violation_hazard}))
        complete, delta = _implement(world, agreement, time, event_id, rng)
        provisions_completed += complete
        implementation += delta
        unmet = sum(1 - world.agreement_provisions[p].progress for p in agreement.provision_ids) / len(agreement.provision_ids)
        power_shift = abs(bargaining_values(world).get("government", {"future_power": .5})["future_power"] - .5)
        recurrence_hazard = cfg.recurrence_base_hazard * exp(1.2 * unmet +
                            1.1 * len(agreement.rejecting_faction_ids) + .7 * power_shift +
                            .8 * sum(world.ceasefires.get(x) == "violated" for x in agreement.signatory_ids))
        if time - agreement.signed_at >= 365 and rng.random() < min(.95, recurrence_hazard):
            agreement.status, agreement.failed_at = "failed", time
            for oid in agreement.signatory_ids:
                org = world.organizations[oid]
                if org.status == "political":
                    org.status = "active"
                world.ceasefires[oid] = "recurrence"
            recurrences += 1
            world.peace_transitions.append(PeaceTransition(
                f"PX{len(world.peace_transitions)+1:07d}", time, "recurrence",
                agreement.agreement_id, agreement.signatory_ids,
                causes={"hazard": recurrence_hazard, "unimplemented_terms": unmet,
                        "power_shift": power_shift}))
    return {"initiated": initiated, "signed": signed, "violations": violations,
            "recurrences": recurrences, "provisions_completed": provisions_completed,
            "implementation_increment": implementation,
            "fragmentation": _fragmentation(world, active)}


def peace_diagnostics(world) -> dict:
    agreements = list(world.peace_agreements.values())
    provisions = list(world.agreement_provisions.values())
    return {
        "negotiations": len(world.negotiations), "agreements": len(agreements),
        "completed_agreements": sum(a.status == "completed" for a in agreements),
        "failed_agreements": sum(a.status == "failed" for a in agreements),
        "mean_implementation": sum(p.progress for p in provisions) / max(1, len(provisions)),
        "ceasefire_violations": sum(t.transition_type == "ceasefire_violation" for t in world.peace_transitions),
        "demobilized_personnel": world.demobilized_personnel,
        "demobilized_arms": world.demobilized_arms,
        "political_transformations": sum(t.transition_type == "political_transformation" for t in world.peace_transitions),
        "recurrences": sum(t.transition_type == "recurrence" for t in world.peace_transitions),
        "causal_events": len(world.peace_transitions),
    }


def run_fragmentation_comparison(world, replications: int = 100, years: int = 12,
                                 opportunity_year: int = 2) -> dict:
    """Matched-seed experiment; only organization fragmentation differs."""
    import copy
    from .organization_ecology import split_organization

    results = {}
    for label, fragmented in (("A_unified", False), ("B_fragmented", True)):
        outcomes = []
        for replication in range(replications):
            trial = copy.deepcopy(world)
            trial.config.organization_ecology.enabled = False
            trial.config.foreign_affairs.enabled = False
            trial.config.peace_process.negotiation_base_hazard = 0
            insurgent = trial.organizations["insurgent"]
            if fragmented:
                split_organization(trial, insurgent.organization_id, 0, random.Random(4411))
                children = [o for o in trial.organizations.values() if o.parent_ids == ("insurgent",)]
                # Equalize combined resources, demands, and formation personnel exactly.
                for child in children:
                    child.ideology = dict(insurgent.ideology)
            rng = random.Random(900000 + replication)
            signed_at = completed_at = recurrence_at = None
            for month in range(years * 12 + 1):
                time = month * 30.0
                if month == opportunity_year * 12:
                    active = [o for o in trial.organizations.values()
                              if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
                    negotiation = initiate_negotiation(trial, time, active)
                    # Common opportunity: positive mutual surplus and equal credibility.
                    negotiation.credibility = .62
                    negotiation.bargaining_surplus = {k: .16 for k in negotiation.bargaining_surplus}
                result = process_peace(trial, time, f"CMP-{replication}-{month}", rng)
                if signed_at is None and trial.peace_agreements:
                    signed_at = min(a.signed_at for a in trial.peace_agreements.values())
                completed = [a.completed_at for a in trial.peace_agreements.values() if a.completed_at is not None]
                failed = [a.failed_at for a in trial.peace_agreements.values() if a.failed_at is not None]
                if completed_at is None and completed:
                    completed_at = min(completed)
                if recurrence_at is None and failed:
                    recurrence_at = min(failed)
            agreements = list(trial.peace_agreements.values())
            implementation = sum(p.progress for p in trial.agreement_provisions.values()) / max(1, len(trial.agreement_provisions))
            outcomes.append({"agreement": bool(agreements),
                             "implementation": implementation,
                             "completed": completed_at is not None,
                             "recurrence": recurrence_at is not None,
                             "time_to_agreement_days": None if signed_at is None else signed_at-opportunity_year*365,
                             "peace_duration_days": None if signed_at is None else
                                 ((recurrence_at or years*365)-signed_at)})
        n = len(outcomes)
        agreed = [x for x in outcomes if x["agreement"]]
        peace = [x["peace_duration_days"] for x in outcomes if x["peace_duration_days"] is not None]
        times = [x["time_to_agreement_days"] for x in outcomes if x["time_to_agreement_days"] is not None]
        results[label] = {
            "replications": n, "agreement_probability": sum(x["agreement"] for x in outcomes)/n,
            "completion_probability": sum(x["completed"] for x in outcomes)/n,
            "recurrence_probability": sum(x["recurrence"] for x in outcomes)/n,
            "mean_implementation": sum(x["implementation"] for x in outcomes)/n,
            "mean_time_to_agreement_days": sum(times)/len(times) if times else None,
            "mean_peace_duration_days": sum(peace)/len(peace) if peace else None,
        }
    return results
