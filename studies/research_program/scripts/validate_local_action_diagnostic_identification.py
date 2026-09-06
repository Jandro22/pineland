"""Synthetic recovery of locality-level action bottleneck diagnostics."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.action_model import action_choice_weights, local_action_support  # noqa: E402
from pineland_sim.entities import ActorBelief, ControlVector, OrganizationKind  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402


CONTRACT = ROOT / "studies" / "research_program" / "local_action_diagnostic_identification_contract_v1.json"
OUTPUT = ROOT / "studies" / "research_program" / "local_action_diagnostic_identification_recovery_v1.json"


TARGET_ACCESS_RAW_REASONS = {
    "believed_battle_target_absent",
    "believed_human_target_absent",
    "believed_asset_target_absent",
    "no_exposed_target_personnel",
    "target_stock_changed_before_execution",
    "no_susceptible_population",
}


def _world(seed: int, contract: dict):
    design = contract["design"]
    return generate_pineland(SimulationConfig(
        seed=seed,
        agent_count=int(design["agent_count"]),
        locality_count=int(design["locality_count"]),
        horizon_days=1.0,
        output_mode="forensic",
    ))


def _insurgent(world):
    return next(
        item for item in world.organizations.values()
        if item.kind is OrganizationKind.INSURGENT and item.status == "active"
    )


def _candidate_localities(world, organization_id: str) -> list[str]:
    occupied = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization_id and formation.personnel > 0
    }
    targets = {
        post.locality_id for post in world.security_posts.values()
        if post.formation_id is None and post.personnel > 0 and post.locality_id not in occupied
    }
    return sorted(targets)


def _set_control_belief(world, organization_id: str, locality_id: str, value: float) -> None:
    value = float(value)
    vector = ControlVector(
        formal=value,
        physical=value,
        administrative=value,
        legal=value,
        fiscal=value,
        social=value,
        expected=value,
    )
    world.control_beliefs[(organization_id, "government", locality_id)] = ActorBelief(
        actor_id=organization_id,
        locality_id=locality_id,
        control_estimate=vector,
        confidence=1.0,
        updated_at=0.0,
        last_reliable_observation_at=0.0,
        evidence_count=1,
        contradiction_index=0.0,
        violence_estimate=0.0,
    )


def _prepare_capacity_supply(world, organization_id: str, locality_id: str, capacity: float) -> None:
    world.organization_manpower_pools[(organization_id, locality_id)] = max(0.0, float(capacity))
    organization = world.organizations[organization_id]
    organization.local_knowledge = 1.0
    organization.capital["material"] = 1.0
    source = next(item for item in world.supply_sources.values() if item.organization_id == organization_id)
    source.locality_id = locality_id
    source.stock = max(float(source.stock), 10000.0)


def _remove_fixed_targets(world, locality_id: str) -> None:
    for post in world.security_posts.values():
        if post.locality_id == locality_id and post.formation_id is None:
            post.personnel = 0.0


def _event(organization_id: str, locality_id: str, interval_days: float) -> ScheduledEvent:
    return ScheduledEvent(
        1.0, 18, 0, "organized_action",
        {
            "organization_id": organization_id,
            "locality_id": locality_id,
            "interval_days": float(interval_days),
        },
    )


def _choice_probability(weights: dict[str, float], channel: str) -> float:
    denominator = sum(max(0.0, float(value)) for value in weights.values())
    if denominator <= 0:
        return 0.0
    return max(0.0, float(weights[channel])) / denominator


def _planner_snapshot(world, organization_id: str, locality_id: str) -> dict:
    support = local_action_support(world, organization_id, locality_id)
    weights = action_choice_weights(world, organization_id, locality_id)
    return {
        "total_fighter_equivalents": float(support.total_fighter_equivalents),
        "nonfielded_target_truth_available": bool(support.nonfielded_human_target),
        "nonfielded_choice_weight": float(weights["nonfielded_human_target"]),
        "nonfielded_choice_probability": _choice_probability(weights, "nonfielded_human_target"),
        "wait_choice_probability": _choice_probability(weights, "wait"),
        "choice_weights": {key: float(value) for key, value in weights.items()},
    }


def _classify(result: dict, planner: dict) -> dict:
    reason = str(result.get("failure_reason") or "realized")
    if reason == "no_local_fighter_capacity":
        stage = "capacity"
    elif reason == "no_action_opportunity":
        stage = "opportunity"
    elif reason == "actor_selected_wait":
        stage = "belief_choice"
    elif reason in TARGET_ACCESS_RAW_REASONS:
        stage = "target_access"
    elif reason in {"execution_failed", "supply_exclusion"}:
        stage = "execution"
    elif float(result.get("latent_event", 0.0)) > 0:
        stage = "realized"
    else:
        stage = "other"
    return {
        "stage": stage,
        "raw_failure_reason": reason,
        "planner_nonfielded_choice_probability": planner["nonfielded_choice_probability"],
        "truth_target_available_at_planning_snapshot": planner["nonfielded_target_truth_available"],
        "semantic_note": (
            "raw label contains 'believed' but this branch is reached only after channel selection and truth-side target enumeration"
            if reason in {"believed_human_target_absent", "believed_asset_target_absent", "believed_battle_target_absent"}
            else None
        ),
    }


def _forced_nonfielded(world, organization_id: str, locality_id: str, interval_days: float,
                       *, force_execution_probability: float | None = None) -> tuple[dict, dict]:
    planner = _planner_snapshot(world, organization_id, locality_id)
    forced = ("nonfielded_human_target", planner["choice_weights"])
    patches = [
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced),
    ]
    if force_execution_probability is not None:
        patches.append(patch(
            "pineland_sim.processes.execution_probability",
            return_value=float(force_execution_probability),
        ))
    entered = []
    try:
        for item in patches:
            entered.append(item.__enter__())
        result = ProcessEngine(world, rng=random.Random(9001)).on_organized_action(
            "LOCAL-DIAG", _event(organization_id, locality_id, interval_days)
        )
    finally:
        for item in reversed(patches):
            item.__exit__(None, None, None)
    return planner, result


def run_seed(seed: int, contract: dict) -> dict:
    design = contract["design"]
    base = _world(seed, contract)
    organization = _insurgent(base)
    localities = _candidate_localities(base, organization.organization_id)
    if len(localities) < 2:
        return {"seed": seed, "passed": False, "failure": "insufficient_candidate_localities"}
    focal, control = localities[:2]
    capacity = float(design["local_fighter_capacity"])
    interval = float(design["interval_days"])

    # 1) Capacity gate.
    no_capacity = copy.deepcopy(base)
    no_capacity.organization_manpower_pools[(organization.organization_id, focal)] = 0.0
    no_capacity_result = ProcessEngine(no_capacity, rng=random.Random(1)).on_organized_action(
        "NO-CAPACITY", _event(organization.organization_id, focal, interval)
    )
    no_capacity_planner = _planner_snapshot(no_capacity, organization.organization_id, focal)

    # 2) Opportunity gate at fixed positive capacity.
    blocked = copy.deepcopy(base)
    _prepare_capacity_supply(blocked, organization.organization_id, focal, capacity)
    blocked_planner = _planner_snapshot(blocked, organization.organization_id, focal)
    with patch("pineland_sim.processes.action_attempt_probability", return_value=0.0):
        blocked_result = ProcessEngine(blocked, rng=random.Random(2)).on_organized_action(
            "NO-OPPORTUNITY", _event(organization.organization_id, focal, interval)
        )

    # 3) Belief/choice contrast: truth and capacity fixed, only focal belief moves.
    low = copy.deepcopy(base)
    high = copy.deepcopy(base)
    for world in (low, high):
        _prepare_capacity_supply(world, organization.organization_id, focal, capacity)
        _prepare_capacity_supply(world, organization.organization_id, control, capacity)
    _set_control_belief(low, organization.organization_id, focal, float(design["belief_low"]))
    _set_control_belief(high, organization.organization_id, focal, float(design["belief_high"]))
    low_focal = _planner_snapshot(low, organization.organization_id, focal)
    high_focal = _planner_snapshot(high, organization.organization_id, focal)
    low_control = _planner_snapshot(low, organization.organization_id, control)
    high_control = _planner_snapshot(high, organization.organization_id, control)

    # 4) Same high belief, target present vs removed after belief is fixed.
    present = copy.deepcopy(high)
    absent = copy.deepcopy(high)
    _remove_fixed_targets(absent, focal)
    present_planner, present_result = _forced_nonfielded(
        present, organization.organization_id, focal, interval, force_execution_probability=1.0
    )
    absent_planner, absent_result = _forced_nonfielded(
        absent, organization.organization_id, focal, interval, force_execution_probability=1.0
    )

    # 5) Execution feasibility failure with belief and truth support held positive.
    execution_blocked = copy.deepcopy(high)
    execution_planner, execution_result = _forced_nonfielded(
        execution_blocked, organization.organization_id, focal, interval,
        force_execution_probability=0.0,
    )

    diagnostics = {
        "no_local_capacity": _classify(no_capacity_result, no_capacity_planner),
        "opportunity_blocked": _classify(blocked_result, blocked_planner),
        "high_belief_target_present": _classify(present_result, present_planner),
        "high_belief_target_absent": _classify(absent_result, absent_planner),
        "execution_feasibility_blocked": _classify(execution_result, execution_planner),
    }
    gates = {
        "capacity_localized": diagnostics["no_local_capacity"]["stage"] == "capacity",
        "opportunity_localized": diagnostics["opportunity_blocked"]["stage"] == "opportunity",
        "focal_belief_changes_choice": (
            high_focal["nonfielded_choice_probability"] > low_focal["nonfielded_choice_probability"]
        ),
        "control_locality_choice_unchanged": abs(
            high_control["nonfielded_choice_probability"] - low_control["nonfielded_choice_probability"]
        ) <= 1e-12,
        "present_target_realizes": (
            diagnostics["high_belief_target_present"]["stage"] == "realized"
            and float(present_result.get("latent_event", 0.0)) == 1.0
        ),
        "absent_target_preserves_planning_belief": abs(
            present_planner["nonfielded_choice_probability"] -
            absent_planner["nonfielded_choice_probability"]
        ) <= 1e-12,
        "absent_target_localized_to_access": (
            diagnostics["high_belief_target_absent"]["stage"] == "target_access"
        ),
        "execution_failure_localized": (
            diagnostics["execution_feasibility_blocked"]["stage"] == "execution"
        ),
    }
    return {
        "seed": seed,
        "focal_locality": focal,
        "control_locality": control,
        "belief_choice_contrast": {
            "low_focal": low_focal,
            "high_focal": high_focal,
            "low_control": low_control,
            "high_control": high_control,
        },
        "raw_results": {
            "no_local_capacity": no_capacity_result,
            "opportunity_blocked": blocked_result,
            "high_belief_target_present": present_result,
            "high_belief_target_absent": absent_result,
            "execution_feasibility_blocked": execution_result,
        },
        "localized_diagnostics": diagnostics,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    repo_before = repository_state(ROOT)
    model_before = model_sha256(ROOT)
    results = [run_seed(int(seed), contract) for seed in contract["design"]["seeds"]]
    model_after = model_sha256(ROOT)
    repo_after = repository_state(ROOT)
    global_gates = {
        "all_seed_gates_pass": all(item.get("passed", False) for item in results),
        "model_hash_stable": model_before == model_after,
        "tracked_diff_stable": repo_before.get("tracked_diff_sha256") == repo_after.get("tracked_diff_sha256"),
    }
    payload = {
        "schema_version": "pineland.local_action_diagnostic_identification_recovery.v1",
        "experiment_id": contract["experiment_id"],
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "model_sha256": model_before,
        "repository_before": repo_before,
        "repository_after": repo_after,
        "global_gates": global_gates,
        "passed": all(global_gates.values()),
        "semantic_finding": (
            "The raw 'believed_*_target_absent' labels are execution-stage truth/access failures "
            "after channel selection; they cannot identify erroneous actor beliefs by themselves."
        ),
        "results": results,
        "interpretation": contract["interpretation"],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.local_action_diagnostic_identification_manifest.v1",
        "artifact": OUTPUT.relative_to(ROOT).as_posix(),
        "artifact_sha256": file_sha256(OUTPUT),
        "contract": CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": file_sha256(CONTRACT),
        "runner": Path(__file__).relative_to(ROOT).as_posix(),
        "runner_sha256": file_sha256(Path(__file__)),
        "passed": payload["passed"],
    }
    OUTPUT.with_name(OUTPUT.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "passed": payload["passed"],
        "global_gates": global_gates,
        "seed_passes": {str(item["seed"]): item.get("passed", False) for item in results},
        "raw_absent_target_reasons": {
            str(item["seed"]): item["localized_diagnostics"]["high_belief_target_absent"]["raw_failure_reason"]
            for item in results
        },
    }, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
