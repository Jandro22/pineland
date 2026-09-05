"""Data-free identification utilities for spatial reproduction diagnostics."""
from __future__ import annotations

from collections import defaultdict
import argparse
import json
from pathlib import Path
import random
from statistics import mean
import sys
from typing import Hashable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
ActiveCell = tuple[str, int]


def build_risk_set(
    active: set[ActiveCell],
    areas: Iterable[str],
    neighbors: Mapping[str, set[str]],
    *,
    first_period: int | None = None,
    last_period: int | None = None,
    strata: Mapping[str, Hashable] | None = None,
) -> list[dict]:
    """Build one-step activation risk rows for currently inactive areas."""
    area_set = set(areas)
    if not area_set:
        return []
    observed_periods = [period for _, period in active]
    if first_period is None:
        first_period = min(observed_periods) if observed_periods else 0
    if last_period is None:
        last_period = max(observed_periods) if observed_periods else first_period
    if last_period <= first_period:
        return []
    rows: list[dict] = []
    for period in range(first_period, last_period):
        active_now = {area for area in area_set if (area, period) in active}
        for area in sorted(area_set):
            if area in active_now:
                continue
            active_neighbors = sum(
                neighbor in active_now
                for neighbor in neighbors.get(area, set())
                if neighbor in area_set
            )
            rows.append({
                "area": area,
                "period": period,
                "outcome": int((area, period + 1) in active),
                "exposed": int(active_neighbors > 0),
                "active_neighbor_count": active_neighbors,
                "degree": sum(neighbor in area_set for neighbor in neighbors.get(area, set())),
                "stratum": None if strata is None else strata.get(area),
            })
    return rows


def risk_difference(rows: Sequence[Mapping]) -> dict[str, float | int | None]:
    exposed = [int(row["outcome"]) for row in rows if int(row["exposed"])]
    unexposed = [int(row["outcome"]) for row in rows if not int(row["exposed"])]
    exposed_rate = mean(exposed) if exposed else None
    unexposed_rate = mean(unexposed) if unexposed else None
    return {
        "exposed_n": len(exposed),
        "unexposed_n": len(unexposed),
        "exposed_rate": exposed_rate,
        "unexposed_rate": unexposed_rate,
        "risk_difference": (
            exposed_rate - unexposed_rate
            if exposed_rate is not None and unexposed_rate is not None else None
        ),
        "causal_claim_licensed": False,
    }


def stratified_risk_difference(
    rows: Sequence[Mapping],
    *,
    fields: tuple[str, ...] = ("period", "degree", "stratum"),
) -> dict[str, float | int | None]:
    """Exact-stratum standardized risk difference for synthetic recovery."""
    grouped: dict[tuple, list[Mapping]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(field) for field in fields)].append(row)
    weighted_sum = 0.0
    total_weight = 0
    matched_strata = 0
    matched_rows = 0
    for group in grouped.values():
        exposed = [int(row["outcome"]) for row in group if int(row["exposed"])]
        unexposed = [int(row["outcome"]) for row in group if not int(row["exposed"])]
        if not exposed or not unexposed:
            continue
        weight = 2 * min(len(exposed), len(unexposed))
        weighted_sum += weight * (mean(exposed) - mean(unexposed))
        total_weight += weight
        matched_rows += len(exposed) + len(unexposed)
        matched_strata += 1
    return {
        "risk_difference": weighted_sum / total_weight if total_weight else None,
        "matched_strata": matched_strata,
        "matched_rows": matched_rows,
        "effective_weight": total_weight,
        "causal_claim_licensed": False,
    }


def dose_response(rows: Sequence[Mapping]) -> dict[int, dict[str, float | int]]:
    by_dose: dict[int, list[int]] = defaultdict(list)
    for row in rows:
        by_dose[int(row["active_neighbor_count"])].append(int(row["outcome"]))
    return {
        dose: {"n": len(values), "activation_rate": mean(values)}
        for dose, values in sorted(by_dose.items())
    }


