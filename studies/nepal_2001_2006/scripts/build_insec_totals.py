"""Extract auditable district totals from INSEC's linked complete report.

The report is cumulative for the 1996-02-13--2006-11-21 conflict.  It is kept
as an independent spatial cross-check only; it is not merged into the
district-week UCDP target.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import fitz
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
PDF = STUDY / "data" / "raw" / "insec_total.pdf"
DISTRICTS = STUDY / "config" / "districts.csv"
OUT = STUDY / "data" / "processed" / "insec_district_totals.csv"
MANIFEST = STUDY / "data" / "processed" / "insec_manifest.json"

# The PDF's historical table order is stable and its Nepali OCR text is not
# a reliable key. Mustang is absent from the report table and remains missing,
# not an imputed zero.
PDF_ORDER = [
    "Jhapa", "Ilam", "Panchthar", "Taplejung", "Morang", "Sunsari", "Dhankuta",
    "Terhathum", "Bhojpur", "Sankhuwasabha", "Saptari", "Siraha", "Udayapur",
    "Khotang", "Okhaldhunga", "Solukhumbu", "Dhanusha", "Mahottari", "Sarlahi",
    "Sindhuli", "Ramechhap", "Dolakha", "Rautahat", "Bara", "Parsa", "Chitwan",
    "Makwanpur", "Lalitpur", "Kavrepalanchok", "Bhaktapur", "Kathmandu", "Dhading",
    "Sindhupalchok", "Nuwakot", "Rasuwa", "Tanahun", "Gorkha", "Lamjung", "Syangja",
    "Kaski", "Manang", "Nawalparasi", "Rupandehi", "Palpa", "Kapilvastu", "Arghakhanchi",
    "Gulmi", "Baglung", "Parbat", "Myagdi", "Dang", "Pyuthan", "Rolpa", "Salyan",
    "Rukum", "Banke", "Bardiya", "Surkhet", "Jajarkot", "Dailekh", "Dolpa", "Jumla",
    "Kalikot", "Mugu", "Humla", "Kailali", "Achham", "Doti", "Bajura", "Bajhang",
    "Kanchanpur", "Dadeldhura", "Baitadi", "Darchula",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_rows() -> list[dict]:
    text = "\n".join(page.get_text() for page in fitz.open(PDF)[:2])
    rows, current = [], None
    for line in text.splitlines():
        match = re.match(r"^(\d+)\s+(.*)$", line)
        if match and 1 <= int(match.group(1)) <= 74:
            if current is not None:
                rows.append(current)
            current = {"number": int(match.group(1)), "tokens": []}
        elif current is not None and line.strip():
            current["tokens"].append(line.strip())
    if current is not None:
        rows.append(current)
    if len(rows) != 74 or [row["number"] for row in rows] != list(range(1, 75)):
        raise RuntimeError("INSEC PDF row markers were not parsed exactly")
    values = []
    for row in rows:
        numbers = [int(token) for token in row["tokens"] if re.fullmatch(r"\d+", token)]
        # Row 74 is followed by grand totals; the district total is the third
        # numeric value (the first four values are its own cells).
        total = numbers[-1] if row["number"] < 74 else numbers[2]
        values.append(total)
    return [{"pdf_row": index, "district_name": name, "victim_total_cumulative": total,
             "source_period": "1996-02-13 through 2006-11-21", "source_status": "observed"}
            for index, (name, total) in enumerate(zip(PDF_ORDER, values), 1)]


def main() -> None:
    if not PDF.exists():
        raise SystemExit(f"missing downloaded source: {PDF}")
    districts = pd.read_csv(DISTRICTS)
    rows = pd.DataFrame(extract_rows())
    rows = rows.merge(districts[["district_id", "district_name"]], on="district_name", how="left", validate="one_to_one")
    if rows.district_id.isna().any():
        raise RuntimeError(f"unmatched INSEC districts: {rows[rows.district_id.isna()].district_name.tolist()}")
    missing = districts.loc[~districts.district_id.isin(rows.district_id), ["district_id", "district_name"]].copy()
    missing["pdf_row"] = None; missing["victim_total_cumulative"] = None
    missing["source_period"] = "1996-02-13 through 2006-11-21"; missing["source_status"] = "not_listed_in_report"
    missing = missing[rows.columns]
    rows = pd.concat([rows, missing], ignore_index=True).sort_values("district_id")
    rows.to_csv(OUT, index=False)
    manifest = {"schema_version": "1.0.0", "source_id": "insec_complete_report",
                "source_url": "https://www.insec.org.np/victim/reports/total.pdf",
                "source_license_note": "INSEC page states non-profit use with due acknowledgement",
                "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                "pdf_sha256": sha256(PDF), "pdf_pages": len(fitz.open(PDF)),
                "extractor": f"PyMuPDF {fitz.version[0]}",
                "districts_observed": int((rows.source_status == "observed").sum()),
                "districts_not_listed": int((rows.source_status != "observed").sum()),
                "period": "1996-02-13 through 2006-11-21",
                "comparability": "cumulative district totals; spatial cross-check only, not district-week target"}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
