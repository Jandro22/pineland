"""End-to-end synthetic smoke for decomposed reproduction competitors.

This runner creates one fully synthetic Pineland world, traces the observation-
only locality genealogy, materializes the full inactive-site risk set, applies a
prospective temporal cutoff, and fits the simple competitor battery on training
rows only.  It is intended to verify benchmark plumbing, not to support a
general-theory claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studies" / "research_program"))
sys.path.insert(0, str(SCRIPT_DIR))

from pineland_sim import SimulationConfig, generate_pineland  # noqa: E402
from pineland_sim.reproducibility import build_run_manifest, file_sha256, model_sha256  # noqa: E402
from trace_locality_activation_genealogy import trace_simulation  # noqa: E402
from reproduction_competitors import (  # noqa: E402
    GenealogyRun,
    build_reproduction_tables,
    decomposition_summary,
    episode_binary_competitors,
    score_episode_binary,
)
from simple_competitors import PanelSpec, predictions_for_panel, score_predictions  # noqa: E402


def _temporal_split_tables(tables: dict[str, pd.DataFrame], cutoff_day: float,
                           *, deepening_horizon: float,
                           survival_horizon: float) -> dict[str, pd.DataFrame]:
    site = tables["site_period"].copy()
    site["split"] = site.period_end_day.map(
        lambda value: "training" if float(value) <= cutoff_day else "temporal_validation"
    )
    aggregate = tables["aggregate_period"].copy()
    aggregate["split"] = aggregate.period_end_day.map(
        lambda value: "training" if float(value) <= cutoff_day else "temporal_validation"
    )
    episode = tables["foothold_episode"].copy()
    # Base split is conservative; target-specific scoring below refines it by
    # the actual follow-up horizon so outcomes completed after cutoff never fit.
    episode["split"] = "temporal_validation"
    episode.loc[episode.activation_day <= cutoff_day, "split"] = "training_candidate"
    return {"site_period": site, "aggregate_period": aggregate, "foothold_episode": episode}


def _score_site_targets(site: pd.DataFrame, adjacency: dict[str, list[str]], out: Path) -> list[pd.DataFrame]:
    risk = site[site.at_risk_for_new_foothold == 1].copy()
    score_frames: list[pd.DataFrame] = []
    for target in (
        "new_foothold_site",
        "local_spontaneous_ignition",
        "parent_attributed_colonization",
    ):
        spec = PanelSpec(
            unit_col="locality_id", time_col="period_index", target_col=target,
            target_type="binary", split_col="split", adjacency=adjacency,
            covariate_cols=("active_site_count_start", "active_neighbor_share_start"),
        )
        predictions, _ = predictions_for_panel(risk, spec)
        predictions.to_csv(out / f"{target}_predictions.csv", index=False)
        scores = score_predictions(predictions, spec)
        scores.insert(0, "target", target)
        score_frames.append(scores)
    return score_frames


def _score_aggregate_targets(aggregate: pd.DataFrame, out: Path) -> list[pd.DataFrame]:
    score_frames: list[pd.DataFrame] = []
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
        predictions.to_csv(out / f"aggregate_{target}_predictions.csv", index=False)
        scores = score_predictions(predictions, spec)
        scores.insert(0, "target", f"aggregate_{target}")
        score_frames.append(scores)
    return score_frames


def _score_episode_target(episode: pd.DataFrame, target: str, cutoff_day: float,
                          horizon: float, out: Path) -> pd.DataFrame | None:
    frame = episode.copy()
    frame["split"] = frame.activation_day.map(
        lambda start: "training"
        if float(start) + horizon <= cutoff_day + 1e-12
        else "temporal_validation"
    )
    observed = frame.dropna(subset=[target])
    if observed.empty or not (observed.split == "training").any():
        return None
    predictions = episode_binary_competitors(frame, target)
    predictions.to_csv(out / f"{target}_predictions.csv", index=False)
    return score_episode_binary(predictions, target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2026090617)
    parser.add_argument("--agents", type=int, default=500)
    parser.add_argument("--localities", type=int, default=28)
    parser.add_argument("--days", type=float, default=56.0)
    parser.add_argument("--cutoff-day", type=float, default=28.0)
    parser.add_argument("--bin-days", type=float, default=7.0)
    parser.add_argument("--deepening-horizon-days", type=float, default=14.0)
    parser.add_argument("--survival-horizon-days", type=float, default=14.0)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "studies" / "research_program" / "benchmarks" / "synthetic_reproduction_smoke",
    )
    args = parser.parse_args()
    if not 0 < args.cutoff_day < args.days:
        raise ValueError("cutoff-day must be strictly inside the run horizon")

    config = SimulationConfig(
        agent_count=args.agents,
        locality_count=args.localities,
        horizon_days=args.days,
        seed=args.seed,
        output_mode="ensemble",
    )
    source_hash_start = model_sha256(ROOT)
    # Generate once only to establish the complete locality universe and
    # topology. trace_simulation deterministically regenerates the same world.
    reference_world = generate_pineland(config)
    locality_ids = tuple(sorted(reference_world.localities))
    adjacency = {
        locality: sorted(str(value) for value in reference_world.adjacency.get(locality, {}))
        for locality in locality_ids
    }
    genealogy = trace_simulation(config, until=args.days)
    if model_sha256(ROOT) != source_hash_start:
        raise RuntimeError("model source changed during synthetic competitor smoke")
    run = GenealogyRun(str(args.seed), "training", genealogy, locality_ids)
    tables = build_reproduction_tables(
        [run],
        bin_days=args.bin_days,
        deepening_horizon_days=args.deepening_horizon_days,
        survival_horizon_days=args.survival_horizon_days,
        adjacency=adjacency,
    )
    tables = _temporal_split_tables(
        tables, args.cutoff_day,
        deepening_horizon=args.deepening_horizon_days,
        survival_horizon=args.survival_horizon_days,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(args.output_dir / f"{name}.csv", index=False)

    score_frames = []
    score_frames.extend(_score_site_targets(tables["site_period"], adjacency, args.output_dir))
    score_frames.extend(_score_aggregate_targets(tables["aggregate_period"], args.output_dir))
    for target, horizon in (
        ("deepened_to_saturated_access", args.deepening_horizon_days),
        ("deepened_to_fielded_force", args.deepening_horizon_days),
        ("survived_horizon", args.survival_horizon_days),
    ):
        scores = _score_episode_target(
            tables["foothold_episode"], target, args.cutoff_day, horizon, args.output_dir
        )
        if scores is not None:
            score_frames.append(scores)
    scores = pd.concat(score_frames, ignore_index=True)
    scores.to_csv(args.output_dir / "scores.csv", index=False)

    summary = decomposition_summary(tables)
    report = {
        "schema_version": "pineland.synthetic_reproduction_competitor_smoke.v1",
        "historical_outcomes_used": False,
        "empirical_parameter_fitting": False,
        "core_dynamics_modified": False,
        "seed": args.seed,
        "agents": args.agents,
        "localities": len(locality_ids),
        "days": args.days,
        "cutoff_day": args.cutoff_day,
        "fit_scope": "pre_cutoff_training_only",
        "holdout_target_updates": False,
        "summary": summary,
        "targets_scored": sorted(scores.target.unique().tolist()),
        "models_scored": sorted(scores.model.unique().tolist()),
        "model_sha256_start": source_hash_start,
        "model_sha256_end": model_sha256(ROOT),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = build_run_manifest(
        config,
        seeds=[args.seed],
        execution_mode="synthetic_reproduction_competitor_smoke",
        output_schema={"name":"synthetic_reproduction_competitor_smoke","version":"1.0.0"},
        repo_root=ROOT,
        extra={
            "historical_outcomes_used": False,
            "holdout_target_updates": False,
            "runner_sha256": file_sha256(Path(__file__)),
            "scores_sha256": file_sha256(args.output_dir / "scores.csv"),
        },
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