def episode_metrics(
    active: set[ActiveCell],
    areas: Iterable[str] | None = None,
    *,
    first_period: int | None = None,
    last_period: int | None = None,
) -> dict[str, float | int | None | str]:
    """Separate continuous episodes from extinction followed by reactivation."""
    area_set = set(areas or {area for area, _ in active})
    periods = [period for _, period in active]
    if first_period is None:
        first_period = min(periods) if periods else 0
    if last_period is None:
        last_period = max(periods) if periods else first_period
    episodes: list[tuple[str, int, int]] = []
    reactivations = 0
    for area in sorted(area_set):
        active_periods = sorted(period for observed_area, period in active if observed_area == area)
        if not active_periods:
            continue
        start = previous = active_periods[0]
        for period in active_periods[1:]:
            if period == previous + 1:
                previous = period
                continue
            episodes.append((area, start, previous))
            reactivations += 1
            start = previous = period
        episodes.append((area, start, previous))
    completed = [
        end - start + 1
        for _, start, end in episodes
        if start > first_period and end < last_period
    ]
    left_censored = sum(start <= first_period for _, start, _ in episodes)
    right_censored = sum(end >= last_period for _, _, end in episodes)
    continuation_eligible = sum(
        (area, period) in active
        for area in area_set
        for period in range(first_period, last_period)
    )
    continued = sum(
        (area, period + 1) in active
        for area in area_set
        for period in range(first_period, last_period)
        if (area, period) in active
    )
    return {
        "episode_count": len(episodes),
        "completed_episode_count": len(completed),
        "left_censored_episode_count": left_censored,
        "right_censored_episode_count": right_censored,
        "mean_completed_episode_duration": mean(completed) if completed else None,
        "reactivation_count": reactivations,
        "continuation_n": continuation_eligible,
        "continuation_rate": continued / continuation_eligible if continuation_eligible else None,
        "interpretation": (
            "Episode continuity and post-extinction reactivation are separate; "
            "completed-duration summaries exclude both left-censored initial "
            "episodes and right-censored terminal episodes."
        ),
    }


def _area_time_series(active: set[ActiveCell], area: str) -> set[int]:
    return {period for observed_area, period in active if observed_area == area}


def permute_area_histories(
    active: set[ActiveCell],
    areas: Iterable[str],
    neighbors: Mapping[str, set[str]],
    rng: random.Random,
    *,
    strata: Mapping[str, Hashable] | None = None,
) -> set[ActiveCell]:
    """Permute full histories within degree and pre-treatment strata."""
    area_set = sorted(set(areas))
    area_lookup = set(area_set)
    groups: dict[tuple, list[str]] = defaultdict(list)
    for area in area_set:
        key = (
            sum(neighbor in area_lookup for neighbor in neighbors.get(area, set())),
            None if strata is None else strata.get(area),
        )
        groups[key].append(area)
    result: set[ActiveCell] = set()
    for members in groups.values():
        donors = list(members)
        rng.shuffle(donors)
        for target, source in zip(members, donors):
            result.update((target, period) for period in _area_time_series(active, source))
    return result


