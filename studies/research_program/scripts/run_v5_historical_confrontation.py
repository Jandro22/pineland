"""Once-only v5 historical confrontation; resume completed cells without overwriting."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from pineland_sim.reproducibility import repository_state, require_certified_core
from run_aligned_predictive_competition import frozen_core, sha256, validate_member

PROGRAM = ROOT / "studies/research_program"
OUTPUT = PROGRAM / "historical_revalidation_v5"
CONTRACT = OUTPUT / "execution_contract.json"
NEPAL = ROOT / "studies/nepal_2001_2006"
AFGHAN = ROOT / "studies/afghanistan_2004_2021"


def write(path, payload):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def prepare():
    require_certified_core(ROOT)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not CONTRACT.exists():
        freeze = json.loads((PROGRAM / "core_freeze.json").read_text())
        paths = set()
        for study in (NEPAL, AFGHAN):
            for folder in ("config", "data/processed", "scripts"):
                paths.update(p for p in (study / folder).rglob("*")
                             if p.is_file() and "__pycache__" not in p.parts)
        paths.update((PROGRAM / "simple_competitors.py",
                      PROGRAM / "scripts/run_aligned_predictive_competition.py",
                      Path(__file__), PROGRAM / "core_freeze.json"))
        contract = {
            "schema_version": "pineland.historical_execution_contract.v1",
            "freeze_id": freeze["freeze_id"],
            "model_sha256": freeze["model_sha256"],
            "certificate_payload_sha256": freeze["certificate_payload_sha256"],
            **repository_state(ROOT),
            "input_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)},
            "nepal_seeds": [20011126 + 10007 * i for i in range(8)],
            "nepal_agent_count": 750,
            "nepal_variant": "E_combined",
            "afghanistan_seed": 20040101,
            "afghanistan_full_strengths": [5000, 7500, 10000],
            "stages": ["nepal_full", "nepal_competition", "afghanistan_init",
                       "afghanistan_smoke", "afghanistan_year", "afghanistan_full",
                       "afghanistan_competition"],
            "holdout_refit": False,
            "core_changes_authorized": False,
            "calibration_licensed": False,
            "coin_inference_licensed": False,
        }
        write(CONTRACT, contract)
    frozen_core(CONTRACT)
    return json.loads(CONTRACT.read_text())


def main():
    contract = prepare()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUNBUFFERED="1")
    nepal_runs = NEPAL / "runs/post_structural_repair/final_empirical_rescore_v5"
    afghan_runs = AFGHAN / "runs/transfer_test_v5"
    scorer = PROGRAM / "scripts/run_aligned_predictive_competition.py"
    commands = [("nepal_full", [NEPAL / "scripts/run_untuned_benchmark.py", "--workers", "4",
        "--agent-count", "750", "--output-dir", nepal_runs])]
    commands.append(("nepal_competition", [scorer, "--case", "nepal", "--run-dir", nepal_runs,
        "--output-dir", PROGRAM / "predictive_competition/nepal_v5", "--expected-members", "8",
        "--final-stage", "--execution-contract", CONTRACT]))
    for stage in ("init", "smoke", "year", "full"):
        commands.append((f"afghanistan_{stage}", [AFGHAN / "scripts/run_transfer_test.py",
            "--stage", stage, "--output-dir", afghan_runs / stage]))
    commands.append(("afghanistan_competition", [scorer, "--case", "afghanistan",
        "--run-dir", afghan_runs / "full", "--output-dir", PROGRAM / "predictive_competition/afghanistan_v5",
        "--expected-members", "3", "--final-stage", "--execution-contract", CONTRACT]))
    state_path = OUTPUT / "status.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"completed_stages": []}
    for stage, command in commands:
        frozen_core(CONTRACT)
        if repository_state(ROOT)["tracked_diff_sha256"] != contract["tracked_diff_sha256"]:
            raise RuntimeError("checkout diff changed since execution preregistration")
        for directory, pattern in [(nepal_runs, "seed_*_agents_750.json"),
                                   *((afghan_runs / s, "seed_*_taliban_*.json") for s in ("init", "smoke", "year", "full"))]:
            for path in directory.glob(pattern):
                validate_member(path, contract["model_sha256"], contract["tracked_diff_sha256"])
        if stage in state["completed_stages"]:
            continue
        state.update(current_stage=stage, status="running")
        write(state_path, state)
        print(f"Starting {stage}", flush=True)
        with (OUTPUT / f"{stage}.log").open("a", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, *map(str, command)], cwd=ROOT, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            state.update(status="failed", returncode=result.returncode)
            write(state_path, state)
            raise SystemExit(result.returncode)
        state["completed_stages"].append(stage)
        write(state_path, state)
        print(f"Completed {stage}", flush=True)
    state.update(status="completed", calibration_licensed=False, coin_inference_licensed=False)
    write(state_path, state)


if __name__ == "__main__":
    main()
