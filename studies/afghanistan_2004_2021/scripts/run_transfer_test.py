"""Run the sourced Afghanistan transfer test through explicit stage gates."""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from math import sqrt, isfinite, fsum
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"
INPUTS_FILE = STUDY / "config" / "historical_case_inputs.json"
CONTROL = STUDY / "data" / "processed" / "sigar_oct2017_control_401.csv"
CONTROL_OPERATOR = STUDY / "config" / "control_observation_model.json"
CONTROL_VALIDATION_PLAN = STUDY / "config" / "control_validation_plan.json"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"
DESIGN = STUDY / "config" / "study_design.json"
OUT = STUDY / "runs" / "transfer_test_v1"
START = date(2004, 1, 1)
END = date(2021, 8, 15)
DEFAULT_SEED = 20_040_101


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _config(seed: int, horizon: float):
    from pineland_sim import SimulationConfig

    config = SimulationConfig(
        seed=seed,
        horizon_days=horizon,
        agent_count=401,
        locality_count=401,
        output_mode="calibration",
    )
    config.information.observation_retention_days = 90.0
    config.organization_ecology.observed_active_intervals = {
        "insurgent": [[0.0, horizon]]
    }
    # Historical Pakistan and coalition state are installed explicitly by the
    # case adapter.  The synthetic foreign-decision generator must not run.
    config.foreign_affairs.enabled = False
    # The requested transfer test ends at Kabul's fall; peace dynamics are not
    # exogenously sourced here and remain outside this benchmark layer.
    config.peace_process.enabled = False
    config.validate()
    return config


def build_conditioned_world(seed: int, horizon: float, taliban_strength: float):
    from pineland_sim import generate_pineland
    from historical_case import condition_world, load_historical_inputs

    case = json.loads(CASE.read_text(encoding="utf-8"))
    inputs = load_historical_inputs()
    config = _config(seed, horizon)
    world = generate_pineland(config, empirical_geography=case)
    condition_world(world, inputs, taliban_strength)
    return world, inputs


