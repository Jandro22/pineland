"""Political institutions, parties, patronage, implementation, and elections."""
from __future__ import annotations

from math import exp
import random

from .entities import (CausalContribution, Election, LocalElite, PartyBranch,
                       PolicyImplementation, PoliticalInstitution, PoliticalTransfer,
                       clamp)
from .timebase import reference_scale


INSTITUTION_TYPES = ("executive", "legislature", "civil_administration",
                     "judiciary", "military", "police")
SERVICE_DIMENSIONS = ("security", "justice", "administration", "services", "representation")


def local_elite_access_capacity(world, locality_id: str) -> float:
    """Locality-level elite brokerage capability, independent of sampled anchors."""
    locality = world.localities[locality_id]
    default = 1.0 if locality.population > 0 else 0.0
    return clamp(locality.governance.get("elite_access_capacity", default))


def _transfer(world, time, kind, source, destination, locality, amount, purpose):
    if amount <= 0:
        return
    world.political_transfers.append(PoliticalTransfer(
        f"PT{len(world.political_transfers)+1:09d}", time, kind, source,
        destination, locality, amount, purpose))


def initialize_political_order(world) -> None:
    rng = __import__("pineland_sim.world", fromlist=["seeded_initialization_rng"]).seeded_initialization_rng(
        world.config, "political-order-generation")
    parties = sorted((o for o in world.organizations.values() if o.kind.value == "party"),
                     key=lambda o: o.organization_id)
    world.ruling_party_id = parties[0].organization_id if parties else None
    for kind in INSTITUTION_TYPES:
        iid = f"INST-FED-{kind.upper()}"
        base = .55 if kind not in {"military", "executive"} else .68
        world.political_institutions[iid] = PoliticalInstitution(
            iid, f"Federal {kind.replace('_', ' ').title()}", kind, "federal", None, None,
            clamp(base + rng.uniform(-.08, .08)), .25, .72, .72,
            clamp(.62 + rng.uniform(-.1, .1)), 0.0, world.ruling_party_id)
    for district in world.districts.values():
        iid = f"INST-{district.district_id}"
        world.political_institutions[iid] = PoliticalInstitution(
            iid, f"{district.name} Government", "district_government", "district", None,
            district.district_id, clamp(.35 + .4 * district.connectivity),
            rng.uniform(.45, .8), rng.uniform(.5, .9), district.connectivity,
            rng.uniform(.45, .8), 0.0, world.ruling_party_id)
    for locality in world.localities.values():
        # Elite brokerage is a represented local capability.  An explicit
        # LocalElite object below is only a sampled anchor for attribution and
        # transfer records; the channel must not disappear because a weighted
        # population draw happened to place no representative in this locality.
        locality.governance["elite_access_capacity"] = (
            1.0 if locality.population > 0 else 0.0
        )
        iid = f"INST-{locality.locality_id}"
        world.political_institutions[iid] = PoliticalInstitution(
            iid, f"{locality.name} Municipal Administration", "municipal_government",
            "municipal", locality.locality_id, locality.district_id,
            locality.administrative_capacity, rng.uniform(.35, .8), rng.uniform(.45, .9),
            clamp(.35 + .55 * locality.infrastructure), rng.uniform(.35, .8), 0.0,
            world.ruling_party_id)
        for party in parties:
            branch_id = f"BR-{party.organization_id}-{locality.locality_id}"
            world.party_branches[branch_id] = PartyBranch(
                branch_id, party.organization_id, locality.locality_id, set(), 0.0, 0.0,
                rng.uniform(.1, .5), rng.uniform(.05, .35))
    # Party affiliation overlaps social communities but is independent of armed membership.
    for person in world.persons.values():
        person.party_legitimacy = {party.organization_id: rng.uniform(.2, .75) for party in parties}
        person.state_legitimacy = clamp(.5 + .25 * person.trust.get("government", .5))
        person.government_legitimacy = clamp(.35 + .3 * person.trust.get("government", .5))
        person.political_access = clamp(.25 + .35 * person.efficacy)
        if parties and rng.random() < .28:
            party = max(parties, key=lambda item: person.private_preference.get(item.organization_id, 0))
            world.party_branches[f"BR-{party.organization_id}-{person.residence_locality_id}"].member_ids.add(person.person_id)
            party.member_ids.add(person.person_id)
    for locality in world.localities.values():
        candidates = sorted((p for p in world.persons.values() if p.residence_locality_id == locality.locality_id),
                            key=lambda p: (-len(world.social_neighbors.get(p.person_id, ())), p.person_id))
        # One sampled resident may anchor the aggregate brokerage capability.
        # Do not instantiate up to three pseudo-elites merely because a finer
        # representative resolution happened to provide more candidate nodes.
        for person in candidates[:1]:
            aligned = max(person.party_legitimacy, key=person.party_legitimacy.get) if person.party_legitimacy else None
            elite = LocalElite(f"EL-{locality.locality_id}-1", person.person_id,
                               locality.locality_id, "composite_brokerage",
                               clamp(len(world.social_neighbors.get(person.person_id, ())) / 20),
                               # Broker resources are an account for explicit
                               # political transfers, not a second copy of the
                               # linked person's civilian wealth.
                               0.0, rng.uniform(.35, .8), rng.uniform(.3, .85), aligned)
            world.local_elites[elite.elite_id] = elite
            if aligned:
                world.party_branches[f"BR-{aligned}-{locality.locality_id}"].broker_ids.add(elite.elite_id)


