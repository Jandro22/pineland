"""Write a fail-closed readiness snapshot for the comparative case ladder."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CASES = ("colombia_1984_2016", "iraq_2003_2011", "vietnam_1955_1975")


def load_validator():
    path = ROOT / "studies/research_program/scripts/validate_case_readiness.py"
    spec = importlib.util.spec_from_file_location("validate_case_readiness", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/case_readiness_snapshot.json")
    args = parser.parse_args()
    validator = load_validator()
    rows = []
    for case_id in CASES:
        case_root = ROOT / "studies" / case_id
        contract = json.loads((case_root / "config/case_contract.json").read_text(encoding="utf-8"))
        rows.append({
            "case_id": case_id,
            "status": contract["status"],
            "readiness": validator.validate(contract, case_root),
        })
    payload = {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "generated_from": "validate_case_readiness.py",
        "cases": rows,
        "all_cases_ready": all(row["readiness"]["passed"] for row in rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
