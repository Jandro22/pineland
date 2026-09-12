from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/tfes_vnus/6212871/TFES.zip"
DOC = ROOT / "studies/research_program/source_cache/nara/vietnam_minimal_v1/tfes_vnus/6212871/152.1DP.pdf"
OUT_DIR = ROOT / "studies/vietnam_1955_1975/data/derived"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digits(text: str) -> int | None:
    s = text.strip()
    return int(s) if s and s.isdigit() else None


def training_month(raw: str) -> str | None:
    s = raw.strip()
    if len(s) != 4 or not s.isdigit() or s == "0000":
        return None
    mm, yy = int(s[:2]), int(s[2:])
    if not 1 <= mm <= 12:
        return None
    year = 1900 + yy
    if not 1960 <= year <= 1975:
        return None
    return f"{year:04d}-{mm:02d}-01"


def parse_unit(payload: bytes, report_month: str, record_sequence: int) -> dict:
    s = payload.decode("cp037", errors="replace")
    if len(payload) not in (608, 1059):
        raise ValueError(len(payload))
    district = s[0:5]
    eval_codes = s[16:36]
    problem_codes = s[36:56]
    assigned = [digits(s[590:593]), digits(s[593:596]), digits(s[596:599])]
    present = [digits(s[599:602]), digits(s[602:605]), digits(s[605:608])]
    assigned_total = sum(v or 0 for v in assigned)
    present_total = sum(v or 0 for v in present)
    row = {
        "record_sequence": record_sequence,
        "report_month": report_month,
        "payload_bytes": len(payload),
        "district_id": district,
        "corps_code": district[0:1],
        "province_code": district[1:3],
        "district_code": district[3:5],
        "unit_number": s[5:9],
        "unit_type": s[9:10],
        "unit_series": s[10:13],
        "record_type": s[13:15],
        "stat_code": s[15:16],
        "basic_training_month": training_month(s[56:60]),
        "refresher_training_month": training_month(s[60:64]),
        "motivational_training_month": training_month(s[64:68]),
        "revolutionary_development_training_month": training_month(s[68:72]),
        "officers_assigned": assigned[0],
        "nco_assigned": assigned[1],
        "enlisted_assigned": assigned[2],
        "officers_present": present[0],
        "nco_present": present[1],
        "enlisted_present": present[2],
        "assigned_total": assigned_total,
        "present_total": present_total,
        "manning_ratio": present_total / assigned_total if assigned_total > 0 else np.nan,
        "personnel_consistency_present_le_assigned": present_total <= assigned_total if assigned_total > 0 else None,
        "evaluation_raw": eval_codes,
        "problem_raw": problem_codes,
    }
    for i, letter in enumerate("ABCDEFGHIJKLMNOPQRST"):
        c = eval_codes[i : i + 1]
        row[f"eval_{letter.lower()}"] = int(c) if c.isdigit() and c != "0" else None
        c2 = problem_codes[i : i + 1]
        row[f"problem_{letter.lower()}"] = int(c2) if c2.isdigit() and c2 != "0" else None
    row["logical_unit_id"] = f"{district}:{row['unit_type']}:{row['unit_number']}:{row['unit_series']}"
    return row


