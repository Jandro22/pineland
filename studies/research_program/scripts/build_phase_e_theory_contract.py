"""Specify the latent-state theory, reproduction quantity, predictions, and tests."""
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
    phase_b_path: Path | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite theory contract: {output}")
    phase_b_path = phase_b_path or ROOT / "studies/research_program/phase_b_inference_validation_v2.json"
    phase_d_path = phase_d_path or ROOT / "studies/research_program/phase_d_historical_confrontation_status_v1.json"
    phase_b = json.loads(phase_b_path.read_text(encoding="utf-8"))
    phase_d = json.loads(phase_d_path.read_text(encoding="utf-8"))
    latent_variables = [
        {"symbol": "O_{i,t}", "name": "organization capacity", "domain": "[0,1]"},
        {"symbol": "A_{i,t}", "name": "civilian access", "domain": "[0,1]"},
        {"symbol": "C_{i,t}", "name": "territorial control", "domain": "[-1,1]"},
        {"symbol": "B_{i,t}", "name": "belief state", "domain": "simplex over actor-local hypotheses"},
        {"symbol": "L_{i,t}", "name": "logistics readiness", "domain": "[0,1]"},
        {"symbol": "P_{i,t}", "name": "operational posture / presence", "domain": "[0,1]"},
        {"symbol": "H_{i,t}", "name": "local exposure / opportunity", "domain": "[0,∞)"},
    ]
    equations = {
        "capacity": "logit(O_{i,t+1}) = rho_O logit(O_{i,t}) + beta_OS support_{i,t} + beta_OC C_{i,t} - beta_OX attrition_{i,t} + eps^O_{i,t}",
        "access": "logit(A_{i,t+1}) = rho_A logit(A_{i,t}) + beta_AP P_{i,t} + beta_AL L_{i,t} - beta_AQ coercion_{i,t} + eps^A_{i,t}",
        "control": "C_{i,t+1} = clip(C_{i,t} + beta_CO O_{i,t} + beta_CA A_{i,t} - beta_CR response_{i,t} + eps^C_{i,t}, -1, 1)",
        "logistics": "L_{i,t+1} = clip(L_{i,t} + inflow_{i,t} - consumption_{i,t} - interdiction_{i,t}, 0, 1)",
        "belief": "B_{i,t+1} = Normalize(B_{i,t} * likelihood(observation_t | state_i,t))",
        "action_hazard": "lambda_{i,j,t} = H_{i,j,t} * exp(theta_0 + theta_O O_{i,t} + theta_A A_{i,t} + theta_C C_{i,t} + theta_L L_{i,t} + theta_B f(B_{i,t}))",
        "reproduction_quantity": "R_t = sum_{new footholds j} E[1{j becomes active by t+Delta} | active footholds at t] / max(1, active footholds_t)",
    }
    predictions = [
        {"id": "P1", "prediction": "Holding exposure fixed, higher civilian access raises delayed foothold survival through capacity accumulation.", "falsifier": "No increase or a sign reversal across preregistered synthetic contrasts."},
        {"id": "P2", "prediction": "Logistics shocks reduce realized action through readiness before they reduce latent organizational capacity.", "falsifier": "Capacity and action move synchronously with no readiness mediation."},
        {"id": "P3", "prediction": "Belief uncertainty broadens action-location dispersion rather than simply scaling total action.", "falsifier": "Uncertainty changes total intensity only, with no dispersion effect."},
        {"id": "P4", "prediction": "R_t crosses below one after sustained access or logistics loss, preceding extinction of active footholds.", "falsifier": "Extinction occurs with R_t consistently above one or R_t never responds to the shock."},
        {"id": "P5", "prediction": "Spatially connected access produces clustered, parent-attributed colonization rather than independent uniform ignition.", "falsifier": "Placebo topology and true topology yield indistinguishable parent attribution."},
    ]
    test_matrix = {
        "synthetic_identification": ["vary one structural coefficient at a time", "recover sign and ordering from blinded simulations", "report posterior coverage and RMSE in posterior SD"],
        "placebos": ["permute spatial adjacency", "shuffle observation timestamps", "replace belief update with prior-only", "randomize parent attribution"],
        "ablations": ["remove civilian access", "remove logistics", "remove territorial control", "remove information/belief channel", "remove organization ecology"],
        "robustness": ["seed panel", "particle-count ladder", "ESS threshold ladder", "proposal variance ladder", "missingness and observation-noise ladder"],
    }
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_e_theory_contract_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "theory_specified_synthetic_supported_historical_unconfronted",
        "latent_variables": latent_variables,
        "equations": equations,
        "predictions": predictions,
        "test_matrix": test_matrix,
        "evidence": {
            "synthetic_inference_validation": {
                "path": str(phase_b_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(phase_b_path),
                "passed": bool(phase_b.get("passed")),
            },
            "historical_confrontation": {
                "path": str(phase_d_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(phase_d_path),
                "passed": bool(phase_d.get("passed")),
            },
        },
        "claims_policy": "Equations and predictions are specified; no historical transfer claim is promoted without an authorized once-only confrontation.",
        "provenance": {
            "model_sha256": model_sha256(ROOT),
            "commit": repository_state(ROOT)["commit_hash"],
            "payload_sha256": canonical_sha256({"equations": equations, "predictions": predictions}),
            "builder_sha256": file_sha256(Path(__file__)),
        },
        "passed": bool(phase_b.get("passed")) and bool(phase_d.get("passed")),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/phase_e_theory_contract_v1.json")
    parser.add_argument("--phase-d", type=Path)
    parser.add_argument("--phase-b", type=Path)
    args = parser.parse_args()
    result = run(
        args.output.resolve(),
        phase_d_path=args.phase_d.resolve() if args.phase_d else None,
        phase_b_path=args.phase_b.resolve() if args.phase_b else None,
    )
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
