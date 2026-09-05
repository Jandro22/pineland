"""Validate question-specific inference sets and expose the unassessed remainder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
PLAN = ROOT / "studies" / "research_program" / "identifiability_plan.json"
OUT = ROOT / "studies" / "research_program" / "identifiability_triage.json"
HARD_MAX_ACTIVE_PARAMETERS = 15


def build(plan: dict) -> dict:
    from pineland_sim import SimulationConfig
    from pineland_sim.validation import parameter_registry

    registry = parameter_registry(SimulationConfig())
    by_name = {item.code_name: item for item in registry}
    maximum = int(plan["maximum_active_parameters_per_question"])
    questions = []
    errors = []
    assessed_names: set[str] = set()
    question_ids: set[str] = set()
    parameter_questions: dict[str, list[str]] = {}
    if plan.get("global_calibration_prohibited") is not True:
        errors.append({"global_calibration_prohibited": "must_be_true"})
    if not 1 <= maximum <= HARD_MAX_ACTIVE_PARAMETERS:
        errors.append({
            "invalid_maximum_active_parameters_per_question": maximum,
            "hard_maximum": HARD_MAX_ACTIVE_PARAMETERS,
        })
    for question in plan["questions"]:
        question_id = str(question.get("question_id") or "").strip()
        if not question_id:
            errors.append({"question_id": question_id, "missing_question_id": True})
        elif question_id in question_ids:
            errors.append({"question_id": question_id, "duplicate_question_id": True})
        question_ids.add(question_id)
        active = list(question["active_parameters"])
        duplicate_active = sorted({name for name in active if active.count(name) > 1})
        if duplicate_active:
            errors.append({"question_id": question_id, "duplicate_active_parameters": duplicate_active})
        missing = sorted(set(active) - set(by_name))
        if missing:
            errors.append({"question_id": question_id, "missing_parameters": missing})
        if not 1 <= len(active) <= min(maximum, HARD_MAX_ACTIVE_PARAMETERS):
            errors.append({"question_id": question_id, "invalid_active_parameter_count": len(active)})
        estimands = list(question.get("estimands") or [])
        mechanisms = list(question.get("mechanisms") or [])
        required_recovery = str(question.get("required_recovery") or "").strip()
        if not estimands or len(set(estimands)) != len(estimands) or any(not str(item).strip() for item in estimands):
            errors.append({"question_id": question_id, "invalid_estimands": estimands})
        if not mechanisms or len(set(mechanisms)) != len(mechanisms) or any(not str(item).strip() for item in mechanisms):
            errors.append({"question_id": question_id, "invalid_mechanisms": mechanisms})
        if not required_recovery:
            errors.append({"question_id": question_id, "missing_required_recovery": True})
        assessed_names.update(active)
        for name in set(active):
            parameter_questions.setdefault(name, []).append(question_id)
        known = [by_name[name] for name in active if name in by_name]
        structural_interventions = [
            item.code_name for item in known
            if item.assumption_type == "fixed structural assumption" or item.calibration_status == "fixed"
        ]
        inferential_parameters = [
            item.code_name for item in known if item.code_name not in structural_interventions
        ]
        questions.append({
            **question,
            "active_parameter_count": len(active),
            "inferential_parameter_count": len(inferential_parameters),
            "inferential_parameters": inferential_parameters,
            "structural_interventions": structural_interventions,
            "parameter_assumption_types": {
                item.code_name: item.assumption_type for item in known
            },
            "pre_historical_gate": "synthetic_recovery_required",
            "identifiability_status": "unassessed_pending_recovery",
        })
    status_counts: dict[str, int] = {}
    for item in registry:
        status_counts[item.identifiability_status] = status_counts.get(item.identifiability_status, 0) + 1
    return {
        "schema_version": "1.1.0",
        "valid": not errors,
        "errors": errors,
        "global_calibration_prohibited": plan.get("global_calibration_prohibited") is True,
        "hard_maximum_active_parameters_per_question": HARD_MAX_ACTIVE_PARAMETERS,
        "registry_parameter_count": len(registry),
        "registry_identifiability_counts": status_counts,
        "parameters_in_any_question": len(assessed_names),
        "parameters_outside_all_current_questions": len(registry) - len(assessed_names),
        "parameters_shared_across_questions": {
            name: ids for name, ids in sorted(parameter_questions.items()) if len(ids) > 1
        },
        "questions": questions,
        "license": (
            "No historical calibration until the question's synthetic estimand-recovery gate passes. "
            "Fixed structural assumptions may appear only as declared interventions, not inferred parameters."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    report = build(json.loads(args.plan.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