def initialization_gate(world, inputs: dict, taliban_strength: float) -> dict:
    from historical_case import initialization_diagnostics

    diagnostic = initialization_diagnostics(world, inputs, taliban_strength)
    expected = diagnostic["expected"]
    supply_accounting = supply_accounting_check(world)
    checks = {
        "population": abs(diagnostic["weighted_population"] - 24_726_689) < 1e-6,
        "ana_stock": abs(diagnostic["ana_personnel"] - expected["ana_personnel"]) < 1e-6,
        "anp_stock": abs(diagnostic["anp_personnel"] - expected["anp_personnel"]) < 1e-6,
        "taliban_stock": abs(
            diagnostic["taliban_personnel"] - expected["taliban_personnel"]
        ) < 1e-6,
        "coalition_stock": abs(
            diagnostic["coalition_personnel"] - expected["coalition_personnel"]
        ) < 1e-6,
        "ana_battalions": diagnostic["ana_formations"] == expected["ana_formations"],
        "pakistan_only": diagnostic["foreign_states"] == ["pakistan"],
        "pakistan_border": (
            diagnostic["pakistan_border_segments"]
            == expected["pakistan_border_segments"]
        ),
        "sanctuary_present": diagnostic["taliban_external_sanctuary"] == 1.0,
        "stock_ledger": abs(diagnostic["stock_ledger_residual"]) < 1e-6,
        "supply_ledger": supply_accounting["passed"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "diagnostics": diagnostic,
        "supply_accounting": supply_accounting,
    }


def _binary_metrics(observed: list[int], predicted: list[int]) -> dict[str, float | int]:
    tp = sum(o == 1 and p == 1 for o, p in zip(observed, predicted))
    tn = sum(o == 0 and p == 0 for o, p in zip(observed, predicted))
    fp = sum(o == 0 and p == 1 for o, p in zip(observed, predicted))
    fn = sum(o == 1 and p == 0 for o, p in zip(observed, predicted))
    sensitivity = tp / max(1, tp + fn)
    specificity = tn / max(1, tn + fp)
    precision = tp / max(1, tp + fp)
    return {
        "n": len(observed),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "precision": precision,
        "jaccard": tp / max(1, tp + fp + fn),
        "binary_mae": (fp + fn) / max(1, len(observed)),
    }


def violence_score(world, horizon: float) -> dict:
    recorded = {
        (
            world.district_hierarchy[
                world.localities[record.locality_id].district_id
            ]["province"],
            int(record.time // 7),
        )
        for record in world.synthetic_records
        if record.event_type in {"contact", "state_based_violence"}
        and record.recorded
        and record.locality_id in world.localities
    }
    latent = {
        (
            world.district_hierarchy[
                world.localities[locality_id].district_id
            ]["province"],
            int(event_time // 7),
        )
        for event_time, locality_id in zip(
            world.state_based_event_times, world.state_based_event_localities
        )
        if locality_id in world.localities
    }
    rows = []
    with PANEL.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["week_index"]) * 7 <= horizon:
                rows.append(row)
    result = {
        "recorded_active_province_weeks": len(recorded),
        "latent_active_province_weeks": len(latent),
        "recorded_contacts": sum(
            record.event_type in {"contact", "state_based_violence"} and record.recorded
            for record in world.synthetic_records
        ),
        "latent_contacts": len(world.state_based_event_times),
        "recorded_active_cells": [
            {"province_id": province_id, "week_index": week_index}
            for province_id, week_index in sorted(recorded)
        ],
        "latent_active_cells": [
            {"province_id": province_id, "week_index": week_index}
            for province_id, week_index in sorted(latent)
        ],
        "splits": {},
    }
    for split in sorted({row["split"] for row in rows}):
        subset = [row for row in rows if row["split"] == split]
        observed = [int(row["taliban_state_active"]) for row in subset]
        predicted = [
            int((row["province_id"], int(row["week_index"])) in recorded)
            for row in subset
        ]
        metrics = _binary_metrics(observed, predicted)
        metrics.update({
            "observed_active_province_weeks": sum(observed),
            "model_active_province_weeks": sum(predicted),
            "observed_event_count": sum(
                int(row["taliban_state_event_count"]) for row in subset
            ),
        })
        result["splits"][split] = metrics
    return result


def hazard_diagnostics(world) -> dict:
    if world.config.combat.organized_action_architecture == "multichannel_v5":
        # v5 schedules organized actions, not the legacy pair-contact funnel.
        # An empty legacy archive cannot imply a 100% probability of no violence.
        return {
            "status": "not_applicable_legacy_contact_hazard",
            "architecture": "multichannel_v5",
            "draws": 0,
            "expected_contacts": None,
            "probability_zero_contacts": None,
            "mean_hazard": None,
            "minimum_hazard": None,
            "median_hazard": None,
            "maximum_hazard": None,
            "action_funnel": dict(world.action_funnel_counts),
        }
    hazards = [
        float(record["contact_hazard"])
        for record in world.contact_funnel_records
        if record.get("hazard_draw") is not None and record.get("contact_hazard") is not None
    ]
    zero_probability = 1.0
    for hazard in hazards:
        zero_probability *= 1.0 - min(1.0, max(0.0, hazard))
    ordered = sorted(hazards)
    return {
        "draws": len(hazards),
        "expected_contacts": sum(hazards),
        "probability_zero_contacts": zero_probability,
        "mean_hazard": sum(hazards) / max(1, len(hazards)),
        "minimum_hazard": ordered[0] if ordered else None,
        "median_hazard": ordered[len(ordered) // 2] if ordered else None,
        "maximum_hazard": ordered[-1] if ordered else None,
    }


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    )
    return numerator / denominator if denominator else None


def control_score(snapshot: dict | None,
                  snapshot_time: float | None) -> dict | None:
    if snapshot is None:
        return None
    targets = []
    with CONTROL.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["government_control_index"]:
                targets.append(row)
    from control_observation import OrdinalControlObservationModel
    operator_spec = json.loads(CONTROL_OPERATOR.read_text(encoding="utf-8"))
    operator = OrdinalControlObservationModel.from_dict(operator_spec)
    observed, modeled, weights = [], [], []
    snapshot_schema = "seven_dimensional_relative_control_v1"
    for row in targets:
        locality_id = f"{row['district_id']}-HQ"
        if locality_id not in snapshot:
            continue
        state = snapshot[locality_id]
        observed.append(float(row["government_control_index"]))
        if isinstance(state, dict) and "government" in state and "insurgent" in state:
            modeled.append(operator.expected_index(state["government"], state["insurgent"]))
        else:
            # Retained only so archived v1 outputs remain readable.  Such a
            # snapshot cannot validate the new operator because its seven
            # dimensions and opposing actor were discarded.
            modeled.append(float(state))
            snapshot_schema = "legacy_effective_scalar_unrecoverable"
        weights.append(float(row["source_population"]))
    errors = [model - obs for model, obs in zip(modeled, observed)]
    total_weight = sum(weights)
    measurement_licensed = snapshot_schema == "seven_dimensional_relative_control_v1"
    validation_plan = json.loads(CONTROL_VALIDATION_PLAN.read_text(encoding="utf-8"))
    success_gate = validation_plan.get("success_gate", {})
    if not measurement_licensed:
        validation_gate_status = "legacy_measurement_failure"
        validation_passed = False
    elif success_gate.get("status") != "preregistered_numeric_gate":
        validation_gate_status = "unassessed_missing_predeclared_success_gate"
        validation_passed = None
    else:
        requirements = success_gate.get("requirements", {})
        provisional_metrics = {
            "mae": sum(abs(error) for error in errors) / max(1, len(errors)),
            "rmse": sqrt(sum(error * error for error in errors) / max(1, len(errors))),
            "pearson": _correlation(observed, modeled),
        }
        checks = []
        for metric, rule in requirements.items():
            value = provisional_metrics.get(metric)
            if value is None:
                checks.append(False)
            elif "lte" in rule:
                checks.append(value <= float(rule["lte"]))
            elif "gte" in rule:
                checks.append(value >= float(rule["gte"]))
            else:
                checks.append(False)
        validation_passed = bool(checks) and all(checks)
        validation_gate_status = "passed" if validation_passed else "failed"
    return {
        "snapshot_time": snapshot_time,
        "target_date": "2017-10-15",
        "snapshot_schema": snapshot_schema,
        "observation_operator_status": (
            operator_spec["status"] if measurement_licensed
            else "legacy_frozen_measurement_failure_not_rescored"
        ),
        "observation_operator_sha256": sha256(CONTROL_OPERATOR),
        "control_validation_plan_sha256": sha256(CONTROL_VALIDATION_PLAN),
        "validation_gate_status": validation_gate_status,
        "validation_passed": validation_passed,
        "n": len(errors),
        "target_districts": len(targets),
        "missing_target_districts": len(targets) - len(errors),
        "mae": sum(abs(error) for error in errors) / max(1, len(errors)),
        "rmse": sqrt(sum(error * error for error in errors) / max(1, len(errors))),
        "population_weighted_mae": (
            sum(abs(error) * weight for error, weight in zip(errors, weights))
            / max(1.0, total_weight)
        ),
        "pearson": _correlation(observed, modeled),
        "observed_mean": sum(observed) / max(1, len(observed)),
        "modeled_mean": sum(modeled) / max(1, len(modeled)),
    }


def supply_accounting_check(world, *, atol: float = 1e-5, rtol: float = 1e-12) -> dict:
    """Roundoff-aware ledger check using gross ledger flow, not net stock.

    This is a numerical check only, never an empirical validation gate.
    """
    terms = [world.initial_supply_stock, world.cumulative_supply_produced,
             world.cumulative_resource_to_supply, world.cumulative_supply_consumed,
             world.cumulative_supply_lost]
    residual = world.supply_conservation_residual()
    if not all(isfinite(value) for value in [*terms, residual, atol, rtol]) or min(atol, rtol) < 0:
        return {"passed": False, "reason": "nonfinite_ledger_or_invalid_tolerance"}
    scale = fsum(abs(value) for value in terms); tolerance = atol + rtol * scale
    return {"passed": abs(residual) <= tolerance, "reason": "within_scaled_tolerance" if abs(residual) <= tolerance else "outside_scaled_tolerance",
            "residual": residual, "scale": scale, "atol": atol, "rtol": rtol,
            "tolerance": tolerance, "relative_residual": abs(residual) / scale if scale else None}


def run_case(seed: int, horizon: float, taliban_strength: float) -> dict:
    from pineland_sim import Simulation
    from historical_case import HistoricalCoalitionSchedule
    from pineland_sim.reproducibility import model_sha256, repository_state

    model_sha256_start = model_sha256(ROOT)
    tracked_diff_sha256 = repository_state(ROOT)["tracked_diff_sha256"]
    started = time.perf_counter()
    world, inputs = build_conditioned_world(seed, horizon, taliban_strength)
    init = initialization_gate(world, inputs, taliban_strength)
    if not init["passed"]:
        raise AssertionError(f"initialization gate failed: {init}")
    initialization_seconds = time.perf_counter() - started

    schedule = HistoricalCoalitionSchedule(inputs)
    simulation_started = time.perf_counter()
    result = Simulation(world, policy_hook=schedule).run()
    runtime = time.perf_counter() - simulation_started
    world = result.world
    model_sha256_end = model_sha256(ROOT)

    final_coalition = sum(
        formation.personnel for formation in world.formations.values()
        if formation.organization_id == "coalition"
    )
    gate_checks = {
        "reached_horizon": abs(result.stopped_at - horizon) < 1e-9,
        "stock_ledger": abs(world.stock_ledger_residual()) < 1e-5,
        "supply_ledger": supply_accounting_check(world)["passed"],
        "pakistan_only": sorted(world.foreign_states) == ["pakistan"],
        "taliban_persisted": world.organizations["insurgent"].status == "active",
        "processed_events": result.events_processed > 0,
        "nonnegative_force_stocks": all(
            formation.personnel >= 0 and formation.supply_stock >= 0
            for formation in world.formations.values()
        ),
    }
    return {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "formulation": "sourced_transfer_test_v1",
        "parameter_fit": False,
        "benchmark_violence_used_for_inputs": False,
        "seed": seed,
        "taliban_initial_strength": taliban_strength,
        "horizon_days": horizon,
        "initialization_seconds": initialization_seconds,
        "runtime_seconds": runtime,
        "model_sha256_start": model_sha256_start,
        "model_sha256_end": model_sha256_end,
        "tracked_diff_sha256": tracked_diff_sha256,
        "model_stable_during_run": model_sha256_start == model_sha256_end,
        "events_processed": result.events_processed,
        "gate": {"passed": all(gate_checks.values()), "checks": gate_checks},
        "supply_accounting": supply_accounting_check(world),
        "initialization_gate": init,
        "historical_schedule_applied": schedule.applied,
        "control_validation_target_day": schedule.control_validation_day,
        "control_validation_status": (
            "matched_snapshot" if schedule.control_snapshot is not None else
            "not_reached_horizon" if horizon < schedule.control_validation_day else
            "no_snapshot_after_target"
        ),
        "final_coalition_personnel": final_coalition,
        "summary": world.summary(),
        "violence_validation": violence_score(world, horizon),
        "hazard_diagnostics": hazard_diagnostics(world),
        "control_validation": control_score(
            schedule.control_snapshot, schedule.control_snapshot_time
        ),
        "contact_funnel_counts": dict(world.contact_funnel_counts),
        "case_hashes": {
            "case_environment": sha256(CASE),
            "historical_case_inputs": sha256(INPUTS_FILE),
            "control_401": sha256(CONTROL),
            "province_week_panel": sha256(PANEL),
            "study_design": sha256(DESIGN),
            "control_observation_model": sha256(CONTROL_OPERATOR),
            "control_validation_plan": sha256(CONTROL_VALIDATION_PLAN),
            "runner": sha256(Path(__file__)),
        },
    }


def stage_spec(stage: str) -> tuple[float, list[float]]:
    if stage == "init":
        return 1.0, [7500.0]
    if stage == "smoke":
        return 30.0, [7500.0]
    if stage == "year":
        return float((date(2005, 1, 1) - START).days), [7500.0]
    if stage == "full":
        return float((END - START).days), [5000.0, 7500.0, 10000.0]
    raise ValueError(stage)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("init", "smoke", "year", "full"), required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--strengths", type=float, nargs="*")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--output-dir", type=Path,
        help="Optional stage-specific output directory; preserves legacy runs when revalidating a new frozen core.",
    )
    args = parser.parse_args()
    horizon, defaults = stage_spec(args.stage)
    strengths = args.strengths or defaults

    stage_dir = args.output_dir.resolve() if args.output_dir else (OUT / args.stage)
    stage_dir.mkdir(parents=True, exist_ok=True)
    results = []
    expected_paths = [stage_dir / f"seed_{args.seed}_taliban_{int(strength)}.json"
                      for strength in strengths]
    pending = [path for path in expected_paths if not path.exists() or args.force]
    if pending:
        from pineland_sim.reproducibility import require_certified_core
        try:
            require_certified_core(ROOT)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
    for strength in strengths:
        label = int(strength)
        path = stage_dir / f"seed_{args.seed}_taliban_{label}.json"
        if path.exists() and not args.force:
            payload = json.loads(path.read_text(encoding="utf-8"))
        elif args.stage == "init":
            from pineland_sim.reproducibility import model_sha256, repository_state
            model_hash_start = model_sha256(ROOT)
            tracked_diff_sha256 = repository_state(ROOT)["tracked_diff_sha256"]
            world, inputs = build_conditioned_world(args.seed, horizon, strength)
            gate = initialization_gate(world, inputs, strength)
            model_hash_end = model_sha256(ROOT)
            payload = {
                "schema_version": "1.0.0",
                "study_id": "afghanistan_2004_2021",
                "formulation": "sourced_transfer_test_v1",
                "stage": "init",
                "seed": args.seed,
                "taliban_initial_strength": strength,
                "model_sha256_start": model_hash_start,
                "model_sha256_end": model_hash_end,
                "tracked_diff_sha256": tracked_diff_sha256,
                "model_stable_during_run": model_hash_start == model_hash_end,
                "gate": gate,
                "case_hashes": {
                    "case_environment": sha256(CASE),
                    "historical_case_inputs": sha256(INPUTS_FILE),
                    "control_401": sha256(CONTROL),
                    "province_week_panel": sha256(PANEL),
                },
            }
            atomic_json(path, payload)
        else:
            payload = run_case(args.seed, horizon, strength)
            payload["stage"] = args.stage
            atomic_json(path, payload)
        results.append(payload)
        print(json.dumps({
            "stage": args.stage,
            "strength": strength,
            "passed": payload["gate"]["passed"],
            "runtime_seconds": payload.get("runtime_seconds", 0.0),
            "latent_contacts": payload.get("violence_validation", {}).get("latent_contacts"),
            "recorded_contacts": payload.get("violence_validation", {}).get("recorded_contacts"),
        }), flush=True)

    manifest = {
        "schema_version": "1.0.0",
        "study_id": "afghanistan_2004_2021",
        "formulation": "sourced_transfer_test_v1",
        "stage": args.stage,
        "horizon_days": horizon,
        "seed": args.seed,
        "strengths": strengths,
        "all_gates_passed": all(result["gate"]["passed"] for result in results),
        "files": [
            f"seed_{args.seed}_taliban_{int(strength)}.json" for strength in strengths
        ],
        "case_hashes": results[0]["case_hashes"],
    }
    atomic_json(stage_dir / "manifest.json", manifest)
    if not manifest["all_gates_passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