def _service_output(institution, public_spending, locality, cycle_scale: float = 1.0):
    if cycle_scale <= 0:
        scale = 0.0
    else:
        scale = (public_spending / cycle_scale) / max(
            1.0, locality.population * .05
        )
    production = clamp(institution.capacity * institution.reach * institution.compliance * scale)
    return {
        "security": production * (.8 + .2 * locality.infrastructure),
        "justice": production * institution.integrity,
        "administration": production * institution.capacity,
        "services": production * locality.infrastructure,
        "representation": production * (.5 + .5 * institution.autonomy),
    }


def process_political_order(world, time: float, event_id: str, rng: random.Random,
                            interval_days: float | None = None) -> dict:
    cfg = world.config.political_order
    if not cfg.enabled:
        return {"budget": 0.0, "implementations": 0, "election": False}
    interval_days = cfg.interval_days if interval_days is None else float(interval_days)
    if interval_days < 0:
        raise ValueError("political-order interval_days cannot be negative")
    cycle_scale = reference_scale(interval_days, 30.0)
    if interval_days == 0:
        election = False
        if not world.elections:
            run_election(world, time, rng)
            election = True
        return {
            "budget": 0.0, "public_spending": 0.0, "patronage": 0.0,
            "private_diversion": 0.0, "patronage_decay": 0.0,
            "implementations": 0, "election": election,
        }
    decay_factor = exp(-cfg.patronage_decay_rate * interval_days / 365.0)
    patronage_decay = 0.0
    for branch in world.party_branches.values():
        before = branch.patronage_stock
        branch.patronage_stock *= decay_factor
        patronage_decay += before - branch.patronage_stock
    government = world.organizations["government"]
    budget = min(government.resources, cfg.federal_policy_budget * cycle_scale)
    government.resources -= budget
    public_total = budget * cfg.public_budget_share
    patronage_total = budget * cfg.patronage_share
    private_total = budget * cfg.private_diversion_share
    world.private_diversion_stock += private_total
    _transfer(world, time, "diversion", "government", "private_diversion", None,
              private_total, "private_consumption")
    localities = list(world.localities.values())
    implementations = 0
    for locality in localities:
        institution = world.political_institutions[f"INST-{locality.locality_id}"]
        public = public_total / max(1, len(localities))
        patronage = patronage_total / max(1, len(localities))
        # Local autonomy and compliance create implementation gaps and distortion.
        compliance = clamp(institution.compliance + rng.normalvariate(0, .08) * institution.autonomy)
        effective_public = public * compliance
        distorted = public - effective_public
        patronage += distorted * .7
        private_local = distorted * .3
        world.private_diversion_stock += private_local
        _transfer(world, time, "budget", "government", institution.institution_id,
                  locality.locality_id, effective_public, "public_governance")
        institution.resources += effective_public
        if private_local:
            _transfer(world, time, "diversion", institution.institution_id, "private_diversion",
                      locality.locality_id, private_local, "implementation_leakage")
        ruling_branch = world.party_branches.get(
            f"BR-{world.ruling_party_id}-{locality.locality_id}") if world.ruling_party_id else None
        # Patronage reach is the local allocation reaching the ruling
        # coalition, including the share routed through explicit elite
        # brokers.  Using only the branch's residual stock made voter response
        # depend on how many sampled broker tokens happened to be instantiated.
        elite_access = local_elite_access_capacity(world, locality.locality_id)
        routed_patronage = patronage * (
            (1 - cfg.elite_broker_share) + cfg.elite_broker_share * elite_access
        )
        patronage_reach = (
            routed_patronage / cycle_scale /
            max(1, locality.population * .01)
        )
        if ruling_branch:
            ruling_branch.patronage_stock += patronage
            _transfer(world, time, "patronage", "government", ruling_branch.branch_id,
                      locality.locality_id, patronage, "coalition_maintenance")
            # broker_ids is a set.  Stable ordering is required so process
            # isolation/PYTHONHASHSEED cannot reassign otherwise identical
            # transfer IDs to different brokers.
            brokers = [world.local_elites[eid] for eid in sorted(ruling_branch.broker_ids)]
            broker_pool = patronage * cfg.elite_broker_share
            for elite in brokers:
                amount = broker_pool / max(1, len(brokers))
                elite.resources += amount
                ruling_branch.patronage_stock -= amount
                _transfer(world, time, "brokerage", ruling_branch.branch_id, elite.elite_id,
                          locality.locality_id, amount, "local_brokerage")
        output = _service_output(
            institution, effective_public, locality, cycle_scale=cycle_scale
        )
        institution.resources -= effective_public
        world.cumulative_public_spending += effective_public
        _transfer(world, time, "service_spending", institution.institution_id, "public_services",
                  locality.locality_id, effective_public, "governance_production")
        quality = sum(output.values()) / len(output)
        integrity_loss = cfg.patronage_capacity_damage * patronage / max(1, public + patronage)
        institution.capacity = clamp(
            institution.capacity + cycle_scale * (
                cfg.capacity_learning_rate * quality -
                cfg.capacity_decay_rate * (1 - quality) -
                integrity_loss
            )
        )
        institution.integrity = clamp(
            institution.integrity - cycle_scale * integrity_loss
        )
        before = locality.control["government"].to_dict()
        locality.control["government"].update({
            "administrative": .004 * output["administration"] * cycle_scale,
            "legal": .004 * output["justice"] * cycle_scale,
            "social": .003 * output["services"] * cycle_scale,
            "expected": .003 * output["representation"] * cycle_scale,
        })
        for dimension, old in before.items():
            delta = getattr(locality.control["government"], dimension) - old
            if delta and world.execution_profile != "particle":
                world.causal_ledger.append(CausalContribution(
                    time, locality.locality_id, dimension, delta,
                    "political_policy_implementation", event_id))
        for person in world.persons.values():
            if person.residence_locality_id != locality.locality_id:
                continue
            fairness = institution.integrity
            experience = quality * (.5 + .5 * fairness)
            person.government_legitimacy = clamp(
                person.government_legitimacy +
                .04 * (experience - .35) * cycle_scale
            )
            person.state_legitimacy = clamp(
                person.state_legitimacy +
                .01 * (output["justice"] - .25) * cycle_scale
            )
            person.political_access = clamp(
                person.political_access +
                .03 * (output["representation"] - .2) * cycle_scale
            )
            if ruling_branch:
                person.party_legitimacy[world.ruling_party_id] = clamp(
                    person.party_legitimacy.get(world.ruling_party_id, .4) +
                    cycle_scale * (
                        .025 * patronage_reach - .015 * (1 - fairness)
                    ))
                for party_id in person.party_legitimacy:
                    if party_id != world.ruling_party_id:
                        person.party_legitimacy[party_id] = clamp(
                            person.party_legitimacy[party_id] -
                            .008 * patronage_reach * cycle_scale)
        world.policy_implementations.append(PolicyImplementation(
            f"PI{len(world.policy_implementations)+1:08d}", time, institution.institution_id,
            locality.locality_id, public + patronage + private_local, effective_public,
            patronage, private_local, compliance, output))
        implementations += 1
    election = False
    if not world.elections or time - world.elections[-1].time >= cfg.election_interval_days:
        run_election(world, time, rng)
        election = True
    return {"budget": budget, "public_spending": public_total,
            "patronage": patronage_total, "private_diversion": private_total,
            "patronage_decay": patronage_decay,
            "implementations": implementations, "election": election}


