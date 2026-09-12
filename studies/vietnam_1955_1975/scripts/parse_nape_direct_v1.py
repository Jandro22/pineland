from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/nape/24746974/RG330.NAPE.Y6971.gz"
DOC = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/nape/24746974/291.1DP.pdf"
OUT_DIR = ROOT / "studies/vietnam_1955_1975/data/derived"
RECORD_BYTES = 87


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text(raw: bytes) -> str:
    return raw.decode("cp037").strip()


def zoned_decimal(raw: bytes) -> int | None:
    if not raw or all(b in (0x40, 0x00) for b in raw):
        return None
    digits: list[str] = []
    for b in raw:
        digit = b & 0x0F
        if digit > 9:
            raise ValueError(f"invalid zoned-decimal byte 0x{b:02X}")
        digits.append(str(digit))
    zone = (raw[-1] >> 4) & 0x0F
    sign = -1 if zone in (0xD, 0xE) else 1
    return sign * int("".join(digits))


FUNCTION_FIELDS = [
    ("judicial_police", 14, 18),
    ("traffic_order_police", 18, 22),
    ("administrative_investigation_police", 22, 26),
    ("immigration_foreign_control_police", 26, 30),
    ("identification_service_police", 30, 34),
    ("scientific_police", 34, 38),
    ("special_police", 38, 42),
    ("resource_control_police", 42, 46),
    ("national_police_field_force", 46, 50),
    ("marine_police", 50, 54),
    ("other_police", 54, 58),
]


def parse_record(raw: bytes, record_number: int) -> dict:
    if len(raw) != RECORD_BYTES:
        raise ValueError(f"record {record_number}: {len(raw)} bytes, expected 87")
    nepid = text(raw[0:9])
    yymm = text(raw[9:13])
    rectp = text(raw[13:14])
    if len(nepid) != 9 or not nepid.isdigit():
        raise ValueError(f"record {record_number}: invalid NAPE ID {nepid!r}")
    if len(yymm) != 4 or not yymm.isdigit():
        raise ValueError(f"record {record_number}: invalid YYMM {yymm!r}")
    yy, mm = int(yymm[:2]), int(yymm[2:])
    if not 1 <= mm <= 12:
        raise ValueError(f"record {record_number}: invalid month {mm}")
    year = 1900 + yy
    if rectp not in {"0", "1", "2"}:
        raise ValueError(f"record {record_number}: invalid record type {rectp!r}")

    row = {
        "record_number": record_number,
        "nape_id": nepid,
        "date": f"{year:04d}-{mm:02d}-01",
        "year": year,
        "month": mm,
        "record_type": int(rectp),
        "corps_code": nepid[0],
        "province_code": nepid[1:3],
        "district_code": nepid[3:5],
        "village_code": nepid[5:7],
        "hamlet_code": nepid[7:9],
    }
    for name, a, b in FUNCTION_FIELDS:
        row[name] = zoned_decimal(raw[a:b]) if rectp == "0" else None
    row["detachment_nape_id"] = text(raw[58:67]) if rectp == "1" else None
    row["police_function_code"] = text(raw[67:70]) if rectp == "1" else None
    row["detached_strength"] = zoned_decimal(raw[70:74]) if rectp == "1" else None
    row["rural_assignment_nape_id"] = text(raw[74:83]) if rectp == "2" else None
    row["assigned_strength_rural"] = zoned_decimal(raw[83:87]) if rectp == "2" else None
    if rectp == "0":
        row["total_function_strength"] = sum((row[name] or 0) for name, _, _ in FUNCTION_FIELDS)
    else:
        row["total_function_strength"] = None
    row["is_corps_aggregate"] = nepid[1:] == "00000000"
    row["is_province_aggregate"] = nepid[1:3] != "00" and nepid[3:] == "000000"
    row["is_district_aggregate"] = nepid[3:5] != "00" and nepid[5:] == "0000"
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ns = ap.parse_args()
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = gzip.open(SOURCE, "rb").read()
    if len(raw) % RECORD_BYTES:
        raise SystemExit(f"source length {len(raw)} is not divisible by {RECORD_BYTES}")
    rows = [parse_record(raw[i : i + RECORD_BYTES], n) for n, i in enumerate(range(0, len(raw), RECORD_BYTES), 1)]
    df = pd.DataFrame(rows)
    expected_records = 31_473
    if len(df) != expected_records:
        raise SystemExit(f"expected {expected_records} documented records, got {len(df)}")

    if df.duplicated(["nape_id", "date", "record_type", "record_number"]).any():
        raise SystemExit("record-number identity duplicate")
    strengths = [c for c in df.columns if c.endswith("_police") or c in {"national_police_field_force", "total_function_strength", "detached_strength", "assigned_strength_rural"}]
    negative = {c: int((pd.to_numeric(df[c], errors="coerce") < 0).sum()) for c in strengths}

    out = out_dir / "nape_direct_1969_1971.parquet"
    df.to_parquet(out, index=False, compression="zstd")
    manifest = {
        "schema_version": "pineland.vietnam_nape_direct_parse.v1",
        "status": "DIRECT_NARA_PARSED",
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_stored_sha256": sha256(SOURCE),
        "source_uncompressed_bytes": len(raw),
        "documentation": str(DOC.relative_to(ROOT)).replace("\\", "/"),
        "documentation_sha256": sha256(DOC),
        "layout": {
            "record_bytes": RECORD_BYTES,
            "documented_record_count": expected_records,
            "observed_record_count": len(df),
            "control_fields": {"nape_id": "1-9", "date_yymm": "10-13", "record_type": "14"},
            "strength_by_function": "15-58 for record type 0",
            "detachment": "59-74 for record type 1",
            "rural_assignment": "75-87 for record type 2"
        },
        "coverage": {
            "min_date": str(pd.to_datetime(df.date).min().date()),
            "max_date": str(pd.to_datetime(df.date).max().date()),
            "record_type_counts": {str(k): int(v) for k, v in df.record_type.value_counts().sort_index().items()},
            "unique_nape_ids": int(df.nape_id.nunique()),
            "province_aggregate_type0_rows": int((df.is_province_aggregate & df.record_type.eq(0)).sum()),
            "district_aggregate_type0_rows": int((df.is_district_aggregate & df.record_type.eq(0)).sum())
        },
        "validation": {
            "byte_length_exactly_31473_x_87": len(raw) == expected_records * RECORD_BYTES,
            "negative_strength_counts": negative,
            "all_record_types_valid": sorted(df.record_type.unique().tolist()) == [0, 1, 2]
        },
        "output": str(out.relative_to(ROOT)).replace("\\", "/"),
        "output_sha256": sha256(out),
        "output_bytes": out.stat().st_size,
        "guard": "Direct archival personnel/deployment quantities. These records do not measure police professionalism or effectiveness."
    }
    mp = out_dir / "nape_direct_1969_1971_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
