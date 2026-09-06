"""Compare frozen ACLED and UCDP Afghanistan province-week incidence.

The comparison is descriptive measurement concordance only. Neither source is
declared ground truth and no model parameter is estimated here.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT
    / "studies/research_program/afghanistan_acled_independent_measurement_contract_v1.json"
)
UCDP = (
    ROOT
    / "studies/afghanistan_2004_2021/data/processed/province_week_panel.csv"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _acled(path: Path) -> dict[tuple[str, int], int]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            (row["province_id"], int(row["week_index"])):
                int(row["acled_reported_active"])
            for row in csv.DictReader(handle)
        }


def _ucdp(year: int, keys: set[tuple[str, int]]) -> dict[tuple[str, int], int]:
    result = {}
    with UCDP.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["province_id"], int(row["week_index"]))
            if key in keys:
                result[key] = int(row["taliban_state_active"])
    missing = keys - set(result)
    if missing:
        raise RuntimeError(f"UCDP panel is missing {len(missing)} ACLED calendar cells")
    return result


def compare(acled_path: Path, year: int, output: Path) -> dict:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if year not in {
        int(contract["target_surface"]["primary_year"]),
        int(contract["target_surface"]["secondary_year"]),
    }:
        raise ValueError("year lies outside the frozen ACLED contract")
    a = _acled(acled_path)
    u = _ucdp(year, set(a))
    both = sum(a[key] and u[key] for key in a)
    acled_only = sum(a[key] and not u[key] for key in a)
    ucdp_only = sum(u[key] and not a[key] for key in a)
    neither = sum(not a[key] and not u[key] for key in a)
    union = both + acled_only + ucdp_only
    positive_agreement = both / union if union else 1.0
    acled_active = both + acled_only
    ucdp_active = both + ucdp_only
    payload = {
        "schema_version": "pineland.afghanistan.acled_ucdp_concordance.v1",
        "year": year,
        "rows": len(a),
        "contract_sha256": sha256(CONTRACT),
        "acled_panel_sha256": sha256(acled_path),
        "ucdp_panel_sha256": sha256(UCDP),
        "cells": {
            "both_reported_active": both,
            "acled_only_reported_active": acled_only,
            "ucdp_only_reported_active": ucdp_only,
            "both_source_silent": neither,
        },
        "rates": {
            "acled_reported_active": acled_active / len(a),
            "ucdp_reported_active": ucdp_active / len(a),
            "positive_jaccard": positive_agreement,
            "acled_overlap_fraction": (
                both / acled_active if acled_active else None
            ),
            "ucdp_overlap_fraction": (
                both / ucdp_active if ucdp_active else None
            ),
        },
        "ground_truth_assumed": False,
        "parameters_fitted": False,
        "interpretation": (
            "This is a source-family concordance diagnostic. ACLED-only and "
            "UCDP-only cells demonstrate measurement-pipeline disagreement; "
            "source silence is not interpreted as latent peace. The result may "
            "not tune Pineland or its recording operator."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acled-panel", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(
        compare(args.acled_panel, args.year, args.output),
        indent=2, sort_keys=True,
    ))


if __name__ == "__main__":
    main()
