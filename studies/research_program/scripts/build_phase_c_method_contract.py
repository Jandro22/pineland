"""Freeze the method contract after synthetic validation, without historical fitting."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim.reproducibility import (  # noqa: E402
    canonical_sha256,
    file_sha256,
    model_sha256,
    repository_state,
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(
    output: Path,
    *,
    phase_a_path: Path | None = None,
    phase_b_path: Path | None = None,
    core_freeze_path: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite method contract: {output}")
    program = ROOT / "studies/research_program"
    phase_a_path = phase_a_path or program / "phase_a_certificate_v11.json"
    phase_b_path = phase_b_path or program / "phase_b_inference_validation_v6.json"
    core_freeze_path = core_freeze_path or program / "core_freeze_current_v1.json"
    phase_a = _load(phase_a_path)
    phase_b = _load(phase_b_path)
    core_freeze = _load(core_freeze_path)
    repo = repository_state(ROOT)
    phase_a_ok = bool(phase_a.get("passed"))
    phase_b_ok = bool(phase_b.get("passed"))
    core_identity = core_freeze.get("software_identity", {})
    core_boundary = core_freeze.get("core_boundary", {})
    live_model_sha = model_sha256(ROOT)
    identity_matches = (
        core_identity.get("model_sha256") == live_model_sha
        and core_identity.get("commit") == repo["commit_hash"]
        and core_identity.get("tracked_diff_sha256") == repo["tracked_diff_sha256"]
    )
    core_clean = bool(core_boundary.get("core_boundary_clean"))
    historical_authorized = phase_a_ok and phase_b_ok and core_clean and identity_matches
    contract = {
        "schema_version": "pineland.phase_c_method_contract.v2",
        "study_id": "phase_c_method_contract_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_for_historical_confrontation" if historical_authorized else "synthetic_contract_frozen_historical_gate_closed",
        "scope": {
            "historical_tuning": False,
            "historical_authorized": historical_authorized,
            "historical_authorization_rule": "A1-A5/A7 and B pass, the current content-addressed core freeze matches the live core, and the tracked scientific core boundary is clean; otherwise historical claims remain unauthorized.",
            "historical_cases": ["Nepal 2001-2006", "Afghanistan 2004-2021"],
            "historical_confrontation_once_only": True,
        },
        "model": {
            "model_sha256": live_model_sha,
            "source_commit": repo["commit_hash"],
            "tracked_diff_sha256": repo["tracked_diff_sha256"],
            "core_freeze": {
                "path": str(core_freeze_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(core_freeze_path),
                "freeze_id": core_freeze.get("freeze_id"),
                "native_binary_sha256": core_identity.get("native_binary_sha256"),
                "configuration_sha256": core_identity.get("configuration_sha256"),
                "parameter_registry_sha256": core_identity.get("parameter_registry_sha256"),
            },
            "core_boundary": core_boundary.get("declared", ["src/pineland_sim/**/*.py", "pyproject.toml"]),
            "core_clean": core_clean,
            "identity_matches_live": identity_matches,
            "full_working_tree_clean": bool(core_boundary.get("full_working_tree_clean")),
        },
        "inference_contract": {
            "particle_count": {
                "synthetic_validation": 256,
                "fixed_work_performance": 32,
                "historical_nepal_members": 8,
                "historical_afghanistan_initialization_conditions": 3,
            },
            "proposal_method": "declared prior proposal for RB and posterior-matched guided proposal in phase B; no case-specific adaptation",
            "rao_blackwellization_rule": "integrate the declared Bernoulli event hazard analytically within each particle-cell; retain the Monte Carlo particle genealogy for latent-state uncertainty",
            "likelihood_specification": "declared observation likelihood in phase_b_inference_validation_protocol_v2.json; historical observation operators remain case-contract-defined",
            "ess_threshold": "the preregistered threshold used by the frozen filter implementation; record ESS at every observation boundary",
            "resampling_algorithm": "systematic resampling with independent child lineage and retained parent indices",
            "resampling_rng": "seeded NumPy generator derived from the declared root seed; root and child seeds are recorded",
            "forecast_stopping_rule": "stop at the declared horizon or at the declared MCSE upper-bound criterion after the minimum draw count; never stop on a target-case score",
            "mcse_threshold": "binary MCSE upper-bound <= 0.02 after at least 32 draws, with regime coverage and RMSE thresholds as preregistered",
            "maximum_forecast_trajectories": 625,
            "minimum_forecast_trajectories": 32,
            "seed_generation_scheme": "explicit integer root seeds in the protocol; child lineage seeds are derived deterministically and retained",
            "observation_schedule": "weekly historical cells; synthetic schedule as declared in the phase B protocol",
            "state_extraction_rule": "decision-state hash and recorded/latent event cell sets are extracted at declared observation boundaries; no output-only archive fields enter propagation",
            "negative_evidence": "retain negative evidence; no silent imputation",
        },
        "empirical_scoring_contract": {
            "primary_outcome": "binary active violence/event cell under each case's predeclared observation operator",
            "row_universe": {
                "nepal": "all 19,575 district-week holdout rows with identical district IDs and weeks",
                "afghanistan": "the fixed province-week panel and the predeclared prospective/identical-row forecast universe",
            },
            "holdout_split": {
                "nepal": "existing all-holdout split in split_manifest.json",
                "afghanistan": "existing prospective split and identical-row competition contract",
            },
            "brier_computation": "mean squared error of the probability against the binary outcome over the complete declared row universe",
            "log_score_computation": "mean Bernoulli log score with declared finite clipping only at machine-safe probability bounds",
            "missing_row_policy": "zero silent dropping; any missing, duplicate, or mismatched row-key is a provenance failure and yields no result",
            "baseline_competitors": "the preserved simple comparator set emitted by run_aligned_predictive_competition.py; no post-hoc competitor removal",
            "tie_rule": "strict improvement on both primary Brier and log score for every required holdout partition; ties do not count as wins",
            "promotion_rule": "historical success requires a complete immutable ensemble and the strict primary rule; mixed and not-supported results remain admissible classifications",
            "diagnostic_only_metrics": ["calibration", "discrimination", "base event-rate error", "spatial allocation error", "latent-to-recorded information loss", "independent control signal"],
            "nepal_rule_preserved": "all-holdout Brier and log-score rule",
            "afghanistan_rule_preserved": "prospective and identical-row rules with independent control assessment",
        },
        "success_failure_semantics": {
            "historical_success": "Pineland beats the declared comparator under the preserved primary score with the declared complete ensemble",
            "mixed": "improved discrimination but worse calibration, or case-specific success without cross-case success",
            "failure": "the primary rule is not passed, the ensemble is incomplete, or a provenance/invariant gate fails",
            "reclassification_forbidden": True,
        },
        "theory_diagnostics_boundary": {
            "diagnostic_classes": ["rate error", "spatial error", "discrimination error", "recording-process error", "control-signal error", "belief error"],
            "diagnostics_authorize_parameter_changes": False,
            "post_historical_substantive_revision": "requires a new synthetic theoretical justification and a new freeze",
        },
        "gate_evidence": {
            "phase_a": {
                "path": str(phase_a_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(phase_a_path),
                "passed": phase_a_ok,
            },
            "phase_b": {
                "path": str(phase_b_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(phase_b_path),
                "passed": phase_b_ok,
            },
            "core_freeze": {
                "path": str(core_freeze_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(core_freeze_path),
                "passed": core_clean and identity_matches,
            },
        },
        "gate_failures": [
            reason for reason, failed in (
                ("phase_a_certificate_failed", not phase_a_ok),
                ("phase_b_synthetic_validation_failed", not phase_b_ok),
                ("core_boundary_not_clean", not core_clean),
                ("core_identity_does_not_match_live", not identity_matches),
            ) if failed
        ],
        "provenance": {
            "dirty_paths": repo["dirty_paths"],
            "contract_payload_sha256": canonical_sha256({
                "model_sha256": live_model_sha,
                "phase_a_sha256": file_sha256(phase_a_path),
                "phase_b_sha256": file_sha256(phase_b_path),
                "core_freeze_sha256": file_sha256(core_freeze_path),
                "historical_authorized": historical_authorized,
            }),
            "builder_sha256": file_sha256(Path(__file__)),
        },
        "passed": historical_authorized,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    return contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/phase_c_method_contract_v2.json")
    parser.add_argument("--phase-a", type=Path)
    parser.add_argument("--phase-b", type=Path)
    parser.add_argument("--core-freeze", type=Path)
    args = parser.parse_args()
    result = run(
        args.output.resolve(),
        phase_a_path=args.phase_a.resolve() if args.phase_a else None,
        phase_b_path=args.phase_b.resolve() if args.phase_b else None,
        core_freeze_path=args.core_freeze.resolve() if args.core_freeze else None,
    )
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