def run_election(world, time: float, rng: random.Random) -> Election:
    parties = sorted((o for o in world.organizations.values() if o.kind.value == "party"),
                     key=lambda o: o.organization_id)
    votes = {party.organization_id: 0.0 for party in parties}
    abstention = 0.0
    for person in world.persons.values():
        base_turnout = clamp(person.political_access * (.45 + .55 * person.state_legitimacy))
        turnout = clamp(base_turnout ** (1 / max(.1, world.config.political_order.election_turnout_sensitivity)))
        # A weighted representative stands for a population cohort.  Treating
        # the whole cohort as one Bernoulli voter makes election variance scale
        # with the number of simulated nodes.  Split represented mass across
        # turnout and party choice by the cohort probabilities instead.
        if not parties:
            abstention += person.weight
            continue
        abstention += person.weight * (1 - turnout)
        utilities = []
        for party in parties:
            branch = world.party_branches[f"BR-{party.organization_id}-{person.residence_locality_id}"]
            utilities.append(max(.001, person.party_legitimacy.get(party.organization_id, .3) *
                                 person.private_preference.get(party.organization_id, .3) *
                                 (1 + branch.electoral_support)))
        utility_total = sum(utilities)
        for party, utility in zip(parties, utilities):
            votes[party.organization_id] += person.weight * turnout * utility / utility_total
    prior = world.ruling_party_id
    winner_id = max(votes, key=votes.get) if votes else prior
    election = Election(
        f"ELN{len(world.elections)+1:05d}",
        time,
        votes,
        abstention,
        winner_id,
        prior,
        represented_electorate=sum(person.weight for person in world.persons.values()),
    )
    world.elections.append(election)
    world.ruling_party_id = winner_id
    for institution in world.political_institutions.values():
        institution.governing_party_id = winner_id
    for branch in world.party_branches.values():
        branch.institutional_influence = clamp(branch.institutional_influence +
                                               (.08 if branch.party_id == winner_id else -.02))
    return election


def political_diagnostics(world) -> dict:
    people = list(world.persons.values())
    represented = sum(person.weight for person in people)
    def weighted_mean(attribute: str) -> float:
        return (sum(person.weight * getattr(person, attribute) for person in people) /
                max(1e-12, represented))
    return {
        "ruling_party_id": world.ruling_party_id,
        "elections": sum(election.time >= 0 for election in world.elections),
        "mean_state_legitimacy": weighted_mean("state_legitimacy"),
        "mean_government_legitimacy": weighted_mean("government_legitimacy"),
        "mean_political_access": weighted_mean("political_access"),
        "institutional_capacity": {i.institution_id: i.capacity for i in world.political_institutions.values()},
        "party_influence": {b.branch_id: b.institutional_influence for b in world.party_branches.values()},
        "public_spending": world.cumulative_public_spending,
        "private_diversion_stock": world.private_diversion_stock,
        "transfers": len(world.political_transfers),
    }
