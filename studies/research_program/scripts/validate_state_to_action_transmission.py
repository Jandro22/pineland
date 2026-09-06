"""Synthetic identification battery for local state -> action transmission."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import random
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.action_model import (  # noqa: E402
    action_attempt_probability,
    action_choice_weights,
    execution_probability,
    local_action_support,
)
from pineland_sim.entities import OrganizationKind  # noqa: E402
from pineland_sim.processes import ProcessEngine  # noqa: E402
from pineland_sim.reproducibility import file_sha256, model_sha256, repository_state  # noqa: E402
from pineland_sim.events import ScheduledEvent  # noqa: E402


CONTRACT = ROOT / "studies" / "research_program" / "state_to_action_transmission_contract_v1.json"
OUTPUT = ROOT / "studies" / "research_program" / "state_to_action_transmission_recovery_v1.json"


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
        organization for organization in world.organizations.values()
        if organization.kind is OrganizationKind.INSURGENT and organization.status == "active"
    )


def _fixed_target_localities(world, organization_id: str) -> list[str]:
    fielded = {
        formation.locality_id for formation in world.formations.values()
        if formation.organization_id == organization_id and formation.personnel > 0
        and not formation.outside_pineland
    }
    candidates = {
        post.locality_id for post in world.security_posts.values()
        if post.formation_id is None and post.personnel > 0 and post.locality_id not in fielded
    }
    return sorted(candidates)


def _prepare_dose_world(base, organization_id: str, locality_id: str, dose: float):
    world = copy.deepcopy(base)
    organization = world.organizations[organization_id]
    key = (organization_id, locality_id)
    dose = max(0.0, float(dose))
    world.organization_manpower_pools[key] = dose
    supply_per_fighter = (
        world.config.logistics.formation_supply_days
        * world.config.logistics.initial_supply_fraction
    )
    reserve = dose * supply_per_fighter
    if reserve:
        if organization.resources < reserve:
            raise RuntimeError("synthetic dose fixture lacks its declared nonbinding funding")
        organization.resources -= reserve
        world.cumulative_resource_to_supply += reserve
        world.organization_manpower_supply_reserves[key] = reserve
    else:
        world.organization_manpower_supply_reserves.pop(key, None)
    organization.local_knowledge = 1.0
    organization.capital["material"] = 1.0
    source = next(
        item for item in world.supply_sources.values()
        if item.organization_id == organization_id
    )
    source.locality_id = locality_id
    source.stock = max(float(source.stock), 10000.0)
    return world


def _choice_probability(weights: dict[str, float], channel: str) -> float:
    denominator = sum(max(0.0, float(value)) for value in weights.values())
    return 0.0 if denominator <= 0 else max(0.0, float(weights[channel])) / denominator


def _action_event(organization_id: str, locality_id: str, interval_days: float):
    return ScheduledEvent(
        1.0,
        18,
        0,
        "organized_action",
        {
            "organization_id": organization_id,
            "locality_id": locality_id,
            "interval_days": interval_days,
        },
    )


def _target_access_falsifier(world, organization_id: str, locality_id: str, interval_days: float):
    present = copy.deepcopy(world)
    missing = copy.deepcopy(world)
    for post in missing.security_posts.values():
        if post.locality_id == locality_id and post.formation_id is None:
            post.personnel = 0.0
    before_weights = action_choice_weights(present, organization_id, locality_id)
    missing_weights = action_choice_weights(missing, organization_id, locality_id)
    forced_choice = ("nonfielded_human_target", before_weights)
    with (
        patch("pineland_sim.processes.action_attempt_probability", return_value=1.0),
        patch("pineland_sim.processes.choose_action", return_value=forced_choice),
        patch("pineland_sim.processes.execution_probability", return_value=1.0),
    ):
        present_result = ProcessEngine(present, rng=random.Random(101)).on_organized_action(
            "STA-PRESENT", _action_event(organization_id, locality_id, interval_days)
        )
        missing_result = ProcessEngine(missing, rng=random.Random(101)).on_organized_action(
            "STA-MISSING", _action_event(organization_id, locality_id, interval_days)
        )
    return {
        "planning_weights_unchanged_when_hidden_target_removed": before_weights == missing_weights,
        "present_latent_event": float(present_result.get("latent_event", 0.0)),
        "missing_latent_event": float(missing_result.get("latent_event", 0.0)),
        "missing_failure_reason": missing_result.get("failure_reason"),
    }


def _strictly_increasing(values: list[float], tolerance: float = 1e-12) -> bool:
    return all(right > left + tolerance for left, right in zip(values, values[1:]))


def run_seed(seed: int, contract: dict) -> dict:
    design = contract["design"]
    base = _world(seed, contract)
    organization = _insurgent(base)
    candidate_localities = _fixed_target_localities(base, organization.organization_id)
    if len(candidate_localities) < 2:
        return {"seed": seed, "passed": False, "failure": "insufficient_fixed_target_localities"}

    # Select by actor-facing nonfielded-target planning weight under a common
    # synthetic reference dose. No historical outcome enters this selection.
    scored = []
    for locality_id in candidate_localities:
        reference = _prepare_dose_world(base, organization.organization_id, locality_id, 100.0)
        weights = action_choice_weights(reference, organization.organization_id, locality_id)
        scored.append((float(weights["nonfielded_human_target"]), locality_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    focal = scored[0][1]
    control = next(item for item in candidate_localities if item != focal)

    rows = []
    for dose in [float(value) for value in design["capacity_doses"]]:
        world = _prepare_dose_world(base, organization.organization_id, focal, dose)
        support = local_action_support(world, organization.organization_id, focal)
        attempt = action_attempt_probability(
            world, organization.organization_id, focal, float(design["interval_days"])
        )
        weights = action_choice_weights(world, organization.organization_id, focal)
        choice_probability = _choice_probability(weights, "nonfielded_human_target")
        execute = execution_probability(
            world,
            organization.organization_id,
            focal,
            target_resistance=float(design["target_resistance"]),
            material_fraction=1.0,
        )
        expected_propensity = attempt * choice_probability * execute
        control_attempt = action_attempt_probability(
            world, organization.organization_id, control, float(design["interval_days"])
        )
        rows.append({
            "dose": dose,
            "total_fighter_equivalents": float(support.total_fighter_equivalents),
            "nonfielded_target_supported": bool(support.nonfielded_human_target),
            "attempt_probability": float(attempt),
            "nonfielded_choice_probability": float(choice_probability),
            "execution_probability": float(execute),
            "expected_nonfielded_latent_event_propensity": float(expected_propensity),
            "control_locality_attempt_probability": float(control_attempt),
        })

    positive = rows[1:]
    attempts = [row["attempt_probability"] for row in positive]
    executions = [row["execution_probability"] for row in positive]
    propensities = [row["expected_nonfielded_latent_event_propensity"] for row in positive]
    controls = [row["control_locality_attempt_probability"] for row in rows]
    high = _prepare_dose_world(base, organization.organization_id, focal, 100.0)
    target_falsifier = _target_access_falsifier(
        high, organization.organization_id, focal, float(design["interval_days"])
    )
    gates = {
        "zero_capacity_zero_attempt": math.isclose(rows[0]["attempt_probability"], 0.0, abs_tol=1e-12),
        "zero_capacity_zero_propensity": math.isclose(
            rows[0]["expected_nonfielded_latent_event_propensity"], 0.0, abs_tol=1e-12
        ),
        "positive_capacity_has_target_support": all(row["nonfielded_target_supported"] for row in positive),
        "attempt_strict_dose_response": _strictly_increasing(attempts),
        "execution_strict_dose_response": _strictly_increasing(executions),
        "latent_propensity_strict_dose_response": _strictly_increasing(propensities),
        "control_locality_unchanged": max(controls) - min(controls) <= 1e-12,
        "target_truth_does_not_change_planning": target_falsifier[
            "planning_weights_unchanged_when_hidden_target_removed"
        ],
        "target_truth_gates_realization": (
            target_falsifier["present_latent_event"] == 1.0
            and target_falsifier["missing_latent_event"] == 0.0
            and target_falsifier["missing_failure_reason"] == "believed_human_target_absent"
        ),
    }
    return {
        "seed": seed,
        "focal_locality": focal,
        "control_locality": control,
        "reference_nonfielded_weight": scored[0][0],
        "rows": rows,
        "target_access_falsifier": target_falsifier,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    before_repo = repository_state(ROOT)
    before_model = model_sha256(ROOT)
    results = [run_seed(int(seed), contract) for seed in contract["design"]["seeds"]]
    after_model = model_sha256(ROOT)
    after_repo = repository_state(ROOT)
    global_gates = {
        "all_seeds_pass": all(row.get("passed", False) for row in results),
        "model_hash_stable": before_model == after_model,
        "tracked_diff_stable": before_repo.get("tracked_diff_sha256") == after_repo.get("tracked_diff_sha256"),
    }
    payload = {
        "schema_version": "pineland.state_to_action_transmission_recovery.v1",
        "experiment_id": contract["experiment_id"],
        "historical_outcomes_used": False,
        "historical_parameter_fitting": False,
        "core_modified": False,
        "contract_sha256": file_sha256(CONTRACT),
        "runner_sha256": file_sha256(Path(__file__)),
        "model_sha256": before_model,
        "repository_before": before_repo,
        "repository_after": after_repo,
        "global_gates": global_gates,
        "passed": all(global_gates.values()),
        "results": results,
        "interpretation": contract["interpretation"],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "pineland.state_to_action_transmission_recovery_manifest.v1",
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
        "seed_passes": {str(row["seed"]): row.get("passed", False) for row in results},
    }, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
