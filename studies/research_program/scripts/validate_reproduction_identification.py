"""Run the complete data-free spatial reproduction identification gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from estimate_insurgent_reproduction import estimate  # noqa: E402
from identify_spatial_reproduction import run_synthetic_recovery_battery  # noqa: E402


def _row(
    activation_id: str,
    locality_id: str,
    activation_day: float,
    observation_end_day: float,
    *,
    activation_end_day: float | None = None,
    followup_probability: float | None = None,
    run_id: str | None = None,
) -> dict:
    row = {
        "activation_id": activation_id,
        "locality_id": locality_id,
        "activation_day": activation_day,
        "observation_end_day": observation_end_day,
        "parent_locality_id": None,
        "viable": True,
    }
    if activation_end_day is not None:
        row["activation_end_day"] = activation_end_day
    if followup_probability is not None:
        row["followup_inclusion_probability"] = followup_probability
    if run_id is not None:
        row["run_id"] = run_id
    return row


def _known_parentage_recovery() -> dict:
    rows = [
        _row("P0", "P0", 0, 100),
        _row("P1", "P1", 0, 100),
        _row("P2", "P2", 0, 100),
        _row("P3", "P3", 0, 100),
        _row("C0", "C0", 10, 20),
        _row("C1", "C1", 12, 20),
    ]
    edges = [
        {
            "child_activation_id": "C0",
            "parent_activation_id": "P0",
            "weight": 0.6,
            "pathway": "social_bridge",
        },
        {
            "child_activation_id": "C0",
            "parent_activation_id": "P1",
            "weight": 0.4,
            "pathway": "social_bridge",
        },
        {
            "child_activation_id": "C1",
            "parent_activation_id": "P0",
            "weight": 1.0,
            "pathway": "formation_movement",
        },
    ]
    base = estimate(rows, parent_edges=edges, horizon_days=30, bootstrap=0)
    with_background = estimate(
        rows + [_row("BG0", "BG0", 15, 20)],
        parent_edges=edges,
        horizon_days=30,
        bootstrap=0,
    )
    return {
        "expected_R_I": 0.5,
        "estimated_R_I": base["estimate"],
        "pathway_estimates": base["estimate_by_pathway"],
        "background_augmented_R_I": with_background["estimate"],
        "unattributed_background_weight_added": (
            with_background["unattributed_viable_child_weight"]
            - base["unattributed_viable_child_weight"]
        ),
    }


def _relocation_recovery() -> dict:
    rows = [
        _row("A1", "A", 0, 100, activation_end_day=12),
        _row("B1", "B", 10, 20, activation_end_day=20),
    ]
    edges = [{
        "child_activation_id": "B1",
        "parent_activation_id": "A1",
        "weight": 1.0,
        "pathway": "formation_relocation",
    }]
    result = estimate(
        rows,
        parent_edges=edges,
        horizon_days=30,
        bootstrap=0,
        minimum_parent_overlap_days=7,
    )
    return {
        "gross_R_I": result["gross_estimate"],
        "net_R_I": result["estimate"],
        "relocation_or_parent_extinction_weight":
            result["relocation_or_parent_extinction_child_weight"],
    }


def _repeated_episode_recovery() -> dict:
    rows = [
        _row("A-1", "A", 0, 100),
        _row("A-2", "A", 40, 100),
        _row("B-1", "B", 10, 20),
        _row("C-1", "C", 50, 60),
    ]
    edges = [
        {
            "child_activation_id": "B-1",
            "parent_activation_id": "A-1",
            "weight": 1.0,
            "pathway": "social_bridge",
        },
        {
            "child_activation_id": "C-1",
            "parent_activation_id": "A-2",
            "weight": 1.0,
            "pathway": "social_bridge",
        },
    ]
    result = estimate(rows, parent_edges=edges, horizon_days=30, bootstrap=0)
    return {
        "eligible_parent_activations": result["eligible_parent_activations"],
        "eligible_parent_localities": result["eligible_parent_localities"],
        "estimated_R_I": result["estimate"],
    }


def _censoring_recovery(seed: int) -> dict:
    rng = random.Random(seed)
    rows: list[dict] = []
    edges: list[dict] = []
    population_parent_count = 400
    true_total_offspring = 0
    observed_high = 0
    observed_low = 0
    for index in range(population_parent_count):
        high = index < population_parent_count // 2
        offspring = 2 if high else 0
        inclusion_probability = 0.25 if high else 1.0
        included = rng.random() < inclusion_probability
        true_total_offspring += offspring
        parent_id = f"P{index:04d}"
        rows.append(_row(
            parent_id,
            f"L{index:04d}",
            0,
            100 if included else 10,
            followup_probability=inclusion_probability,
            run_id=f"run-{index % 8}",
        ))
        if not included:
            continue
        if high:
            observed_high += 1
        else:
            observed_low += 1
        for child_index in range(offspring):
            child_id = f"C{index:04d}-{child_index}"
            rows.append(_row(
                child_id,
                f"CL{index:04d}-{child_index}",
                10 + child_index,
                20,
            ))
            edges.append({
                "child_activation_id": child_id,
                "parent_activation_id": parent_id,
                "weight": 1.0,
                "pathway": "known_synthetic_path",
            })
    truth = true_total_offspring / population_parent_count
    complete = estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=0,
        censoring_adjustment="complete_case",
    )
    adjusted = estimate(
        rows, parent_edges=edges, horizon_days=30, bootstrap=300,
        seed=seed + 1,
        censoring_adjustment="ipw",
        cluster_field="run_id",
    )
    return {
        "population_truth_R_I": truth,
        "complete_case_R_I": complete["estimate"],
        "ipw_R_I": adjusted["estimate"],
        "observed_high_parent_count": observed_high,
        "observed_low_parent_count": observed_low,
        "right_censored_parent_activations":
            adjusted["right_censored_parent_activations"],
        "bootstrap_method": adjusted["bootstrap_method"],
        "bootstrap_cluster_count": adjusted["bootstrap_cluster_count"],
        "bootstrap_inferential_license":
            adjusted["bootstrap_inferential_license"],
        "bootstrap_95_interval": adjusted["bootstrap_95_interval"],
    }


def run(seed: int = 20260905) -> dict:
    spatial = run_synthetic_recovery_battery(seed=seed)
    parentage = _known_parentage_recovery()
    relocation = _relocation_recovery()
    repeated = _repeated_episode_recovery()
    censoring = _censoring_recovery(seed + 100)

    pathway_total = sum(parentage["pathway_estimates"].values())
    truth = censoring["population_truth_R_I"]
    complete_error = abs(censoring["complete_case_R_I"] - truth)
    ipw_error = abs(censoring["ipw_R_I"] - truth)
    gates = {
        "spatial_identification_battery": bool(spatial["passed"]),
        "multi_parent_expected_R_I_recovered": (
            abs(parentage["estimated_R_I"] - parentage["expected_R_I"]) <= 1e-12
        ),
        "pathway_decomposition_sums_to_R_I": (
            abs(pathway_total - parentage["estimated_R_I"]) <= 1e-12
        ),
        "background_activation_does_not_inflate_R_I": (
            abs(parentage["background_augmented_R_I"] - parentage["estimated_R_I"])
            <= 1e-12
            and abs(parentage["unattributed_background_weight_added"] - 1.0) <= 1e-12
        ),
        "relocation_not_net_reproduction": (
            relocation["gross_R_I"] > 0
            and relocation["net_R_I"] == 0
            and relocation["relocation_or_parent_extinction_weight"] == 1.0
        ),
        "repeated_episodes_are_episode_specific": (
            repeated["eligible_parent_activations"] == 2
            and repeated["eligible_parent_localities"] == 1
            and repeated["estimated_R_I"] == 1.0
        ),
        "ipw_recovers_known_censoring_truth": (
            ipw_error <= 0.10 and ipw_error < complete_error
        ),
        "dependence_aware_bootstrap_declared": (
            censoring["bootstrap_method"] == "cluster_bootstrap_parent_activations"
            and censoring["bootstrap_cluster_count"] == 8
            and censoring["bootstrap_inferential_license"] is True
        ),
    }
    return {
        "schema_version": "1.0.0",
        "status": "complete_synthetic_reproduction_identification_gate",
        "historical_outcomes_used": False,
        "empirical_parameter_fitting": False,
        "seed": seed,
        "spatial": spatial,
        "R_I_parentage": parentage,
        "R_I_relocation": relocation,
        "R_I_repeated_episodes": repeated,
        "R_I_censoring": censoring,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(seed=args.seed)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
