"""Extract the preregistered UCDP GED 26.1 civilian-death cross-check.

This script is measurement-only.  It never reads Pineland predictions or model
state and never edits the frozen case event panels.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "studies/research_program"
CONTRACT = PROGRAM / "civilian_harm_ucdp_crosscheck_contract_v1.json"
FIRST_CODER = PROGRAM / "civilian_harm_first_coder_v1.csv"
EVENT_OUT = PROGRAM / "civilian_harm_ucdp_event_crosscheck_v1.csv"
ANNUAL_OUT = PROGRAM / "civilian_harm_ucdp_annual_crosscheck_v1.csv"
AUDIT_OUT = PROGRAM / "civilian_harm_ucdp_overlap_audit_v1.json"

ARCHIVES = {
    "nepal_2001_2006": ROOT / "studies/nepal_2001_2006/data/raw/ged261-csv.zip",
    "afghanistan_2004_2021": ROOT / "studies/afghanistan_2004_2021/data/raw/ged261-csv.zip",
}

EVENT_FIELDS = [
    "case_id", "ucdp_event_id", "date_start", "date_end", "date_prec",
    "where_prec", "where_coordinates", "adm_1", "adm_2", "side_a", "side_b",
    "type_of_violence", "deaths_civilians", "source_article", "source_original",
    "full_interval_inside_case", "single_calendar_year", "annual_countable",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def raw_rows(archive: Path):
    with zipfile.ZipFile(archive) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RuntimeError(f"expected one CSV in {archive}, got {csv_names}")
        with zf.open(csv_names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            yield from csv.DictReader(text)


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    expected_sha = contract["source"]["archive_sha256"]

    event_rows: list[dict[str, str]] = []
    archive_hashes: dict[str, str] = {}
    for case_id, archive in ARCHIVES.items():
        actual_sha = sha256(archive)
        archive_hashes[case_id] = actual_sha
        if actual_sha != expected_sha:
            raise RuntimeError(f"archive hash mismatch for {case_id}: {actual_sha}")

        spec = contract["case_filters"][case_id]
        case_start = parse_date(spec["date_start"])
        case_end = parse_date(spec["date_end"])
        country = spec["country"]
        for row in raw_rows(archive):
            if row.get("country") != country:
                continue
            ds = parse_date(row["date_start"])
            de = parse_date(row["date_end"])
            if de < case_start or ds > case_end:
                continue
            civ = int(float(row.get("deaths_civilians") or 0))
            inside = ds >= case_start and de <= case_end
            one_year = ds.year == de.year
            annual_countable = inside and one_year
            event_rows.append({
                "case_id": case_id,
                "ucdp_event_id": row.get("id", ""),
                "date_start": row["date_start"],
                "date_end": row["date_end"],
                "date_prec": row.get("date_prec", ""),
                "where_prec": row.get("where_prec", ""),
                "where_coordinates": row.get("where_coordinates", ""),
                "adm_1": row.get("adm_1", ""),
                "adm_2": row.get("adm_2", ""),
                "side_a": row.get("side_a", ""),
                "side_b": row.get("side_b", ""),
                "type_of_violence": row.get("type_of_violence", ""),
                "deaths_civilians": str(civ),
                "source_article": row.get("source_article", ""),
                "source_original": row.get("source_original", ""),
                "full_interval_inside_case": str(inside).lower(),
                "single_calendar_year": str(one_year).lower(),
                "annual_countable": str(annual_countable).lower(),
            })

    event_rows.sort(key=lambda r: (r["case_id"], r["date_start"], r["ucdp_event_id"]))
    with EVENT_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        w.writeheader()
        w.writerows(event_rows)

    annual: dict[tuple[str, int], dict[str, int]] = {}
    for row in event_rows:
        if row["annual_countable"] != "true":
            continue
        year = parse_date(row["date_start"]).year
        cell = annual.setdefault((row["case_id"], year), {
            "event_count": 0, "positive_civilian_death_event_count": 0,
            "civilian_deaths": 0,
        })
        cell["event_count"] += 1
        value = int(row["deaths_civilians"])
        cell["civilian_deaths"] += value
        cell["positive_civilian_death_event_count"] += int(value > 0)

    annual_fields = [
        "case_id", "year", "window_status", "ucdp_event_count",
        "ucdp_positive_civilian_death_event_count", "ucdp_civilian_deaths",
    ]
    annual_rows = []
    for (case_id, year), cell in sorted(annual.items()):
        partial = (
            (case_id == "nepal_2001_2006" and year == 2001) or
            (case_id == "afghanistan_2004_2021" and year == 2021)
        )
        annual_rows.append({
            "case_id": case_id,
            "year": year,
            "window_status": "partial_case_year" if partial else "full_case_year",
            "ucdp_event_count": cell["event_count"],
            "ucdp_positive_civilian_death_event_count": cell["positive_civilian_death_event_count"],
            "ucdp_civilian_deaths": cell["civilian_deaths"],
        })
    with ANNUAL_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=annual_fields)
        w.writeheader()
        w.writerows(annual_rows)

    # Measurement overlap only: use existing first-coder UNAMA annual death
    # totals whose interval exactly spans a calendar year.  No model values.
    unama_by_year: dict[int, int] = {}
    if FIRST_CODER.exists():
        with FIRST_CODER.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["case_id"] != "afghanistan_2004_2021":
                    continue
                if row["source_family"] != "UNAMA_OHCHR_civilian_casualty_monitoring":
                    continue
                if row["component"] != "direct_harm" or row["measure"] != "civilian_deaths":
                    continue
                ds = parse_date(row["date_start"])
                de = parse_date(row["date_end"])
                if ds.month == 1 and ds.day == 1 and de.month == 12 and de.day == 31 and ds.year == de.year:
                    if row["value_point"]:
                        unama_by_year[ds.year] = int(float(row["value_point"]))

    afg_ucdp_by_year = {
        int(r["year"]): int(r["ucdp_civilian_deaths"])
        for r in annual_rows
        if r["case_id"] == "afghanistan_2004_2021" and r["window_status"] == "full_case_year"
    }
    matched = []
    for year in sorted(set(unama_by_year) & set(afg_ucdp_by_year)):
        u = afg_ucdp_by_year[year]
        n = unama_by_year[year]
        matched.append({
            "year": year,
            "ucdp_civilian_deaths": u,
            "unama_civilian_deaths": n,
            "ucdp_to_unama_ratio": (u / n) if n else None,
        })

    ambiguous = [r for r in event_rows if r["annual_countable"] != "true"]
    positive = [r for r in event_rows if int(r["deaths_civilians"]) > 0]
    payload = {
        "schema_version": "pineland.civilian_harm_ucdp_overlap_audit.v1",
        "status": "independent_measurement_crosscheck_not_model_scoring",
        "contract_sha256": sha256(CONTRACT),
        "archive_hashes": archive_hashes,
        "event_output_sha256": sha256(EVENT_OUT),
        "annual_output_sha256": sha256(ANNUAL_OUT),
        "event_counts": {
            case_id: sum(r["case_id"] == case_id for r in event_rows)
            for case_id in ARCHIVES
        },
        "positive_civilian_death_event_counts": {
            case_id: sum(r["case_id"] == case_id for r in positive)
            for case_id in ARCHIVES
        },
        "boundary_or_year_crossing_event_count": len(ambiguous),
        "matched_full_year_afghanistan_unama_ucdp": matched,
        "matched_full_year_count": len(matched),
        "no_posthoc_success_threshold": True,
        "interpretation": (
            "UCDP GED deaths_civilians is an independent structured civilian-death measurement family. "
            "Agreement or disagreement with UNAMA/OHCHR is a measurement-concordance result only and does not score Pineland."
        ),
        "historical_predictive_rescore_authorized": False,
        "pineland_model_comparison_authorized": False,
        "parameter_fitting_authorized": False,
        "core_change_authorized": False,
    }
    AUDIT_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
