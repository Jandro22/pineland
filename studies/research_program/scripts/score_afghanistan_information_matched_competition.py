"""Score the filtered Afghanistan forecast against information-matched models.

This scorer is intentionally dormant during architecture work. It requires
``--reveal-holdout`` before reading the 2005 target and fits every simple model
on 2004 rows only. The candidate is scored from the frozen runner's observed
predictive field, not its latent field. The script is separate from the old
frozen-core scorer so that its provenance and information contract cannot be
confused with the consumed historical artifact.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
CASE = STUDY / "config" / "case_environment.json"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"
TRAINING_YEAR = "2004"
HOLDOUT_YEAR = "2005"
EPS = 1e-9

sys.path.insert(0, str(ROOT / "studies" / "research_program"))

from simple_competitors import (  # noqa: E402
    PanelSpec,
    predictions_for_panel,
    score_predictions,
)


def _load_case_features(case: dict) -> pd.DataFrame:
    """Aggregate only preperiod and exogenous geography to province level."""
    high_counts = {
        str(key): float(value)
        for key, value in case.get(
            "preperiod_taliban_state_conflict_counts_2003", {}
        ).items()
    }
    background_counts = {
        str(key): float(value)
        for key, value in case.get(
            "preperiod_taliban_state_conflict_province_background_counts_2003",
            {},
        ).items()
    }
    localities = {
        str(row["district_id"]): row
        for row in case.get("localities", [])
    }
    grouped: dict[str, dict[str, float | str]] = defaultdict(
        lambda: {
            "region_id": "",
            "preperiod_high_precision_events": 0.0,
            "preperiod_high_precision_occupied_districts": 0.0,
            "population": 0.0,
            "connectivity_sum": 0.0,
            "urbanization_sum": 0.0,
            "infrastructure_sum": 0.0,
            "observability_sum": 0.0,
            "capital_districts": 0.0,
            "districts": 0.0,
        }
    )
    for district in case.get("districts", []):
        district_id = str(district["district_id"])
        containers = district["container_ids"]
        province = str(containers["province"])
        row = grouped[province]
        row["region_id"] = str(containers["region"])
        row["districts"] = float(row["districts"]) + 1.0
        row["population"] = float(row["population"]) + float(district["population"])
        row["connectivity_sum"] = float(row["connectivity_sum"]) + float(
            district.get("connectivity", 0.0)
        )
        row["urbanization_sum"] = float(row["urbanization_sum"]) + float(
            district.get("urbanization", 0.0)
        )
        row["capital_districts"] = float(row["capital_districts"]) + float(
            district.get("unit_type") == "Capital"
        )
        if district_id in localities:
            locality = localities[district_id]
            row["infrastructure_sum"] = float(row["infrastructure_sum"]) + float(
                locality.get("infrastructure", 0.0)
            )
            row["observability_sum"] = float(row["observability_sum"]) + float(
                locality.get("observability", 0.0)
            )
        high_count = high_counts.get(district_id, 0.0)
        row["preperiod_high_precision_events"] = float(
            row["preperiod_high_precision_events"]
        ) + high_count
        row["preperiod_high_precision_occupied_districts"] = float(
            row["preperiod_high_precision_occupied_districts"]
        ) + float(high_count > 0)

    result = []
    for province, row in sorted(grouped.items()):
        districts = max(1.0, float(row["districts"]))
        result.append({
            "province_id": province,
            "region_id": str(row["region_id"]),
            "preperiod_high_precision_events": float(
                row["preperiod_high_precision_events"]
            ),
            "preperiod_high_precision_occupied_share": float(
                row["preperiod_high_precision_occupied_districts"]
            ) / districts,
            "preperiod_background_events": background_counts.get(province, 0.0),
            "log_population": math.log1p(float(row["population"])),
            "mean_connectivity": float(row["connectivity_sum"]) / districts,
            "mean_urbanization": float(row["urbanization_sum"]) / districts,
            "mean_infrastructure": float(row["infrastructure_sum"]) / districts,
            "mean_observability": float(row["observability_sum"]) / districts,
            "capital_district_share": float(row["capital_districts"]) / districts,
        })
    return pd.DataFrame(result)


def _province_adjacency(study: Path) -> dict[str, list[str]]:
    districts = pd.read_csv(study / "data/processed/districts.csv")
    province = dict(
        zip(districts.district_id.astype(str), districts.province_id.astype(str))
    )
    raw = json.loads(
        (study / "data/processed/district_adjacency.json").read_text(
            encoding="utf-8"
        )
    )["neighbors"]
    result: dict[str, set[str]] = {value: set() for value in province.values()}
    for district, neighbors in raw.items():
        first = province.get(str(district))
        if first is None:
            continue
        for neighbor in neighbors:
            second = province.get(str(neighbor))
            if second and second != first:
                result[first].add(second)
                result.setdefault(second, set()).add(first)
    return {key: sorted(values) for key, values in sorted(result.items())}


def _causal_history_features(frame: pd.DataFrame) -> np.ndarray:
    """Build history features without updating from holdout rows."""
    ordered = frame.sort_values(["week_index", "province_id"]).reset_index()
    histories: dict[str, list[tuple[int, float]]] = defaultdict(list)
    features = np.zeros((len(ordered), 3), dtype=float)
    for index, row in ordered.iterrows():
        province = str(row["province_id"])
        week = int(row["week_index"])
        history = histories[province]
        positive_weeks = [time for time, value in history if value > 0]
        time_since = week - max(positive_weeks) if positive_weeks else week + 13
        features[index] = [
            math.log1p(max(0, time_since)),
            math.log1p(sum(
                value for time, value in history if 0 < week - time <= 4
            )),
            math.log1p(sum(
                value for time, value in history if 0 < week - time <= 12
            )),
        ]
        if row["split"] == "training":
            histories[province].append((week, float(row["observed_active"])))
    restored = np.zeros_like(features)
    restored[ordered["index"].to_numpy(dtype=int)] = features
    return restored


def _preperiod_training_history_prediction(
    frame: pd.DataFrame,
    feature_columns: list[str],
) -> np.ndarray:
    history = _causal_history_features(frame)
    training_mask = frame["split"].eq("training").to_numpy()
    all_features = np.column_stack([
        frame[feature_columns].astype(float).to_numpy(),
        history,
    ])
    train_features = all_features[training_mask]
    mean = train_features.mean(axis=0)
    scale = train_features.std(axis=0)
    scale[scale < EPS] = 1.0
    targets = frame.loc[training_mask, "observed_active"].astype(int).to_numpy()
    if len(set(targets)) < 2:
        probability = (float(targets.sum()) + 1.0) / (len(targets) + 2.0)
        return np.full(len(frame), probability)
    model = LogisticRegression(C=1.0, max_iter=2000).fit(
        (train_features - mean) / scale,
        targets,
    )
    return model.predict_proba((all_features - mean) / scale)[:, 1]


def _shrunk_group_probability(
    frame: pd.DataFrame,
    group_column: str,
    *,
    prior_rows: float,
) -> np.ndarray:
    training = frame[frame["split"] == "training"]
    global_probability = (float(training["observed_active"].sum()) + 1.0) / (
        len(training) + 2.0
    )
    grouped = training.groupby(group_column)["observed_active"].agg(["sum", "count"])
    probabilities = {
        str(key): (float(row["sum"]) + prior_rows * global_probability)
        / (float(row["count"]) + prior_rows)
        for key, row in grouped.iterrows()
    }
    return frame[group_column].astype(str).map(probabilities).fillna(
        global_probability
    ).to_numpy(dtype=float)


def _binary_metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    probabilities = np.clip(probabilities.astype(float), EPS, 1.0 - EPS)
    return {
        "log_score": float(np.mean(
            targets * np.log(probabilities)
            + (1.0 - targets) * np.log(1.0 - probabilities)
        )),
        "brier": float(np.mean((targets - probabilities) ** 2)),
        "observed_mean": float(np.mean(targets)),
        "predicted_mean": float(np.mean(probabilities)),
    }


def score(
    *,
    forecast_path: Path,
    output_dir: Path,
    panel_path: Path = PANEL,
    case_path: Path = CASE,
    reveal_holdout: bool = False,
) -> dict:
    if not reveal_holdout:
        raise PermissionError(
            "refusing to read the 2005 target; explicitly authorize the "
            "holdout reveal before calling score()"
        )
    candidate = json.loads(forecast_path.read_text(encoding="utf-8"))
    if (
        candidate.get("holdout_outcomes_read") is not False
        or candidate.get("holdout_outcomes_used") is not False
        or candidate.get("posterior_frozen") is not True
        or candidate.get("predictive_estimand")
        != "observed_province_week_conflict_incidence"
    ):
        raise ValueError("candidate forecast is not marked holdout-clean")
    observed_field = candidate.get("posterior_observed_probability_field")
    if not observed_field:
        raise ValueError("candidate has no observed predictive probability field")

    raw = pd.read_csv(panel_path)
    years = raw["week_start"].astype(str).str[:4]
    frame = raw[years.isin({TRAINING_YEAR, HOLDOUT_YEAR})].copy()
    frame["province_id"] = frame["province_id"].astype(str)
    frame["region_id"] = frame["region_id"].astype(str)
    frame["split"] = np.where(
        frame["week_start"].astype(str).str.startswith(f"{TRAINING_YEAR}-"),
        "training",
        "holdout",
    )
    frame["observed_active"] = frame["taliban_state_active"].astype(int)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    features = _load_case_features(case)
    frame = frame.merge(
        features,
        on=["province_id", "region_id"],
        how="left",
        validate="many_to_one",
    )
    if frame[features.columns].isna().any().any():
        raise ValueError("case covariates did not cover every province")
    # ``simple_competitors`` returns rows in time/unit order. Keep the source
    # frame in that same order so custom region/history predictions align by
    # row identity rather than by the panel CSV's province-major order.
    frame = frame.sort_values(["week_index", "province_id"]).reset_index(drop=True)
    feature_columns = [
        column for column in features.columns
        if column not in {"province_id", "region_id"}
    ]
    spec = PanelSpec(
        unit_col="province_id",
        time_col="week_index",
        target_col="observed_active",
        target_type="binary",
        split_col="split",
        covariate_cols=tuple(feature_columns),
        adjacency=_province_adjacency(STUDY),
    )
    predictions, metadata = predictions_for_panel(frame, spec)
    predictions["province_empirical_bayes"] = predictions.pop("unit_empirical_bayes")
    predictions["region_empirical_bayes"] = _shrunk_group_probability(
        frame, "region_id", prior_rows=104.0
    )
    predictions["local_persistence"] = predictions["markov_persistence"]
    predictions["temporal_self_excitation"] = predictions["temporal_hawkes"]
    predictions["spatial_neighbor_self_excitation"] = predictions[
        "spatiotemporal_hawkes"
    ]
    predictions["topology_aware_diffusion"] = predictions[
        "local_neighbor_diffusion"
    ]
    predictions["preperiod_training_history_logit"] = (
        _preperiod_training_history_prediction(frame, feature_columns)
    )

    # The outcome reveal starts only after the candidate/schema and case-panel
    # checks above. Baseline fitting has no code path that updates on holdout.
    baseline_scores = score_predictions(predictions, spec)
    holdout = predictions[predictions["split"] == "holdout"]
    field = {
        (str(row["province_id"]), int(row["week_index"])): float(row["probability"])
        for row in observed_field
    }
    candidate_probabilities = np.asarray([
        field[(str(row["province_id"]), int(row["week_index"]))]
        for _, row in holdout.iterrows()
    ])
    candidate_metrics = _binary_metrics(
        holdout["observed_active"].to_numpy(dtype=float),
        candidate_probabilities,
    )
    candidate_row = {
        "split": "holdout",
        "model": "pineland_observed_forecast",
        "n": len(holdout),
        **candidate_metrics,
    }
    scores = pd.concat(
        [
            baseline_scores[baseline_scores["split"] == "holdout"],
            pd.DataFrame([candidate_row]),
        ],
        ignore_index=True,
    )
    contract = {
        "schema_version": "pineland.afghanistan.information_matched_competition.v1",
        "candidate_schema_version": candidate.get("schema_version"),
        "candidate_forecast": str(forecast_path),
        "target": "observed province-week Taliban-state-security incidence",
        "training_period": TRAINING_YEAR,
        "holdout_period": HOLDOUT_YEAR,
        "fit_scope": "2004 training rows only",
        "holdout_target_updates": False,
        "candidate_refit": False,
        "shared_information": [
            "2003 high-precision and province/background evidence",
            "2004 observed province-week history",
            "fixed 401-district adjacency",
            "source-era population and WorldPop settlement covariates",
            "province and region hierarchy",
        ],
        "unresolved_exogenous_geography": [
            "independent terrain/elevation/ruggedness data",
            "preperiod road/travel-time data",
            "independent district language composition",
            "independent preperiod facility/deployment records",
        ],
        "competitor_models": [
            "global_rate",
            "province_empirical_bayes",
            "region_empirical_bayes",
            "local_persistence",
            "temporal_self_excitation",
            "spatial_neighbor_self_excitation",
            "topology_aware_diffusion",
            "preperiod_training_history_logit",
            "static_covariate_logit",
        ],
        "covariate_columns": feature_columns,
        "candidate_probability_field": "posterior_observed_probability_field",
        "candidate_latent_field_not_scored": True,
        "reveal_guard": "--reveal-holdout is required",
        "simple_competitor_metadata": metadata,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_dir / "predictions.csv", index=False)
    scores.to_csv(output_dir / "scores.csv", index=False)
    (output_dir / "information_match_manifest.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"contract": contract, "scores": scores.to_dict(orient="records")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--case", type=Path, default=CASE)
    parser.add_argument(
        "--reveal-holdout",
        action="store_true",
        help="explicitly authorize reading/scoring 2005 outcomes",
    )
    args = parser.parse_args()
    if not args.reveal_holdout:
        parser.error(
            "refusing to read the 2005 target; pass --reveal-holdout only after "
            "the forecast artifact and architecture are frozen"
        )
    report = score(
        forecast_path=args.forecast,
        output_dir=args.output_dir,
        panel_path=args.panel,
        case_path=args.case,
        reveal_holdout=True,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
