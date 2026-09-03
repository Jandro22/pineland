"""Reproducible validation batteries requested by the pre-publication audit.

The functions in this module are deliberately small orchestration layers around
the simulator.  They do not assert that synthetic priors are empirically
valid; they produce the evidence needed to tell implementation, identification,
measurement, and mechanism failures apart.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Callable, Iterable

from .config import SimulationConfig
from .entities import OrganizationKind
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


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "std": 0.0, "p05": 0.0, "median": 0.0, "p95": 0.0}
    ordered = sorted(values)
    quantile = lambda q: ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
    return {"n": len(values), "mean": mean(values), "std": pstdev(values),
            "p05": quantile(.05), "median": quantile(.5), "p95": quantile(.95)}


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


def _run_metrics(config: SimulationConfig) -> dict[str, float]:
    world = Simulation(generate_pineland(config)).run().world
    metrics = _event_metrics(world)
    true_contacts = sum(event.event_type == "contact" and
                        event.true_state_delta.get("contact", 0) > 0
                        for event in world.event_log)
    recruits = sum(float(event.true_state_delta.get("recruits", 0.0))
                   for event in world.event_log if event.event_type == "recruitment")
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
    return metrics


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
        comparisons.append({
            "agent_count": count, "reference_agent_count": reference,
            "metrics": {name: distributions[str(count)][name]["mean"] -
                         distributions[str(reference)][name]["mean"]
                         for name in metric_names},
        })
    return {"agent_counts": counts, "seeds": seed_values,
            "horizon_days": horizon_days if horizon_days is not None else config.horizon_days,
            "represented_population": {str(count): distributions[str(count)]["represented_population"]["mean"]
                                        for count in counts},
            "distributions": distributions, "comparisons": comparisons,
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
                       parameters: list[str] | None = None, trajectories: int = 8,
                       levels: int = 6, repetitions: int = 1) -> dict[str, Any]:
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
            "parameters": parameters, "analysis": analysis, "records": records}


def variance_sensitivity(config: SimulationConfig, outcomes: list[str],
                        parameters: list[str] | None = None, samples: int = 16,
                        repetitions: int = 1) -> dict[str, Any]:
    """Saltelli-style first/total variance indices on a question subset."""
    parameters = parameters or list(SAMPLE_BOUNDS)
    if samples < 2:
        raise ValueError("variance sensitivity needs at least two samples")
    draws_a = latin_hypercube(samples, parameters, config.seed + 101)
    draws_b = latin_hypercube(samples, parameters, config.seed + 202)

    def evaluate(draw: dict[str, float], seed: int) -> dict[str, float]:
        trial = SimulationConfig.from_dict(config.to_dict()); trial.seed = seed
        for path, value in draw.items(): set_parameter(trial, path, value)
        return {outcome: mean(run_model(trial)[outcome] for _ in range(repetitions))
                for outcome in outcomes}

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
            first_raw = mean((y_b[i][outcome] - center) *
                             (y_ab[parameter][i][outcome] - y_a[i][outcome])
                             for i in range(samples)) / variance
            total_raw = mean((y_a[i][outcome] - y_ab[parameter][i][outcome]) ** 2
                             for i in range(samples)) / (2 * variance)
            indices[parameter] = {
                "first_order": max(0.0, min(1.0, first_raw)),
                "total_order": max(0.0, min(1.0, total_raw)),
                "raw_first_order": first_raw, "raw_total_order": total_raw,
                "finite_sample_out_of_bounds": not (0 <= first_raw <= 1 and 0 <= total_raw <= 1),
            }
        analysis[outcome] = {"variance": variance, "indices": indices,
                             "finite_sample_warning": any(item["finite_sample_out_of_bounds"]
                                                            for item in indices.values())}
    return {"method": "Saltelli variance-based sensitivity", "samples": samples,
            "repetitions": repetitions, "parameters": parameters, "analysis": analysis}


def parameter_recovery_ensemble(config: SimulationConfig, parameters: list[str] | None = None,
                                hidden_vectors: int = 8, candidate_samples: int = 16,
                                repetitions: int = 1) -> dict[str, Any]:
    """Repeated synthetic recovery with bias, RMSE, rank, and boundary diagnostics."""
    parameters = parameters or ["recruitment_rate", "contact_rate"]
    if repetitions < 1:
        raise ValueError("repetitions must be positive")

    def replicated_metrics(template: SimulationConfig, seed_base: int) -> dict[str, float]:
        rows = []
        for repetition in range(repetitions):
            trial = SimulationConfig.from_dict(template.to_dict())
            trial.seed = seed_base + repetition
            rows.append(run_model(trial))
        names = rows[0].keys()
        return {name: mean(row[name] for row in rows) for name in names}

    truths = latin_hypercube(hidden_vectors, parameters, config.seed + 333)
    rows = []
    for index, truth in enumerate(truths):
        truth_config = SimulationConfig.from_dict(config.to_dict()); truth_config.seed = config.seed + 400_000 + index
        for path, value in truth.items(): set_parameter(truth_config, path, value)
        truth_metrics = replicated_metrics(truth_config, truth_config.seed)
        target_keys = [key for key in ("government_control", "insurgent_control", "event_frequency", "implementation")
                       if key in truth_metrics]
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
                                                   for value in recovered_values)}
    return {"method": "repeated synthetic parameter recovery", "parameters": parameters,
            "hidden_vectors": hidden_vectors, "candidate_samples": candidate_samples,
            "repetitions": repetitions, "summary": summary, "runs": rows}


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


def language_factorial(config: SimulationConfig, horizon_days: float | None = None) -> dict[str, Any]:
    """Factor language effects across topology, detection, and fusion channels."""
    modes = ("all", "topology_only", "detection_only", "fusion_only", "none")
    results = {}
    for mode in modes:
        trial = SimulationConfig.from_dict(config.to_dict())
        trial.agent_count = min(trial.agent_count, 2_000)
        if horizon_days is not None:
            trial.horizon_days = horizon_days
        # Language enters topology through individual multilingual weights;
        # detection and fusion channels can be independently neutralized.
        if mode in {"topology_only", "none"}:
            trial.information.detection_language_bonus = 0.0
            trial.information.language_fusion_weight = 0.0
        elif mode == "detection_only":
            trial.information.language_fusion_weight = 0.0
        elif mode == "fusion_only":
            trial.information.detection_language_bonus = 0.0
        if mode == "none":
            trial.social_network.household_tie_strength = trial.social_network.community_tie_strength = 1.0
            trial.social_network.bridge_tie_strength = 1.0
        world = Simulation(generate_pineland(trial)).run().world
        information = world.information_detections
        from .networks import network_diagnostics
        from .information import detection_probability
        network = network_diagnostics(world)
        target = next((formation for formation in world.formations.values()
                       if world.organizations[formation.organization_id].kind is OrganizationKind.INSURGENT), None)
        observer = next((formation for formation in world.formations.values()
                         if world.organizations[formation.organization_id].kind is not OrganizationKind.INSURGENT), None)
        target_detection = 0.0
        if target is not None and observer is not None:
            target_detection = detection_probability(world, observer.formation_id, target.formation_id,
                                                     target.locality_id, "patrol", target.current_microzone_id)
        results[mode] = {
            "mean_belief_confidence": (sum(b.confidence for b in world.control_beliefs.values()) /
                                        max(1, len(world.control_beliefs))),
            "detection_counts": dict(information),
            "network_language_compatibility": network.get("mean_language_compatibility", 0.0),
            "known_target_detection_probability": target_detection,
            "government_control": world.summary()["mean_government_effective_control"],
        }
    return {"modes": results,
            "interpretation": "Factorial diagnostics separate language-sensitive detection/fusion from topology-sensitive network effects; topology is represented by multilingual edge compatibility."}


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
    trial.horizon_days = years * 365.0
    world = Simulation(generate_pineland(trial)).run().world
    checkpoints = world.checkpoints
    warnings = list(__import__("pineland_sim.integrity", fromlist=["causal_integrity_diagnostics"])
                    .causal_integrity_diagnostics(world)["warnings"])
    if any(not 0 <= person.government_legitimacy <= 1 for person in world.persons.values()):
        warnings.append("legitimacy_out_of_bounds")
    if any(branch.patronage_stock > 10 * max(1.0, world.localities[branch.locality_id].population)
           for branch in world.party_branches.values()):
        warnings.append("patronage_absorbing_state")
    return {"years": years, "final_summary": world.summary(),
            "checkpoint_count": len(checkpoints),
            "pathology_series": [snapshot.get("pathology", {}) for snapshot in checkpoints],
            "warnings": sorted(set(warnings)),
            "stock_residual": world.stock_ledger_residual(),
            "supply_residual": world.supply_conservation_residual()}


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
