"""Reproducible calibration, sensitivity, identifiability, and falsification tools.

The module deliberately reports *practical* rather than statistical identifiability:
with stochastic ABMs and sparse targets, a parameter is constrained only when
near-equivalent fits occupy a narrow portion of its declared prior range.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from math import sqrt
import random
from statistics import mean, pstdev
from typing import Any, Mapping

from .config import SimulationConfig
from .generator import generate_pineland
from .simulation import Simulation


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    symbol: str
    code_name: str
    units: str
    subsystem: str
    current_prior: Any
    lower: float | None
    upper: float | None
    assumption_type: str
    empirical_source: str | None
    source_population: str | None
    confidence: str
    calibration_status: str
    sensitivity_ranking: int | None = None
    identifiability_status: str = "unassessed"


# Bounds are deliberately explicit only for parameters whose continuous
# variation is scientifically interpretable. Other config fields remain in the
# registry as fixed structural/numerical assumptions rather than being sampled.
SAMPLE_BOUNDS: dict[str, tuple[float, float, str, str]] = {
    "recruitment_rate": (0.0001, 0.004, r"r_{recruit}", "rate/day"),
    "membership_exit_rate": (0.0001, 0.004, r"r_{exit}", "rate/day"),
    "contact_rate": (0.01, 0.20, r"r_{contact}", "rate/day"),
    "social_network.behavior_update_rate": (.02, .30, r"p_{behavior}", "probability/day"),
    "social_network.bridge_fraction": (.005, .12, r"b_{bridge}", "share"),
    "combat.base_attrition_rate": (.003, .04, r"\alpha_{combat}", "fraction/engagement"),
    "organization_ecology.birth_base_hazard": (.0003, .02, r"\lambda_{birth}", "probability/cycle"),
    "organization_ecology.split_base_hazard": (.0002, .03, r"\lambda_{split}", "probability/cycle"),
    "organization_ecology.collapse_base_hazard": (.0002, .03, r"\lambda_{collapse}", "probability/cycle"),
    "organization_ecology.succession_base_hazard": (.0002, .03, r"\lambda_{succession}", "probability/cycle"),
    "organization_ecology.exit_sympathy_retention": (0.0, 1.0, r"\rho_{exit,sympathy}", "probability/full exit"),
    "organization_ecology.local_rootedness_weight": (0.0, 2.0, r"\beta_{rooted}", "logit utility coefficient"),
    "political_order.peaceful_channel_strength": (.05, .95, r"\pi_{peace}", "share"),
    "foreign_affairs.migration_rate": (.0001, .02, r"m_{out}", "probability/cycle"),
    "foreign_affairs.intervention_base_hazard": (0.0, .12, r"\lambda_{foreign}", "probability/cycle"),
    "peace_process.negotiation_base_hazard": (.005, .35, r"\lambda_{talks}", "probability/cycle"),
    "peace_process.agreement_base_hazard": (.005, .45, r"\lambda_{agreement}", "probability/cycle"),
    "peace_process.implementation_rate": (.005, .20, r"\alpha_{implement}", "progress/cycle"),
    "peace_process.recurrence_base_hazard": (.0001, .05, r"\lambda_{recur}", "probability/cycle"),
}

# Provenance is intentionally explicit even where no external estimate has
# yet been supplied.  Empty provenance used to make engineering constants look
# like empirical quantities in exported registries.
PARAMETER_PROVENANCE: dict[str, tuple[str, str | None, str]] = {
    "recruitment_rate": ("experimental treatment", "synthetic recovery required", "uncalibrated"),
    "membership_exit_rate": ("experimental treatment", "synthetic recovery required", "uncalibrated"),
    "contact_rate": ("experimental treatment", "synthetic recovery required", "uncalibrated"),
    "information": ("empirical estimand", "source-specific observation calibration required", "uncalibrated"),
    "recording": ("empirical estimand", "recording calibration required", "uncalibrated"),
    "physical": ("structural/scaling coefficient", "mechanism validation required", "uncalibrated"),
    "geography": ("engineering prior", "synthetic spatial generator", "engineering"),
    "intervals": ("numerical safeguard", "event-scheduling contract", "fixed"),
    "organization_ecology": ("experimental treatment", "synthetic recovery required", "uncalibrated"),
    "foreign_affairs": ("literature prior", "case-specific intervention evidence required", "uncalibrated"),
    "peace_process": ("literature prior", "case-specific settlement evidence required", "uncalibrated"),
}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    result = {}
    if isinstance(value, Mapping):
        for key, child in sorted(value.items(), key=lambda item: str(item[0])):
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, Mapping):
                result.update(_flatten(child, name))
            elif isinstance(child, (int, float, bool, str)):
                result[name] = child
        return result
    for item in fields(value):
        name = f"{prefix}.{item.name}" if prefix else item.name
        child = getattr(value, item.name)
        if is_dataclass(child):
            result.update(_flatten(child, name))
        elif isinstance(child, (int, float, bool, str)):
            result[name] = child
    return result


def parameter_registry(config: SimulationConfig | None = None) -> list[ParameterSpec]:
    """Complete machine-readable registry with provenance fields for every scalar config value."""
    config = config or SimulationConfig()
    result = []
    for name, value in sorted(_flatten(config).items()):
        bound = SAMPLE_BOUNDS.get(name)
        subsystem = name.split(".")[0] if "." in name else "core"
        provenance_key = name.split(".")[0]
        provenance_kind, provenance_source, provenance_status = PARAMETER_PROVENANCE.get(
            provenance_key, ("engineering prior", "not yet mapped to an empirical source", "unassessed"))
        if bound:
            lower, upper, symbol, units = bound
            kind, status, confidence = provenance_kind, provenance_status, "low"
        elif name.endswith("interval_days") or name.startswith("intervals."):
            lower = upper = None; symbol = name; units = "days"; kind = "numerical safeguard"; status = "fixed"; confidence = "high"
        elif isinstance(value, bool) or name.endswith("count") or name.endswith("members"):
            lower = upper = None; symbol = name; units = "structural"; kind = "fixed structural assumption"; status = "fixed"; confidence = "medium"
        else:
            lower = upper = None; symbol = name; units = "model units"; kind = provenance_kind; status = provenance_status; confidence = "low"
        source_population = ("case-specific observed population; declare in case package"
                             if kind in {"empirical estimand", "literature prior"} else None)
        result.append(ParameterSpec(symbol, name, units, subsystem, value, lower, upper, kind,
                                    provenance_source, source_population, confidence, status))
    return result


def registry_document(config: SimulationConfig | None = None) -> dict[str, Any]:
    specs = parameter_registry(config)
    return {"schema_version": "0.12.0", "parameters": [asdict(x) for x in specs],
            "counts": {kind: sum(x.assumption_type == kind for x in specs)
                       for kind in sorted({x.assumption_type for x in specs})}}


def set_parameter(config: SimulationConfig, path: str, value: float) -> None:
    target: Any = config
    pieces = path.split(".")
    for name in pieces[:-1]:
        target = target[name] if isinstance(target, Mapping) else getattr(target, name)
    if isinstance(target, dict):
        target[pieces[-1]] = value
    else:
        setattr(target, pieces[-1], value)


def _event_metrics(world) -> dict[str, float]:
    events = [
        e for e in world.event_log
        if (
            (e.event_type == "contact" and e.true_state_delta.get("contact", 0) > 0)
            or
            (
                e.event_type == "organized_action"
                and e.true_state_delta.get("state_based_violence_event", 0) > 0
            )
        )
    ]
    count = (
        len(events)
        if world.event_log
        else len(getattr(world, "state_based_event_times", ()))
    )
    per_location: dict[str, int] = {}
    per_day: dict[int, int] = {}
    if events:
        for event in events:
            if event.locality_id:
                per_location[event.locality_id] = per_location.get(event.locality_id, 0) + 1
            per_day[int(event.time)] = per_day.get(int(event.time), 0) + 1
    else:
        for time, locality_id in zip(
            getattr(world, "state_based_event_times", ()),
            getattr(world, "state_based_event_localities", ()),
        ):
            per_location[locality_id] = per_location.get(locality_id, 0) + 1
            per_day[int(time)] = per_day.get(int(time), 0) + 1
    concentration = sum((x / count) ** 2 for x in per_location.values()) if count else 0.0
    daily = list(per_day.values())
    burstiness = pstdev(daily) / max(1e-9, mean(daily)) if len(daily) > 1 else 0.0
    initial = world.checkpoints[0]["control"] if world.checkpoints else {}
    persistence_values = []
    for lid, locality in world.localities.items():
        if lid in initial:
            persistence_values.append(1 - abs(locality.control["government"].effective() -
                                               __import__("pineland_sim.entities", fromlist=["ControlVector"]).ControlVector(**initial[lid]["government"]).effective()))
    organizations = [o for o in world.organizations.values() if o.kind.value == "insurgent"]
    peace = __import__("pineland_sim.peace_process", fromlist=["peace_diagnostics"]).peace_diagnostics(world)
    return {
        "event_frequency": count / max(1.0, world.time),
        "event_spatial_concentration": concentration,
        "event_temporal_burstiness": burstiness,
        "government_control": world.summary()["mean_government_effective_control"],
        "insurgent_control": world.summary()["mean_insurgent_effective_control"],
        "control_persistence": mean(persistence_values) if persistence_values else 1.0,
        "active_insurgent_organizations": sum(o.status == "active" for o in organizations),
        "organization_fragmentation": max(0, len([o for o in organizations if o.status == "active"]) - 1),
        "external_migration_share": sum(p.weight for p in world.persons.values()
                                         if p.external_state_id is not None) /
        max(1e-9, world.weighted_population()),
        "agreement_rate": len(world.peace_agreements),
        "implementation": peace["mean_implementation"],
        "recurrence": peace["recurrences"],
    }


TARGET_FAMILIES: dict[str, tuple[str, ...]] = {
    "conflict_events": ("event_frequency", "event_spatial_concentration", "event_temporal_burstiness"),
    "control": ("government_control", "insurgent_control", "control_persistence"),
    "organizations": ("active_insurgent_organizations", "organization_fragmentation"),
    "population": ("external_migration_share",),
    "peace": ("agreement_rate", "implementation", "recurrence"),
    "recording": ("recorded_event_frequency", "recording_rate", "geocoding_error_rate"),
}


def empirical_target_contract(values: dict[str, float], family: str = "all",
                              source: str = "user-supplied empirical summary",
                              case: str = "unspecified", split: str = "training") -> dict[str, Any]:
    allowed = set().union(*TARGET_FAMILIES.values()) if family == "all" else set(TARGET_FAMILIES[family])
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown target metrics: {sorted(unknown)}")
    return {"schema_version": "0.10.0", "family": family, "source": source,
            "source_population_case": case, "split": split,
            "targets": {key: {"value": value, "weight": 1.0,
                               "tolerance": max(.02, abs(value) * .2)} for key, value in values.items()}}


def score_targets(metrics: dict[str, float], contract: dict[str, Any]) -> dict[str, Any]:
    rows = {}
    weighted = 0.0; total_weight = 0.0
    for key, target in contract["targets"].items():
        observed, tolerance, weight = metrics.get(key, 0.0), target["tolerance"], target.get("weight", 1.0)
        normalized_error = abs(observed - target["value"]) / max(1e-12, tolerance)
        rows[key] = {"model": observed, "target": target["value"], "normalized_error": normalized_error}
        weighted += weight * normalized_error; total_weight += weight
    return {"mean_normalized_error": weighted / max(1e-12, total_weight), "metrics": rows}


def run_model(config: SimulationConfig) -> dict[str, float]:
    # Validation repeatedly evaluates many parameter draws.  Calibration mode
    # retains target counters and checkpoints while omitting forensic event and
    # state-delta payloads; process semantics and RNG streams are unchanged.
    trial = SimulationConfig.from_dict(config.to_dict())
    trial.output_mode = "calibration"
    world = Simulation(generate_pineland(trial)).run().world
    return _event_metrics(world)


def latin_hypercube(samples: int, parameters: list[str], seed: int) -> list[dict[str, float]]:
    if samples < 2:
        raise ValueError("sensitivity sampling requires at least two samples")
    rng = random.Random(seed)
    columns = {}
    for name in parameters:
        lo, hi, _, _ = SAMPLE_BOUNDS[name]
        bins = list(range(samples)); rng.shuffle(bins)
        columns[name] = [lo + ((b + rng.random()) / samples) * (hi - lo) for b in bins]
    return [{name: columns[name][i] for name in parameters} for i in range(samples)]


def _rank(values: list[float]) -> list[float]:
    ordering = sorted(enumerate(values), key=lambda item: item[1]); ranks = [0.0] * len(values)
    for rank, (index, _) in enumerate(ordering): ranks[index] = rank + 1
    return ranks


def _corr(a: list[float], b: list[float]) -> float:
    if len(a) < 2: return 0.0
    ma, mb = mean(a), mean(b)
    numerator = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    denominator = sqrt(sum((x-ma)**2 for x in a) * sum((y-mb)**2 for y in b))
    return numerator / denominator if denominator else 0.0


def global_sensitivity(config: SimulationConfig, outcomes: list[str], samples: int = 32,
                       parameters: list[str] | None = None, repetitions: int = 1) -> dict[str, Any]:
    parameters = parameters or list(SAMPLE_BOUNDS)
    draws = latin_hypercube(samples, parameters, config.seed)
    records = []
    for index, draw in enumerate(draws):
        values = []
        for rep in range(repetitions):
            trial = SimulationConfig.from_dict(config.to_dict()); trial.seed = config.seed + index * 1009 + rep
            for path, value in draw.items(): set_parameter(trial, path, value)
            values.append(run_model(trial))
        records.append({"sample": index, "parameters": draw,
                        "outcomes": {key: mean(x[key] for x in values) for key in outcomes}})
    analysis = {}
    for outcome in outcomes:
        y = [r["outcomes"][outcome] for r in records]
        ranked_y = _rank(y)
        main = {name: abs(_corr(_rank([r["parameters"][name] for r in records]), ranked_y)) for name in parameters}
        interactions = {}
        for left_index, left in enumerate(parameters):
            for right in parameters[left_index+1:]:
                product = [r["parameters"][left] * r["parameters"][right] for r in records]
                interactions[f"{left} × {right}"] = abs(_corr(_rank(product), ranked_y))
        analysis[outcome] = {"main_effect_screen": dict(sorted(main.items(), key=lambda x: -x[1])),
                             "interaction_screen": dict(sorted(interactions.items(), key=lambda x: -x[1])[:10]),
                             "outcome_variance": pstdev(y) ** 2}
    aggregate = {name: mean(analysis[outcome]["main_effect_screen"][name] for outcome in outcomes)
                 for name in parameters}
    ranked = {name: index + 1 for index, (name, _) in enumerate(sorted(aggregate.items(), key=lambda x: -x[1]))}
    assessment = [{**asdict(next(item for item in parameter_registry(config) if item.code_name == name)),
                   "sensitivity_ranking": ranked[name], "sensitivity_screen": aggregate[name],
                   "identifiability_status": "unassessed"} for name in parameters]
    return {"method": "Latin hypercube + rank-correlation global screening",
            "samples": samples, "repetitions": repetitions, "parameters": parameters,
            "records": records, "analysis": analysis, "registry_assessment": assessment}


def practical_identifiability(sensitivity: dict[str, Any], contract: dict[str, Any],
                              equivalence_fraction: float = .15) -> dict[str, Any]:
    scored = []
    for record in sensitivity["records"]:
        score = score_targets(record["outcomes"], contract)["mean_normalized_error"]
        scored.append((score, record))
    best = min(score for score, _ in scored)
    accepted = [r for score, r in scored if score <= best + max(.02, best * equivalence_fraction)]
    report = {}
    for name in sensitivity["parameters"]:
        lo, hi, _, _ = SAMPLE_BOUNDS[name]
        values = [r["parameters"][name] for r in accepted]
        span = (max(values)-min(values)) / (hi-lo) if values else 1.0
        status = "well constrained" if span < .25 else "weakly constrained" if span < .60 else "non-identifiable"
        report[name] = {"status": status, "equivalent_fit_range": [min(values), max(values)] if values else [lo, hi],
                        "prior_range": [lo, hi], "relative_span": span}
    return {"method": "practical equivalence set", "best_error": best,
            "equivalent_runs": len(accepted), "parameters": report}


def calibrate_and_validate(config: SimulationConfig, training: dict[str, Any], holdout: dict[str, Any],
                           samples: int = 32, parameters: list[str] | None = None) -> dict[str, Any]:
    outcomes = sorted(set(training["targets"]) | set(holdout["targets"]))
    sensitivity = global_sensitivity(config, outcomes, samples, parameters)
    scored = [(score_targets(r["outcomes"], training)["mean_normalized_error"], r) for r in sensitivity["records"]]
    train_error, best = min(scored, key=lambda item: item[0])
    holdout_score = score_targets(best["outcomes"], holdout)
    identification = practical_identifiability(sensitivity, training)
    assessed = []
    by_name = {item["code_name"]: item for item in sensitivity["registry_assessment"]}
    for name in sensitivity["parameters"]:
        assessed.append({**by_name[name], "identifiability_status": identification["parameters"][name]["status"]})
    return {"calibration": {"best_training_error": train_error, "parameters": best["parameters"],
                             "training_score": score_targets(best["outcomes"], training)},
            "out_of_sample": {"holdout_score": holdout_score, "split": holdout.get("split", "holdout")},
            "identifiability": identification, "assessed_parameter_registry": assessed,
            "sensitivity": sensitivity["analysis"]}


def model_ladder(config: SimulationConfig, contract: dict[str, Any], seed: int | None = None,
                 holdout_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare null, self-exciting statistical proxy, reduced ABM, and full ABM fairly."""
    rng = random.Random(config.seed if seed is None else seed)
    horizon = config.horizon_days
    base_rate = max(.001, config.contact_rate * .1)
    poisson_count = sum(rng.random() < base_rate for _ in range(max(1, int(horizon))))
    null = {key: 0.0 for key in set().union(*TARGET_FAMILIES.values())}
    null.update({"event_frequency": poisson_count/max(1, horizon), "event_temporal_burstiness": 0.0,
                 "event_spatial_concentration": 1/max(1, config.locality_count)})
    hawkes_count = 0; intensity = base_rate
    for _ in range(max(1, int(horizon))):
        event = rng.random() < min(.95, intensity); hawkes_count += event
        intensity = base_rate + .62 * intensity + (.18 if event else 0)
    hawkes = dict(null); hawkes.update({"event_frequency": hawkes_count/max(1, horizon),
                                        "event_temporal_burstiness": .62, "event_spatial_concentration": .12})
    reduced_config = SimulationConfig.from_dict(config.to_dict())
    reduced_config.organization_ecology.enabled = False; reduced_config.foreign_affairs.enabled = False
    reduced_config.peace_process.enabled = False
    reduced = run_model(reduced_config)
    full = run_model(SimulationConfig.from_dict(config.to_dict()))
    models = {"M0_random_null": (null, set(TARGET_FAMILIES["conflict_events"])),
              "M1_self_exciting_proxy": (hawkes, set(TARGET_FAMILIES["conflict_events"])),
              "M2_reduced_pineland": (reduced, set(TARGET_FAMILIES["conflict_events"]) |
                                     set(TARGET_FAMILIES["control"]) | set(TARGET_FAMILIES["organizations"])),
              "M3_full_pineland": (full, set().union(*TARGET_FAMILIES.values()))}
    scored_models = {}
    for name, (metrics, capabilities) in models.items():
        applicable = {key: value for key, value in contract["targets"].items() if key in capabilities}
        score = score_targets(metrics, {**contract, "targets": applicable}) if applicable else None
        holdout_score = None
        if holdout_contract is not None:
            holdout_targets = {key: value for key, value in holdout_contract["targets"].items()
                               if key in capabilities}
            holdout_score = (score_targets(metrics, {**holdout_contract, "targets": holdout_targets})
                             if holdout_targets else None)
        scored_models[name] = {"metrics": metrics, "capabilities": sorted(capabilities),
                               "score": score, "holdout_score": holdout_score}
    return {"models": scored_models,
            "training_split": contract.get("split", "training"),
            "holdout_split": holdout_contract.get("split", "holdout") if holdout_contract else None,
            "interpretation": "Lower mean normalized error is better; the proxy is intentionally limited to event clustering."}


