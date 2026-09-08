"""Gate the once-only historical confrontation; never substitute stale runs."""
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


def _hash_if_exists(path: Path) -> str | None:
    return file_sha256(path) if path.exists() else None


def run(output: Path, *, contract_path: Path | None = None) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite historical gate: {output}")
    contract_path = contract_path or ROOT / "studies/research_program/phase_c_method_contract_v1.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    historical_authorized = bool(contract.get("scope", {}).get("historical_authorized"))
    prior = ROOT / "studies/research_program/historical_revalidation_v5"
    evidence = {
        "prior_nepal_full_log": _hash_if_exists(prior / "nepal_full.log"),
        "prior_nepal_competition_log": _hash_if_exists(prior / "nepal_competition.log"),
        "prior_afghanistan_init_log": _hash_if_exists(prior / "afghanistan_init.log"),
        "prior_afghanistan_smoke_log": _hash_if_exists(prior / "afghanistan_smoke.log"),
        "prior_afghanistan_year_log": _hash_if_exists(prior / "afghanistan_year.log"),
        "prior_afghanistan_full_log": _hash_if_exists(prior / "afghanistan_full.log"),
    }
    result = {
        "schema_version": "1.0.0",
        "study_id": "phase_d_historical_confrontation_status_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "historical_confrontation_authorized" if historical_authorized else "historical_confrontation_not_authorized",
        "once_only_rule": {
            "required": True,
            "executed_under_current_contract": False,
            "historical_tuning_permitted": False,
            "negative_or_missing_results_preserved": True,
        },
        "case_plan": {
            "nepal": {
                "seeds_required": 8,
                "stages": ["full", "predictive_competition", "identical_row_reproducibility"],
                "status": "blocked_by_phase_c_gate" if not historical_authorized else "authorized_not_started",
            },
            "afghanistan": {
                "stages": ["init", "smoke", "one_year", "full_horizon", "identical_row_reproducibility"],
                "status": "blocked_by_phase_c_gate" if not historical_authorized else "authorized_not_started",
            },
        },
        "gate_reason": (
            "The current method contract does not authorize historical execution. Existing v5 logs are preserved as stale-core evidence and are not promoted."
            if not historical_authorized else
            "Authorization exists; this artifact is the pre-run gate and does not itself claim execution."
        ),
        "preserved_prior_evidence": evidence,
        "provenance": {
            "contract_path": str(contract_path.relative_to(ROOT)).replace("\\", "/"),
            "contract_sha256": file_sha256(contract_path),
            "current_model_sha256": model_sha256(ROOT),
            "commit": repository_state(ROOT)["commit_hash"],
            "status_payload_sha256": canonical_sha256(evidence),
        },
        "passed": historical_authorized,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/phase_d_historical_confrontation_status_v1.json")
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    result = run(
        args.output.resolve(),
        contract_path=args.contract.resolve() if args.contract else None,
    )
    print(json.dumps({"output": str(args.output.resolve()), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
