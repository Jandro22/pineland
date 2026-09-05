"""Summarize synthetic recorded contact events against the frozen UCDP targets.

This deliberately does not map Pineland's unitless reported severity to UCDP
fatalities.  A zero-contact result is retained as a result, not replaced with
an imputed event or a favorable statistic.
"""
from __future__ import annotations

from datetime import date, timedelta
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pineland_sim.historical import (fano_factor, gini, lag_correlation,
                                     morans_i, population_adjusted_hhi)


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
RUNS = STUDY / "runs" / "untuned_realized"
RESULTS = STUDY / "results" / "benchmark"
START = date(2001, 11, 26)
BOUNDARY = date(2005, 1, 1)
END = date(2006, 11, 21)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def windows(start: date, end: date, label: str) -> list[dict]:
    rows = []
    cursor, index = start, 0
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=6))
        rows.append({"window_id": f"{label}-{index:03d}", "start": cursor,
                     "end": stop, "exposure_days": (stop - cursor).days + 1})
        cursor, index = stop + timedelta(days=1), index + 1
    return rows


def split_windows() -> list[dict]:
    return windows(START, BOUNDARY - timedelta(days=1), "early") + windows(
        BOUNDARY, END, "late")


def split_for(district: str, when: date, eastern: set[str]) -> str:
    early = when < BOUNDARY
    return (("geographic_validation" if district in eastern else "training") if early else
            ("strict_joint_holdout" if district in eastern else "temporal_validation"))