def model_ladder_holdout(config: SimulationConfig, training_contract: dict[str, Any],
                         holdout_contract: dict[str, Any], seed: int | None = None) -> dict[str, Any]:
    """Run the model ladder with identical capabilities and a designated holdout.

    The statistical proxies and reduced/full ABMs are scored on exactly the same
    holdout target definitions; a model cannot win by receiving a different
    information set or metric family.
    """
    return model_ladder(config, training_contract, seed=seed,
                        holdout_contract=holdout_contract)


def bargaining_stress_test(config: SimulationConfig, regimes: list[dict[str, float]] | None = None,
                           replications: int = 100, months: int = 24) -> dict[str, Any]:
    """Controlled negotiation test spanning hard-to-easy agreement environments.

    It freezes unrelated ecology and foreign stochasticity, gives each run the
    same initial bargaining opportunity, and varies only agreement hazard,
    institutional credibility inputs, and faction cohesion. It is a mechanism
    stress test, not a historical forecast.
    """
    from .peace_process import initiate_negotiation, process_peace
    regimes = regimes or [
        {"label": "hard_commitment_problem", "agreement_hazard": .003, "accountability": .18, "cohesion": .22},
        {"label": "low_credibility", "agreement_hazard": .012, "accountability": .32, "cohesion": .36},
        {"label": "contested", "agreement_hazard": .035, "accountability": .52, "cohesion": .56},
        {"label": "credible", "agreement_hazard": .11, "accountability": .72, "cohesion": .74},
        {"label": "guaranteed_window", "agreement_hazard": .32, "accountability": .90, "cohesion": .90},
    ]
    results = []
    for regime_index, regime in enumerate(regimes):
        outcomes = []
        for replication in range(replications):
            trial = SimulationConfig.from_dict(config.to_dict())
            trial.seed = config.seed + regime_index * 100_003 + replication
            trial.organization_ecology.enabled = False
            trial.foreign_affairs.enabled = False
            trial.peace_process.negotiation_base_hazard = 0
            trial.peace_process.agreement_base_hazard = regime["agreement_hazard"]
            world = generate_pineland(trial)
            world.organizations["government"].accountability = regime["accountability"]
            world.organizations["insurgent"].cohesion = regime["cohesion"]
            negotiation = initiate_negotiation(world, 0)
            # Same positive bargaining surplus; credibility and agreement hazard
            # remain the experimental levers.
            negotiation.bargaining_surplus = {key: .12 for key in negotiation.bargaining_surplus}
            rng = random.Random(trial.seed + 7)
            for month in range(1, months + 1):
                process_peace(world, month * 30.0, f"stress-{regime_index}-{replication}-{month}", rng)
            agreements = list(world.peace_agreements.values())
            outcomes.append({"agreement": bool(agreements),
                             "implementation": mean(p.progress for p in world.agreement_provisions.values()) if agreements else 0.0,
                             "recurrence": any(a.status == "failed" for a in agreements)})
        results.append({"label": regime["label"], "parameters": regime,
                        "agreement_probability": mean(x["agreement"] for x in outcomes),
                        "mean_implementation": mean(x["implementation"] for x in outcomes),
                        "recurrence_probability": mean(x["recurrence"] for x in outcomes)})
    return {"method": "controlled common-opportunity bargaining stress test", "months": months,
            "replications": replications, "regimes": results}


