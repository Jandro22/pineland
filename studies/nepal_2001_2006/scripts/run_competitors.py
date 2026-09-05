"""Fair, frozen statistical competitors for the Nepal district-week target."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
DATA = STUDY / "data" / "processed"
OUT = STUDY / "results" / "competitors"
START = date(2001, 11, 26)
BOUNDARY = date(2005, 1, 1)
PRIMARY_STRATUM = "government_maoist_state_based"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def split_rows(frame: pd.DataFrame, split: str) -> pd.DataFrame:
    return frame[frame.split == split].copy()


def target_panel() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[str]], pd.Series]:
    panel = pd.read_csv(DATA / "district_week_panel.csv")
    # The contact analogue is two-sided state-based violence.  One-sided
    # violence remains an external diagnostic and is not pooled into this fit.
    panel["events"] = panel[f"{PRIMARY_STRATUM}_events"]
    events = pd.read_csv(DATA / "ucdp_nepal_events.csv")
    events = events[events.district_id.notna() &
                    (events.stratum == PRIMARY_STRATUM)].copy()
    districts = pd.read_csv(STUDY / "config" / "districts.csv")
    eastern = set(districts.loc[districts.is_eastern_holdout, "district_id"])
    events["event_date"] = pd.to_datetime(events.date_start).dt.date
    events["split"] = [
        ("geographic_validation" if district in eastern else "training") if when < BOUNDARY else
        ("strict_joint_holdout" if district in eastern else "temporal_validation")
        for district, when in zip(events.district_id, events.event_date)
    ]
    adjacency = json.loads((DATA / "district_adjacency.json").read_text())["neighbors"]
    population = pd.read_csv(DATA / "population_2001.csv").set_index("district_id").population_2001
    return panel, events, adjacency, population


def fit_rates(training: pd.DataFrame, districts: list[str], adjacency: dict[str, list[str]]) -> dict[str, dict[str, float]]:
    exposure = training.groupby("district_id").exposure_days.sum().reindex(districts, fill_value=0)
    counts = training.groupby("district_id").events.sum().reindex(districts, fill_value=0)
    pooled = float(counts.sum() / max(1.0, exposure.sum()) * 7.0)
    # Fixed empirical-Bayes shrinkage: eight district-weeks of pooled prior.
    kappa = 8.0
    district = ((counts + kappa * pooled) / (exposure / 7.0 + kappa)).to_dict()
    spatial = {}
    for district_id in districts:
        neighbors = adjacency.get(district_id, [])
        neighbor_rate = float(np.mean([district.get(neighbor, pooled) for neighbor in neighbors])) if neighbors else pooled
        spatial[district_id] = .5 * district[district_id] + .5 * neighbor_rate
    return {"poisson": {district_id: pooled for district_id in districts},
            "district_nb": district, "spatial_lag_nb": spatial}


def hawkes_rates(row_frame: pd.DataFrame, training_events: pd.DataFrame, base_rates: dict[str, float],
                 alpha: float = .30, beta: float = .25, update_with_frame: bool = False) -> np.ndarray:
    """Causal weekly Hawkes score with fixed decay (one-step forecasting)."""
    history = {district: [] for district in base_rates}
    for row in training_events.itertuples():
        history.setdefault(row.district_id, []).append((row.event_date - START).days / 7.0)
    values = []
    for row in row_frame.sort_values(["week_start", "district_id"]).itertuples():
        t = (pd.Timestamp(row.week_start).date() - START).days / 7.0
        excitation = alpha * sum(np.exp(-beta * (t - past)) for past in history.get(row.district_id, []) if past < t)
        values.append(max(1e-9, base_rates.get(row.district_id, 0.0) + excitation))
        # For rolling one-step prediction, newly observed events enter only
        # after their week; this is forecasting, not retrospective smoothing.
        if update_with_frame:
            observed = int(row.events)
            history.setdefault(row.district_id, []).extend([t] * observed)
    return np.asarray(values)


def score(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    predicted = np.maximum(predicted, 1e-9)
    # Poisson log score is appropriate for counts, while MAE/Brier retain
    # interpretable incidence and zero/nonzero behavior.
    log_score = observed * np.log(predicted) - predicted - np.array([
        math.lgamma(value + 1) for value in observed
    ])
    active_probability = 1.0 - np.exp(-predicted)
    return {"mean_poisson_log_score": float(np.mean(log_score)),
            "mean_absolute_error": float(np.mean(np.abs(observed - predicted))),
            "active_brier": float(np.mean(((observed > 0).astype(float) - active_probability) ** 2)),
            "observed_mean": float(np.mean(observed)), "predicted_mean": float(np.mean(predicted)),
            "observed_event_count": int(observed.sum())}


def main() -> None:
    panel, events, adjacency, population = target_panel()
    districts = population.index.tolist()
    training = split_rows(panel, "training")
    rates = fit_rates(training, districts, adjacency)
    results = []
    for split in ("training", "temporal_validation", "geographic_validation", "strict_joint_holdout"):
        frame = split_rows(panel, split).sort_values(["week_start", "district_id"])
        observed = frame.events.to_numpy(dtype=float)
        for model, model_rates in rates.items():
            predicted = frame.district_id.map(model_rates).to_numpy(dtype=float)
            results.append({"split": split, "model": model, **score(observed, predicted),
                            "parameter_fit_rows": int(len(training)),
                            "spatial_adjacency_sha256": sha256(DATA / "district_adjacency.json")})
        # Hawkes uses the same frozen training event history for every target;
        # no validation outcomes enter its base-rate fit.
        hawkes = hawkes_rates(frame, events[events.split == "training"], rates["district_nb"],
                              update_with_frame=(split == "training"))
        results.append({"split": split, "model": "hawkes_fixed_kernel", **score(observed, hawkes),
                        "parameter_fit_rows": int(len(training)),
                        "hawkes_alpha": .30, "hawkes_beta_per_week": .25})
    output = pd.DataFrame(results)
    OUT.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUT / "competitor_scores.csv", index=False)
    from pineland_sim.reproducibility import build_run_manifest, file_sha256
    source_paths = [
        DATA / "district_week_panel.csv",
        DATA / "ucdp_nepal_events.csv",
        DATA / "district_adjacency.json",
        DATA / "population_2001.csv",
        STUDY / "config" / "districts.csv",
        STUDY / "config" / "study.json",
        STUDY / "data" / "manifests" / "sources.json",
    ]
    analysis_config = {
        "target_construct": "two_sided_state_based",
        "fit_boundary": "training only",
        "holdout_refitting": False,
        "models": sorted(output.model.unique()),
        "district_empirical_bayes_prior_weeks": 8.0,
        "hawkes_alpha": 0.30,
        "hawkes_beta_per_week": 0.25,
    }
    manifest = build_run_manifest(
        analysis_config,
        seeds=["not_applicable_deterministic"],
        execution_mode={
            "mode": "deterministic_statistical_competitor_fit_and_score",
            "workers": 1,
            "process_isolated": False,
        },
        output_schema={
            "name": "nepal_statistical_competitor_scores",
            "version": "2.0.0",
            "scores_format": "csv",
            "manifest_format": "json",
        },
        case_files=source_paths,
        split_file=STUDY / "config" / "split_manifest.json",
        repo_root=ROOT,
        extra={"runner_sha256": file_sha256(Path(__file__))},
    )
    manifest.update({
        **analysis_config,
        "source_hashes": {path.name: sha256(path) for path in source_paths},
        "scores_file_sha256": sha256(OUT / "competitor_scores.csv"),
    })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
