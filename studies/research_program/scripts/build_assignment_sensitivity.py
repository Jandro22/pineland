"""Quantify raw event location-assignment coverage without imputing missing units.

This is a descriptive missingness audit for the historical signature screen. It
does not reassign events, fit parameters, or convert unassigned events into
zeros or latent activity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies" / "research_program"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ref(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}


def _case(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    raw_path = root / spec["raw"]
    rows = 0
    assigned = 0
    units: set[str] = set()
    dates: list[str] = []
    with raw_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            date_value = str(row.get(spec["date_column"], "")).strip()
            if date_value:
                try:
                    dates.append(datetime.fromisoformat(date_value[:10]).date().isoformat())
                except ValueError:
                    pass
            if spec["assignment_rule"](row):
                assigned += 1
                unit = str(row.get(spec["unit_column"], "")).strip()
                if unit:
                    units.add(unit)
    unassigned = rows - assigned
    return {
        "case_id": spec["case_id"],
        "raw_event_rows": rows,
        "assigned_rows": assigned,
        "unassigned_rows": unassigned,
        "assignment_coverage": assigned / rows if rows else None,
        "assigned_units": len(units),
        "date_range": {"start": min(dates) if dates else None, "end": max(dates) if dates else None},
        "assignment_rule": spec["assignment_description"],
        "provenance": [_ref(raw_path), _ref(root / spec["panel"])],
        "interpretation": "Coverage describes observed location assignment only; unassigned rows remain missing and are not imputed as zero or latent activity.",
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    specs = [
        {
            "case_id": "nepal_2001_2006",
            "raw": "studies/nepal_2001_2006/data/processed/ucdp_nepal_events.csv",
            "panel": "studies/nepal_2001_2006/data/processed/district_week_panel.csv",
            "unit_column": "district_id",
            "date_column": "date_start",
            "assignment_rule": lambda row: bool(str(row.get("district_id", "")).strip()),
            "assignment_description": "district_id is nonempty",
        },
        {
            "case_id": "afghanistan_2004_2021",
            "raw": "studies/afghanistan_2004_2021/data/processed/ucdp_afghanistan_events.csv",
            "panel": "studies/afghanistan_2004_2021/data/processed/district_month_panel.csv",
            "unit_column": "district_id",
            "date_column": "date_start",
            "assignment_rule": lambda row: (
                str(row.get("district_high_confidence", "")).strip() == "1"
                and bool(str(row.get("district_id", "")).strip())
            ),
            "assignment_description": "district_high_confidence == 1 and district_id is nonempty",
        },
    ]
    return {
        "schema_version": "1.0.0",
        "program_id": "comparative-insurgency-v1",
        "status": "descriptive_assignment_coverage_not_imputation",
        "historical_outcomes_used": True,
        "historical_parameter_fitting": False,
        "core_change_licensed": False,
        "cases": [_case(root, spec) for spec in specs],
        "negative_constraints": [
            "assignment coverage does not identify actor reproduction",
            "unassigned events are missing, not zeros or latent activity",
            "coverage differences prevent direct cross-case rate comparison without a measurement model",
        ],
        "promotion_decision": {
            "stable_general_theory_licensed": False,
            "reason": "Location assignment remains an observation-process limitation requiring sensitivity or a frozen case-specific observation model.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROGRAM / "historical_assignment_sensitivity.json")
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