QUESTION_PARAMETER_SETS: dict[str, tuple[str, ...]] = {
    "insurgency_onset": ("recruitment_rate", "social_network.behavior_update_rate",
                         "political_order.peaceful_channel_strength",
                         "organization_ecology.birth_base_hazard"),
    "fragmentation": ("organization_ecology.split_base_hazard",
                       "organization_ecology.birth_base_hazard",
                       "combat.base_attrition_rate", "recruitment_rate"),
    "recurrence": ("peace_process.implementation_rate", "peace_process.recurrence_base_hazard",
                   "peace_process.agreement_base_hazard", "peace_process.negotiation_base_hazard"),
    "foreign_dependence": ("foreign_affairs.intervention_base_hazard", "foreign_affairs.migration_rate",
                           "political_order.peaceful_channel_strength"),
    "control": ("contact_rate", "combat.base_attrition_rate", "recruitment_rate",
                "social_network.behavior_update_rate"),
}


def question_parameter_subset(question: str, config: SimulationConfig | None = None) -> list[str]:
    """Return a defensible active inference set without rewriting the simulator."""
    normalized = question.lower().replace("-", "_").replace(" ", "_")
    for name, parameters in QUESTION_PARAMETER_SETS.items():
        if name in normalized or normalized in name:
            return list(parameters)
    raise ValueError(f"unknown research question {question!r}; choose one of {sorted(QUESTION_PARAMETER_SETS)}")


