"""Reproducible validation batteries requested by the pre-publication audit.

The functions in this module are deliberately small orchestration layers around
the simulator.  They do not assert that synthetic priors are empirically
valid; they produce the evidence needed to tell implementation, identification,
measurement, and mechanism failures apart.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict
from math import sqrt
import os
from statistics import mean, pstdev
import sys
import time as walltime
import tracemalloc
import random
from typing import Any, Callable, Iterable

from .config import SimulationConfig
from .entities import OrganizationKind, clamp
from .generator import generate_pineland
from .processes import ProcessEngine
from .simulation import Simulation
from .events import ScheduledEvent
from .validation import (
    SAMPLE_BOUNDS,
    _event_metrics,
    empirical_target_contract,
    latin_hypercube,
    run_model,
    score_targets,
    set_parameter,
)
from .networks import degree_preserving_rewire, network_diagnostics
from .empirical import first_paper_experiment_spec
from .reproducibility import decision_state_sha256, trajectory_sha256


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "std": 0.0, "p05": 0.0, "median": 0.0, "p95": 0.0}
    ordered = sorted(values)
    quantile = lambda q: ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
    return {"n": len(values), "mean": mean(values), "std": pstdev(values),
            "p05": quantile(.05), "median": quantile(.5), "p95": quantile(.95)}


def output_mode_benchmark(config: SimulationConfig, horizon_days: float | None = None) -> dict[str, Any]:
    """Benchmark output fidelity while checking identical scientific state.

    The benchmark intentionally uses one configuration and one seed per mode.
    Output mode may change retained diagnostics only; event ordering, process
    RNG streams, and final scientific state must remain equal.
    """
    runs = {}
    reference = None
    for mode in ("forensic", "ensemble", "calibration"):
        trial = SimulationConfig.from_dict(config.to_dict())
        trial.output_mode = mode
        if horizon_days is not None:
            trial.horizon_days = horizon_days
        tracemalloc.start()
        started = walltime.perf_counter()
        world = Simulation(generate_pineland(trial)).run().world
        elapsed = walltime.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        signature = world.summary()
        signature.pop("output_mode", None)
        # These fields intentionally describe retained output, not dynamics.
        for key in ("events", "synthetic_records", "synthetic_recording_rate",
                    "state_delta_records"):
            signature.pop(key, None)
        state_hash = decision_state_sha256(world)
        trajectory_hash = trajectory_sha256(world)
        scientific_hashes = (state_hash, trajectory_hash)
        if reference is None:
            reference = scientific_hashes
        runs[mode] = {"seconds": elapsed, "peak_bytes": peak,
                      "scientific_signature": signature,
                      "decision_state_sha256": state_hash,
                      "trajectory_sha256": trajectory_hash,
                      "event_log_records": len(world.event_log),
                      "state_delta_records": len(world.state_deltas),
                      "synthetic_records": len(world.synthetic_records),
                      "same_as_reference": scientific_hashes == reference}
    return {"modes": runs,
            "trajectory_equivalence": all(row["same_as_reference"] for row in runs.values()),
            "interpretation": "Timing/memory differences are output overhead only; a false equivalence flag indicates a dynamics-changing logging path."}


def _rank_correlation(first: list[float], second: list[float]) -> float:
    """Spearman rank correlation with deterministic average ranks for ties."""
    if len(first) != len(second) or len(first) < 2:
        return 0.0

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: (values[index], index))
        result = [0.0] * len(values)
        cursor = 0
        while cursor < len(order):
            end = cursor + 1
            while end < len(order) and values[order[end]] == values[order[cursor]]:
                end += 1
            rank = (cursor + 1 + end) / 2.0
            for position in order[cursor:end]:
                result[position] = rank
            cursor = end
        return result

    first_ranks, second_ranks = ranks(first), ranks(second)
    mean_first, mean_second = mean(first_ranks), mean(second_ranks)
    numerator = sum((a - mean_first) * (b - mean_second)
                    for a, b in zip(first_ranks, second_ranks))
    denominator = sqrt(sum((a - mean_first) ** 2 for a in first_ranks) *
                       sum((b - mean_second) ** 2 for b in second_ranks))
    return numerator / denominator if denominator else 0.0


def _pearson_correlation(first: list[float], second: list[float]) -> float:
    """Pearson correlation used for parameter-compensation diagnostics."""
    if len(first) != len(second) or len(first) < 2:
        return 0.0
    first_mean, second_mean = mean(first), mean(second)
    numerator = sum((a - first_mean) * (b - second_mean)
                    for a, b in zip(first, second))
    denominator = sqrt(sum((a - first_mean) ** 2 for a in first) *
                       sum((b - second_mean) ** 2 for b in second))
    return numerator / denominator if denominator else 0.0


def _run_metrics(config: SimulationConfig) -> dict[str, float]:
    world = Simulation(generate_pineland(config)).run().world
    metrics = _event_metrics(world)
    true_contacts = (sum(event.event_type == "contact" and
                         event.true_state_delta.get("contact", 0) > 0
                         for event in world.event_log)
                     if world.event_log else len(getattr(world, "contact_event_times", ())))
    recruits = (sum(float(event.true_state_delta.get("recruits", 0.0))
                    for event in world.event_log if event.event_type == "recruitment")
                if world.event_log else world.recruitment_total)
    proto_births = sum(transition.transition_type == "birth"
                       for transition in world.organization_transitions)
    splits = sum(transition.transition_type == "split"
                 for transition in world.organization_transitions)
    casualties = sum(float(engagement.personnel_losses.get(formation_id, 0.0))
                     for engagement in world.engagements.values()
                     for formation_id in engagement.personnel_losses)
    metrics.update({
        "represented_population": world.weighted_population(),
        "recruits_per_100k": recruits / max(1e-9, world.weighted_population()) * 100_000,
        "proto_births": float(proto_births), "splits": float(splits),
        "contacts": float(true_contacts), "casualties": casualties,
        "true_positive": float(world.information_detections["true_positive"]),
        "false_positive": float(world.information_detections["false_positive"]),
        "false_negative": float(world.information_detections["false_negative"]),
        "migration_share": metrics["external_migration_share"],
        "peace_agreement": float(bool(world.peace_agreements)),
        "peace_recurrence": metrics["recurrence"],
    })
    metrics.update(_resolution_metrics(world))
    return metrics


def _resolution_metrics(world) -> dict[str, float]:
    """Common weighted and graph metrics used by the resolution battery."""
    controls = [locality.control["government"].effective() for locality in world.localities.values()]
    lifetimes = [world.time - organization.founded_at for organization in world.organizations.values()
                 if organization.kind is OrganizationKind.INSURGENT]
    first_diffusion = next((event.time for event in world.event_log
                            if event.event_type == "social_influence" and
                            float(event.true_state_delta.get("behavior_changes", 0.0)) > 0), 0.0)
    represented = max(1e-9, world.weighted_population())
    participation = [
        1 - election.abstention / represented
        for election in world.elections if election.time >= 0
    ]
    network = network_diagnostics(world)
    return {
        "government_control_variance": pstdev(controls) ** 2 if len(controls) > 1 else 0.0,
        "organization_lifetime_days": mean(lifetimes) if lifetimes else 0.0,
        "fragmentation_eligibility_periods": float(sum(row.get("eligible", False)
                                                        for row in world.organization_eligibility_log)),
        "fragmentation_eligible_share": (sum(row.get("eligible", False)
                                              for row in world.organization_eligibility_log) /
                                          max(1, len(world.organization_eligibility_log))),
        "network_mean_degree": float(network.get("mean_degree", 0.0)),
        "network_represented_mean_degree": float(network.get("represented_mean_degree", 0.0)),
        "network_clustering": float(network.get("sampled_clustering", 0.0)),
        "network_path_length_proxy": float(network.get("path_length_proxy", 0.0)),
        "diffusion_hitting_time_days": float(first_diffusion),
        "engagements": float(len(world.engagements)),
        "casualties_per_100k": sum(sum(engagement.personnel_losses.values())
                                    for engagement in world.engagements.values()) / represented * 100_000,
        "true_negative": float(world.information_detections["true_negative"]),
        "political_participation": mean(participation) if participation else 0.0,
        "agreement_count": float(len(world.peace_agreements)),
        "recurrence_count": float(sum(t.transition_type == "recurrence" for t in world.peace_transitions)),
    }


def representative_agent_audit(config: SimulationConfig, horizon_days: float = 2.0) -> dict[str, Any]:
    """Audit weighted semantics across the population-facing subsystems.

    The simulator uses a representative-agent population.  This audit makes
    the implied units explicit and checks that community membership, initial
    organization assignment, recruitment, migration, elections, casualties,
    and fragmentation conserve represented people rather than sampled-node
    counts.  Household nodes are documented as *household archetypes / kin-
    resource cells*, not literal households of the represented population.
    """
    trial = SimulationConfig.from_dict(config.to_dict())
    trial.agent_count = min(trial.agent_count, 2_000)
    trial.horizon_days = horizon_days
    trial.output_mode = "forensic"
    world = Simulation(generate_pineland(trial)).run().world
    represented = world.weighted_population()
    weights = [person.weight for person in world.persons.values()]
    household_weights = [sum(world.persons[pid].weight for pid in household.member_ids)
                         for household in world.households.values()]
    community_total = sum(world.persons[pid].weight for community in world.social_communities.values()
                           for pid in community.member_ids if pid in world.persons)
    membership_counts = Counter(pid for community in world.social_communities.values()
                                for pid in community.member_ids)
    community_error = abs(community_total - represented)

    # Reconcile weighted recruitment against the event-level causal summaries.
    recruitment_from_events = sum(
        float(event.true_state_delta.get("recruits", 0.0))
        for event in world.event_log if event.event_type == "recruitment"
    )
    recruitment_error = abs(recruitment_from_events - world.recruitment_total)

    displaced_expected = {
        locality_id: sum(person.weight for person in world.persons.values()
                          if person.residence_locality_id == locality_id and person.displaced)
        for locality_id in world.localities
    }
    displacement_error = max(
        (abs(world.localities[locality_id].displaced_population - displaced_expected[locality_id])
         for locality_id in world.localities), default=0.0)

    # Elections are weighted votes.  The identity holds at every election,
    # including after any within-country migration.
    election_errors = []
    for election in world.elections:
        electorate = (
            election.represented_electorate
            if election.represented_electorate is not None
            else sum(election.votes.values()) + election.abstention
        )
        election_errors.append(
            abs(sum(election.votes.values()) + election.abstention - electorate)
        )

    # Continuous formation losses are represented manpower, not node counts.
    casualty_total = sum(sum(engagement.personnel_losses.values())
                         for engagement in world.engagements.values())
    casualty_bound = all(
        sum(engagement.personnel_losses.get(fid, 0.0) for engagement in world.engagements.values()) <=
        world.formations[fid].personnel + world.formations[fid].cumulative_losses + 1e-9
        for fid in world.formations
    )

    # Split transitions must assign each represented member at most once.
    split_assignment_ok = True
    for transition in world.organization_transitions:
        if transition.transition_type != "split":
            continue
        assigned = [pid for members in transition.member_assignments.values() for pid in members]
        split_assignment_ok &= len(assigned) == len(set(assigned)) and all(pid in world.persons for pid in assigned)

    checks = {
        "positive_agent_weights": all(weight > 0 for weight in weights),
        "community_weight_conservation": community_error <= 1e-9 and
        all(membership_counts.get(pid, 0) == 1 for pid in world.persons),
        "household_weights_positive": all(weight > 0 for weight in household_weights),
        "recruitment_is_weighted": recruitment_error <= 1e-9,
        "migration_is_weighted": displacement_error <= 1e-9,
        "election_weight_conservation": max(election_errors, default=0.0) <= 1e-6,
        "casualties_are_bounded": casualty_bound,
        "fragmentation_assignments_are_weighted": split_assignment_ok,
    }
    return {
        "unit_of_analysis": "representative agent with continuous represented weight",
        "household_semantics": "household archetype / kin-resource cell; sampled members are not literal persons",
        "raw_agent_count": len(world.persons),
        "represented_population": represented,
        "mean_agent_weight": mean(weights) if weights else 0.0,
        "household_weight": {"mean": mean(household_weights) if household_weights else 0.0,
                             "min": min(household_weights, default=0.0),
                             "max": max(household_weights, default=0.0)},
        "community_weight_error": community_error,
        "recruitment_weight_error": recruitment_error,
        "migration_represented_population": sum(person.weight for person in world.persons.values()
                                                  if person.external_state_id is not None),
        "displacement_weight_error": displacement_error,
        "election_weight_error": max(election_errors, default=0.0),
        "casualties": casualty_total,
        "casualties_per_100k": casualty_total / max(1e-9, represented) * 100_000,
        "organization_births": sum(t.transition_type == "birth" for t in world.organization_transitions),
        "organization_splits": sum(t.transition_type == "split" for t in world.organization_transitions),
        "checks": checks,
        "all_pass": all(checks.values()),
        "raw_count_uses": {
            "SUBSTANTIVE AND FIXED": [
                "election turnout and party allocation use fractional represented voting mass",
                "social communities are packed by represented population rather than sampled household/person count",
                "bridge-member fractions are no longer capped by a fixed raw four-node ceiling",
                "locality belief signals weight social communities by represented population",
                "political population means weight representative agents by represented population",
                "patronage reach is based on total local patronage allocation rather than the residual after division among sampled broker tokens",
                "cross-border mobility reports represented population rather than migrated agent tokens",
                "topology-ablation behavior distributions and exposure means use represented population",
                "social-influence behavior-change reporting records represented population as well as sampled agent transitions",
                "initial insurgent formation placement uses a force-specific RNG stream independent of civilian resolution",
                "civilian resource stocks are represented-population stocks rather than per-agent-token endowments",
                "household resources are a synchronized derived aggregate and are excluded from the global stock total",
                "proto material capital normalizes represented resource stock by represented founder population",
                "diaspora remittances and proto startup contributions transfer represented resource stocks without a second weight factor",
                "elite patronage is held in a distinct broker account rather than duplicating the linked civilian's starting wealth",
                "proto-founder participation is an exact fractional slice of represented mobilized population, eliminating last-token founder overshoot",
                "local recruitment access scales continuously with represented member foothold or effective local formation personnel rather than any-positive membership",
            ],
            "BENIGN IMPLEMENTATION DETAIL": [
                "sampled-node and event IDs",
                "graph degree, clustering, edge count, and path-length diagnostics explicitly describe the sampled graph",
                "fixed-size candidate subsamples used only to search graph neighbors, such as the 12-node bridge target sample",
                "minimum two-node checks required to partition or rewire graph data structures",
                "counts of organizations, formations, mediators, provisions, institutions, and other explicit actor tokens",
            ],
            "SUBSTANTIVE AND UNRESOLVED": [],
            "note": "No known substantive raw-count population/manpower mechanism remains unresolved in this audit. Raw node counts listed as benign are graph/implementation quantities, not represented-population thresholds.",
        },
    }


def _recorded_metrics(config: SimulationConfig) -> dict[str, float]:
    """Extract targets from the synthetic recorded layer, not latent truth."""
    trial = SimulationConfig.from_dict(config.to_dict())
    trial.output_mode = "ensemble"
    world = Simulation(generate_pineland(trial)).run().world
    records = [record for record in world.synthetic_records if record.recorded]
    contacts = sum(
        record.event_type in {"contact", "state_based_violence"}
        for record in records
    )
    return {
        "recorded_event_frequency": contacts / max(1.0, world.time),
        "recording_rate": len(records) / max(1, len(world.event_log)),
        "geocoding_error_rate": mean(record.geocoding_error for record in records) if records else 0.0,
    }


def resolution_ladder(config: SimulationConfig, agent_counts: Iterable[int] = (25_000, 75_000, 250_000),
                      seeds: Iterable[int] = (1, 2, 3), horizon_days: float | None = None) -> dict[str, Any]:
    """Run a multi-seed distributional resolution ladder at fixed population."""
    counts = list(agent_counts); seed_values = list(seeds)
    if len(counts) < 2 or not seed_values or any(count <= 0 for count in counts):
        raise ValueError("resolution ladder needs two positive resolutions and one seed")
    metrics_by_count: dict[int, list[dict[str, float]]] = {}
    for count in counts:
        rows = []
        for seed in seed_values:
            trial = SimulationConfig.from_dict(config.to_dict())
            trial.agent_count, trial.seed = count, seed
            trial.output_mode = "ensemble"
            if horizon_days is not None:
                trial.horizon_days = horizon_days
            rows.append(_run_metrics(trial))
        metrics_by_count[count] = rows
    metric_names = sorted(set().union(*(row.keys() for row in metrics_by_count[counts[0]])))
    distributions = {
        str(count): {name: _distribution([row[name] for row in rows]) for name in metric_names}
        for count, rows in metrics_by_count.items()
    }
    reference = counts[-1]
    comparisons = []
    for count in counts[:-1]:
        reference_dist = distributions[str(reference)]
        metric_rows = {}
        standardized = {}
        distribution_distance = {}
        for name in metric_names:
            diff = distributions[str(count)][name]["mean"] - reference_dist[name]["mean"]
            metric_rows[name] = diff
            pooled = ((distributions[str(count)][name]["std"] ** 2 +
                       reference_dist[name]["std"] ** 2) / 2) ** .5
            standardized[name] = diff / pooled if pooled > 0 else 0.0
            left_values = sorted(row[name] for row in metrics_by_count[count])
            right_values = sorted(row[name] for row in metrics_by_count[reference])
            quantile_diffs = []
            for q_index in range(21):
                q = q_index / 20
                left = left_values[min(len(left_values) - 1, round(q * (len(left_values) - 1)))]
                right = right_values[min(len(right_values) - 1, round(q * (len(right_values) - 1)))]
                quantile_diffs.append(abs(left - right))
            distribution_distance[name] = sum(quantile_diffs) / len(quantile_diffs)
        comparisons.append({
            "agent_count": count, "reference_agent_count": reference,
            "metrics": metric_rows,
            "standardized_mean_differences": standardized,
            "mean_absolute_quantile_differences": distribution_distance,
        })
    return {"agent_counts": counts, "seeds": seed_values,
            "horizon_days": horizon_days if horizon_days is not None else config.horizon_days,
            "represented_population": {str(count): distributions[str(count)]["represented_population"]["mean"]
                                        for count in counts},
            "distributions": distributions, "comparisons": comparisons,
            "power_warning": len(seed_values) < 3 or len(counts) < 3,
            "interpretation": "Distributional resolution diagnostic; tolerances must be declared per research question."}


def initialization_ensemble(config: SimulationConfig, seeds: Iterable[int] = (1, 2, 3),
                            horizon_days: float | None = None) -> dict[str, Any]:
    """Quantify dependence on plausible structural initializations."""
    seed_values = list(seeds)
    rows = []
    for index, seed in enumerate(seed_values):
        trial = SimulationConfig.from_dict(config.to_dict())
        trial.seed = seed
        trial.random_stream_namespace = f"initialization-{index:04d}"
        if horizon_days is not None:
            trial.horizon_days = horizon_days
        rows.append(_run_metrics(trial))
    names = sorted(set().union(*(row.keys() for row in rows))) if rows else []
    return {"seeds": seed_values, "metrics": {name: _distribution([row[name] for row in rows])
                                               for name in names}, "samples": rows}


def morris_sensitivity(config: SimulationConfig, outcomes: list[str],
                       parameters: list[str] | None = None, trajectories: int = 16,
                       levels: int = 6, repetitions: int = 2) -> dict[str, Any]:
    """Global Morris elementary-effect screening for nonlinear interactions."""
    parameters = parameters or list(SAMPLE_BOUNDS)
    if trajectories < 1 or levels < 3:
        raise ValueError("Morris screening needs positive trajectories and at least three levels")
    records: list[dict[str, Any]] = []
    step = 1 / (levels - 1)

    def evaluate(template: SimulationConfig, seed_base: int) -> dict[str, float]:
        rows = []
        for repetition in range(repetitions):
            trial = SimulationConfig.from_dict(template.to_dict()); trial.seed = seed_base + repetition
            metrics = run_model(trial)
            rows.append({outcome: metrics[outcome] for outcome in outcomes})
        return {outcome: mean(row[outcome] for row in rows) for outcome in outcomes}

    for trajectory in range(trajectories):
        current = {name: (lo + hi) / 2 for name, (lo, hi, _, _) in
                   ((name, SAMPLE_BOUNDS[name]) for name in parameters)}
        order = list(parameters)
        # Deterministic rotation gives every parameter a comparable number of
        # elementary effects without a global random-state side effect.
        shift = trajectory % max(1, len(order)); order = order[shift:] + order[:shift]
        base = SimulationConfig.from_dict(config.to_dict()); base.seed = config.seed + 50_000 + trajectory
        for name in order:
            lo, hi, _, _ = SAMPLE_BOUNDS[name]
            current[name] = lo + (((trajectory + parameters.index(name) + 1) % (levels - 1)) * step) * (hi - lo)
        for path, value in current.items():
            set_parameter(base, path, value)
        previous = evaluate(base, base.seed + 10_000)
        for position, name in enumerate(order):
            trial = SimulationConfig.from_dict(base.to_dict())
            trial.seed = config.seed + 50_000 + trajectory * 101 + position
            lo, hi, _, _ = SAMPLE_BOUNDS[name]
            old = current[name]
            old_level = round((old - lo) / max(1e-12, hi - lo) * (levels - 1))
            new_level = (old_level + 1 + trajectory) % levels
            current[name] = lo + (new_level / (levels - 1)) * (hi - lo)
            for path, value in current.items():
                set_parameter(trial, path, value)
            now = evaluate(trial, trial.seed + 20_000)
            for outcome in outcomes:
                lo, hi, _, _ = SAMPLE_BOUNDS[name]
                records.append({"trajectory": trajectory, "parameter": name,
                                "outcome": outcome,
                                "elementary_effect": (now[outcome] - previous[outcome]) /
                                                    max(1e-12, hi - lo)})
            previous = now
    analysis = {}
    for name in parameters:
        for outcome in outcomes:
            values = [row["elementary_effect"] for row in records
                      if row["parameter"] == name and row["outcome"] == outcome]
            analysis[f"{name}:{outcome}"] = {"mu": mean(values) if values else 0.0,
                                               "mu_star": mean(abs(x) for x in values) if values else 0.0,
                                               "sigma": pstdev(values) if len(values) > 1 else 0.0,
                                               "n": len(values)}
    return {"method": "Morris elementary effects", "levels": levels,
            "trajectories": trajectories, "repetitions": repetitions,
            "parameters": parameters, "analysis": analysis, "records": records,
            "power_warning": trajectories < 16 or repetitions < 2}


def variance_sensitivity(config: SimulationConfig, outcomes: list[str],
                        parameters: list[str] | None = None, samples: int = 32,
                        repetitions: int = 2) -> dict[str, Any]:
    """Saltelli-style first/total variance indices on a question subset."""
    parameters = parameters or list(SAMPLE_BOUNDS)
    if samples < 2:
        raise ValueError("variance sensitivity needs at least two samples")
    draws_a = latin_hypercube(samples, parameters, config.seed + 101)
    draws_b = latin_hypercube(samples, parameters, config.seed + 202)
    stochastic_variances: dict[str, list[float]] = {outcome: [] for outcome in outcomes}

    def evaluate(draw: dict[str, float], seed: int) -> dict[str, float]:
        trial = SimulationConfig.from_dict(config.to_dict()); trial.seed = seed
        for path, value in draw.items(): set_parameter(trial, path, value)
        values = {outcome: [] for outcome in outcomes}
        for repetition in range(repetitions):
            trial.seed = seed + repetition
            row = run_model(trial)
            for outcome in outcomes:
                values[outcome].append(row[outcome])
        for outcome in outcomes:
            if len(values[outcome]) > 1:
                stochastic_variances[outcome].append(pstdev(values[outcome]) ** 2)
        return {outcome: mean(values[outcome]) for outcome in outcomes}

    y_a = [evaluate(draw, config.seed + 700_000 + index * 17) for index, draw in enumerate(draws_a)]
    y_b = [evaluate(draw, config.seed + 800_000 + index * 17) for index, draw in enumerate(draws_b)]
    y_ab: dict[str, list[dict[str, float]]] = {name: [] for name in parameters}
    for parameter_index, parameter in enumerate(parameters):
        rows = []
        for index in range(samples):
            draw = dict(draws_a[index]); draw[parameter] = draws_b[index][parameter]
            rows.append(evaluate(draw, config.seed + 900_000 + parameter_index * 10_000 + index * 17))
        y_ab[parameter] = rows
    analysis = {}
    for outcome in outcomes:
        combined = [row[outcome] for row in y_a + y_b]
        variance = pstdev(combined) ** 2
        if variance <= 1e-18:
            variance = 1e-18
        indices = {}
        center = mean(combined)
        for parameter in parameters:
            first_terms = [(y_b[i][outcome] - center) *
                           (y_ab[parameter][i][outcome] - y_a[i][outcome])
                           for i in range(samples)]
            total_terms = [(y_a[i][outcome] - y_ab[parameter][i][outcome]) ** 2
                           for i in range(samples)]
            first_raw = mean(first_terms) / variance
            total_raw = mean(total_terms) / (2 * variance)
            first_se = (pstdev(first_terms) / max(1.0, samples) ** .5) / variance if samples > 1 else 0.0
            total_se = (pstdev(total_terms) / max(1.0, samples) ** .5) / (2 * variance) if samples > 1 else 0.0
            indices[parameter] = {
                "first_order": max(0.0, min(1.0, first_raw)),
                "total_order": max(0.0, min(1.0, total_raw)),
                "interaction_order": max(0.0, min(1.0, total_raw - first_raw)),
                "raw_first_order": first_raw, "raw_total_order": total_raw,
                "first_order_se": first_se, "total_order_se": total_se,
                "finite_sample_out_of_bounds": not (0 <= first_raw <= 1 and 0 <= total_raw <= 1),
            }
        analysis[outcome] = {"variance": variance, "indices": indices,
                             "finite_sample_warning": any(item["finite_sample_out_of_bounds"]
                                                            for item in indices.values()),
                             "stochastic_variance": mean(stochastic_variances[outcome])
                             if stochastic_variances[outcome] else 0.0,
                             "sampling_standard_error": sqrt(variance / max(1, 2 * samples))}
    return {"method": "Saltelli variance-based sensitivity", "samples": samples,
            "repetitions": repetitions, "parameters": parameters, "analysis": analysis,
            "power_warning": samples < 32 or repetitions < 2}


def parameter_recovery_ensemble(config: SimulationConfig, parameters: list[str] | None = None,
                                hidden_vectors: int = 32, candidate_samples: int = 32,
                                repetitions: int = 2) -> dict[str, Any]:
    """Repeated synthetic recovery with bias, RMSE, rank, and boundary diagnostics."""
    parameters = parameters or ["recruitment_rate", "contact_rate"]
    if repetitions < 1:
        raise ValueError("repetitions must be positive")

    def replicated_metrics(template: SimulationConfig, seed_base: int) -> dict[str, float]:
        rows = []
        for repetition in range(repetitions):
            trial = SimulationConfig.from_dict(template.to_dict())
            trial.seed = seed_base + repetition
            rows.append(_recorded_metrics(trial))
        names = rows[0].keys()
        return {name: mean(row[name] for row in rows) for name in names}

    truths = latin_hypercube(hidden_vectors, parameters, config.seed + 333)
    rows = []
    for index, truth in enumerate(truths):
        truth_config = SimulationConfig.from_dict(config.to_dict()); truth_config.seed = config.seed + 400_000 + index
        for path, value in truth.items(): set_parameter(truth_config, path, value)
        truth_metrics = replicated_metrics(truth_config, truth_config.seed)
        target_keys = [key for key in ("recorded_event_frequency", "recording_rate",
                                       "geocoding_error_rate") if key in truth_metrics]
        contract = empirical_target_contract({key: truth_metrics[key] for key in target_keys})
        candidates = latin_hypercube(candidate_samples, parameters, config.seed + 500_000 + index)
        scored = []
        for candidate_index, draw in enumerate(candidates):
            trial = SimulationConfig.from_dict(config.to_dict()); trial.seed = config.seed + 600_000 + index * 10_000 + candidate_index
            for path, value in draw.items(): set_parameter(trial, path, value)
            outcomes = replicated_metrics(trial, trial.seed)
            scored.append((score_targets(outcomes, contract)["mean_normalized_error"], draw))
        error, recovered = min(scored, key=lambda item: item[0])
        rows.append({"truth": truth, "recovered": recovered, "fit_error": error,
                     "parameter_errors": {path: recovered[path] - truth[path] for path in parameters}})
    summary = {}
    for path in parameters:
        lo, hi, _, _ = SAMPLE_BOUNDS[path]
        errors = [row["parameter_errors"][path] for row in rows]
        truth_values = [row["truth"][path] for row in rows]
        recovered_values = [row["recovered"][path] for row in rows]
        summary[path] = {"bias": mean(errors),
                         "rmse": sqrt(mean(error * error for error in errors)),
                         "rank_correlation": _rank_correlation(truth_values, recovered_values),
                         "boundary_hit_rate": mean(min(abs(value - lo), abs(value - hi)) < .01 * (hi - lo)
                                                   for value in recovered_values),
                         "failure_rate": mean(row["fit_error"] > 2.0 for row in rows),
                         "coverage": None,
                         "coverage_note": "point-estimate recovery has no interval estimator"}
    confusion = {}
    for left_index, left in enumerate(parameters):
        left_errors = [row["parameter_errors"][left] for row in rows]
        for right in parameters[left_index + 1:]:
            right_errors = [row["parameter_errors"][right] for row in rows]
            confusion[f"{left} ↔ {right}"] = {
                "error_correlation": _pearson_correlation(left_errors, right_errors),
                "interpretation": "positive values indicate shared over/under-recovery; negative values indicate compensating trade-off",
            }
    return {"method": "repeated synthetic parameter recovery", "parameters": parameters,
            "hidden_vectors": hidden_vectors, "candidate_samples": candidate_samples,
            "repetitions": repetitions, "summary": summary, "confusion_matrix": confusion,
            "runs": rows,
            "power_warning": hidden_vectors < 32 or candidate_samples < 32 or repetitions < 2}


def mechanism_ablation(config: SimulationConfig, horizon_days: float | None = None) -> dict[str, Any]:
    """Matched full-vs-knockout runs for the major explanatory pathways."""
    modes = ("full", "network_knockout", "information_knockout", "logistics_knockout",
             "political_channel_knockout", "foreign_knockout", "fragmentation_knockout")
    results = {}
    for index, mode in enumerate(modes):
        trial = SimulationConfig.from_dict(config.to_dict()); trial.seed = config.seed
        if horizon_days is not None:
            trial.horizon_days = horizon_days
        if mode == "network_knockout":
            trial.social_network.behavior_update_rate = 0.0
            trial.social_network.bridge_fraction = 0.0
        elif mode == "information_knockout":
            trial.information.civilian_report_rate = trial.information.social_report_rate = 0.0
            trial.information.administrative_report_rate = trial.information.elite_report_rate = 0.0
            trial.information.member_report_rate = trial.information.fixed_post_report_rate = 0.0
            trial.information.patrol_report_rate = 0.0
            trial.information.interpreter_report_rate = 0.0
            trial.information.contact_true_positive_rate = 0.0
            trial.contact_rate = 0.0
        elif mode == "logistics_knockout":
            trial.logistics.presence_consumption_per_person_day = 1e-12
            trial.logistics.movement_consumption_per_person_km = 0.0
            trial.logistics.patrol_consumption_per_person_hour = 0.0
        elif mode == "political_channel_knockout":
            trial.political_order.peaceful_channel_strength = 0.0
        elif mode == "foreign_knockout":
            trial.foreign_affairs.enabled = False
        elif mode == "fragmentation_knockout":
            trial.organization_ecology.split_base_hazard = 0.0
            trial.peace_process.fragmentation_penalty = 0.0
        results[mode] = _run_metrics(trial)
    full = results["full"]
    effects = {mode: {key: value - full[key] for key, value in row.items() if key in full}
               for mode, row in results.items() if mode != "full"}
    return {"modes": results, "effects_vs_full": effects,
            "interpretation": "Knockouts test whether a mechanism contributes to the selected outcomes; they are not historical counterfactuals."}


def topology_ablation(config: SimulationConfig, horizon_days: float | None = None,
                      swaps: int | None = None) -> dict[str, Any]:
    """Compare original, degree-preserving, and random-mixing social graphs.

    All worlds share generated person/community attributes and the same process
    seed.  Rewiring mutates only graph endpoints, preserving the degree
    sequence; random mixing also replaces layer/tie attributes with generic
    values so the topology contribution can be separated from multiplex edge
    semantics.
    """
    modes = ("original", "degree_preserving_rewired", "random_mixing")
    results = {}
    for mode in modes:
        trial = SimulationConfig.from_dict(config.to_dict())
        trial.agent_count = min(trial.agent_count, 2_000)
        if horizon_days is not None:
            trial.horizon_days = horizon_days
        world = generate_pineland(trial)
        before_degrees = sorted(len(neighbors) for neighbors in world.social_neighbors.values())
        rewire = {"attempts": 0, "accepted_swaps": 0}
        if mode != "original":
            rewire = degree_preserving_rewire(
                world, trial.seed + (17 if mode == "random_mixing" else 11),
                swaps=swaps, preserve_attributes=(mode != "random_mixing"),
            )
        metrics = _run_metrics_from_world(world, trial)
        diagnostics = network_diagnostics(world)
        behavior_distribution: dict[str, float] = {}
        exposure_numerator = 0.0
        exposure_denominator = 0.0
        for person in world.persons.values():
            behavior_distribution[person.public_behavior] = (
                behavior_distribution.get(person.public_behavior, 0.0) + person.weight
            )
            for value in person.social_exposure.values():
                exposure_numerator += person.weight * value
                exposure_denominator += person.weight
        after_degrees = sorted(len(neighbors) for neighbors in world.social_neighbors.values())
        results[mode] = {"metrics": metrics, "network": diagnostics,
                         "rewire": rewire,
                         "behavior_distribution": dict(sorted(behavior_distribution.items())),
                         "mean_social_exposure": (exposure_numerator / exposure_denominator
                                                  if exposure_denominator else 0.0),
                         "degree_sequence_preserved": before_degrees == after_degrees}
    baseline = results["original"]["metrics"]
    effects = {mode: {key: value - baseline[key] for key, value in row["metrics"].items()
                      if key in baseline and isinstance(value, (int, float))}
               for mode, row in results.items() if mode != "original"}
    baseline_behavior = results["original"]["behavior_distribution"]
    baseline_network = results["original"]["network"]
    graph_effects = {}
    for mode, row in results.items():
        if mode == "original":
            continue
        behavior_keys = set(baseline_behavior) | set(row["behavior_distribution"])
        graph_effects[mode] = {
            "sampled_clustering_difference": row["network"].get("sampled_clustering", 0.0) -
            baseline_network.get("sampled_clustering", 0.0),
            "mean_degree_difference": row["network"].get("mean_degree", 0.0) -
            baseline_network.get("mean_degree", 0.0),
            "mean_language_compatibility_difference": row["network"].get("mean_language_compatibility", 0.0) -
            baseline_network.get("mean_language_compatibility", 0.0),
            "mean_social_exposure_difference": row["mean_social_exposure"] - results["original"]["mean_social_exposure"],
            "behavior_distribution_l1": sum(abs(row["behavior_distribution"].get(key, 0) -
                                                baseline_behavior.get(key, 0))
                                            for key in behavior_keys) / max(1e-12, world.weighted_population()),
        }
    return {"modes": results, "effects_vs_original": effects,
            "graph_effects_vs_original": graph_effects,
            "interpretation": "Degree-preserving rewiring isolates topology; random mixing additionally removes multiplex tie attributes."}


def _run_metrics_from_world(world, config: SimulationConfig) -> dict[str, float]:
    """Run a pre-built world after graph surgery without regenerating it."""
    return _run_metrics_for_simulation(Simulation(world))


def _run_metrics_for_simulation(simulation: Simulation) -> dict[str, float]:
    world = simulation.run().world
    metrics = _event_metrics(world)
    true_contacts = (sum(event.event_type == "contact" and
                         event.true_state_delta.get("contact", 0) > 0
                         for event in world.event_log)
                     if world.event_log else len(getattr(world, "contact_event_times", ())))
    recruits = (sum(float(event.true_state_delta.get("recruits", 0.0))
                    for event in world.event_log if event.event_type == "recruitment")
                if world.event_log else world.recruitment_total)
    metrics.update({
        "recruits_per_100k": recruits / max(1e-9, world.weighted_population()) * 100_000,
        "contacts": float(true_contacts),
        "behavior_changes": float(world.behavior_change_represented_population),
        "information_observations": float(len(world.observations)),
        "casualties": float(sum(sum(engagement.personnel_losses.values())
                                 for engagement in world.engagements.values())),
        "organization_births": float(sum(t.transition_type == "birth"
                                          for t in world.organization_transitions)),
        "organization_splits": float(sum(t.transition_type == "split"
                                          for t in world.organization_transitions)),
    })
    metrics.update(_resolution_metrics(world))
    return metrics


def _language_factorial_sample(payload: tuple[dict[str, Any], str, int,
                                                float | None]) -> dict[str, Any]:
    """Run one isolated factorial cell/replication."""
    config_values, mode, repetition, horizon_days = payload
    trial = SimulationConfig.from_dict(config_values)
    trial.agent_count = min(trial.agent_count, 2_000)
    trial.seed += repetition
    if horizon_days is not None:
        trial.horizon_days = horizon_days
    topology_on = mode in {"topology", "topology_detection", "topology_fusion", "all"}
    detection_on = mode in {"detection", "topology_detection", "detection_fusion", "all"}
    fusion_on = mode in {"fusion", "topology_fusion", "detection_fusion", "all"}
    trial.social_network.language_topology_enabled = topology_on
    if not detection_on:
        trial.information.detection_language_bonus = 0.0
    if not fusion_on:
        trial.information.language_fusion_weight = 0.0

    world = Simulation(generate_pineland(trial)).run().world
    target = next((formation for formation in world.formations.values()
                   if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT), None)
    observer = next((formation for formation in world.formations.values()
                     if world.organizations[formation.organization_id].kind is not OrganizationKind.INSURGENT), None)
    target_detection = 0.0
    if target is not None and observer is not None:
        from .information import detection_probability
        target_detection = detection_probability(
            world, observer.formation_id, target.formation_id,
            target.locality_id, "patrol", target.current_microzone_id,
        )
    # Avoid the unrelated component and clustering graph walks previously run
    # for every replication; this is the only network statistic used here.
    compatibility = (mean(edge.language_compatibility for edge in world.social_edges.values())
                     if world.social_edges else 0.0)
    return {
        "mean_belief_confidence": (sum(b.confidence for b in world.control_beliefs.values()) /
                                    max(1, len(world.control_beliefs))),
        "detection_counts": dict(world.information_detections),
        "network_language_compatibility": compatibility,
        "known_target_detection_probability": target_detection,
        "government_control": world.summary()["mean_government_effective_control"],
    }


def _factorial_workers(requested: int | None, jobs: int) -> int:
    if requested is not None and requested < 1:
        raise ValueError("workers must be positive")
    return min(jobs, requested or min(8, os.cpu_count() or 1))


def language_factorial(config: SimulationConfig, horizon_days: float | None = None,
                       repetitions: int = 8, workers: int | None = None) -> dict[str, Any]:
    """Factor language across topology, detection, and fusion channels.

    All eight combinations are run with matched configuration/seed streams;
    only the named language channel is neutralized.
    """
    if repetitions < 1:
        raise ValueError("language factorial repetitions must be positive")
    modes = ("none", "topology", "detection", "fusion",
             "topology_detection", "topology_fusion", "detection_fusion", "all")
    config_values = config.to_dict()
    jobs = [(config_values, mode, repetition, horizon_days)
            for mode in modes for repetition in range(repetitions)]
    worker_count = _factorial_workers(workers, len(jobs))
    if worker_count == 1:
        completed = list(map(_language_factorial_sample, jobs))
        backend = "sequential"
    else:
        # Standard CPython needs processes for real CPU parallelism; a
        # free-threaded build can safely use lower-overhead threads.
        gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
        executor_type = ProcessPoolExecutor if gil_enabled else ThreadPoolExecutor
        backend = "processes" if gil_enabled else "threads"
        with executor_type(max_workers=worker_count) as executor:
            completed = list(executor.map(
                _language_factorial_sample, jobs,
                chunksize=max(1, len(jobs) // (worker_count * 4)),
            ))

    results = {}
    offset = 0
    for mode in modes:
        samples = completed[offset:offset + repetitions]
        offset += repetitions
        numeric = ("mean_belief_confidence", "network_language_compatibility",
                   "known_target_detection_probability", "government_control")
        aggregate = {key: mean(row[key] for row in samples) for key in numeric}
        aggregate["detection_counts"] = {
            key: sum(row["detection_counts"].get(key, 0) for row in samples)
            for key in ("true_positive", "false_positive", "false_negative", "true_negative")
        }
        aggregate["replications"] = repetitions
        aggregate["samples"] = samples
        results[mode] = aggregate
    factors = {"topology": "topology", "detection": "detection", "fusion": "fusion"}
    factor_effects = {}
    for factor in factors:
        on = [mode for mode in modes if factor in mode or mode == "all"]
        off = [mode for mode in modes if mode == "none" or factor not in mode]
        factor_effects[factor] = {
            key: mean(results[mode][key] for mode in on) - mean(results[mode][key] for mode in off)
            for key in ("mean_belief_confidence", "known_target_detection_probability", "government_control")
        }
    interactions = {}
    for first, second in (("topology", "detection"), ("topology", "fusion"), ("detection", "fusion")):
        both = f"{first}_{second}"
        first_only, second_only = first, second
        interactions[f"{first}×{second}"] = {
            key: results[both][key] - results[first_only][key] - results[second_only][key] + results["none"][key]
            for key in ("mean_belief_confidence", "known_target_detection_probability", "government_control")
        }
    return {"modes": results, "factor_effects": factor_effects,
            "interaction_effects": interactions, "replications": repetitions,
            "execution": {"workers": worker_count, "backend": backend},
            "interpretation": "Eight-cell ensemble factorial separates language-sensitive detection/fusion from topology-sensitive network effects; effects are mean differences over matched replications."}


def fragmentation_bargaining_ablation(config: SimulationConfig,
                                       horizon_days: float | None = None) -> dict[str, Any]:
    """Measure direct fragmentation/spoiler penalties against the full model."""
    import random
    from .peace_process import initiate_negotiation, process_peace
    modes = ("full", "no_fragmentation_penalty", "no_spoiler_penalty", "no_direct_penalties")
    results = {}
    for mode in modes:
        outcomes = []
        for replication in range(8):
            trial = SimulationConfig.from_dict(config.to_dict()); trial.agent_count = min(trial.agent_count, 2_000)
            trial.seed = config.seed + replication
            trial.peace_process.agreement_base_hazard = max(.8, trial.peace_process.agreement_base_hazard)
            trial.peace_process.negotiation_base_hazard = max(.5, trial.peace_process.negotiation_base_hazard)
            if mode in {"no_fragmentation_penalty", "no_direct_penalties"}:
                trial.peace_process.fragmentation_penalty = 0.0
            if mode in {"no_spoiler_penalty", "no_direct_penalties"}:
                trial.peace_process.spoiler_penalty = 0.0
            world = generate_pineland(trial)
            active = [o for o in world.organizations.values()
                      if o.kind is OrganizationKind.INSURGENT and o.status == "active"]
            if not active:
                outcomes.append({"agreement": False, "implementation": 0.0, "recurrence": False})
                continue
            negotiation = initiate_negotiation(world, 0.0, active)
            negotiation.fragmentation = .9
            negotiation.credibility = .4
            negotiation.bargaining_surplus = {key: .05 for key in negotiation.bargaining_surplus}
            rng = random.Random(trial.seed + 91)
            for step in range(1, 2):
                process_peace(world, float(step), f"FRAG-{mode}-{replication}-{step}", rng)
                if negotiation.status != "active":
                    break
            outcomes.append({"agreement": bool(world.peace_agreements),
                             "implementation": (mean(p.progress for p in world.agreement_provisions.values())
                                                 if world.agreement_provisions else 0.0),
                             "recurrence": any(a.status == "failed" for a in world.peace_agreements.values())})
        results[mode] = {
            "agreement_rate": mean(row["agreement"] for row in outcomes),
            "implementation": mean(row["implementation"] for row in outcomes),
            "recurrence": mean(row["recurrence"] for row in outcomes),
        }
    full = results["full"]
    return {"modes": results,
            "effects_vs_full": {mode: {key: value - full[key] for key, value in row.items() if key in full}
                                 for mode, row in results.items() if mode != "full"},
            "interpretation": "A fragmentation result is emergent only when it persists after direct bargaining penalties are removed."}


def long_horizon_diagnostics(config: SimulationConfig, years: int = 10) -> dict[str, Any]:
    """Run a multi-year stability check and flag watchlist pathologies."""
    if years < 1:
        raise ValueError("years must be positive")
    trial = SimulationConfig.from_dict(config.to_dict())
    # Long-horizon pathology checks are intentionally a bounded diagnostic;
    # callers doing production-scale runs should use independent replications.
    trial.agent_count = min(trial.agent_count, 2_000)
    # Long runs use compact event summaries; this preserves process semantics
    # while avoiding per-event sparse state-delta snapshots.
    trial.output_mode = "ensemble"
    trial.horizon_days = years * 365.0
    initial_world = generate_pineland(trial)
    initial_active = sum(organization.kind is OrganizationKind.INSURGENT and
                         organization.status == "active"
                         for organization in initial_world.organizations.values())
    world = Simulation(initial_world).run().world
    checkpoints = world.checkpoints
    warnings = list(__import__("pineland_sim.integrity", fromlist=["causal_integrity_diagnostics"])
                    .causal_integrity_diagnostics(world)["warnings"])
    pathology = [snapshot.get("pathology", {}) for snapshot in checkpoints]
    represented = max(1.0, world.weighted_population())
    if any(row.get("patronage_total", 0.0) > 10 * represented for row in pathology):
        warnings.append("patronage_runaway")
    if any(row.get("recruitment_total", 0.0) > .5 * represented for row in pathology):
        warnings.append("recruitment_runaway")
    # Organization count is a count of explicit actor tokens, not a proxy for
    # sampled civilians.  A fixed structural explosion guard must therefore
    # not scale with representative-agent resolution.
    if any(row.get("insurgent_organization_count", 0) > 50 for row in pathology):
        warnings.append("organization_explosion")
    if initial_active and pathology and pathology[-1].get("active_insurgent_organizations", 0) == 0:
        warnings.append("organization_extinction")
    if any(row.get("belief_mean_confidence", 1.0) < .01 for row in pathology):
        warnings.append("belief_confidence_collapse")
    if any(row.get("control_saturation_share", 0.0) > .95 for row in pathology):
        warnings.append("control_saturation")
    if any(row.get("external_migrant_weight", 0.0) > .95 * represented for row in pathology):
        warnings.append("migration_depletion")
    if any(row.get("foreign_intervention_cycles", 0) > max(3, years * 2) for row in pathology):
        warnings.append("intervention_cycles")
    if any(row.get("peace_recurrence_count", 0) > max(3, years * 2) for row in pathology):
        warnings.append("peace_recurrence_saturation")
    # Alternating control direction with repeated large swings is a simple
    # pathology screen, not a claim about substantive oscillatory dynamics.
    controls = [row.get("summary", {}).get("mean_government_effective_control", 0.0)
                for row in checkpoints]
    changes = [b - a for a, b in zip(controls, controls[1:]) if abs(b - a) > .02]
    if len(changes) >= 4 and sum(changes[i] * changes[i + 1] < 0 for i in range(len(changes) - 1)) >= 3:
        warnings.append("artificial_control_oscillation")
    warnings = sorted(set(warnings))
    if any(not 0 <= person.government_legitimacy <= 1 for person in world.persons.values()):
        warnings.append("legitimacy_out_of_bounds")
    if any(branch.patronage_stock > 10 * max(1.0, world.localities[branch.locality_id].population)
           for branch in world.party_branches.values()):
        warnings.append("patronage_absorbing_state")
    warnings = sorted(set(warnings))
    return {"years": years, "final_summary": world.summary(),
            "checkpoint_count": len(checkpoints),
            "pathology_series": pathology,
            "warnings": warnings,
            "stock_residual": world.stock_ledger_residual(),
            "supply_residual": world.supply_conservation_residual()}


def long_horizon_ensemble(config: SimulationConfig, years: int = 5,
                          seeds: Iterable[int] = (1, 2, 3)) -> dict[str, Any]:
    """Run multi-year pathology checks over matched independent seeds."""
    seed_values = list(seeds)
    if years < 1 or not seed_values:
        raise ValueError("long-horizon ensemble needs positive years and at least one seed")
    rows = []
    for seed in seed_values:
        trial = SimulationConfig.from_dict(config.to_dict())
        trial.seed = seed
        rows.append(long_horizon_diagnostics(trial, years))
    final = [row["final_summary"] for row in rows]
    scalar = {
        "government_control": [summary["mean_government_effective_control"] for summary in final],
        "insurgent_control": [summary["mean_insurgent_effective_control"] for summary in final],
        "active_insurgent_organizations": [summary["active_armed_organizations"] for summary in final],
        "external_migrants": [summary["external_migrants"] for summary in final],
        "peace_recurrences": [summary["conflict_recurrences"] for summary in final],
    }
    return {
        "years": years, "seeds": seed_values,
        "runs": rows,
        "final_distributions": {name: _distribution(values) for name, values in scalar.items()},
        "warnings": sorted(set(warning for row in rows for warning in row["warnings"])),
        "all_pass": all(not row["warnings"] for row in rows),
        "interpretation": "Multi-seed long-horizon pathology rates are stability diagnostics, not empirical evidence.",
    }


def publication_readiness_report(config: SimulationConfig, *, horizon_days: float = 2.0,
                                 long_horizon_years: int = 1,
                                 language_repetitions: int = 8,
                                 workers: int | None = None,
                                 run_expensive: bool = False,
                                 run_long_horizon: bool = False,
                                 long_horizon_seeds: Iterable[int] = (1, 2, 3),
                                 resolution_agent_counts: Iterable[int] = (25_000, 75_000, 250_000),
                                 resolution_seeds: Iterable[int] = (1, 2, 3),
                                 sensitivity_samples: int = 32,
                                 recovery_hidden_vectors: int = 32,
                                 recovery_candidate_samples: int = 32) -> dict[str, Any]:
    """Produce a machine-readable publication-readiness report.

    The default is a bounded engineering/readiness run.  ``run_expensive``
    additionally executes the requested powered resolution, Morris/Saltelli,
    and synthetic-recovery batteries.  No empirical claim is inferred from
    synthetic trajectories; the first-paper contract remains explicitly data-
    free until a case package is supplied.
    """
    started = walltime.perf_counter()
    resolution_counts = list(resolution_agent_counts)
    resolution_seed_values = list(resolution_seeds)
    trial = SimulationConfig.from_dict(config.to_dict())
    trial.agent_count = min(trial.agent_count, 2_000)
    artifacts: dict[str, Any] = {}
    artifacts["truth_firewall"] = truth_firewall_battery(trial, horizon_days)
    artifacts["output_modes"] = output_mode_benchmark(trial, horizon_days)
    artifacts["representative_agents"] = representative_agent_audit(trial, horizon_days)
    artifacts["topology"] = topology_ablation(trial, horizon_days, swaps=500)
    artifacts["language"] = language_factorial(
        trial, horizon_days, repetitions=language_repetitions, workers=workers)

    accounting_trial = SimulationConfig.from_dict(trial.to_dict())
    accounting_trial.output_mode = "ensemble"
    accounting_world = Simulation(generate_pineland(accounting_trial)).run().world
    artifacts["global_accounting"] = accounting_world.global_accounting_diagnostics()
    if run_long_horizon or run_expensive:
        artifacts["long_horizon"] = long_horizon_ensemble(
            trial, years=long_horizon_years, seeds=long_horizon_seeds)
    else:
        artifacts["long_horizon"] = {"status": "deferred", "reason": "run_long_horizon=False"}

    if run_expensive:
        artifacts["resolution"] = resolution_ladder(
            config, agent_counts=resolution_counts, seeds=resolution_seed_values,
            horizon_days=horizon_days)
        question_parameters = ["recruitment_rate", "contact_rate",
                               "combat.base_attrition_rate",
                               "social_network.behavior_update_rate",
                               "foreign_affairs.migration_rate"]
        artifacts["morris"] = morris_sensitivity(
            config, ["government_control", "event_frequency", "external_migration_share"],
            parameters=question_parameters, trajectories=16, repetitions=2)
        artifacts["variance"] = variance_sensitivity(
            config, ["government_control", "event_frequency"],
            parameters=question_parameters, samples=sensitivity_samples, repetitions=2)
        artifacts["recovery"] = parameter_recovery_ensemble(
            config, parameters=["recruitment_rate", "contact_rate"],
            hidden_vectors=recovery_hidden_vectors,
            candidate_samples=recovery_candidate_samples, repetitions=2)
    else:
        artifacts["resolution"] = {"status": "deferred", "reason": "run_expensive=False",
                                    "requested_agent_counts": resolution_counts,
                                    "requested_seeds": resolution_seed_values}
        artifacts["morris"] = {"status": "deferred", "reason": "run_expensive=False"}
        artifacts["variance"] = {"status": "deferred", "reason": "run_expensive=False"}
        artifacts["recovery"] = {"status": "deferred", "reason": "run_expensive=False"}

    spec = first_paper_experiment_spec()
    checks = {
        "truth_firewall": artifacts["truth_firewall"]["pass"],
        "output_trajectory_equivalence": artifacts["output_modes"]["trajectory_equivalence"],
        "representative_agent_audit": artifacts["representative_agents"]["all_pass"],
        "topology_degree_preservation": all(row["degree_sequence_preserved"]
                                             for row in artifacts["topology"]["modes"].values()),
        "language_factorial_complete": len(artifacts["language"]["modes"]) == 8,
        "global_accounting": artifacts["global_accounting"]["max_abs_stock_residual"] <= 1e-6 and
        abs(artifacts["global_accounting"]["population_residual"]) <= 1e-6,
        "long_horizon_no_flagged_pathology": artifacts["long_horizon"].get("status") == "deferred" or
        not artifacts["long_horizon"].get("warnings"),
    }
    if run_expensive:
        checks.update({
            "resolution_battery_run": artifacts["resolution"].get("agent_counts") == resolution_counts,
            "resolution_powered": not artifacts["resolution"].get("power_warning", True),
            "sensitivity_powered": not artifacts["morris"].get("power_warning", True) and
            not artifacts["variance"].get("power_warning", True),
            "recovery_powered": not artifacts["recovery"].get("power_warning", True),
        })
    deferred = []
    if not run_expensive:
        deferred.extend(["resolution_battery", "morris_sensitivity", "variance_sensitivity", "parameter_recovery"])
    if not (run_long_horizon or run_expensive):
        deferred.append("long_horizon_pathology")
    # Deferred batteries count against readiness until actually run; this
    # prevents a fast engineering smoke test from being reported as a powered
    # scientific result.
    methods_score = round(100 * sum(checks.values()) /
                          max(1, len(checks) + len(deferred)), 1)
    empirical_required = [
        "case-specific locality-week geography and conflict observations",
        "source coverage, reporting delay, and geocoding-error metadata",
        "formation/logistics or force-presence proxies",
        "construct correspondences and measurement-model calibration",
        "temporal and geographic holdout data for competitor comparison",
    ]
    return {
        "report_schema_version": "0.13.0-readiness",
        "runtime_seconds": walltime.perf_counter() - started,
        "run_expensive": run_expensive,
        "checks": checks,
        "methods_paper_readiness_score": methods_score,
        # Research-v1 can execute its synthetic benchmark without historical
        # data, but that does not license a substantive empirical claim.  Do
        # not infer empirical readiness from the wording of ``data_status``:
        # the new contract deliberately says the synthetic benchmark is
        # executable while historical claims remain unlicensed.
        "substantive_paper_readiness_score": 35.0,
        "closed_questions": [name for name, passed in checks.items()
                             if passed and name not in {item for item in deferred}],
        "open_or_conditional_questions": [name for name, passed in checks.items() if not passed] + deferred,
        "empirical_data_required": empirical_required,
        "empirical_claim_status": "not validated; synthetic tests exercise software and identification contracts only",
        "first_paper_experiment": spec,
        "artifacts": artifacts,
    }


def null_and_extreme_checks(config: SimulationConfig) -> dict[str, Any]:
    """Exercise theory-required zero/boundary cases and report violations."""
    checks: dict[str, bool] = {}
    zero_contact = SimulationConfig.from_dict(config.to_dict()); zero_contact.contact_rate = 0.0
    world = Simulation(generate_pineland(zero_contact)).run().world
    checks["zero_contact_no_true_contacts"] = not any(
        event.event_type == "contact" and event.true_state_delta.get("contact", 0) > 0
        for event in world.event_log)
    zero_recruit = SimulationConfig.from_dict(config.to_dict()); zero_recruit.recruitment_rate = 0.0
    world = Simulation(generate_pineland(zero_recruit)).run().world
    checks["zero_recruit_no_recruitment"] = not any(
        event.event_type == "recruitment" and event.true_state_delta.get("recruits", 0) > 0
        for event in world.event_log)
    no_reporting = SimulationConfig.from_dict(config.to_dict())
    for name in ("civilian_report_rate", "social_report_rate", "administrative_report_rate",
                 "elite_report_rate", "member_report_rate", "fixed_post_report_rate",
                 "patrol_report_rate", "interpreter_report_rate"):
        setattr(no_reporting.information, name, 0.0)
    no_reporting.contact_rate = 0.0
    no_reporting.organized_action_rate = 0.0
    world = Simulation(generate_pineland(no_reporting)).run().world
    checks["zero_reporting_no_source_observations"] = len(world.observations) == 0
    no_supply = SimulationConfig.from_dict(config.to_dict())
    no_supply.foreign_affairs.enabled = False
    world = generate_pineland(no_supply)
    for source in world.supply_sources.values():
        source.stock = 0.0
        source.production_per_day = 0.0
        source.operational = False
    for formation in world.formations.values(): formation.supply_stock = 0.0
    world.initial_supply_stock = 0.0; world.initialize_stock_ledger()
    world = Simulation(world).run().world
    checks["zero_supply_no_high_readiness"] = all(
        formation.effective_readiness() <= formation.readiness * .25 + 1e-9
        for formation in world.formations.values())
    return {"checks": checks, "all_pass": all(checks.values())}


def truth_firewall_check(config: SimulationConfig, horizon_days: float = 2.0) -> dict[str, Any]:
    """Adversarially verify that mobility uses beliefs rather than hidden truth."""
    base = SimulationConfig.from_dict(config.to_dict())
    base.agent_count = min(base.agent_count, 2_000)
    base.horizon_days = horizon_days
    base.movement_rate = 1.0
    left = generate_pineland(base)
    right = deepcopy(left)
    # Perturb only latent physical control.  All person beliefs, network state,
    # RNG seed and economic conditions remain identical.
    changed = 0.0
    for locality in right.localities.values():
        old = locality.control["government"].physical
        locality.control["government"].physical = max(0.0, min(1.0, old * .05))
        changed += abs(old - locality.control["government"].physical)
    event = ScheduledEvent(0.0, 0, 0, "mobility", {"interval": base.intervals.mobility})
    for locality in left.localities.values():
        locality.violence = 1.0
    for locality in right.localities.values():
        locality.violence = 1.0
    ProcessEngine(left).execute(event)
    ProcessEngine(right).execute(event)
    left_positions = {pid: p.residence_locality_id for pid, p in left.persons.items()}
    right_positions = {pid: p.residence_locality_id for pid, p in right.persons.items()}
    actions_equal = left_positions == right_positions
    # Conversely, changing only beliefs should be able to change decisions.
    belief_trial = deepcopy(left)
    for person in belief_trial.persons.values():
        person.expected_control["government"] = 1.0 - person.expected_control.get("government", .5)
        for index, destination in enumerate(sorted(belief_trial.adjacency.get(person.residence_locality_id, {}))):
            person.expected_control_by_locality.setdefault(destination, {})["government"] = (
                .99 if index % 2 == 0 else .01)
    ProcessEngine(belief_trial).execute(event)
    belief_positions = {pid: p.residence_locality_id for pid, p in belief_trial.persons.items()}
    return {"latent_truth_delta": changed, "actions_equal_when_truth_changes": actions_equal,
            "actions_change_when_beliefs_change": belief_positions != left_positions,
            "pass": actions_equal and belief_positions != left_positions}


def truth_firewall_battery(config: SimulationConfig, horizon_days: float = 2.0) -> dict[str, Any]:
    """Run the decision-level hidden-state metamorphic firewall battery.

    The paired worlds have identical beliefs, attributes, RNG streams, and
    event timing.  Only latent physical control is changed.  A decision that
    depends on that change is a firewall violation unless the process is an
    explicitly experience-side response (for example, realized civilian
    violence exposure).  The battery therefore compares the actor choices and
    separately reports the experienced-repression channel used by onset.
    """
    base = SimulationConfig.from_dict(config.to_dict())
    base.agent_count = min(base.agent_count, 2_000)
    base.horizon_days = horizon_days
    base.output_mode = "forensic"
    template = generate_pineland(base)

    def perturb_truth(world, violence: bool = False) -> float:
        delta = 0.0
        for locality in world.localities.values():
            old = locality.control["government"].physical
            locality.control["government"].physical = clamp(old * .05)
            delta += abs(old - locality.control["government"].physical)
            if violence:
                locality.violence = clamp(locality.violence * .05)
        return delta

    def execute_pair(event_type: str, payload: dict[str, Any], *, violence: bool = False):
        left, right = deepcopy(template), deepcopy(template)
        perturb_truth(right, violence)
        event = ScheduledEvent(0.0, 0, 0, event_type, dict(payload))
        ProcessEngine(left, random.Random(914)).execute(event)
        ProcessEngine(right, random.Random(914)).execute(
            ScheduledEvent(0.0, 0, 0, event_type, dict(payload)))
        return left, right

    outcomes: dict[str, bool] = {}
    # Civilian behavior is belief/social-signal driven; latent control changes
    # alone must not change the public choice under matched RNG.
    left, right = execute_pair("social_influence", {"interval": base.intervals.social_influence})
    outcomes["civilian_behavior"] = {
        pid: person.public_behavior for pid, person in left.persons.items()
    } == {pid: person.public_behavior for pid, person in right.persons.items()}

    left, right = execute_pair("mobility", {"interval": base.intervals.mobility})
    outcomes["mobility"] = {
        pid: person.residence_locality_id for pid, person in left.persons.items()
    } == {pid: person.residence_locality_id for pid, person in right.persons.items()}

    left, right = execute_pair("recruitment", {"interval": base.intervals.recruitment})
    outcomes["recruitment"] = {
        pid: person.organization_id for pid, person in left.persons.items()
    } == {pid: person.organization_id for pid, person in right.persons.items()}

    left, right = execute_pair("organization_ecology", {"interval": base.organization_ecology.interval_days})
    outcomes["organization_onset_and_adaptation"] = (
        [(t.transition_type, t.parent_ids, t.child_ids) for t in left.organization_transitions] ==
        [(t.transition_type, t.parent_ids, t.child_ids) for t in right.organization_transitions]
    )
    onset_rows = right.organization_onset_log
    outcomes["onset_repression_separation"] = all(
        "expected_repression" in row and "experienced_repression" in row
        for row in onset_rows
    )

    left, right = execute_pair("command", {"interval": base.intervals.command})
    outcomes["deployment_command"] = {
        oid: order.destination_locality_id for oid, order in left.movement_orders.items()
    } == {oid: order.destination_locality_id for oid, order in right.movement_orders.items()}

    patrol_id = next(iter(template.patrols), None)
    if patrol_id is not None:
        left, right = execute_pair("patrol", {"patrol_id": patrol_id})
        outcomes["patrol_routing"] = {
            fid: formation.current_microzone_id for fid, formation in left.formations.items()
        } == {fid: formation.current_microzone_id for fid, formation in right.formations.items()}
    else:
        outcomes["patrol_routing"] = True

    # Foreign decisions consume foreign beliefs and person-level experience;
    # changing hidden control while holding violence fixed must not alter them.
    left, right = execute_pair("foreign_affairs", {"interval": base.foreign_affairs.interval_days})
    outcomes["foreign_decisions"] = (
        sorted(left.foreign_interventions) == sorted(right.foreign_interventions) and
        sorted(left.external_support, key=lambda item: item.support_id) ==
        sorted(right.external_support, key=lambda item: item.support_id)
    )

    # Bargaining exposes both the actor-facing result and an analyst-only truth
    # counterfactual.  The actor-facing values must be invariant to hidden truth.
    from .peace_process import bargaining_values
    left, right = deepcopy(template), deepcopy(template)
    perturb_truth(right, violence=True)
    left_values = bargaining_values(left)
    right_values = bargaining_values(right)
    outcomes["bargaining"] = left_values == right_values
    truth_gap = {
        actor: {
            "war": right_values.get(actor, {}).get("war", 0.0) -
                   __import__("pineland_sim.peace_process", fromlist=["true_bargaining_values"])
                   .true_bargaining_values(right).get(actor, {}).get("war", 0.0)
        }
        for actor in right_values
    }
    return {
        "latent_control_perturbation": "government physical control multiplied by 0.05; beliefs held fixed",
        "horizon_days": horizon_days,
        "outcomes": outcomes,
        "truth_gap_example": truth_gap,
        "experienced_repression_is_environmental": True,
        "pass": all(outcomes.values()),
        "interpretation": "All listed actor choices are belief-invariant to latent control perturbation; realized violence remains an explicitly logged experience-side covariate.",
    }


def scheduler_audit(config: SimulationConfig, horizon_days: float = 30.0) -> dict[str, Any]:
    """Compare observed recurring event counts with the declared schedule."""
    trial = SimulationConfig.from_dict(config.to_dict())
    trial.agent_count = min(trial.agent_count, 2_000)
    trial.horizon_days = horizon_days
    world = Simulation(generate_pineland(trial)).run().world
    counts: dict[str, int] = {}
    for event in world.event_log:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    expected = {}
    for name, interval in {
        "command": trial.intervals.command, "force_movement": trial.intervals.force_movement,
        "logistics": trial.intervals.logistics, "information": trial.intervals.information,
        "beliefs": trial.intervals.beliefs, "physical_refresh": trial.intervals.physical_refresh,
        "social_influence": trial.intervals.social_influence,
        "organization_ecology": trial.organization_ecology.interval_days,
        "political_order": trial.political_order.interval_days,
        "foreign_affairs": trial.foreign_affairs.interval_days,
        "peace_process": trial.peace_process.interval_days, "mobility": trial.intervals.mobility,
        "governance": trial.intervals.governance, "economy": trial.intervals.economy,
        "checkpoint": trial.intervals.checkpoint,
    }.items():
        expected[name] = int(horizon_days // interval) + 1
    # Recruitment is only scheduled while an active insurgent exists.
    expected["recruitment"] = (int(horizon_days // trial.intervals.recruitment) + 1
                                if trial.include_insurgency else 0)
    mismatches = {name: {"observed": counts.get(name, 0), "expected_if_active": value}
                  for name, value in expected.items()
                  if name != "recruitment" and counts.get(name, 0) != value}
    recruitment_unique = counts.get("recruitment", 0) <= expected["recruitment"]
    return {"horizon_days": horizon_days, "counts": counts, "expected": expected,
            "mismatches": mismatches, "recruitment_unique": recruitment_unique,
            "pass": not mismatches and recruitment_unique}


def causal_ledger_audit(config: SimulationConfig, horizon_days: float = 7.0) -> dict[str, Any]:
    """Check event-to-state-delta and causal-contribution referential integrity."""
    trial = SimulationConfig.from_dict(config.to_dict()); trial.agent_count = min(trial.agent_count, 2_000)
    trial.horizon_days = horizon_days
    world = Simulation(generate_pineland(trial)).run().world
    event_ids = {entry.event_id for entry in world.event_log}
    delta_ids = {delta.event_id for delta in world.state_deltas}
    causal_ids = {item.event_id for item in world.causal_ledger}
    missing_deltas = sorted(event_ids - delta_ids)
    orphan_causal = sorted(causal_ids - event_ids)
    stock_report = world.stock_ledger_diagnostics()
    residual = stock_report["residual"]
    return {"events": len(event_ids), "state_deltas": len(world.state_deltas),
            "missing_state_deltas": missing_deltas, "orphan_causal_entries": orphan_causal,
            "stock_residual": residual, "stock_report": stock_report,
            "pass": not missing_deltas and not orphan_causal and abs(residual) <= 1e-6}


def recording_calibration(config: SimulationConfig, repetitions: int = 200,
                          source_types: Iterable[str] | None = None) -> dict[str, Any]:
    """Estimate the synthetic recorder's channel rates under a known event."""
    if repetitions < 2:
        raise ValueError("recording calibration needs at least two repetitions")
    source_types = tuple(source_types or ("patrol", "fixed_post", "civilian", "administrative", "contact"))
    trial = SimulationConfig.from_dict(config.to_dict()); trial.agent_count = min(trial.agent_count, 2_000)
    world = generate_pineland(trial)
    locality_id = sorted(world.localities)[0]
    engine = ProcessEngine(world)
    rows = {}
    for source_type in source_types:
        records = [engine._synthetic_record(f"CAL-{source_type}-{i}", "calibration", locality_id,
                                            .8, "government", source_type)
                   for i in range(repetitions)]
        recorded = [item for item in records if item.recorded]
        rows[source_type] = {
            "n": repetitions, "recording_rate": len(recorded) / repetitions,
            "geocoding_error_rate": (sum(item.geocoding_error for item in recorded) / len(recorded)
                                      if recorded else 0.0),
            "mean_recorded_severity": (mean(item.reported_severity for item in recorded) if recorded else 0.0),
        }
    return {"repetitions": repetitions, "channels": rows,
            "channel_ordering": sorted(rows, key=lambda name: rows[name]["recording_rate"], reverse=True),
            "source_channel_parameters": {name: dict(trial.recording.source_channels.get(name, {}))
                                           for name in source_types}}


