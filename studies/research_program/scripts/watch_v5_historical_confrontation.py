"""Finish declared read-only diagnostics as the immediate v5 computation completes."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
OUT = PROGRAM / "historical_revalidation_v5"


def main():
    diagnosed = (OUT / "nepal_theory_diagnosis.json").exists()
    while True:
        state = json.loads((OUT / "status.json").read_text())
        if "nepal_competition" in state["completed_stages"] and not diagnosed:
            with (OUT / "nepal_theory_diagnosis.log").open("w") as log:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name(
                    "diagnose_v5_historical_confrontation.py"))], cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                (OUT / "diagnostic_failure.json").write_text(json.dumps({
                    "returncode": result.returncode, "primary_run_modified": False}) + "\n")
                raise SystemExit(result.returncode)
            diagnosed = True
            print("Nepal theory diagnosis completed", flush=True)
        lines = ["# Frozen v5 historical confrontation", "",
                 f"Computation status: **{state['status']}**; stage: `{state['current_stage']}`.", "",
                 "No calibration, mechanism modification, or COIN inference is licensed.", ""]
        for case in ("nepal", "afghanistan"):
            path = PROGRAM / f"predictive_competition/{case}_v5/decision.json"
            if f"{case}_competition" not in state["completed_stages"]:
                lines += [f"{case.title()}: historical competition pending.", ""]
                continue
            decision = json.loads(path.read_text())
            lines += [f"## {case.title()}", "", f"Verdict: `{decision['verdict']}`.", "",
                      "| Holdout | Pineland Brier | Best simple Brier | Pineland log score | Best simple log score | Pass both |",
                      "|---|---:|---:|---:|---:|---|"]
            for row in decision["holdout_comparisons"]:
                lines.append(f"| {row['split']} | {row['pineland_brier']:.6f} | {row['best_simple_brier']:.6f} | "
                             f"{row['pineland_log_score']:.6f} | {row['best_simple_log_score']:.6f} | "
                             f"{row['pineland_strictly_better_on_both']} |")
            lines += [""]
        if diagnosed:
            diagnosis = json.loads((OUT / "nepal_theory_diagnosis.json").read_text())
            lines += ["## Nepal theory diagnostics", "",
                "The v4/v5 rows, targets, splits and simple predictions are identical. These diagnostics do not override the primary gate.", "",
                "| Split | v4 recorded AUC | v5 recorded AUC | v5 latent AUC | v5 prior control AUC | v5 Brier improvement over v4 |",
                "|---|---:|---:|---:|---:|---:|"]
            for row in diagnosis["split_diagnostics"]:
                def fmt(value):
                    return "undefined" if value is None else f"{value:.6f}"
                lines.append(f"| {row['split']} | {fmt(row['v4_recorded']['auc'])} | "
                    f"{fmt(row['v5_recorded']['auc'])} | {fmt(row['v5_latent']['auc'])} | "
                    f"{fmt(row['v5_prior_control_composite_auc'])} | "
                    f"{fmt(row['recorded_brier_improvement_v5_over_v4'])} |")
            lines += ["", "The control signal is model-implied state, not independently validated organizational capacity. "
                      "Aggregate action failures cannot identify local belief or support errors.", ""]
        if "afghanistan_full" in state["completed_stages"]:
            lines += ["## Afghanistan independent control outputs", ""]
            for path in sorted((ROOT / "studies/afghanistan_2004_2021/runs/transfer_test_v5/full").glob("seed_*json")):
                run = json.loads(path.read_text())
                lines += [f"Strength {run['taliban_initial_strength']}: `{run['control_validation_status']}`.", "",
                          "```json", json.dumps(run["control_validation"], indent=2), "```", ""]
            lines += ["The three strengths are initial-condition uncertainty, not independent stochastic replications. "
                      "A violence competition pass alone does not establish general transfer.", ""]
        temporary = OUT / "readout.tmp"
        temporary.write_text("\n".join(lines), encoding="utf-8")
        temporary.replace(OUT / "readout.md")
        if state["status"] in {"completed", "failed"}:
            print(f"Historical readout saved; computation {state['status']}", flush=True)
            return
        time.sleep(15)


if __name__ == "__main__":
    main()