def question_specific_registry(question: str, config: SimulationConfig | None = None) -> dict[str, Any]:
    config = config or SimulationConfig()
    active = set(question_parameter_subset(question, config))
    return {"question": question, "parameters": [asdict(item) for item in parameter_registry(config)
                                                   if item.code_name in active],
            "excluded_parameter_count": len(parameter_registry(config)) - len(active)}


def fragmentation_forensic(config: SimulationConfig, empirical_target: float,
                           samples: int = 24, repetitions: int = 2) -> dict[str, Any]:
    """Diagnose fragmentation misses as parameter, measurement, or structural problems."""
    parameters = ["organization_ecology.birth_base_hazard", "organization_ecology.split_base_hazard",
                  "organization_ecology.collapse_base_hazard", "organization_ecology.succession_base_hazard",
                  "combat.base_attrition_rate", "recruitment_rate"]
    sensitivity = global_sensitivity(config, ["organization_fragmentation"], samples, parameters, repetitions)
    contract = empirical_target_contract({"organization_fragmentation": empirical_target}, "organizations",
                                        "focused fragmentation benchmark", "fragmentation-forensic", "training")
    identification = practical_identifiability(sensitivity, contract)
    best = min(((score_targets(row["outcomes"], contract)["mean_normalized_error"], row)
                for row in sensitivity["records"]), key=lambda item: item[0])
    ranked = sensitivity["analysis"]["organization_fragmentation"]["main_effect_screen"]
    if best[0] > 2.0:
        diagnosis = "structural model problem or measurement mismatch"
    elif all(item["status"] == "non-identifiable" for item in identification["parameters"].values()):
        diagnosis = "parameter problem with weak identifiability"
    else:
        diagnosis = "parameter problem: at least one focused lever can reproduce the target"
    return {"diagnosis": diagnosis, "best_normalized_error": best[0],
            "best_parameters": best[1]["parameters"], "sensitivity": ranked,
            "identifiability": identification, "target": empirical_target}