def summarize_panel(panel: pd.DataFrame, events: pd.DataFrame, population: pd.Series,
                    adjacency: dict[str, list[str]]) -> dict:
    values = panel["events"].astype(float) * 7 / panel["exposure_days"]
    totals = panel.groupby("district_id").events.sum().reindex(population.index, fill_value=0)
    rates = (totals / population * 100_000).to_dict()
    by_week = panel.groupby("window_id").events.sum()
    active = panel.assign(active=panel.events > 0).groupby("window_id").active.mean()
    per_district = panel.sort_values("window_start").groupby("district_id").events.apply(
        lambda x: lag_correlation((x > 0).astype(int).tolist()))
    distances = []
    if not events.empty:
        geo = events.sort_values(["day", "event_id"])
        coords = json.loads((STUDY / "config" / "case_environment.json").read_text())
        points = {row["locality_id"]: (row["x_km"], row["y_km"])
                  for row in coords["localities"]}
        for left, right in zip(geo.iloc[:-1].itertuples(), geo.iloc[1:].itertuples()):
            if left.district_id in points and right.district_id in points:
                x1, y1 = points[left.district_id]; x2, y2 = points[right.district_id]
                distances.append(float(np.hypot(x1 - x2, y1 - y2)))
    gaps = []
    for _, group in events.groupby("district_id") if not events.empty else []:
        dates = sorted(group.day.astype(float).tolist())
        gaps.extend(right - left for left, right in zip(dates, dates[1:]))
    return {
        "event_count": int(len(events)),
        "mean_events_per_district_week": float(values.mean()),
        "variance_events_per_district_week": float(values.var(ddof=0)),
        "zero_event_share": float((panel.events == 0).mean()),
        "mean_active_district_share_by_week": float(active.mean()),
        "weekly_fano_including_zeros": fano_factor(values.tolist()),
        "negative_binomial_dispersion_moments": max(0.0, float((values.var(ddof=0) - values.mean()) /
                                                               max(1e-12, values.mean() ** 2))),
        "population_adjusted_normalized_hhi": population_adjusted_hhi(totals.tolist(), population.tolist()),
        "district_count_gini": gini(totals.tolist()),
        "morans_i_events_per_100k": morans_i(rates, adjacency),
        "mean_district_active_state_acf_lag1": float(per_district.mean()) if len(per_district) else 0.0,
        "inter_event_gap_days": {"count": len(gaps), "mean": float(np.mean(gaps)) if gaps else 0.0},
        "consecutive_event_distance_km": {"count": len(distances),
                                           "mean": float(np.mean(distances)) if distances else 0.0},
        "severity_comparable_to_ucdp_fatalities": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=RUNS)
    parser.add_argument("--results-dir", type=Path, default=RESULTS)
    args = parser.parse_args()
    files = sorted(args.runs_dir.glob("seed_*_agents_*.json"))
    if not files:
        raise SystemExit("no untuned run files found; run run_untuned_benchmark.py first")
    case = json.loads((STUDY / "config" / "case_environment.json").read_text())
    districts = pd.read_csv(STUDY / "config" / "districts.csv")
    eastern = set(districts.loc[districts.is_eastern_holdout, "district_id"])
    population = pd.read_csv(STUDY / "data" / "processed" / "population_2001.csv").set_index("district_id").population_2001
    adjacency = json.loads((STUDY / "data" / "processed" / "district_adjacency.json").read_text())["neighbors"]
    all_districts = districts.district_id.tolist()
    base_rows = []
    for district in all_districts:
        for window in split_windows():
            base_rows.append({"district_id": district, "window_id": window["window_id"],
                              "window_start": window["start"], "exposure_days": window["exposure_days"],
                              "events": 0})
    base = pd.DataFrame(base_rows)
    summaries = []
    panel_outputs = []
    for path in files:
        payload = json.loads(path.read_text())
        # Keep each trajectory's panel independent. The frozen zero-event
        # base is a template; it must not accumulate counts across seeds.
        panel = base.copy()
        events = pd.DataFrame([row for row in payload["contacts"]
                               if row.get("realized", False) and row["recorded"]])
        if events.empty:
            events = pd.DataFrame(columns=["event_id", "day", "date", "district_id", "recorded",
                           "reported_severity", "reported_actor", "geocoding_error", "realized"])
        else:
            events["event_date"] = pd.to_datetime(events.date).dt.date
            events["split"] = [split_for(district, when, eastern)
                                for district, when in zip(events.district_id, events.event_date)]
            for row in events.itertuples():
                when = row.event_date
                era_start = START if when < BOUNDARY else BOUNDARY
                label = "early" if when < BOUNDARY else "late"
                window_id = f"{label}-{(when - era_start).days // 7:03d}"
                mask = (base.district_id == row.district_id) & (base.window_id == window_id)
                # Update this trajectory's panel only.  Mutating the frozen
                # template would leak one seed's events into every later
                # trajectory and invalidate uncertainty intervals.
                panel.loc[mask, "events"] += 1
        for split in ("training", "temporal_validation", "geographic_validation", "strict_joint_holdout"):
            split_panel = panel[panel.apply(lambda row: split_for(row.district_id, row.window_start, eastern) == split, axis=1)]
            split_events = events[events.split == split] if not events.empty else events
            result = summarize_panel(split_panel, split_events, population.loc[split_panel.district_id.unique()], adjacency)
            result.update({"seed": payload["seed"], "split": split,
                           "realized_latent_contact_records": int(payload.get("realized_contact_count", 0)),
                           "contact_attempt_records": len(payload["contacts"]),
                           "recorded_contact_count": int(len(split_events))})
            summaries.append(result)
        panel_outputs.append(panel.assign(seed=payload["seed"]))
    summary_frame = pd.DataFrame(summaries)
    args.results_dir.mkdir(parents=True, exist_ok=True)
    summary_frame.to_csv(args.results_dir / "untuned_contact_metrics.csv", index=False)
    numeric_metrics = ["recorded_contact_count", "mean_events_per_district_week",
                       "weekly_fano_including_zeros", "population_adjusted_normalized_hhi",
                       "district_count_gini", "morans_i_events_per_100k"]
    uncertainty = []
    for split, group in summary_frame.groupby("split", sort=False):
        row = {"split": split, "runs": int(len(group))}
        for metric in numeric_metrics:
            values = group[metric].astype(float).to_numpy()
            row[f"{metric}_mean"] = float(np.mean(values))
            row[f"{metric}_p05"] = float(np.quantile(values, .05))
            row[f"{metric}_p95"] = float(np.quantile(values, .95))
        uncertainty.append(row)
    pd.DataFrame(uncertainty).to_csv(args.results_dir / "untuned_contact_uncertainty.csv", index=False)
    pd.concat(panel_outputs, ignore_index=True).to_csv(args.results_dir / "untuned_contact_panel.csv", index=False)
    output = {
        "schema_version": "1.0.0", "study_id": "nepal_2001_2006", "stage": "untuned",
        "comparison": "synthetic realized recorded contacts vs UCDP two-sided state-based recorded events",
        "historical_primary_construct": "government_maoist_state_based",
        "interpretation_guard": "Pineland reported severity is unitless and is not compared to UCDP fatalities",
        "source_hashes": {"case_environment": sha256(STUDY / "config" / "case_environment.json"),
                          "split_manifest": sha256(STUDY / "config" / "split_manifest.json"),
                          "historical_targets": sha256(STUDY / "results" / "historical" / "historical_descriptive_statistics.json")},
        "runs": len(files), "seeds": [json.loads(path.read_text())["seed"] for path in files],
        "total_recorded_contacts": int(summary_frame.recorded_contact_count.sum()),
        "total_realized_latent_contacts": int(summary_frame.groupby("seed").realized_latent_contact_records.first().sum()),
        # Backward-compatible alias retained for consumers of the first
        # corrected run; both fields mean realized latent contacts, not
        # scheduled attempts.
        "total_contact_records": int(summary_frame.groupby("seed").realized_latent_contact_records.first().sum()),
        "total_contact_attempt_records": int(summary_frame.groupby("seed").contact_attempt_records.first().sum()),
        "contact_generation_failure": bool(summary_frame.recorded_contact_count.sum() == 0),
        "uncertainty": uncertainty,
        "metrics": summary_frame.to_dict(orient="records"),
    }
    (args.results_dir / "untuned_benchmark.json").write_text(json.dumps(output, indent=2, default=str) + "\n")
    print(json.dumps({"runs": len(files), "recorded_contacts": output["total_recorded_contacts"],
                      "contact_generation_failure": output["contact_generation_failure"]}, indent=2))


if __name__ == "__main__":
    main()
