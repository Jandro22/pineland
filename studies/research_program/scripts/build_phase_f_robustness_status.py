"""Record robustness gates without upgrading unrun historical analyses."""
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

from pineland_sim.reproducibility import canonical_sha256, file_sha256, model_sha256, repository_state  # noqa: E402


def run(
    output: Path,
    *,
    phase_d_path: Path | None = None,
    phase_e_path: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite robustness status: {output}")
    program = ROOT / "studies/research_program"
    phase_b_path = program / "phase_b_inference_validation_v2.json"
    phase_d_path = phase_d_path or program / "phase_d_historical_confrontation_status_v1.json"
    phase_e_path = phase_e_path or program / "phase_e_theory_contract_v1.json"
    phase_b = json.loads(phase_b_path.read_text(encoding="utf-8"))
    phase_d = json.loads(phase_d_path.read_text(encoding="utf-8"))
    phase_e = json.loads(phase_e_path.read_text(encoding="utf-8"))
    gates = {
        "synthetic_seed_and_mcse_validation": bool(phase_b.get("passed")),
        "synthetic_placebos_and_ablations_specified": bool(phase_e.get("test_matrix")),
        "historical_case_robustness_executed": bool(phase_d.get("passed")),
        "historical_competing_observation_operators_executed": False,
        "cross_case_transfer_robustness_executed": False,
    }
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_f_robustness_status_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "robustness_synthetic_only" if not all(gates.values()) else "robustness_complete",
        "gates": gates,
        "design": {
            "seed_panel": "predeclared multi-seed panel; report all failures",
            "mcse": "report Monte Carlo standard errors with effective sample sizes",
            "placebos": "spatial adjacency permutation, timestamp shuffle, prior-only belief, random parent attribution",
            "ablations": "remove access, logistics, control, beliefs, and organization ecology one at a time",
            "missingness": "retain missing and negative observations; no favorable-case deletion",
            "cross_case": "Nepal and Afghanistan only after the once-only frozen confrontation is authorized",
        },
        "limitations": [
            "Historical robustness is not executed under the current contract because the historical gate is closed.",
            "The existing v5 historical logs are stale-core evidence and are not reused as current results.",
            "A failed performance gate remains a deployment limitation, not a scientific null result.",
        ],
        "evidence": {
            "phase_b": {"path": str(phase_b_path.relative_to(ROOT)).replace("\\", "/"), "sha256": file_sha256(phase_b_path)},
            "phase_d": {"path": str(phase_d_path.relative_to(ROOT)).replace("\\", "/"), "sha256": file_sha256(phase_d_path)},
            "phase_e": {"path": str(phase_e_path.relative_to(ROOT)).replace("\\", "/"), "sha256": file_sha256(phase_e_path)},
        },
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "commit": repository_state(ROOT)["commit_hash"],
            "payload_sha256": canonical_sha256(gates),
            "builder_sha256": file_sha256(Path(__file__)),
        },
        "passed": all(gates.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/phase_f_robustness_status_v1.json")
    parser.add_argument("--phase-d", type=Path)
    parser.add_argument("--phase-e", type=Path)
    args = parser.parse_args()
    result = run(
        args.output.resolve(),
        phase_d_path=args.phase_d.resolve() if args.phase_d else None,
        phase_e_path=args.phase_e.resolve() if args.phase_e else None,
    )
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
