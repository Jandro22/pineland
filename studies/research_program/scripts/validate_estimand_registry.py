"""Validate the prospective Pineland explanatory-target and estimand registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
REGISTRY_PATH = PROGRAM / "estimand_registry.json"
OUTCOME_PATH = PROGRAM / "outcome_measurement_contract.json"
INTERVENTION_PATH = PROGRAM / "coin_interventions.json"

OUTCOME_ORDER = [
    "violence",
    "control",
    "civilian_harm",
    "institutional_capacity",
    "insurgent_regeneration",
    "foreign_dependence",
    "recurrence",
]
SYMBOLS = {
    "violence": "V",
    "control": "C",
    "civilian_harm": "H",
    "institutional_capacity": "I",
    "insurgent_regeneration": "G",
    "foreign_dependence": "D",
    "recurrence": "R",
}
QUIET_STATES = {
    "organizational_loss",
    "accommodation",
    "clandestine_survival",
    "displacement",
    "reporting_failure",
    "dominance",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(path: Path | None = None) -> dict[str, Any]:
    return _load(path or REGISTRY_PATH)


def validate(
    registry: dict[str, Any],
    outcome_contract: dict[str, Any] | None = None,
    intervention_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outcome_contract = outcome_contract or _load(OUTCOME_PATH)
    intervention_contract = intervention_contract or _load(INTERVENTION_PATH)

    outcomes = registry.get("outcomes", {})
    time_contract = registry.get("time_contract", {})
    causal = registry.get("causal_policy_estimand", {})
    info = causal.get("policy_information_set", {})
    welfare = causal.get("welfare", {})
    aggregation = registry.get("aggregation_contract", {})
    target = registry.get("theory_target", {})
    expectation = target.get("expectation_population", {})
    resource_constraints = causal.get("intervention_resource_constraints", {})
    interventions = intervention_contract.get("interventions", [])
    intervention_ids = {item.get("id") for item in interventions}
    required_uncertainty = set(intervention_contract.get("license", {}).get("required_uncertainty", []))

    complete_outcomes = all(
        bool(outcomes.get(name, {}).get(field))
        for name in OUTCOME_ORDER
        for field in (
            "observable_definition",
            "denominator",
            "scale",
            "horizon_operator",
            "horizons_days",
            "falsifier",
        )
    )
    correct_symbols = all(outcomes.get(name, {}).get("symbol") == symbol for name, symbol in SYMBOLS.items())
    resources_complete = intervention_ids == set(resource_constraints) and all(
        rule.get("equalized") and rule.get("treatment_changes") and rule.get("must_measure")
        for rule in resource_constraints.values()
    )

    checks = {
        "prospective_not_fit_or_efficacy_claim": registry.get("status") == "preregistered_estimand_contract_not_fit_or_efficacy_claim",
        "inherits_existing_contracts": set(registry.get("inherits_from", [])) == {
            "studies/research_program/outcome_measurement_contract.json",
            "studies/research_program/coin_interventions.json",
        },
        "outcome_vector_order_frozen": registry.get("outcome_vector_order") == OUTCOME_ORDER
        and intervention_contract.get("outcome_vector") == OUTCOME_ORDER,
        "outcome_registry_matches_measurement_contract": set(outcomes) == set(outcome_contract.get("outcomes", {})) == set(OUTCOME_ORDER),
        "outcome_symbols_correct": correct_symbols,
        "observable_denominator_horizon_falsifier_complete": complete_outcomes,
        "mechanism_unit_defined": target.get("mechanism_unit", {}).get("unit") == "organization-locality-time",
        "observation_unit_defined": target.get("observation_unit", {}).get("unit") == "case-native administrative-unit-time",
        "spillover_unit_defined": target.get("spillover_unit", {}).get("unit") == "actor-network-edge-time",
        "aggregation_mapping_explicit": all(
            bool(aggregation.get(key))
            for key in ("spatial_crosswalk", "actor_rule", "time_rule", "population_weighting", "control_rule", "network_spillovers")
        ),
        "expectation_population_fixed": expectation.get("baseline_denominator_fixed") is True
        and required_uncertainty <= set(expectation.get("uncertainty_dimensions", [])),
        "evaluation_horizons_predeclared": time_contract.get("evaluation_horizons_days") == [30, 90, 365]
        and time_contract.get("chosen_from_historical_fit") is False
        and time_contract.get("sensitivity_policy", {}).get("primary_windows_remain_fixed") is True,
        "persistence_window_predeclared": time_contract.get("persistence", {}).get("window_days") == 90,
        "recurrence_window_predeclared": time_contract.get("recurrence", {}).get("qualifying_quiet_days") == 90
        and time_contract.get("recurrence", {}).get("followup_days") == 365
        and time_contract.get("recurrence", {}).get("short_term_violence_suppression_is_recurrence") is False,
        "six_quiet_states_distinguished": set(registry.get("quiet_state_registry", {})) == QUIET_STATES,
        "vector_estimand_registered": causal.get("estimand_id") == "Delta_c(g,g0;T)"
        and causal.get("vector_outcome_required") is True
        and bool(causal.get("structured_vector_rule"))
        and bool(causal.get("direction_convention")),
        "adaptive_policy_uses_measured_history_only": info.get("measured_past_history_only") is True
        and info.get("simulated_hidden_truth_access") is False
        and info.get("omniscient_policy_allowed_for_efficacy_claims") is False,
        "resource_constraints_cover_all_interventions": resources_complete,
        "scalar_welfare_not_implicit": welfare.get("scalar_welfare_defined") is False
        and welfare.get("weights") is None
        and welfare.get("lower_violence_implies_higher_welfare") is False,
        "global_falsifiers_registered": len(registry.get("global_falsifiers", [])) >= 6,
        "freeze_firewall": registry.get("freeze_rules", {}).get("historical_fit_may_choose_horizons") is False
        and registry.get("freeze_rules", {}).get("holdout_outcomes_may_change_definitions") is False
        and registry.get("freeze_rules", {}).get("missing_outcomes_may_be_replaced_by_proxies") is False,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "outcome_count": len(outcomes),
        "intervention_resource_contract_count": len(resource_constraints),
        "quiet_state_count": len(registry.get("quiet_state_registry", {})),
        "evaluation_horizons_days": time_contract.get("evaluation_horizons_days"),
    }


def main() -> int:
    result = validate(load_registry())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
