"""Build an observation-only cross-case reproduction-signature diagnostic.

This benchmark deliberately consumes historical diagnostic artifacts rather than
the moving simulator core. It harmonizes the signatures that are currently
available, records denominators and provenance, and emits explicit missing
cells for cases that are not ready. It is not a causal estimator or a theory
promotion gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _ref(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}


def _metric_bundle(metrics: dict[str, Any], horizons: list[str]) -> dict[str, Any]:
    return {
        "horizons": {
            horizon: {
                "same_unit_renewal_probability": metrics.get("recurrence_probability", {}).get(horizon),
                "same_unit_renewal_denominator": None,
                "inactive_unit_baseline_activation_probability": metrics.get(
                    "inactive_baseline_activation_probability", {}
                ).get(horizon),
                "adjacent_activation_probability": metrics.get(
                    "adjacent_propagation_probability", {}
                ).get(horizon),
                "active_spell_survival": None,
                "topology_morans_i": metrics.get("morans_i") if horizon == "1" else None,
            }
            for horizon in horizons
        },
        "denominator_note": "The source artifact does not expose a common per-horizon denominator; do not compare rates as if denominators were identical.",
        "missingness": "Explicit denominator missingness is retained rather than imputed.",
    }


def build_benchmark(root: Path = ROOT) -> dict[str, Any]:
    nepal_path = root / "studies/nepal_2001_2006/results/residual_diagnosis/residual_shape_metrics.json"
    afghanistan_path = root / "studies/afghanistan_2004_2021/results/transfer_test_v1/control_target_ensemble_v2/spatial_reproduction_diagnostic.json"
    readiness_path = root / "studies/research_program/case_readiness_snapshot.json"
    nepal = _load(nepal_path)
    afghanistan = _load(afghanistan_path)
    readiness = _load(readiness_path)
    horizons = ["1", "2", "4", "8"]
    training = nepal.get("splits", {}).get("training", {}).get("historical", {})
    afghan_hist = afghanistan.get("historical", {})

    cases: list[dict[str, Any]] = [
        {
            "case_id": "nepal_2001_2006",
            "source_case_id": "nepal_2001_2006",
            "eligibility": "archival_historical_signature_not_current_core_eligible",
            "panel_status": "historical_training_stream_available",
            "metrics": _metric_bundle(training, horizons),
            "historical_summary": {
                "active_cells": training.get("active_cells"),
                "events": training.get("events"),
                "active_cell_share": training.get("active_cell_share"),
                "same_unit_renewal_probability_h1": training.get("recurrence_probability", {}).get("1"),
                "adjacent_activation_probability_h1": training.get("adjacent_propagation_probability", {}).get("1"),
                "topology_morans_i": training.get("morans_i"),
            },
            "provenance": [_ref(nepal_path)],
            "interpretation": "Archival descriptive signature only; source carries frozen hashes but is not bound to the active live-core certificate.",
        },
        {
            "case_id": "afghanistan_2004_2021",
            "source_case_id": "afghanistan_2004_2021",
            "eligibility": "archival_historical_signature_not_current_core_eligible",
            "panel_status": "historical_summary_available",
            "metrics": {
                "horizons": {
                    "1": {
                        "same_unit_renewal_probability": afghan_hist.get("same_area_renewal_rate"),
                        "same_unit_renewal_denominator": afghan_hist.get("same_area_renewal_n"),
                        "inactive_unit_baseline_activation_probability": None,
                        "adjacent_activation_probability": afghan_hist.get("neighbor_activation_rate"),
                        "active_spell_survival": None,
                        "topology_morans_i": None,
                    }
                },
                "denominator_note": "Same-area renewal exposes n; neighbor activation exposes exposures. Other denominators are absent.",
                "missingness": "Unreported metrics remain null.",
            },
            "historical_summary": {
                "active_cells": afghan_hist.get("active_cells"),
                "same_unit_renewal_denominator": afghan_hist.get("same_area_renewal_n"),
                "same_unit_renewal_probability_h1": afghan_hist.get("same_area_renewal_rate"),
                "adjacent_activation_denominator": afghan_hist.get("neighbor_exposures"),
                "adjacent_activation_probability_h1": afghan_hist.get("neighbor_activation_rate"),
            },
            "provenance": [_ref(afghanistan_path)],
            "interpretation": "Archival descriptive signature only; transfer and causal claims remain unlicensed.",
        },
    ]

    readiness_by_source = {item["case_id"].split("_")[0]: item for item in readiness.get("cases", [])}
    for case_id, source_case_id in (("colombia", "colombia_1984_2016"), ("iraq", "iraq_2003_2011"), ("vietnam", "vietnam_1955_1975")):
        item = readiness_by_source.get(case_id, {})
        cases.append(
            {
                "case_id": case_id,
                "source_case_id": source_case_id,
                "eligibility": "not_ready",
                "panel_status": item.get("status", "data_construction"),
                "metrics": None,
                "historical_summary": None,
                "provenance": [{"path": "studies/research_program/case_readiness_snapshot.json", "sha256": _sha256(readiness_path)}],
                "missingness": item.get("readiness", {}).get("blocked_reasons", ["processed_panel_manifest"]),
                "interpretation": "No rate is reported: sparse or incomplete panels cannot be treated as zero activity.",
            }
        )

    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "historical_signature_diagnostic_not_causal_reproduction",
        "generated_by": "build_historical_reproduction_signature_benchmark.py",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "unit": "case-declared local unit with observation-aware denominators",
        "horizons": horizons,
        "metrics": [
            "same_unit_renewal_probability",
            "inactive_unit_baseline_activation_probability",
            "adjacent_activation_probability",
            "active_spell_survival",
            "topology_morans_i",
        ],
        "nulls_required_before_promotion": [
            "temporal_lead_placebo",
            "degree_preserving_or_shuffled_topology",
            "reporting-persistence sensitivity",
        ],
        "interpretation_guard": "A positive signature may reflect reporting persistence, relocation, or unobserved actor identity; it does not prove local reproduction or causal propagation.",
        "cases": cases,
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "No two current-core eligible historical cases with harmonized denominators and placebo/null diagnostics are available.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "historical_reproduction_signature_benchmark.json")
    args = parser.parse_args()
    report = build_benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
