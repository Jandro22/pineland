"""Assemble the provenance-bound once-only v5 historical confrontation record.

Read-only with respect to model/case inputs and simulation outputs. It refuses
partial ensembles and validates hashes before writing the final gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"
OUT = PROGRAM / "historical_revalidation_v5"
EXECUTION = OUT / "execution_contract.json"
STATUS = OUT / "status.json"
NEPAL_RUNS = ROOT / "studies/nepal_2001_2006/runs/post_structural_repair/final_empirical_rescore_v5"
AFGHAN_RUNS = ROOT / "studies/afghanistan_2004_2021/runs/transfer_test_v5/full"

sys.path.insert(0, str(PROGRAM / "scripts"))
from run_aligned_predictive_competition import frozen_core, sha256, validate_member  # noqa: E402


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_artifact_set(directory: Path) -> tuple[dict, dict]:
    manifest = load(directory / "manifest.json")
    for stem, suffix in (
        ("aligned_predictions", "csv"),
        ("scores", "csv"),
        ("decision", "json"),
    ):
        path = directory / f"{stem}.{suffix}"
        if sha256(path) != manifest[f"{stem}_sha256"]:
            raise ValueError(f"artifact hash drift: {path}")
    return manifest, load(directory / "decision.json")


def verify_execution_inputs(contract: dict) -> dict:
    mismatches = []
    for relative, expected in contract["input_sha256"].items():
        path = ROOT / relative
        if not path.is_file():
            mismatches.append({"path": relative, "reason": "missing"})
        else:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                mismatches.append({
                    "path": relative,
                    "reason": "hash_mismatch",
                    "expected": expected,
                    "actual": actual,
                })
    return {"checked": len(contract["input_sha256"]), "mismatches": mismatches}


def verify_members(
    paths: list[Path],
    model_hash: str,
    diff_hash: str,
    *,
    expected_ids: list[int],
    id_field: str,
) -> list[dict]:
    rows = []
    identities = []
    for path in paths:
        run = validate_member(path, model_hash, diff_hash)
        identity = int(run[id_field])
        identities.append(identity)
        rows.append({
            "file": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            id_field: identity,
            "model_stable_during_run": run.get("model_stable_during_run", True),
        })
    if identities != expected_ids:
        raise ValueError(f"{id_field} identities {identities} != expected {expected_ids}")
    return rows


def main() -> int:
    contract = load(EXECUTION)
    state = load(STATUS)
    required_stages = contract["stages"]
    if state.get("status") != "completed":
        raise ValueError(f"historical confrontation is not complete: {state}")
    if state.get("completed_stages") != required_stages:
        raise ValueError(
            f"completed stages differ from contract: {state.get('completed_stages')}"
        )

    model_hash, diff_hash = frozen_core(EXECUTION)
    execution_inputs = verify_execution_inputs(contract)
    if execution_inputs["mismatches"]:
        raise ValueError(f"frozen execution input drift: {execution_inputs['mismatches']}")

    nepal_files = sorted(NEPAL_RUNS.glob("seed_*_agents_750.json"))
    if len(nepal_files) != 8:
        raise ValueError("exactly eight Nepal v5 members required")
    nepal_members = verify_members(
        nepal_files,
        model_hash,
        diff_hash,
        expected_ids=contract["nepal_seeds"],
        id_field="seed",
    )
    for path in nepal_files:
        run = load(path)
        if run.get("case_sha256") != contract["input_sha256"][
            "studies/nepal_2001_2006/config/case_environment_repaired.json"
        ]:
            raise ValueError(f"Nepal case hash mismatch in {path.name}")
        if run.get("split_sha256") != contract["input_sha256"][
            "studies/nepal_2001_2006/config/split_manifest.json"
        ]:
            raise ValueError(f"Nepal split hash mismatch in {path.name}")

    afghan_files = sorted(
        AFGHAN_RUNS.glob("seed_*_taliban_*.json"),
        key=lambda path: int(path.stem.rsplit("_", 1)[1]),
    )
    if len(afghan_files) != 3:
        raise ValueError("exactly three Afghanistan v5 strength conditions required")
    afghan_members = verify_members(
        afghan_files,
        model_hash,
        diff_hash,
        expected_ids=contract["afghanistan_full_strengths"],
        id_field="taliban_initial_strength",
    )
    afghan_case_hash_paths = {
        "case_environment": "studies/afghanistan_2004_2021/config/case_environment.json",
        "historical_case_inputs": "studies/afghanistan_2004_2021/config/historical_case_inputs.json",
        "control_401": "studies/afghanistan_2004_2021/data/processed/sigar_oct2017_control_401.csv",
        "province_week_panel": "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv",
        "study_design": "studies/afghanistan_2004_2021/config/study_design.json",
        "control_observation_model": "studies/afghanistan_2004_2021/config/control_observation_model.json",
        "control_validation_plan": "studies/afghanistan_2004_2021/config/control_validation_plan.json",
        "runner": "studies/afghanistan_2004_2021/scripts/run_transfer_test.py",
    }
    expected_afghan_case_hashes = {
        name: contract["input_sha256"][relative]
        for name, relative in afghan_case_hash_paths.items()
    }
    for path in afghan_files:
        run = load(path)
        if int(run["seed"]) != int(contract["afghanistan_seed"]):
            raise ValueError(f"Afghanistan seed mismatch in {path.name}")
        if not run.get("gate", {}).get("passed"):
            raise ValueError(f"Afghanistan structural gate failed in {path.name}")
        case_hashes = run.get("case_hashes", {})
        for name, expected in expected_afghan_case_hashes.items():
            if case_hashes.get(name) != expected:
                raise ValueError(
                    f"Afghanistan case hash mismatch in {path.name}: {name}"
                )

    expected_member_hashes = {
        "nepal": {Path(row["file"]).name: row["sha256"] for row in nepal_members},
        "afghanistan": {Path(row["file"]).name: row["sha256"] for row in afghan_members},
    }

    cases = {}
    for case, expected_rows, expected_members in (
        ("nepal", 19575, 8),
        ("afghanistan", 31280, 3),
    ):
        directory = PROGRAM / "predictive_competition" / f"{case}_v5"
        manifest, decision = verify_artifact_set(directory)
        if manifest.get("execution_contract_sha256") != sha256(EXECUTION):
            raise ValueError(f"{case} competition is not bound to this execution contract")
        if manifest.get("ensemble_files") != expected_member_hashes[case]:
            raise ValueError(f"{case} competition ensemble hashes differ from verified members")
        predictions = pd.read_csv(directory / "aligned_predictions.csv")
        if len(predictions) != expected_rows or decision.get("rows") != expected_rows:
            raise ValueError(
                f"{case} row count drift: predictions={len(predictions)} "
                f"decision={decision.get('rows')} expected={expected_rows}"
            )
        if not decision.get("ensemble_complete") or decision.get("member_count") != expected_members:
            raise ValueError(f"{case} competition is not a complete ensemble")
        if not decision.get("final_historical_stage"):
            raise ValueError(f"{case} competition is not marked final")
        cases[case] = {
            "decision": decision,
            "manifest_sha256": sha256(directory / "manifest.json"),
            "aligned_predictions_sha256": manifest["aligned_predictions_sha256"],
            "scores_sha256": manifest["scores_sha256"],
            "decision_sha256": manifest["decision_sha256"],
        }

    diagnoses = {}
    for case in ("nepal", "afghanistan"):
        path = OUT / f"{case}_theory_diagnosis.json"
        if not path.is_file():
            raise ValueError(f"missing {case} diagnostic report")
        diagnosis = load(path)
        if diagnosis.get("primary_verdict") != cases[case]["decision"]["verdict"]:
            raise ValueError(f"{case} diagnostic verdict does not match primary decision")
        if not diagnosis.get("diagnostic_not_confirmatory"):
            raise ValueError(f"{case} diagnostic must remain non-confirmatory")
        diagnoses[case] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "primary_verdict": diagnosis["primary_verdict"],
        }

    afghan_diagnosis = load(OUT / "afghanistan_theory_diagnosis.json")
    control = afghan_diagnosis.get("independent_control_assessment", [])
    if [int(row["strength"]) for row in control] != contract["afghanistan_full_strengths"]:
        raise ValueError("independent Afghanistan control assessment is incomplete")

    all_case_predictive_pass = all(
        case["decision"]["verdict"]
        == "pineland_beats_implemented_simple_models_on_all_holdouts"
        for case in cases.values()
    )
    payload = {
        "schema_version": "pineland.v5_historical_confrontation_gate.v1",
        "status": "complete_once_only_historical_confrontation",
        "freeze_id": contract["freeze_id"],
        "model_sha256": model_hash,
        "tracked_diff_sha256": diff_hash,
        "execution_contract_sha256": sha256(EXECUTION),
        "finalizer_sha256": sha256(Path(__file__)),
        "execution_inputs": execution_inputs,
        "case_input_hashes": {
            "nepal_case_environment_repaired": contract["input_sha256"][
                "studies/nepal_2001_2006/config/case_environment_repaired.json"
            ],
            "afghanistan": expected_afghan_case_hashes,
        },
        "split_hashes": {
            "nepal_split_manifest_sha256": contract["input_sha256"][
                "studies/nepal_2001_2006/config/split_manifest.json"
            ],
            "afghanistan_split_source": "province_week_panel.csv::split",
            "afghanistan_province_week_panel_sha256": contract["input_sha256"][
                "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv"
            ],
        },
        "completed_stages": state["completed_stages"],
        "nepal_members": nepal_members,
        "afghanistan_initialization_uncertainty_conditions": afghan_members,
        "cases": cases,
        "diagnoses": diagnoses,
        "afghanistan_independent_control_assessment": control,
        "all_case_predictive_pass": all_case_predictive_pass,
        "general_theory_promoted": False,
        "calibration_licensed": False,
        "coin_inference_licensed": False,
        "interpretation": (
            "A pass motivates further construct/transfer/identification testing only. "
            "A failure is preserved and may motivate a separately justified localized "
            "hypothesis; neither outcome licenses event-rate tuning."
        ),
    }
    gate_path = OUT / "historical_confrontation_gate.json"
    temp = gate_path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(gate_path)

    lines = [
        "# Pineland v5 once-only historical confrontation",
        "",
        "Freeze: `" + contract["freeze_id"] + "`",
        "",
        f"Execution inputs verified: **{execution_inputs['checked']}**, mismatches: **0**.",
        "",
        "## Primary predictive decisions",
        "",
        "| Case | Rows | Members | Verdict |",
        "|---|---:|---:|---|",
    ]
    for case in ("nepal", "afghanistan"):
        d = cases[case]["decision"]
        lines.append(
            f"| {case.title()} | {d['rows']} | {d['member_count']} | `" + d["verdict"] + "` |"
        )
    lines += [
        "",
        "The Afghanistan members are three initial-strength conditions under one seed, "
        "not three independent stochastic replications.",
        "",
        "## Afghanistan independent control assessment",
        "",
        "| Initial strength | Status | Gate | MAE | RMSE | Pearson |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for row in control:
        def fmt(value):
            return "NA" if value is None else f"{value:.6f}"
        lines.append(
            f"| {row['strength']} | {row.get('status')} | "
            f"{row.get('validation_gate_status')} | {fmt(row.get('mae'))} | "
            f"{fmt(row.get('rmse'))} | {fmt(row.get('pearson'))} |"
        )
    lines += [
        "",
        "Diagnostics decompose rate error, discrimination, latent-to-recorded information "
        "loss, and model-implied/independent control signal. Aggregate action-funnel "
        "counts are not used to infer locality-specific belief or support errors.",
        "",
        f"All-case predictive pass: **{all_case_predictive_pass}**.",
        "",
        "General-theory promotion: **false**. Calibration and COIN inference remain unlicensed.",
    ]
    report_path = OUT / "historical_confrontation_report.md"
    tmp_report = report_path.with_suffix(".tmp")
    tmp_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp_report.replace(report_path)
    print(json.dumps({
        "gate": str(gate_path),
        "report": str(report_path),
        "all_case_predictive_pass": all_case_predictive_pass,
        "case_verdicts": {k: v["decision"]["verdict"] for k, v in cases.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
