"""Validate the preregistered COIN intervention design without running simulations."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
REQUIRED_OUTCOMES = {
    "violence",
    "control",
    "civilian_harm",
    "institutional_capacity",
    "insurgent_regeneration",
    "foreign_dependence",
    "recurrence",
}


def load_contract(path: Path | None = None) -> dict[str, Any]:
    target = path or ROOT / "studies" / "research_program" / "coin_interventions.json"
    return json.loads(target.read_text(encoding="utf-8"))


def validate(contract: dict[str, Any]) -> dict[str, Any]:
    interventions = contract.get("interventions", [])
    ids = [item.get("id") for item in interventions]
    checks = {
        "design_not_efficacy_claim": contract.get("status") == "preregistered_design_not_efficacy_claim",
        "seven_dimensional_outcome_vector": set(contract.get("outcome_vector", [])) == REQUIRED_OUTCOMES,
        "unique_intervention_ids": len(ids) == len(set(ids)) and all(ids),
        "minimum_intervention_families": len(interventions) >= 8,
        "each_intervention_has_contrast": all(bool(item.get("contrast")) for item in interventions),
        "each_intervention_has_falsifier": all(bool(item.get("falsifier")) for item in interventions),
        "each_intervention_has_primary_outcomes": all(
            set(item.get("primary_outcomes", [])) <= REQUIRED_OUTCOMES and item.get("primary_outcomes")
            for item in interventions
        ),
        "full_outcome_reporting": "Report the full outcome vector and Pareto tradeoffs; do not rank policies by violence alone." in contract.get("analysis_rules", []),
        "holdout_calibration_forbidden": contract.get("license", {}).get("calibration_on_holdout") is False,
        "violence_only_optimization_forbidden": contract.get("license", {}).get("optimize_violence_alone") is False,
    }
    return {"passed": all(checks.values()), "checks": checks, "intervention_count": len(interventions)}


def main() -> int:
    result = validate(load_contract())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
