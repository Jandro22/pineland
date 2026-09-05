"""Fail-closed gate for claims that local reproduction beats simple models."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "studies/research_program/predictive_competition_gate.json"
REQUIRED = ["national_manpower", "violence_autoregression", "local_persistence_only",
            "static_geography", "government_force_ratio", "simple_spatial_diffusion"]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate() -> dict:
    observations = ROOT / "studies/research_program/data/processed/comparative_control_presence/manifest.json"
    historical = ROOT / "studies/research_program/historical_signature_competitor_benchmark.json"
    cases = json.loads(observations.read_text(encoding="utf-8"))["cases"]
    requirements = {
        "frozen_candidate_predictions_present": False,
        "same_holdout_rows_as_competitors": False,
        "all_required_covariates_available": False,
        "two_transfer_cases": False,
    }
    return {
        "schema_version": "1.0.0",
        "question": "Does competitive local reproduction predict held-out control/presence better than simpler alternatives?",
        "required_competitors": REQUIRED,
        "available_evidence": {
            "violence_signature_benchmark": {
                "path": str(historical.relative_to(ROOT)).replace("\\", "/"), "sha256": _hash(historical),
                "scope": "Event activation only; not control and not fitted reproduction predictions.",
            },
            "control_presence_cases": {key: {"status": value["status"], "run_license": value["run_license"]}
                                       for key, value in cases.items()},
        },
        "candidate_requirements": requirements,
        "gate_passed": all(requirements.values()),
        "verdict": "not_yet_testable_without_fabrication",
        "blocking_evidence": [
            "No frozen candidate reproduction predictions align to these observation rows.",
            "Colombia points are not control states; Iraq is one anchor; Vietnam lacks a declared crosswalk and holdout mapping.",
            "National manpower and government-force-ratio covariates are absent from the comparative panels.",
        ],
        "next_valid_test": "Declare case-specific outcomes and holdouts, attach candidate and all six competitor predictions to identical rows, then score without holdout refitting.",
        "coin_science_authorized": False,
    }


def main() -> None:
    result = evaluate()
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
