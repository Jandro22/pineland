"""Run the reusable simple-model benchmark suite on a frozen panel CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "studies" / "research_program"))
sys.path.insert(0, str(ROOT / "src"))

from simple_competitors import PanelSpec, competitor_registry, predictions_for_panel, score_predictions  # noqa: E402
from pineland_sim.reproducibility import build_run_manifest, file_sha256  # noqa: E402


def load_adjacency(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "neighbors" in raw:
        raw = raw["neighbors"]
    if not isinstance(raw, dict):
        raise ValueError("adjacency JSON must be a mapping or contain a neighbors mapping")
    return {str(key): [str(value) for value in values] for key, values in raw.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--unit-col", required=True)
    parser.add_argument("--time-col", required=True)
    parser.add_argument("--target-col", required=True)
    parser.add_argument("--target-type", choices=("binary", "count", "continuous"), required=True)
    parser.add_argument("--split-col", default="split")
    parser.add_argument("--exposure-col")
    parser.add_argument("--force-ratio-col")
    parser.add_argument("--covariate-col", action="append", default=[])
    parser.add_argument("--adjacency", type=Path)
    parser.add_argument("--prior-rows", type=float, default=8.0)
    parser.add_argument("--split-file", type=Path)
    args = parser.parse_args()

    frame = pd.read_csv(args.panel)
    spec = PanelSpec(
        unit_col=args.unit_col,
        time_col=args.time_col,
        target_col=args.target_col,
        target_type=args.target_type,
        split_col=args.split_col,
        exposure_col=args.exposure_col,
        covariate_cols=tuple(args.covariate_col),
        force_ratio_col=args.force_ratio_col,
        prior_rows=args.prior_rows,
        adjacency=load_adjacency(args.adjacency),
    )
    predictions, metadata = predictions_for_panel(frame, spec)
    scores = score_predictions(predictions, spec)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = args.output_dir / "predictions.csv"
    score_path = args.output_dir / "scores.csv"
    registry_path = args.output_dir / "competitor_registry.json"
    predictions.to_csv(prediction_path, index=False)
    scores.to_csv(score_path, index=False)
    registry_path.write_text(json.dumps(competitor_registry(), indent=2) + "\n", encoding="utf-8")
    case_files = [args.panel]
    if args.adjacency:
        case_files.append(args.adjacency)
    specification = {
        **metadata,
        "target_type": args.target_type,
        "holdout_refit": False,
        "holdout_target_updates": False,
        "runner": str(Path(__file__).relative_to(ROOT)),
    }
    manifest = build_run_manifest(
        specification,
        execution_mode="deterministic_training_only_simple_competitors",
        output_schema={"name": "simple_competitor_scores", "version": "1.0.0"},
        case_files=case_files,
        split_file=args.split_file,
        repo_root=ROOT,
        extra={
            "runner_sha256": file_sha256(Path(__file__)),
            "library_sha256": file_sha256(ROOT / "studies" / "research_program" / "simple_competitors.py"),
            "predictions_sha256": file_sha256(prediction_path),
            "scores_sha256": file_sha256(score_path),
        },
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(scores.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