def foreign_withdrawal_diagnostics(config: SimulationConfig, years: int = 5,
                                  withdrawal_year: int = 3) -> dict[str, Any]:
    """Compare capacity-building/substitution after equal foreign withdrawal."""
    from .foreign_affairs import run_intervention_comparison
    trial = SimulationConfig.from_dict(config.to_dict()); trial.agent_count = min(trial.agent_count, 2_000)
    world = generate_pineland(trial)
    comparison = run_intervention_comparison(world, years=years, withdrawal_year=withdrawal_year)
    post = {}
    for label, result in comparison.items():
        after = [row for row in result["trajectory"] if row["year"] >= withdrawal_year]
        post[label] = {
            "final_host_capacity": result["final"]["host_capacity"],
            "post_withdrawal_min_host_capacity": min((row["host_capacity"] for row in after), default=0.0),
            "withdrawal_shock_peak": result["withdrawal_shock_peak"],
            "capacity_decomposition": {key: result["final"].get(key, 0.0)
                                        for key in ("gross_transferred_capacity", "retained_host_capacity",
                                                    "crowding_out_capacity", "withdrawn_capacity")},
        }
    return {"years": years, "withdrawal_year": withdrawal_year, "comparison": comparison,
            "post_withdrawal": post,
            "interpretation": "Capacity-building is supported only if host capacity persists after withdrawal; substitution is expected to show higher crowding-out."}
