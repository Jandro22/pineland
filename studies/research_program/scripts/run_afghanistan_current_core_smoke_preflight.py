"""Run one bounded Afghanistan smoke trajectory against the live source.

The run is a current-core impact diagnostic, not a transfer claim.  It reads
the declared historical panel for scoring only; it never fits parameters and
cannot license a freeze or a theory promotion.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
TRANSFER_DIR = ROOT / "studies" / "afghanistan_2004_2021" / "scripts"
if str(TRANSFER_DIR) not in sys.path:
    sys.path.insert(0, str(TRANSFER_DIR))

from run_transfer_test import run_case  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402


def build(output: Path, *, seed: int = 20_040_101, horizon_days: float = 30.0,
          strength: float = 7500.0) -> dict:
    output = output.resolve()
    before = repository_state(ROOT)
    source_hash = model_sha256(ROOT)
    run = run_case(seed, horizon_days, strength)
    after = repository_state(ROOT)
    result = {
        "schema_version": "1.0.0",
        "status": "current_core_smoke_impact_diagnostic_not_transfer",
        "study_id": "afghanistan_2004_2021",
        "seed": seed,
        "horizon_days": horizon_days,
        "diagnostic_horizon_days": horizon_days,
        "taliban_initial_strength": strength,
        "model_sha256": source_hash,
        "model_hash_stable_during_run": (
            run.get("model_sha256_start") == run.get("model_sha256_end") == source_hash
        ),
        "repository_stable_during_run": (
            before["commit_hash"] == after["commit_hash"]
            and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        ),
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "integrity_passed": (
            run.get("model_stable_during_run") is True
            and before["commit_hash"] == after["commit_hash"]
            and before["tracked_diff_sha256"] == after["tracked_diff_sha256"]
        ),
        "run": run,
        "repository_before": before,
        "repository_after": after,
        "interpretation": (
            f"A single {horizon_days:g}-day current-core trajectory is retained for impact diagnostics. "
            "Historical scoring is descriptive, not fitted; this artifact is not a transfer result, "
            "superseding certificate, or theory test."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = output.with_name(output.stem + "_manifest.json")
    manifest = {
        "schema_version": "1.0.0",
        "status": "current_core_smoke_impact_diagnostic_manifest",
        "artifact": {"path": output.relative_to(ROOT).as_posix(), "sha256": file_sha256(output)},
        "builder": {
            "path": Path(__file__).relative_to(ROOT).as_posix(),
            "sha256": file_sha256(Path(__file__)),
        },
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
        default=ROOT / "studies" / "research_program" / "afghanistan_current_core_smoke_preflight.json",
    )
    parser.add_argument("--horizon-days", type=float, default=30.0)
    args = parser.parse_args()
    result = build(args.output, horizon_days=args.horizon_days)
    print(json.dumps({
        "status": result["status"],
        "integrity_passed": result["integrity_passed"],
        "model_hash_stable_during_run": result["model_hash_stable_during_run"],
        "repository_stable_during_run": result["repository_stable_during_run"],
        "events_processed": result["run"]["events_processed"],
        "horizon_days": result["horizon_days"],
        "latent_contacts": result["run"]["violence_validation"]["latent_contacts"],
        "recorded_contacts": result["run"]["violence_validation"]["recorded_contacts"],
        "output": args.output.as_posix(),
    }, indent=2))
    return 0 if result["integrity_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
