"""Compute the preregistered descriptive target library from recorded UCDP data."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import random

import numpy as np
import pandas as pd

from pineland_sim.historical import (active_run_lengths, burstiness, fano_factor,
                                      gini, haversine_km, lag_correlation, morans_i,
                                      population_adjusted_hhi, sha256_file)


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
DATA = STUDY / "data" / "processed"
STRATA = (
    "government_maoist_state_based", "state_one_sided", "maoist_one_sided",
)
CONSTRUCTS = {
    "all": list(STRATA),
    "two_sided_state_based": ["government_maoist_state_based"],
    "state_one_sided": ["state_one_sided"],
    "maoist_one_sided": ["maoist_one_sided"],
}
SPLITS = ("training", "temporal_validation", "geographic_validation", "strict_joint_holdout")


def quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {key: 0.0 for key in ("median", "p90", "p95")}
    return {"median": float(np.quantile(values, .5)),
            "p90": float(np.quantile(values, .9)),
            "p95": float(np.quantile(values, .95))}


def event_split(event: pd.Series, eastern_ids: set[str]) -> str:
    early = event["event_date"].date() < date(2005, 1, 1)
    eastern = event["district_id"] in eastern_ids
    return ("geographic_validation" if eastern else "training") if early else (
        "strict_joint_holdout" if eastern else "temporal_validation")


def recurrence_probability(events: pd.DataFrame, days: int) -> float:
    indicators: list[bool] = []
    for _, group in events.groupby("district_id"):
        dates = sorted(group.event_date)
        indicators.extend(0 < (dates[index + 1] - current).days <= days
                          if index + 1 < len(dates) else False
                          for index, current in enumerate(dates))
    return float(np.mean(indicators)) if indicators else 0.0


def incidence(panel: pd.DataFrame, column: str, population: pd.Series) -> dict:
    rates = panel[column] * 7 / panel.exposure_days
    average, variance = float(rates.mean()), float(rates.var(ddof=0))
    totals = panel.groupby("district_id")[column].sum().reindex(population.index, fill_value=0)
    incidence_rates = (totals / population * 100_000).to_dict()
    adjacency = json.loads((DATA / "district_adjacency.json").read_text())["neighbors"]
    return {
        "mean_events_per_district_week": average,
        "variance_events_per_district_week": variance,
        "zero_event_share": float((panel[column] == 0).mean()),
        "mean_active_district_share_by_week": float(
            panel.assign(active=panel[column] > 0).groupby("window_id").active.mean().mean()),
        "negative_binomial_dispersion_moments": max(0.0, (variance - average) / max(1e-12, average ** 2)),
        "population_adjusted_normalized_hhi": population_adjusted_hhi(totals.tolist(), population.tolist()),
        "top_decile_district_event_share": float(totals.nlargest(max(1, int(np.ceil(len(totals) * .1)))).sum() /
                                                   max(1, totals.sum())),
        "district_count_gini": gini(totals.tolist()),
        "morans_i_events_per_100k": morans_i(incidence_rates, adjacency),
    }


def temporal(panel: pd.DataFrame, events: pd.DataFrame, column: str) -> dict:
    gaps: list[int] = []
    for _, group in events.groupby("district_id"):
        dates = sorted(group.event_date)
        gaps.extend((right - left).days for left, right in zip(dates, dates[1:]))
    correlations = []
    runs: list[int] = []
    transitions = defaultdict(int)
    for _, group in panel.sort_values("week_start").groupby("district_id"):
        active = (group[column] > 0).astype(int).tolist()
        correlations.append(lag_correlation(active))
        runs.extend(active_run_lengths(active))
        for left, right in zip(active, active[1:]):
            transitions[f"{left}->{right}"] += 1
    total_from = {state: sum(value for key, value in transitions.items() if key.startswith(f"{state}->"))
                  for state in (0, 1)}
    return {
        "weekly_fano_including_zeros": fano_factor((panel[column] * 7 / panel.exposure_days).tolist()),
        "inter_event_gap_days": {"count": len(gaps), "mean": float(np.mean(gaps)) if gaps else 0.0,
                                 **quantiles(gaps)},
        "inter_event_burstiness": burstiness(gaps),
        "same_district_recurrence_probability": {
            str(days): recurrence_probability(events, days) for days in (7, 14, 28)
        },
        "mean_district_active_state_acf_lag1": float(np.mean(correlations)),
        "active_week_run_length": {"count": len(runs), "mean": float(np.mean(runs)) if runs else 0.0,
                                   **quantiles(runs)},
        "active_state_transitions": {
            key: {"count": value, "probability": value / max(1, total_from[int(key[0])])}
            for key, value in sorted(transitions.items())
        },
    }


def diffusion(panel: pd.DataFrame, events: pd.DataFrame, column: str,
              adjacency: dict[str, list[str]]) -> dict:
    ordered = events.sort_values(["event_date", "id"])
    pairs = list(zip(ordered.iloc[:-1].itertuples(), ordered.iloc[1:].itertuples()))
    distances = [haversine_km((left.latitude, left.longitude), (right.latitude, right.longitude))
                 for left, right in pairs]
    next_adjacent = [right.district_id in adjacency[left.district_id] for left, right in pairs]
    by_district_window = panel.pivot(index="district_id", columns="window_id", values=column)
    window_order = panel[["window_id", "week_start"]].drop_duplicates().sort_values("week_start").window_id.tolist()
    by_district_window = by_district_window.reindex(columns=window_order, fill_value=0)
    hazards = {}
    for horizon in (1, 2, 4):
        outcomes = []
        for district_id in by_district_window.index:
            for index, active in enumerate(by_district_window.loc[district_id]):
                if active <= 0:
                    continue
                future = window_order[index + 1:index + horizon + 1]
                outcomes.append(any(by_district_window.loc[neighbor, future].sum() > 0
                                    for neighbor in adjacency[district_id]
                                    if future and neighbor in by_district_window.index))
        hazards[str(horizon)] = float(np.mean(outcomes)) if outcomes else 0.0
    rng = random.Random(20011126)
    locations = ordered.district_id.tolist()
    nulls = []
    for _ in range(200):
        shuffled = locations[:]; rng.shuffle(shuffled)
        nulls.append(np.mean([right in adjacency[left] for left, right in zip(shuffled, shuffled[1:])]))
    return {
        "consecutive_event_distance_km": {"count": len(distances), "mean": float(np.mean(distances)) if distances else 0.0,
                                          **quantiles(distances)},
        "next_event_adjacent_probability": float(np.mean(next_adjacent)) if next_adjacent else 0.0,
        "neighbor_propagation_probability_weeks": hazards,
        "location_shuffled_next_adjacent_probability": {
            "replications": len(nulls), "mean": float(np.mean(nulls)),
            "p05": float(np.quantile(nulls, .05)), "p95": float(np.quantile(nulls, .95)),
        },
        "same_day_order_rule": "UCDP numeric event id; distance sensitivity must retain this caveat",
    }


def severity(events: pd.DataFrame) -> dict:
    result = {}
    for estimate in ("low", "best", "high"):
        values = events[estimate].astype(float).tolist()
        result[estimate] = {
            "mean": float(np.mean(values)) if values else 0.0,
            **quantiles(values),
            "low_fatality_share_le_1": float(np.mean(np.asarray(values) <= 1)) if values else 0.0,
            "high_fatality_share_ge_10": float(np.mean(np.asarray(values) >= 10)) if values else 0.0,
        }
    return result


def main() -> None:
    panel = pd.read_csv(DATA / "district_week_panel.csv")
    events = pd.read_csv(DATA / "ucdp_nepal_events.csv")
    events = events[events.district_id.notna()].copy()
    events["event_date"] = pd.to_datetime(events.date_start)
    population_frame = pd.read_csv(DATA / "population_2001.csv")
    population = population_frame.set_index("district_id").population_2001
    districts = pd.read_csv(STUDY / "config" / "districts.csv")
    eastern_ids = set(districts.loc[districts.is_eastern_holdout, "district_id"])
    events["split"] = events.apply(event_split, axis=1, eastern_ids=eastern_ids)
    adjacency = json.loads((DATA / "district_adjacency.json").read_text())["neighbors"]

    output: dict[str, object] = {
        "schema_version": "1.0.0",
        "construct": "recorded_lethal_organized_violence_not_latent_conflict_truth",
        "primary_construct": "two_sided_state_based",
        "construct_ontology": {
            "two_sided_state_based": {
                "historical": "UCDP state-based Government of Nepal–CPN-M events",
                "simulation": "realized Pineland two-sided contact/engagement",
                "status": "primary benchmark target",
            },
            "state_one_sided": {
                "historical": "UCDP Government of Nepal–civilian one-sided violence",
                "simulation": None,
                "status": "observational diagnostic only; no validated Pineland analogue",
            },
            "maoist_one_sided": {
                "historical": "UCDP CPN-M–civilian one-sided violence",
                "simulation": None,
                "status": "observational diagnostic only; no validated Pineland analogue",
            },
        },
        "source_hashes": {
            name: sha256_file(DATA / name) for name in (
                "district_week_panel.csv", "ucdp_nepal_events.csv", "population_2001.csv",
                "district_adjacency.json",
            )
        },
        "splits": {},
    }
    ecdf_rows = []
    for split in SPLITS:
        split_panel = panel[panel.split == split]
        split_events = events[events.split == split]
        split_output = {"districts": int(split_panel.district_id.nunique()),
                        "windows": int(split_panel.window_id.nunique()), "strata": {}}
        for label, selected_strata in CONSTRUCTS.items():
            column = f"_{label}_events"
            split_panel = split_panel.copy()
            split_panel[column] = sum(split_panel[f"{item}_events"] for item in selected_strata)
            selected_events = split_events[split_events.stratum.isin(selected_strata)]
            split_output["strata"][label] = {
                "event_count": int(len(selected_events)),
                "incidence_and_concentration": incidence(split_panel, column, population.loc[split_panel.district_id.unique()]),
                "temporal_and_persistence": temporal(split_panel, selected_events, column),
                "spatial_diffusion": diffusion(split_panel, selected_events, column, adjacency),
                "severity": severity(selected_events),
            }
            for estimate in ("low", "best", "high"):
                ordered = np.sort(selected_events[estimate].astype(float).to_numpy())
                ecdf_rows.extend({"split": split, "stratum": label, "estimate": estimate,
                                  "fatalities": value, "ecdf": (index + 1) / len(ordered)}
                                 for index, value in enumerate(ordered))
        output["splits"][split] = split_output
    result_dir = STUDY / "results" / "historical"
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "historical_descriptive_statistics.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(ecdf_rows).to_csv(result_dir / "fatality_ecdf.csv", index=False)
    print(json.dumps({split: {"events": output["splits"][split]["strata"]["all"]["event_count"],
                                    "districts": output["splits"][split]["districts"]}
                      for split in SPLITS}, indent=2))


if __name__ == "__main__":
    main()
