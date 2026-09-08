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
    persons = [world.persons[person_id] for person_id in person_ids]
    formations = [world.formations[formation_id] for formation_id in formation_ids]
    posts = list(world.security_posts.values())
    patrol_by_formation = {patrol.formation_id: patrol for patrol in world.patrols.values()}
    foothold_by_key = world.local_footholds
    sources = list(world.supply_sources.values())

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
    }

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
