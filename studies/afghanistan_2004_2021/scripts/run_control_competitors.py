"""Fit control competitors on pre-target training observations only.

The October 2017 SIGAR snapshot is never accepted as training input.  This
runner therefore fails closed until a longitudinal pre-target control panel is
provided with explicit training/holdout labels.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import csv
from datetime import date
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]


def period_key(value: str) -> tuple[int, int, int]:
    """Parse canonical historical periods into a chronologically sortable key."""
    text = str(value).strip()
    match = re.fullmatch(r"(\d{4})Q([1-4])", text, flags=re.IGNORECASE)
    if match:
        year, quarter = int(match.group(1)), int(match.group(2))
        return year, 1 + (quarter - 1) * 3, 1
    if re.fullmatch(r"\d{4}", text):
        return int(text), 1, 1
    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = map(int, text.split("-"))
        date(year, month, 1)  # validate range
        return year, month, 1
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            "period must be YYYY, YYYY-MM, YYYY-MM-DD, or YYYYQ[1-4]"
        ) from exc
    return parsed.year, parsed.month, parsed.day


def fit_predict(rows: list[dict], *, prior_rows: float = 4.0) -> list[dict]:
    required = {"district_id", "province_id", "period", "split", "control_index"}
    if any(required - set(row) for row in rows):
        raise ValueError(f"control panel requires {sorted(required)}")
    training = [row for row in rows if row["split"] == "training"]
    if not training:
        raise ValueError("at least one explicitly labeled training observation is required")
    holdout = [row for row in rows if row["split"] != "training"]
    if not holdout:
        raise ValueError("at least one non-training observation is required")
    training_periods = {row["period"] for row in training}
    if any(row["split"] != "training" and row["period"] in training_periods for row in rows):
        raise ValueError("training and holdout rows cannot share a period")
    latest_training = max(period_key(row["period"]) for row in training)
    earliest_holdout = min(period_key(row["period"]) for row in holdout)
    if latest_training >= earliest_holdout:
        raise ValueError(
            "all training control periods must precede every holdout period; future control cannot predict the past"
        )
    global_mean = sum(float(row["control_index"]) for row in training) / len(training)
    groups: dict[str, dict[str, list[float]]] = {
        "province": defaultdict(list), "district": defaultdict(list)
    }
    for row in training:
        groups["province"][row["province_id"]].append(float(row["control_index"]))
        groups["district"][row["district_id"]].append(float(row["control_index"]))

    def shrunk(group: str, key: str) -> float:
        values = groups[group].get(key, [])
        return (sum(values) + prior_rows * global_mean) / (len(values) + prior_rows)

    latest: dict[str, tuple[str, float]] = {}
    for row in sorted(training, key=lambda item: item["period"]):
        latest[row["district_id"]] = (row["period"], float(row["control_index"]))
    predictions = []
    for row in rows:
        if row["split"] == "training":
            continue
        district = row["district_id"]
        predictions.append({
            **row,
            "global_training_mean": global_mean,
            "province_empirical_bayes": shrunk("province", row["province_id"]),
            "district_empirical_bayes": shrunk("district", district),
            "last_training_control": latest.get(district, ("", shrunk("province", row["province_id"])))[1],
        })
    return predictions


def score(predictions: list[dict]) -> list[dict]:
    models = ("global_training_mean", "province_empirical_bayes",
              "district_empirical_bayes", "last_training_control")
    result = []

    def correlation(first: list[float], second: list[float]) -> float | None:
        if len(first) < 2:
            return None
        first_mean = sum(first) / len(first)
        second_mean = sum(second) / len(second)
        numerator = sum(
            (a - first_mean) * (b - second_mean) for a, b in zip(first, second)
        )
        denominator = math.sqrt(
            sum((a - first_mean) ** 2 for a in first) *
            sum((b - second_mean) ** 2 for b in second)
        )
        return numerator / denominator if denominator else None

    for split in sorted({row["split"] for row in predictions}):
        subset = [row for row in predictions if row["split"] == split]
        observed = [float(row["control_index"]) for row in subset]
        for model in models:
            predicted = [float(row[model]) for row in subset]
            errors = [p - o for p, o in zip(predicted, observed)]
            result.append({
                "split": split, "model": model, "fit_scope": "training_only",
                "n": len(errors),
                "mae": sum(abs(error) for error in errors) / len(errors),
                "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
                "pearson": correlation(observed, predicted),
            })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    with args.panel.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    predictions = fit_predict(rows)
    scores = score(predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, records in (("predictions.csv", predictions), ("scores.csv", scores)):
        path = args.output_dir / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    manifest = {
        "schema_version": "1.0.0", "status": "completed_training_only_control_competitors",
        "panel": str(args.panel), "training_rows": sum(row["split"] == "training" for row in rows),
        "holdout_rows": len(predictions), "models": [row["model"] for row in scores],
        "october_2017_target_used_for_fit": False,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
