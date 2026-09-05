"""Summarize the Afghanistan contact opportunity funnel without tuning it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS = ROOT / "studies/afghanistan_2004_2021/runs/transfer_test_v1/year_ensemble"


def diagnose(runs_dir: Path) -> dict:
    rows = []
    for path in sorted(runs_dir.glob("seed_*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        funnel = run.get("contact_funnel_counts", {})
        hazard = run.get("hazard_diagnostics", {})
        latent = run.get("violence_validation", {}).get("latent_contacts", 0)
        recorded = run.get("violence_validation", {}).get("recorded_contacts", 0)
        draws = funnel.get("engagement_hazard_draws", 0)
        if draws == 0:
            classification = "universal_opportunity_gate_failure"
        elif latent == 0:
            classification = "zero_realization_consistent_with_declared_hazard"
        elif recorded == 0:
            classification = "latent_contact_without_recorded_contact"
        else:
            classification = "nondegenerate_realized_contact_stream"
        rows.append({
            "strength": run.get("taliban_initial_strength"),
            "horizon_days": run.get("horizon_days"),
            "scheduler_executions": funnel.get("scheduler_executions", 0),
            "opposing_armed_organizations": funnel.get("opposing_armed_organizations", 0),
            "hazard_draws": draws,
            "hazard_passes": funnel.get("engagement_hazard_passes", 0),
            "expected_contacts": hazard.get("expected_contacts", 0.0),
            "probability_zero_contacts": hazard.get("probability_zero_contacts"),
            "latent_contacts": latent,
            "recorded_contacts": recorded,
            "classification": classification,
        })
    return {
        "schema_version": "1.0.0",
        "status": "diagnostic_not_calibration",
        "runs": rows,
        "interpretation": (
            "A zero realized contact count is interpreted against the declared hazard opportunity, "
            "not repaired by changing Afghanistan parameters. This diagnostic does not license a violence claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(args.runs_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
