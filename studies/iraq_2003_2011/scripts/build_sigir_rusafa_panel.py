"""Build the reproducible Rusafa anchor control/presence panel from SIGIR prose.

This is deliberately an anchor-observation artifact, not a fabricated national
control series.  The SIGIR report gives dated responsibility transitions but not
monthly neighborhood-level observations.  Months after the report's operational
window remain explicitly ``not_reported`` and cannot license a case run by
themselves.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from calendar import monthrange
from datetime import date
from pathlib import Path


SOURCE = "SIGIR Special Report Number 3, Interagency Rebuilding Efforts in Iraq: A Case Study of the Rusafa Political District"
SOURCE_URL = "https://www.govinfo.gov/content/pkg/GOVPUB-S-PURL-gpo36625/pdf/GOVPUB-S-PURL-gpo36625.pdf"
SOURCE_PDF_PAGE = 6  # zero-based PDF page containing the dated transition paragraph


def month_starts(start: date, end: date):
    cur = date(start.year, start.month, 1)
    while cur <= end:
        yield cur
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)


def observation_for(month: date) -> tuple[str, int, str]:
    """Return (responsibility, presence_evidence, evidence_status)."""
    if month < date(2003, 4, 1):
        return "not_reported_before_operational_window", 0, "not_reported"
    if month <= date(2004, 12, 1):
        return "us_army_primary", 1, "reported_transition_window"
    if month <= date(2006, 7, 1):
        return "iraqi_security_forces_primary_us_advisory", 1, "reported_transition_window"
    if month <= date(2006, 12, 1):
        return "us_army_primary_reassumed", 1, "reported_transition_window"
    if month <= date(2007, 4, 1):
        return "us_surge_primary", 1, "reported_transition_window"
    if month <= date(2008, 2, 1):
        return "shared_two_battalion_responsibility", 1, "reported_transition_window"
    if month <= date(2010, 12, 1):
        return "us_army_presence_improved_security", 1, "reported_transition_window"
    return "not_reported_after_report_window", 0, "not_reported"


def build(output: Path) -> dict:
    rows = []
    for month in month_starts(date(2003, 3, 1), date(2011, 12, 1)):
        responsibility, presence, status = observation_for(month)
        rows.append({
            "case_id": "iraq_2003_2011",
            "anchor_unit": "rusafa_political_district",
            "month": month.isoformat(),
            "control_responsibility": responsibility,
            "presence_evidence": presence,
            "evidence_status": status,
            "source": SOURCE,
            "source_url": SOURCE_URL,
            "source_pdf_page": SOURCE_PDF_PAGE,
            "date_precision": "month_from_reported_transition_boundaries" if status != "not_reported" else "not_reported",
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "schema_version": "1.0.0",
        "case_id": "iraq_2003_2011",
        "status": "anchor_control_panel_built_not_run_ready",
        "output": str(output.relative_to(output.parents[2])).replace("\\", "/"),
        "sha256": digest,
        "bytes": output.stat().st_size,
        "rows": len(rows),
        "observed_rows": sum(row["evidence_status"] != "not_reported" for row in rows),
        "not_reported_rows": sum(row["evidence_status"] == "not_reported" for row in rows),
        "source": SOURCE,
        "source_url": SOURCE_URL,
        "source_pdf_page": SOURCE_PDF_PAGE,
        "scope": "Rusafa anchor only; not a whole-country control proxy",
        "run_license": False,
        "limitation": "SIGIR reports dated responsibility transitions, not a complete monthly neighborhood panel; not_reported months remain explicit and require additional validation before any run.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("studies/iraq_2003_2011/data/processed/sigir_rusafa_control_presence_panel.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("studies/iraq_2003_2011/data/processed/sigir_rusafa_control_presence_manifest.json"))
    args = parser.parse_args()
    manifest = build(args.output)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