def topology_placebo(
    active: set[ActiveCell],
    areas: Iterable[str],
    neighbors: Mapping[str, set[str]],
    *,
    permutations: int = 199,
    seed: int = 20260905,
    strata: Mapping[str, Hashable] | None = None,
) -> dict:
    area_set = set(areas)
    observed = risk_difference(
        build_risk_set(active, area_set, neighbors, strata=strata)
    )["risk_difference"]
    if observed is None or permutations <= 0:
        return {
            "observed_risk_difference": observed,
            "placebo_repetitions": 0,
            "effective_permutations": 0,
            "placebo_mean": None,
            "two_sided_randomization_p": None,
            "causal_claim_licensed": False,
        }
    rng = random.Random(seed)
    values: list[float] = []
    effective = 0
    for _ in range(permutations):
        shuffled = permute_area_histories(active, area_set, neighbors, rng, strata=strata)
        if shuffled != active:
            effective += 1
        value = risk_difference(
            build_risk_set(shuffled, area_set, neighbors, strata=strata)
        )["risk_difference"]
        if value is not None:
            values.append(float(value))
    tail = sum(abs(value) >= abs(float(observed)) for value in values)
    return {
        "observed_risk_difference": observed,
        "placebo_repetitions": len(values),
        "effective_permutations": effective,
        "placebo_mean": mean(values) if values else None,
        "two_sided_randomization_p": (tail + 1) / (len(values) + 1) if values else None,
        "causal_claim_licensed": False,
        "interpretation": (
            "Topology placebos test adjacency alignment but cannot eliminate "
            "unmeasured spatial frailty or common causes."
        ),
    }


def lead_placebo_risk_difference(
    active: set[ActiveCell],
    areas: Iterable[str],
    neighbors: Mapping[str, set[str]],
) -> dict:
    """Use future neighbor activity as a temporal placebo/warning diagnostic."""
    area_set = set(areas)
    periods = [period for _, period in active]
    if not periods:
        return risk_difference([])
    first_period, last_period = min(periods), max(periods)
    rows: list[dict] = []
    for period in range(first_period + 1, last_period):
        for area in sorted(area_set):
            if (area, period - 1) in active:
                continue
            future_exposure = any(
                (neighbor, period + 1) in active
                for neighbor in neighbors.get(area, set())
                if neighbor in area_set
            )
            rows.append({
                "outcome": int((area, period) in active),
                "exposed": int(future_exposure),
            })
    result = risk_difference(rows)
    result["interpretation"] = (
        "Future-neighbor exposure is a temporal placebo. A positive association can arise "
        "from common shocks or reverse propagation from the target into its neighbors, so "
        "it is a warning diagnostic rather than a quantity expected to equal zero in a "
        "feedback network."
    )
    return result


def transition_identification_summary(
    active: set[ActiveCell],
    areas: Iterable[str],
    neighbors: Mapping[str, set[str]],
    *,
    strata: Mapping[str, Hashable] | None = None,
    placebo_repetitions: int = 99,
    seed: int = 20260905,
) -> dict:
    rows = build_risk_set(active, areas, neighbors, strata=strata)
    return {
        "episode_metrics": episode_metrics(active, areas),
        "crude_neighbor_association": risk_difference(rows),
        "stratified_neighbor_association": stratified_risk_difference(rows),
        "dose_response": dose_response(rows),
        "lead_placebo": lead_placebo_risk_difference(active, areas, neighbors),
        "topology_placebo": topology_placebo(
            active, areas, neighbors, permutations=placebo_repetitions,
            seed=seed, strata=strata,
        ),
        "causal_propagation_claim_licensed": False,
        "license_requirements": [
            "synthetic zero-propagation false-positive recovery",
            "known nonzero propagation recovery",
            "spatial-frailty and degree-confounding null recovery",
            "lead and topology placebo behavior",
            "episode-aware persistence recovery",
            "competing-risk and parentage recovery",
            "censoring recovery",
        ],
    }


def simulate_binary_world(
    areas: Sequence[str],
    neighbors: Mapping[str, set[str]],
    *,
    periods: int,
    seed: int,
    baseline: Mapping[str, float] | float = 0.04,
    persistence: float = 0.0,
    propagation: float = 0.0,
    common_shock: Mapping[int, float] | None = None,
) -> set[ActiveCell]:
    """Generate a small known-DGP binary world using common random numbers."""
    if periods < 2:
        raise ValueError("periods must be at least 2")
    result: set[ActiveCell] = set()
    ordered = list(areas)
    for period in range(periods):
        previous = {area for area in ordered if (area, period - 1) in result}
        for area in ordered:
            base = float(baseline[area] if isinstance(baseline, Mapping) else baseline)
            neighbor_count = sum(neighbor in previous for neighbor in neighbors.get(area, set()))
            probability = base
            if area in previous:
                probability += persistence
            else:
                probability += propagation * neighbor_count
            if common_shock is not None:
                probability += float(common_shock.get(period, 0.0))
            probability = min(0.995, max(0.0, probability))
            draw = random.Random(f"{seed}:{area}:{period}").random()
            if draw < probability:
                result.add((area, period))
    return result


