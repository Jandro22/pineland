"""Run a bounded Nepal current-core smoke trajectory without fitting outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
CASE = STUDY / "config" / "case_environment_repaired.json"


def build(output: Path, *, seed: int = 20_011_126, horizon_days: float = 30.0) -> dict:
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from pineland_sim import SimulationConfig, Simulation, generate_pineland
    from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state

    case = json.loads(CASE.read_text(encoding="utf-8"))
    before = repository_state(ROOT)
    source_hash = model_sha256(ROOT)
    config = SimulationConfig(
        seed=seed,
        agent_count=len(case["localities"]),
        locality_count=len(case["localities"]),
        horizon_days=horizon_days,
        output_mode="ensemble",
    )
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, horizon_days]]
    }
    config.validate()
    world = generate_pineland(config, empirical_geography=case)
    initial_population = world.weighted_population()
    result = Simulation(world).run()
    world = result.world
    after = repository_state(ROOT)
    contact_events = [
        event for event in world.event_log
        if event.event_type == "contact" and event.true_state_delta.get("contact", 0.0) > 0
    ]
    recorded_contacts = [
        record for record in world.synthetic_records if record.event_type == "contact" and record.recorded
    ]
    active_localities = sorted({
        locality_id for locality_id in world.contact_event_localities
        if locality_id in world.localities
    })
    result_payload = {
        "schema_version": "1.0.0",
        "status": "current_core_nepal_smoke_diagnostic_not_transfer",
        "study_id": "nepal_2001_2006",
        "seed": seed,
        "horizon_days": horizon_days,
        "model_sha256": source_hash,
        "model_hash_stable_during_run": source_hash == model_sha256(ROOT),
        "repository_stable_during_run": (
            before["commit_hash"] == after["commit_hash"]
            and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        ),
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "integrity_passed": (
            source_hash == model_sha256(ROOT)
            and before["commit_hash"] == after["commit_hash"]
            and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        ),
        "events_processed": result.events_processed,
        "stopped_at": result.stopped_at,
        "initial_weighted_population": initial_population,
        "final_weighted_population": world.weighted_population(),
        "latent_contacts": len(contact_events),
        "recorded_contacts": len(recorded_contacts),
        "active_contact_localities": active_localities,
        "contact_funnel_counts": dict(world.contact_funnel_counts),
        "event_counts": dict(world.event_counts),
        "supply_conservation_residual": world.supply_conservation_residual(),
        "stock_ledger_residual": world.stock_ledger_residual(),
        "invariants_passed": world.assert_invariants() is None,
        "repository_before": before,
        "repository_after": after,
        "case_sha256": file_sha256(CASE),
        "interpretation": (
            "A 30-day current-core Nepal trajectory exercises repaired geography and latent processes. "
            "It is a construct-level diagnostic, not a historical score, transfer result, or theory claim."
        ),
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest = {
        "schema_version": "1.0.0",
        "status": "current_core_nepal_smoke_diagnostic_manifest",
        "artifact": {"path": output.relative_to(ROOT).as_posix(), "sha256": file_sha256(output)},
        "builder": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Path(__file__)),
        },
        "case": {"path": CASE.relative_to(ROOT).as_posix(), "sha256": file_sha256(CASE)},
        "model_sha256": source_hash,
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_payload["manifest"] = manifest_path.relative_to(ROOT).as_posix()
    return result_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies" / "research_program" / "nepal_current_core_smoke_preflight.json",
    )
    parser.add_argument("--horizon-days", type=float, default=30.0)
    args = parser.parse_args()
    result = build(args.output, horizon_days=args.horizon_days)
    print(json.dumps({
        "status": result["status"],
        "integrity_passed": result["integrity_passed"],
        "invariants_passed": result["invariants_passed"],
        "events_processed": result["events_processed"],
        "latent_contacts": result["latent_contacts"],
        "recorded_contacts": result["recorded_contacts"],
        "output": args.output.as_posix(),
    }, indent=2))
    return 0 if result["integrity_passed"] and result["invariants_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
