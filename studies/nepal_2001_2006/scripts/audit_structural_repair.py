"""Audit and document the post_structural_repair_v1 formulation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
CASE = STUDY / "config" / "case_environment_repaired.json"
LEGACY_CASE = STUDY / "config" / "case_environment.json"
OUT = STUDY / "results" / "post_structural_repair"
FORMULATION = "post_structural_repair_v1"

HASH_FILES = [
    "src/pineland_sim/config.py",
    "src/pineland_sim/entities.py",
    "src/pineland_sim/world.py",
    "src/pineland_sim/generator.py",
    "src/pineland_sim/logistics.py",
    "src/pineland_sim/organization_ecology.py",
    "src/pineland_sim/processes.py",
    "src/pineland_sim/simulation.py",
    "src/pineland_sim/combat.py",
    "src/pineland_sim/physical.py",
    "src/pineland_sim/peace_process.py",
    "studies/nepal_2001_2006/scripts/run_untuned_benchmark.py",
    "studies/nepal_2001_2006/scripts/build_settlement_geography.py",
    "studies/nepal_2001_2006/scripts/acquire_geonames.py",
    "studies/nepal_2001_2006/config/case_environment_repaired.json",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from pineland_sim import SimulationConfig, generate_pineland

    case = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(
        seed=20_011_126, agent_count=len(case["localities"]),
        locality_count=len(case["localities"]), horizon_days=1, output_mode="ensemble",
    )
    config.organization_ecology.observed_active_intervals = {"insurgent": [[0.0, 1.0]]}
    world = generate_pineland(config, empirical_geography=case)
    world.assert_invariants()

    represented = {}
    counts = {}
    for person in world.persons.values():
        represented[person.residence_locality_id] = (
            represented.get(person.residence_locality_id, 0.0) + person.weight
        )
        counts[person.residence_locality_id] = counts.get(person.residence_locality_id, 0) + 1
    population_errors = {
        locality_id: represented.get(locality_id, 0.0) - locality.population
        for locality_id, locality in world.localities.items()
    }

    insurgent = sorted(
        (formation for formation in world.formations.values()
         if formation.organization_id == "insurgent"),
        key=lambda formation: formation.formation_id,
    )
    fdf = [formation for formation in world.formations.values()
           if formation.organization_id == "fdf"]
    state_sources = [source for source in world.supply_sources.values()
                     if source.organization_id in {"fdf", "police"}]
    initial_districts = {world.localities[f.locality_id].district_id for f in insurgent}
    eastern_ids = {f"NP-D{index:02d}" for index in range(1, 17)}
    expected_city_headquarters = sum(
        int(district["population"] >= 500_000) for district in case["districts"]
    )
    actual_city_headquarters = sum(
        locality.administrative_role == "district_headquarters" and locality.kind == "city"
        for locality in world.localities.values()
    )
    zone_region_consistent = all(
        world.geographic_containers[hierarchy["zone_id"]].get("region_id") ==
        hierarchy["region_id"]
        for hierarchy in world.district_hierarchy.values()
    )

    endurance_path = OUT / "structural_endurance_180d_seed_20011126.json"
    endurance = (json.loads(endurance_path.read_text(encoding="utf-8"))
                 if endurance_path.exists() else None)
    test_status_path = OUT / "test_status.json"
    test_status = (json.loads(test_status_path.read_text(encoding="utf-8"))
                   if test_status_path.exists() else None)

    checks = {
        "schema_v2": case.get("schema_version") == "2.0.0",
        "five_regions": len(case.get("regions", [])) == 5,
        "fourteen_zones": len(case.get("zones", [])) == 14,
        "seventy_five_districts": len(world.districts) == 75,
        "three_hundred_localities": len(world.localities) == 300,
        "seventy_five_headquarters": sum(
            locality.administrative_role == "district_headquarters"
            for locality in world.localities.values()
        ) == 75,
        "headquarters_city_template_rule": actual_city_headquarters == expected_city_headquarters,
        "zone_region_parentage_consistent": zone_region_consistent,
        "all_localities_have_representatives": set(counts) == set(world.localities),
        "locality_population_exact": max(abs(value) for value in population_errors.values()) < 1e-6,
        "government_formations_at_headquarters": all(
            world.localities[formation.locality_id].administrative_role == "district_headquarters"
            for formation in fdf
        ),
        "state_supply_sources_at_headquarters": all(
            world.localities[source.locality_id].administrative_role == "district_headquarters"
            for source in state_sources
        ),
        "declared_rolpa_origin": bool(insurgent) and insurgent[0].locality_id == "NP-D53-HQ",
        "dispersion_not_eastern_identifier_order": len(initial_districts & eastern_ids) < 4,
        "initial_insurgent_token_bound": max(
            formation.personnel for formation in insurgent
        ) <= config.force_structure.insurgent_target_personnel + 1e-9,
        "recruitment_access_required": config.organization_ecology.recruitment_requires_access,
        "legacy_case_preserved": LEGACY_CASE.exists(),
    }

    from pineland_sim.reproducibility import build_run_manifest, file_sha256
    payload = build_run_manifest(
        config,
        seeds=[config.seed],
        execution_mode={
            "mode": "structural_repair_audit",
            "output_mode": config.output_mode,
            "workers": 1,
            "process_isolated": False,
        },
        output_schema={
            "name": "nepal_structural_repair_audit",
            "version": "2.0.0",
            "format": "json_and_markdown",
        },
        case_files=[
            CASE,
            LEGACY_CASE,
            STUDY / "config" / "study.json",
            STUDY / "data" / "manifests" / "sources.json",
        ],
        split_file=STUDY / "config" / "split_manifest.json",
        repo_root=ROOT,
        extra={"runner_sha256": file_sha256(Path(__file__))},
    )
    payload.update({
        "formulation_tag": FORMULATION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parameter_fit": False,
        "study_period_outcomes_used_for_repairs": False,
        "case_sha256": sha256(CASE),
        "legacy_case_sha256": sha256(LEGACY_CASE),
        "geography": {
            "regions": len(case.get("regions", [])),
            "zones": len(case.get("zones", [])),
            "districts": len(world.districts),
            "localities": len(world.localities),
            "microzones": len(world.microzones),
            "headquarters": sum(locality.administrative_role == "district_headquarters"
                                 for locality in world.localities.values()),
            "city_headquarters": actual_city_headquarters,
        },
        "initial_force": {
            "insurgent_formations": len(insurgent),
            "insurgent_total_personnel": sum(formation.personnel for formation in insurgent),
            "insurgent_max_personnel": max(formation.personnel for formation in insurgent),
            "insurgent_districts": sorted(initial_districts),
            "government_formations": len(fdf),
        },
        "population_representation": {
            "agent_count": len(world.persons),
            "localities_represented": len(counts),
            "maximum_absolute_locality_population_error": max(
                abs(value) for value in population_errors.values()
            ),
        },
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "source_hashes": {relative: sha256(ROOT / relative) for relative in HASH_FILES},
        "endurance_180d": endurance,
        "test_status": test_status,
        "interpretation": (
            "Structural and software correctness does not establish empirical fit. "
            "Post-repair historical trajectories must be rescored before calibration."
        ),
    })
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "structural_repair_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Post structural repair audit",
        "",
        f"Formulation: `{FORMULATION}`",
        "",
        f"All structural checks pass: **{payload['all_checks_pass']}**",
        "",
        "## Geometry",
        "",
        f"- Regions: {payload['geography']['regions']}",
        f"- Zones: {payload['geography']['zones']}",
        f"- Historical districts: {payload['geography']['districts']}",
        f"- Named settlement/catchment localities: {payload['geography']['localities']}",
        f"- Generated microzones: {payload['geography']['microzones']}",
        f"- District headquarters: {payload['geography']['headquarters']}",
        "",
        "## Structural checks",
        "",
    ]
    lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
    lines.extend([
        "",
        "## Evidence boundary",
        "",
        "These checks establish implementation and construct-level invariants only. They do not establish Nepal historical fit. Calibration remains prohibited until post-repair train and holdout scoring is complete.",
        "",
    ])
    if endurance:
        lines.extend([
            "## 180-day structural endurance",
            "",
            f"- Runtime seconds: {endurance['runtime_seconds']:.3f}",
            f"- Initial insurgent formations: {endurance['initial_insurgent_formations']}",
            f"- Final insurgent formations: {endurance['final_insurgent_formations']}",
            f"- Initial maximum formation personnel: {endurance['initial_max_insurgent_personnel']:.3f}",
            f"- Final maximum formation personnel: {endurance['final_max_insurgent_personnel']:.3f}",
            f"- PRF-01 initial personnel: {endurance['prf01_initial_personnel']:.3f}",
            f"- PRF-01 final personnel: {endurance['prf01_final_personnel']:.3f}",
            f"- Latent engagements: {endurance['latent_engagements']}",
            f"- Recorded engagements: {endurance['recorded_engagements']}",
            "",
        ])
    if test_status:
        lines.extend([
            "## Software verification",
            "",
            f"- Command: `{test_status.get('command', 'not recorded in legacy test-status artifact')}`",
            f"- Passed: {test_status.get('passed', 'not recorded')}",
            f"- Failed: {test_status.get('failed', 'not recorded')}",
            f"- Runtime seconds: {test_status.get('runtime_seconds', 'not recorded')}",
            "",
        ])
    (OUT / "structural_repair_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "report": str(OUT / "structural_repair_report.md"),
        "all_checks_pass": payload["all_checks_pass"],
    }, indent=2))


if __name__ == "__main__":
    main()