def ring_neighbors(areas: Sequence[str]) -> dict[str, set[str]]:
    if len(areas) < 3:
        raise ValueError("ring requires at least three areas")
    return {
        area: {areas[(index - 1) % len(areas)], areas[(index + 1) % len(areas)]}
        for index, area in enumerate(areas)
    }


def grid_neighbors(rows: int, columns: int) -> dict[str, set[str]]:
    if rows < 2 or columns < 2:
        raise ValueError("grid requires at least 2x2 areas")
    result = {f"{row}-{column}": set()
              for row in range(rows) for column in range(columns)}
    for row in range(rows):
        for column in range(columns):
            area = f"{row}-{column}"
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = row + dr, column + dc
                if 0 <= rr < rows and 0 <= cc < columns:
                    result[area].add(f"{rr}-{cc}")
    return result


def factorial_interventional_contrasts(
    outcomes: Mapping[tuple[bool, bool], float],
) -> dict[str, float]:
    """Return transparent 2x2 controlled contrasts without regression mediation.

    The first switch is the source/exposure mechanism and the second is the
    proposed mediator/path.  Interactions are retained rather than forcing an
    additive direct/indirect decomposition.
    """
    required = {(False, False), (False, True), (True, False), (True, True)}
    if set(outcomes) != required:
        raise ValueError("factorial outcomes must contain exactly the four boolean cells")
    y00 = float(outcomes[(False, False)])
    y01 = float(outcomes[(False, True)])
    y10 = float(outcomes[(True, False)])
    y11 = float(outcomes[(True, True)])
    return {
        "source_effect_path_off": y10 - y00,
        "source_effect_path_on": y11 - y01,
        "path_effect_source_off": y01 - y00,
        "path_effect_source_on": y11 - y10,
        "interaction": y11 - y10 - y01 + y00,
        "joint_minus_neither": y11 - y00,
    }


