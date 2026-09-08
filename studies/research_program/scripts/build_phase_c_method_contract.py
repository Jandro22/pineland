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


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite method contract: {output}")
    program = ROOT / "studies/research_program"
    phase_a_path = program / "phase_a_certificate_v1.json"
    phase_b_path = program / "phase_b_inference_validation_v2.json"
    phase_a = _load(phase_a_path)
    phase_b = _load(phase_b_path)
    repo = repository_state(ROOT)
    phase_a_ok = bool(phase_a.get("passed"))
    phase_b_ok = bool(phase_b.get("passed"))
    core_clean = not any(
        path.startswith("src/pineland_sim/") or path in {"pyproject.toml"}
        for path in repo["dirty_paths"]
    )
    historical_authorized = phase_a_ok and phase_b_ok and core_clean
    contract = {
        "schema_version": "1.0.0",
        "study_id": "phase_c_method_contract_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "frozen_for_historical_confrontation" if historical_authorized else "synthetic_contract_frozen_historical_gate_closed",
        "scope": {
            "historical_tuning": False,
            "historical_authorized": historical_authorized,
            "historical_authorization_rule": "A1-A5/A7 and B pass, and the core boundary is clean; otherwise historical claims remain unauthorized.",
            "historical_cases": ["Nepal 2001-2006", "Afghanistan 2004-2021"],
            "historical_confrontation_once_only": True,
        },
        "model": {
            "model_sha256": model_sha256(ROOT),
            "source_commit": repo["commit_hash"],
            "tracked_diff_sha256": repo["tracked_diff_sha256"],
            "core_boundary": ["src/pineland_sim/**/*.py", "pyproject.toml"],
            "core_clean": core_clean,
        },
        "inference_contract": {
            "latent_variables": [
                "state_vector_x_t",
                "organization_capacity",
                "civilian_access",
                "territorial_control",
                "belief_state",
                "logistics_readiness",
            ],
            "proposal": "frozen synthetic-validation proposal; no case-specific adaptation",
            "rao_blackwellization": "as preregistered in phase_b_inference_validation_protocol_v2.json",
            "mcse": "batch means / Monte Carlo standard error retained and reported",
            "ess_and_resampling": "ESS threshold and systematic resampling; genealogy retained",
            "missingness": "negative evidence retained; no silent imputation",
            "scoring": "predeclared synthetic scoring rules; historical score rules remain case-contract-defined",
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
        },
        "gate_failures": [
            reason for reason, failed in (
                ("phase_a_certificate_failed", not phase_a_ok),
                ("phase_b_synthetic_validation_failed", not phase_b_ok),
                ("core_boundary_not_clean", not core_clean),
            ) if failed
        ],
        "provenance": {
            "dirty_paths": repo["dirty_paths"],
            "contract_payload_sha256": canonical_sha256({
                "model_sha256": model_sha256(ROOT),
                "phase_a_sha256": file_sha256(phase_a_path),
                "phase_b_sha256": file_sha256(phase_b_path),
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
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "studies/research_program/phase_c_method_contract_v1.json",
    )
    args = parser.parse_args()
    result = run(args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
