"""Run the once-only historical confrontation under the current C freeze."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studies/research_program/scripts"))

from pineland_sim.reproducibility import repository_state, require_certified_core  # noqa: E402
from run_aligned_predictive_competition import frozen_core, sha256, validate_member  # noqa: E402


PROGRAM = ROOT / "studies/research_program"
NEPAL = ROOT / "studies/nepal_2001_2006"
AFGHAN = ROOT / "studies/afghanistan_2004_2021"


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare(output: Path, contract_path: Path, freeze_path: Path, phase_c_path: Path) -> dict:
    require_certified_core(ROOT, freeze_path=freeze_path)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    identity = freeze["software_identity"]
    if contract_path.exists():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("core_freeze_sha256") != sha256(freeze_path):
            raise RuntimeError("existing execution contract is not bound to the requested current freeze")
        return contract

    paths: set[Path] = {freeze_path, phase_c_path, Path(__file__)}
    for study in (NEPAL, AFGHAN):
        for folder in ("config", "data/processed", "scripts"):
            paths.update(
                p for p in (study / folder).rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            )
    paths.update((
        PROGRAM / "simple_competitors.py",
        PROGRAM / "scripts/run_aligned_predictive_competition.py",
    ))
    state = repository_state(ROOT)
    contract = {
        "schema_version": "pineland.historical_execution_contract.v2",
        "freeze_id": freeze["freeze_id"],
        "core_freeze_path": freeze_path.relative_to(ROOT).as_posix(),
        "core_freeze_sha256": sha256(freeze_path),
        "phase_c_contract_path": phase_c_path.relative_to(ROOT).as_posix(),
        "phase_c_contract_sha256": sha256(phase_c_path),
        "model_sha256": identity["model_sha256"],
        "tracked_diff_sha256": identity["tracked_diff_sha256"],
        "native_binary_sha256": identity["native_binary_sha256"],
        **state,
        "input_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)},
        "nepal_seeds": [20011126 + 10007 * i for i in range(8)],
        "nepal_agent_count": 750,
        "nepal_variant": "E_combined",
        "afghanistan_seed": 20040101,
        "afghanistan_full_strengths": [5000, 7500, 10000],
        "stages": ["nepal_full", "nepal_competition", "afghanistan_init", "afghanistan_smoke", "afghanistan_year", "afghanistan_full", "afghanistan_competition"],
        "holdout_refit": False,
        "core_changes_authorized": False,
        "historical_tuning": False,
        "calibration_licensed": False,
        "coin_inference_licensed": False,
    }
    write(contract_path, contract)
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=PROGRAM / "historical_revalidation_v6")
    parser.add_argument("--core-freeze", type=Path, default=PROGRAM / "core_freeze_current_v1.json")
    parser.add_argument("--phase-c", type=Path, default=PROGRAM / "phase_c_method_contract_v2.json")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    freeze_path = args.core_freeze.resolve()
    phase_c_path = args.phase_c.resolve()
    contract_path = output / "execution_contract.json"
    contract = prepare(output, contract_path, freeze_path, phase_c_path)
    require_certified_core(ROOT, freeze_path=freeze_path)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUNBUFFERED="1")
    suffix = output.name.rsplit("_", 1)[-1]
    nepal_runs = NEPAL / f"runs/post_structural_repair/final_empirical_rescore_{suffix}"
    afghan_runs = AFGHAN / f"runs/transfer_test_{suffix}"
    scorer = PROGRAM / "scripts/run_aligned_predictive_competition.py"
    transfer = AFGHAN / "scripts/run_transfer_test.py"
    commands = [
        ("nepal_full", [NEPAL / "scripts/run_untuned_benchmark.py", "--workers", "4", "--agent-count", "750", "--output-dir", nepal_runs]),
        ("nepal_competition", [scorer, "--case", "nepal", "--run-dir", nepal_runs, "--output-dir", PROGRAM / f"predictive_competition/nepal_{suffix}", "--expected-members", "8", "--final-stage", "--execution-contract", contract_path]),
    ]
    for stage in ("init", "smoke", "year", "full"):
        commands.append((f"afghanistan_{stage}", [transfer, "--stage", stage, "--core-freeze", freeze_path, "--output-dir", afghan_runs / stage]))
    commands.append(("afghanistan_competition", [scorer, "--case", "afghanistan", "--run-dir", afghan_runs / "full", "--output-dir", PROGRAM / f"predictive_competition/afghanistan_{suffix}", "--expected-members", "3", "--final-stage", "--execution-contract", contract_path]))

    state_path = output / "status.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"completed_stages": []}
    for stage, command in commands:
        frozen_core(contract_path)
        if repository_state(ROOT)["tracked_diff_sha256"] != contract["tracked_diff_sha256"]:
            raise RuntimeError("tracked checkout diff changed since execution preregistration")
        for directory, pattern in [
            (nepal_runs, "seed_*_agents_750.json"),
            *((afghan_runs / s, "seed_*_taliban_*.json") for s in ("init", "smoke", "year", "full")),
        ]:
            for path in directory.glob(pattern):
                validate_member(path, contract["model_sha256"], contract["tracked_diff_sha256"])
        if stage in state.get("completed_stages", []):
            continue
        state.update(current_stage=stage, status="running")
        write(state_path, state)
        print(f"Starting {stage}", flush=True)
        with (output / f"{stage}.log").open("a", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, *map(str, command)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            state.update(status="failed", returncode=result.returncode)
            write(state_path, state)
            raise SystemExit(result.returncode)
        state.setdefault("completed_stages", []).append(stage)
        write(state_path, state)
        print(f"Completed {stage}", flush=True)
    state.update(status="completed", calibration_licensed=False, coin_inference_licensed=False)
    write(state_path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
