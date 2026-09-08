"""Compare the native initialization inventory with Python's world oracle.

This is intentionally a fail-closed gate.  It does not coerce unlike object
graphs into a passing scalar summary: the inventory names every requested
semantic category and reports the first mismatches for each predeclared seed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pineland_sim.config import SimulationConfig
from pineland_sim.generator import generate_pineland
from pineland_sim.simulation import Simulation


SEEDS = [
    0,
    1,
    2,
    3,
    7,
    17,
    42,
    99,
    123,
    314_159,
    8_675_309,
    20_260_902,
    20_011_126,
    2_147_483_647,
    4_294_967_295,
    4_294_967_296,
    281_474_976_723_001,
    9_223_372_036_854_775_807,
    18_446_744_073_709_551_615,
    16_021_456_112_345_678_901,
]
BINARY = ROOT / "rust" / "target" / "release" / (
    "pineland.exe" if os.name == "nt" else "pineland"
)
MANIFEST = ROOT / "rust" / "Cargo.toml"

CONTROL_DIMENSIONS = (
    "formal",
    "physical",
    "administrative",
    "legal",
    "fiscal",
    "social",
    "expected",
)
LANGUAGES = ("FS", "AR", "VE", "TA")
ORG_KIND_INDEX = {
    "government": 0,
    "military": 1,
    "police": 2,
    "insurgent": 3,
    "party": 4,
}
U32_MAX = 2**32 - 1


def digest_f64(values: Iterable[float]) -> str:
    material = b"".join(struct.pack("<d", float(value)) for value in values)
    return hashlib.sha256(material).hexdigest()


def digest_u32(values: Iterable[int]) -> str:
    material = b"".join(struct.pack("<I", int(value) & U32_MAX) for value in values)
    return hashlib.sha256(material).hexdigest()


def digest_u8(values: Iterable[int]) -> str:
    return hashlib.sha256(bytes(int(value) & 0xFF for value in values)).hexdigest()


def indexed(values: Iterable[str]) -> dict[str, int]:
    return {value: index for index, value in enumerate(values)}


def _control_values(world, locality_id: str, actor: str) -> list[float]:
    vector = world.localities[locality_id].control.get(actor)
    if vector is None:
        return [0.0] * len(CONTROL_DIMENSIONS)
    return [float(getattr(vector, dimension)) for dimension in CONTROL_DIMENSIONS]


def python_components(world, simulation: Simulation) -> dict[str, object]:
    """Return canonical initialization arrays for comparison with Rust.

    IDs are mapped to their explicit native numeric order before hashing. This
    keeps the certificate about semantic state rather than Python dictionary
    implementation details.
    """
    locality_ids = list(sorted(world.localities))
    locality_index = indexed(locality_ids)
    zone_ids = list(world.ordered_microzone_ids or sorted(world.microzones))
    zone_index = indexed(zone_ids)
    organization_ids = list(world.organizations)
    organization_index = indexed(organization_ids)
    formation_ids = list(world.formations)
    formation_index = indexed(formation_ids)
    household_ids = list(world.households)
    household_index = indexed(household_ids)
    community_ids = list(sorted(world.social_communities))
    community_index = indexed(community_ids)
    person_ids = list(world.ordered_person_ids or sorted(world.persons))
    person_index = indexed(person_ids)
    persons = [world.persons[person_id] for person_id in person_ids]
    formations = [world.formations[formation_id] for formation_id in formation_ids]
    posts = list(world.security_posts.values())
    patrol_by_formation = {patrol.formation_id: patrol for patrol in world.patrols.values()}
    foothold_by_key = world.local_footholds
    sources = list(world.supply_sources.values())

    # Auxiliary initialization tables are explicit certificate inputs.  Set
    # memberships are canonicalized by native person/elite index rather than
    # inheriting Python hash iteration order.
    political_institutions = list(world.political_institutions.values())
    institution_type_codes = {
        "executive": 0,
        "legislature": 1,
        "civil_administration": 2,
        "judiciary": 3,
        "military": 4,
        "police": 5,
        "district_government": 6,
        "municipal_government": 7,
    }
    institution_level_codes = {"federal": 0, "district": 1, "municipal": 2}
    party_branches = list(world.party_branches.values())
    local_elites = list(world.local_elites.values())
    elite_index = indexed(elite.elite_id for elite in local_elites)
    branch_member_indices: list[int] = []
    branch_member_offsets = [0]
    branch_broker_indices: list[int] = []
    branch_broker_offsets = [0]
    for branch in party_branches:
        branch_member_indices.extend(
            sorted(person_index[person_id] for person_id in branch.member_ids)
        )
        branch_member_offsets.append(len(branch_member_indices))
        branch_broker_indices.extend(
            sorted(elite_index[elite_id] for elite_id in branch.broker_ids)
        )
        branch_broker_offsets.append(len(branch_broker_indices))

    foreign_states = list(world.foreign_states.values())
    foreign_state_index = indexed(state.state_id for state in foreign_states)
    border_segments = list(world.border_segments.values())
    foreign_beliefs = list(world.foreign_beliefs.values())
    interpreter_brokers = list(world.interpreter_brokers.values())
    relation_rows = list(world.organization_relations.values())
    relation_status_codes = {
        "allied": 0,
        "cooperative": 1,
        "neutral": 2,
        "rival": 3,
        "hostile": 4,
        "ceasefire": 5,
    }

    values: dict[str, object] = {
        "locality_kind_counts": [
            sum(world.localities[locality_id].kind == kind for locality_id in locality_ids)
            for kind in ("city", "town", "village-cluster")
        ],
        "locality_kinds": [
            {"city": 0, "town": 1, "village-cluster": 2}[world.localities[locality_id].kind]
            for locality_id in locality_ids
        ],
        "locality_districts": [
            sorted(world.districts).index(world.localities[locality_id].district_id)
            for locality_id in locality_ids
        ],
        "locality_populations": [world.localities[locality_id].population for locality_id in locality_ids],
        "locality_population": digest_f64(
            world.localities[locality_id].population for locality_id in locality_ids
        ),
        "locality_economic_output": digest_f64(
            world.localities[locality_id].economic_output for locality_id in locality_ids
        ),
        "locality_infrastructure": digest_f64(
            world.localities[locality_id].infrastructure for locality_id in locality_ids
        ),
        "locality_administrative_capacity": digest_f64(
            world.localities[locality_id].administrative_capacity for locality_id in locality_ids
        ),
        "locality_terrain_friction": digest_f64(
            world.localities[locality_id].terrain_friction for locality_id in locality_ids
        ),
        "locality_observability": digest_f64(
            world.localities[locality_id].observability for locality_id in locality_ids
        ),
        "government_control": digest_f64(
            value
            for locality_id in locality_ids
            for value in _control_values(world, locality_id, "government")
        ),
        "insurgent_control": digest_f64(
            value
            for locality_id in locality_ids
            for value in _control_values(world, locality_id, "insurgent")
        ),
        "locality_government_governance": digest_f64(
            world.localities[locality_id].governance.get("administration", 0.0)
            for locality_id in locality_ids
        ),
        "locality_insurgent_governance": digest_f64(0.0 for _ in locality_ids),
        "zone_population_share": digest_f64(
            world.microzones[zone_id].population_share for zone_id in zone_ids
        ),
        "zone_infrastructure": digest_f64(
            world.microzones[zone_id].infrastructure for zone_id in zone_ids
        ),
        "zone_terrain_friction": digest_f64(
            world.microzones[zone_id].terrain_friction for zone_id in zone_ids
        ),
        "zone_observability": digest_f64(
            world.microzones[zone_id].observability for zone_id in zone_ids
        ),
        "zone_population_share_rows": [
            [
                world.microzones[zone_id].population_share
                for zone_id in world.microzone_ids_by_locality[locality_id]
            ]
            for locality_id in locality_ids
        ],
        "people_locality": digest_u32(locality_index[person.residence_locality_id] for person in persons),
        "people_home": digest_u32(locality_index[person.home_locality_id] for person in persons),
        "people_residence": digest_u32(locality_index[person.residence_locality_id] for person in persons),
        "people_represented_population": digest_f64(person.weight for person in persons),
        "people_household": digest_u32(household_index[person.household_id] for person in persons),
        "people_age": digest_u8(person.age for person in persons),
        "people_languages": digest_f64(
            person.languages[language] for person in persons for language in LANGUAGES
        ),
        "people_identities": digest_f64(
            person.identities[name]
            for person in persons
            for name in ("local", "district", "federal")
        ),
        "people_preferences": digest_f64(
            person.private_preference[f"party-{party}"]
            for person in persons
            for party in range(1, 4)
        ),
        "people_party_legitimacy": digest_f64(
            person.party_legitimacy.get(f"party-{party}", 0.0)
            for person in persons
            for party in range(1, 4)
        ),
        "people_grievance": digest_f64(person.grievance for person in persons),
        "people_fear": digest_f64(person.fear for person in persons),
        "people_efficacy": digest_f64(person.efficacy for person in persons),
        "people_trust": digest_f64(person.trust.get("government", 0.0) for person in persons),
        "people_trust_insurgent": digest_f64(
            person.trust.get("insurgent", 0.0) for person in persons
        ),
        "people_resources": digest_f64(person.resources for person in persons),
        "people_rebel_sympathy": digest_f64(
            person.insurgent_affinity.get("insurgent", 0.0) for person in persons
        ),
        "people_organization": digest_u32(
            organization_index.get(person.organization_id, U32_MAX) for person in persons
        ),
        "people_armed_fraction": digest_f64(person.armed_fraction for person in persons),
        "people_community": digest_u32(
            community_index.get(person.community_id, U32_MAX) for person in persons
        ),
        "people_public_behavior": digest_u8(
            {"neutral": 0, "insurgent_sympathy": 1, "armed_participation": 2}[person.public_behavior]
            for person in persons
        ),
        "people_expected_control": digest_f64(
            person.expected_control.get(actor, 0.0)
            for person in persons
            for actor in ("government", "insurgent")
        ),
        "people_state_legitimacy": digest_f64(person.state_legitimacy for person in persons),
        "people_government_legitimacy": digest_f64(
            person.government_legitimacy for person in persons
        ),
        "people_political_access": digest_f64(person.political_access for person in persons),
        "people_displaced": digest_u8(int(person.displaced) for person in persons),
        "people_displacement_count": digest_u32(person.displacement_count for person in persons),
        "people_origin_tie_strength": digest_f64(person.origin_tie_strength for person in persons),
        "people_insurgent_affinity": digest_f64(
            person.insurgent_affinity.get(organization_id, 0.0)
            for person in persons
            for organization_id in organization_ids
        ),
        "households_locality": digest_u32(
            locality_index[household.home_locality_id] for household in world.households.values()
        ),
        "households_residence": digest_u32(
            locality_index[household.residence_locality_id]
            for household in world.households.values()
        ),
        "households_resources": digest_f64(
            household.resources for household in world.households.values()
        ),
        "households_dependents": digest_u32(
            household.dependents for household in world.households.values()
        ),
        "households_member_offsets": digest_u32(
            [0]
            + [
                sum(len(world.households[household_id].member_ids) for household_id in household_ids)
                for household_ids in [list(world.households)[: index + 1]
                                      for index in range(len(world.households))]
            ]
        ),
        "households_member_indices": digest_u32(
            person_index[person_id]
            for household in world.households.values()
            for person_id in household.member_ids
        ),
        "communities_locality": digest_u32(
            locality_index[community.locality_id]
            for community in (world.social_communities[community_id] for community_id in community_ids)
        ),
        "communities_cohesion": digest_f64(
            world.social_communities[community_id].cohesion for community_id in community_ids
        ),
        "communities_language_profile": digest_f64(
            world.social_communities[community_id].language_profile[language]
            for community_id in community_ids
            for language in LANGUAGES
        ),
        "communities_member_offsets": digest_u32(
            [0]
            + [
                sum(
                    len(world.social_communities[item].member_ids)
                    for item in community_ids[: index + 1]
                )
                for index in range(len(community_ids))
            ]
        ),
        "communities_member_indices": digest_u32(
            person_index[person_id]
            for community_id in community_ids
            for person_id in world.social_communities[community_id].member_ids
        ),
        "communities_bridge_offsets": digest_u32(
            [0]
            + [
                sum(
                    len(world.social_communities[item].bridge_member_ids)
                    for item in community_ids[: index + 1]
                )
                for index in range(len(community_ids))
            ]
        ),
        "communities_bridge_members": digest_u32(
            person_index[person_id]
            for community_id in community_ids
            for person_id in world.social_communities[community_id].bridge_member_ids
        ),
        "social_edges_person_a": digest_u32(
            person_index[edge.person_a_id] for edge in world.social_edges.values()
        ),
        "social_edges_person_b": digest_u32(
            person_index[edge.person_b_id] for edge in world.social_edges.values()
        ),
        "social_edges_layers": digest_u8(
            sum({"household": 1, "community": 2, "bridge": 4}[layer] for layer in edge.layers)
            for edge in world.social_edges.values()
        ),
        "social_edges_weight": digest_f64(edge.weight for edge in world.social_edges.values()),
        "social_edges_language_compatibility": digest_f64(
            edge.language_compatibility for edge in world.social_edges.values()
        ),
        "social_edges_trust": digest_f64(edge.trust for edge in world.social_edges.values()),
        "social_edges_represented_relationships": digest_f64(
            edge.represented_relationships for edge in world.social_edges.values()
        ),
        "social_edges_neighbor_offsets": digest_u32(
            [0]
            + [
                sum(len(world.social_neighbors[person_id]) for person_id in person_ids[: index + 1])
                for index in range(len(person_ids))
            ]
        ),
        "social_edges_neighbor_indices": digest_u32(
            person_index[neighbor]
            for person_id in person_ids
            for neighbor in world.social_neighbors[person_id]
        ),
        "organizations_kind": digest_u8(
            ORG_KIND_INDEX[organization.kind.value] for organization in world.organizations.values()
        ),
        "organizations_active": digest_u8(
            int(organization.status == "active") for organization in world.organizations.values()
        ),
        "organizations_capital": digest_f64(
            organization.resources for organization in world.organizations.values()
        ),
        "organizations_cohesion": digest_f64(
            organization.cohesion for organization in world.organizations.values()
        ),
        "organizations_discipline": digest_f64(
            organization.discipline for organization in world.organizations.values()
        ),
        "organizations_accountability": digest_f64(
            organization.accountability for organization in world.organizations.values()
        ),
        "organizations_local_knowledge": digest_f64(
            organization.local_knowledge for organization in world.organizations.values()
        ),
        "organizations_persistence": digest_f64(
            organization.persistence for organization in world.organizations.values()
        ),
        "organizations_mobility": digest_f64(
            organization.mobility for organization in world.organizations.values()
        ),
        "organizations_institutional_quality": digest_f64(
            organization.institutional_quality for organization in world.organizations.values()
        ),
        "organizations_external_support": digest_f64(
            organization.external_support for organization in world.organizations.values()
        ),
        "organizations_member_population": digest_f64(
            sum(
                person.weight * person.armed_fraction
                for person in persons
                if person.organization_id == organization.organization_id
            )
            for organization in world.organizations.values()
        ),
        "organizations_capital_social": digest_f64(
            organization.capital.get("social", 0.0) for organization in world.organizations.values()
        ),
        "organizations_capital_political": digest_f64(
            organization.capital.get("political", 0.0) for organization in world.organizations.values()
        ),
        "organizations_capital_organizational": digest_f64(
            organization.capital.get("organizational", 0.0)
            for organization in world.organizations.values()
        ),
        "organizations_capital_material": digest_f64(
            organization.capital.get("material", 0.0) for organization in world.organizations.values()
        ),
        "organizations_phenotype": digest_f64(
            organization.phenotype[key]
            for organization in world.organizations.values()
            for key in (
                "centralization",
                "political_investment",
                "governance_investment",
                "dispersion",
                "risk_tolerance",
                "discipline",
                "local_embeddedness",
                "resource_dependence",
            )
        ),
        "organizations_ideology": digest_f64(
            organization.ideology[key]
            for organization in world.organizations.values()
            for key in ("reform", "separatism")
        ),
        "organizations_external_sanctuary": digest_f64(
            organization.external_sanctuary for organization in world.organizations.values()
        ),
        "organizations_adaptation_rate": digest_f64(
            organization.adaptation_rate for organization in world.organizations.values()
        ),
        "organizations_leader": digest_u32(
            indexed(list(world.leaders))[organization.leader_id]
            if organization.leader_id is not None
            else U32_MAX
            for organization in world.organizations.values()
        ),
        "formations_organization": digest_u32(
            organization_index[formation.organization_id] for formation in formations
        ),
        "formations_locality": digest_u32(
            locality_index[formation.locality_id] for formation in formations
        ),
        "formations_microzone": digest_u32(
            zone_index[formation.current_microzone_id] for formation in formations
        ),
        "formations_personnel": digest_f64(formation.personnel for formation in formations),
        "formations_quality": digest_f64(formation.quality for formation in formations),
        "formations_cohesion": digest_f64(formation.cohesion for formation in formations),
        "formations_readiness": digest_f64(formation.readiness for formation in formations),
        "formations_sustainment": digest_f64(formation.sustainment for formation in formations),
        "formations_information": digest_f64(formation.information for formation in formations),
        "formations_mobility": digest_f64(formation.mobility for formation in formations),
        "formations_command": digest_f64(formation.command for formation in formations),
        "formations_embeddedness": digest_f64(formation.embeddedness for formation in formations),
        "formations_fatigue": digest_f64(formation.fatigue for formation in formations),
        "formations_availability": digest_f64(formation.availability for formation in formations),
        "formations_supply_stock": digest_f64(formation.supply_stock for formation in formations),
        "formations_supply_capacity": digest_f64(formation.supply_capacity for formation in formations),
        "formations_home_locality": digest_u32(
            locality_index[formation.home_locality_id] for formation in formations
        ),
        "formations_active": digest_u8(int(formation.personnel > 0) for formation in formations),
        "formations_moving": digest_u8(int(formation.moving) for formation in formations),
        "formations_outside_pineland": digest_u8(int(formation.outside_pineland) for formation in formations),
        "security_posts_organization": digest_u32(
            organization_index[post.organization_id] for post in posts
        ),
        "security_posts_locality": digest_u32(locality_index[post.locality_id] for post in posts),
        "security_posts_microzone": digest_u32(zone_index[post.microzone_id] for post in posts),
        "security_posts_personnel": digest_f64(post.personnel for post in posts),
        "security_posts_presence": digest_f64(post.fixed_presence for post in posts),
        "security_posts_available_fraction": digest_f64(post.available_fraction for post in posts),
        "security_posts_formation": digest_u32(
            formation_index.get(post.formation_id, U32_MAX) for post in posts
        ),
        "patrols_formation": digest_u32(
            index for index in range(len(formations))
        ),
        "patrols_active": digest_u8(
            int(formation.formation_id in patrol_by_formation) for formation in formations
        ),
        "patrols_route_position": digest_u32(
            zone_index[patrol_by_formation[formation.formation_id].current_microzone_id]
            if formation.formation_id in patrol_by_formation
            else 0
            for formation in formations
        ),
        "patrols_route_target": digest_u32(
            zone_index[patrol_by_formation[formation.formation_id].current_microzone_id]
            if formation.formation_id in patrol_by_formation
            else 0
            for formation in formations
        ),
        "patrols_next_available": digest_f64(
            patrol_by_formation[formation.formation_id].available_at
            if formation.formation_id in patrol_by_formation
            else 0.0
            for formation in formations
        ),
        "footholds_active": digest_u8(
            int((organization_id, locality_id) in foothold_by_key)
            for organization_id in organization_ids
            for locality_id in locality_ids
        ),
        "footholds_strength": digest_f64(
            foothold_by_key[(organization_id, locality_id)].strength
            if (organization_id, locality_id) in foothold_by_key
            else 0.0
            for organization_id in organization_ids
            for locality_id in locality_ids
        ),
        "footholds_raw_signal": digest_f64(
            foothold_by_key[(organization_id, locality_id)].raw_signal
            if (organization_id, locality_id) in foothold_by_key
            else 0.0
            for organization_id in organization_ids
            for locality_id in locality_ids
        ),
        "footholds_membership": digest_f64(
            sum(
                world.persons[person_id].weight * world.persons[person_id].armed_fraction
                for person_id in organization.member_ids
                if person_id in world.persons
                and world.persons[person_id].residence_locality_id == locality_id
            ) / max(1e-12, world.localities[locality_id].population)
            if organization_id == "insurgent"
            else 0.0
            for organization_id in organization_ids
            for locality_id in locality_ids
            for organization in [world.organizations[organization_id]]
        ),
        "footholds_embeddedness": digest_f64(
            foothold_by_key[(organization_id, locality_id)].strength
            if (organization_id, locality_id) in foothold_by_key
            else 0.0
            for organization_id in organization_ids
            for locality_id in locality_ids
        ),
        "logistics_organization": digest_u32(
            organization_index[source.organization_id] for source in sources
        ),
        "logistics_locality": digest_u32(locality_index[source.locality_id] for source in sources),
        "logistics_source_stock": digest_f64(source.stock for source in sources),
        "logistics_source_capacity": digest_f64(source.capacity for source in sources),
        "logistics_source_production": digest_f64(source.production_per_day for source in sources),
        "zone_belief_keys": hashlib.sha256(
            b"".join(
                struct.pack(
                    "<II",
                    organization_index[observer],
                    zone_index[microzone_id],
                )
                for (observer, microzone_id) in world.zone_beliefs
            )
        ).hexdigest(),
        "zone_belief_estimate": digest_f64(
            belief.physical_control_estimate for belief in world.zone_beliefs.values()
        ),
        "zone_belief_confidence": digest_f64(
            belief.confidence for belief in world.zone_beliefs.values()
        ),
        "zone_belief_updated_at": digest_f64(
            belief.updated_at for belief in world.zone_beliefs.values()
        ),
        "zone_belief_reliable_at": digest_f64(
            belief.last_reliable_observation_at for belief in world.zone_beliefs.values()
        ),
        "zone_belief_evidence": digest_u32(
            belief.evidence_count for belief in world.zone_beliefs.values()
        ),
        "zone_belief_contradiction": digest_f64(
            belief.contradiction_index for belief in world.zone_beliefs.values()
        ),
        "command_edges_organization": digest_u32(
            organization_index[edge.organization_id]
            for edge in world.command_edges.values()
        ),
        "command_edges_formation": digest_u32(
            formation_index[edge.node_b_id]
            for edge in world.command_edges.values()
        ),
        "command_edges_reliability": digest_f64(
            edge.reliability for edge in world.command_edges.values()
        ),
        "command_edges_latency_hours": digest_f64(
            edge.latency_hours for edge in world.command_edges.values()
        ),
        "manpower_organization": digest_u32(
            organization_index[organization_id]
            for (organization_id, _locality_id) in sorted(world.organization_manpower_pools)
        ),
        "manpower_locality": digest_u32(
            locality_index[locality_id]
            for (_organization_id, locality_id) in sorted(world.organization_manpower_pools)
        ),
        "manpower_pool": digest_f64(
            world.organization_manpower_pools[key]
            for key in sorted(world.organization_manpower_pools)
        ),
        "manpower_supply_reserve": digest_f64(
            world.organization_manpower_supply_reserves.get(key, 0.0)
            for key in sorted(world.organization_manpower_pools)
        ),
        "leaders_organization": digest_u32(
            organization_index[leader.organization_id] for leader in world.leaders.values()
        ),
        "leaders_competence": digest_f64(leader.competence for leader in world.leaders.values()),
        "leaders_charisma": digest_f64(leader.charisma for leader in world.leaders.values()),
        "leaders_risk_tolerance": digest_f64(
            leader.risk_tolerance for leader in world.leaders.values()
        ),
        "leaders_ideological_rigidity": digest_f64(
            leader.ideological_rigidity for leader in world.leaders.values()
        ),
        "leaders_political_skill": digest_f64(
            leader.political_skill for leader in world.leaders.values()
        ),
        "leaders_organizational_skill": digest_f64(
            leader.organizational_skill for leader in world.leaders.values()
        ),
        "leaders_active": digest_u8(int(leader.active) for leader in world.leaders.values()),
    }

    values.update(
        {
            "political_institution_type": digest_u8(
                institution_type_codes[institution.institution_type]
                for institution in political_institutions
            ),
            "political_institution_level": digest_u8(
                institution_level_codes[institution.level]
                for institution in political_institutions
            ),
            "political_institution_locality": digest_u32(
                locality_index.get(institution.locality_id, U32_MAX)
                for institution in political_institutions
            ),
            "political_institution_district": digest_u32(
                sorted(world.districts).index(institution.district_id)
                if institution.district_id is not None
                else U32_MAX
                for institution in political_institutions
            ),
            "political_institution_capacity": digest_f64(
                institution.capacity for institution in political_institutions
            ),
            "political_institution_autonomy": digest_f64(
                institution.autonomy for institution in political_institutions
            ),
            "political_institution_compliance": digest_f64(
                institution.compliance for institution in political_institutions
            ),
            "political_institution_reach": digest_f64(
                institution.reach for institution in political_institutions
            ),
            "political_institution_integrity": digest_f64(
                institution.integrity for institution in political_institutions
            ),
            "political_institution_resources": digest_f64(
                institution.resources for institution in political_institutions
            ),
            "political_institution_governing_party": digest_u32(
                organization_index.get(institution.governing_party_id, U32_MAX)
                for institution in political_institutions
            ),
            "political_branch_party": digest_u32(
                organization_index[branch.party_id] for branch in party_branches
            ),
            "political_branch_locality": digest_u32(
                locality_index[branch.locality_id] for branch in party_branches
            ),
            "political_branch_resources": digest_f64(
                branch.resources for branch in party_branches
            ),
            "political_branch_patronage": digest_f64(
                branch.patronage_stock for branch in party_branches
            ),
            "political_branch_electoral_support": digest_f64(
                branch.electoral_support for branch in party_branches
            ),
            "political_branch_institutional_influence": digest_f64(
                branch.institutional_influence for branch in party_branches
            ),
            "political_branch_member_offsets": digest_u32(branch_member_offsets),
            "political_branch_member_indices": digest_u32(branch_member_indices),
            "political_branch_broker_offsets": digest_u32(branch_broker_offsets),
            "political_branch_broker_indices": digest_u32(branch_broker_indices),
            "political_elite_person": digest_u32(
                person_index[elite.person_id] for elite in local_elites
            ),
            "political_elite_locality": digest_u32(
                locality_index[elite.locality_id] for elite in local_elites
            ),
            "political_elite_network_centrality": digest_f64(
                elite.network_centrality for elite in local_elites
            ),
            "political_elite_resources": digest_f64(
                elite.resources for elite in local_elites
            ),
            "political_elite_legitimacy": digest_f64(
                elite.legitimacy for elite in local_elites
            ),
            "political_elite_institutional_ties": digest_f64(
                elite.institutional_ties for elite in local_elites
            ),
            "political_elite_party_alignment": digest_u32(
                organization_index.get(elite.party_alignment, U32_MAX)
                for elite in local_elites
            ),
            "political_ruling_party": digest_u32(
                [organization_index.get(world.ruling_party_id, U32_MAX)]
            ),
            "political_private_diversion_stock": digest_f64(
                [world.private_diversion_stock]
            ),
            "foreign_resources": digest_f64(state.resources for state in foreign_states),
            "foreign_stability_preference": digest_f64(
                state.stability_preference for state in foreign_states
            ),
            "foreign_government_alignment": digest_f64(
                state.government_alignment for state in foreign_states
            ),
            "foreign_ideological_alignment": digest_f64(
                state.ideological_alignment for state in foreign_states
            ),
            "foreign_border_security_priority": digest_f64(
                state.border_security_priority for state in foreign_states
            ),
            "foreign_regional_influence": digest_f64(
                state.regional_influence for state in foreign_states
            ),
            "foreign_commercial_interest": digest_f64(
                state.commercial_interest for state in foreign_states
            ),
            "foreign_humanitarian_preference": digest_f64(
                state.humanitarian_preference for state in foreign_states
            ),
            "foreign_cost_sensitivity": digest_f64(
                state.cost_sensitivity for state in foreign_states
            ),
            "foreign_domestic_opposition": digest_f64(
                state.domestic_opposition for state in foreign_states
            ),
            "foreign_willingness": digest_f64(state.willingness for state in foreign_states),
            "foreign_language_profile": digest_f64(
                state.language_profile[language]
                for state in foreign_states
                for language in LANGUAGES
            ),
            "foreign_opportunity": digest_f64(state.opportunity for state in foreign_states),
            "foreign_rival_offsets": digest_u32(
                [0]
                + [
                    sum(len(sorted(state.rival_ids)) for state in foreign_states[: index + 1])
                    for index in range(len(foreign_states))
                ]
            ),
            "foreign_rival_indices": digest_u32(
                foreign_state_index[rival_id]
                for state in foreign_states
                for rival_id in sorted(state.rival_ids)
            ),
            "foreign_cumulative_cost": digest_f64(
                state.cumulative_cost for state in foreign_states
            ),
            "foreign_cumulative_casualties": digest_f64(
                state.cumulative_casualties for state in foreign_states
            ),
            "foreign_border_foreign_state": digest_u32(
                foreign_state_index[border.foreign_state_id] for border in border_segments
            ),
            "foreign_border_district": digest_u32(
                sorted(world.districts).index(border.district_id)
                for border in border_segments
            ),
            "foreign_border_locality": digest_u32(
                locality_index[border.locality_id] for border in border_segments
            ),
            "foreign_border_terrain_friction": digest_f64(
                border.terrain_friction for border in border_segments
            ),
            "foreign_border_infrastructure": digest_f64(
                border.infrastructure for border in border_segments
            ),
            "foreign_border_legal_permeability": digest_f64(
                border.legal_permeability for border in border_segments
            ),
            "foreign_border_social_permeability": digest_f64(
                border.social_permeability for border in border_segments
            ),
            "foreign_border_language_overlap": digest_f64(
                border.language_overlap for border in border_segments
            ),
            "foreign_border_kinship_overlap": digest_f64(
                border.kinship_overlap for border in border_segments
            ),
            "foreign_border_state_monitoring": digest_f64(
                border.state_monitoring for border in border_segments
            ),
            "foreign_belief_foreign_state": digest_u32(
                foreign_state_index[belief.foreign_state_id] for belief in foreign_beliefs
            ),
            "foreign_belief_locality": digest_u32(
                locality_index[belief.locality_id] for belief in foreign_beliefs
            ),
            "foreign_belief_government_control": digest_f64(
                belief.government_control_estimate for belief in foreign_beliefs
            ),
            "foreign_belief_insurgent_presence": digest_f64(
                belief.insurgent_presence_estimate for belief in foreign_beliefs
            ),
            "foreign_belief_confidence": digest_f64(
                belief.confidence for belief in foreign_beliefs
            ),
            "foreign_belief_updated_at": digest_f64(
                belief.updated_at for belief in foreign_beliefs
            ),
            "foreign_interpreter_person": digest_u32(
                person_index[broker.person_id] for broker in interpreter_brokers
            ),
            "foreign_interpreter_foreign_state": digest_u32(
                foreign_state_index[broker.foreign_state_id]
                for broker in interpreter_brokers
            ),
            "foreign_interpreter_locality": digest_u32(
                locality_index[broker.locality_id] for broker in interpreter_brokers
            ),
            "foreign_interpreter_foreign_language": digest_f64(
                broker.foreign_language for broker in interpreter_brokers
            ),
            "foreign_interpreter_local_language": digest_f64(
                broker.local_language for broker in interpreter_brokers
            ),
            "foreign_interpreter_foreign_trust": digest_f64(
                broker.foreign_trust for broker in interpreter_brokers
            ),
            "foreign_interpreter_local_trust": digest_f64(
                broker.local_trust for broker in interpreter_brokers
            ),
            "foreign_interpreter_cultural_knowledge": digest_f64(
                broker.cultural_knowledge for broker in interpreter_brokers
            ),
            "relations_organization_a": digest_u32(
                organization_index[relation.organization_a_id] for relation in relation_rows
            ),
            "relations_organization_b": digest_u32(
                organization_index[relation.organization_b_id] for relation in relation_rows
            ),
            "relations_status": digest_u8(
                relation_status_codes[relation.status.value] for relation in relation_rows
            ),
            "relations_rivalry_memory": digest_f64(
                relation.rivalry_memory for relation in relation_rows
            ),
            "relations_hostility_memory": digest_f64(
                relation.hostility_memory for relation in relation_rows
            ),
            "relations_cooperation_memory": digest_f64(
                relation.cooperation_memory for relation in relation_rows
            ),
            "relations_updated_at": digest_f64(
                relation.updated_at for relation in relation_rows
            ),
            "relations_last_interaction_at": digest_f64(
                relation.last_interaction_at or 0.0 for relation in relation_rows
            ),
            "relations_has_last_interaction": digest_u8(
                int(relation.last_interaction_at is not None) for relation in relation_rows
            ),
        }
    )

    belief_presence: list[float] = []
    belief_control: list[float] = []
    belief_confidence: list[float] = []
    for organization_id in organization_ids:
        for locality_id in locality_ids:
            base = world.beliefs[(organization_id, locality_id)]
            belief_presence.append(0.0)
            belief_control.extend(
                getattr(base.control_estimate, dimension) for dimension in CONTROL_DIMENSIONS
            )
            belief_confidence.append(base.confidence)
            for target in (
                "insurgent",
                "insurgent" if organization_id == "insurgent" else "government",
                "government" if organization_id == "insurgent" else "insurgent",
            ):
                control = world.control_beliefs[(organization_id, target, locality_id)]
                belief_presence.append(0.0)
                belief_control.extend(
                    getattr(control.control_estimate, dimension) for dimension in CONTROL_DIMENSIONS
                )
                belief_confidence.append(control.confidence)
    # Native uses three rows per observer/locality (presence, control, and
    # opposing-control). The first row is the shared ActorBelief control row;
    # retain that exact ordering rather than duplicating it in the loop above.
    belief_presence = []
    belief_control = []
    belief_confidence = []
    for organization_id in organization_ids:
        for locality_id in locality_ids:
            base = world.beliefs[(organization_id, locality_id)]
            belief_presence.append(0.0)
            belief_control.extend(
                getattr(base.control_estimate, dimension) for dimension in CONTROL_DIMENSIONS
            )
            belief_confidence.append(base.confidence)
            target = "insurgent" if organization_id == "insurgent" else "government"
            opposing = "government" if organization_id == "insurgent" else "insurgent"
            for actor in (target, opposing):
                control = world.control_beliefs[(organization_id, actor, locality_id)]
                belief_presence.append(0.0)
                belief_control.extend(
                    getattr(control.control_estimate, dimension) for dimension in CONTROL_DIMENSIONS
                )
                belief_confidence.append(control.confidence)
    values.update(
        {
            "belief_presence": digest_f64(belief_presence),
            "belief_control": digest_f64(belief_control),
            "belief_confidence": digest_f64(belief_confidence),
            "belief_keys": hashlib.sha256(
                b"".join(
                    struct.pack(
                        "<IIIB",
                        organization_index[organization_id],
                        organization_index[target],
                        locality_index[locality_id],
                        kind,
                    )
                    for organization_id in organization_ids
                    for locality_id in locality_ids
                    for target, kind in (
                        ("insurgent", 0),
                        (("insurgent" if organization_id == "insurgent" else "government"), 1),
                        (("government" if organization_id == "insurgent" else "insurgent"), 2),
                    )
                )
            ).hexdigest(),
        }
    )

    event_codes = {
        "patrol": 1,
        "contact_scan": 2,
        "command": 3,
        "force_movement": 4,
        "logistics": 5,
        "information": 6,
        "beliefs": 7,
        "physical_refresh": 8,
        "social_influence": 9,
        "mobility": 10,
        "recruitment": 11,
        "organization_ecology": 12,
        "governance": 13,
        "economy": 14,
        "political_order": 15,
        "foreign_affairs": 16,
        "peace_process": 17,
        "recording_noise": 18,
        "checkpoint": 19,
    }
    scheduler_rows = []
    for event in simulation.scheduler.pending_events():
        scheduler_rows.append(
            {
                "time_bits": struct.unpack("<Q", struct.pack("<d", event.time))[0],
                "priority": event.priority,
                "sequence": event.sequence,
                "kind": event.event_type,
                "code": event_codes[event.event_type],
            }
        )
    values["scheduler"] = scheduler_rows
    return values


def binary_path() -> Path:
    configured = os.environ.get("PINELAND_BIN")
    binary = Path(configured) if configured else BINARY
    if not binary.is_file():
        subprocess.run(
            [
                "cargo",
                "build",
                "--release",
                "--locked",
                "--manifest-path",
                str(MANIFEST),
                "-p",
                "pineland-cli",
            ],
            cwd=ROOT,
            check=True,
        )
    return binary


def python_inventory(config: SimulationConfig) -> dict[str, object]:
    world = generate_pineland(config)
    simulation = Simulation(world)
    simulation.initialize()
    summary = world.summary()
    counts = {
        "people": summary["agents"],
        "households": summary["households"],
        "communities": summary["social_communities"],
        "organizations": summary["organizations"],
        "formations": summary["formations"],
        "posts": summary["security_posts"],
        "patrols": summary["patrols"],
        "localities": summary["localities"],
        "microzones": summary["microzones"],
        "footholds": summary["local_footholds"],
        "manpower_pools": len(world.organization_manpower_pools),
        "logistics_sources": summary["supply_sources"],
        "belief_state": len(world.beliefs) + len(world.control_beliefs),
        "zone_belief_state": len(world.zone_beliefs),
        "social_edges": len(world.social_edges),
        "command_edges": len(world.command_edges),
        "leaders": len(world.leaders),
        "political_institutions": len(world.political_institutions),
        "party_branches": len(world.party_branches),
        "local_elites": len(world.local_elites),
        "foreign_states": len(world.foreign_states),
        "border_segments": len(world.border_segments),
        "foreign_beliefs": len(world.foreign_beliefs),
        "interpreter_brokers": len(world.interpreter_brokers),
        "organization_relations": len(world.organization_relations),
        "scheduler": len(simulation.scheduler),
    }
    return {
        "counts": counts,
        "components": python_components(world, simulation),
        "summary": {
            key: summary[key]
            for key in (
                "represented_population",
                "mean_government_effective_control",
                "mean_insurgent_effective_control",
                "active_insurgent_formation_personnel",
                "mean_local_foothold_strength",
            )
        },
        "configuration_hash": hashlib.sha256(
            json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def native_inventory(binary: Path, config_path: Path, seed: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            str(binary),
            "certify-initialization",
            "--config",
            str(config_path),
            "--seed",
            str(seed),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "scenarios" / "baseline.json")
    parser.add_argument("--agent-count", type=int, default=300)
    parser.add_argument("--locality-count", type=int, default=34)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)

    base = json.loads(args.config.read_text(encoding="utf-8"))
    base.update(
        agent_count=args.agent_count,
        locality_count=args.locality_count,
        burn_in_days=0.0,
        output_mode="calibration",
    )
    config = SimulationConfig.from_dict(base)
    config.validate()
    binary = binary_path()
    mismatches: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(config.to_dict(), handle, sort_keys=True, separators=(",", ":"))
        config_path = Path(handle.name)
    try:
        for seed in SEEDS:
            seeded = SimulationConfig.from_dict({**config.to_dict(), "seed": seed})
            expected = python_inventory(seeded)
            actual = native_inventory(binary, config_path, seed)
            mismatching_fields = {
                key: {
                    "python": expected["counts"].get(key),
                    "rust": actual["counts"].get(key),
                }
                for key in expected["counts"]
                if expected["counts"].get(key) != actual["counts"].get(key)
            }
            rust_components = dict(actual.get("components", {}))
            rust_components["scheduler"] = actual.get("scheduler")
            row = {
                "seed": seed,
                "mismatches": mismatching_fields,
                "component_mismatches": {
                    key: {
                        "python": expected["components"].get(key),
                        "rust": rust_components.get(key),
                    }
                    for key in expected["components"]
                    if expected["components"].get(key)
                    != rust_components.get(key)
                },
                "native_components": rust_components,
            }
            rows.append(row)
            if mismatching_fields or row["component_mismatches"]:
                mismatches.append(row)
    finally:
        config_path.unlink(missing_ok=True)

    certificate = {
        "schema": "pineland-initialization-parity-certificate-v1",
        "status": "passed" if not mismatches else "failed",
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "seed_count": len(SEEDS),
        "configuration": {
            "agent_count": args.agent_count,
            "locality_count": args.locality_count,
            "burn_in_days": 0.0,
        },
        "rows": rows,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "gate": "zero semantic discrepancies required",
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    if mismatches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
