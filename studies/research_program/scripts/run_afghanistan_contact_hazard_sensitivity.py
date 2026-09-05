"""Run a preregistered contact-hazard sensitivity without historical fitting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
TRANSFER_DIR = ROOT / "studies" / "afghanistan_2004_2021" / "scripts"
if str(TRANSFER_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSFER_DIR))

import run_transfer_test as transfer  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402

CONTRACT = ROOT / "studies" / "research_program" / "afghanistan_contact_hazard_sensitivity_contract.json"


def build(output: Path) -> dict:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    before = repository_state(ROOT)
    source_hash = model_sha256(ROOT)
    baseline_config = transfer._config
    runs = []
    try:
        for multiplier in contract["contact_rate_multipliers"]:
            def scaled_config(seed: int, horizon: float, *, _multiplier=float(multiplier)):
                config = baseline_config(seed, horizon)
                config.contact_rate = float(contract["contact_rate_baseline"]) * _multiplier
                config.validate()
                return config

            transfer._config = scaled_config
            run = transfer.run_case(
                int(contract["seed"]),
                float(contract["horizon_days"]),
                float(contract["taliban_initial_strength"]),
            )
            runs.append({
                "contact_rate_multiplier": float(multiplier),
                "contact_rate": float(contract["contact_rate_baseline"]) * float(multiplier),
                "model_sha256": run["model_sha256_end"],
                "model_stable_during_run": run["model_stable_during_run"],
                "gate": run["gate"],
                "events_processed": run["events_processed"],
                "latent_contacts": run["violence_validation"]["latent_contacts"],
                "recorded_contacts": run["violence_validation"]["recorded_contacts"],
                "latent_active_province_weeks": len(run["violence_validation"]["latent_active_cells"]),
                "recorded_active_province_weeks": len(run["violence_validation"]["recorded_active_cells"]),
                "hazard_diagnostics": run["hazard_diagnostics"],
                "contact_funnel_counts": run["contact_funnel_counts"],
                "case_hashes": run["case_hashes"],
            })
    finally:
        transfer._config = baseline_config
    after = repository_state(ROOT)
    contact_counts = [run["latent_contacts"] for run in runs]
    hazards = [run["hazard_diagnostics"]["mean_hazard"] for run in runs]
    monotone_contacts = all(left <= right for left, right in zip(contact_counts, contact_counts[1:]))
    monotone_hazards = all(left <= right for left, right in zip(hazards, hazards[1:]))
    integrity = (
        before["commit_hash"] == after["commit_hash"]
        and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        and all(run["model_sha256"] == source_hash and run["model_stable_during_run"] for run in runs)
    )
    result = {
        "schema_version": "1.0.0",
        "status": "current_core_contact_hazard_sensitivity_not_fit",
        "contract_sha256": file_sha256(CONTRACT),
        "model_sha256": source_hash,
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "repository_before": before,
        "repository_after": after,
        "runs": runs,
        "integrity_passed": integrity,
        "monotone_mean_hazard": monotone_hazards,
        "monotone_latent_contacts": monotone_contacts,
        "contact_counts": contact_counts,
        "mean_hazards": hazards,
        "scientific_interpretation": (
            "This fixed-seed sensitivity is diagnostic only. Monotone contact response would support "
            "hazard limitation; a flat response would implicate detection, spatial co-presence, readiness, "
            "or recording gates. Neither outcome licenses historical fitting or theory promotion."
        ),
    }
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest = {
        "schema_version": "1.0.0",
        "status": "current_core_contact_hazard_sensitivity_manifest",
        "artifact": {"path": output.relative_to(ROOT).as_posix(), "sha256": file_sha256(output)},
        "builder": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Path(__file__)),
        },
        "contract": {"path": CONTRACT.relative_to(ROOT).as_posix(), "sha256": file_sha256(CONTRACT)},
        "model_sha256": source_hash,
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["manifest"] = manifest_path.relative_to(ROOT).as_posix()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies" / "research_program" / "afghanistan_contact_hazard_sensitivity.json",
    )
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({
        "status": result["status"],
        "integrity_passed": result["integrity_passed"],
        "monotone_mean_hazard": result["monotone_mean_hazard"],
        "monotone_latent_contacts": result["monotone_latent_contacts"],
        "contact_counts": result["contact_counts"],
        "output": args.output.as_posix(),
    }, indent=2))
    return 0 if result["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
