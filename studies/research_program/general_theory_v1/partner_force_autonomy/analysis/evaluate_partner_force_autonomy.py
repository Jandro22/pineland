"""Stage-3 discovery analysis for the Pineland partner-force autonomy program.

This script never launches Pineland.  It analyzes raw branch output created by
the Rust Stage-3 runner.  Dry-run mode is plumbing-only and writes no artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(HERE))

from partner_force_metrics import pair_counterfactual_rows, analyze_paired_panel
from partner_force_regenerative_coordinates import (
    add_candidate_regenerative_coordinates,
    evaluate_bottleneck_competitors,
    evaluate_regeneration_vs_stocks,
    evaluate_supported_performance_vs_indigenous_state,
)


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze real Stage-3 paired Pineland output")
    p.add_argument("--input-csv")
    p.add_argument("--output-dir", default=str(BASE / "outputs"))
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def load_input(ns: argparse.Namespace) -> tuple[pd.DataFrame, Path]:
    if ns.dry_run:
        path = BASE / "fixtures" / "neutral_pairing_fixture_v2.csv"
    else:
        if not ns.input_csv:
            raise SystemExit("--input-csv is required for real analysis; the evaluator never substitutes fixture data")
        path = Path(ns.input_csv)
        if "fixtures" in path.parts:
            raise SystemExit("refusing scientific analysis of a fixture path; use --dry-run for plumbing validation")
    if not path.exists():
        raise SystemExit(f"input not found: {path}")
    return pd.read_csv(path), path


def main() -> None:
    ns = args()
    raw, source = load_input(ns)
    paired = pair_counterfactual_rows(raw)
    paired = add_candidate_regenerative_coordinates(paired)

    if ns.dry_run:
        assert len(paired) >= 2
        assert paired["autonomy_ratio"].notna().all()
        assert paired[["omega_manpower", "omega_logistics", "omega_command"]].notna().all().all()
        print("PLUMBING_ONLY_PASS: neutral fixture paired correctly; R_h/Delta_h and candidate coordinates derive from raw branches.")
        print("NO_SCIENTIFIC_EVALUATION: dry-run generated no findings and wrote no output files.")
        return

    bundle = {
        "schema_version": "pineland.partner_force_autonomy_stage3_discovery_analysis.v1",
        "status": "DISCOVERY_ANALYSIS_NO_HOLDOUT_CLAIMS",
        "source_csv": str(source),
        "paired_summary": analyze_paired_panel(paired),
        "PF-H1_performance_masking_discovery": evaluate_supported_performance_vs_indigenous_state(paired),
        "PF-H2_bottleneck_discovery": evaluate_bottleneck_competitors(paired),
        "PF-H3_regeneration_discovery": evaluate_regeneration_vs_stocks(paired),
        "PF-H4_complexity_capacity": {
            "status": "NOT_TESTED_IN_STAGE3_DISCOVERY",
            "reason": "Complexity is intentionally reserved for a preregistered held-out mechanism family after discovery predictors are frozen."
        },
        "claim_boundary": "These are in-model discovery results. No transport or real-world claim is licensed until zero-refit held-out tests are completed."
    }
    outdir = Path(ns.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "partner_force_autonomy_stage3_discovery_metrics_v1.json"
    paired_path = outdir / "partner_force_autonomy_stage3_paired_v1.csv"
    json_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    paired.to_csv(paired_path, index=False)
    print(f"Wrote discovery metrics: {json_path}")
    print(f"Wrote derived paired panel: {paired_path}")
    print("STATUS: DISCOVERY ONLY — freeze candidate predictors before running any held-out mechanism family.")


if __name__ == "__main__":
    main()