def iter_records():
    with zipfile.ZipFile(SOURCE) as z:
        member = z.namelist()[0]
        with z.open(member) as f:
            record_sequence = 0
            block_count = 0
            report_month: str | None = None
            while True:
                bdw = f.read(4)
                if not bdw:
                    break
                if len(bdw) != 4 or bdw[2:] != b"\x00\x00":
                    raise ValueError(f"bad BDW at block {block_count + 1}: {bdw.hex()}")
                block_len = int.from_bytes(bdw[:2], "big")
                body = f.read(block_len - 4)
                if len(body) != block_len - 4:
                    raise ValueError("short VB block")
                block_count += 1
                pos = 0
                while pos < len(body):
                    if pos + 4 > len(body):
                        raise ValueError("short RDW")
                    rdw = body[pos : pos + 4]
                    record_len = int.from_bytes(rdw[:2], "big")
                    if rdw[2:] != b"\x00\x00" or record_len < 4 or pos + record_len > len(body):
                        raise ValueError(f"bad RDW block={block_count} pos={pos} value={rdw.hex()}")
                    payload = body[pos + 4 : pos + record_len]
                    pos += record_len
                    record_sequence += 1
                    if len(payload) == 27:
                        header = payload.decode("cp037", errors="strict")
                        yymm = header[15:19]
                        if len(yymm) != 4 or not yymm.isdigit() or not 1 <= int(yymm[2:]) <= 12:
                            raise ValueError(f"invalid monthly control record {header!r}")
                        report_month = f"19{yymm[:2]}-{yymm[2:]}-01"
                        yield "control", {"record_sequence": record_sequence, "report_month": report_month, "control_raw": header}
                    elif len(payload) in (608, 1059):
                        if report_month is None:
                            raise ValueError("unit record before monthly control record")
                        yield "unit", parse_unit(payload, report_month, record_sequence)
                    elif len(payload) == 1024:
                        yield "district", {"record_sequence": record_sequence, "report_month": report_month}
                    else:
                        raise ValueError(f"unexpected TFES payload length {len(payload)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ns = ap.parse_args()
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    unit_rows = []
    controls = []
    district_count = 0
    for kind, row in iter_records():
        if kind == "unit":
            unit_rows.append(row)
        elif kind == "control":
            controls.append(row)
        else:
            district_count += 1
    df = pd.DataFrame(unit_rows)
    ctl = pd.DataFrame(controls)
    expected = {"control": 25, "unit_608": 259_516, "unit_1059": 1_100, "district_1024": 8_437}
    observed = {
        "control": len(ctl),
        "unit_608": int((df.payload_bytes == 608).sum()),
        "unit_1059": int((df.payload_bytes == 1059).sum()),
        "district_1024": district_count,
    }
    if expected != observed:
        raise SystemExit(f"documented record counts mismatch expected={expected} observed={observed}")
    documented_months = [
        "1970-04-01", "1970-05-01", "1970-06-01", "1970-10-01", "1970-11-01", "1970-12-01",
        *[f"1971-{m:02d}-01" for m in range(1, 13)],
        *[f"1972-{m:02d}-01" for m in range(1, 8)],
    ]
    if ctl.report_month.tolist() != documented_months:
        raise SystemExit(f"monthly control sequence mismatch: {ctl.report_month.tolist()}")

    out = out_dir / "tfes_direct_unit_month_1970_1972.parquet"
    df.to_parquet(out, index=False, compression="zstd")
    control_out = out_dir / "tfes_direct_month_control_records.parquet"
    ctl.to_parquet(control_out, index=False, compression="zstd")

    active = df.stat_code.eq("0")
    denom = active & df.assigned_total.gt(0)
    inconsistent = denom & df.present_total.gt(df.assigned_total)
    duplicates = df.duplicated(["report_month", "logical_unit_id"], keep=False)
    manifest = {
        "schema_version": "pineland.vietnam_tfes_direct_parse.v1",
        "status": "DIRECT_NARA_PARSED",
        "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": sha256(SOURCE),
        "documentation": str(DOC.relative_to(ROOT)).replace("\\", "/"),
        "documentation_sha256": sha256(DOC),
        "vb_integrity": {
            "expected_record_counts": expected,
            "observed_record_counts": observed,
            "monthly_control_sequence_exact": True,
            "monthly_controls": ctl.report_month.tolist()
        },
        "unit_coverage": {
            "rows": len(df),
            "logical_units": int(df.logical_unit_id.nunique()),
            "report_months": int(df.report_month.nunique()),
            "unit_type_counts": {str(k): int(v) for k, v in df.unit_type.value_counts(dropna=False).items()},
            "stat_code_counts": {str(k): int(v) for k, v in df.stat_code.value_counts(dropna=False).items()},
            "duplicate_logical_unit_month_rows": int(duplicates.sum()),
        },
        "personnel_quality": {
            "active_rows_with_positive_assigned_strength": int(denom.sum()),
            "active_rows_present_gt_assigned": int(inconsistent.sum()),
            "active_rows_present_gt_assigned_fraction": float(inconsistent.sum() / max(1, denom.sum())),
            "policy": "preserve source values; do not cap manning ratio; analyses requiring bounded manning must preregister an exclusion/sensitivity rule"
        },
        "outputs": [
            {"path": str(out.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(out), "bytes": out.stat().st_size},
            {"path": str(control_out.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(control_out), "bytes": control_out.stat().st_size}
        ],
        "field_guard": "Evaluation codes and training dates are preserved as archival measurements. No composite effectiveness/veterancy index is created by this parser."
    }
    mp = out_dir / "tfes_direct_unit_month_1970_1972_manifest.json"
    mp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
