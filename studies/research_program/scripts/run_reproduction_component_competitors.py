"""Run simple challengers against each decomposed reproduction component table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "studies" / "research_program"))
sys.path.insert(0, str(ROOT / "src"))

from simple_competitors import PanelSpec, predictions_for_panel, score_predictions  # noqa: E402
from reproduction_competitors import episode_binary_competitors, score_episode_binary  # noqa: E402
from pineland_sim.reproducibility import build_run_manifest, file_sha256  # noqa: E402


def load_adjacency(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "neighbors" in raw:
        raw = raw["neighbors"]
    return {str(key): [str(value) for value in values] for key, values in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--adjacency", type=Path)
    args = parser.parse_args()

    site = pd.read_csv(args.tables_dir / "site_period.csv")
    episode = pd.read_csv(args.tables_dir / "foothold_episode.csv")
    aggregate = pd.read_csv(args.tables_dir / "aggregate_period.csv")
    adjacency = load_adjacency(args.adjacency)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    score_frames = []

    # New-site risk sets. Local ignition and attributed colonization are scored
    # separately, while any-new-site occupancy is a useful umbrella target.
    risk = site[site.at_risk_for_new_foothold == 1].copy()
    for target in (
        "new_foothold_site",
        "local_spontaneous_ignition",
        "parent_attributed_colonization",
    ):
        spec = PanelSpec(
            unit_col="locality_id", time_col="period_index", target_col=target,
            target_type="binary", split_col="split", adjacency=adjacency,
            covariate_cols=("active_site_count_start",),
        )
        predictions, _ = predictions_for_panel(risk, spec)
        predictions.to_csv(args.output_dir / f"{target}_predictions.csv", index=False)
        scores = score_predictions(predictions, spec)
        scores.insert(0, "target", target)
        score_frames.append(scores)

    # Aggregate births are where branching + immigration is a direct simple
    # competitor. Treat each independent run as a unit/time series.
    for target in (
        "new_foothold_sites",
        "local_spontaneous_ignitions",
        "parent_attributed_colonizations",
    ):
        spec = PanelSpec(
            unit_col="run_id", time_col="period_index", target_col=target,
            target_type="count", split_col="split",
            covariate_cols=("active_sites_start", "at_risk_sites"),
        )
        predictions, _ = predictions_for_panel(aggregate, spec)
        predictions.to_csv(args.output_dir / f"aggregate_{target}_predictions.csv", index=False)
        scores = score_predictions(predictions, spec)
        scores.insert(0, "target", f"aggregate_{target}")
        score_frames.append(scores)

    for target in (
        "deepened_to_saturated_access",
        "deepened_to_fielded_force",
        "survived_horizon",
    ):
        predictions = episode_binary_competitors(episode, target)
        predictions.to_csv(args.output_dir / f"{target}_predictions.csv", index=False)
        score_frames.append(score_episode_binary(predictions, target))

    scores = pd.concat(score_frames, ignore_index=True)
    scores.to_csv(args.output_dir / "scores.csv", index=False)
    inputs = [
        args.tables_dir / "site_period.csv",
        args.tables_dir / "foothold_episode.csv",
        args.tables_dir / "aggregate_period.csv",
    ]
    if args.adjacency:
        inputs.append(args.adjacency)
    specification = {
        "status": "decomposed_reproduction_simple_competitors",
        "fit_scope": "training_only",
        "holdout_refit": False,
        "holdout_target_updates": False,
        "relocation_target": False,
        "unresolved_parentage_imputed": False,
        "targets": sorted(scores.target.unique().tolist()),
        "models": sorted(scores.model.unique().tolist()),
    }
    manifest = build_run_manifest(
        specification,
        execution_mode="deterministic_decomposed_reproduction_competitors",
        output_schema={"name":"reproduction_component_competitors","version":"1.0.0"},
        case_files=inputs,
        repo_root=ROOT,
        extra={
            "runner_sha256": file_sha256(Path(__file__)),
            "scores_sha256": file_sha256(args.output_dir / "scores.csv"),
        },
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(scores.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
