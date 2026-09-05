"""Compile deterministic paper-preparation status from the live research program.

This script does not run the simulator, score historical outcomes, calibrate a
parameter, or promote a theory.  It translates existing research-program
contracts into a paper-facing status artifact and fails closed on unfinished
evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
PAPER = PROGRAM / "paper_prerequisites"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_record(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": _sha256(path),
    }


def _live_repository_state(root: Path) -> dict[str, Any]:
    """Use the project reproducibility implementation when importable.

    Missing imports fail closed rather than silently declaring the source
    stable.
    """
    try:
        from pineland_sim.reproducibility import model_sha256, repository_state

        state = repository_state(root)
        return {
            "available": True,
            "model_sha256": model_sha256(root),
            "commit_hash": state.get("commit_hash"),
            "tracked_diff_sha256": state.get("tracked_diff_sha256"),
        }
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return {
            "available": False,
            "model_sha256": None,
            "commit_hash": None,
            "tracked_diff_sha256": None,
            "reason": str(exc),
        }


def _claim_language_level(current_result: str) -> int:
    """Return only the paper-language level already licensed by the label.

    Historical descriptive or legacy evidence is deliberately *not* inferred
    to satisfy the case-supported level.  That promotion must come from case
    eligibility and frozen holdout evidence, not string interpretation.
    """
    label = current_result.lower()
    if "synthetic" in label or "pathway_recovered" in label:
        return 1
    return 0


def compile_status(root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    program = root / "studies" / "research_program"
    paper = program / "paper_prerequisites"

    freeze_path = program / "core_freeze.json"
    ladder_path = program / "case_ladder.json"
    theory_path = program / "theory_extraction_protocol.json"
    promotion_path = program / "comparative_theory_promotion_matrix.json"
    mechanism_path = program / "mechanism_registry.json"
    outcomes_path = program / "outcome_measurement_contract.json"
    architecture_path = paper / "manuscript_architecture.json"
    outputs_path = paper / "figure_table_registry.json"
    language_path = paper / "claim_language_contract.json"
    contribution_path = paper / "contribution_contract.json"
    literature_path = paper / "literature_gap_matrix.json"
    reproducibility_path = paper / "reproducibility_appendix_contract.json"
    negative_path = paper / "negative_result_ledger.json"

    inputs = [
        freeze_path,
        ladder_path,
        theory_path,
        promotion_path,
        mechanism_path,
        outcomes_path,
        architecture_path,
        outputs_path,
        language_path,
        contribution_path,
        literature_path,
        reproducibility_path,
        negative_path,
    ]
    freeze = _load(freeze_path)
    ladder = _load(ladder_path)
    theory = _load(theory_path)
    promotion = _load(promotion_path)
    mechanisms = _load(mechanism_path)
    outcomes = _load(outcomes_path)
    architecture = _load(architecture_path)
    outputs = _load(outputs_path)
    language = _load(language_path)
    contribution = _load(contribution_path)
    literature = _load(literature_path)
    negative = _load(negative_path)

    live = _live_repository_state(root)
    core_matches_freeze = bool(
        live["available"]
        and live["model_sha256"] == freeze.get("model_sha256")
        and live["commit_hash"] == freeze.get("commit")
        and live["tracked_diff_sha256"] == freeze.get("tracked_diff_sha256")
    )
    eligible_labels = set(promotion.get("eligible_case_statuses", []))
    eligible_cases = [
        case["case_id"]
        for case in promotion.get("cases", [])
        if case.get("eligibility") in eligible_labels
    ]
    general_licensed = bool(
        promotion.get("promotion_decision", {}).get("stable_general_theory_licensed")
    )
    mechanisms_unresolved = all(
        status == "unresolved" for status in theory.get("mechanism_statuses", {}).values()
    )

    safe_sections = [
        section["id"]
        for section in architecture.get("sections", [])
        if section.get("safe_now")
    ]
    blocked_sections = [
        section["id"]
        for section in architecture.get("sections", [])
        if section.get("blocked_until")
    ]
    safe_figures = [
        item["id"]
        for item in outputs.get("figures", [])
        if item.get("buildability", "").startswith("safe_now")
        or item.get("buildability", "").startswith("shell_now")
    ]
    blocked_figures = [
        item["id"]
        for item in outputs.get("figures", [])
        if item.get("buildability", "").startswith("blocked")
    ]
    safe_tables = [
        item["id"]
        for item in outputs.get("tables", [])
        if item.get("buildability", "").startswith("safe_now")
        or item.get("buildability", "").startswith("shell_now")
    ]
    blocked_tables = [
        item["id"]
        for item in outputs.get("tables", [])
        if item.get("buildability", "").startswith("blocked")
    ]

    paper_gates = {
        "research_declared_unfinished": contribution.get("research_status") == "unfinished",
        "candidate_theory_remains_replaceable": contribution.get("candidate_theory_is_replaceable") is True,
        "core_matches_active_freeze": core_matches_freeze,
        "mechanism_statuses_remain_unresolved": mechanisms_unresolved,
        "two_eligible_transfer_cases": len(eligible_cases) >= 2,
        "stable_general_theory_licensed": general_licensed,
        "multidimensional_outcomes_declared": set(outcomes.get("outcomes", {})) == set(
            mechanisms.get("coin_outcome_vector", [])
        ),
        "negative_result_ledger_active": negative.get("status") == "continuous_negative_result_ledger",
        "claim_language_starts_conservative": language.get("current_maximum_general_theory_level") == 0,
    }

    status = {
        "schema_version": "1.0.0",
        "status": "paper_prerequisites_in_progress_not_manuscript_result",
        "paper_target": contribution["paper_target"],
        "live_repository": live,
        "active_freeze": {
            "freeze_id": freeze.get("freeze_id"),
            "model_sha256": freeze.get("model_sha256"),
            "commit": freeze.get("commit"),
            "tracked_diff_sha256": freeze.get("tracked_diff_sha256"),
        },
        "paper_gates": paper_gates,
        "publication_claims_unlocked": bool(
            core_matches_freeze
            and len(eligible_cases) >= 2
            and general_licensed
        ),
        "eligible_transfer_cases": eligible_cases,
        "eligible_transfer_case_count": len(eligible_cases),
        "safe_to_build_now": {
            "section_ids": safe_sections,
            "figure_ids": safe_figures,
            "table_ids": safe_tables,
            "literature_domains": [item["id"] for item in literature.get("domains", []) if item.get("safe_to_compile_now")],
            "reproducibility_schema": True,
            "negative_result_ledger": True,
        },
        "blocked_from_finalization": {
            "section_ids": blocked_sections,
            "figure_ids": blocked_figures,
            "table_ids": blocked_tables,
            "final_abstract": True,
            "final_general_theory_propositions": True,
            "final_policy_implications": True,
        },
        "research_program_state": {
            "case_statuses": {
                case["case_id"]: case["status"] for case in ladder.get("cases", [])
            },
            "candidate_binding_conditions": theory.get("candidate_binding_conditions", []),
            "candidate_negative_constraints": theory.get("candidate_negative_constraints", []),
        },
        "input_artifacts": [_source_record(path) for path in inputs],
        "interpretation": (
            "This artifact reports what paper infrastructure can be built without "
            "promoting unfinished research. False publication_claims_unlocked is "
            "the expected state until final provenance, comparative transfer, and "
            "theory-promotion gates are all satisfied."
        ),
    }

    level_names = {
        item["level"]: item["id"] for item in language.get("levels", [])
    }
    claim_rows = []
    for claim in promotion.get("claims", []):
        level = _claim_language_level(str(claim.get("current_result", "")))
        claim_rows.append({
            "claim_id": claim.get("claim_id"),
            "candidate_claim": claim.get("claim"),
            "current_result": claim.get("current_result"),
            "current_language_level": level,
            "current_language_status": level_names.get(level, "conceptual_candidate"),
            "minimum_promotion_evidence": claim.get("minimum_promotion_evidence", []),
            "case_cells": claim.get("case_cells", {}),
            "general_theory_language_licensed": bool(general_licensed and level >= 4),
        })

    claim_matrix = {
        "schema_version": "1.0.0",
        "status": "paper_claim_evidence_matrix_not_general_theory",
        "stable_general_theory_licensed": general_licensed,
        "eligible_transfer_case_count": len(eligible_cases),
        "claims": claim_rows,
        "rule": (
            "This matrix can lag only toward weaker language. It must never "
            "promote a claim from synthetic, descriptive, legacy, or ineligible "
            "case evidence into historical or general support."
        ),
        "source_artifacts": [
            _source_record(promotion_path),
            _source_record(language_path),
        ],
    }
    return status, claim_matrix


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PAPER / "paper_prerequisite_status.json",
    )
    parser.add_argument(
        "--claim-output",
        type=Path,
        default=PAPER / "paper_claim_evidence_matrix.json",
    )
    args = parser.parse_args()
    status, claims = compile_status(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.claim_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    args.claim_output.write_text(json.dumps(claims, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status["status"],
        "publication_claims_unlocked": status["publication_claims_unlocked"],
        "eligible_transfer_case_count": status["eligible_transfer_case_count"],
        "core_matches_active_freeze": status["paper_gates"]["core_matches_active_freeze"],
        "claim_count": len(claims["claims"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

