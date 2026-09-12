from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/tfes_vnus/6212873/RG349.VNUS.J71A72.gz"
DOC = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/tfes_vnus/6212873/152.1DP.pdf"
OUT_DIR = ROOT / "studies/vietnam_1955_1975/data/derived"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def integer(s: str) -> int | None:
    s = s.strip()
    return int(s) if s and s.isdigit() else None


def parse_line(line: str, n: int) -> dict:
    if len(line) != 80:
        raise ValueError(f"line {n}: expected 80 chars, got {len(line)}")
    corps, province, district = line[0], line[1:3], line[3:5]
    day = integer(line[61:63])
    month = integer(line[63:65])
    year2 = integer(line[65:67])
    date_valid = (
        day is not None and month is not None and year2 is not None
        and 1 <= day <= 31 and 1 <= month <= 12
        and year2 in {71, 72}
    )
    year = 1900 + year2 if year2 is not None else None
    return {
        "record_number": n,
        "district_id": f"{corps}{province}{district}",
        "corps_code": corps,
        "province_code": province,
        "district_code": district,
        "unit_type": line[5:6],
        "unit_id_3": line[6:9],
        "unit_nomenclature": line[9:23].strip(),
        "friendly_kia": integer(line[23:26]),
        "friendly_wia": integer(line[26:29]),
        "friendly_mia": integer(line[29:32]),
        "friendly_deserted": integer(line[32:35]),
        "enemy_kia": integer(line[35:38]),
        "enemy_captured": integer(line[38:41]),
        "weapons_lost_individual": integer(line[41:43]),
        "weapons_lost_crew_served": integer(line[43:45]),
        "weapons_captured_individual": integer(line[45:47]),
        "weapons_captured_crew_served": integer(line[47:49]),
        "day_night_operations_total": integer(line[49:52]),
        "day_night_operations_with_contact": integer(line[52:55]),
        "night_operations_total": integer(line[55:58]),
        "night_operations_with_contact": integer(line[58:61]),
        "day": day,
        "month": month,
        "year": year,
        "report_date": f"{year:04d}-{month:02d}-{day:02d}" if date_valid else None,
        "date_status": "valid_source_date" if date_valid else "invalid_source_date_preserved",
        "raw_date_field": line[61:67],
        "pri_la": line[78:79].strip(),
        "logical_unit_id_vnus": f"{corps}{province}{district}:{line[5:6]}:{line[6:9]}",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ns = ap.parse_args()
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = gzip.open(SOURCE, "rb").read()
    lines = raw.splitlines()
    if len(lines) != 103_624:
        raise SystemExit(f"documented VNUS count 103624 != observed {len(lines)}")
    if {len(x) for x in lines} != {80}:
        raise SystemExit(f"unexpected VNUS line widths {sorted({len(x) for x in lines})}")
    df = pd.DataFrame(parse_line(line.decode("ascii", errors="strict"), i) for i, line in enumerate(lines, 1))
    out = out_dir / "vnus_direct_unit_month_1971_1972.parquet"
    df.to_parquet(out, index=False, compression="zstd")

    valid_dates = pd.to_datetime(df.loc[df.date_status.eq("valid_source_date"), "report_date"])
    manifest = {
        "schema_version": "pineland.vietnam_vnus_direct_parse.v1",
        "status": "DIRECT_NARA_PARSED",
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha256(SOURCE),
        "source_uncompressed_bytes": len(raw),
        "documentation": str(DOC.relative_to(ROOT)).replace("\\", "/"),
        "documentation_sha256": sha256(DOC),
        "integrity": {
            "documented_rows": 103_624,
            "observed_rows": len(df),
            "line_width_exact_80": True,
            "min_report_date": str(valid_dates.min().date()),
            "max_report_date": str(valid_dates.max().date()),
            "report_months": int(valid_dates.dt.to_period("M").nunique()),
            "logical_units": int(df.logical_unit_id_vnus.nunique()),
            "duplicate_unit_report_dates": int(df[df.report_date.notna()].duplicated(["logical_unit_id_vnus", "report_date"]).sum()),
            "invalid_source_date_rows": int(df.date_status.eq("invalid_source_date_preserved").sum()),
            "invalid_source_date_records": df.loc[df.date_status.eq("invalid_source_date_preserved"), ["record_number", "logical_unit_id_vnus", "raw_date_field"]].to_dict(orient="records")
        },
        "output": str(out.relative_to(ROOT)).replace("\\", "/"),
        "output_sha256": sha256(out),
        "output_bytes": out.stat().st_size,
        "guard": "Direct archival operations/casualty process. Body counts and operational reporting have source-specific measurement error; no field is treated as ground truth without sensitivity analysis."
    }
    mp = out_dir / "vnus_direct_unit_month_1971_1972_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
