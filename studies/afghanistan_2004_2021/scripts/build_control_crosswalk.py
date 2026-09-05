"""Build the SIGAR/USFOR-A October 2017 407-to-401 control crosswalk.

The source is the declassified addendum to SIGAR's January 2018 quarterly
report.  The benchmark geography is the frozen 401-district COD/FEWS-style
surface already built for this study.  No control observation is inferred
from violence.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
RAW_PDF = ROOT / "data" / "raw" / "sigar_2018_01_30_addendum.pdf"
DISTRICTS = ROOT / "data" / "processed" / "districts.csv"
OUT_407 = ROOT / "data" / "processed" / "sigar_oct2017_control_407.csv"
OUT_XWALK = ROOT / "data" / "processed" / "sigar_407_to_401_crosswalk.csv"
OUT_401 = ROOT / "data" / "processed" / "sigar_oct2017_control_401.csv"

STATUSES = (
    "GIRoA Control",
    "GIRoA Influence",
    "INS Control",
    "INS Influence",
    "Contested",
)
CONTROL_SCORE = {
    "INS Control": 0.0,
    "INS Influence": 0.25,
    "Contested": 0.5,
    "GIRoA Influence": 0.75,
    "GIRoA Control": 1.0,
}

PROVINCE_ALIAS = {
    "wardak": "Maidan Wardak",
    "panjshayr": "Panjsher",
    "paktiya": "Paktya",
    "jowzjan": "Jawzjan",
    "herat": "Hirat",
    "helmand": "Hilmand",
    "uruzgan": "Uruzgan",
    "faryab": "Faryab",
}

# Temporary/split districts on the 407-unit RS surface.  The parent relations
# are documented in the Afghanistan administrative-boundary extension notes
# (AGCHO-derived 419-district layer); these rows intentionally share a 401
# target with the parent district's own RS observation.
SPLIT_CHILDREN = {
    ("Hilmand", "Marjah"): "AF3002",          # Nad-e-Ali
    ("Kandahar", "Dand"): "AF2701",          # Kandahar City
    ("Laghman", "Bad Pash"): "AF0701",       # Mehtarlam
    ("Nimroz", "Delaram"): "AF3405",         # Khashrod
    ("Paktya", "Lajah Mangal"): "AF1308",    # Lija Ahmad Khel
    ("Paktya", "Mirzakah"): "AF1306",        # Sayed Karam
    ("Panjsher", "Abshar"): "AF0803",        # Darah
}

# Same substantive districts placed in a different province by the two
# administrative snapshots.
ADMIN_TRANSFER = {
    ("Balkh", "Khulm"): "AF2008",       # benchmark: Samangan / Khulm
    ("Daykundi", "Gizab"): "AF2507",    # benchmark: Uruzgan / Gizab
}

# Explicit historical/spelling aliases.  These are naming changes, not
# substantive geographic merges.
NAME_ALIAS = {
    ("Badakhshan", "Kishim"): "Keshem",
    ("Badakhshan", "Zaybak"): "Zebak",
    ("Daykundi", "Gayti"): "Kiti",
    ("Ghazni", "Bahram-e Shahid"): "Jaghatu",
    ("Ghazni", "Bahram-e Shahid (Jaghatu)"): "Jaghatu",
    ("Ghazni", "Wali Muhammad"): "Wal-e-Muhammad-e-Shahid",
    ("Ghazni", "Wali Muhammad Shahid Khug yani"): "Wal-e-Muhammad-e-Shahid",
    ("Ghor", "Chaghcharan"): "Feroz Koh",
    ("Hilmand", "Dishu"): "Deh-e-Shu",
    ("Kabul", "Istalif"): "Estalef",
    ("Kandahar", "Registan"): "Reg",
    ("Kandahar", "Zharey"): "Zheray",
    ("Khost", "Khost"): "Matun",
    ("Kunar", "Shigal wa Sheltan"): "Shigal",
    ("Kunar", "Tsowkey"): "Chawkay",
    ("Paktika", "Nikeh"): "Nika",
    ("Panjsher", "Unabah"): "Anawa",
    ("Parwan", "Sayyid Khayl"): "Sayed Khel",
    ("Parwan", "Siahgird Ghorband"): "Ghorband",
    ("Takhar", "Ishkamish"): "Eshkmesh",
}


def _clean(value: str) -> str:
    return " ".join(value.replace("\ufffd", "").split())


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", _clean(value))
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def _read_401() -> list[dict[str, str]]:
    with DISTRICTS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _parse_407(cod_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not RAW_PDF.exists():
        raise FileNotFoundError(
            f"missing {RAW_PDF}; download the declassified SIGAR addendum first"
        )
    reader = PdfReader(RAW_PDF)
    canonical_provinces = {_norm(row["province_name"]): row["province_name"]
                           for row in cod_rows}
    rows: list[dict[str, object]] = []
    # PDF pages 7-17 (zero-indexed 6:17) are the 407-row district table.
    for page_index in range(6, 17):
        text = reader.pages[page_index].extract_text(extraction_mode="layout") or ""
        lines = text.splitlines()
        for line_index, line in enumerate(lines):
            status = next((item for item in STATUSES if item in line), None)
            if status is None:
                continue
            split_at = line.index(status)
            prefix = line[:split_at]
            raw_province = _clean(prefix[:20])
            district = _clean(prefix[20:])
            # A few district names wrap onto a second physical PDF line
            # (Kapisa's two Kohistan districts and Wardak's Hesa-e-Awal-e
            # Behsud).  Join only a blank-province/non-numeric continuation;
            # never infer a missing name from fuzzy matching.
            if line_index + 1 < len(lines):
                continuation = lines[line_index + 1]
                continuation_province = _clean(continuation[:20])
                continuation_district = _clean(continuation[20:48])
                continuation_tail = continuation[48:]
                if (
                    not continuation_province
                    and continuation_district
                    and re.search(r"[A-Za-z]", continuation_district)
                    and not re.search(r"\d", continuation_tail)
                ):
                    district = _clean(f"{district} {continuation_district}")
            numbers = re.findall(r"[\d,]+", line[split_at + len(status):])
            if len(numbers) < 2:
                raise ValueError(f"could not parse SIGAR numeric columns: {line!r}")
            province_key = _norm(raw_province)
            province = PROVINCE_ALIAS.get(
                province_key, canonical_provinces.get(province_key, raw_province)
            )
            rows.append({
                "sigar_row": len(rows) + 1,
                "province": province,
                "district": district,
                "status": status,
                "government_control_index": CONTROL_SCORE[status],
                "landmass_sq_km": int(numbers[0].replace(",", "")),
                "population": int(numbers[1].replace(",", "")),
            })
    if len(rows) != 407:
        raise AssertionError(f"expected 407 SIGAR rows, parsed {len(rows)}")
    return rows


def _assign(rows: list[dict[str, object]],
            cod_rows: list[dict[str, str]]) -> dict[int, tuple[str, str, float]]:
    assignments: dict[int, tuple[str, str, float]] = {}
    used_one_to_one: set[str] = set()

    for index, row in enumerate(rows):
        key = (str(row["province"]), str(row["district"]))
        if key in SPLIT_CHILDREN:
            # Deliberately do not reserve the parent: its own 407 row must map
            # to the same 401 unit.
            assignments[index] = (SPLIT_CHILDREN[key], "split_child_to_parent", 1.0)
        elif key in ADMIN_TRANSFER:
            target = ADMIN_TRANSFER[key]
            assignments[index] = (target, "same_district_admin_transfer", 1.0)
            used_one_to_one.add(target)

    # First consume normalized exact and explicit historical-name matches.
    for index, row in enumerate(rows):
        if index in assignments:
            continue
        province = str(row["province"])
        district = str(row["district"])
        target_name = NAME_ALIAS.get((province, district), district)
        candidates = [
            item for item in cod_rows
            if item["province_name"] == province
            and item["district_id"] not in used_one_to_one
            and item["district_id"] != "AF2409"  # Patoo: no Oct-2017 RS row.
        ]
        exact = [item for item in candidates
                 if _norm(item["district_name"]) == _norm(target_name)]
        if len(exact) == 1:
            target = exact[0]["district_id"]
            method = "historical_name_alias" if target_name != district else "normalized_exact"
            assignments[index] = (target, method, 1.0)
            used_one_to_one.add(target)

    # Remaining spelling variants are globally greedily paired within province.
    # By this stage all substantive aliases/splits/transfers are already fixed;
    # the residual candidates are orthographic variants only.
    pairs: list[tuple[float, int, str]] = []
    for index, row in enumerate(rows):
        if index in assignments:
            continue
        for candidate in cod_rows:
            if (candidate["province_name"] != row["province"]
                    or candidate["district_id"] in used_one_to_one
                    or candidate["district_id"] == "AF2409"):
                continue
            score = SequenceMatcher(
                None, _norm(str(row["district"])), _norm(candidate["district_name"])
            ).ratio()
            pairs.append((score, index, candidate["district_id"]))
    for score, index, district_id in sorted(pairs, reverse=True):
        if index in assignments or district_id in used_one_to_one:
            continue
        if score < 0.68:
            continue
        assignments[index] = (district_id, "unique_spelling_match", score)
        used_one_to_one.add(district_id)

    if len(assignments) != 407:
        missing = [rows[index] for index in range(len(rows)) if index not in assignments]
        raise AssertionError(f"unmapped SIGAR source rows: {missing}")
    unique_targets = {item[0] for item in assignments.values()}
    missing_targets = [
        item["district_id"] for item in cod_rows if item["district_id"] not in unique_targets
    ]
    if unique_targets.__len__() != 400 or missing_targets != ["AF2409"]:
        raise AssertionError(
            f"expected 400/401 target coverage with only Patoo missing; "
            f"got {len(unique_targets)} targets, missing={missing_targets}"
        )
    return assignments


def _write(rows: list[dict[str, object]], cod_rows: list[dict[str, str]],
           assignments: dict[int, tuple[str, str, float]]) -> None:
    cod_by_id = {row["district_id"]: row for row in cod_rows}
    OUT_407.parent.mkdir(parents=True, exist_ok=True)
    with OUT_407.open("w", encoding="utf-8", newline="") as handle:
        fields = list(rows[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    xrows: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for index, source in enumerate(rows):
        target_id, method, confidence = assignments[index]
        target = cod_by_id[target_id]
        record = {
            **source,
            "target_district_id": target_id,
            "target_province": target["province_name"],
            "target_district": target["district_name"],
            "relation": method,
            "name_match_confidence": round(confidence, 6),
        }
        xrows.append(record)
        grouped[target_id].append(record)
    with OUT_XWALK.open("w", encoding="utf-8", newline="") as handle:
        fields = list(xrows[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(xrows)

    out401: list[dict[str, object]] = []
    for target in cod_rows:
        source = grouped.get(target["district_id"], [])
        if not source:
            out401.append({
                "district_id": target["district_id"],
                "province_name": target["province_name"],
                "district_name": target["district_name"],
                "source_district_count": 0,
                "source_population": 0,
                "government_control_index": "",
                "single_source_status": "",
                "coverage": "missing_no_direct_oct2017_rs_observation",
            })
            continue
        population = sum(int(item["population"]) for item in source)
        weighted = sum(
            float(item["government_control_index"]) * int(item["population"])
            for item in source
        ) / max(1, population)
        out401.append({
            "district_id": target["district_id"],
            "province_name": target["province_name"],
            "district_name": target["district_name"],
            "source_district_count": len(source),
            "source_population": population,
            "government_control_index": round(weighted, 8),
            "single_source_status": source[0]["status"] if len(source) == 1 else "",
            "coverage": "direct" if len(source) == 1 else "population_weighted_many_to_one",
        })
    with OUT_401.open("w", encoding="utf-8", newline="") as handle:
        fields = list(out401[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out401)


def main() -> None:
    cod_rows = _read_401()
    if len(cod_rows) != 401:
        raise AssertionError(f"benchmark geography is not 401 districts: {len(cod_rows)}")
    rows = _parse_407(cod_rows)
    assignments = _assign(rows, cod_rows)
    _write(rows, cod_rows, assignments)
    unique = {item[0] for item in assignments.values()}
    print(f"wrote {len(rows)} SIGAR observations -> {len(unique)} of 401 targets")
    print("unobserved 401 target: AF2409 Daykundi/Patoo")
    print(f"crosswalk: {OUT_XWALK}")


if __name__ == "__main__":
    main()
