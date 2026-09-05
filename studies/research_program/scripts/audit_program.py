"""Audit the frozen core and comparative research-program stage gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_evidence(root: Path, record: Any, model_hash: str,
                    expected_path: str | None = None) -> dict[str, Any]:
    """Verify pinned evidence; legacy path-only references never certify a stage.

    Bindings must be captured by the producing run, not reconstructed from the
    present checkout. Missing or malformed evidence fails closed.
    """
    from pineland_sim.reproducibility import audit_run_manifest, file_sha256

    checks: dict[str, bool] = {}
    try:
        if not isinstance(record, dict):
            return {"valid": False, "reason": "legacy_path_only_unverified"}
        def pinned_file(item):
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("evidence path escapes repository")
            if file_sha256(path) != item["sha256"]:
                raise ValueError("file hash mismatch: " + item["path"])
            return path

        status = record.get("status")
        if status == "verified_pinned_file":
            artifact_record = record["artifact"]
            pinned_file(artifact_record)
            checks["expected_path"] = (
                expected_path is None or artifact_record.get("path") == expected_path
            )
            return {"valid": all(checks.values()), "checks": checks}

        if status != "verified_run_evidence":
            return {"valid": False, "reason": record.get("reason", "evidence_not_verified")}

        artifact_record = record["artifact"]
        artifact = pinned_file(artifact_record)
        manifest = _load(pinned_file(record["run_manifest"]))
        checks["manifest_contract"] = audit_run_manifest(manifest)["valid"]
        checks["model_hash"] = manifest.get("model_sha256") == model_hash
        expected = record["expected"]
        for key in ("model_sha256", "config_sha256", "case_data_hashes", "split_sha256"):
            checks[key] = bool(expected.get(key)) and manifest.get(key) == expected[key]
        checks["frozen_model"] = expected.get("model_sha256") == model_hash
        extra = manifest.get("extra", {})
        checks["expected_stage"] = bool(record.get("expected_stage")) and extra.get("stage") == record["expected_stage"]
        checks["artifact_bound_to_run"] = extra.get("artifacts", {}).get(
            artifact.relative_to(root.resolve()).as_posix()
        ) == record["artifact"]["sha256"]
        artifact_model = record.get("artifact_model_sha256")
        if artifact_model is not None:
            checks["artifact_model_sha256"] = artifact_model == model_hash
        return {"valid": all(checks.values()), "checks": checks}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"valid": False, "checks": checks, "reason": str(exc)}


def audit_program(root: Path = ROOT) -> dict[str, Any]:
    from pineland_sim.reproducibility import canonical_sha256, file_sha256, model_sha256, repository_state

    program = root / "studies" / "research_program"
    freeze = _load(program / "core_freeze.json")
    ladder = _load(program / "case_ladder.json")
    mechanisms = _load(program / "mechanism_registry.json")
    coin = _load(program / "coin_interventions.json")
    theory_protocol = _load(program / "theory_extraction_protocol.json")
    theory_matrix = _load(program / "theory_status_matrix.json")
    comparative_matrix = _load(program / "comparative_theory_promotion_matrix.json")
    signature_benchmark = _load(program / "historical_reproduction_signature_benchmark.json")
    change_ledger = _load(program / "core_change_classification_ledger.json")
    event_signature = _load(program / "event_only_spatial_signature_diagnostic.json")
    harmonized_signature = _load(program / "harmonized_historical_event_signatures.json")
    competitor_benchmark = _load(program / "historical_signature_competitor_benchmark.json")
    actor_diagnostic = _load(program / "actor_continuity_diagnostic.json")
    assignment_sensitivity = _load(program / "historical_assignment_sensitivity.json")
    signature_manifest = _load(program / "historical_signature_artifact_manifest.json")
    timebase_evidence = _load(program / "timebase_repair_evidence.json")
    control_observation_recovery = _load(
        root / "studies" / "afghanistan_2004_2021" / "results" / "control_observation_synthetic_recovery.json"
    )
    nepal_structural_preflight = _load(
        root / "studies" / "nepal_2001_2006" / "results" / "post_structural_repair" / "structural_repair_manifest.json"
    )
    afghanistan_initialization_preflight = _load(
        program / "afghanistan_initialization_preflight.json"
    )
    afghanistan_initialization_manifest = _load(
        program / "afghanistan_initialization_preflight_manifest.json"
    )
    afghanistan_smoke_preflight = _load(
        program / "afghanistan_current_core_smoke_preflight.json"
    )
    afghanistan_smoke_manifest = _load(
        program / "afghanistan_current_core_smoke_preflight_manifest.json"
    )
    afghanistan_year_preflight = _load(
        program / "afghanistan_current_core_year_preflight.json"
    )
    afghanistan_year_manifest = _load(
        program / "afghanistan_current_core_year_preflight_manifest.json"
    )
    current_core_contact_pilot = _load(
        program / "contact_challenge_current_core_pilot.json"
    )
    current_core_contact_manifest = _load(
        program / "contact_challenge_current_core_pilot_manifest.json"
    )
    contact_hazard_sensitivity = _load(
        program / "afghanistan_contact_hazard_sensitivity.json"
    )
    contact_hazard_sensitivity_manifest = _load(
        program / "afghanistan_contact_hazard_sensitivity_manifest.json"
    )
    nepal_smoke_preflight = _load(
        program / "nepal_current_core_smoke_preflight.json"
    )
    nepal_smoke_manifest = _load(
        program / "nepal_current_core_smoke_preflight_manifest.json"
    )
    contact_challenge = _load(program / "contact_challenge_eight_seed_replication.json")
    contact_challenge_manifest = _load(program / "contact_challenge_eight_seed_replication_manifest.json")
    challenge_contract = _load(program / "spatial_factorial_contact_challenge_contract.json")
    outcome_contract = _load(program / "outcome_measurement_contract.json")
    checklist = _load(program / "moonshot_checklist.json")
    v5_action_validation = _load(program / "v5_action_architecture_validation.json")
    certificate = _load(root / freeze["authoritative_certificate"])
    certificate_digest = certificate.get("certificate_payload_sha256")
    certificate_body = dict(certificate)
    certificate_body.pop("certificate_payload_sha256", None)
    certificate_checks = {
        "status_certified": certificate.get("status") == "CERTIFIED",
        "payload_hash_valid": canonical_sha256(certificate_body) == certificate_digest,
        "payload_hash_pinned": certificate_digest == freeze["certificate_payload_sha256"],
        "model_hash_pinned": certificate["repository"]["model_sha256"] == freeze["model_sha256"],
        "tracked_diff_pinned": certificate["repository"]["tracked_diff_sha256"] == freeze["tracked_diff_sha256"],
        "all_certification_conditions": all(certificate["certification_conditions"].values()),
    }

    live_model_hash = model_sha256(root)
    live_repository = repository_state(root)
    historical_revalidation_pending = (
        freeze.get("historical_revalidation", {}).get("required") is True
        and freeze.get("status") == "frozen_for_historical_revalidation"
    )
    freeze_checks = {
        "model_hash_matches": live_model_hash == freeze["model_sha256"],
        "commit_matches": live_repository["commit_hash"] == freeze["commit"],
        "tracked_diff_matches": live_repository["tracked_diff_sha256"] == freeze["tracked_diff_sha256"],
        "case_fit_cannot_justify_core_change": freeze["change_rule"]["case_fit_is_sufficient"] is False,
        "calibration_not_licensed": freeze["calibration_licensed"] is False,
    }

    records = freeze.get("evidence_records", {})
    certification_keys = freeze.get("certification_evidence_keys")
    if certification_keys is None:
        # Backward compatibility for pre-v4 freezes, where every path-like
        # freeze-basis item was implicitly treated as certification evidence.
        certification_keys = [
            name for name, relative in freeze["freeze_basis"].items()
            if isinstance(relative, str) and ("/" in relative or "\\" in relative)
        ]
    evidence_details = {
        name: verify_evidence(
            root,
            records.get(name, freeze["freeze_basis"].get(name)),
            freeze["model_sha256"],
            freeze["freeze_basis"].get(name),
        )
        for name in certification_keys
    }
    evidence = {name: detail["valid"] for name, detail in evidence_details.items()}
    cases = ladder["cases"]
    orders = [case["order"] for case in cases]
    ladder_checks = {
        "unique_case_ids": len({case["case_id"] for case in cases}) == len(cases),
        "strict_order": orders == list(range(1, len(cases) + 1)),
        "nepal_falsification_preserved": cases[0]["status"] == "completed_falsification",
        "afghanistan_is_first_transfer": cases[1]["role"] == "first_transfer",
        "future_cases_not_claimed_complete": all(
            case["status"] in {"not_started", "data_construction", "preregistered"}
            for case in cases[2:]
        ),
        "promotion_gates_complete": len(ladder["promotion_gates"]) >= 8,
    }
    theory_checks = {
        "theory_is_candidate": mechanisms["theory_status"] == "candidate_to_be_falsified",
        "ri_is_not_claimed": mechanisms["reproduction_quantity"]["status"]
        == "decomposed_estimands_not_claim",
        "reproduction_is_decomposed": {
            item.get("id")
            for item in mechanisms["reproduction_quantity"].get("primary_estimands", [])
        } == {
            "local_endogenous_ignition",
            "parent_attributed_cross_local_colonization",
            "foothold_deepening_force_formation",
            "post_establishment_survival",
        },
        "legacy_scalar_is_secondary": mechanisms["reproduction_quantity"].get(
            "legacy_scalar_R_I"
        ) == "deprecated_compatibility_only",
        "simple_competitors_required": len(mechanisms["competitor_classes"]) >= 3,
        "multidimensional_coin_outcomes": len(mechanisms["coin_outcome_vector"]) == 7,
    }
    coin_checks = {
        "design_not_efficacy_claim": coin["status"] == "preregistered_design_not_efficacy_claim",
        "nine_intervention_families": len(coin["interventions"]) >= 9,
        "full_outcome_vector": set(coin["outcome_vector"]) == set(mechanisms["coin_outcome_vector"]),
        "holdout_calibration_forbidden": coin["license"]["calibration_on_holdout"] is False,
        "violence_only_optimization_forbidden": coin["license"]["optimize_violence_alone"] is False,
        "all_interventions_have_falsifiers": all(item.get("falsifier") for item in coin["interventions"]),
    }
    protocol_checks = {
        "candidate_protocol_not_result": theory_protocol["status"] == "candidate_theory_protocol_not_result",
        "cycle_is_explicit": len(theory_protocol["candidate_cycle"]) == 7,
        "binding_conditions_declared": len(theory_protocol.get("candidate_binding_conditions", [])) >= 3,
        "negative_constraints_declared": len(theory_protocol.get("candidate_negative_constraints", [])) >= 3,
        "survival_criteria_are_cross_case": any("two cases" in item for item in theory_protocol["survival_criteria"]),
        "negative_results_required": "negative-result narrative" in theory_protocol["required_outputs_per_case"],
        "unresolved_claim_rule": theory_protocol["claim_rule"].startswith("No mechanism is promoted"),
    }
    outcome_checks = {
        "seven_outcomes_declared": set(outcome_contract["outcomes"]) == set(mechanisms["coin_outcome_vector"]),
        "measurement_operators_declared": all(
            item.get("observation_operator") for item in outcome_contract["outcomes"].values()
        ),
        "violence_proxy_forbidden": "control" in outcome_contract["outcomes"]["violence"]["proxy_forbidden"],
        "control_proxy_forbidden": "violence" in outcome_contract["outcomes"]["control"]["proxy_forbidden"],
        "missingness_rule": any("reported as missing" in rule for rule in outcome_contract["rules"]),
    }
    challenge_checks = {
        "synthetic_only": (
            challenge_contract.get("historical_outcomes_used") is False and
            challenge_contract.get("historical_parameter_fitting") is False and
            challenge_contract.get("core_change_licensed") is False
        ),
        "preregistered_not_run": challenge_contract.get("status") == "preregistered_synthetic_challenge_not_run",
        "four_cells_declared": challenge_contract.get("design", {}).get("cells") == 4,
        "focal_pair_declared": bool(challenge_contract.get("design", {}).get("focal_pair")),
        "acceptance_gate_declared": bool(challenge_contract.get("acceptance_gate")),
    }
    theory_matrix_checks = {
        "candidate_not_general": theory_matrix.get("status") == "candidate_theory_not_general",
        "claims_have_status": bool(theory_matrix.get("claims")) and all(
            item.get("status") for item in theory_matrix.get("claims", [])
        ),
        "promotion_rule_declared": bool(theory_matrix.get("promotion_rule")),
        "current_blockers_declared": len(theory_matrix.get("current_blockers", [])) >= 3,
    }
    comparative_matrix_checks = {
        "promotion_blocked": comparative_matrix.get("status") == "promotion_blocked_by_case_readiness_and_core_provenance",
        "all_ladder_cases_mapped": {
            case.get("case_id") for case in cases
        } == {
            case.get("case_id") for case in comparative_matrix.get("cases", [])
        },
        "all_claims_have_case_cells": bool(comparative_matrix.get("claims")) and all(
            set(item.get("case_cells", {})) == {
                case.get("case_id") for case in cases
            }
            for item in comparative_matrix.get("claims", [])
        ),
        "stable_theory_not_licensed": comparative_matrix.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
        "ineligible_rules_declared": len(comparative_matrix.get("ineligible_evidence_rules", [])) >= 4,
    }
    signature_benchmark_checks = {
        "diagnostic_not_causal": signature_benchmark.get("status") == "historical_signature_diagnostic_not_causal_reproduction",
        "historical_outcomes_declared": signature_benchmark.get("historical_outcomes_used") is True,
        "fitting_forbidden": signature_benchmark.get("historical_parameter_fitting") is False,
        "core_change_forbidden": signature_benchmark.get("core_change_licensed") is False,
        "all_ladder_cases_present": {
            case.get("case_id") for case in cases
        } == {
            case.get("case_id") for case in signature_benchmark.get("cases", [])
        },
        "nulls_required": len(signature_benchmark.get("nulls_required_before_promotion", [])) >= 3,
        "stable_theory_not_licensed": signature_benchmark.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    change_ledger_checks = {
        "observed_snapshot_matches_live": (
            change_ledger.get("observed_live_snapshot", {}).get("model_sha256") == live_model_hash and
            change_ledger.get("observed_live_snapshot", {}).get("tracked_diff_sha256") == live_repository["tracked_diff_sha256"]
        ),
        "snapshot_freeze_license_consistent": (
            change_ledger.get("observed_live_snapshot", {}).get(
                "superseding_freeze_licensed"
            ) is (live_model_hash == freeze["model_sha256"])
        ),
        "stability_check_declared": all(
            change_ledger.get("observed_live_snapshot", {}).get("stability_check", {}).get(key) is True
            for key in ("model_hash_equal", "tracked_diff_hash_equal")
        ),
        "all_change_groups_pending_or_classified": bool(change_ledger.get("change_groups")) and all(
            item.get("classification") in {"pending", "general_defect", "structural_change", "unresolved_drift", "infrastructure"}
            for item in change_ledger.get("change_groups", [])
        ),
        "all_change_groups_classified": bool(change_ledger.get("change_groups")) and all(
            item.get("classification") in {"general_defect", "structural_change", "unresolved_drift", "infrastructure"}
            for item in change_ledger.get("change_groups", [])
        ),
        "substantive_effect_flags_present": all(
            isinstance(item.get("substantive_model_effect"), bool)
            for item in change_ledger.get("change_groups", [])
        ),
        "all_changed_source_modules_accounted_for": (
            lambda changed, classified: not (changed - classified)
        )(
            {
                path for path in live_repository.get("dirty_paths", [])
                if path.startswith("src/pineland_sim/") and path.endswith(".py")
            },
            {
                path
                for item in change_ledger.get("change_groups", [])
                for path in item.get("paths", [])
            },
        ),
    }
    event_signature_checks = {
        "diagnostic_not_causal": event_signature.get("status") == "event_only_spatial_signature_diagnostic_not_causal",
        "historical_outcomes_declared": event_signature.get("historical_outcomes_used") is True,
        "fitting_forbidden": event_signature.get("historical_parameter_fitting") is False,
        "core_change_forbidden": event_signature.get("core_change_licensed") is False,
        "colombia_and_iraq_present": {
            item.get("case_id") for item in event_signature.get("cases", [])
        } == {"colombia_1984_2016", "iraq_2003_2011"},
        "placebo_and_shuffle_declared": (
            "temporal_lead_placebo" in json.dumps(event_signature) and
            bool(event_signature.get("topology_method"))
        ),
        "stable_theory_not_licensed": event_signature.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    harmonized_signature_checks = {
        "diagnostic_not_causal": harmonized_signature.get("status") == "harmonized_historical_event_signature_not_causal",
        "four_cases_present": {
            item.get("case_id") for item in harmonized_signature.get("cases", [])
        } == {
            "nepal_2001_2006", "afghanistan_2004_2021", "colombia_1984_2016", "iraq_2003_2011"
        },
        "monthly_harmonization_declared": harmonized_signature.get("frequency") == "monthly",
        "stratum_sensitivity_declared": (
            bool(harmonized_signature.get("stratum_sensitivity_definition"))
            and all(
                item.get("stratum_sensitivity")
                for item in harmonized_signature.get("cases", [])
                if item.get("case_id") in {"nepal_2001_2006", "afghanistan_2004_2021"}
            )
        ),
        "negative_constraints_declared": len(harmonized_signature.get("negative_constraints", [])) >= 3,
        "fitting_forbidden": harmonized_signature.get("historical_parameter_fitting") is False,
        "core_change_forbidden": harmonized_signature.get("core_change_licensed") is False,
        "stable_theory_not_licensed": harmonized_signature.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    competitor_benchmark_checks = {
        "benchmark_not_causal": competitor_benchmark.get("status") == "training_only_simple_competitor_benchmark_not_causal",
        "four_cases_present": {
            item.get("case_id") for item in competitor_benchmark.get("cases", [])
        } == {
            "nepal_2001_2006", "afghanistan_2004_2021", "colombia_1984_2016", "iraq_2003_2011"
        },
        "four_models_declared": len(competitor_benchmark.get("models", [])) == 4,
        "training_only": all(
            item.get("split", {}).get("type") == "deterministic_temporal_holdout"
            and item.get("split", {}).get("preregistered") is False
            for item in competitor_benchmark.get("cases", [])
        ),
        "local_lift_positive_in_each_case": all(
            (item.get("brier_lift_over_baseline", {}).get("local_state") or 0) > 0
            for item in competitor_benchmark.get("cases", [])
        ),
        "rolling_origin_declared": all(
            len(item.get("rolling_origin", {}).get("windows", [])) == 3
            and item.get("rolling_origin", {}).get("train_fractions") == [0.5, 0.6, 0.7]
            for item in competitor_benchmark.get("cases", [])
        ),
        "rolling_local_lift_positive_in_each_case": all(
            item.get("rolling_origin", {}).get("positive_brier_lift_counts", {}).get("local_state") == 3
            for item in competitor_benchmark.get("cases", [])
        ),
        "rolling_combined_lift_positive_in_each_case": all(
            item.get("rolling_origin", {}).get("positive_brier_lift_counts", {}).get("local_plus_neighbor") == 3
            for item in competitor_benchmark.get("cases", [])
        ),
        "stratum_sensitivity_declared": (
            bool(competitor_benchmark.get("stratum_sensitivity_definition"))
            and all(
                item.get("stratum_sensitivity")
                for item in competitor_benchmark.get("cases", [])
                if item.get("case_id") in {"nepal_2001_2006", "afghanistan_2004_2021"}
            )
        ),
        "stratum_negative_results_preserved": any(
            (stratum.get("brier_lift_over_baseline", {}).get("local_state") or 0.0) < 0
            for item in competitor_benchmark.get("cases", [])
            for stratum in item.get("stratum_sensitivity", [])
        ),
        "combined_model_best_in_each_case": all(
            item.get("holdout_scores", {}).get("local_plus_neighbor", {}).get("brier")
            is not None and item["holdout_scores"]["local_plus_neighbor"]["brier"] <= min(
                score.get("brier") for name, score in item.get("holdout_scores", {}).items()
                if score.get("brier") is not None
            )
            for item in competitor_benchmark.get("cases", [])
        ),
        "simulator_fit_forbidden": competitor_benchmark.get("simulator_parameter_fitting") is False,
        "core_change_forbidden": competitor_benchmark.get("core_change_licensed") is False,
        "stable_theory_not_licensed": competitor_benchmark.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    actor_diagnostic_checks = {
        "diagnostic_not_causal": actor_diagnostic.get("status") == "recorded_dyad_continuity_diagnostic_not_causal",
        "two_cases_present": {
            item.get("case_id") for item in actor_diagnostic.get("cases", [])
        } == {"nepal_2001_2006", "afghanistan_2004_2021"},
        "identity_guard_declared": bool(actor_diagnostic.get("identity_unit")) and all(
            item.get("identity_guard") for item in actor_diagnostic.get("cases", [])
        ),
        "placebo_declared": "reverse_time_placebo" in json.dumps(actor_diagnostic),
        "fitting_forbidden": actor_diagnostic.get("historical_parameter_fitting") is False,
        "core_change_forbidden": actor_diagnostic.get("core_change_licensed") is False,
        "stable_theory_not_licensed": actor_diagnostic.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    assignment_sensitivity_checks = {
        "diagnostic_not_imputation": assignment_sensitivity.get("status") == "descriptive_assignment_coverage_not_imputation",
        "two_cases_present": {
            item.get("case_id") for item in assignment_sensitivity.get("cases", [])
        } == {"nepal_2001_2006", "afghanistan_2004_2021"},
        "historical_outcomes_declared": assignment_sensitivity.get("historical_outcomes_used") is True,
        "fitting_forbidden": assignment_sensitivity.get("historical_parameter_fitting") is False,
        "core_change_forbidden": assignment_sensitivity.get("core_change_licensed") is False,
        "coverage_is_explicit": all(
            item.get("raw_event_rows", 0) >= item.get("assigned_rows", 0) >= 0
            and item.get("unassigned_rows", -1) == item.get("raw_event_rows", 0) - item.get("assigned_rows", 0)
            for item in assignment_sensitivity.get("cases", [])
        ),
        "stable_theory_not_licensed": assignment_sensitivity.get("promotion_decision", {}).get(
            "stable_general_theory_licensed"
        ) is False,
    }
    control_observation_recovery_checks = {
        "synthetic_only": control_observation_recovery.get("historical_target_used_for_fit") is False,
        "operator_prospective": control_observation_recovery.get("operator_status") == "prospective_unfitted_observation_operator",
        "recovery_passed": control_observation_recovery.get("passed") is True,
        "accuracy_gate": control_observation_recovery.get("recovery", {}).get("accuracy", 0.0) >= 0.75,
        "recovery_not_historical_fit": control_observation_recovery.get("recovery", {}).get(
            "status"
        ) == "synthetic_observation_recovery_not_historical_fit",
    }
    current_core_preflight_checks = {
        "nepal_construct_checks_pass": nepal_structural_preflight.get("all_checks_pass") is True,
        # The structural-repair manifest is immutable provenance for the
        # snapshot on which those repair checks were first established.  It is
        # intentionally *not* rewritten to claim production by a later core.
        # Current-core binding is checked separately by
        # ``current_core_nepal_smoke`` below.
        "nepal_structural_snapshot_preserved": (
            bool(nepal_structural_preflight.get("model_sha256"))
            and bool(nepal_structural_preflight.get("tracked_diff_sha256"))
            and nepal_structural_preflight.get("model_sha256") != live_model_hash
        ),
        "nepal_no_parameter_fit": nepal_structural_preflight.get("parameter_fit") is False,
        "nepal_no_study_period_outcomes_for_repairs": nepal_structural_preflight.get(
            "study_period_outcomes_used_for_repairs"
        ) is False,
        "afghanistan_initialization_gate_pass": afghanistan_initialization_preflight.get(
            "initialization_gate", {}
        ).get("passed") is True,
        "afghanistan_binding_or_explicit_revalidation_pending": (
            afghanistan_initialization_preflight.get("model_sha256") == live_model_hash
            or (
                historical_revalidation_pending
                and bool(afghanistan_initialization_preflight.get("model_sha256"))
                and afghanistan_initialization_preflight.get("model_sha256") != live_model_hash
            )
        ),
        "afghanistan_run_stable": (
            afghanistan_initialization_preflight.get("model_hash_stable_during_run") is True
            and afghanistan_initialization_preflight.get("repository_stable_during_run") is True
        ),
        "afghanistan_no_historical_fit": (
            afghanistan_initialization_preflight.get("historical_outcomes_used") is False
            and afghanistan_initialization_preflight.get("historical_parameter_fitting") is False
            and afghanistan_initialization_preflight.get("core_change_licensed") is False
        ),
        "afghanistan_manifest_status": afghanistan_initialization_manifest.get("status")
        == "current_core_initialization_preflight_manifest",
        "afghanistan_artifact_hash_matches": file_sha256(
            root / afghanistan_initialization_manifest["artifact"]["path"]
        ) == afghanistan_initialization_manifest["artifact"]["sha256"],
        "afghanistan_builder_hash_matches": file_sha256(
            root / afghanistan_initialization_manifest["builder"]["path"]
        ) == afghanistan_initialization_manifest["builder"]["sha256"],
        "preflight_not_transfer_claim": (
            afghanistan_initialization_preflight.get("status")
            == "current_core_initialization_preflight_not_transfer"
        ),
    }
    current_core_smoke_checks = {
        "diagnostic_status": afghanistan_smoke_preflight.get("status")
        == "current_core_smoke_impact_diagnostic_not_transfer",
        "integrity_passed": afghanistan_smoke_preflight.get("integrity_passed") is True,
        "binding_or_explicit_revalidation_pending": (
            afghanistan_smoke_preflight.get("model_sha256") == live_model_hash
            or (
                historical_revalidation_pending
                and bool(afghanistan_smoke_preflight.get("model_sha256"))
                and afghanistan_smoke_preflight.get("model_sha256") != live_model_hash
            )
        ),
        "run_stable": (
            afghanistan_smoke_preflight.get("model_hash_stable_during_run") is True
            and afghanistan_smoke_preflight.get("repository_stable_during_run") is True
        ),
        "historical_scoring_not_fit": (
            afghanistan_smoke_preflight.get("historical_outcomes_used") is True
            and afghanistan_smoke_preflight.get("historical_parameter_fitting") is False
        ),
        "core_change_not_licensed": afghanistan_smoke_preflight.get("core_change_licensed") is False,
        "zero_contact_limitation_preserved": (
            afghanistan_smoke_preflight.get("run", {}).get("violence_validation", {}).get("latent_contacts") == 0
            and afghanistan_smoke_preflight.get("run", {}).get("violence_validation", {}).get("recorded_contacts") == 0
        ),
        "manifest_status": afghanistan_smoke_manifest.get("status")
        == "current_core_smoke_impact_diagnostic_manifest",
        "artifact_hash_matches": file_sha256(
            root / afghanistan_smoke_manifest["artifact"]["path"]
        ) == afghanistan_smoke_manifest["artifact"]["sha256"],
        "builder_hash_matches": file_sha256(
            root / afghanistan_smoke_manifest["builder"]["path"]
        ) == afghanistan_smoke_manifest["builder"]["sha256"],
        "not_transfer_claim": "not a transfer result" in afghanistan_smoke_preflight.get(
            "interpretation", ""
        ),
    }
    current_core_year_checks = {
        "diagnostic_status": afghanistan_year_preflight.get("status")
        == "current_core_smoke_impact_diagnostic_not_transfer",
        "one_year_horizon": afghanistan_year_preflight.get("horizon_days") == 365.0,
        "integrity_passed": afghanistan_year_preflight.get("integrity_passed") is True,
        # This is an intentionally preserved long-horizon diagnostic.  It is
        # content-addressed to the source snapshot that produced it; after a
        # later live-core edit it must not be treated as a current-core result.
        "snapshot_binding_recorded": bool(afghanistan_year_preflight.get("model_sha256")),
        "run_stable": (
            afghanistan_year_preflight.get("model_hash_stable_during_run") is True
            and afghanistan_year_preflight.get("repository_stable_during_run") is True
        ),
        "historical_scoring_not_fit": (
            afghanistan_year_preflight.get("historical_outcomes_used") is True
            and afghanistan_year_preflight.get("historical_parameter_fitting") is False
        ),
        "core_change_not_licensed": afghanistan_year_preflight.get("core_change_licensed") is False,
        "nonzero_contact_constraint_recorded": (
            afghanistan_year_preflight.get("run", {}).get("violence_validation", {}).get("latent_contacts", 0) >= 1
            and afghanistan_year_preflight.get("run", {}).get("violence_validation", {}).get("recorded_contacts", 0)
            <= afghanistan_year_preflight.get("run", {}).get("violence_validation", {}).get("latent_contacts", 0)
        ),
        "gate_is_structural_not_transfer": afghanistan_year_preflight.get("run", {}).get(
            "gate", {}
        ).get("passed") is True,
        "manifest_status": afghanistan_year_manifest.get("status")
        == "current_core_smoke_impact_diagnostic_manifest",
        "artifact_hash_matches": file_sha256(
            root / afghanistan_year_manifest["artifact"]["path"]
        ) == afghanistan_year_manifest["artifact"]["sha256"],
        "builder_hash_matches": file_sha256(
            root / afghanistan_year_manifest["builder"]["path"]
        ) == afghanistan_year_manifest["builder"]["sha256"],
        "not_transfer_claim": "not a transfer result" in afghanistan_year_preflight.get(
            "interpretation", ""
        ),
    }
    current_core_contact_checks = {
        "pilot_status": current_core_contact_pilot.get("status")
        == "contact_challenge_pilot_synthetic_only",
        "synthetic_only": (
            current_core_contact_pilot.get("historical_outcomes_used") is False
            and current_core_contact_pilot.get("historical_parameter_fitting") is False
            and current_core_contact_pilot.get("core_change_licensed") is False
        ),
        "four_cells_complete": len(current_core_contact_pilot.get("cells", [])) == 4,
        "all_cells_have_contact": all(
            cell.get("metrics", {}).get("latent_contact_count", 0) >= 1
            for cell in current_core_contact_pilot.get("cells", [])
        ),
        "memory_contrast_positive": (
            next(
                (
                    cell["metrics"]["presence_memory_total_by_actor"]["insurgent"]
                    for cell in current_core_contact_pilot.get("cells", [])
                    if cell.get("presence_memory") == "symmetric_stationary_formation_memory"
                    and cell.get("destination_choice") == "current_live_policy"
                ),
                0.0,
            )
            > next(
                (
                    cell["metrics"]["presence_memory_total_by_actor"]["insurgent"]
                    for cell in current_core_contact_pilot.get("cells", [])
                    if cell.get("presence_memory") == "government_patrol_only"
                    and cell.get("destination_choice") == "current_live_policy"
                ),
                0.0,
            )
        ),
        "integrity_passed": current_core_contact_pilot.get("integrity_passed") is True,
        "snapshot_binding_recorded": (
            bool(current_core_contact_pilot.get("cells"))
            and all(
                bool(cell.get("manifest", {}).get("model_sha256"))
                for cell in current_core_contact_pilot.get("cells", [])
            )
        ),
        "acceptance_gate_remains_false": current_core_contact_pilot.get(
            "scientific_acceptance_gate_passed"
        ) is False,
        "manifest_status": current_core_contact_manifest.get("status")
        == "synthetic_pilot_provenance_manifest",
        "artifact_hash_matches": file_sha256(
            root / current_core_contact_manifest["artifact"]
        ) == current_core_contact_manifest["artifact_sha256"],
        "script_hash_matches": file_sha256(
            root / current_core_contact_manifest["script"]
        ) == current_core_contact_manifest["script_sha256"],
        "contract_hash_matches": file_sha256(
            root / current_core_contact_manifest["contract"]
        ) == current_core_contact_manifest["contract_sha256"],
    }
    hazard_sensitivity_checks = {
        "diagnostic_status": contact_hazard_sensitivity.get("status")
        == "current_core_contact_hazard_sensitivity_not_fit",
        "four_preregistered_runs": [
            run.get("contact_rate_multiplier")
            for run in contact_hazard_sensitivity.get("runs", [])
        ] == [0.5, 1.0, 2.0, 4.0],
        "integrity_passed": contact_hazard_sensitivity.get("integrity_passed") is True,
        # The hazard sweep is also retained as a snapshot-bound sensitivity
        # diagnostic.  Requiring the expensive sweep to be rerun after every
        # bounded source edit would obscure, rather than improve, provenance.
        "snapshot_binding_recorded": bool(contact_hazard_sensitivity.get("model_sha256")),
        "historical_scoring_not_fit": (
            contact_hazard_sensitivity.get("historical_outcomes_used") is True
            and contact_hazard_sensitivity.get("historical_parameter_fitting") is False
        ),
        "core_change_not_licensed": contact_hazard_sensitivity.get("core_change_licensed") is False,
        "mean_hazard_monotone": contact_hazard_sensitivity.get("monotone_mean_hazard") is True,
        "latent_contact_response_monotone": contact_hazard_sensitivity.get(
            "monotone_latent_contacts"
        ) is True,
        "baseline_zero_and_high_factor_nonzero": (
            contact_hazard_sensitivity.get("contact_counts", [None])[0] == 0
            and contact_hazard_sensitivity.get("contact_counts", [None, None, None, 0])[3] >= 1
        ),
        "manifest_status": contact_hazard_sensitivity_manifest.get("status")
        == "current_core_contact_hazard_sensitivity_manifest",
        "artifact_hash_matches": file_sha256(
            root / contact_hazard_sensitivity_manifest["artifact"]["path"]
        ) == contact_hazard_sensitivity_manifest["artifact"]["sha256"],
        "builder_hash_matches": file_sha256(
            root / contact_hazard_sensitivity_manifest["builder"]["path"]
        ) == contact_hazard_sensitivity_manifest["builder"]["sha256"],
        "contract_hash_matches": file_sha256(
            root / contact_hazard_sensitivity_manifest["contract"]["path"]
        ) == contact_hazard_sensitivity_manifest["contract"]["sha256"],
    }
    nepal_smoke_checks = {
        "diagnostic_status": nepal_smoke_preflight.get("status")
        == "current_core_nepal_smoke_diagnostic_not_transfer",
        "integrity_passed": nepal_smoke_preflight.get("integrity_passed") is True,
        "invariants_passed": nepal_smoke_preflight.get("invariants_passed") is True,
        "binding_or_explicit_revalidation_pending": (
            nepal_smoke_preflight.get("model_sha256") == live_model_hash
            or (
                historical_revalidation_pending
                and bool(nepal_smoke_preflight.get("model_sha256"))
                and nepal_smoke_preflight.get("model_sha256") != live_model_hash
            )
        ),
        "run_stable": (
            nepal_smoke_preflight.get("model_hash_stable_during_run") is True
            and nepal_smoke_preflight.get("repository_stable_during_run") is True
        ),
        "no_historical_fit": (
            nepal_smoke_preflight.get("historical_outcomes_used") is False
            and nepal_smoke_preflight.get("historical_parameter_fitting") is False
            and nepal_smoke_preflight.get("core_change_licensed") is False
        ),
        "population_conserved": abs(
            nepal_smoke_preflight.get("final_weighted_population", 0.0)
            - nepal_smoke_preflight.get("initial_weighted_population", 0.0)
        ) < 1e-6,
        "manifest_status": nepal_smoke_manifest.get("status")
        == "current_core_nepal_smoke_diagnostic_manifest",
        "artifact_hash_matches": file_sha256(
            root / nepal_smoke_manifest["artifact"]["path"]
        ) == nepal_smoke_manifest["artifact"]["sha256"],
        "builder_hash_matches": file_sha256(
            root / nepal_smoke_manifest["builder"]["path"]
        ) == nepal_smoke_manifest["builder"]["sha256"],
        "case_hash_matches": file_sha256(
            root / nepal_smoke_manifest["case"]["path"]
        ) == nepal_smoke_manifest["case"]["sha256"],
        "not_transfer_claim": "not a historical score" in nepal_smoke_preflight.get(
            "interpretation", ""
        ),
    }
    contact_challenge_checks = {
        "synthetic_only": (
            contact_challenge.get("historical_outcomes_used") is False
            and contact_challenge.get("historical_parameter_fitting") is False
            and contact_challenge.get("core_change_licensed") is False
        ),
        "replication_complete": (
            contact_challenge.get("seed_count") == 8
            and contact_challenge.get("cell_count") == 32
        ),
        "latent_contact_gate": contact_challenge.get("all_seeds_have_latent_contacts") is True,
        "presence_memory_contrast_gate": contact_challenge.get(
            "presence_memory_contrast_positive_every_seed"
        ) is True,
        "integrity_passed": contact_challenge.get("integrity_passed") is True,
        "scientific_acceptance_gate_passed": contact_challenge.get(
            "scientific_acceptance_gate_passed"
        ) is True,
        "core_uncertified_guard": contact_challenge.get("core_certificate", {}).get(
            "passed"
        ) is False,
        "manifest_status": contact_challenge_manifest.get("status")
        == "synthetic_replication_provenance_manifest",
        "artifact_hash_matches": file_sha256(
            root / contact_challenge_manifest["artifact"]["path"]
        )
        == contact_challenge_manifest["artifact"]["sha256"],
        "builder_hash_matches": file_sha256(
            root / contact_challenge_manifest["builder"]["path"]
        )
        == contact_challenge_manifest["builder"]["sha256"],
        "contract_hash_matches": file_sha256(
            root / contact_challenge_manifest["contract"]["path"]
        )
        == contact_challenge_manifest["contract"]["sha256"],
        "manifest_guardrails": (
            contact_challenge_manifest.get("historical_outcomes_used") is False
            and contact_challenge_manifest.get("historical_parameter_fitting") is False
            and contact_challenge_manifest.get("core_change_licensed") is False
        ),
    }
    manifest_checks = {
        "content_addressed_status": signature_manifest.get("status") == "content_addressed_historical_signature_artifacts",
        "four_artifacts_declared": len(signature_manifest.get("artifacts", [])) == 4,
        "artifact_hashes_match": all(
            file_sha256((root / item["path"]).resolve()) == item.get("sha256")
            for item in signature_manifest.get("artifacts", [])
        ),
        "builder_hashes_match": all(
            file_sha256((root / item["builder"]).resolve()) == item.get("builder_sha256")
            for item in signature_manifest.get("artifacts", [])
        ),
        "source_ref_hashes_match": all(
            file_sha256((root / ref["path"]).resolve()) == ref.get("sha256")
            for item in signature_manifest.get("artifacts", [])
            for ref in item.get("source_refs", [])
        ),
        "core_change_not_licensed": all(
            item.get("core_change_licensed") is False for item in signature_manifest.get("artifacts", [])
        ),
    }
    timebase_evidence_checks = {
        "data_free_only": timebase_evidence.get("historical_outcomes_used") is False,
        "general_defect_classified": timebase_evidence.get("classification") == "general_defect",
        "failure_reproduction_declared": bool(timebase_evidence.get("failure_reproduction", {}).get("counterexample")),
        "composition_contract_declared": bool(timebase_evidence.get("repair_contract", {}).get("composition_invariant")),
        "release_not_licensed": timebase_evidence.get("core_change_licensed") is False,
    }
    checklist_checks = {
        "eight_stages_declared": len(checklist.get("stages", [])) == 8,
        "unique_stage_numbers": len({stage.get("stage") for stage in checklist.get("stages", [])}) == 8,
        "completion_rule_declared": bool(checklist.get("completion_rule")),
        "remaining_work_is_explicit": all("remaining" in stage for stage in checklist.get("stages", [])),
    }
    v5_action_checks = {
        "synthetic_promotion_certified": v5_action_validation.get("status")
        == "synthetic_promotion_passed_core_certified",
        "current_model_bound": v5_action_validation.get("model_sha256") == live_model_hash,
        "historical_outcomes_not_used_to_define_equations": v5_action_validation.get(
            "historical_outcomes_used_to_define_equations"
        ) is False,
        "release_certificate_bound": v5_action_validation.get(
            "release_certificate", {}
        ).get("certificate_payload_sha256") == freeze.get("certificate_payload_sha256"),
        "bounded_forensic_equivalent": v5_action_validation.get(
            "bounded_forensic_equivalent"
        ) is True,
        "retention_behaviorally_equivalent": v5_action_validation.get(
            "retention_behaviorally_equivalent"
        ) is True,
        "endurance_model_stable": v5_action_validation.get("endurance_model_stable") is True,
        "historical_validation_pending": v5_action_validation.get(
            "historical_validation_status"
        ) == "not_run_on_v5",
        "coin_inference_blocked": v5_action_validation.get("coin_inference_authorized") is False,
    }
    sections = {
        "certificate": certificate_checks,
        "freeze": freeze_checks,
        "freeze_evidence": evidence,
        "case_ladder": ladder_checks,
        "theory": theory_checks,
        "coin_design": coin_checks,
        "theory_protocol": protocol_checks,
        "outcome_contract": outcome_checks,
        "challenge_contract": challenge_checks,
        "theory_status_matrix": theory_matrix_checks,
        "comparative_theory_promotion_matrix": comparative_matrix_checks,
        "historical_reproduction_signature_benchmark": signature_benchmark_checks,
        "core_change_classification_ledger": change_ledger_checks,
        "event_only_spatial_signature_diagnostic": event_signature_checks,
        "harmonized_historical_event_signatures": harmonized_signature_checks,
        "historical_signature_competitor_benchmark": competitor_benchmark_checks,
        "actor_continuity_diagnostic": actor_diagnostic_checks,
        "historical_assignment_sensitivity": assignment_sensitivity_checks,
        "control_observation_synthetic_recovery": control_observation_recovery_checks,
        "current_core_case_preflights": current_core_preflight_checks,
        "current_core_smoke_impact_diagnostic": current_core_smoke_checks,
        "current_core_year_impact_diagnostic": current_core_year_checks,
        "current_core_contact_challenge_pilot": current_core_contact_checks,
        "current_core_contact_hazard_sensitivity": hazard_sensitivity_checks,
        "current_core_nepal_smoke": nepal_smoke_checks,
        "contact_challenge_eight_seed_replication": contact_challenge_checks,
        "historical_signature_artifact_manifest": manifest_checks,
        "timebase_repair_evidence": timebase_evidence_checks,
        "moonshot_checklist": checklist_checks,
        "v5_action_architecture": v5_action_checks,
    }
    certificate_valid = all(certificate_checks.values())
    live_core_matches = all(freeze_checks.values())
    passed = all(all(checks.values()) for checks in sections.values())
    return {
        "schema_version": "1.1.0",
        "evidence_details": evidence_details,
        "passed": passed,
        "certificate_valid": certificate_valid,
        "live_core_matches_certificate": live_core_matches,
        "sections": sections,
        "live_model_sha256": live_model_hash,
        "frozen_model_sha256": freeze["model_sha256"],
        "current_stage": (
            "provenance_evidence_incomplete" if not all(evidence.values()) else
            "v5_frozen_historical_revalidation_pending"
            if historical_revalidation_pending and freeze.get("freeze_id") == "pineland-core-transfer-v5"
            else
            "post_first_transfer_diagnosis"
            if cases[1].get("status") == "completed_failed_first_transfer" and live_core_matches
            else "afghanistan_first_transfer" if live_core_matches
            else "transfer_paused_classified_core_drift_pending_impact"
        ),
        "calibration_licensed": False,
        "coin_inference_licensed": False,
        "program_complete": all(
            stage.get("status") in {"complete", "complete_falsification"}
            for stage in checklist.get("stages", [])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "program_audit.json")
    args = parser.parse_args()
    report = audit_program()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
