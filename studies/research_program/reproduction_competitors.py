"""Benchmark-table construction for the decomposed insurgent reproduction estimand.

The functions here consume observation-only locality activation genealogies and
produce explicit risk-set tables for:

* local endogenous ignition;
* parent-attributed cross-local colonization;
* foothold deepening into saturated access and fielded force;
* post-establishment survival; and
* aggregate site counts suitable for branching-process competitors.

Relocation is never counted as colonization. Unresolved parentage remains
unresolved. The full locality universe is mandatory so inactive sites remain in
the denominator.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


FOOTHOLD = "member_foothold_present"
ACCESS = "member_access_saturated"
FIELDED = "fielded_force_viable"

PARENT_COLONIZATION_CLASSES = {
    "social_network_seeded",
    "migrating_member_seeded",
    "formation_recruitment_seeded",
    "organizational_split_offspring",
    "sanctuary_external_seeded",
}
LOCAL_IGNITION_CLASS = "local_spontaneous_ignition"
UNRESOLVED_CLASS = "unresolved"
RELOCATION_CLASS = "formation_relocation"


@dataclass(frozen=True)
class GenealogyRun:
    run_id: str
    split: str
    genealogy: dict[str, Any]
    locality_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.locality_ids:
            raise ValueError("full locality universe is required for each run")
        if len(set(self.locality_ids)) != len(self.locality_ids):
            raise ValueError("locality universe contains duplicates")


def _observation_end(genealogy: dict[str, Any]) -> float:
    values = [
        float(row.get("observation_end_day", 0.0))
        for row in genealogy.get("episodes", [])
        if row.get("observation_end_day") is not None
    ]
    if values:
        return max(values)
    return float(genealogy.get("horizon_days", 0.0))


def _episode_end(row: dict[str, Any], observation_end: float) -> float:
    value = row.get("activation_end_day")
    if value is None:
        return observation_end
    return float(value)


def _parentage_class(row: dict[str, Any]) -> str:
    value = str(row.get("parentage_class") or "").strip()
    if value:
        return value
    cause = str(row.get("cause") or "")
    mapping = {
        "cross_local_social_recruitment": "social_network_seeded",
        "sympathizer_chain_recruitment": "social_network_seeded",
        "stored_social_exposure_recruitment": "social_network_seeded",
        "armed_member_migration": "migrating_member_seeded",
        "cross_local_recruitment_force_generation": "formation_recruitment_seeded",
        "formation_relocation": "formation_relocation",
        "organizational_split_offspring": "organizational_split_offspring",
        "sanctuary_external_seeded": "sanctuary_external_seeded",
        "local_recruitment": "local_spontaneous_ignition",
    }
    if cause == "initial_condition":
        return "initial_condition"
    return mapping.get(cause, "unresolved")


def _active_at(episode: dict[str, Any], day: float, observation_end: float) -> bool:
    start = float(episode["activation_day"])
    end = _episode_end(episode, observation_end)
    return start <= day < end - 1e-12 or (
        abs(day - start) <= 1e-12 and end >= start
    )


def _active_at_period_start(episode: dict[str, Any], day: float,
                            observation_end: float) -> bool:
    """Left-limit occupancy used to define the new-foothold risk set.

    Initial conditions are present at the start of period zero. A noninitial
    activation exactly on a later bin boundary is a birth in that bin, not an
    already-established site.
    """
    start = float(episode["activation_day"])
    end = _episode_end(episode, observation_end)
    if episode.get("cause") == "initial_condition" and abs(day) <= 1e-12 and abs(start) <= 1e-12:
        return end >= day
    return start < day - 1e-12 and end > day + 1e-12


def _foothold_episodes(genealogy: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in genealogy.get("episodes", []) if row.get("channel") == FOOTHOLD]


def build_site_period_panel(run: GenealogyRun, *, bin_days: float = 7.0,
                            adjacency: dict[str, list[str]] | None = None) -> pd.DataFrame:
    if bin_days <= 0:
        raise ValueError("bin_days must be positive")
    genealogy = run.genealogy
    observation_end = _observation_end(genealogy)
    if observation_end <= 0:
        raise ValueError("genealogy has no positive observation horizon")
    episodes = _foothold_episodes(genealogy)
    unknown = {str(row["locality_id"]) for row in episodes} - set(run.locality_ids)
    if unknown:
        raise ValueError(f"genealogy contains localities outside declared universe: {sorted(unknown)}")
    adjacency = adjacency or {}
    bins = int(math.ceil(observation_end / bin_days))
    rows: list[dict[str, Any]] = []
    for period in range(bins):
        start = period * bin_days
        end = min(observation_end, (period + 1) * bin_days)
        active_start = {
            locality for locality in run.locality_ids
            if any(
                row["locality_id"] == locality and
                _active_at_period_start(row, start, observation_end)
                for row in episodes
            )
        }
        activations_by_locality: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in episodes:
            activation_day = float(row["activation_day"])
            if start <= activation_day < end - 1e-12 and row.get("cause") != "initial_condition":
                activations_by_locality[str(row["locality_id"])].append(row)
        for locality in run.locality_ids:
            new_rows = sorted(
                activations_by_locality.get(locality, []),
                key=lambda item: (float(item["activation_day"]), str(item["activation_id"])),
            )
            classes = [_parentage_class(row) for row in new_rows]
            # Site-level target is first activation while inactive at period
            # start. Episode counts are retained separately for reactivation.
            risk_eligible = locality not in active_start
            first_class = classes[0] if risk_eligible and classes else None
            neighbors = adjacency.get(locality, [])
            neighbor_share = (
                sum(str(neighbor) in active_start for neighbor in neighbors) / len(neighbors)
                if neighbors else 0.0
            )
            rows.append({
                "run_id": run.run_id,
                "split": run.split,
                "locality_id": locality,
                "period_index": period,
                "period_start_day": start,
                "period_end_day": end,
                "active_foothold_start": int(locality in active_start),
                "at_risk_for_new_foothold": int(risk_eligible),
                "new_foothold_site": int(risk_eligible and bool(new_rows)),
                "new_foothold_episodes": len(new_rows),
                "local_spontaneous_ignition": int(first_class == LOCAL_IGNITION_CLASS),
                "parent_attributed_colonization": int(first_class in PARENT_COLONIZATION_CLASSES),
                "unresolved_new_foothold": int(first_class == UNRESOLVED_CLASS),
                "relocation_classified_new_foothold": int(first_class == RELOCATION_CLASS),
                "first_parentage_class": first_class or "none",
                "active_neighbor_share_start": neighbor_share,
                "active_neighbor_count_start": sum(str(neighbor) in active_start for neighbor in neighbors),
                "active_site_count_start": len(active_start),
            })
    return pd.DataFrame(rows)


def _first_followup(episodes: list[dict[str, Any]], locality_id: str, channel: str,
                    start: float, end: float) -> dict[str, Any] | None:
    candidates = [
        row for row in episodes
        if row.get("locality_id") == locality_id and row.get("channel") == channel
        and start - 1e-12 <= float(row["activation_day"]) <= end + 1e-12
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: (float(row["activation_day"]), str(row["activation_id"])))


def build_foothold_episode_panel(run: GenealogyRun, *, deepening_horizon_days: float = 30.0,
                                 survival_horizon_days: float = 14.0) -> pd.DataFrame:
    if deepening_horizon_days <= 0 or survival_horizon_days <= 0:
        raise ValueError("follow-up horizons must be positive")
    episodes = list(run.genealogy.get("episodes", []))
    observation_end = _observation_end(run.genealogy)
    rows: list[dict[str, Any]] = []
    for foothold in [row for row in episodes if row.get("channel") == FOOTHOLD]:
        start = float(foothold["activation_day"])
        locality = str(foothold["locality_id"])
        end = _episode_end(foothold, observation_end)
        deepening_eligible = observation_end + 1e-12 >= start + deepening_horizon_days
        survival_eligible = observation_end + 1e-12 >= start + survival_horizon_days
        access = _first_followup(
            episodes, locality, ACCESS, start, start + deepening_horizon_days
        ) if deepening_eligible else None
        force = _first_followup(
            episodes, locality, FIELDED, start, start + deepening_horizon_days
        ) if deepening_eligible else None
        rows.append({
            "run_id": run.run_id,
            "split": run.split,
            "activation_id": foothold["activation_id"],
            "locality_id": locality,
            "activation_day": start,
            "parentage_class": _parentage_class(foothold),
            "cause": foothold.get("cause"),
            "duration_days_observed": max(0.0, end - start),
            "deepening_followup_eligible": int(deepening_eligible),
            "survival_followup_eligible": int(survival_eligible),
            "deepened_to_saturated_access": int(access is not None) if deepening_eligible else np.nan,
            "deepened_to_fielded_force": int(force is not None) if deepening_eligible else np.nan,
            "survived_horizon": int(end + 1e-12 >= start + survival_horizon_days) if survival_eligible else np.nan,
            "time_to_access_days": (
                float(access["activation_day"]) - start if access is not None else np.nan
            ),
            "time_to_force_days": (
                float(force["activation_day"]) - start if force is not None else np.nan
            ),
        })
    return pd.DataFrame(rows)


def build_aggregate_period_panel(site_period: pd.DataFrame) -> pd.DataFrame:
    if site_period.empty:
        return pd.DataFrame()
    grouped = site_period.groupby(
        ["run_id", "split", "period_index", "period_start_day", "period_end_day"],
        as_index=False,
    ).agg(
        active_sites_start=("active_foothold_start", "sum"),
        at_risk_sites=("at_risk_for_new_foothold", "sum"),
        new_foothold_sites=("new_foothold_site", "sum"),
        new_foothold_episodes=("new_foothold_episodes", "sum"),
        local_spontaneous_ignitions=("local_spontaneous_ignition", "sum"),
        parent_attributed_colonizations=("parent_attributed_colonization", "sum"),
        unresolved_new_footholds=("unresolved_new_foothold", "sum"),
        relocation_classified_new_footholds=("relocation_classified_new_foothold", "sum"),
    )
    return grouped.sort_values(["run_id", "period_index"]).reset_index(drop=True)


def build_reproduction_tables(runs: Iterable[GenealogyRun], *, bin_days: float = 7.0,
                              deepening_horizon_days: float = 30.0,
                              survival_horizon_days: float = 14.0,
                              adjacency: dict[str, list[str]] | None = None) -> dict[str, pd.DataFrame]:
    site_parts, episode_parts = [], []
    for run in runs:
        site_parts.append(build_site_period_panel(run, bin_days=bin_days, adjacency=adjacency))
        episode_parts.append(build_foothold_episode_panel(
            run,
            deepening_horizon_days=deepening_horizon_days,
            survival_horizon_days=survival_horizon_days,
        ))
    site = pd.concat(site_parts, ignore_index=True) if site_parts else pd.DataFrame()
    episode = pd.concat(episode_parts, ignore_index=True) if episode_parts else pd.DataFrame()
    aggregate = build_aggregate_period_panel(site)
    return {"site_period": site, "foothold_episode": episode, "aggregate_period": aggregate}


def fit_group_shrunk_binary(training: pd.DataFrame, target: str,
                            group: str | None = None, prior_rows: float = 8.0) -> tuple[float, dict[str, float]]:
    observed = training[target].dropna().astype(float)
    if observed.empty:
        raise ValueError(f"no observed training rows for {target}")
    global_p = (float(observed.sum()) + 1.0) / (len(observed) + 2.0)
    if group is None:
        return global_p, {}
    grouped = training.dropna(subset=[target]).groupby(group)[target].agg(["sum", "count"])
    probabilities = {
        str(index): float((row["sum"] + prior_rows * global_p) /
                          (row["count"] + prior_rows))
        for index, row in grouped.iterrows()
    }
    return global_p, probabilities


def episode_binary_competitors(frame: pd.DataFrame, target: str,
                               *, split_col: str = "split") -> pd.DataFrame:
    eligible = frame.dropna(subset=[target]).copy()
    training = eligible[eligible[split_col] == "training"]
    global_p, locality = fit_group_shrunk_binary(training, target, "locality_id")
    _, parentage = fit_group_shrunk_binary(training, target, "parentage_class")
    output = eligible[["run_id", split_col, "activation_id", "locality_id", target]].copy()
    output["constant_probability"] = global_p
    output["locality_empirical_bayes"] = eligible.locality_id.map(locality).fillna(global_p)
    output["parentage_class_empirical_bayes"] = eligible.parentage_class.map(parentage).fillna(global_p)
    return output


def score_episode_binary(predictions: pd.DataFrame, target: str,
                         *, split_col: str = "split") -> pd.DataFrame:
    identity = {"run_id", split_col, "activation_id", "locality_id", target}
    models = [column for column in predictions.columns if column not in identity]
    rows = []
    for split, subset in predictions.groupby(split_col, sort=False):
        y = subset[target].to_numpy(dtype=float)
        for model in models:
            p = np.clip(subset[model].to_numpy(dtype=float), 1e-9, 1-1e-9)
            rows.append({
                "split": split,
                "target": target,
                "model": model,
                "n": len(subset),
                "log_score": float(np.mean(y*np.log(p) + (1-y)*np.log(1-p))),
                "brier": float(np.mean((y-p)**2)),
                "observed_mean": float(np.mean(y)),
                "predicted_mean": float(np.mean(p)),
            })
    return pd.DataFrame(rows)


def decomposition_summary(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    site = tables["site_period"]
    episode = tables["foothold_episode"]
    new_rows = site[site.new_foothold_site == 1]
    return {
        "site_period_rows": int(len(site)),
        "foothold_episode_rows": int(len(episode)),
        "new_foothold_sites": int(new_rows.new_foothold_site.sum()) if not new_rows.empty else 0,
        "local_spontaneous_ignitions": int(new_rows.local_spontaneous_ignition.sum()) if not new_rows.empty else 0,
        "parent_attributed_colonizations": int(new_rows.parent_attributed_colonization.sum()) if not new_rows.empty else 0,
        "unresolved_new_footholds": int(new_rows.unresolved_new_foothold.sum()) if not new_rows.empty else 0,
        "relocation_classified_new_footholds": int(new_rows.relocation_classified_new_foothold.sum()) if not new_rows.empty else 0,
        "parentage_class_counts": dict(Counter(new_rows.first_parentage_class)) if not new_rows.empty else {},
        "deepening_eligible": int(episode.deepening_followup_eligible.sum()) if not episode.empty else 0,
        "survival_eligible": int(episode.survival_followup_eligible.sum()) if not episode.empty else 0,
    }
