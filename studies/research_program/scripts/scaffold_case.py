"""Create a preregistration-first comparative case package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def contract(case_id: str, role: str, start: str, end: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "role": role,
        "status": "preregistered",
        "period": {"start": start, "end": end},
        "construct_map": [
            {"construct": "violence", "source": None, "unit": None, "measurement_model": None},
            {"construct": "control_or_presence", "source": None, "unit": None, "measurement_model": None},
        ],
        "inputs": [
            {"construct": "geography", "source": None, "future_outcome_used": False},
            {"construct": "population", "source": None, "future_outcome_used": False},
            {"construct": "actor_existence", "source": None, "future_outcome_used": False},
        ],
        "observables": ["violence", "control_or_presence"],
        "holdouts": {
            "temporal": None,
            "geographic": None,
            "joint": None,
            "outcome_blind_selection": True,
        },
        "disabled_mechanisms": [],
        "case_input_uncertainty": ["geography", "population", "actor attribution"],
        "calibration": {"licensed": False, "training_only": True, "holdout_refit": False},
    }


def scaffold(destination: Path, payload: dict) -> None:
    if destination.exists():
        raise FileExistsError(f"case directory already exists: {destination}")
    for relative in ("config", "data/raw", "data/processed", "results", "runs", "scripts"):
        (destination / relative).mkdir(parents=True, exist_ok=True)
    (destination / "config" / "case_contract.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (destination / "README.md").write_text(
        f"# {payload['case_id']} comparative case\n\n"
        "Status: preregistered. Calibration is prohibited until the construct map, "
        "source manifests, outcome-blind holdouts, independent control/presence evidence, "
        "and structural gates are complete.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--role", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    destination = args.destination or ROOT / "studies" / args.case_id
    scaffold(destination, contract(args.case_id, args.role, args.start, args.end))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
