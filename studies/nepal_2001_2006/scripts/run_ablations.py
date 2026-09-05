"""Run preregistered mechanism ablations on the same frozen case and seeds."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import time
import traceback


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
CASE = STUDY / "config" / "case_environment_repaired.json"
SPLIT = STUDY / "config" / "split_manifest.json"
OUT = STUDY / "runs" / "post_structural_repair" / "ablations"
START = date(2001, 11, 26)
END = date(2006, 11, 21)
SEEDS = (20_011_126, 20_051_154)
VARIANTS = ("baseline", "no_logistics", "no_information", "no_network")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run_one(variant: str, seed: int, agent_count: int = 750) -> dict:
    from pineland_sim.config import SimulationConfig
    from pineland_sim.generator import generate_pineland
    from pineland_sim.simulation import Simulation

    case = json.loads(CASE.read_text(encoding="utf-8"))
    config = SimulationConfig(seed=seed, horizon_days=(END - START).days,
                              agent_count=agent_count, locality_count=len(case["localities"]),
                              output_mode="ensemble")
    config.organization_ecology.observed_active_intervals = {"insurgent": [[0.0, float((END - START).days)]]}
    config.information.observation_retention_days = 90.0
    if variant == "no_logistics":
        # Remove logistics-mediated readiness and mobility penalties while
        # retaining the same supply ledger and route graph.
        config.logistics.formation_supply_days = 1_000_000.0
        # The config contract requires a positive presence cost; 1e-12 is the
        # explicit no-logistics limit while preserving validation semantics.
        config.logistics.presence_consumption_per_person_day = 1e-12
        config.logistics.movement_consumption_per_person_km = 0.0
        config.logistics.patrol_consumption_per_person_hour = 0.0
        config.logistics.readiness_degradation_rate = 0.0
        config.logistics.readiness_recovery_near_source = 0.0
        config.logistics.readiness_recovery_remote = 0.0
    elif variant == "no_information":
        for name in ("civilian_report_rate", "social_report_rate", "administrative_report_rate",
                     "elite_report_rate", "member_report_rate", "fixed_post_report_rate",
                     "patrol_report_rate", "interpreter_report_rate"):
            setattr(config.information, name, 0.0)
        config.information.true_positive_rate = 0.0
        config.information.contact_true_positive_rate = 0.0
    elif variant == "no_network":
        config.social_network.mean_social_degree = 1.0
        config.social_network.maximum_social_degree = 1
        config.social_network.bridge_fraction = 0.0
        config.social_network.language_topology_enabled = False
    started = time.perf_counter()
    world = Simulation(generate_pineland(config, empirical_geography=case)).run().world
    realized = {entry.event_id: bool(entry.true_state_delta.get("contact", 0.0) > 0)
                for entry in world.event_log if entry.event_type == "contact"}
    contacts = [record for record in world.synthetic_records
                if record.event_type == "contact" and realized.get(record.event_id, False)]
    by_split = {name: {"latent_contacts": 0, "recorded_contacts": 0} for name in (
        "training", "temporal_validation", "geographic_validation", "strict_joint_holdout")}
    eastern = {row["district_id"] for row in case["districts"] if row["region_id"] == "NP-R1"}
    for record in contacts:
        when = START + timedelta(days=int(record.time))
        early = when < date(2005, 1, 1)
        district_id = world.localities[record.locality_id].district_id
        split = (("geographic_validation" if district_id in eastern else "training") if early else
                 ("strict_joint_holdout" if district_id in eastern else "temporal_validation"))
        by_split[split]["latent_contacts"] += 1
        by_split[split]["recorded_contacts"] += int(record.recorded)
    return {"schema_version": "1.0.0", "variant": variant, "seed": seed,
            "formulation_tag": "post_structural_repair_v1",
            "agent_count": agent_count, "runtime_seconds": time.perf_counter() - started,
            "case_sha256": sha256(CASE), "split_sha256": sha256(SPLIT),
            "config": config.to_dict(), "summary": world.summary(),
            "contact_funnel": world.contact_funnel_records,
            "contact_funnel_counts": world.contact_funnel_counts,
            "by_split": by_split}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(variant, seed) for variant in VARIANTS for seed in SEEDS]
    expected = {(variant, seed): OUT / f"{variant}_seed_{seed}.json" for variant, seed in jobs}
    pending = [(variant, seed) for variant, seed in jobs if not expected[(variant, seed)].exists()]
    if pending:
        with ProcessPoolExecutor(max_workers=min(4, len(pending))) as executor:
            futures = {executor.submit(run_one, variant, seed): (variant, seed)
                       for variant, seed in pending}
            for future in as_completed(futures):
                variant, seed = futures[future]
                try:
                    payload = future.result()
                except Exception as error:
                    # Preserve a machine-readable blocker and continue other
                    # matched jobs; one ablation must not hide the others.
                    failure = {"schema_version": "1.0.0", "variant": variant,
                               "seed": seed, "status": "failed",
                               "error_type": type(error).__name__, "error": str(error),
                               "traceback": traceback.format_exc()}
                    failure_path = expected[(variant, seed)].with_suffix(".error.json")
                    failure_path.write_text(json.dumps(failure, indent=2) + "\n")
                    print(json.dumps({"failed": variant, "seed": seed,
                                      "error_type": type(error).__name__, "error": str(error)}), flush=True)
                    continue
                temporary = expected[(variant, seed)].with_suffix(".tmp")
                temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                temporary.replace(expected[(variant, seed)])
                print(json.dumps({"completed": variant, "seed": seed,
                                  "runtime_seconds": payload["runtime_seconds"],
                                  "recorded_contacts": sum(item["recorded_contacts"]
                                                           for item in payload["by_split"].values())}), flush=True)
    rows = [json.loads(expected[key].read_text()) for key in sorted(expected) if expected[key].exists()]
    failures = [json.loads(path.read_text()) for path in sorted(OUT.glob("*.error.json"))]
    from pineland_sim.config import SimulationConfig
    from pineland_sim.reproducibility import (
        build_run_manifest, canonical_sha256, file_sha256,
    )
    if rows:
        representative_config = SimulationConfig.from_dict(rows[0]["config"])
    else:
        case = json.loads(CASE.read_text(encoding="utf-8"))
        representative_config = SimulationConfig(
            seed=SEEDS[0], horizon_days=(END - START).days,
            agent_count=750, locality_count=len(case["localities"]),
            output_mode="ensemble",
        )
        representative_config.information.observation_retention_days = 90.0
    result_rows = [{
        "variant": row["variant"],
        "seed": row["seed"],
        "runtime_seconds": row["runtime_seconds"],
        "config_sha256": canonical_sha256(row["config"]),
        "file": expected[(row["variant"], row["seed"])].name,
        "sha256": sha256(expected[(row["variant"], row["seed"])]),
    } for row in rows]
    failure_paths = sorted(OUT.glob("*.error.json"))
    failure_rows = [{
        "variant": row["variant"],
        "seed": row["seed"],
        "error_type": row["error_type"],
        "error": row["error"],
        "file": path.name,
    } for path, row in zip(failure_paths, failures, strict=True)]
    manifest = build_run_manifest(
        representative_config,
        seeds=SEEDS,
        execution_mode={
            "mode": "mechanism_ablation_ensemble",
            "output_mode": "ensemble",
            "workers": min(4, len(jobs)),
            "process_isolated": True,
            "collation": "sorted_variant_seed_order",
            "bounded_information_retention_days": 90.0,
        },
        output_schema={
            "name": "nepal_mechanism_ablations",
            "version": "2.0.0",
            "per_run_format": "json",
            "manifest_format": "json",
        },
        case_files=[
            CASE,
            STUDY / "config" / "study.json",
            STUDY / "data" / "manifests" / "sources.json",
        ],
        split_file=SPLIT,
        repo_root=ROOT,
        extra={
            "runner_sha256": file_sha256(Path(__file__)),
            "variants": list(VARIANTS),
            "fit": False,
            "same_seeds_as": "baseline sensitivity subset",
        },
    )
    manifest.update({
        "study_id": "nepal_2001_2006",
        "same_seeds_as": "baseline sensitivity subset",
        "variants": list(VARIANTS),
        "fit": False,
        "case_sha256": sha256(CASE),
        "results": result_rows,
        "failures": failure_rows,
    })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"runs": len(rows), "failures": len(failures), "manifest": str(OUT / "manifest.json")}))


if __name__ == "__main__":
    main()
