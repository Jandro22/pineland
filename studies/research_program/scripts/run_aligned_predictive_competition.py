"""Score frozen Pineland ensembles and simple competitors on identical rows.

This is post-processing only: no simulator parameter is fitted and holdout
outcomes never update competitor state.  Candidate probabilities are empirical
ensemble frequencies on the exact historical panel cells.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "studies" / "research_program"))
sys.path.insert(0, str(ROOT / "src"))

from simple_competitors import PanelSpec, predictions_for_panel, score_predictions  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def frozen_core(execution_contract: Path | None = None) -> tuple[str, str]:
    freeze_path = ROOT / "studies/research_program/core_freeze.json"
    freeze = json.loads(freeze_path.read_text())
    if execution_contract is not None:
        contract = json.loads(execution_contract.read_text())
        if contract.get("core_freeze_path"):
            freeze_path = (ROOT / contract["core_freeze_path"]).resolve()
            freeze = json.loads(freeze_path.read_text())
        from pineland_sim.reproducibility import require_certified_core
        require_certified_core(ROOT, freeze_path=freeze_path)
        identity = freeze.get("software_identity", freeze)
        if contract["model_sha256"] != identity["model_sha256"]:
            raise ValueError("execution contract does not match frozen core")
        if contract.get("core_freeze_sha256") and sha256(freeze_path) != contract["core_freeze_sha256"]:
            raise ValueError("execution contract does not match current core freeze")
        if contract.get("certificate_payload_sha256") and contract["certificate_payload_sha256"] != freeze.get("certificate_payload_sha256"):
            raise ValueError("execution contract does not match legacy certificate")
        if not contract.get("input_sha256"):
            raise ValueError("execution contract must pin study inputs")
        for name, expected in contract["input_sha256"].items():
            if sha256(ROOT / name) != expected:
                raise ValueError(f"execution input drift: {name}")
        return contract["model_sha256"], contract["tracked_diff_sha256"]
    identity = freeze.get("software_identity", freeze)
    return identity["model_sha256"], identity["tracked_diff_sha256"]


def validate_member(path: Path, model_hash: str, diff_hash: str) -> dict:
    row = json.loads(path.read_text(encoding="utf-8"))
    if row.get("model_sha256_start") != model_hash or row.get("model_sha256_end") != model_hash:
        raise ValueError(f"{path.name} is not bound to frozen model {model_hash}")
    if row.get("tracked_diff_sha256") != diff_hash:
        raise ValueError(f"{path.name} is not bound to frozen tracked diff {diff_hash}")
    if row.get("model_stable_during_run") is False:
        raise ValueError(f"{path.name} reports model drift during run")
    return row


def province_adjacency(study: Path) -> dict[str, list[str]]:
    districts = pd.read_csv(study / "data/processed/districts.csv")
    province = dict(zip(districts.district_id.astype(str), districts.province_id.astype(str)))
    raw = json.loads((study / "data/processed/district_adjacency.json").read_text())["neighbors"]
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


def nepal_inputs(run_dir: Path, model_hash: str, diff_hash: str):
    study = ROOT / "studies/nepal_2001_2006"
    panel = pd.read_csv(study / "data/processed/district_week_panel.csv")
    start = pd.Timestamp("2001-11-26")
    panel["simulation_week_index"] = ((pd.to_datetime(panel.week_start) - start).dt.days // 7).astype(int)
    panel["observed_active"] = (panel.government_maoist_state_based_events > 0).astype(int)
    files = sorted(run_dir.glob("seed_*_agents_750.json"))
    recorded_sets, latent_sets = [], []
    for path in files:
        run = validate_member(path, model_hash, diff_hash)
        recorded_sets.append({
            (str(event["district_id"]), int(float(event["day"]) // 7))
            for event in run.get("contacts", []) if event.get("realized") and event.get("recorded")
        })
        latent_sets.append({
            (str(event["district_id"]), int(float(event["day"]) // 7))
            for event in run.get("contacts", []) if event.get("realized")
        })
    adjacency = json.loads((study / "data/processed/district_adjacency.json").read_text())["neighbors"]
    return panel, files, recorded_sets, latent_sets, adjacency, "district_id", "week_start", "simulation_week_index"


def afghanistan_inputs(run_dir: Path, model_hash: str, diff_hash: str):
    study = ROOT / "studies/afghanistan_2004_2021"
    panel = pd.read_csv(study / "data/processed/province_week_panel.csv")
    panel["province_id"] = panel.province_id.astype(str)
    panel["observed_active"] = panel.taliban_state_active.astype(int)
    files = sorted(path for path in run_dir.glob("seed_*_taliban_*.json"))
    recorded_sets, latent_sets = [], []
    for path in files:
        run = validate_member(path, model_hash, diff_hash)
        violence = run.get("violence_validation") or {}
        recorded_sets.append({
            (str(row["province_id"]), int(row["week_index"]))
            for row in violence.get("recorded_active_cells", [])
        })
        latent_sets.append({
            (str(row["province_id"]), int(row["week_index"]))
            for row in violence.get("latent_active_cells", [])
        })
    return panel, files, recorded_sets, latent_sets, province_adjacency(study), "province_id", "week_index", "week_index"


def ensemble_probability(panel: pd.DataFrame, unit_col: str, cell_time_col: str,
                         members: list[set[tuple[str, int]]]) -> list[float]:
    if not members:
        return [0.0] * len(panel)
    denominator = float(len(members))
    return [
        sum((str(unit), int(time)) in member for member in members) / denominator
        for unit, time in zip(panel[unit_col], panel[cell_time_col])
    ]


def decision(scores: pd.DataFrame, *, complete: bool, member_count: int,
             expected_members: int, final_stage: bool) -> dict:
    holdout = scores[scores.split != "training"]
    comparisons = []
    all_wins = True
    for split, subset in holdout.groupby("split", sort=True):
        candidate = subset[subset.model == "pineland_recorded_ensemble"]
        simple = subset[~subset.model.str.startswith("pineland_")]
        if candidate.empty or simple.empty:
            all_wins = False
            continue
        best = simple.sort_values(["log_score", "brier"], ascending=[False, True]).iloc[0]
        cand = candidate.iloc[0]
        win = bool(cand.log_score > best.log_score and cand.brier < best.brier)
        all_wins &= win
        comparisons.append({
            "split": split,
            "best_simple_model": best.model,
            "pineland_log_score": float(cand.log_score),
            "best_simple_log_score": float(best.log_score),
            "pineland_brier": float(cand.brier),
            "best_simple_brier": float(best.brier),
            "pineland_strictly_better_on_both": win,
        })
    licensed = bool(complete and final_stage)
    if not complete:
        verdict = "provisional_incomplete_ensemble"
    elif not final_stage:
        verdict = "diagnostic_nonfinal_horizon"
    elif all_wins and comparisons:
        verdict = "pineland_beats_implemented_simple_models_on_all_holdouts"
    else:
        verdict = "simple_models_not_beaten_on_all_holdouts"
    return {
        "member_count": member_count,
        "expected_members": expected_members,
        "ensemble_complete": complete,
        "final_historical_stage": final_stage,
        "scientific_verdict_licensed": licensed,
        "verdict": verdict,
        "holdout_comparisons": comparisons,
        "coin_science_authorized": False,
        "coin_authorization_rule": "Requires at least two independent transfer cases to pass the predictive gate; a single aligned case can never authorize COIN science.",
    }


def attach_candidate_predictions(predictions: pd.DataFrame, panel: pd.DataFrame,
                                 unit_col: str, time_col: str) -> pd.DataFrame:
    """Align by cell identity; competitor preparation may reorder the panel."""
    keys = [unit_col, time_col]
    columns = [column for column in panel if column.startswith("pineland_")]
    result = predictions.merge(panel[keys + columns], on=keys, how="left",
                               validate="one_to_one", indicator=True, sort=False)
    if len(result) != len(panel) or not result["_merge"].eq("both").all():
        raise ValueError("candidate and competitor cell identities do not match")
    return result.drop(columns="_merge")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("nepal", "afghanistan"), required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-members", type=int, required=True)
    parser.add_argument("--final-stage", action="store_true")
    parser.add_argument("--execution-contract", type=Path)
    args = parser.parse_args()
    model_hash, diff_hash = frozen_core(args.execution_contract)
    loader = nepal_inputs if args.case == "nepal" else afghanistan_inputs
    panel, files, recorded, latent, adjacency, unit_col, time_col, cell_time_col = loader(
        args.run_dir.resolve(), model_hash, diff_hash
    )
    if len(files) > args.expected_members:
        raise ValueError("more ensemble members found than expected")
    panel["pineland_recorded_ensemble"] = ensemble_probability(panel, unit_col, cell_time_col, recorded)
    panel["pineland_latent_ensemble"] = ensemble_probability(panel, unit_col, cell_time_col, latent)
    spec = PanelSpec(
        unit_col=unit_col,
        time_col=time_col,
        target_col="observed_active",
        target_type="binary",
        split_col="split",
        adjacency=adjacency,
    )
    predictions, metadata = predictions_for_panel(panel, spec)
    predictions = attach_candidate_predictions(predictions, panel, unit_col, time_col)
    scores = score_predictions(predictions, spec)
    report = decision(
        scores,
        complete=len(files) == args.expected_members,
        member_count=len(files),
        expected_members=args.expected_members,
        final_stage=args.final_stage,
    )
    report.update({
        "schema_version": "pineland.aligned_predictive_competition.v1",
        "case": args.case,
        "frozen_model_sha256": model_hash,
        "frozen_tracked_diff_sha256": diff_hash,
        "fit_scope": "training_only_for_simple_models",
        "holdout_refit": False,
        "holdout_target_updates": False,
        "candidate_parameter_fit": False,
        "candidate_probability_definition": "fraction_of_frozen_ensemble_members_with_active_cell",
        "rows": len(panel),
        "models": sorted(scores.model.unique().tolist()),
    })
    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_dir / "aligned_predictions.csv", index=False)
    scores.to_csv(args.output_dir / "scores.csv", index=False)
    (args.output_dir / "decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema_version": "pineland.aligned_predictive_competition_manifest.v1",
        "case": args.case,
        "model_sha256": model_hash,
        "tracked_diff_sha256": diff_hash,
        "ensemble_files": {path.name: sha256(path) for path in files},
        "aligned_predictions_sha256": sha256(args.output_dir / "aligned_predictions.csv"),
        "scores_sha256": sha256(args.output_dir / "scores.csv"),
        "decision_sha256": sha256(args.output_dir / "decision.json"),
        "metadata": metadata,
        "execution_contract_sha256": sha256(args.execution_contract) if args.execution_contract else None,
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