def run_synthetic_recovery_battery(seed: int = 20260905) -> dict:
    """Adversarial data-free recovery gate for the spatial estimands."""
    areas = [f"A{index:02d}" for index in range(48)]
    neighbors = ring_neighbors(areas)
    strata = {
        area: ("high" if (index // 6) % 2 == 0 else "low")
        for index, area in enumerate(areas)
    }
    baseline = {
        area: (0.18 if strata[area] == "high" else 0.015)
        for area in areas
    }
    null = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed, baseline=0.04,
    )
    frailty = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed + 1, baseline=baseline,
    )
    propagation = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed + 2,
        baseline=0.025, propagation=0.18,
    )
    low_persistence = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed + 3,
        baseline=0.04, persistence=0.05,
    )
    high_persistence = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed + 3,
        baseline=0.04, persistence=0.70,
    )
    combined = simulate_binary_world(
        areas, neighbors, periods=240, seed=seed + 8,
        baseline=0.025, persistence=0.55, propagation=0.14,
    )
    degree_neighbors = grid_neighbors(8, 8)
    degree_areas = sorted(degree_neighbors)
    degree_baseline = {
        area: 0.01 + 0.14 * (len(degree_neighbors[area]) - 2)
        for area in degree_areas
    }
    degree_null = simulate_binary_world(
        degree_areas, degree_neighbors, periods=300, seed=seed + 4,
        baseline=degree_baseline,
    )
    common_shock = {
        period: (0.18 if (period // 10) % 2 == 0 else 0.0)
        for period in range(300)
    }
    shock_null = simulate_binary_world(
        areas, neighbors, periods=300, seed=seed + 5,
        baseline=0.01, common_shock=common_shock,
    )
    null_rd = risk_difference(build_risk_set(null, areas, neighbors))["risk_difference"]
    frailty_rows = build_risk_set(frailty, areas, neighbors, strata=strata)
    frailty_crude = risk_difference(frailty_rows)["risk_difference"]
    frailty_adjusted = stratified_risk_difference(
        frailty_rows, fields=("period", "degree", "stratum")
    )["risk_difference"]
    propagation_rd = risk_difference(
        build_risk_set(propagation, areas, neighbors)
    )["risk_difference"]
    propagation_dose = dose_response(
        build_risk_set(propagation, areas, neighbors)
    )
    combined_rd = risk_difference(
        build_risk_set(combined, areas, neighbors)
    )["risk_difference"]
    combined_episode = episode_metrics(combined, areas)
    degree_rows = build_risk_set(degree_null, degree_areas, degree_neighbors)
    degree_crude = risk_difference(degree_rows)["risk_difference"]
    degree_adjusted = stratified_risk_difference(
        degree_rows, fields=("period", "degree")
    )["risk_difference"]
    shock_rows = build_risk_set(shock_null, areas, neighbors)
    shock_crude = risk_difference(shock_rows)["risk_difference"]
    shock_adjusted = stratified_risk_difference(
        shock_rows, fields=("period", "degree")
    )["risk_difference"]
    propagation_placebo = topology_placebo(
        propagation, areas, neighbors, permutations=99, seed=seed + 6
    )
    low_episode = episode_metrics(low_persistence, areas)
    high_episode = episode_metrics(high_persistence, areas)
    empty_neighbors = {area: set() for area in areas}
    factorial_outcomes: dict[tuple[bool, bool], float] = {}
    for source_on in (False, True):
        for path_on in (False, True):
            cell_neighbors = neighbors if source_on else empty_neighbors
            cell = simulate_binary_world(
                areas, cell_neighbors, periods=200, seed=seed + 7,
                baseline=0.025,
                propagation=(0.18 if path_on else 0.0),
            )
            factorial_outcomes[(source_on, path_on)] = (
                len(cell) / (len(areas) * 200)
            )
    mediation = factorial_interventional_contrasts(factorial_outcomes)
    gates = {
        "homogeneous_null_near_zero": (
            null_rd is not None and abs(float(null_rd)) <= 0.035
        ),
        "frailty_adjustment_reduces_spurious_signal": (
            frailty_crude is not None and frailty_adjusted is not None
            and abs(float(frailty_adjusted)) + 0.015 < abs(float(frailty_crude))
        ),
        "frailty_adjusted_near_zero": (
            frailty_adjusted is not None and abs(float(frailty_adjusted)) <= 0.04
        ),
        "known_propagation_detected": (
            propagation_rd is not None and float(propagation_rd) >= 0.07
        ),
        "known_neighbor_dose_response_recovered": (
            set(propagation_dose) >= {0, 1, 2}
            and propagation_dose[0]["n"] >= 100
            and propagation_dose[1]["n"] >= 100
            and propagation_dose[2]["n"] >= 20
            and propagation_dose[0]["activation_rate"]
                < propagation_dose[1]["activation_rate"]
                < propagation_dose[2]["activation_rate"]
        ),
        "combined_persistence_and_propagation_recovered": (
            combined_rd is not None
            and float(combined_rd) >= 0.07
            and combined_episode["mean_completed_episode_duration"] is not None
            and low_episode["mean_completed_episode_duration"] is not None
            and float(combined_episode["mean_completed_episode_duration"])
                >= float(low_episode["mean_completed_episode_duration"]) + 0.5
        ),
        "degree_confounding_adjusted_near_zero": (
            degree_crude is not None and degree_adjusted is not None
            and abs(float(degree_crude)) >= 0.03
            and abs(float(degree_adjusted)) <= 0.025
        ),
        "serial_common_shock_adjusted_near_zero": (
            shock_crude is not None and shock_adjusted is not None
            and abs(float(shock_crude)) >= 0.04
            and abs(float(shock_adjusted)) <= 0.025
        ),
        "topology_placebo_breaks_known_propagation_alignment": (
            propagation_placebo["placebo_mean"] is not None
            and propagation_placebo["two_sided_randomization_p"] is not None
            and float(propagation_placebo["observed_risk_difference"])
                >= float(propagation_placebo["placebo_mean"]) + 0.08
            and float(propagation_placebo["two_sided_randomization_p"]) <= 0.05
        ),
        "known_persistence_increases_episode_duration": (
            low_episode["mean_completed_episode_duration"] is not None
            and high_episode["mean_completed_episode_duration"] is not None
            and float(high_episode["mean_completed_episode_duration"])
            >= float(low_episode["mean_completed_episode_duration"]) + 1.0
        ),
        "factorial_path_ablation_recovers_joint_requirement": (
            abs(mediation["source_effect_path_off"]) <= 1e-12
            and abs(mediation["path_effect_source_off"]) <= 1e-12
            and mediation["joint_minus_neither"] >= 0.005
            and mediation["interaction"] >= 0.005
        ),
    }
    return {
        "schema_version": "1.0.0",
        "status": "synthetic_identification_recovery_not_empirical_fit",
        "historical_outcomes_used": False,
        "seed": seed,
        "metrics": {
            "homogeneous_null_crude_risk_difference": null_rd,
            "frailty_null_crude_risk_difference": frailty_crude,
            "frailty_null_stratified_risk_difference": frailty_adjusted,
            "known_propagation_crude_risk_difference": propagation_rd,
            "known_propagation_dose_response": propagation_dose,
            "combined_persistence_propagation_risk_difference": combined_rd,
            "combined_persistence_propagation_mean_completed_duration":
                combined_episode["mean_completed_episode_duration"],
            "degree_null_crude_risk_difference": degree_crude,
            "degree_null_stratified_risk_difference": degree_adjusted,
            "common_shock_null_crude_risk_difference": shock_crude,
            "common_shock_null_time_stratified_risk_difference": shock_adjusted,
            "known_propagation_topology_placebo": propagation_placebo,
            "low_persistence_mean_completed_duration":
                low_episode["mean_completed_episode_duration"],
            "high_persistence_mean_completed_duration":
                high_episode["mean_completed_episode_duration"],
            "factorial_interventional_contrasts": mediation,
        },
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_synthetic_recovery_battery(seed=args.seed)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        # This is a data-free synthetic result, but it still needs exact
        # provenance so later theory reviews can distinguish it from a result
        # generated by another live source tree.
        sys.path.insert(0, str(ROOT / "src"))
        from pineland_sim.reproducibility import (  # noqa: E402
            environment_manifest, file_sha256, model_sha256, repository_state,
        )
        state = repository_state(ROOT)
        manifest = {
            "schema_version": "1.0.0",
            "artifact": output.relative_to(ROOT).as_posix(),
            "artifact_sha256": file_sha256(output),
            "script": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "script_sha256": file_sha256(Path(__file__).resolve()),
            "seed": args.seed,
            "historical_outcomes_used": False,
            "historical_parameter_fitting": False,
            "model_sha256_at_generation": model_sha256(ROOT),
            "commit_hash": state["commit_hash"],
            "dirty_tree": state["dirty_tree"],
            "tracked_diff_sha256": state["tracked_diff_sha256"],
            "environment": environment_manifest(),
            "status": "synthetic_identification_recovery_not_empirical_fit",
        }
        manifest_path = output.with_name(output.stem + "_manifest.json")
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(payload, end="")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
