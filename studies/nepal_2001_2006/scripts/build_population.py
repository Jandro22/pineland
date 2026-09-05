"""Extract district denominators from the official 2001 census HTML table."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "nepal_2001_2006"
SOURCE = STUDY / "data" / "raw" / "census2001" / "html" / "fr1" / "tab1.htm"
DISTRICTS = STUDY / "config" / "districts.csv"
OUT = STUDY / "data" / "processed" / "population_2001.csv"
ALIASES = {
    "Chitawan": "Chitwan", "Dhanusa": "Dhanusha", "Kapilbastu": "Kapilvastu",
    "Tanahu": "Tanahun",
}


def main() -> None:
    registry = {row["district_name"]: row for row in csv.DictReader(DISTRICTS.open(encoding="utf-8"))}
    extracted: dict[str, dict[str, object]] = {}
    for table in pd.read_html(SOURCE):
        for _, row in table.iloc[4:].iterrows():
            raw_name = str(row.iloc[0]).strip()
            affected = raw_name.endswith("*")
            name = ALIASES.get(raw_name.rstrip("*"), raw_name.rstrip("*"))
            if name not in registry:
                continue
            extracted[name] = {
                "district_id": registry[name]["district_id"],
                "district_name": name,
                "population_2001": int(row.iloc[1]),
                "census_area_km2": float(row.iloc[7]),
                "enumeration_affected": affected,
                "source_table": "National Census 2001 National Report fr1/tab1.htm",
            }
    missing = sorted(set(registry) - set(extracted))
    if missing or len(extracted) != 75:
        raise RuntimeError({"rows": len(extracted), "missing": missing})
    frame = pd.DataFrame(extracted.values()).sort_values("district_id")
    frame.to_csv(OUT, index=False)
    print({
        "districts": len(frame), "population": int(frame.population_2001.sum()),
        "affected_districts": int(frame.enumeration_affected.sum()),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    })


if __name__ == "__main__":
    main()
