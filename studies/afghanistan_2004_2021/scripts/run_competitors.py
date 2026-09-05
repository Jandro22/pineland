"""Fit leakage-controlled binary competitors on Afghanistan training rows only."""
from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "afghanistan_2004_2021"
PANEL = STUDY / "data" / "processed" / "province_week_panel.csv"
DESIGN = STUDY / "config" / "study_design.json"
OUT = STUDY / "results" / "competitors"
SPLITS = ("training", "geographic_validation", "temporal_validation", "strict_joint_holdout")


def _score(rows: list[dict], probabilities: list[float]) -> dict:
    y = [int(row["taliban_state_active"]) for row in rows]
    p = [min(1 - 1e-9, max(1e-9, value)) for value in probabilities]
    return {
        "n": len(y),
        "observed_rate": sum(y) / max(1, len(y)),
        "predicted_rate": sum(p) / max(1, len(p)),
        "log_score": sum(
            actual * math.log(predicted) + (1 - actual) * math.log(1 - predicted)
            for actual, predicted in zip(y, p)
        ) / max(1, len(y)),
        "brier": sum((actual - predicted) ** 2 for actual, predicted in zip(y, p)) / max(1, len(y)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with PANEL.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows.sort(key=lambda row: (int(row["week_index"]), row["province_id"]))
    training = [row for row in rows if row["split"] == "training"]
    positives = sum(int(row["taliban_state_active"]) for row in training)
    global_p = (positives + 1) / (len(training) + 2)

    def grouped_probability(field: str, prior_rows: float) -> dict[str, float]:
        counts = defaultdict(lambda: [0, 0])
        for row in training:
            counts[row[field]][0] += int(row["taliban_state_active"])
            counts[row[field]][1] += 1
        return {
            key: (positive + prior_rows * global_p) / (total + prior_rows)
            for key, (positive, total) in counts.items()
        }

    province_p = grouped_probability("province_id", 52.0)
    region_p = grouped_probability("region_id", 104.0)
    history: dict[str, list[int]] = defaultdict(list)
    predictions = {name: {} for name in (
        "global_rate", "province_empirical_bayes", "region_empirical_bayes",
        "training_history_self_exciting",
    )}
    alpha, decay = 0.18, 0.20
    for row in rows:
        key = (row["province_id"], int(row["week_index"]))
        base = province_p.get(row["province_id"], global_p)
        excitation = sum(
            math.exp(-decay * (key[1] - prior_week))
            for prior_week in history[row["province_id"]]
            if prior_week < key[1]
        )
        predictions["global_rate"][key] = global_p
        predictions["province_empirical_bayes"][key] = base
        predictions["region_empirical_bayes"][key] = region_p.get(row["region_id"], global_p)
        predictions["training_history_self_exciting"][key] = 1 - math.exp(
            -(-math.log(1 - base) + alpha * excitation)
        )
        # Holdout outcomes never enter prediction history, including earlier
        # weeks from a held-out geography or the temporal validation period.
        if row["split"] == "training" and int(row["taliban_state_active"]):
            history[row["province_id"]].append(key[1])

    scored = []
    for split in SPLITS:
        subset = [row for row in rows if row["split"] == split]
        keys = [(row["province_id"], int(row["week_index"])) for row in subset]
        for model, values in predictions.items():
            scored.append({
                "split": split,
                "model": model,
                "fit_scope": "training_only",
                **_score(subset, [values[key] for key in keys]),
            })
    csv_path = OUT / "competitor_scores.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scored[0]))
        writer.writeheader()
        writer.writerows(scored)

    from pineland_sim.reproducibility import build_run_manifest, file_sha256
    specification = {
        "target": "province-week Taliban-government state-based event incidence",
        "training_only": True,
        "holdout_refit": False,
        "models": list(predictions),
        "province_prior_rows": 52,
        "region_prior_rows": 104,
        "self_excitation_alpha": alpha,
        "self_excitation_decay_per_week": decay,
        "self_excitation_history_updates": "training rows only",
    }
    manifest = build_run_manifest(
        specification,
        execution_mode="deterministic_training_only_competitors",
        output_schema={"name": "afghanistan_competitor_scores", "version": "1.0.0"},
        case_files=[PANEL, DESIGN],
        split_file=DESIGN,
        repo_root=ROOT,
        extra={"runner_sha256": file_sha256(Path(__file__)), "scores_sha256": file_sha256(csv_path)},
    )
    manifest.update(specification)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rows": len(scored), "output": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
