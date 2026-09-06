"""Versioned civilian-harm source-coverage audit after UCDP cross-check.

V1 remains an intentional failed pre-UCDP coverage audit.  This V2 combines the
manual/source-bound first coder with the preregistered structured UCDP extraction.
It never reads Pineland output.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
FIRST = PROGRAM / "civilian_harm_first_coder_v1.csv"
FIRST_AUDIT = PROGRAM / "civilian_harm_first_coder_audit_v1.json"
EXPOSURE = PROGRAM / "civilian_harm_source_exposure_log_v1.csv"
UCDP_CONTRACT = PROGRAM / "civilian_harm_ucdp_crosscheck_contract_v1.json"
UCDP_AUDIT = PROGRAM / "civilian_harm_ucdp_overlap_audit_v1.json"
MODEL_COMPAT = PROGRAM / "civilian_harm_model_compatibility_contract_v1.json"
OUT = PROGRAM / "civilian_harm_source_coverage_audit_v2.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    dx = [v - mx for v in x]
    dy = [v - my for v in y]
    denom = (sum(v * v for v in dx) * sum(v * v for v in dy)) ** 0.5
    return sum(a * b for a, b in zip(dx, dy)) / denom if denom else None


def main() -> int:
    first_audit = json.loads(FIRST_AUDIT.read_text(encoding="utf-8"))
    ucdp = json.loads(UCDP_AUDIT.read_text(encoding="utf-8"))
    compat = json.loads(MODEL_COMPAT.read_text(encoding="utf-8"))
    with FIRST.open(encoding="utf-8-sig", newline="") as f:
        first_rows = list(csv.DictReader(f))
    with EXPOSURE.open(encoding="utf-8-sig", newline="") as f:
        exposure = list(csv.DictReader(f))

    ucdp_cases = {
        row["case_id"] for row in exposure
        if row["source_family"] == "UCDP_GED" and row["first_coder_status"] == "structured_crosscheck_extracted_v1"
    }
    manual_direct_families = {
        case: {
            row["source_family"] for row in first_rows
            if row["case_id"] == case and row["component"] == "direct_harm"
        }
        for case in ("nepal_2001_2006", "afghanistan_2004_2021")
    }
    manual_displacement_families = {
        case: {
            row["source_family"] for row in first_rows
            if row["case_id"] == case and row["component"] == "displacement"
        }
        for case in ("nepal_2001_2006", "afghanistan_2004_2021")
    }

    # Collapse known derivative labels to their originating institutions.
    origin_map = {
        "OHCHR_conflict_IHL_monitoring": "OHCHR",
        "UNAMA_OHCHR_civilian_casualty_monitoring": "UNAMA_OHCHR",
        "UNHCR_displacement_monitoring": "UNHCR",
        "UNHCR_via_IDMC_displacement_figures": "UNHCR",
    }
    direct_origins = {}
    displacement_origins = {}
    for case in manual_direct_families:
        origins = {origin_map.get(x, x) for x in manual_direct_families[case]}
        if case in ucdp_cases:
            origins.add("UCDP_GED")
        direct_origins[case] = sorted(origins)
        displacement_origins[case] = sorted(
            {origin_map.get(x, x) for x in manual_displacement_families[case]}
        )

    matched = ucdp["matched_full_year_afghanistan_unama_ucdp"]
    ratios = [float(r["ucdp_to_unama_ratio"]) for r in matched if r["ucdp_to_unama_ratio"] is not None]
    u = [float(r["ucdp_civilian_deaths"]) for r in matched]
    n = [float(r["unama_civilian_deaths"]) for r in matched]
    spearman = pearson(rank(u), rank(n)) if len(matched) >= 4 else None

    coverage = {
        "nepal_direct_harm_two_independent_families": len(direct_origins["nepal_2001_2006"]) >= 2,
        "afghanistan_direct_harm_two_independent_families_or_audited_series_plus_crosscheck": len(direct_origins["afghanistan_2004_2021"]) >= 2,
        "nepal_displacement_or_resource_loss_family_present": bool(displacement_origins["nepal_2001_2006"]) or first_audit["case_component_coverage"]["nepal_2001_2006"]["resource_loss"]["coded_record_count"] > 0,
        "afghanistan_longitudinal_displacement_family_present": bool(displacement_origins["afghanistan_2004_2021"]),
    }
    payload = {
        "schema_version": "pineland.civilian_harm_source_coverage.v2",
        "status": "coverage_gate_after_independent_ucdp_crosscheck_not_confirmatory_validation",
        "preserved_prior_result": {
            "path": "studies/research_program/civilian_harm_first_coder_audit_v1.json",
            "sha256": sha(FIRST_AUDIT),
            "v1_first_coder_coverage_gate_passed": first_audit["first_coder_coverage_gate_passed"],
            "rule": "V1 remains failed; V2 adds prospectively contracted evidence rather than rewriting V1."
        },
        "artifact_hashes": {
            "first_coder": sha(FIRST),
            "source_exposure_log": sha(EXPOSURE),
            "ucdp_contract": sha(UCDP_CONTRACT),
            "ucdp_overlap_audit": sha(UCDP_AUDIT),
            "model_compatibility_contract": sha(MODEL_COMPAT),
        },
        "direct_harm_independent_origins": direct_origins,
        "displacement_independent_origins": displacement_origins,
        "coverage_gate_components": coverage,
        "source_acquisition_coverage_gate_passed": all(coverage.values()),
        "afghanistan_ucdp_unama_measurement_concordance": {
            "matched_full_year_count": len(matched),
            "matched_rows": matched,
            "ucdp_to_unama_ratio_min": min(ratios) if ratios else None,
            "ucdp_to_unama_ratio_median": median(ratios) if ratios else None,
            "ucdp_to_unama_ratio_max": max(ratios) if ratios else None,
            "spearman_rank_correlation": spearman,
            "interpretation": "Matched years can have similar temporal ordering while differing substantially in absolute level. This is source-measurement disagreement, not a calibration target and not grounds to privilege either source."
        },
        "a60_343_screening_update": {
            "finding": "A/60/343 reports about 130000 IDPs remaining at end-2004, but the population includes heterogeneous displacement histories and does not identify the stock as a clean conflict/policy-attributable civilian-harm flow or stock under the frozen coding contract.",
            "coded_as_confirmatory_harm": False,
            "rule": "Preserve the quantitative source fact as screened context rather than weakening the attribution requirement."
        },
        "remaining_confirmatory_blockers": [
            "blind second-coder reliability/adjudication has not been completed for source-interpreted records",
            "manual web/PDF sources are not all immutable-byte-hash bound",
            "current Pineland harm components remain semantically incompatible with historical numeric harm",
            "UNAMA and UCDP civilian-death levels materially disagree and require explicit measurement-model treatment rather than averaging"
        ],
        "confirmatory_historical_harm_validation_authorized": False,
        "pineland_model_comparison_authorized": False,
        "historical_predictive_rescore_authorized": False,
        "parameter_fitting_authorized": False,
        "core_change_authorized": False,
        "next_licensed_step": "Freeze blind second-coder/adjudication rules and packet for the source-interpreted first-coder records; treat UCDP structured extraction as a separately hash-audited measurement family."
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
