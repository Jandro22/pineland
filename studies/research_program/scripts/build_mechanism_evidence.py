"""Build a descriptive mechanism-ablation matrix from a completed case.

The output deliberately reports deltas, not causal claims.  A mechanism earns
cross-case status only after the same ablation contract and holdouts are run in
another case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
METRICS = (
    "events",
    "active_cells",
    "new_district_activation_rate",
    "return_activation_rate",
    "morans_i",
    "weekly_fano",
    "district_gini",
    "final_active_formations",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(payload: dict[str, Any], *, case_id: str, source: Path) -> dict[str, Any]:
    designs = payload.get("designs", {})
    baseline = designs.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("ablation payload must contain designs.baseline")
    baseline_means = {
        metric: baseline.get(metric, {}).get("mean")
        for metric in METRICS
        if isinstance(baseline.get(metric), dict) and "mean" in baseline[metric]
    }
    rows = []
    for design_id, design in sorted(designs.items()):
        if design_id == "baseline":
            continue
        deltas = {}
        for metric, baseline_value in baseline_means.items():
            value = design.get(metric, {}).get("mean") if isinstance(design.get(metric), dict) else None
            if value is not None:
                deltas[metric] = {"baseline_mean": baseline_value, "design_mean": value, "delta": value - baseline_value}
        rows.append({
            "design_id": design_id,
            "interpretation_status": "descriptive_ablation_not_causal_claim",
            "deltas": deltas,
        })
    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "status": "case_evidence_pending_cross_case_replication",
        "source_file": str(source).replace("\\", "/"),
        "source_sha256": _sha256(source),
        "baseline_metrics": baseline_means,
        "ablation_rows": rows,
        "promotion_rule": "Do not label a mechanism general unless its predeclared direction and holdout value replicate across at least two transfer cases and survive simple competitors.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "studies/nepal_2001_2006/results/residual_diagnosis/compact_mechanism_diagnostics.json")
    parser.add_argument("--case-id", default="nepal_2001_2006")
    parser.add_argument("--output", type=Path, default=ROOT / "studies/research_program/nepal_mechanism_evidence.json")
    args = parser.parse_args()
    result = build(json.loads(args.input.read_text(encoding="utf-8")), case_id=args.case_id, source=args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