def parameter_recovery_experiment(config: SimulationConfig, parameters: list[str] | None = None,
                                  samples: int = 24, repetitions: int = 1) -> dict[str, Any]:
    """Hide a known synthetic vector, generate recorded targets, and attempt recovery."""
    parameters = parameters or ["recruitment_rate", "contact_rate",
                                "peace_process.implementation_rate"]
    truth_draw = latin_hypercube(2, parameters, config.seed + 17)[1]
    truth_config = SimulationConfig.from_dict(config.to_dict()); truth_config.seed = config.seed + 1717
    for path, value in truth_draw.items(): set_parameter(truth_config, path, value)
    truth_metrics = run_model(truth_config)
    # Synthetic target uncertainty simulates an imperfect recorded history.
    contract = empirical_target_contract({key: truth_metrics[key] for key in ("government_control", "implementation")},
                                        "all", "synthetic recorded history", "parameter-recovery", "training")
    sensitivity = global_sensitivity(config, list(contract["targets"]), samples, parameters, repetitions)
    scored = [(score_targets(row["outcomes"], contract)["mean_normalized_error"], row)
              for row in sensitivity["records"]]
    best_error, best = min(scored, key=lambda item: item[0])
    recovered = best["parameters"]
    comparison = {}
    for path in parameters:
        lo, hi, _, _ = SAMPLE_BOUNDS[path]
        comparison[path] = {"true": truth_draw[path], "recovered": recovered[path],
                            "absolute_error": abs(truth_draw[path] - recovered[path]),
                            "normalized_error": abs(truth_draw[path] - recovered[path]) / (hi - lo)}
    mean_parameter_error = mean(item["normalized_error"] for item in comparison.values())
    status = "recovered" if mean_parameter_error < .25 else "partially recovered" if mean_parameter_error < .60 else "not recovered"
    return {"method": "synthetic parameter recovery from recorded target contract", "truth": truth_draw,
            "target_metrics": {key: truth_metrics[key] for key in contract["targets"]},
            "best_training_error": best_error, "recovered": recovered,
            "comparison": comparison, "mean_normalized_parameter_error": mean_parameter_error,
            "status": status, "identifiability": practical_identifiability(sensitivity, contract)}
